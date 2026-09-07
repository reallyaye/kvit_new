import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import config
import server
import services.storage.pipeline as sp
from database.connection import get_db
from services.portal_search import (
    _clean_text,
    extract_snippet,
    highlight_term,
    render_global_search_page,
    search_portal_content,
)
from services.reconciliation.reconcile_service import reconcile_service
from services.storage.pipeline import storage_pipeline


class TestStoragePipelineBoost(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fake_receipts = os.path.join(self.temp_dir, "receipts")
        self.fake_spool = os.path.join(self.temp_dir, "spool")
        self.fake_proc = os.path.join(self.temp_dir, "processing")
        self.fake_failed = os.path.join(self.temp_dir, "failed")
        for p in (self.fake_receipts, self.fake_spool, self.fake_proc, self.fake_failed):
            os.makedirs(p, exist_ok=True)

        self._orig_cfg_dirs = (config.RECEIPTS_DIR, config.SPOOL_DIR, config.PROCESSING_DIR, config.FAILED_DIR)
        self._orig_sp_dirs = (sp.RECEIPTS_DIR, sp.SPOOL_DIR, sp.PROCESSING_DIR, sp.FAILED_DIR)

        config.RECEIPTS_DIR = self.fake_receipts
        config.SPOOL_DIR = self.fake_spool
        config.PROCESSING_DIR = self.fake_proc
        config.FAILED_DIR = self.fake_failed

        sp.RECEIPTS_DIR = self.fake_receipts
        sp.SPOOL_DIR = self.fake_spool
        sp.PROCESSING_DIR = self.fake_proc
        sp.FAILED_DIR = self.fake_failed

    def tearDown(self):
        config.RECEIPTS_DIR, config.SPOOL_DIR, config.PROCESSING_DIR, config.FAILED_DIR = self._orig_cfg_dirs
        sp.RECEIPTS_DIR, sp.SPOOL_DIR, sp.PROCESSING_DIR, sp.FAILED_DIR = self._orig_sp_dirs
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_move_to_processing_branches(self):
        job_id = "boost_job_1"
        src_file = os.path.join(self.temp_dir, "sample.pdf")
        with open(src_file, "w") as f:
            f.write("pdf-content")

        # 1. Normal move
        target = storage_pipeline.move_to_processing(src_file, job_id, "sample.pdf")
        self.assertTrue(os.path.exists(target))

        # 2. Same source and target path (line 60-61)
        same_target = storage_pipeline.move_to_processing(target, job_id, "sample.pdf")
        self.assertEqual(same_target, target)

        # 3. OSError on os.replace fallback to shutil.copy2
        src_file2 = os.path.join(self.temp_dir, "sample2.pdf")
        with open(src_file2, "w") as f:
            f.write("pdf-content-2")

        with patch("os.replace", side_effect=OSError("Cross-device link")):
            target2 = storage_pipeline.move_to_processing(src_file2, job_id, "sample2.pdf")
            self.assertTrue(os.path.exists(target2))
            self.assertFalse(os.path.exists(src_file2))

        # Cleanup
        storage_pipeline.cleanup_job(job_id)

    def test_commit_to_receipts_branches(self):
        staged = os.path.join(self.temp_dir, "staged.pdf")
        with open(staged, "w") as f:
            f.write("staged-receipt")

        # 1. Normal commit
        rel_path, abs_path = storage_pipeline.commit_to_receipts(staged, "123456789", "123456789_08.2026.pdf")
        self.assertTrue(os.path.exists(abs_path))
        self.assertTrue(rel_path.endswith("123456789_08.2026.pdf"))

        # 2. OSError on replace fallback to copy2
        staged2 = os.path.join(self.temp_dir, "staged2.pdf")
        with open(staged2, "w") as f:
            f.write("staged-receipt-2")

        with patch("os.replace", side_effect=OSError("Cross-device link")):
            rel_path2, abs_path2 = storage_pipeline.commit_to_receipts(staged2, "123456789", "123456789_09.2026.pdf")
            self.assertTrue(os.path.exists(abs_path2))

    def test_quarantine_failed_branches(self):
        bad_file = os.path.join(self.temp_dir, "corrupt.pdf")
        with open(bad_file, "w") as f:
            f.write("corrupt")

        job_id = "failed_job_1"
        # 1. Normal quarantine
        q_path = storage_pipeline.quarantine_failed(bad_file, job_id, "corrupt.pdf", "CRC mismatch")
        self.assertTrue(os.path.exists(q_path))
        meta_path = f"{q_path}.meta.json"
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path, "r", encoding="utf-8") as mf:
            data = json.load(mf)
            self.assertEqual(data["error"], "CRC mismatch")

        # 2. Quarantine move exception fallback
        bad_file2 = os.path.join(self.temp_dir, "corrupt2.pdf")
        with open(bad_file2, "w") as f:
            f.write("corrupt2")

        with patch("shutil.move", side_effect=Exception("Disk full")):
            q_path2 = storage_pipeline.quarantine_failed(bad_file2, job_id, "corrupt2.pdf", "Error 2")
            self.assertEqual(q_path2, bad_file2)

        # 3. Quarantine meta json write exception
        with patch("builtins.open", side_effect=PermissionError("Locked")):
            # should pass without uncaught error
            q_path3 = storage_pipeline.quarantine_failed(bad_file, job_id, "corrupt.pdf", "Error 3")
            self.assertIsNotNone(q_path3)

    def test_cleanup_job_branches(self):
        job_id = "cleanup_test_job"
        spool_dir = os.path.join(sp.SPOOL_DIR, job_id)
        proc_dir = os.path.join(sp.PROCESSING_DIR, job_id)
        os.makedirs(spool_dir, exist_ok=True)
        os.makedirs(proc_dir, exist_ok=True)

        with patch("shutil.rmtree", side_effect=Exception("File locked")):
            # handles exception gracefully
            storage_pipeline.cleanup_job(job_id)

        # Actual cleanup
        storage_pipeline.cleanup_job(job_id)
        self.assertFalse(os.path.exists(spool_dir))
        self.assertFalse(os.path.exists(proc_dir))


