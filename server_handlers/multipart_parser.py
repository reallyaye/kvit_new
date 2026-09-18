# -*- coding: utf-8 -*-
import logging
import os
import re
import shutil
import tempfile

import config

logger = logging.getLogger('kvit.server.multipart')
BOUNDARY_PREFIX = 'boundary='


class MultipartParserMixin:
    """Потоковый разбор multipart/form-data на диск с O(1) памятью и лимитами безопасности."""

    def _parse_multipart_to_disk(self):
        """
        Потоковый разбор multipart/form-data на диск с константным потреблением памяти O(1).
        Включает жесткие лимиты безопасности уровня приложения:
        - MAX_UPLOAD_BYTES: ограничение общего размера тела запроса (защита от DoS)
        - MAX_FILES_PER_REQUEST: ограничение количества файлов в одной пачке
        - MAX_HEADER_SIZE: ограничение размера заголовков одной секции (64 KB)
        """
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > config.MAX_UPLOAD_BYTES:
            logger.warning(f"[Upload] Отклонен запрос: Content-Length ({content_length} байт) > MAX_UPLOAD_BYTES ({config.MAX_UPLOAD_BYTES} байт)")
            return None, "PAYLOAD_TOO_LARGE"

        boundary = None
        for part in content_type.split(';'):
            part = part.strip()
            if part.startswith(BOUNDARY_PREFIX):
                boundary = part[len(BOUNDARY_PREFIX):].strip('"\'')
                break
        if not boundary or content_length <= 0:
            return None, None

        boundary_bytes = boundary.encode('latin1')
        delimiter = b'--' + boundary_bytes
        delimiter_crlf = b'\r\n--' + boundary_bytes

        tmp_dir = tempfile.mkdtemp(prefix='kvit_upload_', dir=config.SPOOL_DIR)
        pdf_files = []

        remaining = content_length
        total_read = 0
        read_chunk_size = 64 * 1024

        def read_stream():
            nonlocal remaining, total_read
            while remaining > 0:
                to_read = min(read_chunk_size, remaining)
                chunk = self.rfile.read(to_read)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > config.MAX_UPLOAD_BYTES:
                    logger.warning(f"[Upload] Превышен лимит байт при чтении потока ({total_read} > {config.MAX_UPLOAD_BYTES})")
                    break
                remaining -= len(chunk)
                yield chunk

        stream = read_stream()
        buf = b''

        while delimiter not in buf:
            try:
                chunk = next(stream)
            except StopIteration:
                break
            buf += chunk

        first_delim_idx = buf.find(delimiter)
        if first_delim_idx < 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None, None

        buf = buf[first_delim_idx + len(delimiter):]
        MAX_HEADER_SIZE = 64 * 1024

        while True:
            if buf.startswith(b'--'):
                break

            if buf.startswith(b'\r\n'):
                buf = buf[2:]
            elif buf.startswith(b'\n'):
                buf = buf[1:]

            while b'\r\n\r\n' not in buf and b'\n\n' not in buf:
                if len(buf) > MAX_HEADER_SIZE:
                    break
                try:
                    chunk = next(stream)
                except StopIteration:
                    break
                buf += chunk

            header_end = buf.find(b'\r\n\r\n')
            header_len = 4
            if header_end < 0:
                header_end = buf.find(b'\n\n')
                header_len = 2

            if header_end < 0:
                break

            header_bytes = buf[:header_end]
            buf = buf[header_end + header_len:]

            header_text = header_bytes.decode('utf-8', errors='replace')
            m_name = re.search(r'name="([^"]*)"', header_text)
            m_fn = re.search(r'filename="([^"]*)"', header_text)
            field_name = m_name.group(1) if m_name else ''
            file_name = m_fn.group(1) if m_fn else ''

            is_target_file = (field_name == 'pdf' or file_name.lower().endswith('.pdf')) and bool(file_name)

            out_file = None
            tmp_path = None
            base_name = None
            if is_target_file:
                cleaned_name = os.path.basename(file_name.replace('\\', '/')).replace('\x00', '').strip()
                cleaned_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cleaned_name).strip(' .')
                base_name = cleaned_name if cleaned_name else f'upload_{len(pdf_files):04d}.pdf'
                tmp_path = os.path.join(tmp_dir, f'{len(pdf_files):06d}_{base_name}')
                try:
                    out_file = open(tmp_path, 'wb')
                except OSError:
                    base_name = f'upload_{len(pdf_files):04d}.pdf'
                    tmp_path = os.path.join(tmp_dir, f'{len(pdf_files):06d}_{base_name}')
                    out_file = open(tmp_path, 'wb')

            needle = delimiter_crlf
            needle_len = len(needle)

            while True:
                idx = buf.find(needle)
                if idx >= 0:
                    if out_file and idx > 0:
                        out_file.write(buf[:idx])
                    buf = buf[idx + needle_len:]
                    break
                else:
                    if len(buf) > needle_len:
                        flush_len = len(buf) - needle_len
                        if out_file:
                            out_file.write(buf[:flush_len])
                        buf = buf[flush_len:]

                    try:
                        chunk = next(stream)
                        buf += chunk
                    except StopIteration:
                        if out_file and buf:
                            out_file.write(buf)
                        buf = b''
                        break

            if out_file:
                out_file.close()
                if os.path.getsize(tmp_path) > 0:
                    pdf_files.append((base_name, tmp_path))
                    if len(pdf_files) >= config.MAX_FILES_PER_REQUEST:
                        logger.warning(f"[Upload] Достигнут лимит файлов в одном запросе ({config.MAX_FILES_PER_REQUEST})")
                        break
                else:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        for _ in stream:
            pass

        return tmp_dir, pdf_files

    def _parse_accounts_multipart(self):
        """
        Потоковый разбор multipart/form-data для загрузки файла реестра счетов.
        Возвращает (tmp_dir, target_file_path, mode, target_file_name).
        """
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > config.MAX_UPLOAD_BYTES:
            logger.warning(f"[Accounts] Отклонен запрос: Content-Length ({content_length} байт) > MAX_UPLOAD_BYTES ({config.MAX_UPLOAD_BYTES} байт)")
            return None, "PAYLOAD_TOO_LARGE", None, None

        boundary = None
        for part in content_type.split(';'):
            part = part.strip()
            if part.startswith(BOUNDARY_PREFIX):
                boundary = part[len(BOUNDARY_PREFIX):].strip('"\'')
                break
        if not boundary or content_length <= 0:
            return None, None, None, None

        boundary_bytes = boundary.encode('latin1')
        delimiter = b'--' + boundary_bytes
        delimiter_crlf = b'\r\n--' + boundary_bytes

        tmp_dir = tempfile.mkdtemp(prefix='kvit_acc_upload_', dir=config.SPOOL_DIR)
        target_file_path = None
        target_file_name = None
        mode = 'upsert'

        remaining = content_length
        total_read = 0
        read_chunk_size = 64 * 1024

        def read_stream():
            nonlocal remaining, total_read
            while remaining > 0:
                to_read = min(read_chunk_size, remaining)
                chunk = self.rfile.read(to_read)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > config.MAX_UPLOAD_BYTES:
                    logger.warning(f"[Accounts] Превышен лимит байт при чтении потока ({total_read} > {config.MAX_UPLOAD_BYTES})")
                    break
                remaining -= len(chunk)
                yield chunk

        stream = read_stream()
        buf = b''

        while delimiter not in buf:
            try:
                chunk = next(stream)
            except StopIteration:
                break
            buf += chunk

        first_delim_idx = buf.find(delimiter)
        if first_delim_idx < 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None, None, None, None

        buf = buf[first_delim_idx + len(delimiter):]
        MAX_HEADER_SIZE = 64 * 1024

        while True:
            if buf.startswith(b'--'):
                break

            if buf.startswith(b'\r\n'):
                buf = buf[2:]
            elif buf.startswith(b'\n'):
                buf = buf[1:]

            while b'\r\n\r\n' not in buf and b'\n\n' not in buf:
                if len(buf) > MAX_HEADER_SIZE:
                    break
                try:
                    chunk = next(stream)
                except StopIteration:
                    break
                buf += chunk

            header_end = buf.find(b'\r\n\r\n')
            header_len = 4
            if header_end < 0:
                header_end = buf.find(b'\n\n')
                header_len = 2

            if header_end < 0:
                break

            header_bytes = buf[:header_end]
            buf = buf[header_end + header_len:]

            header_text = header_bytes.decode('utf-8', errors='replace')
            m_name = re.search(r'name="([^"]*)"', header_text)
            m_fn = re.search(r'filename="([^"]*)"', header_text)
            field_name = m_name.group(1) if m_name else ''
            file_name = m_fn.group(1) if m_fn else ''

            is_file = (field_name == 'file' or bool(file_name))
            out_file = None
            field_data = bytearray()

            if is_file and file_name:
                cleaned_name = os.path.basename(file_name.replace('\\', '/')).replace('\x00', '').strip()
                cleaned_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cleaned_name).strip(' .')
                target_file_name = cleaned_name if cleaned_name else 'accounts_upload.xlsx'
                target_file_path = os.path.join(tmp_dir, target_file_name)
                try:
                    out_file = open(target_file_path, 'wb')
                except OSError:
                    target_file_name = 'accounts_upload.xlsx'
                    target_file_path = os.path.join(tmp_dir, target_file_name)
                    out_file = open(target_file_path, 'wb')

            needle = delimiter_crlf
            needle_len = len(needle)

            while True:
                idx = buf.find(needle)
                if idx >= 0:
                    if out_file and idx > 0:
                        out_file.write(buf[:idx])
                    elif not is_file and idx > 0:
                        field_data.extend(buf[:idx])
                    buf = buf[idx + needle_len:]
                    break
                else:
                    if len(buf) > needle_len:
                        flush_len = len(buf) - needle_len
                        if out_file:
                            out_file.write(buf[:flush_len])
                        elif not is_file:
                            field_data.extend(buf[:flush_len])
                        buf = buf[flush_len:]

                    try:
                        chunk = next(stream)
                        buf += chunk
                    except StopIteration:
                        if out_file and buf:
                            out_file.write(buf)
                        elif not is_file and buf:
                            field_data.extend(buf)
                        buf = b''
                        break

            if out_file:
                out_file.close()

            if not is_file and field_name == 'mode':
                mode_val = field_data.decode('utf-8', errors='replace').strip().lower()
                if mode_val in ('upsert', 'replace', 'insert_only'):
                    mode = mode_val

        for _ in stream:
            pass

        return tmp_dir, target_file_path, mode, target_file_name
