import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

import config
import server
from services.security.auth_service import auth_service


def test_server_login_flow():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.client_address = ('127.0.0.1', 50000)
    h.headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': '30'}

    # 1. Login success operator
    h._read_bounded_body = MagicMock(return_value=b"username=oper1&password=pass1")
    h._get_client_ip = MagicMock(return_value='127.0.0.1')
    h._redirect = MagicMock()
    h._get_session_cookie_header = MagicMock(return_value='session=tok1; Path=/')

    with patch.object(auth_service, 'verify_credentials', return_value={'username': 'oper1', 'role': 'operator'}), \
         patch.object(auth_service, 'create_session', return_value='tok1'), \
         patch.object(auth_service, 'log_audit'):
        h._handle_login()
        h._redirect.assert_called_with('/upload', extra_headers={'Set-Cookie': 'session=tok1; Path=/'})

    # 2. Login success admin
    with patch.object(auth_service, 'verify_credentials', return_value={'username': 'admin', 'role': 'admin'}), \
         patch.object(auth_service, 'create_session', return_value='tok2'), \
         patch.object(auth_service, 'log_audit'):
        h._handle_login()
        h._redirect.assert_called_with('/admin/pages', extra_headers={'Set-Cookie': 'session=tok1; Path=/'})

    # 3. Login failure
    h.send_html = MagicMock()
    with patch.object(auth_service, 'verify_credentials', return_value=None), \
         patch.object(auth_service, 'log_audit'):
        h._handle_login()
        assert h.send_html.called

def test_server_admin_users_create_delete():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.client_address = ('127.0.0.1', 50000)
    h._get_client_ip = MagicMock(return_value='127.0.0.1')
    h._get_current_user = MagicMock(return_value={'username': 'admin'})
    h._redirect = MagicMock()

    # Unauthorized
    h._is_admin = MagicMock(return_value=False)
    h._handle_admin_users_create()
    h._redirect.assert_called_with('/login')

    h._handle_admin_users_delete()
    h._redirect.assert_called_with('/login')

    # Authorized - CSRF invalid
    h._is_admin.return_value = True
    h._read_form_params = MagicMock(return_value={'csrf_token': ['bad']})
    h._verify_csrf = MagicMock(return_value=False)
    h._handle_admin_users_create()
    assert 'err=' in h._redirect.call_args[0][0]

    h._handle_admin_users_delete()
    assert 'err=' in h._redirect.call_args[0][0]

    # Authorized - Success create
    h._verify_csrf.return_value = True
    h._read_form_params.return_value = {
        'csrf_token': ['tok'], 'username': ['newuser'], 'password': ['pass'],
        'full_name': ['New User'], 'role': ['operator']
    }
    with patch.object(auth_service, 'create_user'), \
         patch.object(auth_service, 'log_audit'):
        h._redirect.reset_mock()
        h._handle_admin_users_create()
        assert 'msg=' in h._redirect.call_args[0][0]

    # Authorized - Success delete
    h._read_form_params.return_value = {'csrf_token': ['tok'], 'username': ['newuser']}
    with patch.object(auth_service, 'delete_user'), \
         patch.object(auth_service, 'log_audit'):
        h._redirect.reset_mock()
        h._handle_admin_users_delete()
        assert 'msg=' in h._redirect.call_args[0][0]

