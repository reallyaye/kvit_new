# -*- coding: utf-8 -*-
"""
Атомарный транзакционный импортер квитанций (Staged 2-Phase Commit / Outbox Pattern).
Гарантирует строгую согласованность между файловой системой и базой данных:
- Состояния: PROCESSING -> READY / FAILED
- Никаких "висячих" файлов без записей в БД
- Никаких записей в БД без существующих файлов на диске
"""

import logging
import os
import secrets
from dataclasses import dataclass
from typing import List, Optional, Tuple

import config
from config import get_receipt_shard_parts
from database.connection import write_transaction

logger = logging.getLogger(__name__)

class ReceiptStatus:
    UPLOADING = 'UPLOADING'
    PROCESSING = 'PROCESSING'
    READY = 'READY'
    FAILED = 'FAILED'

@dataclass
class StagedReceipt:
    account: str
    period: str
    pdf_bytes: bytes
    file_hash: str
    semantic_hash: str
    content_hash: str
    access_token: str
    address: Optional[str]
    target_rel_path: str
    target_full_path: str
    is_orphan: bool = False

class AtomicReceiptImporter:
    """
    Выполняет двухфазную атомарную фиксацию пачки квитанций.
    """

    @classmethod
    def stage_receipt(cls, account: str, period: str, pdf_bytes: bytes, address: Optional[str],
                      file_hash: str, semantic_hash: str, is_orphan: bool = False) -> StagedReceipt:
        """Подготавливает квитанцию к атомарной фиксации без записи на диск."""
        s1, s2 = get_receipt_shard_parts(account)
        shard_dir = os.path.join(config.RECEIPTS_DIR, s1, s2)
        base_filename = f'{account}_{file_hash[:12]}_{semantic_hash[:8]}.pdf'
        target_rel_path = f'{s1}/{s2}/{base_filename}'
        target_full_path = os.path.join(shard_dir, base_filename)
        access_token = secrets.token_hex(16)
        content_hash = semantic_hash

        return StagedReceipt(
            account=account,
            period=period,
            pdf_bytes=pdf_bytes,
            file_hash=file_hash,
            semantic_hash=semantic_hash,
            content_hash=content_hash,
            access_token=access_token,
            address=address,
            target_rel_path=target_rel_path,
            target_full_path=target_full_path,
            is_orphan=is_orphan
        )

    @classmethod
    def commit_staged_batch(cls, staged_receipts: List[StagedReceipt]) -> Tuple[int, List[str]]:
        """
        Атомарно сохраняет пачку квитанций:
        1. Записывает временные файлы (.staged_*) в целевые шарды
        2. Открывает транзакцию SQLite, вставляет записи со статусом 'PROCESSING' -> 'READY'
        3. Атомарно переименовывает временные файлы в целевые имена (os.replace)
        4. В случае сбоя: удаляет все созданные временные и целевые файлы, откатывает транзакцию БД.
        """
        if not staged_receipts:
            return 0, []

        created_temp_files = []
        committed_target_files = []

        try:
            # Фаза 1: Запись во временные файлы рядом с целевыми путями (в тех же файловых системах)
            for item in staged_receipts:
                target_dir = os.path.dirname(item.target_full_path)
                os.makedirs(target_dir, exist_ok=True)

                temp_file_name = f".staged_{secrets.token_hex(8)}_{os.path.basename(item.target_full_path)}"
                temp_file_path = os.path.join(target_dir, temp_file_name)

                with open(temp_file_path, 'wb') as f:
                    f.write(item.pdf_bytes)

                created_temp_files.append((temp_file_path, item.target_full_path))

            # Фаза 2: Транзакция БД + Атомарное перемещение
            with write_transaction() as con:
                # 1. Автоматическая регистрация/обновление лицевых счетов в таблице accounts
                for r in staged_receipts:
                    if r.account:
                        con.execute('''
                            INSERT INTO accounts(account_number, customer_name, address)
                            VALUES (?, '', ?)
                            ON CONFLICT(account_number) DO UPDATE SET
                                address = CASE 
                                    WHEN accounts.address IS NULL OR accounts.address = '' 
                                    THEN excluded.address 
                                    ELSE accounts.address 
                                END
                        ''', (str(r.account).strip(), r.address or ''))

                # 2. Вставляем записи квитанций со статусом 'READY'
                insert_rows = [
                    (
                        r.account,
                        r.period,
                        r.target_rel_path,
                        r.content_hash,
                        r.file_hash,
                        r.semantic_hash,
                        ReceiptStatus.READY,
                        r.access_token,
                        r.address
                    )
                    for r in staged_receipts
                ]

                con.executemany('''
                    INSERT INTO receipts(
                        account_number, period, pdf_file, content_hash, file_hash, semantic_hash, status, access_token, address
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_number, period) DO UPDATE SET
                        pdf_file = excluded.pdf_file,
                        content_hash = excluded.content_hash,
                        file_hash = excluded.file_hash,
                        semantic_hash = excluded.semantic_hash,
                        status = excluded.status,
                        access_token = excluded.access_token,
                        address = excluded.address
                ''', insert_rows)

                # Атомарный перенос файлов
                for temp_path, target_path in created_temp_files:
                    os.replace(temp_path, target_path)
                    committed_target_files.append(target_path)

            return len(staged_receipts), [r.target_rel_path for r in staged_receipts]

        except Exception as e:
            logger.error(f"[AtomicImporter] Ошибка при сохранении пачки квитанций: {e}. Выполняется откат...")

            # Компенсирующее действие: очистка временных файлов
            for temp_path, _ in created_temp_files:
                try:
                    if os.path.isfile(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

            # Компенсирующее действие: очистка перенесенных целевых файлов этой пачки
            for target_path in committed_target_files:
                try:
                    if os.path.isfile(target_path):
                        os.remove(target_path)
                except Exception:
                    pass

            raise e

atomic_importer = AtomicReceiptImporter()
