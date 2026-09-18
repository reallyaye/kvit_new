# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote, urlparse

import config
from services.appeals import appeal_service
from services.appeals.appeal_service import AppealValidationError, _clean
from services.security import auth_service
from templates import render_forbidden_page
from templates.layout import layout

logger = logging.getLogger('kvit.server.appeals')
CSRF_INVALID_MSG = 'Сессия истекла или передан неверный токен защиты (CSRF). Обновите страницу и попробуйте снова.'


class AppealHandlerMixin:
    """Обработчики подачи, статуса и модерации обращений граждан."""

    def _handle_appeal_submit(self):
        origin = self.headers.get('Origin', '').strip()
        host = self.headers.get('Host', '').split(':', 1)[0].strip().lower()
        if origin and urlparse(origin).hostname != host:
            self.send_json({
                'error': 'Forbidden',
                'message': 'Запрос отправлен с недоверенного сайта.',
            }, 403)
            return

        params = self._read_form_params(max_bytes=config.MAX_APPEAL_BODY_BYTES)
        if not params:
            return
        if params.get('website', [''])[0].strip():
            self.send_json({
                'error': 'Spam detected',
                'message': 'Обращение не принято.',
            }, 400)
            return

        payload = {
            field: params.get(field, [''])[0]
            for field in (
                'category', 'applicant_name', 'phone', 'email',
                'account_number', 'service_address', 'message', 'consent',
            )
        }
        try:
            appeal = appeal_service.create(
                payload,
                client_ip=self._get_client_ip(),
                user_agent=self.headers.get('User-Agent', ''),
            )
            notification = {'confirmation_sent': False}
            try:
                notification = appeal_service.notify(appeal)
            except Exception as exc:
                logger.warning(
                    '[Appeals] Уведомление не отправлено для %s: %s',
                    appeal['registration_number'],
                    exc,
                )
            try:
                auth_service.log_audit(
                    'public',
                    self._get_client_ip(),
                    'APPEAL_CREATE',
                    f"Зарегистрировано обращение {appeal['registration_number']} ({appeal['category']})",
                )
            except Exception as exc:
                logger.warning(
                    '[Appeals] Не удалось записать аудит для %s: %s',
                    appeal['registration_number'],
                    exc,
                )
            self.send_json({
                'success': True,
                'registration_number': appeal['registration_number'],
                'access_code': appeal.get('access_code'),
                'confirmation_sent': notification.get('confirmation_sent', False),
            }, 201)
        except AppealValidationError as exc:
            self.send_json({
                'error': 'Validation Error',
                'message': str(exc),
            }, 400)
        except Exception as exc:
            logger.exception('[Appeals] Не удалось зарегистрировать обращение: %s', exc)
            self.send_json({
                'error': 'Internal Server Error',
                'message': 'Не удалось зарегистрировать обращение. Попробуйте позднее.',
            }, 500, {'Cache-Control': 'no-store'})

    def _handle_appeal_status(self):
        origin = self.headers.get('Origin', '').strip()
        host = self.headers.get('Host', '').split(':', 1)[0].strip().lower()
        if origin and urlparse(origin).hostname != host:
            self.send_json({
                'error': 'Forbidden',
                'message': 'Запрос отправлен с недоверенного сайта.',
            }, 403, {'Cache-Control': 'no-store'})
            return
        params = self._read_form_params(max_bytes=config.MAX_APPEAL_BODY_BYTES)
        if not params:
            return
        reg_number = params.get('registration_number', [''])[0]
        credential = params.get('credential', [''])[0]
        try:
            public_info = appeal_service.get_public(reg_number, credential)
            self.send_json({'success': True, **public_info}, 200, {'Cache-Control': 'no-store, no-cache'})
        except AppealValidationError as exc:
            self.send_json({
                'error': 'Not Found',
                'message': str(exc),
            }, 404, {'Cache-Control': 'no-store, no-cache'})

    def _handle_admin_appeal_update(self):
        if not self._is_assistant_or_admin():
            self._redirect('/login')
            return
        params = self._read_form_params(max_bytes=config.MAX_APPEAL_BODY_BYTES)
        if not params:
            return
        csrf_token = params.get('csrf_token', [''])[0].strip()
        if not self._verify_csrf(body_csrf=csrf_token):
            self.send_html(
                layout(render_forbidden_page(CSRF_INVALID_MSG), is_admin=True),
                403,
            )
            return
        try:
            appeal_id = int(params.get('id', ['0'])[0])
            status = params.get('status', [''])[0].strip().upper()
            comment = params.get('admin_comment', [''])[0]
            action = params.get('action', ['save'])[0].strip().lower()
            current_user = self._get_current_user() or {}
            username = current_user.get('username', 'admin')

            old_appeal = appeal_service.get_by_id(appeal_id)
            if not old_appeal:
                self._redirect('/admin/appeals?error=' + quote('Обращение не найдено'))
                return

            old_status = old_appeal.get('status')
            old_text = old_appeal.get('response_text') or ''
            old_sent = bool(old_appeal.get('response_sent'))

            if action == 'respond':
                new_text = _clean(params.get('response_text', [''])[0], 10000)
                if old_status == 'ANSWERED' and old_text == new_text and old_sent:
                    appeal = appeal_service.update(
                        appeal_id,
                        'ANSWERED',
                        admin_comment=comment,
                        assigned_to=username,
                        response_text=None,
                        reset_sent=False,
                    )
                    status = 'ANSWERED'
                    result_message = 'Ответ опубликован и отправлен на email'
                else:
                    appeal = appeal_service.respond(
                        appeal_id,
                        new_text,
                        admin_comment=comment,
                        assigned_to=username,
                    )
                    email_sent = appeal_service.notify_response(appeal)
                    status = 'ANSWERED'
                    fresh_appeal = appeal_service.get_by_id(appeal_id) or appeal
                    email_ok = email_sent or bool(fresh_appeal.get('response_sent'))
                    result_message = (
                        'Ответ опубликован и отправлен на email'
                        if email_ok else 'Ответ опубликован. Email-уведомление не отправлено'
                    )
            else:
                raw_response_text = params.get('response_text', [None])[0]
                new_text = _clean(raw_response_text, 10000) if raw_response_text is not None else old_text
                status_changed = (status != old_status)
                text_changed = (raw_response_text is not None and new_text != old_text)
                unsent = not old_sent
                should_notify = (
                    status in ('ANSWERED', 'CLOSED', 'REJECTED')
                    and (status_changed or text_changed or unsent)
                )

                appeal = appeal_service.update(
                    appeal_id,
                    status,
                    admin_comment=comment,
                    assigned_to=username,
                    response_text=raw_response_text,
                    reset_sent=(status_changed or text_changed),
                )
                email_sent = False
                if should_notify:
                    email_sent = appeal_service.notify_response(appeal)

                fresh_appeal = appeal_service.get_by_id(appeal_id) or appeal
                email_ok = email_sent or bool(fresh_appeal.get('response_sent'))
                if email_ok:
                    result_message = 'Статус обновлён, уведомление отправлено на email'
                elif should_notify:
                    result_message = 'Изменения сохранены. Email-уведомление не отправлено'
                else:
                    result_message = 'Изменения сохранены'
            auth_service.log_audit(
                username,
                self._get_client_ip(),
                'APPEAL_UPDATE',
                f"Обращение {appeal['registration_number']}: статус {status}",
            )
            self._redirect(
                f'/admin/appeals/view?id={appeal_id}&msg={quote(result_message)}'
            )
        except (AppealValidationError, ValueError) as exc:
            appeal_id = params.get('id', ['0'])[0]
            self._redirect(
                f'/admin/appeals/view?id={quote(str(appeal_id))}&err={quote(str(exc))}'
            )
