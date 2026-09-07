import importlib
import io
import re
from types import MethodType
from urllib.parse import urlencode

import pytest

import config
from database import get_db
from server import AppRequestHandler
from services.appeals import AppealValidationError, appeal_service
from templates.appeals_views import (
    render_admin_appeal_detail,
    render_admin_appeals_list,
    render_appeals_page,
)

VALID_APPEAL = {
    'category': 'billing',
    'applicant_name': 'Иванов Иван Иванович',
    'phone': '+7 (700) 123-45-67',
    'email': 'person@example.kz',
    'account_number': '12345678',
    'service_address': 'г. Караганда, ул. Тестовая, 10',
    'message': 'Прошу проверить корректность начисления за август.',
    'consent': '1',
}


def test_migration_creates_appeals_table():
    con = get_db()
    try:
        columns = {row[1] for row in con.execute('PRAGMA table_info(appeals)').fetchall()}
    finally:
        con.close()
    assert {'registration_number', 'status', 'confirmation_sent'} <= columns


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('category', 'unknown'),
        ('applicant_name', ''),
        ('phone', '123'),
        ('email', 'wrong-address'),
        ('service_address', 'x'),
        ('message', 'коротко'),
        ('consent', ''),
    ],
)
def test_validation_rejects_invalid_payload(field, value):
    payload = dict(VALID_APPEAL)
    payload[field] = value
    with pytest.raises(AppealValidationError):
        appeal_service.validate(payload)


def test_create_list_update_and_stats():
    first = appeal_service.create(VALID_APPEAL, '127.0.0.1', 'pytest')
    second_payload = dict(VALID_APPEAL, email='second@example.kz', applicant_name='ТОО Тест')
    second = appeal_service.create(second_payload, '127.0.0.2', 'pytest')

    assert first['id'] != second['id']
    assert re.fullmatch(r'ЭП-\d{8}-[A-Z2-9]{6}', first['registration_number'])
    assert appeal_service.get_by_registration_number(first['registration_number'])['email'] == VALID_APPEAL['email']

    listing = appeal_service.list(status='NEW', search='Иванов')
    assert listing['total'] == 1
    assert listing['items'][0]['id'] == first['id']

    updated = appeal_service.update(first['id'], 'IN_REVIEW', 'Принято в работу', 'admin')
    assert updated['status'] == 'IN_REVIEW'
    assert updated['assigned_to'] == 'admin'
    stats = appeal_service.get_stats()
    assert stats['TOTAL'] == 2
    assert stats['NEW'] == 1
    assert stats['IN_REVIEW'] == 1


def test_update_rejects_missing_or_invalid_appeal():
    with pytest.raises(AppealValidationError):
        appeal_service.update(999, 'NEW')
    with pytest.raises(AppealValidationError):
        appeal_service.update(1, 'INVALID')


def test_notify_sends_office_and_confirmation(monkeypatch):
    appeal = appeal_service.create(VALID_APPEAL)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            assert host == 'smtp.example.kz'
            assert port == 587

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context):
            assert context

        def login(self, username, password):
            assert username == 'mailer'
            assert password == 'secret'

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(config, 'APPEALS_EMAIL_ENABLED', True)
    monkeypatch.setattr(config, 'SMTP_HOST', 'smtp.example.kz')
    monkeypatch.setattr(config, 'SMTP_PORT', 587)
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'mailer')
    monkeypatch.setattr(config, 'SMTP_PASSWORD', 'secret')
    monkeypatch.setattr(config, 'SMTP_FROM_EMAIL', 'no-reply@example.kz')
    monkeypatch.setattr(config, 'APPEALS_NOTIFY_EMAIL', 'office@example.kz')
    monkeypatch.setattr(config, 'SMTP_USE_TLS', True)
    monkeypatch.setattr(config, 'SMTP_USE_SSL', False)
    service_module = importlib.import_module('services.appeals.appeal_service')
    monkeypatch.setattr(service_module.smtplib, 'SMTP', FakeSMTP)

    result = appeal_service.notify(appeal)

    assert result == {'office_notified': True, 'confirmation_sent': True}
    assert len(sent) == 2
    stored = appeal_service.get_by_id(appeal['id'])
    assert stored['office_notified'] == 1
    assert stored['confirmation_sent'] == 1


def _make_handler(payload, origin='https://krec.kz'):
    body = urlencode(payload).encode()
    handler = object.__new__(AppRequestHandler)
    handler.path = '/api/appeals'
    handler.headers = {
        'Content-Length': str(len(body)),
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'Host': 'krec.kz',
        'Origin': origin,
        'User-Agent': 'pytest',
    }
    handler.rfile = io.BytesIO(body)
    handler.responses = []
    handler.send_json = MethodType(
        lambda self, data, status=200, extra_headers=None: self.responses.append((status, data, extra_headers)),
        handler,
    )
    handler._get_client_ip = MethodType(lambda self: '127.0.0.1', handler)
    return handler


def test_submit_handler_persists_and_returns_real_number(monkeypatch):
    monkeypatch.setattr(config, 'APPEALS_EMAIL_ENABLED', False)
    handler = _make_handler(VALID_APPEAL)

    handler._handle_appeal_submit()

    status, response, _ = handler.responses[-1]
    assert status == 201
    assert response['success'] is True
    stored = appeal_service.get_by_registration_number(response['registration_number'])
    assert stored['applicant_name'] == VALID_APPEAL['applicant_name']


def test_submit_succeeds_when_email_is_unavailable(monkeypatch):
    handler = _make_handler(VALID_APPEAL)
    monkeypatch.setattr(appeal_service, 'notify', lambda appeal: (_ for _ in ()).throw(RuntimeError('SMTP down')))

    handler._handle_appeal_submit()

    status, response, _ = handler.responses[-1]
    assert status == 201
    assert response['confirmation_sent'] is False
    assert appeal_service.get_by_registration_number(response['registration_number']) is not None


def test_submit_handler_blocks_cross_origin_and_honeypot():
    cross_origin = _make_handler(VALID_APPEAL, origin='https://evil.example')
    cross_origin._handle_appeal_submit()
    assert cross_origin.responses[-1][0] == 403

    spam = _make_handler({**VALID_APPEAL, 'website': 'spam.example'})
    spam._handle_appeal_submit()
    assert spam.responses[-1][0] == 400


def test_public_and_admin_templates_escape_content():
    public_html = render_appeals_page()
    assert 'action="/api/appeals"' in public_html
    assert 'fetch(form.action' in public_html
    assert 'Math.random' not in public_html
    assert 'setTimeout' not in public_html

    appeal = appeal_service.create({**VALID_APPEAL, 'applicant_name': '<script>alert(1)</script>'})
    listing = appeal_service.list()
    list_html = render_admin_appeals_list(listing, appeal_service.get_stats(), {}, 'csrf')
    detail_html = render_admin_appeal_detail(appeal, 'csrf')
    assert '<script>alert(1)</script>' not in list_html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in list_html
    assert '<script>alert(1)</script>' not in detail_html
