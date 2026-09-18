# -*- coding: utf-8 -*-
import base64
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
from http.cookies import SimpleCookie

import config
from services.security import auth_service
from services.security.request_guards import (
    parse_bounded_form,
    parse_bounded_multipart,
    read_bounded_body,
    send_payload_error,
)
from services.websocket import ws_manager
from templates import layout

logger = logging.getLogger('kvit.server')
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SW_JS_PATH = '/sw.js'


class BaseHandlerMixin:
    """Базовые HTTP-хелперы, аутентификация, CSRF, сессии и статическая раздача."""

    @property
    def task_manager(self):
        """Возвращает актуальный экземпляр менеджера задач (из server.py, self.server или синглтон по умолчанию)."""
        import sys
        srv = sys.modules.get('server')
        if srv and hasattr(srv, 'task_manager'):
            return srv.task_manager
        if hasattr(self, 'server') and hasattr(self.server, 'task_manager'):
            return self.server.task_manager
        from services.tasks import task_manager as default_tm
        return default_tm

    def log_message(self, format, *args):
        """Перенаправляет стандартные HTTP логи доступа в централизованный логер."""
        logger.info(f"{self._get_client_ip()} - {format % args}")

    def _is_trusted_proxy(self, ip_str: str) -> bool:
        """Проверяет, принадлежит ли IP-адрес доверенной подсети обратного прокси."""
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            return any(ip_obj in net for net in config.TRUSTED_PROXY_NETWORKS)
        except ValueError:
            return False

    def _get_client_ip(self) -> str:
        """Определяет реальный IP-адрес клиента с защитой от спуфинга заголовков."""
        peer_ip = self.client_address[0] if self.client_address else '127.0.0.1'

        if not getattr(config, 'TRUST_PROXY', False) or not self._is_trusted_proxy(peer_ip):
            return peer_ip

        forwarded = self.headers.get('X-Forwarded-For')
        if forwarded:
            ips = [p.strip() for p in forwarded.split(',') if p.strip()]
            for candidate in reversed(ips):
                try:
                    ipaddress.ip_address(candidate)
                    if not self._is_trusted_proxy(candidate):
                        return candidate
                except ValueError:
                    continue
            if ips:
                try:
                    ipaddress.ip_address(ips[0])
                    return ips[0]
                except ValueError:
                    pass

        real_ip = self.headers.get('X-Real-IP')
        if real_ip:
            candidate = real_ip.strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass

        return peer_ip

    def _is_request_https(self) -> bool:
        """Определяет, защищено ли соединение (TLS/HTTPS или доверенный заголовок X-Forwarded-Proto)."""
        if getattr(config, 'USE_HTTPS', False):
            return True
        peer_ip = self.client_address[0] if self.client_address else '127.0.0.1'
        if getattr(config, 'TRUST_PROXY', False) and self._is_trusted_proxy(peer_ip):
            proto = self.headers.get('X-Forwarded-Proto', '').strip().lower()
            if proto == 'https':
                return True
        return False

    def _get_session_cookie_header(self, token: str, max_age: int = 86400) -> str:
        """Формирует заголовок Set-Cookie с атрибутами безопасности HttpOnly, SameSite, Secure."""
        mode = getattr(config, 'COOKIE_SECURE', 'auto').strip().lower()
        if mode in ('true', '1', 'yes'):
            use_secure = True
        elif mode in ('false', '0', 'no'):
            use_secure = False
        else:
            use_secure = self._is_request_https()

        secure_flag = "; Secure" if use_secure else ""
        return f"session={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure_flag}"

    def _get_session_token(self):
        if not hasattr(self, 'headers') or not self.headers:
            return None
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
            if 'session' in cookie:
                return cookie['session'].value
        except Exception:
            pass
        return None

    def _get_current_user(self):
        token = self._get_session_token()
        if not token:
            return None
        return auth_service.get_session_user(token)

    def _is_authenticated(self) -> bool:
        return self._get_current_user() is not None

    def _is_admin(self) -> bool:
        user = self._get_current_user()
        return user is not None and user.get('role') == 'admin'

    def _is_operator_or_admin(self) -> bool:
        user = self._get_current_user()
        return user is not None and user.get('role') in ('admin', 'operator')

    def _is_assistant_or_admin(self) -> bool:
        user = self._get_current_user()
        return user is not None and user.get('role') in ('admin', 'assistant')

    def _verify_csrf(self, body_csrf: str = None) -> bool:
        """Проверяет CSRF-токен из X-CSRF-Token, X-CSRFToken или поля формы."""
        if not getattr(config, 'CSRF_ENABLED', True):
            return True
        session_token = self._get_session_token()
        if not session_token:
            return False
        csrf_token = (
            self.headers.get('X-CSRF-Token')
            or self.headers.get('X-CSRFToken')
            or body_csrf
        )
        if not csrf_token:
            return False
        return auth_service.verify_csrf_token(session_token, csrf_token)

    def _send_security_headers(self):
        """Внедрение обязательных заголовков безопасности и идентификатора инстанса."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if not getattr(config, 'IS_PRODUCTION', False):
            backend_instance = os.environ.get('HOSTNAME') or f"pid-{os.getpid()}"
            self.send_header('X-Backend-Instance', backend_instance)

    def send_html(self, text: str, code: int = 200, extra_headers: dict = None):
        try:
            data = text.encode('utf-8')
            self.send_response(code)
            self._send_security_headers()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            request_locale = getattr(self, 'request_locale', None)
            if request_locale in ('ru', 'kk'):
                self.send_header('Set-Cookie', f'krec_lang={request_locale}; Path=/; Max-Age=31536000; SameSite=Lax')
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def send_json(self, data: dict, code: int = 200, extra_headers: dict = None):
        try:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self._send_security_headers()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _read_bounded_body(self, max_bytes: int, allow_chunked: bool = True) -> bytes | None:
        return read_bounded_body(self, max_bytes=max_bytes, allow_chunked=allow_chunked)

    def _send_payload_error(self, code: int, message: str) -> None:
        return send_payload_error(self, code=code, message=message)

    def _read_form_params(self, max_bytes: int | None = None) -> dict[str, list[str]]:
        return parse_bounded_form(self, max_bytes=max_bytes)

    def _parse_multipart_fields_and_files(self, max_bytes: int | None = None):
        return parse_bounded_multipart(self, max_bytes=max_bytes)

    def _serve_static(self, path: str):
        clean_path = path.split('?')[0].split('#')[0]
        if clean_path.startswith('/static/'):
            rel_path = clean_path[len('/static/'):]
        else:
            rel_path = clean_path.lstrip('/')
        target_file = os.path.join(config.STATIC_DIR, rel_path)
        try:
            abs_target = os.path.abspath(target_file)
            abs_static = os.path.abspath(config.STATIC_DIR)
            if os.path.commonpath([abs_target, abs_static]) != abs_static or not os.path.isfile(abs_target):
                self.send_html(layout("<h1>404 Not Found</h1>"), 404)
                return

            mime_type, _ = mimetypes.guess_type(abs_target)
            if not mime_type:
                mime_type = 'application/octet-stream'

            if path == SW_JS_PATH:
                mime_type = 'application/javascript; charset=utf-8'
            elif path == '/manifest.json':
                mime_type = 'application/manifest+json; charset=utf-8'
            elif path == '/offline.html':
                mime_type = 'text/html; charset=utf-8'

            with open(abs_target, 'rb') as f:
                data = f.read()

            self.send_response(200)
            self._send_security_headers()
            if path == SW_JS_PATH:
                self.send_header('Service-Worker-Allowed', '/')
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_html(layout("<h1>404 Not Found</h1>"), 404)

    def _serve_maintenance_page(self):
        m_path = os.path.join(config.STATIC_DIR, 'maintenance.html')
        if os.path.isfile(m_path):
            try:
                with open(m_path, 'rb') as f:
                    content = f.read()
                self.send_response(503)
                self._send_security_headers()
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Retry-After', '300')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception:
                pass
        self.send_html("<!DOCTYPE html><html><head><title>503 Service Unavailable</title></head><body><h1>Ведутся технические работы</h1><p>Сайт временно недоступен в связи с плановым обновлением.</p></body></html>", 503)

    def _redirect(self, location: str, extra_headers: dict = None):
        self.send_response(302)
        self.send_header('Location', location)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()

    def _handle_websocket(self):
        key = self.headers.get('Sec-WebSocket-Key')
        if not key:
            self.send_error(400, 'Missing Sec-WebSocket-Key')
            return

        accept_val = base64.b64encode(hashlib.sha1((key + WS_GUID).encode('utf-8'), usedforsecurity=False).digest()).decode('utf-8')

        try:
            self.send_response(101, 'Switching Protocols')
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', accept_val)
            self.end_headers()
            self.wfile.flush()
        except Exception:
            return

        self.close_connection = True
        ws_manager.handle_connection(self.connection, self._get_client_ip())
