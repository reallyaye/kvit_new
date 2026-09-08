# -*- coding: utf-8 -*-
"""
Тесты соответствия законодательству о персональных данных (РК № 94-V),
АППК РК, блокировки Метрики до согласия и минимизации данных.
"""

import time

from database.connection import get_db
from services.analytics.stats_service import stats_service
from services.appeals.appeal_service import appeal_service
from templates.appeals_views import render_appeals_page
from templates.portal_layout import portal_layout
from templates.privacy_views import render_privacy_page
from templates.search_views import render_search_form
from templates.terms_views import render_terms_page


def test_schema_and_cookie_consent_in_portal_layout():
    html = portal_layout("<h1>Тестовая страница</h1>", current_slug="home")
    # 1. Schema.org
    assert '"@type": "Organization"' in html
    assert '"GovernmentService"' not in html
    assert '"taxID": "031140001297"' in html
    assert '"leiCode"' not in html

    # 2. Яндекс.Метрика не запускается безусловно в теле страницы
    assert '<script type="text/javascript" >\n    (function (d, w, c) {\n        (w[c] = w[c] || []).push' not in html

    # 3. Присутствует Cookie Consent Banner и Modal
    assert 'id="krecCookieBanner"' in html
    assert 'id="krecCookieModal"' in html
    assert 'krecAcceptAllCookies()' in html
    assert 'krecRejectCookies()' in html
    assert 'krecOpenCookieModal()' in html

    # 4. В подвале присутствуют БИН, адрес, dpo и ссылки на документы
    assert 'БИН: <strong>031140001297</strong>' in html
    assert 'dpo@krec.kz' in html
    assert '/privacy' in html
    assert '/terms' in html


def test_sensitive_pages_shield_in_portal_layout():
    html_search = portal_layout("<div>Поиск</div>", current_slug="search")
    assert "currentSlug = 'search'" in html_search
    assert "webvisor: enableWebvisor && !isSensitive" in html_search


def test_search_inputs_protected():
    form_html = render_search_form([])
    assert 'name="account" class="ym-disable-keys"' in form_html
    assert 'autocomplete="off"' in form_html


