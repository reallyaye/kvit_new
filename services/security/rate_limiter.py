import logging
import threading
import time
from collections import defaultdict, deque
from typing import Tuple

import config

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_LIB_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_LIB_AVAILABLE = False


class RateLimiter:
    """
    Ограничитель частоты запросов методом скользящего окна (Sliding Window).
    Поддерживает:
    1. Распределенный режим через Redis ZSET + атомарный Lua-скрипт (для нескольких API-реплик).
    2. Потокобезопасный In-Memory режим для локальной разработки и тестов.
    """

    LUA_SLIDING_WINDOW = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local clear_before = now - window

    redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
    local current_requests = redis.call('ZCARD', key)

    if current_requests < limit then
        redis.call('ZADD', key, now, tostring(now) .. '-' .. ARGV[4])
        redis.call('EXPIRE', key, math.ceil(window) + 2)
        return {1, 0, limit - current_requests - 1}
    else
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local retry_after = 1
        if oldest and #oldest >= 2 then
            local oldest_time = tonumber(oldest[2])
            retry_after = math.max(1, math.ceil(oldest_time + window - now))
        end
        return {0, retry_after, 0}
    end
    """

    def __init__(self, redis_client=None):
        self._lock = threading.RLock()
        self._buckets = defaultdict(lambda: defaultdict(deque))
        self._last_cleanup = time.time()
        self._redis_client = redis_client
        self._script = None

    def _get_redis(self):
        if self._redis_client is not None:
            return self._redis_client
        if getattr(config, 'REDIS_ENABLED', False) and REDIS_LIB_AVAILABLE:
            try:
                redis_url = getattr(config, 'REDIS_URL', 'redis://localhost:6379/0')
                self._redis_client = redis.Redis.from_url(
                    redis_url,
                    socket_timeout=1.0,
                    socket_connect_timeout=1.0
                )
                self._script = self._redis_client.register_script(self.LUA_SLIDING_WINDOW)
            except Exception as e:
                logger.debug(f"[RateLimiter] Не удалось подключиться к Redis: {e}")
                self._redis_client = None
        return self._redis_client

    def is_allowed(self, bucket: str, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int, int]:
        """
        Проверяет, не превышен ли лимит запросов для данного ключа (IP, аккаунт, токен).
        Возвращает кортеж (is_allowed, retry_after_seconds, remaining_requests).
        """
        r_client = self._get_redis()
        if r_client is not None and self._script is not None:
            try:
                now = time.time()
                seq = int((now % 1) * 1000000)
                redis_key = f"kvit:ratelimit:{bucket}:{key}"
                res = self._script(
                    keys=[redis_key],
                    args=[now, window_seconds, max_requests, seq]
                )
                if res and len(res) == 3:
                    allowed = bool(res[0])
                    retry_after = int(res[1])
                    remaining = int(res[2])
                    return allowed, retry_after, remaining
            except Exception as e:
                if getattr(config, 'IS_PRODUCTION', False):
                    logger.error(
                        f"[RateLimiter] ❌ Ошибка Redis rate-limit в production: {e}. Запрос заблокирован (Fail-Closed)."
                    )
                    return False, 60, 0
                logger.debug(f"[RateLimiter] Ошибка Redis rate-limit, откат на память: {e}")

        if getattr(config, 'IS_PRODUCTION', False):
            logger.error("[RateLimiter] ❌ Redis недоступен в production окружении. Запрос заблокирован (Fail-Closed).")
            return False, 60, 0

        # Fallback на In-Memory Sliding Window (только для development/testing)
        return self._is_allowed_memory(bucket, key, max_requests, window_seconds)

    def _is_allowed_memory(self, bucket: str, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        now = time.time()
        with self._lock:
            # Периодическая очистка старых данных раз в 5 минут
            if now - self._last_cleanup > 300:
                self._cleanup(now)
                self._last_cleanup = now

            timestamps = self._buckets[bucket][key]
            # Удаляем запросы, вышедшие за пределы скользящего окна
            while timestamps and timestamps[0] <= now - window_seconds:
                timestamps.popleft()

            if len(timestamps) < max_requests:
                timestamps.append(now)
                remaining = max_requests - len(timestamps)
                return True, 0, remaining
            else:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after, 0

    def _cleanup(self, now: float):
        for bucket in list(self._buckets.keys()):
            for key in list(self._buckets[bucket].keys()):
                timestamps = self._buckets[bucket][key]
                while timestamps and timestamps[0] <= now - 3600:
                    timestamps.popleft()
                if not timestamps:
                    del self._buckets[bucket][key]


rate_limiter = RateLimiter()
