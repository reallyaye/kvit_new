import re
import secrets
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage

import config
from database import get_db
from database.connection import write_transaction
from logger import logger
from services.metrics import metrics_collector

APPEAL_CATEGORIES = {
    'billing': 'Начисления и оплата',
    'connection': 'Подключение к электрическим сетям',
    'outage': 'Отключение электроэнергии',
    'meter': 'Приборы учёта',
    'quality': 'Качество электроснабжения',
    'complaint': 'Жалоба на обслуживание',
    'other': 'Другое',
}

APPEAL_STATUSES = {
    'NEW': 'Новое',
    'IN_REVIEW': 'На рассмотрении',
    'ANSWERED': 'Ответ направлен',
    'CLOSED': 'Закрыто',
    'REJECTED': 'Отклонено',
}

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_ACCOUNT_RE = re.compile(r'^[\w./-]*$', re.UNICODE)
_APPEAL_COLUMNS = (
    'id', 'registration_number', 'category', 'applicant_name', 'phone',
    'email', 'account_number', 'service_address', 'message', 'status',
    'consent', 'submitted_at', 'updated_at', 'client_ip', 'user_agent',
    'assigned_to', 'admin_comment', 'office_notified', 'confirmation_sent',
    'consent_version',
)


class AppealValidationError(ValueError):
    """Ошибка проверки данных публичного обращения."""


def _row_to_dict(row):
    if not row:
        return None
    return {column: row[index] for index, column in enumerate(_APPEAL_COLUMNS[:len(row)])}


