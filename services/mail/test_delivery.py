"""
Комплексная диагностика и проверка почтовой службы (SMTP/DNS/Delivery) ТОО «КРЭК».

Поддерживает:
1. Проверку DNS-записей домена (MX, SPF, DKIM, DMARC) для krec.kz.
2. Проверку сетевого подключения, TLS/SSL рукопожатия и аутентификации SMTP.
3. Отправку тестового письма с замером времени и фиксацией метрик.
4. Вывод рекомендаций для dpo@krec.kz и info@krec.kz.
"""
import argparse
import json
import logging
import os
import smtplib
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, List, Optional

# Импортируем конфигурацию приложения
try:
    import config
except ImportError:
    # Если запуск вне контекста корня проекта
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    import config

logger = logging.getLogger('mail_delivery')

try:
    from services.metrics.collector import metrics_collector
except Exception:
    metrics_collector = None


def query_doh(name: str, qtype: str, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """
    Выполняет DNS-запрос через DNS-over-HTTPS (Google & Cloudflare).
    Не требует сторонних зависимостей (dnspython).
    """
    providers = [
        f"https://dns.google/resolve?name={urllib.parse.quote(name)}&type={urllib.parse.quote(qtype)}",
        f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(name)}&type={urllib.parse.quote(qtype)}",
    ]
    for url in providers:
        try:
            req = urllib.request.Request(
                url,
                headers={'Accept': 'application/dns-json', 'User-Agent': 'KrecMailTester/1.0'},
            )
            if not url.startswith('https://'):
                continue
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                data = json.loads(resp.read().decode('utf-8'))
                if 'Answer' in data:
                    return data['Answer']
                if 'Authority' in data:
                    return []
        except Exception:
            continue
    return []


def check_domain_dns(domain: str = 'krec.kz') -> Dict[str, Any]:
    """
    Проверяет наличие и корректность DNS-записей для доставки почты:
    - MX (почтовые серверы)
    - TXT / SPF (авторизованные отправители)
    - TXT / DMARC (_dmarc.<domain>)
    - TXT / DKIM (mail._domainkey.<domain>)
    """
    report = {
        'domain': domain,
        'mx_records': [],
        'spf_record': None,
        'dmarc_record': None,
        'dkim_record': None,
        'has_mx': False,
        'has_spf': False,
        'has_dmarc': False,
        'has_dkim': False,
        'recommendations': [],
    }

    # 1. Проверка MX
    mx_answers = query_doh(domain, 'MX')
    for ans in mx_answers:
        if ans.get('type') == 15:  # MX
            report['mx_records'].append(ans.get('data', ''))
    report['has_mx'] = len(report['mx_records']) > 0

    if not report['has_mx']:
        report['recommendations'].append(
            f"Для домена '{domain}' отсутствует MX-запись. Входящие письма на @{domain} не смогут доставляться."
        )

    # 2. Проверка SPF (TXT на корне домена)
    txt_answers = query_doh(domain, 'TXT')
    for ans in txt_answers:
        data = ans.get('data', '').strip('"')
        if data.startswith('v=spf1'):
            report['spf_record'] = data
            report['has_spf'] = True
            break

    if not report['has_spf']:
        report['recommendations'].append(
            f"Отсутствует SPF-запись для '{domain}'. Исходящие письма могут отклоняться спам-фильтрами. "
            f"Рекомендуется добавить TXT: 'v=spf1 redirect=_spf.mail.ru' (при использовании Mail.ru) "
            f"или 'v=spf1 ip4:79.140.225.194 ~all' (при отправке со своего сервера)."
        )

    # 3. Проверка DMARC
    dmarc_answers = query_doh(f"_dmarc.{domain}", 'TXT')
    for ans in dmarc_answers:
        data = ans.get('data', '').strip('"')
        if data.startswith('v=DMARC1'):
            report['dmarc_record'] = data
            report['has_dmarc'] = True
            break

    if not report['has_dmarc']:
        report['recommendations'].append(
            f"Отсутствует DMARC-запись для '{domain}'. Рекомендуется добавить TXT на _dmarc.{domain}: "
            f"'v=DMARC1; p=none; rua=mailto:dpo@{domain}'."
        )

    # 4. Проверка DKIM
    dkim_answers = query_doh(f"mail._domainkey.{domain}", 'TXT')
    for ans in dkim_answers:
        data = ans.get('data', '').strip('"')
        if 'v=DKIM1' in data or 'p=' in data:
            report['dkim_record'] = data
            report['has_dkim'] = True
            break

    return report