def test_server_api_upload_batch_and_accounts():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.client_address = ('127.0.0.1', 50000)
    h._get_client_ip = MagicMock(return_value='127.0.0.1')
    h._get_current_user = MagicMock(return_value={'username': 'operator'})
    h.send_json = MagicMock()

    # 1. API upload batch unauthorized
    h._is_operator_or_admin = MagicMock(return_value=False)
    h._handle_api_upload_batch()
    h.send_json.assert_called_with({'error': 'Unauthorized'}, 401)

    # 2. API upload batch success
    h._is_operator_or_admin.return_value = True
    h._verify_csrf = MagicMock(return_value=True)
    h._parse_multipart_to_disk = MagicMock(return_value=('/tmp/dir', [('f1.pdf', '/tmp/dir/f1.pdf')]))
    mock_task = MagicMock()
    mock_task.job_id = 'job_batch_1'
    mock_task.status = 'PENDING'
    with patch('server.task_manager.submit_pdf_job', return_value=mock_task), \
         patch.object(auth_service, 'log_audit'):
        h.send_json.reset_mock()
        h._handle_api_upload_batch()
        assert h.send_json.call_args[0][1] == 202

    # 3. API upload accounts unauthorized
    h._is_admin = MagicMock(return_value=False)
    h._handle_api_upload_accounts()
    h.send_json.assert_called_with({'error': 'Unauthorized'}, 401)

    # 4. API upload accounts success
    h._is_admin.return_value = True
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tf:
        tf.write(b"mock xlsx content")
        tf_path = tf.name

    h._parse_accounts_multipart = MagicMock(return_value=(os.path.dirname(tf_path), tf_path, 'upsert', 'accounts.xlsx'))
    with patch('import_accounts.import_accounts_file', return_value={'imported': 10, 'skipped': 0, 'total_in_db': 100, 'elapsed_seconds': 0.5}):
        h.send_json.reset_mock()
        h._handle_api_upload_accounts()
        assert h.send_json.call_args[0][1] == 200

def test_server_serve_pdf():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h._is_admin = MagicMock(return_value=False)
    h.send_html = MagicMock()
    h.send_response = MagicMock()
    h._send_security_headers = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    h.wfile = io.BytesIO()

    # 1. Invalid token (< 32 chars) -> 403
    h._serve_pdf('/download', {'token': ['short']})
    assert h.send_html.called
    assert h.send_html.call_args[0][1] == 403

    # 2. Missing token -> 404
    h.send_html.reset_mock()
    with patch('server.receipt_service.get_pdf_by_token', return_value=None):
        h._serve_pdf('/download', {'token': ['0123456789abcdef0123456789abcdef']})
        assert h.send_html.called
        assert h.send_html.call_args[0][1] == 404

    # 3. Valid file with X-Accel-Redirect
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pf:
        pf.write(b"%PDF-1.4 test stream content")
        pf_path = pf.name

    with patch('server.receipt_service.get_pdf_by_token', return_value=pf_path), \
         patch.object(config, 'ENABLE_X_ACCEL_REDIRECT', True):
        h._serve_pdf('/download', {'token': ['0123456789abcdef0123456789abcdef']})
        assert h.send_response.called

    # 4. Valid file with regular streaming
    with patch('server.receipt_service.get_pdf_by_token', return_value=pf_path), \
         patch.object(config, 'ENABLE_X_ACCEL_REDIRECT', False):
        h._serve_pdf('/view-pdf', {'token': ['0123456789abcdef0123456789abcdef']})
        assert h.send_response.called
        assert len(h.wfile.getvalue()) > 0

    if os.path.exists(pf_path):
        os.remove(pf_path)

def test_bot_main(monkeypatch):
    import bot

    # 1. Missing token raises SystemExit
    monkeypatch.setattr(config, 'TELEGRAM_BOT_TOKEN', '')
    with pytest.raises(SystemExit):
        bot.main()

    # 2. Valid token
    monkeypatch.setattr(config, 'TELEGRAM_BOT_TOKEN', '123456:ABC-DEF')
    monkeypatch.setattr(config, 'TELEGRAM_ADMIN_IDS', {123456})
    with patch('bot.migrate_db'), \
         patch('bot.telegram_bot_service.run_polling', side_effect=KeyboardInterrupt), \
         patch('bot.telegram_bot_service.stop'):
        bot.main()

def test_worker_main(monkeypatch):
    import worker

    # Mock migration, queue creation, manager
    mock_mgr = MagicMock()
    with patch('sys.argv', ['worker.py']), \
         patch('worker.migrate_db'), \
         patch('worker.create_task_queue_backend'), \
         patch('worker.TaskQueueManager', return_value=mock_mgr), \
         patch('time.sleep', side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit):
            worker.main()
        assert mock_mgr.start.called
        assert mock_mgr.stop.called

