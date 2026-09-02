import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Optional, Tuple, Union

import config
from database.connection import get_db, write_transaction
from logger import logger


class DBFailurePolicy(str, Enum):
    """
    Политика поведения SessionStore при сбоях базы данных (L2 Storage):
    - FAIL_CLOSED: (По умолчанию) Безопасный отказ. Если L2 недоступна и L1 TTL истёк, сессия
      не валидируется, а при сбое сохранения токен не создаётся в памяти.
    - FAIL_OPEN_L1: Максимальная доступность. При сбое L2 БД используется локальный кэш L1 RAM,
      если абсолютный срок жизни сессии (expires_at) ещё не истёк.
    - STRICT: Строгий режим. При любой ошибке БД выбрасывается исключение.
    """
    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN_L1 = "fail_open_l1"
    STRICT = "strict"

    @classmethod
    def from_value(cls, val: Union['DBFailurePolicy', str, None]) -> 'DBFailurePolicy':
        if isinstance(val, cls):
            return val
        if isinstance(val, str):
            clean = val.strip().lower()
            for member in cls:
                if member.value == clean:
                    return member
        return cls.FAIL_CLOSED


class BaseSessionStore(ABC):
    """Абстрактный интерфейс хранилища сессий (Session Store)."""

    @abstractmethod
    def save_session(self, token: str, expires_at: float, created_at: float, username: str = 'admin', role: str = 'admin') -> None:
        """Сохраняет новую или обновляет существующую сессию."""
        pass

    @abstractmethod
    def get_session_expiry(self, token: str) -> Optional[float]:
        """Возвращает timestamp expires_at если сессия валидна, иначе None."""
        pass

    @abstractmethod
    def get_session_info(self, token: str) -> Optional[dict]:
        """Возвращает метаданные сессии {'expires_at': float, 'username': str, 'role': str} или None."""
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
    Двухуровневое хранилище сессий с явной политикой обработки сбоев БД:
    - L1 Fast In-Memory Cache: быстрый словарь в RAM с коротким TTL (по умолчанию 10 сек)
      для мгновенной проверки (O(1), без I/O нагрузки на базу данных).
    - L2 Persistent Database: авторитетный источник истины (SQLite / PostgreSQL)
      для сохранения сессий при перезапусках и синхронизации между репликами.
    """

    def __init__(
        self,
        l1_ttl_seconds: float = 10.0,
        db_failure_policy: Optional[Union[DBFailurePolicy, str]] = None,
    ):
        self._lock = threading.Lock()
        # token -> (expires_at, l1_valid_until, username, role)
        self._l1_cache: Dict[str, Tuple[float, float, str, str]] = {}
        self._l1_ttl = float(l1_ttl_seconds)
        self._last_cleanup = time.time()

        policy_val = db_failure_policy if db_failure_policy is not None else getattr(config, 'SESSION_DB_FAILURE_POLICY', 'fail_closed')
        self.failure_policy: DBFailurePolicy = DBFailurePolicy.from_value(policy_val)

    def save_session(self, token: str, expires_at: float, created_at: float, username: str = 'admin', role: str = 'admin') -> None:
        """
        Сохраняет сессию в авторитетную БД и при успехе обновляет L1 кэш.
        При ошибке БД применяется явная политика failure_policy.
        """
        try:
            with write_transaction() as con:
                con.execute(
                    'INSERT INTO app_sessions(token, expires_at, created_at, username, role) VALUES (?, ?, ?, ?, ?) '
                    'ON CONFLICT(token) DO UPDATE SET expires_at=EXCLUDED.expires_at, created_at=EXCLUDED.created_at, username=EXCLUDED.username, role=EXCLUDED.role',
                    (token, expires_at, created_at, username, role)
                )
            now = time.time()
            with self._lock:
                self._l1_cache[token] = (expires_at, now + self._l1_ttl, username, role)
        except Exception as e:
            logger.error(f"[SessionStore] Ошибка сохранения сессии в БД: {e}")
            if self.failure_policy == DBFailurePolicy.STRICT:
                raise
            elif self.failure_policy == DBFailurePolicy.FAIL_OPEN_L1:
                now = time.time()
                with self._lock:
                    self._l1_cache[token] = (expires_at, now + self._l1_ttl, username, role)
            # В режиме FAIL_CLOSED не добавляем в L1, предотвращая неперсистентные сессии

    def get_session_info(self, token: str) -> Optional[dict]:
        """Возвращает информацию о сессии: expires_at, username, role."""
        if not token or not isinstance(token, str):
            return None

        now = time.time()

        # 1. Проверка L1 RAM кэша (Fast Path, 0 запросов к БД)
        with self._lock:
            cached = self._l1_cache.get(token)
            if cached is not None:
                if len(cached) == 4:
                    expires_at, l1_valid_until, username, role = cached
                elif len(cached) == 2:
                    expires_at, l1_valid_until = cached
                    username, role = 'admin', 'admin'
                else:
                    expires_at = cached[0]
                    l1_valid_until = cached[1] if len(cached) > 1 else now + self._l1_ttl
                    username, role = 'admin', 'admin'

                if now <= expires_at and now <= l1_valid_until:
                    return {'expires_at': expires_at, 'username': username, 'role': role}
                elif now > expires_at:
                    self._l1_cache.pop(token, None)
                    return None

        # 2. L1 MISS или истёк L1 TTL -> запрос к авторитетной L2 БД
        try:
            con = get_db()
            try:
                row = con.execute('SELECT expires_at, username, role FROM app_sessions WHERE token = ?', (token,)).fetchone()
                if row:
                    db_expiry = float(row[0])
                    u_name = row[1] if row[1] else 'admin'
                    u_role = row[2] if row[2] else 'admin'
                    if now <= db_expiry:
                        with self._lock:
                            self._l1_cache[token] = (db_expiry, now + self._l1_ttl, u_name, u_role)
                        return {'expires_at': db_expiry, 'username': u_name, 'role': u_role}
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
            logger.error(f"[SessionStore] Сбой чтения сессии из БД: {e}")
            if self.failure_policy == DBFailurePolicy.STRICT:
                raise
            elif self.failure_policy == DBFailurePolicy.FAIL_OPEN_L1:
                with self._lock:
                    cached = self._l1_cache.get(token)
                    if cached is not None and now <= cached[0]:
                        u_name = cached[2] if len(cached) > 2 else 'admin'
                        u_role = cached[3] if len(cached) > 3 else 'admin'
                        return {'expires_at': cached[0], 'username': u_name, 'role': u_role}
                return None
            else:  # FAIL_CLOSED
                return None

    def get_session_expiry(self, token: str) -> Optional[float]:
        """Возвращает timestamp expires_at если сессия валидна, иначе None."""
        info = self.get_session_info(token)
        return info['expires_at'] if (info and isinstance(info, dict)) else None

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._l1_cache.pop(token, None)

        try:
            with write_transaction() as con:
                con.execute('DELETE FROM app_sessions WHERE token = ?', (token,))
        except Exception as e:
            logger.error(f"[SessionStore] Ошибка удаления сессии из БД: {e}")
            if self.failure_policy == DBFailurePolicy.STRICT:
                raise

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
        except Exception as e:
            logger.error(f"[SessionStore] Ошибка фоновой очистки сессий в БД: {e}")
            if self.failure_policy == DBFailurePolicy.STRICT:
                raise

    def clear_l1_cache(self) -> None:
        with self._lock:
            self._l1_cache.clear()
