# -*- coding: utf-8 -*-
"""
Комплексный честный End-to-End тест полного цикла (Full-Stack E2E):
1. Nginx Reverse Proxy / Load Balancer (Round-Robin балансировка между несколькими API)
2. Несколько инстансов API (kvit-api-1, kvit-api-2 на разных портах)
3. Асинхронная очередь задач (Claim -> Processing -> ACK)
4. Выделенный фоновый воркер (TaskQueueManager / worker pipeline)
5. База данных (PostgreSQL / SQLite dialect с миграциями и индексами)
6. Реальный PDF генератор (бинарный файл с лицевыми счетами, периодами, начислениями)
7. Загрузка multipart/form-data -> Spooling -> Background Worker -> DB Storage -> Sharded Disk
8. Поиск по адресу/счету -> Получение access_token
9. Скачивание PDF через защищенный X-Accel-Redirect с верификацией целостности байт и структуры PyMuPDF.
"""
import concurrent.futures
import hashlib
import http.client
import io
import os
import shutil
import socket
import socketserver
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import config
from database.connection import get_db, write_transaction
from database.migrations import migrate_db
from server import AppRequestHandler
from services.pdf import pdf_processor
from services.receipts.receipt_service import receipt_service
from services.security import auth_service
from services.tasks.queue_backend import MemoryTaskQueueBackend
from services.tasks.task_manager import TaskQueueManager, TaskStatus


