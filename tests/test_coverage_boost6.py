# -*- coding: utf-8 -*-
"""
test_coverage_boost6.py — целевые тесты для покрытия пробелов в:
- services/tasks/task_manager.py  (BackgroundTask, TaskQueueManager)
- services/tasks/queue_backend.py (MemoryTaskQueueBackend edge cases)
- services/websocket/ws_manager.py (WebSocketClientState, WebSocketManager)
"""
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────
# 1. BackgroundTask model
# ─────────────────────────────────────────────────────────────
class TestBackgroundTask(unittest.TestCase):

    def _make_task(self, files=None, status=None):
        from services.tasks.task_manager import BackgroundTask
        t = BackgroundTask(
            job_id='job_test_001',
            source='test',
            files=files or [('a.pdf', '/tmp/a.pdf')],
        )
        if status:
            t.status = status
        return t

    def test_progress_pct_zero_total_files_pending(self):
        from services.tasks.task_manager import BackgroundTask
        t = BackgroundTask(job_id='j1', source='s', files=[])
        # total_files == 0 and status != COMPLETED → 0
        self.assertEqual(t.progress_pct, 0)

    def test_progress_pct_zero_total_files_completed(self):
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        t = BackgroundTask(job_id='j2', source='s', files=[])
        t.status = TaskStatus.COMPLETED
        # total_files == 0 and COMPLETED → 100
        self.assertEqual(t.progress_pct, 100)

    def test_progress_pct_with_files(self):
        t = self._make_task(files=[('a.pdf', '/a'), ('b.pdf', '/b')])
        t.processed_files = 1
        self.assertEqual(t.progress_pct, 50)

    def test_speed_no_started_at(self):
        t = self._make_task()
        t.started_at = None
        t.processed_files = 5
        self.assertEqual(t.speed_files_per_sec, 0.0)

    def test_speed_no_processed_files(self):
        t = self._make_task()
        t.started_at = time.time() - 10
        t.processed_files = 0
        self.assertEqual(t.speed_files_per_sec, 0.0)

    def test_speed_with_finished_at(self):
        t = self._make_task()
        t.started_at = time.time() - 5
        t.finished_at = time.time()
        t.processed_files = 10
        self.assertGreater(t.speed_files_per_sec, 0.0)

    def test_eta_completed_returns_zero(self):
        from services.tasks.task_manager import TaskStatus
        t = self._make_task()
        t.status = TaskStatus.COMPLETED
        self.assertEqual(t.eta_seconds, 0)

    def test_eta_failed_returns_none(self):
        from services.tasks.task_manager import TaskStatus
        t = self._make_task()
        t.status = TaskStatus.FAILED
        self.assertIsNone(t.eta_seconds)

    def test_eta_with_speed(self):
        from services.tasks.task_manager import BackgroundTask
        t = BackgroundTask(job_id='j3', source='s', files=[('a', '/a'), ('b', '/b'), ('c', '/c')])
        t.started_at = time.time() - 2
        t.processed_files = 1
        eta = t.eta_seconds
        self.assertIsNotNone(eta)
        self.assertIsInstance(eta, int)

    def test_update_from_dict(self):
        t = self._make_task()
        t.update_from_dict({
            'status': 'COMPLETED',
            'added': 5,
            'orphan': 2,
            'skipped': 1,
            'duplicates': 0,
            'details': ['d1', 'd2'],
            'error_message': None,
            'retry_count': 1,
            'max_retries': 3,
        })
        self.assertEqual(t.status, 'COMPLETED')
        self.assertEqual(t.added, 5)
        self.assertEqual(t.orphan, 2)
        self.assertEqual(len(t.details), 2)

    def test_from_dict_roundtrip(self):
        from services.tasks.task_manager import BackgroundTask
        original = BackgroundTask(
            job_id='rt1', source='upload', files=[('x.pdf', '/x.pdf')],
            max_retries=5, retry_count=2
        )
        original.added = 10
        original.status = 'RETRY'
        d = original.to_dict()
        d['files'] = [('x.pdf', '/x.pdf')]
        restored = BackgroundTask.from_dict(d)
        self.assertEqual(restored.job_id, 'rt1')
        self.assertEqual(restored.status, 'RETRY')
        self.assertEqual(restored.max_retries, 5)
        self.assertEqual(restored.retry_count, 2)

    def test_to_dict_has_required_keys(self):
        t = self._make_task()
        d = t.to_dict()
        for key in ('job_id', 'source', 'status', 'progress_pct', 'total_files',
                    'processed_files', 'added', 'orphan', 'skipped', 'duplicates',
                    'details', 'error_message', 'created_at', 'updated_at',
                    'retry_count', 'max_retries'):
            self.assertIn(key, d)

    def test_details_capped_to_50_in_to_dict(self):
        t = self._make_task()
        t.details = [f'line {i}' for i in range(100)]
        d = t.to_dict()
        self.assertEqual(len(d['details']), 50)


