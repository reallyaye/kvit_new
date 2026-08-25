import os
import secrets
import sys
from http.server import ThreadingHTTPServer

import config
from config import GRPC_HOST, GRPC_PORT, HOST, PORT
from database import migrate_db
from logger import logger
from server import AppRequestHandler
from services.grpc_service import create_grpc_server
from services.telegram_bot import telegram_bot_service
from services.websocket import ws_manager


def main():
    logger.info("Запуск приложения...")

    # 1. Проверка обязательного ключа подписи сессий и CSRF-токенов
    if not config.SECRET_KEY:
        suggested_secret = secrets.token_hex(32)
        logger.error("=" * 70)
        logger.error("❌ ОШИБКА БЕЗОПАСНОСТИ: Переменная SECRET_KEY не задана!")
        logger.error("Ключ SECRET_KEY обязателен для безопасной криптографической подписи CSRF-токенов и сессий.")
        logger.error("Сгенерирован криптостойкий ключ для вашего файла .env:\n")
        logger.error(f"    SECRET_KEY={suggested_secret}\n")
        logger.error("Добавьте эту строку в файл .env и перезапустите приложение.")
        logger.error("=" * 70)
        sys.exit(1)

    # 2. Проверка обязательного секрета gRPC
    if not config.GRPC_API_KEY:
        suggested_key = secrets.token_hex(32)
        logger.error("=" * 70)
        logger.error("❌ ОШИБКА КОНФИГУРАЦИИ: Переменная GRPC_API_KEY не задана!")
        logger.error("Для безопасности gRPC микросервис не может запускаться без секретного ключа.")
        logger.error("Сгенерирован криптостойкий ключ для вашего файла .env:\n")
        logger.error(f"    GRPC_API_KEY={suggested_key}\n")
        logger.error("Добавьте эту строку в файл .env и перезапустите приложение.")
        logger.error("=" * 70)
        sys.exit(1)

    # 3. Проверка обязательного хеша пароля администратора (хранение открытых паролей запрещено)
    if not config.ADMIN_PASSWORD_HASH:
        from services.security.auth_service import hash_password
        # Если случайно был передан открытый пароль, помогаем пользователю его захешировать
        raw_pass = os.environ.get('ADMIN_PASSWORD', '').strip()
        sample_pass = raw_pass if raw_pass else secrets.token_urlsafe(12)
        sample_hash = hash_password(sample_pass)
        logger.error("=" * 70)
        logger.error("❌ ОШИБКА БЕЗОПАСНОСТИ: Переменная ADMIN_PASSWORD_HASH не задана!")
        logger.error("Хранение паролей в открытом виде (ADMIN_PASSWORD) запрещено в продакшене.")
        logger.error("Сгенерирован криптостойкий PBKDF2-хеш для вашего пароля:")
        if not raw_pass:
            logger.error(f"\n    Пароль: {sample_pass}")
        logger.error(f"    ADMIN_PASSWORD_HASH={sample_hash}\n")
        logger.error("Добавьте строку ADMIN_PASSWORD_HASH в файл .env и перезапустите приложение.")
        logger.error("=" * 70)
        sys.exit(1)

    # 3. Автоматические миграции базы данных
    try:
        migrate_db()
        logger.info("Миграции базы данных проверены.")
    except Exception as e:
        logger.critical("=" * 70)
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Сбой применения миграций БД: {e}")
        logger.critical("Запуск приложения остановлен во избежание повреждения данных.")
        logger.critical("=" * 70)
        sys.exit(1)

    # 4. Инициализация и запуск gRPC сервера
    grpc_server = create_grpc_server(host=GRPC_HOST, port=GRPC_PORT)
    grpc_server.start()

    # 5. Инициализация и запуск Telegram-бота (если задан TELEGRAM_BOT_TOKEN)
    if config.TELEGRAM_ENABLED:
        telegram_bot_service.start_in_thread()

    # 6. Инициализация и запуск многопоточного HTTP/WebSocket сервера
    ThreadingHTTPServer.allow_reuse_address = True
    http_server = ThreadingHTTPServer((HOST, PORT), AppRequestHandler)
    http_server.daemon_threads = True

    protocol = "http"
    is_tls = False
    if config.USE_HTTPS or (config.SSL_CERT_PATH and config.SSL_KEY_PATH):
        if os.path.isfile(config.SSL_CERT_PATH) and os.path.isfile(config.SSL_KEY_PATH):
            import ssl
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(certfile=config.SSL_CERT_PATH, keyfile=config.SSL_KEY_PATH)
            http_server.socket = ssl_ctx.wrap_socket(http_server.socket, server_side=True)
            protocol = "https"
            is_tls = True
        else:
            logger.error(f"❌ ОШИБКА TLS: Файлы сертификатов не найдены: cert='{config.SSL_CERT_PATH}', key='{config.SSL_KEY_PATH}'")
            sys.exit(1)

    def _get_local_ip():
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    local_ip = _get_local_ip()
    logger.info(f"Веб-сервер ({protocol.upper()}):     {protocol}://{HOST}:{PORT}")
    if HOST in ('0.0.0.0', '::') and local_ip not in ('127.0.0.1', '0.0.0.0'):
        logger.info(f"  ➜ Локально на этом ПК:   {protocol}://localhost:{PORT}")
        logger.info(f"  ➜ С других ПК в сети:    {protocol}://{local_ip}:{PORT}")
    logger.info(f"WebSocket шлюз:      {'wss' if is_tls else 'ws'}://{HOST}:{PORT}/ws (Async Multiplexed)")
    logger.info(f"gRPC микросервис:    {GRPC_HOST}:{GRPC_PORT} (TLS={'ON' if config.GRPC_USE_TLS else 'OFF'})")
    if config.TELEGRAM_ENABLED:
        logger.info("Telegram-бот:        ВКЛЮЧЕН (фоновый поток Long Polling)")
    else:
        logger.info("Telegram-бот:        ВЫКЛЮЧЕН (не задан TELEGRAM_BOT_TOKEN в .env)")
    if config.TRUST_PROXY:
        logger.info("Режим Reverse Proxy: TLS терминируется внешним прокси (Nginx/IIS/Traefik).")
    elif not is_tls:
        logger.info("Архитектура: сервис ожидает Reverse Proxy (Nginx/IIS) с TLS-терминацией перед собой.")
    logger.info("Система безопасности: IDOR Token, Rate Limiter, IP Throttler, gRPC Auth, WS Timeout")

    import time

    running = True
    try:
        while running:
            try:
                shut_down_event = getattr(http_server, '_BaseServer__is_shut_down', None)
                if shut_down_event is not None:
                    shut_down_event.clear()
                http_server.serve_forever()
            except KeyboardInterrupt:
                running = False
                break
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                time.sleep(0.1)
                continue
            except Exception as loop_err:
                logger.warning(f"Внутренний сбой HTTP-сервера ({loop_err}), автоматический перезапуск потока...")
                time.sleep(0.5)
                continue
    except KeyboardInterrupt:
        logger.info("Остановка серверов по сигналу завершения...")
    except BaseException as e:
        import traceback
        logger.critical(f"Необработанное исключение: {e}\n{traceback.format_exc()}")
    finally:
        try:
            http_server.server_close()
        except Exception:
            pass
        ws_manager.stop()
        telegram_bot_service.stop()
        grpc_server.stop(grace=1)
        logger.info("Все серверы успешно остановлены.")


if __name__ == '__main__':
    main()