def check_smtp_connection(
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_ssl: Optional[bool] = None,
    use_tls: Optional[bool] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Проверяет сетевое соединение, TLS/SSL и авторизацию на SMTP-шлюзе.
    Возвращает подробный структурированный отчёт.
    """
    host = host or config.SMTP_HOST
    port = port or config.SMTP_PORT
    username = username if username is not None else config.SMTP_USERNAME
    password = password if password is not None else config.SMTP_PASSWORD
    use_ssl = use_ssl if use_ssl is not None else config.SMTP_USE_SSL
    use_tls = use_tls if use_tls is not None else config.SMTP_USE_TLS
    timeout = timeout or config.SMTP_TIMEOUT

    report = {
        'host': host,
        'port': port,
        'use_ssl': use_ssl,
        'use_tls': use_tls,
        'username': username,
        'password_set': bool(password),
        'tcp_connected': False,
        'ehlo_success': False,
        'tls_success': False,
        'auth_success': False,
        'latency_ms': None,
        'error_phase': None,
        'error_message': None,
        'error_code': None,
        'action_required': None,
    }

    if not host:
        report['error_phase'] = 'config'
        report['error_message'] = 'SMTP_HOST не настроен в конфигурации.'
        report['action_required'] = 'Укажите SMTP_HOST (например, smtp.mail.ru) в файле .env.'
        return report

    t_start = time.perf_counter()

    try:
        # 1. Установка TCP и SSL (при use_ssl=True)
        context = ssl.create_default_context()
        if use_ssl:
            client = smtplib.SMTP_SSL(host, port, context=context, timeout=timeout)
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        report['tcp_connected'] = True

        # 2. EHLO
        code, resp = client.ehlo()
        if code == 250:
            report['ehlo_success'] = True
        else:
            raise smtplib.SMTPResponseException(code, resp)

        # 3. STARTTLS (при use_tls=True и не SSL)
        if use_tls and not use_ssl:
            client.starttls(context=context)
            client.ehlo()
            report['tls_success'] = True
        elif use_ssl:
            report['tls_success'] = True

        # 4. Аутентификация
        if username:
            if not password:
                report['error_phase'] = 'auth'
                report['error_message'] = f"Имя пользователя указано ({username}), но пароль пустой."
                report['action_required'] = (
                    "Сгенерируйте и впишите Пароль приложения в .env (параметр SMTP_PASSWORD). "
                    "Для Mail.ru: Настройки → Безопасность → Пароли для внешних приложений."
                )
                client.quit()
                return report

            try:
                auth_code, auth_resp = client.login(username, password)
                report['auth_success'] = True
            except smtplib.SMTPAuthenticationError as auth_err:
                report['error_phase'] = 'auth'
                report['error_code'] = auth_err.smtp_code
                err_text = auth_err.smtp_error.decode('utf-8', errors='replace') if isinstance(auth_err.smtp_error, bytes) else str(auth_err.smtp_error)
                report['error_message'] = f"Ошибка авторизации ({auth_err.smtp_code}): {err_text}"
                if auth_err.smtp_code == 535:
                    report['action_required'] = (
                        "Mail.ru отклонил авторизацию (535): требуется Пароль для внешних приложений "
                        "(https://help.mail.ru/mail/security/protection/external). "
                        "Обычный пароль от почты не принимается почтовым шлюзом."
                    )
                else:
                    report['action_required'] = f"Проверьте правильность логина ({username}) и пароля."
                client.quit()
                return report

        # 5. Проверка работоспособности соединения NOOP
        try:
            client.noop()
        except Exception:
            pass

        client.quit()
        report['latency_ms'] = round((time.perf_counter() - t_start) * 1000, 2)

    except (socket.timeout, TimeoutError):
        report['error_phase'] = 'network'
        report['error_message'] = f"Превышен таймаут подключения ({timeout} сек.) к {host}:{port}."
        report['action_required'] = "Проверьте сетевой доступ и фаервол к SMTP-серверу."
    except ConnectionRefusedError:
        report['error_phase'] = 'network'
        report['error_message'] = f"В соединении с {host}:{port} отказано (Connection Refused)."
        report['action_required'] = f"Убедитесь, что порт {port} открыт на сервере {host}."
    except Exception as exc:
        report['error_phase'] = 'unexpected'
        report['error_message'] = f"{type(exc).__name__}: {str(exc)}"
        report['action_required'] = "Проверьте корректность настроек SMTP в .env."

    return report


def send_test_email(
    to_email: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    subject: Optional[str] = None,
    body_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Отправляет проверочное тестовое письмо на указанный адрес.
    """
    from_email = from_email or config.SMTP_FROM_EMAIL
    from_name = from_name or getattr(config, 'SMTP_FROM_NAME', 'ТОО «КРЭК»')
    subject = subject or "Тестовое уведомление почтового шлюза ТОО «КРЭК»"

    result = {
        'to': to_email,
        'from': from_email,
        'subject': subject,
        'success': False,
        'message_id': None,
        'latency_ms': None,
        'error': None,
    }

    if not config.SMTP_HOST:
        result['error'] = 'SMTP_HOST не настроен'
        return result

    msg_id = make_msgid(domain=from_email.split('@')[-1] if '@' in from_email else 'krec.kz')
    result['message_id'] = msg_id

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr((from_name, from_email))
    msg['To'] = to_email
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = msg_id

    plain_content = body_text or (
        f"Уважаемый пользователь!\n\n"
        f"Это служебное тестовое сообщение системы электронных обращений ТОО «КРЭК».\n"
        f"Дата и время отправки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Отправитель: {from_email}\n"
        f"Шлюз: {config.SMTP_HOST}:{config.SMTP_PORT}\n\n"
        f"Если вы получили это письмо, доставка почты функционирует штатно.\n\n"
        f"С уважением,\nТОО «Карагандинская Региональная Энергетическая Компания»\n"
        f"Контакты канцелярии: +7 (7212) 90-03-50 | info@krec.kz | dpo@krec.kz\n"
    )
    msg.set_content(plain_content)

    html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 20px;">
        <h2 style="color: #0f172a; margin: 0;">ТОО «КРЭК» — Проверка доставки почты</h2>
    </div>
    <p>Это автоматическое служебное сообщение проверки почтового шлюза веб-портала ТОО «КРЭК».</p>
    <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
        <tr><td style="padding: 6px; font-weight: bold; width: 140px;">Отправитель:</td><td style="padding: 6px;">{from_email}</td></tr>
        <tr><td style="padding: 6px; font-weight: bold;">Получатель:</td><td style="padding: 6px;">{to_email}</td></tr>
        <tr><td style="padding: 6px; font-weight: bold;">SMTP-шлюз:</td><td style="padding: 6px;">{config.SMTP_HOST}:{config.SMTP_PORT}</td></tr>
        <tr><td style="padding: 6px; font-weight: bold;">Время:</td><td style="padding: 6px;">{time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
    </table>
    <div style="margin-top: 24px; padding: 12px; background: #f8fafc; border-left: 4px solid #2563eb; font-size: 13px; color: #475569;">
        По вопросам защиты персональных данных: <a href="mailto:dpo@krec.kz" style="color:#2563eb;">dpo@krec.kz</a><br>
        Официальная канцелярия: <a href="mailto:info@krec.kz" style="color:#2563eb;">info@krec.kz</a> | +7 (7212) 90-03-50
    </div>
</body>
</html>"""
    msg.add_alternative(html_content, subtype='html')

    t_start = time.perf_counter()
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
            client.send_message(msg)

        result['success'] = True
        result['latency_ms'] = round((time.perf_counter() - t_start) * 1000, 2)
        if metrics_collector:
            metrics_collector.record_smtp_success()
    except Exception as exc:
        result['error'] = f"{type(exc).__name__}: {str(exc)}"
        if metrics_collector:
            metrics_collector.record_smtp_error(str(exc))
        logger.error("Failed to send test email to %s: %s", to_email, exc)

    return result


def run_diagnostics(target_email: Optional[str] = None, domain: str = 'krec.kz', send_actual: bool = False) -> Dict[str, Any]:
    """
    Запускает полный цикл диагностики:
    1. Анализ текущей конфигурации
    2. Проверка DNS домена krec.kz
    3. Проверка соединения и авторизации SMTP
    4. (Опционально) Тестовая отправка письма
    """
    dns_res = check_domain_dns(domain)
    smtp_res = check_smtp_connection()

    delivery_res = None
    if send_actual and target_email:
        delivery_res = send_test_email(target_email)

    return {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'config': {
            'SMTP_HOST': config.SMTP_HOST,
            'SMTP_PORT': config.SMTP_PORT,
            'SMTP_USERNAME': config.SMTP_USERNAME,
            'SMTP_FROM_EMAIL': config.SMTP_FROM_EMAIL,
            'APPEALS_NOTIFY_EMAIL': config.APPEALS_NOTIFY_EMAIL,
            'APPEALS_EMAIL_ENABLED': config.APPEALS_EMAIL_ENABLED,
            'SMTP_USE_SSL': config.SMTP_USE_SSL,
            'SMTP_USE_TLS': config.SMTP_USE_TLS,
            'SMTP_PASSWORD_SET': bool(config.SMTP_PASSWORD),
        },
        'dns_analysis': dns_res,
        'smtp_connection': smtp_res,
        'test_delivery': delivery_res,
    }


def main():
    parser = argparse.ArgumentParser(description="Диагностика почтового шлюза и доставки писем ТОО «КРЭК»")
    parser.add_argument('--send-to', dest='send_to', help='Email для отправки проверочного тестового письма')
    parser.add_argument('--domain', dest='domain', default='krec.kz', help='Домен для проверки DNS (по умолчанию: krec.kz)')
    parser.add_argument('--json', action='store_true', help='Вывести результат в формате JSON')
    args = parser.parse_args()

    should_send = bool(args.send_to)
    report = run_diagnostics(target_email=args.send_to, domain=args.domain, send_actual=should_send)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    # Человекочитаемый красивый вывод
    print("=" * 70)
    print(" ДИАГНОСТИКА ПОЧТОВОЙ СЛУЖБЫ ТОО «КРЭК» (krec.kz)")
    print("=" * 70)

    cfg = report['config']
    print("\n1. Текущая конфигурация приложения:")
    print(f"   SMTP_HOST:             {cfg['SMTP_HOST'] or '[НЕ ЗАДАНО]'}")
    print(f"   SMTP_PORT:             {cfg['SMTP_PORT']}")
    print(f"   SMTP_USE_SSL/TLS:      SSL={cfg['SMTP_USE_SSL']}, TLS={cfg['SMTP_USE_TLS']}")
    print(f"   SMTP_USERNAME:         {cfg['SMTP_USERNAME'] or '[НЕ ЗАДАНО]'}")
    print(f"   SMTP_PASSWORD:         {'[УСТАНОВЛЕН]' if cfg['SMTP_PASSWORD_SET'] else '[ОТСУТСТВУЕТ / ПУСТОЙ]'}")
    print(f"   SMTP_FROM_EMAIL:       {cfg['SMTP_FROM_EMAIL'] or '[НЕ ЗАДАНО]'}")
    print(f"   APPEALS_NOTIFY_EMAIL:  {cfg['APPEALS_NOTIFY_EMAIL'] or '[НЕ ЗАДАНО]'}")
    print(f"   APPEALS_EMAIL_ENABLED: {cfg['APPEALS_EMAIL_ENABLED']}")

    dns = report['dns_analysis']
    print(f"\n2. Состояние DNS домена '{args.domain}':")
    print(f"   MX записи:   {'ДА (' + ', '.join(dns['mx_records']) + ')' if dns['has_mx'] else 'НЕТ [Входящие письма на @krec.kz не работают]'}")
    print(f"   SPF запись:  {'ДА (' + dns['spf_record'] + ')' if dns['has_spf'] else 'НЕТ [Риск попадания исходящих в спам]'}")
    print(f"   DMARC:       {'ДА (' + dns['dmarc_record'] + ')' if dns['has_dmarc'] else 'НЕТ'}")
    print(f"   DKIM:        {'ДА' if dns['has_dkim'] else 'НЕТ'}")

    smtp = report['smtp_connection']
    print(f"\n3. Тест соединения с SMTP ({smtp['host']}:{smtp['port']}):")
    print(f"   TCP подключение:       {'УСПЕШНО' if smtp['tcp_connected'] else 'СБОЙ'}")
    print(f"   EHLO рукопожатие:      {'УСПЕШНО' if smtp['ehlo_success'] else 'СБОЙ'}")
    print(f"   Шифрование TLS/SSL:    {'УСПЕШНО' if smtp['tls_success'] else 'СБОЙ'}")
    print(f"   Аутентификация:        {'УСПЕШНО' if smtp['auth_success'] else 'СБОЙ'}")
    if smtp['latency_ms']:
        print(f"   Задержка (Latency):    {smtp['latency_ms']} ms")

    if smtp['error_message']:
        print(f"\n   [!] ОШИБКА: {smtp['error_message']}")
    if smtp['action_required']:
        print(f"   [!] ТРЕБУЕМОЕ ДЕЙСТВИЕ: {smtp['action_required']}")

    if report['test_delivery']:
        td = report['test_delivery']
        print(f"\n4. Тестовая отправка письма на {td['to']}:")
        if td['success']:
            print(f"   Статус:   УСПЕШНО отправлено за {td['latency_ms']} ms")
            print(f"   Message-ID: {td['message_id']}")
        else:
            print("   Статус:   СБОЙ")
            print(f"   Причина:  {td['error']}")

    print("\n" + "=" * 70)
    print(" РЕКОМЕНДАЦИИ И ШАГИ ДЛЯ dpo@krec.kz И info@krec.kz:")
    print("=" * 70)
    if dns['recommendations']:
        for i, rec in enumerate(dns['recommendations'], 1):
            print(f" {i}. {rec}")
    else:
        print(" Все DNS-записи в норме.")

    print("\n")


if __name__ == '__main__':
    main()
