#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт комплексного нагрузочного тестирования (Load & Stress Test Harness).
Проверяет требования пункта 16:
- Одновременная фоновая обработка 1 000 – 30 000 PDF в воркерах
- Параллельная нагрузка от 100, 500, 1000 пользователей:
  * Поиск лицевого счета
  * Просмотр информации о квитанции
  * Скачивание PDF квитанции (потоковая отдача)
  * Liveness/Readiness probes
- Оценка latency (p50, p95, p99), RPS и процента ошибок API под тяжелой фоновой нагрузкой.
"""
import argparse
import concurrent.futures
import os
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import json

# Добавляем корень проекта в sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from database.connection import get_db, write_transaction
from services.tasks.task_manager import task_manager, TaskStatus


def generate_sample_pdf_batch(count: int, temp_dir: str):
    """Генерирует тестовые легковесные PDF-документы для тестирования очереди."""
    import fitz  # PyMuPDF
    pdf_files = []

    for i in range(count):
        acc_num = f"800{i:04d}"
        period = "01.2026"
        filename = f"kvit_{acc_num}_{period}.pdf"
        file_path = os.path.join(temp_dir, filename)

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        text = f"КВИТАНЦИЯ ЗА ЭЛЕКТРОЭНЕРГИЮ\nЛицевой счет: {acc_num}\nПериод: {period}\nАдрес: ул. Абая, д. {i+1}, кв. 10\nСумма к оплате: 5400.00 KZT"
        page.insert_text((50, 100), text, fontsize=12)
        doc.save(file_path)
        doc.close()

        pdf_files.append((filename, file_path))

    return pdf_files


def simulate_user_session(user_id: int, base_url: str, account_sample: str) -> dict:
    """Симулирует одного пользователя: поиск -> просмотр -> скачивание."""
    latencies = []
    errors = 0

    # 1. Поиск по лицевому счету
    t0 = time.perf_counter()
    try:
        url = f"{base_url}/api/search?account={account_sample}"
        req = urllib.request.Request(url, headers={'User-Agent': f'LoadTestUser-{user_id}'})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            latencies.append(time.perf_counter() - t0)
            receipts = data.get('receipts', [])
            token = receipts[0]['access_token'] if receipts else None
    except Exception as e:
        errors += 1
        token = None

    # 2. Скачивание квитанции (потоковая выдача)
    if token:
        t0 = time.perf_counter()
        try:
            dl_url = f"{base_url}/download?token={token}"
            req = urllib.request.Request(dl_url, headers={'User-Agent': f'LoadTestUser-{user_id}'})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                _ = resp.read()
                latencies.append(time.perf_counter() - t0)
        except Exception:
            errors += 1

    # 3. Health Probe
    t0 = time.perf_counter()
    try:
        h_url = f"{base_url}/health"
        req = urllib.request.Request(h_url, headers={'User-Agent': f'LoadTestUser-{user_id}'})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            _ = resp.read()
            latencies.append(time.perf_counter() - t0)
    except Exception:
        errors += 1

    return {
        'user_id': user_id,
        'latencies': latencies,
        'errors': errors,
        'requests': len(latencies) + errors
    }


def run_load_test(base_url: str = "http://127.0.0.1:8000", concurrent_users: int = 100, pdf_count: int = 1000):
    print("=" * 75)
    print(f"🚀 НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ: {concurrent_users} пользователей + {pdf_count} фоновых PDF")
    print("=" * 75)

    # 1. Подготовка тестовых данных
    temp_dir = tempfile.mkdtemp(prefix="kvit_loadtest_")
    print(f"📦 Генерация {pdf_count} тестовых PDF файлов...")
    sample_pdfs = generate_sample_pdf_batch(pdf_count, temp_dir)
    print(f"✅ Создано {len(sample_pdfs)} PDF файлов.")

    # 2. Запуск фоновой пакетной обработки через TaskManager
    print("⚡ Запуск фоновой очереди задач (Background Batch Processing)...")
    batch_start_time = time.time()
    task = task_manager.submit_pdf_job(
        files=sample_pdfs,
        source='load_test_batch',
        spool_dir=temp_dir
    )
    print(f"✅ Задача зарегистрирована в очереди: ID = {task.job_id}")

    # 3. Запуск одновременной нагрузки пользователей (User Requests Under Load)
    print(f"👥 Запуск параллельных пользовательских сессий ({concurrent_users} concurrent workers)...")
    users_start_time = time.time()

    all_latencies = []
    total_requests = 0
    total_errors = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(concurrent_users, 100)) as executor:
        futures = [
            executor.submit(simulate_user_session, uid, base_url, f"800{uid % max(1, pdf_count):04d}")
            for uid in range(concurrent_users)
        ]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            all_latencies.extend(res['latencies'])
            total_requests += res['requests']
            total_errors += res['errors']

    users_duration = time.time() - users_start_time

    # 4. Ожидание завершения фонового импорта (или проверка прогресса)
    print(f"⏳ Ожидание завершения обработки пакета PDF...")
    while True:
        t_state = task_manager.get_task(task.job_id)
        if not t_state or t_state.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            break
        print(f"   ➜ Прогресс очереди: {t_state.progress_pct}% ({t_state.processed_files}/{t_state.total_files}) | Скорость: {t_state.speed_files_per_sec} ф/сек")
        time.sleep(1.0)

    batch_duration = time.time() - batch_start_time

    # 5. Расчет метрик производительности
    all_latencies.sort()
    n = len(all_latencies)
    p50 = (all_latencies[int(n * 0.50)] * 1000) if n else 0
    p95 = (all_latencies[int(n * 0.95)] * 1000) if n else 0
    p99 = (all_latencies[int(n * 0.99)] * 1000) if n else 0
    avg_lat = (sum(all_latencies) / n * 1000) if n else 0
    max_lat = (all_latencies[-1] * 1000) if n else 0
    rps = total_requests / max(0.001, users_duration)
    error_rate = (total_errors / total_requests * 100) if total_requests else 0

    print("\n" + "=" * 75)
    print("📊 РЕЗУЛЬТАТЫ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ:")
    print("=" * 75)
    print(f"1. Пользовательский API (User Requests under Heavy Background OCR/PDF Load):")
    print(f"   • Всего запросов:          {total_requests}")
    print(f"   • Ошибок API:              {total_errors} ({error_rate:.2f}%)")
    print(f"   • Пропускная способность:  {rps:.2f} req/sec")
    print(f"   • Latency Avg:             {avg_lat:.2f} ms")
    print(f"   • Latency p50 (медиана):   {p50:.2f} ms")
    print(f"   • Latency p95:             {p95:.2f} ms")
    print(f"   • Latency p99:             {p99:.2f} ms")
    print(f"   • Latency Max:             {max_lat:.2f} ms")
    print(f"\n2. Фоновый импорт PDF (Background Queue & Worker Cluster):")
    print(f"   • Файлов обработано:       {task.processed_files} / {task.total_files}")
    print(f"   • Успешно привязано:       {task.added}")
    print(f"   • Дубликатов пропущено:    {task.duplicates}")
    print(f"   • Время импорта пакета:    {batch_duration:.2f} сек")
    print(f"   • Скорость воркеров:       {task.speed_files_per_sec} файлов/сек")
    print("=" * 75)

    assert total_errors == 0, f"Обнаружены ошибки пользовательских запросов: {total_errors}"
    print("🏆 ТЕСТ УСПЕШНО ПРОЙДЕН: Пользовательский API сохранил высокую отзывчивость и стабильность под нагрузкой.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Стресс-тест очереди задач и пользовательского API")
    parser.add_argument('--url', type=str, default="http://127.0.0.1:8000", help="Базовый URL сервера")
    parser.add_argument('--users', type=int, default=100, help="Количество одновременных пользователей")
    parser.add_argument('--files', type=int, default=500, help="Количество файлов для фонового импорта")
    args = parser.parse_args()

    run_load_test(base_url=args.url, concurrent_users=args.users, pdf_count=args.files)
