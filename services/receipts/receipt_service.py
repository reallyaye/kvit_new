import os
import re
import config
from config import get_receipt_shard_parts
from database import get_db

import difflib

KZ_RU_CHAR_MAP = str.maketrans({
    'ә': 'а', 'і': 'и', 'ң': 'н', 'ғ': 'г', 'ү': 'у', 'ұ': 'у', 'қ': 'к', 'ө': 'о', 'һ': 'х',
    'Ә': 'А', 'І': 'И', 'Ң': 'Н', 'Ғ': 'Г', 'Ү': 'У', 'Ұ': 'У', 'Қ': 'К', 'Ө': 'О', 'Һ': 'Х',
    'ё': 'е', 'Ё': 'Е'
})

def normalize_text_chars(s: str) -> str:
    """Нормализует специфические символы казахского и русского алфавитов."""
    return (s or '').translate(KZ_RU_CHAR_MAP).lower().strip()

RE_HOUSE = re.compile(
    r'(?:дом\s*(?:№\s*)?|д\.?\s*|д\s+|үй(?:і)?\s*|корп(?:ус)?\.?\s*|стр(?:оение)?\.?\s*)(\d+[\w\-\/]*)',
    re.IGNORECASE
)
RE_FLAT = re.compile(
    r'(?:кв(?:артира)?\s*(?:№\s*)?|кв\.?\s*|к\.?\s*|комн?\.?\s*|комната\s*|пәт(?:ер)?(?:і)?\s*|бөлме(?:сі)?\s*)(\d+[\w\-]*)',
    re.IGNORECASE
)

# Шаблон для составного адреса в конце строки: например "Абая 10-5" или "Абая 10/5" или "Абая 10, кв 5"
RE_COMPOUND_END = re.compile(
    r'(\d+[a-zA-Zа-яА-Я]?)[/-](\d+[a-zA-Zа-яА-Я]?)$',
    re.IGNORECASE
)

STOP_WORDS = {
    'адрес', 'мекенжайы', 'мекенжай', 'мекен', 'жайы',
    'ул', 'улица', 'көшесі', 'көше', 'д', 'дом', 'үй', 'үйі',
    'кв', 'квартира', 'пәт', 'пәтер', 'пәтері', 'к', 'комн', 'комната', 'бөлме', 'бөлмесі',
    'г', 'город', 'қала', 'қаласы',
    'обл', 'область', 'облысы',
    'р-н', 'район', 'аудан', 'ауданы',
    'с', 'село', 'аул', 'ауыл', 'ауылы', 'кент', 'кенті',
    'п', 'пос', 'поселок', 'станц', 'станция', 'ст', 'строение',
    'корп', 'корпус', 'пер', 'переулок',
    'пр', 'проспект', 'даңғылы', 'даңғыл',
    'шағынаудан', 'шағынауданы'
}

def extract_addr_parts(text: str):
    """
    Извлекает номер дома и номер квартиры/комнаты из строки адреса.
    Поддерживает:
    - Явные обозначения ('дом 10/2', 'кв 5', 'үй 12 пәтер 3')
    - Запись через дефис / слэш ('Абая 10-5' -> дом 10, кв 5; 'Абая 10/2-5' -> дом 10/2, кв 5)
    """
    raw = (text or '').strip()
    house = ''
    flat = ''

    # 1. Поиск явных ключевых слов квартиры
    m_f = RE_FLAT.search(raw)
    if m_f:
        flat = m_f.group(1).strip()

    # 2. Поиск явных ключевых слов дома
    m_h = RE_HOUSE.search(raw)
    if m_h:
        house = m_h.group(1).strip()

    # 3. Если квартира не найдена, проверяем составную запись в конце (например "Абая 10-5")
    if not flat:
        m_comp = RE_COMPOUND_END.search(raw)
        if m_comp:
            h_cand, f_cand = m_comp.group(1).strip(), m_comp.group(2).strip()
            if not house or house == h_cand:
                house = h_cand
                flat = f_cand

    return house, flat

