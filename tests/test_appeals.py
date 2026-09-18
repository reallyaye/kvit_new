import importlib
import io
import re
import smtplib
import time
from types import MethodType
from urllib.parse import urlencode

import pytest

import config
from database import get_db, write_transaction
from server import AppRequestHandler
from services.appeals import AppealValidationError, appeal_service
from templates.appeals_views import (
    render_admin_appeal_detail,
    render_admin_appeals_list,
    render_appeal_status_page,
    render_appeals_page,
)

VALID_APPEAL = {
    'category': 'billing', 'applicant_name': 'Иванов Иван Иванович', 'phone': '+7 (700) 123-45-67',
    'email': 'person@example.kz', 'account_number': '12345678', 'service_address': 'г. Караганда, ул. Тестовая, 10',
    'message': 'Прошу проверить корректность начисления за август.', 'consent': '1',
}


def test_migration_creates_appeals_table():
    con = get_db()
    try:
        columns = {row[1] for row in con.execute('PRAGMA table_info(appeals)').fetchall()}
    finally:
        con.close()
    assert {
        'registration_number', 'status', 'confirmation_sent', 'public_token_hash',
        'response_text', 'responded_at', 'response_sent',
    } <= columns


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('category', 'unknown'), ('applicant_name', ''), ('phone', '123'),
        ('email', 'wrong-address'), ('service_address', 'x'), ('message', 'коротко'), ('consent', ''),
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
    assert re.fullmatch(r'[A-Z2-9]{5}-[A-Z2-9]{5}-[A-Z2-9]{5}', first['access_code'])
    assert first['public_token_hash'] != first['access_code']
    assert appeal_service.get_by_registration_number(first['registration_number'])['email'] == VALID_APPEAL['email']

    public = appeal_service.get_public(first['registration_number'], first['access_code'])
    assert public['registration_number'] == first['registration_number']
    assert 'email' not in public
    with pytest.raises(AppealValidationError):
        appeal_service.get_public(first['registration_number'], 'WRONG-CODE')

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

    answered = appeal_service.respond(first['id'], 'Ваши начисления проверены.', 'Готово', 'assistant')
    assert answered['status'] == 'ANSWERED'
    assert answered['response_text'] == 'Ваши начисления проверены.'
    assert appeal_service.get_public(first['registration_number'], first['access_code'])['response_text'] == answered['response_text']


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

    for k, v in [
        ('APPEALS_EMAIL_ENABLED', True), ('SMTP_HOST', 'smtp.example.kz'), ('SMTP_PORT', 587),
        ('SMTP_USERNAME', 'mailer'), ('SMTP_PASSWORD', 'secret'), ('SMTP_FROM_EMAIL', 'no-reply@example.kz'),
        ('APPEALS_NOTIFY_EMAIL', 'office@example.kz'), ('SMTP_USE_TLS', True), ('SMTP_USE_SSL', False),
    ]:
        monkeypatch.setattr(config, k, v)
    service_module = importlib.import_module('services.appeals.appeal_service')
    monkeypatch.setattr(service_module.smtplib, 'SMTP', FakeSMTP)

    result = appeal_service.notify(appeal)

    assert result == {'office_notified': True, 'confirmation_sent': True}
    assert len(sent) == 2
    assert 'https://krec.kz/appeals/status#number=' in sent[1].get_content()
    stored = appeal_service.get_by_id(appeal['id'])
    assert stored['office_notified'] == 1
    assert stored['confirmation_sent'] == 1

    answered = appeal_service.respond(appeal['id'], 'Тестовый ответ заявителю.', assigned_to='assistant')
    assert appeal_service.notify_response(answered) is True
    assert len(sent) == 3
    assert appeal_service.get_by_id(appeal['id'])['response_sent'] == 1
    assert 'обработано' in sent[2].get_content().lower()
    assert 'Тестовый ответ заявителю.' in sent[2].get_content()
    assert 'https://krec.kz/appeals/status#number=' in sent[2].get_content()
    assert '&code=' in sent[2].get_content()
    code_match = re.search(r'&code=([A-Z0-9-]+)', sent[2].get_content())
    assert code_match is not None
    public_res = appeal_service.get_public(answered['registration_number'], code_match.group(1))
    assert public_res['response_text'] == 'Тестовый ответ заявителю.'

    closed = appeal_service.update(
        appeal['id'], 'CLOSED', admin_comment='Вопрос решен', response_text='Заявка выполнена в полном объеме'
    )
    assert appeal_service.notify_response(closed) is True
    assert len(sent) == 4
    assert 'закрыто' in sent[3].get_content().lower()
    assert 'Заявка выполнена в полном объеме' in sent[3].get_content()

    rejected = appeal_service.update(
        appeal['id'], 'REJECTED', response_text='Отклонено: не в зоне обслуживания'
    )
    public_view = appeal_service.get_public(rejected['registration_number'], appeal['access_code'])
    assert public_view['response_text'] == 'Отклонено: не в зоне обслуживания'


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
    assert response['access_code']
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
    assert "link.href=`/appeals/status#${access.toString()}`" in public_html
    assert 'Открыть моё обращение' in public_html
    assert "localStorage.setItem('krec_my_appeals_v1'" in public_html
    assert 'class="krec-btn-cabinet"' not in public_html
    assert '<a href="/appeals/status" class="krec-dropdown-item">' in public_html
    status_html = render_appeal_status_page()
    assert 'action="/api/appeals/status"' in status_html
    assert 'name="credential"' in status_html
    assert 'method="post" hidden aria-hidden="true"' in status_html
    assert 'Найти обращение вручную' not in status_html
    assert 'id="saved-appeals-empty"' in status_html
    assert 'window.location.hash.slice(1)' in status_html
    assert 'form.requestSubmit()' in status_html
    assert 'id="saved-appeals-list"' in status_html
    assert 'localStorage.removeItem(storageKey)' in status_html
    assert "link.addEventListener('click'" in status_html
    assert 'loadAppeal(item.number,item.code)' in status_html
    assert "result.scrollIntoView({block:'nearest'})" in status_html

    appeal = appeal_service.create({**VALID_APPEAL, 'applicant_name': '<script>alert(1)</script>'})
    listing = appeal_service.list()
    list_html = render_admin_appeals_list(listing, appeal_service.get_stats(), {}, 'csrf')
    detail_html = render_admin_appeal_detail(appeal, 'csrf')
    assert '<script>alert(1)</script>' not in list_html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in list_html
    assert '<script>alert(1)</script>' not in detail_html


