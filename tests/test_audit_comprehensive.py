import io
import os
import shutil
import socket
import struct
import tempfile

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

from config import get_receipt_shard_parts
from database import get_db
from server import AppRequestHandler
from services.pdf.pdf_processor import pdf_processor
from services.receipts.receipt_service import receipt_service
from services.reconciliation.reconcile_service import reconcile_service
from services.security import auth_service, ip_throttler
from services.websocket import ws_manager


def create_test_pdf(file_path: str, pages_data: list):
    doc = fitz.open()
    for text in pages_data:
        page = doc.new_page()
        page.insert_text((50, 100), text, fontsize=12)
    doc.save(file_path)
    doc.close()


def test_audit_multipart_parser_edge_cases():
    """Тестирование парсера multipart/form-data на граничных и некорректных потоках данных."""
    boundary = "----WebKitBoundaryAuditTest123"
    pdf_bytes = b"%PDF-1.4 test audit content 9999"
    txt_bytes = b"This is a text file that should be ignored"

    # 1. Смешанные файлы: PDF + TXT (TXT должен быть проигнорирован)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="doc"; filename="ignore.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode("latin1") + txt_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="pdf"; filename="valid_receipt.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("latin1") + pdf_bytes + f"\r\n--{boundary}--\r\n".encode("latin1")

    class MockReqHandler(AppRequestHandler):
        def __init__(self, raw_body, bnd):
            self.headers = {
                'Content-Type': f'multipart/form-data; boundary={bnd}',
                'Content-Length': str(len(raw_body))
            }
            self.rfile = io.BytesIO(raw_body)

    h1 = MockReqHandler(body, boundary)
    tmp_dir1, pdf_files1 = h1._parse_multipart_to_disk()
    assert tmp_dir1 is not None
    assert len(pdf_files1) == 1
    assert pdf_files1[0][0] == "valid_receipt.pdf"
    with open(pdf_files1[0][1], "rb") as f:
        assert f.read() == pdf_bytes
    shutil.rmtree(tmp_dir1, ignore_errors=True)

    # 2. Некорректный/пустой запрос
    h_empty = MockReqHandler(b"", boundary)
    h_empty.headers['Content-Length'] = '0'
    t_empty, f_empty = h_empty._parse_multipart_to_disk()
    assert t_empty is None and f_empty is None

    # 3. Обрезанный поток (truncation)
    truncated_body = body[:len(body) // 2]
    h_trunc = MockReqHandler(truncated_body, boundary)
    t_trunc, f_trunc = h_trunc._parse_multipart_to_disk()
    if t_trunc:
        shutil.rmtree(t_trunc, ignore_errors=True)


def test_audit_reconcile_service_pagination_and_multiperiod():
    """Тестирование точности сверки и пагинации при наличии счетов с несколькими квитанциями."""
    con = get_db()
    con.executescript('''
        DELETE FROM receipts;
        DELETE FROM accounts;
        INSERT INTO accounts(account_number, customer_name, address) VALUES
            ('100', 'Алимов А.', 'ул. 1'),
            ('200', 'Беков Б.', 'ул. 2'),
            ('300', 'Сериков С.', 'ул. 3');

        INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token) VALUES
            ('100', 'Январь 2026', '10/00/100_1.pdf', 'h1', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
            ('100', 'Февраль 2026', '10/00/100_2.pdf', 'h2', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'),
            ('100', 'Март 2026', '10/00/100_3.pdf', 'h3', 'cccccccccccccccccccccccccccccccc'),
            ('200', 'Январь 2026', '20/00/200_1.pdf', 'h4', 'dddddddddddddddddddddddddddddddd'),
            ('999', 'Январь 2026', '99/90/999_1.pdf', 'h5', 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee');
    ''')
    con.commit()
    con.close()

    # 1. Без фильтра периода:
    # Счет 100 имеет 3 квитанции, Счет 200 имеет 1, Счет 300 имеет 0, 999 - сирота.
    res_all = reconcile_service.get_reconciliation_data('all', '', page_num=1, per_page=10)
    assert res_all['total_accounts'] == 3
    assert res_all['total_receipts'] == 5
    assert res_all['matched'] == 2  # 100 и 200
    assert res_all['unmatched'] == 1 # 300
    assert res_all['orphans'] == 1   # 999
    # Проверка пагинации: 3 (счет 100) + 1 (счет 200) + 1 (счет 300) = 5 строк
    assert res_all['list_count'] == 5
    assert len(res_all['rows']) == 5

    # 2. Фильтр 'with' без фильтра периода:
    res_with = reconcile_service.get_reconciliation_data('with', '', page_num=1, per_page=10)
    assert res_with['list_count'] == 4 # 3 для счета 100, 1 для счета 200
    assert len(res_with['rows']) == 4

    # 3. Фильтр 'without' без фильтра периода:
    res_without = reconcile_service.get_reconciliation_data('without', '', page_num=1, per_page=10)
    assert res_without['list_count'] == 1 # счет 300
    assert len(res_without['rows']) == 1
    assert res_without['rows'][0]['account_number'] == '300'

    # 4. Фильтр по периоду 'Февраль 2026':
    res_feb = reconcile_service.get_reconciliation_data('with', 'Февраль 2026', page_num=1, per_page=10)
    assert res_feb['matched'] == 1
    assert len(res_feb['rows']) == 1
    assert res_feb['rows'][0]['account_number'] == '100'

    # 5. Граничные значения пагинации: page_num = 0, page_num = -5
    res_edge = reconcile_service.get_reconciliation_data('all', '', page_num=-5, per_page=2)
    assert res_edge['page_num'] == 1
    assert len(res_edge['rows']) == 2


def test_audit_sharding_and_security_traversal():
    """Тестирование шардирования нестандартных счетов и защиты от атак обхода каталогов."""

    # 1. Различные граничные номера счетов
    assert get_receipt_shard_parts("5") == ("05", "00")
    assert get_receipt_shard_parts("88") == ("88", "00")
    assert get_receipt_shard_parts("999") == ("99", "90")
    assert get_receipt_shard_parts("123456") == ("12", "34")
    assert get_receipt_shard_parts("987654321") == ("98", "76")
    assert get_receipt_shard_parts("ABC") == ("misc", "00")
    assert get_receipt_shard_parts(None) == ("misc", "00")

    # 2. Попытки Path Traversal в get_pdf_by_token
    assert receipt_service.get_pdf_by_token("../../../etc/shadow") is None
    assert receipt_service.get_pdf_by_token("..\\..\\windows\\system32") is None
    assert receipt_service.get_pdf_by_token("%2e%2e%2fetc%2fpasswd") is None
    assert receipt_service.get_pdf_by_token("a" * 31) is None
    assert receipt_service.get_pdf_by_token("a" * 33) is None
    assert receipt_service.get_pdf_by_token("g" * 32) is None # non-hex


def test_audit_pdf_processor_corrupt_and_edge_cases(tmp_path):
    """Тестирование обработки поврежденных, пустых и нестандартных PDF документов."""
    # 1. Поврежденный файл (битый заголовок)
    corrupt_path = os.path.join(tmp_path, "corrupt.pdf")
    with open(corrupt_path, "wb") as f:
        f.write(b"CORRUPT DATA NOT A PDF")

    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        corrupt_path, "corrupt.pdf", known_accounts={"123"}
    )
    assert added == 0
    assert skipped == 1
    assert any("не удалось открыть как PDF" in d for d in details)

    # 2. Пустой 0-байтовый файл
    empty_path = os.path.join(tmp_path, "empty.pdf")
    with open(empty_path, "wb") as f:
        pass

    added_e, orphan_e, skipped_e, dups_e, details_e, receipts_e = pdf_processor.process_single_pdf(
        empty_path, "empty.pdf", known_accounts={"123"}
    )
    assert added_e == 0
    assert skipped_e == 1


