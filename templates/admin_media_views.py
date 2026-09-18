# -*- coding: utf-8 -*-
import html
from typing import Any, Dict, List, Optional

from templates.admin_nav import _admin_nav_bar
from templates.icons import icon


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

