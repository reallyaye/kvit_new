# -*- coding: utf-8 -*-
import os
import re
import sys

import config
from server_handlers.admin_get_handlers import AdminGetHandlerMixin
from services.analytics import stats_service
from services.metrics import alert_service, metrics_collector
from services.receipts import receipt_service
from templates import (
    layout,
    render_address_clarification_prompt,
    render_address_not_found,
    render_search_form,
    render_search_result,
)
from templates.appeals_views import (
    render_appeal_status_page,
    render_appeals_page,
)
from templates.portal_views import DOCUMENTS_REGISTRY, PORTAL_PAGES
from templates.portal_views import render_document as render_portal_document
from templates.portal_views import render_page as render_portal_page
from templates.privacy_views import render_privacy_page
from templates.terms_views import render_terms_page


def __getattr__(name: str):
    if name == 'task_manager':
        srv = sys.modules.get('server')
        if srv and hasattr(srv, 'task_manager'):
            return srv.task_manager
        from services.tasks import task_manager as default_tm
        return default_tm
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

PAGE_ALIASES = {
    'privacy': 'privacy',
    'privacy-policy': 'privacy',
    'terms': 'terms',
    'terms-of-use': 'terms',
    'potreb': 'consumers',
    'potrebitelyam': 'consumers',
    'potrebitel': 'consumers',
    'consumer': 'consumers',
    'contact': 'contacts',
    'kontakty': 'contacts',
    'otchety': 'reports',
    'tarify': 'tarif',
    'zayavka': 'online',
    'zayavki': 'online',
    'notice': 'notices',
    'obyavleniya': 'notices',
    'obyavlenie': 'notices',
    'obyavleniye': 'notices',
    'announcements': 'notices',
    'announcement': 'notices',
    'podstancii': 'load',
    'podstantsii': 'load',
    'zagruzka': 'load',
    'zagruzka-ps': 'load',
    'substations': 'load',
    'connection': 'tu',
    'podklyuchenie': 'tu',
    'network': 'load',
    'grid': 'load',
    'company': 'contacts',
    'about': 'contacts',
    'documents': 'docs',
    'dokumenty': 'docs',
    'outages': 'outages',
    'otklyucheniya': 'outages',
    'appeals': 'appeals',
    'obrascheniya': 'appeals',
    'safety': 'tbquest',
    'dogovor': 'pd_byt_potr',
    'dogovory': 'pd_byt_potr',
    'dogovor-fiz': 'pd_byt_potr',
    'dogovor-fiz-lic': 'pd_byt_potr',
    'publichnyj-dogovor': 'pd_byt_potr',
    'public-contract': 'pd_byt_potr',
    'tipovoj-dogovor': 'pd_byt_potr',
    'pd-byt-potr': 'pd_byt_potr',
    'pd_byt': 'pd_byt_potr',
}


