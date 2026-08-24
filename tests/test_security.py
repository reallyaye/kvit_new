import time
import threading
try:
    import pytest
except ImportError:
    pytest = None
from services.security.auth_service import auth_service
from services.security.rate_limiter import rate_limiter
from services.security.ip_throttler import ip_throttler

def test_auth_service_lifecycle():
    import config
    from services.security.auth_service import hash_password, verify_password_hash

    # Тест: проверка через PBKDF2 хеш
    config.ADMIN_PASSWORD_HASH = hash_password('admin')
    assert auth_service.verify_password('admin') is True
    assert auth_service.verify_password('wrong_password') is False
    assert auth_service.verify_password('') is False
    assert auth_service.verify_password('   ') is False
    assert auth_service.verify_password(None) is False

    # Тест: если в конфигурации пустая строка
    config.ADMIN_PASSWORD_HASH = ''
    assert auth_service.verify_password('') is False
    assert auth_service.verify_password('admin') is False
    assert auth_service.verify_password('   ') is False

    # Тест проверки через сложный PBKDF2 хеш
    h = hash_password('SecretSecure123!')
    assert h.startswith('pbkdf2_sha256$')
    assert verify_password_hash('SecretSecure123!', h) is True
    assert verify_password_hash('wrong', h) is False

    config.ADMIN_PASSWORD_HASH = h
    assert auth_service.verify_password('SecretSecure123!') is True
    assert auth_service.verify_password('admin') is False
    assert auth_service.verify_password('') is False

    token = auth_service.create_session()
    assert len(token) == 64
    assert auth_service.is_valid_session(token) is True
    assert auth_service.is_valid_session('unknown_token') is False

    auth_service.destroy_session(token)
    assert auth_service.is_valid_session(token) is False
    config.ADMIN_PASSWORD_HASH = hash_password('admin')

def test_auth_service_concurrency():
    tokens = []
    def worker():
        for _ in range(20):
            t = auth_service.create_session()
            assert auth_service.is_valid_session(t)
            tokens.append(t)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for th in threads: th.start()
    for th in threads: th.join()

    assert len(tokens) == 100
    for t in tokens:
        auth_service.destroy_session(t)

def test_rate_limiter_sliding_window():
    ip = "192.168.1.55"
    max_req = 3
    window = 1

    allowed, _, _ = rate_limiter.is_allowed('test_b', ip, max_req, window)
    assert allowed is True
    allowed, _, _ = rate_limiter.is_allowed('test_b', ip, max_req, window)
    assert allowed is True
    allowed, _, _ = rate_limiter.is_allowed('test_b', ip, max_req, window)
    assert allowed is True

    # 4-й запрос превышает лимит
    allowed, retry_after, _ = rate_limiter.is_allowed('test_b', ip, max_req, window)
    assert allowed is False
    assert retry_after >= 1

def test_ip_throttler_concurrency_and_burst():
    ip = "10.0.0.99"
    # Создаём изолированный экземпляр для теста
    from services.security.ip_throttler import IPThrottler
    throttler = IPThrottler(max_concurrent=2, burst_rps=3)

    # 1. Проверка concurrency
    ok1, _, _ = throttler.acquire(ip)
    assert ok1 is True
    ok2, _, _ = throttler.acquire(ip)
    assert ok2 is True

    # 3-й одновременный запрос должен быть отклонен
    ok3, reason, _ = throttler.acquire(ip)
    assert ok3 is False
    assert reason == 'concurrency_limit'

    # Освобождаем слот
    throttler.release(ip)
    ok4, _, _ = throttler.acquire(ip)
    assert ok4 is True
    throttler.release(ip)
    throttler.release(ip)

def test_client_ip_anti_spoofing():
    from server import AppRequestHandler
    import config

    class MockHandler(AppRequestHandler):
        def __init__(self, client_ip, headers):
            self.client_address = (client_ip, 12345)
            self.headers = headers

    # 1. TRUST_PROXY = False -> любые X-Forwarded-For игнорируются
    orig_tp = config.TRUST_PROXY
    try:
        config.TRUST_PROXY = False
        h = MockHandler("198.51.100.20", {"X-Forwarded-For": "1.1.1.1, 2.2.2.2"})
        assert h._get_client_ip() == "198.51.100.20"

        # 2. TRUST_PROXY = True, но запрос пришел напрямую НЕ от прокси (198.51.100.20 - публичный IP)
        config.TRUST_PROXY = True
        h2 = MockHandler("198.51.100.20", {"X-Forwarded-For": "1.1.1.1"})
        assert h2._get_client_ip() == "198.51.100.20"

        # 3. TRUST_PROXY = True, запрос пришел от доверенного прокси (127.0.0.1)
        # Клиент отправил спуфленный заголовок "1.1.1.1", прокси добавил реальный IP клиента "203.0.113.50"
        h3 = MockHandler("127.0.0.1", {"X-Forwarded-For": "1.1.1.1, 203.0.113.50"})
        assert h3._get_client_ip() == "203.0.113.50"

        # 4. Прокси цепочка (127.0.0.1 -> 10.0.0.5 -> 203.0.113.99)
        h4 = MockHandler("127.0.0.1", {"X-Forwarded-For": "203.0.113.99, 10.0.0.5"})
        assert h4._get_client_ip() == "203.0.113.99"
    finally:
        config.TRUST_PROXY = orig_tp

