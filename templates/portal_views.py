import json
import os
import urllib.parse

from templates.portal_layout import portal_layout
from templates.icons import icon

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_FILENAME = 'extracted_portal_pages.json'
DOCS_FILENAME = 'documents.json'
PAGES_JSON_PATH = os.path.join(BASE_DIR, 'data', PAGES_FILENAME)
DOCS_JSON_PATH = os.path.join(BASE_DIR, 'data', DOCS_FILENAME)

def load_portal_pages():
    paths = [
        PAGES_JSON_PATH,
        os.path.join(os.path.dirname(BASE_DIR), 'data', PAGES_FILENAME),
        os.path.join(os.getcwd(), 'data', PAGES_FILENAME),
        os.path.join(os.getcwd(), 'kvit_test', 'data', PAGES_FILENAME),
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def load_documents_registry():
    paths = [
        DOCS_JSON_PATH,
        os.path.join(os.path.dirname(BASE_DIR), 'data', DOCS_FILENAME),
        os.path.join(os.getcwd(), 'data', DOCS_FILENAME),
        os.path.join(os.getcwd(), 'kvit_test', 'data', DOCS_FILENAME),
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

PORTAL_PAGES = load_portal_pages()
DOCUMENTS_REGISTRY = load_documents_registry()

def render_page(page_name: str, is_admin: bool = False) -> str:
    """Рендерит HTML-страницу портала из базы extracted_portal_pages.json."""
    global PORTAL_PAGES
    if not PORTAL_PAGES:
        PORTAL_PAGES = load_portal_pages()

    clean_name = page_name.lower().lstrip('/').removesuffix('.php')
    if clean_name in ('', 'index', 'main'):
        clean_name = 'home'

    page_data = PORTAL_PAGES.get(clean_name)
    if not page_data:
        # Fallback 404
        page_404 = PORTAL_PAGES.get('404', {})
        html_404 = page_404.get('html', '<h1>404 Страница не найдена</h1>')
        return portal_layout(html_404, title="404 — Страница не найдена", active_nav='', is_admin=is_admin, current_slug='404')

    active_nav = 'home' if clean_name == 'home' else clean_name
    return portal_layout(
        content=page_data.get('html', ''),
        title=page_data.get('title', 'ТОО КРЭК'),
        active_nav=active_nav,
        is_admin=is_admin,
        current_slug=clean_name
    )

def render_document(doc: dict, is_admin: bool = False, doc_key: str = '') -> str:
    """Рендерит документ/отчет из реестра документов в современном корпоративном стиле."""
    title = doc.get('title', 'ТОО КРЭК — Документ')
    h1 = doc.get('h1', title)
    desc = doc.get('description', 'ТОО КРЭК')
    date_text = doc.get('date_text', '')
    files = doc.get('files', [])
    iframes = doc.get('iframes', [])

    body_parts = []
    
    # Breadcrumbs & Header
    date_meta_html = f'<div class="doc-meta-date">{icon("calendar", 14, "#64748b")} <span>Опубликовано: {date_text}</span></div>' if date_text else ''
    body_parts.append(f'''
    <nav class="breadcrumb-nav" aria-label="Хлебные крошки">
        <a href="/">{icon("home", 13, "#64748b")} Главная</a>
        <span class="breadcrumb-sep">{icon("chevron_right", 12, "#94a3b8")}</span>
        <a href="/reports">Отчеты</a>
        <span class="breadcrumb-sep">{icon("chevron_right", 12, "#94a3b8")}</span>
        <span class="breadcrumb-current">{h1}</span>
    </nav>
    <div class="page-title-wrap">
        <div class="page-category-badge">{icon("file_text", 12, "#2563eb")} Официальный документ</div>
        <h1 class="page-main-title">{h1}</h1>
        {date_meta_html}
    </div>
    ''')

    if iframes:
        body_parts.append('<div class="iframes-container">')
        for ifr in iframes:
            fname = os.path.basename(ifr)
            clean_src = '/files/' + urllib.parse.quote(fname)
            body_parts.append(f'''
            <div class="doc-viewer-card">
                <div class="doc-viewer-header">
                    <div class="doc-viewer-filename">
                        {icon('file_text', 16, '#2563eb')}
                        <span>{fname}</span>
                    </div>
                    <div class="doc-viewer-actions">
                        <a href="{clean_src}" target="_blank" rel="noopener noreferrer" class="btn-doc-action">
                            {icon('external_link', 14, '#2563eb')}
                            <span>Открыть в новой вкладке</span>
                        </a>
                        <a href="{clean_src}" download class="btn-doc-download">
                            {icon('download', 14, '#ffffff')}
                            <span>Скачать PDF</span>
                        </a>
                    </div>
                </div>
                <div class="doc-iframe-wrapper">
                    <iframe src="{clean_src}" width="100%" height="820" style="border:none; border-radius:0 0 12px 12px; background:#fff;"></iframe>
                </div>
            </div>''')
        body_parts.append('</div>')
    elif files:
        body_parts.append('<div class="doc-files-grid">')
        for f in files:
            fname = os.path.basename(f)
            file_url = '/files/' + urllib.parse.quote(fname)
            body_parts.append(f'''
            <div class="doc-file-card">
                <div class="doc-file-icon">
                    {icon('file_text', 28, '#2563eb')}
                </div>
                <div class="doc-file-info">
                    <div class="doc-file-name">{fname}</div>
                    <div class="doc-file-meta">Формат: PDF / Документ • Официальная публикация ТОО «КРЭК»</div>
                </div>
                <div class="doc-file-action">
                    <a href="{file_url}" target="_blank" rel="noopener noreferrer" class="btn-doc-download">
                        {icon('download', 14, '#ffffff')}
                        <span>Скачать документ</span>
                    </a>
                </div>
            </div>''')
        body_parts.append('</div>')
    else:
        body_parts.append(f'''
        <div class="doc-empty-state">
            <div class="doc-empty-icon">{icon('info', 32, '#64748b')}</div>
            <div class="doc-empty-text">Документ временно недоступен для скачивания.</div>
            <a href="/reports" class="btn-return">{icon('arrow_left', 14, '#2563eb')} Вернуться к архиву отчетов</a>
        </div>''')

    full_html = '\n'.join(body_parts)
    return portal_layout(content=full_html, title=title, description=desc, active_nav='reports', is_admin=is_admin, current_slug=doc_key)
