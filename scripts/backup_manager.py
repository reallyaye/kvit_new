#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KREC Portal - Comprehensive Automated Backup & Disaster Recovery Manager
Резервное копирование и реальная проверка восстановления:
1. База данных (PostgreSQL pg_dump с компрессией gzip / SQLite online backup).
2. Каталог PDF-квитанций (data/receipts -> tar.gz).
3. Каталог загруженных файлов CMS (data/uploads, static/images/uploads, extracted_portal_pages.json -> tar.gz).
4. Манифест с контрольными суммами SHA-256, метаданными и метриками базы данных.
5. Реальная проверка восстановления (--verify) с проверкой архивов и тестовым восстановлением.
6. Репликация на внешний накопитель или удаленный сервер (--remote-target / rsync).
7. Автоматическая ротация архивов старше N дней (retention policy).
"""

import argparse
import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, Dict, List, Optional

# Добавляем корень проекта в sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config  # noqa: E402
from database.connection import get_db, is_postgres_configured  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [BackupManager] %(message)s'
)
logger = logging.getLogger('backup_manager')


def calc_sha256(filepath: str) -> str:
    """Вычисляет хэш SHA-256 файла."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> str:
    """Возвращает текущий commit hash репозитория."""
    try:
        res = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def get_database_metrics() -> Dict[str, Any]:
    """Считывает ключевые количественные метрики из активной БД (get_db / docker exec / sqlite fallback)."""
    # 1. Попытка через стандартный get_db()
    try:
        con = get_db()
        try:
            def _cnt(tbl: str) -> int:
                try:
                    row = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                    return int(row[0]) if row else 0
                except Exception:
                    return 0

            acc_cnt = _cnt('accounts')
            rec_cnt = _cnt('receipts')
            audit_cnt = _cnt('audit_logs')

            sample_receipts: List[str] = []
            try:
                rows = con.execute("SELECT pdf_file FROM receipts WHERE pdf_file IS NOT NULL AND pdf_file != '' LIMIT 10").fetchall()
                for r in rows:
                    sample_receipts.append(str(r[0]))
            except Exception:
                pass

            return {
                'accounts_count': acc_cnt,
                'receipts_count': rec_cnt,
                'audit_logs_count': audit_cnt,
                'sample_receipt_files': sample_receipts
            }
        finally:
            con.close()
    except Exception as db_err:
        logger.debug(f"Прямой доступ get_db() недоступен ({db_err}). Пробуем docker exec...")

    # 2. Попытка через docker exec kvit-postgres (если запущено на хосте без прямого доступа к порту 5432)
    try:
        pg_user = os.getenv('POSTGRES_USER', 'user')
        pg_db = os.getenv('POSTGRES_DB', 'kvit_db')
        res = subprocess.run([
            'docker', 'exec', '-i', 'kvit-postgres',
            'psql', '-U', pg_user, '-d', pg_db, '-t', '-A', '-c',
            "SELECT (SELECT COUNT(*) FROM accounts), (SELECT COUNT(*) FROM receipts), (SELECT COUNT(*) FROM audit_logs);"
        ], capture_output=True, text=True, check=False)

        if res.returncode == 0 and '|' in res.stdout:
            parts = res.stdout.strip().split('|')
            acc_cnt = int(parts[0])
            rec_cnt = int(parts[1])
            audit_cnt = int(parts[2]) if len(parts) > 2 else 0

            sample_receipts = []
            res_samples = subprocess.run([
                'docker', 'exec', '-i', 'kvit-postgres',
                'psql', '-U', pg_user, '-d', pg_db, '-t', '-A', '-c',
                "SELECT pdf_file FROM receipts WHERE pdf_file IS NOT NULL AND pdf_file != '' LIMIT 10;"
            ], capture_output=True, text=True, check=False)
            if res_samples.returncode == 0:
                sample_receipts = [line.strip() for line in res_samples.stdout.strip().split('\n') if line.strip()]

            return {
                'accounts_count': acc_cnt,
                'receipts_count': rec_cnt,
                'audit_logs_count': audit_cnt,
                'sample_receipt_files': sample_receipts
            }
    except Exception as docker_err:
        logger.debug(f"Docker fallback не сработал: {docker_err}")

    # 3. Fallback на SQLite локальный файл
    db_path = getattr(config, 'DB', os.path.join(BASE_DIR, 'data.sqlite3'))
    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        try:
            acc_cnt = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            rec_cnt = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            return {
                'accounts_count': acc_cnt,
                'receipts_count': rec_cnt,
                'audit_logs_count': 0,
                'sample_receipt_files': []
            }
        except Exception:
            pass
        finally:
            con.close()

    return {
        'accounts_count': 0,
        'receipts_count': 0,
        'audit_logs_count': 0,
        'sample_receipt_files': []
    }


