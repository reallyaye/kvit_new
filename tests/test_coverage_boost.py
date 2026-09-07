# -*- coding: utf-8 -*-
"""
tests/test_coverage_boost.py: Комплексный набор тестов для достижения целевого покрытия 80%+:
1. Рендеринг всех шаблонов (reconcile_views, search_views, admin_cms_views, auth_views, portal_views).
2. TelegramClient: mock-тесты сетевых вызовов (sendMessage, sendDocument, getUpdates, downloadFile, getMe, editMessageText).
3. gRPC Servicers (GetAccount, GetReceipts, GetDistinctPeriods, GetSystemStats, StreamReceiptPDF, GetReconcileSummary).
4. MemoryTaskQueueBackend & RedisTaskQueueBackend (Push, Pop, ACK, NACK, Reclaim, Locks, DLQ).
5. AppRequestHandler в server.py (do_GET, do_POST, do_HEAD, static, search, API, Admin CMS CRUD).
"""

import io
import json
import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from database import get_db

# ────────────────────── 1. Тесты шаблонов: reconcile_views ──────────────────────

def test_reconcile_views_render_all_filters():
    from templates.reconcile_views import render_reconcile_page

    base_data = {
        'filt': 'all',
        'period_filter': '08.2026',
        'all_periods': [{'period': '08.2026'}, {'period': '07.2026'}],
        'total_accounts': 100,
        'total_receipts': 85,
        'matched': 80,
        'unmatched': 20,
        'orphans': 5,
        'list_count': 100,
        'rows': [
            {'account_number': '800101', 'customer_name': 'Тест 1', 'address': 'ул. Мира 1', 'period': '08.2026', 'pdf_file': '80/01/f1.pdf'},
            {'account_number': '800102', 'customer_name': 'Тест 2', 'address': 'ул. Мира 2', 'period': None, 'pdf_file': None},
        ],
        'page_num': 1,
        'per_page': 20,
    }

    # 1. Фильтр 'all'
    html_all = render_reconcile_page(base_data)
    assert 'Сверка' in html_all
    assert '800101' in html_all
    assert '800102' in html_all

    # 2. Фильтр 'orphans'
    base_data_orphans = dict(base_data)
    base_data_orphans['filt'] = 'orphans'
    base_data_orphans['rows'] = [
        {'account_number': '999999', 'period': '08.2026', 'pdf_file': '99/99/orphan.pdf'}
    ]
    html_orphans = render_reconcile_page(base_data_orphans)
    assert 'Нет в базе' in html_orphans
    assert '999999' in html_orphans

    # 3. Фильтр 'orphans' пустой
    base_data_empty_orphans = dict(base_data_orphans)
    base_data_empty_orphans['rows'] = []
    html_empty_orphans = render_reconcile_page(base_data_empty_orphans)
    assert 'Все квитанции привязаны к лицевым счетам' in html_empty_orphans

    # 4. Пагинация
    base_data_pag = dict(base_data)
    base_data_pag['list_count'] = 500
    base_data_pag['page_num'] = 12
    base_data_pag['per_page'] = 20
    html_pag = render_reconcile_page(base_data_pag)
    assert 'pagination' in html_pag


# ────────────────────── 2. Тесты шаблонов: search_views & auth_views ──────────

