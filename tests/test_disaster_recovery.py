# -*- coding: utf-8 -*-
"""
Тесты сценариев сбоев и восстановления (Disaster Recovery):
1. Аварийное восстановление БД: онлайн-бэкап -> повреждение текущей БД -> восстановление -> сверка счетов и квитанций.
2. Авария воркера / потеря связи с Redis: задача в статусе PROCESSING перехватывается через reclaim и успешно завершается.
"""
import os
import sqlite3
import tempfile
import time
import pytest

import config
from database.connection import get_db
from database.migrations import migrate_db
from services.tasks.queue_backend import MemoryTaskQueueBackend
from services.tasks.task_manager import TaskQueueManager, TaskStatus


def test_database_backup_and_disaster_restore(tmp_path):
    """Тест: бэкап рабочей БД -> сброс данных -> восстановление из копии -> проверка целостности."""
    con = get_db()
    con.execute("INSERT OR REPLACE INTO accounts(account_number, customer_name, address) VALUES ('900100', 'Алиев', 'ул. Абая 5')")
    con.execute("INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, access_token, status) VALUES ('900100', '01.2026', 'sample.pdf', 'tok12345678901234567890123456789', 'READY')")
    con.commit()
    con.close()

    # 1. Делаем бэкап
    backup_file = str(tmp_path / "backup_db.sqlite3")
    src = get_db()
    dst = sqlite3.connect(backup_file)
    src.backup(dst)
    dst.close()
    src.close()

    # 2. Симулируем повреждение/очистку основной БД
    src = get_db()
    src.execute("DELETE FROM receipts")
    src.execute("DELETE FROM accounts")
    src.commit()
    assert src.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
    src.close()

    # 3. Восстанавливаем из бэкапа
    restore_src = sqlite3.connect(backup_file)
    target = get_db()
    restore_src.backup(target)
    restore_src.close()

    # 4. Проверяем целостность восстановленных данных
    acc = target.execute("SELECT customer_name FROM accounts WHERE account_number='900100'").fetchone()
    assert acc is not None
    assert acc['customer_name'] == 'Алиев'

    rec = target.execute("SELECT status FROM receipts WHERE account_number='900100'").fetchone()
    assert rec is not None
    assert rec['status'] == 'READY'
    target.close()


def test_worker_crash_and_redis_queue_recovery():
    """Тест: аварийное падение воркера во время задачи -> reclaim_stale_jobs возвращает задачу -> второй воркер завершает ее."""
    backend = MemoryTaskQueueBackend()
    job_id = "job_crash_test_123"
    job_data = {
        "job_id": job_id,
        "source": "test_crash",
        "files": [("file1.pdf", "/dummy/path/file1.pdf")],
        "retry_count": 0,
        "max_retries": 3
    }

    # 1. Постановка задачи в очередь
    backend.push_job(job_data)
    assert backend.queue_length == 1

    # 2. Воркер берет задачу (claim с visibility_timeout=1 секунда)
    claimed_job = backend.pop_job(timeout=1, visibility_timeout=1.0, worker_id="worker_dead_1")
    assert claimed_job is not None
    assert claimed_job["job_id"] == job_id
    assert backend.queue_length == 0
    assert backend.processing_length == 1

    # 3. Симулируем падение воркера (не вызвал ack_job) и ждем истечения visibility_timeout
    time.sleep(1.2)

    # 4. Монитор восстановления очередей перехватывает зависшую задачу
    reclaimed = backend.reclaim_stale_jobs()
    assert len(reclaimed) == 1
    assert backend.queue_length == 1
    assert backend.processing_length == 0

    # 5. Новый здоровый воркер подхватывает задачу и подтверждает завершение
    recovered_job = backend.pop_job(timeout=1, visibility_timeout=5.0, worker_id="worker_alive_2")
    assert recovered_job is not None
    assert recovered_job["job_id"] == job_id
    assert recovered_job.get("retry_count", 0) >= 1

    # Подтверждаем успешное выполнение (ACK)
    backend.ack_job(recovered_job)

    # Очередь processing и pending должны быть пусты
    assert backend.processing_length == 0
    assert backend.queue_length == 0