class TestReconcileServiceBoost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        con = get_db()
        try:
            con.execute("INSERT OR IGNORE INTO accounts (account_number, customer_name, address) VALUES ('88001', 'Алиев А.', 'ул. Абая, 1')")
            con.execute("INSERT OR IGNORE INTO accounts (account_number, customer_name, address) VALUES ('88002', 'Беков Б.', 'ул. Абая, 2')")
            con.execute("INSERT OR IGNORE INTO receipts (account_number, period, pdf_file) VALUES ('88001', '08.2026', 'receipts/88001.pdf')")
            con.execute("INSERT OR IGNORE INTO receipts (account_number, period, pdf_file) VALUES ('88099', '08.2026', 'receipts/88099.pdf')")
            con.commit()
        finally:
            con.close()

    def test_reconcile_with_period_filter_all(self):
        data = reconcile_service.get_reconciliation_data(filt='all', period_filter='08.2026', page_num=1, per_page=10)
        self.assertIn('rows', data)
        self.assertEqual(data['period_filter'], '08.2026')

    def test_reconcile_with_period_filter_without(self):
        data = reconcile_service.get_reconciliation_data(filt='without', period_filter='08.2026', page_num=1, per_page=10)
        self.assertIn('rows', data)
        self.assertEqual(data['filt'], 'without')

    def test_reconcile_with_period_filter_orphans(self):
        data = reconcile_service.get_reconciliation_data(filt='orphans', period_filter='08.2026', page_num=1, per_page=10)
        self.assertIn('rows', data)
        self.assertEqual(data['filt'], 'orphans')

    def test_reconcile_with_period_filter_with(self):
        data = reconcile_service.get_reconciliation_data(filt='with', period_filter='08.2026', page_num=1, per_page=10)
        self.assertIn('rows', data)
        self.assertEqual(data['filt'], 'with')

    def test_reconcile_invalid_filter_fallback(self):
        data = reconcile_service.get_reconciliation_data(filt='invalid_filter', period_filter='', page_num=1, per_page=10)
        self.assertIn('rows', data)


class TestPortalSearchBoost(unittest.TestCase):
    def test_clean_text_variations(self):
        self.assertEqual(_clean_text(""), "")
        html_input = "<script>alert(1)</script><style>body{color:red}</style><p>Hello &amp; <b>World</b></p>"
        cleaned = _clean_text(html_input)
        self.assertEqual(cleaned, "Hello & World")

    def test_highlight_term_variations(self):
        # Empty query
        self.assertEqual(highlight_term("Привет Мир", ""), "Привет Мир")
        # Single char query (len < 2)
        self.assertEqual(highlight_term("Привет Мир", "а"), "Привет Мир")
        # Normal match
        res = highlight_term("Тариф на электроэнергию", "тариф")
        self.assertIn("<mark", res)

    def test_extract_snippet_variations(self):
        # Short query
        s1 = extract_snippet("Очень длинный текст для сниппета", "а", max_chars=10)
        self.assertTrue(s1.endswith("..."))
        # No match query
        s2 = extract_snippet("Текст без искомого слова", "тариф", max_chars=10)
        self.assertTrue(s2.endswith("..."))
        # Matching query
        s3 = extract_snippet("Тарифы в нашем регионе обновлены", "тарифы", max_chars=50)
        self.assertIn("тариф", s3.lower())

    def test_search_portal_content_variations(self):
        # Empty query
        self.assertEqual(search_portal_content(""), [])
        self.assertEqual(search_portal_content("   "), [])
        # Short 1-char query fallback
        res_short = search_portal_content("а")
        self.assertIsInstance(res_short, list)
        # Search page & doc
        res_tarif = search_portal_content("тариф")
        self.assertGreater(len(res_tarif), 0)

    def test_render_global_search_page(self):
        html_empty = render_global_search_page("неизвестноеслово12345", [], is_admin=False)
        self.assertIn("Ничего не найдено", html_empty)

        results = search_portal_content("тариф")
        html_results = render_global_search_page("тариф", results, is_admin=True)
        self.assertIn("Результаты поиска по сайту", html_results)
        self.assertIn("Перейти в раздел", html_results)


