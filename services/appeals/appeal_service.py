import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlencode

import config
from database import get_db
from database.connection import write_transaction
from logger import logger
from services.metrics import metrics_collector

APPEAL_CATEGORIES = {
    'billing': 'Начисления и оплата', 'connection': 'Подключение к электрическим сетям',
    'outage': 'Отключение электроэнергии', 'meter': 'Приборы учёта',
    'quality': 'Качество электроснабжения', 'complaint': 'Жалоба на обслуживание',
    'other': 'Другое',
}

APPEAL_STATUSES = {
    'NEW': 'Новое', 'IN_REVIEW': 'На рассмотрении', 'ANSWERED': 'Ответ направлен',
    'CLOSED': 'Закрыто', 'REJECTED': 'Отклонено',
}

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_ACCOUNT_RE = re.compile(r'^[\w./-]*$', re.UNICODE)
_APPEAL_COLUMNS = (
    'id', 'registration_number', 'category', 'applicant_name', 'phone', 'email',
    'account_number', 'service_address', 'message', 'status', 'consent',
    'submitted_at', 'updated_at', 'client_ip', 'user_agent', 'assigned_to',
    'admin_comment', 'office_notified', 'confirmation_sent', 'consent_version',
    'public_token_hash', 'response_text', 'responded_at', 'response_sent',
    'response_version', 'response_lease', 'response_attempts',
)


class AppealValidationError(ValueError):
    """Ошибка проверки данных публичного обращения."""


def _row_to_dict(row):
    if not row:
        return None
    if hasattr(row, 'keys'):
        k = set(row.keys())
        return {c: row[c] for c in _APPEAL_COLUMNS if c in k}
    return {c: row[i] for i, c in enumerate(_APPEAL_COLUMNS[:len(row)])}


def _clean(value, max_length):
    return str(value or '').strip()[:max_length]


def _normalize_phone(value):
    return re.sub(r'\D', '', str(value or ''))


def _hash_access_code(value):
    return hashlib.sha256(re.sub(r'[^A-Z0-9]', '', str(value or '').upper()).encode('utf-8')).hexdigest()


ACTIVE_CONSENT_VERSION = 'v1.0-2026-kz'


