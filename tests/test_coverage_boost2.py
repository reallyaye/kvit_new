import json
from unittest.mock import MagicMock, patch

import pytest

import app
import config
import server
from database import connection, postgres_backend
from services.tasks.queue_backend import RedisTaskQueueBackend, create_task_queue_backend, mask_redis_url
from templates import portal_views

# ─────────────────────────────────────────────────────────────────────────────
# 1. app.py testing
# ─────────────────────────────────────────────────────────────────────────────

def test_app_validate_startup_security_dev(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'SECRET_KEY', '')
    monkeypatch.setattr(config, 'GRPC_API_KEY', '')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', '')
    app.validate_startup_security()
    assert config.SECRET_KEY != ''
    assert config.GRPC_API_KEY == 'dev-grpc-insecure-key-local'
    assert config.ADMIN_PASSWORD_HASH.startswith('pbkdf2_sha256$')

def test_app_validate_startup_security_prod_valid(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', 'x' * 32)
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', 'pbkdf2_sha256$600000$saltsaltsalt$hashhashhash')
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'y' * 16)
    app.validate_startup_security()

def test_app_validate_startup_security_prod_invalid(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', 'short')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', 'invalid_hash')
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'short')
    with pytest.raises(SystemExit):
        app.validate_startup_security()

def test_app_get_local_ip():
    ip = app.get_local_ip()
    assert isinstance(ip, str)
    with patch('socket.gethostname', side_effect=OSError("Network error")):
        assert app.get_local_ip() == '127.0.0.1'

def test_app_configure_tls(monkeypatch):
    mock_server = MagicMock()
    monkeypatch.setattr(config, 'USE_HTTPS', False)
    monkeypatch.setattr(config, 'SSL_CERT_PATH', '')
    monkeypatch.setattr(config, 'SSL_KEY_PATH', '')
    proto, is_tls = app.configure_tls(mock_server)
    assert proto == 'http'
    assert is_tls is False

    # Missing cert file exits
    monkeypatch.setattr(config, 'USE_HTTPS', True)
    monkeypatch.setattr(config, 'SSL_CERT_PATH', '/non/existent/cert.pem')
    monkeypatch.setattr(config, 'SSL_KEY_PATH', '/non/existent/key.pem')
    with pytest.raises(SystemExit):
        app.configure_tls(mock_server)

def test_app_run_http_loop():
    mock_server = MagicMock()
    mock_server.serve_forever.side_effect = KeyboardInterrupt
    app.run_http_loop(mock_server)
    assert mock_server.serve_forever.called

def test_app_main(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'TELEGRAM_ENABLED', True)
    monkeypatch.setattr(config, 'RUN_EMBEDDED_BOT', True)
    monkeypatch.setattr(config, 'RUN_EMBEDDED_WORKER', True)

    with patch('app.migrate_db') as mock_mig, \
         patch('app.create_grpc_server') as mock_grpc_factory, \
         patch('app.telegram_bot_service') as mock_bot, \
         patch('app.ThreadingHTTPServer') as mock_http_factory, \
         patch('app.run_http_loop') as mock_loop, \
         patch('app.task_manager') as mock_tm, \
         patch('app.ws_manager') as mock_ws:

        mock_grpc = MagicMock()
        mock_grpc_factory.return_value = mock_grpc
        mock_http = MagicMock()
        mock_http_factory.return_value = mock_http

        app.main()

        assert mock_mig.called
        assert mock_grpc.start.called
        assert mock_bot.start_in_thread.called
        assert mock_tm.start.called
        assert mock_loop.called
        assert mock_grpc.stop.called
        assert mock_bot.stop.called
        assert mock_tm.stop.called
        assert mock_ws.stop.called

# ─────────────────────────────────────────────────────────────────────────────
# 2. database/postgres_backend.py testing
# ─────────────────────────────────────────────────────────────────────────────

