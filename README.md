# 📄 Kvit-App — Высокопроизводительный сервис квитанций и сверки счетов

[![CI Tests & Security](https://github.com/reallyaye/kvit_new/actions/workflows/tests.yml/badge.svg)](https://github.com/reallyaye/kvit_new/actions)
![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Security: Audited & Fuzzed](https://img.shields.io/badge/Security-Audited%20%26%20Fuzzed-success.svg)](SECURITY.md)

Современный промышленный сервис для обработки, шардированного хранения, сверки и выдачи квитанций по лицевым счетам (Web UI, WebSocket Real-time, gRPC API).

---

## 🚀 Возможности

1. **Многоуровневое распознавание и OCR**:
   - Быстрое извлечение векторного текстового слоя PDF (PyMuPDF).
   - Автоматический fallback на OCR (Tesseract: `rus+kaz+eng`) для сканированных растровых документов.
   - Поддержка гибких regex-паттернов для казахских и русских вариантов написания лицевых счетов и расчётных периодов.
   - Автоматическая группировка многостраничных квитанций.

2. **Двухуровневое шардирование хранилища**:
   - Масштабируемое распределение сотен тысяч PDF файлов: `receipts/80/01/800146_{hash}.pdf`.
   - Полная обратная совместимость с существующими плоскими квитанциями.
   - Встроенная команда автоматической миграции файловой системы.

3. **Безопасность промышленного уровня**:
   - **IDOR Protection**: выдача PDF по криптостойким 128-битным одноразовым токенам доступа.
   - **Path Traversal Protection**: строгая проверка путей через canonical sandbox `RECEIPTS_DIR`.
   - **Rate Limiting & IP Throttling**: алгоритм Sliding Window + ограничение конкурентных запросов и всплесков.
   - **Anti-Spoofing**: валидация цепочки `X-Forwarded-For` только от доверенных прокси-сетей.
   - **Timing Attack Resistance**: проверка паролей через `secrets.compare_digest`.
   - **Persistent Auth & Bans**: сохранение сессий и блокировок в SQLite для кластерной работы.

4. **Асинхронные интерфейсы**:
   - **Web UI**: отзывчивый интерфейс, drag-and-drop пакетная загрузка, постраничная сверка.
   - **WebSocket Gateway (RFC 6455)**: I/O мультиплексирование на Reactor Pattern (один поток на тысячи клиентов).
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

### 4. Тестирование
```bash
python run_tests.py
```

### 5. Запуск в Docker
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
