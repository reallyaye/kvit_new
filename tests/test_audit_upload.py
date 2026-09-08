# -*- coding: utf-8 -*-
"""
Тест проверки расширенного аудита загрузок:
- Запуск фоновой задачи с автором (username, client_ip)
- Завершение задачи
- Проверка записи UPLOAD_SUCCESS / UPLOAD_FAILED в таблицу audit_logs с метриками
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
    task.started_at = time.time() - 2.5
    task.finished_at = time.time()
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
