import os
try:
    import pymupdf as fitz
except ImportError:
    import fitz
try:
    import pytest
except ImportError:
    pytest = None
from services.pdf.pdf_processor import pdf_processor

def create_sample_pdf(file_path: str, pages_data: list):
    """Создаёт тестовый PDF документ с заданным текстом на каждой странице."""
    doc = fitz.open()
    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None

    for text in pages_data:
        page = doc.new_page()
        if font_path:
            page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
            page.insert_text((50, 100), text, fontname='arial', fontsize=12)
        else:
            page.insert_text((50, 100), text, fontsize=12)
    doc.save(file_path)
    doc.close()


def test_pdf_processor_extract_and_save(tmp_path):
    from config import RECEIPTS_DIR
    pdf_path = str(tmp_path / "sample.pdf")
    pages = [
        "Жеке шот / Лицевой счёт 800146\nСчёт-извещение за Январь 2026 г.\nСумма: 5000",
        "Жеке шот / Лицевой счёт 800147\nСчёт-извещение за Январь 2026 г.\nСумма: 7500",
    ]
    create_sample_pdf(pdf_path, pages)

    known_accounts = {"800146"}
    existing_hashes = set()

    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        pdf_path, "sample.pdf", known_accounts, existing_hashes
    )

    assert added == 1
    assert orphan == 1  # 800147 нет в known_accounts
    assert skipped == 0
    assert dups == 0
    assert len(receipts) == 2

    # Проверка формата записей и двухуровневого шардирования
    acc1, period1, out_file1, hash1, token1, addr1 = receipts[0]
    assert acc1 == "800146"
    assert period1 == "Январь 2026"
    assert out_file1.startswith("80/01/800146_")
    assert out_file1.endswith(".pdf")
    assert len(token1) == 32
    assert os.path.isfile(os.path.join(RECEIPTS_DIR, out_file1))

def test_pdf_processor_address_extraction(tmp_path):
    pdf_path = str(tmp_path / "addr_sample.pdf")
    pages = [
        "Жеке шот / Лицевой счёт 800999\nМекенжайы / Адрес: Нуринский район, с. Балыктыколь, ул. Балабиева, дом № 1А, к. 1\nСчёт-извещение за Март 2026 г.",
    ]
    create_sample_pdf(pdf_path, pages)
    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        pdf_path, "addr_sample.pdf", {"800999"}, set()
    )
    assert added == 1
    assert len(receipts) == 1
    acc, per, path, h, tok, addr = receipts[0]
    assert acc == "800999"
    assert addr == "Нуринский район, с. Балыктыколь, ул. Балабиева, дом № 1А, к. 1"

def test_pdf_processor_idempotency_and_duplicates(tmp_path):
    pdf_path = str(tmp_path / "dup.pdf")
    pages = [
        "Жеке шот / Лицевой счёт 800146\nСчёт-извещение за Февраль 2026 г.\nСумма: 3000",
        "Жеке шот / Лицевой счёт 800146\nСчёт-извещение за Февраль 2026 г.\nСумма: 3000", # точный дубликат
    ]
    create_sample_pdf(pdf_path, pages)

    known_accounts = {"800146"}
    existing_hashes = set()

    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        pdf_path, "dup.pdf", known_accounts, existing_hashes
    )

    assert added == 1
    assert dups == 1
    assert len(receipts) == 1

def test_pdf_processor_missing_account(tmp_path):
    pdf_path = str(tmp_path / "no_account.pdf")
    pages = [
        "Просто произвольный текст без номера лицевого счета",
    ]
    create_sample_pdf(pdf_path, pages)

    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        pdf_path, "no_account.pdf", {"800146"}, set()
    )

    assert added == 0
    assert skipped == 1
    assert len(receipts) == 0

