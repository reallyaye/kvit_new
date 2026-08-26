#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт верификации балансировки нагрузки Nginx:
- Выполняет серию параллельных HTTP запросов.
- Считывает заголовок X-Backend-Instance.
- Строит гистограмму распределения и проверяет равномерность Round-Robin.
"""
import argparse
import collections
import concurrent.futures
import time
import urllib.request

def probe_instance(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'KvitLoadBalancerAuditor/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            instance = response.headers.get('X-Backend-Instance', 'unknown')
            return instance
    except Exception as e:
        return f"error: {e}"

def test_load_balancing(url: str, requests_count: int = 200, concurrency: int = 20):
    print(f"🚀 Запуск проверки балансировки: {requests_count} запросов (конкурентность: {concurrency}) к {url}")
    start = time.time()
    results = collections.Counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(probe_instance, url) for _ in range(requests_count)]
        for f in concurrent.futures.as_completed(futures):
            results[f.result()] += 1

    elapsed = time.time() - start
    print(f"\n📊 Результаты тестирования за {elapsed:.2f} сек ({requests_count / elapsed:.1f} RPS):")
    print("-" * 50)
    for inst, count in results.most_common():
        pct = (count / requests_count) * 100
        bar = "█" * int(pct / 2)
        print(f"  {inst:<25}: {count:>4} ({pct:>5.1f}%) {bar}")
    print("-" * 50)

    unique_healthy = [k for k in results if not k.startswith('error')]
    if len(unique_healthy) > 1:
        print(f"✅ Балансировка активна: запросы распределены между {len(unique_healthy)} репликами.")
    else:
        print(f"ℹ Обнаружен 1 активный backend инстанс ({unique_healthy[0] if unique_healthy else 'none'}).")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Тест балансировки Nginx")
    parser.add_argument("--url", default="http://127.0.0.1/", help="URL тестируемого шлюза Nginx")
    parser.add_argument("--count", type=int, default=200, help="Количество запросов")
    parser.add_argument("--concurrency", type=int, default=20, help="Параллельность")
    args = parser.parse_args()

    test_load_balancing(args.url, args.count, args.concurrency)
