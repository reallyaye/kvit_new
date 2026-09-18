# -*- coding: utf-8 -*-
"""
Периодический фоновый планировщик очистки и минимизации персональных данных.
Выполняет автоматическое исполнение политик хранения:
- Удаление сетевых визитов старше 90 дней (k-anonymity & data minimization);
- Обезличивание архивных обращений граждан старше 3 лет (ст. 8, 24 Закона РК № 94-V).
"""
import threading
import time

from logger import logger
from services.analytics import stats_service
from services.appeals import appeal_service
from services.receipts import receipt_service

_scheduler_started = False
_scheduler_lock = threading.Lock()
_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None


ADVISORY_LOCK_ID = 949494


def run_retention_cycle(
    visits_days: int = 90,
    appeals_days: int = 1095,
    deleted_receipts_days: int | None = None,
) -> dict:
    """Выполняет один цикл автоматической очистки данных с защитой от параллельного запуска."""
    from database.connection import get_db, is_postgres_configured

    lock_acquired = False
    con = None
    if is_postgres_configured():
        try:
            con = get_db()
            cur = con.execute("SELECT pg_try_advisory_lock(?)", (ADVISORY_LOCK_ID,))
            row = cur.fetchone()
            lock_acquired = bool(row[0]) if row else False
            if not lock_acquired:
                logger.info("[Retention] Цикл очистки уже выполняется другим процессом/воркером. Пропуск.")
                return {'purged_visits': 0, 'anonymized_appeals': 0, 'purged_deleted_receipts': 0}
        except Exception as exc:
            logger.warning("[Retention] Не удалось проверить advisory lock PostgreSQL: %s", exc)

    try:
        logger.info("[Retention] Запуск планового цикла очистки устаревших персональных данных...")
        results = {'purged_visits': 0, 'anonymized_appeals': 0, 'purged_deleted_receipts': 0}
        try:
            results['purged_visits'] = stats_service.purge_old_visits(days=visits_days)
        except Exception as exc:
            logger.warning("[Retention] Сбой очистки визитов: %s", exc)

        try:
            results['anonymized_appeals'] = appeal_service.purge_expired_appeals(retention_days=appeals_days)
        except Exception as exc:
            logger.warning("[Retention] Сбой обезличивания обращений: %s", exc)

        try:
            import config
            quarantine_days = (
                deleted_receipts_days
                if deleted_receipts_days is not None
                else config.DELETED_RECEIPTS_RETENTION_DAYS
            )
            results['purged_deleted_receipts'] = receipt_service.purge_deleted_receipt_files(
                days=quarantine_days
            )
        except Exception as exc:
            logger.warning("[Retention] Сбой очистки карантина удалённых квитанций: %s", exc)

        try:
            import os
            cutoff_time = time.time() - (max(1, visits_days) * 86400.0)
            log_dirs = ['/app/logs', os.path.join(os.getcwd(), 'logs'), '/var/log/nginx']
            purged_logs = 0
            for ldir in log_dirs:
                if os.path.isdir(ldir):
                    for entry in os.scandir(ldir):
                        if entry.is_file() and (entry.name.endswith(('.gz', '.old')) or '.log.' in entry.name):
                            if entry.stat().st_mtime < cutoff_time:
                                try:
                                    os.remove(entry.path)
                                    purged_logs += 1
                                except OSError:
                                    pass
            if purged_logs > 0:
                logger.info("[Retention] Удалено %d архивных файлов логов (>%d дн.)", purged_logs, visits_days)
        except Exception as exc:
            logger.debug("[Retention] Очистка файлов логов завершилась: %s", exc)

        try:
            results['retried_appeals'] = appeal_service.retry_pending_responses()
        except Exception as exc:
            logger.warning("[Retention] Сбой повторной отправки ответов: %s", exc)

        logger.info(
            "[Retention] Плановый цикл завершен: удалено %d сетевых визитов (>%d дн.), обезличено %d архивных обращений (>%d дн.), очищено %d PDF из карантина",
            results['purged_visits'],
            visits_days,
            results['anonymized_appeals'],
            appeals_days,
            results['purged_deleted_receipts'],
        )
        return results
    finally:
        if lock_acquired and con is not None:
            try:
                con.execute("SELECT pg_advisory_unlock(?)", (ADVISORY_LOCK_ID,))
            except Exception as exc:
                logger.warning("[Retention] Ошибка снятия advisory lock: %s", exc)
            try:
                con.close()
            except Exception:
                pass


def _retention_worker_loop(interval_seconds: int = 86400, initial_delay: int = 60):
    if initial_delay > 0:
        if _stop_event.wait(timeout=initial_delay):
            return
    last_retention = 0.0
    while not _stop_event.is_set():
        now = time.time()
        if now - last_retention >= interval_seconds:
            try:
                run_retention_cycle()
                last_retention = now
            except Exception as exc:
                logger.error("[Retention] Непредвиденная ошибка в цикле очистки: %s", exc)
        try:
            appeal_service.retry_pending_responses()
        except Exception as exc:
            logger.debug("[Retention] Ошибка повтора email обращений: %s", exc)
        if _stop_event.wait(timeout=30.0):
            break


def start_retention_scheduler(interval_seconds: int = 86400, initial_delay: int = 60) -> bool:
    """Запускает фоновый поток-демон для ежедневной очистки данных."""
    global _scheduler_started, _scheduler_thread
    with _scheduler_lock:
        if _scheduler_started and _scheduler_thread and _scheduler_thread.is_alive():
            return False
        _stop_event.clear()
        _scheduler_started = True
        _scheduler_thread = threading.Thread(
            target=_retention_worker_loop,
            args=(interval_seconds, initial_delay),
            name="RetentionCleanerThread",
            daemon=True,
        )
        _scheduler_thread.start()
    logger.info("[Retention] Фоновый планировщик очистки запущен (интервал: %d сек.)", interval_seconds)
    return True


def stop_retention_scheduler(timeout: float = 5.0) -> bool:
    """Штатно останавливает фоновый поток очистки данных."""
    global _scheduler_started, _scheduler_thread
    with _scheduler_lock:
        if not _scheduler_started:
            return True
        _stop_event.set()
        thread = _scheduler_thread
        _scheduler_started = False
        _scheduler_thread = None

    if thread and thread.is_alive():
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("[Retention] Поток RetentionCleanerThread не завершился за %.1f сек.", timeout)
            return False
    logger.info("[Retention] Фоновый планировщик очистки успешно остановлен")
    return True
