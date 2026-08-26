# -*- coding: utf-8 -*-
"""
Модуль асинхронной очереди фоновых задач (PDF-парсинг, OCR, массовый импорт).
Поддерживает:
- Распределенный Redis бэкенд и быстрый In-Memory бэкенд
- Состояния: PENDING, PROCESSING, COMPLETED, FAILED, RETRY
- Автоматический Retry с экспоненциальной задержкой
- Восстановление зависших задач при падении серверов (Dead Worker Recovery)
- Конвейер хранения incoming → processing → receipts / failed
- Мониторинг скорости обработки (files/sec) и расчет ETA
"""
import os
import secrets
import shutil
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import config
from database.connection import get_db
from logger import logger
from services.pdf import pdf_processor
from services.storage.pipeline import storage_pipeline
from services.tasks.queue_backend import BaseTaskQueueBackend, create_task_queue_backend
from services.websocket import ws_manager


class TaskStatus:
    """Константы жизненного цикла фоновой задачи."""
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    RETRY = 'RETRY'


class BackgroundTask:
    """Модель фоновой задачи обработки файлов."""

    def __init__(
        self,
        job_id: str,
        source: str,
        files: List[Tuple[str, str]],
        spool_dir: Optional[str] = None,
        callbacks: Optional[List[Callable[['BackgroundTask'], None]]] = None,
        meta: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        retry_count: int = 0
    ):
        self.job_id = job_id
        self.source = source
        self.files = files  # Список кортежей: (base_name, file_path)
        self.spool_dir = spool_dir
        self.callbacks = callbacks or []
        self.meta = meta or {}

        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.updated_at: float = time.time()

        self.total_files = len(files)
        self.processed_files = 0
        self.current_file: Optional[str] = None

        self.added = 0
        self.orphan = 0
        self.skipped = 0
        self.duplicates = 0
        self.details: List[str] = []
        self.error_message: Optional[str] = None

        self.max_retries = max_retries
        self.retry_count = retry_count

    @property
    def progress_pct(self) -> int:
        if self.total_files == 0:
            return 100 if self.status == TaskStatus.COMPLETED else 0
        return int((self.processed_files / self.total_files) * 100)

    @property
    def speed_files_per_sec(self) -> float:
        """Скорость обработки файлов в секунду."""
        if not self.started_at or self.processed_files == 0:
            return 0.0
        elapsed = max(0.001, (self.finished_at or time.time()) - self.started_at)
        return round(self.processed_files / elapsed, 2)

    @property
    def eta_seconds(self) -> Optional[int]:
        """Расчет примерного оставшегося времени выполнения задачи."""
        speed = self.speed_files_per_sec
        if speed <= 0 or self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return 0 if self.status == TaskStatus.COMPLETED else None
        remaining_files = max(0, self.total_files - self.processed_files)
        return int(remaining_files / speed)

    def to_dict(self) -> dict:
        return {
            'job_id': self.job_id,
            'source': self.source,
            'status': self.status,
            'progress_pct': self.progress_pct,
            'total_files': self.total_files,
            'processed_files': self.processed_files,
            'current_file': self.current_file,
            'added': self.added,
            'orphan': self.orphan,
            'skipped': self.skipped,
            'duplicates': self.duplicates,
            'details': self.details[-50:],  # Ограничение размера лога для сети
            'error_message': self.error_message,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'updated_at': self.updated_at,
            'speed_files_per_sec': self.speed_files_per_sec,
            'eta_seconds': self.eta_seconds,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'spool_dir': self.spool_dir,
            'meta': self.meta
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BackgroundTask':
        task = cls(
            job_id=data['job_id'],
            source=data.get('source', 'unknown'),
            files=data.get('files', []),
            spool_dir=data.get('spool_dir'),
            meta=data.get('meta', {}),
            max_retries=data.get('max_retries', 3),
            retry_count=data.get('retry_count', 0)
        )
        task.status = data.get('status', TaskStatus.PENDING)
        task.created_at = data.get('created_at', time.time())
        task.started_at = data.get('started_at')
        task.finished_at = data.get('finished_at')
        task.updated_at = data.get('updated_at', time.time())
        task.total_files = data.get('total_files', len(task.files))
        task.processed_files = data.get('processed_files', 0)
        task.current_file = data.get('current_file')
        task.added = data.get('added', 0)
        task.orphan = data.get('orphan', 0)
        task.skipped = data.get('skipped', 0)
        task.duplicates = data.get('duplicates', 0)
        task.details = data.get('details', [])
        task.error_message = data.get('error_message')
        return task


class TaskQueueManager:
    """Менеджер очереди задач, координирующий бэкенд, воркеры и мониторинг."""

    def __init__(self, backend: Optional[BaseTaskQueueBackend] = None, max_workers: Optional[int] = None):
        self.backend = backend or create_task_queue_backend()
        self.max_workers = max_workers or getattr(config, 'WORKER_COUNT', 4)
        self._workers: List[threading.Thread] = []
        self._local_tasks: Dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self._recovery_timer: Optional[threading.Thread] = None

    def start(self):
        """Запускает рабочие потоки обработки очереди и монитор зависших задач."""
        with self._lock:
            if self._running:
                return
            self._running = True

            # Восстановление незавершенных задач после перезапуска
            self.recover_stale_jobs()

            for i in range(self.max_workers):
                worker = threading.Thread(
                    target=self._worker_loop,
                    name=f"PDFTaskWorker-{i+1}",
                    daemon=True
                )
                worker.start()
                self._workers.append(worker)

            # Фоновый поток восстановления зависших задач
            self._recovery_timer = threading.Thread(
                target=self._recovery_loop,
                name="TaskRecoveryMonitor",
                daemon=True
            )
            self._recovery_timer.start()

            logger.info(f"[TaskManager] Запущено {self.max_workers} воркеров очереди задач.")

    def stop(self):
        """Останавливает рабочие потоки очереди."""
        with self._lock:
            self._running = False
            self._workers.clear()

    def submit_pdf_job(
        self,
        files: List[Tuple[str, str]],
        source: str = 'web_upload',
        spool_dir: Optional[str] = None,
        callbacks: Optional[List[Callable[[BackgroundTask], None]]] = None,
        meta: Optional[Dict[str, str]] = None
    ) -> BackgroundTask:
        """Регистрирует новую задачу на обработку PDF и отправляет в очередь."""
        job_id = f"job_{secrets.token_hex(8)}"
        task = BackgroundTask(
            job_id=job_id,
            source=source,
            files=files,
            spool_dir=spool_dir,
            callbacks=callbacks,
            meta=meta,
            max_retries=getattr(config, 'JOB_RETRY_COUNT', 3)
        )

        with self._lock:
            self._local_tasks[job_id] = task

        # Сохраняем сериализуемые данные в бэкенд очереди
        task_payload = task.to_dict()
        task_payload['files'] = files
        self.backend.push_job(task_payload)
        logger.info(f"[TaskManager] Задача {job_id} ({source}, файлов: {len(files)}) добавлена в очередь.")

        try:
            ws_manager.broadcast('task_queued', task.to_dict())
        except Exception as ws_err:
            logger.debug(f"[TaskManager] Ошибка WS broadcast (task_queued): {ws_err}")

        # Если воркеры еще не запущены и включен встроенный режим — стартуем
        if not self._running and getattr(config, 'RUN_EMBEDDED_WORKER', True):
            self.start()

        return task

    def get_task(self, job_id: str) -> Optional[BackgroundTask]:
        """Получает актуальное состояние задачи из локальной памяти или бэкенда."""
        with self._lock:
            if job_id in self._local_tasks:
                return self._local_tasks[job_id]

        state = self.backend.get_job_state(job_id)
        if state:
            task = BackgroundTask.from_dict(state)
            with self._lock:
                self._local_tasks[job_id] = task
            return task
        return None

    def list_tasks(self, limit: int = 30) -> List[dict]:
        """Возвращает список последних задач из бэкенда очереди."""
        return self.backend.list_jobs(limit=limit)

    def get_queue_stats(self) -> dict:
        """Собирает сводную статистику по очереди и задачам для админ-панели и метрик."""
        all_jobs = self.list_tasks(limit=100)
        stats = {
            'queue_length': self.backend.queue_length,
            'processing_queue_length': getattr(self.backend, 'processing_length', 0),
            'dlq_length': getattr(self.backend, 'dlq_length', 0),
            'active_workers': len([w for w in self._workers if w.is_alive()]) if self._running else 0,
            'total_jobs': len(all_jobs),
            'pending_count': 0,
            'processing_count': 0,
            'completed_count': 0,
            'failed_count': 0,
            'retried_count': 0,
            'total_files': 0,
            'processed_files': 0
        }

        for j in all_jobs:
            st = j.get('status')
            if st == TaskStatus.PENDING:
                stats['pending_count'] += 1
            elif st == TaskStatus.PROCESSING:
                stats['processing_count'] += 1
            elif st == TaskStatus.COMPLETED:
                stats['completed_count'] += 1
            elif st == TaskStatus.FAILED:
                stats['failed_count'] += 1
            elif st == TaskStatus.RETRY:
                stats['retried_count'] += 1

            stats['total_files'] += j.get('total_files', 0)
            stats['processed_files'] += j.get('processed_files', 0)

        return stats

    def recover_stale_jobs(self, timeout_sec: Optional[float] = None):
        """
        Восстанавливает зависшие задачи (Dead Worker Recovery).
        1. Сначала использует надежный механизм reclaim_stale_jobs из ZSET очереди обработки.
        2. При необходимости восстанавливает устаревшие метаданные.
        """
        timeout = timeout_sec or getattr(config, 'QUEUE_VISIBILITY_TIMEOUT', 300)
        now = time.time()

        # Надежный Reclaim из ZSET processing бэкенда
        try:
            reclaimed_ids = self.backend.reclaim_stale_jobs(timeout_sec=timeout)
            if reclaimed_ids:
                logger.warning(f"[TaskManager] Возвращено в очередь {len(reclaimed_ids)} зависших задач: {reclaimed_ids}")
        except Exception as e:
            logger.debug(f"[TaskManager] Ошибка бэкенда reclaim_stale_jobs: {e}")

        # Дополнительная проверка метаданных
        jobs = self.backend.list_jobs(limit=100)
        for j in jobs:
            if j.get('status') == TaskStatus.PROCESSING:
                updated_at = j.get('updated_at') or j.get('started_at') or j.get('created_at', now)
                if (now - updated_at) > timeout:
                    job_id = j['job_id']
                    retries = j.get('retry_count', 0)
                    max_retries = j.get('max_retries', 3)

                    if retries < max_retries:
                        logger.warning(f"[TaskManager] Задача {job_id} зависла (>{timeout} сек). Перевод в статус RETRY ({retries+1}/{max_retries}).")
                        j['status'] = TaskStatus.RETRY
                        j['retry_count'] = retries + 1
                        j['updated_at'] = now
                        self.backend.save_job_state(job_id, j)
                        self.backend.push_job(j)
                    else:
                        logger.error(f"[TaskManager] Задача {job_id} превысила лимит повторов ({max_retries}). Перевод в статус FAILED.")
                        j['status'] = TaskStatus.FAILED
                        j['error_message'] = f"Таймаут выполнения задачи (>{timeout} сек) и превышен лимит повторов."
                        j['finished_at'] = now
                        j['updated_at'] = now
                        self.backend.save_job_state(job_id, j)

    def _recovery_loop(self):
        """Периодический фоновый цикл проверки зависших задач."""
        while self._running:
            try:
                time.sleep(15.0)
                if self._running:
                    self.recover_stale_jobs()
            except Exception as e:
                logger.debug(f"[TaskManager] Ошибка в цикле восстановления: {e}")

    def _worker_loop(self):
        """Основной цикл фонового воркера с надёжным Claim и Visibility Timeout."""
        worker_name = threading.current_thread().name
        visibility_timeout = getattr(config, 'QUEUE_VISIBILITY_TIMEOUT', 300)

        while self._running:
            try:
                job_data = self.backend.pop_job(
                    timeout=1.0,
                    visibility_timeout=visibility_timeout,
                    worker_id=worker_name
                )
            except Exception as err:
                logger.debug(f"[TaskManager] Ошибка извлечения задачи из очереди: {err}")
                time.sleep(1.0)
                continue

            if not job_data:
                continue

            job_id = job_data.get('job_id')
            if not job_id:
                continue

            task = self.get_task(job_id)
            if not task:
                task = BackgroundTask.from_dict(job_data)
                with self._lock:
                    self._local_tasks[job_id] = task

            # Захват блокировки задачи для предотвращения параллельной обработки двумя воркерами
            if not self.backend.acquire_lock(f"task:{job_id}", timeout=getattr(config, 'JOB_TIMEOUT', 300)):
                logger.warning(f"[TaskManager] Задача {job_id} уже обрабатывается другим воркером. Пропуск.")
                continue

            try:
                self._process_task(task)
            finally:
                self.backend.release_lock(f"task:{job_id}")

    def _process_task(self, task: BackgroundTask):
        """Выполняет обработку задачи с конвейером pipeline и защитой от race conditions."""
        task.status = TaskStatus.PROCESSING
        task.started_at = time.time()
        task.updated_at = time.time()
        self._sync_task_state(task)
        logger.info(f"[TaskManager] Старт обработки задачи {task.job_id} ({task.total_files} файлов).")

        try:
            ws_manager.broadcast('task_started', task.to_dict())
        except Exception:
            pass

        # Сессионный кэш дедупликации хешей в рамках текущей задачи
        task_hashes = set()

        try:
            for base_name, raw_file_path in task.files:
                task.current_file = base_name
                task.updated_at = time.time()

                # Перемещаем файл в директорию active processing
                proc_file_path = storage_pipeline.move_to_processing(raw_file_path, task.job_id, base_name)

                try:
                    # Индексированная обработка без предварительной загрузки всей базы в память
                    added, orphan, skipped, dups, details, _ = pdf_processor.process_single_pdf(
                        proc_file_path, base_name, known_accounts=None, existing_hashes=task_hashes
                    )
                    task.added += added
                    task.orphan += orphan
                    task.skipped += skipped
                    task.duplicates += dups
                    status_icon = '✅' if orphan == 0 and skipped == 0 and dups == 0 else '⚠'
                    task.details.append(
                        f'📄 {base_name}: {status_icon} +{added}, сирот {orphan}, пропущено {skipped}, дубликатов {dups}'
                    )
                    task.details.extend(details)
                except Exception as file_err:
                    logger.error(f"[TaskManager] Ошибка при обработке файла {base_name}: {file_err}", exc_info=True)
                    task.skipped += 1
                    task.details.append(f'❌ {base_name}: сбой обработки ({file_err})')
                    # Перемещаем ошибочный файл в карантин
                    storage_pipeline.quarantine_failed(proc_file_path, task.job_id, base_name, str(file_err))

                task.processed_files += 1
                self._sync_task_state(task)

                try:
                    ws_manager.broadcast('task_progress', task.to_dict())
                except Exception:
                    pass

            task.status = TaskStatus.COMPLETED
            task.finished_at = time.time()
            task.updated_at = time.time()
            self._sync_task_state(task)

            logger.info(
                f"[TaskManager] Задача {task.job_id} успешно завершена "
                f"(+{task.added}, сирот: {task.orphan}, дублей: {task.duplicates}, пропущено: {task.skipped})."
            )

        except Exception as unhandled_err:
            logger.error(f"[TaskManager] Критический сбой задачи {task.job_id}: {unhandled_err}", exc_info=True)
            self._handle_task_failure(task, str(unhandled_err))

        finally:
            self._finalize_task(task)

    def _handle_task_failure(self, task: BackgroundTask, error_msg: str):
        """Обрабатывает сбой задачи с поддержкой повторных попыток (Retry)."""
        now = time.time()
        task.updated_at = now
        task.error_message = error_msg

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.RETRY
            logger.warning(f"[TaskManager] Задача {task.job_id} завершилась сбоем ({error_msg}). Назначен Retry ({task.retry_count}/{task.max_retries}).")
            self._sync_task_state(task)
            # Возвращаем задачу в очередь для повторной попытки
            self.backend.nack_job(task.job_id, requeue=False)
            self.backend.push_job(task.to_dict())
        else:
            task.status = TaskStatus.FAILED
            task.finished_at = now
            self._sync_task_state(task)
            self.backend.ack_job(task.job_id)

    def _sync_task_state(self, task: BackgroundTask):
        """Синхронизирует состояние задачи с бэкендом очереди."""
        try:
            self.backend.save_job_state(task.job_id, task.to_dict())
        except Exception as e:
            logger.debug(f"[TaskManager] Ошибка сохранения состояния {task.job_id}: {e}")

    def _finalize_task(self, task: BackgroundTask):
        """Завершает задачу: отправляет оповещения, подтверждает ACK в очереди, вызывает callbacks и чистит спул."""
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return

        # Подтверждаем удаление из очереди активной обработки (ACK)
        try:
            self.backend.ack_job(task.job_id)
        except Exception as ack_err:
            logger.debug(f"[TaskManager] Ошибка ACK для задачи {task.job_id}: {ack_err}")

        # 1. Рассылка WebSocket событий
        try:
            event_name = 'task_completed' if task.status == TaskStatus.COMPLETED else 'task_failed'
            ws_manager.broadcast(event_name, task.to_dict())
            if task.status == TaskStatus.COMPLETED and (task.added > 0 or task.orphan > 0):
                ws_manager.broadcast('upload_batch_completed', {
                    'files_count': task.total_files,
                    'added': task.added,
                    'orphan': task.orphan,
                    'duplicates': task.duplicates,
                    'skipped': task.skipped,
                    'source': task.source
                })
        except Exception as ws_err:
            logger.debug(f"[TaskManager] Ошибка WS broadcast завершения: {ws_err}")

        # 2. Вызов зарегистрированных колбэков
        for cb in task.callbacks:
            try:
                cb(task)
            except Exception as cb_err:
                logger.error(f"[TaskManager] Ошибка в callback задачи {task.job_id}: {cb_err}", exc_info=True)

        # 3. Очистка временных спул-директорий
        storage_pipeline.cleanup_job(task.job_id)
        if task.spool_dir and os.path.exists(task.spool_dir):
            try:
                shutil.rmtree(task.spool_dir, ignore_errors=True)
            except Exception:
                pass


# Глобальный синглтон менеджера фоновых задач
task_manager = TaskQueueManager()
