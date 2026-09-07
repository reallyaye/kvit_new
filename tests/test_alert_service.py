# -*- coding: utf-8 -*-
"""
Тесты подсистемы оперативных оповещений и мониторинга (AlertService):
1. Оповещения о сбоях SMTP (регистрация ошибок, формирование алертов, сброс).
2. Оповещения о накопившихся необработанных обращениях (превышение лимита штук или времени).
3. Оповещения о просроченных ответах (превышение установленного законом РК 15-дневного срока).
4. Оповещения о росте и всплесках ошибок HTTP 500.
5. Дедупликация и кулдаун отправки оповещений в Telegram.
6. Интеграционный HTTP-тест эндпоинта /api/admin/alerts и отображения в UI.
"""

import time
import urllib.parse
import urllib.request

from database.connection import write_transaction
from services.metrics.alert_service import AlertSeverity, alert_service
from services.metrics.collector import metrics_collector
from tests.test_appeals_e2e import _http_request


def test_smtp_error_alert():
    # Очищаем недавние ошибки SMTP
    metrics_collector._smtp_errors.clear()
    metrics_collector._last_smtp_error = None

    # До ошибок алерт отсутствует
    assert alert_service.evaluate_smtp_errors() is None

    # Регистрируем единичные ошибки
    metrics_collector.record_smtp_error("smtplib.SMTPConnectError: connection refused")
    alert = alert_service.evaluate_smtp_errors()
    assert alert is not None
    assert alert["id"] == "smtp_error"
    assert alert["severity"] == AlertSeverity.WARNING
    assert "connection refused" in alert["message"]
    assert alert["metadata"]["error_count"] == 1

    # Регистрируем еще 4 ошибки (итого 5 -> эскалация до CRITICAL)
    for _ in range(4):
        metrics_collector.record_smtp_error("smtplib.SMTPServerDisconnected: unexpected disconnect")

    crit_alert = alert_service.evaluate_smtp_errors()
    assert crit_alert["severity"] == AlertSeverity.CRITICAL
    assert crit_alert["metadata"]["error_count"] == 5

    # Успешная отправка
    metrics_collector.record_smtp_success()
    assert metrics_collector._smtp_success_total >= 1


def test_unhandled_appeals_backlog_alert():
    # Очищаем таблицу обращений
    with write_transaction() as con:
        con.execute("DELETE FROM appeals")

    assert alert_service.evaluate_unhandled_appeals() is None

    now = time.time()
    # 1. Создаем 10 обращений со статусом NEW (порог количества)
    with write_transaction() as con:
        for i in range(10):
            con.execute(
                """
                INSERT INTO appeals (
                    registration_number, category, applicant_name, phone, email,
                    service_address, message, status, consent, submitted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"BACKLOG-{i}",
                    "billing",
                    f"Заявитель {i}",
                    "+77001112233",
                    f"user{i}@test.kz",
                    "ул. Тестовая",
                    "Сообщение",
                    "NEW",
                    1,
                    now,
                    now,
                ),
            )

    alert = alert_service.evaluate_unhandled_appeals()
    assert alert is not None
    assert alert["id"] == "unhandled_appeals"
    assert alert["metadata"]["count"] >= 10

    # 2. Проверяем старейшее обращение > 24 часов
    with write_transaction() as con:
        con.execute("DELETE FROM appeals")
        con.execute(
            """
            INSERT INTO appeals (
                registration_number, category, applicant_name, phone, email,
                service_address, message, status, consent, submitted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "OLD-1",
                "other",
                "Старый заявитель",
                "+77001112233",
                "old@test.kz",
                "ул. Тестовая",
                "Сообщение",
                "NEW",
                1,
                now - (30 * 3600),  # 30 часов назад
                now - (30 * 3600),
            ),
        )

    alert_old = alert_service.evaluate_unhandled_appeals()
    assert alert_old is not None
    assert alert_old["metadata"]["oldest_hours"] >= 24.0


