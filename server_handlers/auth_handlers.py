# -*- coding: utf-8 -*-
import html
import logging
from urllib.parse import parse_qs, quote

import config
from services.security import auth_service, ip_throttler
from templates import layout, render_login_form

logger = logging.getLogger('kvit.server.auth')
CSRF_INVALID_MSG = 'Недействительный или отсутствующий CSRF-токен.'


class AuthHandlerMixin:
    """Обработчики входа/выхода и администрирования пользователей (RBAC)."""

    def _handle_login(self):
        client_ip = self._get_client_ip()
        data = self._read_bounded_body(config.MAX_LOGIN_BODY_BYTES)
        if data is None:
            return
        params = parse_qs(data.decode('utf-8', errors='replace'))
        username = params.get('username', [''])[0].strip() or 'admin'
        password = params.get('password', [''])[0]

        user = auth_service.verify_credentials(username, password)
        if user:
            u_role = user.get('role', 'operator')
            u_name = user.get('username', username)
            token = auth_service.create_session(username=u_name, role=u_role)
            auth_service.log_audit(u_name, client_ip, 'LOGIN', f"Успешный вход (роль: {u_role})")

            if u_role == 'operator':
                target_url = '/upload'
            elif u_role == 'assistant':
                target_url = '/admin/appeals'
            else:
                target_url = '/admin/pages'
            self._redirect(target_url, extra_headers={
                'Set-Cookie': self._get_session_cookie_header(token, max_age=config.SESSION_LIFETIME)
            })
        else:
            auth_service.log_audit(username, client_ip, 'LOGIN_FAILED', 'Неверный логин или пароль')
            failed_count = auth_service.count_recent_failed_logins(
                client_ip,
                config.LOGIN_FAILURE_WINDOW_SECONDS,
            )
            if failed_count >= config.LOGIN_FAILURE_BAN_THRESHOLD:
                ip_throttler.ban_ip(
                    client_ip,
                    duration_seconds=config.LOGIN_FAILURE_BAN_SECONDS,
                    reason=(
                        f'Login brute force: {failed_count} failed attempts '
                        f'in {config.LOGIN_FAILURE_WINDOW_SECONDS}s'
                    ),
                )
                auth_service.log_audit(
                    username,
                    client_ip,
                    'IP_BLOCKED',
                    f'Автоблокировка на {config.LOGIN_FAILURE_BAN_SECONDS} сек. '
                    f'после {failed_count} неудачных попыток входа',
                )
                body = render_login_form(
                    'Слишком много неудачных попыток. '
                    'Доступ временно заблокирован.'
                )
                self.send_html(
                    layout(body, 'login', is_admin=False),
                    429,
                    {'Retry-After': str(config.LOGIN_FAILURE_BAN_SECONDS)},
                )
                return
            body = render_login_form('Неверный логин или пароль. Попробуйте ещё раз.')
            self.send_html(layout(body, 'login', is_admin=False))

    def _handle_admin_users_create(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_tok = params.get('csrf_token', [''])[0].strip()
        if not self._verify_csrf(body_csrf=csrf_tok):
            self._redirect('/admin/users?err=' + html.escape(CSRF_INVALID_MSG))
            return

        username = params.get('username', [''])[0].strip()
        password = params.get('password', [''])[0]
        full_name = params.get('full_name', [''])[0].strip()
        role = params.get('role', ['operator'])[0].strip()

        try:
            auth_service.create_user(username, password, full_name, role)
            auth_service.log_audit(admin_name, client_ip, 'CREATE_USER', f"Создан пользователь {username} ({role})")
            msg = quote(f"Пользователь {username} успешно создан")
            self._redirect(f'/admin/users?msg={msg}')
        except Exception as e:
            logger.error(f"[Auth] Ошибка при создании пользователя '{username}': {e}")
            err = quote(str(e))
            self._redirect(f'/admin/users?err={err}')

    def _handle_admin_users_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_tok = params.get('csrf_token', [''])[0].strip()
        if not self._verify_csrf(body_csrf=csrf_tok):
            self._redirect('/admin/users?err=' + html.escape(CSRF_INVALID_MSG))
            return

        username = params.get('username', [''])[0].strip()
        try:
            auth_service.delete_user(username)
            auth_service.log_audit(admin_name, client_ip, 'DELETE_USER', f"Удален пользователь {username}")
            msg = quote(f"Пользователь {username} удален")
            self._redirect(f'/admin/users?msg={msg}')
        except Exception as e:
            logger.error(f"[Auth] Ошибка при удалении пользователя '{username}': {e}")
            err = quote(str(e))
            self._redirect(f'/admin/users?err={err}')
