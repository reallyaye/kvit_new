# -*- coding: utf-8 -*-
import logging
import os
import shutil
from urllib.parse import parse_qs

import config
from database import purge_missing_receipts, sync_receipts_with_filesystem
from services.receipts import receipt_service
from services.security import auth_service
from services.websocket import ws_manager
from templates import (
    layout,
    render_404_page,
    render_forbidden_page,
)

logger = logging.getLogger('kvit.server.receipts')


class ReceiptHandlerMixin:
    """Обработчики безопасной отдачи PDF и управления квитанциями."""

    def _serve_pdf(self, path: str, q: dict):
        token = q.get('token', [''])[0].strip()
        fp = receipt_service.get_pdf_by_token(token)
        if not fp:
            if not token or len(token) != 32:
                body = render_forbidden_page()
                self.send_html(layout(body, 'search', is_admin=self._is_admin()), 403)
            else:
                body = render_404_page()
                self.send_html(layout(body, 'search', is_admin=self._is_admin()), 404)
            return

        disp = 'attachment; ' if path == '/download' else 'inline; '
        filename = os.path.basename(fp)

        if getattr(config, 'ENABLE_X_ACCEL_REDIRECT', False):
            try:
                rel_path = os.path.relpath(fp, config.RECEIPTS_DIR).replace('\\', '/')
            except ValueError:
                rel_path = filename
            x_accel_uri = f"{getattr(config, 'X_ACCEL_PREFIX', '/internal_receipts/')}{rel_path}"

            self.send_response(200)
            self._send_security_headers()
            self.send_header('X-Accel-Redirect', x_accel_uri)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition', f'{disp}filename="{filename}"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return

        try:
            file_size = os.path.getsize(fp)
            self.send_response(200)
            self._send_security_headers()
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Length', str(file_size))
            self.send_header('Content-Disposition', f'{disp}filename="{filename}"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

            with open(fp, 'rb') as f:
                shutil.copyfileobj(f, self.wfile, length=65536)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.error(f"[Server] Ошибка при потоковой отдаче PDF ({fp}): {e}")

    def _handle_api_delete_receipt(self):
        if not self._is_operator_or_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({
                'error': 'Forbidden',
                'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)',
            }, 403)
            return

        body_bytes = self._read_bounded_body(config.MAX_LOGIN_BODY_BYTES)
        if body_bytes is None:
            return
        params = parse_qs(body_bytes.decode('utf-8', errors='replace'))
        token = params.get('token', [''])[0].strip().lower()

        try:
            deleted = receipt_service.delete_receipt_by_token(token)
        except ValueError as exc:
            self.send_json({'error': 'Bad Request', 'message': str(exc)}, 400)
            return
        except LookupError as exc:
            self.send_json({'error': 'Not Found', 'message': str(exc)}, 404)
            return
        except Exception:
            logger.exception('[Receipts] Ошибка удаления квитанции оператором')
            self.send_json({
                'error': 'Internal Server Error',
                'message': 'Не удалось удалить квитанцию. Запись и файл оставлены без изменений.',
            }, 500)
            return

        current_user = self._get_current_user() or {}
        username = current_user.get('username', 'unknown')
        quarantine_text = 'да' if deleted['file_quarantined'] else 'файл отсутствовал на диске'
        auth_service.log_audit(
            username,
            self._get_client_ip(),
            'DELETE_RECEIPT',
            f"Лицевой счёт {deleted['account_number']}; период {deleted['period']}; PDF в карантине: {quarantine_text}",
        )
        ws_manager.broadcast('receipt_deleted', {
            'account_number': deleted['account_number'],
            'period': deleted['period'],
        })
        self.send_json({
            'success': True,
            'account_number': deleted['account_number'],
            'period': deleted['period'],
            'file_quarantined': deleted['file_quarantined'],
            'message': (
                f"Квитанция лицевого счёта {deleted['account_number']} "
                f"за период {deleted['period']} удалена."
            ),
        })

    def _handle_api_sync_receipts(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        import sys
        server_mod = sys.modules.get('server')
        _sync_fn = getattr(server_mod, 'sync_receipts_with_filesystem', sync_receipts_with_filesystem) if server_mod else sync_receipts_with_filesystem
        _ws_mgr = getattr(server_mod, 'ws_manager', ws_manager) if server_mod else ws_manager

        marked_missing, restored_ready, valid = _sync_fn()
        _ws_mgr.broadcast('receipts_synced', {
            'marked_missing': marked_missing,
            'restored_ready': restored_ready,
            'valid': valid
        })
        self.send_json({
            'success': True,
            'marked_missing': marked_missing,
            'restored_ready': restored_ready,
            'valid': valid,
            'message': f'Синхронизация завершена (обратимо): помечено missing — {marked_missing}, восстановлено — {restored_ready}, доступно на диске — {valid}'
        })

    def _handle_api_purge_missing_receipts(self):
        if not self._is_admin():
            self.send_json({'error': 'Unauthorized'}, 401)
            return

        if not self._verify_csrf():
            self.send_json({'error': 'Forbidden', 'message': 'Недействительный или отсутствующий CSRF-токен (X-CSRF-Token)'}, 403)
            return

        import sys
        server_mod = sys.modules.get('server')
        _purge_fn = getattr(server_mod, 'purge_missing_receipts', purge_missing_receipts) if server_mod else purge_missing_receipts
        _ws_mgr = getattr(server_mod, 'ws_manager', ws_manager) if server_mod else ws_manager

        purged_count = _purge_fn()
        _ws_mgr.broadcast('receipts_purged', {'purged': purged_count})
        self.send_json({
            'success': True,
            'purged': purged_count,
            'message': f'Очистка завершена: удалено {purged_count} записей со статусом missing.'
        })