def test_safe_import_path_protection():
    import config
    import os
    import tempfile
    import shutil

    test_base = tempfile.mkdtemp(prefix='kvit_sec_test_')
    inside_dir = os.path.join(test_base, 'allowed_folder')
    outside_dir = tempfile.mkdtemp(prefix='kvit_sec_outside_')
    os.makedirs(inside_dir, exist_ok=True)

    orig_allowed = config.ALLOWED_IMPORT_DIRS
    try:
        config.ALLOWED_IMPORT_DIRS = [os.path.realpath(test_base)]

        # 1. Корректный путь внутри разрешенного каталога
        ok, real_p, err = config.is_safe_import_path(inside_dir)
        assert ok is True
        assert real_p == os.path.realpath(inside_dir)
        assert err == ''

        # 2. Попытка сканирования внешнего пути (Path Traversal / Escape)
        ok2, _, err2 = config.is_safe_import_path(outside_dir)
        assert ok2 is False
        assert 'Доступ запрещён' in err2

        # 3. Попытка обхода через относительные пути ..
        escape_path = os.path.join(inside_dir, '..', '..')
        ok3, _, err3 = config.is_safe_import_path(escape_path)
        assert ok3 is False

        # 4. Несуществующая папка
        ok4, _, err4 = config.is_safe_import_path(os.path.join(inside_dir, 'not_found'))
        assert ok4 is False
        assert 'Папка не найдена' in err4
    finally:
        config.ALLOWED_IMPORT_DIRS = orig_allowed
        shutil.rmtree(test_base, ignore_errors=True)
        shutil.rmtree(outside_dir, ignore_errors=True)

def test_grpc_rate_limiting_and_security():
    import grpc
    from services.grpc_service import extract_peer_ip, RateLimitInterceptor
    from services.security import rate_limiter

    # 1. Проверка извлечения IP из peer
    assert extract_peer_ip("ipv4:192.168.1.100:54321") == "192.168.1.100"
    assert extract_peer_ip("ipv6:[2001:db8::1]:54321") == "2001:db8::1"
    assert extract_peer_ip("10.0.0.1:8000") == "10.0.0.1"
    assert extract_peer_ip("") == "127.0.0.1"

    # 2. Проверка работы интерцептора
    interceptor = RateLimitInterceptor(default_limit=2, reconcile_limit=1)

    class MockContext:
        def __init__(self, peer_ip="ipv4:172.20.0.55:12345"):
            self._peer = peer_ip
            self.aborted = False
            self.status_code = None
            self.details = ""

        def peer(self):
            return self._peer

        def abort(self, code, details):
            self.aborted = True
            self.status_code = code
            self.details = details
            raise grpc.RpcError(details)

    class MockCallDetails:
        def __init__(self, method):
            self.method = method
            self.invocation_metadata = []

    def mock_continuation(details):
        def handler(req, ctx):
            return "OK"
        return grpc.unary_unary_rpc_method_handler(handler)

    # Вызовы общего метода (лимит 2)
    details = MockCallDetails("/receipts.ReceiptService/GetAccount")
    wrapped_handler = interceptor.intercept_service(mock_continuation, details)

    ctx1 = MockContext("ipv4:172.20.0.99:1111")
    res1 = wrapped_handler.unary_unary({}, ctx1)
    assert res1 == "OK"
    assert ctx1.aborted is False

    ctx2 = MockContext("ipv4:172.20.0.99:2222")
    res2 = wrapped_handler.unary_unary({}, ctx2)
    assert res2 == "OK"

    # 3-й вызов должен быть заблокирован лимитом
    ctx3 = MockContext("ipv4:172.20.0.99:3333")
    try:
        wrapped_handler.unary_unary({}, ctx3)
    except grpc.RpcError:
        pass
    assert ctx3.aborted is True
    assert ctx3.status_code == grpc.StatusCode.RESOURCE_EXHAUSTED