def test_server_import_folder_and_upload():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.client_address = ('127.0.0.1', 50000)
    h._is_admin = MagicMock(return_value=True)
    h._get_session_token = MagicMock(return_value='tok1')
    h.send_html = MagicMock()
    h.send_json = MagicMock()

    # 1. _handle_import_folder - invalid CSRF
    h._read_bounded_body = MagicMock(return_value=b"folder_path=/tmp/receipts&csrf_token=bad")
    h._verify_csrf = MagicMock(return_value=False)
    h._handle_import_folder()
    assert h.send_html.called
    assert h.send_html.call_args[0][1] == 403

    # 2. _handle_import_folder - unsafe path
    h._verify_csrf.return_value = True
    with patch('config.is_safe_import_path', return_value=(False, '', 'Путь запрещен')):
        h.send_html.reset_mock()
        h._handle_import_folder()
        assert h.send_html.called

    # 3. _handle_import_folder - safe path with no pdfs
    with patch('config.is_safe_import_path', return_value=(True, '/tmp/empty', '')), \
         patch('os.walk', return_value=[('/tmp/empty', [], [])]):
        h.send_html.reset_mock()
        h._handle_import_folder()
        assert h.send_html.called

    # 4. _handle_import_folder - safe path with pdfs -> success
    with patch('config.is_safe_import_path', return_value=(True, '/tmp/pdfs', '')), \
         patch('os.walk', return_value=[('/tmp/pdfs', [], ['test.pdf'])]), \
         patch('server.task_manager.submit_pdf_job', return_value=MagicMock(job_id='job_imp_1')):
        h.send_html.reset_mock()
        h._handle_import_folder()
        assert h.send_html.called

    # 5. _handle_upload - invalid CSRF
    h._verify_csrf.return_value = False
    h._handle_upload()
    assert h.send_html.call_args[0][1] == 403

    # 6. _handle_upload - payload too large
    h._verify_csrf.return_value = True
    h._parse_multipart_to_disk = MagicMock(return_value=(None, "PAYLOAD_TOO_LARGE"))
    h._handle_upload()
    assert h.send_html.call_args[0][1] == 413

    # 7. _handle_upload - no files
    h._parse_multipart_to_disk.return_value = (None, [])
    h._handle_upload()
    assert h.send_html.called

    # 8. _handle_upload - success
    h._parse_multipart_to_disk.return_value = ('/tmp/spool', [('r1.pdf', '/tmp/spool/r1.pdf')])
    with patch('server.task_manager.submit_pdf_job', return_value=MagicMock(job_id='job_web_1')):
        h.send_html.reset_mock()
        h._handle_upload()
        assert h.send_html.called

def test_server_api_sync_and_purge():
    h = server.AppRequestHandler.__new__(server.AppRequestHandler)
    h.client_address = ('127.0.0.1', 50000)
    h.send_json = MagicMock()

    # 1. API sync receipts - unauthorized
    h._is_admin = MagicMock(return_value=False)
    h._handle_api_sync_receipts()
    assert h.send_json.call_args[0][1] == 401

    # 2. API sync receipts - success
    h._is_admin.return_value = True
    h._verify_csrf = MagicMock(return_value=True)
    with patch('server.sync_receipts_with_filesystem', return_value=(1, 2, 3)), \
         patch('server.ws_manager.broadcast'):
        h.send_json.reset_mock()
        h._handle_api_sync_receipts()
        assert h.send_json.called
        assert h.send_json.call_args[0][0]['success'] is True

    # 3. API purge missing receipts - unauthorized
    h._is_admin.return_value = False
    h._handle_api_purge_missing_receipts()
    assert h.send_json.call_args[0][1] == 401

    # 4. API purge missing receipts - success
    h._is_admin.return_value = True
    with patch('server.purge_missing_receipts', return_value=5), \
         patch('server.ws_manager.broadcast'):
        h.send_json.reset_mock()
        h._handle_api_purge_missing_receipts()
        assert h.send_json.called
        assert h.send_json.call_args[0][0]['purged'] == 5


