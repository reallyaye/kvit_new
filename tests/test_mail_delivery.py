import smtplib
from unittest.mock import MagicMock, patch

import config
from services.mail.test_delivery import (
    check_domain_dns,
    check_smtp_connection,
    send_test_email,
)


def test_check_smtp_connection_no_host(monkeypatch):
    monkeypatch.setattr(config, 'SMTP_HOST', '')
    res = check_smtp_connection(host='')
    assert res['tcp_connected'] is False
    assert res['error_phase'] == 'config'
    assert 'не настроен' in res['error_message']


def test_check_smtp_connection_empty_password(monkeypatch):
    monkeypatch.setattr(config, 'SMTP_HOST', 'smtp.example.kz')
    monkeypatch.setattr(config, 'SMTP_PORT', 465)
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'test@krec.kz')
    monkeypatch.setattr(config, 'SMTP_PASSWORD', '')
    monkeypatch.setattr(config, 'SMTP_USE_SSL', True)

    with patch('smtplib.SMTP_SSL') as mock_ssl:
        instance = MagicMock()
        instance.ehlo.return_value = (250, b'ok')
        mock_ssl.return_value = instance

        res = check_smtp_connection()
        assert res['tcp_connected'] is True
        assert res['ehlo_success'] is True
        assert res['auth_success'] is False
        assert res['error_phase'] == 'auth'
        assert 'пароль пустой' in res['error_message']


def test_check_smtp_connection_auth_535(monkeypatch):
    monkeypatch.setattr(config, 'SMTP_HOST', 'smtp.mail.ru')
    monkeypatch.setattr(config, 'SMTP_PORT', 465)
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'info.krec@mail.ru')
    monkeypatch.setattr(config, 'SMTP_PASSWORD', 'wrong_pass')
    monkeypatch.setattr(config, 'SMTP_USE_SSL', True)

    with patch('smtplib.SMTP_SSL') as mock_ssl:
        instance = MagicMock()
        instance.ehlo.return_value = (250, b'ok')
        instance.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b'5.7.0 NEOBHODIM parol prilozheniya'
        )
        mock_ssl.return_value = instance

        res = check_smtp_connection()
        assert res['tcp_connected'] is True
        assert res['auth_success'] is False
        assert res['error_code'] == 535
        assert 'Пароль для внешних приложений' in res['action_required']


def test_check_smtp_connection_success(monkeypatch):
    monkeypatch.setattr(config, 'SMTP_HOST', 'smtp.example.kz')
    monkeypatch.setattr(config, 'SMTP_PORT', 587)
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'info@krec.kz')
    monkeypatch.setattr(config, 'SMTP_PASSWORD', 'app_secret')
    monkeypatch.setattr(config, 'SMTP_USE_SSL', False)
    monkeypatch.setattr(config, 'SMTP_USE_TLS', True)

    with patch('smtplib.SMTP') as mock_smtp:
        instance = MagicMock()
        instance.ehlo.return_value = (250, b'ok')
        instance.login.return_value = (235, b'2.7.0 Accepted')
        mock_smtp.return_value = instance

        res = check_smtp_connection()
        assert res['tcp_connected'] is True
        assert res['ehlo_success'] is True
        assert res['tls_success'] is True
        assert res['auth_success'] is True
        assert res['error_phase'] is None


def test_check_domain_dns():
    mock_answers = {
        ('krec.kz', 'MX'): [{'type': 15, 'data': '10 emx.mail.ru.'}],
        ('krec.kz', 'TXT'): [{'type': 16, 'data': '"v=spf1 redirect=_spf.mail.ru"'}],
        ('_dmarc.krec.kz', 'TXT'): [{'type': 16, 'data': '"v=DMARC1; p=none;"'}],
        ('mail._domainkey.krec.kz', 'TXT'): [{'type': 16, 'data': '"v=DKIM1; k=rsa; p=MIGfMA0G..."'}],
    }

    def fake_query_doh(name, qtype, timeout=4.0):
        return mock_answers.get((name, qtype), [])

    with patch('services.mail.test_delivery.query_doh', side_effect=fake_query_doh):
        res = check_domain_dns('krec.kz')
        assert res['has_mx'] is True
        assert res['has_spf'] is True
        assert res['has_dmarc'] is True
        assert res['has_dkim'] is True
        assert len(res['recommendations']) == 0


def test_send_test_email(monkeypatch):
    monkeypatch.setattr(config, 'SMTP_HOST', 'smtp.example.kz')
    monkeypatch.setattr(config, 'SMTP_PORT', 587)
    monkeypatch.setattr(config, 'SMTP_FROM_EMAIL', 'info@krec.kz')
    monkeypatch.setattr(config, 'SMTP_FROM_NAME', 'ТОО «КРЭК»')
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'info@krec.kz')
    monkeypatch.setattr(config, 'SMTP_PASSWORD', 'secret')
    monkeypatch.setattr(config, 'SMTP_USE_SSL', False)
    monkeypatch.setattr(config, 'SMTP_USE_TLS', True)

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def starttls(self, context=None):
            pass
        def login(self, u, p):
            pass
        def send_message(self, msg):
            sent.append(msg)

    with patch('smtplib.SMTP', FakeSMTP):
        res = send_test_email('citizen@example.kz')
        assert res['success'] is True
        assert len(sent) == 1
        msg = sent[0]
        assert msg['To'] == 'citizen@example.kz'
        assert 'ТОО «КРЭК»' in msg['From']
        assert 'info@krec.kz' in msg['From']