def test_async_websocket_multiplexer():
    import socket
    import json
    import struct
    from services.websocket.ws_manager import ws_manager

    # Создаем пару связанных сокетов для имитации клиента и сервера
    s_srv, s_cli = socket.socketpair()
    try:
        ws_manager.register(s_srv, "127.0.0.1")
        time.sleep(0.05)

        # 1. Читаем приветственное сообщение на стороне клиента
        data = s_cli.recv(4096)
        assert len(data) > 2
        assert data[0] == 0x81

        # 2. Клиент отправляет WebSocket фрейм с действием ping
        raw_msg = json.dumps({"action": "ping"}).encode('utf-8')
        mask = b'\x12\x34\x56\x78'
        masked_payload = bytes([b ^ mask[i % 4] for i, b in enumerate(raw_msg)])
        frame = struct.pack('!BB', 0x81, 0x80 | len(raw_msg)) + mask + masked_payload
        s_cli.sendall(frame)

        time.sleep(0.1)

        # 3. Читаем ответ pong от единого мультиплексора
        resp = s_cli.recv(4096)
        assert len(resp) > 2
        payload = resp[2:]
        parsed = json.loads(payload.decode('utf-8'))
        assert parsed.get('event') == 'pong'

        # 4. Проверяем широковещательную рассылку broadcast
        ws_manager.broadcast("test_event", {"status": "ok"})
        time.sleep(0.05)
        bc_data = s_cli.recv(4096)
        bc_parsed = json.loads(bc_data[2:].decode('utf-8'))
        assert bc_parsed.get('event') == 'test_event'
        assert bc_parsed.get('data', {}).get('status') == 'ok'
    finally:
        ws_manager.unregister(s_srv)
        s_cli.close()

def test_concurrent_database_writes_with_retry():
    import threading
    import sqlite3
    from database import write_transaction, get_db

    # Создаем тестовую таблицу
    with write_transaction() as con:
        con.execute("CREATE TABLE IF NOT EXISTS test_concurrency(id INTEGER PRIMARY KEY AUTOINCREMENT, val TEXT, thread_id INT)")
        con.execute("DELETE FROM test_concurrency")

    errors = []
    def worker(th_id):
        try:
            for i in range(15):
                with write_transaction() as con:
                    con.execute("INSERT INTO test_concurrency(val, thread_id) VALUES (?, ?)", (f"val_{th_id}_{i}", th_id))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for th in threads: th.start()
    for th in threads: th.join()

    assert len(errors) == 0, f"Ошибки при параллельной записи: {errors}"

    con_read = get_db()
    try:
        count = con_read.execute("SELECT COUNT(*) FROM test_concurrency").fetchone()[0]
        assert count == 8 * 15
    finally:
        con_read.close()

def test_persistent_state_and_session_sharing():
    from services.security.auth_service import AuthService, auth_service
    from services.security.ip_throttler import IPThrottler
    from database import migrate_db
    migrate_db()

    # 1. Тестирование персистентности и разделения сессий (AuthService)
    token = auth_service.create_session()
    assert auth_service.is_valid_session(token) is True

    # Имитируем падение/перезапуск сервиса или запрос на другой реплике (чистим память)
    with auth_service._lock:
        auth_service._sessions.clear()

    # Проверяем, что токен восстанавливается из БД
    assert auth_service.is_valid_session(token) is True

    # Создаем абсолютно новый инстанс (эмуляция запуска 2-го пода/контейнера)
    auth_service_replica_2 = AuthService()
    assert auth_service_replica_2.is_valid_session(token) is True

    # Удаляем сессию и проверяем очистку
    auth_service.destroy_session(token)
    assert auth_service.is_valid_session(token) is False
    assert auth_service_replica_2.is_valid_session(token) is False

    # 2. Тестирование персистентности банов IP (IPThrottler)
    test_ip = "192.168.222.111"
    ip_throttler.ban_ip(test_ip, duration_seconds=120, reason="DDoS Attack Simulation")

    # Имитируем перезапуск (сбрасываем память)
    with ip_throttler._lock:
        ip_throttler._banned_ips.clear()

    allowed, reason, retry_after = ip_throttler.acquire(test_ip)
    assert allowed is False
    assert reason == 'ip_banned'
    assert retry_after > 0

    # Создаем новый инстанс троттлера
    throttler_replica_2 = IPThrottler()
    allowed2, reason2, _ = throttler_replica_2.acquire(test_ip)
    assert allowed2 is False
    assert reason2 == 'ip_banned'

