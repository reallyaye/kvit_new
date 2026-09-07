import os
import secrets
import socket
import sys
import time
import traceback
from http.server import ThreadingHTTPServer

import config
from config import GRPC_HOST, GRPC_PORT, HOST, PORT
from database import migrate_db
from logger import logger
from server import AppRequestHandler
from services.grpc_service import create_grpc_server
from services.tasks import task_manager
from services.telegram_bot import telegram_bot_service
from services.websocket import ws_manager

INSECURE_SECRET_VALUES = {
    'kvit-secret-key-production-change-in-prod',
    'test_secure_secret_key_for_testing',
    'secret',
    'secretkey',
    'admin',
    'admin123',
    'changeme',
    'default',
    '12345678',
    'password',
}


def validate_startup_security() -> None:
    """Проверяет обязательные переменные безопасности перед стартом."""
    if config.IS_PRODUCTION:
        errors = []

        # 1. SECRET_KEY
        if not config.SECRET_KEY:
            errors.append("Переменная SECRET_KEY не задана.")
        elif len(config.SECRET_KEY) < 32:
            errors.append("SECRET_KEY слишком короткий (требуется не менее 32 символов).")
        elif config.SECRET_KEY.lower() in INSECURE_SECRET_VALUES:
            errors.append("SECRET_KEY использует известное тестовое/небезопасное значение.")

        # 2. ADMIN_PASSWORD_HASH
        if not config.ADMIN_PASSWORD_HASH:
            errors.append("Переменная ADMIN_PASSWORD_HASH не задана.")
        else:
            parts = config.ADMIN_PASSWORD_HASH.split('$')
            if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
                errors.append("ADMIN_PASSWORD_HASH не соответствует формату pbkdf2_sha256$<iterations>$<salt>$<hash>.")
            elif config.ADMIN_PASSWORD_HASH == 'pbkdf2_sha256$600000$c39a69e0d844f92023de12de1d2f2c54$63ad158940b48e73648c4d9d2d88099f7e0897529040f53c88ffcae75935daa5':
                errors.append("ADMIN_PASSWORD_HASH использует стандартный пароль по умолчанию (admin123).")

        # 3. GRPC_API_KEY
        if not config.GRPC_API_KEY:
            errors.append("Переменная GRPC_API_KEY не задана.")
        elif len(config.GRPC_API_KEY) < 16:
            errors.append("GRPC_API_KEY слишком короткий (требуется не менее 16 символов).")
        elif config.GRPC_API_KEY.lower() in INSECURE_SECRET_VALUES:
            errors.append("GRPC_API_KEY использует известное тестовое значение.")

        if errors:
            logger.error("=" * 70)
            logger.error("❌ ОШИБКА БЕЗОПАСНОСТИ PRODUCTION-КОНФИГУРАЦИИ:")
            for err in errors:
                logger.error(f"  • {err}")
            logger.error("")
            logger.error("Для генерации криптостойких секретов выполните команду:")
            logger.error("    python scripts/generate_secrets.py")
            logger.error("и укажите полученные значения в файле .env или переменных окружения.")
            logger.error("=" * 70)
            sys.exit(1)
    else:
        # Development / Test mode: fallback to ephemeral secrets if not specified
        if not config.SECRET_KEY:
            config.SECRET_KEY = secrets.token_hex(32)
            logger.info("ℹ️ [DEV] SECRET_KEY не задан. Сгенерирован временный ключ для текущей dev-сессии.")
        if not config.GRPC_API_KEY:
            config.GRPC_API_KEY = 'dev-grpc-insecure-key-local'
        if not config.ADMIN_PASSWORD_HASH:
            from services.security.auth_service import hash_password
            raw_pass = os.environ.get('ADMIN_PASSWORD', 'admin').strip()
            config.ADMIN_PASSWORD_HASH = hash_password(raw_pass)
            logger.info("ℹ️ [DEV] ADMIN_PASSWORD_HASH не задан. Используется dev-пароль.")



def get_local_ip() -> str:
    """Безопасно определяет локальный IP-адрес интерфейса."""
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except OSError:
        return '127.0.0.1'


def configure_tls(http_server: ThreadingHTTPServer) -> tuple[str, bool]:
    """Настраивает TLS при наличии сертификатов."""
    if not (config.USE_HTTPS or (config.SSL_CERT_PATH and config.SSL_KEY_PATH)):
        return "http", False

    if not (os.path.isfile(config.SSL_CERT_PATH) and os.path.isfile(config.SSL_KEY_PATH)):
        logger.error(f"❌ ОШИБКА TLS: Файлы сертификатов не найдены: cert='{config.SSL_CERT_PATH}', key='{config.SSL_KEY_PATH}'")
        sys.exit(1)

    import ssl
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_ctx.options |= getattr(ssl, 'OP_NO_SSLv2', 0) | getattr(ssl, 'OP_NO_SSLv3', 0) | getattr(ssl, 'OP_NO_TLSv1', 0) | getattr(ssl, 'OP_NO_TLSv1_1', 0)
    ssl_ctx.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384')
    ssl_ctx.load_cert_chain(certfile=config.SSL_CERT_PATH, keyfile=config.SSL_KEY_PATH)
    http_server.socket = ssl_ctx.wrap_socket(http_server.socket, server_side=True)
    return "https", True


