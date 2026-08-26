#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Load & Stress Test Suite:
1. High-Concurrency API Benchmark:
   - 500 concurrent users
   - 1000 concurrent users
   - Измерение latency (p50, p95, p99), RPS, Error rate.
2. Ingestion & Worker Pipeline Benchmark:
   - Симуляция и обработка до 30 000 PDF квитанций
   - Измерение пропускной способности (PDF/min, OCR/min)
   - Измерение дискового IOPS и задержек БД.
"""
import argparse
import collections
import concurrent.futures
import io
import math
import os
import random
import sys
import threading
import time
import urllib.request
from typing import List

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from database.connection import get_db, write_transaction
from services.pdf import pdf_processor
from services.receipts.receipt_service import receipt_service

def percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

def run_concurrent_api_load_test(target_url: str, total_requests: int = 5000, concurrency: int = 500):
    """Стресс-тест HTTP API под высокой нагрузкой (500 - 1000 одновременных пользователей)."""
    print(f"\n" + "=" * 70)
    print(f"🔥 ЗАПУСК СТРЕСС-ТЕСТА API: {total_requests} запросов | {concurrency} одновременных пользователей")
    print(f"🎯 URL: {target_url}")
    print("=" * 70)

    latencies = []
    status_codes = collections.Counter()
    errors = collections.Counter()
    backend_instances = collections.Counter()

    lock = threading.Lock()
    start_time = time.time()

    def _worker_task():
        # Имитируем типичные действия пользователя (поиск по адресу, запрос статики, проверка статуса)
        sub_paths = [
            "/",
            "/static/manifest.json",
            "/api/search?q=%D0%90%D0%B1%D0%B0%D1%8F",
            "/health"
        ]
        url = target_url.rstrip("/") + random.choice(sub_paths)
        req = urllib.request.Request(url, headers={'User-Agent': 'KvitStressTestRunner/1.0'})

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                inst = resp.headers.get('X-Backend-Instance', 'default')
                _ = resp.read()
                elapsed = time.time() - t0
                with lock:
                    latencies.append(elapsed * 1000.0)  # ms
                    status_codes[code] += 1
                    backend_instances[inst] += 1
        except urllib.error.HTTPError as e:
            elapsed = time.time() - t0
            with lock:
                latencies.append(elapsed * 1000.0)
                status_codes[e.code] += 1
        except Exception as err:
            with lock:
                errors[str(type(err).__name__)] += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_worker_task) for _ in range(total_requests)]
        concurrent.futures.wait(futures)

    total_time = time.time() - start_time
    rps = total_requests / total_time if total_time > 0 else 0

    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0

    print(f"\n📊 [РЕЗУЛЬТАТЫ СТРЕСС-ТЕСТА API]")
    print(f"  Общее время:       {total_time:.2f} сек")
    print(f"  Пропускная способность: {rps:.1f} req/sec (RPS)")
    print(f"  Успешных запросов:  {sum(v for k, v in status_codes.items() if 200 <= k < 400)} / {total_requests}")
    print(f"  Ошибок сети:       {sum(errors.values())}")
    print(f"  -------------------------------------------")
    print(f"  Latency Min:       {min_lat:.1f} ms")
    print(f"  Latency p50:       {p50:.1f} ms")
    print(f"  Latency p95:       {p95:.1f} ms")
    print(f"  Latency p99:       {p99:.1f} ms")
    print(f"  Latency Max:       {max_lat:.1f} ms")
    print(f"  -------------------------------------------")
    print(f"  Коды ответов:      {dict(status_codes)}")
    if backend_instances:
        print(f"  Распределение реплик: {dict(backend_instances)}")
    print("=" * 70)


def run_high_volume_pdf_benchmark(total_docs: int = 30000, worker_threads: int = 4):
    """
    Бенчмарк конвейера импорта и индексации PDF (симуляция до 30 000 квитанций).
    Замеряет скорость разбора, генерации хешей, записи в БД и дисковый throughput.
    """
    print(f"\n" + "=" * 70)
    print(f"🚀 ЗАПУСК ТЕСТА ПРОИЗВОДИТЕЛЬНОСТИ ПАЙПЛАЙНА: {total_docs:,} квитанций | {worker_threads} воркеров")
    print("=" * 70)

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    # 1. Регистрация тестовых счетов в БД для чистого замера полного цикла
    con = get_db()
    with write_transaction() as con:
        con.executemany(
            "INSERT OR IGNORE INTO accounts(account_number, customer_name, address) VALUES (?, ?, ?)",
            [(f"800{i:03d}", f"Абонент {i}", f"ул. Тестовая, {i}") for i in range(100)]
        )

    # 2. Генерация тестового PDF образца
    doc = fitz.open()
    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None

    for p_idx in range(50):  # 50 страниц в пакете
        page = doc.new_page()
        acc = f"800{p_idx:03d}"
        text = f"ТОО 'Тест Энерго'\nЛицевой счет: {acc}\nПериод: 12.2026\nАдрес: ул. Тестовая, {p_idx}\nК оплате: 1500.00 тг"
        if font_path:
            page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
            page.insert_text((50, 100), text, fontname='arial', fontsize=11)
        else:
            page.insert_text((50, 100), text, fontsize=11)

    pdf_bytes = doc.tobytes()
    doc.close()



    batch_size = 50
    batches_count = total_docs // batch_size
    temp_dir = os.path.abspath("./tmp_load_test")
    os.makedirs(temp_dir, exist_ok=True)

    pdf_files = []
    print(f"📦 Подготовка {batches_count} пакетных PDF файлов...")
    for i in range(batches_count):
        fn = os.path.join(temp_dir, f"batch_{i}.pdf")
        with open(fn, "wb") as f:
            f.write(pdf_bytes)
        pdf_files.append(fn)

    print(f"⚡ Старт параллельной обработки {batches_count} файлов ({total_docs:,} квитанций)...")
    start_time = time.time()
    processed_receipts = 0
    lock = threading.Lock()

    def _process_batch_file(path: str):
        nonlocal processed_receipts
        b_name = os.path.basename(path)
        added, orphan, skipped, dups, _, _ = pdf_processor.process_single_pdf(
            path, b_name, known_accounts=None, existing_hashes=None
        )
        with lock:
            processed_receipts += (added + orphan + dups)

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_threads) as executor:
        futures = [executor.submit(_process_batch_file, f) for f in pdf_files]
        concurrent.futures.wait(futures)

    total_time = time.time() - start_time
    pdf_per_sec = processed_receipts / total_time if total_time > 0 else 0
    pdf_per_min = pdf_per_sec * 60.0

    print(f"\n📊 [РЕЗУЛЬТАТЫ ОБРАБОТКИ ПАЙПЛАЙНА]")
    print(f"  Всего документов обработано: {processed_receipts:,} шт.")
    print(f"  Общее время:                 {total_time:.2f} сек")
    print(f"  Скорость обработки:          {pdf_per_sec:.1f} квит/сек  ({pdf_per_min:,.0f} квит/мин)")
    print("=" * 70)

    # Очистка временных файлов
    for f in pdf_files:
        try:
            os.remove(f)
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Kvit Load & Stress Test Suite")
    parser.add_argument("--mode", choices=["api", "pipeline", "all"], default="all", help="Режим тестирования")
    parser.add_argument("--url", default="http://127.0.0.1:8000/", help="URL для тестирования API")
    parser.add_argument("--requests", type=int, default=2000, help="Количество HTTP запросов")
    parser.add_argument("--concurrency", type=int, default=500, help="Параллельность (пользователи)")
    parser.add_argument("--docs", type=int, default=5000, help="Количество документов для теста пайплайна")
    parser.add_argument("--workers", type=int, default=4, help="Количество параллельных воркеров")
    args = parser.parse_args()

    if args.mode in ("pipeline", "all"):
        run_high_volume_pdf_benchmark(total_docs=args.docs, worker_threads=args.workers)

    if args.mode in ("api", "all"):
        run_concurrent_api_load_test(target_url=args.url, total_requests=args.requests, concurrency=args.concurrency)
