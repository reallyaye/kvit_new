# -*- coding: utf-8 -*-
import html
from typing import Any, Dict, List, Optional

from templates.admin_audit_views import time_format
from templates.admin_nav import _admin_nav_bar
from templates.icons import icon


def render_admin_users(
    users: List[Dict[str, Any]],
    logs: List[Dict[str, Any]],
    csrf_token: str,
    message: Optional[str] = None,
    error: Optional[str] = None,
    current_username: str = 'admin',
    current_role: str = 'admin'
) -> str:
    """Рендерит страницу управления учетными записями операторов и журнал аудита."""
    msg_html = f'<div class="ok" style="margin-bottom:16px">{html.escape(message)}</div>' if message else ''
    err_html = f'<div class="err" style="margin-bottom:16px">{html.escape(error)}</div>' if error else ''

    user_rows = []
    for u in users:
        u_name = html.escape(u.get('username', ''))
        u_fname = html.escape(u.get('full_name', ''))
        u_role = u.get('role', 'operator')
        u_active = u.get('is_active', True)
        u_last = time_format(u.get('last_login_at')) if u.get('last_login_at') else 'Никогда'

        if u_role == 'admin':
            role_badge = f'<span class="status-badge" style="background:#e0e7ff;color:#3730a3;display:inline-flex;align-items:center;gap:4px">{icon("shield", 13, "#4f46e5")} Администратор</span>'
        elif u_role == 'assistant':
            role_badge = f'<span class="status-badge" style="background:#fef3c7;color:#92400e;display:inline-flex;align-items:center;gap:4px">{icon("file_text", 13, "#d97706")} Административный помощник</span>'
        else:
            role_badge = f'<span class="status-badge" style="background:#dcfce7;color:#166534;display:inline-flex;align-items:center;gap:4px">{icon("user", 13, "#16a34a")} Оператор сбыта</span>'
        status_badge = '<span style="color:#16a34a;font-weight:600">● Активен</span>' if u_active else '<span style="color:#dc2626;font-weight:600">● Заблокирован</span>'

        delete_btn = ''
        if u_name.lower() != 'admin' and u_name != current_username:
            delete_btn = f'''
            <form action="/admin/users/delete" method="post" style="display:inline;" onsubmit="return confirm('Удалить пользователя {u_name}?');">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <input type="hidden" name="username" value="{u_name}">
                <button type="submit" class="btn btn-sm btn-danger" style="display:inline-flex;align-items:center;gap:4px;padding:6px 12px;font-size:12px">
                    {icon('trash', 13, '#fff')} Удалить
                </button>
            </form>
            '''

        user_rows.append(f'''
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:12px 16px;font-weight:600;color:#0f172a;">{u_name}</td>
            <td style="padding:12px 16px;color:#334155;">{u_fname}</td>
            <td style="padding:12px 16px;">{role_badge}</td>
            <td style="padding:12px 16px;">{status_badge}</td>
            <td style="padding:12px 16px;color:#64748b;font-size:13px;">{u_last}</td>
            <td style="padding:12px 16px;text-align:right;">
                {delete_btn}
            </td>
        </tr>
        ''')

    log_rows = []
    for log_item in logs:
        l_time = time_format(log_item.get('created_at'))
        l_user = html.escape(log_item.get('username', ''))
        l_ip = html.escape(log_item.get('ip', ''))
        l_action = html.escape(log_item.get('action', ''))
        l_details = html.escape(log_item.get('details', ''))

        log_rows.append(f'''
        <tr style="border-bottom:1px solid #f1f5f9;font-size:13px;">
            <td style="padding:8px 12px;color:#64748b;">{l_time}</td>
            <td style="padding:8px 12px;font-weight:600;color:#0f172a;">{l_user}</td>
            <td style="padding:8px 12px;color:#475569;"><code>{l_ip}</code></td>
            <td style="padding:8px 12px;font-weight:600;color:#2563eb;">{l_action}</td>
            <td style="padding:8px 12px;color:#334155;">{l_details}</td>
        </tr>
        ''')

    return f'''
    {_admin_nav_bar('users', role=current_role, username=current_username)}

    <div style="display:grid;grid-template-columns:1fr 340px;gap:24px;margin-top:20px;align-items:start;">
        <!-- Левая колонка: Список пользователей и Аудит -->
        <div>
            <div class="card" style="margin-bottom:24px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                    <div>
                        <h2 style="margin:0;font-size:18px;">Учётные записи сотрудников</h2>
                        <p style="margin:4px 0 0;color:#64748b;font-size:13px;">Разделение прав доступа: сотрудники сбыта имеют доступ только к загрузке и сверке</p>
                    </div>
                </div>
                {msg_html}
                {err_html}
                <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;text-align:left;">
                        <thead>
                            <tr style="background:#f8fafc;border-bottom:2px solid #cbd5e1;font-size:13px;color:#475569;">
                                <th style="padding:10px 16px;">Логин</th>
                                <th style="padding:10px 16px;">ФИО / Отдел</th>
                                <th style="padding:10px 16px;">Роль</th>
                                <th style="padding:10px 16px;">Статус</th>
                                <th style="padding:10px 16px;">Последний вход</th>
                                <th style="padding:10px 16px;text-align:right;">Действия</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(user_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Журнал действий (Audit Log) -->
            <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
                    <div>
                        <h2 style="margin:0;font-size:18px;display:flex;align-items:center;gap:8px;">
                            {icon('activity', 18, '#2563eb')} Журнал аудита действий (Audit Log)
                        </h2>
                        <p style="margin:4px 0 0;color:#64748b;font-size:13px;">Фиксация входов, загрузок реестров и изменений для информационной безопасности</p>
                    </div>
                    <a href="/admin/audit" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:6px;">
                        {icon('activity', 14, '#2563eb')} Открыть полный журнал
                    </a>
                </div>
                <div style="overflow-x:auto;max-height:380px;overflow-y:auto;">
                    <table style="width:100%;border-collapse:collapse;text-align:left;">
                        <thead>
                            <tr style="background:#f8fafc;border-bottom:2px solid #cbd5e1;font-size:12px;color:#475569;position:sticky;top:0;">
                                <th style="padding:8px 12px;">Время</th>
                                <th style="padding:8px 12px;">Пользователь</th>
                                <th style="padding:8px 12px;">IP</th>
                                <th style="padding:8px 12px;">Действие</th>
                                <th style="padding:8px 12px;">Детали</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(log_rows) if log_rows else '<tr><td colspan="5" style="padding:16px;text-align:center;color:#94a3b8">Записей пока нет</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Правая колонка: Создание нового пользователя -->
        <div class="card" style="position:sticky;top:20px;">
            <h2 style="margin:0 0 16px;font-size:18px;display:flex;align-items:center;gap:8px">
                {icon('user_plus', 18, '#16a34a')} Добавить сотрудника
            </h2>
            <form action="/admin/users/create" method="post">
                <input type="hidden" name="csrf_token" value="{csrf_token}">

                <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:600;color:#334155;">Логин (английские буквы)</label>
                <input type="text" name="username" placeholder="Например: sbyt_operator1" required style="width:100%;margin-bottom:14px;padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;">

                <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:600;color:#334155;">Пароль (не менее 6 символов)</label>
                <input type="password" name="password" placeholder="••••••••" required style="width:100%;margin-bottom:14px;padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;">

                <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:600;color:#334155;">ФИО сотрудника / Примечание</label>
                <input type="text" name="full_name" placeholder="Иванова А. (Отдел сбыта)" style="width:100%;margin-bottom:14px;padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;">

                <label style="display:block;margin-bottom:6px;font-size:13px;font-weight:600;color:#334155;">Роль в системе</label>
                <select name="role" style="width:100%;margin-bottom:18px;padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;">
                    <option value="operator" selected>Оператор сбыта (только загрузка и сверка)</option>
                    <option value="assistant">Административный помощник (доступ к реестру обращений)</option>
                    <option value="admin">Администратор (полный доступ к сайту)</option>
                </select>

                <button type="submit" class="btn btn-green" style="width:100%;display:flex;align-items:center;justify-content:center;gap:6px;padding:10px;font-weight:600;">
                    {icon('plus', 15, '#fff')} Создать аккаунт
                </button>
            </form>
        </div>
    </div>
    '''



