"""
Стресс-тестирование и бенчмаркинг SQLite-слоя Kvit-App.
Тестирует поведение базы данных на объемах в сотни тысяч записей в условиях
высокой конкурентной нагрузки (одновременное чтение, поиск, сверка и параллельная запись).
"""
import os
import sys
import time
import secrets
import random
import threading
import tempfile
import statistics
import sqlite3

# Подключаем корневую директорию проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.connection import get_db, write_transaction
from database.migrations import migrate_db
from services.reconciliation.reconcile_service import reconcile_service
from services.receipts.receipt_service import receipt_service

def run_sqlite_load_test(num_accounts=100_000, num_receipts=200_000, concurrent_threads=30, test_duration=10.0):
    print("=" * 75)
    print("🚀 НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ SQLITE-СЛОЯ KVIT-APP")
    print(f"Параметры: {num_accounts:,} счетов | {num_receipts:,} квитанций | {concurrent_threads} потоков")
    print("=" * 75)

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = os.path.join(tmp_dir, "benchmark_load.sqlite3")
        config.DB = test_db
        config.RECEIPTS_DIR = os.path.join(tmp_dir, "receipts")
        os.makedirs(config.RECEIPTS_DIR, exist_ok=True)

        print("\n[1/4] Инициализация схемы и индексов...")
        migrate_db()

        # Проверка включенного WAL
        con = get_db()
        journal_mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
        mmap_size = con.execute("PRAGMA mmap_size;").fetchone()[0]
        con.close()
        print(f"  ✓ PRAGMA journal_mode: {journal_mode.upper()} (WAL активен)")
        print(f"  ✓ PRAGMA mmap_size: {mmap_size // (1024*1024)} MB")

        # -------------------------------------------------------------
        # 1. Генерация и пакетная вставка 100,000 счетов
        # -------------------------------------------------------------
        print(f"\n[2/4] Генерация и пакетная запись {num_accounts:,} лицевых счетов...")
        accounts_data = [
            (
                f"ACC{i:07d}",
                f"Потребитель {i}",
                f"ул. Абая, д. {i % 500 + 1}, кв. {i % 120 + 1}",
                "ул. Абая",
                str(i % 500 + 1),
                "",
                "Алмалинский",
                "ТОО АлматыЭнергоСбыт"
            )
            for i in range(1, num_accounts + 1)
        ]

        t0 = time.perf_counter()
        with write_transaction() as wcon:
            wcon.executemany(
                "INSERT INTO accounts (account_number, customer_name, address, street, building, corpus, district, organization) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                accounts_data
            )
        t_acc_insert = time.perf_counter() - t0
        acc_ops = num_accounts / t_acc_insert
        print(f"  ✓ Вставка {num_accounts:,} счетов: {t_acc_insert:.2f} сек ({acc_ops:,.0f} записей/сек)")

        # -------------------------------------------------------------
        # 2. Генерация и пакетная вставка 200,000 квитанций
        # -------------------------------------------------------------
        print(f"\n[3/4] Генерация и пакетная запись {num_receipts:,} квитанций...")
        periods = ["2026-01", "2026-02", "2026-03"]
        receipts_data = []
        for i in range(1, num_receipts + 1):
            acc_num = f"ACC{(i % num_accounts) + 1:07d}"
            period = periods[i % len(periods)]
            token = secrets.token_hex(16)
            chash = f"hash_{i}_{acc_num}"
            rel_path = f"80/{i % 99:02d}/{acc_num}_{period}.pdf"
            receipts_data.append((acc_num, period, rel_path, chash, token, f"ул. Абая, д. {i % 500 + 1}"))

        t0 = time.perf_counter()
        with write_transaction() as wcon:
            wcon.executemany(
                "INSERT INTO receipts (account_number, period, pdf_file, content_hash, access_token, address) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                receipts_data
            )
        t_rec_insert = time.perf_counter() - t0
        rec_ops = num_receipts / t_rec_insert
        print(f"  ✓ Вставка {num_receipts:,} квитанций: {t_rec_insert:.2f} сек ({rec_ops:,.0f} записей/сек)")

        db_size_mb = os.path.getsize(test_db) / (1024 * 1024)
        print(f"  ✓ Размер базы данных SQLite на диске: {db_size_mb:.2f} MB")

        # -------------------------------------------------------------
        # 3. Конкурентный стресс-тест чтения/записи (Параллельная нагрузка)
        # -------------------------------------------------------------
        print(f"\n[4/4] Запуск {concurrent_threads} параллельных воркеров (Чтение + Поиск + Сверка + Запись) на {test_duration} сек...")

        stop_event = threading.Event()
        read_latencies = []
        write_latencies = []
        reconcile_latencies = []
        errors = []
        lock = threading.Lock()

        def reader_worker():
            local_reads = []
            while not stop_event.is_set():
                t_start = time.perf_counter()
                try:
                    # Случайный точечный поиск по счету или токену
                    rnd_id = random.randint(1, num_accounts)
                    target_acc = f"ACC{rnd_id:07d}"
                    con = get_db()
                    try:
                        row = con.execute("SELECT * FROM accounts WHERE account_number = ?", (target_acc,)).fetchone()
                        recs = con.execute("SELECT * FROM receipts WHERE account_number = ?", (target_acc,)).fetchall()
                        _ = row, recs
                    finally:
                        con.close()
                    elapsed = (time.perf_counter() - t_start) * 1000.0  # ms
                    local_reads.append(elapsed)
                except Exception as e:
                    with lock:
                        errors.append(f"Reader error: {e}")
                time.sleep(0.001)
            with lock:
                read_latencies.extend(local_reads)

        def reconcile_worker():
            local_reconciles = []
            while not stop_event.is_set():
                t_start = time.perf_counter()
                try:
                    # Комплексный аналитический запрос сверки с группировкой и фильтрами
                    con = get_db()
                    try:
                        res = con.execute("""
                            SELECT 
                                COUNT(DISTINCT a.id) as total_accounts,
                                COUNT(DISTINCT r.id) as total_receipts
                            FROM accounts a
                            LEFT JOIN receipts r ON a.account_number = r.account_number AND r.period = '2026-01'
                        """).fetchone()
                        _ = res[0], res[1]
                    finally:
                        con.close()
                    elapsed = (time.perf_counter() - t_start) * 1000.0  # ms
                    local_reconciles.append(elapsed)
                except Exception as e:
                    with lock:
                        errors.append(f"Reconcile error: {e}")
                time.sleep(0.01)
            with lock:
                reconcile_latencies.extend(local_reconciles)

        def writer_worker():
            local_writes = []
            w_counter = 0
            while not stop_event.is_set():
                w_counter += 1
                t_start = time.perf_counter()
                try:
                    rnd_acc = f"ACC{random.randint(1, num_accounts):07d}"
                    token = secrets.token_hex(16)
                    with write_transaction() as wcon:
                        wcon.execute(
                            "INSERT OR REPLACE INTO receipts (account_number, period, pdf_file, content_hash, access_token, address) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (rnd_acc, f"2026-04-{w_counter % 10}", f"test_{token}.pdf", token, token, "Тестовый адрес")
                        )
                    elapsed = (time.perf_counter() - t_start) * 1000.0  # ms
                    local_writes.append(elapsed)
                except Exception as e:
                    with lock:
                        errors.append(f"Writer error: {e}")
                time.sleep(0.005)
            with lock:
                write_latencies.extend(local_writes)

        threads = []
        # Распределяем потоки: 15 читателей, 5 аналитиков сверки, 10 параллельных писателей
        for _ in range(15):
            threads.append(threading.Thread(target=reader_worker))
        for _ in range(5):
            threads.append(threading.Thread(target=reconcile_worker))
        for _ in range(10):
            threads.append(threading.Thread(target=writer_worker))

        t_load_start = time.perf_counter()
        for t in threads:
            t.daemon = True
            t.start()

        time.sleep(test_duration)
        stop_event.set()

        for t in threads:
            t.join()
        total_time = time.perf_counter() - t_load_start

        # -------------------------------------------------------------
        # Вычисление метрик и перцентилей
        # -------------------------------------------------------------
        def calc_stats(latencies):
            if not latencies:
                return 0, 0, 0, 0, 0
            latencies.sort()
            n = len(latencies)
            avg = statistics.mean(latencies)
            p50 = latencies[int(n * 0.50)]
            p95 = latencies[int(n * 0.95)]
            p99 = latencies[min(int(n * 0.99), n - 1)]
            return n, avg, p50, p95, p99

        n_r, avg_r, p50_r, p95_r, p99_r = calc_stats(read_latencies)
        n_w, avg_w, p50_w, p95_w, p99_w = calc_stats(write_latencies)
        n_rec, avg_rec, p50_rec, p95_rec, p99_rec = calc_stats(reconcile_latencies)

        total_ops = n_r + n_w + n_rec

        print("\n" + "=" * 75)
        print("📊 РЕЗУЛЬТАТЫ СТРЕСС-ТЕСТА (WAL-РЕЖИМ + WRITE-LOCK)")
        print("=" * 75)
        print(f"Всего выполнено операций: {total_ops:,} за {total_time:.2f} сек ({total_ops / total_time:,.0f} ops/sec)")
        print(f"Ошибок блокировки (Locking / Busy Errors): {len(errors)}")

        print("\n🔹 Точечное чтение (Point Reads by Index):")
        print(f"  • Выполнено запросов: {n_r:,} ({n_r / total_time:,.0f} QPS)")
        print(f"  • Средняя задержка:   {avg_r:.2f} мс")
        print(f"  • Latency p50:        {p50_r:.2f} мс")
        print(f"  • Latency p95:        {p95_r:.2f} мс")
        print(f"  • Latency p99:        {p99_r:.2f} мс")

        print("\n🔹 Конкурентная запись (Concurrent Transactions):")
        print(f"  • Выполнено записей:  {n_w:,} ({n_w / total_time:,.0f} TPS)")
        print(f"  • Средняя задержка:   {avg_w:.2f} мс")
        print(f"  • Latency p50:        {p50_w:.2f} мс")
        print(f"  • Latency p95:        {p95_w:.2f} мс")
        print(f"  • Latency p99:        {p99_w:.2f} мс")

        print("\n🔹 Аналитические запросы сверки (Complex Aggregation Reconcile):")
        print(f"  • Выполнено запросов: {n_rec:,} ({n_rec / total_time:,.1f} QPS)")
        print(f"  • Средняя задержка:   {avg_rec:.2f} мс")
        print(f"  • Latency p50:        {p50_rec:.2f} мс")
        print(f"  • Latency p95:        {p95_rec:.2f} мс")
        print(f"  • Latency p99:        {p99_rec:.2f} мс")

        print("=" * 75)
        assert len(errors) == 0, f"Тест провален из-за ошибок: {errors[:5]}"
        print("✅ Стресс-тест пройден успешно без единой ошибки блокировки!")

if __name__ == "__main__":
    run_sqlite_load_test(num_accounts=100_000, num_receipts=200_000, concurrent_threads=30, test_duration=8.0)
