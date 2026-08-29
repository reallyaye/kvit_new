# -*- coding: utf-8 -*-
"""
Централизованный сборщик метрик и телеметрии (Metrics Collector).
Отслеживает:
- Количество HTTP-запросов, статус-коды и распределение задержек (p50, p95, p99)
- Время выполнения OCR и разбора PDF
- Состояние пула базы данных и файлового хранилища
- Метрики очереди фоновых задач и активных воркеров
Поддерживает выдачу в форматах JSON и Prometheus exposition format.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict


class MetricsCollector:
    """Потокобезопасный коллектор операционных метрик."""

    def __init__(self, latency_window_size: int = 1000):
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._requests_total = 0
        self._requests_by_status: Dict[int, int] = {}
        self._requests_by_endpoint: Dict[str, int] = {}
        self._latencies: Deque[float] = deque(maxlen=latency_window_size)

        self._ocr_operations_total = 0
        self._ocr_duration_total = 0.0
        self._ocr_pages_total = 0

        self._pdf_operations_total = 0
        self._pdf_duration_total = 0.0
        self._pdf_files_total = 0

        self._db_errors_total = 0

    def record_request(self, method: str, path: str, status_code: int, duration_sec: float):
        """Регистрирует завершенный HTTP-запрос."""
        endpoint = path.split('?')[0]
        # Нормализация для агрегации динамических URL
        if endpoint.startswith('/api/tasks/'):
            endpoint = '/api/tasks/:id'
        elif endpoint.startswith('/admin/pages/edit'):
            endpoint = '/admin/pages/edit'
        elif endpoint.startswith('/admin/documents/edit'):
            endpoint = '/admin/documents/edit'

        with self._lock:
            self._requests_total += 1
            self._requests_by_status[status_code] = self._requests_by_status.get(status_code, 0) + 1
            self._requests_by_endpoint[endpoint] = self._requests_by_endpoint.get(endpoint, 0) + 1
            self._latencies.append(duration_sec)

    def record_ocr(self, duration_sec: float, pages: int = 1):
        """Регистрирует завершенную операцию OCR."""
        with self._lock:
            self._ocr_operations_total += 1
            self._ocr_duration_total += duration_sec
            self._ocr_pages_total += pages

    def record_pdf_process(self, duration_sec: float, files_count: int = 1):
        """Регистрирует завершенную обработку PDF."""
        with self._lock:
            self._pdf_operations_total += 1
            self._pdf_duration_total += duration_sec
            self._pdf_files_total += files_count

    def record_db_error(self):
        """Регистрирует ошибку доступа к БД."""
        with self._lock:
            self._db_errors_total += 1

    def _calc_percentiles(self) -> Dict[str, float]:
        with self._lock:
            if not self._latencies:
                return {'p50_ms': 0.0, 'p95_ms': 0.0, 'p99_ms': 0.0, 'avg_ms': 0.0, 'max_ms': 0.0}
            sorted_lat = sorted(self._latencies)
            n = len(sorted_lat)

            def get_p(pct):
                idx = min(n - 1, int(n * pct))
                return round(sorted_lat[idx] * 1000, 2)

            avg_ms = round((sum(sorted_lat) / n) * 1000, 2)
            max_ms = round(sorted_lat[-1] * 1000, 2)

            return {
                'p50_ms': get_p(0.50),
                'p95_ms': get_p(0.95),
                'p99_ms': get_p(0.99),
                'avg_ms': avg_ms,
                'max_ms': max_ms
            }

    def to_dict(self) -> dict:
        """Возвращает метрики в формате структурированного JSON."""
        uptime = time.time() - self._start_time
        latency_stats = self._calc_percentiles()

        with self._lock:
            req_total = self._requests_total
            status_copy = dict(self._requests_by_status)
            endpoints_copy = dict(self._requests_by_endpoint)
            ocr_ops = self._ocr_operations_total
            ocr_dur = self._ocr_duration_total
            ocr_pages = self._ocr_pages_total
            pdf_ops = self._pdf_operations_total
            pdf_dur = self._pdf_duration_total
            pdf_files = self._pdf_files_total
            db_errors = self._db_errors_total

        # Вычисляем процент ошибок 5xx и 4xx
        errors_5xx = sum(count for sc, count in status_copy.items() if 500 <= sc < 600)
        errors_4xx = sum(count for sc, count in status_copy.items() if 400 <= sc < 500)
        error_rate_pct = round((errors_5xx / req_total * 100), 2) if req_total > 0 else 0.0

        return {
            'uptime_seconds': round(uptime, 2),
            'requests': {
                'total': req_total,
                'rps': round(req_total / max(1.0, uptime), 2),
                'by_status': status_copy,
                'errors_5xx': errors_5xx,
                'errors_4xx': errors_4xx,
                'error_rate_pct': error_rate_pct,
                'latencies': latency_stats,
                'top_endpoints': sorted(endpoints_copy.items(), key=lambda x: x[1], reverse=True)[:15]
            },
            'ocr': {
                'operations_total': ocr_ops,
                'pages_total': ocr_pages,
                'duration_total_seconds': round(ocr_dur, 2),
                'avg_page_time_seconds': round(ocr_dur / max(1, ocr_pages), 3) if ocr_pages > 0 else 0.0
            },
            'pdf_processing': {
                'operations_total': pdf_ops,
                'files_total': pdf_files,
                'duration_total_seconds': round(pdf_dur, 2),
                'avg_file_time_seconds': round(pdf_dur / max(1, pdf_files), 3) if pdf_files > 0 else 0.0
            },
            'database': {
                'errors_total': db_errors
            }
        }

    def to_prometheus(self) -> str:
        """Форматирует метрики в стандартном формате Prometheus exposition."""
        d = self.to_dict()
        lines = [
            '# HELP http_requests_total Total HTTP requests received',
            '# TYPE http_requests_total counter',
            f"http_requests_total {d['requests']['total']}",
            '# HELP http_request_duration_ms_avg Average HTTP latency in ms',
            '# TYPE http_request_duration_ms_avg gauge',
            f"http_request_duration_ms_avg {d['requests']['latencies']['avg_ms']}",
            '# HELP http_request_duration_ms_p95 95th percentile HTTP latency in ms',
            '# TYPE http_request_duration_ms_p95 gauge',
            f"http_request_duration_ms_p95 {d['requests']['latencies']['p95_ms']}",
            '# HELP ocr_pages_total Total pages processed with OCR',
            '# TYPE ocr_pages_total counter',
            f"ocr_pages_total {d['ocr']['pages_total']}",
            '# HELP pdf_files_total Total PDF files processed',
            '# TYPE pdf_files_total counter',
            f"pdf_files_total {d['pdf_processing']['files_total']}",
            '# HELP db_errors_total Total DB errors encountered',
            '# TYPE db_errors_total counter',
            f"db_errors_total {d['database']['errors_total']}"
        ]
        for sc, count in d['requests']['by_status'].items():
            lines.append(f'http_requests_by_status{{status="{sc}"}} {count}')
        return '\n'.join(lines) + '\n'


metrics_collector = MetricsCollector()
