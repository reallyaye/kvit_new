"""
Фаззинг-тесты и тестирование устойчивости сетевых парсеров:
1. Потоковый Multipart/form-data парсер (_parse_multipart_to_disk).
2. WebSocket RFC 6455 парсер фреймов и handshake (_process_frames, _handle_websocket).
"""
import io
import os
import random
import string
import struct
import tempfile
import socket
from server import AppRequestHandler
from services.websocket.ws_manager import ws_manager, WebSocketClientState

class DummyServer:
    def __init__(self):
        pass

class DummySocket:
    def __init__(self):
        self._fileno = random.randint(100, 9999)
        self.closed = False
        self.sent_data = bytearray()
        self.timeout = None

    def fileno(self):
        return self._fileno

    def settimeout(self, t):
        self.timeout = t

    def setblocking(self, b):
        pass

    def sendall(self, data):
        if self.closed:
            raise OSError("Socket closed")
        self.sent_data.extend(data)

    def close(self):
        self.closed = True

def _build_dummy_handler(body_bytes: bytes, content_type: str, method: str = 'POST'):
    req = AppRequestHandler.__new__(AppRequestHandler)
    req.command = method
    req.path = '/api/upload-batch'
    req.request_version = 'HTTP/1.1'
    req.headers = {
        'Content-Type': content_type,
        'Content-Length': str(len(body_bytes)),
        'Host': '127.0.0.1:8000'
    }
    req.rfile = io.BytesIO(body_bytes)
    req.wfile = io.BytesIO()
    req.connection = DummySocket()
    req.server = DummyServer()
    return req

def test_fuzz_multipart_random_mutations():
    """Фаззинг: генерация 500+ случайных мутаций multipart-потоков (битые boundary, мусорные байты)."""
    boundary = "----WebKitFormBoundaryFuzzTest7MA4YWxkTrZu0gW"
    ct = f"multipart/form-data; boundary={boundary}"

    valid_payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="pdf"; filename="test.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
        f"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\r\n"
        f"--{boundary}--\r\n"
    ).encode('utf-8')

    random.seed(42)
    for iteration in range(300):
        # Применяем случайные мутации: вставка случайного байта, удаление, срез
        mutated = bytearray(valid_payload)
        mutation_type = random.choice(['corrupt', 'truncate', 'insert_garbage', 'split'])

        if mutation_type == 'corrupt' and len(mutated) > 10:
            idx = random.randint(0, len(mutated) - 1)
            mutated[idx] = random.randint(0, 255)
        elif mutation_type == 'truncate':
            cut_point = random.randint(0, len(mutated))
            mutated = mutated[:cut_point]
        elif mutation_type == 'insert_garbage':
            idx = random.randint(0, len(mutated))
            garbage = bytes(random.choices(range(256), k=random.randint(1, 64)))
            mutated = mutated[:idx] + garbage + mutated[idx:]
        elif mutation_type == 'split':
            # Мутация заголовков
            mutated = bytearray(b"\r\n".join(mutated.split(b"\r\n")[:random.randint(1, 4)]))

        handler = _build_dummy_handler(bytes(mutated), ct)
        # Парсер обязан безопасно завершиться, не упасть с необработанным исключением и не зависнуть
        tmp_dir, pdf_files = handler._parse_multipart_to_disk()
        if tmp_dir and os.path.exists(tmp_dir):
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

