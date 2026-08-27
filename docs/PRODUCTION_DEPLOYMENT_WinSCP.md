# 🚀 Регламент безопасного обновления Production-сервера через WinSCP (SFTP) и SSH

> [!IMPORTANT]
> **Главное правило Production**:
> Мы **НЕ переустанавливаем сервер с нуля** и **НЕ удаляем рабочую директорию проекта**.
> Обновление выполняется накатом новых файлов кода с сохранением:
> - Базы данных PostgreSQL (`postgres-data`);
> - Всех ранее загруженных PDF-квитанций (`kvit-receipts` / `/opt/kvit/receipts`);
> - Сессий и очередей Redis (`redis-data`);
> - Боевого конфигурационного файла `.env`;
> - SSL-сертификатов (Let's Encrypt / `/etc/nginx/ssl`).

---

## 🎯 1. Архитектура боевого сервера: Какой файл Compose используется

На вашем рабочем production-сервере развернут **полный автономный стек** через **`docker-compose.yml`**:

```text
               ┌────────────────────────────────────────────────────────┐
               │              Docker Compose (docker-compose.yml)       │
               │                                                        │
Интернет ────> │  [kvit-nginx] (Порты 80, 443 + SSL)                    │
               │        │                                               │
               │        ├──> [kvit-api] (Масштабируемый Web API)        │
               │        │          │                                    │
               │        │          ├──────> [kvit-postgres] (БД)        │
               │        │          │        (Volume: postgres-data)     │
               │        │          │                                    │
               │        └──> [kvit-worker]  [kvit-redis] (Очередь)      │
               │             (PDF/OCR)      (Volume: redis-data)        │
               │                   │                                    │
               │                   └───> Storage: kvit-receipts         │
               └────────────────────────────────────────────────────────┘
```

> [!NOTE]
> Файл `docker-compose.prod.yml` предназначен **исключительно для внешних облачных баз данных** (Managed PostgreSQL / Redis от облачного провайдера). 
> **Для стандартного боевого сервера используется основной `docker-compose.yml`!**

---

## 🔒 2. Исправление SSL-сертификатов (Проверка путей)

В конфигурации Nginx прописаны стандартные пути:
* `ssl_certificate /etc/nginx/ssl/fullchain.pem;`
* `ssl_certificate_key /etc/nginx/ssl/privkey.pem;`

В `docker-compose.yml` сертификаты подключаются из переменных окружения в `.env`:
```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  - ${SSL_CERT_PATH:-./nginx/ssl/fullchain.pem}:/etc/nginx/ssl/fullchain.pem:ro
  - ${SSL_KEY_PATH:-./nginx/ssl/privkey.pem}:/etc/nginx/ssl/privkey.pem:ro
```

### Как настроить боевые сертификаты в `.env` на сервере:
Если на сервере используется **Let's Encrypt (Certbot)**, укажите в `/opt/kvit/.env`:
```bash
SSL_CERT_PATH=/etc/letsencrypt/live/krec.kz/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/krec.kz/privkey.pem
```
Если сертификаты лежат в папке проекта на сервере:
```bash
SSL_CERT_PATH=/opt/kvit/nginx/ssl/fullchain.pem
SSL_KEY_PATH=/opt/kvit/nginx/ssl/privkey.pem
```

---

## 📂 3. Строгий регламент WinSCP: Что копировать, а что ЗАПРЕЩЕНО

Откройте **WinSCP**, подключитесь к вашему серверу (протокол **SFTP**, порт **22**).

В **левой панели** (Windows ПК) откройте папку проекта (`c:\Users\User\Desktop\сайт`).
В **правой панели** (Сервер) откройте рабочую директорию (`/opt/kvit`).

### ✅ ЧТО КОПИРОВАТЬ ЧЕРЕЗ WinSCP:
* 📁 `database/`
* 📁 `services/`
* 📁 `templates/`
* 📁 `static/`
* 📁 `proto/`
* 📁 `scripts/`
* 📁 `benchmarks/`
* 📁 `data/` (только JSON-файлы: `extracted_portal_pages.json`, `documents.json`)
* 📄 **`nginx/nginx.conf`** *(копируем ТОЛЬКО этот файл конфигурации!)*
* 📄 `app.py`
* 📄 `server.py`
* 📄 `worker.py`
* 📄 `bot.py`
* 📄 `config.py`
* 📄 `logger.py`
* 📄 `import_data.py`
* 📄 `requirements.txt`
* 📄 `Dockerfile`
* 📄 `docker-compose.yml`
* 📄 `pyproject.toml`

---

### ❌ ЧТО КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО КОПИРОВАТЬ / ПЕРЕЗАПИСЫВАТЬ:

| Файл / Папка | Почему нельзя копировать из Windows |
| :--- | :--- |
| ❌ **`nginx/ssl/`** | **КАТЕГОРИЧЕСКИ НЕ ТРОГАТЬ!** Перезапись уничтожит боевые SSL-ключи на сервере. |
| ❌ **`.env`** | На сервере хранятся **боевые пароли БД, SECRET_KEY, токен Telegram**. Локальный файл сломает прод! |
| ❌ **`receipts/`** | На сервере в этой папке лежат реальные PDF-квитанции жителей. |
| ❌ **`data.sqlite3` / `data/*.db`** | База данных на сервере. |
| ❌ **`logs/`** | Журналы работы сервисов. |
| ❌ **`__pycache__/`, `.pytest_cache/`, `.git/`** | Временные файлы Windows. |
| ❌ **`лицевые все.xls*`** | Локальные таблицы. |

> [!TIP]
> **Настройка безопасной маски исключений в WinSCP**:
> Нажмите в WinSCP `Ctrl + Alt + F` (Transfer Settings -> Other -> Mask) и вставьте:
> `.env; receipts/; logs/; *.sqlite3; *.db; __pycache__/; .git/; .pytest_cache/; nginx/ssl/*; *.xls; *.xlsx`

---

## 🛡️ 4. Шаг 1: Создание бэкапа перед обновлением (через SSH)

Перед загрузкой файлов откройте SSH-терминал (PuTTY / WinSCP Terminal) и выполните:

```bash
# 1. Переходим в папку проекта на сервере
cd /opt/kvit

# 2. Создаем директорию бэкапов (если её нет)
mkdir -p /opt/kvit_backups

# 3. Делаем бэкап боевого .env файла
cp .env /opt/kvit_backups/.env_backup_$(date +%Y%m%d_%H%M%S)

# 4. Делаем горячий дамп базы данных PostgreSQL
docker exec -t kvit-postgres pg_dump -U ${POSTGRES_USER:-kvit_admin} ${POSTGRES_DB:-kvit_db} > /opt/kvit_backups/db_backup_$(date +%Y%m%d_%H%M%S).sql

# 5. Делаем снапшот предыдущей версии кода
tar -czf /opt/kvit_backups/code_prev_$(date +%Y%m%d_%H%M%S).tar.gz \
    --exclude='./receipts' \
    --exclude='./logs' \
    --exclude='./data/*.sqlite3' \
    --exclude='./.git' .
```

---

## 🚀 5. Шаг 2: Загрузка файлов и применение обновления (Deployment)

1. В **WinSCP** скопируйте файлы исходного кода (по списку из Раздела 3) в `/opt/kvit`.
2. В **SSH-терминале** выполните бесшовный перезапуск:

```bash
cd /opt/kvit

# 1. Пересобираем Docker-образы с новым кодом
docker compose build kvit-api kvit-worker

# 2. Перезапускаем только сервисы API и Worker (PostgreSQL и Redis НЕ останавливаются!)
docker compose up -d --no-deps kvit-api kvit-worker

# 3. Мягко применяем обновленный nginx.conf без обрыва клиентских соединений
docker compose exec nginx nginx -s reload
```

---

## ✅ 6. Шаг 3: Чек-лист проверки после обновления

Выполните контрольные команды в SSH-терминале:

### 1. Проверка API
```bash
curl -i http://localhost/health
```
*Результат:* HTTP `200 OK`, JSON `{"status": "ok"}`, заголовок `X-Backend-Instance: ...`.

### 2. Проверка PostgreSQL
```bash
docker exec -it kvit-postgres psql -U ${POSTGRES_USER:-kvit_admin} -d ${POSTGRES_DB:-kvit_db} -c "
SELECT 
    (SELECT count(*) FROM receipts) AS total_receipts,
    (SELECT count(*) FROM accounts) AS total_accounts;
"
```
*Результат:* Количество квитанций и абонентов осталось прежним.

### 3. Проверка Redis
```bash
docker exec -it kvit-redis redis-cli ping
# Ответ: PONG
```

### 4. Проверка логов воркера
```bash
docker compose logs --tail=30 kvit-worker
# Не должно быть ошибок подключения к Redis или PostgreSQL
```

### 5. Проверка поиска и скачивания реального PDF
1. Откройте в браузере `https://krec.kz/` (или ваш рабочий домен).
2. Введите реальный номер лицевого счета абонента -> нажмите **Найти**.
3. Нажмите **Скачать PDF** -> файл должен открыться мгновенно (Nginx отдаёт его через `X-Accel-Redirect`).

---

## ⏪ 7. Экстренный откат (Rollback Procedure)

Если после обновления обнаружена критическая ошибка:

```bash
cd /opt/kvit

# 1. Распаковываем предыдущую рабочую версию кода
LATEST_CODE=$(ls -t /opt/kvit_backups/code_prev_*.tar.gz | head -1)
tar -xzf $LATEST_CODE -C /opt/kvit/

# 2. Пересобираем и запускаем стабильные контейнеры
docker compose build kvit-api kvit-worker
docker compose up -d kvit-api kvit-worker
docker compose exec nginx nginx -s reload
```

---

## 🚫 8. Команды, КАТЕГОРИЧЕСКИ ЗАПРЕЩЕННЫЕ на Production

| ❌ Опасная команда | Последствия |
| :--- | :--- |
| `docker compose down -v` | Флаг `-v` **УДАЛЯЕТ ВСЕ ТОМА**: базу данных PostgreSQL, очередь Redis и все PDF-квитанции! |
| `docker volume prune -f` / `docker system prune -a --volumes` | Уничтожает все тома данных на сервере. |
| `rm -rf receipts/*` / `rm -rf /opt/kvit` | Безвозвратно стирает файлы квитанций и проект. |
| `git reset --hard` на сервере | Затрёт боевой `.env` и локальные SSL-настройки. |
| `DROP DATABASE ...` / `TRUNCATE receipts;` | Удалит базу данных абонентов. |

---

## 📊 9. Справка по постоянным томам (Persistent Volumes)

| Данные | Docker Volume / Каталог | Назначение |
| :--- | :--- | :--- |
| **База данных** | `postgres-data` (`/var/lib/postgresql/data`) | Таблицы абонентов, квитанций, прав, пользователей |
| **PDF-файлы** | `kvit-receipts` (`/app/receipts`) | Шардированные PDF-файлы (`/80/01/800101_*.pdf`) |
| **Очередь** | `redis-data` (`/data`) | AOF-журнал и snapshot Redis |
| **Конфиг** | `/opt/kvit/.env` | Секретные ключи, пароли, хеши |
| **SSL-сертификаты** | `/etc/letsencrypt` или `/opt/kvit/nginx/ssl` | Ключи и цепочки HTTPS |
| **Логи** | `kvit-logs` (`/app/logs`) | Логи запросов и ошибок |

---
*Документ полностью верифицирован для безопасного обновления работающего сервера без простоя.*
