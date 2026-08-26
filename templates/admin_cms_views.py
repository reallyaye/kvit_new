# -*- coding: utf-8 -*-
import html
import json
import urllib.parse
from typing import Any, Dict, List, Optional

from templates.icons import icon


def _admin_nav_bar(active_tab: str = 'pages') -> str:
    """Верхняя навигационная полоса внутри разделов админ-панели."""
    tabs = [
        ('pages', '/admin/pages', 'pages', 'Страницы сайта'),
        ('media', '/admin/media', 'image', 'Медиа и файлы'),
        ('documents', '/admin/documents', 'files', 'Реестр отчетов и документов'),
        ('kvit', '/upload', 'upload', 'Квитанции'),
        ('reconcile', '/reconcile', 'reconcile', 'Сверка'),
    ]
    links_html = []
    for key, href, ic, label in tabs:
        active_cls = ' active' if key == active_tab else ''
        links_html.append(f'<a href="{href}" class="admin-tab-btn{active_cls}">{icon(ic, 15)} {label}</a>')
    
    return f'''
    <div class="admin-nav-tabs" style="display:flex;gap:8px;margin-bottom:24px;border-bottom:2px solid #e2e8f0;padding-bottom:12px;flex-wrap:wrap;align-items:center;">
        <div style="font-weight:700;color:#1e293b;margin-right:12px;font-size:15px;display:flex;align-items:center;gap:6px;">
            {icon('shield', 18, '#2563eb')} Панель управления
        </div>
        {''.join(links_html)}
        <a href="/" target="_blank" class="admin-tab-btn" style="margin-left:auto;background:#f1f5f9;color:#2563eb;">
            {icon('external_link', 14, '#2563eb')} Перейти на сайт ↗
        </a>
    </div>
    '''


