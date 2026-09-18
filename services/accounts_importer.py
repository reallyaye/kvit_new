#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/accounts_importer.py - Readers and mapping utilities for account imports.
"""

import csv
import json
import os
import re
import sqlite3
from typing import Dict, Generator, List

COLUMN_SYNONYMS = {
    'account_number': [
        'account_number', 'account', 'account_no', 'acc', 'acc_num',
        'лицевой счет', 'лицевой_счет', 'лицевой_счёт', 'лицевой', 'лс', 'л/с',
        'номер счета', 'номер_счета', 'номер_счёта', 'счет', 'счёт', 'код',
        'жеке шот', 'жеке_шот', 'шот'
    ],
    'customer_name': [
        'customer_name', 'name', 'fio', 'full_name', 'client', 'payer',
        'фио', 'ф.и.о.', 'абонент', 'плательщик', 'потребитель', 'клиент',
        'собственник', 'жилец', 'имя', 'аты-жөні', 'тұтынушы'
    ],
    'address': [
        'address', 'addr', 'full_address', 'street_address',
        'адрес', 'полный адрес', 'мекенжай', 'мекенжайы', 'адрес проживания'
    ],
    'street': [
        'street', 'street_name', 'улица', 'көше', 'көшесі', 'проспект', 'переулок'
    ],
    'building': [
        'building', 'house', 'house_number', 'дом', 'үй', 'үйі', 'здание'
    ],
    'corpus': [
        'corpus', 'corp', 'building_block', 'корпус', 'корп', 'строение', 'стр', 'блок'
    ],
    'flat': [
        'flat', 'apartment', 'apt', 'room', 'квартира', 'кв', 'пәтер', 'комната'
    ],
    'district': [
        'district', 'area', 'region', 'район', 'аудан', 'микрорайон', 'мкр'
    ],
    'organization': [
        'organization', 'org', 'company', 'branch',
        'организация', 'предприятие', 'участок', 'участок жкх', 'домком', 'кск', 'оси'
    ]
}


def normalize_header(header: str) -> str:
    """Очищает и нормализует строку заголовка для сопоставления."""
    clean = re.sub(r'[\s_\-–—/\\.]+', ' ', str(header).lower().strip())
    clean = clean.replace('№', '').replace('#', '').strip()
    return clean


def detect_column_mapping(headers: List[str]) -> Dict[str, int]:
    """Автоматически сопоставляет заголовки файла с полями таблицы accounts."""
    mapping = {}
    normalized_headers = [normalize_header(h) for h in headers]

    for field, synonyms in COLUMN_SYNONYMS.items():
        matched_idx = None
        for idx, nh in enumerate(normalized_headers):
            if nh in synonyms:
                matched_idx = idx
                break
        if matched_idx is None:
            for idx, nh in enumerate(normalized_headers):
                if any(syn in nh for syn in synonyms):
                    matched_idx = idx
                    break
        if matched_idx is not None:
            mapping[field] = matched_idx

    if 'account_number' not in mapping and headers:
        mapping['account_number'] = 0

    return mapping


def detect_encoding(file_path: str) -> str:
    """Определяет кодировку текстового файла (UTF-8, Windows-1251, Latin1)."""
    with open(file_path, 'rb') as f:
        raw_sample = f.read(65536)

    if raw_sample.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'

    try:
        raw_sample.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    try:
        raw_sample.decode('cp1251')
        return 'cp1251'
    except UnicodeDecodeError:
        pass

    return 'utf-8'


def read_csv_records(file_path: str) -> Generator[Dict[str, str], None, None]:
    """Потоково считывает строки из CSV/TSV файла с автоопределением кодировки и диалекта."""
    encoding = detect_encoding(file_path)

    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
        sample = f.read(16384)
        f.seek(0)

        delimiter = ';'
        if sample:
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample, delimiters=';,\t|')
                delimiter = dialect.delimiter
            except Exception:
                counts = {';': sample.count(';'), ',': sample.count(','), '\t': sample.count('\t'), '|': sample.count('|')}
                delimiter = max(counts, key=counts.get) if any(counts.values()) else ';'

        reader = csv.reader(f, delimiter=delimiter)
        try:
            raw_headers = next(reader, None)
        except StopIteration:
            return

        if not raw_headers:
            return

        mapping = detect_column_mapping(raw_headers)
        if 'account_number' not in mapping:
            mapping['account_number'] = 0

        for row in reader:
            if not row or not any(row):
                continue

            def extract(field: str, r=row) -> str:
                idx = mapping.get(field)
                if idx is not None and idx < len(r):
                    val = r[idx]
                    return str(val).strip() if val is not None else ''
                return ''

            acc = extract('account_number')
            if re.match(r'^\d+\.0$', acc):
                acc = acc[:-2]

            if not acc:
                continue

            addr = extract('address')
            street = extract('street')
            building = extract('building')
            corpus = extract('corpus')
            flat = extract('flat')

            if not addr and (street or building or flat):
                parts = []
                if street:
                    parts.append(street)
                if building:
                    parts.append(f"д. {building}")
                if corpus:
                    parts.append(f"корп. {corpus}")
                if flat:
                    parts.append(f"кв. {flat}")
                addr = ", ".join(parts)

            yield {
                'account_number': acc,
                'customer_name': extract('customer_name'),
                'address': addr,
                'street': street,
                'building': building,
                'corpus': corpus,
                'district': extract('district'),
                'organization': extract('organization')
            }


def read_excel_records(file_path: str) -> Generator[Dict[str, str], None, None]:
    """Считывает строки из файлов Excel (.xlsx или .xls)."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.xlsx':
        try:
            import openpyxl
            book = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet = book[book.sheetnames[0]]
            iter_rows = sheet.iter_rows(values_only=True)
            raw_headers = next(iter_rows, None)
            if not raw_headers:
                book.close()
                return

            mapping = detect_column_mapping([str(h or '') for h in raw_headers])
            if 'account_number' not in mapping:
                mapping['account_number'] = 0

            for row in iter_rows:
                if not row or not any(row):
                    continue

                def get_val(field: str, r=row) -> str:
                    idx = mapping.get(field)
                    if idx is not None and idx < len(r):
                        v = r[idx]
                        if v is None:
                            return ''
                        if isinstance(v, float) and v.is_integer():
                            return str(int(v))
                        return str(v).strip()
                    return ''

                acc = get_val('account_number')
                if not acc:
                    continue

                yield {
                    'account_number': acc,
                    'customer_name': get_val('customer_name'),
                    'address': get_val('address'),
                    'street': get_val('street'),
                    'building': get_val('building'),
                    'corpus': get_val('corpus'),
                    'district': get_val('district'),
                    'organization': get_val('organization')
                }
            book.close()
        except ImportError as err:
            raise RuntimeError("Для чтения .xlsx файлов установите: pip install openpyxl") from err

    elif ext == '.xls':
        try:
            import xlrd
            book = xlrd.open_workbook(file_path)
            sheet = book.sheet_by_index(0)
            if sheet.nrows < 1:
                return

            raw_headers = [str(sheet.cell_value(0, c)) for c in range(sheet.ncols)]
            mapping = detect_column_mapping(raw_headers)
            if 'account_number' not in mapping:
                mapping['account_number'] = 0

            for r_idx in range(1, sheet.nrows):
                def get_val(field: str, r=r_idx) -> str:
                    idx = mapping.get(field)
                    if idx is not None and idx < sheet.ncols:
                        v = sheet.cell_value(r, idx)
                        if isinstance(v, float) and v.is_integer():
                            return str(int(v))
                        return str(v).strip()
                    return ''

                acc = get_val('account_number')
                if not acc:
                    continue

                yield {
                    'account_number': acc,
                    'customer_name': get_val('customer_name'),
                    'address': get_val('address'),
                    'street': get_val('street'),
                    'building': get_val('building'),
                    'corpus': get_val('corpus'),
                    'district': get_val('district'),
                    'organization': get_val('organization')
                }
        except ImportError as err:
            raise RuntimeError("Для чтения .xls файлов установите: pip install xlrd") from err