def test_overdue_appeals_alert():
    now = time.time()
    with write_transaction() as con:
        con.execute("DELETE FROM appeals")
        # Обращение с нарушением установленного законом РК 15-дневного срока (16 дней назад)
        con.execute(
            """
            INSERT INTO appeals (
                registration_number, category, applicant_name, phone, email,
                service_address, message, status, consent, submitted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "OVERDUE-15D",
                "quality",
                "Ахметов А.А.",
                "+77019998877",
                "akhmetov@test.kz",
                "ул. Абая 50",
                "Нет света",
                "IN_REVIEW",
                1,
                now - (16 * 86400),  # 16 календарных дней назад
                now,
            ),
        )

    alert = alert_service.evaluate_overdue_appeals()
    assert alert is not None
    assert alert["id"] == "overdue_appeals"
    assert alert["severity"] == AlertSeverity.CRITICAL
    assert "OVERDUE-15D" in alert["message"]
    assert alert["metadata"]["overdue_count"] == 1
    assert alert["metadata"]["oldest_days"] >= 15.0

    # После закрытия обращения (статус ANSWERED) просрочки больше нет
    with write_transaction() as con:
        con.execute("UPDATE appeals SET status = 'ANSWERED' WHERE registration_number = 'OVERDUE-15D'")

    assert alert_service.evaluate_overdue_appeals() is None


def test_http_500_spike_alert():
    metrics_collector._rolling_requests.clear()

    # До ошибок алерт отсутствует
    assert alert_service.evaluate_http_500_spikes() is None

    # Регистрируем 5 ошибок HTTP 500
    for _ in range(5):
        metrics_collector.record_request("GET", "/api/test", 500, 0.05)

    alert = alert_service.evaluate_http_500_spikes()
    assert alert is not None
    assert alert["id"] == "http_500_spike"
    assert alert["severity"] == AlertSeverity.CRITICAL
    assert alert["metadata"]["count_5xx"] == 5


def test_telegram_dispatch_and_cooldown(monkeypatch):
    import config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "fake_bot_token_12345")
    monkeypatch.setattr(config, "TELEGRAM_ADMIN_IDS", [12345678, 87654321])

    sent_messages = []

    class MockTelegramClient:
        def send_message(self, chat_id, text, **kwargs):
            sent_messages.append({"chat_id": chat_id, "text": text})

    mock_client = MockTelegramClient()

    # Очищаем состояние для изоляции теста
    metrics_collector._rolling_requests.clear()
    metrics_collector._smtp_errors.clear()
    with write_transaction() as con:
        con.execute("DELETE FROM appeals")

    # Создаем ситуацию строго с одним алертом SMTP
    metrics_collector.record_smtp_error("Test SMTP Failure")
    alert_service._last_alert_dispatch.clear()

    # Первая отправка
    sent_count = alert_service.dispatch_telegram_alerts(client=mock_client)
    assert sent_count == 2  # Отправлено обоим администраторам
    assert len(sent_messages) == 2
    assert "Сбои отправки почты" in sent_messages[0]["text"]

    # Повторная немедленная отправка блокируется кулдауном
    sent_count_2 = alert_service.dispatch_telegram_alerts(client=mock_client)
    assert sent_count_2 == 0


def test_admin_alerts_api_and_ui_integration(e2e_server):
    base_url = e2e_server["base_url"]
    admin_password = e2e_server["admin_password"]

    # 1. Неавторизованный запрос к /api/admin/alerts -> 401
    res_unauth = _http_request(f"{base_url}/api/admin/alerts")
    assert res_unauth["status"] == 401

    # 2. Авторизуемся как администратор
    login_payload = urllib.parse.urlencode(
        {"username": "admin", "password": admin_password}
    ).encode("utf-8")
    res_login = _http_request(
        f"{base_url}/login",
        method="POST",
        data=login_payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert res_login["status"] in (302, 303)
    session_cookie = res_login["headers"]["Set-Cookie"].split(";")[0]

    # 3. Авторизованный запрос к /api/admin/alerts -> 200
    res_api = _http_request(
        f"{base_url}/api/admin/alerts",
        headers={"Cookie": session_cookie},
    )
    assert res_api["status"] == 200
    import json
    data = json.loads(res_api["body"])
    assert "alerts" in data
    assert "count" in data
    assert "has_critical" in data

    # 4. Проверяем отображение алертов в UI /admin/appeals при наличии ошибки SMTP
    metrics_collector.record_smtp_error("Simulated SMTP Server Down")
    res_admin_page = _http_request(
        f"{base_url}/admin/appeals",
        headers={"Cookie": session_cookie},
    )
    assert res_admin_page["status"] == 200
    assert "Сбои отправки почты" in res_admin_page["body"]
