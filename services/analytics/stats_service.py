# -*- coding: utf-8 -*-
"""
Подсистема веб-аналитики и сбора статистики посещаемости (StatsService).
Обеспечивает:
1. Неблокирующий учет визитов страниц с анонимизацией IP (SHA-256).
2. Классификацию устройств (мобильные, ПК, планшеты), ОС и браузеров.
3. Отсеивание поисковых ботов и веб-краулеров.
4. Агрегацию метрик посещаемости (уникальные посетители, просмотры, динамика по дням, топ страниц).
5. Импорт исторических логов Nginx.
"""

import datetime
import hashlib
import re
import time
from typing import Any, Dict, Optional, Tuple

import config
from database.connection import get_db, write_transaction
from logger import logger


class StatsService:
    """Сервис аналитики и учета посещаемости веб-портала."""

    # Регулярные выражения и сигнатуры поисковых ботов
    BOT_PATTERNS = [
        re.compile(r'bot\b', re.IGNORECASE),
        re.compile(r'crawler\b', re.IGNORECASE),
        re.compile(r'spider\b', re.IGNORECASE),
        re.compile(r'slurp\b', re.IGNORECASE),
        re.compile(r'googlebot', re.IGNORECASE),
        re.compile(r'yandexbot', re.IGNORECASE),
        re.compile(r'bingbot', re.IGNORECASE),
        re.compile(r'duckduckbot', re.IGNORECASE),
        re.compile(r'baiduspider', re.IGNORECASE),
        re.compile(r'facebookexternalhit', re.IGNORECASE),
        re.compile(r'python-requests', re.IGNORECASE),
        re.compile(r'python-urllib', re.IGNORECASE),
        re.compile(r'aiohttp', re.IGNORECASE),
        re.compile(r'curl/', re.IGNORECASE),
        re.compile(r'wget/', re.IGNORECASE),
        re.compile(r'censys', re.IGNORECASE),
        re.compile(r'shodan', re.IGNORECASE),
        re.compile(r'postman', re.IGNORECASE),
    ]

    def _hash_ip(self, ip_str: str) -> str:
        """Анонимизирует IP-адрес с солью для соблюдения конфиденциальности."""
        secret = getattr(config, 'SECRET_KEY', 'krec_analytics_salt_key')
        raw = f"{ip_str}_{secret}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def parse_user_agent(self, ua: str) -> Tuple[str, str, str, bool]:
        """
        Классифицирует User-Agent.
        Возвращает: (device_type, browser, os_name, is_bot).
        """
        if not ua:
            return 'desktop', 'Other', 'Other', False

        ua_lower = ua.lower()

        # 1. Проверка на ботов
        is_bot = any(pattern.search(ua) for pattern in self.BOT_PATTERNS)
        if is_bot:
            return 'bot', 'Bot / Crawler', 'Other', True

        # 2. Определение устройства
        if 'ipad' in ua_lower or 'tablet' in ua_lower:
            device = 'tablet'
        elif any(m in ua_lower for m in ('mobile', 'android', 'iphone', 'ipod', 'opera mini', 'blackberry')):
            device = 'mobile'
        else:
            device = 'desktop'

        # 3. Определение браузера
        if 'edg/' in ua_lower or 'edge/' in ua_lower:
            browser = 'Edge'
        elif 'yabrowser' in ua_lower:
            browser = 'Yandex'
        elif 'opr/' in ua_lower or 'opera' in ua_lower:
            browser = 'Opera'
        elif 'chrome' in ua_lower and 'safari' in ua_lower and 'edg' not in ua_lower:
            browser = 'Chrome'
        elif 'safari' in ua_lower and 'chrome' not in ua_lower:
            browser = 'Safari'
        elif 'firefox' in ua_lower:
            browser = 'Firefox'
        else:
            browser = 'Other'

        # 4. Определение операционной системы
        if 'windows' in ua_lower:
            os_name = 'Windows'
        elif 'android' in ua_lower:
            os_name = 'Android'
        elif any(i in ua_lower for i in ('iphone', 'ipad', 'ipod')):
            os_name = 'iOS'
        elif 'mac os' in ua_lower or 'macintosh' in ua_lower:
            os_name = 'macOS'
        elif 'linux' in ua_lower:
            os_name = 'Linux'
        else:
            os_name = 'Other'

        return device, browser, os_name, False

    def record_visit(
        self,
        path: str,
        client_ip: str,
        user_agent: str,
        visited_at: Optional[float] = None
    ) -> bool:
        """
        Регистрирует просмотр страницы в БД.
        Безопасен к исключениям: никогда не ломает обработку основного HTTP-запроса.
        """
        if not path:
            return False

        # Нормализация пути: отсекаем query string и ограничиваем длину
        norm_path = path.split('?')[0].strip()
        if len(norm_path) > 255:
            norm_path = norm_path[:255]

        # Игнорируем технические эндпоинты
        if norm_path in ('/health', '/ready', '/api/health', '/api/ready', '/favicon.ico', '/robots.txt', '/sw.js', '/manifest.json'):
            return False
        if norm_path.startswith(('/css/', '/images/', '/files/', '/static/')):
            return False

        ts = visited_at if visited_at is not None else time.time()
        ip_h = self._hash_ip(client_ip or '127.0.0.1')
        ua_str = (user_agent or '')[:500]

        device_type, browser, os_name, is_bot = self.parse_user_agent(ua_str)

        try:
            with write_transaction() as con:
                con.execute(
                    """
                    INSERT INTO page_visits (visited_at, path, ip_hash, user_agent, device_type, browser, os, is_bot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ts, norm_path, ip_h, ua_str, device_type, browser, os_name, bool(is_bot))
                )
            return True
        except Exception as exc:
            logger.debug("[Analytics] Ошибка сохранения визита страницы %s: %s", norm_path, exc)
            return False

    def get_dashboard_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Формирует комплексную статистику для дашборда администратора:
        - KPI: Сегодня, Вчера, За 7 дней, За 30 дней (уникальные посетители и просмотры).
        - Динамика посещений по дням (для графиков).
        - Топ-10 страниц.
        - Распределение по типам устройств и браузерам.
        - Последние 15 визитов в реальном времени.
        """
        now = time.time()
        now_dt = datetime.datetime.fromtimestamp(now)

        # Границы суток
        today_start = datetime.datetime(now_dt.year, now_dt.month, now_dt.day).timestamp()
        yesterday_start = today_start - 86400.0
        week_start = now - (7 * 86400.0)
        month_start = now - (days * 86400.0)

        summary = {
            'unique_today': 0,
            'views_today': 0,
            'unique_yesterday': 0,
            'views_yesterday': 0,
            'unique_week': 0,
            'views_week': 0,
            'unique_month': 0,
            'views_month': 0,
            'bot_views_today': 0,
            'mobile_share_pct': 0.0,
            'daily_trend': [],
            'top_pages': [],
            'device_stats': {'mobile': 0, 'desktop': 0, 'tablet': 0, 'bot': 0},
            'browser_stats': [],
            'recent_visits': []
        }

        try:
            con = get_db()
            try:
                # 1. KPI метрики (реальные люди, NOT is_bot)
                row_today = con.execute(
                    """
                    SELECT COUNT(DISTINCT ip_hash) AS unique_count, COUNT(*) AS total_views
                    FROM page_visits
                    WHERE visited_at >= ? AND (NOT is_bot OR is_bot IS NULL)
                    """,
                    (today_start,)
                ).fetchone()
                if row_today:
                    summary['unique_today'] = int(row_today['unique_count'] if 'unique_count' in row_today.keys() else row_today[0] or 0)
                    summary['views_today'] = int(row_today['total_views'] if 'total_views' in row_today.keys() else row_today[1] or 0)

                row_bot_today = con.execute(
                    """
                    SELECT COUNT(*) AS bot_count
                    FROM page_visits
                    WHERE visited_at >= ? AND is_bot
                    """,
                    (today_start,)
                ).fetchone()
                if row_bot_today:
                    summary['bot_views_today'] = int(row_bot_today['bot_count'] if 'bot_count' in row_bot_today.keys() else row_bot_today[0] or 0)

                row_yesterday = con.execute(
                    """
                    SELECT COUNT(DISTINCT ip_hash) AS unique_count, COUNT(*) AS total_views
                    FROM page_visits
                    WHERE visited_at >= ? AND visited_at < ? AND (NOT is_bot OR is_bot IS NULL)
                    """,
                    (yesterday_start, today_start)
                ).fetchone()
                if row_yesterday:
                    summary['unique_yesterday'] = int(row_yesterday['unique_count'] if 'unique_count' in row_yesterday.keys() else row_yesterday[0] or 0)
                    summary['views_yesterday'] = int(row_yesterday['total_views'] if 'total_views' in row_yesterday.keys() else row_yesterday[1] or 0)

                row_week = con.execute(
                    """
                    SELECT COUNT(DISTINCT ip_hash) AS unique_count, COUNT(*) AS total_views
                    FROM page_visits
                    WHERE visited_at >= ? AND (NOT is_bot OR is_bot IS NULL)
                    """,
                    (week_start,)
                ).fetchone()
                if row_week:
                    summary['unique_week'] = int(row_week['unique_count'] if 'unique_count' in row_week.keys() else row_week[0] or 0)
                    summary['views_week'] = int(row_week['total_views'] if 'total_views' in row_week.keys() else row_week[1] or 0)

                row_month = con.execute(
                    """
                    SELECT COUNT(DISTINCT ip_hash) AS unique_count, COUNT(*) AS total_views
                    FROM page_visits
                    WHERE visited_at >= ? AND (NOT is_bot OR is_bot IS NULL)
                    """,
                    (month_start,)
                ).fetchone()
                if row_month:
                    summary['unique_month'] = int(row_month['unique_count'] if 'unique_count' in row_month.keys() else row_month[0] or 0)
                    summary['views_month'] = int(row_month['total_views'] if 'total_views' in row_month.keys() else row_month[1] or 0)

                # 2. Динамика по дням за последние N дней (по умолчанию 14 дней для компактного графика)
                trend_days = min(days, 30)
                daily_trend = []
                months_ru = ['', 'янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

                for i in range(trend_days - 1, -1, -1):
                    day_dt = now_dt - datetime.timedelta(days=i)
                    d_start = datetime.datetime(day_dt.year, day_dt.month, day_dt.day).timestamp()
                    d_end = d_start + 86400.0

                    d_row = con.execute(
                        """
                        SELECT COUNT(DISTINCT ip_hash) AS unique_count, COUNT(*) AS total_views
                        FROM page_visits
                        WHERE visited_at >= ? AND visited_at < ? AND (NOT is_bot OR is_bot IS NULL)
                        """,
                        (d_start, d_end)
                    ).fetchone()

                    if d_row:
                        u_count = int(d_row['unique_count'] if 'unique_count' in d_row.keys() else d_row[0] or 0)
                        v_count = int(d_row['total_views'] if 'total_views' in d_row.keys() else d_row[1] or 0)
                    else:
                        u_count = 0
                        v_count = 0

                    daily_trend.append({
                        'date': day_dt.strftime('%Y-%m-%d'),
                        'label': f"{day_dt.day} {months_ru[day_dt.month]}",
                        'visitors': u_count,
                        'views': v_count
                    })
                summary['daily_trend'] = daily_trend

                # 3. Топ-10 страниц за последние 30 дней
                top_rows = con.execute(
                    """
                    SELECT path, COUNT(*) as views_cnt, COUNT(DISTINCT ip_hash) as visitors_cnt
                    FROM page_visits
                    WHERE visited_at >= ? AND (NOT is_bot OR is_bot IS NULL)
                    GROUP BY path
                    ORDER BY views_cnt DESC
                    LIMIT 10
                    """,
                    (month_start,)
                ).fetchall()

                total_human_views = summary['views_month'] or 1
                top_pages = []
                for r in top_rows:
                    p_path = r[0]
                    p_views = int(r[1])
                    p_visitors = int(r[2])
                    pct = round((p_views / total_human_views) * 100, 1)
                    top_pages.append({
                        'path': p_path,
                        'views': p_views,
                        'visitors': p_visitors,
                        'pct': pct
                    })
                summary['top_pages'] = top_pages

                # 4. Распределение устройств за последние 30 дней
                dev_rows = con.execute(
                    """
                    SELECT device_type, COUNT(*)
                    FROM page_visits
                    WHERE visited_at >= ?
                    GROUP BY device_type
                    """,
                    (month_start,)
                ).fetchall()

                dev_counts = {'mobile': 0, 'desktop': 0, 'tablet': 0, 'bot': 0}
                for dr in dev_rows:
                    d_name = (dr[0] or 'desktop').lower()
                    if d_name in dev_counts:
                        dev_counts[d_name] += int(dr[1])

                summary['device_stats'] = dev_counts
                human_devices_total = dev_counts['mobile'] + dev_counts['desktop'] + dev_counts['tablet']
                if human_devices_total > 0:
                    summary['mobile_share_pct'] = round((dev_counts['mobile'] / human_devices_total) * 100, 1)

                # 5. Браузеры за последние 30 дней
                br_rows = con.execute(
                    """
                    SELECT browser, COUNT(*) as cnt
                    FROM page_visits
                    WHERE visited_at >= ? AND (NOT is_bot OR is_bot IS NULL)
                    GROUP BY browser
                    ORDER BY cnt DESC
                    LIMIT 5
                    """,
                    (month_start,)
                ).fetchall()
                summary['browser_stats'] = [{'browser': r[0], 'count': int(r[1])} for r in br_rows]

                # 6. Последние 15 посещений в реальном времени
                recent_rows = con.execute(
                    """
                    SELECT visited_at, path, ip_hash, device_type, browser, os, is_bot
                    FROM page_visits
                    ORDER BY visited_at DESC
                    LIMIT 15
                    """
                ).fetchall()

                recent_visits = []
                for rr in recent_rows:
                    v_time = float(rr[0])
                    v_dt = datetime.datetime.fromtimestamp(v_time)
                    recent_visits.append({
                        'time_str': v_dt.strftime('%H:%M:%S'),
                        'date_str': v_dt.strftime('%d.%m.%Y'),
                        'path': rr[1],
                        'ip_masked': f"{rr[2][:6]}...",
                        'device_type': rr[3],
                        'browser': rr[4],
                        'os': rr[5],
                        'is_bot': bool(rr[6])
                    })
                summary['recent_visits'] = recent_visits

            finally:
                con.close()
        except Exception as exc:
            logger.warning("[Analytics] Не удалось вычислить статистику дашборда: %s", exc)

        return summary

    def import_from_nginx_log(self, log_path: str, max_lines: int = 50000) -> int:
        """
        Импортирует записи из access.log Nginx в таблицу page_visits.
        Парсит формат main: $remote_addr ... [$time_local] "$request" $status ... "$http_user_agent"
        Возвращает число успешно загруженных визитов.
        """
        import os

        if not os.path.isfile(log_path):
            logger.warning("[Analytics] Файл лога Nginx не найден: %s", log_path)
            return 0

        # Формат даты: 08/Sep/2026:03:31:38 +0000
        log_pattern = re.compile(
            r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+"(?P<method>\S+)\s+(?P<url>\S+)\s+[^"]*"\s+(?P<status>\d+)\s+\S+\s+"[^"]*"\s+"(?P<ua>[^"]*)"'
        )

        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }

        imported_count = 0
        batch = []
        batch_size = 500

        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                for line_idx, line in enumerate(f):
                    if line_idx >= max_lines:
                        break
                    match = log_pattern.match(line.strip())
                    if not match:
                        continue

                    ip = match.group('ip')
                    url = match.group('url').split('?')[0]
                    status = int(match.group('status'))
                    ua = match.group('ua')
                    time_raw = match.group('time')

                    # Фильтруем статику и неуспешные ответы
                    if status not in (200, 301, 302, 304):
                        continue
                    if url.startswith(('/css/', '/images/', '/files/', '/static/')) or url in ('/sw.js', '/favicon.ico', '/robots.txt', '/manifest.json'):
                        continue

                    # Парсим время
                    try:
                        # 08/Sep/2026:03:31:38
                        dt_part = time_raw.split()[0]
                        d_str, m_str, rest = dt_part.split('/', 2)
                        y_str, h_str, min_str, s_str = rest.replace(':', ' ').split()
                        dt = datetime.datetime(int(y_str), months.get(m_str, 1), int(d_str), int(h_str), int(min_str), int(s_str))
                        ts = dt.timestamp()
                    except Exception:
                        ts = time.time()

                    device_type, browser, os_name, is_bot = self.parse_user_agent(ua)
                    ip_h = self._hash_ip(ip)

                    batch.append((ts, url[:255], ip_h, ua[:500], device_type, browser, os_name, bool(is_bot)))

                    if len(batch) >= batch_size:
                        with write_transaction() as con:
                            con.executemany(
                                """
                                INSERT INTO page_visits (visited_at, path, ip_hash, user_agent, device_type, browser, os, is_bot)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                batch
                            )
                        imported_count += len(batch)
                        batch.clear()

            if batch:
                with write_transaction() as con:
                    con.executemany(
                        """
                        INSERT INTO page_visits (visited_at, path, ip_hash, user_agent, device_type, browser, os, is_bot)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch
                    )
                imported_count += len(batch)

            logger.info("[Analytics] Импортировано %d записей визитов из лога Nginx.", imported_count)
            return imported_count
        except Exception as exc:
            logger.error("[Analytics] Ошибка импорта лога Nginx: %s", exc)
            return imported_count


stats_service = StatsService()
