# -*- coding: utf-8 -*-
"""
Модуль бэкендов очереди фоновых задач (Queue Backend).
Поддерживает:
1. RedisTaskQueueBackend (для распределенного промышленного кластера воркеров)
2. MemoryTaskQueueBackend (потокобезопасный in-memory бэкенд для локальной разработки и тестов)
"""
import json
import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_LIB_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_LIB_AVAILABLE = False


class BaseTaskQueueBackend(ABC):
    """Абстрактный интерфейс очереди задач и хранилища состояний."""

    @abstractmethod
    def push_job(self, job_data: dict) -> bool:
        """Помещает задачу в очередь."""
        pass

    @abstractmethod
    def pop_job(self, timeout: float = 1.0) -> Optional[dict]:
        """Извлекает следующую задачу из очереди с блокировкой по таймауту."""
        pass

    @abstractmethod
    def save_job_state(self, job_id: str, state: dict) -> bool:
        """Сохраняет актуальное состояние задачи."""
        pass

    @abstractmethod
    def get_job_state(self, job_id: str) -> Optional[dict]:
        """Возвращает текущее состояние задачи по job_id."""
        pass

    @abstractmethod
    def list_jobs(self, limit: int = 50) -> List[dict]:
        """Возвращает список последних задач."""
        pass

    @abstractmethod
    def acquire_lock(self, lock_key: str, timeout: float = 60.0) -> bool:
        """Пытается захватить распределенную блокировку (защита от race conditions)."""
        pass

    @abstractmethod
    def release_lock(self, lock_key: str) -> None:
        """Освобождает блокировку."""
        pass

    @abstractmethod
    def ping(self) -> bool:
        """Проверяет доступность бэкенда."""
        pass

    @property
    @abstractmethod
    def queue_length(self) -> int:
        """Возвращает текущую длину очереди."""
        pass


class MemoryTaskQueueBackend(BaseTaskQueueBackend):
    """Потокобезопасная in-memory очередь с поддержкой блокировок и истории."""

    def __init__(self, max_history: int = 200):
        self._queue: queue.Queue = queue.Queue()
        self._states: Dict[str, dict] = {}
        self._locks: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._max_history = max_history

    def push_job(self, job_data: dict) -> bool:
        job_id = job_data.get('job_id')
        if not job_id:
            return False
        with self._lock:
            self._states[job_id] = job_data
            if len(self._states) > self._max_history:
                oldest_k = next(iter(self._states))
                del self._states[oldest_k]
        self._queue.put(job_data)
        return True

    def pop_job(self, timeout: float = 1.0) -> Optional[dict]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def save_job_state(self, job_id: str, state: dict) -> bool:
        with self._lock:
            self._states[job_id] = state
        return True

    def get_job_state(self, job_id: str) -> Optional[dict]:
        with self._lock:
            return self._states.get(job_id)

    def list_jobs(self, limit: int = 50) -> List[dict]:
        with self._lock:
            items = list(self._states.values())
        items.sort(key=lambda x: x.get('created_at', 0), reverse=True)
        return items[:limit]

    def acquire_lock(self, lock_key: str, timeout: float = 60.0) -> bool:
        now = time.time()
        with self._lock:
            # Очистка устаревших блокировок
            if lock_key in self._locks:
                if self._locks[lock_key] > now:
                    return False  # Заблокировано
            self._locks[lock_key] = now + timeout
            return True

    def release_lock(self, lock_key: str) -> None:
        with self._lock:
            self._locks.pop(lock_key, None)

    def ping(self) -> bool:
        return True

    @property
    def queue_length(self) -> int:
        return self._queue.qsize()


class RedisTaskQueueBackend(BaseTaskQueueBackend):
    """
    Промышленный Redis-бэкенд для распределенных воркеров.
    Использует LPUSH / BRPOP для надежной очереди и Hash для хранения метаданных.
    """

    def __init__(self, redis_url: str, socket_timeout: float = 5.0):
        self._redis_url = redis_url
        self._socket_timeout = socket_timeout
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout
        )
        self._queue_key = getattr(config, 'REDIS_QUEUE_KEY', 'kvit:tasks:pdf_queue')
        self._hash_key = getattr(config, 'REDIS_TASKS_HASH', 'kvit:tasks:metadata')

    def push_job(self, job_data: dict) -> bool:
        job_id = job_data.get('job_id')
        if not job_id:
            return False
        payload = json.dumps(job_data, ensure_ascii=False)
        # Сохраняем состояние задачи в Hash и помещаем идентификатор в очередь
        self._client.hset(self._hash_key, job_id, payload)
        self._client.rpush(self._queue_key, job_id)
        return True

    def pop_job(self, timeout: float = 1.0) -> Optional[dict]:
        # blpop возвращает tuple (queue_name, item) или None
        res = self._client.blpop(self._queue_key, timeout=int(max(1, timeout)))
        if not res:
            return None
        job_id = res[1]
        raw_state = self._client.hget(self._hash_key, job_id)
        if raw_state:
            try:
                return json.loads(raw_state)
            except Exception:
                pass
        return {'job_id': job_id}

    def save_job_state(self, job_id: str, state: dict) -> bool:
        payload = json.dumps(state, ensure_ascii=False)
        self._client.hset(self._hash_key, job_id, payload)
        return True

    def get_job_state(self, job_id: str) -> Optional[dict]:
        raw_state = self._client.hget(self._hash_key, job_id)
        if raw_state:
            try:
                return json.loads(raw_state)
            except Exception:
                pass
        return None

    def list_jobs(self, limit: int = 50) -> List[dict]:
        all_vals = self._client.hvals(self._hash_key)
        jobs = []
        for val in all_vals:
            try:
                jobs.append(json.loads(val))
            except Exception:
                pass
        jobs.sort(key=lambda x: x.get('created_at', 0), reverse=True)
        return jobs[:limit]

    def acquire_lock(self, lock_key: str, timeout: float = 60.0) -> bool:
        # SET key value NX EX seconds
        res = self._client.set(f"kvit:lock:{lock_key}", "1", nx=True, ex=int(timeout))
        return bool(res)

    def release_lock(self, lock_key: str) -> None:
        self._client.delete(f"kvit:lock:{lock_key}")

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    @property
    def queue_length(self) -> int:
        try:
            return self._client.llen(self._queue_key)
        except Exception:
            return 0


def create_task_queue_backend() -> BaseTaskQueueBackend:
    """Фабрика создания бэкенда очереди с автоматическим graceful fallback."""
    if getattr(config, 'REDIS_ENABLED', False) and REDIS_LIB_AVAILABLE:
        try:
            backend = RedisTaskQueueBackend(config.REDIS_URL, config.REDIS_SOCKET_TIMEOUT)
            if backend.ping():
                logger.info(f"[TaskQueue] Инициализирован распределенный Redis бэкенд ({config.REDIS_URL})")
                return backend
            else:
                logger.warning("[TaskQueue] Redis недоступен по PING. Переключение на MemoryTaskQueueBackend.")
        except Exception as e:
            logger.warning(f"[TaskQueue] Сбой подключения к Redis ({e}). Переключение на MemoryTaskQueueBackend.")

    logger.info("[TaskQueue] Инициализирована потокобезопасная MemoryTaskQueueBackend очередь.")
    return MemoryTaskQueueBackend()