class TestServerHandlersBoost(unittest.TestCase):
    def _create_handler(self, path="/", headers=None):
        req = MagicMock()
        client_address = ("127.0.0.1", 54321)
        server_obj = MagicMock()
        with patch.object(server.AppRequestHandler, "setup"), \
             patch.object(server.AppRequestHandler, "handle"), \
             patch.object(server.AppRequestHandler, "finish"):
            h = server.AppRequestHandler(req, client_address, server_obj)
        h.path = path
        h.headers = headers or {}
        h.rfile = MagicMock()
        h.wfile = MagicMock()
        h.send_response = MagicMock()
        h.send_header = MagicMock()
        h.end_headers = MagicMock()
        h.send_json = MagicMock()
        h.send_html = MagicMock()
        return h

    def test_api_stats_handler(self):
        h = self._create_handler("/api/stats")
        # without period
        h._handle_api_stats({})
        h.send_json.assert_called()
        self.assertEqual(h.send_json.call_args[0][1], 200)

        # with period
        h._handle_api_stats({'period': ['08.2026']})
        self.assertEqual(h.send_json.call_args[0][1], 200)

    def test_api_tasks_list_and_status(self):
        h = self._create_handler("/api/tasks")
        # Unauthorized (non-admin)
        with patch.object(h, "_is_admin", return_value=False):
            h._handle_api_tasks_list()
            self.assertEqual(h.send_json.call_args[0][1], 401)

            h._handle_api_task_status("job123")
            self.assertEqual(h.send_json.call_args[0][1], 401)

        # Admin, task not found
        with patch.object(h, "_is_admin", return_value=True), \
             patch.object(server.task_manager, "get_task", return_value=None):
            h._handle_api_task_status("job_missing")
            self.assertEqual(h.send_json.call_args[0][1], 404)

        # Admin, task found
        mock_task = MagicMock()
        mock_task.to_dict.return_value = {"job_id": "job_ok", "status": "completed"}
        with patch.object(h, "_is_admin", return_value=True), \
             patch.object(server.task_manager, "get_task", return_value=mock_task), \
             patch.object(server.task_manager, "list_tasks", return_value=[{"job_id": "job_ok"}]):
            h._handle_api_tasks_list()
            self.assertEqual(h.send_json.call_args[0][1], 200)

            h._handle_api_task_status("job_ok")
            self.assertEqual(h.send_json.call_args[0][1], 200)

    def test_api_sync_and_purge_receipts(self):
        h = self._create_handler("/api/sync-receipts")
        # 1. Non-admin
        with patch.object(h, "_is_admin", return_value=False):
            h._handle_api_sync_receipts()
            self.assertEqual(h.send_json.call_args[0][1], 401)

            h._handle_api_purge_missing_receipts()
            self.assertEqual(h.send_json.call_args[0][1], 401)

        # 2. Admin but invalid CSRF
        with patch.object(h, "_is_admin", return_value=True), \
             patch.object(h, "_verify_csrf", return_value=False):
            h._handle_api_sync_receipts()
            self.assertEqual(h.send_json.call_args[0][1], 403)

            h._handle_api_purge_missing_receipts()
            self.assertEqual(h.send_json.call_args[0][1], 403)

        # 3. Admin and valid CSRF
        with patch.object(h, "_is_admin", return_value=True), \
             patch.object(h, "_verify_csrf", return_value=True), \
             patch("server.sync_receipts_with_filesystem", return_value=(0, 0, 10)), \
             patch("server.purge_missing_receipts", return_value=5), \
             patch.object(server.ws_manager, "broadcast"):
            h._handle_api_sync_receipts()
            self.assertEqual(h.send_json.call_args[0][0]["success"], True)

            h._handle_api_purge_missing_receipts()
            self.assertEqual(h.send_json.call_args[0][0]["success"], True)
            self.assertEqual(h.send_json.call_args[0][0]["purged"], 5)


