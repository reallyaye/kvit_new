# -*- coding: utf-8 -*-
"""
Тест проверки расширенного аудита загрузок:
- Запуск фоновой задачи с автором (username, client_ip)
- Завершение задачи с фиксацией скорости обработки (files/sec)
- Проверка записи UPLOAD_SUCCESS / UPLOAD_FAILED в таблицу audit_logs
- Проверка, что задачи с 0 добавленных квитанций получают UPLOAD_FAILED
- Проверка статистики get_audit_stats() без двойного счета (без UPLOAD_START)
"""

import time

from services.security.auth_service import auth_service
from services.tasks.task_manager import BackgroundTask, TaskStatus, task_manager


def test_upload_task_audit_lifecycle():
    task = BackgroundTask(
        job_id="job_audit_test_123",
        source="web_upload",
        files=[("rec1.pdf", "p1.pdf"), ("rec2.pdf", "p2.pdf")],
        meta={"username": "shtabel", "client_ip": "192.168.1.55"}
    )
    task.started_at = time.time() - 2.0
    task.finished_at = time.time()
    task.processed_files = 2
    task.status = TaskStatus.COMPLETED
    task.added = 1
    task.orphan = 1
    task.skipped = 0
    task.duplicates = 0
    task.details = ["Файл 2: лицевой счет не найден"]

    task_manager._finalize_task(task)

    # Проверяем журнал аудита
    logs = auth_service.list_audit_logs(limit=10, username="shtabel")
    assert len(logs) > 0
    latest = logs[0]
    assert latest['action'] == 'UPLOAD_SUCCESS'
    assert latest['ip'] == '192.168.1.55'
    assert 'job_audit_test_123' in latest['details']
    assert 'Добавлено: 1' in latest['details']
    assert 'Отклонено (без счёта): 1' in latest['details']
    assert 'Файл 2: лицевой счет не найден' in latest['details']
    assert 'Скорость обработки:' in latest['details']
    assert 'ф/с' in latest['details']


def test_upload_task_audit_failed_scenario():
    task = BackgroundTask(
        job_id="job_audit_fail_456",
        source="web_upload",
        files=[("bad1.pdf", "p_bad.pdf")],
        meta={"username": "operator_ivan", "client_ip": "10.10.1.20"}
    )
    task.started_at = time.time() - 1.0
    task.finished_at = time.time()
    task.processed_files = 1
    task.status = TaskStatus.FAILED
    task.error_message = "Поврежденный файл PDF: заголовок не распознан"

    task_manager._finalize_task(task)

    logs = auth_service.list_audit_logs(limit=10, username="operator_ivan")
    assert len(logs) > 0
    latest = logs[0]
    assert latest['action'] == 'UPLOAD_FAILED'
    assert latest['ip'] == '10.10.1.20'
    assert 'job_audit_fail_456' in latest['details']
    assert 'Поврежденный файл PDF' in latest['details']
    assert 'Скорость обработки:' in latest['details']
    assert 'ф/с' in latest['details']


def test_upload_task_audit_zero_added_with_errors_is_failed():
    task = BackgroundTask(
        job_id="job_audit_zero_789",
        source="web_upload",
        files=[("rec1.pdf", "p1.pdf"), ("rec2.pdf", "p2.pdf")],
        meta={"username": "uploader_olga", "client_ip": "192.168.10.15"}
    )
    task.started_at = time.time() - 1.5
    task.finished_at = time.time()
    task.processed_files = 2
    task.status = TaskStatus.COMPLETED  # Внешний цикл мог завершиться, но добавленных 0
    task.added = 0
    task.orphan = 1
    task.skipped = 1
    task.duplicates = 0
    task.error_message = "Не найдены лицевые счета для всех квитанций"

    task_manager._finalize_task(task)

    logs = auth_service.list_audit_logs(limit=10, username="uploader_olga")
    assert len(logs) > 0
    latest = logs[0]
    # Должен быть зафиксирован как сбой UPLOAD_FAILED, так как добавлено 0 квитанций
    assert latest['action'] == 'UPLOAD_FAILED'
    assert 'job_audit_zero_789' in latest['details']
    assert 'Добавлено: 0' in latest['details']
    assert 'Не найдены лицевые счета' in latest['details']
    assert 'Скорость обработки:' in latest['details']


def test_audit_stats_no_double_counting():
    """Проверка, что UPLOAD_START не учитывается в статистике uploads (нет двойного счета)."""
    user = "audit_stats_test_user"
    auth_service.log_audit(user, "127.0.0.1", "UPLOAD_START", "Запуск загрузки batch_1")
    auth_service.log_audit(user, "127.0.0.1", "UPLOAD_SUCCESS", "Загрузка batch_1 успешно завершена")

    stats = auth_service.get_audit_stats()
    assert stats['uploads'] >= 1

    logs = auth_service.list_audit_logs(limit=100, username=user)
    actions = [entry['action'] for entry in logs]
    assert 'UPLOAD_START' in actions
    assert 'UPLOAD_SUCCESS' in actions

    from database.connection import get_db
    con = get_db()
    try:
        user_uploads = con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE username = ? AND action IN ('UPLOAD_SUCCESS', 'UPLOAD_RECEIPTS')",
            (user,)
        ).fetchone()[0]
        user_all_upload_actions = con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE username = ? AND action IN ('UPLOAD_START', 'UPLOAD_SUCCESS', 'UPLOAD_RECEIPTS')",
            (user,)
        ).fetchone()[0]
        assert user_uploads == 1
        assert user_all_upload_actions == 2
    finally:
        con.close()
