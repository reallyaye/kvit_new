# -*- coding: utf-8 -*-
"""
tests/test_wave5_hardening.py: Проверка защиты от DoS по размеру тела запроса (Wave 5).
Проверяет:
1. Защиту /login от oversized тела (413 Payload Too Large).
2. Отклонение невалидных / отрицательных Content-Length (400 Bad Request) без traceback.
3. Поддержку и лимиты Transfer-Encoding: chunked.
4. Безопасное ограничение размера стандартных POST-форм и CMS HTML-страниц.
5. Защиту multipart-парсера для медиа от превышения лимитов и атак с избыточным числом секций.
"""

import io

import config
from server import AppRequestHandler
from services.security.request_guards import (
    parse_bounded_form,
    parse_bounded_multipart,
    read_bounded_body,
)


class DummyMockHandler:
    """Легковесный мок обработчика HTTP-запроса."""

    def __init__(self, headers=None, body_bytes=b"", path="/login"):
        self.headers = headers or {}
        self.rfile = io.BytesIO(body_bytes)
        self.path = path
        self.last_error_code = None
        self.last_error_message = None
        self.sent_html = None
        self.sent_json = None
        self.sent_code = None

    def _get_client_ip(self):
        return "127.0.0.1"

    def _is_admin(self):
        return False

    def send_html(self, text, code=200, extra_headers=None):
        self.sent_html = text
        self.sent_code = code

    def send_json(self, data, code=200, extra_headers=None):
        self.sent_json = data
        self.sent_code = code

    def send_error(self, code, message=None):
        self.sent_code = code
        self.last_error_message = message


def test_login_oversized_payload_rejected_413():
    """Большое тело /login отклоняется кодом 413 без чтения в память."""
    oversized_len = config.MAX_LOGIN_BODY_BYTES + 4096
    handler = DummyMockHandler(
        headers={'Content-Length': str(oversized_len)},
        body_bytes=b"username=admin&password=" + (b"A" * oversized_len),
        path="/login"
    )

    data = read_bounded_body(handler, max_bytes=config.MAX_LOGIN_BODY_BYTES)
    assert data is None
    assert handler.last_error_code == 413
    assert handler.sent_code == 413
    assert "413" in (handler.sent_html or "")


def test_login_valid_payload_accepted():
    """Валидный запрос /login успешно считывается."""
    valid_body = b"username=admin&password=secretpassword"
    handler = DummyMockHandler(
        headers={'Content-Length': str(len(valid_body))},
        body_bytes=valid_body,
        path="/login"
    )

    data = read_bounded_body(handler, max_bytes=config.MAX_LOGIN_BODY_BYTES)
    assert data == valid_body
    assert handler.last_error_code is None


def test_invalid_content_length_rejected_400():
    """Невалидный, отрицательный или отсутствующий Content-Length возвращает 400 без исключений."""
    # 1. Нечисловой Content-Length
    h1 = DummyMockHandler(headers={'Content-Length': 'invalid_number'}, body_bytes=b"test")
    res1 = read_bounded_body(h1, max_bytes=1024)
    assert res1 is None
    assert h1.last_error_code == 400

    # 2. Отрицательный Content-Length
    h2 = DummyMockHandler(headers={'Content-Length': '-500'}, body_bytes=b"test")
    res2 = read_bounded_body(h2, max_bytes=1024)
    assert res2 is None
    assert h2.last_error_code == 400

    # 3. Отсутствующий Content-Length
    h3 = DummyMockHandler(headers={}, body_bytes=b"test")
    res3 = read_bounded_body(h3, max_bytes=1024)
    assert res3 is None
    assert h3.last_error_code == 400