def test_streaming_multipart_parser(tmp_path):
    import io
    from server import AppRequestHandler

    boundary = "----WebKitFormBoundaryX9QWz7qg8jL"
    pdf_content = b"%PDF-1.4 mock binary content 12345"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="pdf"; filename="test_doc.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("latin1") + pdf_content + f"\r\n--{boundary}--\r\n".encode("latin1")

    class MockHandler(AppRequestHandler):
        def __init__(self, raw_body, bnd):
            self.headers = {
                'Content-Type': f'multipart/form-data; boundary={bnd}',
                'Content-Length': str(len(raw_body))
            }
            self.rfile = io.BytesIO(raw_body)

    handler = MockHandler(body, boundary)
    tmp_dir, pdf_files = handler._parse_multipart_to_disk()

    assert tmp_dir is not None
    assert len(pdf_files) == 1
    base_name, file_path = pdf_files[0]
    assert base_name == "test_doc.pdf"
    with open(file_path, "rb") as f:
        read_bytes = f.read()
    assert read_bytes == pdf_content

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

def test_pdf_processor_flexible_patterns_and_diagnostics(tmp_path):
    from services.pdf.pdf_processor import pdf_processor

    # 1. Проверка различных вариантов написания лицевого счёта
    assert pdf_processor.extract_account_number("Лицевой счет № 88472910") == "88472910"
    assert pdf_processor.extract_account_number("Л/с: 554321") == "554321"
    assert pdf_processor.extract_account_number("Л.счет 998877") == "998877"
    assert pdf_processor.extract_account_number("Жеке шот / Лицевой счет 100200300") == "100200300"
    assert pdf_processor.extract_account_number("Лицевой счет / Жеке шот 999888") == "999888"
    assert pdf_processor.extract_account_number("Абонентский счет: 123456") == "123456"
    assert pdf_processor.extract_account_number("Дербес шот #777666") == "777666"

    # 2. Проверка различных форматов расчетного периода
    assert "май 2026" in pdf_processor.extract_period("Квитанция за май 2026 г.")
    assert "04.2026" in pdf_processor.extract_period("Период: 04.2026")
    assert "қараша 2025" in pdf_processor.extract_period("Счет-извещение за қараша 2025 г.")
    assert "11/2025" in pdf_processor.extract_period("Период 11/2025")

    # 3. Проверка диагностических сообщений для пустых/нераспознанных страниц
    mock_pdf_path = os.path.join(tmp_path, "diag_test.pdf")
    doc = fitz.open()
    # Стр 1: Пустая страница (имитация скана без OCR)
    doc.new_page()
    # Стр 2: Текст общего назначения без Л/С
    page2 = doc.new_page()
    page2.insert_text((50, 50), "Памятка потребителю: своевременно передавайте показания счетчиков.")
    doc.save(mock_pdf_path)
    doc.close()

    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        mock_pdf_path, "diag_test.pdf", known_accounts=set()
    )
    assert skipped == 2
    assert any("растровый скан без OCR" in d for d in details)
    assert any("Лицевой счет не распознан" in d for d in details)

def test_pdf_processor_multipage_receipt_grouping(tmp_path):
    from services.pdf.pdf_processor import pdf_processor
    from config import RECEIPTS_DIR

    # Создаем 3-страничный PDF:
    # Стр 1: Лицевой счет 1001 (Квитанция 1, страница 1 из 2)
    # Стр 2: Детализация расхода воды без заголовка (Квитанция 1, страница 2 из 2)
    # Стр 3: Лицевой счет 1002 (Квитанция 2, одностраничная)
    multi_pdf_path = os.path.join(tmp_path, "multipage_doc.pdf")
    pages = [
        "Счет-извещение за май 2026 г.\nЛицевой счет 1001\nСумма: 5000 тг",
        "Таблица расшифровки показаний счетчиков и тарифов\nХолодная вода: 12 м3",
        "Счет-извещение за май 2026 г.\nЛицевой счет 1002\nСумма: 7500 тг"
    ]
    create_sample_pdf(multi_pdf_path, pages)

    known_accounts = {"1001", "1002"}
    added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(
        multi_pdf_path, "multipage_doc.pdf", known_accounts=known_accounts
    )

    # Проверяем, что создано ровно 2 квитанции, и 0 пропущено
    assert added == 2
    assert orphan == 0
    assert skipped == 0
    assert len(receipts) == 2

    # Проверяем квитанцию 1001
    rec_1001 = [r for r in receipts if r[0] == "1001"][0]
    out_pdf_1001 = os.path.join(RECEIPTS_DIR, rec_1001[2])
    saved_doc_1001 = fitz.open(out_pdf_1001)
    assert len(saved_doc_1001) == 2  # Сформирован цельный 2-страничный PDF!
    saved_doc_1001.close()

    # Проверяем квитанцию 1002
    rec_1002 = [r for r in receipts if r[0] == "1002"][0]
    out_pdf_1002 = os.path.join(RECEIPTS_DIR, rec_1002[2])
    saved_doc_1002 = fitz.open(out_pdf_1002)
    assert len(saved_doc_1002) == 1  # Одностраничная квитанция
    saved_doc_1002.close()

