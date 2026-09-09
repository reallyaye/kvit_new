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
    assert 'КРЭК' in offline_content
    assert '+7 (7212) 90-03-58' in offline_content
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

