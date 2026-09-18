# -*- coding: utf-8 -*-
from urllib.parse import quote

import config
from services.portal_cms import portal_cms
from services.security import auth_service
from templates import layout, render_forbidden_page


class CmsHandlerMixin:
    """Обработчики мутаций CMS: страницы, медиа-файлы, документы."""

    def _handle_admin_pages_save(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params(max_bytes=config.MAX_CMS_BODY_BYTES)
        if not params:
            return
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        slug = params.get('slug', [''])[0]
        title = params.get('title', [''])[0]
        html_content = params.get('html', [''])[0]
        ok, saved_slug = portal_cms.save_page(slug, title, html_content)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'PAGE_SAVE', f"Сохранена страница '{saved_slug}' ({title})")
            msg = quote('Страница успешно сохранена.')
            self._redirect(f'/admin/pages/edit?slug={saved_slug}&msg={msg}')
        else:
            err = quote('Ошибка сохранения страницы.')
            self._redirect(f'/admin/pages?err={err}')

    def _handle_admin_pages_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        slug = params.get('slug', [''])[0]
        ok, msg = portal_cms.delete_page(slug)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'PAGE_DELETE', f"Удалена страница '{slug}'")
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/pages?{param_name}={quote(msg)}')

    def _handle_admin_media_upload(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        fields, files = self._parse_multipart_fields_and_files()
        csrf_token = fields.get('csrf_token', [''])[0] if fields else ''
        if not self._verify_csrf(csrf_token):
            if 'ajax' in self.path:
                self.send_json({'ok': False, 'error': 'Недействительный CSRF-токен.'}, 403)
            else:
                self.send_html(layout(render_forbidden_page('Недействительный CSRF-токен.'), is_admin=True), 403)
            return

        is_ajax = 'ajax' in self.path
        if not files:
            if is_ajax:
                self.send_json({'ok': False, 'error': 'Файл не выбран.'}, 400)
            else:
                self._redirect('/admin/media?err=' + quote('Файл не выбран.'))
            return

        _, orig_filename, file_bytes = files[0]
        ok, file_info, msg = portal_cms.save_media_file(orig_filename, file_bytes)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'MEDIA_UPLOAD', f"Загружен медиа-файл '{orig_filename}'")
        if is_ajax:
            self.send_json({'ok': ok, 'file': file_info, 'error': '' if ok else msg})
        else:
            param = 'msg' if ok else 'err'
            self._redirect(f'/admin/media?{param}={quote(msg)}')

    def _handle_admin_media_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        filename = params.get('filename', [''])[0]
        ok, msg = portal_cms.delete_media_file(filename)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'MEDIA_DELETE', f"Удален медиа-файл '{filename}'")
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/media?{param_name}={quote(msg)}')

    def _handle_admin_documents_save(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        key = params.get('key', [''])[0]
        title = params.get('title', [''])[0]
        cat = params.get('category', ['other'])[0]
        date_text = params.get('date_text', [''])[0]
        files = [f.strip() for f in params.get('files', [''])[0].split('\n') if f.strip()]
        iframes = [f.strip() for f in params.get('iframes', [''])[0].split('\n') if f.strip()]
        doc_data = {
            'title': title,
            'category': cat,
            'date_text': date_text,
            'files': files,
            'iframes': iframes
        }
        ok, saved_key = portal_cms.save_document(key, doc_data)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'DOCUMENT_SAVE', f"Сохранен документ '{saved_key}' ({title})")
            msg = quote('Документ успешно сохранен.')
            self._redirect(f'/admin/documents?msg={msg}')
        else:
            err = quote('Ошибка сохранения документа.')
            self._redirect(f'/admin/documents?err={err}')

    def _handle_admin_documents_delete(self):
        if not self._is_admin():
            self._redirect('/login')
            return
        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        admin_name = cur_user.get('username', 'admin')

        params = self._read_form_params()
        csrf_token = params.get('csrf_token', [''])[0]
        if not self._verify_csrf(csrf_token):
            self.send_html(layout(render_forbidden_page('Недействительный или отсутствующий CSRF-токен.'), is_admin=True), 403)
            return
        key = params.get('key', [''])[0]
        ok, msg = portal_cms.delete_document(key)
        if ok:
            auth_service.log_audit(admin_name, client_ip, 'DOCUMENT_DELETE', f"Удален документ '{key}'")
        param_name = 'msg' if ok else 'err'
        self._redirect(f'/admin/documents?{param_name}={quote(msg)}')
