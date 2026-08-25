import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

import config
from database.connection import get_db, write_transaction
from logger import logger


class BaseSessionStore(ABC):
    """Абстрактный интерфейс хранилища сессий (Session Store)."""

    @abstractmethod
    def save_session(self, token: str, expires_at: float, created_at: float) -> None:
        """Сохраняет новую или обновляет существующую сессию."""
        pass

    @abstractmethod
    def get_session_expiry(self, token: str) -> Optional[float]:
        """Возвращает timestamp expires_at если сессия валидна, иначе None."""
        pass

    @abstractmethod
    def delete_session(self, token: str) -> None:
        """Удаляет сессию (logout/инвалидация)."""
        pass

    @abstractmethod
    def cleanup_expired(self) -> None:
        """Очищает просроченные сессии."""
        pass

    @abstractmethod
    def clear_l1_cache(self) -> None:
        """Сбрасывает локальный L1 кэш (для тестирования или принудительного обновления)."""
        pass


class DatabaseSessionStore(BaseSessionStore):
    """
    Двухуровневое хранилище сессий:
    - L1 Fast In-Memory Cache: быстрый словарь в RAM с коротким TTL (по умолчанию 10 сек)
      для мгновенной проверки (O(1), без I/O нагрузки на базу данных).
    - L2 Persistent Database: авторитетный источник истины (SQLite / PostgreSQL)
      для сохранения сессий при перезапусках и синхронизации между репликами.
    """

    def __init__(self, l1_ttl_seconds: float = 10.0):
        self._lock = threading.Lock()
        # token -> (expires_at, l1_valid_until)
        self._l1_cache: Dict[str, Tuple[float, float]] = {}
        self._l1_ttl = float(l1_ttl_seconds)
        self._last_cleanup = time.time()
        self._warmup_l1_from_db()

    def _warmup_l1_from_db(self):
        """Прогревает L1 кэш активными сессиями из БД при старте инстанса."""
        now = time.time()
        try:
            con = get_db()
            try:
                rows = con.execute('SELECT token, expires_at FROM app_sessions WHERE expires_at > ?', (now,)).fetchall()
                with self._lock:
                    for r in rows:
                        token, exp = r[0], float(r[1])
                        self._l1_cache[token] = (exp, now + self._l1_ttl)
            finally:
                con.close()
        except Exception as e:
            logger.warn(f"[SessionStore] Предупреждение при прогреве L1 кэша: {e}")

    def save_session(self, token: str, expires_at: float, created_at: float) -> None:
        now = time.time()
        with self._lock:
            self._l1_cache[token] = (expires_at, now + self._l1_ttl)

        try:
            with write_transaction() as con:
                con.execute(
                    'INSERT OR REPLACE INTO app_sessions(token, expires_at, created_at) VALUES (?, ?, ?)',
                    (token, expires_at, created_at)
                )
        except Exception as e:
            logger.warn(f"[SessionStore] Ошибка сохранения сессии в БД: {e}")

    def get_session_expiry(self, token: str) -> Optional[float]:
        if not token or not isinstance(token, str):
            return None

        now = time.time()

        # 1. Проверка L1 RAM кэша (Fast Path, 0 запросов к БД)
        with self._lock:
            cached = self._l1_cache.get(token)
            if cached is not None:
                expires_at, l1_valid_until = cached
                if now <= expires_at and now <= l1_valid_until:
                    return expires_at
                elif now > expires_at:
                    self._l1_cache.pop(token, None)
                    return None

        # 2. L1 MISS или истёк L1 TTL -> запрос к авторитетной L2 БД
        try:
            con = get_db()
            try:
                row = con.execute('SELECT expires_at FROM app_sessions WHERE token = ?', (token,)).fetchone()
                if row:
                    db_expiry = float(row[0])
                    if now <= db_expiry:
                        # Записываем в L1 с новым окном TTL
                        with self._lock:
                            self._l1_cache[token] = (db_expiry, now + self._l1_ttl)
                        return db_expiry
                    else:
                        self.delete_session(token)
                        return None
                else:
                    # Токена нет в БД (удалён/инвалидирован) -> удаляем из L1
                    with self._lock:
                        self._l1_cache.pop(token, None)
                    return None
            finally:
                con.close()
        except Exception as e:
            logger.warn(f"[SessionStore] Сбой чтения сессии из БД: {e}")
            # Fallback на локальный кэш, если БД временно недоступна
            with self._lock:
                cached = self._l1_cache.get(token)
                if cached is not None and now <= cached[0]:
                    return cached[0]
            return None

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._l1_cache.pop(token, None)

        try:
            with write_transaction() as con:
                con.execute('DELETE FROM app_sessions WHERE token = ?', (token,))
        except Exception as e:
            logger.warn(f"[SessionStore] Ошибка удаления сессии из БД: {e}")

    def cleanup_expired(self) -> None:
        now = time.time()
        with self._lock:
            if now - self._last_cleanup < 300:  # Раз в 5 минут
                return
            self._last_cleanup = now
            expired_tokens = [t for t, (exp, _) in self._l1_cache.items() if exp < now]
            for t in expired_tokens:
                self._l1_cache.pop(t, None)

        try:
            with write_transaction() as con:
                con.execute('DELETE FROM app_sessions WHERE expires_at < ?', (now,))
        except Exception:
            pass

    def clear_l1_cache(self) -> None:
        with self._lock:
            self._l1_cache.clear()
