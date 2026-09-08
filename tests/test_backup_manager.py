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
import shutil
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


def test_backup_verification_fails_on_corrupted_or_missing_sample(tmp_path):
    """Проверка, что бэкап бракуется (success=False), если хотя бы один сэмпл отсутствует или поврежден."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    bundle_dir = backup_dir / "kvit_backup_test_fail"
    bundle_dir.mkdir(parents=True)

    # Создаем фиктивный tar.gz с поврежденным файлом квитанции (не PDF)
    import gzip
    import tarfile

    fake_tar = bundle_dir / "receipts_test.tar.gz"
    with tarfile.open(fake_tar, 'w:gz') as tar:
        corrupt_txt = tmp_path / "corrupt.pdf"
        corrupt_txt.write_bytes(b"NOT_A_VALID_PDF_HEADER")
        tar.add(str(corrupt_txt), arcname="corrupt.pdf")

    # Создаем фиктивную валидную SQLite БД
    import sqlite3
    db_raw = tmp_path / "valid_test.db"
    con = sqlite3.connect(db_raw)
    con.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY);")
    con.execute("CREATE TABLE receipts (id INTEGER PRIMARY KEY);")
    con.execute("INSERT INTO receipts (id) VALUES (1);")
    con.commit()
    con.close()

    fake_db = bundle_dir / "sqlite_test.db.gz"
    with open(db_raw, 'rb') as f_in, gzip.open(fake_db, 'wb') as f_gz:
        shutil.copyfileobj(f_in, f_gz)

    cms_tar = bundle_dir / "cms_test.tar.gz"
    with tarfile.open(cms_tar, 'w:gz') as tar:
        pass

    manifest = {
        'database_type': 'sqlite',
        'files': {
            'database': {'filename': fake_db.name, 'sha256': calc_sha256(str(fake_db))},
            'receipts': {'filename': fake_tar.name, 'sha256': calc_sha256(str(fake_tar))},
            'cms': {'filename': cms_tar.name, 'sha256': calc_sha256(str(cms_tar))}
        },
        'initial_metrics': {
            'accounts_count': 0,
            'receipts_count': 1,
            'sample_receipt_files': ['corrupt.pdf']
        }
    }

    mgr = BackupManager(base_dir=str(tmp_path), backup_root=str(backup_dir))
    res = mgr.verify_backup_bundle(str(bundle_dir), manifest)

    # Верификация обязана провалиться, так как заголовок не %PDF-
    assert res['success'] is False
    assert res['receipts_sample_verified'] is False
    assert "поврежден" in res['error']


def test_backup_remote_sync_failure_raises_error(tmp_path):
    """Проверка, что ошибка синхронизации прерывает создание бэкапа исключением RuntimeError."""
    import pytest

    mgr = BackupManager(base_dir=str(tmp_path), backup_root=str(tmp_path / "backups"))

    # Делаем родительский каталог недоступным или проверяем вызов
    with pytest.raises(RuntimeError):
        # Передаем заведомо невалидный rsync таргет
        mgr._sync_remote(str(tmp_path), "invalid_user@non_existent_host_999.local:/tmp")


def test_postgres_restore_fails_when_temp_db_cannot_be_created(tmp_path, monkeypatch):
    """Проверка, что _verify_postgres_restore возвращает False, если создание временной базы провалилось."""
    import gzip
    import subprocess

    sql_gz = tmp_path / "pg_test.sql.gz"
    with gzip.open(sql_gz, 'wt', encoding='utf-8') as f:
        f.write("CREATE TABLE accounts (id int);\nCREATE TABLE receipts (id int);\n")

    mgr = BackupManager(base_dir=str(tmp_path), backup_root=str(tmp_path / "backups"))

    def fake_run(cmd, *args, **kwargs):
        if 'docker' in cmd and 'ps' in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout='kvit-postgres\n', stderr='')
        if 'CREATE DATABASE' in ' '.join(cmd):
            return subprocess.CompletedProcess(cmd, 1, stdout='', stderr='permission denied')
        return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)

    ok = mgr._verify_postgres_restore(str(sql_gz), {'accounts_count': 0, 'receipts_count': 0})
    assert ok is False


def test_postgres_restore_fails_when_psql_restore_fails(tmp_path, monkeypatch):
    """Проверка, что _verify_postgres_restore возвращает False, если psql упал с ошибкой (код возврата != 0)."""
    import gzip
    import subprocess

    sql_gz = tmp_path / "pg_test.sql.gz"
    with gzip.open(sql_gz, 'wt', encoding='utf-8') as f:
        f.write("CREATE TABLE accounts (id int);\nCREATE TABLE receipts (id int);\n")

    mgr = BackupManager(base_dir=str(tmp_path), backup_root=str(tmp_path / "backups"))

    def fake_run(cmd, *args, **kwargs):
        if 'docker' in cmd and 'ps' in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout='kvit-postgres\n', stderr='')
        if 'CREATE DATABASE' in ' '.join(cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        if 'DROP DATABASE' in ' '.join(cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 2

        def communicate(self, *args, **kwargs):
            return b'', b'syntax error in SQL'

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)

    ok = mgr._verify_postgres_restore(str(sql_gz), {'accounts_count': 0, 'receipts_count': 0})
    assert ok is False

