import os
import json
import urllib.parse
from templates.portal_layout import portal_layout

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
    """Рендерит именованную страницу портала (home, contacts, reports, etc.)."""
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
    """Рендерит документ/отчет из реестра документов (PDF-скачивание или iframe просмотр)."""
    title = doc.get('title', 'ТОО КРЭК — Документ')
    h1 = doc.get('h1', title)
    desc = doc.get('description', 'ТОО КРЭК')
    date_text = doc.get('date_text', '')
    files = doc.get('files', [])
    iframes = doc.get('iframes', [])

    body_parts = []
    body_parts.append(f'<h1>{h1}</h1>')
    if date_text:
        body_parts.append(f'<p class="doc-date" style="font-weight:600; color:#475569; margin:10px 0 20px;">{date_text}</p>')
    body_parts.append('<div class="line"></div>')

    if iframes:
        body_parts.append('<div class="iframes-container" style="display:flex; flex-direction:column; gap:30px; margin:20px 0;">')
        for ifr in iframes:
            fname = os.path.basename(ifr)
            clean_src = '/files/' + urllib.parse.quote(fname)
            body_parts.append(f'''
            <div class="iframe-box" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
                <div style="margin-bottom:8px; font-weight:500; color:#1e293b; display:flex; justify-content:space-between; align-items:center;">
                    <span>{fname}</span>
                    <a href="{clean_src}" target="_blank" rel="noopener noreferrer" style="font-size:13px; color:#2563eb; text-decoration:underline;">Открыть в новой вкладке ↗</a>
                </div>
                <iframe src="{clean_src}" width="100%" height="800" style="border:none; border-radius:4px; background:#fff;"></iframe>
            </div>''')
        body_parts.append('</div>')
    elif files:
        body_parts.append('<div class="doc-actions" style="margin:20px 0; display:flex; flex-wrap:wrap; gap:12px;">')
        for f in files:
            fname = os.path.basename(f)
            file_url = '/files/' + urllib.parse.quote(fname)
            body_parts.append(f'''
            <div class="buttom">
                <a href="{file_url}" target="_blank" rel="noopener noreferrer">Посмотреть документ ({fname})</a>
            </div>''')
        body_parts.append('</div>')
    else:
        body_parts.append('<p>Документ временно недоступен для скачивания.</p>')

    full_html = '\n'.join(body_parts)
    return portal_layout(content=full_html, title=title, description=desc, active_nav='reports', is_admin=is_admin, current_slug=doc_key)