def _clean(value, max_length):
    return str(value or '').strip()[:max_length]


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
        # Версия согласия жестко контролируется сервером для предотвращения фальсификации
        consent_version = ACTIVE_CONSENT_VERSION

        if category not in APPEAL_CATEGORIES:
            raise AppealValidationError('Выберите категорию обращения.')
        if len(applicant_name) < 2:
            raise AppealValidationError('Укажите ФИО заявителя или наименование организации.')
        digits = re.sub(r'\D', '', phone)
        if not 10 <= len(digits) <= 15:
            raise AppealValidationError('Укажите корректный контактный телефон.')
        if email and (len(email) > 254 or not _EMAIL_RE.fullmatch(email)):
            raise AppealValidationError('Укажите корректный адрес электронной почты.')
        if account_number and not _ACCOUNT_RE.fullmatch(account_number):
            raise AppealValidationError('Лицевой счёт содержит недопустимые символы.')
        if category in ('outage', 'connection') and len(service_address) < 5:
            raise AppealValidationError('Укажите адрес объекта электроснабжения.')
        elif service_address and len(service_address) < 5:
            raise AppealValidationError('Укажите корректный адрес объекта электроснабжения.')
        elif not service_address:
            service_address = 'Не указан'
        if len(message) < 10:
            raise AppealValidationError('Опишите суть обращения подробнее (не менее 10 символов).')
        if not consent:
            raise AppealValidationError('Необходимо согласие на обработку персональных данных.')

        return {
            'category': category,
            'applicant_name': applicant_name,
            'phone': phone,
            'email': email,
            'account_number': account_number,
            'service_address': service_address,
            'message': message,
            'consent': True,
            'consent_version': consent_version,
        }

    @staticmethod
    def _new_registration_number():
        suffix = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
        return f'ЭП-{datetime.now().strftime("%Y%m%d")}-{suffix}'

    def create(self, payload, client_ip='', user_agent=''):
        from services.analytics.stats_service import stats_service

        data = self.validate(payload)
        now = time.time()
        # Минимизация сетевых данных: не сохраняем сырой IP и сырой UA пользователя в открытом виде
        anonymized_ip = stats_service._hash_ip(client_ip, now) if client_ip else ''
        dev_info = stats_service.parse_user_agent(user_agent) if user_agent else ('desktop', 'Other', 'Other', False)
        safe_ua = f"{dev_info[0]} / {dev_info[1]}" if user_agent else ''

        for _ in range(5):
            registration_number = self._new_registration_number()
            try:
                with write_transaction() as con:
                    con.execute(
                        '''INSERT INTO appeals (
                            registration_number, category, applicant_name, phone, email,
                            account_number, service_address, message, status, consent,
                            submitted_at, updated_at, client_ip, user_agent, consent_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?, ?, ?, ?)''',
                        (
                            registration_number, data['category'], data['applicant_name'],
                            data['phone'], data['email'], data['account_number'],
                            data['service_address'], data['message'], data['consent'],
                            now, now, anonymized_ip, safe_ua, data['consent_version'],
                        ),
                    )
                appeal = self.get_by_registration_number(registration_number)
                if appeal:
                    return appeal
            except Exception as exc:
                if 'unique' not in str(exc).lower() and 'duplicate' not in str(exc).lower():
                    raise
        raise RuntimeError('Не удалось сформировать уникальный номер обращения.')

    def get_by_id(self, appeal_id):
        return self._get_one('id', appeal_id)

    def get_by_registration_number(self, registration_number):
        return self._get_one('registration_number', registration_number)

    @staticmethod
    def _get_one(field, value):
        if field not in ('id', 'registration_number'):
            raise ValueError('Unsupported appeal lookup field')
        con = get_db()
        try:
            # field выбирается только из закрытого списка выше; значение параметризовано.
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
        clauses = []
        params = []
        if status in APPEAL_STATUSES:
            clauses.append('status = ?')
            params.append(status)
        search = _clean(search, 200)
        if search:
            clauses.append(
                '(registration_number LIKE ? OR applicant_name LIKE ? OR email LIKE ? '
                'OR phone LIKE ? OR account_number LIKE ?)'
            )
            needle = f'%{search}%'
            params.extend([needle] * 5)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ''
        con = get_db()
        try:
            # where_sql составлен только из константных фрагментов; пользовательские значения параметризованы.
            total = con.execute(
                f'SELECT COUNT(*) FROM appeals{where_sql}',  # nosec B608
                tuple(params),
            ).fetchone()[0]
            rows = con.execute(
                f"SELECT {', '.join(_APPEAL_COLUMNS)} FROM appeals{where_sql} "  # nosec B608
                'ORDER BY submitted_at DESC LIMIT ? OFFSET ?',
                tuple(params + [per_page, (page - 1) * per_page]),
            ).fetchall()
            return {
                'items': [_row_to_dict(row) for row in rows],
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': max(1, (total + per_page - 1) // per_page),
            }
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

    def update(self, appeal_id, status, admin_comment='', assigned_to=''):
        if status not in APPEAL_STATUSES:
            raise AppealValidationError('Недопустимый статус обращения.')
        comment = _clean(admin_comment, 5000)
        assignee = _clean(assigned_to, 64)
        with write_transaction() as con:
            cursor = con.execute(
                '''UPDATE appeals SET status = ?, admin_comment = ?, assigned_to = ?,
                   updated_at = ? WHERE id = ?''',
                (status, comment, assignee, time.time(), int(appeal_id)),
            )
            if cursor.rowcount == 0:
                raise AppealValidationError('Обращение не найдено.')
        return self.get_by_id(int(appeal_id))

    def notify(self, appeal):
        result = {'office_notified': False, 'confirmation_sent': False}
        if not config.APPEALS_EMAIL_ENABLED or not config.SMTP_HOST or not config.SMTP_FROM_EMAIL:
            return result

        messages = []
        if config.APPEALS_NOTIFY_EMAIL:
            office = EmailMessage()
            office['Subject'] = f"Новое обращение {appeal['registration_number']}"
            office['From'] = config.SMTP_FROM_EMAIL
            office['To'] = config.APPEALS_NOTIFY_EMAIL
            office['Reply-To'] = appeal['email']
            office.set_content(self._office_email_body(appeal))
            messages.append(('office_notified', office))

        if appeal.get('email'):
            confirmation = EmailMessage()
            confirmation['Subject'] = f"Обращение зарегистрировано: {appeal['registration_number']}"
            confirmation['From'] = config.SMTP_FROM_EMAIL
            confirmation['To'] = appeal['email']
            confirmation.set_content(self._confirmation_email_body(appeal))
            messages.append(('confirmation_sent', confirmation))

        try:
            smtp_class = smtplib.SMTP_SSL if config.SMTP_USE_SSL else smtplib.SMTP
            context = ssl.create_default_context()
            kwargs = {'timeout': config.SMTP_TIMEOUT}
            if config.SMTP_USE_SSL:
                kwargs['context'] = context
            with smtp_class(config.SMTP_HOST, config.SMTP_PORT, **kwargs) as client:
                if config.SMTP_USE_TLS and not config.SMTP_USE_SSL:
                    client.starttls(context=context)
                if config.SMTP_USERNAME:
                    client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                for flag, message in messages:
                    try:
                        client.send_message(message)
                        result[flag] = True
                        metrics_collector.record_smtp_success()
                    except Exception as exc:
                        metrics_collector.record_smtp_error(str(exc))
                        logger.warning('[Appeals] Email %s failed for %s: %s', flag, appeal['registration_number'], exc)
        except Exception as exc:
            metrics_collector.record_smtp_error(str(exc))
            logger.warning('[Appeals] SMTP unavailable for %s: %s', appeal['registration_number'], exc)

        if any(result.values()):
            with write_transaction() as con:
                con.execute(
                    'UPDATE appeals SET office_notified = ?, confirmation_sent = ? WHERE id = ?',
                    (result['office_notified'], result['confirmation_sent'], appeal['id']),
                )
        return result

    @staticmethod
    def _office_email_body(appeal):
        return (
            f"Регистрационный номер: {appeal['registration_number']}\n"
            f"Категория: {APPEAL_CATEGORIES.get(appeal['category'], appeal['category'])}\n"
            f"Заявитель: {appeal['applicant_name']}\n"
            f"Телефон: {appeal['phone']}\n"
            f"Email: {appeal['email']}\n"
            f"Лицевой счёт: {appeal['account_number'] or 'не указан'}\n"
            f"Адрес: {appeal['service_address']}\n\n"
            f"Суть обращения:\n{appeal['message']}\n"
        )

    @staticmethod
    def _confirmation_email_body(appeal):
        return (
            f"Здравствуйте, {appeal['applicant_name']}!\n\n"
            f"Ваше обращение зарегистрировано под номером {appeal['registration_number']}.\n"
            "Срок рассмотрения — до 15 рабочих дней со дня поступления в соответствии с законодательством Республики Казахстан (АППК РК).\n"
            "Ответ будет направлен на этот адрес электронной почты.\n\n"
            "ТОО «КРЭК»"
        )

    def purge_expired_appeals(self, retention_days: int = 1095) -> int:
        """
        Обезличивает персональные данные всех обращений, срок хранения которых истёк (по умолчанию 3 года).
        Очищает ВСЕ персональные и идентифицирующие поля (ФИО, телефон, email, лицевой счет, адрес,
        текст, IP, User-Agent, комментарии оператора, назначенного сотрудника).
        Оставляет только деперсонализированные метаданные (номер, дата, категория, статус CLOSED).
        """
        cutoff = time.time() - (max(1, retention_days) * 86400.0)
        try:
            with write_transaction() as con:
                cur = con.execute(
                    '''UPDATE appeals
                       SET applicant_name = 'Обезличено (истёк срок хранения)',
                           phone = 'Обезличено',
                           email = '',
                           account_number = NULL,
                           service_address = 'Обезличено',
                           message = 'Текст обращения удален по истечении срока хранения персональных данных',
                           client_ip = '',
                           user_agent = '',
                           admin_comment = 'Обезличено по истечении срока хранения',
                           assigned_to = NULL,
                           status = 'CLOSED'
                       WHERE submitted_at < ?
                         AND (applicant_name != 'Обезличено (истёк срок хранения)' OR account_number IS NOT NULL)''',
                    (cutoff,),
                )
                affected = cur.rowcount if hasattr(cur, 'rowcount') and cur.rowcount != -1 else 0
                if affected == 0:
                    changes = con.execute("SELECT changes()").fetchone() if hasattr(con, 'execute') else None
                    affected = changes[0] if changes else 0
                logger.info("[Appeals] Обезличено %d архивных обращений старше %d дней", affected, retention_days)
                return affected
        except Exception as exc:
            logger.warning("[Appeals] Ошибка очистки архивных обращений: %s", exc)
            return 0


appeal_service = AppealService()