def test_purge_expired_appeals_clears_response_text_and_token_hash():
    appeal = appeal_service.create(VALID_APPEAL)
    answered = appeal_service.respond(appeal['id'], 'Конфиденциальный ответ заявителю.')
    assert answered['response_text'] == 'Конфиденциальный ответ заявителю.'
    token = appeal_service._make_access_token(answered)
    assert appeal_service.get_public(answered['registration_number'], token)['response_text'] == 'Конфиденциальный ответ заявителю.'

    con = get_db()
    try:
        con.execute('UPDATE appeals SET submitted_at = ? WHERE id = ?', (time.time() - (365 * 4 * 86400), appeal['id']))
        con.commit()
    finally:
        con.close()

    affected = appeal_service.purge_expired_appeals(retention_days=1095)
    assert affected >= 1

    stored = appeal_service.get_by_id(appeal['id'])
    assert stored['response_text'] == ''
    assert stored['public_token_hash'] is None
    assert stored['applicant_name'] == 'Обезличено (истёк срок хранения)'

    with pytest.raises(AppealValidationError):
        appeal_service.get_public(appeal['registration_number'], token)
    with pytest.raises(AppealValidationError):
        appeal_service.get_public(appeal['registration_number'], appeal['access_code'])


def test_admin_appeal_update_duplicate_and_versioning(monkeypatch):
    sent = []

    class MockSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def login(self, u, p):
            pass
        def starttls(self, context=None):
            pass
        def send_message(self, msg):
            sent.append(msg)

    for k, v in [
        ('APPEALS_EMAIL_ENABLED', True), ('SMTP_HOST', 'smtp.example.kz'), ('SMTP_USE_TLS', False),
        ('SMTP_USE_SSL', False), ('SMTP_FROM_EMAIL', 'no-reply@example.kz'), ('APPEALS_NOTIFY_EMAIL', 'office@example.kz'),
    ]:
        monkeypatch.setattr(config, k, v)
    service_module = importlib.import_module('services.appeals.appeal_service')
    monkeypatch.setattr(service_module.smtplib, 'SMTP', MockSMTP)

    appeal = appeal_service.create(VALID_APPEAL)

    handler = object.__new__(AppRequestHandler)
    handler.responses = []
    handler.redirects = []
    handler._get_current_user = lambda: {'username': 'admin', 'role': 'admin'}
    handler._is_assistant_or_admin = lambda: True
    handler._get_client_ip = lambda: '127.0.0.1'
    handler._verify_csrf = lambda **kw: True
    handler._redirect = lambda url: handler.redirects.append(url)

    # 1. Первый вызов respond -> письмо уходит
    handler._read_form_params = lambda max_bytes=None: {
        'id': [str(appeal['id'])], 'action': ['respond'],
        'response_text': ['Первый ответ'], 'admin_comment': ['Комментарий 1'],
        'csrf_token': ['valid'],
    }
    handler._handle_admin_appeal_update()
    assert len(sent) == 1
    assert 'Первый ответ' in sent[0].get_content()
    assert appeal_service.get_by_id(appeal['id'])['response_sent'] == 1

    # 2. Двойное нажатие (тот же текст и статус, уже отправлено) -> комментарий сохраняется, письмо НЕ дублируется
    handler._read_form_params = lambda max_bytes=None: {
        'id': [str(appeal['id'])], 'action': ['respond'],
        'response_text': ['Первый ответ'], 'admin_comment': ['Обновленный комментарий'],
        'csrf_token': ['valid'],
    }
    handler._handle_admin_appeal_update()
    assert len(sent) == 1
    assert appeal_service.get_by_id(appeal['id'])['admin_comment'] == 'Обновленный комментарий'

    # 3. Обновление текста при прежнем статусе через 'save' -> сбрасывает флаг и отправляет новое письмо
    handler._read_form_params = lambda max_bytes=None: {
        'id': [str(appeal['id'])], 'action': ['save'], 'status': ['ANSWERED'],
        'response_text': ['Обновленный текст ответа'], 'admin_comment': ['Дополнено'],
        'csrf_token': ['valid'],
    }
    handler._handle_admin_appeal_update()
    assert len(sent) == 2
    assert 'Обновленный текст ответа' in sent[1].get_content()
    assert appeal_service.get_by_id(appeal['id'])['response_sent'] == 1


