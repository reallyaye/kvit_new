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


from database.connection import get_db, write_transaction
from logger import logger


class AuthService:
    """
    Потокобезопасный сервис аутентификации и авторизации (RBAC),
    использующий абстракцию SessionStore и таблицы users/audit_logs.
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
        """Безопасная проверка мастер-пароля администратора строго по PBKDF2 хешу из конфигурации."""
        if not isinstance(password, str) or not password:
            return False
        clean_pwd = password.strip()
        if not clean_pwd:
            return False

        stored_hash = (getattr(config, 'ADMIN_PASSWORD_HASH', '') or '').strip()
        if stored_hash:
            return verify_password_hash(clean_pwd, stored_hash)

        return False

    def verify_credentials(self, username: str, password: str) -> Optional[dict]:
        """
        Проверяет логин и пароль пользователя в таблице users.
        Возвращает dict с данными пользователя или None при неверных данных.
        """
        if not username or not password or not isinstance(username, str) or not isinstance(password, str):
            return None

        clean_user = username.strip()
        clean_pwd = password.strip()
        if not clean_user or not clean_pwd:
            return None

        try:
            con = get_db()
            try:
                row = con.execute(
                    "SELECT id, username, password_hash, full_name, role, is_active FROM users WHERE LOWER(username) = LOWER(?)",
                    (clean_user,)
                ).fetchone()

                if row:
                    u_id, u_name, u_hash, u_fname, u_role, u_active = row[0], row[1], row[2], row[3], row[4], bool(row[5])
                    if not u_active:
                        logger.warning(f"[Auth] Попытка входа заблокированного пользователя: {clean_user}")
                        return None
                    if verify_password_hash(clean_pwd, u_hash):
                        # Обновляем timestamp последнего входа
                        with write_transaction() as wcon:
                            wcon.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (time.time(), u_id))
                        return {
                            'id': u_id,
                            'username': u_name,
                            'full_name': u_fname or u_name,
                            'role': u_role or 'operator'
                        }
            finally:
                con.close()
        except Exception as e:
            logger.error(f"[Auth] Ошибка проверки учетных данных в БД: {e}")

        # Fallback для администратора из конфигурации при пустой БД
        if clean_user.lower() == 'admin':
            stored_hash = (getattr(config, 'ADMIN_PASSWORD_HASH', '') or '').strip()
            if stored_hash and verify_password_hash(clean_pwd, stored_hash):
                return {
                    'id': 1,
                    'username': 'admin',
                    'full_name': 'Главный Администратор',
                    'role': 'admin'
                }

        return None

    def create_session(self, username: str = 'admin', role: str = 'admin') -> str:
        """Создаёт новую сессию с указанной ролью и именем пользователя."""
        token = secrets.token_hex(32)
        now = time.time()
        expires_at = now + SESSION_LIFETIME

        self.store.cleanup_expired()
        self.store.save_session(token, expires_at, now, username=username, role=role)
        return token

    def is_valid_session(self, token: str) -> bool:
        """Проверяет валидность токена через SessionStore."""
        if not token or not isinstance(token, str):
            return False

        expiry = self.store.get_session_expiry(token)
        return expiry is not None and time.time() <= expiry

    def get_session_user(self, token: str) -> Optional[dict]:
        """Возвращает информацию о текущем авторизованном пользователе и его роли."""
        if not token or not isinstance(token, str):
            return None
        info = self.store.get_session_info(token)
        if not info:
            return None
        if time.time() > info.get('expires_at', 0):
            return None
        return {
            'username': info.get('username', 'admin'),
            'role': info.get('role', 'admin')
        }

    def destroy_session(self, token: str) -> None:
        """Удаляет сессию из памяти и персистентного хранилища."""
        self.store.delete_session(token)

    def get_csrf_token(self, session_token: str) -> str:
        """Генерирует криптографически стойкий CSRF-токен (HMAC-SHA256)."""
        if not session_token or not isinstance(session_token, str):
            return ""
        secret_key = (getattr(config, 'SECRET_KEY', '') or '').strip()
        if not secret_key:
            raise ValueError("Критическая ошибка безопасности: SECRET_KEY не задан в конфигурации.")
        secret = secret_key.encode('utf-8')
        message = f"csrf:{session_token}".encode('utf-8')
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def verify_csrf_token(self, session_token: str, csrf_token: str) -> bool:
        """Проверяет CSRF-токен с защитой от атак по времени (Timing Attack Resistant)."""
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

    # ────────────────────── Управление пользователями (RBAC) ──────────────────────

    def create_user(self, username: str, password: str, full_name: str = '', role: str = 'operator') -> dict:
        """Создает нового пользователя (оператора сбыта или администратора)."""
        if not username or not password:
            raise ValueError("Логин и пароль обязательны для заполнения")
        clean_user = username.strip().lower()
        if len(clean_user) < 3:
            raise ValueError("Логин должен содержать не менее 3 символов")
        if len(password) < 6:
            raise ValueError("Пароль должен содержать не менее 6 символов")

        pwd_hash = hash_password(password)
        now = time.time()

        with write_transaction() as con:
            existing = con.execute("SELECT id FROM users WHERE LOWER(username) = ?", (clean_user,)).fetchone()
            if existing:
                raise ValueError(f"Пользователь с логином '{clean_user}' уже существует")

            con.execute(
                "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (clean_user, pwd_hash, full_name.strip(), role, True, now)
            )
        return {'username': clean_user, 'full_name': full_name, 'role': role}

    def list_users(self) -> list:
        """Возвращает список всех зарегистрированных пользователей."""
        con = get_db()
        try:
            rows = con.execute(
                "SELECT id, username, full_name, role, is_active, created_at, last_login_at FROM users ORDER BY id ASC"
            ).fetchall()
            users = []
            for r in rows:
                users.append({
                    'id': r[0],
                    'username': r[1],
                    'full_name': r[2] or r[1],
                    'role': r[3],
                    'is_active': bool(r[4]),
                    'created_at': r[5],
                    'last_login_at': r[6]
                })
            return users
        finally:
            con.close()

    def update_user_password(self, username: str, new_password: str) -> bool:
        """Обновляет пароль пользователя."""
        if not new_password or len(new_password) < 6:
            raise ValueError("Новый пароль должен содержать не менее 6 символов")
        pwd_hash = hash_password(new_password)
        with write_transaction() as con:
            res = con.execute("UPDATE users SET password_hash = ? WHERE LOWER(username) = LOWER(?)", (pwd_hash, username.strip()))
            return True

    def delete_user(self, username: str) -> bool:
        """Удаляет пользователя (запрещено удалять главного администратора 'admin')."""
        clean_user = username.strip().lower()
        if clean_user == 'admin':
            raise ValueError("Запрещено удалять главного администратора системы")
        with write_transaction() as con:
            con.execute("DELETE FROM users WHERE LOWER(username) = ?", (clean_user,))
            return True

    def toggle_user_active(self, username: str, is_active: bool) -> bool:
        """Включает или блокирует учетную запись пользователя."""
        clean_user = username.strip().lower()
        if clean_user == 'admin' and not is_active:
            raise ValueError("Запрещено блокировать главного администратора системы")
        with write_transaction() as con:
            con.execute("UPDATE users SET is_active = ? WHERE LOWER(username) = ?", (bool(is_active), clean_user))
            return True

    # ────────────────────── Журнал аудита действий (Audit Log) ──────────────────────

    def log_audit(self, username: str, ip: str, action: str, details: str = '') -> None:
        """Записывает событие в журнал аудита безопасности."""
        try:
            with write_transaction() as con:
                con.execute(
                    "INSERT INTO audit_logs (created_at, username, ip, action, details) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), username or 'anonymous', ip or '127.0.0.1', action, details)
                )
        except Exception as e:
            logger.error(f"[Audit] Ошибка записи в журнал аудита: {e}")

    def list_audit_logs(
        self,
        limit: int = 50,
        username: Optional[str] = None,
        action: Optional[str] = None,
        search: Optional[str] = None
    ) -> list:
        """Возвращает записи журнала аудита с поддержкой гибкой фильтрации."""
        con = get_db()
        try:
            query = "SELECT id, created_at, username, ip, action, details FROM audit_logs"
            conditions = []
            params: list = []

            if username:
                conditions.append("username = ?")
                params.append(username)

            if action:
                conditions.append("action = ?")
                params.append(action)

            if search:
                conditions.append("(details LIKE ? OR ip LIKE ? OR username LIKE ?)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = con.execute(query, tuple(params)).fetchall()
            logs = []
            for r in rows:
                logs.append({
                    'id': r[0],
                    'created_at': r[1],
                    'username': r[2],
                    'ip': r[3],
                    'action': r[4],
                    'details': r[5]
                })
            return logs
        finally:
            con.close()

    def get_audit_stats(self) -> dict:
        """Возвращает сводную статистику по журналу аудита для администратора."""
        con = get_db()
        try:
            total = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0
            logins = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'LOGIN'").fetchone()[0] or 0
            failed_logins = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'LOGIN_FAILED'").fetchone()[0] or 0
            uploads = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'UPLOAD_RECEIPTS'").fetchone()[0] or 0
            
            # Уникальные пользователи и действия для выпадающих списков фильтра
            user_rows = con.execute("SELECT DISTINCT username FROM audit_logs WHERE username IS NOT NULL AND username != '' ORDER BY username").fetchall()
            action_rows = con.execute("SELECT DISTINCT action FROM audit_logs WHERE action IS NOT NULL AND action != '' ORDER BY action").fetchall()
            
            return {
                'total': total,
                'logins': logins,
                'failed_logins': failed_logins,
                'uploads': uploads,
                'users': [r[0] for r in user_rows],
                'actions': [r[0] for r in action_rows]
            }
        finally:
            con.close()


auth_service = AuthService()

