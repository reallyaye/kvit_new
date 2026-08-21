import time
import threading
from collections import defaultdict, deque

class RateLimiter:
    """Потокобезопасный ограничитель частоты запросов методом скользящего окна (Sliding Window)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._buckets = defaultdict(lambda: defaultdict(deque))
        self._last_cleanup = time.time()

    def is_allowed(self, bucket: str, key: str, max_requests: int, window_seconds: int = 60):
        """
        Проверяет, не превышен ли лимит запросов для данного ключа (например, IP-адреса).
        Возвращает (is_allowed, retry_after_seconds, remaining_requests).
        """
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
