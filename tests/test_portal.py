from templates.portal_views import DOCUMENTS_REGISTRY, PORTAL_PAGES, render_document, render_page


def test_portal_pages_loaded():
    assert len(PORTAL_PAGES) > 15, "Страницы портала должны быть загружены"
    assert 'home' in PORTAL_PAGES
    assert 'contacts' in PORTAL_PAGES
    assert 'reports' in PORTAL_PAGES
    assert 'tarif' in PORTAL_PAGES
    assert 'load' in PORTAL_PAGES

def test_documents_registry_loaded():
    assert len(DOCUMENTS_REGISTRY) > 200, "Реестр документов должен содержать > 200 отчетов"
    assert 'invest-1-2024.php' in DOCUMENTS_REGISTRY
    assert 'ktp_2024_03.php' in DOCUMENTS_REGISTRY

def test_render_home_page():
    html = render_page('home')
    assert 'КРЭК' in html
    assert 'квитанц' in html.lower()
    assert '<!DOCTYPE html>' in html

def test_render_contacts_page():
    html = render_page('contacts')
    assert 'Наш адрес' in html
    assert 'Караганда' in html

def test_render_document_invest():
    doc = DOCUMENTS_REGISTRY.get('invest-1-2024.php')
    assert doc is not None
    html = render_document(doc)
    assert 'Отчет инвестиционной программы' in html
    assert '.pdf' in html

def test_render_document_iframe_ktp():
    doc = DOCUMENTS_REGISTRY.get('ktp_2024_03.php')
    assert doc is not None
    html = render_document(doc)
    assert 'iframe' in html
    assert 'ktp_2024_03' in html

def test_render_404():
    html = render_page('some_non_existent_page_123')
    assert '404' in html

def test_render_zakup_page():
    html = render_page('zakup')
    assert 'Закупки' in html
    assert 'План закупок' in html
    assert '404' not in html

    html_slash = render_page('/zakup.php')
    assert 'Закупки' in html_slash
    assert 'Страница не найдена' not in html_slash

def test_render_notices_page():
    html = render_page('notices')
    assert 'Объявления' in html
    assert '/notices' in html
    assert 'Страница не найдена' not in html

    html_slash = render_page('/notices.php')
    assert 'Объявления' in html_slash
    assert 'Страница не найдена' not in html_slash

def test_health_and_readiness_probes():
    """Тестирует liveness (/health) и readiness (/ready) проверки сервера."""
    from unittest import mock

    from server import AppRequestHandler

    handler = AppRequestHandler.__new__(AppRequestHandler)
    captured = {}

    def mock_send_json(data, code=200, extra_headers=None):
        captured['data'] = data
        captured['code'] = code
        captured['headers'] = extra_headers

    handler.send_json = mock_send_json

    # 1. Liveness probe (/health) -> 200 OK
    handler._handle_health()
    assert captured['code'] == 200
    assert captured['data']['status'] == 'ok'
    assert 'uptime_seconds' in captured['data']
    assert captured['data']['service'] == 'kvit-service'

    # 2. Readiness probe (/ready) -> 200 Ready
    handler._handle_ready()
    assert captured['code'] == 200
    assert captured['data']['status'] == 'ready'
    assert captured['data']['checks']['database'] == 'ok'

    # 3. Readiness probe при сбое БД -> 503 Not Ready
    with mock.patch('server.get_db', side_effect=Exception('Database unreachable')):
        handler._handle_ready()
        assert captured['code'] == 503
        assert captured['data']['status'] == 'not_ready'
        assert 'Database unreachable' in captured['data']['checks']['database']


def test_pwa_and_offline_support():
    """Тестирует доступность Service Worker, манифеста и страницы оффлайн-режима."""
    import os
    from unittest import mock

    import config
    from server import AppRequestHandler

    # 1. Проверяем существование статических файлов
    assert os.path.isfile(os.path.join(config.STATIC_DIR, 'sw.js'))
    assert os.path.isfile(os.path.join(config.STATIC_DIR, 'manifest.json'))
    assert os.path.isfile(os.path.join(config.STATIC_DIR, 'offline.html'))

    # 2. Проверяем содержимое оффлайн страницы
    with open(os.path.join(config.STATIC_DIR, 'offline.html'), 'r', encoding='utf-8') as f:
        offline_content = f.read()
    assert 'автономном режиме' in offline_content
    assert '+7 (7212) 90-03-50' in offline_content
    assert '90-03-58' not in offline_content
    assert '90-03-59' not in offline_content
    assert 'src="/images/logo.png"' in offline_content
    assert 'src="/images/logo.png?v=8"' not in offline_content

    with open(os.path.join(config.STATIC_DIR, 'sw.js'), 'r', encoding='utf-8') as f:
        service_worker = f.read()
    assert "krek-portal-v29" in service_worker
    assert "caches.match(req, { ignoreSearch: true })" in service_worker

    # 3. Тестируем отдачу /sw.js сервером
    handler = AppRequestHandler.__new__(AppRequestHandler)
    sent_headers = {}
    response_code = None

    def mock_send_response(code):
        nonlocal response_code
        response_code = code

    def mock_send_header(name, val):
        sent_headers[name] = val

    handler.send_response = mock_send_response
    handler.send_header = mock_send_header
    handler._send_security_headers = lambda: None
    handler.end_headers = lambda: None
    handler.wfile = mock.MagicMock()

    handler._serve_static('/sw.js')
    assert response_code == 200
    assert 'javascript' in sent_headers.get('Content-Type', '')
    assert sent_headers.get('Service-Worker-Allowed') == '/'


