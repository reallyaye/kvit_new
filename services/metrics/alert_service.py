# -*- coding: utf-8 -*-
"""
Подсистема мониторинга и формирования оперативных оповещений (Alerting Service).
Контролирует 4 критических показателя промышленной эксплуатации:
1. Ошибки SMTP (сбои отправки почтовых уведомлений канцелярии и заявителям).
2. Накопившиеся необработанные обращения (очередь обращений в статусе NEW).
3. Просроченные ответы на обращения (превышение установленного законом РК 15-дневного срока).
4. Рост ошибок HTTP 500 (всплеск пятисотых ошибок за скользящее окно 5 минут).
"""

import time
from typing import Any, Dict, List, Optional

import config
from database import get_db
from logger import logger
from services.metrics.collector import metrics_collector


class AlertSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertService:
    """Сервис формирования, фильтрации и отправки оперативных алертов."""

    # Пороговые значения
    OVERDUE_DAYS_CRITICAL = 15.0  # Установленный законом РК срок ответа
    OVERDUE_DAYS_WARNING = 10.0
    UNHANDLED_APPEALS_COUNT_THRESHOLD = 10
    UNHANDLED_APPEALS_HOURS_THRESHOLD = 24.0
    HTTP_500_SPIKE_COUNT_THRESHOLD = 5
    HTTP_500_SPIKE_RATE_THRESHOLD_PCT = 5.0
    HTTP_500_MIN_REQUESTS_FOR_RATE = 20
    SMTP_WINDOW_SECONDS = 900.0  # 15 минут

    def __init__(self):
        self._last_alert_dispatch: Dict[str, float] = {}
        self._dispatch_cooldown_seconds = 900.0  # 15 минут между повторными уведомлениями в Telegram

    def evaluate_smtp_errors(self) -> Optional[Dict[str, Any]]:
        """Проверяет наличие недавних ошибок отправки почты через SMTP."""
        recent_errors = metrics_collector.get_recent_smtp_errors(self.SMTP_WINDOW_SECONDS)
        if not recent_errors:
            return None

        last_err = recent_errors[-1]
        err_count = len(recent_errors)
        return {
            "id": "smtp_error",
            "severity": AlertSeverity.WARNING if err_count < 5 else AlertSeverity.CRITICAL,
            "title": "Сбои отправки почты (SMTP)",
            "message": f"Зафиксировано {err_count} ошибок отправки email за последние 15 минут. Последняя ошибка: {last_err.get('error', 'Unknown')}",
            "created_at": last_err.get("timestamp", time.time()),
            "metadata": {
                "error_count": err_count,
                "last_error": last_err.get("error"),
            },
        }

    def evaluate_unhandled_appeals(self) -> Optional[Dict[str, Any]]:
        """Проверяет накопление необработанных обращений (статус NEW)."""
        now = time.time()
        try:
            con = get_db()
            try:
                row = con.execute(
                    "SELECT COUNT(*), MIN(submitted_at) FROM appeals WHERE status = 'NEW'"
                ).fetchone()
                count = row[0] if row else 0
                oldest_ts = row[1] if row and row[1] is not None else None
            finally:
                con.close()
        except Exception as exc:
            logger.warning("[Alerts] Не удалось проверить очередь обращений: %s", exc)
            return None

        if count == 0:
            return None

        oldest_hours = round((now - oldest_ts) / 3600.0, 1) if oldest_ts else 0.0
        is_count_exceeded = count >= self.UNHANDLED_APPEALS_COUNT_THRESHOLD
        is_age_exceeded = oldest_hours >= self.UNHANDLED_APPEALS_HOURS_THRESHOLD

        if is_count_exceeded or is_age_exceeded:
            severity = AlertSeverity.CRITICAL if (count >= 25 or oldest_hours >= 48) else AlertSeverity.WARNING
            details = []
            if is_count_exceeded:
                details.append(f"{count} обращений ожидают обработки")
            if is_age_exceeded:
                details.append(f"старейшее обращение ожидает более {oldest_hours} ч.")

            return {
                "id": "unhandled_appeals",
                "severity": severity,
                "title": "Накопились необработанные обращения",
                "message": f"В очереди {', '.join(details)}.",
                "created_at": now,
                "metadata": {
                    "count": count,
                    "oldest_hours": oldest_hours,
                },
            }
        return None

    def evaluate_overdue_appeals(self) -> Optional[Dict[str, Any]]:
        """Проверяет наличие обращений с превышением установленного законом РК 15-дневного срока ответа."""
        now = time.time()
        critical_cutoff = now - (self.OVERDUE_DAYS_CRITICAL * 86400.0)

        try:
            con = get_db()
            try:
                rows = con.execute(
                    """
                    SELECT id, registration_number, applicant_name, submitted_at, status
                    FROM appeals
                    WHERE status IN ('NEW', 'IN_REVIEW') AND submitted_at < ?
                    ORDER BY submitted_at ASC
                    """,
                    (critical_cutoff,),
                ).fetchall()
            finally:
                con.close()
        except Exception as exc:
            logger.warning("[Alerts] Не удалось проверить просроченные обращения: %s", exc)
            return None

        if not rows:
            return None

        overdue_count = len(rows)
        sample_numbers = [r[1] for r in rows[:3]]
        sample_str = ", ".join(sample_numbers) + ("..." if overdue_count > 3 else "")
        oldest_days = round((now - float(rows[0][3])) / 86400.0, 1)

        return {
            "id": "overdue_appeals",
            "severity": AlertSeverity.CRITICAL,
            "title": "Просрочены ответы на обращения граждан",
            "message": f"Обнаружено {overdue_count} активных обращений с нарушением 15-дневного срока РК (макс. задержка: {oldest_days} дн.). Номера: {sample_str}",
            "created_at": now,
            "metadata": {
                "overdue_count": overdue_count,
                "oldest_days": oldest_days,
                "sample_numbers": sample_numbers,
            },
        }

    def evaluate_http_500_spikes(self) -> Optional[Dict[str, Any]]:
        """Проверяет всплеск внутренних ошибок сервера (HTTP 5xx) за последние 5 минут."""
        now = time.time()
        stats = metrics_collector.get_recent_5xx_rate(window_seconds=300.0)
        count_5xx = stats.get("count_5xx", 0)
        total = stats.get("total_requests", 0)
        rate_pct = stats.get("rate_pct", 0.0)

        is_count_spike = count_5xx >= self.HTTP_500_SPIKE_COUNT_THRESHOLD
        is_rate_spike = (
            total >= self.HTTP_500_MIN_REQUESTS_FOR_RATE
            and rate_pct >= self.HTTP_500_SPIKE_RATE_THRESHOLD_PCT
        )

        if is_count_spike or is_rate_spike:
            return {
                "id": "http_500_spike",
                "severity": AlertSeverity.CRITICAL,
                "title": "Всплеск ошибок сервера HTTP 500",
                "message": f"Зафиксировано {count_5xx} ошибок HTTP 5xx за последние 5 минут ({rate_pct}% от общего трафика {total} запр.).",
                "created_at": now,
                "metadata": {
                    "count_5xx": count_5xx,
                    "total_requests": total,
                    "rate_pct": rate_pct,
                },
            }
        return None

    def evaluate_all(self) -> List[Dict[str, Any]]:
        """Вычисляет и возвращает список всех текущих активных алертов."""
        alerts: List[Dict[str, Any]] = []

        smtp_alert = self.evaluate_smtp_errors()
        if smtp_alert:
            alerts.append(smtp_alert)

        unhandled_alert = self.evaluate_unhandled_appeals()
        if unhandled_alert:
            alerts.append(unhandled_alert)

        overdue_alert = self.evaluate_overdue_appeals()
        if overdue_alert:
            alerts.append(overdue_alert)

        http_500_alert = self.evaluate_http_500_spikes()
        if http_500_alert:
            alerts.append(http_500_alert)

        return alerts

    get_active_alerts = evaluate_all

    def dispatch_telegram_alerts(self, client=None) -> int:
        """
        Отправляет критические алерты в Telegram администраторам с соблюдением кулдауна.
        Возвращает количество отправленных сообщений.
        """
        bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", None)
        admin_ids = getattr(config, "TELEGRAM_ADMIN_IDS", [])
        if not bot_token and client is None:
            return 0
        if not admin_ids:
            return 0

        alerts = self.evaluate_all()
        if not alerts:
            return 0

        now = time.time()
        dispatched_count = 0

        if client is None:
            from services.telegram_bot.telegram_client import TelegramClient
            client = TelegramClient(bot_token)

        for alert in alerts:
            # Отправляем только WARNING и CRITICAL
            if alert["severity"] not in (AlertSeverity.WARNING, AlertSeverity.CRITICAL):
                continue

            alert_id = alert["id"]
            last_time = self._last_alert_dispatch.get(alert_id, 0.0)
            if now - last_time < self._dispatch_cooldown_seconds:
                continue

            icon = "🚨" if alert["severity"] == AlertSeverity.CRITICAL else "⚠️"
            text = (
                f"{icon} <b>[ОПОВЕЩЕНИЕ СИСТЕМЫ]</b> {alert['title']}\n\n"
                f"<b>Уровень:</b> {alert['severity']}\n"
                f"<b>Описание:</b> {alert['message']}\n"
                f"<b>Время:</b> {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert['created_at']))}"
            )

            for admin_id in admin_ids:
                try:
                    client.send_message(admin_id, text, parse_mode="HTML")
                    dispatched_count += 1
                except Exception as exc:
                    logger.warning("[Alerts] Не удалось отправить алерт админу %s: %s", admin_id, exc)

            self._last_alert_dispatch[alert_id] = now

        return dispatched_count


alert_service = AlertService()
