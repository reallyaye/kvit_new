# -*- coding: utf-8 -*-
"""
Модуль представления админ-панели CMS.
Декомпозирован на специализированные модули:
  - templates.admin_nav: навигационная панель
  - templates.admin_pages_views: страницы сайта
  - templates.admin_media_views: медиатека и файлы
  - templates.admin_documents_views: реестр документов
  - templates.admin_users_views: сотрудники и права доступа
  - templates.admin_audit_views: журнал действий и аудит
"""

from templates.admin_audit_views import (
    _format_audit_action_badge,
    render_admin_audit_log,
    time_format,
    time_format_detailed,
)
from templates.admin_documents_views import render_admin_document_editor, render_admin_documents_list
from templates.admin_media_views import render_admin_media_gallery
from templates.admin_nav import _admin_nav_bar
from templates.admin_pages_views import render_admin_page_editor, render_admin_pages_list
from templates.admin_users_views import render_access_denied_page, render_admin_users

__all__ = [
    '_admin_nav_bar',
    'render_admin_pages_list',
    'render_admin_page_editor',
    'render_admin_media_gallery',
    'render_admin_documents_list',
    'render_admin_document_editor',
    'render_admin_users',
    'render_access_denied_page',
    '_format_audit_action_badge',
    'render_admin_audit_log',
    'time_format',
    'time_format_detailed',
]
