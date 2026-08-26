# -*- coding: utf-8 -*-
"""
Тесты надежности очереди задач, хранилища pipeline, метрик и устойчивости к сбоям.
"""
import os
import shutil
import tempfile
import time
import pytest

from services.metrics.collector import MetricsCollector
from services.storage.pipeline import StoragePipeline
from services.tasks.queue_backend import MemoryTaskQueueBackend
from services.tasks.task_manager import BackgroundTask, TaskQueueManager, TaskStatus


def test_memory_queue_backend_push_pop_lock():
    backend = MemoryTaskQueueBackend(max_history=10)
    job_data = {'job_id': 'job_test_1', 'created_at': time.time(), 'total_files': 5}
    assert backend.push_job(job_data) is True
    assert backend.queue_length == 1

    popped = backend.pop_job(timeout=0.1)
    assert popped is not None
    assert popped['job_id'] == 'job_test_1'
    assert backend.queue_length == 0

    # Проверка блокировок
    assert backend.acquire_lock('test_lock', timeout=10.0) is True
    assert backend.acquire_lock('test_lock', timeout=10.0) is False  # Уже заблокировано
    backend.release_lock('test_lock')
    assert backend.acquire_lock('test_lock', timeout=10.0) is True


def test_storage_pipeline_lifecycle():
    tmp_root = tempfile.mkdtemp(prefix="test_pipeline_")
    try:
        pipeline = StoragePipeline()
        job_id = "test_job_123"
        base_name = "test_sample.pdf"

        # 1. Создаем тестовый файл в спуле
        spool_dir = pipeline.prepare_job_spool(job_id)
        raw_path = os.path.join(spool_dir, base_name)
        with open(raw_path, 'wb') as f:
            f.write(b"%PDF-1.4 dummy test content")

        sha256 = pipeline.compute_file_sha256(raw_path)
        assert len(sha256) == 64

        # 2. Перемещаем в processing
        proc_path = pipeline.move_to_processing(raw_path, job_id, base_name)
        assert os.path.exists(proc_path)
        assert not os.path.exists(raw_path)

        # 3. Карантин при ошибке
        failed_path = pipeline.quarantine_failed(proc_path, job_id, base_name, "Corrupt PDF Header")
        assert os.path.exists(failed_path)
        assert os.path.exists(f"{failed_path}.meta.json")

        # 4. Очистка спула
        pipeline.cleanup_job(job_id)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_task_manager_dead_worker_recovery():
    backend = MemoryTaskQueueBackend()
    manager = TaskQueueManager(backend=backend, max_workers=1)

    # Создаем задачу, застрявшую в PROCESSING 400 секунд назад
    old_time = time.time() - 400
    stale_job = {
        'job_id': 'stale_job_1',
        'source': 'test',
        'status': TaskStatus.PROCESSING,
        'created_at': old_time,
        'started_at': old_time,
        'updated_at': old_time,
        'total_files': 10,
        'processed_files': 2,
        'retry_count': 0,
        'max_retries': 3
    }
    backend.save_job_state('stale_job_1', stale_job)

    # Запускаем восстановление
    manager.recover_stale_jobs(timeout_sec=300)

    recovered = backend.get_job_state('stale_job_1')
    assert recovered is not None
    assert recovered['status'] == TaskStatus.RETRY
    assert recovered['retry_count'] == 1
    assert backend.queue_length == 1  # Задача возвращена в очередь


def test_metrics_collector_stats_and_prometheus():
    collector = MetricsCollector()
    collector.record_request('GET', '/api/search?account=800101', 200, 0.015)
    collector.record_request('GET', '/api/search?account=800102', 200, 0.025)
    collector.record_request('GET', '/api/search?account=999999', 404, 0.010)
    collector.record_ocr(0.5, pages=2)
    collector.record_pdf_process(0.1, files_count=1)

    data = collector.to_dict()
    assert data['requests']['total'] == 3
    assert data['requests']['by_status'][200] == 2
    assert data['requests']['by_status'][404] == 1
    assert data['requests']['latencies']['avg_ms'] > 0
    assert data['ocr']['pages_total'] == 2

    prom = collector.to_prometheus()
    assert 'http_requests_total 3' in prom
    assert 'ocr_pages_total 2' in prom