def test_postgres_backend_classes():
    row_data = {'id': 1, 'name': 'test_account', 'balance': 100.5}
    cols = ['id', 'name', 'balance']
    row = postgres_backend.PostgresRowWrapper(row_data, cols)

    assert row[0] == 1
    assert row['name'] == 'test_account'
    assert row.get('balance') == 100.5
    assert row.get('unknown', 'def') == 'def'
    assert row.keys() == cols
    assert list(row) == [1, 'test_account', 100.5]
    assert 'PostgresRow' in repr(row)

    mock_raw_cur = MagicMock()
    mock_raw_cur.description = [('id',), ('name',), ('balance',)]
    mock_raw_cur.fetchone.return_value = row_data
    mock_raw_cur.fetchall.return_value = [row_data, row_data]
    mock_raw_cur.rowcount = 1

    cur_wrap = postgres_backend.PostgresCursorWrapper(mock_raw_cur)
    conv = cur_wrap._convert_query('SELECT * FROM t WHERE a = ? AND b != ""')
    assert '%s' in conv
    assert "!= ''" in conv

    cur_wrap.execute('SELECT ?', 123)
    assert mock_raw_cur.execute.called

    cur_wrap.executemany('INSERT INTO t VALUES (?)', [(1,), (2,)])
    assert mock_raw_cur.executemany.called

    cur_wrap.executescript('SELECT 1;')
    assert mock_raw_cur.execute.called

    f1 = cur_wrap.fetchone()
    assert f1['id'] == 1

    mock_raw_cur.fetchone.return_value = None
    assert cur_wrap.fetchone() is None

    fall = cur_wrap.fetchall()
    assert len(fall) == 2
    mock_raw_cur.fetchall.return_value = []
    assert cur_wrap.fetchall() == []
    assert cur_wrap.rowcount == 1

    mock_pool = MagicMock()
    mock_raw_conn = MagicMock()
    mock_raw_conn.cursor.return_value = mock_raw_cur
    conn_wrap = postgres_backend.PostgresConnectionWrapper(mock_raw_conn, mock_pool)
    c = conn_wrap.cursor()
    assert isinstance(c, postgres_backend.PostgresCursorWrapper)
    conn_wrap.commit()
    assert mock_raw_conn.commit.called
    conn_wrap.rollback()
    assert mock_raw_conn.rollback.called
    conn_wrap.close()
    assert mock_pool.putconn.called

def test_postgres_pool_and_transactions(monkeypatch):
    mock_pool = MagicMock()
    mock_raw_conn = MagicMock()
    mock_pool.getconn.return_value = mock_raw_conn

    monkeypatch.setattr(postgres_backend, '_PG_POOL', mock_pool)

    # get_postgres_db context manager
    db = postgres_backend.get_postgres_db()
    assert isinstance(db, postgres_backend.PostgresConnectionWrapper)
    db.close()
    assert mock_pool.putconn.called

    # postgres_write_transaction success
    with postgres_backend.postgres_write_transaction() as db:
        pass
    assert mock_raw_conn.commit.called

    # postgres_write_transaction failure
    with pytest.raises(ValueError):
        with postgres_backend.postgres_write_transaction() as db:
            raise ValueError("Rollback test")
    assert mock_raw_conn.rollback.called

# ─────────────────────────────────────────────────────────────────────────────
# 3. database/connection.py testing
# ─────────────────────────────────────────────────────────────────────────────