def read_json_records(file_path: str) -> Generator[Dict[str, str], None, None]:
    """Считывает записи из JSON или JSON-Lines (.jsonl)."""
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        first_char = f.read(1).strip()
        f.seek(0)

        if first_char == '[':
            items = json.load(f)
            for item in items:
                if isinstance(item, dict):
                    acc = str(item.get('account_number') or item.get('account') or item.get('лс') or '').strip()
                    if acc:
                        yield {
                            'account_number': acc,
                            'customer_name': str(item.get('customer_name') or item.get('fio') or item.get('фио') or '').strip(),
                            'address': str(item.get('address') or item.get('адрес') or '').strip(),
                            'street': str(item.get('street') or item.get('улица') or '').strip(),
                            'building': str(item.get('building') or item.get('дом') or '').strip(),
                            'corpus': str(item.get('corpus') or item.get('корпус') or '').strip(),
                            'district': str(item.get('district') or item.get('район') or '').strip(),
                            'organization': str(item.get('organization') or item.get('организация') or '').strip()
                        }
        else:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    acc = str(item.get('account_number') or item.get('account') or item.get('лс') or '').strip()
                    if acc:
                        yield {
                            'account_number': acc,
                            'customer_name': str(item.get('customer_name') or item.get('fio') or item.get('фио') or '').strip(),
                            'address': str(item.get('address') or item.get('адрес') or '').strip(),
                            'street': str(item.get('street') or item.get('улица') or '').strip(),
                            'building': str(item.get('building') or item.get('дом') or '').strip(),
                            'corpus': str(item.get('corpus') or item.get('корпус') or '').strip(),
                            'district': str(item.get('district') or item.get('район') or '').strip(),
                            'organization': str(item.get('organization') or item.get('организация') or '').strip()
                        }
                except json.JSONDecodeError:
                    continue