def test_audit_auth_and_throttler_concurrency():
    """Тестирование AuthService и IPThrottler в условиях конкурентной нагрузки."""
    # 1. AuthService
    assert auth_service.verify_password("admin") is True
    assert auth_service.verify_password("wrong_password") is False
    assert auth_service.verify_password("") is False
    assert auth_service.verify_password(None) is False

    token = auth_service.create_session()
    assert auth_service.is_valid_session(token) is True
    auth_service.destroy_session(token)
    assert auth_service.is_valid_session(token) is False

    # 2. IPThrottler
    test_ip = "198.51.100.99"
    # Бан IP
    ip_throttler.ban_ip(test_ip, duration_seconds=60, reason="Audit Test Ban")
    is_b, retry = ip_throttler.is_banned(test_ip)
    assert is_b is True
    assert retry > 0

    allowed, reason, r_after = ip_throttler.acquire(test_ip)
    assert allowed is False
    assert reason == 'ip_banned'

    # Снятие бана вручную
    with ip_throttler._lock:
        ip_throttler._banned_ips.pop(test_ip, None)
    con = get_db()
    con.execute('DELETE FROM security_blocks WHERE ip = ?', (test_ip,))
    con.commit()
    con.close()

    is_b2, _ = ip_throttler.is_banned(test_ip)
    assert is_b2 is False


