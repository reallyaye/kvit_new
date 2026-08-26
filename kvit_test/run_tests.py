import os
import shutil
import sqlite3
import sys
import tempfile
import traceback

import config


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
    config.SECRET_KEY = "test_secure_secret_key_for_testing"
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
            DROP TABLE IF EXISTS telegram_users;
        ''')
        con.commit()
        con.close()
        from database import migrate_db
        migrate_db()

    # 1. test_security
    from tests import test_security
    reset_db()
    for fn_name in ['test_auth_service_lifecycle', 'test_auth_service_concurrency', 'test_rate_limiter_sliding_window', 'test_ip_throttler_concurrency_and_burst', 'test_client_ip_anti_spoofing', 'test_safe_import_path_protection', 'test_grpc_rate_limiting_and_security', 'test_async_websocket_multiplexer', 'test_concurrent_database_writes_with_retry', 'test_persistent_state_and_session_sharing', 'test_session_store_db_failure_policies', 'test_env_crypto_encode_decode', 'test_database_migration_fail_fast', 'test_postgres_backend_wrapper_and_dialect', 'test_cookie_secure_flags_and_scheme_detection', 'test_csrf_token_lifecycle_and_validation', 'test_all_admin_endpoints_auth_and_csrf_matrix', 'test_validate_safe_path_canonicalization_and_traversal']:
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
    for fn_name in ['test_pdf_processor_extract_and_save', 'test_pdf_processor_address_extraction', 'test_pdf_processor_idempotency_and_duplicates', 'test_pdf_processor_missing_account', 'test_streaming_multipart_parser', 'test_pdf_processor_flexible_patterns_and_diagnostics', 'test_pdf_processor_multipage_receipt_grouping', 'test_pdf_processor_sharding_helpers', 'test_pdf_processor_ocr_fallback_and_handling', 'test_pdf_processor_ocr_budget_and_dos_protection', 'test_migrate_receipts_to_sharding', 'test_pdf_processor_file_vs_semantic_hash', 'test_atomic_importer_2phase_commit_and_rollback', 'test_pdf_processor_account_period_conflict_and_no_orphan_files']:
        try:
            reset_db()
            # Check if function accepts arguments
            import inspect
            import pathlib
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
    for fn_name in ['test_get_account', 'test_get_receipts', 'test_get_pdf_by_token_valid', 'test_get_pdf_by_token_invalid_or_traversal', 'test_get_pdf_by_token_sharded', 'test_search_accounts_by_address', 'test_search_account_by_specific_address', 'test_privacy_search_view_no_personal_data', 'test_search_by_exact_receipt_address', 'test_api_stats_live_polling', 'test_search_by_structured_and_compound_address', 'test_fuzzy_street_match_and_typo_correction', 'test_api_search_endpoint']:
        try:
            reset_db()
            import inspect
            import pathlib
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
    for fn_name in ['test_reconcile_metrics', 'test_reconcile_filter_without', 'test_reconcile_filter_orphans', 'test_reconcile_with_period_filter', 'test_safe_sync_and_purge_lifecycle']:
        try:
            reset_db()
            if fn_name == 'test_safe_sync_and_purge_lifecycle':
                class DummyMonkeyPatch:
                    def setattr(self, obj, name, val):
                        setattr(obj, name, val)
                test_reconcile_service.test_safe_sync_and_purge_lifecycle(test_dir, DummyMonkeyPatch())
            else:
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
        'test_audit_websocket_frames_and_multiplexing',
        'test_application_level_resource_limits'
    ]:
        try:
            reset_db()
            import inspect
            import pathlib
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
        'test_bot_upload_pdf_receipt_flow',
        'test_bot_user_registration_and_admin_approval_lifecycle',
        'test_bot_admin_user_management_commands'
    ]:
        try:
            reset_db()
            import inspect
            import pathlib
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

    # 8. test_portal (Тесты портала и реестра документов)
    from tests import test_portal
    for fn_name in [
        'test_portal_pages_loaded',
        'test_documents_registry_loaded',
        'test_render_home_page',
        'test_render_contacts_page',
        'test_render_document_invest',
        'test_render_document_iframe_ktp',
        'test_render_404',
        'test_render_zakup_page',
        'test_health_and_readiness_probes'
    ]:
        try:
            getattr(test_portal, fn_name)()
            print(f"  [OK] test_portal.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_portal.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 9. test_portal_cms (CMS, Медиа-менеджер, Безопасность и Редактор)
    from tests import test_portal_cms
    for fn_name in [
        'test_portal_cms_list_and_get_pages',
        'test_portal_cms_save_and_delete_page',
        'test_portal_cms_media_save_and_delete',
        'test_portal_cms_documents_lifecycle',
        'test_admin_bar_rendering',
        'test_admin_cms_security_access'
    ]:
        try:
            getattr(test_portal_cms, fn_name)()
            print(f"  [OK] test_portal_cms.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_portal_cms.{fn_name}: {e}")
            traceback.print_exc()
            failed += 1

    # 10. test_tasks (Менеджер асинхронных фоновых задач обработки PDF)
    from tests import test_tasks
    import pathlib
    for fn_name in [
        'test_task_manager_submit_and_completion',
        'test_task_manager_get_and_list',
        'test_task_manager_error_isolation'
    ]:
        try:
            reset_db()
            import inspect
            sig = inspect.signature(getattr(test_tasks, fn_name))
            if len(sig.parameters) > 0:
                getattr(test_tasks, fn_name)(pathlib.Path(test_dir))
            else:
                getattr(test_tasks, fn_name)()
            print(f"  [OK] test_tasks.{fn_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] test_tasks.{fn_name}: {e}")
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
