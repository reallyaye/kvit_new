import io
import json
import struct
import time
from unittest.mock import MagicMock, patch

import pytest

from services.security.request_guards import read_bounded_body, send_payload_error
from services.security.session_store import DatabaseSessionStore, DBFailurePolicy
from services.tasks.task_manager import BackgroundTask, TaskQueueManager, TaskStatus
from services.websocket.ws_manager import WebSocketClientState, ws_manager

# ─────────────────────────────────────────────────────────────────────────────
# 1. WebSocket ws_manager tests
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_encode_frames():
    # Short
    short_f = ws_manager._encode_frame("hello", opcode=0x1)
    assert len(short_f) == 2 + 5

    # Medium (126)
    med_text = "x" * 200
    med_f = ws_manager._encode_frame(med_text, opcode=0x1)
    assert med_f[1] == 126

    # Large (127)
    big_text = "y" * 70000
    big_f = ws_manager._encode_frame(big_text, opcode=0x1)
    assert big_f[1] == 127

def test_ws_process_frames_ping_pong_close_text():
    mock_sock = MagicMock()
    mock_sock.fileno.return_value = 42
    state = WebSocketClientState(mock_sock, "127.0.0.1")

    # 1. Ping frame (opcode 0x9) -> should send Pong (0x8A)
    # Masked ping frame: 0x89, 0x80 (masked, len 0), mask 4 bytes
    ping_frame = struct.pack('!BB4s', 0x89, 0x80, b'\x01\x02\x03\x04')
    state.buf.extend(ping_frame)
    ws_manager._process_frames(state)
    assert mock_sock.sendall.called

    # 2. Text frame (opcode 0x1) unmasked JSON
    msg_json = json.dumps({'action': 'subscribe', 'channel': 'test'}).encode('utf-8')
    text_frame = struct.pack('!BB', 0x81, len(msg_json)) + msg_json
    state.buf.extend(text_frame)
    ws_manager._process_frames(state)

    # 3. Text frame with 16-bit length (126)
    long_msg = json.dumps({'action': 'ping', 'data': 'a' * 200}).encode('utf-8')
    frame_126 = struct.pack('!BBH', 0x81, 126, len(long_msg)) + long_msg
    state.buf.extend(frame_126)
    ws_manager._process_frames(state)

    # 4. Close frame (opcode 0x8) -> triggers unregister
    with patch.object(ws_manager, 'unregister') as mock_unreg:
        close_frame = struct.pack('!BB', 0x88, 0)
        state.buf.extend(close_frame)
        ws_manager._process_frames(state)
        mock_unreg.assert_called_with(mock_sock)

    # 5. Overflow frame (> 16MB)
    state.buf = bytearray(b'x' * (17 * 1024 * 1024))
    with patch.object(ws_manager, 'unregister') as mock_unreg:
        ws_manager._process_frames(state)
        mock_unreg.assert_called_with(mock_sock)

def test_ws_broadcast_and_subscriber():
    mock_sock = MagicMock()
    mock_sock.fileno.return_value = 99
    state = WebSocketClientState(mock_sock, "127.0.0.1")

    with ws_manager._lock:
        ws_manager._clients[99] = state

    # Local broadcast
    ws_manager._local_broadcast('test_event', {'foo': 'bar'})
    assert mock_sock.sendall.called

    # Send directly to client
    ws_manager.send(mock_sock, 'direct_event', {'n': 1})
    assert mock_sock.sendall.called

    # Dead client cleanup in local broadcast
    mock_sock.sendall.side_effect = BrokenPipeError("Closed")
    ws_manager._local_broadcast('test_fail', {})

    # Cleanup idle clients
    ws_manager._clients[100] = WebSocketClientState(MagicMock(), "1.2.3.4")
    ws_manager._clients[100].last_active = time.time() - 1000
    with patch.object(ws_manager, 'unregister'):
        ws_manager._cleanup_idle_clients(time.time())

    with ws_manager._lock:
        ws_manager._clients.clear()

# ─────────────────────────────────────────────────────────────────────────────
# 2. Task Manager extra coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_task_manager_stats_and_recovery():
    tm = TaskQueueManager()

    # BackgroundTask from_dict & to_dict
    task_dict = {
        'job_id': 'job_test_123',
        'source': 'test_src',
        'files': [('f1', 'f1.pdf')],
        'spool_dir': '/tmp/spool',
        'meta': {'author': 'admin'},
        'max_retries': 3,
        'retry_count': 1,
        'status': TaskStatus.PENDING,
        'progress': 50,
        'processed_files': 5,
        'total_files': 10
    }
    task = BackgroundTask.from_dict(task_dict)
    assert task.job_id == 'job_test_123'
    assert task.progress_pct == 50

    # get_queue_stats across all statuses
    jobs_mock = [
        {'status': TaskStatus.PENDING, 'total_files': 2, 'processed_files': 0},
        {'status': TaskStatus.PROCESSING, 'total_files': 2, 'processed_files': 1},
        {'status': TaskStatus.COMPLETED, 'total_files': 2, 'processed_files': 2},
        {'status': TaskStatus.FAILED, 'total_files': 2, 'processed_files': 0},
        {'status': TaskStatus.RETRY, 'total_files': 2, 'processed_files': 1},
    ]
    with patch.object(tm, 'list_tasks', return_value=jobs_mock):
        stats = tm.get_queue_stats()
        assert stats['pending_count'] == 1
        assert stats['processing_count'] == 1
        assert stats['completed_count'] == 1
        assert stats['failed_count'] == 1
        assert stats['retried_count'] == 1
        assert stats['total_files'] == 10

    # recover_stale_jobs
    with patch.object(tm.backend, 'reclaim_stale_jobs', return_value=['stale_job_1']):
        tm.recover_stale_jobs()

