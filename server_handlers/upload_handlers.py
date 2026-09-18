# -*- coding: utf-8 -*-
import html
import logging
import os
import shutil
import sys
import tempfile
from urllib.parse import parse_qs

import config
from server_handlers.multipart_parser import MultipartParserMixin
from services.security import auth_service
from templates import (
    layout,
    render_forbidden_page,
    render_upload_form,
)


def __getattr__(name: str):
    if name == 'task_manager':
        srv = sys.modules.get('server')
        if srv and hasattr(srv, 'task_manager'):
            return srv.task_manager
        from services.tasks import task_manager as default_tm
        return default_tm
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

logger = logging.getLogger('kvit.server.upload')
CSRF_INVALID_MSG = 'Недействительный или отсутствующий CSRF-токен.'


class UploadHandlerMixin(MultipartParserMixin):
    """Обработчики пакетной загрузки PDF, реестров счетов и импорта папок."""
    def _handle_api_upload_batch(self):
        if not self._is_operator_or_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        client_ip = self._get_client_ip()
        cur_user = self._get_current_user() or {}
        username = cur_user.get('username', 'operator')

        tmp_dir, pdf_files = self._parse_multipart_to_disk()
        if pdf_files == "PAYLOAD_TOO_LARGE":
            max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            self.send_json({'error': f'Превышен максимальный размер загрузки ({max_mb} MB)'}, 413)
            return

        if tmp_dir is None or not pdf_files:
            self.send_json({'error': 'Файлы не получены'}, 400)
            return

        task = self.task_manager.submit_pdf_job(
            files=pdf_files,
            source='api_batch',
            spool_dir=tmp_dir,
            meta={'username': username, 'client_ip': client_ip}
        )

        auth_service.log_audit(
            username,
            client_ip,
            'UPLOAD_START',
            f"Запущена пакетная API-загрузка {len(pdf_files)} файлов квитанций (задача: {task.job_id})"
        )

        self.send_json({
            'success': True,
            'job_id': task.job_id,
            'status': task.status,
            'files_count': len(pdf_files),
            'status_url': f'/api/tasks/{task.job_id}',
            'message': 'Файлы успешно приняты в очередь фоновой обработки.'
        }, 202)

    def _handle_api_upload_accounts(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': CSRF_INVALID_MSG}, 403)
            return

        tmp_dir, file_path, mode, file_name = self._parse_accounts_multipart()
        if file_path == "PAYLOAD_TOO_LARGE":
            max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            self.send_json({'error': f'Превышен максимальный размер загрузки ({max_mb} MB)'}, 413)
            return

        if not tmp_dir or not file_path or not os.path.isfile(file_path):
            self.send_json({'error': 'Файл реестра не получен или повреждён'}, 400)
            return

        try:
            from import_accounts import import_accounts_file
            res = import_accounts_file(file_path, mode=mode, verbose=False)
            self.send_json({
                'success': True,
                'file_name': file_name,
                'mode': mode,
                'imported': res.get('imported', 0),
                'skipped': res.get('skipped', 0),
                'total_in_db': res.get('total_in_db', 0),
                'elapsed_seconds': res.get('elapsed_seconds', 0),
                'message': f"Успешно обработано: {res.get('imported', 0):,} счетов. Всего в базе: {res.get('total_in_db', 0):,}."
            }, 200)
        except Exception as e:
            logger.error(f"[UploadAccounts] Ошибка импорта реестра {file_name}: {e}", exc_info=True)
            self.send_json({
                'error': f'Ошибка импорта файла: {str(e)}'
            }, 500)
        finally:
            if tmp_dir and os.path.abspath(tmp_dir) != os.path.abspath(tempfile.gettempdir()):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _handle_import_folder(self):
        body_bytes = self._read_bounded_body(config.MAX_FORM_BODY_BYTES)
        if body_bytes is None:
            return
        params = parse_qs(body_bytes.decode('utf-8', errors='replace'))
        csrf_token = params.get('csrf_token', [''])[0].strip()
        folder_path = params.get('folder_path', [''])[0].strip()

        if not self._verify_csrf(body_csrf=csrf_token):
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_forbidden_page(CSRF_INVALID_MSG)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 403)
            return

        is_safe, real_folder_path, error_msg = config.is_safe_import_path(folder_path)
        if not is_safe:
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="err">{error_msg}</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        pdf_paths = []
        base_depth = real_folder_path.count(os.sep)

        for root, dirs, files in os.walk(real_folder_path):
            current_depth = root.count(os.sep) - base_depth
            if current_depth >= config.MAX_IMPORT_DEPTH:
                dirs.clear()
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_paths.append(os.path.join(root, file))
                    if len(pdf_paths) >= config.MAX_IMPORT_FILES:
                        break
            if len(pdf_paths) >= config.MAX_IMPORT_FILES:
                break

        if not pdf_paths:
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="warn">В папке <code>{html.escape(folder_path)}</code> не найдено ни одного .pdf файла.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        cur_user = self._get_current_user() if hasattr(self, '_get_current_user') else {}
        cur_user = cur_user or {}
        username = cur_user.get('username', 'operator')
        client_ip = self._get_client_ip() if hasattr(self, '_get_client_ip') else '127.0.0.1'

        files = [(os.path.basename(p), p) for p in pdf_paths]
        task = self.task_manager.submit_pdf_job(
            files=files,
            source='folder_import',
            meta={'username': username, 'client_ip': client_ip, 'folder_path': folder_path}
        )

        auth_service.log_audit(
            username,
            client_ip,
            'UPLOAD_START',
            f"Запущен импорт из папки {len(pdf_paths)} файлов квитанций (задача: {task.job_id}, путь: {folder_path})"
        )

        msg = f'''<div class="ok">
            <b>Импорт из папки передан в фоновую обработку: {len(pdf_paths)} PDF-файлов</b><br><br>
            Идентификатор задачи: <code>{task.job_id}</code><br>
            Путь к папке: <code>{html.escape(folder_path)}</code><br><br>
            <i>Обработка выполняется в фоновом режиме без блокировки сервера. Статус обновляется автоматически.</i>
        </div>'''
        csrf_tok = auth_service.get_csrf_token(self._get_session_token())
        body = render_upload_form(msg, csrf_token=csrf_tok, active_job_id=task.job_id)
        self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))

    def _handle_upload(self):
        if not self._verify_csrf():
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_forbidden_page(CSRF_INVALID_MSG)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 403)
            return

        tmp_dir, pdf_files = self._parse_multipart_to_disk()
        if pdf_files == "PAYLOAD_TOO_LARGE":
            max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form(f'<div class="err">❌ Превышен максимальный размер загрузки ({max_mb} MB). Уменьшите объем файлов или загрузите их частями.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok), 413)
            return

        if tmp_dir is None or not pdf_files:
            csrf_tok = auth_service.get_csrf_token(self._get_session_token())
            body = render_upload_form('<div class="err">Файлы не выбраны или не удалось разобрать запрос.</div>', csrf_token=csrf_tok)
            self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
            return

        cur_user = self._get_current_user() if hasattr(self, '_get_current_user') else {}
        cur_user = cur_user or {}
        username = cur_user.get('username', 'operator')
        client_ip = self._get_client_ip() if hasattr(self, '_get_client_ip') else '127.0.0.1'

        task = self.task_manager.submit_pdf_job(
            files=pdf_files,
            source='web_upload',
            spool_dir=tmp_dir,
            meta={'username': username, 'client_ip': client_ip}
        )

        auth_service.log_audit(
            username,
            client_ip,
            'UPLOAD_START',
            f"Запущена веб-загрузка {len(pdf_files)} файлов квитанций (задача: {task.job_id})"
        )

        total_files = len(pdf_files)
        files_label = f'{total_files} файл' + ('ов' if total_files >= 5 else ('а' if 2 <= total_files <= 4 else ''))
        msg = f'''<div class="ok">
            <b>Загрузка успешно принята в фоновую обработку: {files_label}</b><br><br>
            Идентификатор задачи: <code>{task.job_id}</code><br><br>
            <i>Файлы обрабатываются в фоновом режиме. Вы можете следить за прогрессом или закрыть страницу.</i>
        </div>'''
        csrf_tok = auth_service.get_csrf_token(self._get_session_token())
        body = render_upload_form(msg, csrf_token=csrf_tok, active_job_id=task.job_id)
        self.send_html(layout(body, 'upload', is_admin=True, csrf_token=csrf_tok))
