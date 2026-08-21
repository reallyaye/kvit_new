# -*- coding: utf-8 -*-
import os, re, hashlib, secrets
from config import RECEIPTS_DIR, OCR_ENABLED, OCR_LANGUAGES, OCR_DPI, get_receipt_shard_parts, get_sharded_receipt_rel_path

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

os.makedirs(RECEIPTS_DIR, exist_ok=True)

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

    @classmethod
    def process_single_pdf(cls, pdf_path, original_filename, known_accounts, existing_hashes=None):
        if fitz is None:
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
            content_hash = hashlib.sha256(combined_text.encode('utf-8')).hexdigest()

            if content_hash in existing_hashes:
                duplicates += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 дубликат, пропущен')
                continue

            existing_hashes.add(content_hash)

            # Двухуровневое шардирование: receipts/{s1}/{s2}/{account}_{hash}.pdf
            s1, s2 = get_receipt_shard_parts(account)
            shard_dir = os.path.join(RECEIPTS_DIR, s1, s2)
            os.makedirs(shard_dir, exist_ok=True)

            base_filename = f'{account}_{content_hash[:16]}.pdf'
            out_rel_path = f'{s1}/{s2}/{base_filename}'
            out_full_path = os.path.join(shard_dir, base_filename)

            new_pdf = fitz.open()
            new_pdf.insert_pdf(pdf, from_page=doc.pages[0], to_page=doc.pages[-1])
            new_pdf.save(out_full_path)
            new_pdf.close()

            access_token = secrets.token_hex(16)
            receipts_to_insert.append((account, period, out_rel_path, content_hash, access_token, address))

            if account in known_accounts:
                added += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ✅ привязан')
            else:
                orphan += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ⚠ счёта нет в базе')

        pdf.close()
        return added, orphan, skipped, duplicates, details, receipts_to_insert
        return added, orphan, skipped, duplicates, details, receipts_to_insert

pdf_processor = PDFProcessor()
