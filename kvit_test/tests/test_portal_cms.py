# -*- coding: utf-8 -*-
import io
import os
import tempfile
import urllib.parse
from unittest import mock

import config
from services.portal_cms import portal_cms
from services.security import auth_service
from templates.portal_views import render_page, render_document


def test_portal_cms_list_and_get_pages():
    pages = portal_cms.get_all_pages()
    assert len(pages) > 0
    slugs = [p['slug'] for p in pages]
    assert 'home' in slugs
    assert 'tarif' in slugs
    assert 'consumers' in slugs
    assert 'zakup' in slugs

    home_page = portal_cms.get_page('home')
    assert home_page is not None
    assert home_page['slug'] == 'home'
    assert 'html' in home_page


def test_portal_cms_save_and_delete_page():
    test_slug = 'test-cms-temp-page'
    test_title = 'Тестовая страница CMS'
    test_html = '<div class="test">Привет из теста CMS! <img src="/images/uploads/test.png"></div>'

    # 1. Сохранение новой страницы
    ok, saved_slug = portal_cms.save_page(test_slug, test_title, test_html)
    assert ok is True
    assert saved_slug == test_slug

    # 2. Чтение сохраненной страницы
    page = portal_cms.get_page(test_slug)
    assert page is not None
    assert page['title'] == test_title
    assert test_html in page['html']

    # 3. Рендеринг через render_page
    rendered = render_page(test_slug)
    assert test_title in rendered
    assert 'Привет из теста CMS!' in rendered

    # 4. Удаление страницы
    ok, msg = portal_cms.delete_page(test_slug)
    assert ok is True
    assert portal_cms.get_page(test_slug) is None

    # 5. Защита от удаления системных страниц
    ok_home, _ = portal_cms.delete_page('home')
    assert ok_home is False


def test_portal_cms_media_save_and_delete():
    # 1. Сохранение изображения
    img_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
    ok, file_info, msg = portal_cms.save_media_file('sample_test_photo.png', img_content, as_image=True)
    assert ok is True
    assert file_info['type'] == 'image'
    assert '/images/uploads/' in file_info['url']
    saved_fname = file_info['filename']

    # 2. Проверка в списке медиа
    media_list = portal_cms.list_media_files()
    fnames = [m['filename'] for m in media_list]
    assert saved_fname in fnames

    # 3. Удаление медиа-файла
    del_ok, _ = portal_cms.delete_media_file(saved_fname)
    assert del_ok is True
    assert saved_fname not in [m['filename'] for m in portal_cms.list_media_files()]

    # 4. Запрет загрузки опасных исполняемых файлов
    bad_ok, _, err_msg = portal_cms.save_media_file('evil_script.php', b'<?php echo 1; ?>')
    assert bad_ok is False
    assert 'запрещена' in err_msg


def test_portal_cms_documents_lifecycle():
    doc_key = 'test-report-2026.php'
    doc_data = {
        'title': 'Тестовый отчет инвестпрограммы 2026',
        'category': 'invest',
        'date_text': 'Дата: 01.01.2026 г.',
        'files': ['/files/test_report.pdf'],
        'iframes': []
    }

    # 1. Сохранение документа
    ok, saved_key = portal_cms.save_document(doc_key, doc_data)
    assert ok is True
    assert saved_key == doc_key

    # 2. Получение документа
    doc = portal_cms.get_document(doc_key)
    assert doc is not None
    assert doc['title'] == doc_data['title']
    assert '/files/test_report.pdf' in doc['files']

    # 3. Рендеринг документа
    rendered = render_document(doc)
    assert 'Тестовый отчет' in rendered
    assert 'test_report.pdf' in rendered

    # 4. Удаление документа
    del_ok, _ = portal_cms.delete_document(doc_key)
    assert del_ok is True
    assert portal_cms.get_document(doc_key) is None


def test_admin_bar_rendering():
    # 1. Для неавторизованного пользователя admin-bar отсутствует
    html_anon = render_page('tarif', is_admin=False)
    assert 'portal-admin-bar' not in html_anon
    assert 'Редактировать эту страницу' not in html_anon

    # 2. Для авторизованного администратора admin-bar отображается
    html_admin = render_page('tarif', is_admin=True)
    assert 'portal-admin-bar' in html_admin
    assert 'Редактировать эту страницу' in html_admin
    assert '/admin/pages/edit?slug=tarif' in html_admin


def test_admin_cms_security_access():
    """Тестирует защиту административных маршрутов CMS."""
    from server import AppRequestHandler
    handler = AppRequestHandler.__new__(AppRequestHandler)
    captured = {}

    def mock_send_html(content, code=200, extra_headers=None):
        captured['html'] = content
        captured['code'] = code

    def mock_redirect(location, extra_headers=None):
        captured['redirect'] = location

    def mock_send_json(data, code=200, extra_headers=None):
        captured['json'] = data
        captured['code'] = code

    handler.send_html = mock_send_html
    handler._redirect = mock_redirect
    handler.send_json = mock_send_json

    # 1. Неавторизованный доступ к /admin/pages -> 302 редирект на /login
    handler._is_admin = lambda: False
    handler._get_session_token = lambda: None
    handler.path = '/admin/pages'
    handler._get_client_ip = lambda: '127.0.0.1'
    handler.headers = {}

    handler.do_GET()
    assert captured.get('redirect') == '/login'

    # 2. Авторизованный доступ к /admin/pages -> 200 OK HTML
    captured.clear()
    handler._is_admin = lambda: True
    token = 'test_session_token'
    handler._get_session_token = lambda: token
    handler.headers = {}
    with mock.patch.object(auth_service, 'get_csrf_token', return_value='csrf_123'):
        handler.do_GET()
        assert captured.get('code') == 200
        assert 'Управление страницами' in captured.get('html', '')
