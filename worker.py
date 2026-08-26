#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автономный процесс фонового воркера (Dedicated PDF Worker).
Обрабатывает задачи PDF-парсинга, OCR и импорта из Redis/очереди изолированно от веб-сервера.
Использование:
    python worker.py --workers 4
    python worker.py --redis-url redis://localhost:6379/0 --workers 8
"""
import argparse
import os
import signal
import sys
import time

import config
from database import migrate_db
from logger import logger
from services.tasks.queue_backend import create_task_queue_backend
from services.tasks.task_manager import TaskQueueManager


def main():
    parser = argparse.ArgumentParser(description="Автономный фоновый воркер обработки квитанций и OCR")
    parser.add_argument('--workers', type=int, default=getattr(config, 'WORKER_COUNT', 4), help="Количество параллельных потоков воркера")
    parser.add_argument('--redis-url', type=str, default=getattr(config, 'REDIS_URL', ''), help="URL подключения к Redis")
    args = parser.parse_args()

    if args.redis_url:
        os.environ['REDIS_URL'] = args.redis_url
        config.REDIS_URL = args.redis_url
        config.REDIS_ENABLED = True

    logger.info("=" * 70)
    logger.info(f"🚀 Запуск выделенного фонового воркера PDF/OCR")
    logger.info(f"   Потоков обработки: {args.workers}")
    logger.info(f"   Бэкенд очереди:    {'Redis (' + config.REDIS_URL + ')' if config.REDIS_ENABLED else 'In-Memory Queue'}")
    logger.info(f"   Лимит OCR потоков: {config.MAX_OCR_CONCURRENT_WORKERS}")
    logger.info("=" * 70)

    # Проверка схемы базы данных
    try:
        migrate_db()
        logger.info("[Worker] База данных проверена.")
    except Exception as e:
        logger.critical(f"[Worker] ❌ Ошибка проверки БД: {e}")
        sys.exit(1)

    backend = create_task_queue_backend()
    manager = TaskQueueManager(backend=backend, max_workers=args.workers)
    manager.start()

    stop_requested = False

    def handle_shutdown(signum, frame):
        nonlocal stop_requested
        if not stop_requested:
            stop_requested = True
            logger.info(f"[Worker] Получен сигнал {signum}. Выполняется корректное завершение (Graceful Shutdown)...")
            manager.stop()
            sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        while not stop_requested:
            time.sleep(2.0)
    except KeyboardInterrupt:
        handle_shutdown(signal.SIGINT, None)


if __name__ == '__main__':
    main()
