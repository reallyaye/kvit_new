# -*- coding: utf-8 -*-
import html

from templates.icons import icon


def _admin_nav_bar(active_tab: str = 'pages', role: str = 'admin', username: str = 'admin') -> str:
    """Современная премиальная навигационная панель админ-зоны с поддержкой RBAC ролей."""
    if role == 'operator':
        tabs = [
            ('upload', '/upload', 'upload', 'Загрузка квитанций'),
            ('reconcile', '/reconcile', 'reconcile', 'Сверка базы'),
        ]
        badge_title = "Отдел сбыта"
        badge_sub = f"Оператор: {html.escape(username)}"
    elif role == 'assistant':
        tabs = [
            ('appeals', '/admin/appeals', 'bell', 'Обращения'),
        ]
        badge_title = "Канцелярия / Приёмная"
        badge_sub = f"Помощник: {html.escape(username)}"
    else:
        tabs = [
            ('stats', '/admin/stats', 'trending_up', 'Посещаемость'),
            ('appeals', '/admin/appeals', 'bell', 'Обращения'),
            ('pages', '/admin/pages', 'file_text', 'Страницы сайта'),
            ('media', '/admin/media', 'image', 'Медиа и файлы'),
            ('documents', '/admin/documents', 'files', 'Реестр документов'),
            ('users', '/admin/users', 'users', 'Сотрудники'),
            ('audit', '/admin/audit', 'activity', 'Журнал действий'),
            ('upload', '/upload', 'upload', 'Загрузка квитанций'),
            ('reconcile', '/reconcile', 'reconcile', 'Сверка базы'),
        ]
        badge_title = "ТОО «КРЭК»"
        badge_sub = f"Администратор ({html.escape(username)})"

    links_html = []
    for key, href, ic, label in tabs:
        active_cls = ' active' if key == active_tab else ''
        ic_color = '#ffffff' if key == active_tab else '#64748b'
        links_html.append(f'''<a href="{href}" class="admin-tab-item{active_cls}">
            {icon(ic, 15, ic_color)} <span>{label}</span>
        </a>''')

    return f'''
    <div class="admin-top-nav-card">
        <div class="admin-brand-badge">
            <div class="admin-brand-icon">
                {icon('shield', 18, '#ffffff')}
            </div>
            <div class="admin-brand-text">
                <span class="admin-brand-title">{badge_title}</span>
                <span class="admin-brand-sub">{badge_sub}</span>
            </div>
        </div>
        <nav class="admin-tabs-list">
            {''.join(links_html)}
        </nav>
        <div class="admin-nav-actions">
            <a href="/" target="_blank" class="admin-btn-portal" title="Открыть сайт в новой вкладке">
                {icon('external_link', 14, '#2563eb')} <span>На сайт</span>
            </a>
            <a href="/logout" class="admin-btn-logout" title="Завершить сеанс">
                {icon('logout', 14, '#e11d48')} <span>Выйти</span>
            </a>
        </div>
    </div>
    '''
