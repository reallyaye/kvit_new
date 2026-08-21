import os
try:
    import pytest
except ImportError:
    pytest = None
from database import get_db
from services.receipts.receipt_service import receipt_service

@pytest.fixture
def seed_receipt_data(tmp_path):
    con = get_db()
    con.execute('INSERT INTO accounts(account_number, customer_name, address) VALUES (?,?,?)',
                ('800100', 'Алимов Алишер', 'пр. Достык 10'))

    # Создаём физический файл PDF для проверки выдачи по токену
    valid_token = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'
    pdf_filename = '800100_test.pdf'

    from config import RECEIPTS_DIR
    real_pdf_path = os.path.join(RECEIPTS_DIR, pdf_filename)
    with open(real_pdf_path, 'wb') as f:
        f.write(b'%PDF-1.4 test receipt')

    con.execute('INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token) VALUES (?,?,?,?,?)',
                ('800100', 'Март 2026', pdf_filename, 'hash100', valid_token))
    con.commit()
    con.close()
    return valid_token, real_pdf_path

def test_get_account(seed_receipt_data):
    acc = receipt_service.get_account('800100')
    assert acc is not None
    assert acc['customer_name'] == 'Алимов Алишер'
    assert acc['address'] == 'пр. Достык 10'

    assert receipt_service.get_account('999999') is None

def test_get_receipts(seed_receipt_data):
    receipts = receipt_service.get_receipts('800100')
    assert len(receipts) == 1
    assert receipts[0]['period'] == 'Март 2026'

    receipts_march = receipt_service.get_receipts('800100', 'Март 2026')
    assert len(receipts_march) == 1

    receipts_empty = receipt_service.get_receipts('800100', 'Январь 2020')
    assert len(receipts_empty) == 0

def test_get_pdf_by_token_valid(seed_receipt_data):
    valid_token, real_path = seed_receipt_data
    found_path = receipt_service.get_pdf_by_token(valid_token)
    assert found_path == real_path

def test_get_pdf_by_token_invalid_or_traversal(seed_receipt_data):
    # Неверная длина / символы
    assert receipt_service.get_pdf_by_token('') is None
    assert receipt_service.get_pdf_by_token('short') is None
    assert receipt_service.get_pdf_by_token('../../../etc/passwd') is None
    assert receipt_service.get_pdf_by_token('00000000000000000000000000000000') is None

def test_get_pdf_by_token_sharded():
    from config import RECEIPTS_DIR
    con = get_db()
    sharded_token = '11223344556677889900aabbccddeeff'
    rel_path = '80/01/800100_sharded.pdf'
    full_path = os.path.join(RECEIPTS_DIR, '80', '01', '800100_sharded.pdf')
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'wb') as f:
        f.write(b'%PDF-1.4 test sharded')

    con.execute('INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token) VALUES (?,?,?,?,?)',
                ('800100', 'Февраль 2026', rel_path, 'shardedhash', sharded_token))
    con.commit()
    con.close()

    found_path = receipt_service.get_pdf_by_token(sharded_token)
    assert found_path == os.path.abspath(full_path)

def test_search_accounts_by_address(seed_receipt_data):
    # Точный поиск с номером дома
    res = receipt_service.search_accounts_by_address('Достык 10')
    assert len(res) == 1
    assert res[0]['account_number'] == '800100'
    assert 'пр. Достык 10' in res[0]['address']

    # Поиск с сокращениями
    res_abbr = receipt_service.search_accounts_by_address('пр. Достык, д. 10')
    assert len(res_abbr) == 1
    assert res_abbr[0]['account_number'] == '800100'

    # Поиск без номера дома (возвращает пустой список - список соседей скрыт)
    res_no_house = receipt_service.search_accounts_by_address('пр. Достык')
    assert len(res_no_house) == 0

    # Поиск несуществующего адреса
    res_none = receipt_service.search_accounts_by_address('Несуществующая улица 999')
    assert len(res_none) == 0

    # Пустой запрос
    assert receipt_service.search_accounts_by_address('') == []
    assert receipt_service.search_accounts_by_address('   ') == []

def test_search_account_by_specific_address(seed_receipt_data):
    # 1. Запрос без номера дома -> статус NEED_HOUSE
    status, acc, msg = receipt_service.search_account_by_specific_address('пр. Достык')
    assert status == 'NEED_HOUSE'
    assert acc is None
    assert 'номер дома' in msg

    # 2. Точный запрос с номером дома -> статус EXACT_MATCH
    status, acc, msg = receipt_service.search_account_by_specific_address('пр. Достык, дом 10')
    assert status == 'EXACT_MATCH'
    assert acc['account_number'] == '800100'

    # 3. Несуществующий адрес -> статус NOT_FOUND
    status, acc, msg = receipt_service.search_account_by_specific_address('Улица Призрачная, дом 777')
    assert status == 'NOT_FOUND'
    assert acc is None

def test_privacy_search_view_no_personal_data(seed_receipt_data):
    from templates.search_views import (
        render_search_result, render_address_clarification_prompt, render_address_not_found
    )

    acc = receipt_service.get_account('800100')
    receipts = receipt_service.get_receipts('800100')

    # Проверяем карточку с 1 квитанцией
    html_single = render_search_result('800100', '', acc, receipts)
    assert 'Алимов Алишер' not in html_single
    assert 'Контрагент' not in html_single
    assert '800100' in html_single
    assert 'пр. Достык 10' in html_single

    # Проверяем карточку без квитанций
    html_no_receipt = render_search_result('800100', 'Январь 2020', acc, [])
    assert 'Алимов Алишер' not in html_no_receipt
    assert 'Контрагент' not in html_no_receipt

    # Проверяем карточку множественных квитанций
    html_multi = render_search_result('800100', '', acc, receipts + receipts)
    assert 'Алимов Алишер' not in html_multi
    assert 'Контрагент' not in html_multi

    # Проверяем экран уточнения адреса (нет чужих адресов и ФИО)
    html_prompt = render_address_clarification_prompt('Автобаза', '', 'Пожалуйста, укажите номер дома.')
    assert 'Алимов Алишер' not in html_prompt
    assert 'Контрагент' not in html_prompt
    assert 'Уточните адрес' in html_prompt

    # Проверяем экран "не найдено"
    html_not_found = render_address_not_found('Несуществующая 99', '', 'Квитанция не найдена.')
    assert 'Алимов Алишер' not in html_not_found
    assert 'Контрагент' not in html_not_found

def test_search_by_exact_receipt_address():
    con = get_db()
    # Квитанция с точным адресом (дом, квартира)
    con.execute('''
        INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token, address)
        VALUES (?,?,?,?,?,?)
    ''', ('020002', 'Июль 2026', '020002_0002.pdf', 'hash020002', 'tok02000200000000000000000000000',
          'Нуринский район, с. Балыктыколь, ул. Назарбаева, дом № 5, к. 1'))
    con.commit()
    con.close()

    # Поиск по конкретному адресу из квитанции
    status, acc, msg = receipt_service.search_account_by_specific_address('Балыктыколь Назарбаева 5 к 1')
    assert status == 'EXACT_MATCH'
    assert acc['account_number'] == '020002'
    assert 'дом № 5, к. 1' in acc['address']

    # Проверка получения аккаунта с точным адресом из квитанции
    acc_row = receipt_service.get_account('020002')
    assert acc_row is not None
    assert acc_row['account_number'] == '020002'
    assert 'дом № 5, к. 1' in acc_row['address']


