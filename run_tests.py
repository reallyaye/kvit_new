import os, sys, tempfile, shutil, sqlite3, traceback
import config

# Fallback pytest fixture для работы без установленного пакета pytest
class _MockPytest:
    @staticmethod
    def fixture(fn=None, *args, **kwargs):
        if fn and callable(fn): return fn
        return lambda f: f

import builtins
sys.modules['pytest'] = _MockPytest()


def run_all():
    print("=" * 65)
    print("Запуск автоматических тестов...")
    print("=" * 65)

    passed = 0
    failed = 0

    # Создаем временную тестовую среду
    test_dir = tempfile.mkdtemp(prefix="kvit_test_run_")
    db_file = os.path.join(test_dir, "test.sqlite3")
    receipts_dir = os.path.join(test_dir, "receipts")
    os.makedirs(receipts_dir, exist_ok=True)

    config.DB = db_file
    config.RECEIPTS_DIR = receipts_dir
    config.GRPC_API_KEY = "test_secure_grpc_key_for_testing"
    config.ADMIN_PASSWORD = "admin"

    import services.pdf.pdf_processor
    import services.receipts.receipt_service
    services.pdf.pdf_processor.RECEIPTS_DIR = receipts_dir
    services.receipts.receipt_service.RECEIPTS_DIR = receipts_dir

    def reset_db():
        con = sqlite3.connect(db_file)
        con.executescript('''
            DROP TABLE IF EXISTS receipts;
            DROP TABLE IF EXISTS accounts;
            CREATE TABLE accounts(
                id INTEGER PRIMARY KEY,
                account_number TEXT NOT NULL UNIQUE,
                customer_name TEXT,
                address TEXT,
                street TEXT,
                building TEXT,
                corpus TEXT,
                district TEXT,
                organization TEXT
            );
            CREATE INDEX idx_accounts_account ON accounts(account_number);
            CREATE INDEX idx_accounts_address ON accounts(address);

            CREATE TABLE receipts(
                id INTEGER PRIMARY KEY,
                account_number TEXT NOT NULL,
                period TEXT NOT NULL,
                pdf_file TEXT NOT NULL,
                content_hash TEXT,
                access_token TEXT,
                address TEXT,
                UNIQUE(account_number, period)
            );
            CREATE INDEX idx_receipts_account_period ON receipts(account_number, period);
            CREATE INDEX idx_receipts_hash ON receipts(content_hash);
            CREATE INDEX idx_receipts_address ON receipts(address);
            CREATE UNIQUE INDEX idx_receipts_token ON receipts(access_token);

            CREATE TABLE IF NOT EXISTS app_sessions (
                token TEXT PRIMARY KEY,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON app_sessions(expires_at);

            CREATE TABLE IF NOT EXISTS security_blocks (
                ip TEXT PRIMARY KEY,
                blocked_until REAL NOT NULL,
                reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_blocks_until ON security_blocks(blocked_until);
        ''')
        con.commit()
        con.close()

    # 1. test_security
    from tests import test_security
    reset_db()
    for fn_name in ['test_auth_service_lifecycle', 'test_auth_service_concurrency', 'test_rate_limiter_sliding_window', 'test_ip_throttler_concurrency_and_burst', 'test_client_ip_anti_spoofing', 'test_safe_import_path_protection', 'test_grpc_rate_limiting_and_security', 'test_async_websocket_multiplexer', 'test_concurrent_database_writes_with_retry', 'test_persistent_state_and_session_sharing']:
        try:
            getattr(test_security, fn_name)()
            print(f"  [OK] test_security.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_security.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 2. test_pdf_processor
    from tests import test_pdf_processor
    for fn_name in ['test_pdf_processor_extract_and_save', 'test_pdf_processor_address_extraction', 'test_pdf_processor_idempotency_and_duplicates', 'test_pdf_processor_missing_account', 'test_streaming_multipart_parser', 'test_pdf_processor_flexible_patterns_and_diagnostics', 'test_pdf_processor_multipage_receipt_grouping', 'test_pdf_processor_sharding_helpers', 'test_pdf_processor_ocr_fallback_and_handling', 'test_migrate_receipts_to_sharding']:
        try:
            reset_db()
            import pathlib
            # Check if function accepts arguments
            import inspect
            sig = inspect.signature(getattr(test_pdf_processor, fn_name))
            if len(sig.parameters) > 0:
                getattr(test_pdf_processor, fn_name)(pathlib.Path(test_dir))
            else:
                getattr(test_pdf_processor, fn_name)()
            print(f"  [OK] test_pdf_processor.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_pdf_processor.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1


    # 3. test_receipt_service
    from tests import test_receipt_service
    for fn_name in ['test_get_account', 'test_get_receipts', 'test_get_pdf_by_token_valid', 'test_get_pdf_by_token_invalid_or_traversal', 'test_get_pdf_by_token_sharded', 'test_search_accounts_by_address', 'test_search_account_by_specific_address', 'test_privacy_search_view_no_personal_data', 'test_search_by_exact_receipt_address']:
        try:
            reset_db()
            import pathlib
            import inspect
            sig = inspect.signature(getattr(test_receipt_service, fn_name))
            if len(sig.parameters) > 0:
                fixture_res = test_receipt_service.seed_receipt_data(pathlib.Path(test_dir))
                getattr(test_receipt_service, fn_name)(fixture_res)
            else:
                getattr(test_receipt_service, fn_name)()
            print(f"  [OK] test_receipt_service.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_receipt_service.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 4. test_reconcile_service
    from tests import test_reconcile_service
    for fn_name in ['test_reconcile_metrics', 'test_reconcile_filter_without', 'test_reconcile_filter_orphans', 'test_reconcile_with_period_filter']:
        try:
            reset_db()
            test_reconcile_service.seed_reconcile_data()
            getattr(test_reconcile_service, fn_name)(None)
            print(f"  [OK] test_reconcile_service.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_reconcile_service.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 5. test_audit_comprehensive (Глубокий независимый аудит)
    from tests import test_audit_comprehensive
    for fn_name in [
        'test_audit_multipart_parser_edge_cases',
        'test_audit_reconcile_service_pagination_and_multiperiod',
        'test_audit_sharding_and_security_traversal',
        'test_audit_pdf_processor_corrupt_and_edge_cases',
        'test_audit_auth_and_throttler_concurrency',
        'test_audit_websocket_frames_and_multiplexing'
    ]:
        try:
            reset_db()
            import pathlib, inspect
            sig = inspect.signature(getattr(test_audit_comprehensive, fn_name))
            if len(sig.parameters) > 0:
                getattr(test_audit_comprehensive, fn_name)(pathlib.Path(test_dir))
            else:
                getattr(test_audit_comprehensive, fn_name)()
            print(f"  [OK] test_audit_comprehensive.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_audit_comprehensive.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    shutil.rmtree(test_dir, ignore_errors=True)

    print("=" * 65)
    print(f"ИТОГИ: Успешно: {passed}, Провалено: {failed}")
    print("=" * 65)
    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    run_all()
