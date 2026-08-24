import sqlite3
import threading
import time
import random
from contextlib import contextmanager
import config
from logger import logger

# Глобальный мьютекс для строгой сериализации параллельных операций записи в SQLite
_DB_WRITE_LOCK = threading.Lock()

def is_postgres_configured() -> bool:
    """Проверяет, настроена ли работа через PostgreSQL."""
    db_url = getattr(config, 'DATABASE_URL', '') or ''
    return db_url.startswith(('postgresql://', 'postgres://'))

def get_db():
    """
    Создаёт и возвращает соединение с базой данных:
    - PostgreSQL: соединение из пула ThreadedConnectionPool с адаптером строк и плейсхолдеров
    - SQLite: оптимизированное соединение (WAL, busy_timeout=60s, mmap_size=256MB, кэш 64MB)
    """
    if is_postgres_configured():
        from database.postgres_backend import get_postgres_db, init_postgres_pool, _PG_POOL
        if _PG_POOL is None:
            init_postgres_pool(config.DATABASE_URL)
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

