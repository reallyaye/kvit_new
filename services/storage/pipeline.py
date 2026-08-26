# -*- coding: utf-8 -*-
"""
Модуль конвейера хранения файлов (Storage Pipeline).
Обеспечивает четкое разделение жизненного цикла файлов:
incoming (spool) → processing → receipts (final sharded storage) / failed (quarantine).
Гарантирует изоляцию, атомарность и защиту от потери данных при падении серверов/воркеров.
"""
import hashlib
import json
import logging
import os
import shutil
import time
from typing import Dict, Optional, Tuple

import config
from config import FAILED_DIR, PROCESSING_DIR, RECEIPTS_DIR, SPOOL_DIR, get_receipt_shard_parts

logger = logging.getLogger(__name__)


class StoragePipeline:
    """Менеджер конвейера хранения файлов PDF."""

    def __init__(self):
        self._ensure_directories()

    def _ensure_directories(self):
        for path in (SPOOL_DIR, PROCESSING_DIR, FAILED_DIR, RECEIPTS_DIR):
            os.makedirs(path, exist_ok=True)

    @staticmethod
    def compute_file_sha256(file_path: str) -> str:
        """Вычисляет криптографический SHA-256 хеш файла потоково (блоками 64 KB)."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def prepare_job_spool(self, job_id: str) -> str:
        """Создает изолированную директорию спула для конкретной задачи."""
        job_dir = os.path.join(SPOOL_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        return job_dir

    def prepare_job_processing(self, job_id: str) -> str:
        """Создает изолированную директорию активной обработки для задачи."""
        proc_dir = os.path.join(PROCESSING_DIR, job_id)
        os.makedirs(proc_dir, exist_ok=True)
        return proc_dir

    def move_to_processing(self, source_path: str, job_id: str, base_name: str) -> str:
        """
        Перемещает файл из входящего спула в директорию активной обработки.
        Возвращает новый абсолютный путь к файлу.
        """
        proc_dir = self.prepare_job_processing(job_id)
        target_path = os.path.join(proc_dir, base_name)

        if os.path.abspath(source_path) == os.path.abspath(target_path):
            return target_path

        # Если файл находится на том же диске, os.replace выполнит атомарный перенос
        try:
            os.replace(source_path, target_path)
        except OSError:
            shutil.copy2(source_path, target_path)
            try:
                os.unlink(source_path)
            except OSError:
                pass

        return target_path

    def commit_to_receipts(self, staged_file_path: str, account: str, final_filename: str) -> Tuple[str, str]:
        """
        Атомарно фиксирует готовый PDF-файл в шардированное постоянное хранилище receipts/{s1}/{s2}/...
        Возвращает: (относительный_путь_в_POSIX, абсолютный_путь_на_диске).
        """
        s1, s2 = get_receipt_shard_parts(account)
        shard_dir = os.path.join(RECEIPTS_DIR, s1, s2)
        os.makedirs(shard_dir, exist_ok=True)

        final_full_path = os.path.join(shard_dir, final_filename)
        final_rel_path = f"{s1}/{s2}/{final_filename}"

        # Атомарная замена/перемещение
        try:
            os.replace(staged_file_path, final_full_path)
        except OSError:
            shutil.copy2(staged_file_path, final_full_path)
            try:
                os.unlink(staged_file_path)
            except OSError:
                pass

        return final_rel_path, final_full_path

    def quarantine_failed(self, file_path: str, job_id: str, base_name: str, error_message: str) -> str:
        """
        Перемещает поврежденный или ошибочный файл в карантин (FAILED_DIR)
        и сохраняет рядом метаданные об ошибке (.meta.json).
        """
        failed_job_dir = os.path.join(FAILED_DIR, job_id)
        os.makedirs(failed_job_dir, exist_ok=True)

        target_file_path = os.path.join(failed_job_dir, base_name)
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, target_file_path)
        except Exception as e:
            logger.warning(f"[StoragePipeline] Не удалось переместить {file_path} в карантин: {e}")
            target_file_path = file_path

        # Записываем метаданные сбоя
        meta_path = f"{target_file_path}.meta.json"
        try:
            with open(meta_path, 'w', encoding='utf-8') as mf:
                json.dump({
                    'job_id': job_id,
                    'file_name': base_name,
                    'failed_at': time.time(),
                    'error': error_message
                }, mf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return target_file_path

    def cleanup_job(self, job_id: str):
        """Очищает временные директории спула и обработки для завершенной задачи."""
        for base_dir in (SPOOL_DIR, PROCESSING_DIR):
            job_dir = os.path.join(base_dir, job_id)
            if os.path.exists(job_dir):
                try:
                    shutil.rmtree(job_dir, ignore_errors=True)
                except Exception as e:
                    logger.debug(f"[StoragePipeline] Ошибка очистки директории {job_dir}: {e}")


storage_pipeline = StoragePipeline()
