import os
import sys
import tempfile
import shutil
import sqlite3
import traceback
import config
import builtins

# Fallback pytest fixture для работы без установленного пакета pytest
class _MockPytest:
    @staticmethod
    def fixture(fn=None, *args, **kwargs):
        if fn and callable(fn):
            return fn
        return lambda f: f

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
    from services.security.auth_service import hash_password
    config.ADMIN_PASSWORD_HASH = hash_password("admin")

    import services.pdf.pdf_processor
    import services.receipts.receipt_service
    services.pdf.pdf_processor.RECEIPTS_DIR = receipts_dir
    services.receipts.receipt_service.RECEIPTS_DIR = receipts_dir

    def reset_db():
        con = sqlite3.connect(db_file)
        con.executescript('''
            DROP TABLE IF EXISTS receipts;
            DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS app_sessions;
            DROP TABLE IF EXISTS security_blocks;
        ''')
        con.commit()
        con.close()
        from database import migrate_db
        migrate_db()

    # 1. test_security
    from tests import test_security
    reset_db()
    for fn_name in ['test_auth_service_lifecycle', 'test_auth_service_concurrency', 'test_rate_limiter_sliding_window', 'test_ip_throttler_concurrency_and_burst', 'test_client_ip_anti_spoofing', 'test_safe_import_path_protection', 'test_grpc_rate_limiting_and_security', 'test_async_websocket_multiplexer', 'test_concurrent_database_writes_with_retry', 'test_persistent_state_and_session_sharing', 'test_env_crypto_encode_decode', 'test_database_migration_fail_fast', 'test_postgres_backend_wrapper_and_dialect']:
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
    for fn_name in ['test_pdf_processor_extract_and_save', 'test_pdf_processor_address_extraction', 'test_pdf_processor_idempotency_and_duplicates', 'test_pdf_processor_missing_account', 'test_streaming_multipart_parser', 'test_pdf_processor_flexible_patterns_and_diagnostics', 'test_pdf_processor_multipage_receipt_grouping', 'test_pdf_processor_sharding_helpers', 'test_pdf_processor_ocr_fallback_and_handling', 'test_migrate_receipts_to_sharding', 'test_pdf_processor_file_vs_semantic_hash', 'test_atomic_importer_2phase_commit_and_rollback']:
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
    for fn_name in ['test_get_account', 'test_get_receipts', 'test_get_pdf_by_token_valid', 'test_get_pdf_by_token_invalid_or_traversal', 'test_get_pdf_by_token_sharded', 'test_search_accounts_by_address', 'test_search_account_by_specific_address', 'test_privacy_search_view_no_personal_data', 'test_search_by_exact_receipt_address', 'test_api_stats_live_polling']:
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
            seed_res = test_reconcile_service.seed_reconcile_data()
            getattr(test_reconcile_service, fn_name)(seed_res)
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
            import pathlib
            import inspect
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
    # 6. test_fuzzing (Фаззинг-тесты сетевых парсеров)
    from tests import test_fuzzing
    for fn_name in [
        'test_fuzz_multipart_random_mutations',
        'test_fuzz_multipart_giant_headers_and_path_traversal',
        'test_fuzz_websocket_frames_random_garbage',
        'test_fuzz_websocket_malicious_lengths_and_opcodes',
        'test_fuzz_websocket_fragmented_delivery'
    ]:
        try:
            reset_db()
            getattr(test_fuzzing, fn_name)()
            print(f"  [OK] test_fuzzing.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_fuzzing.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 7. test_telegram_bot (Тесты Telegram-бота)
    from tests import test_telegram_bot
    for fn_name in [
        'test_telegram_client_init_and_validation',
        'test_bot_authorization_flow',
        'test_bot_help_and_stats_commands',
        'test_bot_search_account_and_receipt',
        'test_bot_upload_pdf_receipt_flow'
    ]:
        try:
            reset_db()
            import pathlib
            import inspect
            sig = inspect.signature(getattr(test_telegram_bot, fn_name))
            if 'tmp_path' in sig.parameters:
                getattr(test_telegram_bot, fn_name)(pathlib.Path(test_dir))
            else:
                getattr(test_telegram_bot, fn_name)()
            print(f"  [OK] test_telegram_bot.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_telegram_bot.{fn_name}: {e}")
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
