# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import parse_qs

import config
from templates.auth_views import render_forbidden_page, render_payload_too_large_page
from templates.layout import layout

logger = logging.getLogger(__name__)

BOUNDARY_PREFIX = 'boundary='


def send_payload_error(handler, code: int, message: str) -> None:
    """
    Отправляет клиенту ответ с ошибкой размера или формата запроса (400 / 413).
    Корректно выбирает JSON для API или HTML для браузера, сохраняя статус в handler.
    """
    handler.last_error_code = code
    handler.last_error_message = message

    path = getattr(handler, 'path', '') or ''
    headers = getattr(handler, 'headers', None) or {}
    accept = headers.get('Accept', '') if hasattr(headers, 'get') else ''
    content_type = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''

    is_api = path.startswith('/api/') or 'application/json' in accept or 'application/json' in content_type

    if is_api and hasattr(handler, 'send_json'):
        handler.send_json({'ok': False, 'error': message, 'status': code}, code)
        return

    if hasattr(handler, 'send_html'):
        is_admin = False
        if hasattr(handler, '_is_admin'):
            try:
                is_admin = handler._is_admin()
            except Exception:
                is_admin = False

        if code == 413:
            body = render_payload_too_large_page(message)
            handler.send_html(layout(body, is_admin=is_admin), 413)
            return
        elif code == 400:
            body = render_forbidden_page(message)
            handler.send_html(layout(body, is_admin=is_admin), 400)
            return

    # Fallback на стандартный send_error BaseHTTPRequestHandler
    if hasattr(handler, 'send_error'):
        try:
            handler.send_error(code, message)
        except Exception:
            pass


def read_bounded_body(handler, max_bytes: int, allow_chunked: bool = True) -> bytes | None:
    """
    Безопасно считывает тело HTTP-запроса с жестким верхним ограничением по размеру.
    Защищает от DoS (неограниченного потребления памяти).
    - Если заголовок Content-Length невалидный (не число или < 0) -> 400 Bad Request.
    - Если Content-Length > max_bytes -> 413 Payload Too Large.
    - Если передан Transfer-Encoding: chunked:
        - считывает по чанкам, если суммарный размер > max_bytes -> 413 Payload Too Large.
    - Считывает поток из handler.rfile не более max_bytes байт.
    - Если превышен лимит или ошибка -> вызывает send_payload_error и возвращает None.
    """
    headers = getattr(handler, 'headers', None) or {}
    transfer_encoding = headers.get('Transfer-Encoding', '').lower() if hasattr(headers, 'get') else ''
    content_length_raw = headers.get('Content-Length') if hasattr(headers, 'get') else None
    rfile = getattr(handler, 'rfile', None)

    if rfile is None:
        send_payload_error(handler, 400, "Bad Request: Missing request stream")
        return None

    # 1. Поддержка Transfer-Encoding: chunked
    if transfer_encoding == 'chunked' and allow_chunked:
        try:
            body = bytearray()
            while True:
                line = rfile.readline(65536)
                if not line:
                    break
                # Удаляем CRLF и chunk extensions (;ext...)
                chunk_header = line.strip().split(b';')[0]
                if not chunk_header:
                    continue
                try:
                    chunk_len = int(chunk_header, 16)
                except ValueError:
                    send_payload_error(handler, 400, "Bad Request: Invalid chunk hex length")
                    return None

                if chunk_len < 0:
                    send_payload_error(handler, 400, "Bad Request: Negative chunk size")
                    return None

                if chunk_len == 0:
                    # Читаем trailers до пустой строки
                    while True:
                        trailer = rfile.readline(65536)
                        if not trailer or trailer in (b'\r\n', b'\n'):
                            break
                    break

                if len(body) + chunk_len > max_bytes:
                    logger.warning(f"[RequestGuard] Chunked body ({len(body) + chunk_len}) exceeds limit ({max_bytes})")
                    send_payload_error(handler, 413, f"Payload Too Large: Maximum allowed body is {max_bytes} bytes")
                    return None

                chunk_data = rfile.read(chunk_len)
                body.extend(chunk_data)
                # Читаем закрывающий \r\n чанка
                rfile.readline(10)

            return bytes(body)
        except Exception as e:
            logger.warning(f"[RequestGuard] Ошибка при чтении chunked body: {e}")
            send_payload_error(handler, 400, "Bad Request: Malformed chunked stream")
            return None

    # 2. Обработка Content-Length
    if content_length_raw is None:
        send_payload_error(handler, 400, "Bad Request: Missing Content-Length header")
        return None

    try:
        content_length = int(content_length_raw)
    except (ValueError, TypeError):
        send_payload_error(handler, 400, "Bad Request: Content-Length must be an integer")
        return None

    if content_length < 0:
        send_payload_error(handler, 400, "Bad Request: Content-Length cannot be negative")
        return None

    if content_length > max_bytes:
        path = getattr(handler, 'path', '')
        logger.warning(f"[RequestGuard] Отклонен запрос ({path}): Content-Length {content_length} > {max_bytes}")
        send_payload_error(
            handler, 413, f"Payload Too Large: Content-Length ({content_length}) exceeds maximum limit ({max_bytes})"
        )
        return None

    # 3. Безопасное чтение блоками
    try:
        body = bytearray()
        remaining = content_length
        chunk_size = 64 * 1024
        while remaining > 0:
            to_read = min(remaining, chunk_size)
            chunk = rfile.read(to_read)
            if not chunk:
                break
            body.extend(chunk)
            remaining -= len(chunk)

        if len(body) > max_bytes:
            send_payload_error(handler, 413, f"Payload Too Large: Exceeds {max_bytes} bytes")
            return None

        return bytes(body)
    except Exception as e:
        logger.warning(f"[RequestGuard] Ошибка при чтении потока запроса: {e}")
        send_payload_error(handler, 400, "Bad Request: Error reading request stream")
        return None