def run_http_loop(http_server: ThreadingHTTPServer) -> None:
    """Запускает и поддерживает цикл обработки HTTP-запросов."""
    running = True
    while running:
        try:
            shut_down_event = getattr(http_server, '_BaseServer__is_shut_down', None)
            if shut_down_event is not None:
                shut_down_event.clear()
            http_server.serve_forever()
        except KeyboardInterrupt:
            running = False
            break
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            time.sleep(0.1)
        except Exception as loop_err:
            logger.warning(f"Внутренний сбой HTTP-сервера ({loop_err}), перезапуск потока...")
            time.sleep(0.5)


def main():
    logger.info("Запуск приложения...")
    validate_startup_security()

    try:
        migrate_db()
        logger.info("Миграции базы данных проверены.")
    except Exception as e:
        logger.critical("=" * 70)
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Сбой применения миграций БД: {e}")
        logger.critical("Запуск приложения остановлен во избежание повреждения данных.")
        logger.critical("=" * 70)
        sys.exit(1)

    grpc_server = create_grpc_server(host=GRPC_HOST, port=GRPC_PORT)
    grpc_server.start()

    if config.TELEGRAM_ENABLED and getattr(config, 'RUN_EMBEDDED_BOT', True):
        telegram_bot_service.start_in_thread()

    ThreadingHTTPServer.allow_reuse_address = True
    http_server = ThreadingHTTPServer((HOST, PORT), AppRequestHandler)
    http_server.daemon_threads = True

    protocol, is_tls = configure_tls(http_server)
    local_ip = get_local_ip()

    logger.info(f"Веб-сервер ({protocol.upper()}):     {protocol}://{HOST}:{PORT}")
    if HOST in ('0.0.0.0', '::') and local_ip not in ('127.0.0.1', '0.0.0.0'):  # nosec B104
        logger.info(f"  ➜ Локально на этом ПК:   {protocol}://localhost:{PORT}")
        logger.info(f"  ➜ С других ПК в сети:    {protocol}://{local_ip}:{PORT}")
    logger.info(f"WebSocket шлюз:      {'wss' if is_tls else 'ws'}://{HOST}:{PORT}/ws (Async Multiplexed)")
    logger.info(f"gRPC микросервис:    {GRPC_HOST}:{GRPC_PORT} (TLS={'ON' if config.GRPC_USE_TLS else 'OFF'})")
    if config.TELEGRAM_ENABLED and getattr(config, 'RUN_EMBEDDED_BOT', True):
        logger.info("Telegram-бот:        ВКЛЮЧЕН (встроенный фоновый поток Long Polling)")
    elif config.TELEGRAM_ENABLED:
        logger.info("Telegram-бот:        ВЫКЛЮЧЕН в веб-сервере (запуск через отдельный сервис bot.py)")
    else:
        logger.info("Telegram-бот:        ВЫКЛЮЧЕН (не задан TELEGRAM_BOT_TOKEN в .env)")
    if config.TRUST_PROXY:
        logger.info("Режим Reverse Proxy: TLS терминируется внешним прокси (Nginx/IIS/Traefik).")
    elif not is_tls:
        logger.info("Архитектура: сервис ожидает Reverse Proxy (Nginx/IIS) с TLS-терминацией перед собой.")

    if getattr(config, 'RUN_EMBEDDED_WORKER', True):
        task_manager.start()
        logger.info("Воркер задач:        ВКЛЮЧЕН (встроенный пул потоков)")
    else:
        logger.info("Воркер задач:        ВЫКЛЮЧЕН в веб-сервере (обработка через отдельный worker-контейнер)")

    try:
        run_http_loop(http_server)
    except KeyboardInterrupt:
        logger.info("Остановка серверов по сигналу завершения...")
    except Exception as e:
        logger.critical(f"Необработанное исключение: {e}\n{traceback.format_exc()}")
    finally:
        try:
            http_server.server_close()
        except Exception:
            pass
        ws_manager.stop()
        if config.TELEGRAM_ENABLED and getattr(config, 'RUN_EMBEDDED_BOT', True):
            telegram_bot_service.stop()
        grpc_server.stop(grace=1)
        if getattr(config, 'RUN_EMBEDDED_WORKER', True):
            task_manager.stop()
        logger.info("Все серверы успешно остановлены.")


if __name__ == '__main__':
    main()
