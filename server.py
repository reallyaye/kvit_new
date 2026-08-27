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
from config import PROTECTED_PATHS, RATE_LIMIT_API, RATE_LIMIT_LOGIN, RATE_LIMIT_SEARCH, RATE_LIMIT_UPLOAD, WS_GUID
from database import get_db, purge_missing_receipts, sync_receipts_with_filesystem
from logger import logger
from services.metrics import metrics_collector
from services.pdf import pdf_processor
from services.receipts import receipt_service
from services.reconciliation import reconcile_service
from services.security import auth_service, ip_throttler, rate_limiter
from services.websocket import ws_manager
from services.portal_cms import portal_cms
from services.tasks import task_manager
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
from templates.admin_cms_views import (
    render_admin_document_editor,
    render_admin_documents_list,
    render_admin_media_gallery,
    render_admin_page_editor,
    render_admin_pages_list,
)
from templates.portal_views import PORTAL_PAGES, DOCUMENTS_REGISTRY, render_page as render_portal_page, render_document as render_portal_document

START_TIME = time.time()
SW_JS_PATH = '/sw.js'
KVIT_PATH_PREFIX = '/kvit/'
BOUNDARY_PREFIX = 'boundary='
CSRF_INVALID_MSG = 'Недействительный или отсутствующий CSRF-токен.'


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
        """Внедрение обязательных заголовков безопасности и идентификатора инстанса."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
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

    def _handle_health(self):
        """Liveness probe: мгновенная проверка работоспособности HTTP-сервера."""
        self.send_json({
            'status': 'ok',
            'timestamp': time.time(),
            'uptime_seconds': round(time.time() - START_TIME, 2),
            'service': 'kvit-service'
        }, 200, {'Cache-Control': 'no-store, no-cache'})

    def _handle_ready(self):
        """Readiness probe: проверка готовности зависимостей (база данных, хранилище файлов, Redis, очередь)."""
        checks = {}
        all_ok = True

        # 1. Проверка доступности БД
        try:
            con = get_db()
            try:
                con.execute('SELECT 1').fetchone()
                checks['database'] = 'ok'
            finally:
                con.close()
        except Exception as e:
            checks['database'] = f'error: {e}'
            all_ok = False
            metrics_collector.record_db_error()

        # 2. Проверка доступности каталога квитанций
        try:
            receipts_dir = getattr(config, 'RECEIPTS_DIR', 'receipts')
            if os.path.exists(receipts_dir) and os.path.isdir(receipts_dir):
                checks['storage'] = 'ok'
            else:
                os.makedirs(receipts_dir, exist_ok=True)
                checks['storage'] = 'created'
        except Exception as e:
            checks['storage'] = f'error: {e}'
            all_ok = False

        # 3. Проверка Redis (если включен)
        if getattr(config, 'REDIS_ENABLED', False):
            try:
                if task_manager.backend.ping():
                    checks['redis'] = 'ok'
                else:
                    checks['redis'] = 'unavailable'
                    all_ok = False
            except Exception as re:
                checks['redis'] = f'error: {re}'
                all_ok = False
        else:
            checks['redis'] = 'disabled (in-memory queue active)'

        # 4. Проверка состояния очереди и воркеров
        try:
            q_stats = task_manager.get_queue_stats()
            checks['tasks_queue'] = {
                'length': q_stats['queue_length'],
                'active_workers': q_stats['active_workers'],
                'pending': q_stats['pending_count'],
                'processing': q_stats['processing_count']
            }
        except Exception as qe:
            checks['tasks_queue'] = f'error: {qe}'

        status_code = 200 if all_ok else 503
        self.send_json({
            'status': 'ready' if all_ok else 'not_ready',
            'checks': checks,
            'timestamp': time.time()
        }, status_code, {'Cache-Control': 'no-store, no-cache'})

    # ────────────────────── GET ──────────────────────

    def do_HEAD(self):
        """Обрабатывает HTTP HEAD запросы идентично GET для healthcheck и curl -I."""
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        is_admin = self._is_admin()
        client_ip = self._get_client_ip()

        # Health & Readiness probes (Liveness / Readiness для k8s, docker, load balancers)
        if path in ('/health', '/healthz', '/api/health'):
            self._handle_health()
            return
        elif path in ('/ready', '/readyz', '/api/ready'):
            self._handle_ready()
            return

        # WebSocket перехват
        if path == '/ws' and self.headers.get('Upgrade', '').lower() == 'websocket':
            self._handle_websocket()
            return

        # Статические файлы (CSS, JS, изображения, PDF, favicon, robots, sitemap, PWA)
        if path.startswith(('/css/', '/images/', '/files/')) or path in ('/favicon.ico', '/robots.txt', '/sitemap.xml', '/sw.js', '/manifest.json', '/offline.html'):
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
            if path in ('/api/metrics', '/metrics'):
                if 'text' in q or self.headers.get('Accept', '').startswith('text/plain'):
                    body_bytes = metrics_collector.to_prometheus().encode('utf-8')
                    self.send_response(200)
                    self._send_security_headers()
                    self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
                    self.send_header('Content-Length', str(len(body_bytes)))
                    self.end_headers()
                    self.wfile.write(body_bytes)
                else:
                    self.send_json(metrics_collector.to_dict(), 200, extra_headers={'Cache-Control': 'no-store'})
                return
            elif path == '/api/tasks/stats':
                if not self._is_admin():
                    self.send_json({'error': 'Unauthorized'}, 401)
                    return
                self.send_json(task_manager.get_queue_stats(), 200, extra_headers={'Cache-Control': 'no-store'})
                return
            elif path == '/api/stats':
                self._handle_api_stats(q)
                return
            elif path == '/api/tasks':
                self._handle_api_tasks_list()
                return
            elif path.startswith('/api/tasks/'):
                job_id = path[len('/api/tasks/'):].strip()
                self._handle_api_task_status(job_id)
                return
            elif path == '/api/search':
                self._handle_api_search(q)
                return
            elif path in ('/kvit', KVIT_PATH_PREFIX):
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
                msg = q.get('msg', [None])[0]
                err = q.get('err', [None])[0]

                if path in ('/admin', '/admin/pages'):
                    pages = portal_cms.get_all_pages()
                    body = render_admin_pages_list(pages, csrf_tok, message=msg, error=err)
                    self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/pages/edit':
                    slug = q.get('slug', [''])[0]
                    page_data = portal_cms.get_page(slug) or {'title': slug, 'html': ''}
                    media_files = portal_cms.list_media_files()
                    body = render_admin_page_editor(slug, page_data, csrf_tok, media_files, is_new=False, message=msg, error=err)
                    self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/pages/new':
                    media_files = portal_cms.list_media_files()
                    body = render_admin_page_editor('', {'title': '', 'html': ''}, csrf_tok, media_files, is_new=True, message=msg, error=err)
                    self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/media':
                    media_files = portal_cms.list_media_files()
                    body = render_admin_media_gallery(media_files, csrf_tok, message=msg, error=err)
                    self.send_html(layout(body, 'media', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/documents':
                    docs = portal_cms.get_all_documents()
                    body = render_admin_documents_list(docs, csrf_tok, message=msg, error=err)
                    self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/documents/edit':
                    key = q.get('key', [''])[0]
                    doc_data = portal_cms.get_document(key) or {}
                    body = render_admin_document_editor(key, doc_data, csrf_tok, is_new=False, message=msg, error=err)
                    self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
                elif path == '/admin/documents/new':
                    body = render_admin_document_editor('', {}, csrf_tok, is_new=True, message=msg, error=err)
                    self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
                elif path == '/upload':
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
                self.send_html(render_portal_page('home', is_admin=is_admin))
            else:
                clean_name = path.strip('/').removesuffix('.php').strip('/')
                if clean_name in PORTAL_PAGES:
                    self.send_html(render_portal_page(clean_name, is_admin=is_admin))
                    return

                doc_key = os.path.basename(path).strip('/')
                if not doc_key.endswith('.php'):
                    doc_key += '.php'
                if doc_key in DOCUMENTS_REGISTRY:
                    self.send_html(render_portal_document(DOCUMENTS_REGISTRY[doc_key], is_admin=is_admin, doc_key=doc_key))
                    return

                # 404 Not Found
                self.send_html(render_portal_page('404', is_admin=is_admin), 404)
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

            # 3. Rate Limit для загрузки файлов (защита от перегрузки очереди)
            if u.path in ('/upload', '/import-folder', '/api/upload-batch'):
                allowed, retry_after, remaining = rate_limiter.is_allowed('upload', client_ip, RATE_LIMIT_UPLOAD, 60)
                if not allowed:
                    if u.path.startswith('/api/'):
                        self.send_json({
                            'error': 'Too Many Requests',
                            'message': f'Превышен лимит операций загрузки. Пожалуйста, подождите {retry_after} сек.',
                            'retry_after': retry_after
                        }, 429, {'Retry-After': str(retry_after)})
                    else:
                        csrf_tok = auth_service.get_csrf_token(self._get_session_token()) if is_admin else ''
                        body = render_rate_limit_page(retry_after)
                        self.send_html(layout(body, 'upload', is_admin=is_admin, csrf_token=csrf_tok), 429, {'Retry-After': str(retry_after)})
                    return

            # 4. Rate Limit для API эндпоинтов (POST)
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
            elif u.path == '/admin/pages/save':
                self._handle_admin_pages_save()
            elif u.path == '/admin/pages/delete':
                self._handle_admin_pages_delete()
            elif u.path == '/admin/media/upload':
                self._handle_admin_media_upload()
            elif u.path == '/admin/media/delete':
                self._handle_admin_media_delete()
            elif u.path == '/admin/documents/save':
                self._handle_admin_documents_save()
            elif u.path == '/admin/documents/delete':
                self._handle_admin_documents_delete()
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
            if part.startswith(BOUNDARY_PREFIX):
                boundary = part[len(BOUNDARY_PREFIX):].strip('"\'')
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

        task = task_manager.submit_pdf_job(
            files=pdf_files,
            source='api_batch',
            spool_dir=tmp_dir
        )

        self.send_json({
            'success': True,
            'job_id': task.job_id,
            'status': task.status,
            'files_count': len(pdf_files),
            'status_url': f'/api/tasks/{task.job_id}',
            'message': 'Файлы успешно приняты в очередь фоновой обработки.'
        }, 202)

    def _handle_api_tasks_list(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return
        tasks = task_manager.list_tasks(limit=30)
        self.send_json({'tasks': tasks}, 200, extra_headers={'Cache-Control': 'no-store'})

    def _handle_api_task_status(self, job_id: str):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return
        task = task_manager.get_task(job_id)
        if not task:
            self.send_json({'error': 'Task not found', 'job_id': job_id}, 404)
            return
        self.send_json(task.to_dict(), 200, extra_headers={'Cache-Control': 'no-store'})

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
            periods_rows = con.execute("SELECT DISTINCT period FROM receipts WHERE period IS NOT NULL AND period != '' ORDER BY period DESC").fetchall()
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
            body = render_forbidden_page(CSRF_INVALID_MSG)
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
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="warn">В папке <code>{html.escape(folder_path)}</code> не найдено ни одного .pdf файла.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        files = [(os.path.basename(p), p) for p in pdf_paths]
        task = task_manager.submit_pdf_job(
            files=files,
            source='folder_import',
            meta={'folder_path': folder_path}
        )

        msg = f'''<div class="ok">
            <b>Импорт из папки передан в фоновую обработку: {len(pdf_paths)} PDF-файлов</b><br><br>
            Идентификатор задачи: <code>{task.job_id}</code><br>
            Путь к папке: <code>{html.escape(folder_path)}</code><br><br>
            <i>Обработка выполняется в фоновом режиме без блокировки сервера. Статус обновляется автоматически.</i>
        </div>'''
        csrf_tok = auth_service.get_csrf_token(self._get_session_token())
        body = render_upload_form(msg, csrf_token=csrf_tok, active_job_id=task.job_id)
        self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))

    def _handle_upload(self):
        if not self._verify_csrf():
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_forbidden_page(CSRF_INVALID_MSG)
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
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form('<div class="err">Файлы не выбраны или не удалось разобрать запрос.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        task = task_manager.submit_pdf_job(
            files=pdf_files,
            source='web_upload',
            spool_dir=tmp_dir
        )

        total_files = len(pdf_files)
        files_label = f'{total_files} файл' + ('ов' if total_files >= 5 else ('а' if 2 <= total_files <= 4 else ''))
        msg = f'''<div class="ok">
            <b>Загрузка успешно принята в фоновую обработку: {files_label}</b><br><br>
            Идентификатор задачи: <code>{task.job_id}</code><br><br>
            <i>Файлы обрабатываются в фоновом режиме. Вы можете следить за прогрессом или закрыть страницу.</i>
        </div>'''
        csrf_tok = auth_service.get_csrf_token(self._get_session_token())
        body = render_upload_form(msg, csrf_token=csrf_tok, active_job_id=task.job_id)
        self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))

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

        disp = 'attachment; ' if path == '/download' else 'inline; '
        filename = os.path.basename(fp)

        # 1. Nginx X-Accel-Redirect (нулевое использование CPU/RAM Python для передачи файла)
        if getattr(config, 'ENABLE_X_ACCEL_REDIRECT', False):
            try:
                rel_path = os.path.relpath(fp, config.RECEIPTS_DIR).replace('\\', '/')
            except ValueError:
                rel_path = filename
            x_accel_uri = f"{getattr(config, 'X_ACCEL_PREFIX', '/internal_receipts/')}{rel_path}"

            self.send_response(200)
            self._send_security_headers()
            self.send_header('X-Accel-Redirect', x_accel_uri)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition', f'{disp}filename="{filename}"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return

        # 2. Потоковая передача фиксированными блоками 64 KB без чтения файла целиком в память
        try:
            file_size = os.path.getsize(fp)
            self.send_response(200)
            self._send_security_headers()
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Length', str(file_size))
            self.send_header('Content-Disposition', f'{disp}filename="{filename}"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

            with open(fp, 'rb') as f:
                shutil.copyfileobj(f, self.wfile, length=65536)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.error(f"[Server] Ошибка при потоковой отдаче PDF ({fp}): {e}")


    # ────────────────────── CMS Обработчики ──────────────────────

    def _read_form_params(self) -> dict:
        """Считывает и декодирует application/x-www-form-urlencoded параметры формы."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            return parse_qs(data.decode('utf-8', errors='replace'))
        except Exception:
            return {}

    def _parse_multipart_fields_and_files(self):
        """
        Разбирает multipart/form-data на текстовые поля и список файлов:
        Возвращает: (fields: dict, files: list of (field_name, filename, bytes))
        """
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > config.MAX_UPLOAD_BYTES:
            return {}, []

        boundary = None
        for part in content_type.split(';'):
            part = part.strip()
            if part.startswith('boundary='):
                boundary = part[len('boundary='):].strip('"\'')
                break
        if not boundary or content_length <= 0:
            return {}, []

        data = self.rfile.read(content_length)
        boundary_bytes = boundary.encode('latin1')
        parts = data.split(b'--' + boundary_bytes)

        fields = {}
        files = []

        for part in parts:
            if not part or part == b'--\r\n' or part == b'--\r\n\r\n' or part == b'--':
                continue
            if part.startswith(b'\r\n'):
                part = part[2:]
            if part.endswith(b'\r\n'):
                part = part[:-2]

            hdr_end = part.find(b'\r\n\r\n')
            if hdr_end < 0:
                hdr_end = part.find(b'\n\n')
                hdr_len = 2
            else:
                hdr_len = 4
            if hdr_end < 0:
                continue

            header_bytes = part[:hdr_end]
            body_bytes = part[hdr_end + hdr_len:]
            header_text = header_bytes.decode('utf-8', errors='replace')

            m_name = re.search(r'name="([^"]*)"', header_text)
            m_fn = re.search(r'filename="([^"]*)"', header_text)
            f_name = m_name.group(1) if m_name else ''
            f_filename = m_fn.group(1) if m_fn else ''

            if f_filename:
                files.append((f_name, f_filename, body_bytes))
            elif f_name:
                val_text = body_bytes.decode('utf-8', errors='replace')
                if f_name not in fields:
                    fields[f_name] = []
                fields[f_name].append(val_text)

        return fields, files

    def _handle_admin_pages_save(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        slug = params.get('slug', [''])[0]
        title = params.get('title', [''])[0]
        html_content = params.get('html', [''])[0]
        ok, saved_slug = portal_cms.save_page(slug, title, html_content)
        if ok:
            import urllib.parse
            msg = urllib.parse.quote('Страница успешно сохранена.')
            self._redirect(f'/admin/pages/edit?slug={saved_slug}&msg={msg}')
        else:
            import urllib.parse
            err = urllib.parse.quote('Ошибка сохранения страницы.')
            self._redirect(f'/admin/pages?err={err}')

    def _handle_admin_pages_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        slug = params.get('slug', [''])[0]
        ok, msg = portal_cms.delete_page(slug)
        import urllib.parse
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/pages?{param_name}={urllib.parse.quote(msg)}')

    def _handle_admin_media_upload(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        fields, files = self._parse_multipart_fields_and_files()
        csrf_token = fields.get('csrf_token', [''])[0] if fields else ''
        if not self._verify_csrf(csrf_token):
            if 'ajax' in self.path:
                self.send_json({'ok': False, 'error': 'Недействительный CSRF-токен.'}, 403)
            else:
                self.send_html(layout(render_forbidden_page('Недействительный CSRF-токен.'), is_admin=True), 403)
            return

        is_ajax = 'ajax' in self.path
        if not files:
            if is_ajax:
                self.send_json({'ok': False, 'error': 'Файл не выбран.'}, 400)
            else:
                import urllib.parse
                self._redirect('/admin/media?err=' + urllib.parse.quote('Файл не выбран.'))
            return

        _, orig_filename, file_bytes = files[0]
        ok, file_info, msg = portal_cms.save_media_file(orig_filename, file_bytes)
        if is_ajax:
            self.send_json({'ok': ok, 'file': file_info, 'error': '' if ok else msg})
        else:
            import urllib.parse
            param = 'msg' if ok else 'err'
            self._redirect(f'/admin/media?{param}={urllib.parse.quote(msg)}')

    def _handle_admin_media_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        filename = params.get('filename', [''])[0]
        ok, msg = portal_cms.delete_media_file(filename)
        import urllib.parse
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/media?{param_name}={urllib.parse.quote(msg)}')

    def _handle_admin_documents_save(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        key = params.get('key', [''])[0]
        title = params.get('title', [''])[0]
        cat = params.get('category', ['other'])[0]
        date_text = params.get('date_text', [''])[0]
        files = [f.strip() for f in params.get('files', [''])[0].split('\n') if f.strip()]
        iframes = [f.strip() for f in params.get('iframes', [''])[0].split('\n') if f.strip()]
        doc_data = {
            'title': title,
            'category': cat,
            'date_text': date_text,
            'files': files,
            'iframes': iframes
        }
        ok, saved_key = portal_cms.save_document(key, doc_data)
        import urllib.parse
        if ok:
            msg = urllib.parse.quote('Документ успешно сохранен.')
            self._redirect(f'/admin/documents?msg={msg}')
        else:
            err = urllib.parse.quote('Ошибка сохранения документа.')
            self._redirect(f'/admin/documents?err={err}')

    def _handle_admin_documents_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        key = params.get('key', [''])[0]
        ok, msg = portal_cms.delete_document(key)
        import urllib.parse
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/documents?{param_name}={urllib.parse.quote(msg)}')
