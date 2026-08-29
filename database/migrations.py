import logging
import secrets

from database.connection import write_transaction

logger = logging.getLogger(__name__)

class DatabaseMigrationError(RuntimeError):
    """Критическая ошибка применения миграций базы данных (Fail-Fast)."""
    pass

def migrate_db():
    """
    Гарантирует инициализацию схемы и миграции (accounts, receipts, app_sessions, security_blocks).
    Поддерживает как PostgreSQL (production), так и SQLite (dev/test).
    При любой ошибке выбрасывает DatabaseMigrationError и останавливает запуск приложения.
    """
    from database.connection import is_postgres_configured
    import os

    try:
        with write_transaction() as con:
            if is_postgres_configured():
                schema_path = os.path.join(os.path.dirname(__file__), 'schema.postgres.sql')
                if os.path.exists(schema_path):
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        pg_sql = f.read()
                    con.executescript(pg_sql)
                    logger.info("[DB] Схема PostgreSQL успешно проверена и применена.")
                    return

            # 1. Создание базовых таблиц (SQLite)
            con.executescript('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at REAL NOT NULL
                );

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

                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    role TEXT NOT NULL DEFAULT 'USER',
                    requested_at REAL NOT NULL,
                    reviewed_at REAL,
                    reviewed_by INTEGER,
                    comment TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tg_users_status ON telegram_users(status);
            ''')

            # 2. Проверка и динамическое добавление недостающих колонок
            cols = [row[1] for row in con.execute('PRAGMA table_info(receipts)').fetchall()]
            if 'content_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN content_hash TEXT')
            if 'file_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN file_hash TEXT')
            if 'semantic_hash' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN semantic_hash TEXT')
            if 'status' not in cols:
                con.execute("ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'READY'")
            if 'access_token' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN access_token TEXT')
                rows = con.execute('SELECT rowid FROM receipts WHERE access_token IS NULL').fetchall()
                for row in rows:
                    con.execute('UPDATE receipts SET access_token=? WHERE rowid=?',
                                (secrets.token_hex(16), row[0]))
            if 'address' not in cols:
                con.execute('ALTER TABLE receipts ADD COLUMN address TEXT')

            # 3. Создание индексов (после гарантированного наличия колонок)
            con.executescript('''
                CREATE INDEX IF NOT EXISTS idx_receipts_account_period ON receipts(account_number, period);
                CREATE INDEX IF NOT EXISTS idx_receipts_account ON receipts(account_number);
                CREATE INDEX IF NOT EXISTS idx_receipts_period ON receipts(period);
                CREATE INDEX IF NOT EXISTS idx_receipts_address ON receipts(address);
                CREATE INDEX IF NOT EXISTS idx_receipts_file_hash ON receipts(file_hash);
                CREATE INDEX IF NOT EXISTS idx_receipts_semantic_hash ON receipts(semantic_hash);
                CREATE INDEX IF NOT EXISTS idx_receipts_hash ON receipts(content_hash);
                CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_token ON receipts(access_token);
                CREATE INDEX IF NOT EXISTS idx_accounts_street_bld ON accounts(street, building);
                CREATE INDEX IF NOT EXISTS idx_receipts_hash_acc ON receipts(content_hash, account_number);
            ''')
    except Exception as e:
        logger.exception("[DB] Migration failed: %s", e)
        raise DatabaseMigrationError(f"Database migration failed: {e}") from e


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

    from config import RECEIPTS_DIR, get_receipt_shard_parts

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
    Синхронизирует записи в БД с реальными файлами на диске (БЕЗОПАСНАЯ И ОБРАТИМАЯ ОПЕРАЦИЯ):
    - Проверяет наличие каждого PDF-файла из таблицы receipts в директории RECEIPTS_DIR.
    - Если файл отсутствует на диске, переводит статус записи в 'missing' (БЕЗ УДАЛЕНИЯ МЕТАДАННЫХ).
    - Если файл снова появился на диске (например, смонтировали сетевой диск/хранилище), восстанавливает статус 'ready'.
    Возвращает: (marked_missing_count, restored_ready_count, valid_ready_count)
    """
    import os

    from config import RECEIPTS_DIR, get_receipt_shard_parts
    from database.connection import get_db

    marked_missing = 0
    restored_ready = 0
    valid_ready = 0

    to_mark_missing = []
    to_mark_ready = []

    con_read = get_db()
    try:
        rows = con_read.execute('SELECT id, account_number, pdf_file, status FROM receipts').fetchall()
        for r in rows:
            rec_id = r['id']
            acc = r['account_number']
            pdf_file = r['pdf_file']
            current_status = r['status'] if 'status' in r.keys() else 'ready'

            file_exists = False
            if pdf_file:
                fp = os.path.abspath(os.path.join(RECEIPTS_DIR, pdf_file))
                if os.path.isfile(fp):
                    file_exists = True
                else:
                    # Fallback checks (sharded vs flat)
                    base_filename = os.path.basename(pdf_file)
                    s1, s2 = get_receipt_shard_parts(acc)
                    sharded_fp = os.path.abspath(os.path.join(RECEIPTS_DIR, s1, s2, base_filename))
                    flat_fp = os.path.abspath(os.path.join(RECEIPTS_DIR, base_filename))
                    if os.path.isfile(sharded_fp) or os.path.isfile(flat_fp):
                        file_exists = True

            if file_exists:
                valid_ready += 1
                if str(current_status).upper() != 'READY':
                    to_mark_ready.append(rec_id)
            else:
                if str(current_status).upper() != 'MISSING':
                    to_mark_missing.append(rec_id)
    finally:
        con_read.close()

    if to_mark_missing or to_mark_ready:
        with write_transaction() as con_write:
            if to_mark_missing:
                for i in range(0, len(to_mark_missing), 500):
                    chunk = to_mark_missing[i:i + 500]
                    placeholders = ','.join('?' * len(chunk))
                    con_write.execute(f"UPDATE receipts SET status = 'MISSING' WHERE id IN ({placeholders})", chunk)  # nosec B608
                marked_missing = len(to_mark_missing)

            if to_mark_ready:
                for i in range(0, len(to_mark_ready), 500):
                    chunk = to_mark_ready[i:i + 500]
                    placeholders = ','.join('?' * len(chunk))
                    con_write.execute(f"UPDATE receipts SET status = 'READY' WHERE id IN ({placeholders})", chunk)  # nosec B608
                restored_ready = len(to_mark_ready)

    return marked_missing, restored_ready, valid_ready

def purge_missing_receipts() -> int:
    """
    ЯВНАЯ АДМИНИСТРАТИВНАЯ ОПЕРАЦИЯ:
    Физически удаляет из БД только те записи, которые имеют статус 'missing'.
    Возвращает: количество удаленных записей.
    """
    with write_transaction() as con:
        cur = con.execute("DELETE FROM receipts WHERE UPPER(status) = 'MISSING'")
        deleted_count = cur.rowcount if hasattr(cur, 'rowcount') and cur.rowcount != -1 else 0
        if deleted_count == 0:
            changes = con.execute("SELECT changes()").fetchone()
            deleted_count = changes[0] if changes else 0
    return deleted_count




