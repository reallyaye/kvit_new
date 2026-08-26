# 📄 Kvit-App — Высокопроизводительный сервис квитанций и сверки счетов

[![CI Tests & Security](https://github.com/reallyaye/kvit_new/actions/workflows/tests.yml/badge.svg)](https://github.com/reallyaye/kvit_new/actions)
![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Security: Audited & Fuzzed](https://img.shields.io/badge/Security-Audited%20%26%20Fuzzed-success.svg)](SECURITY.md)

Современный промышленный сервис для обработки, шардированного хранения, сверки и выдачи квитанций по лицевым счетам (Web UI, WebSocket Real-time, gRPC API).

---

## 🚨 Обязательные шаги перед продакшн-деплоем (Security Checklist)

Приложение использует **Fail-Fast архитектуру**: при отсутствии обязательных ключей и паролей в окружении сервис завершает работу с кодом `1` и выводит подсказки по настройке. Перед запуском на сервере обязательно настройте файл `.env`:

1. **Сгенерируйте секретный ключ gRPC (`GRPC_API_KEY`)**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   *Скопируйте полученное 64-символьное значение в `.env`.*

2. **Захешируйте пароль администратора (`ADMIN_PASSWORD_HASH`)**:
   ```bash
   python -c "from services.security.auth_service import hash_password; print(hash_password('ваш_надежный_пароль'))"
   ```
   *В боевом окружении пароли в открытом виде не хранятся — сохраните полученный PBKDF2-хеш в `.env`.*

3. **Настройте путь к хранилищу квитанций на выделенном диске**:
   ```ini
   # Windows Server (второй диск D:)
   RECEIPTS_DIR=D:/ReceiptsStorage
   # Linux / Debian (отдельная точка монтирования)
   RECEIPTS_DIR=/mnt/storage/receipts
   ```

4. **Включите доверие к Reverse Proxy (`TRUST_PROXY=true`)**:
   * Если приложение работает за Nginx или Windows Server IIS, укажите `TRUST_PROXY=true` для корректной работы Rate Limiting и логирования реальных IP-адресов.

---

## 🚀 Возможности и архитектура

1. **Многоуровневое распознавание и OCR**:
   - Быстрое извлечение векторного текстового слоя PDF (PyMuPDF).
   - Автоматический fallback на OCR (Tesseract: `rus+kaz+eng`) для сканированных растровых документов.
   - Поддержка гибких regex-паттернов для казахских и русских вариантов написания лицевых счетов и расчётных периодов.
   - Автоматическая группировка многостраничных квитанций.

2. **Двухуровневое шардирование хранилища**:
   - Масштабируемое распределение файлов по структуре: `receipts/80/01/800146_{hash}.pdf`.
   - Полная обратная совместимость с существующими плоскими квитанциями.
   - Встроенная команда автоматической миграции файловой системы (`--migrate-sharding`).

3. **Комплекс мер безопасности**:
   - **IDOR Protection**: выдача PDF по криптостойким 128-битным одноразовым токенам доступа.
   - **PBKDF2 Password Hashing**: хранение безопасных хешей (SHA-256, 600k итераций, уникальная соль) вместо открытых паролей.
   - **Path Traversal Protection**: строгая проверка путей через canonical sandbox `RECEIPTS_DIR`.
   - **Rate Limiting & IP Throttling**: алгоритм Sliding Window + ограничение конкурентных запросов и автоматическая блокировка DDoS.
   - **Anti-Spoofing**: валидация цепочки `X-Forwarded-For` только от доверенных прокси-сетей (`TRUSTED_PROXIES`).
   - **Timing Attack Resistance**: проверка паролей и токенов через `secrets.compare_digest`.
   - **Fuzzed Network Parsers**: защита потокового multipart и WebSocket RFC 6455 парсеров от OOM, гигантских заголовков и аномальных фреймов.

4. **Асинхронные интерфейсы и микросервисы**:
   - **Web UI**: отзывчивый интерфейс, drag-and-drop пакетная загрузка, постраничная сверка с фильтрами.
   - **WebSocket Gateway (RFC 6455)**: I/O мультиплексирование на Reactor Pattern (один фоновый поток на тысячи клиентов).
   - **gRPC Microservice**: микросервис с поддержкой Protobuf, streaming PDF и интерцепторами авторизации и rate limit.

---

## 🛠️ Установка и запуск

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Импорт реестра и квитанций
```bash
# Импорт реестра счетов и PDF квитанций
python import_data.py --accounts "лицевые все.xlsx" --receipts "квитанции.pdf"

# Миграция существующей плоской папки receipts/ в 2-уровневое шардирование
python import_data.py --migrate-sharding
```

### 3. Запуск сервиса
```bash
python app.py
```
- **Web UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **WebSocket**: `ws://127.0.0.1:8000/ws`
- **gRPC**: `127.0.0.1:50051`
- **Telegram-бот**: фоновый поток (если задан `TELEGRAM_BOT_TOKEN`) или автономно: `python bot.py`

### 4. Использование Telegram-бота 🤖
1. Создайте бота через [@BotFather](https://t.me/BotFather) и скопируйте токен.
2. В файле `.env` настройте:
   ```ini
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   # Разрешенные ID администраторов для загрузки (через запятую):
   TELEGRAM_ADMIN_IDS=123456789,987654321
   ```
3. **Возможности бота**:
   - 📤 **Загрузка квитанций**: просто отправьте PDF-файл в чат боту — он автоматически распознает лицевые счета, периоды, распределит по папкам и сохранит в базу с подробным отчётом.
   - 🔍 **Поиск квитанций**: отправьте номер счёта (например, `800146` или `/kvit 800146`) либо точный адрес (`/address ул. Абая 10, кв 5`) — бот пришлёт PDF-файл квитанции прямо в чат Telegram.
   - 📊 **Статистика и сверка**: команда `/stats` показывает количество счетов, загруженных квитанций, сирот и процент покрытия.
   - 🔐 **Безопасность**: проверка по списку `TELEGRAM_ADMIN_IDS` либо вход по паролю через `/login <пароль>`.

### 5. Тестирование
```bash
python run_tests.py
```

### 6. Запуск в Docker
```bash
docker-compose up --build -d
```


---

## 🔒 Сетевая архитектура и TLS / HTTPS

> **Важно:** По умолчанию сервис слушает внутренний HTTP/WebSocket порт (`127.0.0.1:8000`) и gRPC (`0.0.0.0:50051`).  
> **Рекомендуемая продакшн-архитектура:** Сервис ожидает Reverse Proxy (Nginx, Traefik, Caddy или IIS на Windows Server) с TLS-терминацией перед собой.

### Вариант 1: Развёртывание за Nginx (Linux / Debian)
В файле `.env` установите:
```ini
TRUST_PROXY=true
TRUSTED_PROXIES=127.0.0.1,::1
```

Пример конфигурации `/etc/nginx/sites-available/kvit`:
```nginx
server {
    listen 443 ssl http2;
    server_name kvit.your-company.kz;

    ssl_certificate /etc/letsencrypt/live/kvit.your-company.kz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kvit.your-company.kz/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket поддержка
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Передача реального IP для Rate Limiting и IP Throttling
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Вариант 2: Развёртывание на Windows Server (IIS как Reverse Proxy)
1. Установите в IIS модули **URL Rewrite** и **Application Request Routing (ARR)**.
2. В IIS включите проксирование (Server Proxy Settings → Enable proxy).
3. Создайте правило перенаправления с SSL-сайта (порт 443) на `http://127.0.0.1:8000`.
4. В `.env` задайте `TRUST_PROXY=true`.

### Вариант 3: Прямой запуск со встроенным TLS (без Reverse Proxy)
Если требуется поднять HTTPS напрямую силами Python:
1. Поместите SSL-сертификаты на сервер.
2. В `.env` укажите:
```ini
USE_HTTPS=true
SSL_CERT_PATH=/path/to/fullchain.pem
SSL_KEY_PATH=/path/to/privkey.pem
```
Сервис автоматически обернет серверный сокет через `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)`.
