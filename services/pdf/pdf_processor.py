# -*- coding: utf-8 -*-
import os
import re
import hashlib
import secrets
import config
from config import OCR_ENABLED, OCR_LANGUAGES, OCR_DPI, get_receipt_shard_parts, get_sharded_receipt_rel_path
from services.pdf.atomic_importer import AtomicReceiptImporter, StagedReceipt, ReceiptStatus

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

ACCOUNT_PATTERNS = [
    re.compile(r'(?:Жеке\s+шот\s*/\s*Лицевой\s+сч[её]т|Лицевой\s+сч[её]т\s*/\s*Жеке\s+шот)\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'Лицевой\s+сч[её]т\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'Л[/\.]\s*сч?[её]?т?\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'Абонентский\s+сч[её]т\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'Сч[её]т-извещение\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'(?:Жеке|Дербес)\s+шот\s*[:№#\s]*(\d+)', re.IGNORECASE),
    re.compile(r'Абонент\s*[:№#\s]*(\d+)', re.IGNORECASE),
]

PERIOD_PATTERNS = [
    re.compile(r'(?:Сч[её]т-извещение|Квитанция|Извещение)\s+за\s+(.+?)(?:\s*г\.|\s*$|\n)', re.IGNORECASE),
    re.compile(r'(?:Мезгілі\s*/\s*Период|Период\s*/\s*Мезгілі|Период)\s*[:\s]+(.+?)(?:\s*г\.|\s*$|\n)', re.IGNORECASE),
    re.compile(r'за\s+((?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан)\s+\d{4})', re.IGNORECASE),
    re.compile(r'((?:0[1-9]|1[0-2])[\./]\d{4})'),
]

ADDRESS_PATTERNS = [
    re.compile(r'(?:Мекенжайы\s*/\s*Адрес|Мекен-жайы\s*/\s*Адрес|Адрес\s*/\s*Мекенжайы|Мекенжайы|Мекен-жайы|Адрес)\s*[:\s]+([^\n\r]+)', re.IGNORECASE),
]

os.makedirs(config.RECEIPTS_DIR, exist_ok=True)

class ReceiptDocument:
    def __init__(self, start_page_idx: int, account: str, period: str, address: str = None):
        self.pages = [start_page_idx]
        self.account = account
        self.period = period
        self.address = address
        self.texts = []

class PDFProcessor:
    @staticmethod
    def extract_account_number(text: str):
        if not text:
            return None
        for pattern in ACCOUNT_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def extract_period(text: str) -> str:
        if not text:
            return 'не указан'
        for pattern in PERIOD_PATTERNS:
            match = pattern.search(text)
            if match:
                val = match.group(1).strip().rstrip('.,;')
                if val:
                    return val
        return 'не указан'

    @staticmethod
    def extract_address(text: str):
        if not text:
            return None
        for pattern in ADDRESS_PATTERNS:
            match = pattern.search(text)
            if match:
                val = match.group(1).strip()
                if val:
                    return val
        return None

    @classmethod
    def extract_page_text(cls, page) -> tuple[str, bool]:
        """
        Извлекает текст со страницы:
        1. Сначала пробует быстрый векторный текстовый слой (page.get_text()).
        2. Если текст пуст или не содержит лицевого счёта, и на странице есть изображения (растр),
           пробует выполнить OCR через PyMuPDF get_textpage_ocr() при включенном OCR.
        Возвращает (text, used_ocr: bool).
        """
        raw_text = ""
        try:
            raw_text = page.get_text().replace('\xa0', ' ').replace('\xad', '-')
        except Exception:
            raw_text = ""

        # Если векторный текст содержит распознанный номер лицевого счёта, сразу возвращаем его
        if raw_text.strip() and cls.extract_account_number(raw_text):
            return raw_text, False

        # Если векторный текст не дал Л/С или пуст — пробуем OCR распознавание скана
        if OCR_ENABLED and hasattr(page, 'get_textpage_ocr'):
            try:
                # full=True включает распознавание всей страницы, включая изображения
                textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=OCR_DPI, full=True)
                ocr_text = page.get_text(textpage=textpage).replace('\xa0', ' ').replace('\xad', '-')
                if ocr_text.strip():
                    if cls.extract_account_number(ocr_text) or not raw_text.strip():
                        return ocr_text, True
            except Exception:
                # OCR недоступен (например, не установлен Tesseract/tessdata) - fallback на сырой текст
                pass

        return raw_text, False

    @classmethod
    def group_pages_into_documents(cls, pdf):
        """
        Группирует страницы PDF в логические квитанции:
        - Каждая страница с номером лицевого счета начинает новую квитанцию.
        - Страницы без номера лицевого счета присоединяются как продолжение (стр. 2..N).
        """
        documents = []
        current_doc = None
        unattached_skipped = []

        for i in range(len(pdf)):
            page = pdf[i]
            text, used_ocr = cls.extract_page_text(page)
            account = cls.extract_account_number(text)
            period = cls.extract_period(text)
            address = cls.extract_address(text)

            if account:
                current_doc = ReceiptDocument(i, account, period, address)
                current_doc.texts.append(text)
                documents.append(current_doc)
            else:
                if current_doc is not None:
                    current_doc.pages.append(i)
                    current_doc.texts.append(text)
                    if current_doc.period == 'не указан' and period != 'не указан':
                        current_doc.period = period
                    if not current_doc.address and address:
                        current_doc.address = address
                else:
                    if not text.strip():
                        reason = "Текст не извлечен (страница пуста или содержит растровый скан без OCR-слоя / Tesseract не настроен)"
                    else:
                        sample = text[:80].replace('\n', ' ').strip()
                        reason = f'Лицевой счет не распознан. Образец текста: "{sample}..."'
                    unattached_skipped.append((i + 1, reason))

        return documents, unattached_skipped

    @staticmethod
    def compute_file_hash(pdf_bytes: bytes) -> str:
        """SHA-256 оригинальных байт PDF-файла (физический хеш документа)."""
        return hashlib.sha256(pdf_bytes).hexdigest()

    @staticmethod
    def compute_semantic_hash(account: str, period: str, combined_text: str) -> str:
        """
        SHA-256 нормализованных значимых полей квитанции:
        account_number + normalized period + normalized cleaned text.
        Логический хеш для защиты от повторной загрузки той же квитанции.
        """
        normalized_acc = str(account).strip()
        normalized_per = str(period).strip().lower()
        normalized_text = " ".join(combined_text.split())
        payload = f"{normalized_acc}|{normalized_per}|{normalized_text}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    @classmethod
    def process_single_pdf(cls, pdf_path: str, original_filename: str, known_accounts: set = None, existing_hashes: set = None):
        """
        Обрабатывает один PDF:
        1. Распознаёт текст (и выполняет OCR при необходимости)
        2. Группирует страницы по лицевому счёту и периоду
        3. Разделяет file_hash (физический хеш байт) и semantic_hash (логический хеш данных)
        4. Сохраняет квитанцию в шардированное хранилище receipts/{s1}/{s2}/{account}_{file_hash}_{semantic_hash}.pdf
        5. Возвращает: (added, orphan, skipped, duplicates, details, receipts_to_insert)
        """
        if not fitz:
            return 0, 0, 1, 0, [f'📄 {original_filename}: ❌ PyMuPDF не установлен'], []

        try:
            pdf = fitz.open(pdf_path)
        except Exception:
            return 0, 0, 1, 0, [f'📄 {original_filename}: ❌ не удалось открыть как PDF'], []

        if existing_hashes is None:
            existing_hashes = set()

        added = 0
        skipped = 0
        orphan = 0
        duplicates = 0
        details = []
        receipts_to_insert = []

        documents, unattached_skipped = cls.group_pages_into_documents(pdf)

        for page_num, reason in unattached_skipped:
            skipped += 1
            details.append(f'  Стр. {page_num}: ❌ {reason}')

        for doc in documents:
            account = doc.account
            period = doc.period
            address = doc.address
            page_range_str = f'Стр. {doc.pages[0]+1}' if len(doc.pages) == 1 else f'Стр. {doc.pages[0]+1}–{doc.pages[-1]+1} ({len(doc.pages)} стр.)'

            combined_text = "\n---PAGE---\n".join(doc.texts)

            # Выделяем бинарные байты страниц для физического хеша
            new_pdf = fitz.open()
            new_pdf.insert_pdf(pdf, from_page=doc.pages[0], to_page=doc.pages[-1])
            extracted_pdf_bytes = new_pdf.tobytes()
            new_pdf.close()

            # 1. Физический хеш (SHA-256 бинарного содержимого PDF)
            file_hash = cls.compute_file_hash(extracted_pdf_bytes)

            # 2. Логический / семантический хеш (нормализованный счет + период + текст)
            semantic_hash = cls.compute_semantic_hash(account, period, combined_text)
            content_hash = semantic_hash

            # Проверка дедупликации по обоим уровням
            is_file_dup = file_hash in existing_hashes
            is_semantic_dup = semantic_hash in existing_hashes

            if is_file_dup or is_semantic_dup:
                duplicates += 1
                dup_type = "физический дубликат файла" if is_file_dup else "логический дубликат данных"
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 {dup_type}, пропущен')
                continue

            existing_hashes.add(file_hash)
            existing_hashes.add(semantic_hash)
            existing_hashes.add(content_hash)

            # Создаем подготовленную квитанцию (StagedReceipt) без прямой записи на диск
            is_orphan = (known_accounts is not None and account not in known_accounts)
            staged_item = AtomicReceiptImporter.stage_receipt(
                account=account,
                period=period,
                pdf_bytes=extracted_pdf_bytes,
                address=address,
                file_hash=file_hash,
                semantic_hash=semantic_hash,
                is_orphan=is_orphan
            )

            receipts_to_insert.append((
                staged_item.account,
                staged_item.period,
                staged_item.target_rel_path,
                staged_item.content_hash,
                staged_item.file_hash,
                staged_item.semantic_hash,
                staged_item.access_token,
                staged_item.address
            ))

            # Сохраняем объект для транзакционной фиксации
            if not hasattr(cls, '_temp_staged_collector'):
                pass

            # Атомарная фиксация квитанции через 2-Phase Commit
            AtomicReceiptImporter.commit_staged_batch([staged_item])

            if account in known_accounts:
                added += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ✅ привязан (READY)')
            else:
                orphan += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ⚠ счёта нет в базе')

        pdf.close()
        return added, orphan, skipped, duplicates, details, receipts_to_insert

pdf_processor = PDFProcessor()
