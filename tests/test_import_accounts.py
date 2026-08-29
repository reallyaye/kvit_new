import csv
import json
import os
import sqlite3
import pytest

from import_accounts import (
    detect_column_mapping,
    detect_encoding,
    export_accounts_to_csv,
    import_accounts_file,
    read_csv_records,
    read_json_records,
    read_sqlite_records,
)
from database.connection import get_db, write_transaction


@pytest.fixture(autouse=True)
def clean_accounts_table():
    with write_transaction() as con:
        con.execute("DELETE FROM accounts")
    yield
    with write_transaction() as con:
        con.execute("DELETE FROM accounts")


def test_detect_column_mapping():
    headers_ru = ["№ Лицевого счета", "ФИО Абонента", "Полный Адрес", "Район"]
    m = detect_column_mapping(headers_ru)
    assert m["account_number"] == 0
    assert m["customer_name"] == 1
    assert m["address"] == 2
    assert m["district"] == 3

    headers_kz = ["Жеке шот", "Тұтынушы", "Мекенжайы"]
    m_kz = detect_column_mapping(headers_kz)
    assert m_kz["account_number"] == 0
    assert m_kz["customer_name"] == 1
    assert m_kz["address"] == 2


def test_import_csv_utf8_and_cp1251(tmp_path):
    csv_utf8 = str(tmp_path / "accounts_utf8.csv")
    with open(csv_utf8, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Лицевой счет", "ФИО", "Адрес"])
        writer.writerow(["100001", "Иванов Иван", "ул. Абая 10, кв 5"])
        writer.writerow(["100002", "Петров Петр", "ул. Ленина 25"])

    res = import_accounts_file(csv_utf8, mode="upsert", verbose=False)
    assert res["imported"] == 2
    assert res["total_in_db"] == 2

    # Проверяем чтение из БД
    con = get_db()
    try:
        row = con.execute("SELECT customer_name, address FROM accounts WHERE account_number = '100001'").fetchone()
        assert row["customer_name"] == "Иванов Иван"
        assert row["address"] == "ул. Абая 10, кв 5"
    finally:
        con.close()

    # Проверка CP1251
    csv_cp1251 = str(tmp_path / "accounts_cp1251.csv")
    with open(csv_cp1251, "w", encoding="cp1251", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Лицевой счет", "ФИО", "Адрес"])
        writer.writerow(["100003", "Сидоров Сергей", "ул. Мира 1"])

    res_cp = import_accounts_file(csv_cp1251, mode="upsert", verbose=False)
    assert res_cp["imported"] == 1
    assert res_cp["total_in_db"] == 3


def test_import_json_and_export(tmp_path):
    json_path = str(tmp_path / "accounts.json")
    data = [
        {"account_number": "200001", "customer_name": "Ахметов А.", "address": "мкр. 1, д. 2"},
        {"account_number": "200002", "customer_name": "Бериков Б.", "address": "мкр. 2, д. 4"},
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    res = import_accounts_file(json_path, mode="replace", verbose=False)
    assert res["imported"] == 2
    assert res["total_in_db"] == 2

    # Экспорт в CSV
    export_csv = str(tmp_path / "exported.csv")
    exported_count = export_accounts_to_csv(export_csv, verbose=False)
    assert exported_count == 2
    assert os.path.isfile(export_csv)


def test_import_from_sqlite_database(tmp_path):
    src_db = str(tmp_path / "legacy.sqlite3")
    con = sqlite3.connect(src_db)
    con.execute('''
        CREATE TABLE accounts (
            account_number TEXT PRIMARY KEY,
            customer_name TEXT,
            address TEXT,
            street TEXT,
            building TEXT,
            corpus TEXT,
            district TEXT,
            organization TEXT
        )
    ''')
    con.execute("INSERT INTO accounts (account_number, customer_name, address) VALUES ('300001', 'Кузнецов К.', 'ул. Победы 7')")
    con.commit()
    con.close()

    res = import_accounts_file(src_db, mode="upsert", verbose=False)
    assert res["imported"] == 1
    assert res["total_in_db"] == 1
