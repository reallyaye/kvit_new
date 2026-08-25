from templates.portal_views import PORTAL_PAGES, DOCUMENTS_REGISTRY, render_page, render_document

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
    assert 'Квитанции' in html
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
