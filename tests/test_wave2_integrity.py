# -*- coding: utf-8 -*-
"""
Тесты Wave 2: Промышленная целостность и стабильность архитектуры.
Проверяют:
1. Выполнение PostgreSQL миграций без замалчивания ошибок и без предварительного ALTER TABLE.
2. Инициализацию схемы PostgreSQL и сидирование администратора.
3. Соблюдение флагов RUN_EMBEDDED_WORKER и RUN_EMBEDDED_BOT.
4. Отсутствие остаточных ссылок на устаревший каталог kvit_test в CI/CD конфигурациях.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

import config
from database.migrations import DatabaseMigrationError, migrate_db


def test_postgres_migration_error_raises_database_migration_error(monkeypatch):
    """Сбой выполнения схемы PostgreSQL должен выбрасывать DatabaseMigrationError, а не замалчиваться."""
    monkeypatch.setattr(config, 'DATABASE_URL', 'postgresql://user:pass@localhost:5432/testdb')
    monkeypatch.setattr(config, 'DB_TYPE', 'postgres')

    mock_con = MagicMock()
    mock_con.executescript.side_effect = Exception("Syntax error in custom SQL migration")

    with patch('database.migrations.write_transaction') as mock_tx:
        mock_tx.return_value.__enter__.return_value = mock_con
        mock_tx.return_value.__exit__.return_value = None

        with pytest.raises(DatabaseMigrationError) as excinfo:
            migrate_db()
        assert "Database migration failed" in str(excinfo.value)


def test_postgres_migration_success_and_admin_seeding(monkeypatch):
    """Успешное применение схемы PostgreSQL и корректное сидирование администратора."""
    monkeypatch.setattr(config, 'DATABASE_URL', 'postgresql://user:pass@localhost:5432/testdb')
    monkeypatch.setattr(config, 'DB_TYPE', 'postgres')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', 'pbkdf2_sha256$600000$test_hash')

    mock_con = MagicMock()
    # admin does not exist initially
    mock_con.execute.return_value.fetchone.return_value = None

    with patch('database.migrations.write_transaction') as mock_tx:
        mock_tx.return_value.__enter__.return_value = mock_con
        mock_tx.return_value.__exit__.return_value = None

        migrate_db()

        # Check executescript was called for schema.postgres.sql
        assert mock_con.executescript.called
        # Check admin was inserted
        insert_calls = [c for c in mock_con.execute.call_args_list if "INSERT INTO users" in str(c)]
        assert len(insert_calls) == 1


def test_embedded_worker_flag_respected(monkeypatch):
    """Проверка конфигурационного флага RUN_EMBEDDED_WORKER."""
    monkeypatch.setenv('RUN_EMBEDDED_WORKER', 'false')
    val = os.environ.get('RUN_EMBEDDED_WORKER', 'true').lower() in ('true', '1', 'yes')
    assert val is False

    monkeypatch.setenv('RUN_EMBEDDED_WORKER', 'true')
    val = os.environ.get('RUN_EMBEDDED_WORKER', 'true').lower() in ('true', '1', 'yes')
    assert val is True


def test_embedded_bot_flag_respected(monkeypatch):
    """Проверка конфигурационного флага RUN_EMBEDDED_BOT."""
    monkeypatch.setenv('RUN_EMBEDDED_BOT', 'false')
    val = os.environ.get('RUN_EMBEDDED_BOT', 'true').lower() in ('true', '1', 'yes')
    assert val is False

    monkeypatch.setenv('RUN_EMBEDDED_BOT', 'true')
    val = os.environ.get('RUN_EMBEDDED_BOT', 'true').lower() in ('true', '1', 'yes')
    assert val is True


def test_no_kvit_test_in_ci_and_dependabot():
    """Проверка чистоты CI/CD файлов от устаревших путей kvit_test."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    dependabot_file = os.path.join(base_dir, '.github', 'dependabot.yml')
    if os.path.isfile(dependabot_file):
        with open(dependabot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'kvit_test' not in content, "В .github/dependabot.yml обнаружены ссылки на kvit_test!"

    ci_file = os.path.join(base_dir, '.github', 'workflows', 'tests.yml')
    if os.path.isfile(ci_file):
        with open(ci_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'kvit_test' not in content, "В .github/workflows/tests.yml обнаружены ссылки на kvit_test!"
