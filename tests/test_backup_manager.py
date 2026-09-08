# -*- coding: utf-8 -*-
"""
Тесты менеджера резервного копирования и верификации восстановления:
1. Создание полного бэкапа (БД, квитанции, CMS-файлы, манифест).
2. Проверка целостности архивов и контрольных сумм SHA-256.
3. Проверка восстановления и сопоставления метрик.
4. Ротация устаревших копий.
"""

import json
import os
import time

from database.connection import get_db
from scripts.backup_manager import BackupManager, calc_sha256


def test_backup_manager_full_cycle(tmp_path):
    # 1. Подготовка тестовых данных в базе
    con = get_db()
    con.execute("INSERT OR REPLACE INTO accounts(account_number, customer_name, address) VALUES ('999001', 'Тест Бэкап', 'ул. Ленина 10')")
    con.execute("INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, access_token, status) VALUES ('999001', '02.2026', 'sample_receipt_999.pdf', 'token999000000000000000000000000', 'READY')")
    con.commit()
    con.close()

    # Создаем фиктивный receipts каталог и тестовый PDF
    test_receipts_dir = tmp_path / "data" / "receipts"
    test_receipts_dir.mkdir(parents=True)
    sample_pdf = test_receipts_dir / "sample_receipt_999.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4 test backup receipt content")

    # Создаем фиктивный uploads каталог
    test_uploads_dir = tmp_path / "data" / "uploads"
    test_uploads_dir.mkdir(parents=True)
    sample_upload = test_uploads_dir / "test_doc.pdf"
    sample_upload.write_bytes(b"test upload content")

    backup_dir = tmp_path / "backups"

    # 2. Запуск создания резервной копии с верификацией
    mgr = BackupManager(
        base_dir=str(tmp_path),
        backup_root=str(backup_dir),
        retention_days=7
    )

    manifest = mgr.run_backup(verify=True)

    # 3. Проверка манифеста и сгенерированных файлов
    assert manifest is not None
    assert manifest['bundle_name'].startswith('kvit_backup_')
    bundle_path = backup_dir / manifest['bundle_name']
    assert bundle_path.exists()

    manifest_file = bundle_path / "manifest.json"
    assert manifest_file.exists()
    with open(manifest_file, 'r', encoding='utf-8') as f:
        loaded_manifest = json.load(f)

    assert loaded_manifest['verification']['success'] is True
    assert loaded_manifest['verification']['database_verified'] is True

    # Проверяем файлы
    files_meta = loaded_manifest['files']
    assert 'database' in files_meta
    assert 'receipts' in files_meta
    assert 'cms' in files_meta

    for _comp, meta in files_meta.items():
        comp_file = bundle_path / meta['filename']
        assert comp_file.exists()
        assert comp_file.stat().st_size == meta['size_bytes']
        assert calc_sha256(str(comp_file)) == meta['sha256']

    # 4. Проверка ротации старых копий
    old_bundle = backup_dir / "kvit_backup_20200101_000000"
    old_bundle.mkdir()
    old_file = old_bundle / "dummy.txt"
    old_file.write_text("old")
    # Меняем mtime на 30 дней назад
    thirty_days_ago = time.time() - (30 * 86400)
    os.utime(str(old_bundle), (thirty_days_ago, thirty_days_ago))

    mgr.rotate_old_backups()
    assert not old_bundle.exists()
    assert bundle_path.exists()
