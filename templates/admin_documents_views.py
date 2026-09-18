# -*- coding: utf-8 -*-
import html
from typing import Any, Dict, List, Optional

from templates.admin_nav import _admin_nav_bar
from templates.icons import icon


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

