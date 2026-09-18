# -*- coding: utf-8 -*-
"""
HTTP-сервер и диспетчер маршрутов портала квитанций КРЭК.
Декомпозирован на модульные обработчики: server_handlers.
"""

import logging
import os
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote, urlparse

import config
from config import (
    COOKIE_SECURE,
    CSRF_ENABLED,
    IS_PRODUCTION,
    MAINTENANCE_FLAG_FILE,
    MAINTENANCE_MODE,
    MAX_FORM_BODY_BYTES,
    MAX_LOGIN_BODY_BYTES,
    MAX_UPLOAD_BYTES,
    PROTECTED_PATHS,
    RATE_LIMIT_API,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_SEARCH,
    RATE_LIMIT_UPLOAD,
    RECEIPTS_DIR,
    STATIC_DIR,
    TRUST_PROXY,
    TRUSTED_PROXY_NETWORKS,
    USE_HTTPS,
    WS_GUID,
)
from database import get_db, purge_missing_receipts, sync_receipts_with_filesystem
from server_handlers import (
    ApiHandlerMixin,
    AppealHandlerMixin,
    AuthHandlerMixin,
    BaseHandlerMixin,
    CmsHandlerMixin,
    GetHandlerMixin,
    ReceiptHandlerMixin,
    UploadHandlerMixin,
)
from services.analytics import stats_service
from services.appeals import AppealValidationError, appeal_service
from services.metrics import alert_service, metrics_collector
from services.portal_cms import portal_cms
from services.receipts import receipt_service
from services.reconciliation import reconcile_service
from services.security import auth_service, ip_throttler, rate_limiter
from services.security.request_guards import (
    parse_bounded_form,
    parse_bounded_multipart,
    read_bounded_body,
    send_payload_error,
)
from services.tasks import task_manager
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
from templates.admin_cms_views import (
    render_access_denied_page,
    render_admin_audit_log,
    render_admin_document_editor,
    render_admin_documents_list,
    render_admin_media_gallery,
    render_admin_page_editor,
    render_admin_pages_list,
    render_admin_users,
)
from templates.admin_stats_views import render_admin_stats_dashboard
from templates.appeals_views import (
    render_admin_appeal_detail,
    render_admin_appeals_list,
    render_appeal_status_page,
    render_appeals_page,
)
from templates.locale import set_locale
from templates.portal_views import DOCUMENTS_REGISTRY, PORTAL_PAGES
from templates.portal_views import render_document as render_portal_document
from templates.portal_views import render_page as render_portal_page
from templates.privacy_views import render_privacy_page

logger = logging.getLogger('kvit.server')
KVIT_PATH_PREFIX = '/kvit/'
SW_JS_PATH = '/sw.js'

__all__ = [
    'AppRequestHandler',
    'COOKIE_SECURE',
    'CSRF_ENABLED',
    'DOCUMENTS_REGISTRY',
    'IS_PRODUCTION',
    'KVIT_PATH_PREFIX',
    'MAINTENANCE_FLAG_FILE',
    'MAINTENANCE_MODE',
    'MAX_FORM_BODY_BYTES',
    'MAX_LOGIN_BODY_BYTES',
    'MAX_UPLOAD_BYTES',
    'PORTAL_PAGES',
    'PROTECTED_PATHS',
    'RATE_LIMIT_API',
    'RATE_LIMIT_LOGIN',
    'RATE_LIMIT_SEARCH',
    'RATE_LIMIT_UPLOAD',
    'RECEIPTS_DIR',
    'STATIC_DIR',
    'SW_JS_PATH',
    'TRUST_PROXY',
    'TRUSTED_PROXY_NETWORKS',
    'USE_HTTPS',
    'WS_GUID',
    'AppealValidationError',
    'alert_service',
    'appeal_service',
    'auth_service',
    'get_db',
    'ip_throttler',
    'logger',
    'metrics_collector',
    'parse_bounded_form',
    'parse_bounded_multipart',
    'portal_cms',
    'purge_missing_receipts',
    'rate_limiter',
    'read_bounded_body',
    'receipt_service',
    'reconcile_service',
    'render_404_page',
    'render_access_denied_page',
    'render_address_clarification_prompt',
    'render_address_not_found',
    'render_admin_appeal_detail',
    'render_admin_appeals_list',
    'render_admin_audit_log',
    'render_admin_document_editor',
    'render_admin_documents_list',
    'render_admin_media_gallery',
    'render_admin_page_editor',
    'render_admin_pages_list',
    'render_admin_stats_dashboard',
    'render_admin_users',
    'render_appeal_status_page',
    'render_appeals_page',
    'render_forbidden_page',
    'render_login_form',
    'render_portal_document',
    'render_portal_page',
    'render_privacy_page',
    'render_rate_limit_page',
    'render_reconcile_page',
    'render_search_form',
    'render_search_result',
    'render_throttled_page',
    'render_upload_form',
    'send_payload_error',
    'set_locale',
    'stats_service',
    'sync_receipts_with_filesystem',
    'task_manager',
    'ws_manager',
    'layout',
    'parse_qs',
    'quote',
]