def test_pdf_processor_sharding_helpers():
    from config import get_receipt_shard_parts, get_sharded_receipt_rel_path

    # Стандартный 6-значный лицевой счет
    assert get_receipt_shard_parts("800146") == ("80", "01")
    assert get_sharded_receipt_rel_path("800146", "800146_abc.pdf") == "80/01/800146_abc.pdf"

    # 4-значный счет
    assert get_receipt_shard_parts("1001") == ("10", "01")
    assert get_sharded_receipt_rel_path("1001", "1001_abc.pdf") == "10/01/1001_abc.pdf"

    # Короткий 2-значный счет
    assert get_receipt_shard_parts("88") == ("88", "00")
    assert get_sharded_receipt_rel_path("88", "88_abc.pdf") == "88/00/88_abc.pdf"

    # 1-значный счет
    assert get_receipt_shard_parts("7") == ("07", "00")

    # Нечисловой / пустой
    assert get_receipt_shard_parts("") == ("misc", "00")
    assert get_receipt_shard_parts("N/A") == ("misc", "00")

def test_pdf_processor_ocr_fallback_and_handling(tmp_path):
    from services.pdf.pdf_processor import pdf_processor
    import services.pdf.pdf_processor as mod

    # Проверка извлечения со страницы без OCR и с OCR
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Лицевой счет: 998877\nПериод: Май 2026")

    # Обычный векторный текст
    text, used_ocr = pdf_processor.extract_page_text(page)
    assert "998877" in text
    assert used_ocr is False

    # Пустая страница без OCR
    blank_page = doc.new_page()
    b_text, b_ocr = pdf_processor.extract_page_text(blank_page)
    assert b_text == ""
    assert b_ocr is False
    doc.close()

def test_migrate_receipts_to_sharding(tmp_path):
    from config import RECEIPTS_DIR
    from database import get_db
    from database.migrations import migrate_receipts_to_sharding

    con = get_db()
    flat_pdf_name = "800199_flat_hash.pdf"
    flat_file_path = os.path.join(RECEIPTS_DIR, flat_pdf_name)
    with open(flat_file_path, "wb") as f:
        f.write(b"%PDF-1.4 test flat receipt")

    token = "abcdef1234567890abcdef1234567890"
    con.execute("INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token) VALUES (?,?,?,?,?)",
                ("800199", "Апрель 2026", flat_pdf_name, "flathash", token))
    con.commit()
    con.close()

    migrated_files, updated_db = migrate_receipts_to_sharding()
    assert migrated_files >= 1
    assert updated_db >= 1

    # Проверяем, что файл переместился в 80/01/800199_flat_hash.pdf
    expected_path = os.path.join(RECEIPTS_DIR, "80", "01", flat_pdf_name)
    assert os.path.isfile(expected_path)
    assert not os.path.isfile(flat_file_path)

    # Проверяем запись в БД
    con = get_db()
    row = con.execute("SELECT pdf_file FROM receipts WHERE access_token = ?", (token,)).fetchone()
    assert row["pdf_file"] == "80/01/800199_flat_hash.pdf"
    con.close()