def test_search_views_full_suite():
    from templates.auth_views import (
        render_404_page,
        render_forbidden_page,
        render_login_form,
        render_rate_limit_page,
        render_throttled_page,
    )
    from templates.search_views import (
        render_address_clarification_prompt,
        render_address_not_found,
        render_address_search_results,
        render_search_form,
        render_search_result,
    )

    f1 = render_search_form([{'period': '08.2026'}], active_tab='account')
    assert 'Получение квитанции' in f1
    assert '08.2026' in f1

    f2 = render_search_form([], active_tab='address')
    assert 'Получение квитанции' in f2

    acc = {'account_number': '800100', 'address': 'ул. Ленина 5', 'customer_name': 'Иванов'}
    r1 = [{'period': '08.2026', 'access_token': 'tok1'}]
    r2 = [{'period': '08.2026', 'access_token': 'tok1'}, {'period': '07.2026', 'access_token': 'tok2'}]

    res_single = render_search_result('800100', '', acc, r1, is_verified=True)
    assert 'Квитанция найдена' in res_single
    assert 'tok1' in res_single

    res_multi = render_search_result('800100', '', acc, r2, is_verified=True)
    assert 'Квитанции найдены' in res_multi
    assert 'tok2' in res_multi

    res_unverified = render_search_result('800100', '', acc, r1, is_verified=False, verification_failed=True)
    assert 'Подтверждение доступа' in res_unverified
    assert 'Неверный номер дома' in res_unverified

    res_none = render_search_result('800100', '01.2020', acc, [], is_verified=True)
    assert 'Квитанция за период не найдена' in res_none

    res_empty = render_search_result('800100', '', acc, [], is_verified=True)
    assert 'Квитанции не найдены' in res_empty

    assert '404' in render_404_page()
    assert 'устаревшая' in render_forbidden_page()
    assert '45' in render_rate_limit_page(45)
    assert '30' in render_throttled_page(30)
    assert 'Неверный' in render_login_form('Неверный')
    assert 'Уточните дом' in render_address_clarification_prompt('Абая', '', 'Уточните дом', [{'period': '08.2026'}])
    assert 'Не найдено' in render_address_not_found('Неизвестная 1', '', 'Не найдено', [{'period': '08.2026'}])
    assert 'Найдена 1 запись' in render_address_search_results('Абая', '', [{'account_number': '123'}])


# ────────────────────── 3. Тесты шаблонов: admin_cms_views ───────────────────

def test_admin_cms_views_render():
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

    pages = [
        {'slug': 'home', 'title': 'Главная', 'nav_url': '/', 'is_main_nav': True, 'content_length': 100, 'snippet': 'Добро пожаловать'},
        {'slug': 'custom', 'title': 'Новая страница', 'nav_url': '/custom', 'is_main_nav': False, 'content_length': 200, 'snippet': 'Текст'}
    ]
    p_list = render_admin_pages_list(pages, csrf_token='csrf123', message='Успешно', error='Ошибка')
    assert 'Главная' in p_list
    assert 'Новая страница' in p_list

    p_edit = render_admin_page_editor('custom', pages[1], csrf_token='csrf123', media_files=[])
    assert 'Редактирование страницы' in p_edit

    docs = [
        {'key': 'doc1', 'title': 'Отчет 2026', 'date_text': 'Сентябрь 2026', 'category': 'reports', 'files': ['f1.pdf']}
    ]
    d_list = render_admin_documents_list(docs, csrf_token='csrf123')
    assert 'Отчет 2026' in d_list

    d_edit = render_admin_document_editor('doc1', docs[0], csrf_token='csrf123')
    assert 'Редактирование документа' in d_edit

    images = [{
        'filename': 'img1.png',
        'url': '/images/uploads/img1.png',
        'size_formatted': '45.2 KB',
        'modified_formatted': '01.09.2026',
        'type': 'image',
        'ext': 'png'
    }]
    m_gal = render_admin_media_gallery(images, csrf_token='csrf123')
    assert 'img1.png' in m_gal

    users = [{'id': 1, 'username': 'admin', 'full_name': 'Администратор', 'role': 'admin', 'is_active': 1, 'created_at': 1700000000, 'last_login_at': 1700000000}]
    logs = [{'id': 1, 'username': 'admin', 'ip_address': '127.0.0.1', 'action': 'LOGIN', 'details': 'Вход', 'created_at': 1700000000}]
    u_view = render_admin_users(users, logs, csrf_token='csrf123', current_username='admin', current_role='admin')
    assert 'Администратор' in u_view

    stats = {'total_logs': 10, 'actions': {'LOGIN': 5}, 'users': {'admin': 10}}
    audit_v = render_admin_audit_log(logs, stats, filters={}, csrf_token='csrf123')
    assert 'Журнал действий' in audit_v

    denied = render_access_denied_page('operator', 'user1')
    assert 'Доступ ограничен' in denied


# ────────────────────── 4. Тесты TelegramClient (urllib mock) ────────────────

