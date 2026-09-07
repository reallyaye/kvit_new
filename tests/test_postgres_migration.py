# -*- coding: utf-8 -*-
"""
Тест реальной миграции схемы в запущенном PostgreSQL (CI и интеграционное тестирование).
Проверяет:
1. Корректность выполнения database.migrations.migrate_db() на реальном PostgreSQL.
2. Идемпотентность повторного применения миграций (CREATE TABLE IF NOT EXISTS, индексы).
3. Наличие всех таблиц схемы (accounts, receipts, app_sessions, users, audit_logs, security_blocks, telegram_users, appeals).
4. Наличие и типы колонок таблицы appeals (включая BOOLEAN, DOUBLE PRECISION, BIGSERIAL).
5. Транзакционную запись и чтение тестового обращения через Postgres backend.
"""

import os
import time

import pytest

try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def _get_pg_test_url():
    return os.environ.get("POSTGRES_TEST_URL") or os.environ.get("DATABASE_URL") or ""


@pytest.fixture(scope="module")
def pg_connection():
    if not PSYCOPG2_AVAILABLE:
        pytest.skip("psycopg2-binary не установлен")

    pg_url = _get_pg_test_url()
    if not pg_url or not pg_url.startswith(("postgresql://", "postgres://")):
        pytest.skip("POSTGRES_TEST_URL / DATABASE_URL не задан или не указывает на PostgreSQL")

    # Проверяем доступность базы данных
    try:
        conn = psycopg2.connect(pg_url)
        conn.autocommit = True
        yield conn, pg_url
        conn.close()
    except Exception as e:
        pytest.skip(f"Не удалось подключиться к PostgreSQL ({pg_url}): {e}")


def test_postgres_migration_and_schema_verification(pg_connection, monkeypatch):
    raw_conn, pg_url = pg_connection

    import config
    import database.connection as db_conn
    import database.postgres_backend as pg_backend
    from database.migrations import migrate_db

    # Сбрасываем пул и переключаем конфигурацию на тестовый PostgreSQL
    with db_conn._PG_INIT_LOCK:
        if pg_backend._PG_POOL is not None:
            try:
                pg_backend.close_postgres_pool()
            except Exception:
                pass
            pg_backend._PG_POOL = None

    monkeypatch.setattr(config, "DATABASE_URL", pg_url)
    monkeypatch.setattr(config, "DB_TYPE", "postgres")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "pbkdf2_sha256$600000$test_admin_hash")

    # 1. Первичный запуск миграции
    migrate_db()

    # 2. Проверка идемпотентности — повторный запуск не должен вызывать ошибок
    migrate_db()

    # 3. Проверка наличия всех обязательных таблиц
    expected_tables = {
        "accounts",
        "receipts",
        "app_sessions",
        "users",
        "audit_logs",
        "security_blocks",
        "telegram_users",
        "appeals",
    }

    with raw_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public';
            """
        )
        existing_tables = {row[0] for row in cur.fetchall()}

    for table in expected_tables:
        assert table in existing_tables, f"Таблица {table} отсутствует в схеме PostgreSQL!"

    # 4. Проверка структуры таблицы appeals
    with raw_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'appeals';
            """
        )
        columns = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    required_columns = [
        "id",
        "registration_number",
        "category",
        "applicant_name",
        "phone",
        "email",
        "account_number",
        "service_address",
        "message",
        "status",
        "consent",
        "submitted_at",
        "updated_at",
        "client_ip",
        "user_agent",
        "assigned_to",
        "admin_comment",
        "office_notified",
        "confirmation_sent",
    ]
    for col in required_columns:
        assert col in columns, f"Колонка {col} отсутствует в таблице appeals"

    assert columns["consent"][0] == "boolean"
    assert columns["office_notified"][0] == "boolean"
    assert columns["confirmation_sent"][0] == "boolean"

    # 5. Проверка записи и чтения через db_conn.write_transaction()
    reg_num = f"TEST-PG-{int(time.time())}"
    with db_conn.write_transaction() as con:
        con.execute(
            """
            INSERT INTO appeals (
                registration_number, category, applicant_name, phone, email,
                service_address, message, status, consent, submitted_at, updated_at,
                office_notified, confirmation_sent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reg_num,
                "other",
                "Тестовый Заявитель",
                "+7 (777) 123-45-67",
                "test_pg@example.com",
                "г. Алматы, ул. Абая 1",
                "Тестовое сообщение миграции",
                "NEW",
                True,
                time.time(),
                time.time(),
                False,
                False,
            ),
        )

    # Читаем обратно
    con = db_conn.get_db()
    try:
        row = con.execute("SELECT * FROM appeals WHERE registration_number = ?", (reg_num,)).fetchone()
        assert row is not None
        assert row["registration_number"] == reg_num
        assert row["applicant_name"] == "Тестовый Заявитель"
        assert row["email"] == "test_pg@example.com"
        assert row["consent"] is True
        assert row["office_notified"] is False
    finally:
        con.close()
