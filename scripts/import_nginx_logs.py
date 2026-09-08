# -*- coding: utf-8 -*-
"""
Утилита импорта исторических логов Nginx access.log в аналитическую таблицу page_visits.
Использование:
    python scripts/import_nginx_logs.py [/path/to/access.log] [--limit 100000]
"""

import os
import sys

# Добавляем корневую директорию проекта в sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database import migrate_db  # noqa: E402
from services.analytics import stats_service  # noqa: E402


def main():
    log_path = None
    limit = 100000

    args = sys.argv[1:]
    for idx, arg in enumerate(args):
        if arg == '--limit' and idx + 1 < len(args):
            try:
                limit = int(args[idx + 1])
            except ValueError:
                pass
        elif not arg.startswith('--') and log_path is None:
            log_path = arg

    if not log_path:
        candidates = [
            '/var/log/nginx/access.log',
            os.path.join(BASE_DIR, 'logs', 'access.log'),
            os.path.join(BASE_DIR, 'logs', 'nginx_access.log'),
            os.path.join(BASE_DIR, 'access.log'),
        ]
        for c in candidates:
            if os.path.isfile(c):
                log_path = c
                break

    if not log_path or not os.path.isfile(log_path):
        print(f"[ERROR] Файл лога Nginx не найден (проверено: {log_path})")
        print("Укажите путь аргументом: python scripts/import_nginx_logs.py /var/log/nginx/access.log")
        sys.exit(1)

    print("[*] Применяем миграции БД (проверка наличия таблицы page_visits)...")
    migrate_db()

    print(f"[*] Запуск импорта из {log_path} (лимит {limit} строк)...")
    imported = stats_service.import_from_nginx_log(log_path, max_lines=limit)
    print(f"[OK] Успешно импортировано {imported} записей визитов.")

    stats = stats_service.get_dashboard_stats()
    print("\n--- Текущие показатели аналитики ---")
    print(f"Сегодня:      {stats.get('unique_today')} уникальных, {stats.get('views_today')} просмотров")
    print(f"Вчера:        {stats.get('unique_yesterday')} уникальных, {stats.get('views_yesterday')} просмотров")
    print(f"За 7 дней:    {stats.get('unique_week')} уникальных, {stats.get('views_week')} просмотров")
    print(f"За 30 дней:   {stats.get('unique_month')} уникальных, {stats.get('views_month')} просмотров")
    print(f"Доля mobile:  {stats.get('mobile_share_pct')}%")
    print(f"Боты сегодня: {stats.get('bot_views_today')} отсеяно")


if __name__ == '__main__':
    main()