def test_env_crypto_encode_decode():
    from services.security.env_crypto import encode_val, decode_val, encode_env_content, decode_env_content
    from config import _decode_env_val

    raw_secret = "super_secret_token_12345"
    encoded = encode_val(raw_secret)
    assert encoded.startswith("B64:")
    assert decode_val(encoded) == raw_secret
    assert _decode_env_val(encoded) == raw_secret

    sample_env = "PORT=8000\nSECRET_KEY=my_secret\n# Comment line\nFLAG=true"
    encoded_env = encode_env_content(sample_env)
    assert "SECRET_KEY=B64:" in encoded_env
    decoded_env = decode_env_content(encoded_env)
    assert "SECRET_KEY=my_secret" in decoded_env

def test_database_migration_fail_fast():
    """Проверяет, что сбои в миграциях БД не глушатся, а выбрасывают DatabaseMigrationError."""
    import unittest.mock as mock
    from database.migrations import migrate_db, DatabaseMigrationError

    # 1. Штатная миграция проходит успешно
    migrate_db()

    # 2. Имитация критического сбоя (например, повреждение структуры или ошибка доступа)
    with mock.patch("database.connection.sqlite3.connect", side_effect=Exception("Disk I/O failure or permission denied")):
        try:
            migrate_db()
            assert False, "Миграция обязана выбросить DatabaseMigrationError при сбое"
        except DatabaseMigrationError as e:
            assert "Database migration failed" in str(e)

def test_postgres_backend_wrapper_and_dialect():
    """Тестирует PostgresRowWrapper, PostgresCursorWrapper и трансляцию диалекта SQL."""
    from database.postgres_backend import PostgresRowWrapper, PostgresCursorWrapper
    import unittest.mock as mock

    # 1. Тест RowWrapper: доступ по ключу, индексу, .get(), итерация
    data = {"account_number": "800111", "period": "Август 2026", "address": "ул. Мира 5"}
    cols = ["account_number", "period", "address"]
    row = PostgresRowWrapper(data, cols)

    assert row["account_number"] == "800111"
    assert row[0] == "800111"
    assert row[1] == "Август 2026"
    assert row.get("address") == "ул. Мира 5"
    assert row.get("non_existent", "default") == "default"
    assert list(row) == ["800111", "Август 2026", "ул. Мира 5"]
    assert row.keys() == cols

    # 2. Тест CursorWrapper: трансляция плейсхолдеров '?' -> '%s'
    mock_raw_cur = mock.MagicMock()
    cur = PostgresCursorWrapper(mock_raw_cur)
    cur.execute("SELECT * FROM receipts WHERE account_number = ? AND period = ?", ("800111", "2026"))
    mock_raw_cur.execute.assert_called_once_with(
        "SELECT * FROM receipts WHERE account_number = %s AND period = %s",
        ("800111", "2026")
    )

def test_cookie_secure_flags_and_scheme_detection():
    """Тестирует генерацию атрибута Secure в Set-Cookie в зависимости от режима и протокола."""
    from server import AppRequestHandler
    import unittest.mock as mock
    import config

    handler = AppRequestHandler.__new__(AppRequestHandler)
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = {}

    # 1. Режим COOKIE_SECURE='true' -> всегда Secure
    with mock.patch.object(config, "COOKIE_SECURE", "true"):
        hdr = handler._get_session_cookie_header("token123")
        assert "Secure" in hdr
        assert "HttpOnly" in hdr
        assert "SameSite=Strict" in hdr

    # 2. Режим COOKIE_SECURE='false' -> без Secure
    with mock.patch.object(config, "COOKIE_SECURE", "false"):
        hdr = handler._get_session_cookie_header("token123")
        assert "Secure" not in hdr

    # 3. Режим auto + USE_HTTPS=True -> Secure
    with mock.patch.object(config, "COOKIE_SECURE", "auto"), mock.patch.object(config, "USE_HTTPS", True):
        hdr = handler._get_session_cookie_header("token123")
        assert "Secure" in hdr

    # 4. Режим auto + Reverse Proxy (TRUST_PROXY=True + X-Forwarded-Proto: https) -> Secure
    with mock.patch.object(config, "COOKIE_SECURE", "auto"), \
         mock.patch.object(config, "USE_HTTPS", False), \
         mock.patch.object(config, "TRUST_PROXY", True):
        handler.headers = {"X-Forwarded-Proto": "https"}
        assert handler._is_request_https() is True
        hdr = handler._get_session_cookie_header("token123")
        assert "Secure" in hdr

    # 5. Режим auto + Plain HTTP без прокси -> нет Secure (локальный dev)
    with mock.patch.object(config, "COOKIE_SECURE", "auto"), \
         mock.patch.object(config, "USE_HTTPS", False), \
         mock.patch.object(config, "TRUST_PROXY", False):
        handler.headers = {}
        assert handler._is_request_https() is False
        hdr = handler._get_session_cookie_header("token123")
        assert "Secure" not in hdr