def test_make_access_token_requires_secret_key(monkeypatch):
    appeal = appeal_service.create(VALID_APPEAL)
    monkeypatch.setattr(config, 'SECRET_KEY', '')
    assert appeal_service._make_access_token(appeal) == ''


def test_admin_appeal_update_parallel_requests_no_duplicate_emails(monkeypatch):
    import threading

    sent = []

    class MockSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def login(self, u, p):
            pass
        def starttls(self, context=None):
            pass
        def send_message(self, msg):
            sent.append(msg)

    for k, v in [
        ('APPEALS_EMAIL_ENABLED', True), ('SMTP_HOST', 'smtp.example.kz'), ('SMTP_USE_TLS', False),
        ('SMTP_USE_SSL', False), ('SMTP_FROM_EMAIL', 'no-reply@example.kz'), ('APPEALS_NOTIFY_EMAIL', 'office@example.kz'),
    ]:
        monkeypatch.setattr(config, k, v)
    service_module = importlib.import_module('services.appeals.appeal_service')
    monkeypatch.setattr(service_module.smtplib, 'SMTP', MockSMTP)

    appeal = appeal_service.create(VALID_APPEAL)

    def run_update(idx):
        handler = object.__new__(AppRequestHandler)
        handler.responses = []
        handler.redirects = []
        handler._get_current_user = lambda: {'username': f'admin_{idx}', 'role': 'admin'}
        handler._is_assistant_or_admin = lambda: True
        handler._get_client_ip = lambda: '127.0.0.1'
        handler._verify_csrf = lambda **kw: True
        handler._redirect = lambda url: handler.redirects.append(url)
        handler._read_form_params = lambda max_bytes=None: {
            'id': [str(appeal['id'])], 'action': ['respond'],
            'response_text': ['Параллельный ответ заявителю'],
            'admin_comment': [f'Комментарий от потока {idx}'],
            'csrf_token': ['valid'],
        }
        handler._handle_admin_appeal_update()

    threads = [threading.Thread(target=run_update, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Из 5 параллельных запросов ровно 1 должен отправить email
    assert len(sent) == 1
    assert appeal_service.get_by_id(appeal['id'])['response_sent'] == 1


def test_outbox_lease_retry_and_crash_recovery(monkeypatch):
    sent = []

    class FailingSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send_message(self, msg): raise smtplib.SMTPException('Connection refused')

    class SuccessSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send_message(self, msg): sent.append(msg)

    for k, v in [
        ('APPEALS_EMAIL_ENABLED', True), ('SMTP_HOST', 'smtp.example.kz'),
        ('SMTP_USE_TLS', False), ('SMTP_USE_SSL', False), ('SMTP_FROM_EMAIL', 'no-reply@example.kz'),
    ]:
        monkeypatch.setattr(config, k, v)

    service_module = importlib.import_module('services.appeals.appeal_service')
    monkeypatch.setattr(service_module.smtplib, 'SMTP', FailingSMTP)

    appeal = appeal_service.create(VALID_APPEAL)
    answered = appeal_service.respond(appeal['id'], 'Ответ с имитацией сбоя сети')

    now = time.time()
    assert appeal_service.notify_response(answered) is False
    rec = appeal_service.get_by_id(appeal['id'])
    assert rec['response_sent'] == 0 and rec['response_attempts'] == 1 and rec['response_lease'] >= now + 25.0
    assert appeal_service.retry_pending_responses() == 0  # задержка backoff активна

    # Истечение аренды -> успешная доставка и сброс счетчика попыток
    with write_transaction() as con:
        con.execute('UPDATE appeals SET response_lease = 0.0 WHERE id = ?', (appeal['id'],))
    monkeypatch.setattr(service_module.smtplib, 'SMTP', SuccessSMTP)
    assert appeal_service.retry_pending_responses() == 1
    assert len(sent) == 1 and 'Ответ с имитацией сбоя сети' in sent[0].get_content()
    rec_ok = appeal_service.get_by_id(appeal['id'])
    assert rec_ok['response_sent'] == 1 and rec_ok['response_attempts'] == 0

    # Предел попыток: при превышении limit автоповтор прекращается
    monkeypatch.setattr(service_module.smtplib, 'SMTP', FailingSMTP)
    monkeypatch.setattr(config, 'APPEALS_MAX_ATTEMPTS', 2)
    app2 = appeal_service.create({**VALID_APPEAL, 'registration_number': f'EP-MAX-{int(now)}'})
    ans2 = appeal_service.respond(app2['id'], 'Попытка 1')
    appeal_service.notify_response(ans2)
    with write_transaction() as con:
        con.execute('UPDATE appeals SET response_lease = 0.0 WHERE id = ?', (app2['id'],))
    appeal_service.retry_pending_responses()  # attempt 2 -> исчерпан лимит
    assert appeal_service.get_by_id(app2['id'])['response_attempts'] == 2
    with write_transaction() as con:
        con.execute('UPDATE appeals SET response_lease = 0.0 WHERE id = ?', (app2['id'],))
    monkeypatch.setattr(service_module.smtplib, 'SMTP', SuccessSMTP)
    assert appeal_service.retry_pending_responses() == 0  # не выбирается, так как >= max_attempts

    # Лимит в атомарном claim: отклоняет notify_response без обращения к SMTP
    with write_transaction() as con:
        con.execute('UPDATE appeals SET response_attempts = 5, response_lease = 0.0 WHERE id = ?', (app2['id'],))
    assert appeal_service.notify_response(app2['id']) is False

    # Подтверждение версии и привязка аренды к отправителю
    class StealLeaseSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send_message(self, msg):
            with write_transaction() as con:
                con.execute('UPDATE appeals SET response_lease = ? WHERE id = ?', (time.time() + 999.0, app2['id']))
    monkeypatch.setattr(service_module.smtplib, 'SMTP', StealLeaseSMTP)
    with write_transaction() as con:
        con.execute('UPDATE appeals SET response_lease = 0.0, response_attempts = 0 WHERE id = ?', (app2['id'],))
    assert appeal_service.notify_response(app2['id']) is False
    assert appeal_service.get_by_id(app2['id'])['response_sent'] == 0