class TestTargetedBranchCoverageBoost(unittest.TestCase):
    def test_metrics_collector_endpoints(self):
        from services.metrics.collector import metrics_collector
        metrics_collector.record_request('GET', '/api/tasks/job_123', 200, 0.05)
        metrics_collector.record_request('GET', '/admin/pages/edit?slug=home', 200, 0.05)
        metrics_collector.record_request('GET', '/admin/documents/edit?key=ustav', 200, 0.05)
        self.assertIn('/api/tasks/:id', metrics_collector._requests_by_endpoint)
        self.assertIn('/admin/pages/edit', metrics_collector._requests_by_endpoint)
        self.assertIn('/admin/documents/edit', metrics_collector._requests_by_endpoint)

    def test_portal_layout_asset_v_fallback(self):
        from templates.portal_layout import _asset_v
        res = _asset_v('non_existent_file_xyz_12345.css')
        self.assertEqual(res, '20260903')

    def test_reconcile_views_pagination_edge_and_with_filter(self):
        from templates.reconcile_views import render_reconcile_page
        data = {
            'rows': [{'account_number': '123', 'customer_name': 'Test', 'address': 'Addr', 'period': '08.2026', 'pdf_file': '123.pdf'}],
            'page_num': 20,
            'total_pages': 20,
            'list_count': 200,
            'per_page': 10,
            'filt': 'with',
            'period_filter': '08.2026',
            'all_periods': [{'period': '08.2026'}],
            'total_accounts': 200,
            'total_receipts': 200,
            'matched': 200,
            'unmatched': 0,
            'orphans': 0,
            'role': 'admin',
            'username': 'admin'
        }
        html_out = render_reconcile_page(data)
        self.assertIn('Список лицевых счетов с квитанцией', html_out)

    def test_admin_cms_views_time_format_and_badges(self):
        from templates.admin_cms_views import (
            _format_audit_action_badge,
            render_admin_audit_log,
            render_admin_users,
            time_format,
            time_format_detailed,
        )
        self.assertEqual(time_format(None), '—')
        self.assertEqual(time_format(1e25), '—')
        self.assertEqual(time_format_detailed(None), '—')
        self.assertEqual(time_format_detailed(1e25), '—')

        badge = _format_audit_action_badge('UNKNOWN_CUSTOM_ACTION')
        self.assertIn('UNKNOWN_CUSTOM_ACTION', badge)

        users = [{'username': 'operator1', 'role': 'operator', 'is_active': 1, 'created_at': 1700000000, 'last_login': 1700000000}]
        users_html = render_admin_users(users, [], 'csrf_tok', current_username='admin')
        self.assertIn('Удалить', users_html)

        audit_html = render_admin_audit_log([], {'total': 0, 'actions': ['CUSTOM_NEW_ACTION']}, {}, 'csrf_tok')
        self.assertIn('CUSTOM_NEW_ACTION', audit_html)

    def test_atomic_importer_empty_batch(self):
        from services.pdf.atomic_importer import atomic_importer
        count, paths = atomic_importer.commit_staged_batch([])
        self.assertEqual(count, 0)
        self.assertEqual(paths, [])

    def test_rate_limiter_branches(self):
        import time

        import config
        from services.security.rate_limiter import rate_limiter

        # 1. Redis error in production
        with patch.object(config, 'IS_PRODUCTION', True), \
             patch.object(rate_limiter, '_get_redis', return_value=MagicMock()), \
             patch.object(rate_limiter, '_script', side_effect=Exception("Redis down")):
            allowed, retry, rem = rate_limiter.is_allowed("test", "ip", 10, 60)
            self.assertFalse(allowed)
            self.assertEqual(retry, 60)

        # 2. Redis is None in production
        with patch.object(config, 'IS_PRODUCTION', True), \
             patch.object(rate_limiter, '_get_redis', return_value=None):
            allowed, retry, rem = rate_limiter.is_allowed("test", "ip", 10, 60)
            self.assertFalse(allowed)

        # 3. Memory cleanup with timestamps older than 3600
        now = time.time()
        rate_limiter._buckets["cleanup_bucket"]["old_key"].append(now - 4000)
        rate_limiter._last_cleanup = now - 400
        allowed, retry, rem = rate_limiter.is_allowed("cleanup_bucket", "new_key", 10, 60)
        self.assertTrue(allowed)
        self.assertNotIn("old_key", rate_limiter._buckets["cleanup_bucket"])

    def test_database_connection_transaction_error_paths(self):
        import sqlite3

        from database.connection import write_transaction

        # 1. Non-busy sqlite error is raised directly
        with self.assertRaises(sqlite3.OperationalError):
            with write_transaction() as con:
                raise sqlite3.OperationalError("syntax error")

        # 2. Rollback exception is handled gracefully
        mock_con = MagicMock()
        mock_con.rollback.side_effect = Exception("rollback failed")
        with patch("database.connection.get_db", return_value=mock_con):
            with self.assertRaises(ValueError):
                with write_transaction() as con:
                    raise ValueError("boom")

