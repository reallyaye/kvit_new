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

def test_safe_sync_and_purge_lifecycle(tmp_path, monkeypatch):
    """
    Тестирует безопасную и обратимую синхронизацию с диском:
    1. Отсутствующие на диске файлы не удаляются, а переводятся в статус 'missing'.
    2. При повторном появлении файлов на диске статус восстанавливается в 'ready'.
    3. Физическое удаление записей происходит только при явном вызове purge_missing_receipts().
    """
    import os

    import config
    from database import get_db, purge_missing_receipts, sync_receipts_with_filesystem

    monkeypatch.setattr(config, 'RECEIPTS_DIR', str(tmp_path))

    con = get_db()
    con.execute("DELETE FROM receipts")
    con.executemany('INSERT INTO receipts(account_number, period, pdf_file, content_hash, access_token, status) VALUES (?,?,?,?,?,?)', [
        ('800001', 'Январь 2026', '800001_test.pdf', 'h1', 't1'*16, 'ready'),
        ('800002', 'Январь 2026', '800002_test.pdf', 'h2', 't2'*16, 'ready'),
    ])
    con.commit()
    con.close()

    # 1. Создаем только один файл на диске
    file1_path = os.path.join(tmp_path, '800001_test.pdf')
    with open(file1_path, 'wb') as f:
        f.write(b"%PDF-1.4 test")

    # 2. Первая синхронизация: 800002 должен быть помечен как 'missing', но НЕ удален
    marked_missing, restored_ready, valid_ready = sync_receipts_with_filesystem()
    assert marked_missing == 1
    assert restored_ready == 0
    assert valid_ready == 1

    con = get_db()
    r1 = con.execute("SELECT status FROM receipts WHERE account_number='800001'").fetchone()
    r2 = con.execute("SELECT status FROM receipts WHERE account_number='800002'").fetchone()
    con.close()
    assert r1['status'] == 'ready'
    assert r2['status'] == 'missing'

    # 3. Эмулируем монтирование диска: создаем второй файл
    file2_path = os.path.join(tmp_path, '800002_test.pdf')
    with open(file2_path, 'wb') as f:
        f.write(b"%PDF-1.4 test2")

    # 4. Вторая синхронизация: 800002 должен автоматически восстановиться в 'ready'
    marked_missing2, restored_ready2, valid_ready2 = sync_receipts_with_filesystem()
    assert marked_missing2 == 0
    assert restored_ready2 == 1
    assert valid_ready2 == 2

    con = get_db()
    r2_restored = con.execute("SELECT status FROM receipts WHERE account_number='800002'").fetchone()
    con.close()
    assert r2_restored['status'] == 'ready'

    # 5. Удаляем файл 2 и синхронизируем -> status='missing'
    os.remove(file2_path)
    sync_receipts_with_filesystem()

    # 6. Явная административная очистка (purge)
    purged = purge_missing_receipts()
    assert purged == 1

    con = get_db()
    remaining = con.execute("SELECT account_number FROM receipts").fetchall()
    con.close()
    assert len(remaining) == 1
    assert remaining[0]['account_number'] == '800001'

