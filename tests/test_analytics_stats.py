# -*- coding: utf-8 -*-
"""
Тесты подсистемы аналитики и статистики посещаемости сайта (StatsService):
1. Классификация User-Agent (устройства, браузеры, операционные системы, обнаружение ботов).
2. Запись визитов, анонимизация IP (хэширование) и игнорирование статики/пробок.
3. Агрегация метрик дашборда (Сегодня, Вчера, 7 дней, 30 дней, динамика по дням, топ страниц).
4. Защита и работа веб-маршрутов /admin/stats и /api/admin/stats.
5. Импорт записей из журнала Nginx access.log.
"""

import datetime
import json
import time
import urllib.parse

from services.analytics import stats_service
from tests.test_appeals_e2e import _http_request


def test_parse_user_agent_classification():
    # 1. Смартфоны
    ua_android = "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_android)
    assert dev == 'mobile'
    assert browser == 'Chrome'
    assert os_name == 'Android'
    assert not is_bot

    ua_iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_iphone)
    assert dev == 'mobile'
    assert browser == 'Safari'
    assert os_name == 'iOS'
    assert not is_bot

    # 2. Планшеты
    ua_ipad = "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_ipad)
    assert dev == 'tablet'
    assert not is_bot

    # 3. Десктопные ПК
    ua_win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_win)
    assert dev == 'desktop'
    assert browser == 'Edge'
    assert os_name == 'Windows'
    assert not is_bot

    ua_firefox = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_firefox)
    assert dev == 'desktop'
    assert browser == 'Firefox'
    assert os_name == 'Linux'
    assert not is_bot

    # 4. Поисковые боты и сканеры
    ua_googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_googlebot)
    assert is_bot is True
    assert dev == 'bot'

    ua_yandex = "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_yandex)
    assert is_bot is True
    assert dev == 'bot'

    ua_curl = "curl/8.5.0"
    dev, browser, os_name, is_bot = stats_service.parse_user_agent(ua_curl)
    assert is_bot is True


