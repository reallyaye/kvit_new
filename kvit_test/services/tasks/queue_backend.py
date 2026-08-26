# -*- coding: utf-8 -*-
"""
Модуль бэкендов очереди фоновых задач (Queue Backend).
Реализует надёжный паттерн Claim → Processing → ACK с поддержкой:
1. RedisTaskQueueBackend (промышленный распределенный кластер на Redis ZSET + List + Hash)
2. MemoryTaskQueueBackend (потокобезопасный in-memory бэкенд для локальной разработки и тестов)
3. Visibility Timeout и автоматический Reclaim/Requeue зависших задач при падении воркеров
4. Dead Letter Queue (DLQ) для задач с превышением лимита повторов
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
    """Абстрактный интерфейс надежной очереди задач и хранилища состояний."""

    @abstractmethod
    def push_job(self, job_data: dict) -> bool:
        """Помещает задачу в очередь ожидания."""
        pass

    @abstractmethod
    def pop_job(
        self,
        timeout: float = 1.0,
        visibility_timeout: float = 300.0,
        worker_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Атомарно захватывает (Claim) следующую задачу из очереди и переводит в статус обработки.
        Задача резервируется на время visibility_timeout.
        """
        pass

    @abstractmethod
    def ack_job(self, job_id: str) -> bool:
        """Подтверждает успешное завершение задачи (ACK), удаляя её из списка активной обработки."""
        pass

    @abstractmethod
    def nack_job(self, job_id: str, requeue: bool = True) -> bool:
        """Отказ от задачи (NACK). При requeue=True возвращает её обратно в очередь."""
        pass

    @abstractmethod
    def extend_visibility(self, job_id: str, extra_timeout: float = 300.0) -> bool:
        """Продлевает время видимости (heartbeat) для длительно выполняющейся задачи."""
        pass

    @abstractmethod
    def reclaim_stale_jobs(self, timeout_sec: Optional[float] = None, max_reclaim: int = 50) -> List[str]:
        """
        Возвращает в очередь зависшие задачи, у которых истек visibility timeout
        (например, при падении воркера без вызова ACK).
        """
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
        """Возвращает текущую длину очереди ожидания."""
        pass

    @property
    @abstractmethod
    def processing_length(self) -> int:
        """Возвращает количество задач, находящихся в активной обработке."""
        pass


class MemoryTaskQueueBackend(BaseTaskQueueBackend):
    """Потокобезопасная in-memory очередь с надежным Claim → Processing → ACK циклом."""

    def __init__(self, max_history: int = 200):
        self._queue: queue.Queue = queue.Queue()
        self._states: Dict[str, dict] = {}
        self._processing: Dict[str, dict] = {}  # job_id -> {expire_at, worker_id, claimed_at}
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

    def pop_job(
        self,
        timeout: float = 1.0,
        visibility_timeout: float = 300.0,
        worker_id: Optional[str] = None
    ) -> Optional[dict]:
        try:
            job_data = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        job_id = job_data.get('job_id')
        if not job_id:
            return job_data

        now = time.time()
        with self._lock:
            self._processing[job_id] = {
                'job_id': job_id,
                'expire_at': now + visibility_timeout,
                'claimed_at': now,
                'worker_id': worker_id or threading.current_thread().name
            }
            if job_id in self._states:
                return dict(self._states[job_id])
        return job_data

    def ack_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._processing:
                del self._processing[job_id]
                return True
        return False

    def nack_job(self, job_id: str, requeue: bool = True) -> bool:
        with self._lock:
            self._processing.pop(job_id, None)
            job_data = self._states.get(job_id)
        if requeue and job_data:
            self._queue.put(job_data)
            return True
        return False

    def extend_visibility(self, job_id: str, extra_timeout: float = 300.0) -> bool:
        with self._lock:
            if job_id in self._processing:
                self._processing[job_id]['expire_at'] = time.time() + extra_timeout
                return True
        return False

    def reclaim_stale_jobs(self, timeout_sec: Optional[float] = None, max_reclaim: int = 50) -> List[str]:
        now = time.time()
        reclaimed: List[str] = []
        with self._lock:
            stale_ids = [
                jid for jid, info in self._processing.items()
                if info.get('expire_at', 0) <= now
            ][:max_reclaim]

            for jid in stale_ids:
                del self._processing[jid]
                job_data = self._states.get(jid)
                if job_data:
                    retries = job_data.get('retry_count', 0)
                    max_retries = job_data.get('max_retries', 3)
                    if retries < max_retries:
                        job_data['retry_count'] = retries + 1
                        job_data['status'] = 'RETRY'
                        job_data['updated_at'] = now
                        self._queue.put(job_data)
                        reclaimed.append(jid)
                    else:
                        job_data['status'] = 'FAILED'
                        job_data['error_message'] = "Visibility timeout expired & max retries exceeded."
                        job_data['finished_at'] = now
                        job_data['updated_at'] = now
        return reclaimed

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
            if lock_key in self._locks:
                if self._locks[lock_key] > now:
                    return False
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

    @property
    def processing_length(self) -> int:
        with self._lock:
            return len(self._processing)


