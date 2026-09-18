# -*- coding: utf-8 -*-
import datetime
import html
from typing import Any, Dict, List, Optional

from templates.admin_nav import _admin_nav_bar
from templates.icons import icon


def _format_audit_action_badge(action: str) -> str:
    """Форматирует тип действия в стилизованный бейдж с иконкой."""
    action = (action or '').upper()
    mapping = {
        'LOGIN': ('background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;', 'check', '#15803d', 'Вход в систему'),
        'LOGIN_FAILED': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'alert_triangle', '#b91c1c', 'Ошибка входа'),
        'LOGOUT': ('background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;', 'logout', '#475569', 'Выход'),
        'UPLOAD_START': ('background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;', 'upload', '#1d4ed8', 'Запуск загрузки'),
        'UPLOAD_SUCCESS': ('background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;', 'check_circle', '#15803d', 'Загрузка завершена'),
        'UPLOAD_FAILED': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'alert_triangle', '#b91c1c', 'Сбой загрузки'),
        'UPLOAD_RECEIPTS': ('background:#dbeafe;color:#1d4ed8;border:1px solid #bfdbfe;', 'upload', '#1d4ed8', 'Загрузка квитанций'),
        'DELETE_RECEIPT': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'trash', '#b91c1c', 'Удаление квитанции'),
        'CREATE_USER': ('background:#f3e8ff;color:#7e22ce;border:1px solid #e9d5ff;', 'user_plus', '#7e22ce', 'Создание пользователя'),
        'DELETE_USER': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'trash', '#b91c1c', 'Удаление пользователя'),
        'PAGE_SAVE': ('background:#e0e7ff;color:#4338ca;border:1px solid #c7d2fe;', 'save', '#4338ca', 'Сохранение страницы'),
        'PAGE_DELETE': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'trash', '#b91c1c', 'Удаление страницы'),
        'DOCUMENT_SAVE': ('background:#e0e7ff;color:#4338ca;border:1px solid #c7d2fe;', 'files', '#4338ca', 'Сохранение документа'),
        'DOCUMENT_DELETE': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'trash', '#b91c1c', 'Удаление документа'),
        'MEDIA_UPLOAD': ('background:#ccfbf1;color:#0f766e;border:1px solid #99f6e4;', 'image', '#0f766e', 'Загрузка медиа'),
        'MEDIA_DELETE': ('background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;', 'trash', '#b91c1c', 'Удаление медиа'),
        'RECONCILE_RUN': ('background:#fef3c7;color:#b45309;border:1px solid #fde68a;', 'reconcile', '#b45309', 'Сверка базы'),
        'RECONCILE_SYNC': ('background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;', 'refresh', '#15803d', 'Синхронизация'),
    }

    if action in mapping:
        style, ic, color, label = mapping[action]
        return f'<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:600;{style}">{icon(ic, 13, color)} {label}</span>'

    return f'<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:600;background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;">{icon("activity", 13, "#475569")} {html.escape(action)}</span>'


