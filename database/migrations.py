import secrets
from database.connection import write_transaction

def migrate_db():
    """Гарантирует инициализацию схемы и миграции (receipts, app_sessions, security_blocks)."""
    try:
        with write_transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    account_number TEXT NOT NULL UNIQUE,
                    customer_name TEXT,
                    address TEXT,
                    street TEXT,
                    building TEXT,
                    corpus TEXT,
                    district TEXT,
                    organization TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_accounts_account ON accounts(account_number);
                CREATE INDEX IF NOT EXISTS idx_accounts_address ON accounts(address);

                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY,
                    account_number TEXT NOT NULL,
                    period TEXT NOT NULL,
                    pdf_file TEXT NOT NULL,
                    file_hash TEXT,
                    semantic_hash TEXT,
                    content_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'READY',
                    access_token TEXT,
                    address TEXT,
                    UNIQUE(account_number, period)
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_account_period ON receipts(account_number, period);
                CREATE INDEX IF NOT EXISTS idx_receipts_account ON receipts(account_number);
                CREATE INDEX IF NOT EXISTS idx_receipts_period ON receipts(period);
                CREATE INDEX IF NOT EXISTS idx_receipts_address ON receipts(address);
                CREATE INDEX IF NOT EXISTS idx_receipts_file_hash ON receipts(file_hash);
                CREATE INDEX IF NOT EXISTS idx_receipts_semantic_hash ON receipts(semantic_hash);
                CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);

                CREATE TABLE IF NOT EXISTS app_sessions (
                    token TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON app_sessions(expires_at);

                CREATE TABLE IF NOT EXISTS security_blocks (
                    ip TEXT PRIMARY KEY,
                    blocked_until REAL NOT NULL,
                    reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_blocks_until ON security_blocks(blocked_until);
            ''')

            # Проверка и добавление недостающих колонок
            cols = [row[1] for row in con.execute('PRAGMA table_info(receipts)').fetchall()]
            if 'content_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN content_hash TEXT')
                con.execute('CREATE INDEX IF NOT EXISTS idx_receipts_hash ON receipts(content_hash)')
            if 'file_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN file_hash TEXT')
                con.execute('CREATE INDEX IF NOT EXISTS idx_receipts_file_hash ON receipts(file_hash)')
            if 'semantic_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN semantic_hash TEXT')
                con.execute('CREATE INDEX IF NOT EXISTS idx_receipts_semantic_hash ON receipts(semantic_hash)')
            if 'status' not in cols:
                con.execute("ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'READY'")
                con.execute('CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status)')
            if 'access_token' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN access_token TEXT')
                con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_token ON receipts(access_token)')
                rows = con.execute('SELECT rowid FROM receipts WHERE access_token IS NULL').fetchall()
                for row in rows:
                    con.execute('UPDATE receipts SET access_token=? WHERE rowid=?',
                                (secrets.token_hex(16), row[0]))
            if 'address' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN address TEXT')
                con.execute('CREATE INDEX IF NOT EXISTS idx_receipts_address ON receipts(address)')
    except Exception:
        pass

def migrate_receipts_to_sharding():
    """
    Миграция файлового хранилища квитанций:
    Переносит файлы из плоской структуры (receipts/{account}_{hash}.pdf)
    в шардированную структуру (receipts/{s1}/{s2}/{account}_{hash}.pdf)
    и обновляет относительные пути в БД.
    Возвращает: (migrated_files_count, updated_db_records_count)
    """
    import os
    import shutil
    from config import RECEIPTS_DIR, get_receipt_shard_parts, get_sharded_receipt_rel_path

    migrated_files = 0
    updated_db = 0

    with write_transaction() as con:
        rows = con.execute('SELECT id, account_number, pdf_file FROM receipts WHERE pdf_file IS NOT NULL').fetchall()
        for r in rows:
            rec_id, acc, pdf_file = r[0], r[1], r[2]
            # Проверяем, шардирован ли уже путь в БД
            if '/' in pdf_file or '\\' in pdf_file:
                # Уже в подкаталоге
                continue

            base_filename = os.path.basename(pdf_file)
            s1, s2 = get_receipt_shard_parts(acc)
            new_rel_path = f"{s1}/{s2}/{base_filename}"

            old_file_path = os.path.join(RECEIPTS_DIR, base_filename)
            new_dir_path = os.path.join(RECEIPTS_DIR, s1, s2)
            new_file_path = os.path.join(new_dir_path, base_filename)

            # Перемещаем файл на диске, если он существует в плоском корне
            if os.path.isfile(old_file_path):
                os.makedirs(new_dir_path, exist_ok=True)
                if not os.path.isfile(new_file_path):
                    shutil.move(old_file_path, new_file_path)
                    migrated_files += 1
                elif old_file_path != new_file_path:
                    # Файл уже есть в целевой директории
                    os.remove(old_file_path)
                    migrated_files += 1

            # Обновляем запись в БД
            con.execute('UPDATE receipts SET pdf_file = ? WHERE id = ?', (new_rel_path, rec_id))
            updated_db += 1

    return migrated_files, updated_db

def sync_receipts_with_filesystem():
    """
    Синхронизирует записи в БД с реальными файлами на диске:
    - Проверяет наличие каждого PDF-файла из таблицы receipts в директории RECEIPTS_DIR.
    - Удаляет из БД записи о квитанциях, файлы которых физически отсутствуют на диске.
    Возвращает: (removed_ghost_records_count, remaining_valid_records_count)
    """
    import os
    from config import RECEIPTS_DIR, get_receipt_shard_parts
    from database.connection import get_db

    removed_count = 0
    valid_count = 0
    ids_to_delete = []

    con_read = get_db()
    try:
        rows = con_read.execute('SELECT id, account_number, pdf_file FROM receipts').fetchall()
        for r in rows:
            rec_id = r['id']
            acc = r['account_number']
            pdf_file = r['pdf_file']
            if not pdf_file:
                ids_to_delete.append(rec_id)
                continue

            fp = os.path.abspath(os.path.join(RECEIPTS_DIR, pdf_file))
            if os.path.isfile(fp):
                valid_count += 1
                continue

            # Fallback checks (sharded vs flat)
            base_filename = os.path.basename(pdf_file)
            s1, s2 = get_receipt_shard_parts(acc)
            sharded_fp = os.path.abspath(os.path.join(RECEIPTS_DIR, s1, s2, base_filename))
            flat_fp = os.path.abspath(os.path.join(RECEIPTS_DIR, base_filename))

            if os.path.isfile(sharded_fp) or os.path.isfile(flat_fp):
                valid_count += 1
            else:
                ids_to_delete.append(rec_id)
    finally:
        con_read.close()

    if ids_to_delete:
        with write_transaction() as con_write:
            for i in range(0, len(ids_to_delete), 500):
                chunk = ids_to_delete[i:i+500]
                placeholders = ','.join('?' * len(chunk))
                con_write.execute(f'DELETE FROM receipts WHERE id IN ({placeholders})', chunk)  # nosec B608
        removed_count = len(ids_to_delete)

    return removed_count, valid_count