def test_stats_service_salt_rotation_and_ua_minimization():
    # Проверка ежемесячной соли: май vs июнь дают разные хеши для одного IP
    ts_may = 1715000000.0   # May 2024
    ts_june = 1718000000.0  # June 2024
    h_may = stats_service._hash_ip("192.168.1.100", ts_may)
    h_june = stats_service._hash_ip("192.168.1.100", ts_june)
    assert h_may != h_june, "IP hash должен изменяться с ежемесячной солью"

    # Запись визита: сырой User-Agent НЕ должен сохраняться в БД
    stats_service.record_visit("/privacy", "192.168.1.100", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    con = get_db()
    try:
        row = con.execute("SELECT ip_hash, user_agent, device_type, browser FROM page_visits WHERE path = '/privacy' ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None
        assert row['user_agent'] is None, "Сырой User-Agent не должен сохраняться в БД"
        assert row['device_type'] == 'desktop'
        assert row['browser'] in ('Chrome', 'Other', 'Firefox', 'Edge')
    finally:
        con.close()

    # Очистка старых визитов
    deleted = stats_service.purge_old_visits(days=90)
    assert isinstance(deleted, int)


def test_appeals_consent_version_and_ip_anonymization():
    payload = {
        'category': 'billing',
        'applicant_name': 'Тестовый Заявитель',
        'phone': '+7 (701) 999-88-77',
        'email': 'applicant@example.kz',
        'service_address': 'г. Караганда, пр. Бухар Жырау, 15',
        'message': 'Прошу предоставить расшифровку начислений за текущий период.',
        'consent': '1',
    }
    created = appeal_service.create(payload, client_ip="192.168.5.5", user_agent="Mozilla/5.0 (Android; Mobile)")
    assert created['consent_version'] == 'v1.0-2026-kz'
    # IP в БД не должен быть сырым "192.168.5.5"
    assert created['client_ip'] != "192.168.5.5"
    assert len(created['client_ip']) == 16

    # Форма обращений
    page_html = render_appeals_page()
    assert 'Электронная приёмная обращений потребителей' in page_html
    assert 'До 15 рабочих дней' in page_html
    assert 'name="consent_version" value="v1.0-2026-kz"' in page_html
    assert 'ym-disable-keys' in page_html
    assert '031140001297' in page_html

    # Очистка старых обращений
    purged = appeal_service.purge_expired_appeals(retention_days=1095)
    assert isinstance(purged, int)


def test_privacy_and_terms_pages():
    privacy_html = render_privacy_page()
    assert 'Политика сбора, обработки и защиты персональных данных' in privacy_html
    assert '031140001297' in privacy_html
    assert 'Законом Республики Казахстан от 21 мая 2013 года № 94-V' in privacy_html
    assert 'dpo@krec.kz' in privacy_html
    assert '8 сентября 2026 года' in privacy_html

    terms_html = render_terms_page()
    assert 'Условия использования веб-портала krec.kz' in terms_html
    assert '031140001297' in terms_html
    assert 'не является интернет-магазином' in terms_html


def test_font_localization():
    with open('static/css/style.css', 'r', encoding='utf-8') as f:
        style_css = f.read()
    assert 'fonts.googleapis.com' not in style_css
    assert 'fonts.gstatic.com' not in style_css
    assert '/css/inter.css' in style_css

    with open('static/css/heroui.css', 'r', encoding='utf-8') as f:
        heroui_css = f.read()
    assert 'fonts.googleapis.com' not in heroui_css
    assert 'fonts.gstatic.com' not in heroui_css
    assert '/css/inter.css' in heroui_css


def test_kvit_layout_unification():
    from templates.layout import layout
    html = layout('<h1>Квитанция</h1>', active='search')
    assert 'krecCookieBanner' in html
    assert 'krecCookieModal' in html
    assert 'krecOpenCookieModal' in html
    assert '031140001297' in html
    assert '/privacy' in html
    assert '/terms' in html
    assert 'purgeTrackingData' in html


def test_deep_anonymization_appeals():
    from database import get_db
    from services.appeals import appeal_service
    payload = {
        'category': 'meter',
        'applicant_name': 'Петров Петр Петрович',
        'phone': '+7 (777) 123-45-67',
        'email': 'petrov@example.kz',
        'account_number': '9876543210',
        'service_address': 'г. Караганда, ул. Ленина, 5, кв. 10',
        'message': 'Заявление на проверку прибора учета электроэнергии.',
        'consent': '1',
    }
    appeal = appeal_service.create(payload, client_ip="10.0.0.1")
    appeal_id = appeal['id']

    # Имитируем возраст обращения более 3 лет (например, 1150 дней назад)
    old_timestamp = time.time() - (1150 * 86400)
    with get_db() as db:
        db.execute(
            "UPDATE appeals SET submitted_at = ?, admin_comment = ?, assigned_to = ? WHERE id = ?",
            (old_timestamp, "Служебный комментарий инженера", "engineer_ivanov", appeal_id)
        )
        db.commit()

    # Запуск очистки
    purged_count = appeal_service.purge_expired_appeals(retention_days=1095)
    assert purged_count >= 1

    # Проверка глубокого обезличивания
    anonymized = appeal_service.get_by_id(appeal_id)
    assert anonymized is not None
    assert 'Обезличено' in anonymized['applicant_name']
    assert anonymized['phone'] == 'Обезличено'
    assert anonymized['email'] == ''
    assert anonymized['account_number'] is None
    assert anonymized['service_address'] == 'Обезличено'
    assert anonymized['admin_comment'] == 'Обезличено по истечении срока хранения'
    assert anonymized['assigned_to'] is None
    assert anonymized['status'] == 'CLOSED'

