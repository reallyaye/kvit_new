import sqlite3
try:
    import pytest
except ImportError:
    pytest = None
from database import get_db
from services.reconciliation.reconcile_service import reconcile_service

@pytest.fixture
def seed_reconcile_data():
    con = get_db()
    # 3 аккаунта: 800001, 800002, 800003
    con.executemany('INSERT INTO accounts(account_number, customer_name, address) VALUES (?,?,?)', [
        ('800001', 'Иванов Иван', 'ул. Ленина 1'),
        ('800002', 'Петров Петр', 'ул. Мира 2'),
        ('800003', 'Сидоров Сидор', 'ул. Абая 3'),
    ])
    # Квитанции:
    # 800001 (Январь 2026) - привязан
    # 800004 (Январь 2026) - сирота (нет в accounts)
    con.executemany('INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token) VALUES (?,?,?,?,?)', [
        ('800001', 'Январь 2026', '800001_abc.pdf', 'hash1', 'tok1'*8),
        ('800004', 'Январь 2026', '800004_def.pdf', 'hash2', 'tok2'*8),
    ])
    con.commit()
    con.close()

def test_reconcile_metrics(seed_reconcile_data):
    data = reconcile_service.get_reconciliation_data(filt='all', period_filter='')
    assert data['total_accounts'] == 3
    assert data['total_receipts'] == 2
    assert data['matched'] == 1
    assert data['unmatched'] == 2
    assert data['orphans'] == 1

def test_reconcile_filter_without(seed_reconcile_data):
    data = reconcile_service.get_reconciliation_data(filt='without', period_filter='')
    assert data['list_count'] == 2
    accs = [r['account_number'] for r in data['rows']]
    assert '800002' in accs
    assert '800003' in accs
    assert '800001' not in accs

def test_reconcile_filter_orphans(seed_reconcile_data):
    data = reconcile_service.get_reconciliation_data(filt='orphans', period_filter='')
    assert data['list_count'] == 1
    assert data['rows'][0]['account_number'] == '800004'

def test_reconcile_with_period_filter(seed_reconcile_data):
    data = reconcile_service.get_reconciliation_data(filt='with', period_filter='Январь 2026')
    assert data['matched'] == 1
    assert len(data['rows']) == 1
    assert data['rows'][0]['account_number'] == '800001'
