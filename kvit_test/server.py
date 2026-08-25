import base64
import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import tempfile
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import mimetypes
import config
from config import PROTECTED_PATHS, RATE_LIMIT_API, RATE_LIMIT_LOGIN, RATE_LIMIT_SEARCH, WS_GUID
from database import get_db, purge_missing_receipts, sync_receipts_with_filesystem
from logger import logger
from services.pdf import pdf_processor
from services.receipts import receipt_service
from services.reconciliation import reconcile_service
from services.security import auth_service, ip_throttler, rate_limiter
from services.websocket import ws_manager
from templates import (
    layout,
    render_404_page,
    render_address_clarification_prompt,
    render_address_not_found,
    render_forbidden_page,
    render_login_form,
    render_rate_limit_page,
    render_reconcile_page,
    render_search_form,
    render_search_result,
    render_throttled_page,
    render_upload_form,
)
from templates.portal_views import PORTAL_PAGES, DOCUMENTS_REGISTRY, render_page as render_portal_page, render_document as render_portal_document


class AppRequestHandler(BaseHTTPRequestHandler):
    """Главный HTTP-шлюз и роутер приложения."""

    def log_message(self, format, *args):
        """Перенаправляет стандартные HTTP логи доступа в централизованный логер."""
        logger.info(f"{self._get_client_ip()} - {format % args}")

    # ────────────────────── Вспомогательные методы ──────────────────────

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

        # Если TRUST_PROXY выключен или прямое соединение поступило НЕ от доверенного прокси,
        # любые заголовки X-Forwarded-For и X-Real-IP безусловно игнорируются
        if not getattr(config, 'TRUST_PROXY', False) or not self._is_trusted_proxy(peer_ip):
            return peer_ip

        # Обработка цепочки X-Forwarded-For (клиент, прокси1, прокси2...)
        # Идем справа налево: первый не доверенный прокси IP является реальным адресом клиента
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
        """
        Формирует заголовок Set-Cookie с атрибутами безопасности:
        - HttpOnly: защита от XSS кражи токена
        - SameSite=Strict: защита от CSRF атак
        - Secure: защита от отправки cookie по открытому HTTP-каналу
        """
        mode = getattr(config, 'COOKIE_SECURE', 'auto').strip().lower()
        use_secure = False
        if mode in ('true', '1', 'yes'):
            use_secure = True
        elif mode in ('false', '0', 'no'):
            use_secure = False
        else:  # auto
            if self._is_request_https() or os.environ.get('ENVIRONMENT', '').lower() == 'production':
                use_secure = True

        secure_flag = "; Secure" if use_secure else ""
        return f"session={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure_flag}"

    def _get_session_token(self):
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

    def _is_admin(self) -> bool:
        token = self._get_session_token()
        return auth_service.is_valid_session(token)

    def _verify_csrf(self, body_csrf: str = None) -> bool:
        """
        Проверяет CSRF-токен для защищенных административных POST запросов.
        Токен считывается из заголовка X-CSRF-Token / X-CSRFToken или поля формы csrf_token.
        """
        if not getattr(config, 'CSRF_ENABLED', True):
            return True
        session_token = self._get_session_token()
        if not session_token:
            return False
        csrf_token = (
            self.headers.get('X-CSRF-Token') or
            self.headers.get('X-CSRFToken') or
            body_csrf
        )
        if not csrf_token:
            return False
        return auth_service.verify_csrf_token(session_token, csrf_token)

    def _send_security_headers(self):
        """Внедрение обязательных заголовков безопасности."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')

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

    def _serve_static(self, path: str):
        """Безопасная отдача статических файлов (CSS, JS, изображения, PDF)."""
        rel_path = path.lstrip('/')
        target_file = os.path.join(config.STATIC_DIR, rel_path)
        try:
            abs_target = os.path.abspath(target_file)
            abs_static = os.path.abspath(config.STATIC_DIR)
            if os.path.commonpath([abs_target, abs_static]) != abs_static or not os.path.isfile(abs_target):
                self.send_html(render_portal_page('404'), 404)
                return

            mime_type, _ = mimetypes.guess_type(abs_target)
            if not mime_type:
                mime_type = 'application/octet-stream'

            with open(abs_target, 'rb') as f:
                data = f.read()

            self.send_response(200)
            self._send_security_headers()
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_html(render_portal_page('404'), 404)

    def _redirect(self, location: str, extra_headers: dict = None):
        self.send_response(302)
        self.send_header('Location', location)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()

    # ────────────────────── WebSocket Handshake ──────────────────────

    def _handle_websocket(self):
        """Выполняет handshake WebSocket (RFC 6455) и передает управление в WebSocket менеджер."""
        key = self.headers.get('Sec-WebSocket-Key')
        if not key:
            self.send_error(400, 'Missing Sec-WebSocket-Key')
            return

        # Согласно спецификации RFC 6455 (WebSocket Handshake), для вычисления Sec-WebSocket-Accept используется SHA-1
        accept_val = base64.b64encode(hashlib.sha1((key + WS_GUID).encode('utf-8'), usedforsecurity=False).digest()).decode('utf-8')  # nosec B324

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

    # ────────────────────── GET ──────────────────────

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        is_admin = self._is_admin()
        client_ip = self._get_client_ip()

        # WebSocket перехват
        if path == '/ws' and self.headers.get('Upgrade', '').lower() == 'websocket':
            self._handle_websocket()
            return

        # Статические файлы (CSS, JS, изображения, PDF, favicon, robots, sitemap)
        if path.startswith(('/css/', '/images/', '/files/')) or path in ('/favicon.ico', '/robots.txt', '/sitemap.xml'):
            self._serve_static(path)
            return

        # 1. IP Throttling (ограничение одновременных запросов и всплесков)
        throttle_allowed, throttle_reason, throttle_retry = ip_throttler.acquire(client_ip)
        if not throttle_allowed:
            if path.startswith('/api/'):
                msg = 'Слишком много одновременных запросов с вашего IP' if throttle_reason == 'concurrency_limit' else 'Слишком высокая частота запросов (burst limit)'
                self.send_json({
                    'error': 'Throttled',
                    'message': f'{msg}. Пожалуйста, подождите {throttle_retry} сек.',
                    'retry_after': throttle_retry
                }, 429, {
                    'Retry-After': str(throttle_retry),
                    'X-Throttled-Reason': throttle_reason
                })
            else:
                body = render_throttled_page(throttle_retry)
                self.send_html(layout(body, 'search', is_admin=is_admin), 429, {'Retry-After': str(throttle_retry)})
            return

        try:
            # 2. Rate Limit для API эндпоинтов (GET)
            if path.startswith('/api/') and path != '/api/stats':
                allowed, retry_after, remaining = rate_limiter.is_allowed('api', client_ip, RATE_LIMIT_API, 60)
                if not allowed:
                    self.send_json({
                        'error': 'Too Many Requests',
                        'message': f'Превышен лимит запросов к API. Пожалуйста, подождите {retry_after} сек.',
                        'retry_after': retry_after
                    }, 429, {
                        'Retry-After': str(retry_after),
                        'X-RateLimit-Limit': str(RATE_LIMIT_API),
                        'X-RateLimit-Remaining': '0'
                    })
                    return

            # 3. Rate Limit для публичных операций поиска и скачивания
            if path in ('/search', '/receipt', '/download'):
                allowed, retry_after, remaining = rate_limiter.is_allowed('search', client_ip, RATE_LIMIT_SEARCH, 60)
                if not allowed:
                    body = render_rate_limit_page(retry_after)
                    self.send_html(layout(body, 'search', is_admin=is_admin), 429, {'Retry-After': str(retry_after)})
                    return

            # ── 4. Роутинг API и сервиса квитанций ───────────────────────────
            if path == '/api/stats':
                self._handle_api_stats(q)
                return
            elif path == '/api/search':
                self._handle_api_search(q)
                return
            elif path in ('/kvit', '/kvit/'):
                tab = q.get('tab', ['account'])[0].strip()
                periods = receipt_service.get_distinct_periods()
                body = render_search_form(periods, active_tab=tab)
                self.send_html(layout(body, 'search', is_admin=is_admin))
                return
            elif path == '/search':
                account = q.get('account', [''])[0].strip()
                address_query = q.get('address', [''])[0].strip()
                street = q.get('street', [''])[0].strip()
                house = q.get('house', [''])[0].strip()
                flat = q.get('flat', [''])[0].strip()
                period_filter = q.get('period', [''])[0].strip()

                if account:
                    account_row = receipt_service.get_account(account)
                    receipts = receipt_service.get_receipts(account, period_filter) if account_row else []
                    body = render_search_result(account, period_filter, account_row, receipts)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                elif street or house:
                    status, acc_data, prompt_msg = receipt_service.search_by_structured_address(street, house, flat)
                    combined_query = f"{street} {house} {flat}".strip()
                    if status == 'EXACT_MATCH' and acc_data:
                        acc_num = str(acc_data['account_number'])
                        account_row = receipt_service.get_account(acc_num)
                        receipts = receipt_service.get_receipts(acc_num, period_filter) if account_row else []
                        body = render_search_result(acc_num, period_filter, account_row, receipts)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                    elif status == 'NOT_FOUND':
                        periods = receipt_service.get_distinct_periods()
                        body = render_address_not_found(combined_query, period_filter, prompt_msg, periods)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                    else:
                        periods = receipt_service.get_distinct_periods()
                        body = render_address_clarification_prompt(combined_query, period_filter, prompt_msg, periods)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                elif address_query:
                    status, acc_data, prompt_msg = receipt_service.search_account_by_specific_address(address_query)
                    if status == 'EXACT_MATCH' and acc_data:
                        acc_num = str(acc_data['account_number'])
                        account_row = receipt_service.get_account(acc_num)
                        receipts = receipt_service.get_receipts(acc_num, period_filter) if account_row else []
                        body = render_search_result(acc_num, period_filter, account_row, receipts)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                    elif status == 'NOT_FOUND':
                        periods = receipt_service.get_distinct_periods()
                        body = render_address_not_found(address_query, period_filter, prompt_msg, periods)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                    else:
                        periods = receipt_service.get_distinct_periods()
                        body = render_address_clarification_prompt(address_query, period_filter, prompt_msg, periods)
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                else:
                    self._redirect('/kvit/')
            elif path == '/login':
                if is_admin:
                    self._redirect('/kvit/')
                else:
                    body = render_login_form()
                    self.send_html(layout(body, 'login', is_admin=False))
            elif path == '/logout':
                token = self._get_session_token()
                if token:
                    auth_service.destroy_session(token)
                self._redirect('/', extra_headers={
                    'Set-Cookie': self._get_session_cookie_header('', max_age=0)
                })
            elif path in PROTECTED_PATHS:
                if not is_admin:
                    self._redirect('/login')
                    return
                session_token = self._get_session_token()
                csrf_tok = auth_service.get_csrf_token(session_token) if is_admin else ''
                if path == '/upload':
                    body = render_upload_form(csrf_token=csrf_tok)
                    self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
                elif path == '/reconcile':
                    filt = q.get('filter', ['without'])[0]
                    if filt not in ('all', 'with', 'without', 'orphans'):
                        filt = 'without'
                    period_filter = q.get('period', [''])[0].strip()
                    page_num = max(1, int(q.get('page', ['1'])[0]))
                    data = reconcile_service.get_reconciliation_data(filt, period_filter, page_num)
                    body = render_reconcile_page(data)
                    self.send_html(layout(body, 'reconcile', is_admin=True, csrf_token=csrf_tok))
            elif path in ('/receipt', '/download'):
                self._serve_pdf(path, q)

            # ── 5. Роутинг информационного портала КРЭК ─────────────────────
            elif path in ('/', '/index.php', '/index.html'):
                self.send_html(render_portal_page('home'))
            else:
                clean_name = path.strip('/').removesuffix('.php').strip('/')
                if clean_name in PORTAL_PAGES:
                    self.send_html(render_portal_page(clean_name))
                    return

                doc_key = os.path.basename(path).strip('/')
                if not doc_key.endswith('.php'):
                    doc_key += '.php'
                if doc_key in DOCUMENTS_REGISTRY:
                    self.send_html(render_portal_document(DOCUMENTS_REGISTRY[doc_key]))
                    return

                # 404 Not Found
                self.send_html(render_portal_page('404'), 404)
        finally:
            ip_throttler.release(client_ip)

    # ────────────────────── POST ──────────────────────

    def do_POST(self):
        u = urlparse(self.path)
        is_admin = self._is_admin()
        client_ip = self._get_client_ip()

        # 1. IP Throttling (ограничение одновременных запросов и всплесков)
        throttle_allowed, throttle_reason, throttle_retry = ip_throttler.acquire(client_ip)
        if not throttle_allowed:
            if u.path.startswith('/api/'):
                msg = 'Слишком много одновременных запросов с вашего IP' if throttle_reason == 'concurrency_limit' else 'Слишком высокая частота запросов (burst limit)'
                self.send_json({
                    'error': 'Throttled',
                    'message': f'{msg}. Пожалуйста, подождите {throttle_retry} сек.',
                    'retry_after': throttle_retry
                }, 429, {
                    'Retry-After': str(throttle_retry),
                    'X-Throttled-Reason': throttle_reason
                })
            else:
                body = render_login_form(f'Слишком много одновременных запросов. Пожалуйста, подождите {throttle_retry} сек.')
                self.send_html(layout(body, 'login', is_admin=False), 429)
            return

        try:
            # 2. Rate Limit для попыток авторизации (защита от брутфорса)
            if u.path == '/login':
                allowed, retry_after, remaining = rate_limiter.is_allowed('login', client_ip, RATE_LIMIT_LOGIN, 60)
                if not allowed:
                    body = render_login_form(f'Слишком много попыток входа. В целях безопасности подождите {retry_after} сек.')
                    self.send_html(layout(body, 'login', is_admin=False), 429, {'Retry-After': str(retry_after)})
                    return
                self._handle_login()
                return

            # 3. Rate Limit для API эндпоинтов (POST)
            if u.path.startswith('/api/'):
                allowed, retry_after, remaining = rate_limiter.is_allowed('api', client_ip, RATE_LIMIT_API, 60)
                if not allowed:
                    self.send_json({
                        'error': 'Too Many Requests',
                        'message': f'Превышен лимит запросов к API. Пожалуйста, подождите {retry_after} сек.',
                        'retry_after': retry_after
                    }, 429, {
                        'Retry-After': str(retry_after),
                        'X-RateLimit-Limit': str(RATE_LIMIT_API),
                        'X-RateLimit-Remaining': '0'
                    })
                    return

            # Роутинг POST запросов
            if u.path == '/upload':
                if not is_admin:
                    self._redirect('/login')
                    return
                self._handle_upload()
            elif u.path == '/import-folder':
                if not is_admin:
                    self._redirect('/login')
                    return
                self._handle_import_folder()
            elif u.path == '/api/upload-batch':
                self._handle_api_upload_batch()
            elif u.path == '/api/sync-receipts':
                self._handle_api_sync_receipts()
            elif u.path == '/api/purge-missing-receipts':
                self._handle_api_purge_missing_receipts()
            else:
                self.send_html(layout(render_404_page(), is_admin=is_admin), 404)
        finally:
            ip_throttler.release(client_ip)

    # ────────────────────── Обработчики действий ──────────────────────

    def _handle_login(self):
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        params = parse_qs(data.decode('utf-8', errors='replace'))
        password = params.get('password', [''])[0]

        if auth_service.verify_password(password):
            token = auth_service.create_session()
            self._redirect('/', extra_headers={
                'Set-Cookie': self._get_session_cookie_header(token, max_age=config.SESSION_LIFETIME)
            })
        else:
            body = render_login_form('Неверный пароль. Попробуйте ещё раз.')
            self.send_html(layout(body, 'login', is_admin=False))

    def _parse_multipart_to_disk(self):
        """
        Потоковый разбор multipart/form-data на диск с константным потреблением памяти O(1).
        Включает жесткие лимиты безопасности уровня приложения:
        - MAX_UPLOAD_BYTES: ограничение общего размера тела запроса (защита от DoS)
        - MAX_FILES_PER_REQUEST: ограничение количества файлов в одной пачке
        - MAX_HEADER_SIZE: ограничение размера заголовков одной секции (64 KB)
        """
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0

        # Защита от DoS: проверка размера тела запроса по заголовку
        if content_length > config.MAX_UPLOAD_BYTES:
            logger.warning(f"[Upload] Отклонен запрос: Content-Length ({content_length} байт) > MAX_UPLOAD_BYTES ({config.MAX_UPLOAD_BYTES} байт)")
            return None, "PAYLOAD_TOO_LARGE"

        boundary = None
        for part in content_type.split(';'):
            part = part.strip()
            if part.startswith('boundary='):
                boundary = part[len('boundary='):].strip('"\'')
                break
        if not boundary or content_length <= 0:
            return None, None

        boundary_bytes = boundary.encode('latin1')
        delimiter = b'--' + boundary_bytes
        delimiter_crlf = b'\r\n--' + boundary_bytes

        tmp_dir = tempfile.mkdtemp(prefix='kvit_upload_')
        pdf_files = []

        remaining = content_length
        total_read = 0
        read_chunk_size = 64 * 1024  # 64 KB буфер чтения

        def read_stream():
            nonlocal remaining, total_read
            while remaining > 0:
                to_read = min(read_chunk_size, remaining)
                chunk = self.rfile.read(to_read)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > config.MAX_UPLOAD_BYTES:
                    logger.warning(f"[Upload] Превышен лимит байт при чтении потока ({total_read} > {config.MAX_UPLOAD_BYTES})")
                    break
                remaining -= len(chunk)
                yield chunk

        stream = read_stream()
        buf = b''

        # 1. Поиск первого разделителя
        while delimiter not in buf:
            try:
                chunk = next(stream)
            except StopIteration:
                break
            buf += chunk

        first_delim_idx = buf.find(delimiter)
        if first_delim_idx < 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None, None

        buf = buf[first_delim_idx + len(delimiter):]

        MAX_HEADER_SIZE = 64 * 1024  # 64 KB максимум на заголовки одной секции (защита от memory exhaustion)

        # 2. Потоковый разбор каждой части
        while True:
            # Если это завершающий разделитель '--'
            if buf.startswith(b'--'):
                break

            # Пропускаем CRLF после разделителя
            if buf.startswith(b'\r\n'):
                buf = buf[2:]
            elif buf.startswith(b'\n'):
                buf = buf[1:]

            # Читаем заголовки секции до '\r\n\r\n' (или '\n\n') с защитой от гигантских заголовков
            while b'\r\n\r\n' not in buf and b'\n\n' not in buf:
                if len(buf) > MAX_HEADER_SIZE:
                    # Превышен лимит размера заголовков (аномальный/вредоносный поток)
                    break
                try:
                    chunk = next(stream)
                except StopIteration:
                    break
                buf += chunk

            header_end = buf.find(b'\r\n\r\n')
            header_len = 4
            if header_end < 0:
                header_end = buf.find(b'\n\n')
                header_len = 2

            if header_end < 0:
                break

            header_bytes = buf[:header_end]
            buf = buf[header_end + header_len:]

            header_text = header_bytes.decode('utf-8', errors='replace')
            m_name = re.search(r'name="([^"]*)"', header_text)
            m_fn = re.search(r'filename="([^"]*)"', header_text)
            field_name = m_name.group(1) if m_name else ''
            file_name = m_fn.group(1) if m_fn else ''

            is_target_file = (field_name == 'pdf' or file_name.lower().endswith('.pdf')) and bool(file_name)

            out_file = None
            tmp_path = None
            base_name = None
            if is_target_file:
                # Санитизация имени файла: защита от Path Traversal, NUL байтов, спецсимволов ОС и абсолютных путей
                cleaned_name = os.path.basename(file_name.replace('\\', '/')).replace('\x00', '').strip()
                cleaned_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cleaned_name).strip(' .')
                base_name = cleaned_name if cleaned_name else f'upload_{len(pdf_files):04d}.pdf'
                tmp_path = os.path.join(tmp_dir, f'{len(pdf_files):06d}_{base_name}')
                try:
                    out_file = open(tmp_path, 'wb')
                except OSError:
                    base_name = f'upload_{len(pdf_files):04d}.pdf'
                    tmp_path = os.path.join(tmp_dir, f'{len(pdf_files):06d}_{base_name}')
                    out_file = open(tmp_path, 'wb')

            # Потоковая запись данных секции на диск до следующего delimiter_crlf
            needle = delimiter_crlf
            needle_len = len(needle)

            while True:
                idx = buf.find(needle)
                if idx >= 0:
                    # Разделитель найден
                    if out_file and idx > 0:
                        out_file.write(buf[:idx])
                    buf = buf[idx + needle_len:]
                    break
                else:
                    # Сбрасываем безопасную часть буфера на диск
                    if len(buf) > needle_len:
                        flush_len = len(buf) - needle_len
                        if out_file:
                            out_file.write(buf[:flush_len])
                        buf = buf[flush_len:]

                    try:
                        chunk = next(stream)
                        buf += chunk
                    except StopIteration:
                        if out_file and buf:
                            out_file.write(buf)
                        buf = b''
                        break

            if out_file:
                out_file.close()
                if os.path.getsize(tmp_path) > 0:
                    pdf_files.append((base_name, tmp_path))
                    if len(pdf_files) >= config.MAX_FILES_PER_REQUEST:
                        logger.warning(f"[Upload] Достигнут лимит файлов в одном запросе ({config.MAX_FILES_PER_REQUEST})")
                        break
                else:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        # Дочитываем оставшийся хвост потока, если есть
        for _ in stream:
            pass

        return tmp_dir, pdf_files

    def _handle_api_upload_batch(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        tmp_dir, pdf_files = self._parse_multipart_to_disk()
        if pdf_files == "PAYLOAD_TOO_LARGE":
            max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            self.send_json({'error': f'Превышен максимальный размер загрузки ({max_mb} MB)'}, 413)
            return

        if tmp_dir is None or not pdf_files:
            self.send_json({'error': 'Файлы не получены'}, 400)
            return

        con = get_db()
        try:
            known_accounts = {row[0] for row in con.execute('SELECT account_number FROM accounts').fetchall()}
            existing_hashes = {h for row in con.execute('SELECT content_hash, file_hash, semantic_hash FROM receipts').fetchall() for h in row if h}
            total_added = 0
            total_skipped = 0
            total_orphan = 0
            total_duplicates = 0
            all_details = []
            all_receipts = []

            for base_name, tmp_path in pdf_files:
                added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(tmp_path, base_name, known_accounts, existing_hashes)
                total_added += added
                total_orphan += orphan
                total_skipped += skipped
                total_duplicates += dups
                status_icon = '✅' if orphan == 0 and skipped == 0 and dups == 0 else '⚠'
                all_details.append(f'📄 {base_name}: {status_icon} +{added}, сирот {orphan}, пропущено {skipped}, дубликатов {dups}')
                all_details.extend(details)
                all_receipts.extend(receipts)

            if total_added > 0 or total_orphan > 0:
                ws_manager.broadcast('upload_batch_completed', {
                    'files_count': len(pdf_files),
                    'added': total_added,
                    'orphan': total_orphan,
                    'duplicates': total_duplicates,
                    'skipped': total_skipped
                })

            self.send_json({
                'success': True,
                'files_count': len(pdf_files),
                'added': total_added,
                'orphan': total_orphan,
                'skipped': total_skipped,
                'duplicates': total_duplicates,
                'details': all_details
            })
        finally:
            con.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _handle_api_stats(self, q: dict):
        period_filter = q.get('period', [''])[0].strip()
        con = get_db()
        try:
            total_accounts = con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
            if period_filter:
                total_receipts = con.execute('SELECT COUNT(*) FROM receipts WHERE period = ?', (period_filter,)).fetchone()[0]
                matched = con.execute('''
                    SELECT COUNT(DISTINCT a.account_number)
                    FROM accounts a
                    JOIN receipts r ON a.account_number = r.account_number
                    WHERE r.period = ?
                ''', (period_filter,)).fetchone()[0]
                orphans = con.execute('''
                    SELECT COUNT(DISTINCT r.account_number)
                    FROM receipts r
                    LEFT JOIN accounts a ON r.account_number = a.account_number
                    WHERE a.account_number IS NULL AND r.period = ?
                ''', (period_filter,)).fetchone()[0]
            else:
                total_receipts = con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
                matched = con.execute('''
                    SELECT COUNT(DISTINCT a.account_number)
                    FROM accounts a
                    JOIN receipts r ON a.account_number = r.account_number
                ''').fetchone()[0]
                orphans = con.execute('''
                    SELECT COUNT(DISTINCT r.account_number)
                    FROM receipts r
                    LEFT JOIN accounts a ON r.account_number = a.account_number
                    WHERE a.account_number IS NULL
                ''').fetchone()[0]

            unmatched = max(0, total_accounts - matched)
            coverage_pct = round(matched / total_accounts * 100, 1) if total_accounts > 0 else 0.0
            periods_rows = con.execute('SELECT DISTINCT period FROM receipts WHERE period IS NOT NULL AND period != "" ORDER BY period DESC').fetchall()
            distinct_periods = [r['period'] for r in periods_rows]
        finally:
            con.close()

        self.send_json({
            'status': 'ok',
            'timestamp': int(time.time()),
            'total_accounts': total_accounts,
            'total_receipts': total_receipts,
            'matched': matched,
            'unmatched': unmatched,
            'orphans': orphans,
            'coverage_pct': coverage_pct,
            'periods': distinct_periods,
            'periods_count': len(distinct_periods),
            'selected_period': period_filter
        }, 200, extra_headers={'Cache-Control': 'no-store, no-cache, must-revalidate'})

    def _handle_api_search(self, q: dict):
        """Обрабатывает AJAX-запросы поиска квитанций по лицевому счету или адресу."""
        account = q.get('account', [''])[0].strip()
        address_query = q.get('address', [''])[0].strip()
        street = q.get('street', [''])[0].strip()
        house = q.get('house', [''])[0].strip()
        flat = q.get('flat', [''])[0].strip()
        period_filter = q.get('period', [''])[0].strip()

        if account:
            account_row = receipt_service.get_account(account)
            if not account_row:
                self.send_json({
                    'status': 'NOT_FOUND',
                    'message': f'Лицевой счёт {account} отсутствует в базе данных.',
                    'account': account,
                    'receipts': []
                }, 200, extra_headers={'Cache-Control': 'no-store'})
                return

            receipts = receipt_service.get_receipts(account, period_filter)
            rec_list = []
            for r in receipts:
                rec_list.append({
                    'period': r['period'],
                    'access_token': r['access_token'],
                    'receipt_url': f"/receipt?token={r['access_token']}",
                    'download_url': f"/download?token={r['access_token']}"
                })

            self.send_json({
                'status': 'EXACT_MATCH',
                'message': 'Квитанция найдена',
                'account': str(account_row['account_number']),
                'address': account_row['address'] or '—',
                'customer_name': account_row['customer_name'] or '',
                'period_filter': period_filter,
                'receipts': rec_list
            }, 200, extra_headers={'Cache-Control': 'no-store'})
            return

        # Поиск по раздельным структурированным полям
        if street or house:
            status, acc_data, prompt_msg = receipt_service.search_by_structured_address(street, house, flat)
        elif address_query:
            status, acc_data, prompt_msg = receipt_service.search_account_by_specific_address(address_query)
        else:
            self.send_json({
                'status': 'EMPTY',
                'message': 'Пожалуйста, введите номер лицевого счёта или адрес.',
                'receipts': []
            }, 200, extra_headers={'Cache-Control': 'no-store'})
            return

        if status == 'EXACT_MATCH' and acc_data:
            acc_num = str(acc_data['account_number'])
            account_row = receipt_service.get_account(acc_num)
            receipts = receipt_service.get_receipts(acc_num, period_filter) if account_row else []
            rec_list = []
            for r in receipts:
                rec_list.append({
                    'period': r['period'],
                    'access_token': r['access_token'],
                    'receipt_url': f"/receipt?token={r['access_token']}",
                    'download_url': f"/download?token={r['access_token']}"
                })

            self.send_json({
                'status': 'EXACT_MATCH',
                'message': prompt_msg or 'Квитанция найдена',
                'account': acc_num,
                'address': acc_data.get('address') or (account_row['address'] if account_row else '—'),
                'customer_name': account_row['customer_name'] if account_row else '',
                'is_corrected': acc_data.get('is_corrected', False),
                'corrected_street': acc_data.get('corrected_street'),
                'original_query': acc_data.get('original_query', address_query or f"{street} {house} {flat}".strip()),
                'period_filter': period_filter,
                'receipts': rec_list
            }, 200, extra_headers={'Cache-Control': 'no-store'})
        else:
            self.send_json({
                'status': status,
                'message': prompt_msg,
                'is_corrected': False,
                'receipts': []
            }, 200, extra_headers={'Cache-Control': 'no-store'})

    def _handle_api_sync_receipts(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        marked_missing, restored_ready, valid = sync_receipts_with_filesystem()
        ws_manager.broadcast('receipts_synced', {
            'marked_missing': marked_missing,
            'restored_ready': restored_ready,
            'valid': valid
        })
        self.send_json({
            'success': True,
            'marked_missing': marked_missing,
            'restored_ready': restored_ready,
            'valid': valid,
            'message': f'Синхронизация завершена (обратимо): помечено missing — {marked_missing}, восстановлено — {restored_ready}, доступно на диске — {valid}'
        })

    def _handle_api_purge_missing_receipts(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        purged_count = purge_missing_receipts()
        ws_manager.broadcast('receipts_purged', {'purged': purged_count})
        self.send_json({
            'success': True,
            'purged': purged_count,
            'message': f'Очистка завершена: удалено {purged_count} записей со статусом missing.'
        })

    def _handle_import_folder(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)
        params = parse_qs(body_bytes.decode('utf-8', errors='replace'))
        csrf_token = params.get('csrf_token', [''])[0].strip()
        folder_path = params.get('folder_path', [''])[0].strip()

        # 0. Проверка CSRF токена
        if not self._verify_csrf(body_csrf=csrf_token):
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_forbidden_page('Недействительный или отсутствующий CSRF-токен.')
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 403)
            return

        # 1. Проверка безопасности пути (whitelist, jail, path traversal)
        is_safe, real_folder_path, error_msg = config.is_safe_import_path(folder_path)
        if not is_safe:
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="err">{error_msg}</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        # 2. Безопасное сканирование с ограничением глубины и максимального числа файлов
        pdf_paths = []
        base_depth = real_folder_path.count(os.sep)

        for root, dirs, files in os.walk(real_folder_path):
            current_depth = root.count(os.sep) - base_depth
            if current_depth >= config.MAX_IMPORT_DEPTH:
                dirs.clear()  # Прекращаем спуск по подпапкам глубже MAX_IMPORT_DEPTH
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_paths.append(os.path.join(root, file))
                    if len(pdf_paths) >= config.MAX_IMPORT_FILES:
                        break
            if len(pdf_paths) >= config.MAX_IMPORT_FILES:
                break

        if not pdf_paths:
            body = render_upload_form(f'<div class="warn">В папке <code>{html.escape(folder_path)}</code> не найдено ни одного .pdf файла.</div>')
            self.send_html(layout(body, 'upload', is_admin=True))
            return

        con = get_db()
        try:
            known_accounts = {row[0] for row in con.execute('SELECT account_number FROM accounts').fetchall()}
            existing_hashes = {h for row in con.execute('SELECT content_hash, file_hash, semantic_hash FROM receipts').fetchall() for h in row if h}
            total_added = 0
            total_skipped = 0
            total_orphan = 0
            total_duplicates = 0
            all_details = []
            all_receipts = []

            for path in pdf_paths:
                base_name = os.path.basename(path)
                added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(path, base_name, known_accounts, existing_hashes)
                total_added += added
                total_orphan += orphan
                total_skipped += skipped
                total_duplicates += dups
                status_icon = '✅' if orphan == 0 and skipped == 0 and dups == 0 else '⚠'
                all_details.append(f'📄 {base_name}: {status_icon} +{added}, сирот {orphan}, пропущено {skipped}, дубликатов {dups}')
                all_details.extend(details)
                all_receipts.extend(receipts)

            if total_added > 0 or total_orphan > 0:
                ws_manager.broadcast('folder_import_completed', {
                    'files_count': len(pdf_paths),
                    'added': total_added,
                    'orphan': total_orphan,
                    'duplicates': total_duplicates,
                    'skipped': total_skipped
                })

            detail_html = '<br>'.join(html.escape(d) for d in all_details)
            cls = 'ok' if total_orphan == 0 and total_skipped == 0 else 'warn'
            msg = f'''<div class="{cls}">
                <b>Импорт из папки завершён: {len(pdf_paths)} PDF-файлов</b><br><br>
                Путь к папке: <code>{html.escape(folder_path)}</code><br>
                Привязано к счетам: <b>{total_added}</b><br>
                Счёта нет в базе: <b>{total_orphan}</b><br>
                Не удалось распознать: <b>{total_skipped}</b><br>
                Дубликатов пропущено: <b>{total_duplicates}</b><br><br>
                <details><summary>Подробности по файлам</summary><br>{detail_html}</details>
            </div>'''
            body = render_upload_form(msg)
            self.send_html(layout(body, 'upload', is_admin=True))
        finally:
            con.close()

    def _handle_upload(self):
        if not self._verify_csrf():
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_forbidden_page('Недействительный или отсутствующий CSRF-токен.')
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 403)
            return

        tmp_dir, pdf_files = self._parse_multipart_to_disk()
        if pdf_files == "PAYLOAD_TOO_LARGE":
            max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="err">❌ Превышен максимальный размер загрузки ({max_mb} MB). Уменьшите объем файлов или загрузите их частями.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 413)
            return

        if tmp_dir is None or not pdf_files:
            body = render_upload_form('<div class="err">Файлы не выбраны или не удалось разобрать запрос.</div>')
            self.send_html(layout(body, 'upload', is_admin=True))
            return

        total_added = 0
        total_skipped = 0
        total_orphan = 0
        total_duplicates = 0
        total_files = len(pdf_files)
        all_details = []
        all_receipts = []

        con = get_db()
        try:
            known_accounts = {row[0] for row in con.execute('SELECT account_number FROM accounts').fetchall()}
            existing_hashes = {h for row in con.execute('SELECT content_hash, file_hash, semantic_hash FROM receipts').fetchall() for h in row if h}

            for file_name, tmp_path in pdf_files:
                added, orphan, skipped, dups, details, receipts = pdf_processor.process_single_pdf(tmp_path, file_name, known_accounts, existing_hashes)
                total_added += added
                total_orphan += orphan
                total_skipped += skipped
                total_duplicates += dups
                status_icon = '✅' if orphan == 0 and skipped == 0 and dups == 0 else '⚠'
                all_details.append(f'📄 {file_name}: {status_icon} привязано {added}, сирот {orphan}, пропущено {skipped}, дубликатов {dups}')
                all_details.extend(details)
                all_receipts.extend(receipts)

            if total_added > 0 or total_orphan > 0:
                ws_manager.broadcast('upload_completed', {
                    'files_count': len(pdf_files),
                    'added': total_added,
                    'orphan': total_orphan,
                    'duplicates': total_duplicates,
                    'skipped': total_skipped
                })
        finally:
            con.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

        detail_html = '<br>'.join(html.escape(d) for d in all_details)
        cls = 'ok' if total_orphan == 0 and total_skipped == 0 else 'warn'
        files_label = f'{total_files} файл' + ('ов' if total_files >= 5 else ('а' if 2 <= total_files <= 4 else ''))
        msg = f'''<div class="{cls}">
            <b>Обработано: {files_label}</b><br><br>
            Привязано к счетам: <b>{total_added}</b><br>
            Счёта нет в базе: <b>{total_orphan}</b><br>
            Не удалось распознать: <b>{total_skipped}</b><br>
            Дубликатов пропущено: <b>{total_duplicates}</b><br><br>
            <details><summary>Подробности по файлам</summary><br>{detail_html}</details>
        </div>'''
        body = render_upload_form(msg)
        self.send_html(layout(body, 'upload', is_admin=True))

    def _serve_pdf(self, path: str, q: dict):
        token = q.get('token', [''])[0].strip()
        fp = receipt_service.get_pdf_by_token(token)
        if not fp:
            if not token or len(token) != 32:
                body = render_forbidden_page()
                self.send_html(layout(body, 'search', is_admin=self._is_admin()), 403)
            else:
                body = render_404_page()
                self.send_html(layout(body, 'search', is_admin=self._is_admin()), 404)
            return

        with open(fp, 'rb') as f:
            data = f.read()

        disp = 'attachment; ' if path == '/download' else 'inline; '
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Content-Disposition', disp + 'filename="receipt.pdf"')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)
