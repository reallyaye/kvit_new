# -*- coding: utf-8 -*-
"""
Тесты Wave 3: Чистый тестовый набор, линтер и канонические данные.
Проверяют:
1. Целостность канонических данных портала в data/ (наличие обязательных страниц).
2. Синхронность между data/ и docs/data/.
3. Корректность работы парсера реестров import_accounts (CSV / Excel).
4. Конфигурацию pyproject.toml.
"""
import json
import os

from import_accounts import detect_column_mapping, read_csv_records
from scripts.sync_portal_data import compute_sha256, validate_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_canonical_portal_pages_integrity():
    """Канонический файл data/extracted_portal_pages.json существует и содержит все обязательные страницы."""
    pages_path = os.path.join(BASE_DIR, 'data', 'extracted_portal_pages.json')
    assert os.path.isfile(pages_path)
    assert validate_json(pages_path)

    with open(pages_path, 'r', encoding='utf-8') as f:
        pages = json.load(f)

    required_keys = ['home', 'contacts', 'tarif', 'zakup', 'consumers', 'tu']
    for key in required_keys:
        assert key in pages, f"Обязательная страница {key} отсутствует в каноническом реестре"
        assert 'html' in pages[key]
        assert len(pages[key]['html']) > 50


def test_canonical_and_docs_data_sync():
    """Файлы в data/ и docs/data/ синхронизированы по SHA256."""
    tracked = ['extracted_portal_pages.json', 'documents.json']
    for fname in tracked:
        src = os.path.join(BASE_DIR, 'data', fname)
        dst = os.path.join(BASE_DIR, 'docs', 'data', fname)
        assert os.path.isfile(src)
        assert os.path.isfile(dst)
        assert compute_sha256(src) == compute_sha256(dst), f"Файл {fname} рассинхронизирован"


def test_import_accounts_csv_records(tmp_path):
    """Парсинг CSV-записей через read_csv_records с составными адресами и очисткой."""
    csv_content = (
        "Лицевой счет,ФИО,Улица,Дом,Квартира\n"
        "102938.0,Иванов Иван,ул. Абая,15,4\n"
        "102939,Петров Петр,ул. Ленина,20,12\n"
    )
    csv_file = tmp_path / "test_accounts.csv"
    csv_file.write_text(csv_content, encoding='utf-8')

    records = list(read_csv_records(str(csv_file)))
    assert len(records) == 2

    # Проверяем очистку экспоненциального/float формата .0
    assert records[0]['account_number'] == '102938'
    assert records[0]['customer_name'] == 'Иванов Иван'
    assert 'ул. Абая' in records[0]['address']
    assert 'д. 15' in records[0]['address']
    assert 'кв. 4' in records[0]['address']

    assert records[1]['account_number'] == '102939'
    assert records[1]['customer_name'] == 'Петров Петр'


def test_detect_column_mapping():
    """Распознавание колонок заголовков реестров абонентов."""
    headers = ['Номер л/с', 'Потребитель', 'Адрес потребителя']
    mapping = detect_column_mapping(headers)
    assert mapping.get('account_number') == 0
    assert mapping.get('customer_name') == 1
    assert mapping.get('address') == 2
