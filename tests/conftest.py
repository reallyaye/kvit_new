import os
import socket
import socketserver
import threading
import time

os.environ['APP_ENV'] = 'testing'
os.environ['DB_TYPE'] = 'sqlite'
os.environ['DATABASE_URL'] = ''

try:
    import pytest
except ImportError:
    pytest = None
import config

config.APP_ENV = 'testing'
config.IS_PRODUCTION = False
config.DB_TYPE = 'sqlite'
config.DATABASE_URL = ''


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    """Изолирует тестовую БД и директорию квитанций для каждого теста."""
    db_file = str(tmp_path / "test_data.sqlite3")
    receipts_dir = str(tmp_path / "test_receipts")
    os.makedirs(receipts_dir, exist_ok=True)

    from services.security.auth_service import hash_password
    monkeypatch.setattr(config, 'APP_ENV', 'testing')
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(config, 'DATABASE_URL', '')
    monkeypatch.setattr(config, 'DB', db_file)
    monkeypatch.setattr(config, 'RECEIPTS_DIR', receipts_dir)
    monkeypatch.setattr(config, 'SECRET_KEY', 'test_secure_secret_key_for_testing')
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'test_secure_grpc_key_for_testing')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('admin'))

    # Инициализация полной схемы БД через миграции
    from database import migrate_db
    migrate_db()

    yield {
        'db_file': db_file,
        'receipts_dir': receipts_dir,
    }


class E2EThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def e2e_server():
    from server import AppRequestHandler

    port = _get_free_port()
    server = E2EThreadedServer(("127.0.0.1", port), AppRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.2)

    yield {
        "base_url": base_url,
        "admin_password": "admin",
    }

    server.shutdown()
    server.server_close()
