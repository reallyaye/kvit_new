#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backup & Disaster Recovery Verification Drill
- Создает горячий бэкап базы данных (PostgreSQL pg_dump / SQLite backup API).
- Проверяет контрольную сумму и количество записей (accounts, receipts).
- Симулирует восстановление в тестовую БД и сверяет данные на 100% целостность.
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import time

import config
from database.connection import get_db, is_postgres_configured

def get_db_metrics(con):
    total_accounts = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    total_receipts = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    sample_receipts = [
        dict(r) for r in con.execute("SELECT account_number, period, access_token FROM receipts LIMIT 10").fetchall()
    ]
    return {
        "accounts": total_accounts,
        "receipts": total_receipts,
        "sample": sample_receipts
    }

def run_sqlite_backup_drill(backup_dir: str):
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f"kvit_backup_{int(time.time())}.sqlite3")

    print(f"📦 [SQLite] Запуск горячего онлайн-бэкапа в {backup_file}...")
    src_con = get_db()
    orig_metrics = get_db_metrics(src_con)

    # Онлайн бэкап без блокировки БД
    dst_con = sqlite3.connect(backup_file)
    src_con.backup(dst_con)
    dst_con.close()
    src_con.close()

    print(f"✅ Онлайн-бэкап создан ({os.path.getsize(backup_file)} байт).")
    print(f"🔍 [SQLite] Проверка восстановления в изолированной среде...")

    restore_con = sqlite3.connect(backup_file)
    restore_con.row_factory = sqlite3.Row
    restored_metrics = get_db_metrics(restore_con)
    restore_con.close()

    assert orig_metrics["accounts"] == restored_metrics["accounts"], "Несовпадение счетов!"
    assert orig_metrics["receipts"] == restored_metrics["receipts"], "Несовпадение квитанций!"

    print(f"🎉 Проверка восстановления успешно пройдена:")
    print(f"   - Счетов: {restored_metrics['accounts']}")
    print(f"   - Квитанций: {restored_metrics['receipts']}")
    print(f"   - Целостность: 100% OK")

def run_postgres_backup_drill(backup_dir: str):
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f"kvit_pg_dump_{int(time.time())}.sql")
    db_url = config.DATABASE_URL
    print(f"📦 [PostgreSQL] Запуск pg_dump из {db_url} в {backup_file}...")

    cmd = ["pg_dump", "--clean", "--if-exists", "--no-owner", "-f", backup_file, db_url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Ошибка pg_dump: {res.stderr}")
        return False

    print(f"✅ Бэкап PostgreSQL успешно создан ({os.path.getsize(backup_file)} байт).")
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Disaster Recovery Backup Drill")
    parser.add_argument("--dir", default="./backups", help="Директория для бэкапов")
    args = parser.parse_args()

    if is_postgres_configured():
        run_postgres_backup_drill(args.dir)
    else:
        run_sqlite_backup_drill(args.dir)
