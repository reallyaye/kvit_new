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
    raw_files = doc.get('files', [])
    raw_iframes = doc.get('iframes', [])

    # Разделяем на PDF-просмотрщики и сопутствующие вложения (ZIP, DOCX, XLSX и др.)
    pdf_viewers = []
    attachments = []

    # 1. Явные iframes
    for ifr in raw_iframes:
        if ifr and ifr not in pdf_viewers:
            pdf_viewers.append(ifr)

    # 2. Файлы: если это PDF — направляем в интерактивный просмотрщик (если еще не добавлен)
    for f in raw_files:
        if not f:
            continue
        clean_ext = os.path.splitext(f)[1].lower()
        if clean_ext == '.pdf':
            if f not in pdf_viewers:
                pdf_viewers.append(f)
        else:
            if f not in attachments:
                attachments.append(f)

    body_parts = []
    
    # Breadcrumbs & Header с кнопкой возврата к отчетам
    date_meta_html = f'<div class="doc-meta-date">{icon("calendar", 14, "#64748b")} <span>Опубликовано: {date_text}</span></div>' if date_text else ''
    body_parts.append(f'''
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
        <nav class="breadcrumb-nav" style="margin-bottom: 0;" aria-label="Хлебные крошки">
            <a href="/">{icon("home", 13, "#64748b")} Главная</a>
            <span class="breadcrumb-sep">{icon("chevron_right", 12, "#94a3b8")}</span>
            <a href="/reports">Отчеты</a>
            <span class="breadcrumb-sep">{icon("chevron_right", 12, "#94a3b8")}</span>
            <span class="breadcrumb-current">{h1}</span>
        </nav>
        <a href="/reports" class="btn-doc-action" style="padding: 6px 14px; font-size: 13px; font-weight: 600;">
            {icon("arrow_left", 14, "#2563eb")}
            <span>Назад к отчетам</span>
        </a>
    </div>
    <div class="page-title-wrap">
        <div class="page-category-badge">{icon("file_text", 12, "#2563eb")} Официальный отчет</div>
        <h1 class="page-main-title">{h1}</h1>
        {date_meta_html}
    </div>
    ''')

    # Блок интерактивного PDF-просмотрщика
    if pdf_viewers:
        body_parts.append('<div class="iframes-container">')
        for ifr in pdf_viewers:
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
                    <iframe src="{clean_src}" width="100%" height="840" style="border:none; border-radius:0 0 12px 12px; background:#fff;"></iframe>
                </div>
            </div>''')
        body_parts.append('</div>')

    # Блок сопутствующих материалов и приложений (ZIP-архивы, обосновывающие материалы)
    if attachments:
        body_parts.append(f'''
        <div class="doc-attachments-wrap" style="margin-top: { '32px' if pdf_viewers else '16px' };">
            <div class="doc-attachments-header" style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px;">
                <div style="width: 32px; height: 32px; border-radius: 8px; background: #fef3c7; display: flex; align-items: center; justify-content: center;">
                    {icon('archive', 16, '#d97706')}
                </div>
                <div>
                    <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;">Обосновывающие материалы и приложения</h3>
                    <p style="margin: 2px 0 0 0; font-size: 12.5px; color: #64748b;">Файлы и архивы, прилагаемые к официальному отчету</p>
                </div>
            </div>
            <div class="doc-files-grid">
        ''')
        for att in attachments:
            fname = os.path.basename(att)
            ext = os.path.splitext(fname)[1].lower()
            file_url = '/files/' + urllib.parse.quote(fname)
            
            # Определение типа файла, бейджей и иконок
            if ext in ('.zip', '.rar', '.7z'):
                badge_text = 'ZIP-архив'
                badge_bg = '#fef3c7'
                badge_color = '#92400e'
                icon_name = 'archive'
                icon_color = '#d97706'
                icon_bg = '#fffbeb'
                btn_label = 'Скачать ZIP'
                if 'object' in fname.lower():
                    readable_name = 'Материалы и обосновывающие объекты'
                else:
                    readable_name = 'Архив сопутствующих документов и материалов'
            elif ext in ('.xls', '.xlsx'):
                badge_text = 'Excel-таблица'
                badge_bg = '#d1fae5'
                badge_color = '#065f46'
                icon_name = 'file_spreadsheet'
                icon_color = '#059669'
                icon_bg = '#ecfdf5'
                btn_label = 'Скачать Excel'
                readable_name = 'Таблица расчетов и показателей'
            elif ext in ('.doc', '.docx'):
                badge_text = 'Word-документ'
                badge_bg = '#e0e7ff'
                badge_color = '#3730a3'
                icon_name = 'file_text'
                icon_color = '#4338ca'
                icon_bg = '#eef2ff'
                btn_label = 'Скачать Word'
                readable_name = 'Текстовый документ'
            else:
                badge_text = ext.replace('.', '').upper() + ' файл'
                badge_bg = '#f1f5f9'
                badge_color = '#475569'
                icon_name = 'file_text'
                icon_color = '#64748b'
                icon_bg = '#f8fafc'
                btn_label = 'Скачать файл'
                readable_name = 'Приложение к отчету'

            body_parts.append(f'''
            <div class="doc-file-card">
                <div class="doc-file-icon" style="background: {icon_bg};">
                    {icon(icon_name, 24, icon_color)}
                </div>
                <div class="doc-file-info">
                    <div class="doc-file-title">
                        {readable_name}
                    </div>
                    <div class="doc-file-meta">
                        <span style="display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; background: {badge_bg}; color: {badge_color};">
                            {badge_text}
                        </span>
                        <span style="font-family: monospace; font-size: 12px; color: #64748b;">{fname}</span>
                    </div>
                </div>
                <div class="doc-file-action">
                    <a href="{file_url}" download class="btn-doc-download" style="background: {icon_color}; border-color: {icon_color};">
                        {icon('download', 14, '#ffffff')}
                        <span>{btn_label}</span>
                    </a>
                </div>
            </div>''')
        body_parts.append('</div></div>')

    # Пустое состояние
    if not pdf_viewers and not attachments:
        body_parts.append(f'''
        <div class="doc-empty-state">
            <div class="doc-empty-icon">{icon('info', 32, '#64748b')}</div>
            <div class="doc-empty-text">Документ временно недоступен для скачивания.</div>
            <a href="/reports" class="btn-return">{icon('arrow_left', 14, '#2563eb')} Вернуться к архиву отчетов</a>
        </div>''')

    clean_content = '\n'.join(body_parts)

    return portal_layout(
        content=clean_content,
        title=f"{h1} — ТОО «КРЭК»",
        active_nav='reports',
        is_admin=is_admin,
        current_slug=doc_key
    )
