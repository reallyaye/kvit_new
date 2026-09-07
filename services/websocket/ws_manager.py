import json
import os
import selectors
import socket
import struct
import threading
import time
import uuid

import config
from config import WS_SOCKET_TIMEOUT
from logger import logger

try:
    import redis
    REDIS_LIB_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_LIB_AVAILABLE = False


class WebSocketClientState:
    def __init__(self, sock: socket.socket, client_ip: str):
        self.sock = sock
        self.client_ip = client_ip
        self.buf = bytearray()
        self.last_active = time.time()

    @property
    def buffer(self):
        return self.buf

    @buffer.setter
    def buffer(self, v):
        self.buf = v

class WebSocketManager:
    """
    Высокопроизводительный асинхронный менеджер WebSocket на базе неблокирующего
    I/O мультиплексирования (selectors / Reactor Pattern) и межпроцессной шины событий
    на базе Redis Pub/Sub для многорепличного развертывания.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._selector = selectors.DefaultSelector()
        self._clients = {}  # {fileno: WebSocketClientState}
        self._running = True
        self._last_cleanup = time.time()
        self._node_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self._redis_pub = None
        self._loop_thread = threading.Thread(target=self._event_loop, daemon=True, name="WebSocketEventLoop")
        self._loop_thread.start()

        if getattr(config, 'REDIS_ENABLED', False) and REDIS_LIB_AVAILABLE:
            self._redis_sub_thread = threading.Thread(
                target=self._redis_subscriber_loop,
                daemon=True,
                name="WebSocketRedisSub"
            )
            self._redis_sub_thread.start()

    def handle_connection(self, client_sock: socket.socket, client_ip: str = "127.0.0.1"):
        """
        Управляет жизненным циклом WebSocket соединения в рабочем потоке запроса.
        Регистрирует клиента в общем пуле для broadcast и обрабатывает входящие фреймы.
        """
        client_sock.settimeout(WS_SOCKET_TIMEOUT)
        state = WebSocketClientState(client_sock, client_ip)
        with self._lock:
            self._clients[client_sock.fileno()] = state

        logger.info(f"[WS] Клиент {client_ip} подключен (всего онлайн: {len(self._clients)})")
        self.send(client_sock, 'connected', {'message': 'WebSocket соединение установлено'})

        try:
            while self._running:
                try:
                    chunk = client_sock.recv(4096)
                    if not chunk:
                        break
                    state.buf.extend(chunk)
                    state.last_active = time.time()
                    self._process_frames(state)
                except socket.timeout:
                    # Отправляем Ping для поддержания соединения (keep-alive)
                    try:
                        ping_frame = struct.pack('!BB', 0x89, 0)
                        client_sock.sendall(ping_frame)
                    except Exception:
                        break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                    break
                except Exception as e:
                    logger.error(f"[WS] Ошибка в соединении {client_ip}: {e}")
                    break
        finally:
            self.unregister(client_sock)

    def register(self, client_sock: socket.socket, client_ip: str = "127.0.0.1"):
        """Регистрирует новый WebSocket сокет в селекторе."""
        client_sock.setblocking(False)
        state = WebSocketClientState(client_sock, client_ip)
        with self._lock:
            try:
                self._selector.register(client_sock, selectors.EVENT_READ, data=state)
                self._clients[client_sock.fileno()] = state
            except Exception as e:
                logger.error(f"[WS] Ошибка регистрации клиента {client_ip}: {e}")
                try:
                    client_sock.close()
                except Exception:
                    pass
                return
        self.send(client_sock, 'connected', {'message': 'WebSocket соединение установлено'})
        logger.info(f"[WS] Клиент {client_ip} успешно зарегистрирован (всего онлайн: {len(self._clients)})")

    def unregister(self, client_sock: socket.socket):
        """Отключает и удаляет сокет из активных клиентов и селектора."""
        with self._lock:
            fn = client_sock.fileno()
            if fn in self._clients:
                state = self._clients.pop(fn)
                try:
                    self._selector.unregister(client_sock)
                except Exception:
                    pass
                try:
                    client_sock.close()
                except Exception:
                    pass
                logger.info(f"[WS] Клиент {state.client_ip} отключен (осталось онлайн: {len(self._clients)})")

    def _get_redis_publisher(self):
        if not getattr(config, 'REDIS_ENABLED', False) or not REDIS_LIB_AVAILABLE:
            return None
        if self._redis_pub is None:
            try:
                redis_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
                self._redis_pub = redis.Redis.from_url(redis_url, socket_timeout=2.0)
            except Exception as e:
                logger.debug(f"[WS] Не удалось инициализировать Redis publisher: {e}")
        return self._redis_pub

    def _redis_subscriber_loop(self):
        """Фоновый поток подписки на события WebSocket из распределенной шины Redis."""
        redis_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
        channel = getattr(config, 'REDIS_WS_CHANNEL', 'kvit:events:ws')
        while self._running:
            try:
                sub_client = redis.Redis.from_url(redis_url, socket_timeout=5.0)
                pubsub = sub_client.pubsub()
                pubsub.subscribe(channel)
                logger.info(f"[WS] Подписка на шину Redis Pub/Sub активна ({channel})")
                for msg in pubsub.listen():
                    if not self._running:
                        break
                    if msg and msg.get('type') == 'message':
                        raw_data = msg.get('data')
                        if isinstance(raw_data, bytes):
                            raw_data = raw_data.decode('utf-8', errors='replace')
                        try:
                            payload_obj = json.loads(raw_data)
                            if payload_obj.get('origin_node') == self._node_id:
                                continue  # Уже отправлено локальным клиентам на этом узле
                            evt = payload_obj.get('event', '')
                            data = payload_obj.get('data', {})
                            self._local_broadcast(evt, data)
                        except Exception as parse_err:
                            logger.error(f"[WS] Ошибка парсинга события из Redis: {parse_err}")
            except Exception as e:
                if not self._running:
                    break
                logger.debug(f"[WS] Ошибка подписки на Redis Pub/Sub, переподключение через 2с: {e}")
                time.sleep(2.0)

    def _local_broadcast(self, event_type: str, payload: dict = None):
        """Отправляет JSON-событие всем локально активным WebSocket-клиентам без риска deadlock."""
        msg_data = json.dumps({'event': event_type, 'data': payload or {}, 'timestamp': time.time()}, ensure_ascii=False)
        frame = self._encode_frame(msg_data)
        dead_clients = []
        with self._lock:
            for _fn, state in list(self._clients.items()):
                try:
                    state.sock.sendall(frame)
                except Exception:
                    dead_clients.append(state.sock)

        # Вызов unregister строго за пределами lock для предотвращения deadlock
        for sock in dead_clients:
            self.unregister(sock)

    def broadcast(self, event_type: str, payload: dict = None, publish_to_redis: bool = True):
        """Отправляет JSON-событие всем активным WebSocket-клиентам и публикует в Redis Pub/Sub."""
        self._local_broadcast(event_type, payload)

        if publish_to_redis and getattr(config, 'REDIS_ENABLED', False) and REDIS_LIB_AVAILABLE:
            pub = self._get_redis_publisher()
            if pub:
                try:
                    channel = getattr(config, 'REDIS_WS_CHANNEL', 'kvit:events:ws')
                    msg = json.dumps({
                        'event': event_type,
                        'data': payload or {},
                        'timestamp': time.time(),
                        'origin_node': self._node_id
                    }, ensure_ascii=False)
                    pub.publish(channel, msg)
                except Exception as e:
                    logger.debug(f"[WS] Ошибка публикации события в Redis Pub/Sub: {e}")

    def send(self, client_sock: socket.socket, event_type: str, payload: dict = None):
        """Отправляет событие конкретному клиенту."""
        msg_data = json.dumps({'event': event_type, 'data': payload or {}, 'timestamp': time.time()}, ensure_ascii=False)
        frame = self._encode_frame(msg_data)
        try:
            client_sock.sendall(frame)
        except Exception:
            self.unregister(client_sock)

    @staticmethod
    def _encode_frame(text: str, opcode: int = 0x1) -> bytes:
        """Кодирует фрейм WebSocket (RFC 6455)."""
        payload = text.encode('utf-8')
        length = len(payload)
        first_byte = 0x80 | (opcode & 0x0F)
        if length <= 125:
            header = struct.pack('!BB', first_byte, length)
        elif length <= 65535:
            header = struct.pack('!BBH', first_byte, 126, length)
        else:
            header = struct.pack('!BBQ', first_byte, 127, length)
        return header + payload

    def _cleanup_idle_clients(self, now):
        with self._lock:
            timed_out = [
                st.sock for st in self._clients.values()
                if now - st.last_active > WS_SOCKET_TIMEOUT
            ]
        for sock in timed_out:
            self.unregister(sock)

    def _event_loop(self):
        """Единый фоновый поток мультиплексирования ввода/вывода для всех подключений."""
        while self._running:
            try:
                # На Windows select.select() на пустом селекторе падает с WinError 10022
                with self._lock:
                    has_clients = bool(self._clients)
                if not has_clients:
                    time.sleep(0.05)
                    continue

                events = self._selector.select(timeout=0.2)
                now = time.time()
                for key, _mask in events:
                    state: WebSocketClientState = key.data
                    sock = state.sock
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            self.unregister(sock)
                            continue
                        state.buf.extend(chunk)
                        state.last_active = now
                        self._process_frames(state)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except Exception:
                        self.unregister(sock)

                # Периодическая проверка неактивных клиентов раз в 10 секунд
                if now - self._last_cleanup > 10.0:
                    self._cleanup_idle_clients(now)
                    self._last_cleanup = now
            except Exception:
                time.sleep(0.05)

    def _process_frames(self, state: WebSocketClientState):
        """Парсит накопленный буфер фреймов WebSocket по RFC 6455."""
        MAX_FRAME_SIZE = 16 * 1024 * 1024
        while True:
            # Если буфер клиента превысил допустимый лимит — отключаем клиента во избежание DoS / исчерпания памяти
            if len(state.buf) > MAX_FRAME_SIZE:
                logger.warning("[WS] Превышен максимальный лимит фрейма WebSocket (16MB). Принудительное закрытие соединения.")
                self.unregister(state.sock)
                return

            if len(state.buf) < 2:
                break

            b1 = state.buf[0]
            b2 = state.buf[1]

            opcode = b1 & 0x0F
            masked = (b2 & 0x80) != 0
            payload_len = b2 & 0x7F
            header_offset = 2

            if payload_len == 126:
                if len(state.buf) < 4:
                    return
                payload_len = struct.unpack('!H', state.buf[2:4])[0]
                header_offset = 4
            elif payload_len == 127:
                if len(state.buf) < 10:
                    return
                payload_len = struct.unpack('!Q', state.buf[2:10])[0]
                header_offset = 10

            if payload_len > MAX_FRAME_SIZE or payload_len < 0:
                try:
                    state.sock.close()
                except Exception:
                    pass
                self.unregister(state.sock)
                return

            mask_len = 4 if masked else 0
            total_frame_len = header_offset + mask_len + payload_len

            if len(state.buf) < total_frame_len:
                return  # Ждем прихода остальных байтов фрейма

            frame_data = state.buf[:total_frame_len]
            state.buf = state.buf[total_frame_len:]

            payload = frame_data[header_offset + mask_len:]
            if masked:
                mask = frame_data[header_offset:header_offset + 4]
                payload = bytes([b ^ mask[i % 4] for i, b in enumerate(payload)])

            # 0x8 - Close
            if opcode == 0x8:
                self.unregister(state.sock)
                return
            # 0x9 - Ping -> Pong
            elif opcode == 0x9:
                pong = struct.pack('!BB', 0x8A, 0)
                try:
                    state.sock.sendall(pong)
                except Exception:
                    self.unregister(state.sock)
                    return
            # 0x1 - Text Frame
            elif opcode == 0x1:
                try:
                    text_data = payload.decode('utf-8')
                    msg = json.loads(text_data)
                    action = msg.get('action')
                    if action == 'ping':
                        self.send(state.sock, 'pong', {})
                    elif action == 'get_stats':
                        from services.receipts import receipt_service
                        total_acc, total_rec = receipt_service.get_stats()
                        self.send(state.sock, 'stats', {'total_accounts': total_acc, 'total_receipts': total_rec})
                except Exception:
                    pass

    def stop(self):
        """Останавливает селектор и закрывает все сокеты."""
        self._running = False
        with self._lock:
            for sock in list(self._clients.values()):
                try:
                    sock.sock.close()
                except OSError:
                    pass
            self._clients.clear()
            try:
                self._selector.close()
            except OSError:
                pass

ws_manager = WebSocketManager()

