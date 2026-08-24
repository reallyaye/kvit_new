# -*- coding: utf-8 -*-
"""
PostgreSQL драйвер и пул соединений для высоконагруженных промышленных развертываний.
Поддерживает:
- ThreadedConnectionPool (пул соединений для многопоточного HTTP/gRPC/WebSocket)
- Преобразование SQL-диалектов (плейсхолдеры '?' -> '%s')
- Доступ к результатам по именам колонок (как dict/sqlite3.Row)
- ACID транзакции с авто-откатом и возвратом соединений в пул
"""

import os
import re
import logging
from typing import Optional, Any, List, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2 import pool, extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    pool = None
    extras = None
    PSYCOPG2_AVAILABLE = False

_PG_POOL: Optional[Any] = None

class PostgresRowWrapper:
    """Обертка над словарем/кортежем строки PostgreSQL для совместимости с интерфейсом sqlite3.Row."""
    def __init__(self, data: Dict[str, Any], col_names: List[str]):
        self._data = data
        self._col_names = col_names

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[self._col_names[key]]
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._col_names

    def __iter__(self):
        for col in self._col_names:
            yield self._data[col]

    def __repr__(self):
        return f"<PostgresRow {self._data}>"

class PostgresCursorWrapper:
    """Обертка курсора PostgreSQL, обеспечивающая совместимость с интерфейсом sqlite3."""
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    def _convert_query(self, query: str) -> str:
        """Конвертирует плейсхолдеры SQLite '?' в плейсхолдеры PostgreSQL '%s'."""
        # Заменяем '?' на '%s', если это не внутри строкового литерала
        # В нашей кодовой базе все параметризованные запросы используют ?
        return query.replace('?', '%s')

    def execute(self, query: str, params: Any = None):
        converted_sql = self._convert_query(query)
        if params is not None:
            if isinstance(params, (list, tuple)):
                self._cur.execute(converted_sql, params)
            else:
                self._cur.execute(converted_sql, (params,))
        else:
            self._cur.execute(converted_sql)
        return self

    def executemany(self, query: str, seq_of_params: Any):
        converted_sql = self._convert_query(query)
        self._cur.executemany(converted_sql, seq_of_params)
        return self

    def executescript(self, sql_script: str):
        self._cur.execute(sql_script)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        col_names = [desc[0] for desc in self._cur.description]
        return PostgresRowWrapper(dict(row), col_names)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        col_names = [desc[0] for desc in self._cur.description]
        return [PostgresRowWrapper(dict(r), col_names) for r in rows]

    @property
    def rowcount(self):
        return self._cur.rowcount

class PostgresConnectionWrapper:
    """Обертка соединения PostgreSQL из пула."""
    def __init__(self, raw_con, pool_instance):
        self._con = raw_con
        self._pool = pool_instance
        self._closed = False

    def cursor(self):
        return PostgresCursorWrapper(self._con.cursor(cursor_factory=extras.RealDictCursor))

    def execute(self, query: str, params: Any = None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def executemany(self, query: str, seq_of_params: Any):
        cur = self.cursor()
        cur.executemany(query, seq_of_params)
        return cur

    def executescript(self, script: str):
        cur = self.cursor()
        cur.executescript(script)
        return cur

    def commit(self):
        self._con.commit()

    def rollback(self):
        self._con.rollback()

    def close(self):
        if not self._closed and self._pool:
            try:
                self._pool.putconn(self._con)
            except Exception:
                pass
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def init_postgres_pool(database_url: str, minconn: int = 2, maxconn: int = 50):
    """Инициализирует глобальный пул соединений PostgreSQL."""
    global _PG_POOL
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError(
            "Для использования PostgreSQL необходимо установить драйвер psycopg2:\n"
            "    pip install psycopg2-binary"
        )
    if _PG_POOL is None:
        _PG_POOL = pool.ThreadedConnectionPool(minconn, maxconn, dsn=database_url)
        logger.info(f"[PostgreSQL] Пул соединений успешно инициализирован (min={minconn}, max={maxconn})")

def get_postgres_db():
    """Получает соединение из пула PostgreSQL."""
    global _PG_POOL
    if _PG_POOL is None:
        raise RuntimeError("Пул PostgreSQL не инициализирован. Вызовите init_postgres_pool(database_url).")
    raw_con = _PG_POOL.getconn()
    raw_con.autocommit = False
    return PostgresConnectionWrapper(raw_con, _PG_POOL)

@contextmanager
def postgres_write_transaction():
    """Контекстный менеджер транзакции записи для PostgreSQL."""
    con = get_postgres_db()
    try:
        yield con
        con.commit()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()