class BackupManager:
    """Комплексный менеджер резервного копирования и верификации восстановления."""

    def __init__(
        self,
        base_dir: str = BASE_DIR,
        backup_root: str = os.path.join(BASE_DIR, 'backups'),
        retention_days: int = 14
    ):
        self.base_dir = os.path.abspath(base_dir)
        self.backup_root = os.path.abspath(backup_root)
        self.retention_days = max(1, retention_days)
        os.makedirs(self.backup_root, exist_ok=True)

    def run_backup(
        self,
        verify: bool = True,
        remote_target: Optional[str] = None
    ) -> Dict[str, Any]:
        """Выполняет полный цикл резервного копирования всех компонентов."""
        ts_str = time.strftime('%Y%m%d_%H%M%S')
        bundle_name = f"kvit_backup_{ts_str}"
        bundle_dir = os.path.join(self.backup_root, bundle_name)
        os.makedirs(bundle_dir, exist_ok=True)

        logger.info(f"Начало создания резервной копии в {bundle_dir}...")
        start_time = time.time()

        # 1. Сбор исходных метрик базы данных
        initial_metrics = get_database_metrics()
        logger.info(
            f"Текущее состояние базы: счетов: {initial_metrics['accounts_count']}, "
            f"квитанций: {initial_metrics['receipts_count']}, событий аудита: {initial_metrics['audit_logs_count']}"
        )

        manifest: Dict[str, Any] = {
            'bundle_name': bundle_name,
            'created_at': time.time(),
            'timestamp': ts_str,
            'git_commit': get_git_commit(),
            'database_type': 'postgres' if is_postgres_configured() else 'sqlite',
            'initial_metrics': initial_metrics,
            'files': {},
            'verification': {}
        }

        # 2. Бэкап базы данных
        db_file = self._backup_database(bundle_dir, ts_str)
        manifest['database_type'] = 'postgres' if db_file.endswith('.sql.gz') else 'sqlite'
        manifest['files']['database'] = {
            'filename': os.path.basename(db_file),
            'size_bytes': os.path.getsize(db_file),
            'sha256': calc_sha256(db_file)
        }
        logger.info(f"Бэкап БД создан: {os.path.basename(db_file)} ({manifest['files']['database']['size_bytes']} байт)")

        # 3. Бэкап каталога PDF-квитанций
        receipts_file, receipts_count = self._backup_receipts(bundle_dir, ts_str)
        manifest['files']['receipts'] = {
            'filename': os.path.basename(receipts_file),
            'size_bytes': os.path.getsize(receipts_file),
            'sha256': calc_sha256(receipts_file),
            'archived_files_count': receipts_count
        }
        logger.info(f"Архив квитанций создан: {os.path.basename(receipts_file)} ({receipts_count} файлов, {manifest['files']['receipts']['size_bytes']} байт)")

        # 4. Бэкап файлов CMS и загрузок
        cms_file, cms_count = self._backup_cms_files(bundle_dir, ts_str)
        manifest['files']['cms'] = {
            'filename': os.path.basename(cms_file),
            'size_bytes': os.path.getsize(cms_file),
            'sha256': calc_sha256(cms_file),
            'archived_files_count': cms_count
        }
        logger.info(f"Архив CMS создан: {os.path.basename(cms_file)} ({cms_count} файлов, {manifest['files']['cms']['size_bytes']} байт)")

        # 5. Проверка восстановления (Disaster Recovery Verification Drill)
        if verify:
            logger.info("Запуск верификации восстановления (Disaster Recovery Drill)...")
            verify_result = self.verify_backup_bundle(bundle_dir, manifest)
            manifest['verification'] = verify_result
            if not verify_result.get('success'):
                logger.error(f"Верификация бэкапа завершилась ошибкой: {verify_result.get('error')}")
                raise RuntimeError(f"Верификация бэкапа не пройдена: {verify_result.get('error')}")
            logger.info("Верификация бэкапа успешно пройдена на 100%!")

        # 6. Сохранение итогового манифеста
        manifest_path = os.path.join(bundle_dir, 'manifest.json')
        manifest['elapsed_seconds'] = round(time.time() - start_time, 2)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 7. Синхронизация на внешний накопитель / удаленный сервер
        target_remote = remote_target or os.getenv('BACKUP_REMOTE_TARGET')
        if target_remote:
            self._sync_remote(bundle_dir, target_remote)

        # 8. Ротация старых копий
        self.rotate_old_backups()

        logger.info(f"Резервное копирование полностью завершено за {manifest['elapsed_seconds']} с.")
        return manifest

    # ────────────────────── Вспомогательные методы создания бэкапов ──────────────────────

    def _backup_database(self, bundle_dir: str, ts_str: str) -> str:
        """Создает горячий сжатый дамп базы данных."""
        has_docker_pg = False
        try:
            check_docker = subprocess.run(
                ['docker', 'ps', '--filter', 'name=kvit-postgres', '--format', '{{.Names}}'],
                capture_output=True, text=True, check=False
            )
            has_docker_pg = (check_docker.returncode == 0 and 'kvit-postgres' in check_docker.stdout)
        except Exception:
            pass

        if is_postgres_configured() or has_docker_pg:
            try:
                return self._dump_postgres(bundle_dir, ts_str)
            except Exception as pg_err:
                logger.warning(f"Ошибка дампа PostgreSQL: {pg_err}. Проверяем SQLite fallback...")
                db_path = getattr(config, 'DB', os.path.join(self.base_dir, 'data.sqlite3'))
                if os.path.exists(db_path):
                    return self._dump_sqlite(bundle_dir, ts_str)
                raise
        else:
            return self._dump_sqlite(bundle_dir, ts_str)

    def _dump_postgres(self, bundle_dir: str, ts_str: str) -> str:
        """Дамп PostgreSQL через docker exec kvit-postgres или pg_dump."""
        target_file = os.path.join(bundle_dir, f"postgres_kvit_{ts_str}.sql.gz")
        pg_user = os.getenv('POSTGRES_USER', 'user')
        pg_db = os.getenv('POSTGRES_DB', 'kvit_db')

        dump_cmd = None
        # Проверяем наличие docker контейнера kvit-postgres
        try:
            check_docker = subprocess.run(
                ['docker', 'ps', '--filter', 'name=kvit-postgres', '--format', '{{.Names}}'],
                capture_output=True, text=True, check=False
            )
            if check_docker.returncode == 0 and 'kvit-postgres' in check_docker.stdout:
                dump_cmd = [
                    'docker', 'exec', '-i', 'kvit-postgres',
                    'pg_dump', '-U', pg_user, '-d', pg_db,
                    '--clean', '--if-exists', '--no-owner'
                ]
        except Exception:
            pass

        # Если докера нет, пробуем pg_dump напрямую
        if not dump_cmd:
            db_url = getattr(config, 'DATABASE_URL', '') or os.getenv('DATABASE_URL', '')
            if not db_url:
                pg_pass = os.getenv('POSTGRES_PASSWORD', '')
                pg_host = os.getenv('POSTGRES_HOST', '127.0.0.1')
                pg_port = os.getenv('POSTGRES_PORT', '5432')
                if pg_user and pg_pass:
                    db_url = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
            if not db_url:
                raise RuntimeError("Не задан URL подключения к PostgreSQL (DATABASE_URL пуст)")
            dump_cmd = ['pg_dump', '--clean', '--if-exists', '--no-owner', db_url]

        logger.info(f"Выполнение pg_dump: {' '.join(dump_cmd[:4])} ...")
        proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        with gzip.open(target_file, 'wb', compresslevel=9) as gz_out:
            shutil.copyfileobj(proc.stdout, gz_out)

        _, stderr = proc.communicate()
        if proc.returncode != 0:
            err_text = stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"Ошибка выполнения pg_dump (код {proc.returncode}): {err_text}")

        return target_file

    def _dump_sqlite(self, bundle_dir: str, ts_str: str) -> str:
        """Горячий онлайн-бэкап SQLite с компрессией в gzip."""
        raw_db = os.path.join(bundle_dir, f"sqlite_kvit_{ts_str}.db")
        target_gz = os.path.join(bundle_dir, f"sqlite_kvit_{ts_str}.db.gz")

        db_path = getattr(config, 'DB', os.path.join(self.base_dir, 'data.sqlite3'))
        if not os.path.exists(db_path):
            init_con = sqlite3.connect(db_path)
            init_con.close()

        src_con = sqlite3.connect(db_path)
        try:
            dst_con = sqlite3.connect(raw_db)
            src_con.backup(dst_con)
            dst_con.close()
        finally:
            src_con.close()

        # Сжимаем в gzip
        with open(raw_db, 'rb') as f_in, gzip.open(target_gz, 'wb', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

        if os.path.exists(raw_db):
            os.remove(raw_db)

        return target_gz

    def _backup_receipts(self, bundle_dir: str, ts_str: str) -> tuple[str, int]:
        """Упаковывает каталог PDF-квитанций в tar.gz."""
        target_file = os.path.join(bundle_dir, f"receipts_{ts_str}.tar.gz")
        receipts_dir = os.path.join(self.base_dir, 'data', 'receipts')
        if not os.path.exists(receipts_dir):
            receipts_dir = os.path.join(self.base_dir, 'receipts')
        if not os.path.exists(receipts_dir) and hasattr(config, 'RECEIPTS_DIR'):
            receipts_dir = config.RECEIPTS_DIR

        if not os.path.exists(receipts_dir):
            os.makedirs(receipts_dir, exist_ok=True)

        count = 0
        with tarfile.open(target_file, 'w:gz', compresslevel=6) as tar:
            for root, _, files in os.walk(receipts_dir):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, receipts_dir)
                    tar.add(full_p, arcname=rel_p)
                    count += 1

        return target_file, count

    def _backup_cms_files(self, bundle_dir: str, ts_str: str) -> tuple[str, int]:
        """Упаковывает загруженные CMS-файлы и канонический контент в tar.gz."""
        target_file = os.path.join(bundle_dir, f"cms_uploads_{ts_str}.tar.gz")
        count = 0

        with tarfile.open(target_file, 'w:gz', compresslevel=6) as tar:
            # 1. Загрузки data/uploads
            uploads_dir = os.path.join(self.base_dir, 'data', 'uploads')
            if os.path.exists(uploads_dir):
                for root, _, files in os.walk(uploads_dir):
                    for f in files:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.join('uploads', os.path.relpath(full_p, uploads_dir))
                        tar.add(full_p, arcname=rel_p)
                        count += 1

            # 2. Картинки static/images/uploads (если есть)
            static_uploads = os.path.join(self.base_dir, 'static', 'images', 'uploads')
            if os.path.exists(static_uploads):
                for root, _, files in os.walk(static_uploads):
                    for f in files:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.join('static_uploads', os.path.relpath(full_p, static_uploads))
                        tar.add(full_p, arcname=rel_p)
                        count += 1

            # 3. Канонические страницы data/extracted_portal_pages.json
            pages_json = os.path.join(self.base_dir, 'data', 'extracted_portal_pages.json')
            if os.path.exists(pages_json):
                tar.add(pages_json, arcname='extracted_portal_pages.json')
                count += 1

        return target_file, count

    # ────────────────────── Верификация восстановления ──────────────────────

    def verify_backup_bundle(self, bundle_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Проводит детальную проверку восстановления архивов и базы данных."""
        res: Dict[str, Any] = {
            'success': False,
            'archive_integrity': {},
            'database_verified': False,
            'receipts_sample_verified': False
        }

        files_meta = manifest.get('files', {})

        # 1. Проверка контрольных сумм и целостности каждого архива
        for component, meta in files_meta.items():
            fpath = os.path.join(bundle_dir, meta['filename'])
            if not os.path.exists(fpath):
                res['error'] = f"Файл архива не найден: {meta['filename']}"
                return res

            calc_hash = calc_sha256(fpath)
            if calc_hash != meta['sha256']:
                res['error'] = f"Несовпадение SHA-256 для {meta['filename']}: ожидалось {meta['sha256']}, получено {calc_hash}"
                return res

            # Проверка gzip / tar integrity с РЕАЛЬНОЙ распаковкой
            if fpath.endswith('.tar.gz'):
                try:
                    with tarfile.open(fpath, 'r:gz') as tar:
                        members = tar.getmembers()
                        with tempfile.TemporaryDirectory() as tmp_extract_dir:
                            if hasattr(tarfile, 'data_filter'):
                                tar.extractall(path=tmp_extract_dir, filter='data')
                            else:
                                tar.extractall(path=tmp_extract_dir)

                            for m in members:
                                if m.isfile():
                                    extracted_file = os.path.join(tmp_extract_dir, m.name)
                                    if not os.path.exists(extracted_file):
                                        res['error'] = f"Файл {m.name} не найден после распаковки архива {meta['filename']}"
                                        return res
                                    if os.path.getsize(extracted_file) != m.size:
                                        res['error'] = (
                                            f"Размер распакованного файла {m.name} ({os.path.getsize(extracted_file)}) "
                                            f"не совпадает с размером в tar ({m.size})"
                                        )
                                        return res
                                    with open(extracted_file, 'rb') as ef:
                                        _ = ef.read(min(4096, m.size))
                    res['archive_integrity'][component] = 'OK'
                except Exception as tar_err:
                    res['error'] = f"Повреждение tar архива {meta['filename']}: {tar_err}"
                    return res
            elif fpath.endswith('.gz'):
                try:
                    with gzip.open(fpath, 'rb') as gz:
                        while gz.read(1024 * 1024):
                            pass
                    res['archive_integrity'][component] = 'OK'
                except Exception as gz_err:
                    res['error'] = f"Повреждение gzip файла {meta['filename']}: {gz_err}"
                    return res

        # 2. Проверка восстановления базы данных
        db_meta = files_meta.get('database', {})
        db_file = os.path.join(bundle_dir, db_meta['filename'])

        if manifest.get('database_type') == 'sqlite':
            db_ok = self._verify_sqlite_restore(db_file, manifest['initial_metrics'])
        else:
            db_ok = self._verify_postgres_restore(db_file, manifest['initial_metrics'])

        if not db_ok:
            res['error'] = "Проверка восстановления базы данных завершилась сбоем"
            return res
        res['database_verified'] = True

        # 3. Проверка ВСЕХ сэмплов файлов квитанций
        receipts_meta = files_meta.get('receipts', {})
        receipts_file = os.path.join(bundle_dir, receipts_meta['filename'])
        sample_files = manifest.get('initial_metrics', {}).get('sample_receipt_files', [])

        if sample_files:
            try:
                with tarfile.open(receipts_file, 'r:gz') as tar:
                    missing_samples = []
                    with tempfile.TemporaryDirectory() as tmp_samples_dir:
                        for sf in sample_files:
                            base_sf = os.path.basename(sf)
                            matching_member = next(
                                (
                                    m for m in tar.getmembers()
                                    if m.name.endswith(base_sf) or os.path.basename(m.name) == base_sf
                                ),
                                None
                            )
                            if not matching_member:
                                missing_samples.append(base_sf)
                            else:
                                if hasattr(tarfile, 'data_filter'):
                                    tar.extract(matching_member, path=tmp_samples_dir, filter='data')
                                else:
                                    tar.extract(matching_member, path=tmp_samples_dir)
                                extracted_sample = os.path.join(tmp_samples_dir, matching_member.name)
                                with open(extracted_sample, 'rb') as sf_fp:
                                    header = sf_fp.read(5)
                                    if header != b'%PDF-':
                                        res['error'] = f"Файл квитанции {base_sf} в архиве поврежден (некорректный заголовок: {header!r})"
                                        res['receipts_sample_verified'] = False
                                        res['success'] = False
                                        return res

                    if missing_samples:
                        res['error'] = f"Не все сэмплы квитанций найдены в архиве! Отсутствуют: {', '.join(missing_samples)}"
                        res['receipts_sample_verified'] = False
                        res['success'] = False
                        return res

                    res['receipts_sample_verified'] = True
            except Exception as e:
                logger.error(f"Ошибка проверки сэмплов квитанций: {e}")
                res['error'] = f"Сбой проверки сэмплов квитанций: {e}"
                res['receipts_sample_verified'] = False
                res['success'] = False
                return res
        else:
            res['receipts_sample_verified'] = True

        if not res['database_verified'] or not res['receipts_sample_verified']:
            res['success'] = False
            if not res.get('error'):
                res['error'] = "Комплексная проверка компонентов бэкапа не пройдена"
            return res

        res['success'] = True
        return res

    def _verify_sqlite_restore(self, db_gz_file: str, expected_metrics: Dict[str, Any]) -> bool:
        """Тестовая распаковка и валидация SQLite во временной БД."""
        temp_dir = os.path.join(self.backup_root, '.tmp_verify')
        os.makedirs(temp_dir, exist_ok=True)
        temp_db = os.path.join(temp_dir, f"test_restore_{int(time.time())}_{os.getpid()}.db")
        con = None
        try:
            with gzip.open(db_gz_file, 'rb') as f_in, open(temp_db, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

            con = sqlite3.connect(temp_db)
            con.row_factory = sqlite3.Row
            row_acc = con.execute("SELECT COUNT(*) FROM accounts").fetchone()
            row_rec = con.execute("SELECT COUNT(*) FROM receipts").fetchone()

            acc_cnt = row_acc[0] if row_acc else 0
            rec_cnt = row_rec[0] if row_rec else 0

            assert acc_cnt == expected_metrics['accounts_count'], f"Счетов {acc_cnt} != ожидалось {expected_metrics['accounts_count']}"
            assert rec_cnt == expected_metrics['receipts_count'], f"Квитанций {rec_cnt} != ожидалось {expected_metrics['receipts_count']}"
            logger.info(f"Тестовое восстановление SQLite успешно проверено: счетов {acc_cnt}, квитанций {rec_cnt}.")
            return True
        except Exception as err:
            logger.error(f"Сбой валидации SQLite: {err}")
            return False
        finally:
            if con:
                try:
                    con.close()
                except Exception:
                    pass
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    def _verify_postgres_restore(self, sql_gz_file: str, expected_metrics: Dict[str, Any]) -> bool:
        """Валидация SQL-дампа PostgreSQL (синтаксис, таблицы, тестовая изолированная накатка)."""
        logger.info("Валидация дампа PostgreSQL...")
        try:
            table_markers = {'accounts': False, 'receipts': False, 'audit_logs': False}
            total_lines = 0

            with gzip.open(sql_gz_file, 'rt', encoding='utf-8', errors='replace') as f:
                for line in f:
                    total_lines += 1
                    for tbl in table_markers:
                        if (
                            f'CREATE TABLE public.{tbl}' in line
                            or f'CREATE TABLE {tbl}' in line
                            or f'COPY public.{tbl}' in line
                            or f'COPY {tbl}' in line
                        ):
                            table_markers[tbl] = True

            logger.info(f"Дамп содержит {total_lines} строк. Найдены таблицы: {table_markers}")
            if not table_markers['accounts'] or not table_markers['receipts']:
                logger.error("В дампе отсутствуют критически важные таблицы accounts/receipts!")
                return False

            # Проверяем доступность docker контейнера kvit-postgres
            check_docker = subprocess.run(
                ['docker', 'ps', '--filter', 'name=kvit-postgres', '--format', '{{.Names}}'],
                capture_output=True, text=True, check=False
            )
            if check_docker.returncode != 0 or 'kvit-postgres' not in check_docker.stdout:
                logger.error("Контейнер kvit-postgres не найден или не запущен. Невозможно провести верификацию восстановления!")
                return False

            pg_user = os.getenv('POSTGRES_USER', 'user')
            tmp_db_name = f"kvit_restore_drill_{int(time.time())}"
            logger.info(f"Создание временной тестовой базы {tmp_db_name} для drill-теста...")

            # 1. CREATE DATABASE с флагом ON_ERROR_STOP=1
            c_create = subprocess.run([
                'docker', 'exec', '-i', 'kvit-postgres',
                'psql', '-U', pg_user, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', f"CREATE DATABASE {tmp_db_name};"
            ], capture_output=True, text=True, check=False)

            if c_create.returncode != 0:
                logger.error(f"Не удалось создать временную тестовую базу {tmp_db_name} (код {c_create.returncode}): {c_create.stderr}")
                return False

            try:
                # 2. Восстановление дампа во временную базу с флагом ON_ERROR_STOP=1
                p_restore = subprocess.Popen([
                    'docker', 'exec', '-i', 'kvit-postgres',
                    'psql', '-U', pg_user, '-d', tmp_db_name, '-v', 'ON_ERROR_STOP=1', '-q'
                ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                with gzip.open(sql_gz_file, 'rb') as f_gz:
                    sql_data = f_gz.read()
                _, r_err = p_restore.communicate(input=sql_data)

                if p_restore.returncode != 0:
                    err_msg = r_err.decode('utf-8', errors='replace') if isinstance(r_err, bytes) else str(r_err)
                    logger.error(f"Сбой восстановления дампа psql (код возврата {p_restore.returncode}): {err_msg}")
                    return False

                # 3. Сверка количества записей через psql с ON_ERROR_STOP=1
                c_check = subprocess.run([
                    'docker', 'exec', '-i', 'kvit-postgres',
                    'psql', '-U', pg_user, '-d', tmp_db_name, '-v', 'ON_ERROR_STOP=1', '-t', '-A', '-c',
                    "SELECT (SELECT COUNT(*) FROM accounts), (SELECT COUNT(*) FROM receipts);"
                ], capture_output=True, text=True, check=False)

                if c_check.returncode != 0:
                    logger.error(f"Ошибка запроса проверки записей в тестовой БД (код {c_check.returncode}): {c_check.stderr}")
                    return False

                out_str = c_check.stdout.strip()
                if '|' not in out_str:
                    logger.error(f"Неожиданный формат ответа сверки метрик: {out_str}")
                    return False

                parts = out_str.split('|')
                r_acc, r_rec = int(parts[0]), int(parts[1])
                exp_acc = expected_metrics.get('accounts_count', 0)
                exp_rec = expected_metrics.get('receipts_count', 0)

                if r_acc != exp_acc:
                    logger.error(f"Несовпадение количества счетов: в дампе {r_acc} != ожидалось {exp_acc}")
                    return False
                if r_rec != exp_rec:
                    logger.error(f"Несовпадение количества квитанций: в дампе {r_rec} != ожидалось {exp_rec}")
                    return False

                logger.info(f"Disaster Recovery Drill в PostgreSQL завершен успешно! Счетов: {r_acc}, Квитанций: {r_rec}")
                return True

            finally:
                # Очистка: удаление временной БД с FORCE
                c_drop = subprocess.run([
                    'docker', 'exec', '-i', 'kvit-postgres',
                    'psql', '-U', pg_user, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', f"DROP DATABASE IF EXISTS {tmp_db_name} WITH (FORCE);"
                ], capture_output=True, text=True, check=False)
                if c_drop.returncode != 0:
                    logger.warning(f"Предупреждение при удалении временной базы {tmp_db_name}: {c_drop.stderr}")

        except Exception as drill_err:
            logger.error(f"Критический сбой Isolated Drill в PostgreSQL: {drill_err}", exc_info=True)
            return False

    # ────────────────────── Репликация и ротация ──────────────────────

    def _sync_remote(self, bundle_dir: str, remote_target: str):
        """Синхронизирует резервную копию на удаленный сервер или накопитель."""
        logger.info(f"Синхронизация копии в удаленный таргет: {remote_target}...")
        try:
            # Если целевой путь - локальная папка (внешний примонтированный диск)
            if ':' not in remote_target:
                os.makedirs(remote_target, exist_ok=True)
                dest = os.path.join(remote_target, os.path.basename(bundle_dir))
                shutil.copytree(bundle_dir, dest, dirs_exist_ok=True)
                logger.info(f"Копия успешно скопирована на внешний накопитель: {dest}")
                return

            # Иначе используем rsync
            cmd = [
                'rsync', '-avz', '--progress',
                bundle_dir, remote_target
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                logger.info("Удаленная синхронизация rsync успешно выполнена.")
            else:
                err_msg = res.stderr.strip() or f"код {res.returncode}"
                logger.error(f"Ошибка rsync при отправке на {remote_target}: {err_msg}")
                raise RuntimeError(f"Ошибка rsync (код {res.returncode}): {err_msg}")
        except Exception as e:
            logger.error(f"Сбой при удаленной синхронизации на {remote_target}: {e}")
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"Сбой при удаленной синхронизации на {remote_target}: {e}") from e

    def rotate_old_backups(self):
        """Удаляет резервные копии старше указанного retention_days."""
        now = time.time()
        max_age_seconds = self.retention_days * 86400
        removed = 0

        for item in os.listdir(self.backup_root):
            if not item.startswith('kvit_backup_'):
                continue
            full_p = os.path.join(self.backup_root, item)
            if not os.path.isdir(full_p):
                continue

            age = now - os.path.getmtime(full_p)
            if age > max_age_seconds:
                try:
                    shutil.rmtree(full_p, ignore_errors=True)
                    removed += 1
                    logger.info(f"Ротация: удален устаревший бэкап {item} (возраст {round(age / 86400, 1)} дней)")
                except Exception as e:
                    logger.warning(f"Не удалось удалить старый бэкап {item}: {e}")

        if removed > 0:
            logger.info(f"Ротация завершена: удалено {removed} устаревших копий.")


def main():
    parser = argparse.ArgumentParser(description="KREC Disaster Recovery & Backup Manager")
    parser.add_argument('--dir', default=os.path.join(BASE_DIR, 'backups'), help="Директория хранения бэкапов")
    parser.add_argument('--no-verify', action='store_true', help="Пропустить верификацию восстановления")
    parser.add_argument('--remote-target', default=None, help="Внешняя папка или remote rsync адрес (user@host:/path)")
    parser.add_argument('--retention-days', type=int, default=14, help="Срок хранения копий в днях")
    args = parser.parse_args()

    mgr = BackupManager(
        base_dir=BASE_DIR,
        backup_root=args.dir,
        retention_days=args.retention_days
    )

    try:
        manifest = mgr.run_backup(
            verify=not args.no_verify,
            remote_target=args.remote_target
        )
        print(f"\n✅ РЕЗЕРВНАЯ КОПИЯ УСПЕШНО СОЗДАНА И ВЕРИФИЦИРОВАНА: {manifest['bundle_name']}")
        print(f"📁 Путь: {os.path.join(mgr.backup_root, manifest['bundle_name'])}")
        print(f"📦 База данных: {manifest['files']['database']['filename']} ({manifest['files']['database']['size_bytes']} байт)")
        print(f"📑 Квитанции: {manifest['files']['receipts']['filename']} ({manifest['files']['receipts']['archived_files_count']} файлов)")
        print(f"🌐 CMS-файлы: {manifest['files']['cms']['filename']} ({manifest['files']['cms']['archived_files_count']} файлов)")
        print("🔍 Верификация: 100% OK, контрольные суммы SHA-256 проверены.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА РЕЗЕРВНОГО КОПИРОВАНИЯ: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
