# -*- coding: utf-8 -*-
import logging
import os
import sys
import tempfile
import time
from urllib.parse import quote

import config
from database import get_db
from services.analytics import stats_service
from services.metrics import metrics_collector
from services.receipts import receipt_service
from templates import layout, render_forbidden_page


def __getattr__(name: str):
    if name == 'task_manager':
        srv = sys.modules.get('server')
        if srv and hasattr(srv, 'task_manager'):
            return srv.task_manager
        from services.tasks import task_manager as default_tm
        return default_tm
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

logger = logging.getLogger('kvit.server.api')
CSRF_INVALID_MSG = 'Недействительный или отсутствующий CSRF-токен.'
START_TIME = time.time()


class ApiHandlerMixin:
    """Обработчики REST API, статистики, фоновых задач, healthchecks и безопасной отдачи PDF."""

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

        try:
            import sys
            server_mod = sys.modules.get('server')
            _get_db = getattr(server_mod, 'get_db', get_db) if server_mod else get_db
            con = _get_db()
            try:
                con.execute('SELECT 1').fetchone()
                checks['database'] = 'ok'
            finally:
                con.close()
        except Exception as e:
            logger.error(f"[Readiness] Ошибка проверки БД: {e}")
            checks['database'] = 'error' if config.IS_PRODUCTION else f'error: {e}'
            all_ok = False
            metrics_collector.record_db_error()

        try:
            receipts_dir = getattr(config, 'RECEIPTS_DIR', 'receipts')
            os.makedirs(receipts_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=receipts_dir, prefix='.readiness_probe_', delete=True) as tf:
                tf.write(b'ok')
                tf.flush()
            checks['storage'] = 'ok'
        except Exception as e:
            logger.error(f"[Readiness] Ошибка хранилища: {e}")
            checks['storage'] = 'error' if config.IS_PRODUCTION else f'error: {e}'
            all_ok = False

        if config.IS_PRODUCTION or getattr(config, 'REDIS_ENABLED', False):
            try:
                if self.task_manager.backend.ping():
                    checks['redis'] = 'ok'
                else:
                    checks['redis'] = 'unavailable'
                    all_ok = False
            except Exception as re:
                logger.error(f"[Readiness] Ошибка проверки Redis: {re}")
                checks['redis'] = 'error' if config.IS_PRODUCTION else f'error: {re}'
                all_ok = False
        else:
            checks['redis'] = 'disabled (in-memory queue active)'

        try:
            q_stats = self.task_manager.get_queue_stats()
            checks['tasks_queue'] = {
                'length': q_stats['queue_length'],
                'active_workers': q_stats['active_workers'],
                'pending': q_stats['pending_count'],
                'processing': q_stats['processing_count']
            }
        except Exception as qe:
            logger.error(f"[Readiness] Ошибка получения статистики очереди: {qe}")
            checks['tasks_queue'] = 'error' if config.IS_PRODUCTION else f'error: {qe}'
            all_ok = False

        try:
            if not getattr(config, 'RUN_EMBEDDED_WORKER', True):
                worker_alive = False
                if hasattr(self.task_manager.backend, '_client') and self.task_manager.backend._client:
                    client = self.task_manager.backend._client
                    if hasattr(client, 'scan_iter'):
                        for _ in client.scan_iter(match='kvit:worker:heartbeat:*', count=10):
                            worker_alive = True
                            break
                    elif hasattr(client, 'scan'):
                        _, matched_keys = client.scan(cursor=0, match='kvit:worker:heartbeat:*', count=10)
                        if matched_keys:
                            worker_alive = True
                checks['workers'] = 'ok' if worker_alive else 'no_active_workers'
                if not worker_alive and config.IS_PRODUCTION:
                    all_ok = False
            else:
                checks['workers'] = f'embedded (active: {checks.get("tasks_queue", {}).get("active_workers", 0)})'
        except Exception as we:
            logger.error(f"[Readiness] Ошибка проверки worker heartbeat: {we}")
            checks['workers'] = 'error'
            if config.IS_PRODUCTION:
                all_ok = False

        status_code = 200 if all_ok else 503
        self.send_json({
            'status': 'ready' if all_ok else 'not_ready',
            'checks': checks,
            'timestamp': time.time()
        }, status_code, {'Cache-Control': 'no-store, no-cache'})

    def _handle_admin_stats_import_nginx(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        params = self._read_form_params()
        if not params:
            return
        csrf_token = params.get('csrf_token', [''])[0].strip()
        if not self._verify_csrf(body_csrf=csrf_token):
            self.send_html(
                layout(render_forbidden_page(CSRF_INVALID_MSG), is_admin=True),
                403,
            )
            return

        candidates = [
            getattr(config, 'NGINX_ACCESS_LOG', ''),
            '/var/log/nginx/access.log',
            os.path.join(os.getcwd(), 'logs', 'nginx_access.log'),
            os.path.join(os.getcwd(), 'access.log'),
        ]
        target_log = None
        for c in candidates:
            if c and os.path.isfile(c):
                target_log = c
                break

        if not target_log:
            self._redirect(f'/admin/stats?err={quote("Файл логов Nginx (/var/log/nginx/access.log) не найден в путях")}')
            return

        count = stats_service.import_from_nginx_log(target_log, max_lines=50000)
        self._redirect(f'/admin/stats?msg={quote(f"Успешно импортировано {count} записей визитов из лога Nginx")}')

    def _handle_api_tasks_list(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return
        tasks = self.task_manager.list_tasks(limit=30)
        self.send_json({'tasks': tasks}, 200, extra_headers={'Cache-Control': 'no-store'})

    def _handle_api_task_status(self, job_id: str):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return
        task = self.task_manager.get_task(job_id)
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
        account = q.get('account', [''])[0].strip()
        address_query = q.get('address', [''])[0].strip()
        street = q.get('street', [''])[0].strip()
        house = q.get('house', [''])[0].strip()
        flat = q.get('flat', [''])[0].strip()
        verify_code = q.get('verify', q.get('code', q.get('verify_code', [''])))[0].strip()
        period_filter = q.get('period', [''])[0].strip()
        is_admin = self._is_admin()

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

            require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
            is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))

            if require_verification and not is_verified:
                msg = 'Неверный номер дома/квартиры для данного лицевого счета.' if verify_code else 'Для доступа к квитанции введите номер дома или квартиры.'
                self.send_json({
                    'status': 'NEED_VERIFICATION',
                    'message': msg,
                    'account': str(account_row['account_number']),
                    'address': receipt_service.mask_address(account_row['address']),
                    'customer_name': '',
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
                    'download_url': f"/download?token={r['access_token']}",
                    'uploaded_at': r.get('uploaded_at')
                })

            self.send_json({
                'status': 'EXACT_MATCH',
                'message': 'Квитанция найдена',
                'account': str(account_row['account_number']),
                'address': account_row['address'] or '—',
                'customer_name': '',
                'period_filter': period_filter,
                'database_updated_at': receipt_service.get_receipts_database_updated_at(),
                'receipts': rec_list
            }, 200, extra_headers={'Cache-Control': 'no-store'})
            return

        if street or house or address_query:
            if not getattr(config, 'ENABLE_ADDRESS_SEARCH', True) and not is_admin:
                self.send_json({
                    'status': 'FORBIDDEN',
                    'message': 'Поиск по адресу отключен в целях защиты персональных данных абонентов. Пожалуйста, используйте поиск по номеру лицевого счёта.',
                    'receipts': []
                }, 403, extra_headers={'Cache-Control': 'no-store'})
                return

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
            require_verification = getattr(config, 'REQUIRE_RECEIPT_VERIFICATION', False)
            is_verified = not require_verification or is_admin or bool(verify_code and receipt_service.verify_account_ownership(account_row, verify_code))
            if not is_verified and account_row:
                msg = 'Неверный проверочный код для данного лицевого счета.' if verify_code else 'Для доступа к квитанции введите номер дома или квартиры.'
                self.send_json({
                    'status': 'NEED_VERIFICATION',
                    'message': msg,
                    'account': acc_num,
                    'address': receipt_service.mask_address(acc_data.get('address') or account_row['address']),
                    'customer_name': '',
                    'receipts': []
                }, 200, extra_headers={'Cache-Control': 'no-store'})
                return

            receipts = receipt_service.get_receipts(acc_num, period_filter) if account_row else []
            rec_list = []
            for r in receipts:
                rec_list.append({
                    'period': r['period'],
                    'access_token': r['access_token'],
                    'receipt_url': f"/receipt?token={r['access_token']}",
                    'download_url': f"/download?token={r['access_token']}",
                    'uploaded_at': r.get('uploaded_at')
                })

            self.send_json({
                'status': 'EXACT_MATCH',
                'message': prompt_msg or 'Квитанция найдена',
                'account': acc_num,
                'address': acc_data.get('address') or (account_row['address'] if account_row else '—'),
                'customer_name': '',
                'is_corrected': acc_data.get('is_corrected', False),
                'corrected_street': acc_data.get('corrected_street'),
                'original_query': acc_data.get('original_query', address_query or f"{street} {house} {flat}".strip()),
                'period_filter': period_filter,
                'database_updated_at': receipt_service.get_receipts_database_updated_at(),
                'receipts': rec_list
            }, 200, extra_headers={'Cache-Control': 'no-store'})
        else:
            self.send_json({
                'status': status,
                'message': prompt_msg,
                'is_corrected': False,
                'receipts': []
            }, 200, extra_headers={'Cache-Control': 'no-store'})