def read_sqlite_records(file_path: str) -> Generator[Dict[str, str], None, None]:
    """Считывает лицевые счета напрямую из другого файла базы SQLite."""
    con = sqlite3.connect(file_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
        if not cur.fetchone():
            raise ValueError(f"Таблица 'accounts' не найдена в SQLite файле {file_path}")

        rows = cur.execute("SELECT * FROM accounts").fetchall()
        for r in rows:
            keys = r.keys()
            acc = str(r['account_number'] if 'account_number' in keys else r['id']).strip()
            if not acc:
                continue
            yield {
                'account_number': acc,
                'customer_name': str(r['customer_name'] or '') if 'customer_name' in keys else '',
                'address': str(r['address'] or '') if 'address' in keys else '',
                'street': str(r['street'] or '') if 'street' in keys else '',
                'building': str(r['building'] or '') if 'building' in keys else '',
                'corpus': str(r['corpus'] or '') if 'corpus' in keys else '',
                'district': str(r['district'] or '') if 'district' in keys else '',
                'organization': str(r['organization'] or '') if 'organization' in keys else ''
            }
    finally:
        con.close()


def load_records_from_source(file_path: str) -> Generator[Dict[str, str], None, None]:
    """Маршрутизатор считывания записей в зависимости от расширения файла."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ('.csv', '.tsv', '.txt'):
        return read_csv_records(file_path)
    elif ext in ('.xlsx', '.xls'):
        return read_excel_records(file_path)
    elif ext in ('.json', '.jsonl'):
        return read_json_records(file_path)
    elif ext in ('.sqlite', '.sqlite3', '.db'):
        return read_sqlite_records(file_path)
    else:
        return read_csv_records(file_path)