def test_telegram_client_api_methods():
    from services.telegram_bot.telegram_client import TelegramAPIError, TelegramClient

    client = TelegramClient("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

    # Mock успешного JSON ответа
    def mock_urlopen_success(req, *args, **kwargs):
        resp_data = {"ok": True, "result": {"message_id": 42, "text": "OK", "id": 12345}}
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [json.dumps(resp_data).encode('utf-8'), b""]
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch('urllib.request.urlopen', side_effect=mock_urlopen_success):
        assert client.get_me()['id'] == 12345
        assert client.send_message(chat_id=1001, text="Привет", reply_to_message_id=40)['message_id'] == 42
        assert client.get_file("file_id_123")['message_id'] == 42
        assert client.get_updates(offset=0, timeout=1)['message_id'] == 42
        assert client.edit_message_text(1001, 42, "Новый текст", reply_markup={'inline_keyboard': []})['message_id'] == 42
        assert client.answer_callback_query("cb_1", text="OK", show_alert=True) is True
        assert client.set_my_commands([{'command': 'start', 'description': 'Старт'}]) is True

        # send_document
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
            tmp_pdf.write(b"%PDF-1.4 test")
            tmp_pdf_path = tmp_pdf.name
        try:
            doc_res = client.send_document(1001, tmp_pdf_path, caption="Квитанция")
            assert doc_res['message_id'] == 42
        finally:
            if os.path.exists(tmp_pdf_path):
                os.remove(tmp_pdf_path)

        # download_file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_dest:
            dest_path = tmp_dest.name
        try:
            assert client.download_file("file_remote.pdf", dest_path) is True
            assert client.download_file("", dest_path) is False
        finally:
            if os.path.exists(dest_path):
                os.remove(dest_path)

    # Mock ошибки API (ok: False)
    def mock_urlopen_fail(req, *args, **kwargs):
        resp_data = {"ok": False, "description": "Chat not found", "error_code": 404}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(resp_data).encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch('urllib.request.urlopen', side_effect=mock_urlopen_fail):
        with pytest.raises(TelegramAPIError):
            client.send_message(chat_id=9999, text="Тест")

    # Mock HTTPError
    def mock_urlopen_httperror(req, *args, **kwargs):
        fp = io.BytesIO(b'{"description": "Forbidden", "error_code": 403}')
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, fp)

    with patch('urllib.request.urlopen', side_effect=mock_urlopen_httperror):
        with pytest.raises(TelegramAPIError):
            client.get_me()

    # Mock URLError
    def mock_urlopen_urlerror(req, *args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    with patch('urllib.request.urlopen', side_effect=mock_urlopen_urlerror):
        with pytest.raises(TelegramAPIError):
            client.get_me()

    # Mock TimeoutError
    def mock_urlopen_timeout(req, *args, **kwargs):
        raise TimeoutError("Timed out")

    with patch('urllib.request.urlopen', side_effect=mock_urlopen_timeout):
        with pytest.raises(TelegramAPIError):
            client.get_me()


# ────────────────────── 5. Тесты gRPC Servicer Methods ──────────────────────

def test_grpc_servicers_full_flow():
    from services.grpc_service import ReceiptGrpcServicer, ReconcileGrpcServicer

    con = get_db()
    con.execute('INSERT OR REPLACE INTO accounts(account_number, customer_name, address) VALUES (?,?,?)',
                ('700700', 'Абонент gRPC', 'ул. Тестовая 70'))
    con.execute('INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address) VALUES (?,?,?,?,?,?)',
                ('700700', '10.2026', '70/07/700700.pdf', 'h700700', 'tok_grpc_700', 'ул. Тестовая 70'))
    con.commit()
    con.close()

    servicer = ReceiptGrpcServicer()
    ctx = MagicMock()

    # GetAccount
    req_acc = MagicMock()
    req_acc.account_number = '700700'
    assert servicer.GetAccount(req_acc, ctx).found is True

    req_acc.account_number = '000000'
    assert servicer.GetAccount(req_acc, ctx).found is False

    # GetReceipts
    req_rec = MagicMock()
    req_rec.account_number = '700700'
    req_rec.period_filter = ''
    assert servicer.GetReceipts(req_rec, ctx).total_count >= 1

    # GetDistinctPeriods & SystemStats
    req_empty = MagicMock()
    assert hasattr(servicer.GetDistinctPeriods(req_empty, ctx), 'periods')
    assert servicer.GetSystemStats(req_empty, ctx).total_accounts >= 1

    # StreamReceiptPDF (not found)
    req_pdf = MagicMock()
    req_pdf.access_token = 'non_existent_token'
    chunks = list(servicer.StreamReceiptPDF(req_pdf, ctx))
    assert len(chunks) == 0

    # StreamReceiptPDF (valid file)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
        tmp_pdf.write(b"%PDF-1.4 sample content for streaming test")
        tmp_path = tmp_pdf.name

    with patch('services.grpc_service.receipt_service.get_pdf_by_token', return_value=tmp_path):
        req_pdf.access_token = 'tok_grpc_700'
        chunks = list(servicer.StreamReceiptPDF(req_pdf, ctx))
        assert len(chunks) >= 1
        assert b"%PDF-1.4" in chunks[0].data

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # ReconcileGrpcServicer
    rec_servicer = ReconcileGrpcServicer()
    req_recon = MagicMock()
    req_recon.filter = 'all'
    req_recon.period_filter = ''
    req_recon.page = 1
    req_recon.per_page = 10
    assert hasattr(rec_servicer.GetReconcileSummary(req_recon, ctx), 'total_accounts')


# ────────────────────── 6. Тесты Queue Backend (Memory & Redis) ─────────────

def test_queue_backends_coverage():
    from services.tasks.queue_backend import MemoryTaskQueueBackend, RedisTaskQueueBackend

    # 1. MemoryTaskQueueBackend
    mem = MemoryTaskQueueBackend()
    assert mem.ping() is True

    job1 = {'job_id': 'j1', 'filename': 'test1.pdf', 'max_retries': 2, 'retry_count': 0}
    assert mem.push_job(job1) is True
    assert mem.queue_length == 1

    # Pop & ACK
    popped = mem.pop_job(timeout=0.1, visibility_timeout=10.0, worker_id='w1')
    assert popped['job_id'] == 'j1'
    assert mem.processing_length == 1
    assert mem.extend_visibility('j1', extra_timeout=20.0) is True
    assert mem.ack_job('j1') is True
    assert mem.processing_length == 0

    # NACK (requeue=True)
    job2 = {'job_id': 'j2', 'filename': 'test2.pdf'}
    mem.save_job_state('j2', job2)
    mem.push_job(job2)
    p2 = mem.pop_job(timeout=0.1, visibility_timeout=10.0)
    assert p2['job_id'] == 'j2'
    assert mem.nack_job('j2', requeue=True) is True
    assert mem.queue_length == 1

    # State & list
    assert mem.get_job_state('j2')['job_id'] == 'j2'
    assert len(mem.list_jobs(limit=10)) >= 1

    # Locks
    assert mem.acquire_lock('test_lock', timeout=5.0) is True
    assert mem.acquire_lock('test_lock', timeout=5.0) is False
    mem.release_lock('test_lock')
    assert mem.acquire_lock('test_lock', timeout=5.0) is True
    mem.release_lock('test_lock')

    # Reclaim stale jobs with fresh queue
    mem_stale = MemoryTaskQueueBackend()
    job3 = {'job_id': 'j3', 'retry_count': 0, 'max_retries': 1}
    mem_stale.save_job_state('j3', job3)
    mem_stale.push_job(job3)
    mem_stale.pop_job(timeout=0.1, visibility_timeout=-1.0)  # сразу просрочена
    reclaimed = mem_stale.reclaim_stale_jobs()
    assert 'j3' in reclaimed

    # 2. RedisTaskQueueBackend с моком клиента redis
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.rpush.return_value = 1
    mock_redis.blpop.return_value = ('q', 'rj1')
    mock_redis.hset.return_value = 1
    mock_redis.hget.return_value = json.dumps({'job_id': 'rj1'}).encode('utf-8')
    mock_redis.hgetall.return_value = {b'rj1': json.dumps({'job_id': 'rj1', 'created_at': 100}).encode('utf-8')}
    mock_redis.hvals.return_value = [json.dumps({'job_id': 'rj1', 'created_at': 100}).encode('utf-8')]
    mock_redis.zrem.return_value = 1
    mock_redis.zadd.return_value = 1
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.register_script.return_value = MagicMock(return_value=1)

    with patch('redis.Redis.from_url', return_value=mock_redis):
        rb = RedisTaskQueueBackend("redis://localhost:6379/0")
        assert rb.ping() is True
        assert rb.push_job({'job_id': 'rj1'}) is True
        assert rb.ack_job('rj1') is True
        assert rb.nack_job('rj1', requeue=True) is True
        assert rb.extend_visibility('rj1') is True
        assert rb.save_job_state('rj1', {'job_id': 'rj1'}) is True
        assert rb.get_job_state('rj1')['job_id'] == 'rj1'
        assert len(rb.list_jobs()) == 1
        assert rb.acquire_lock('rlock') is True
        rb.release_lock('rlock')


# ────────────────────── 7. Тесты AppRequestHandler server.py ─────────────────

def test_server_handlers_and_static_serving():
    from server import AppRequestHandler

    con = get_db()
    con.execute('INSERT OR REPLACE INTO accounts(account_number, customer_name, address) VALUES (?,?,?)',
                ('700700', 'Абонент Тест', 'ул. Тестовая 70'))
    con.execute('INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address) VALUES (?,?,?,?,?,?)',
                ('700700', '10.2026', '70/07/700700.pdf', 'h700700', 'tok_grpc_700', 'ул. Тестовая 70'))
    con.commit()
    con.close()

    class TestHandler(AppRequestHandler):
        def __init__(self):
            self.headers = {}
            self.client_address = ('127.0.0.1', 54321)
            self.sent_json = None
            self.sent_html = None
            self.status_code = None
            self.headers_sent = {}
            self.wfile = io.BytesIO()
            self.rfile = io.BytesIO()
            self.path = '/'

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            self.headers_sent[keyword] = value

        def end_headers(self):
            pass

        def send_json(self, data, code=200, extra_headers=None, **kwargs):
            self.sent_json = data
            self.status_code = code

        def send_html(self, body, code=200, extra_headers=None):
            self.sent_html = body
            self.status_code = code

        def _redirect(self, url, status=302, extra_headers=None):
            self.status_code = status
            self.redirect_url = url

    h = TestHandler()

    # 1. Healthcheck & ready
    h._handle_health()
    assert h.status_code == 200
    h._handle_ready()
    assert h.status_code in (200, 503)

    # 2. Tasks API
    h._handle_api_tasks_list()
    assert h.status_code == 401

    with patch.object(h, '_is_admin', return_value=True):
        h._handle_api_tasks_list()
        assert h.status_code == 200
        h._handle_api_task_status('non_existent')
        assert h.status_code == 404

    # 3. Static serving
    h._serve_static('/robots.txt')
    assert h.status_code == 200
    h._serve_static('/static/../../etc/passwd')
    assert h.status_code == 404

    # 4. API search
    h._handle_api_search({'account': ['700700'], 'period': ['10.2026']})
    assert h.status_code == 200
    assert h.sent_json['status'] in ('EXACT_MATCH', 'NEED_VERIFICATION')

    # 5. API stats & sync
    h._handle_api_stats({'period': ['10.2026']})
    assert h.status_code == 200

    with patch.object(h, '_is_admin', return_value=True), patch.object(h, '_verify_csrf', return_value=True):
        h._handle_api_sync_receipts()
        assert h.status_code == 200
        h._handle_api_purge_missing_receipts()
        assert h.status_code == 200

    # 6. do_GET на основные портальные роуты (с отключенным rate limiting / throttling для тестового прогона)
    portal_routes = [
        '/',
        '/kvit',
        '/contacts',
        '/tarify',
        '/zakup',
        '/login',
        '/api/metrics',
        '/api/stats',
        '/search?q=700700',
        '/search?address=Тестовая+70',
        '/search?address=Несуществующая+улица+999'
    ]
    import server
    with patch.object(server.ip_throttler, 'acquire', return_value=(True, None, 0)), \
         patch.object(server.rate_limiter, 'is_allowed', return_value=(True, 0, 100)):
        for route in portal_routes:
            h.path = route
            h.do_GET()
            assert h.status_code in (200, 301, 302, 404), f"Route {route} returned {h.status_code}"

        # 7. do_GET на защищенные админские роуты
        with patch.object(h, '_is_admin', return_value=True):
            admin_routes = [
                '/admin/pages',
                '/admin/documents',
                '/admin/media',
                '/admin/users',
                '/admin/audit',
                '/reconcile',
                '/upload',
                '/api/tasks/stats',
            ]
            for route in admin_routes:
                h.path = route
                h.do_GET()
                assert h.status_code in (200, 302), f"Admin route {route} returned {h.status_code}"

    # 8. do_HEAD
    h.path = '/health'
    h.do_HEAD()
    assert h.status_code == 200


def test_server_do_post_routing():
    import server
    from server import AppRequestHandler

    class TestPostHandler(AppRequestHandler):
        def __init__(self):
            self.headers = {'Content-Length': '0'}
            self.client_address = ('127.0.0.1', 54321)
            self.sent_json = None
            self.sent_html = None
            self.status_code = None
            self.headers_sent = {}
            self.wfile = io.BytesIO()
            self.rfile = io.BytesIO(b'')
            self.path = '/'
            self.redirect_url = None

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            self.headers_sent[keyword] = value

        def end_headers(self):
            pass

        def send_json(self, data, code=200, extra_headers=None, **kwargs):
            self.sent_json = data
            self.status_code = code

        def send_html(self, body, code=200, extra_headers=None):
            self.sent_html = body
            self.status_code = code

        def _redirect(self, url, status=302, extra_headers=None):
            self.status_code = status
            self.redirect_url = url

        def _read_body(self, max_bytes=None):
            return b''

    h = TestPostHandler()

    with patch.object(server.ip_throttler, 'acquire', return_value=(True, None, 0)), \
         patch.object(server.rate_limiter, 'is_allowed', return_value=(True, 0, 100)), \
         patch.object(h, '_verify_csrf', return_value=True):

        # 1. Unauthenticated redirect
        h.path = '/upload'
        h.do_POST()
        assert h.status_code == 302
        assert h.redirect_url == '/login'

        h.path = '/import-folder'
        h.do_POST()
        assert h.status_code == 302

        # 2. Forbidden when not admin
        h.path = '/admin/pages/save'
        h.do_POST()
        assert h.status_code == 403

        h.path = '/admin/pages/delete'
        h.do_POST()
        assert h.status_code == 403

        h.path = '/admin/media/upload'
        h.do_POST()
        assert h.status_code == 403

        h.path = '/admin/media/delete'
        h.do_POST()
        assert h.status_code == 403

        h.path = '/admin/documents/save'
        h.do_POST()
        assert h.status_code == 403

        h.path = '/admin/documents/delete'
        h.do_POST()
        assert h.status_code == 403

        # 3. Authenticated as admin (mocking inner handler methods)
        with patch.object(h, '_is_admin', return_value=True), \
             patch.object(h, '_is_operator_or_admin', return_value=True), \
             patch.object(h, '_handle_upload'), \
             patch.object(h, '_handle_import_folder'), \
             patch.object(h, '_handle_admin_pages_save'), \
             patch.object(h, '_handle_admin_pages_delete'), \
             patch.object(h, '_handle_admin_media_upload'), \
             patch.object(h, '_handle_admin_media_delete'), \
             patch.object(h, '_handle_admin_documents_save'), \
             patch.object(h, '_handle_admin_documents_delete'), \
             patch.object(h, '_handle_admin_users_create'), \
             patch.object(h, '_handle_admin_users_delete'):

            h.path = '/upload'; h.do_POST(); assert h._handle_upload.called
            h.path = '/import-folder'; h.do_POST(); assert h._handle_import_folder.called
            h.path = '/admin/pages/save'; h.do_POST(); assert h._handle_admin_pages_save.called
            h.path = '/admin/pages/delete'; h.do_POST(); assert h._handle_admin_pages_delete.called
            h.path = '/admin/media/upload'; h.do_POST(); assert h._handle_admin_media_upload.called
            h.path = '/admin/media/delete'; h.do_POST(); assert h._handle_admin_media_delete.called
            h.path = '/admin/documents/save'; h.do_POST(); assert h._handle_admin_documents_save.called
            h.path = '/admin/documents/delete'; h.do_POST(); assert h._handle_admin_documents_delete.called
            h.path = '/admin/users/create'; h.do_POST(); assert h._handle_admin_users_create.called
            h.path = '/admin/users/delete'; h.do_POST(); assert h._handle_admin_users_delete.called