# ─────────────────────────────────────────────────────────────────────────────
# 3. Request Guards chunked body and error pages
# ─────────────────────────────────────────────────────────────────────────────

def test_request_guards_chunked_body():
    # 1. Valid chunked body: 5\r\nHello\r\n6\r\n World\r\n0\r\n\r\n
    stream_data = b"5\r\nHello\r\n6\r\n World\r\n0\r\n\r\n"
    handler = MagicMock()
    handler.headers = {'Transfer-Encoding': 'chunked'}
    handler.rfile = io.BytesIO(stream_data)

    body = read_bounded_body(handler, max_bytes=1024)
    assert body == b"Hello World"

    # 2. Chunked body exceeding limit
    handler.rfile = io.BytesIO(b"20\r\n" + b"x" * 32 + b"\r\n0\r\n\r\n")
    handler.send_json = MagicMock()
    handler.path = '/api/upload'
    res_too_large = read_bounded_body(handler, max_bytes=10)
    assert res_too_large is None
    handler.send_json.assert_called_with({'ok': False, 'error': 'Payload Too Large: Maximum allowed body is 10 bytes', 'status': 413}, 413)

    # 3. Invalid hex in chunked stream
    handler.rfile = io.BytesIO(b"ZZ\r\nBadHex\r\n0\r\n\r\n")
    res_bad_hex = read_bounded_body(handler, max_bytes=100)
    assert res_bad_hex is None

    # 4. send_payload_error for HTML views (413 and 400)
    html_handler = MagicMock()
    html_handler.path = '/upload'
    html_handler.headers = {'Accept': 'text/html'}
    del html_handler.send_json
    html_handler.send_html = MagicMock()
    html_handler._is_admin = MagicMock(return_value=True)

    send_payload_error(html_handler, 413, "Слишком большой файл")
    assert html_handler.send_html.called

    html_handler.send_html.reset_mock()
    send_payload_error(html_handler, 400, "Неверный запрос")
    assert html_handler.send_html.called

    # Fallback to send_error
    class BasicHandler:
        def __init__(self):
            self.path = '/some/path'
            self.headers = {'Accept': 'text/plain'}
            self.send_error_called = False
            self.last_code = None
            self.last_msg = None
        def send_error(self, code, msg):
            self.send_error_called = True
            self.last_code = code
            self.last_msg = msg

    basic = BasicHandler()
    send_payload_error(basic, 500, "Internal Server Error")
    assert basic.send_error_called is True
    assert basic.last_code == 500

# ─────────────────────────────────────────────────────────────────────────────
# 4. SessionStore policies & maintenance
# ─────────────────────────────────────────────────────────────────────────────

def test_session_store_extra():
    store = DatabaseSessionStore(l1_ttl_seconds=10.0, db_failure_policy=DBFailurePolicy.FAIL_OPEN_L1)
    tok = 'test_token_l1_999'

    # Store in L1 cache
    store._l1_cache[tok] = (time.time() + 1000, time.time() + 1000, 'admin_user', 'admin')

    # Simulate DB error during get_session_info
    with patch('services.security.session_store.get_db', side_effect=RuntimeError("DB dead")):
        info = store.get_session_info(tok)
        assert info is not None
        assert info['username'] == 'admin_user'

    # Strict policy raises
    strict_store = DatabaseSessionStore(l1_ttl_seconds=10.0, db_failure_policy=DBFailurePolicy.STRICT)
    with patch('services.security.session_store.get_db', side_effect=RuntimeError("DB dead")):
        with pytest.raises(RuntimeError):
            strict_store.get_session_info(tok)

    # delete_session
    with patch('services.security.session_store.write_transaction'):
        store.delete_session(tok)
    assert tok not in store._l1_cache

    # cleanup_expired & clear_l1_cache
    store._last_cleanup = 0.0  # Force cleanup trigger
    store._l1_cache['expired_tok'] = (time.time() - 100, time.time() - 100, 'u', 'r')
    with patch('services.security.session_store.write_transaction'):
        store.cleanup_expired()
    assert 'expired_tok' not in store._l1_cache
    store.clear_l1_cache()
    assert len(store._l1_cache) == 0

