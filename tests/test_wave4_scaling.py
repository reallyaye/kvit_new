# -*- coding: utf-8 -*-
"""
Тесты Wave 4: Масштабирование и распределенная инфраструктура.
Проверяют:
1. Защиту от deadlock при трансляции WebSocket сообщений при отключении/сбое сокетов.
2. Публикацию и формат сообщений в Redis Pub/Sub для межпроцессной шины событий.
3. Распределенный скользящий ограничитель запросов RateLimiter (Redis + In-Memory fallback).
4. Проверку готовности /ready (атомарная проверка записи хранилища и экранирование чувствительных данных).
5. Согласованность Nginx и SSL-конфигурации.
"""
import io
import json
import os
import socket
from unittest.mock import MagicMock, patch

import config
from server import AppRequestHandler
from services.security.rate_limiter import RateLimiter
from services.websocket.ws_manager import WebSocketManager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_websocket_broadcast_deadlock_prevention():
    """Проверка, что отключение неисправного сокета во время broadcast не вызывает deadlock."""
    mgr = WebSocketManager()
    try:
        s_srv1, s_cli1 = socket.socketpair()
        s_srv2, s_cli2 = socket.socketpair()

        mgr.register(s_srv1, "127.0.0.1")
        mgr.register(s_srv2, "127.0.0.1")

        # Принудительно закрываем второй клиентский сокет, чтобы sendall выбросил исключение
        s_cli2.close()
        s_srv2.close()

        # broadcast не должен зависнуть (deadlock) и должен корректно отработать
        mgr.broadcast("task_progress", {"progress": 50}, publish_to_redis=False)

        # Проверяем, что первый клиент получил сообщение
        raw_msg = s_cli1.recv(1024)
        assert len(raw_msg) > 0
        assert b"task_progress" in raw_msg

        # Неисправный сокет должен быть удален из пула клиентов
        with mgr._lock:
            assert s_srv2.fileno() not in mgr._clients

        s_srv1.close()
        s_cli1.close()
    finally:
        mgr._running = False


def test_websocket_redis_pubsub_publish():
    """Проверка отправки события в Redis Pub/Sub при вызове broadcast."""
    mgr = WebSocketManager()
    try:
        mock_redis = MagicMock()
        mgr._redis_pub = mock_redis

        with patch.object(config, 'REDIS_ENABLED', True):
            with patch('services.websocket.ws_manager.REDIS_LIB_AVAILABLE', True):
                mgr.broadcast("job_done", {"job_id": "123"}, publish_to_redis=True)

        assert mock_redis.publish.called
        call_args = mock_redis.publish.call_args[0]
        channel = call_args[0]
        payload = json.loads(call_args[1])

        assert channel == getattr(config, 'REDIS_WS_CHANNEL', 'kvit:events:ws')
        assert payload['event'] == 'job_done'
        assert payload['data']['job_id'] == '123'
        assert payload['origin_node'] == mgr._node_id
    finally:
        mgr._running = False


def test_rate_limiter_in_memory_and_redis_fallback():
    """Тестирование скользящего окна лимитера запросов и fallback-механизма."""
    limiter = RateLimiter()

    # Лимит 3 запроса в минуту
    bucket = "test_search"
    key = "ip_1.2.3.4"

    ok1, retry1, rem1 = limiter.is_allowed(bucket, key, max_requests=3, window_seconds=60)
    assert ok1 is True
    assert rem1 == 2

    ok2, retry2, rem2 = limiter.is_allowed(bucket, key, max_requests=3, window_seconds=60)
    assert ok2 is True
    assert rem2 == 1

    ok3, retry3, rem3 = limiter.is_allowed(bucket, key, max_requests=3, window_seconds=60)
    assert ok3 is True
    assert rem3 == 0

    # 4-й запрос должен быть заблокирован
    ok4, retry4, rem4 = limiter.is_allowed(bucket, key, max_requests=3, window_seconds=60)
    assert ok4 is False
    assert retry4 > 0
    assert rem4 == 0


def test_rate_limiter_redis_sliding_window_script():
    """Тестирование вызова Redis Lua-скрипта при доступном Redis."""
    mock_redis = MagicMock()
    mock_script = MagicMock()
    # Имитация ответа Lua-скрипта: [allowed, retry_after, remaining]
    mock_script.return_value = [1, 0, 4]
    mock_redis.register_script.return_value = mock_script

    limiter = RateLimiter(redis_client=mock_redis)
    limiter._script = mock_script

    allowed, retry_after, remaining = limiter.is_allowed("api", "user_1", max_requests=5, window_seconds=60)
    assert allowed is True
    assert retry_after == 0
    assert remaining == 4
    assert mock_script.called


def test_readiness_probe_storage_write_probe_and_error_sanitization(tmp_path, monkeypatch):
    """Проверка /ready: тестирование записи в хранилище и сокрытие деталей БД-ошибок."""
    test_receipts = tmp_path / "receipts"
    monkeypatch.setattr(config, 'RECEIPTS_DIR', str(test_receipts))

    class DummyServer:
        pass

    handler = AppRequestHandler.__new__(AppRequestHandler)
    handler.server = DummyServer()
    handler.headers = {}
    handler.wfile = io.BytesIO()

    # Перехватываем send_json
    captured_json = {}
    captured_status = []

    def mock_send_json(data, status=200, headers=None):
        captured_json.update(data)
        captured_status.append(status)

    handler.send_json = mock_send_json

    # 1. Успешный запуск
    handler._handle_ready()
    assert captured_status[0] == 200
    assert captured_json['status'] == 'ready'
    assert captured_json['checks']['storage'] == 'ok'
    assert captured_json['checks']['database'] == 'ok'

    # 2. Имитация ошибки базы данных в production — ответ должен содержать 503 и 'error' без учетных данных
    captured_json.clear()
    captured_status.clear()
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)

    with patch('server.get_db') as mock_db:
        mock_db.side_effect = Exception("FATAL: password authentication failed for user postgres")
        handler._handle_ready()

        assert captured_status[0] == 503
        assert captured_json['status'] == 'not_ready'
        # В тексте ответа не должно быть пароля или внутренней ошибки
        assert captured_json['checks']['database'] == 'error'
        assert "password" not in json.dumps(captured_json)


def test_nginx_config_ssl_and_body_size():
    """Проверка конфигурации Nginx на соответствие путям сертификатов и лимитам загрузки."""
    nginx_conf_path = os.path.join(BASE_DIR, 'nginx', 'nginx.conf')
    assert os.path.isfile(nginx_conf_path)

    with open(nginx_conf_path, 'r', encoding='utf-8') as f:
        conf = f.read()

    # Проверяем согласованность путей сертификатов
    assert "/etc/nginx/ssl/fullchain.pem" in conf
    assert "/etc/nginx/ssl/privkey.pem" in conf
    # Проверяем согласованность максимального размера запроса
    assert "client_max_body_size 500m;" in conf