def render_admin_audit_log(
    logs: List[Dict[str, Any]],
    stats: Dict[str, Any],
    filters: Dict[str, Any],
    csrf_token: str,
    message: Optional[str] = None,
    error: Optional[str] = None,
    current_username: str = 'admin',
    current_role: str = 'admin'
) -> str:
    """Рендерит полноценный журнал аудита действий пользователей и администраторов."""
    msg_html = f'<div class="ok" style="margin-bottom:16px;">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err" style="margin-bottom:16px;">{html.escape(error)}</div>' if error else ''

    selected_user = filters.get('username') or ''
    selected_action = filters.get('action') or ''
    search_query = filters.get('search') or ''
    selected_limit = int(filters.get('limit') or 50)

    # Опции пользователей
    user_options = ['<option value="">Все пользователи</option>']
    for u in stats.get('users', []):
        sel = ' selected' if u == selected_user else ''
        user_options.append(f'<option value="{html.escape(u)}"{sel}>{html.escape(u)}</option>')

    # Опции действий
    action_labels = {
        '': 'Все типы действий',
        'LOGIN': 'Вход в систему (LOGIN)',
        'LOGIN_FAILED': 'Ошибка входа (LOGIN_FAILED)',
        'LOGOUT': 'Выход из системы (LOGOUT)',
        'UPLOAD_START': 'Запуск загрузки (UPLOAD_START)',
        'UPLOAD_SUCCESS': 'Загрузка завершена (UPLOAD_SUCCESS)',
        'UPLOAD_FAILED': 'Сбой загрузки (UPLOAD_FAILED)',
        'UPLOAD_RECEIPTS': 'Загрузка квитанций (UPLOAD_RECEIPTS)',
        'DELETE_RECEIPT': 'Удаление квитанции (DELETE_RECEIPT)',
        'CREATE_USER': 'Создание пользователя (CREATE_USER)',
        'DELETE_USER': 'Удаление пользователя (DELETE_USER)',
        'PAGE_SAVE': 'Сохранение страницы (PAGE_SAVE)',
        'PAGE_DELETE': 'Удаление страницы (PAGE_DELETE)',
        'DOCUMENT_SAVE': 'Сохранение документа (DOCUMENT_SAVE)',
        'DOCUMENT_DELETE': 'Удаление документа (DOCUMENT_DELETE)',
        'MEDIA_UPLOAD': 'Загрузка медиа (MEDIA_UPLOAD)',
        'MEDIA_DELETE': 'Удаление медиа (MEDIA_DELETE)',
        'RECONCILE_RUN': 'Сверка базы (RECONCILE_RUN)',
        'RECONCILE_SYNC': 'Синхронизация базы (RECONCILE_SYNC)'
    }
    action_options = []
    # Добавляем стандартные и уникальные из БД
    all_action_keys = list(action_labels.keys())
    for a in stats.get('actions', []):
        if a and a not in all_action_keys:
            all_action_keys.append(a)

    for act in all_action_keys:
        sel = ' selected' if act == selected_action else ''
        lbl = action_labels.get(act, act)
        action_options.append(f'<option value="{html.escape(act)}"{sel}>{html.escape(lbl)}</option>')

    # Опции лимита
    limit_options = []
    for lim in (50, 100, 200, 500):
        sel = ' selected' if lim == selected_limit else ''
        limit_options.append(f'<option value="{lim}"{sel}>Показывать {lim}</option>')

    # Формирование строк таблицы
    rows_html = []
    for log in logs:
        log_id = log.get('id', '')
        ts = log.get('created_at', 0)
        formatted_time = time_format_detailed(ts)
        u_name = log.get('username', '—')
        ip_addr = log.get('ip', '—')
        act = log.get('action', '')
        act_badge = _format_audit_action_badge(act)
        details = log.get('details', '')

        # Бейдж пользователя
        is_admin_user = (u_name == 'admin')
        user_badge_style = "background:#fee2e2;color:#991b1b;border:1px solid #fecaca;" if is_admin_user else "background:#eff6ff;color:#1e40af;border:1px solid #dbeafe;"
        user_badge = f'''<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:600;{user_badge_style}">
            {icon("shield" if is_admin_user else "user", 13, "#991b1b" if is_admin_user else "#1e40af")} {html.escape(u_name)}
        </span>'''

        rows_html.append(f'''
        <tr style="border-bottom:1px solid #e2e8f0;transition:background 0.15s;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='transparent'">
            <td style="padding:10px 14px;color:#94a3b8;font-size:12px;font-family:monospace;">#{log_id}</td>
            <td style="padding:10px 14px;color:#334155;font-size:13px;white-space:nowrap;font-weight:500;">
                <span style="display:inline-flex;align-items:center;gap:5px;">{icon('clock', 13, '#64748b')} {formatted_time}</span>
            </td>
            <td style="padding:10px 14px;white-space:nowrap;">{user_badge}</td>
            <td style="padding:10px 14px;color:#475569;font-size:12px;font-family:monospace;white-space:nowrap;">
                <span style="background:#f1f5f9;padding:2px 6px;border-radius:4px;border:1px solid #e2e8f0;">{html.escape(ip_addr)}</span>
            </td>
            <td style="padding:10px 14px;white-space:nowrap;">{act_badge}</td>
            <td style="padding:10px 14px;color:#334155;font-size:13px;line-height:1.4;">{html.escape(details)}</td>
        </tr>
        ''')

    empty_row = '''
    <tr>
        <td colspan="6" style="padding:40px 16px;text-align:center;color:#94a3b8;">
            <div style="margin-bottom:8px;">''' + icon('activity', 32, '#cbd5e1') + '''</div>
            <div style="font-size:15px;font-weight:500;color:#64748b;">Записей в журнале не найдено</div>
            <div style="font-size:13px;margin-top:4px;">Попробуйте изменить параметры фильтрации или строку поиска.</div>
        </td>
    </tr>
    '''

    nav = _admin_nav_bar('audit', role=current_role, username=current_username)

    return f'''
    {nav}
    {msg_html}
    {err_html}

    <div style="margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
            <h1 style="margin:0 0 4px;font-size:24px;display:flex;align-items:center;gap:10px;color:#0f172a;">
                {icon('activity', 24, '#2563eb')} Журнал аудита действий пользователей
            </h1>
            <p style="margin:0;color:#64748b;font-size:14px;">
                Полный реестр событий информационной безопасности, входов в систему и операций с базой
            </p>
        </div>
        <div style="display:flex;gap:8px;">
            <a href="/admin/audit" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:6px;" title="Обновить журнал">
                {icon('refresh', 14, '#475569')} Обновить
            </a>
        </div>
    </div>

    <!-- Статистические карточки -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:16px;margin-bottom:20px;">
        <div class="card" style="display:flex;align-items:center;gap:16px;padding:16px 20px;">
            <div style="width:48px;height:48px;border-radius:12px;background:#eff6ff;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                {icon('activity', 24, '#2563eb')}
            </div>
            <div>
                <div style="font-size:22px;font-weight:700;color:#0f172a;">{stats.get('total', 0)}</div>
                <div style="font-size:13px;color:#64748b;">Всего событий в базе</div>
            </div>
        </div>

        <div class="card" style="display:flex;align-items:center;gap:16px;padding:16px 20px;">
            <div style="width:48px;height:48px;border-radius:12px;background:#dcfce7;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                {icon('check_circle', 24, '#16a34a')}
            </div>
            <div>
                <div style="font-size:22px;font-weight:700;color:#0f172a;">{stats.get('logins', 0)}</div>
                <div style="font-size:13px;color:#64748b;">Успешных авторизаций</div>
            </div>
        </div>

        <div class="card" style="display:flex;align-items:center;gap:16px;padding:16px 20px;">
            <div style="width:48px;height:48px;border-radius:12px;background:#fee2e2;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                {icon('alert_triangle', 24, '#dc2626')}
            </div>
            <div>
                <div style="font-size:22px;font-weight:700;color:#0f172a;">{stats.get('failed_logins', 0)}</div>
                <div style="font-size:13px;color:#64748b;">Неудачных попыток входа</div>
            </div>
        </div>

        <div class="card" style="display:flex;align-items:center;gap:16px;padding:16px 20px;">
            <div style="width:48px;height:48px;border-radius:12px;background:#f3e8ff;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                {icon('upload', 24, '#7c3aed')}
            </div>
            <div>
                <div style="font-size:22px;font-weight:700;color:#0f172a;">{stats.get('uploads', 0)}</div>
                <div style="font-size:13px;color:#64748b;">Загрузок пачек квитанций</div>
            </div>
        </div>
    </div>

    <!-- Панель фильтров -->
    <div class="card" style="margin-bottom:20px;padding:16px 20px;">
        <form action="/admin/audit" method="get" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)) 120px auto;gap:12px;align-items:end;">
            <div>
                <label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#475569;">Поиск по деталям или IP</label>
                <input type="text" name="search" value="{html.escape(search_query)}" placeholder="Поиск в описании..." style="width:100%;padding:8px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13px;">
            </div>

            <div>
                <label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#475569;">Пользователь</label>
                <select name="user" style="width:100%;padding:8px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13px;">
                    {''.join(user_options)}
                </select>
            </div>

            <div>
                <label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#475569;">Тип события</label>
                <select name="action" style="width:100%;padding:8px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13px;">
                    {''.join(action_options)}
                </select>
            </div>

            <div>
                <label style="display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#475569;">Количество</label>
                <select name="limit" style="width:100%;padding:8px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:13px;">
                    {''.join(limit_options)}
                </select>
            </div>

            <div style="display:flex;gap:8px;">
                <button type="submit" class="btn btn-green" style="padding:8px 16px;display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:13px;">
                    {icon('search', 14, '#fff')} Найти
                </button>
                <a href="/admin/audit" class="btn btn-outline" style="padding:8px 12px;display:inline-flex;align-items:center;gap:4px;font-size:13px;" title="Сбросить фильтры">
                    {icon('x', 14, '#64748b')}
                </a>
            </div>
        </form>
    </div>

    <!-- Основная таблица журнала -->
    <div class="card" style="padding:0;overflow:hidden;">
        <div style="padding:16px 20px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;background:#f8fafc;">
            <div style="font-size:14px;font-weight:600;color:#334155;">
                Отображено записей: <span style="color:#2563eb;">{len(logs)}</span>
            </div>
            <div style="font-size:12px;color:#64748b;">
                Автоматическая фиксация событий безопасности
            </div>
        </div>

        <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;text-align:left;">
                <thead>
                    <tr style="background:#f1f5f9;border-bottom:2px solid #cbd5e1;font-size:12px;color:#475569;">
                        <th style="padding:10px 14px;width:60px;">ID</th>
                        <th style="padding:10px 14px;width:160px;">Время события</th>
                        <th style="padding:10px 14px;width:150px;">Пользователь</th>
                        <th style="padding:10px 14px;width:130px;">IP-адрес</th>
                        <th style="padding:10px 14px;width:190px;">Действие</th>
                        <th style="padding:10px 14px;">Детали и описание</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_html) if rows_html else empty_row}
                </tbody>
            </table>
        </div>
    </div>
    '''



def time_format(ts: Optional[float]) -> str:
    """Форматирует timestamp в читаемую строку."""
    if not ts:
        return '—'
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return '—'


def time_format_detailed(ts: Optional[float]) -> str:
    """Форматирует timestamp в детальную строку с секундами."""
    if not ts:
        return '—'
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except Exception:
        return '—'