# ─────────────────────────────────────────────────────────────────────────────
# 5. gRPC Interceptors and Server creation
# ─────────────────────────────────────────────────────────────────────────────

def test_grpc_interceptors_and_server():
    import grpc

    from services.grpc_service import AuthInterceptor, RateLimitInterceptor, create_grpc_server

    # 1. AuthInterceptor
    interceptor = AuthInterceptor('secret_key_123')
    call_details = MagicMock()
    call_details.invocation_metadata = [('authorization', 'Bearer secret_key_123')]

    mock_handler = MagicMock()
    mock_handler.unary_stream = False
    continuation = MagicMock(return_value=mock_handler)

    # Authorized
    res = interceptor.intercept_service(continuation, call_details)
    assert res == mock_handler

    # Unauthorized
    call_details.invocation_metadata = [('authorization', 'Bearer bad_key')]
    denied_handler = interceptor.intercept_service(continuation, call_details)
    assert denied_handler is not None
    mock_ctx = MagicMock()
    denied_handler.unary_unary(None, mock_ctx)
    mock_ctx.abort.assert_called_with(grpc.StatusCode.UNAUTHENTICATED, "Invalid or missing gRPC API key")

    # 2. RateLimitInterceptor
    rl_interceptor = RateLimitInterceptor()
    mock_stream_handler = MagicMock()
    mock_stream_handler.unary_stream = True
    mock_stream_handler.unary_unary = None
    res_stream = rl_interceptor.intercept_service(lambda details: mock_stream_handler, call_details)
    assert res_stream is not None

    # 3. create_grpc_server
    server = create_grpc_server(host="127.0.0.1", port=50099)
    assert server is not None
    server.start()
    server.stop(grace=0)

# ─────────────────────────────────────────────────────────────────────────────
# 6. TelegramBotService commands coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_telegram_bot_commands():
    from services.telegram_bot.bot_service import TelegramBotService
    mock_client = MagicMock()
    mock_client.get_me.return_value = {'ok': True, 'result': {'username': 'testbot'}}

    with patch('services.telegram_bot.bot_service.TelegramClient', return_value=mock_client):
        bot = TelegramBotService(token='fake_bot_token')
        bot.client = mock_client

        # 1. /status
        with patch.object(bot, 'is_approved', return_value=True):
            bot._handle_text(100, 100, '/status', {})
            assert 'одобрена' in mock_client.send_message.call_args[0][1]

        with patch.object(bot, 'is_approved', return_value=False), \
             patch.object(bot, 'get_user_record', return_value={'status': 'PENDING'}):
            bot._handle_text(100, 100, '/status', {})
            assert 'рассмотрении' in mock_client.send_message.call_args[0][1]

        with patch.object(bot, 'is_approved', return_value=False), \
             patch.object(bot, 'get_user_record', return_value={'status': 'REJECTED'}):
            bot._handle_text(100, 100, '/status', {})
            assert 'отклонена' in mock_client.send_message.call_args[0][1]

        with patch.object(bot, 'is_approved', return_value=False), \
             patch.object(bot, 'get_user_record', return_value=None):
            bot._handle_text(100, 100, '/status', {})
            assert 'не подавали заявку' in mock_client.send_message.call_args[0][1]

        # 2. /users non-admin vs admin
        with patch.object(bot, 'is_admin', return_value=False):
            bot._handle_text(100, 100, '/users', {})
            assert 'только администраторам' in mock_client.send_message.call_args[0][1].lower()

        with patch.object(bot, 'is_admin', return_value=True), \
             patch.object(bot, '_send_users_list_to_admin') as mock_admin_list:
            bot._handle_text(100, 100, '/users', {})
            assert mock_admin_list.called

        # 3. /approve and /reject
        with patch.object(bot, 'is_admin', return_value=True), \
             patch('services.telegram_bot.bot_service.write_transaction'):
            mock_client.send_message.reset_mock()
            bot._handle_text(100, 100, '/approve 777', {})
            assert any('успешно' in call[0][1] for call in mock_client.send_message.call_args_list)

            mock_client.send_message.reset_mock()
            bot._handle_text(100, 100, '/reject 777', {})
            assert any('отклонен' in call[0][1] for call in mock_client.send_message.call_args_list)

        # 4. /login
        with patch('services.telegram_bot.bot_service.auth_service.verify_password', return_value=True):
            bot._handle_text(100, 100, '/login correct_pass', {})
            assert 'успешна' in mock_client.send_message.call_args[0][1]

        with patch('services.telegram_bot.bot_service.auth_service.verify_password', return_value=False):
            bot._handle_text(100, 100, '/login wrong_pass', {})
            assert 'Неверный пароль' in mock_client.send_message.call_args[0][1]

        bot._handle_text(100, 100, '/login', {})
        assert 'Для авторизации' in mock_client.send_message.call_args[0][1]

        # 5. /help
        with patch.object(bot, '_send_help') as mock_help:
            bot._handle_text(100, 100, '/help', {})
            assert mock_help.called