def test_global_portal_search():
    """Тестирует работу полнотекстового глобального поиска портала."""
    from services.portal_search import render_global_search_page, search_portal_content

    # 1. Поиск по ключевому слову тариф
    results_tarif = search_portal_content('тариф')
    assert len(results_tarif) > 0
    assert any('tarif' in r['url'] or 'report' in r['url'] for r in results_tarif)

    # 2. Поиск по вакансиям
    results_vac = search_portal_content('вакансии')
    assert len(results_vac) > 0
    assert results_vac[0]['url'] == '/vacancy'

    # 3. Поиск по техусловиям
    results_tu = search_portal_content('подключение')
    assert len(results_tu) > 0

    # 4. Рендеринг страницы поиска
    html = render_global_search_page('тариф', results_tarif)
    assert '<!DOCTYPE html>' in html
    assert 'Результаты поиска' in html
    assert 'mark' in html


def test_maintenance_contacts_and_company_name():
    """Проверяет корректность телефона и названия компании на странице техработ."""
    import os
    maint_path = os.path.join('static', 'maintenance.html')
    assert os.path.exists(maint_path)
    with open(maint_path, 'r', encoding='utf-8') as f:
        html = f.read()

    assert '+7 (7212) 90-03-50' in html, "На странице техработ должен быть телефон канцелярии КРЭК"
    assert '378-00-00' not in html, "Чужой телефон 378-00-00 должен отсутствовать"
    assert 'Карагандинская Региональная Энергетическая Компания' in html
    assert 'Капшагай' not in html, "Чужое название компании должно отсутствовать"
    assert 'info@krec.kz' in html


def test_offline_schedule_consistency():
    """Проверяет единообразие графика работы на странице offline.html."""
    import os
    offline_path = os.path.join('static', 'offline.html')
    assert os.path.exists(offline_path)
    with open(offline_path, 'r', encoding='utf-8') as f:
        html = f.read()

    assert '08:00 до 17:00' in html, "График должен быть 08:00–17:00"
    assert '08:30' not in html, "Не должно быть расхождения с 08:30"
    assert '17:30' not in html, "Не должно быть расхождения с 17:30"


def test_portal_pages_email_uniformity():
    """Проверяет отсутствие info.krec@mail.ru на страницах портала."""
    import json
    with open('data/extracted_portal_pages.json', 'r', encoding='utf-8') as f:
        d = json.load(f)
    for key, val in d.items():
        if isinstance(val, dict) and 'html' in val:
            assert 'info.krec@mail.ru' not in val['html'], f"Страница {key} содержит устаревший email info.krec@mail.ru"


def test_reconcile_invalid_page_param():
    """Проверяет устойчивость /reconcile к некорректным параметрам page=abc."""
    from unittest import mock

    from server import AppRequestHandler

    for role in ('admin', 'operator'):
        handler = AppRequestHandler.__new__(AppRequestHandler)
        sent_html = []
        sent_status = []

        handler.send_html = lambda body, status=200, sh=sent_html, ss=sent_status: (sh.append(body), ss.append(status))
        handler._get_current_user = lambda r=role: {'role': r, 'username': 'testuser'}
        handler._get_session_token = lambda: 'dummy_session'
        handler.headers = mock.MagicMock()
        handler.headers.get = lambda k, d=None: '127.0.0.1' if 'host' in k.lower() else d

        with mock.patch('server_handlers.admin_get_handlers.auth_service.get_csrf_token', return_value='csrf123'):
            with mock.patch('server_handlers.admin_get_handlers.reconcile_service.get_reconciliation_data') as mock_reconcile:
                mock_reconcile.return_value = {
                    'all_periods': [],
                    'total_accounts': 0,
                    'total_receipts': 0,
                    'matched': 0,
                    'unmatched': 0,
                    'orphans': 0,
                    'list_count': 0,
                    'rows': [],
                    'page_num': 1,
                    'per_page': 50,
                    'filt': 'without',
                    'period_filter': '',
                    'account_query': '',
                }
                # Вызываем с некорректным page=abc
                res = handler._handle_get_admin('/reconcile', {'page': ['abc']}, is_admin=(role == 'admin'), client_ip='127.0.0.1')
                assert res is True
                assert sent_status[0] == 200, f"Роль {role} получила ошибку при /reconcile?page=abc"
                assert mock_reconcile.call_args[0][2] == 1


def test_admin_stats_dashboard_responsive_layout():
    """Проверяет адаптивность панели статистики (отсутствие жесткого inline grid 2fr 1fr)."""
    from templates.admin_stats_views import render_admin_stats_dashboard

    sample_stats = {
        'unique_today': 10,
        'views_today': 25,
        'top_pages': [{'path': '/', 'views': 10, 'visitors': 5, 'pct': 40.0}],
        'devices': {'mobile': 10, 'desktop': 15, 'tablet': 0},
        'browsers': {'Chrome': 20}
    }
    html = render_admin_stats_dashboard(sample_stats, csrf_token='csrf')
    assert 'class="stats-two-cols"' in html
    assert 'grid-template-columns:2fr 1fr' not in html, "Не должно быть жесткого inline стиля 2fr 1fr"
    assert '@media' in html or '.stats-two-cols' in html


def test_retention_scheduler_lifecycle():
    """Проверяет штатный запуск и корректную остановку фонового потока RetentionCleanerThread."""
    import threading

    from services.retention_scheduler import (
        start_retention_scheduler,
        stop_retention_scheduler,
    )

    stop_retention_scheduler()

    started = start_retention_scheduler(interval_seconds=3600, initial_delay=3600)
    assert started is True

    started_duplicate = start_retention_scheduler(interval_seconds=3600, initial_delay=3600)
    assert started_duplicate is False

    stopped = stop_retention_scheduler(timeout=3.0)
    assert stopped is True

    active_threads = [t.name for t in threading.enumerate()]
    assert "RetentionCleanerThread" not in active_threads
