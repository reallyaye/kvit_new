# -*- coding: utf-8 -*-
import logging

from config import PROTECTED_PATHS
from services.analytics import stats_service
from services.appeals import appeal_service
from services.metrics import alert_service
from services.portal_cms import portal_cms
from services.reconciliation import reconcile_service
from services.security import auth_service
from templates import (
    layout,
    render_404_page,
    render_reconcile_page,
    render_upload_form,
)
from templates.admin_cms_views import (
    render_access_denied_page,
    render_admin_audit_log,
    render_admin_document_editor,
    render_admin_documents_list,
    render_admin_media_gallery,
    render_admin_page_editor,
    render_admin_pages_list,
    render_admin_users,
)
from templates.admin_stats_views import render_admin_stats_dashboard
from templates.appeals_views import (
    render_admin_appeal_detail,
    render_admin_appeals_list,
)

logger = logging.getLogger('kvit.server')


class AdminGetHandlerMixin:
    """Обработчик защищенных GET-маршрутов панели управления (Admin CMS, Новости, Пользователи, Сверка)."""

    def _handle_get_admin(self, path: str, q: dict, is_admin: bool, client_ip: str) -> bool:
        if path not in PROTECTED_PATHS and not path.startswith('/admin'):
            return False

        cur_user = self._get_current_user()
        if not cur_user and self._is_admin():
            cur_user = {'username': 'admin', 'role': 'admin'}
        if not cur_user:
            self._redirect('/login')
            return True

        u_role = cur_user.get('role', 'operator')
        u_name = cur_user.get('username', 'user')
        session_token = self._get_session_token()
        csrf_tok = auth_service.get_csrf_token(session_token)
        msg = q.get('msg', [None])[0]
        err = q.get('err', [None])[0]

        if u_role == 'operator':
            if path == '/upload':
                body = render_upload_form(csrf_token=csrf_tok, role='operator', username=u_name)
                self.send_html(layout(body, 'upload', is_admin=False, csrf_token=csrf_tok))
                return True
            elif path == '/reconcile':
                filt = q.get('filter', ['without'])[0]
                if filt not in ('all', 'with', 'without', 'orphans'):
                    filt = 'without'
                period_filter = q.get('period', [''])[0].strip()
                account_query = q.get('account', [''])[0].strip()
                try:
                    page_num = max(1, int(q.get('page', ['1'])[0]))
                except (ValueError, TypeError):
                    page_num = 1
                data = reconcile_service.get_reconciliation_data(
                    filt, period_filter, page_num, account_query=account_query
                )
                data['role'] = 'operator'
                data['username'] = u_name
                body = render_reconcile_page(data)
                self.send_html(layout(body, 'reconcile', is_admin=False, csrf_token=csrf_tok))
                return True
            else:
                body = render_access_denied_page(role='operator', username=u_name)
                self.send_html(layout(body, 'forbidden', is_admin=False, csrf_token=csrf_tok), 403)
                return True
        elif u_role == 'assistant':
            if path == '/admin/appeals':
                status_filter = q.get('status', [''])[0].strip().upper()
                search_filter = q.get('search', [''])[0].strip()
                try:
                    page_num = max(1, int(q.get('page', ['1'])[0]))
                except (ValueError, TypeError):
                    page_num = 1
                appeals = appeal_service.list(status_filter, search_filter, page_num)
                stats = appeal_service.get_stats()
                active_alerts = alert_service.evaluate_all()
                body = render_admin_appeals_list(
                    appeals,
                    stats,
                    {'status': status_filter, 'search': search_filter},
                    csrf_tok,
                    message=msg,
                    error=err,
                    username=u_name,
                    alerts_list=active_alerts,
                    role='assistant',
                )
                self.send_html(layout(body, 'appeals', is_admin=False, csrf_token=csrf_tok))
                return True
            elif path == '/admin/appeals/view':
                try:
                    appeal_id = int(q.get('id', ['0'])[0])
                except (ValueError, TypeError):
                    appeal_id = 0
                appeal = appeal_service.get_by_id(appeal_id) if appeal_id > 0 else None
                if not appeal:
                    self.send_html(layout(render_404_page(), is_admin=False), 404)
                    return True
                body = render_admin_appeal_detail(
                    appeal, csrf_tok, message=msg, error=err, username=u_name, role='assistant'
                )
                self.send_html(layout(body, 'appeals', is_admin=False, csrf_token=csrf_tok))
                return True
            else:
                body = render_access_denied_page(role='assistant', username=u_name)
                self.send_html(layout(body, 'forbidden', is_admin=False, csrf_token=csrf_tok), 403)
                return True

        if path in ('/admin', '/admin/pages'):
            pages = portal_cms.get_all_pages()
            body = render_admin_pages_list(pages, csrf_tok, message=msg, error=err)
            self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/users':
            users = auth_service.list_users()
            logs = auth_service.list_audit_logs(50)
            body = render_admin_users(users, logs, csrf_tok, message=msg, error=err, current_username=u_name, current_role='admin')
            self.send_html(layout(body, 'users', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/audit':
            user_filter = q.get('user', [''])[0].strip()
            action_filter = q.get('action', [''])[0].strip()
            search_filter = q.get('search', [''])[0].strip()
            try:
                limit_val = min(500, max(1, int(q.get('limit', ['50'])[0])))
            except (ValueError, TypeError):
                limit_val = 50

            logs = auth_service.list_audit_logs(
                limit=limit_val,
                username=user_filter or None,
                action=action_filter or None,
                search=search_filter or None
            )
            stats = auth_service.get_audit_stats()
            filters_map = {
                'username': user_filter,
                'action': action_filter,
                'search': search_filter,
                'limit': limit_val
            }
            body = render_admin_audit_log(
                logs,
                stats,
                filters_map,
                csrf_tok,
                message=msg,
                error=err,
                current_username=u_name,
                current_role='admin'
            )
            self.send_html(layout(body, 'audit', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/stats':
            stats_data = stats_service.get_dashboard_stats(days=30)
            body = render_admin_stats_dashboard(
                stats_data,
                csrf_token=csrf_tok,
                username=u_name,
                message=msg,
                error=err
            )
            self.send_html(layout(body, 'stats', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/appeals':
            status_filter = q.get('status', [''])[0].strip().upper()
            search_filter = q.get('search', [''])[0].strip()
            try:
                page_num = max(1, int(q.get('page', ['1'])[0]))
            except (ValueError, TypeError):
                page_num = 1
            appeals = appeal_service.list(status_filter, search_filter, page_num)
            stats = appeal_service.get_stats()
            active_alerts = alert_service.evaluate_all()
            body = render_admin_appeals_list(
                appeals,
                stats,
                {'status': status_filter, 'search': search_filter},
                csrf_tok,
                message=msg,
                error=err,
                username=u_name,
                alerts_list=active_alerts,
            )
            self.send_html(layout(body, 'appeals', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/appeals/view':
            try:
                appeal_id = int(q.get('id', ['0'])[0])
            except (ValueError, TypeError):
                appeal_id = 0
            appeal = appeal_service.get_by_id(appeal_id) if appeal_id > 0 else None
            if not appeal:
                self.send_html(layout(render_404_page(), is_admin=True), 404)
                return True
            body = render_admin_appeal_detail(
                appeal, csrf_tok, message=msg, error=err, username=u_name
            )
            self.send_html(layout(body, 'appeals', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/pages/edit':
            slug = q.get('slug', [''])[0]
            page_data = portal_cms.get_page(slug) or {'title': slug, 'html': ''}
            media_files = portal_cms.list_media_files()
            body = render_admin_page_editor(slug, page_data, csrf_tok, media_files, is_new=False, message=msg, error=err)
            self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/pages/new':
            media_files = portal_cms.list_media_files()
            body = render_admin_page_editor('', {'title': '', 'html': ''}, csrf_tok, media_files, is_new=True, message=msg, error=err)
            self.send_html(layout(body, 'pages', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/media':
            media_files = portal_cms.list_media_files()
            body = render_admin_media_gallery(media_files, csrf_tok, message=msg, error=err)
            self.send_html(layout(body, 'media', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/documents':
            docs = portal_cms.get_all_documents()
            body = render_admin_documents_list(docs, csrf_tok, message=msg, error=err)
            self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/documents/edit':
            key = q.get('key', [''])[0]
            doc_data = portal_cms.get_document(key) or {}
            body = render_admin_document_editor(key, doc_data, csrf_tok, is_new=False, message=msg, error=err)
            self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
        elif path == '/admin/documents/new':
            body = render_admin_document_editor('', {}, csrf_tok, is_new=True, message=msg, error=err)
            self.send_html(layout(body, 'documents', is_admin=True, csrf_token=csrf_tok))
        elif path == '/upload':
            body = render_upload_form(csrf_token=csrf_tok, role='admin', username=u_name)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
        elif path == '/reconcile':
            filt = q.get('filter', ['without'])[0]
            if filt not in ('all', 'with', 'without', 'orphans'):
                filt = 'without'
            period_filter = q.get('period', [''])[0].strip()
            account_query = q.get('account', [''])[0].strip()
            try:
                page_num = max(1, int(q.get('page', ['1'])[0]))
            except (ValueError, TypeError):
                page_num = 1
            data = reconcile_service.get_reconciliation_data(
                filt, period_filter, page_num, account_query=account_query
            )
            data['role'] = 'admin'
            data['username'] = u_name
            body = render_reconcile_page(data)
            self.send_html(layout(body, 'reconcile', is_admin=True, csrf_token=csrf_tok))
        return True