def test_audit_websocket_frames_and_multiplexing():
    """Тестирование кодирования и декодирования WebSocket фреймов RFC 6455 разного размера."""
    from services.websocket.ws_manager import WebSocketClientState

    # 1. Маленький фрейм (< 126 байт)
    small_text = "Hello WebSocket"
    f_small = ws_manager._encode_frame(small_text)
    assert len(f_small) == 2 + len(small_text.encode('utf-8'))
    assert f_small[0] == 0x81  # FIN=1, Opcode=1 (Text)
    assert f_small[1] == len(small_text)

    # 2. Средний фрейм (126..65535 байт)
    medium_text = "X" * 1000
    f_med = ws_manager._encode_frame(medium_text)
    assert f_med[0] == 0x81
    assert f_med[1] == 126
    length_unpacked = struct.unpack('!H', f_med[2:4])[0]
    assert length_unpacked == 1000

    # 3. Декодирование замаскированного фрейма (от клиента)
    mock_payload = b'{"action":"ping"}'
    mask_key = b'\x12\x34\x56\x78'
    masked_payload = bytes([b ^ mask_key[i % 4] for i, b in enumerate(mock_payload)])

    client_frame = bytearray([0x81, 0x80 | len(mock_payload)]) + mask_key + masked_payload

    # Создаем фиктивный сокет для state
    s1, s2 = socket.socketpair()
    try:
        state = WebSocketClientState(s1, "127.0.0.1")
        state.buf = client_frame
        ws_manager._process_frames(state)
        # Буфер должен быть полностью обработан
        assert len(state.buf) == 0
    finally:
        s1.close()
        s2.close()

def test_application_level_resource_limits():
    """Тестирует применение лимитов уровня приложения (MAX_UPLOAD_BYTES, MAX_PDF_PAGES, MAX_PDF_OUTPUT_SIZE)."""
    import unittest.mock as mock

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    from server import AppRequestHandler
    from services.pdf.pdf_processor import pdf_processor
    import config

    # 1. Защита от превышения размера загрузки (MAX_UPLOAD_BYTES)
    class MockHandler(AppRequestHandler):
        def __init__(self, c_len, raw_bytes=b""):
            self.headers = {
                'Content-Type': 'multipart/form-data; boundary=----WebKitBoundaryXYZ',
                'Content-Length': str(c_len)
            }
            self.rfile = io.BytesIO(raw_bytes)

    # Content-Length превышает MAX_UPLOAD_BYTES -> немедленный отказ 413
    oversized_handler = MockHandler(c_len=config.MAX_UPLOAD_BYTES + 1024)
    tmp_d, res = oversized_handler._parse_multipart_to_disk()
    assert tmp_d is None
    assert res == "PAYLOAD_TOO_LARGE"

    # 2. Защита от PDF-бомб (MAX_PDF_PAGES)
    doc = fitz.open()
    for _ in range(5):
        p = doc.new_page()
        p.insert_text((50, 50), "Лицевой счёт: 800100\nПериод: 2026")
    pdf_bomb_bytes = doc.tobytes()
    doc.close()

    tmp_pdf_path = os.path.join(tempfile.gettempdir(), "test_bomb.pdf")
    with open(tmp_pdf_path, "wb") as f:
        f.write(pdf_bomb_bytes)

    try:
        with mock.patch("config.MAX_PDF_PAGES", 3):
            added, orphan, skipped, dups, details, recs = pdf_processor.process_single_pdf(
                tmp_pdf_path, "test_bomb.pdf", {"800100"}
            )
            assert skipped == 1
            assert any("Превышен лимит страниц" in d for d in details)
    finally:
        if os.path.isfile(tmp_pdf_path):
            os.remove(tmp_pdf_path)