def render_access_denied_page(role: str = 'operator', username: str = 'user') -> str:
    """Рендерит страницу 403 Доступ ограничен для сотрудников с ограниченными ролями."""
    if role == 'assistant':
        active_tab = 'appeals'
        role_label = 'Административный помощник'
        desc_text = 'У вашей учетной записи нет прав на управление страницами, файлами и настройками портала.<br>Вам доступна работа с реестром обращений граждан.'
        buttons = f'''
        <a href="/admin/appeals" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px">
            {icon('bell', 15)} Перейти к обращениям
        </a>
        '''
    else:
        active_tab = 'upload'
        role_label = 'Оператор отдела сбыта'
        desc_text = 'У вашей учетной записи нет прав на управление страницами и настройками портала.<br>Вам доступна загрузка квитанций и сверка реестров.'
        buttons = f'''
        <a href="/upload" class="btn btn-green" style="display:inline-flex;align-items:center;gap:6px">
            {icon('upload', 15)} Перейти к загрузке квитанций
        </a>
        <a href="/reconcile" class="btn btn-outline" style="display:inline-flex;align-items:center;gap:6px">
            {icon('reconcile', 15)} Сверка базы
        </a>
        '''

    return f'''
    {_admin_nav_bar(active_tab, role=role, username=username)}
    <div class="card" style="max-width:600px;margin:40px auto;text-align:center;padding:40px 32px">
        <div style="width:64px;height:64px;background:#fee2e2;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;">
            {icon('shield_alert', 32, '#dc2626')}
        </div>
        <h1 style="color:#0f172a;font-size:24px;margin-bottom:8px">Доступ ограничен</h1>
        <p style="color:#64748b;line-height:1.6;margin-bottom:24px">
            У вашей учетной записи (роль: <b>{html.escape(role_label)}</b>) {desc_text}
        </p>
        <div style="display:flex;gap:12px;justify-content:center">
            {buttons}
        </div>
    </div>
    '''


