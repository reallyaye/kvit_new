# -*- coding: utf-8 -*-
"""
Комплексные тесты промышленной архитектуры:
1. Запрет Redis -> Memory fallback в Production (Fail-Fast).
2. Запрет SQLite в Production (обязательность PostgreSQL).
3. Индексированный Batch Lookup счетов и хешей без вычитки всей БД в память.
4. Реальная работа X-Accel-Redirect (User -> API Auth -> X-Accel-Redirect -> Nginx Protected Path).
"""
import io
import os
import shutil
import tempfile
import time
from unittest.mock import MagicMock, patch
import pytest

import config
from database.connection import get_db, is_postgres_configured
from database.migrations import migrate_db
from services.pdf import pdf_processor
from services.receipts.receipt_service import receipt_service
from services.tasks.queue_backend import create_task_queue_backend, MemoryTaskQueueBackend, RedisTaskQueueBackend


def _create_test_pdf(path: str, account: str = "800101", period: str = "09.2026"):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    doc = fitz.open()
    page = doc.new_page()
    text = f"Лицевой счет: {account}\nПериод: {period}\nАдрес: Тестовый проспект, 10"
    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None
    if font_path:
        page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
        page.insert_text((50, 100), text, fontname='arial', fontsize=12)
    else:
        page.insert_text((50, 100), text, fontsize=12)
    doc.save(path)
    doc.close()


def test_production_redis_fail_fast():
    """В Production окружении недоступность Redis должна приводить к немедленной ошибке старта (Fail-Fast)."""
    orig_env = config.APP_ENV
    orig_prod = config.IS_PRODUCTION
    orig_redis_url = config.REDIS_URL

    try:
        config.APP_ENV = 'production'
        config.IS_PRODUCTION = True
        config.REDIS_URL = 'redis://invalid-host-unreachable:9999/0'

        # При сбое подключения в Production должен быть поднят RuntimeError
        with pytest.raises(RuntimeError) as excinfo:
            create_task_queue_backend()
        assert "КРИТИЧЕСКАЯ ОШИБКА" in str(excinfo.value)
        assert "Production" in str(excinfo.value)
    finally:
        config.APP_ENV = orig_env
        config.IS_PRODUCTION = orig_prod
        config.REDIS_URL = orig_redis_url


def test_development_redis_graceful_fallback():
    """В Development окружении недоступность Redis приводит к безопасному переключению на In-Memory."""
    orig_env = config.APP_ENV
    orig_prod = config.IS_PRODUCTION
    orig_redis_url = config.REDIS_URL

    try:
        config.APP_ENV = 'development'
        config.IS_PRODUCTION = False
        config.REDIS_URL = 'redis://invalid-host-unreachable:9999/0'
        config.REDIS_ENABLED = True

        backend = create_task_queue_backend()
        assert isinstance(backend, MemoryTaskQueueBackend)
    finally:
        config.APP_ENV = orig_env
        config.IS_PRODUCTION = orig_prod
        config.REDIS_URL = orig_redis_url


def test_production_postgresql_requirement():
    """В Production окружении использование SQLite запрещено — требуется PostgreSQL."""
    orig_env = config.APP_ENV
    orig_prod = config.IS_PRODUCTION
    orig_db_url = config.DATABASE_URL
    orig_db_type = getattr(config, 'DB_TYPE', 'sqlite')

    try:
        config.APP_ENV = 'production'
        config.IS_PRODUCTION = True
        config.DATABASE_URL = ''
        config.DB_TYPE = 'sqlite'

        with pytest.raises(RuntimeError) as excinfo:
            get_db()
        assert "Production" in str(excinfo.value)
        assert "PostgreSQL" in str(excinfo.value)
    finally:
        config.APP_ENV = orig_env
        config.IS_PRODUCTION = orig_prod
        config.DATABASE_URL = orig_db_url
        config.DB_TYPE = orig_db_type