class GetHandlerMixin(AdminGetHandlerMixin):
    """Модульные методы маршрутизации GET-запросов."""

    def _handle_get_api(self, path: str, q: dict) -> bool:
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
            return True
        elif path == '/api/admin/alerts':
            if not self._is_assistant_or_admin():
                self.send_json({'error': 'Unauthorized'}, 401)
                return True
            alerts = alert_service.evaluate_all()
            self.send_json({
                'alerts': alerts,
                'count': len(alerts),
                'has_critical': any(a.get('severity') == 'CRITICAL' for a in alerts),
            }, 200, extra_headers={'Cache-Control': 'no-store'})
            return True
        elif path == '/api/admin/stats':
            if not self._is_admin():
                self.send_json({'error': 'Unauthorized'}, 401)
                return True
            self.send_json(stats_service.get_dashboard_stats(), 200, extra_headers={'Cache-Control': 'no-store'})
            return True
        elif path == '/api/tasks/stats':
            if not self._is_admin():
                self.send_json({'error': 'Unauthorized'}, 401)
                return True
            self.send_json(self.task_manager.get_queue_stats(), 200, extra_headers={'Cache-Control': 'no-store'})
            return True
        elif path == '/api/stats':
            self._handle_api_stats(q)
            return True
        elif path == '/api/tasks':
            self._handle_api_tasks_list()
            return True
        elif path.startswith('/api/tasks/'):
            job_id = path[len('/api/tasks/'):].strip()
            self._handle_api_task_status(job_id)
            return True
        elif path == '/api/search':
            self._handle_api_search(q)
            return True
        return False

    def _handle_get_search(self, path: str, q: dict, is_admin: bool) -> bool:
        if path in ('/kvit', '/kvit/'):
            tab = q.get('tab', ['account'])[0].strip()
            periods = receipt_service.get_distinct_periods()
            body = render_search_form(periods, active_tab=tab)
            self.send_html(layout(body, 'search', is_admin=is_admin))
            return True
        elif path == '/search':
            q_text = q.get('q', [''])[0].strip()
            account = q.get('account', [''])[0].strip()
            address_query = q.get('address', [''])[0].strip()
            street = q.get('street', [''])[0].strip()
            house = q.get('house', [''])[0].strip()
            flat = q.get('flat', [''])[0].strip()
            period_filter = q.get('period', [''])[0].strip()
            verify_code = q.get('verify', q.get('code', q.get('verify_code', [''])))[0].strip()

            if q_text:
                clean_digits = re.sub(r'\D', '', q_text)
                if clean_digits and len(clean_digits) >= 5:
                    account_row = receipt_service.get_account(clean_digits)
                    if account_row:
                        require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
                        is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))
                        receipts = receipt_service.get_receipts(clean_digits, period_filter) if is_verified else []
                        body = render_search_result(
                            clean_digits,
                            period_filter,
                            account_row,
                            receipts,
                            is_verified=is_verified,
                            verification_failed=bool(verify_code and not is_verified),
                            database_updated_at=receipt_service.get_receipts_database_updated_at()
                        )
                        self.send_html(layout(body, 'search', is_admin=is_admin))
                        return True
                from services.portal_search import render_global_search_page, search_portal_content
                results = search_portal_content(q_text)
                self.send_html(render_global_search_page(q_text, results, is_admin=is_admin))
                return True

            if account:
                account_row = receipt_service.get_account(account)
                if account_row:
                    require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
                    is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))
                    receipts = receipt_service.get_receipts(account, period_filter) if is_verified else []
                    body = render_search_result(
                        account,
                        period_filter,
                        account_row,
                        receipts,
                        is_verified=is_verified,
                        verification_failed=bool(verify_code and not is_verified),
                        database_updated_at=receipt_service.get_receipts_database_updated_at()
                    )
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                    return True
                if any(c.isalpha() for c in account):
                    from services.portal_search import render_global_search_page, search_portal_content
                    results = search_portal_content(account)
                    self.send_html(render_global_search_page(account, results, is_admin=is_admin))
                    return True
                body = render_search_result(account, period_filter, None, [])
                self.send_html(layout(body, 'search', is_admin=is_admin))
                return True
            elif street or house:
                if not getattr(config, 'ENABLE_ADDRESS_SEARCH', True) and not is_admin:
                    msg = 'Поиск по адресу отключен в целях защиты персональных данных абонентов. Пожалуйста, используйте поиск по номеру лицевого счёта.'
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_not_found(f"{street} {house} {flat}".strip(), period_filter, msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                    return True
                status, acc_data, prompt_msg = receipt_service.search_by_structured_address(street, house, flat)
                combined_query = f"{street} {house} {flat}".strip()
                if status == 'EXACT_MATCH' and acc_data:
                    acc_num = str(acc_data['account_number'])
                    account_row = receipt_service.get_account(acc_num)
                    require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
                    is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))
                    receipts = receipt_service.get_receipts(acc_num, period_filter) if is_verified and account_row else []
                    body = render_search_result(
                        acc_num,
                        period_filter,
                        account_row,
                        receipts,
                        is_verified=is_verified,
                        verification_failed=bool(verify_code and not is_verified),
                        database_updated_at=receipt_service.get_receipts_database_updated_at()
                    )
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                elif status == 'NOT_FOUND':
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_not_found(combined_query, period_filter, prompt_msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                else:
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_clarification_prompt(combined_query, period_filter, prompt_msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                return True
            elif address_query:
                if not getattr(config, 'ENABLE_ADDRESS_SEARCH', True) and not is_admin:
                    msg = 'Поиск по адресу отключен в целях защиты персональных данных абонентов. Пожалуйста, используйте поиск по номеру лицевого счёта.'
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_not_found(address_query, period_filter, msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                    return True
                status, acc_data, prompt_msg = receipt_service.search_account_by_specific_address(address_query)
                if status == 'EXACT_MATCH' and acc_data:
                    acc_num = str(acc_data['account_number'])
                    account_row = receipt_service.get_account(acc_num)
                    require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
                    is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))
                    receipts = receipt_service.get_receipts(acc_num, period_filter) if is_verified and account_row else []
                    body = render_search_result(
                        acc_num,
                        period_filter,
                        account_row,
                        receipts,
                        is_verified=is_verified,
                        verification_failed=bool(verify_code and not is_verified),
                        database_updated_at=receipt_service.get_receipts_database_updated_at()
                    )
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                elif status == 'NOT_FOUND':
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_not_found(address_query, period_filter, prompt_msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                else:
                    periods = receipt_service.get_distinct_periods()
                    body = render_address_clarification_prompt(address_query, period_filter, prompt_msg, periods)
                    self.send_html(layout(body, 'search', is_admin=is_admin))
                return True
            else:
                self._redirect('/kvit/')
                return True
        return False

    def _handle_get_portal(self, path: str, u, is_admin: bool):
        if path in ('/', '/index.php', '/index.html'):
            self.send_html(render_portal_page('home', is_admin=is_admin))
            return
        elif path == '/appeals':
            self.send_html(render_appeals_page(is_admin=is_admin))
            return
        elif path == '/appeals/status':
            self.send_html(
                render_appeal_status_page(is_admin=is_admin),
                extra_headers={'Cache-Control': 'no-store, no-cache'},
            )
            return
        elif path in ('/privacy', '/privacy-policy', '/privacy.php'):
            self.send_html(render_privacy_page(is_admin=is_admin))
            return
        elif path in ('/terms', '/terms-of-use', '/terms.php'):
            self.send_html(render_terms_page(is_admin=is_admin))
            return

        clean_name = path.strip('/').removesuffix('.php').strip('/')
        clean_name = PAGE_ALIASES.get(clean_name, clean_name)

        if clean_name in PORTAL_PAGES:
            canonical_path = '/' if clean_name == 'home' else f'/{clean_name}'
            if path != canonical_path:
                target = canonical_path + (f'?{u.query}' if u.query else '')
                self.send_response(301)
                self.send_header('Location', target)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_html(render_portal_page(clean_name, is_admin=is_admin))
            return

        doc_key = os.path.basename(path).strip('/')
        if not doc_key.endswith('.php'):
            doc_key += '.php'
        if doc_key in DOCUMENTS_REGISTRY:
            canonical_path = f"/{doc_key.removesuffix('.php')}"
            if path != canonical_path:
                target = canonical_path + (f'?{u.query}' if u.query else '')
                self.send_response(301)
                self.send_header('Location', target)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_html(render_portal_document(DOCUMENTS_REGISTRY[doc_key], is_admin=is_admin, doc_key=doc_key))
            return

        # 404 Not Found
        self.send_html(render_portal_page('404', is_admin=is_admin), 404)
