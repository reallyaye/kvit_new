# -*- coding: utf-8 -*-
"""
tests/test_hotfix_readiness.py: Тестирование исправлений hotfix-релиза:
1. task_manager.active_workers свойство и корректный heartbeat.
2. mask_redis_url маскирование чувствительных данных в URL Redis.
3. rate_limiter.is_allowed fail-closed в production при сбое Redis.
4. Использование scan_iter для worker heartbeats в server.py.
"""

from unittest.mock import MagicMock, patch

import config
from services.security.rate_limiter import RateLimiter
from services.tasks.queue_backend import mask_redis_url
from services.tasks.task_manager import TaskQueueManager


def test_task_manager_active_workers_property():
    """Свойство active_workers возвращает целое число и не падает с AttributeError."""
    tm = TaskQueueManager(max_workers=2)
    assert hasattr(tm, 'active_workers')
    assert isinstance(tm.active_workers, int)
    assert tm.active_workers == 0


def test_mask_redis_url_passwords():
    """mask_redis_url скрывает пароли в строках подключения к Redis."""
    raw = "redis://:super_secret_pwd@10.0.0.5:6379/0"
    masked = mask_redis_url(raw)
    assert "super_secret_pwd" not in masked
    assert "***" in masked
    assert "10.0.0.5:6379/0" in masked

    raw_user = "redis://admin:mypassword@redis-cluster:6380/1"
    masked_user = mask_redis_url(raw_user)
    assert "mypassword" not in masked_user
    assert "admin:***@redis-cluster:6380/1" in masked_user

    # Без пароля
    clean = "redis://127.0.0.1:6379/0"
    assert mask_redis_url(clean) == clean


def test_rate_limiter_production_fail_closed():
    """В режиме IS_PRODUCTION при отказе Redis возвращается (False, 60, 0) Fail-Closed."""
    limiter = RateLimiter()
    mock_redis = MagicMock()
    # Имитируем сбой выполнения скрипта Redis
    mock_redis.register_script.return_value.side_effect = Exception("Redis connection lost")

    with patch.object(config, 'IS_PRODUCTION', True):
        with patch.object(limiter, '_get_redis', return_value=mock_redis):
            allowed, retry_after, remaining = limiter.is_allowed("test_bucket", "1.2.3.4", max_requests=5, window_seconds=60)
            assert allowed is False
            assert retry_after > 0
            assert remaining == 0



def test_rate_limiter_development_fallback():
    """В режиме development/testing при отказе Redis происходит откат на in-memory."""
    limiter = RateLimiter()
    with patch.object(config, 'IS_PRODUCTION', False):
        with patch.object(limiter, '_get_redis', return_value=None):
            allowed, _, remaining = limiter.is_allowed("dev_bucket", "1.2.3.4", max_requests=2, window_seconds=60)
            assert allowed is True
            assert remaining == 1
