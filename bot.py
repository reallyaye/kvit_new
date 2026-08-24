#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автономная точка входа для запуска Telegram-бота Kvit-App.
Использование:
    python bot.py
"""

import sys
import os
import signal
import config
from logger import logger
from database import migrate_db
from services.telegram_bot import telegram_bot_service

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("=" * 70)
        logger.error("❌ ОШИБКА КОНФИГУРАЦИИ: Переменная TELEGRAM_BOT_TOKEN не задана!")
        logger.error("Получите токен бота у @BotFather в Telegram и укажите его в .env:")
        logger.error("    TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        logger.error("=" * 70)
        sys.exit(1)

    # Проверяем миграции базы данных перед стартом
    migrate_db()

    logger.info("Запуск Telegram-бота Kvit-App в автономном режиме...")
    if config.TELEGRAM_ADMIN_IDS:
        logger.info(f"Настроены ID администраторов: {list(config.TELEGRAM_ADMIN_IDS)}")
    else:
        logger.info("ID администраторов не заданы в .env — вход через /login <пароль>")

    def handle_signal(sig, frame):
        logger.info("Остановка Telegram-бота по сигналу...")
        telegram_bot_service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        telegram_bot_service.run_polling()
    except KeyboardInterrupt:
        logger.info("Остановка Telegram-бота...")
        telegram_bot_service.stop()

if __name__ == '__main__':
    main()