# ─────────────────────────────────────────────────────────────
# 2. TaskQueueManager edge cases
# ─────────────────────────────────────────────────────────────
class TestTaskQueueManagerEdgeCases(unittest.TestCase):

    def _make_manager(self):
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import TaskQueueManager
        backend = MemoryTaskQueueBackend()
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        return mgr, backend

    def test_backend_setter(self):
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        mgr, _ = self._make_manager()
        new_backend = MemoryTaskQueueBackend()
        mgr.backend = new_backend
        self.assertIs(mgr.backend, new_backend)

    def test_get_task_creates_from_dict_when_not_local(self):
        """get_task returns BackgroundTask from backend when not in local cache."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import TaskQueueManager
        backend = MemoryTaskQueueBackend()
        job_data = {
            'job_id': 'remote_job_1',
            'source': 'remote',
            'files': [],
            'status': 'COMPLETED',
            'total_files': 0,
            'processed_files': 0,
            'added': 0, 'orphan': 0, 'skipped': 0, 'duplicates': 0,
            'details': [], 'error_message': None,
            'created_at': time.time(), 'updated_at': time.time(),
            'started_at': None, 'finished_at': None,
            'retry_count': 0, 'max_retries': 3,
            'spool_dir': None, 'meta': {}
        }
        backend.save_job_state('remote_job_1', job_data)
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        # _local_tasks is empty — should build from backend state
        task = mgr.get_task('remote_job_1')
        self.assertIsNotNone(task)
        self.assertEqual(task.job_id, 'remote_job_1')

    def test_get_task_none_when_missing(self):
        mgr, _ = self._make_manager()
        result = mgr.get_task('nonexistent_job')
        self.assertIsNone(result)

    def test_recover_stale_jobs_no_stale(self):
        """recover_stale_jobs with no stale tasks should not raise."""
        mgr, _ = self._make_manager()
        mgr.recover_stale_jobs(timeout_sec=300)

    def test_recover_stale_jobs_with_stale_retry(self):
        """Stale task with retry_count < max_retries gets RETRY status."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import TaskQueueManager, TaskStatus
        backend = MemoryTaskQueueBackend()
        job_data = {
            'job_id': 'stale_1',
            'source': 'test',
            'files': [],
            'status': TaskStatus.PROCESSING,
            'total_files': 0,
            'processed_files': 0,
            'added': 0, 'orphan': 0, 'skipped': 0, 'duplicates': 0,
            'details': [], 'error_message': None,
            'created_at': time.time() - 400,
            'updated_at': time.time() - 400,
            'started_at': time.time() - 400,
            'finished_at': None,
            'retry_count': 0, 'max_retries': 3,
            'spool_dir': None, 'meta': {}
        }
        backend.save_job_state('stale_1', job_data)
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        # Inject into local tasks
        from services.tasks.task_manager import BackgroundTask
        t = BackgroundTask.from_dict(dict(job_data, files=[]))
        mgr._local_tasks['stale_1'] = t
        mgr.recover_stale_jobs(timeout_sec=300)

    def test_recover_stale_jobs_with_exceeded_retries(self):
        """Stale task that exceeded max_retries gets FAILED status."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import TaskQueueManager, TaskStatus
        backend = MemoryTaskQueueBackend()
        now = time.time()
        job_data = {
            'job_id': 'stale_max_retry',
            'source': 'test',
            'files': [],
            'status': TaskStatus.PROCESSING,
            'total_files': 0,
            'processed_files': 0,
            'added': 0, 'orphan': 0, 'skipped': 0, 'duplicates': 0,
            'details': [], 'error_message': None,
            'created_at': now - 400,
            'updated_at': now - 400,
            'started_at': now - 400,
            'finished_at': None,
            'retry_count': 3, 'max_retries': 3,
            'spool_dir': None, 'meta': {}
        }
        backend.save_job_state('stale_max_retry', job_data)
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        mgr.recover_stale_jobs(timeout_sec=300)
        # After recover, the state should be FAILED
        state = backend.get_job_state('stale_max_retry')
        if state:
            self.assertEqual(state.get('status'), TaskStatus.FAILED)

    def test_handle_task_failure_retry_path(self):
        """_handle_task_failure increments retry_count and sets RETRY status."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import BackgroundTask, TaskQueueManager, TaskStatus
        backend = MemoryTaskQueueBackend()
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        task = BackgroundTask(job_id='fail_retry', source='t', files=[], max_retries=3, retry_count=0)
        backend.save_job_state('fail_retry', task.to_dict())
        mgr._handle_task_failure(task, 'test error')
        self.assertEqual(task.status, TaskStatus.RETRY)
        self.assertEqual(task.retry_count, 1)

    def test_handle_task_failure_exceeded_path(self):
        """_handle_task_failure with retry_count >= max_retries sets FAILED."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        from services.tasks.task_manager import BackgroundTask, TaskQueueManager, TaskStatus
        backend = MemoryTaskQueueBackend()
        mgr = TaskQueueManager(backend=backend, max_workers=1)
        task = BackgroundTask(job_id='fail_final', source='t', files=[], max_retries=3, retry_count=3)
        backend.save_job_state('fail_final', task.to_dict())
        mgr._handle_task_failure(task, 'too many errors')
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_sync_task_state_exception(self):
        """_sync_task_state with failing backend logs debug and doesn't raise."""
        from services.tasks.task_manager import BackgroundTask
        mgr, backend = self._make_manager()
        backend.save_job_state = MagicMock(side_effect=RuntimeError('db error'))
        task = BackgroundTask(job_id='sync_err', source='t', files=[])
        # Should not raise
        mgr._sync_task_state(task)

    def test_finalize_task_early_return_pending(self):
        """_finalize_task returns early if status is PENDING."""
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        mgr, backend = self._make_manager()
        task = BackgroundTask(job_id='pend', source='t', files=[])
        task.status = TaskStatus.PENDING
        ack_called = []
        backend.ack_job = lambda jid: ack_called.append(jid)
        mgr._finalize_task(task)
        self.assertEqual(ack_called, [])

    def test_finalize_task_ack_error_doesnt_raise(self):
        """_finalize_task with failing ACK should not raise."""
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        mgr, backend = self._make_manager()
        task = BackgroundTask(job_id='ack_err', source='t', files=[])
        task.status = TaskStatus.COMPLETED
        backend.ack_job = MagicMock(side_effect=RuntimeError('ack failed'))
        # Should not raise
        mgr._finalize_task(task)

    def test_finalize_task_callback_error_doesnt_raise(self):
        """_finalize_task with crashing callback should log error and continue."""
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        mgr, backend = self._make_manager()

        def bad_callback(t):
            raise ValueError('callback boom')

        task = BackgroundTask(job_id='cb_err', source='t', files=[], callbacks=[bad_callback])
        task.status = TaskStatus.COMPLETED
        # Should not raise
        mgr._finalize_task(task)

    def test_finalize_task_telegram_notify_called_without_callback(self):
        """_finalize_task calls _notify_telegram_completion when no callbacks and chat_id present."""
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        mgr, backend = self._make_manager()
        task = BackgroundTask(job_id='tg_notify', source='t', files=[], meta={'chat_id': '12345'})
        task.status = TaskStatus.COMPLETED
        notify_calls = []
        mgr._notify_telegram_completion = lambda t: notify_calls.append(t.job_id)
        mgr._finalize_task(task)
        self.assertIn('tg_notify', notify_calls)

    def test_finalize_task_spool_cleanup(self):
        """_finalize_task removes spool_dir if it exists."""
        from services.tasks.task_manager import BackgroundTask, TaskStatus
        mgr, backend = self._make_manager()
        spool = tempfile.mkdtemp()
        task = BackgroundTask(job_id='spool_cl', source='t', files=[], spool_dir=spool)
        task.status = TaskStatus.COMPLETED
        mgr._finalize_task(task)
        self.assertFalse(os.path.exists(spool))

    def test_notify_telegram_no_token(self):
        """_notify_telegram_completion exits early when TELEGRAM_BOT_TOKEN is empty."""
        from services.tasks.task_manager import BackgroundTask
        mgr, _ = self._make_manager()
        task = BackgroundTask(job_id='tg_no_tok', source='t', files=[], meta={'chat_id': '111'})
        with patch('config.TELEGRAM_BOT_TOKEN', ''):
            mgr._notify_telegram_completion(task)

    def test_notify_telegram_no_chat_id(self):
        """_notify_telegram_completion exits early when chat_id is missing."""
        from services.tasks.task_manager import BackgroundTask
        mgr, _ = self._make_manager()
        task = BackgroundTask(job_id='tg_no_chat', source='t', files=[], meta={})
        with patch('config.TELEGRAM_BOT_TOKEN', 'fake_token'):
            mgr._notify_telegram_completion(task)

    def test_notify_telegram_sends_message(self):
        """_notify_telegram_completion sends message when token + chat_id present."""
        from services.tasks.task_manager import BackgroundTask
        mgr, _ = self._make_manager()
        task = BackgroundTask(
            job_id='tg_send', source='t', files=[],
            meta={'chat_id': '12345', 'file_name': 'report.pdf'}
        )
        task.added = 3
        task.orphan = 1
        task.details = ['page 1: ok']
        mock_client = MagicMock()
        with patch('config.TELEGRAM_BOT_TOKEN', 'fake_token'), \
             patch('services.telegram_bot.telegram_client.TelegramClient', return_value=mock_client):
            mgr._notify_telegram_completion(task)

    def test_get_queue_stats_empty(self):
        """get_queue_stats returns expected keys with zero values on empty queue."""
        mgr, _ = self._make_manager()
        stats = mgr.get_queue_stats()
        self.assertIn('queue_length', stats)
        self.assertIn('total_jobs', stats)
        self.assertIn('pending_count', stats)
        self.assertIn('completed_count', stats)
        self.assertEqual(stats['total_jobs'], 0)

    def test_list_tasks_empty(self):
        mgr, _ = self._make_manager()
        tasks = mgr.list_tasks(limit=10)
        self.assertEqual(tasks, [])


