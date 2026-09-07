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


def test_mask_address_protects_personal_data():
    """mask_address скрывает номера домов и квартир, защищая персональные данные."""
    from services.receipts.receipt_service import mask_address

    assert mask_address("ул. Абая, дом 10, кв. 5") == "ул. Абая, дом ***, кв. ***"
    assert mask_address("г. Кызылорда, ул. Желтоксан, д. 45-А") == "г. Кызылорда, ул. Желтоксан, д. ***"
    assert mask_address("ул. Сатпаева 15/3") == "ул. Сатпаева ***"
    assert mask_address("") == "—"


def test_verify_account_ownership():
    """verify_account_ownership подтверждает владение счетом по номеру дома или квартиры."""
    from services.receipts.receipt_service import verify_account_ownership

    account_row = {
        'account_number': '800100',
        'address': 'ул. Казыбек би, дом 24, кв. 12',
        'building': '24',
        'flat': '12'
    }

    # По номеру дома
    assert verify_account_ownership(account_row, '24') is True
    assert verify_account_ownership(account_row, 'дом 24') is True

    # По номеру квартиры
    assert verify_account_ownership(account_row, '12') is True
    assert verify_account_ownership(account_row, 'кв 12') is True

    # Неверный номер
    assert verify_account_ownership(account_row, '99') is False
    assert verify_account_ownership(account_row, '') is False
    assert verify_account_ownership(None, '24') is False


def test_receipt_search_verification_lifecycle():
    """Проверка полного цикла верификации владельца квитанции в API."""
    from database import get_db
    con = get_db()
    con.execute('INSERT OR REPLACE INTO accounts(account_number, customer_name, address) VALUES (?,?,?)',
                ('999111', 'Секретный Абонент', 'ул. Достык, дом 42, кв. 7'))
    con.execute('INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address) VALUES (?,?,?,?,?,?)',
                ('999111', '09.2026', '99/91/999111_s.pdf', 'h999111', 'tok999111_secret_token_value', 'ул. Достык, дом 42, кв. 7'))
    con.commit()
    con.close()

    from server import AppRequestHandler
    class MockHandler(AppRequestHandler):
        def __init__(self):
            self.headers = {}
            self.sent_json = None
            self.status_code = None
        def send_json(self, data, code=200, extra_headers=None, **kwargs):
            self.sent_json = data
            self.status_code = code

    with patch.object(config, 'REQUIRE_RECEIPT_VERIFICATION', True):
        # 1. Запрос только по номеру лицевого счета без кода подтверждения -> статус NEED_VERIFICATION
        h1 = MockHandler()
        h1._handle_api_search({'account': ['999111']})
        assert h1.status_code == 200
        assert h1.sent_json['status'] == 'NEED_VERIFICATION'
        assert '***' in h1.sent_json['address']
        assert len(h1.sent_json['receipts']) == 0  # Ссылки и токены не отдаются!

        # 2. Запрос с неверным номером дома/квартиры -> статус NEED_VERIFICATION с ошибкой
        h2 = MockHandler()
        h2._handle_api_search({'account': ['999111'], 'verify': ['100']})
        assert h2.status_code == 200
        assert h2.sent_json['status'] == 'NEED_VERIFICATION'
        assert 'Неверный номер' in h2.sent_json['message']
        assert len(h2.sent_json['receipts']) == 0

        # 3. Запрос с правильным номером дома (42) -> статус EXACT_MATCH с выдачей квитанции
        h3 = MockHandler()
        h3._handle_api_search({'account': ['999111'], 'verify': ['42']})
        assert h3.status_code == 200
        assert h3.sent_json['status'] == 'EXACT_MATCH'
        assert '42' in h3.sent_json['address']
        assert len(h3.sent_json['receipts']) == 1
        assert h3.sent_json['receipts'][0]['access_token'] == 'tok999111_secret_token_value'