def test_chunked_transfer_encoding_reading_and_limits():
    """Проверка корректности и лимитов для Transfer-Encoding: chunked."""
    # 1. Корректный chunked поток
    # Chunks: 'Hello ' (6 байт = 0x6) + 'World!' (6 байт = 0x6) + end (0x0)
    chunked_data = b"6\r\nHello \r\n6\r\nWorld!\r\n0\r\n\r\n"
    h_chunked = DummyMockHandler(
        headers={'Transfer-Encoding': 'chunked'},
        body_bytes=chunked_data,
        path="/api/test"
    )
    res = read_bounded_body(h_chunked, max_bytes=1024)
    assert res == b"Hello World!"
    assert h_chunked.last_error_code is None

    # 2. Превышение лимита для chunked потока
    oversized_chunk = b"10\r\n0123456789ABCDEF\r\n0\r\n\r\n"
    h_oversized = DummyMockHandler(
        headers={'Transfer-Encoding': 'chunked'},
        body_bytes=oversized_chunk,
        path="/api/test"
    )
    res_oversized = read_bounded_body(h_oversized, max_bytes=10)
    assert res_oversized is None
    assert h_oversized.last_error_code == 413
    assert h_oversized.sent_code == 413

    # 3. Некорректный chunked поток (битый hex размер)
    bad_chunk = b"ZZ\r\nData\r\n0\r\n\r\n"
    h_bad = DummyMockHandler(
        headers={'Transfer-Encoding': 'chunked'},
        body_bytes=bad_chunk,
        path="/api/test"
    )
    res_bad = read_bounded_body(h_bad, max_bytes=1024)
    assert res_bad is None
    assert h_bad.last_error_code == 400


def test_form_params_bounded_parsing():
    """Форма application/x-www-form-urlencoded с ограничением размера."""
    raw_form = b"key1=val1&key2=val2"
    h_form = DummyMockHandler(
        headers={'Content-Length': str(len(raw_form))},
        body_bytes=raw_form
    )
    parsed = parse_bounded_form(h_form, max_bytes=1024)
    assert parsed == {'key1': ['val1'], 'key2': ['val2']}

    # Oversized форма
    h_oversized_form = DummyMockHandler(
        headers={'Content-Length': str(config.MAX_FORM_BODY_BYTES + 100)},
        body_bytes=b"a=b"
    )
    parsed_oversized = parse_bounded_form(h_oversized_form, max_bytes=config.MAX_FORM_BODY_BYTES)
    assert parsed_oversized == {}
    assert h_oversized_form.last_error_code == 413


def test_multipart_bounded_parsing_limits():
    """Multipart-парсер проверяет ограничения размера и структуры."""
    boundary = "----TestBoundaryXYZ"
    multipart_body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="title"\r\n\r\n'
        "Sample Title\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "File text content\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    h_mp = DummyMockHandler(
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(multipart_body))
        },
        body_bytes=multipart_body
    )
    fields, files = parse_bounded_multipart(h_mp, max_bytes=1024 * 1024)
    assert fields.get('title') == ['Sample Title']
    assert len(files) == 1
    assert files[0][0] == 'file'
    assert files[0][1] == 'test.txt'
    assert files[0][2] == b"File text content"

    # Превышение лимита для multipart
    h_oversized_mp = DummyMockHandler(
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(1024 * 1024)
        },
        body_bytes=multipart_body
    )
    fields_over, files_over = parse_bounded_multipart(h_oversized_mp, max_bytes=100)
    assert fields_over == {}
    assert files_over == []
    assert h_oversized_mp.last_error_code == 413


def test_app_request_handler_integration():
    """Интеграция методов _read_bounded_body и _read_form_params в AppRequestHandler."""
    class TestHandler(AppRequestHandler):
        def __init__(self, c_len, body_bytes=b""):
            self.headers = {'Content-Length': str(c_len)}
            self.rfile = io.BytesIO(body_bytes)
            self.path = "/test"
            self.last_error_code = None
            self.last_error_message = None
            self.wfile = io.BytesIO()

        def send_error(self, code, message=None):
            self.last_error_code = code
            self.last_error_message = message

        def send_html(self, text, code=200, extra_headers=None):
            self.last_error_code = code

    # Проверка вызова через экземпляр AppRequestHandler
    th = TestHandler(c_len=50000)
    data = th._read_bounded_body(max_bytes=16384)
    assert data is None
    assert th.last_error_code == 413
