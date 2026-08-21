import os
import re
import config
from config import get_receipt_shard_parts
from database import get_db

RE_HOUSE = re.compile(r'(?:дом\s*(?:№\s*)?|д\.?\s*|д\s+|үй(?:і)?\s*)(\d+[\w\-\/]*)', re.IGNORECASE)
RE_FLAT = re.compile(r'(?:кв(?:артира)?\s*(?:№\s*)?|кв\.?\s*|к\.?\s*|комн?\.?\s*|комната\s*|пәт(?:ер)?\s*|бөлме\s*)(\d+[\w\-]*)', re.IGNORECASE)

STOP_WORDS = {
    'адрес', 'мекенжайы', 'мекенжай', 'мекен', 'жайы',
    'ул', 'улица', 'көшесі', 'көше', 'д', 'дом', 'үй', 'үйі',
    'кв', 'квартира', 'пәт', 'пәтер', 'пәтері', 'к', 'комн', 'комната', 'бөлме',
    'г', 'город', 'қала', 'қаласы',
    'обл', 'область', 'облысы',
    'р-н', 'район', 'аудан', 'ауданы',
    'с', 'село', 'аул', 'ауыл', 'ауылы', 'кент', 'кенті',
    'п', 'пос', 'поселок', 'станц', 'станция', 'ст', 'строение',
    'корп', 'корпус', 'пер', 'переулок',
    'пр', 'проспект', 'даңғылы', 'даңғыл',
    'мкр', 'микрорайон', 'шағынаудан', 'шағын'
}

def extract_addr_parts(text: str):
    """Извлекает номер дома и номер квартиры/комнаты из строки адреса."""
    house = ''
    flat = ''
    m_h = RE_HOUSE.search(text or '')
    if m_h:
        house = m_h.group(1).strip()
    m_f = RE_FLAT.search(text or '')
    if m_f:
        flat = m_f.group(1).strip()
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
                'SELECT address FROM receipts WHERE account_number = ? AND address IS NOT NULL AND address != "" ORDER BY period DESC LIMIT 1',
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

        # Числовые токены
        all_numbers = re.findall(r'\d+[\w\-]*', raw_query)

        # Если дом не распознан ключевым словом 'дом', но в запросе есть числа (например "Автобаза 1" или "Автобаза 2-1")
        if not q_house and all_numbers:
            q_house = all_numbers[0]
            if not q_flat and len(all_numbers) > 1:
                q_flat = all_numbers[1]

        # Если в запросе вообще нет номера дома
        if not q_house:
            return 'NEED_HOUSE', None, 'Пожалуйста, укажите номер дома (и квартиру при наличии). В целях безопасности поиск работает только по точному адресу.'

        # Текстовые поисковые слова (без чисел и стоп-слов)
        tokens = re.findall(r'[\w\-]+', raw_query)
        meaningful = [t for t in tokens if t.lower() not in STOP_WORDS and not re.search(r'^\d+$', t)]
        if not meaningful:
            meaningful = [t for t in tokens if t.lower() not in STOP_WORDS]
        if not meaningful:
            meaningful = tokens

        con = get_db()
        try:
            conds_r = ' AND '.join(['r.address LIKE ?' for _ in meaningful])
            params_r = [f'%{t}%' for t in meaningful]

            sql_receipts = f'''
                SELECT DISTINCT r.account_number, r.address
                FROM receipts r
                WHERE {conds_r} AND r.address IS NOT NULL AND r.address != ""
            '''
            rows = con.execute(sql_receipts, params_r).fetchall()

            if not rows:
                conds_a = ' AND '.join(['a.address LIKE ?' for _ in meaningful])
                params_a = [f'%{t}%' for t in meaningful]
                sql_accounts = f'''
                    SELECT DISTINCT a.account_number, a.address
                    FROM accounts a
                    WHERE {conds_a} AND a.address IS NOT NULL AND a.address != ""
                '''
                rows = con.execute(sql_accounts, params_a).fetchall()

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
                    'flat': r_flat
                })

            if not filtered:
                return 'NOT_FOUND', None, f'По адресу «{raw_query}» квитанция не найдена. Проверьте номер дома и квартиры.'

            # Группируем по уникальным лицевым счетам
            unique_accounts = {item['account_number']: item for item in filtered}

            if len(unique_accounts) == 1:
                acc_data = list(unique_accounts.values())[0]
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
                    'SELECT period, pdf_file, access_token FROM receipts WHERE account_number = ? AND period = ? ORDER BY period DESC',
                    (account_number, period_filter)
                ).fetchall()
            else:
                return con.execute(
                    'SELECT period, pdf_file, access_token FROM receipts WHERE account_number = ? ORDER BY period DESC',
                    (account_number,)
                ).fetchall()
        finally:
            con.close()

    @staticmethod
    def get_distinct_periods():
        con = get_db()
        try:
            return con.execute('SELECT DISTINCT period FROM receipts ORDER BY period').fetchall()
        finally:
            con.close()

    @staticmethod
    def get_pdf_by_token(token: str):
        """Возвращает абсолютный путь к файлу PDF по токену доступа (IDOR & Path Traversal safe)."""
        if not token or len(token) != 32 or not all(c in '0123456789abcdef' for c in token):
            return None
        con = get_db()
        try:
            r = con.execute('SELECT pdf_file, account_number FROM receipts WHERE access_token=?', (token,)).fetchone()
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