def test_database_connection_helpers(monkeypatch):
    monkeypatch.setattr(config, 'DATABASE_URL', 'postgresql://user:pass@localhost:5432/db')
    monkeypatch.setattr(config, 'DB_TYPE', 'postgres')
    assert connection.is_postgres_configured() is True

    # _ensure_postgres_initialized with empty DATABASE_URL
    monkeypatch.setattr(config, 'DATABASE_URL', '')
    monkeypatch.setattr(postgres_backend, '_PG_POOL', None)
    with pytest.raises(RuntimeError, match="DATABASE_URL пуста"):
        connection._ensure_postgres_initialized()

    # get_db() with production guard
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'DB_TYPE', 'sqlite')
    with pytest.raises(RuntimeError, match="Production окружение требует PostgreSQL"):
        connection.get_db()

    # get_db() with postgres
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'DB_TYPE', 'postgres')
    monkeypatch.setattr(config, 'DATABASE_URL', 'postgresql://u:p@h/d')
    with patch('database.postgres_backend.init_postgres_pool'), \
         patch('database.postgres_backend.get_postgres_db', return_value="pg_mock"):
        monkeypatch.setattr(postgres_backend, '_PG_POOL', MagicMock())
        assert connection.get_db() == "pg_mock"

    # write_transaction with postgres
    with patch('database.postgres_backend.postgres_write_transaction') as mock_pwt:
        mock_pwt.return_value.__enter__.return_value = "pg_tx"
        with connection.write_transaction() as tx:
            assert tx == "pg_tx"

    # write_transaction with sqlite retry
    monkeypatch.setattr(config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(config, 'DATABASE_URL', '')

    mock_sqlite_con = MagicMock()
    mock_sqlite_con.execute.side_effect = [
        connection.sqlite3.OperationalError("database is locked"),
        None, # BEGIN IMMEDIATE
    ]
    with patch('database.connection.get_db', return_value=mock_sqlite_con):
        with connection.write_transaction(max_retries=3, base_delay=0.001) as con:
            assert con == mock_sqlite_con

# ─────────────────────────────────────────────────────────────────────────────
# 4. templates/portal_views.py document rendering with all attachment types
# ─────────────────────────────────────────────────────────────────────────────

def test_portal_views_document_render_full():
    doc_data = {
        'title': 'Комплексный годовой отчет',
        'h1': 'Комплексный отчет 2026',
        'date_text': '01.09.2026',
        'iframes': ['/static/pdf/annual_report.pdf'],
        'files': [
            '/static/pdf/details.pdf',
            '/static/files/object_materials.zip',
            '/static/files/general_archive.zip',
            '/static/files/calculations.xlsx',
            '/static/files/description.docx',
            '/static/files/data.csv',
        ]
    }
    rendered = portal_views.render_document(doc_data, is_admin=True, doc_key='annual_report')
    assert 'Комплексный отчет 2026' in rendered
    assert 'Скачать ZIP' in rendered
    assert 'Скачать Excel' in rendered
    assert 'Скачать Word' in rendered
    assert 'CSV файл' in rendered

    # Empty document fallback
    empty_doc = {'title': 'Пустой отчет'}
    rendered_empty = portal_views.render_document(empty_doc, is_admin=False)
    assert 'Документ временно недоступен для скачивания' in rendered_empty

    # render_page fallback 404
    p404 = portal_views.render_page('not_existing_slug_xyz')
    assert '404' in p404

# ─────────────────────────────────────────────────────────────────────────────
# 5. server.py CMS & Accounts Handlers
# ─────────────────────────────────────────────────────────────────────────────

def test_server_cms_handlers(monkeypatch):
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': '100'}
    h.path = '/admin/pages/save'
    h.client_address = ('127.0.0.1', 12345)

    # 1. Pages Save: Unauthorized
    h._is_admin = MagicMock(return_value=False)
    h._redirect = MagicMock()
    h._handle_admin_pages_save()
    h._redirect.assert_called_with('/login')

    # 2. Pages Save: Authorized, invalid CSRF
    h._is_admin.return_value = True
    h._get_client_ip = MagicMock(return_value='127.0.0.1')
    h._get_current_user = MagicMock(return_value={'username': 'admin'})
    h._read_form_params = MagicMock(return_value={'csrf_token': ['bad'], 'slug': ['test'], 'title': ['Test'], 'html': ['<p>Hi</p>']})
    h._verify_csrf = MagicMock(return_value=False)
    h.send_html = MagicMock()
    h._handle_admin_pages_save()
    assert h.send_html.called

    # 3. Pages Save: Authorized, valid CSRF, success
    h._verify_csrf.return_value = True
    monkeypatch.setattr(server.portal_cms, 'save_page', MagicMock(return_value=(True, 'test')))
    h._redirect.reset_mock()
    h._handle_admin_pages_save()
    assert 'msg=' in h._redirect.call_args[0][0]

    # 4. Pages Delete: Authorized, valid CSRF
    h.path = '/admin/pages/delete'
    h._read_form_params.return_value = {'csrf_token': ['tok'], 'slug': ['test']}
    monkeypatch.setattr(server.portal_cms, 'delete_page', MagicMock(return_value=(True, 'Удалено')))
    h._redirect.reset_mock()
    h._handle_admin_pages_delete()
    assert 'msg=' in h._redirect.call_args[0][0]

    # 5. Media Upload: Ajax & Regular
    h.path = '/admin/media/upload?ajax=1'
    h._parse_multipart_fields_and_files = MagicMock(return_value=({'csrf_token': ['tok']}, [('file', 'pic.png', b'data')]))
    h.send_json = MagicMock()
    monkeypatch.setattr(server.portal_cms, 'save_media_file', MagicMock(return_value=(True, {'url': '/img/pic.png'}, '')))
    h._handle_admin_media_upload()
    h.send_json.assert_called_with({'ok': True, 'file': {'url': '/img/pic.png'}, 'error': ''})

    # 6. Media Delete
    h.path = '/admin/media/delete'
    h._read_form_params.return_value = {'csrf_token': ['tok'], 'filename': ['pic.png']}
    monkeypatch.setattr(server.portal_cms, 'delete_media_file', MagicMock(return_value=(True, 'Удален')))
    h._redirect.reset_mock()
    h._handle_admin_media_delete()
    assert 'msg=' in h._redirect.call_args[0][0]

    # 7. Documents Save & Delete
    h.path = '/admin/documents/save'
    h._read_form_params.return_value = {
        'csrf_token': ['tok'], 'key': ['k1'], 'title': ['T1'], 'category': ['cat'],
        'date_text': ['2026'], 'files': ['f1.pdf'], 'iframes': ['if1.pdf']
    }
    monkeypatch.setattr(server.portal_cms, 'save_document', MagicMock(return_value=(True, 'k1')))
    h._redirect.reset_mock()
    h._handle_admin_documents_save()
    assert 'msg=' in h._redirect.call_args[0][0]

    h.path = '/admin/documents/delete'
    h._read_form_params.return_value = {'csrf_token': ['tok'], 'key': ['k1']}
    monkeypatch.setattr(server.portal_cms, 'delete_document', MagicMock(return_value=(True, 'Удален')))
    h._redirect.reset_mock()
    h._handle_admin_documents_delete()
    assert 'msg=' in h._redirect.call_args[0][0]

# ─────────────────────────────────────────────────────────────────────────────
# 6. services/tasks/queue_backend.py Redis methods
# ─────────────────────────────────────────────────────────────────────────────

def test_redis_queue_backend_extra_methods():
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.register_script.return_value = MagicMock(return_value=1)
    mock_redis.zrangebyscore.return_value = [b'stale1']
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch('redis.Redis.from_url', return_value=mock_redis):
        backend = RedisTaskQueueBackend("redis://localhost:6379/0")

        # pop_job via claim script
        backend._script_claim = MagicMock(return_value=['j1', json.dumps({'job_id': 'j1'})])
        assert backend.pop_job()['job_id'] == 'j1'

        # pop_job via blpop fallback
        backend._script_claim = MagicMock(return_value=None)
        mock_redis.blpop.return_value = (b'kvit:jobs:pending', 'j2')
        backend._script_register = MagicMock(return_value=json.dumps({'job_id': 'j2'}))
        assert backend.pop_job(timeout=1.0)['job_id'] == 'j2'

        # reclaim_stale_jobs
        with patch.object(backend, 'get_job_state', return_value={'job_id': 'stale1', 'retries': 0, 'max_retries': 2}):
            assert backend.reclaim_stale_jobs() == ['stale1']

        # properties
        mock_redis.llen.return_value = 7
        mock_redis.zcard.return_value = 3
        assert backend.queue_length == 7
        assert backend.processing_length == 3
        assert backend.dlq_length == 7

def test_mask_redis_url_and_factory(monkeypatch):
    masked = mask_redis_url("redis://default:mysecretpassword@redis.internal:6379/0")
    assert "mysecretpassword" not in masked
    assert "***" in masked

    # Factory in dev with redis unavailable
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
    with patch('services.tasks.queue_backend.RedisTaskQueueBackend.ping', return_value=False):
        b = create_task_queue_backend()
        assert b.__class__.__name__ == 'MemoryTaskQueueBackend'