def parse_bounded_form(handler, max_bytes: int | None = None) -> dict:
    """Считывает и декодирует application/x-www-form-urlencoded параметры формы с лимитом размера."""
    if max_bytes is None:
        max_bytes = config.MAX_FORM_BODY_BYTES
    data = read_bounded_body(handler, max_bytes)
    if data is None:
        return {}
    try:
        return parse_qs(data.decode('utf-8', errors='replace'))
    except Exception:
        return {}


def parse_bounded_multipart(
    handler,
    max_bytes: int | None = None,
    max_parts: int = 100,
    max_header_len: int = 8192,
) -> tuple[dict, list]:
    """
    Безопасный разбор multipart/form-data в память для небольших форм (CMS медиа/файлы):
    - Ограничение общего размера (max_bytes)
    - Ограничение количества частей (max_parts)
    - Ограничение размера заголовков одной части (max_header_len)
    Возвращает (fields: dict, files: list of (field_name, filename, bytes)).
    """
    if max_bytes is None:
        max_bytes = config.MAX_MEDIA_UPLOAD_BYTES

    headers = getattr(handler, 'headers', None) or {}
    content_type = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''

    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith(BOUNDARY_PREFIX):
            boundary = part[len(BOUNDARY_PREFIX):].strip('"\'')
            break

    if not boundary:
        send_payload_error(handler, 400, "Bad Request: Missing multipart boundary")
        return {}, []

    data = read_bounded_body(handler, max_bytes)
    if data is None:
        return {}, []

    boundary_bytes = boundary.encode('latin1')
    raw_parts = data.split(b'--' + boundary_bytes)

    fields = {}
    files = []
    parts_count = 0

    for part in raw_parts:
        if not part or part in (b'--\r\n', b'--\r\n\r\n', b'--', b'\r\n--\r\n'):
            continue
        if part.startswith(b'\r\n'):
            part = part[2:]
        if part.endswith(b'\r\n'):
            part = part[:-2]

        hdr_end = part.find(b'\r\n\r\n')
        if hdr_end < 0:
            hdr_end = part.find(b'\n\n')
            hdr_len = 2
        else:
            hdr_len = 4
        if hdr_end < 0:
            continue

        parts_count += 1
        if parts_count > max_parts:
            logger.warning(f"[RequestGuard] Превышено максимальное количество частей multipart ({max_parts})")
            send_payload_error(handler, 400, "Bad Request: Too many multipart parts")
            return {}, []

        if hdr_end > max_header_len:
            logger.warning(f"[RequestGuard] Заголовки части multipart превышают лимит {max_header_len} байт")
            send_payload_error(handler, 400, "Bad Request: Multipart header too large")
            return {}, []

        header_bytes = part[:hdr_end]
        body_bytes = part[hdr_end + hdr_len:]
        header_text = header_bytes.decode('utf-8', errors='replace')

        m_name = re.search(r'name="([^"]*)"', header_text)
        m_fn = re.search(r'filename="([^"]*)"', header_text)
        f_name = m_name.group(1) if m_name else ''
        f_filename = m_fn.group(1) if m_fn else ''

        if f_filename:
            files.append((f_name, f_filename, body_bytes))
        elif f_name:
            val_text = body_bytes.decode('utf-8', errors='replace')
            if f_name not in fields:
                fields[f_name] = []
            fields[f_name].append(val_text)

    return fields, files