class ReceiptService:
    """Сервис для поиска и выдачи квитанций и информации по лицевым счетам."""

    @staticmethod
    def get_account(account_number: str):
        con = get_db()
        try:
            row = con.execute(
                'SELECT account_number, customer_name, address FROM accounts WHERE account_number = ?',
                (account_number,)
            ).fetchone()

            # Проверяем наличие точного адреса из квитанции
            rec_row = con.execute(
                "SELECT address FROM receipts WHERE account_number = ? AND address IS NOT NULL AND address != '' ORDER BY period DESC LIMIT 1",
                (account_number,)
            ).fetchone()
            rec_addr = rec_row['address'] if rec_row and rec_row['address'] else None

            if row:
                addr = rec_addr or row['address']
                return {
                    'account_number': row['account_number'],
                    'customer_name': row['customer_name'],
                    'address': addr
                }
            elif rec_addr:
                return {
                    'account_number': account_number,
                    'customer_name': '',
                    'address': rec_addr
                }
            return None
        finally:
            con.close()

    @classmethod
    def search_by_structured_address(cls, street: str, house: str, flat: str = ''):
        """
        Поиск по раздельным структурированным полям: Улица, Дом, Квартира.
        """
        street_clean = (street or '').strip()
        house_clean = (house or '').strip()
        flat_clean = (flat or '').strip()

        if not street_clean and not house_clean:
            return 'EMPTY', None, 'Пожалуйста, укажите улицу и номер дома.'
        if not house_clean:
            return 'NEED_HOUSE', None, 'Пожалуйста, укажите номер дома.'

        # Формируем составную строку для надежного сопоставления
        parts = [street_clean]
        if house_clean:
            parts.append(f"дом {house_clean}")
        if flat_clean:
            parts.append(f"кв. {flat_clean}")

        query = ", ".join(parts)
        return cls.search_account_by_specific_address(query)

    @classmethod
    def _find_fuzzy_street_match(cls, con, query_tokens):
        """
        Ищет похожую улицу в базе данных (исправление опечаток).
        Возвращает (best_matched_street_name, similarity_ratio) или (None, 0).
        """
        if not query_tokens:
            return None, 0

        # Собираем все уникальные адреса из БД
        rows = con.execute('''
            SELECT DISTINCT address FROM receipts WHERE address IS NOT NULL AND address != ''
            UNION
            SELECT DISTINCT address FROM accounts WHERE address IS NOT NULL AND address != ''
        ''').fetchall()

        if not rows:
            return None, 0

        query_str_norm = normalize_text_chars(" ".join(query_tokens))
        best_token = None
        best_ratio = 0.0

        for r in rows:
            addr = r['address'] or ''
            addr_tokens = re.findall(r'[\w\-]+', addr)
            meaningful_db = [t for t in addr_tokens if normalize_text_chars(t) not in STOP_WORDS and not re.match(r'^\d+$', t)]

            for db_t in meaningful_db:
                db_t_norm = normalize_text_chars(db_t)
                for q_t in query_tokens:
                    q_t_norm = normalize_text_chars(q_t)
                    # Если длины слишком разные, пропускаем
                    if abs(len(db_t_norm) - len(q_t_norm)) > 3:
                        continue
                    ratio = difflib.SequenceMatcher(None, q_t_norm, db_t_norm).ratio()
                    if ratio > best_ratio and ratio >= 0.75:
                        best_ratio = ratio
                        best_token = db_t

        return best_token, best_ratio

    @classmethod
    def search_account_by_specific_address(cls, address_query: str):
        """
        Строгий поиск лицевого счета по конкретному адресу.
        Защита приватности: никогда не выводит список чужих адресов/лицевых счетов соседей.
        Возвращает кортеж: (status, account_info, prompt_message)
          status:
            - 'EXACT_MATCH': найден единственный конкретный лицевой счёт
            - 'NEED_HOUSE': не указан номер дома (запрос слишком общий)
            - 'NEED_FLAT': указан дом, но в нем несколько квартир/комнат (требуется номер квартиры)
            - 'NEED_CLARIFICATION': найдено несколько записей, требуется уточнение
            - 'NOT_FOUND': квитанция по данному адресу не найдена
            - 'EMPTY': пустой запрос
        """
        raw_query = (address_query or '').strip()
        if not raw_query:
            return 'EMPTY', None, 'Пожалуйста, введите адрес объекта.'

        # Извлекаем дом и квартиру из запроса
        q_house, q_flat = extract_addr_parts(raw_query)

        # Числовые токены: исключаем суффиксы названий вроде "Аксай-4" или "Самал-2"
        all_numbers = [
            m.group(0) for m in re.finditer(r'(?<![а-яa-z0-9_]\-)(?<![а-яa-z0-9_])\d+[\w\-\/]*(?!\w)', raw_query, re.IGNORECASE)
        ]

        # Если дом не распознан ключевым словом 'дом', но в запросе есть числа (например "Автобаза 1", "Автобаза 2-1", "мкр. Аксай-4, 12")
        if not q_house and all_numbers:
            q_house = all_numbers[0]
            if not q_flat and len(all_numbers) > 1:
                q_flat = all_numbers[1]

        # Если в запросе вообще нет номера дома
        if not q_house:
            return 'NEED_HOUSE', None, 'Пожалуйста, укажите номер дома (и квартиру при наличии). В целях безопасности поиск работает только по точному адресу.'

        # Текстовые поисковые слова (без чисел и стоп-слов)
        tokens = re.findall(r'[\w\-]+', raw_query)
        meaningful = [
            t for t in tokens
            if normalize_text_chars(t) not in STOP_WORDS and not re.search(r'^\d+$', t) and t.lower() != q_house.lower() and t.lower() != q_flat.lower()
        ]
        if not meaningful:
            meaningful = [t for t in tokens if normalize_text_chars(t) not in STOP_WORDS and t.lower() != q_house.lower() and t.lower() != q_flat.lower()]
        if not meaningful:
            meaningful = [t for t in tokens if t.lower() != q_house.lower() and t.lower() != q_flat.lower()]

        con = get_db()
        corrected_street = None
        is_corrected = False

        try:
            # 1. Попытка прямого поиска по токенам
            conds_r = ' AND '.join(['r.address LIKE ?' for _ in meaningful]) if meaningful else '1=1'
            params_r = [f'%{t}%' for t in meaningful]

            sql_receipts = f'''
                SELECT DISTINCT r.account_number, r.address
                FROM receipts r
                WHERE {conds_r} AND r.address IS NOT NULL AND r.address != ''
            '''
            rows = con.execute(sql_receipts, params_r).fetchall()

            if not rows:
                conds_a = ' AND '.join(['a.address LIKE ?' for _ in meaningful]) if meaningful else '1=1'
                params_a = [f'%{t}%' for t in meaningful]
                sql_accounts = f'''
                    SELECT DISTINCT a.account_number, a.address
                    FROM accounts a
                    WHERE {conds_a} AND a.address IS NOT NULL AND a.address != ''
                '''
                rows = con.execute(sql_accounts, params_a).fetchall()

            # 2. Если точный поиск не нашел совпадений, пробуем нечеткий поиск (Fuzzy Matching / опечатки)
            if not rows and meaningful:
                fuzzy_token, ratio = cls._find_fuzzy_street_match(con, meaningful)
                if fuzzy_token:
                    corrected_street = fuzzy_token
                    is_corrected = True
                    # Повторяем поиск с исправленным названием улицы
                    sql_fuzzy_r = '''
                        SELECT DISTINCT r.account_number, r.address
                        FROM receipts r
                        WHERE r.address LIKE ? AND r.address IS NOT NULL AND r.address != ''
                    '''
                    rows = con.execute(sql_fuzzy_r, [f'%{fuzzy_token}%']).fetchall()
                    if not rows:
                        sql_fuzzy_a = '''
                            SELECT DISTINCT a.account_number, a.address
                            FROM accounts a
                            WHERE a.address LIKE ? AND a.address IS NOT NULL AND a.address != ''
                        '''
                        rows = con.execute(sql_fuzzy_a, [f'%{fuzzy_token}%']).fetchall()

            if not rows:
                return 'NOT_FOUND', None, f'По адресу «{raw_query}» квитанции не найдены. Проверьте правильность написания.'

            # Фильтруем результаты строго по номеру дома и квартиры
            filtered = []
            for r in rows:
                addr = r['address']
                r_house, r_flat = extract_addr_parts(addr)

                # 1. Проверка номера дома
                if q_house:
                    if r_house:
                        if r_house.lower() != q_house.lower():
                            continue
                    else:
                        pattern = r'(?<!\d)' + re.escape(q_house.lower()) + r'(?!\d)'
                        if not re.search(pattern, addr.lower()):
                            continue

                # 2. Проверка номера квартиры/комнаты
                if q_flat:
                    if r_flat:
                        if r_flat.lower() != q_flat.lower():
                            continue
                    else:
                        pattern = r'(?<!\d)' + re.escape(q_flat.lower()) + r'(?!\d)'
                        if not re.search(pattern, addr.lower()):
                            continue

                filtered.append({
                    'account_number': str(r['account_number']),
                    'address': addr,
                    'house': r_house,
                    'flat': r_flat,
                    'is_corrected': is_corrected,
                    'corrected_street': corrected_street,
                    'original_query': raw_query
                })

            if not filtered:
                return 'NOT_FOUND', None, f'По адресу «{raw_query}» квитанция не найдена. Проверьте номер дома и квартиры.'

            # Группируем по уникальным лицевым счетам
            unique_accounts = {item['account_number']: item for item in filtered}

            if len(unique_accounts) == 1:
                acc_data = next(iter(unique_accounts.values()))
                return 'EXACT_MATCH', acc_data, 'Квитанция найдена'

            # Если найдено несколько счетов в одном доме:
            flats = {item['flat'] for item in filtered if item['flat']}
            if len(flats) > 1 and not q_flat:
                return 'NEED_FLAT', None, f'В доме № {q_house} зарегистрировано несколько квартир/комнат. Пожалуйста, укажите номер вашей квартиры (например: дом {q_house}, кв. 1).'

            # Если несколько разных счетов привязаны к одному адресу
            return 'NEED_CLARIFICATION', None, 'По вашему адресу найдено несколько лицевых счетов. Пожалуйста, воспользуйтесь поиском по номеру лицевого счёта.'

        finally:
            con.close()

    @classmethod
    def search_accounts_by_address(cls, address_query: str, limit: int = 50):
        """Обратная совместимость: возвращает список счетов."""
        status, acc, msg = cls.search_account_by_specific_address(address_query)
        if status == 'EXACT_MATCH' and acc:
            return [acc]
        return []

    @staticmethod
    def get_receipts(account_number: str, period_filter: str = None):
        con = get_db()
        try:
            if period_filter:
                return con.execute(
                    "SELECT period, pdf_file, access_token FROM receipts WHERE account_number = ? AND period = ? AND (status = 'READY' OR status IS NULL) ORDER BY period DESC",
                    (account_number, period_filter)
                ).fetchall()
            else:
                return con.execute(
                    "SELECT period, pdf_file, access_token FROM receipts WHERE account_number = ? AND (status = 'READY' OR status IS NULL) ORDER BY period DESC",
                    (account_number,)
                ).fetchall()
        finally:
            con.close()

    @staticmethod
    def get_distinct_periods():
        con = get_db()
        try:
            return con.execute("SELECT DISTINCT period FROM receipts WHERE status = 'READY' OR status IS NULL ORDER BY period").fetchall()
        finally:
            con.close()

    @staticmethod
    def get_pdf_by_token(token: str):
        """Возвращает абсолютный путь к файлу PDF по токену доступа (IDOR & Path Traversal safe)."""
        if not token or len(token) != 32 or not all(c in '0123456789abcdef' for c in token):
            return None
        con = get_db()
        try:
            r = con.execute("SELECT pdf_file, account_number FROM receipts WHERE access_token=? AND (status = 'READY' OR status IS NULL)", (token,)).fetchone()
            if not r:
                return None

            raw_file = r['pdf_file']
            receipts_abs = os.path.abspath(config.RECEIPTS_DIR)
            fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, raw_file))

            # Защита от Path Traversal: путь обязан находиться строго внутри RECEIPTS_DIR
            try:
                if os.path.commonpath([receipts_abs, fp]) != receipts_abs:
                    return None
            except ValueError:
                return None

            if os.path.isfile(fp):
                return fp

            # Обратная совместимость при миграции структуры:
            # 1. Если в БД записан плоский файл '800146_hash.pdf', но на диске он уже шардирован
            acc = r['account_number'] if 'account_number' in r.keys() else None
            base_filename = os.path.basename(raw_file)
            if acc:
                s1, s2 = get_receipt_shard_parts(acc)
                sharded_fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, s1, s2, base_filename))
                if os.path.isfile(sharded_fp):
                    return sharded_fp

            # 2. Если в БД записан шардированный путь '80/01/800146_hash.pdf', но файл лежит в корне
            flat_fp = os.path.abspath(os.path.join(config.RECEIPTS_DIR, base_filename))
            if os.path.isfile(flat_fp):
                return flat_fp

            return None
        finally:
            con.close()

    @staticmethod
    def get_stats():
        con = get_db()
        try:
            total_acc = con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
            total_rec = con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
            return total_acc, total_rec
        finally:
            con.close()

receipt_service = ReceiptService()