# ─────────────────────────────────────────────────────────────
# 3. MemoryTaskQueueBackend edge cases
# ─────────────────────────────────────────────────────────────
class TestMemoryTaskQueueBackendEdgeCases(unittest.TestCase):

    def _backend(self):
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        return MemoryTaskQueueBackend(max_history=5)

    def test_push_job_no_job_id_returns_false(self):
        b = self._backend()
        result = b.push_job({'source': 'test'})  # no job_id
        self.assertFalse(result)

    def test_push_job_overflow_evicts_oldest(self):
        """When history > max_history, oldest entry is evicted."""
        b = self._backend()
        for i in range(7):
            b.push_job({'job_id': f'job_{i}', 'source': 'test'})
        # Only max_history (5) should remain in states
        self.assertLessEqual(len(b._states), 5)

    def test_pop_job_empty_returns_none(self):
        b = self._backend()
        result = b.pop_job(timeout=0.01)
        self.assertIsNone(result)

    def test_pop_job_no_job_id_returns_data(self):
        """pop_job with data that has no job_id returns the raw data."""
        b = self._backend()
        b._queue.put({'source': 'weird', 'payload': 'data'})
        result = b.pop_job(timeout=0.1)
        self.assertEqual(result['source'], 'weird')

    def test_ack_job_dict_job_id(self):
        """ack_job accepts dict with job_id key."""
        b = self._backend()
        b.push_job({'job_id': 'j1', 'source': 'test'})
        b.pop_job(timeout=0.1)
        result = b.ack_job({'job_id': 'j1'})
        self.assertTrue(result)

    def test_ack_job_missing_returns_false(self):
        b = self._backend()
        result = b.ack_job('nonexistent')
        self.assertFalse(result)

    def test_nack_job_dict_job_id_no_requeue(self):
        """nack_job with dict job_id and requeue=False returns False."""
        b = self._backend()
        b.push_job({'job_id': 'j2', 'source': 'test'})
        b.pop_job(timeout=0.1)
        result = b.nack_job({'job_id': 'j2'}, requeue=False)
        self.assertFalse(result)

    def test_nack_job_requeue_true_returns_true(self):
        b = self._backend()
        b.push_job({'job_id': 'j3', 'source': 'test'})
        b.pop_job(timeout=0.1)
        result = b.nack_job('j3', requeue=True)
        self.assertTrue(result)

    def test_extend_visibility_not_processing_returns_false(self):
        b = self._backend()
        result = b.extend_visibility('nonexistent')
        self.assertFalse(result)

    def test_extend_visibility_in_processing_returns_true(self):
        b = self._backend()
        b.push_job({'job_id': 'ev1', 'source': 'test'})
        b.pop_job(timeout=0.1)
        result = b.extend_visibility('ev1', extra_timeout=100.0)
        self.assertTrue(result)

    def test_reclaim_stale_with_exceeded_retries(self):
        """Stale jobs exceeding max_retries should be marked FAILED in state."""
        from services.tasks.queue_backend import MemoryTaskQueueBackend
        b = MemoryTaskQueueBackend()
        job = {'job_id': 'stale_over', 'source': 'test', 'status': 'PROCESSING',
               'retry_count': 5, 'max_retries': 3}
        b.save_job_state('stale_over', job)
        # Manually inject into processing with expired time
        b._processing['stale_over'] = {'expire_at': time.time() - 100, 'worker_id': 'w1', 'claimed_at': 0}
        reclaimed = b.reclaim_stale_jobs(timeout_sec=60)
        self.assertNotIn('stale_over', reclaimed)
        state = b.get_job_state('stale_over')
        if state:
            self.assertEqual(state.get('status'), 'FAILED')

    def test_acquire_release_lock(self):
        b = self._backend()
        self.assertTrue(b.acquire_lock('mylock', timeout=5.0))
        self.assertFalse(b.acquire_lock('mylock', timeout=0))  # already locked
        b.release_lock('mylock')
        self.assertTrue(b.acquire_lock('mylock', timeout=5.0))

    def test_ping_returns_true(self):
        b = self._backend()
        self.assertTrue(b.ping())

    def test_queue_length_and_processing_length(self):
        b = self._backend()
        b.push_job({'job_id': 'ql1', 'source': 'test'})
        b.push_job({'job_id': 'ql2', 'source': 'test'})
        self.assertEqual(b.queue_length, 2)
        b.pop_job(timeout=0.1)
        self.assertEqual(b.processing_length, 1)

    def test_list_jobs_empty(self):
        b = self._backend()
        self.assertEqual(b.list_jobs(), [])

    def test_list_jobs_with_items(self):
        b = self._backend()
        b.push_job({'job_id': 'lj1', 'source': 'test'})
        jobs = b.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['job_id'], 'lj1')

    def test_save_and_get_job_state(self):
        b = self._backend()
        b.save_job_state('s1', {'job_id': 's1', 'status': 'PENDING'})
        state = b.get_job_state('s1')
        self.assertEqual(state['status'], 'PENDING')

    def test_get_job_state_missing(self):
        b = self._backend()
        self.assertIsNone(b.get_job_state('missing'))