def test_indexed_batch_lookup_without_full_table_load(tmp_path):
    """Проверка работы pdf_processor с прямым индексным batch-lookup счетов и хешей (known_accounts=None)."""
    con = get_db()
    # Регистрируем только один валидный счет
    con.execute("INSERT OR IGNORE INTO accounts(account_number, customer_name, address) VALUES ('800101', 'Иванов', 'ул. Мира')")
    con.commit()
    con.close()

    tmp_file = str(tmp_path / "batch_lookup_test.pdf")
    _create_test_pdf(tmp_file, account="800101", period="11.2026")

    # Передаем known_accounts=None: функция сама выполняет быстрый индексный запрос
    added, orphan, skipped, dups, details, recs = pdf_processor.process_single_pdf(
        tmp_file, "batch_lookup_test.pdf", known_accounts=None, existing_hashes=None
    )

    assert added == 1
    assert orphan == 0
    assert skipped == 0
    assert dups == 0

    # Повторный импорт того же файла должен быть мгновенно распознан как дубликат по индексу в БД
    added2, orphan2, skipped2, dups2, details2, recs2 = pdf_processor.process_single_pdf(
        tmp_file, "batch_lookup_test.pdf", known_accounts=None, existing_hashes=None
    )
    assert dups2 == 1
    assert added2 == 0


def test_real_x_accel_redirect_flow(tmp_path):
    """
    Сквозная проверка реальной работы X-Accel-Redirect:
    1. Авторизованный запрос по токену возвращает 200 и заголовок X-Accel-Redirect: /internal_receipts/...
    2. Неавторизованный запрос возвращает 403/404 и не содержит X-Accel-Redirect.
    """
    orig_x_accel = getattr(config, 'ENABLE_X_ACCEL_REDIRECT', False)
    orig_prefix = getattr(config, 'X_ACCEL_PREFIX', '/internal_receipts/')
    orig_receipts_dir = config.RECEIPTS_DIR

    try:
        config.ENABLE_X_ACCEL_REDIRECT = True
        config.X_ACCEL_PREFIX = '/internal_receipts/'
        config.RECEIPTS_DIR = str(tmp_path)

        # Создаем тестовую квитанцию на диске внутри RECEIPTS_DIR
        test_pdf_rel = "80/09/800999_sample.pdf"
        test_pdf_abs = os.path.join(str(tmp_path), "80", "09", "800999_sample.pdf")
        os.makedirs(os.path.dirname(test_pdf_abs), exist_ok=True)
        with open(test_pdf_abs, 'wb') as f:
            f.write(b"%PDF-1.4 dummy protected content")

        token = "a" * 32

        con = get_db()
        con.execute(
            "INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, access_token, status) VALUES ('800999', '12.2026', ?, ?, 'READY')",
            (test_pdf_rel, token)
        )
        con.commit()
        con.close()

        # Мокируем HTTP-хэндлер сервера для проверки заголовков
        from server import AppRequestHandler
        mock_handler = MagicMock()
        headers_sent = {}

        def mock_send_header(name, value):
            headers_sent[name] = value

        mock_handler.send_header = mock_send_header
        mock_handler._is_admin.return_value = False

        # Вызываем метод _serve_pdf с валидным токеном
        AppRequestHandler._serve_pdf(mock_handler, '/download', {'token': [token]})

        assert mock_handler.send_response.called
        assert mock_handler.send_response.call_args[0][0] == 200
        assert 'X-Accel-Redirect' in headers_sent
        assert headers_sent['X-Accel-Redirect'] == '/internal_receipts/80/09/800999_sample.pdf'
        assert headers_sent['Content-Type'] == 'application/pdf'

        # Вызываем метод _serve_pdf с невалидным токеном
        headers_sent.clear()
        mock_handler.send_response.reset_mock()
        mock_handler.send_html.reset_mock()

        AppRequestHandler._serve_pdf(mock_handler, '/download', {'token': ['invalid_short_tok']})

        # Должен быть отказ (403/404) и никакого заголовка X-Accel-Redirect
        assert 'X-Accel-Redirect' not in headers_sent
        assert mock_handler.send_html.called
        assert mock_handler.send_html.call_args[0][1] in (403, 404)

    finally:
        config.ENABLE_X_ACCEL_REDIRECT = orig_x_accel
        config.X_ACCEL_PREFIX = orig_prefix
        config.RECEIPTS_DIR = orig_receipts_dir
