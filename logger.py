import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from config import BASE, LOG_FILE, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

def setup_logger(name: str = "kvit") -> logging.Logger:
    """Создаёт и конфигурирует централизованный логер с выводом в консоль и ротируемый файл."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    log_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Консольный обработчик (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 2. Файловый обработчик с ротацией
    try:
        log_path = LOG_FILE if os.path.isabs(LOG_FILE) else os.path.join(BASE, LOG_FILE)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Не удалось инициализировать файловый логер ({LOG_FILE}): {e}")

    logger.propagate = False
    return logger

logger = setup_logger()
