import os
import tempfile
import sqlite3
try:
    import pytest
except ImportError:
    pytest = None
import config

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    """Изолирует тестовую БД и директорию квитанций для каждого теста."""
    db_file = str(tmp_path / "test_data.sqlite3")
    receipts_dir = str(tmp_path / "test_receipts")
    os.makedirs(receipts_dir, exist_ok=True)

    from services.security.auth_service import hash_password
    monkeypatch.setattr(config, 'DB', db_file)
    monkeypatch.setattr(config, 'RECEIPTS_DIR', receipts_dir)
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'test_secure_grpc_key_for_testing')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('admin'))
    monkeypatch.setattr('services.pdf.pdf_processor.RECEIPTS_DIR', receipts_dir)
    monkeypatch.setattr('services.receipts.receipt_service.RECEIPTS_DIR', receipts_dir)

    # Инициализация схемы
    con = sqlite3.connect(db_file)
    con.executescript('''
        CREATE TABLE accounts(
            id INTEGER PRIMARY KEY,
            account_number TEXT NOT NULL UNIQUE,
            customer_name TEXT,
            address TEXT,
            street TEXT,
            building TEXT,
            corpus TEXT,
            district TEXT,
            organization TEXT
        );
        CREATE INDEX idx_accounts_account ON accounts(account_number);
        CREATE INDEX idx_accounts_address ON accounts(address);

        CREATE TABLE receipts(
            id INTEGER PRIMARY KEY,
            account_number TEXT NOT NULL,
            period TEXT NOT NULL,
            pdf_file TEXT NOT NULL,
            content_hash TEXT,
            access_token TEXT,
            address TEXT,
            UNIQUE(account_number, period)
        );
        CREATE INDEX idx_receipts_account_period ON receipts(account_number, period);
        CREATE INDEX idx_receipts_hash ON receipts(content_hash);
        CREATE INDEX idx_receipts_address ON receipts(address);
        CREATE UNIQUE INDEX idx_receipts_token ON receipts(access_token);
    ''')
    con.commit()
    con.close()

    yield {
        'db_file': db_file,
        'receipts_dir': receipts_dir,
    }
