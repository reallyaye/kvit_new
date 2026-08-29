# -*- coding: utf-8 -*-
import hashlib
import os
import re
import threading
import time

import config
from config import OCR_ENABLED, OCR_LANGUAGES
from services.pdf.atomic_importer import AtomicReceiptImporter

# Глобальный семафор для ограничения одновременных OCR процессов на уровне сервера (DoS protection)
_OCR_SEMAPHORE = threading.Semaphore(config.MAX_OCR_CONCURRENT_WORKERS)

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

ACCOUNT_PATTERNS = [
    re.compile(r'(?:Жеке\s+шот\s*/\s*Лицевой\s+сч[её]т|Лицевой\s+сч[её]т\s*/\s*Жеке\s+шот)[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'Лицевой\s+сч[её]т[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'Л[/\.]\s*сч?[её]?т?[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'Абонентский\s+сч[её]т[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'Сч[её]т-извещение[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'(?:Жеке|Дербес)\s+шот[:№#\s]+(\d+)', re.IGNORECASE),
    re.compile(r'Абонент[:№#\s]+(\d+)', re.IGNORECASE),
]

PERIOD_PATTERNS = [
    re.compile(r'(?:Сч[её]т-извещение|Квитанция|Извещение)\s+за\s+([^\r\n]+)', re.IGNORECASE),
    re.compile(r'(?:Мезгілі\s*/\s*Период|Период\s*/\s*Мезгілі|Период)[:\s]+([^\r\n]+)', re.IGNORECASE),
    re.compile(r'за\s+((?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан)\s+\d{4})', re.IGNORECASE),
    re.compile(r'((?:0[1-9]|1[0-2])[\./]\d{4})'),
]

ADDRESS_PATTERNS = [
    re.compile(r'(?:Мекенжайы\s*/\s*Адрес|Мекен-жайы\s*/\s*Адрес|Адрес\s*/\s*Мекенжайы|Мекенжайы|Мекен-жайы|Адрес)[:\s]+([^\n\r]+)', re.IGNORECASE),
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
                for suffix in (' г.', ' г', 'г.', 'г'):
                    if val.lower().endswith(suffix):
                        val = val[:-len(suffix)].strip()
                        break
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
    def extract_page_text(cls, page, ocr_context: dict = None) -> tuple[str, bool, str]:
        """
        Извлекает текст со страницы:
        1. Сначала пробует быстрый векторный текстовый слой (page.get_text()).
        2. Если текст пуст или не содержит лицевого счёта, и на странице есть изображения (растр),
           пробует выполнить OCR с проверкой бюджета ресурсов и лимитов DoS:
           - MAX_OCR_PAGES_PER_DOC: ограничение количества страниц на OCR в документе
           - MAX_OCR_DOC_TIME_BUDGET: суммарный таймаут времени OCR на документ
           - MAX_OCR_PAGE_TIME: таймаут на одну страницу
           - MAX_OCR_DPI и MAX_OCR_IMAGE_PIXELS: защита от гигантских разрешений и потребления RAM
           - _OCR_SEMAPHORE: ограничение глобальной параллельности OCR на сервер
        Возвращает (text, used_ocr: bool, ocr_status: str).
        """
        raw_text = ""
        try:
            raw_text = page.get_text().replace('\xa0', ' ').replace('\xad', '-')
        except Exception:
            raw_text = ""

        # Если векторный текст содержит распознанный номер лицевого счёта, сразу возвращаем его
        if raw_text.strip() and cls.extract_account_number(raw_text):
            return raw_text, False, 'OK'

        # Если OCR отключен
        if not OCR_ENABLED or not hasattr(page, 'get_textpage_ocr'):
            return raw_text, False, 'OCR_DISABLED'

        # ─── Проверка бюджета ресурсов OCR для текущего документа ───
        if ocr_context is not None:
            if ocr_context.get('pages_done', 0) >= config.MAX_OCR_PAGES_PER_DOC:
                return raw_text, False, f"OCR_LIMIT_PAGES_EXCEEDED ({config.MAX_OCR_PAGES_PER_DOC} стр.)"
            if ocr_context.get('total_time', 0.0) >= config.MAX_OCR_DOC_TIME_BUDGET:
                return raw_text, False, f"OCR_LIMIT_TIME_EXCEEDED ({config.MAX_OCR_DOC_TIME_BUDGET}с)"

        # ─── Проверка геометрических размеров страницы (Pixel Bomb Protection) ───
        rect = getattr(page, 'rect', None)
        effective_dpi = min(config.OCR_DPI, config.MAX_OCR_DPI)
        if rect:
            est_pixels = (rect.width / 72.0 * effective_dpi) * (rect.height / 72.0 * effective_dpi)
            if est_pixels > config.MAX_OCR_IMAGE_PIXELS:
                return raw_text, False, f"OCR_IMAGE_TOO_LARGE ({int(est_pixels)} px > {config.MAX_OCR_IMAGE_PIXELS} px)"

        # ─── Контроль параллельности OCR через семафор ───
        acquired = _OCR_SEMAPHORE.acquire(timeout=config.MAX_OCR_PAGE_TIME)
        if not acquired:
            return raw_text, False, "OCR_WORKERS_BUSY"

        try:
            t_start = time.monotonic()
            textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=effective_dpi, full=True)
            ocr_text = page.get_text(textpage=textpage).replace('\xa0', ' ').replace('\xad', '-')
            elapsed = time.monotonic() - t_start

            if ocr_context is not None:
                ocr_context['pages_done'] = ocr_context.get('pages_done', 0) + 1
                ocr_context['total_time'] = ocr_context.get('total_time', 0.0) + elapsed

            if ocr_text.strip():
                if cls.extract_account_number(ocr_text) or not raw_text.strip():
                    return ocr_text, True, 'OK'
        except Exception as e:
            # Fallback на сырой текст при ошибке Tesseract
            return raw_text, False, f'OCR_ERROR ({e})'
        finally:
            _OCR_SEMAPHORE.release()

        return raw_text, False, 'NO_TEXT'

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
        ocr_context = {'pages_done': 0, 'total_time': 0.0}

        for i in range(len(pdf)):
            page = pdf[i]
            text, used_ocr, ocr_status = cls.extract_page_text(page, ocr_context)
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
                        if 'EXCEEDED' in ocr_status:
                            reason = f"Текст не извлечен (исчерпан лимит OCR для документа: {ocr_status})"
                        else:
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

        # Защита от PDF-бомб и исчерпания памяти
        total_pages = len(pdf)
        if total_pages > config.MAX_PDF_PAGES:
            pdf.close()
            return 0, 0, 1, 0, [f'📄 {original_filename}: ❌ Превышен лимит страниц ({total_pages} > {config.MAX_PDF_PAGES})'], []

        if existing_hashes is None:
            existing_hashes = set()

        added = 0
        skipped = 0
        orphan = 0
        duplicates = 0
        details = []
        receipts_to_insert = []
        batch_account_periods = set()

        documents, unattached_skipped = cls.group_pages_into_documents(pdf)

        for page_num, reason in unattached_skipped:
            skipped += 1
            details.append(f'  Стр. {page_num}: ❌ {reason}')

        # ─── Индексированный Batch Lookup счетов ───
        # Если known_accounts не передан (None), запрашиваем из БД только счета текущего файла
        valid_accounts = set()
        if known_accounts is not None:
            valid_accounts = known_accounts
        else:
            doc_accounts = [d.account for d in documents if d.account]
            if doc_accounts:
                from database.connection import get_db
                con_acc = get_db()
                try:
                    placeholders = ','.join('?' * len(doc_accounts))
                    rows = con_acc.execute(
                        f"SELECT account_number FROM accounts WHERE account_number IN ({placeholders})",  # nosec B608
                        doc_accounts
                    ).fetchall()
                    valid_accounts = {row[0] for row in rows}
                finally:
                    con_acc.close()

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

            # Защита от гигантского размера одной квитанции
            if len(extracted_pdf_bytes) > config.MAX_PDF_OUTPUT_SIZE:
                skipped += 1
                details.append(f'  {page_range_str}: счёт {account} ❌ Превышен лимит размера одной квитанции ({len(extracted_pdf_bytes) // 1024} KB > {config.MAX_PDF_OUTPUT_SIZE // 1024} KB)')
                continue

            # 1. Физический хеш (SHA-256 бинарного содержимого PDF)
            file_hash = cls.compute_file_hash(extracted_pdf_bytes)

            # 2. Логический / семантический хеш (нормализованный счет + период + текст)
            semantic_hash = cls.compute_semantic_hash(account, period, combined_text)
            content_hash = semantic_hash

            # Проверка дубликатов внутри текущей пачки
            if (account, period) in batch_account_periods:
                duplicates += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 дубликат в текущем запросе, пропущен')
                continue

            # Проверка дедупликации по хешам (внутри текущего сеанса)
            is_file_dup = file_hash in existing_hashes
            is_semantic_dup = semantic_hash in existing_hashes

            if is_file_dup or is_semantic_dup:
                duplicates += 1
                dup_type = "физический дубликат файла" if is_file_dup else "логический дубликат данных"
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 {dup_type}, пропущен')
                continue

            # Индексированная проверка существования записи и хешей в БД
            from database.connection import get_db
            con_check = get_db()
            try:
                # 1. Проверка по уникальной паре (account_number, period)
                existing_rec = con_check.execute(
                    "SELECT id, content_hash, file_hash, semantic_hash, pdf_file, status FROM receipts WHERE account_number = ? AND period = ?",
                    (account, period)
                ).fetchone()

                if existing_rec:
                    existing_file_hash = existing_rec.get('file_hash') if hasattr(existing_rec, 'get') else (existing_rec['file_hash'] if 'file_hash' in existing_rec.keys() else None)
                    existing_semantic_hash = existing_rec.get('semantic_hash') if hasattr(existing_rec, 'get') else (existing_rec['semantic_hash'] if 'semantic_hash' in existing_rec.keys() else None)
                    existing_content_hash = existing_rec.get('content_hash') if hasattr(existing_rec, 'get') else (existing_rec['content_hash'] if 'content_hash' in existing_rec.keys() else None)
                    existing_pdf_file = existing_rec.get('pdf_file') if hasattr(existing_rec, 'get') else (existing_rec['pdf_file'] if 'pdf_file' in existing_rec.keys() else None)
                    existing_status = str(existing_rec.get('status', '') if hasattr(existing_rec, 'get') else (existing_rec['status'] if 'status' in existing_rec.keys() else '')).upper()

                    # Проверяем, существует ли файл физически на диске
                    is_file_on_disk = False
                    if existing_pdf_file:
                        fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, existing_pdf_file))
                        if os.path.isfile(fp):
                            is_file_on_disk = True
                        else:
                            s1, s2 = config.get_receipt_shard_parts(account)
                            sharded_fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, s1, s2, os.path.basename(existing_pdf_file)))
                            flat_fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, os.path.basename(existing_pdf_file)))
                            if os.path.isfile(sharded_fp) or os.path.isfile(flat_fp):
                                is_file_on_disk = True

                    # Если файл на диске существует и статус READY:
                    if is_file_on_disk and (existing_status == 'READY' or not existing_status):
                        duplicates += 1
                        if (file_hash and file_hash == existing_file_hash) or \
                           (semantic_hash and semantic_hash == existing_semantic_hash) or \
                           (content_hash and content_hash == existing_content_hash):
                            details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 дубликат (уже в базе), пропущен')
                        else:
                            details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ⚠ конфликт: квитанция за этот период уже существует с другим содержимым, пропущен')
                        continue

                # 2. Индексированная проверка по хешам в БД (если хеш уже был сохранен ранее)
                hash_dup = con_check.execute(
                    "SELECT pdf_file, status FROM receipts WHERE (file_hash = ? OR semantic_hash = ? OR content_hash = ?) LIMIT 1",
                    (file_hash, semantic_hash, content_hash)
                ).fetchone()
                if hash_dup:
                    h_pdf = hash_dup.get('pdf_file') if hasattr(hash_dup, 'get') else (hash_dup['pdf_file'] if 'pdf_file' in hash_dup.keys() else None)
                    h_status = str(hash_dup.get('status', '') if hasattr(hash_dup, 'get') else (hash_dup['status'] if 'status' in hash_dup.keys() else '')).upper()
                    h_on_disk = False
                    if h_pdf and os.path.isfile(os.path.abspath(os.path.join(config.RECEIPTS_DIR, h_pdf))):
                        h_on_disk = True

                    if h_on_disk and (h_status == 'READY' or not h_status):
                        duplicates += 1
                        details.append(f'  {page_range_str}: счёт {account}, период «{period}» → 🔄 дубликат по содержимому (хеш найден в базе), пропущен')
                        continue
            finally:
                con_check.close()

            batch_account_periods.add((account, period))
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

            # Атомарная фиксация квитанции через 2-Phase Commit
            AtomicReceiptImporter.commit_staged_batch([staged_item])

            if not is_orphan:
                added += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ✅ привязан (READY)')
            else:
                orphan += 1
                details.append(f'  {page_range_str}: счёт {account}, период «{period}» → ⚠ счёта нет в базе')


        pdf.close()
        return added, orphan, skipped, duplicates, details, receipts_to_insert

pdf_processor = PDFProcessor()
