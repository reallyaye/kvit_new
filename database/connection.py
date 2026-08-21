import sqlite3
import threading
import time
import random
from contextlib import contextmanager
import config
from logger import logger

# Глобальный мьютекс для строгой сериализации параллельных операций записи в SQLite
_DB_WRITE_LOCK = threading.Lock()

def get_db():
    """Создаёт и возвращает оптимизированное соединение с SQLite (WAL, busy timeout, mmap, кэш страниц)."""
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
    - Сериализует запись через threading.Lock, исключая взаимные блокировки между потоками приложения;
    - Использует BEGIN IMMEDIATE для мгновенной фиксации монопольного намерения записи;
    - Реализует экспоненциальный jitter-backoff при межпроцессных коллизиях блокировок;
    - Гарантирует авто-rollback при ошибках и корректное закрытие сокета БД.
    """
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