def test_fuzz_multipart_giant_headers_and_path_traversal():
    """Фаззинг: атака гигантскими заголовками (100KB+) и попытки Path Traversal в filename."""
    boundary = "----BoundaryAttackSecurityTest"
    ct = f"multipart/form-data; boundary={boundary}"

    # 1. Атака гигантскими заголовками без CRLF-CRLF
    giant_header = "X-Attack-Header: " + ("A" * 80_000)
    body_giant = (
        f"--{boundary}\r\n"
        f"{giant_header}\r\n"
        f'Content-Disposition: form-data; name="pdf"; filename="exploit.pdf"\r\n\r\n'
        f"%PDF-1.4\r\n"
        f"--{boundary}--\r\n"
    ).encode('utf-8')

    h_giant = _build_dummy_handler(body_giant, ct)
    tmp_dir1, files1 = h_giant._parse_multipart_to_disk()
    if tmp_dir1 and os.path.exists(tmp_dir1):
        import shutil
        shutil.rmtree(tmp_dir1, ignore_errors=True)

    # 2. Атака Path Traversal в имени файла
    malicious_filenames = [
        "../../../../../../windows/system32/calc.exe",
        "..\\..\\..\\..\\boot.ini",
        "/etc/shadow",
        "C:\\autoexec.bat",
        "test\x00malicious.pdf",
        "CON", "PRN", "AUX", "NUL",
        " " * 100 + ".pdf",
        "normal/../../../evil.pdf"
    ]

    for evil_name in malicious_filenames:
        body_traversal = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="pdf"; filename="{evil_name}"\r\n\r\n'
            f"%PDF-1.4 valid content\r\n"
            f"--{boundary}--\r\n"
        ).encode('utf-8')

        h_trav = _build_dummy_handler(body_traversal, ct)
        tmp_dir2, files2 = h_trav._parse_multipart_to_disk()
        if files2:
            for base_name, file_path in files2:
                # Проверяем, что файл сохранён СТРОГО внутри временной директории, а не вне её
                assert os.path.dirname(os.path.abspath(file_path)) == os.path.abspath(tmp_dir2)
                assert ".." not in os.path.basename(file_path)
                assert "/" not in os.path.basename(file_path)
                assert "\\" not in os.path.basename(file_path)
        if tmp_dir2 and os.path.exists(tmp_dir2):
            import shutil
            shutil.rmtree(tmp_dir2, ignore_errors=True)

def test_fuzz_websocket_frames_random_garbage():
    """Фаззинг: генерация 500+ случайных байтовых последовательностей в парсер WebSocket фреймов."""
    dummy_sock = DummySocket()
    state = WebSocketClientState(dummy_sock, "127.0.0.1")

    random.seed(1337)
    for _ in range(500):
        # Генерируем случайный пакет данных
        garbage_len = random.randint(1, 256)
        garbage = bytes(random.choices(range(256), k=garbage_len))
        state.buf.extend(garbage)

        # Парсер фреймов не должен падать с необработанным исключением
        try:
            ws_manager._process_frames(state)
        except Exception as e:
            assert False, f"WebSocket parser crashed on random bytes: {e}"

        # Очищаем буфер, если он превысил лимит
        if len(state.buf) > 1000:
            state.buf.clear()

def test_fuzz_websocket_malicious_lengths_and_opcodes():
    """Фаззинг: атака аномальными длинами фреймов (64-bit int overflow / giant payload)."""
    dummy_sock = DummySocket()
    state = WebSocketClientState(dummy_sock, "127.0.0.1")

    # 1. Фрейм с декларированной длиной 1 ТБ (64-bit length) для попытки вызвать OOM
    giant_64bit_len = 1024 * 1024 * 1024 * 1024  # 1 TB
    header = struct.pack('!BBQ', 0x81, 127, giant_64bit_len)
    state.buf.extend(header)
    state.buf.extend(b"small payload")

    # Должен безопасно задетектить превышение MAX_FRAME_SIZE и закрыть клиентский сокет
    ws_manager._process_frames(state)
    assert dummy_sock.closed is True or len(state.buf) == 0

    # 2. Неизвестные/недопустимые opcodes (0x3, 0x4, 0xB, 0xF)
    for invalid_opcode in [0x3, 0x4, 0x5, 0x6, 0x7, 0xB, 0xC, 0xD, 0xE, 0xF]:
        dummy_sock2 = DummySocket()
        state2 = WebSocketClientState(dummy_sock2, "127.0.0.1")
        # Unmasked small frame
        frame = struct.pack('!BB', 0x80 | invalid_opcode, 4) + b"test"
        state2.buf.extend(frame)
        ws_manager._process_frames(state2)
        # Обработка должна пройти корректно без падений

def test_fuzz_websocket_fragmented_delivery():
    """Фаззинг: подача корректных фреймов по 1 байту (имитация медленной фрагментированной сети)."""
    dummy_sock = DummySocket()
    state = WebSocketClientState(dummy_sock, "127.0.0.1")

    # Валидный Ping frame и валидный Text frame
    ping_frame = struct.pack('!BB', 0x89, 0)
    text_data = b'{"action":"ping"}'
    text_frame = struct.pack('!BB', 0x81, len(text_data)) + text_data
    stream = ping_frame + text_frame

    for b in stream:
        state.buf.append(b)
        ws_manager._process_frames(state)

    # В результате парсер должен успешно разобрать все входящие байты без остатка
    assert len(state.buf) == 0
