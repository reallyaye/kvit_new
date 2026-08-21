import time
import secrets
import threading
import hashlib
import config
from config import SESSION_LIFETIME
from database.connection import get_db, write_transaction
from logger import logger

def hash_password(password: str, iterations: int = 600_000) -> str:
    """Генерирует криптостойкий PBKDF2-HMAC-SHA256 хеш с уникальной солью."""
    if not isinstance(password, str) or not password:
        raise ValueError("Пароль должен быть непустой строкой")
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"

def verify_password_hash(password: str, stored_hash: str) -> bool:
    """Безопасная проверка пароля против хеша PBKDF2 с защитой от атак по времени (Timing Attacks)."""
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.strip().split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
        return secrets.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False

class AuthService:
    """
    Потокобезопасный и распределенный сервис аутентификации.
    Поддерживает двухуровневое хранение:
    1. L1 Fast In-Memory Cache для субмиллисекундной проверки.
    2. L2 Persistent Database Storage (app_sessions) для сохранения сессий при перезапусках
       и синхронизации между несколькими репликами приложения за балансировщиком.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}  # {token: expiry_time}
        self._last_cleanup = time.time()
        self._load_active_sessions_from_db()

    def _load_active_sessions_from_db(self):
        """Загружает непросроченные сессии из БД при старте инстанса."""
        now = time.time()
        try:
            con = get_db()
            try:
                rows = con.execute('SELECT token, expires_at FROM app_sessions WHERE expires_at > ?', (now,)).fetchall()
                with self._lock:
                    for r in rows:
                        self._sessions[r[0]] = float(r[1])
            finally:
                con.close()
        except Exception:
            pass

    def verify_password(self, password: str) -> bool:
        """Безопасная проверка пароля администратора строго по криптостойкому PBKDF2 хешу."""
        if not isinstance(password, str) or not password or not password.strip():
            return False

        stored_hash = (config.ADMIN_PASSWORD_HASH or '').strip()
        if stored_hash:
            return verify_password_hash(password, stored_hash)

        return False

    def create_session(self) -> str:
        """Создаёт новую сессию, сохраняет её в БД и возвращает токен."""
        token = secrets.token_hex(32)
        now = time.time()
        expires_at = now + SESSION_LIFETIME

        with self._lock:
            self._cleanup_expired(now)
            self._sessions[token] = expires_at

        # Персистируем в БД для выживания при рестартах и шаринга между репликами
        try:
            with write_transaction() as con:
                con.execute('INSERT OR REPLACE INTO app_sessions(token, expires_at, created_at) VALUES (?, ?, ?)',
                            (token, expires_at, now))
        except Exception as e:
            logger.warn(f"[Auth] Не удалось сохранить сессию в БД: {e}")

        return token

    def is_valid_session(self, token: str) -> bool:
        """Проверяет валидность токена сессии с гарантией консистентности между репликами."""
        if not token or not isinstance(token, str):
            return False

        now = time.time()
        # Авторитетная проверка в БД (гарантирует мгновенную инвалидацию logout на всех репликах)
        try:
            con = get_db()
            try:
                row = con.execute('SELECT expires_at FROM app_sessions WHERE token = ?', (token,)).fetchone()
                if row:
                    db_expiry = float(row[0])
                    if now <= db_expiry:
                        with self._lock:
                            self._sessions[token] = db_expiry
                        return True
                    else:
                        self.destroy_session(token)
                        return False
                else:
                    with self._lock:
                        self._sessions.pop(token, None)
                    return False
            finally:
                con.close()
        except Exception:
            # Fallback на локальную память при временных сбоях соединения с БД
            with self._lock:
                expiry = self._sessions.get(token)
                if expiry is not None and now <= expiry:
                    return True
            return False

    def destroy_session(self, token: str):
        """Удаляет сессию из памяти и персистентного хранилища."""
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

        try:
            with write_transaction() as con:
                con.execute('DELETE FROM app_sessions WHERE token = ?', (token,))
        except Exception:
            pass

    def _cleanup_expired(self, now: float):
        """Очищает просроченные сессии из памяти и БД."""
        if now - self._last_cleanup > 300:  # раз в 5 минут
            expired = [t for t, exp in self._sessions.items() if exp < now]
            for t in expired:
                self._sessions.pop(t, None)
            self._last_cleanup = now

            try:
                with write_transaction() as con:
                    con.execute('DELETE FROM app_sessions WHERE expires_at <= ?', (now,))
            except Exception:
                pass

auth_service = AuthService()