class RedisTaskQueueBackend(BaseTaskQueueBackend):
    """
    Промышленный Redis-бэкенд с надёжной моделью Claim → Processing → ACK.
    - Очередь ожидания: Redis List (`kvit:tasks:pdf_queue`)
    - Очередь активной обработки: Redis Sorted Set (`kvit:tasks:processing`) со score = unix_timestamp + visibility_timeout
    - Dead Letter Queue: Redis List (`kvit:tasks:dlq`)
    - Метаданные задач: Redis Hash (`kvit:tasks:metadata`)
    """

    # Lua-скрипт для атомарного подтверждения (ACK)
    LUA_ACK = """
    local processing_key = KEYS[1]
    local job_id = ARGV[1]
    return redis.call('ZREM', processing_key, job_id)
    """

    # Lua-скрипт для отказа и возврата в очередь (NACK / Requeue)
    LUA_NACK = """
    local processing_key = KEYS[1]
    local queue_key = KEYS[2]
    local job_id = ARGV[1]
    local requeue = ARGV[2]

    redis.call('ZREM', processing_key, job_id)
    if requeue == '1' then
        redis.call('LPUSH', queue_key, job_id)
    end
    return 1
    """

    # Lua-скрипт для быстрого атомарного Claim (RPOP + ZADD)
    LUA_CLAIM = """
    local queue_key = KEYS[1]
    local processing_key = KEYS[2]
    local hash_key = KEYS[3]
    local expire_at = tonumber(ARGV[1])

    local job_id = redis.call('RPOP', queue_key)
    if not job_id then
        return nil
    end
    redis.call('ZADD', processing_key, expire_at, job_id)
    local raw_state = redis.call('HGET', hash_key, job_id)
    return {job_id, raw_state}
    """

    # Lua-скрипт для регистрации задачи из BLPOP в processing ZSET
    LUA_REGISTER_PROCESSING = """
    local processing_key = KEYS[1]
    local hash_key = KEYS[2]
    local job_id = ARGV[1]
    local expire_at = tonumber(ARGV[2])

    redis.call('ZADD', processing_key, expire_at, job_id)
    local raw_state = redis.call('HGET', hash_key, job_id)
    return raw_state
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
        self._processing_key = getattr(config, 'REDIS_PROCESSING_KEY', 'kvit:tasks:processing')
        self._dlq_key = getattr(config, 'REDIS_DLQ_KEY', 'kvit:tasks:dlq')
        self._hash_key = getattr(config, 'REDIS_TASKS_HASH', 'kvit:tasks:metadata')

        self._script_ack = self._client.register_script(self.LUA_ACK)
        self._script_nack = self._client.register_script(self.LUA_NACK)
        self._script_claim = self._client.register_script(self.LUA_CLAIM)
        self._script_register = self._client.register_script(self.LUA_REGISTER_PROCESSING)

    def push_job(self, job_data: dict) -> bool:
        job_id = job_data.get('job_id')
        if not job_id:
            return False
        payload = json.dumps(job_data, ensure_ascii=False)
        pipe = self._client.pipeline()
        pipe.hset(self._hash_key, job_id, payload)
        pipe.rpush(self._queue_key, job_id)
        pipe.execute()
        return True

    def pop_job(
        self,
        timeout: float = 1.0,
        visibility_timeout: float = 300.0,
        worker_id: Optional[str] = None
    ) -> Optional[dict]:
        now = time.time()
        expire_at = now + visibility_timeout

        # 1. Быстрый атомарный Claim через RPOP + ZADD
        try:
            res = self._script_claim(
                keys=[self._queue_key, self._processing_key, self._hash_key],
                args=[expire_at]
            )
            if res and res[0]:
                job_id = res[0]
                raw_state = res[1]
                if raw_state:
                    try:
                        return json.loads(raw_state)
                    except Exception:
                        pass
                return {'job_id': job_id}
        except Exception as e:
            logger.debug(f"[RedisQueue] Ошибка claim скрипта: {e}")

        # 2. Если очередь пуста, используем BLPOP с блокировкой по timeout
        if timeout <= 0:
            return None

        blpop_res = self._client.blpop(self._queue_key, timeout=int(max(1, timeout)))
        if not blpop_res:
            return None

        job_id = blpop_res[1]
        try:
            raw_state = self._script_register(
                keys=[self._processing_key, self._hash_key],
                args=[job_id, expire_at]
            )
            if raw_state:
                try:
                    return json.loads(raw_state)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[RedisQueue] Ошибка регистрации задачи {job_id} в processing: {e}")
            self._client.zadd(self._processing_key, {job_id: expire_at})

        return {'job_id': job_id}

    def ack_job(self, job_id: str) -> bool:
        """Подтверждает успешное завершение и удаляет задачу из processing ZSET."""
        try:
            res = self._script_ack(keys=[self._processing_key], args=[job_id])
            return bool(res)
        except Exception as e:
            logger.warning(f"[RedisQueue] Ошибка ACK для задачи {job_id}: {e}")
            return bool(self._client.zrem(self._processing_key, job_id))

    def nack_job(self, job_id: str, requeue: bool = True) -> bool:
        """Отказ от задачи с возможностью возврата в очередь ожидания."""
        try:
            self._script_nack(
                keys=[self._processing_key, self._queue_key],
                args=[job_id, '1' if requeue else '0']
            )
            return True
        except Exception as e:
            logger.warning(f"[RedisQueue] Ошибка NACK для задачи {job_id}: {e}")
            pipe = self._client.pipeline()
            pipe.zrem(self._processing_key, job_id)
            if requeue:
                pipe.lpush(self._queue_key, job_id)
            pipe.execute()
            return True

    def extend_visibility(self, job_id: str, extra_timeout: float = 300.0) -> bool:
        """Продлевает время видимости для задачи в обработке."""
        try:
            score = self._client.zscore(self._processing_key, job_id)
            if score is not None:
                new_expire = time.time() + extra_timeout
                self._client.zadd(self._processing_key, {job_id: new_expire})
                return True
        except Exception as e:
            logger.debug(f"[RedisQueue] Ошибка extend_visibility {job_id}: {e}")
        return False

    def reclaim_stale_jobs(self, timeout_sec: Optional[float] = None, max_reclaim: int = 50) -> List[str]:
        """
        Находит задачи в processing ZSET с истекшим visibility timeout (score <= now).
        Атомарно возвращает их в очередь или отправляет в DLQ.
        """
        now = time.time()
        reclaimed: List[str] = []
        try:
            stale_job_ids = self._client.zrangebyscore(
                self._processing_key,
                min=0,
                max=now,
                start=0,
                num=max_reclaim
            )
            if not stale_job_ids:
                return []

            for jid in stale_job_ids:
                raw = self._client.hget(self._hash_key, jid)
                job_data = json.loads(raw) if raw else {'job_id': jid}

                retries = job_data.get('retry_count', 0)
                max_retries = job_data.get('max_retries', getattr(config, 'JOB_RETRY_COUNT', 3))

                pipe = self._client.pipeline()
                pipe.zrem(self._processing_key, jid)

                if retries < max_retries:
                    job_data['retry_count'] = retries + 1
                    job_data['status'] = 'RETRY'
                    job_data['updated_at'] = now
                    pipe.hset(self._hash_key, jid, json.dumps(job_data, ensure_ascii=False))
                    pipe.lpush(self._queue_key, jid)
                    reclaimed.append(jid)
                    logger.warning(
                        f"[RedisQueue] Задача {jid} зависла (истек visibility timeout). "
                        f"Requeue в очередь ({job_data['retry_count']}/{max_retries})."
                    )
                else:
                    job_data['status'] = 'FAILED'
                    job_data['error_message'] = "Visibility timeout expired & max retries exceeded."
                    job_data['finished_at'] = now
                    job_data['updated_at'] = now
                    pipe.hset(self._hash_key, jid, json.dumps(job_data, ensure_ascii=False))
                    pipe.lpush(self._dlq_key, jid)
                    logger.error(
                        f"[RedisQueue] Задача {jid} превысила лимит повторов. Перемещена в DLQ ({self._dlq_key})."
                    )

                pipe.execute()

        except Exception as e:
            logger.error(f"[RedisQueue] Ошибка при reclaim_stale_jobs: {e}", exc_info=True)

        return reclaimed

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

    @property
    def processing_length(self) -> int:
        try:
            return self._client.zcard(self._processing_key)
        except Exception:
            return 0

    @property
    def dlq_length(self) -> int:
        try:
            return self._client.llen(self._dlq_key)
        except Exception:
            return 0


def create_task_queue_backend() -> BaseTaskQueueBackend:
    """
    Фабрика создания бэкенда очереди.
    - Production (APP_ENV == 'production'): Обязательное использование Redis.
      При недоступности Redis выбрасывается исключение RuntimeError (Fail-Fast),
      предотвращая тихий переход в In-Memory очередь и потерю распределенных задач.
    - Development/Test: При недоступности Redis выполняется graceful fallback на MemoryTaskQueueBackend.
    """
    is_prod = getattr(config, 'IS_PRODUCTION', False) or getattr(config, 'APP_ENV', '') == 'production'
    redis_enabled = getattr(config, 'REDIS_ENABLED', False) or is_prod

    if is_prod or redis_enabled:
        if not REDIS_LIB_AVAILABLE:
            if is_prod:
                raise RuntimeError(
                    "[TaskQueue] ❌ КРИТИЧЕСКАЯ ОШИБКА: Библиотека 'redis' не установлена в Production окружении! "
                    "Запуск остановлен (Fail-Fast). Установите: pip install redis"
                )
            logger.warning("[TaskQueue] Библиотека redis не найдена. Переключение на MemoryTaskQueueBackend.")
        else:
            try:
                backend = RedisTaskQueueBackend(config.REDIS_URL, config.REDIS_SOCKET_TIMEOUT)
                if backend.ping():
                    logger.info(f"[TaskQueue] Инициализирован распределенный Redis бэкенд ({config.REDIS_URL})")
                    return backend
                else:
                    if is_prod:
                        raise RuntimeError(
                            f"[TaskQueue] ❌ КРИТИЧЕСКАЯ ОШИБКА: Redis ({config.REDIS_URL}) недоступен по PING в Production! "
                            "Запуск остановлен (Fail-Fast). Проверьте подключение к Redis."
                        )
                    logger.warning("[TaskQueue] Redis недоступен по PING. Переключение на MemoryTaskQueueBackend.")
            except Exception as e:
                if is_prod:
                    raise RuntimeError(
                        f"[TaskQueue] ❌ КРИТИЧЕСКАЯ ОШИБКА: Сбой подключения к Redis ({config.REDIS_URL}) в Production: {e}. "
                        "Запуск остановлен (Fail-Fast)."
                    ) from e
                logger.warning(f"[TaskQueue] Сбой подключения к Redis ({e}). Переключение на MemoryTaskQueueBackend.")

    logger.info("[TaskQueue] Инициализирована потокобезопасная MemoryTaskQueueBackend очередь.")
    return MemoryTaskQueueBackend()

