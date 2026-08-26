"""Тестирование подсистемы асинхронных фоновых задач и очереди обработки PDF."""
import os
import shutil
import tempfile
import time
import pytest

import config
from database.connection import get_db
from services.tasks import TaskStatus, task_manager


def _create_dummy_pdf(path: str, account: str = "800146", period: str = "08.2026"):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    doc = fitz.open()
    page = doc.new_page()
    text = f"Лицевой счет: {account}\nПериод: {period}\nАдрес: ул. Тестовая 1"
    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None
    if font_path:
        page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
        page.insert_text((50, 100), text, fontname='arial', fontsize=12)
    else:
        page.insert_text((50, 100), text, fontsize=12)
    doc.save(path)
    doc.close()


def test_task_manager_submit_and_completion(tmp_path):
    """Проверка полного жизненного цикла задачи: PENDING -> PROCESSING -> COMPLETED."""
    task_manager.start()

    tmp_dir = str(tmp_path / "spool_test")
    os.makedirs(tmp_dir, exist_ok=True)
    pdf_file = os.path.join(tmp_dir, "test_job_receipt.pdf")
    _create_dummy_pdf(pdf_file, account="800146", period="10.2026")

    con = get_db()
    con.execute("INSERT OR IGNORE INTO accounts(account_number, customer_name, address) VALUES ('800146', 'Тест', 'Адрес')")
    con.commit()
    con.close()

    callbacks_fired = []

    def on_done(t):
        callbacks_fired.append(t.job_id)

    task = task_manager.submit_pdf_job(
        files=[("test_job_receipt.pdf", pdf_file)],
        source='unit_test',
        spool_dir=tmp_dir,
        callbacks=[on_done]
    )

    assert task.job_id.startswith("job_")
    assert task.total_files == 1

    # Ждем завершения фоновой обработки
    for _ in range(50):
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            break
        time.sleep(0.05)

    assert task.status == TaskStatus.COMPLETED
    assert task.processed_files == 1
    assert task.progress_pct == 100
    assert task.added >= 1 or task.duplicates >= 1
    assert len(callbacks_fired) == 1
    assert callbacks_fired[0] == task.job_id

    # Проверяем, что временная спул-директория очищена
    assert not os.path.exists(tmp_dir)


def test_task_manager_get_and_list():
    """Проверка методов получения задачи по ID и списка недавних задач."""
    task_manager.start()

    tasks_before = task_manager.list_tasks(limit=10)
    task = task_manager.submit_pdf_job(files=[], source='test_list')

    found = task_manager.get_task(task.job_id)
    assert found is not None
    assert found.job_id == task.job_id

    tasks_after = task_manager.list_tasks(limit=10)
    assert any(t['job_id'] == task.job_id for t in tasks_after)


def test_task_manager_error_isolation(tmp_path):
    """Проверка изоляции ошибок при обработке поврежденного файла."""
    task_manager.start()

    corrupt_file = str(tmp_path / "corrupt.pdf")
    with open(corrupt_file, 'wb') as f:
        f.write(b"NOT A VALID PDF FILE DATA")

    task = task_manager.submit_pdf_job(
        files=[("corrupt.pdf", corrupt_file)],
        source='corrupt_test'
    )

    for _ in range(50):
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            break
        time.sleep(0.05)

    assert task.status == TaskStatus.COMPLETED
    assert task.skipped >= 1
    assert any('corrupt.pdf' in d for d in task.details)