def test_record_visit_and_privacy_hash():
    now = time.time()

    # 1. Запись обычного визита
    ok = stats_service.record_visit("/tu", "203.0.113.42", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0", visited_at=now)
    assert ok is True

    # 2. Игнорирование статических файлов и служебных проверок
    assert stats_service.record_visit("/css/style.css", "203.0.113.42", "Chrome") is False
    assert stats_service.record_visit("/images/logo.png", "203.0.113.42", "Chrome") is False
    assert stats_service.record_visit("/health", "127.0.0.1", "curl/8.0") is False
    assert stats_service.record_visit("/sw.js", "203.0.113.42", "Chrome") is False

    # 3. Проверка нормализации query параметров
    ok_query = stats_service.record_visit("/search?account=406919&period=2026-08", "203.0.113.43", "Mozilla/5.0", visited_at=now)
    assert ok_query is True


def test_dashboard_stats_aggregation():
    now = time.time()
    now_dt = datetime.datetime.fromtimestamp(now)
    today_start = datetime.datetime(now_dt.year, now_dt.month, now_dt.day).timestamp()
    yesterday_time = today_start - 3600.0  # Вчера вечером
    older_time = today_start - (5 * 86400.0)  # 5 дней назад

    # Очищаем таблицу для точности теста
    from database.connection import write_transaction
    with write_transaction() as con:
        con.execute("DELETE FROM page_visits")

    # Генерируем тестовые визиты:
    # Сегодня: 2 уникальных человека (3 просмотра), 1 бот
    stats_service.record_visit("/", "198.51.100.1", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0", visited_at=today_start + 100)
    stats_service.record_visit("/search", "198.51.100.1", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0", visited_at=today_start + 200)
    stats_service.record_visit("/tu", "198.51.100.2", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1", visited_at=today_start + 300)
    stats_service.record_visit("/tarif", "198.51.100.99", "Googlebot/2.1", visited_at=today_start + 400)

    # Вчера: 1 уникальный человек (2 просмотра)
    stats_service.record_visit("/", "198.51.100.5", "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0", visited_at=yesterday_time)
    stats_service.record_visit("/appeals", "198.51.100.5", "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0", visited_at=yesterday_time + 10)

    # 5 дней назад: 1 уникальный человек
    stats_service.record_visit("/contacts", "198.51.100.10", "Mozilla/5.0 (Android 14; Mobile) Chrome/120.0.0.0", visited_at=older_time)

    # Получаем сводку
    res = stats_service.get_dashboard_stats(days=14)

    # Проверяем KPI
    assert res["unique_today"] == 2
    assert res["views_today"] == 3
    assert res["bot_views_today"] == 1

    assert res["unique_yesterday"] == 1
    assert res["views_yesterday"] == 2

    assert res["unique_week"] >= 3
    assert res["views_week"] >= 5

    # Проверяем топ страниц
    top_paths = [p["path"] for p in res["top_pages"]]
    assert "/" in top_paths
    assert "/search" in top_paths

    # Проверяем распределение устройств
    assert res["device_stats"]["mobile"] >= 2
    assert res["device_stats"]["desktop"] >= 3
    assert res["mobile_share_pct"] > 0


def test_admin_stats_http_and_api_integration(e2e_server):
    base_url = e2e_server["base_url"]
    admin_password = e2e_server["admin_password"]

    # 1. Неавторизованный запрос к /admin/stats -> редирект на /login
    res_unauth_html = _http_request(f"{base_url}/admin/stats", follow_redirects=False)
    assert res_unauth_html["status"] in (302, 303)
    assert "/login" in res_unauth_html["headers"].get("Location", "")

    # 2. Неавторизованный запрос к /api/admin/stats -> 401
    res_unauth_api = _http_request(f"{base_url}/api/admin/stats")
    assert res_unauth_api["status"] == 401

    # 3. Авторизация администратора
    login_data = urllib.parse.urlencode({"username": "admin", "password": admin_password}).encode("utf-8")
    res_login = _http_request(
        f"{base_url}/login",
        method="POST",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False
    )
    session_cookie = res_login["headers"]["Set-Cookie"].split(";")[0]

    # 4. Авторизованный запрос к /admin/stats -> 200 HTML дашборд
    res_admin_page = _http_request(f"{base_url}/admin/stats", headers={"Cookie": session_cookie})
    assert res_admin_page["status"] == 200
    body = res_admin_page["body"]
    assert "Статистика посещаемости портала" in body
    assert "Динамика визитов по дням" in body
    assert "Популярные страницы" in body
    assert "Типы устройств" in body

    # 5. Авторизованный запрос к /api/admin/stats -> 200 JSON
    res_api = _http_request(f"{base_url}/api/admin/stats", headers={"Cookie": session_cookie})
    assert res_api["status"] == 200
    data = json.loads(res_api["body"])
    assert "unique_today" in data
    assert "views_today" in data
    assert "daily_trend" in data
    assert "top_pages" in data
    assert "device_stats" in data


def test_import_from_nginx_log_parsing(tmp_path):
    log_file = tmp_path / "sample_access.log"
    sample_lines = [
        '89.42.60.76 - - [08/Sep/2026:03:31:38 +0000] "GET /search HTTP/2.0" 200 205 "https://krec.kz/" "Mozilla/5.0 (Linux; Android 10; K) Mobile Safari/537.36" "-"\n',
        '89.42.60.76 - - [08/Sep/2026:03:31:39 +0000] "GET /tu HTTP/2.0" 200 1540 "https://krec.kz/" "Mozilla/5.0 (Linux; Android 10; K) Mobile Safari/537.36" "-"\n',
        '192.168.101.120 - - [08/Sep/2026:03:31:40 +0000] "GET /images/logo.png HTTP/2.0" 200 265669 "-" "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" "-"\n',  # Статика, должна быть пропущена
        '66.249.66.1 - - [08/Sep/2026:03:31:41 +0000] "GET /tarif HTTP/2.0" 200 8900 "-" "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" "-"\n',
    ]
    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(sample_lines)

    imported_count = stats_service.import_from_nginx_log(str(log_file))
    assert imported_count == 3  # 2 обычные страницы + 1 бот, статика пропущена
