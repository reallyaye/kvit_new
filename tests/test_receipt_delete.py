import os

import config
from database import get_db
from server import AppRequestHandler
from services.security import auth_service


def _handler():
    handler = AppRequestHandler.__new__(AppRequestHandler)
    handler.headers = {}
    handler.client_address = ('127.0.0.1', 12345)
    handler.sent = {}
    handler.send_json = lambda data, code=200, extra_headers=None: handler.sent.update(
        {'data': data, 'code': code}
    )
    return handler


def test_operator_can_delete_one_receipt_with_audit(tmp_path, monkeypatch):
    token = 'abcdef0123456789abcdef0123456789'
    pdf_name = '900001_receipt.pdf'
    pdf_path = os.path.join(config.RECEIPTS_DIR, pdf_name)
    with open(pdf_path, 'wb') as pdf:
        pdf.write(b'%PDF-1.4 operator delete test')

    con = get_db()
    con.execute(
        'INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token) '
        'VALUES (?, ?, ?, ?, ?)',
        ('900001', 'Август 2026', pdf_name, 'delete-hash', token),
    )
    con.commit()
    con.close()

    quarantine_dir = tmp_path / 'deleted_receipts'
    monkeypatch.setattr(config, 'DELETED_RECEIPTS_DIR', str(quarantine_dir))
    handler = _handler()
    monkeypatch.setattr(handler, '_is_operator_or_admin', lambda: True)
    monkeypatch.setattr(handler, '_verify_csrf', lambda: True)
    monkeypatch.setattr(handler, '_read_bounded_body', lambda _limit: f'token={token}'.encode())
    monkeypatch.setattr(handler, '_get_current_user', lambda: {'username': 'shtabel', 'role': 'operator'})
    monkeypatch.setattr(handler, '_get_client_ip', lambda: '192.0.2.10')

    handler._handle_api_delete_receipt()

    assert handler.sent['code'] == 200
    assert handler.sent['data']['success'] is True
    assert handler.sent['data']['account_number'] == '900001'
    assert not os.path.exists(pdf_path)
    assert len(list(quarantine_dir.iterdir())) == 1

    logs = auth_service.list_audit_logs(limit=10, username='shtabel', action='DELETE_RECEIPT')
    assert len(logs) == 1
    assert '900001' in logs[0]['details']
    assert 'Август 2026' in logs[0]['details']


def test_delete_receipt_requires_operator_or_admin(monkeypatch):
    handler = _handler()
    monkeypatch.setattr(handler, '_is_operator_or_admin', lambda: False)

    handler._handle_api_delete_receipt()

    assert handler.sent['code'] == 401


def test_delete_receipt_permission_accepts_admin_and_operator(monkeypatch):
    handler = _handler()

    for role in ('admin', 'operator'):
        monkeypatch.setattr(handler, '_get_current_user', lambda current_role=role: {
            'username': 'test-user',
            'role': current_role,
        })
        assert handler._is_operator_or_admin() is True


def test_delete_receipt_requires_valid_csrf(monkeypatch):
    handler = _handler()
    monkeypatch.setattr(handler, '_is_operator_or_admin', lambda: True)
    monkeypatch.setattr(handler, '_verify_csrf', lambda: False)

    handler._handle_api_delete_receipt()

    assert handler.sent['code'] == 403
