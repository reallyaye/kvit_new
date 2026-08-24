import os

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

    # Инициализация полной схемы БД через миграции
    from database import migrate_db
    migrate_db()

    yield {
        'db_file': db_file,
        'receipts_dir': receipts_dir,
    }
