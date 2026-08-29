import hashlib
import hmac
import secrets
import time
from typing import Optional

import config
from config import SESSION_LIFETIME
from services.security.session_store import BaseSessionStore, DatabaseSessionStore


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
    Потокобезопасный сервис аутентификации, использующий абстракцию SessionStore.

    Архитектура хранилища:
    - L1 Fast In-Memory Cache (RAM с коротким TTL 10с) для мгновенной валидации O(1).
    - L2 Persistent Database Storage (app_sessions) / Redis как источник истины.
    """

    def __init__(self, session_store: Optional[BaseSessionStore] = None):
        self.store = session_store or DatabaseSessionStore(l1_ttl_seconds=10.0)

    @property
    def _lock(self):
        """Обратная совместимость со старыми тестовыми хелперами."""
        return getattr(self.store, '_lock', None)

    @property
    def _sessions(self):
        """Обратная совместимость: словарь L1 кэша."""
        return getattr(self.store, '_l1_cache', {})

    def verify_password(self, password: str) -> bool:
        """Безопасная проверка пароля администратора строго по криптостойкому PBKDF2 хешу."""
        if not isinstance(password, str) or not password:
            return False

        clean_pwd = password.strip()
        if not clean_pwd:
            return False

        stored_hash = (getattr(config, 'ADMIN_PASSWORD_HASH', '') or '').strip()
        if stored_hash:
            return verify_password_hash(clean_pwd, stored_hash)

        return False

    def create_session(self) -> str:
        """Создаёт новую сессию, сохраняет её в SessionStore и возвращает токен."""
        token = secrets.token_hex(32)
        now = time.time()
        expires_at = now + SESSION_LIFETIME

        self.store.cleanup_expired()
        self.store.save_session(token, expires_at, now)
        return token

    def is_valid_session(self, token: str) -> bool:
        """Проверяет валидность токена через SessionStore (L1 RAM -> L2 DB)."""
        if not token or not isinstance(token, str):
            return False

        expiry = self.store.get_session_expiry(token)
        return expiry is not None and time.time() <= expiry

    def destroy_session(self, token: str) -> None:
        """Удаляет сессию из памяти и персистентного хранилища."""
        self.store.delete_session(token)

    def get_csrf_token(self, session_token: str) -> str:
        """
        Генерирует криптографически стойкий CSRF-токен, привязанный к текущей сессии (HMAC-SHA256).
        При смене/инвалидации сессии CSRF-токен автоматически аннулируется.
        """
        if not session_token or not isinstance(session_token, str):
            return ""
        secret_key = (getattr(config, 'SECRET_KEY', '') or '').strip()
        if not secret_key:
            raise ValueError("Критическая ошибка безопасности: SECRET_KEY не задан в конфигурации.")
        secret = secret_key.encode('utf-8')
        message = f"csrf:{session_token}".encode('utf-8')
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def verify_csrf_token(self, session_token: str, csrf_token: str) -> bool:
        """
        Проверяет CSRF-токен с защитой от атак по времени (Timing Attack Resistant).
        """
        if not session_token or not csrf_token:
            return False
        if not self.is_valid_session(session_token):
            return False
        try:
            expected = self.get_csrf_token(session_token)
        except ValueError:
            return False
        if not expected:
            return False
        return secrets.compare_digest(str(csrf_token).strip(), expected)


auth_service = AuthService()