def render_admin_pages_list(
    pages: List[Dict[str, Any]],
    csrf_token: str,
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Рендерит дашборд со списком всех страниц портала."""
    msg_html = f'<div class="ok">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''

    cards_html = []
    for p in pages:
        slug = p['slug']
        title = p.get('title', slug)
        url = p.get('nav_url', f"/{slug}")
        is_main = p.get('is_main_nav', False)
        ic_name = p.get('icon', 'file_text')
        content_len = p.get('content_length', 0)
        snippet = p.get('snippet', '')
        if len(snippet) > 120:
            snippet = snippet[:120] + '...'

        main_badge = '<span class="tag tag-ok" style="font-size:11px;">Основное меню</span>' if is_main else '<span class="tag" style="background:#e2e8f0;color:#475569;font-size:11px;">Страница</span>'
        
        # Кнопка удаления (запрещено удалять home и 404)
        delete_btn = ''
        if slug not in ('home', '404'):
            delete_btn = f'''
            <form action="/admin/pages/delete" method="post" style="display:inline;" onsubmit="return confirm('Вы уверены, что хотите удалить страницу «{html.escape(slug)}»?');">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <input type="hidden" name="slug" value="{html.escape(slug)}">
                <button type="submit" class="btn btn-outline btn-sm" style="color:#dc2626;border-color:#fca5a5;" title="Удалить страницу">
                    {icon('trash', 14, '#dc2626')}
                </button>
            </form>
            '''

        cards_html.append(f'''
        <div class="cms-page-card" style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:16px;transition:.15s;margin-bottom:12px;">
            <div style="display:flex;align-items:center;gap:16px;min-width:0;">
                <div style="width:42px;height:42px;border-radius:10px;background:#eff6ff;color:#2563eb;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                    {icon(ic_name, 22, '#2563eb')}
                </div>
                <div style="min-width:0;">
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;flex-wrap:wrap;">
                        <span style="font-weight:700;font-size:16px;color:#1e293b;">{html.escape(title)}</span>
                        {main_badge}
                        <code style="background:#f1f5f9;color:#64748b;padding:2px 8px;border-radius:6px;font-size:12px;">{html.escape(url)}</code>
                    </div>
                    <div style="font-size:13px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:550px;">
                        {html.escape(snippet) if snippet else '<em>(Контент не задан)</em>'} &bull; <span style="color:#94a3b8;">{content_len} симв.</span>
                    </div>
                </div>
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
                <a href="{html.escape(url)}" target="_blank" class="btn btn-outline btn-sm" title="Открыть страницу на сайте">
                    {icon('external_link', 14, '#2563eb')} Посмотреть
                </a>
                <a href="/admin/pages/edit?slug={html.escape(slug)}" class="btn btn-sm" style="display:inline-flex;align-items:center;gap:4px;">
                    {icon('edit', 14, '#fff')} Редактировать
                </a>
                {delete_btn}
            </div>
        </div>
        ''')

    return f'''
    <div class="card" style="max-width:1100px;margin:24px auto;">
        {_admin_nav_bar('pages')}
        
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
            <div>
                <h1 style="font-size:22px;color:#1e293b;margin:0 0 4px;">Управление страницами сайта</h1>
                <p class="subtitle" style="margin:0;">Редактируйте текст, добавляйте новые разделы, прикрепляйте фото, документы и ссылки.</p>
            </div>
            <div style="display:flex;gap:10px;">
                <a href="/admin/media" class="btn btn-outline" style="display:inline-flex;align-items:center;gap:6px;margin:0;">
                    {icon('image', 16, '#2563eb')} Медиа и файлы
                </a>
                <a href="/admin/pages/new" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px;margin:0;">
                    {icon('plus', 16, '#fff')} Создать страницу
                </a>
            </div>
        </div>

        {msg_html}
        {err_html}

        <div style="margin-top:16px;">
            {''.join(cards_html)}
        </div>
    </div>
    '''


def render_admin_page_editor(
    slug: str,
    page_data: Dict[str, Any],
    csrf_token: str,
    media_files: List[Dict[str, Any]],
    is_new: bool = False,
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Рендерит полноценный визуальный / HTML редактор страницы с тулбаром и медиа-вставками."""
    msg_html = f'<div class="ok">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''

    title_val = page_data.get('title', '')
    html_val = page_data.get('html', '')
    url_preview = f"/{slug}" if slug != 'home' else '/'

    # Подготовка списка медиа-файлов в формате JSON для JS-вставки
    media_json = json.dumps([{
        'filename': m['filename'],
        'url': m['url'],
        'type': m['type'],
        'size': m['size_formatted']
    } for m in media_files], ensure_ascii=False)

    return f'''
    <div class="card" style="max-width:1200px;margin:24px auto;">
        {_admin_nav_bar('pages')}

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:12px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <a href="/admin/pages" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:4px;">
                    {icon('arrow_left', 14, '#2563eb')} Назад к списку
                </a>
                <h1 style="font-size:20px;color:#1e293b;margin:0;">
                    {'Создание новой страницы' if is_new else f'Редактирование страницы: <code>{html.escape(slug)}</code>'}
                </h1>
            </div>
            {'<a href="' + html.escape(url_preview) + '" target="_blank" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:4px;">' + icon('external_link', 14, '#2563eb') + ' Открыть на сайте ↗</a>' if not is_new else ''}
        </div>

        {msg_html}
        {err_html}

        <form action="/admin/pages/save" method="post" id="pageEditorForm">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <input type="hidden" name="is_new" value="{'1' if is_new else '0'}">
            
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
                <div>
                    <label style="margin-top:0;">Название страницы (Заголовок / Title)</label>
                    <input type="text" name="title" id="pageTitle" value="{html.escape(title_val)}" placeholder="например: Тарифы на электроэнергию" required style="font-size:15px;padding:10px 14px;">
                </div>
                <div>
                    <label style="margin-top:0;">URL-адрес (Slug страницы)</label>
                    <input type="text" name="slug" id="pageSlug" value="{html.escape(slug)}" placeholder="например: tarif или zakupki" {'readonly' if (not is_new and slug in ('home', '404')) else 'required'} style="font-size:15px;padding:10px 14px;{'background:#f8fafc;' if not is_new and slug in ('home', '404') else ''}">
                    <small style="color:#64748b;font-size:12px;">Страница будет доступна по адресу: <code>http://.../имя-страницы</code></small>
                </div>
            </div>

            <!-- ТУЛБАР БЫСТРЫХ ДЕЙСТВИЙ И ВСТАВОК -->
            <div class="cms-toolbar" style="background:#f8fafc;border:1.5px solid #cbd5e1;border-bottom:none;border-radius:10px 10px 0 0;padding:10px 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <span style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;margin-right:4px;">Вставка:</span>
                
                <button type="button" class="tool-btn" onclick="openMediaModal('image')" title="Вставить изображение из медиатеки">
                    {icon('image', 14, '#2563eb')} Фото / Картинка
                </button>
                <button type="button" class="tool-btn" onclick="openMediaModal('doc')" title="Прикрепить кнопку скачивания документа">
                    {icon('file_text', 14, '#16a34a')} Файл / Документ (PDF/Word/Excel)
                </button>
                <button type="button" class="tool-btn" onclick="insertLinkPrompt()" title="Вставить гиперссылку">
                    {icon('link', 14, '#0284c7')} Ссылка
                </button>
                <button type="button" class="tool-btn" onclick="insertTableSnippet()" title="Вставить таблицу">
                    {icon('grid', 14, '#475569')} Таблица
                </button>
                <button type="button" class="tool-btn" onclick="insertHeadingSnippet()" title="Вставить заголовок H2">
                    <b>H2</b>
                </button>
                <button type="button" class="tool-btn" onclick="insertAlertSnippet()" title="Вставить информационный блок">
                    {icon('info', 14, '#d97706')} Инфо-блок
                </button>

                <div style="margin-left:auto;display:flex;gap:8px;">
                    <button type="button" class="tool-btn" id="previewToggleBtn" onclick="togglePreview()" style="background:#eff6ff;color:#2563eb;font-weight:600;">
                        {icon('eye', 14, '#2563eb')} Предпросмотр
                    </button>
                </div>
            </div>

            <!-- РЕДАКТОР И ПРЕДПРОСМОТР -->
            <div style="display:grid;grid-template-columns:1fr;gap:0;margin-bottom:20px;" id="editorContainer">
                <div id="codeEditorPane">
                    <textarea name="html" id="pageHtmlContent" rows="22" style="width:100%;font-family:Consolas,monospace;font-size:14px;line-height:1.5;padding:16px;border:1.5px solid #cbd5e1;border-radius:0 0 10px 10px;outline:none;background:#fafbfc;color:#1e293b;box-sizing:border-box;resize:vertical;" placeholder="Введите HTML-контент страницы...">{html.escape(html_val)}</textarea>
                </div>
                <div id="previewPane" style="display:none;border:1.5px solid #cbd5e1;border-radius:0 0 10px 10px;padding:24px;background:#fff;min-height:300px;max-height:600px;overflow-y:auto;">
                    <div id="previewContent"></div>
                </div>
            </div>

            <!-- БЛОК БЫСТРОЙ ЗАГРУЗКИ ФАЙЛА НАПРЯМУЮ ИЗ РЕДАКТОРА -->
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
                <div style="display:flex;align-items:center;gap:10px;">
                    {icon('upload', 18, '#2563eb')}
                    <div>
                        <div style="font-weight:600;font-size:14px;color:#1e293b;">Быстрая загрузка нового фото или файла прямо сюда:</div>
                        <div style="font-size:12px;color:#64748b;">После загрузки файл появится в галерее и будет вставлен в контент.</div>
                    </div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;">
                    <input type="file" id="inlineQuickUploadInput" style="font-size:13px;max-width:240px;">
                    <button type="button" class="btn btn-outline btn-sm" onclick="uploadInlineFile()" style="margin:0;">Загрузить и вставить</button>
                </div>
            </div>

            <!-- КНОПКИ СОХРАНЕНИЯ -->
            <div style="display:flex;gap:12px;align-items:center;">
                <button type="submit" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px;padding:12px 28px;font-size:16px;margin:0;">
                    {icon('save', 18, '#fff')} Сохранить страницу
                </button>
                <a href="/admin/pages" class="btn btn-outline" style="margin:0;">Отмена</a>
            </div>
        </form>
    </div>

    <!-- МОДАЛЬНОЕ ОКНО ВЫБОРА МЕДИА-ФАЙЛОВ -->
    <div id="mediaPickerModal" style="display:none;position:fixed;inset:0;background:rgba(15,23,42,0.6);z-index:9999;align-items:center;justify-content:center;backdrop-filter:blur(4px);">
        <div style="background:#fff;border-radius:14px;max-width:800px;width:90%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 20px 25px -5px rgba(0,0,0,0.3);overflow:hidden;">
            <div style="padding:16px 20px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;">
                <div style="font-weight:700;font-size:17px;color:#1e293b;display:flex;align-items:center;gap:8px;" id="modalTitle">
                    {icon('image', 18, '#2563eb')} Выберите файл для вставки
                </div>
                <button type="button" onclick="closeMediaModal()" style="border:none;background:none;cursor:pointer;font-size:20px;color:#64748b;">✕</button>
            </div>
            
            <div style="padding:16px 20px;overflow-y:auto;flex:1;">
                <div id="modalMediaList" style="display:grid;grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));gap:14px;"></div>
            </div>

            <div style="padding:14px 20px;border-top:1px solid #e2e8f0;background:#f8fafc;display:flex;justify-content:space-between;align-items:center;">
                <a href="/admin/media" target="_blank" style="font-size:13px;color:#2563eb;text-decoration:none;">Открыть полный менеджер медиа ↗</a>
                <button type="button" class="btn btn-outline btn-sm" onclick="closeMediaModal()" style="margin:0;">Закрыть</button>
            </div>
        </div>
    </div>

    <style>
    .tool-btn {{
        background: #fff;
        border: 1px solid #cbd5e1;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        color: #334155;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        transition: .15s;
    }}
    .tool-btn:hover {{
        background: #f1f5f9;
        border-color: #94a3b8;
    }}
    .admin-tab-btn {{
        padding: 8px 16px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        color: #475569;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        transition: .15s;
    }}
    .admin-tab-btn:hover {{
        background: #f1f5f9;
        color: #1e293b;
    }}
    .admin-tab-btn.active {{
        background: #2563eb;
        color: #fff;
    }}
    </style>

    <script>
    const mediaFilesData = {media_json};
    const csrfToken = "{csrf_token}";

    function insertAtCursor(text) {{
        const textarea = document.getElementById('pageHtmlContent');
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const val = textarea.value;
        textarea.value = val.substring(0, start) + text + val.substring(end);
        textarea.focus();
        textarea.selectionStart = textarea.selectionEnd = start + text.length;
        if (document.getElementById('previewPane').style.display !== 'none') {{
            updateLivePreview();
        }}
    }}

    function insertLinkPrompt() {{
        const url = prompt('Введите URL ссылки (например https://example.com или /reports):', 'https://');
        if (!url) return;
        const text = prompt('Введите текст ссылки:', 'Подробнее');
        if (!text) return;
        insertAtCursor('<a href="' + url + '" target="_blank" rel="noopener noreferrer" style="color:#2563eb;text-decoration:underline;">' + text + '</a>');
    }}

    function insertTableSnippet() {{
        const tableHtml = `
<table class="portal-table" style="width:100%; border-collapse:collapse; margin:20px 0; font-size:14px;">
    <thead>
        <tr style="background:#f8fafc; border-bottom:2px solid #cbd5e1; text-align:left;">
            <th style="padding:10px 14px;">№</th>
            <th style="padding:10px 14px;">Наименование</th>
            <th style="padding:10px 14px;">Значение / Тариф</th>
        </tr>
    </thead>
    <tbody>
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px 14px;">1</td>
            <td style="padding:10px 14px;">Пример строки 1</td>
            <td style="padding:10px 14px;">100.00 ₸</td>
        </tr>
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px 14px;">2</td>
            <td style="padding:10px 14px;">Пример строки 2</td>
            <td style="padding:10px 14px;">200.00 ₸</td>
        </tr>
    </tbody>
</table>
`;
        insertAtCursor(tableHtml);
    }}

    function insertHeadingSnippet() {{
        const heading = prompt('Введите текст заголовка:', 'Новый раздел');
        if (!heading) return;
        insertAtCursor('<h2 style="font-size:20px; color:#1e293b; margin:24px 0 12px; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">' + heading + '</h2>\\n');
    }}

    function insertAlertSnippet() {{
        const text = prompt('Введите текст информационного сообщения:', 'Важная информация для потребителей');
        if (!text) return;
        insertAtCursor('<div style="background:#eff6ff; border-left:4px solid #2563eb; padding:14px 18px; border-radius:6px; margin:16px 0; color:#1e40af; font-size:14px;">' + text + '</div>\\n');
    }}

    let isPreviewActive = false;
    function togglePreview() {{
        const codePane = document.getElementById('codeEditorPane');
        const prevPane = document.getElementById('previewPane');
        const btn = document.getElementById('previewToggleBtn');
        isPreviewActive = !isPreviewActive;

        if (isPreviewActive) {{
            updateLivePreview();
            codePane.style.display = 'none';
            prevPane.style.display = 'block';
            btn.innerHTML = '{icon('code', 14, '#2563eb')} Редактор HTML';
        }} else {{
            codePane.style.display = 'block';
            prevPane.style.display = 'none';
            btn.innerHTML = '{icon('eye', 14, '#2563eb')} Предпросмотр';
        }}
    }}

    function updateLivePreview() {{
        const html = document.getElementById('pageHtmlContent').value;
        document.getElementById('previewContent').innerHTML = html;
    }}

    function openMediaModal(filterType) {{
        const modal = document.getElementById('mediaPickerModal');
        const list = document.getElementById('modalMediaList');
        const title = document.getElementById('modalTitle');
        list.innerHTML = '';

        title.innerHTML = filterType === 'image' 
            ? '{icon('image', 18, '#2563eb')} Выберите изображение для вставки' 
            : '{icon('file_text', 18, '#16a34a')} Выберите документ для прикрепления';

        const filtered = mediaFilesData.filter(m => filterType === 'all' || m.type === filterType);
        
        if (filtered.length === 0) {{
            list.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:30px;">Нет загруженных файлов данного типа. Воспользуйтесь быстрой загрузкой ниже.</div>';
        }} else {{
            filtered.forEach(m => {{
                const item = document.createElement('div');
                item.style.border = '1px solid #e2e8f0';
                item.style.borderRadius = '8px';
                item.style.padding = '10px';
                item.style.background = '#f8fafc';
                item.style.cursor = 'pointer';
                item.style.display = 'flex';
                item.style.flexDirection = 'column';
                item.style.alignItems = 'center';
                item.style.gap = '8px';
                item.style.transition = '.15s';
                item.onmouseover = () => item.style.borderColor = '#2563eb';
                item.onmouseout = () => item.style.borderColor = '#e2e8f0';

                let previewHtml = '';
                if (m.type === 'image') {{
                    previewHtml = '<img src="' + m.url + '" style="width:100%;height:90px;object-fit:cover;border-radius:6px;">';
                }} else {{
                    previewHtml = '<div style="height:90px;display:flex;align-items:center;justify-content:center;color:#16a34a;">' + `{icon('file_text', 36, '#16a34a')}` + '</div>';
                }}

                item.innerHTML = previewHtml + 
                    '<div style="font-size:12px;font-weight:600;color:#1e293b;word-break:break-all;text-align:center;">' + m.filename + '</div>' +
                    '<div style="font-size:11px;color:#64748b;">' + m.size + '</div>' +
                    '<button type="button" class="btn btn-sm" style="width:100%;padding:4px 8px;font-size:12px;margin:0;">Выбрать</button>';
                
                item.onclick = () => {{
                    if (m.type === 'image') {{
                        insertAtCursor('<img src="' + m.url + '" alt="' + m.filename + '" style="max-width:100%; border-radius:8px; margin:16px 0; box-shadow:0 2px 8px rgba(0,0,0,0.08);" />\\n');
                    }} else {{
                        insertAtCursor('<div class="buttom" style="margin:14px 0;"><a href="' + m.url + '" target="_blank" rel="noopener noreferrer">Посмотреть документ (' + m.filename + ')</a></div>\\n');
                    }}
                    closeMediaModal();
                }};

                list.appendChild(item);
            }});
        }}

        modal.style.display = 'flex';
    }}

    function closeMediaModal() {{
        document.getElementById('mediaPickerModal').style.display = 'none';
    }}

    async function uploadInlineFile() {{
        const input = document.getElementById('inlineQuickUploadInput');
        if (!input.files || input.files.length === 0) {{
            alert('Пожалуйста, выберите файл на вашем компьютере.');
            return;
        }}
        const file = input.files[0];
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);
        formData.append('media_file', file);

        try {{
            const res = await fetch('/admin/media/upload?ajax=1', {{
                method: 'POST',
                body: formData
            }});
            const data = await res.json();
            if (data.ok && data.file) {{
                mediaFilesData.unshift(data.file);
                if (data.file.type === 'image') {{
                    insertAtCursor('<img src="' + data.file.url + '" alt="' + data.file.filename + '" style="max-width:100%; border-radius:8px; margin:16px 0; box-shadow:0 2px 8px rgba(0,0,0,0.08);" />\\n');
                }} else {{
                    insertAtCursor('<div class="buttom" style="margin:14px 0;"><a href="' + data.file.url + '" target="_blank" rel="noopener noreferrer">Скачать / Просмотреть документ (' + data.file.filename + ')</a></div>\\n');
                }}
                alert('Файл «' + data.file.filename + '» успешно загружен и вставлен в редактор!');
                input.value = '';
            }} else {{
                alert('Ошибка загрузки: ' + (data.error || 'Неизвестная ошибка'));
            }}
        }} catch(e) {{
            alert('Сетевая ошибка при загрузке: ' + e);
        }}
    }}
    </script>
    '''


def render_admin_media_gallery(
    media_files: List[Dict[str, Any]],
    csrf_token: str,
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Рендерит медиатеку и файловый менеджер со всеми загруженными фотографиями и документами."""
    msg_html = f'<div class="ok">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''

    cards_html = []
    for m in media_files:
        fname = m['filename']
        url = m['url']
        size = m['size_formatted']
        mtime = m['modified_formatted']
        is_img = m['type'] == 'image'

        if is_img:
            preview = f'<img src="{html.escape(url)}" alt="{html.escape(fname)}" style="width:100%;height:130px;object-fit:cover;border-radius:8px 8px 0 0;background:#f1f5f9;">'
        else:
            preview = f'''
            <div style="height:130px;background:#f8fafc;border-radius:8px 8px 0 0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;border-bottom:1px solid #e2e8f0;">
                <span style="color:#2563eb;">{icon('file_text', 36, '#2563eb')}</span>
                <span style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;">.{html.escape(m['ext'])}</span>
            </div>'''

        cards_html.append(f'''
        <div class="media-card" style="background:#fff;border:1.5px solid #e2e8f0;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 1px 3px rgba(0,0,0,0.05);transition:.15s;">
            {preview}
            <div style="padding:12px;display:flex;flex-direction:column;flex:1;gap:6px;">
                <div style="font-weight:600;font-size:13px;color:#1e293b;word-break:break-all;line-height:1.3;" title="{html.escape(fname)}">
                    {html.escape(fname)}
                </div>
                <div style="font-size:11px;color:#64748b;display:flex;justify-content:space-between;align-items:center;margin-top:auto;">
                    <span>{size}</span>
                    <span>{mtime}</span>
                </div>
                <div style="display:flex;gap:6px;margin-top:8px;">
                    <button type="button" class="btn btn-outline btn-sm" onclick="copyMediaUrl('{html.escape(url)}')" style="flex:1;padding:6px 8px;font-size:12px;margin:0;" title="Скопировать ссылку">
                        {icon('copy', 12, '#2563eb')} Ссылка
                    </button>
                    <a href="{html.escape(url)}" target="_blank" class="btn btn-outline btn-sm" style="padding:6px 10px;font-size:12px;margin:0;" title="Открыть">
                        {icon('external_link', 12, '#2563eb')}
                    </a>
                    <form action="/admin/media/delete" method="post" style="display:inline;margin:0;" onsubmit="return confirm('Удалить файл {html.escape(fname)}?');">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <input type="hidden" name="filename" value="{html.escape(fname)}">
                        <button type="submit" class="btn btn-outline btn-sm" style="color:#dc2626;border-color:#fca5a5;padding:6px 8px;font-size:12px;margin:0;" title="Удалить">
                            {icon('trash', 12, '#dc2626')}
                        </button>
                    </form>
                </div>
            </div>
        </div>
        ''')

    return f'''
    <div class="card" style="max-width:1100px;margin:24px auto;">
        {_admin_nav_bar('media')}

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
            <div>
                <h1 style="font-size:22px;color:#1e293b;margin:0 0 4px;">Медиа и файлы</h1>
                <p class="subtitle" style="margin:0;">Загружайте фотографии, отчеты, презентации, нормативные документы и файлы.</p>
            </div>
        </div>

        {msg_html}
        {err_html}

        <!-- ФОРМА ЗАГРУЗКИ НОВЫХ ФАЙЛОВ -->
        <div style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:12px;padding:24px;text-align:center;margin-bottom:28px;">
            <form action="/admin/media/upload" method="post" enctype="multipart/form-data" id="mediaUploadForm">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <div style="color:#2563eb;margin-bottom:8px;">{icon('upload_cloud_large', 44, '#2563eb')}</div>
                <div style="font-weight:600;font-size:16px;color:#1e293b;margin-bottom:4px;">Перетащите сюда файлы или выберите с компьютера</div>
                <div style="font-size:13px;color:#64748b;margin-bottom:16px;">Поддерживаются: PNG, JPG, WEBP, SVG, PDF, DOCX, XLSX, XLS, ZIP (до 50 МБ)</div>
                <div style="display:flex;justify-content:center;gap:12px;align-items:center;flex-wrap:wrap;">
                    <input type="file" name="media_file" id="mediaFileInput" required style="font-size:14px;max-width:320px;">
                    <button type="submit" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px;margin:0;">
                        {icon('upload', 16, '#fff')} Загрузить в хранилище
                    </button>
                </div>
            </form>
        </div>

        <!-- СПИСОК / СЕТКА ФАЙЛОВ -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <div style="font-weight:700;font-size:16px;color:#1e293b;">Все файлы ({len(media_files)})</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));gap:16px;">
            {''.join(cards_html) if cards_html else '<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:40px;">Файлов пока нет. Загрузите первый файл выше.</div>'}
        </div>
    </div>

    <script>
    function copyMediaUrl(url) {{
        const fullUrl = window.location.origin + url;
        navigator.clipboard.writeText(url).then(() => {{
            alert('Относительный URL скопирован в буфер обмена:\\n' + url);
        }}).catch(() => {{
            prompt('Скопируйте URL:', url);
        }});
    }}
    </script>
    '''


def render_admin_documents_list(
    documents: List[Dict[str, Any]],
    csrf_token: str,
    search: str = '',
    category: str = '',
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Рендерит реестр документов и отчетов (инвестпрограммы, тарифные сметы и др.)."""
    msg_html = f'<div class="ok">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''

    docs_rows = []
    for d in documents:
        key = d['key']
        title = d.get('title', key)
        cat = d.get('category', 'other')
        date_text = d.get('date_text', '')
        files_count = len(d.get('files', []))
        iframes_count = len(d.get('iframes', []))

        docs_rows.append(f'''
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px 12px;font-weight:600;color:#1e293b;">
                <a href="/{html.escape(key)}" target="_blank" style="color:#2563eb;text-decoration:none;font-weight:600;">
                    {html.escape(title)}
                </a>
                <div style="font-size:12px;color:#64748b;margin-top:2px;"><code>{html.escape(key)}</code> &bull; {html.escape(date_text)}</div>
            </td>
            <td style="padding:10px 12px;">
                <span class="tag" style="background:#f1f5f9;color:#475569;font-size:12px;">{html.escape(cat)}</span>
            </td>
            <td style="padding:10px 12px;font-size:13px;color:#475569;">
                {f'<span style="display:inline-flex;align-items:center;gap:4px;">{icon("file_text", 13, "#2563eb")} Файлов: {files_count}</span> ' if files_count else ''}
                {f'<span style="display:inline-flex;align-items:center;gap:4px;">{icon("eye", 13, "#0891b2")} Iframes: {iframes_count}</span>' if iframes_count else ''}
            </td>
            <td style="padding:10px 12px;text-align:right;white-space:nowrap;">
                <a href="/admin/documents/edit?key={html.escape(key)}" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:4px;margin:0;">
                    {icon('edit', 13, '#2563eb')} Редактировать
                </a>
                <form action="/admin/documents/delete" method="post" style="display:inline;margin-left:6px;" onsubmit="return confirm('Удалить документ {html.escape(key)}?');">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <input type="hidden" name="key" value="{html.escape(key)}">
                    <button type="submit" class="btn btn-outline btn-sm" style="color:#dc2626;border-color:#fca5a5;margin:0;" title="Удалить">
                        {icon('trash', 13, '#dc2626')}
                    </button>
                </form>
            </td>
        </tr>
        ''')

    return f'''
    <div class="card" style="max-width:1100px;margin:24px auto;">
        {_admin_nav_bar('documents')}

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
            <div>
                <h1 style="font-size:22px;color:#1e293b;margin:0 0 4px;">Реестр отчетов и документов</h1>
                <p class="subtitle" style="margin:0;">Квартальные и годовые отчеты ИП, тарифные сметы, документы по закупкам и загрузке подстанций.</p>
            </div>
            <a href="/admin/documents/new" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px;margin:0;">
                {icon('plus', 16, '#fff')} Добавить отчет / документ
            </a>
        </div>

        {msg_html}
        {err_html}

        <div style="margin-top:16px;overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;text-align:left;">
                        <th style="padding:10px 12px;">Наименование отчета / Документа</th>
                        <th style="padding:10px 12px;">Категория</th>
                        <th style="padding:10px 12px;">Прикрепления</th>
                        <th style="padding:10px 12px;text-align:right;">Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(docs_rows) if docs_rows else '<tr><td colspan="4" style="text-align:center;padding:30px;color:#64748b;">Документы не найдены.</td></tr>'}
                </tbody>
            </table>
        </div>
    </div>
    '''


def render_admin_document_editor(
    doc_key: str,
    doc_data: Dict[str, Any],
    csrf_token: str,
    is_new: bool = False,
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Форма редактирования документа/отчета из реестра."""
    msg_html = f'<div class="ok">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''

    title_val = doc_data.get('title', '')
    cat_val = doc_data.get('category', 'other')
    date_val = doc_data.get('date_text', '')
    files_val = '\n'.join(doc_data.get('files', []))
    iframes_val = '\n'.join(doc_data.get('iframes', []))

    return f'''
    <div class="card" style="max-width:900px;margin:24px auto;">
        {_admin_nav_bar('documents')}

        <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;">
            <a href="/admin/documents" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:4px;">
                {icon('arrow_left', 14, '#2563eb')} Назад
            </a>
            <h1 style="font-size:20px;color:#1e293b;margin:0;">
                {'Добавление нового документа/отчета' if is_new else f'Редактирование документа: <code>{html.escape(doc_key)}</code>'}
            </h1>
        </div>

        {msg_html}
        {err_html}

        <form action="/admin/documents/save" method="post">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <input type="hidden" name="is_new" value="{'1' if is_new else '0'}">

            <label>Имя страницы / Ключ документа (например: invest-1-2026.php)</label>
            <input type="text" name="key" value="{html.escape(doc_key)}" {'readonly' if not is_new else 'required'} placeholder="invest-1-2026.php" style="font-size:15px;padding:10px 14px;{'background:#f8fafc;' if not is_new else ''}">

            <label>Заголовок отчета / документа</label>
            <input type="text" name="title" value="{html.escape(title_val)}" required placeholder="Отчет по исполнению инвестиционной программы за 1 квартал 2026 года" style="font-size:15px;padding:10px 14px;">

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                <div>
                    <label>Категория</label>
                    <select name="category" style="font-size:15px;padding:10px 14px;">
                        <option value="invest" {'selected' if cat_val == 'invest' else ''}>Инвестиционная программа (invest)</option>
                        <option value="isp_ts" {'selected' if cat_val == 'isp_ts' else ''}>Тарифная смета (isp_ts)</option>
                        <option value="ktp" {'selected' if cat_val == 'ktp' else ''}>Загрузка КТП (ktp)</option>
                        <option value="line" {'selected' if cat_val == 'line' else ''}>Линии электропередач (line)</option>
                        <option value="other" {'selected' if cat_val == 'other' else ''}>Прочее / Другие отчеты</option>
                    </select>
                </div>
                <div>
                    <label>Дата / Период</label>
                    <input type="text" name="date_text" value="{html.escape(date_val)}" placeholder="Дата: 31.03.2026 г." style="font-size:15px;padding:10px 14px;">
                </div>
            </div>

            <label>Прикрепленные файлы (по одному пути в строке, например /files/report.pdf или report.pdf)</label>
            <textarea name="files" rows="4" style="width:100%;font-family:Consolas,monospace;font-size:13px;padding:10px 14px;border:1.5px solid #cbd5e1;border-radius:8px;outline:none;" placeholder="/files/invest_1_2026.pdf">{html.escape(files_val)}</textarea>

            <label>Интерактивные просмотрщики (Iframe файлы, по одному в строке, например /files/ktp_2026.pdf)</label>
            <textarea name="iframes" rows="3" style="width:100%;font-family:Consolas,monospace;font-size:13px;padding:10px 14px;border:1.5px solid #cbd5e1;border-radius:8px;outline:none;" placeholder="/files/ktp_2026_01.pdf">{html.escape(iframes_val)}</textarea>

            <div style="margin-top:24px;display:flex;gap:12px;align-items:center;">
                <button type="submit" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px;padding:12px 28px;font-size:15px;margin:0;">
                    {icon('save', 16, '#fff')} Сохранить документ
                </button>
                <a href="/admin/documents" class="btn btn-outline" style="margin:0;">Отмена</a>
            </div>
        </form>
    </div>
    '''