class AppRequestHandler(
    BaseHandlerMixin,
    AuthHandlerMixin,
    AppealHandlerMixin,
    UploadHandlerMixin,
    CmsHandlerMixin,
    ApiHandlerMixin,
    ReceiptHandlerMixin,
    GetHandlerMixin,
    BaseHTTPRequestHandler,
):
    """Главный HTTP-шлюз и роутер приложения."""

    # ────────────────────── HTTP Методы ──────────────────────

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        self.request_locale = 'ru'
        prefixed_locale = False
        for prefix, locale in (('/kk', 'kk'), ('/kz', 'kk'), ('/ru', 'ru')):
            if path == prefix or path.startswith(prefix + '/'):
                self.request_locale = locale
                path = path[len(prefix):] or '/'
                prefixed_locale = True
                break
        if not prefixed_locale:
            try:
                cookies = SimpleCookie()
                cookies.load(self.headers.get('Cookie', ''))
                saved_locale = cookies.get('krec_lang')
                if saved_locale and saved_locale.value in ('ru', 'kk'):
                    self.request_locale = saved_locale.value
            except Exception:
                pass
        set_locale(self.request_locale)
        is_admin = self._is_admin()
        client_ip = self._get_client_ip()

        if path in ('/health', '/healthz', '/api/health'):
            self._handle_health()
            return
        elif path in ('/ready', '/readyz', '/api/ready'):
            self._handle_ready()
            return

        if path == '/ws' and self.headers.get('Upgrade', '').lower() == 'websocket':
            self._handle_websocket()
            return

        if path.startswith(('/css/', '/fonts/', '/images/', '/files/', '/static/')) or path in ('/favicon.ico', '/robots.txt', '/sitemap.xml', '/sw.js', '/manifest.json', '/offline.html', '/maintenance.html'):
            self._serve_static(path)
            return

        maintenance_active = getattr(config, 'MAINTENANCE_MODE', False) or os.path.exists(getattr(config, 'MAINTENANCE_FLAG_FILE', ''))
        if maintenance_active and not is_admin and path not in ('/login', '/static/maintenance.html'):
            if path.startswith('/api/'):
                self.send_json({'error': 'Maintenance', 'message': 'На сайте ведутся плановые технические работы. Доступ будет восстановлен в ближайшее время.'}, 503)
            else:
                self._serve_maintenance_page()
            return

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

            if path in ('/search', '/receipt', '/download'):
                allowed, retry_after, remaining = rate_limiter.is_allowed('search', client_ip, RATE_LIMIT_SEARCH, 60)
                if not allowed:
                    body = render_rate_limit_page(retry_after)
                    self.send_html(layout(body, 'search', is_admin=is_admin), 429, {'Retry-After': str(retry_after)})
                    return

            if not path.startswith(('/api/', '/admin', '/login', '/logout', '/static/')):
                dnt = self.headers.get('DNT') == '1'
                cookie_hdr = self.headers.get('Cookie', '')
                analytics_allowed = False
                if not dnt and cookie_hdr:
                    try:
                        sc = SimpleCookie()
                        sc.load(cookie_hdr)
                        if 'krec_analytics' in sc and sc['krec_analytics'].value == '1':
                            analytics_allowed = True
                    except Exception:
                        analytics_allowed = False
                if analytics_allowed:
                    ua_hdr = self.headers.get('User-Agent', '')
                    stats_service.record_visit(path, client_ip, ua_hdr)

            if self._handle_get_api(path, q):
                return
            if self._handle_get_search(path, q, is_admin):
                return
            if path == '/login':
                cur_user = self._get_current_user()
                if cur_user:
                    u_r = cur_user.get('role')
                    target = '/upload' if u_r == 'operator' else ('/admin/appeals' if u_r == 'assistant' else '/admin/pages')
                    self._redirect(target)
                else:
                    body = render_login_form()
                    self.send_html(layout(body, 'login', is_admin=False))
                return
            if path == '/logout':
                token = self._get_session_token()
                if token:
                    cur_u = auth_service.get_session_user(token)
                    if cur_u:
                        auth_service.log_audit(cur_u.get('username'), client_ip, 'LOGOUT', 'Выход из системы')
                    auth_service.destroy_session(token)
                self._redirect('/', extra_headers={
                    'Set-Cookie': self._get_session_cookie_header('', max_age=0)
                })
                return
            if self._handle_get_admin(path, q, is_admin, client_ip):
                return
            if path in ('/receipt', '/download'):
                self._serve_pdf(path, q)
                return

            self._handle_get_portal(path, u, is_admin)
        finally:
            ip_throttler.release(client_ip)

    def do_POST(self):
        u = urlparse(self.path)
        is_admin = self._is_admin()
        client_ip = self._get_client_ip()

        maintenance_active = getattr(config, 'MAINTENANCE_MODE', False) or os.path.exists(getattr(config, 'MAINTENANCE_FLAG_FILE', ''))
        if maintenance_active and not is_admin and u.path != '/login':
            self.send_json({'error': 'Maintenance', 'message': 'На сайте ведутся плановые технические работы. Прием запросов временно приостановлен.'}, 503)
            return

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
            if u.path == '/login':
                allowed, retry_after, remaining = rate_limiter.is_allowed('login', client_ip, RATE_LIMIT_LOGIN, 60)
                if not allowed:
                    body = render_login_form(f'Слишком много попыток входа. В целях безопасности подождите {retry_after} сек.')
                    self.send_html(layout(body, 'login', is_admin=False), 429, {'Retry-After': str(retry_after)})
                    return
                self._handle_login()
                return

            if u.path in ('/upload', '/import-folder', '/api/upload-batch', '/api/upload-accounts'):
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

            if u.path == '/api/appeals':
                allowed, retry_after, remaining = rate_limiter.is_allowed(
                    'appeals', client_ip, config.RATE_LIMIT_APPEALS, 3600
                )
                if not allowed:
                    self.send_json({
                        'error': 'Too Many Requests',
                        'message': 'Превышен лимит отправки обращений. Попробуйте позднее.',
                        'retry_after': retry_after,
                    }, 429, {'Retry-After': str(retry_after)})
                    return

            if u.path == '/api/appeals/status':
                allowed, retry_after, remaining = rate_limiter.is_allowed(
                    'appeals_status', client_ip, 10, 60
                )
                if not allowed:
                    self.send_json({
                        'error': 'Too Many Requests',
                        'message': 'Слишком много попыток. Попробуйте через минуту.',
                        'retry_after': retry_after,
                    }, 429, {'Retry-After': str(retry_after), 'Cache-Control': 'no-store'})
                    return

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

            if u.path == '/upload':
                if not self._is_operator_or_admin():
                    self._redirect('/login')
                    return
                self._handle_upload()
            elif u.path == '/import-folder':
                if not self._is_operator_or_admin():
                    self._redirect('/login')
                    return
                self._handle_import_folder()
            elif u.path == '/admin/users/create':
                self._handle_admin_users_create()
            elif u.path == '/admin/users/delete':
                self._handle_admin_users_delete()
            elif u.path == '/admin/pages/save':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для редактирования страниц'), 403)
                    return
                self._handle_admin_pages_save()
            elif u.path == '/admin/pages/delete':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для удаления страниц'), 403)
                    return
                self._handle_admin_pages_delete()
            elif u.path == '/admin/media/upload':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для загрузки медиа'), 403)
                    return
                self._handle_admin_media_upload()
            elif u.path == '/admin/media/delete':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для удаления медиа'), 403)
                    return
                self._handle_admin_media_delete()
            elif u.path == '/admin/documents/save':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для изменения реестра документов'), 403)
                    return
                self._handle_admin_documents_save()
            elif u.path == '/admin/documents/delete':
                if not self._is_admin():
                    self.send_html(render_forbidden_page('У вас нет прав администратора для удаления документов'), 403)
                    return
                self._handle_admin_documents_delete()
            elif u.path == '/admin/appeals/update':
                self._handle_admin_appeal_update()
            elif u.path == '/admin/stats/import-nginx':
                self._handle_admin_stats_import_nginx()
            elif u.path == '/api/appeals':
                self._handle_appeal_submit()
            elif u.path == '/api/appeals/status':
                self._handle_appeal_status()
            elif u.path == '/api/upload-batch':
                self._handle_api_upload_batch()
            elif u.path == '/api/upload-accounts':
                self._handle_api_upload_accounts()
            elif u.path == '/api/receipts/delete':
                self._handle_api_delete_receipt()
            elif u.path == '/api/sync-receipts':
                self._handle_api_sync_receipts()
            elif u.path == '/api/purge-missing-receipts':
                self._handle_api_purge_missing_receipts()
            else:
                self.send_html(layout(render_forbidden_page('404 Not Found'), is_admin=is_admin), 404)
        finally:
            ip_throttler.release(client_ip)
