import time
import threading
from collections import defaultdict, deque
from config import THROTTLE_MAX_CONCURRENT, THROTTLE_BURST_RPS
from database.connection import get_db, write_transaction
from logger import logger

class IPThrottler:
    """
    Ограничитель параллельных запросов (Concurrency Throttling), всплесков (Burst Smoothing)
    и персистентной блокировки вредоносных IP-адресов (State-Sharing / Persistent Ban).
    """
    def __init__(self, max_concurrent=THROTTLE_MAX_CONCURRENT, burst_rps=THROTTLE_BURST_RPS):
        self._lock = threading.Lock()
        self._active_concurrency = defaultdict(int)  # {ip: active_concurrent_requests_count}
        self._burst_tracker = defaultdict(deque)      # {ip: deque([timestamps_in_last_sec])}
        self._banned_ips = {}                         # {ip: blocked_until}
        self.max_concurrent = max_concurrent
        self.burst_rps = burst_rps
        self._load_active_bans_from_db()

    def _load_active_bans_from_db(self):
        """Загружает неистекшие блокировки IP из БД при старте приложения."""
        now = time.time()
        try:
            con = get_db()
            try:
                rows = con.execute('SELECT ip, blocked_until FROM security_blocks WHERE blocked_until > ?', (now,)).fetchall()
                with self._lock:
                    for r in rows:
                        self._banned_ips[r[0]] = float(r[1])
            finally:
                con.close()
        except Exception:
            pass

    def ban_ip(self, ip: str, duration_seconds: int = 3600, reason: str = "Excessive requests / Abuse"):
        """Персистентно блокирует IP адрес в памяти и базе данных."""
        now = time.time()
        blocked_until = now + duration_seconds
        with self._lock:
            self._banned_ips[ip] = blocked_until

        try:
            with write_transaction() as con:
                con.execute('INSERT OR REPLACE INTO security_blocks(ip, blocked_until, reason) VALUES (?, ?, ?)',
                            (ip, blocked_until, reason))
            logger.warning(f"[Security] IP {ip} заблокирован на {duration_seconds}с. Причина: {reason}")
        except Exception as e:
            logger.warning(f"[Security] Не удалось персистировать бан IP {ip}: {e}")

    def is_banned(self, ip: str) -> tuple[bool, int]:
        """Проверяет, заблокирован ли IP (в памяти или БД). Возвращает (is_banned, retry_after)."""
        now = time.time()
        with self._lock:
            blocked_until = self._banned_ips.get(ip)
            if blocked_until is not None:
                if now < blocked_until:
                    return True, max(1, int(blocked_until - now))
                else:
                    self._banned_ips.pop(ip, None)

        # Fallback проверка в БД
        try:
            con = get_db()
            try:
                row = con.execute('SELECT blocked_until FROM security_blocks WHERE ip = ?', (ip,)).fetchone()
                if row:
                    db_until = float(row[0])
                    if now < db_until:
                        with self._lock:
                            self._banned_ips[ip] = db_until
                        return True, max(1, int(db_until - now))
            finally:
                con.close()
        except Exception:
            pass

        return False, 0

    def acquire(self, ip: str):
        """
        Пытается занять слот для выполнения запроса.
        Возвращает (allowed, reason, retry_after).
        """
        banned, retry_after = self.is_banned(ip)
        if banned:
            return False, 'ip_banned', retry_after

        now = time.time()
        with self._lock:
            # 1. Проверка на кратковременный всплеск (burst)
            bursts = self._burst_tracker[ip]
            while bursts and bursts[0] <= now - 1.0:
                bursts.popleft()
            if len(bursts) >= self.burst_rps:
                return False, 'burst_limit', 1

            # 2. Проверка на одновременные соединения (concurrency)
            if self._active_concurrency[ip] >= self.max_concurrent:
                return False, 'concurrency_limit', 1

            # Фиксируем активность
            bursts.append(now)
            self._active_concurrency[ip] += 1
            return True, '', 0

    def release(self, ip: str):
        """Освобождает активный слот для данного IP."""
        with self._lock:
            if self._active_concurrency[ip] > 0:
                self._active_concurrency[ip] -= 1
                if self._active_concurrency[ip] == 0:
                    del self._active_concurrency[ip]

ip_throttler = IPThrottler()

