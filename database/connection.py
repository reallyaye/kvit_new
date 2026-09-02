import random
import sqlite3
import threading
import time
from contextlib import contextmanager

import config
from logger import logger

# Глобальный мьютекс для строгой сериализации параллельных операций записи в SQLite
_DB_WRITE_LOCK = threading.Lock()
# Глобальный мьютекс для потокобезопасной инициализации пула PostgreSQL
_PG_INIT_LOCK = threading.Lock()

def is_postgres_configured() -> bool:
    """Проверяет, настроена ли работа через PostgreSQL."""
    db_url = getattr(config, 'DATABASE_URL', '') or ''
    db_type = getattr(config, 'DB_TYPE', '').lower()
    return db_url.startswith(('postgresql://', 'postgres://')) or db_type == 'postgres'

def _ensure_postgres_initialized():
    """Потокобезопасно гарантирует инициализацию пула PostgreSQL."""
    from database import postgres_backend
    if postgres_backend._PG_POOL is None:
        with _PG_INIT_LOCK:
            if postgres_backend._PG_POOL is None:
                if not getattr(config, 'DATABASE_URL', None):
                    raise RuntimeError(
                        "[DB] ❌ КРИТИЧЕСКАЯ ОШИБКА: Задана конфигурация PostgreSQL, но переменная DATABASE_URL пуста! "
                        "Укажите DATABASE_URL=postgresql://user:password@host:5432/dbname"
                    )
                postgres_backend.init_postgres_pool(config.DATABASE_URL)

def get_db():
    """
    Создаёт и возвращает соединение с базой данных:
    - Production: строго PostgreSQL (при отсутствии DATABASE_URL выдает Fail-Fast ошибку).
    - Development / Small installations / Tests: SQLite (WAL, mmap_size=256MB, кэш 64MB).
    """
    if is_postgres_configured():
        _ensure_postgres_initialized()
        from database.postgres_backend import get_postgres_db
        return get_postgres_db()

    con = sqlite3.connect(config.DB, timeout=60.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode = WAL;')
    con.execute('PRAGMA busy_timeout = 60000;')
    con.execute('PRAGMA synchronous = NORMAL;')
    con.execute('PRAGMA cache_size = -64000;')  # 64 MB памяти на кэш страниц
    con.execute('PRAGMA temp_store = MEMORY;')  # Временные таблицы и индексы в RAM
    con.execute('PRAGMA mmap_size = 268435456;')  # 256 MB Memory-mapped I/O для ускорения чтения
    return con


@contextmanager
def write_transaction(max_retries: int = 10, base_delay: float = 0.05):
    """
    Потокобезопасный контекстный менеджер для выполнения транзакций записи:
    - PostgreSQL: полноценные параллельные транзакции MVCC с row-level блокировками без bottleneck
    - SQLite: строгая сериализация через мьютекс и BEGIN IMMEDIATE с jitter-backoff
    """
    if is_postgres_configured():
        _ensure_postgres_initialized()
        from database.postgres_backend import postgres_write_transaction
        with postgres_write_transaction() as con:
            yield con
        return

    attempt = 0
    while True:
        try:
            with _DB_WRITE_LOCK:
                con = get_db()
                try:
                    con.execute("BEGIN IMMEDIATE;")
                    yield con
                    con.commit()
                    return
                except Exception:
                    try:
                        con.rollback()
                    except Exception:
                        pass
                    raise
                finally:
                    con.close()
        except sqlite3.OperationalError as e:
            err_str = str(e).lower()
            if 'locked' in err_str or 'busy' in err_str:
                attempt += 1
                if attempt >= max_retries:
                    logger.error(f"[DB] Превышен лимит попыток записи ({max_retries}): {e}")
                    raise
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.01, 0.05)
                logger.warn(f"[DB] База данных заблокирована другим процессом. Повтор записи #{attempt} через {delay:.3f}с...")
                time.sleep(delay)
            else:
                raise