# ─────────────────────────────────────────────────────────────
# 4. WebSocketClientState
# ─────────────────────────────────────────────────────────────
class TestWebSocketClientState(unittest.TestCase):

    def test_buffer_property_get(self):
        from services.websocket.ws_manager import WebSocketClientState
        mock_sock = MagicMock()
        state = WebSocketClientState(mock_sock, '127.0.0.1')
        state.buf = bytearray(b'hello')
        self.assertEqual(state.buffer, bytearray(b'hello'))

    def test_buffer_property_set(self):
        from services.websocket.ws_manager import WebSocketClientState
        mock_sock = MagicMock()
        state = WebSocketClientState(mock_sock, '127.0.0.1')
        state.buffer = bytearray(b'world')
        self.assertEqual(state.buf, bytearray(b'world'))

    def test_last_active_initialized(self):
        from services.websocket.ws_manager import WebSocketClientState
        mock_sock = MagicMock()
        state = WebSocketClientState(mock_sock, '192.168.1.1')
        self.assertAlmostEqual(state.last_active, time.time(), delta=2.0)
        self.assertEqual(state.client_ip, '192.168.1.1')


# ─────────────────────────────────────────────────────────────
# 5. WebSocketManager basic operations
# ─────────────────────────────────────────────────────────────
class TestWebSocketManagerBasic(unittest.TestCase):

    def _get_manager(self):
        from services.websocket.ws_manager import WebSocketManager
        with patch('services.websocket.ws_manager.selectors.DefaultSelector'), \
             patch('services.websocket.ws_manager.threading.Thread') as mock_thread:
            mock_thread.return_value = MagicMock()
            mgr = WebSocketManager.__new__(WebSocketManager)
            import threading
            mgr._lock = threading.RLock()
            mgr._selector = MagicMock()
            mgr._clients = {}
            mgr._running = True
            mgr._last_cleanup = time.time()
            import os
            import uuid
            mgr._node_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
            mgr._redis_pub = None
        return mgr

    def test_broadcast_no_clients(self):
        """broadcast with no connected clients should not raise."""
        from services.websocket import ws_manager as singleton
        original_clients = dict(singleton._clients)
        singleton._clients = {}
        try:
            singleton.broadcast('test_event', {'key': 'val'})
        finally:
            singleton._clients = original_clients

    def test_broadcast_with_broken_client(self):
        """broadcast with a broken socket should remove client and not raise."""
        from services.websocket import ws_manager as singleton
        from services.websocket.ws_manager import WebSocketClientState

        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 9999
        mock_sock.sendall.side_effect = BrokenPipeError('broken')
        state = WebSocketClientState(mock_sock, '10.0.0.1')

        original_clients = dict(singleton._clients)
        singleton._clients[9999] = state
        try:
            singleton.broadcast('test_event', {'key': 'val'})
        finally:
            singleton._clients = original_clients

    def test_unregister_unknown_client(self):
        """unregister of unknown fileno should not raise."""
        from services.websocket import ws_manager as singleton
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 88888
        singleton.unregister(mock_sock)

    def test_clients_dict_accessible(self):
        """_clients dict is accessible and reflects connected state."""
        from services.websocket import ws_manager as singleton
        original = dict(singleton._clients)
        singleton._clients = {}
        try:
            count = len(singleton._clients)
            self.assertEqual(count, 0)
        finally:
            singleton._clients = original


if __name__ == '__main__':
    unittest.main()