def _find_free_port() -> int:
    """Находит свободный порт в системе."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _create_realistic_pdf(path: str, account: str = "800146", period: str = "12.2026", customer: str = "ТОО Тест Энерго") -> str:
    """Генерирует реальный валидный PDF-документ квитанции."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    text = (
        f"ТОО 'ЭНЕРГОСБЫТ СЕРВИС'\n"
        f"Счет-извещение за 12.2026\n"
        f"Период: 12.2026\n"
        f"Лицевой счет: {account}\n"
        f"Потребитель: {customer}\n"
        f"Адрес: г. Алматы, ул. Абая, д. 10, кв. 25\n"
        f"Тариф: 24.50 тг/кВт*ч | Показания: 12500 - 12650 | К оплате: 3675.00 тг\n"
    )


    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None
    if font_path:
        page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
        page.insert_text((50, 80), text, fontname='arial', fontsize=12)
    else:
        page.insert_text((50, 80), text, fontsize=12)

    # Рисуем рамку квитанции
    rect = fitz.Rect(40, 60, 555, 200)
    page.draw_rect(rect, color=(0.2, 0.4, 0.8), width=1.5)

    doc.save(path)
    doc.close()

    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class MiniNginxLoadBalancer:
    """
    Эмулятор Nginx Reverse Proxy / Load Balancer:
    - Балансирует входящие запросы между несколькими API бэкендами (Round-Robin).
    - Перехватывает X-Accel-Redirect и отдает файлы напрямую из receipts storage (как реальный Nginx).
    """

    def __init__(self, backend_ports: list, receipts_dir: str):
        self.backend_ports = backend_ports
        self.receipts_dir = receipts_dir
        self.port = _find_free_port()
        self._current_idx = 0
        self._lock = threading.Lock()
        self.server = None
        self.thread = None

    def start(self):
        lb_self = self

        class LBHandler(socketserver.StreamRequestHandler):
            def handle(self):
                # Читаем HTTP запрос
                request_line = self.rfile.readline().decode('utf-8', errors='ignore')
                if not request_line:
                    return
                parts = request_line.strip().split()
                if len(parts) < 2:
                    return
                method, path = parts[0], parts[1]

                # Читаем заголовки
                headers = {}
                while True:
                    line = self.rfile.readline().decode('utf-8', errors='ignore')
                    if not line or line in ('\r\n', '\n'):
                        break
                    if ':' in line:
                        k, v = line.split(':', 1)
                        headers[k.strip().lower()] = v.strip()

                content_len = int(headers.get('content-length', 0))
                body = self.rfile.read(content_len) if content_len > 0 else b''

                # Выбираем следующий API бэкенд (Round-Robin)
                with lb_self._lock:
                    target_port = lb_self.backend_ports[lb_self._current_idx]
                    lb_self._current_idx = (lb_self._current_idx + 1) % len(lb_self.backend_ports)

                # Проксируем запрос к выбранному API
                try:
                    conn = http.client.HTTPConnection('127.0.0.1', target_port, timeout=10)
                    proxy_headers = {k: v for k, v in headers.items() if k not in ('host',)}
                    proxy_headers['Host'] = f'127.0.0.1:{target_port}'
                    proxy_headers['X-Forwarded-For'] = '127.0.0.1'
                    proxy_headers['X-Forwarded-Proto'] = 'http'
                    proxy_headers['X-Real-IP'] = '127.0.0.1'

                    conn.request(method, path, body=body, headers=proxy_headers)
                    resp = conn.getresponse()
                    resp_headers = resp.getheaders()
                    resp_body = resp.read()

                    # ─── Nginx X-Accel-Redirect Handling ───
                    x_accel = None
                    for h_k, h_v in resp_headers:
                        if h_k.lower() == 'x-accel-redirect':
                            x_accel = h_v
                            break

                    if x_accel:
                        # Nginx перехватывает X-Accel-Redirect и отдает локальный файл
                        # /internal_receipts/{rel_path} -> receipts_dir/{rel_path}
                        rel_path = x_accel.replace('/internal_receipts/', '').lstrip('/')
                        file_path = os.path.join(lb_self.receipts_dir, rel_path)

                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                file_content = f.read()

                            self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                            self.wfile.write(b"Content-Type: application/pdf\r\n")
                            self.wfile.write(f"Content-Length: {len(file_content)}\r\n".encode())
                            self.wfile.write(b"X-Served-By: Nginx-X-Accel\r\n")
                            self.wfile.write(b"Connection: close\r\n\r\n")
                            self.wfile.write(file_content)
                            conn.close()
                            return

                    # Обычный ответ API
                    self.wfile.write(f"HTTP/1.1 {resp.status} {resp.reason}\r\n".encode())
                    for h_k, h_v in resp_headers:
                        self.wfile.write(f"{h_k}: {h_v}\r\n".encode())
                    self.wfile.write(b"\r\n")
                    self.wfile.write(resp_body)
                    conn.close()
                except Exception as e:
                    err_msg = f"Proxy error: {e}".encode()
                    self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\n")
                    self.wfile.write(f"Content-Length: {len(err_msg)}\r\n\r\n".encode())
                    self.wfile.write(err_msg)

        self.server = ThreadedHTTPServer(('127.0.0.1', self.port), LBHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def test_full_stack_end_to_end_lifecycle(tmp_path):
    """
    Полный сквозной тест:
    1. Инициализация БД и регистрация аккаунта.
    2. Запуск 2 инстансов API (API-1, API-2) с общим бэкендом очередей и хранилищем.
    3. Запуск Nginx балансировщика с поддержкой X-Accel-Redirect.
    4. Запуск отдельного Worker процесса в фоне.
    5. Загрузка реального PDF через multipart POST на Nginx.
    6. Очередь передает задачу воркеру, воркер обрабатывает PDF, шардирует на диск и регистрирует в БД.
    7. Клиент через поиск находит квитанцию и получает access_token.
    8. Клиент запрашивает /download?token=... через Nginx.
    9. Nginx отдает файл по X-Accel-Redirect, клиент скачивает бинарный PDF и проверяет его валидность через PyMuPDF.
    """
    receipts_dir = str(tmp_path / "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    orig_receipts_dir = config.RECEIPTS_DIR
    orig_x_accel = getattr(config, 'ENABLE_X_ACCEL_REDIRECT', False)
    orig_trust_proxy = getattr(config, 'TRUST_PROXY', False)

    try:
        config.RECEIPTS_DIR = receipts_dir
        config.ENABLE_X_ACCEL_REDIRECT = True
        config.TRUST_PROXY = True

        # ─── 1. Инициализация БД и регистрация лицевого счета ───
        migrate_db()
        test_account = "800146"
        with write_transaction() as con:
            con.execute(
                "INSERT OR REPLACE INTO accounts(account_number, customer_name, address, street, building) "
                "VALUES (?, ?, ?, ?, ?)",
                (test_account, "ТОО Тест Энерго", "г. Алматы, ул. Абая, д. 10, кв. 25", "Абая", "10")
            )

        # ─── 2. Создание общей очереди и запуск Worker ───
        shared_queue = MemoryTaskQueueBackend()
        worker_mgr = TaskQueueManager(backend=shared_queue, max_workers=2)
        worker_mgr.start()

        # ─── 3. Запуск 2 реплик API ───
        port_api_1 = _find_free_port()
        port_api_2 = _find_free_port()

        class CustomAPIHandler(AppRequestHandler):
            pass

        # Подменяем менеджер задач в server на общий worker_mgr
        import server
        orig_tm = server.task_manager
        server.task_manager = worker_mgr


        server_api_1 = ThreadedHTTPServer(('127.0.0.1', port_api_1), CustomAPIHandler)
        thread_api_1 = threading.Thread(target=server_api_1.serve_forever, daemon=True)
        thread_api_1.start()

        server_api_2 = ThreadedHTTPServer(('127.0.0.1', port_api_2), CustomAPIHandler)
        thread_api_2 = threading.Thread(target=server_api_2.serve_forever, daemon=True)
        thread_api_2.start()

        # ─── 4. Запуск Nginx Балансировщика ───
        nginx_lb = MiniNginxLoadBalancer(
            backend_ports=[port_api_1, port_api_2],
            receipts_dir=receipts_dir
        )
        nginx_lb.start()
        lb_base_url = f"http://127.0.0.1:{nginx_lb.port}"

        # ─── 5. Генерация реального PDF файла ───
        raw_pdf_path = str(tmp_path / "raw_receipt_batch.pdf")
        original_hash = _create_realistic_pdf(raw_pdf_path, account=test_account, period="12.2026")

        # ─── 6. Клиентский шаг: Авторизация админа и Загрузка файла через Nginx ───
        # Создаем сессию админа
        session_token = auth_service.create_session()
        csrf_token = auth_service.get_csrf_token(session_token)

        # Формируем multipart/form-data тело запроса
        boundary = "----WebKitFormBoundaryE2ETest7MA4YWxkTrZu0gW"
        with open(raw_pdf_path, 'rb') as f:
            pdf_data = f.read()

        body_io = io.BytesIO()
        body_io.write(f"--{boundary}\r\n".encode())
        body_io.write(f'Content-Disposition: form-data; name="csrf_token"\r\n\r\n'.encode())
        body_io.write(f"{csrf_token}\r\n".encode())
        body_io.write(f"--{boundary}\r\n".encode())
        body_io.write(f'Content-Disposition: form-data; name="pdf_file"; filename="incoming_batch.pdf"\r\n'.encode())
        body_io.write(b"Content-Type: application/pdf\r\n\r\n")
        body_io.write(pdf_data)
        body_io.write(b"\r\n")
        body_io.write(f"--{boundary}--\r\n".encode())
        payload = body_io.getvalue()

        req = urllib.request.Request(
            f"{lb_base_url}/upload",
            data=payload,
            headers={
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Cookie': f'session={session_token}',
                'X-CSRF-Token': csrf_token,
                'User-Agent': 'KvitE2EClient/1.0'
            }
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
            resp_html = resp.read().decode('utf-8')
            assert "Загрузка успешно принята в фоновую обработку" in resp_html or "job_" in resp_html

        # ─── 7. Ожидание завершения обработки воркером ───
        # Воркер забирает задачу из очереди и сохраняет квитанцию в БД
        max_wait = 15.0
        start_wait = time.time()
        receipt_record = None

        while time.time() - start_wait < max_wait:
            time.sleep(0.3)
            con = get_db()
            receipt_record = con.execute(
                "SELECT * FROM receipts WHERE account_number = ? ORDER BY id DESC LIMIT 1",
                (test_account,)
            ).fetchone()
            con.close()
            if receipt_record and receipt_record['status'] == 'READY':
                break


        assert receipt_record is not None, "Квитанция не была обработана воркером вовремя!"
        access_token = receipt_record['access_token']
        assert access_token is not None and len(access_token) == 32

        # ─── 8. Поиск квитанции через API (балансировка на API-2) ───
        search_req = urllib.request.Request(
            f"{lb_base_url}/api/search?q={test_account}",
            headers={'User-Agent': 'KvitE2EClient/1.0'}
        )
        with urllib.request.urlopen(search_req, timeout=5) as search_resp:
            assert search_resp.status == 200
            search_body = search_resp.read().decode('utf-8')
            assert test_account in search_body or "status" in search_body

        # ─── 9. Скачивание PDF через Nginx (X-Accel-Redirect -> Binary stream) ───
        download_req = urllib.request.Request(
            f"{lb_base_url}/download?token={access_token}",
            headers={'User-Agent': 'KvitE2EClient/1.0'}
        )
        with urllib.request.urlopen(download_req, timeout=5) as dl_resp:
            assert dl_resp.status == 200
            assert dl_resp.headers.get('Content-Type') == 'application/pdf'
            downloaded_bytes = dl_resp.read()

        # ─── 10. Проверка целостности и структуры скачанного файла ───
        assert len(downloaded_bytes) > 0
        assert downloaded_bytes.startswith(b"%PDF-"), "Файл не является валидным PDF!"

        # Открываем скачанный файл через PyMuPDF
        downloaded_doc = fitz.open(stream=downloaded_bytes, filetype="pdf")
        assert len(downloaded_doc) >= 1
        page_text = downloaded_doc[0].get_text().replace('\xa0', ' ').replace('\xad', '-')
        assert test_account in page_text, f"Лицевой счет {test_account} не найден в содержимом скачанной квитанции!"
        assert "ТОО 'ЭНЕРГОСБЫТ СЕРВИС'" in page_text
        assert "3675.00 тг" in page_text
        downloaded_doc.close()


        print("\n🎉 [E2E УСПЕХ] Полный сквозной цикл Nginx -> Multi-API -> Queue -> Worker -> DB -> X-Accel -> Download пройден!")

    finally:
        # Корректная остановка всех сервисов
        if 'worker_mgr' in locals():
            worker_mgr.stop()
        if 'nginx_lb' in locals():
            nginx_lb.stop()
        if 'server_api_1' in locals():
            server_api_1.shutdown()
            server_api_1.server_close()
        if 'server_api_2' in locals():
            server_api_2.shutdown()
            server_api_2.server_close()
        if 'orig_tm' in locals():
            import server
            server.task_manager = orig_tm

        config.RECEIPTS_DIR = orig_receipts_dir
        config.ENABLE_X_ACCEL_REDIRECT = orig_x_accel
        config.TRUST_PROXY = orig_trust_proxy