class AppealService:
    def validate(self, payload):
        category = _clean(payload.get('category'), 32)
        applicant_name = _clean(payload.get('applicant_name'), 255)
        phone = _clean(payload.get('phone'), 64)
        email = _clean(payload.get('email'), 255).lower()
        account_number = _clean(payload.get('account_number'), 64)
        service_address = _clean(payload.get('service_address'), 500)
        message = _clean(payload.get('message'), 5000)
        consent = str(payload.get('consent', '')).lower() in ('1', 'true', 'yes', 'on')
        consent_version = ACTIVE_CONSENT_VERSION

        if category not in APPEAL_CATEGORIES:
            raise AppealValidationError('Выберите категорию обращения.')
        if len(applicant_name) < 2:
            raise AppealValidationError('Укажите ФИО заявителя или наименование организации.')
        if not 10 <= len(re.sub(r'\D', '', phone)) <= 15:
            raise AppealValidationError('Укажите корректный контактный телефон.')
        if email and (len(email) > 254 or not _EMAIL_RE.fullmatch(email)):
            raise AppealValidationError('Укажите корректный адрес электронной почты.')
        if account_number and not _ACCOUNT_RE.fullmatch(account_number):
            raise AppealValidationError('Лицевой счёт содержит недопустимые символы.')
        if (category in ('outage', 'connection') and len(service_address) < 5) or (service_address and len(service_address) < 5):
            raise AppealValidationError('Укажите корректный адрес объекта электроснабжения.')
        if not service_address:
            service_address = 'Не указан'
        if len(message) < 10:
            raise AppealValidationError('Опишите суть обращения подробнее (не менее 10 символов).')
        if not consent:
            raise AppealValidationError('Необходимо согласие на обработку персональных данных.')

        return {
            'category': category, 'applicant_name': applicant_name, 'phone': phone,
            'email': email, 'account_number': account_number, 'service_address': service_address,
            'message': message, 'consent': True, 'consent_version': consent_version,
        }

    @staticmethod
    def _new_registration_number():
        suffix = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
        return f'ЭП-{datetime.now().strftime("%Y%m%d")}-{suffix}'

    @staticmethod
    def _new_access_code():
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        raw = ''.join(secrets.choice(alphabet) for _ in range(15))
        return '-'.join(raw[index:index + 5] for index in range(0, 15, 5))

    def create(self, payload, client_ip='', user_agent=''):
        from services.analytics.stats_service import stats_service

        data = self.validate(payload)
        now = time.time()
        anonymized_ip = stats_service._hash_ip(client_ip, now) if client_ip else ''
        dev_info = stats_service.parse_user_agent(user_agent) if user_agent else ('desktop', 'Other', 'Other', False)
        safe_ua = f"{dev_info[0]} / {dev_info[1]}" if user_agent else ''

        for _ in range(5):
            registration_number, access_code = self._new_registration_number(), self._new_access_code()
            token_hash = _hash_access_code(access_code)
            try:
                with write_transaction() as con:
                    con.execute(
                        '''INSERT INTO appeals (
                            registration_number, category, applicant_name, phone, email,
                            account_number, service_address, message, status, consent,
                            submitted_at, updated_at, client_ip, user_agent, consent_version,
                            public_token_hash, response_version, response_lease
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?, ?, ?, ?, ?, 1, 0.0)''',
                        (
                            registration_number, data['category'], data['applicant_name'],
                            data['phone'], data['email'], data['account_number'],
                            data['service_address'], data['message'], data['consent'],
                            now, now, anonymized_ip, safe_ua, data['consent_version'], token_hash,
                        ),
                    )
                appeal = self.get_by_registration_number(registration_number)
                if appeal:
                    appeal['access_code'] = access_code
                    return appeal
            except Exception as exc:
                if 'unique' not in str(exc).lower() and 'duplicate' not in str(exc).lower():
                    raise
        raise RuntimeError('Не удалось сформировать уникальный номер обращения.')

    def get_by_id(self, appeal_id):
        return self._get_one('id', appeal_id)

    def get_by_registration_number(self, registration_number):
        return self._get_one('registration_number', registration_number)

    def get_public(self, registration_number, credential):
        reg = _clean(registration_number, 40).upper()
        cred = _clean(credential, 64)
        if not reg or not cred:
            raise AppealValidationError('Укажите номер обращения и код доступа.')
        appeal = self.get_by_registration_number(reg)
        if not appeal:
            raise AppealValidationError('Обращение не найдено или данные доступа неверны.')

        token_hash = appeal.get('public_token_hash') or ''
        if token_hash:
            exp_tok = self._make_access_token(appeal)
            auth = hmac.compare_digest(token_hash, _hash_access_code(cred)) or (bool(exp_tok) and hmac.compare_digest(exp_tok, cred))
        else:
            norm_cred = _normalize_phone(cred)
            auth = hmac.compare_digest(_normalize_phone(appeal.get('phone')), norm_cred) and len(norm_cred) >= 10
        if not auth:
            raise AppealValidationError('Обращение не найдено или данные доступа неверны.')
        return {
            'registration_number': appeal['registration_number'],
            'category': appeal['category'], 'status': appeal['status'],
            'submitted_at': appeal['submitted_at'], 'updated_at': appeal['updated_at'],
            'response_text': appeal.get('response_text') or '' if appeal['status'] in ('ANSWERED', 'CLOSED', 'REJECTED') else '',
            'responded_at': appeal.get('responded_at'),
        }

    @classmethod
    def _make_access_token(cls, appeal):
        token_hash, reg_num = appeal.get('public_token_hash') or '', appeal.get('registration_number') or ''
        secret = (getattr(config, 'SECRET_KEY', '') or '').strip().encode('utf-8')
        if not token_hash or not reg_num or not secret:
            return ''
        raw = hmac.new(secret, f'{reg_num}:{token_hash}'.encode('utf-8'), hashlib.sha256).hexdigest()[:15].upper()
        return '-'.join(raw[i:i + 5] for i in range(0, 15, 5))

    @staticmethod
    def _get_one(field, value):
        if field not in ('id', 'registration_number'):
            raise ValueError('Unsupported appeal lookup field')
        con = get_db()
        try:
            row = con.execute(
                f"SELECT {', '.join(_APPEAL_COLUMNS)} FROM appeals WHERE {field} = ?",  # nosec B608
                (value,),
            ).fetchone()
            return _row_to_dict(row)
        finally:
            con.close()

    def list(self, status='', search='', page=1, per_page=30):
        page = max(1, int(page or 1))
        per_page = min(100, max(1, int(per_page or 30)))
        clauses = ['status = ?'] if status in APPEAL_STATUSES else []
        params = [status] if status in APPEAL_STATUSES else []
        search = _clean(search, 200)
        if search:
            clauses.append('(registration_number LIKE ? OR applicant_name LIKE ? OR email LIKE ? OR phone LIKE ? OR account_number LIKE ?)')
            params.extend([f'%{search}%'] * 5)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
        con = get_db()
        try:
            total = con.execute(f'SELECT COUNT(*) FROM appeals{where_sql}', tuple(params)).fetchone()[0]  # nosec B608
            rows = con.execute(
                f"SELECT {', '.join(_APPEAL_COLUMNS)} FROM appeals{where_sql} ORDER BY submitted_at DESC LIMIT ? OFFSET ?",  # nosec B608
                tuple(params + [per_page, (page - 1) * per_page]),
            ).fetchall()
            return {'items': [_row_to_dict(r) for r in rows], 'total': total, 'page': page, 'per_page': per_page, 'pages': max(1, (total + per_page - 1) // per_page)}
        finally:
            con.close()

    @staticmethod
    def get_stats():
        con = get_db()
        try:
            rows = con.execute('SELECT status, COUNT(*) FROM appeals GROUP BY status').fetchall()
            result = {status: 0 for status in APPEAL_STATUSES}
            result.update({row[0]: row[1] for row in rows})
            result['TOTAL'] = sum(result[status] for status in APPEAL_STATUSES)
            return result
        finally:
            con.close()

    def update(self, appeal_id, status, admin_comment='', assigned_to='', response_text=None, reset_sent=False):
        if status not in APPEAL_STATUSES:
            raise AppealValidationError('Недопустимый статус обращения.')
        comment, assignee, now = _clean(admin_comment, 5000), _clean(assigned_to, 64), time.time()
        with write_transaction() as con:
            if response_text is not None:
                resp = _clean(response_text, 10000)
                cursor = con.execute(
                    '''UPDATE appeals SET status = ?, admin_comment = ?, assigned_to = ?, response_text = ?,
                       responded_at = CASE WHEN ? != '' THEN ? ELSE responded_at END,
                       response_version = CASE WHEN status = ? AND response_text = ? THEN response_version ELSE response_version + 1 END,
                       response_sent = CASE WHEN status = ? AND response_text = ? THEN response_sent ELSE FALSE END,
                       response_lease = CASE WHEN status = ? AND response_text = ? THEN response_lease ELSE 0.0 END,
                       response_attempts = CASE WHEN status = ? AND response_text = ? THEN response_attempts ELSE 0 END,
                       updated_at = ? WHERE id = ?''',
                    (status, comment, assignee, resp, resp, now,
                     status, resp, status, resp, status, resp, status, resp, now, int(appeal_id)),
                )
            else:
                cursor = con.execute(
                    '''UPDATE appeals SET status = ?, admin_comment = ?, assigned_to = ?,
                       response_version = CASE WHEN status = ? THEN response_version ELSE response_version + 1 END,
                       response_sent = CASE WHEN status = ? THEN response_sent ELSE FALSE END,
                       response_lease = CASE WHEN status = ? THEN response_lease ELSE 0.0 END,
                       response_attempts = CASE WHEN status = ? THEN response_attempts ELSE 0 END,
                       updated_at = ? WHERE id = ?''',
                    (status, comment, assignee, status, status, status, status, now, int(appeal_id)),
                )
            if cursor.rowcount == 0:
                raise AppealValidationError('Обращение не найдено.')
        return self.get_by_id(int(appeal_id))

    def respond(self, appeal_id, response_text, admin_comment='', assigned_to=''):
        response = _clean(response_text, 10000)
        if len(response) < 3:
            raise AppealValidationError('Введите текст ответа заявителю.')
        comment, assignee, now = _clean(admin_comment, 5000), _clean(assigned_to, 64), time.time()
        with write_transaction() as con:
            cursor = con.execute(
                '''UPDATE appeals SET status = 'ANSWERED', response_text = ?, responded_at = COALESCE(responded_at, ?),
                   response_version = CASE WHEN status = 'ANSWERED' AND response_text = ? THEN response_version ELSE response_version + 1 END,
                   response_sent = CASE WHEN status = 'ANSWERED' AND response_text = ? THEN response_sent ELSE FALSE END,
                   response_lease = CASE WHEN status = 'ANSWERED' AND response_text = ? THEN response_lease ELSE 0.0 END,
                   response_attempts = CASE WHEN status = 'ANSWERED' AND response_text = ? THEN response_attempts ELSE 0 END,
                   admin_comment = ?, assigned_to = ?, updated_at = ? WHERE id = ?''',
                (response, now, response, response, response, response, comment, assignee, now, int(appeal_id)),
            )
            if cursor.rowcount == 0:
                raise AppealValidationError('Обращение не найдено.')
        return self.get_by_id(int(appeal_id))

    @staticmethod
    def _send_smtp(messages, appeal_number):
        sent_keys = set()
        try:
            smtp_cls = smtplib.SMTP_SSL if config.SMTP_USE_SSL else smtplib.SMTP
            kwargs = {'timeout': config.SMTP_TIMEOUT, **({'context': ssl.create_default_context()} if config.SMTP_USE_SSL else {})}
            with smtp_cls(config.SMTP_HOST, config.SMTP_PORT, **kwargs) as client:
                if config.SMTP_USE_TLS and not config.SMTP_USE_SSL:
                    client.starttls(context=ssl.create_default_context())
                if config.SMTP_USERNAME:
                    client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                for flag, message in messages:
                    try:
                        client.send_message(message)
                        sent_keys.add(flag)
                        metrics_collector.record_smtp_success()
                    except Exception as exc:
                        metrics_collector.record_smtp_error(str(exc))
                        logger.warning('[Appeals] Email %s failed for %s: %s', flag, appeal_number, exc)
        except Exception as exc:
            metrics_collector.record_smtp_error(str(exc))
            logger.warning('[Appeals] SMTP unavailable for %s: %s', appeal_number, exc)
        return sent_keys

    def notify_response(self, appeal):
        appeal_id = int(appeal['id']) if isinstance(appeal, dict) else int(appeal)
        if not (config.APPEALS_EMAIL_ENABLED and config.SMTP_HOST and config.SMTP_FROM_EMAIL):
            return False
        now, lease_dur = time.time(), 60.0
        lease_until = round(now + lease_dur, 4)
        max_att = getattr(config, 'APPEALS_MAX_ATTEMPTS', 5)
        with write_transaction() as con:
            cur = con.execute(
                '''UPDATE appeals SET response_lease = ?
                   WHERE id = ? AND response_sent = FALSE
                     AND (response_attempts IS NULL OR response_attempts < ?)
                     AND (response_lease IS NULL OR response_lease < ?)''',
                (lease_until, appeal_id, max_att, now),
            )
            if cur.rowcount == 0:
                return False
            row = con.execute(
                f'SELECT {", ".join(_APPEAL_COLUMNS)} FROM appeals WHERE id = ?',
                (appeal_id,),
            ).fetchone()
            if not row:
                return False
            fresh = _row_to_dict(row)
            if isinstance(appeal, dict) and appeal.get('access_code'):
                fresh['access_code'] = appeal['access_code']
            appeal = fresh
            version = appeal['response_version']

        if not appeal.get('email') or appeal.get('status') not in ('ANSWERED', 'CLOSED', 'REJECTED'):
            with write_transaction() as con:
                con.execute('UPDATE appeals SET response_lease = 0.0 WHERE id = ? AND response_version = ? AND response_lease = ?', (appeal_id, version, lease_until))
            return False

        from_name = getattr(config, 'SMTP_FROM_NAME', 'ТОО «КРЭК»')
        from_hdr = formataddr((from_name, config.SMTP_FROM_EMAIL)) if from_name else config.SMTP_FROM_EMAIL
        message = EmailMessage()
        message['Subject'] = f"Ваше обращение {appeal['registration_number']} обработано — ТОО «КРЭК»"
        message['From'] = from_hdr
        message['To'] = appeal['email']
        message.set_content(self._processed_email_body(appeal))
        sent = self._send_smtp([('response_sent', message)], appeal['registration_number'])
        if 'response_sent' in sent:
            with write_transaction() as con:
                cur = con.execute(
                    '''UPDATE appeals
                       SET response_sent = TRUE, response_lease = 0.0, response_attempts = 0
                       WHERE id = ? AND response_version = ? AND response_lease = ?''',
                    (appeal_id, version, lease_until),
                )
                confirmed = cur.rowcount > 0
            return confirmed

        failed_at = time.time()
        attempts = int(appeal.get('response_attempts') or 0) + 1
        base_backoff = getattr(config, 'APPEALS_RETRY_BACKOFF_BASE', 30.0)
        backoff = min(3600.0, base_backoff * (2 ** min(attempts - 1, 6)))
        next_lease = (failed_at + backoff) if attempts < max_att else (failed_at + 31536000.0)
        with write_transaction() as con:
            con.execute(
                '''UPDATE appeals SET response_lease = ?, response_attempts = ?
                   WHERE id = ? AND response_version = ? AND response_lease = ?''',
                (next_lease, attempts, appeal_id, version, lease_until),
            )
        return False

    def retry_pending_responses(self, limit=20):
        if not (config.APPEALS_EMAIL_ENABLED and config.SMTP_HOST and config.SMTP_FROM_EMAIL):
            return 0
        now, con, max_att = time.time(), get_db(), getattr(config, 'APPEALS_MAX_ATTEMPTS', 5)
        try:
            rows = con.execute(
                '''SELECT id FROM appeals
                   WHERE status IN ('ANSWERED', 'CLOSED', 'REJECTED')
                     AND response_sent = FALSE AND email IS NOT NULL AND email != ''
                     AND (response_attempts IS NULL OR response_attempts < ?)
                     AND (response_lease IS NULL OR response_lease < ?)
                   ORDER BY updated_at ASC LIMIT ?''',
                (max_att, now, int(limit)),
            ).fetchall()
        finally:
            con.close()
        sent_count = 0
        for row in rows:
            app = self.get_by_id(row[0])
            if app and self.notify_response(app):
                sent_count += 1
        return sent_count

    def notify(self, appeal):
        result = {'office_notified': False, 'confirmation_sent': False}
        if not config.APPEALS_EMAIL_ENABLED or not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
            return result
        messages, from_name = [], getattr(config, 'SMTP_FROM_NAME', 'ТОО «КРЭК»')
        from_hdr = formataddr((from_name, config.SMTP_FROM_EMAIL)) if from_name else config.SMTP_FROM_EMAIL
        if config.APPEALS_NOTIFY_EMAIL:
            off = EmailMessage()
            off['Subject'], off['From'], off['To'] = f"Новое обращение {appeal['registration_number']}", from_hdr, config.APPEALS_NOTIFY_EMAIL
            if appeal.get('email'):
                off['Reply-To'] = appeal['email']
            off.set_content(self._office_email_body(appeal))
            messages.append(('office_notified', off))
        if appeal.get('email'):
            conf = EmailMessage()
            conf['Subject'], conf['From'], conf['To'] = f"Обращение зарегистрировано: {appeal['registration_number']}", from_hdr, appeal['email']
            conf.set_content(self._confirmation_email_body(appeal))
            messages.append(('confirmation_sent', conf))
        sent = self._send_smtp(messages, appeal['registration_number'])
        result['office_notified'] = 'office_notified' in sent
        result['confirmation_sent'] = 'confirmation_sent' in sent
        if any(result.values()):
            with write_transaction() as con:
                con.execute('UPDATE appeals SET office_notified = ?, confirmation_sent = ? WHERE id = ?', (result['office_notified'], result['confirmation_sent'], appeal['id']))
        return result

    @classmethod
    def _processed_email_body(cls, appeal):
        status_name = APPEAL_STATUSES.get(appeal.get('status'), 'Обработано')
        category_name = APPEAL_CATEGORIES.get(appeal.get('category'), appeal.get('category', ''))
        code = appeal.get('access_code') or cls._make_access_token(appeal)
        frag = urlencode({'number': appeal['registration_number'], **({'code': code} if code else {})})
        status_url = f"{config.PUBLIC_BASE_URL}/appeals/status#{frag}"
        code_line = f"Код доступа: {code}\n" if code else ''
        resp_line = f"\nОтвет организации:\n{appeal['response_text']}\n" if appeal.get('response_text') else ''
        return (
            f"Здравствуйте, {appeal['applicant_name']}!\n\n"
            f"Ваше обращение {appeal['registration_number']} по теме «{category_name}» было обработано.\n"
            f"Текущий статус: {status_name}.\n{code_line}{resp_line}\n"
            f"Проверить статус и ответ можно на сайте:\n{status_url}\n\n"
            "С уважением,\nТОО «Карагандинская региональная электросетевая компания» (ТОО «КРЭК»)"
        )

    @staticmethod
    def _office_email_body(appeal):
        return (
            f"Регистрационный номер: {appeal['registration_number']}\nКатегория: {APPEAL_CATEGORIES.get(appeal['category'], appeal['category'])}\n"
            f"Заявитель: {appeal['applicant_name']}\nТелефон: {appeal['phone']}\nEmail: {appeal['email']}\n"
            f"Лицевой счёт: {appeal['account_number'] or 'не указан'}\nАдрес: {appeal['service_address']}\n\nСуть обращения:\n{appeal['message']}\n"
        )

    @staticmethod
    def _confirmation_email_body(appeal):
        code = appeal.get('access_code') or ''
        access_line = f"\nКод доступа: {code}\n" if code else ''
        personal_url = f"\nПерсональная ссылка: {config.PUBLIC_BASE_URL}/appeals/status#{urlencode({'number': appeal['registration_number'], 'code': code})}\n" if code else ''
        return (
            f"Здравствуйте, {appeal['applicant_name']}!\n\n"
            f"Ваше обращение зарегистрировано под номером {appeal['registration_number']}.\n"
            f"{access_line}{personal_url}"
            "Сохраните персональную ссылку: по ней можно открыть статус и ответ.\n"
            "Срок рассмотрения — до 15 рабочих дней со дня поступления (ст. 76 АППК РК).\n"
            "Ответ будет направлен на этот адрес электронной почты.\n\nТОО «КРЭК»"
        )

    def purge_expired_appeals(self, retention_days: int = 1095) -> int:
        """Обезличивает персональные данные всех обращений, срок хранения которых истёк."""
        cutoff = time.time() - (max(1, retention_days) * 86400.0)
        try:
            with write_transaction() as con:
                cur = con.execute(
                    """UPDATE appeals
                       SET applicant_name = 'Обезличено (истёк срок хранения)', phone = 'Обезличено',
                           email = '', account_number = NULL, service_address = 'Обезличено',
                           message = 'Текст обращения удален по истечении срока хранения персональных данных',
                           client_ip = '', user_agent = '', admin_comment = 'Обезличено по истечении срока хранения',
                           assigned_to = NULL, response_text = '', public_token_hash = NULL, status = 'CLOSED'
                       WHERE submitted_at < ?
                         AND (applicant_name != 'Обезличено (истёк срок хранения)'
                              OR account_number IS NOT NULL OR public_token_hash IS NOT NULL OR response_text != '')""",
                    (cutoff,),
                )
                affected = max(0, getattr(cur, 'rowcount', 0))
                logger.info("[Appeals] Обезличено %d архивных обращений старше %d дней", affected, retention_days)
                return affected
        except Exception as exc:
            logger.warning("[Appeals] Ошибка очистки архивных обращений: %s", exc)
            return 0


appeal_service = AppealService()
