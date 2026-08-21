import sys, secrets
from http.server import ThreadingHTTPServer
import config
from config import HOST, PORT, GRPC_HOST, GRPC_PORT
from database import migrate_db
from server import AppRequestHandler
from services.grpc_service import create_grpc_server
from services.websocket import ws_manager
from logger import logger

def main():
    logger.info("Запуск приложения...")

    # 1. Проверка обязательного секрета gRPC
    if not config.GRPC_API_KEY:
        suggested_key = secrets.token_hex(32)
        logger.error("=" * 70)
        logger.error("❌ ОШИБКА КОНФИГУРАЦИИ: Переменная GRPC_API_KEY не задана!")
        logger.error("Для безопасности gRPC микросервис не может запускаться без секретного ключа.")
        logger.error("Сгенерирован криптостойкий ключ для вашего файла .env:\n")
        logger.error(f"    GRPC_API_KEY={suggested_key}\n")
        logger.error("Добавьте эту строку в файл .env и перезапустите приложение.")
        logger.error("=" * 70)
        sys.exit(1)

    # 2. Автоматические миграции базы данных
    migrate_db()
    logger.info("Миграции базы данных проверены.")

    # 2. Инициализация и запуск gRPC сервера
    grpc_server = create_grpc_server(host=GRPC_HOST, port=GRPC_PORT)
    grpc_server.start()

    # 3. Инициализация и запуск многопоточного HTTP/WebSocket сервера
    http_server = ThreadingHTTPServer((HOST, PORT), AppRequestHandler)

    logger.info(f"HTTP/Web сервер:     http://{HOST}:{PORT}")
    logger.info(f"WebSocket шлюз:      ws://{HOST}:{PORT}/ws (Async Multiplexed)")
    logger.info(f"gRPC микросервис:    {GRPC_HOST}:{GRPC_PORT}")
    logger.info("Система безопасности: IDOR Token, Rate Limiter, IP Throttler, gRPC Auth, WS Timeout")

    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Остановка серверов по сигналу завершения...")
        http_server.server_close()
        ws_manager.stop()
        grpc_server.stop(grace=2)
        logger.info("Все серверы успешно остановлены.")

if __name__ == '__main__':
    main()

