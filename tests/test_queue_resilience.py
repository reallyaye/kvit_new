# -*- coding: utf-8 -*-
"""
Тесты надежности очереди задач, хранилища pipeline, метрик и устойчивости к сбоям.
Проверяет:
- Паттерн Claim → Processing → ACK
- Visibility Timeout и автоматический Reclaim/Requeue
- Dead-Letter Queue (DLQ) при исчерпании retry_count
- Продление видимости (extend_visibility)
- Метрики и конвейер хранения
"""
import os
import shutil
import tempfile
import time
import pytest
from unittest.mock import MagicMock

from services.metrics.collector import MetricsCollector
from services.storage.pipeline import StoragePipeline
from services.tasks.queue_backend import MemoryTaskQueueBackend, RedisTaskQueueBackend
from services.tasks.task_manager import BackgroundTask, TaskQueueManager, TaskStatus


def test_memory_queue_claim_processing_ack():
    """Проверка полного цикла Claim → Processing → ACK."""
    backend = MemoryTaskQueueBackend(max_history=10)
    job_data = {'job_id': 'job_ack_1', 'created_at': time.time(), 'total_files': 3}
    assert backend.push_job(job_data) is True
    assert backend.queue_length == 1
    assert backend.processing_length == 0

    # 1. Claim (pop_job переводит в processing)
    popped = backend.pop_job(timeout=0.1, visibility_timeout=60.0, worker_id="worker_1")
    assert popped is not None
    assert popped['job_id'] == 'job_ack_1'
    assert backend.queue_length == 0
    assert backend.processing_length == 1

    # 2. ACK (удаляет из processing)
    assert backend.ack_job('job_ack_1') is True
    assert backend.processing_length == 0
    assert backend.queue_length == 0


def test_memory_queue_visibility_timeout_and_reclaim():
    """Проверка автоматического Requeue при истечении Visibility Timeout (падение воркера)."""
    backend = MemoryTaskQueueBackend(max_history=10)
    job_data = {
        'job_id': 'job_stale_1',
        'created_at': time.time(),
        'total_files': 1,
        'retry_count': 0,
        'max_retries': 3
    }
    backend.push_job(job_data)

    # Claim с коротким visibility timeout (0.05 сек)
    popped = backend.pop_job(timeout=0.1, visibility_timeout=0.05)
    assert popped is not None
    assert backend.processing_length == 1
    assert backend.queue_length == 0

    # Ждем истечения visibility timeout
    time.sleep(0.08)

    # Reclaim возвращает задачу в очередь ожидания
    reclaimed = backend.reclaim_stale_jobs(max_reclaim=10)
    assert 'job_stale_1' in reclaimed
    assert backend.processing_length == 0
    assert backend.queue_length == 1

    # Проверяем, что задача извлекается снова со статусом RETRY и retry_count = 1
    re_popped = backend.pop_job(timeout=0.1)
    assert re_popped is not None
    assert re_popped['retry_count'] == 1
    assert re_popped['status'] == 'RETRY'


def test_memory_queue_dlq_on_max_retries():
    """Проверка перевода задачи в FAILED при исчерпании лимита retry_count."""
    backend = MemoryTaskQueueBackend(max_history=10)
    job_data = {
        'job_id': 'job_dead_1',
        'created_at': time.time(),
        'total_files': 1,
        'retry_count': 3,
        'max_retries': 3
    }
    backend.push_job(job_data)

    # Claim с моментальным истечением visibility timeout
    backend.pop_job(timeout=0.1, visibility_timeout=0.01)
    time.sleep(0.03)

    # Reclaim должен пометить как FAILED и не возвращать в очередь
    reclaimed = backend.reclaim_stale_jobs(max_reclaim=10)
    assert 'job_dead_1' not in reclaimed  # Не возвращена в очередь
    assert backend.queue_length == 0
    assert backend.processing_length == 0

    state = backend.get_job_state('job_dead_1')
    assert state is not None
    assert state['status'] == 'FAILED'


def test_memory_queue_extend_visibility():
    """Проверка продления visibility timeout во время длительной обработки."""
    backend = MemoryTaskQueueBackend(max_history=10)
    job_data = {'job_id': 'job_heartbeat_1', 'created_at': time.time()}
    backend.push_job(job_data)

    backend.pop_job(timeout=0.1, visibility_timeout=0.05)
    # Продлеваем видимость на 10 секунд
    assert backend.extend_visibility('job_heartbeat_1', extra_timeout=10.0) is True

    # Спустя 0.08 сек задача не должна считаться зависшей
    time.sleep(0.08)
    reclaimed = backend.reclaim_stale_jobs()
    assert len(reclaimed) == 0
    assert backend.processing_length == 1


def test_memory_queue_nack_requeue():
    """Проверка NACK с возвратом в очередь."""
    backend = MemoryTaskQueueBackend()
    job_data = {'job_id': 'job_nack_1', 'created_at': time.time()}
    backend.push_job(job_data)

    backend.pop_job(timeout=0.1)
    assert backend.processing_length == 1
    assert backend.queue_length == 0

    # NACK с requeue=True
    assert backend.nack_job('job_nack_1', requeue=True) is True
    assert backend.processing_length == 0
    assert backend.queue_length == 1


def test_redis_backend_interface_and_scripts():
    """Проверка структуры и интерфейса RedisTaskQueueBackend (мокирование redis)."""
    mock_redis_cls = MagicMock()
    mock_client = MagicMock()
    mock_redis_cls.from_url.return_value = mock_client
    mock_client.ping.return_value = True

    # Тестируем инициализацию скриптов и свойств
    import redis as real_redis
    orig_redis = real_redis.Redis
    try:
        real_redis.Redis = mock_redis_cls
        backend = RedisTaskQueueBackend("redis://localhost:6379/0")
        assert backend.ping() is True

        # Проверка вызова регистрации скриптов
        assert mock_client.register_script.call_count >= 4

        # Проверка push_job
        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        backend.push_job({'job_id': 'redis_job_1'})
        assert mock_pipe.execute.called

        # Проверка ACK
        backend.ack_job('redis_job_1')
        assert backend._script_ack.called
    finally:
        real_redis.Redis = orig_redis


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

