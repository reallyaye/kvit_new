# 🚀 Руководство по безопасному обновлению Production-сервера через WinSCP (SFTP) и SSH

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

## 🗺️ Общая схема процесса

```text
[ Windows ПК ]
   │
   ├─ 1. Скачивание свежей версии из Git (git pull)
   │
   ├─ 2. Подключение к серверу через WinSCP (SFTP)
   │     └─ Загрузка ТОЛЬКО файлов кода (БЕЗ .env, БД и квитанций)
   │
[ Production Server (SSH) ]
   │
   ├─ 3. Создание бэкапа БД и конфигурации (1 минута)
   │
   ├─ 4. Бесшовный перезапуск Docker Compose
   │     (kvit-api, kvit-worker, nginx)
   │
   └─ 5. Экспресс-проверка работоспособности (Healthcheck & PDF)
```

---

## 📦 1. Подготовка на Windows ПК

1. В терминале на Windows ПК перейдите в корень проекта и получите последние изменения из репозитория:
   ```powershell
   cd c:\Users\User\Desktop\сайт
   git checkout main
   git pull origin main
   ```
2. Убедитесь, что все локальные тесты зеленые:
   ```powershell
   pytest tests -v
   ```

---

## 📂 2. Матрица файлов для WinSCP: Что копировать, а что НЕТ

Откройте **WinSCP**, подключитесь к вашему серверу (протокол **SFTP**, порт **22**).

В **левой панели** (Windows) откройте папку проекта (`c:\Users\User\Desktop\сайт`).
В **правой панели** (Сервер) откройте рабочую директорию проекта (например, `/opt/kvit`).

### ✅ ЧТО КОПИРОВАТЬ (Выделить и перетащить в WinSCP):
* 📁 `database/`
* 📁 `services/`
* 📁 `templates/`
* 📁 `static/`
* 📁 `nginx/` (включая `nginx/nginx.conf`, **но НЕ трогая папку сертификатов `nginx/ssl/` на сервере**)
* 📁 `proto/`
* 📁 `scripts/`
* 📁 `benchmarks/`
* 📁 `data/` (только JSON-файлы: `extracted_portal_pages.json`, `documents.json`)
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
* 📄 `docker-compose.prod.yml`
* 📄 `pyproject.toml`

---

### ❌ ЧТО КАТЕГОРИЧЕСКИ НЕЛЬЗЯ КОПИРОВАТЬ / ПЕРЕЗАПИСЫВАТЬ:

| Файл / Папка | Причина запрета |
| :--- | :--- |
| ❌ **`.env`** | На сервере находятся **боевые секреты, пароли к PostgreSQL, SECRET_KEY и токен Telegram-бота**. Перезапись приведет к падению сервера! |
| ❌ **`receipts/`** | В этой папке на сервере хранятся реальные PDF-квитанции жителей. |
| ❌ **`data.sqlite3`** / **`data/*.db`** | Боевая база данных (если используется SQLite). |
| ❌ **`logs/`** | Рабочие журналы API, воркеров и Nginx на сервере. |
| ❌ **`nginx/ssl/`** / **`/etc/letsencrypt/`** | Боевые SSL-сертификаты домена. |
| ❌ **`__pycache__/`**, **`.pytest_cache/`**, **`.ruff_cache/`**, **`.ai/`** | Мусорные временные файлы Windows. |
| ❌ **`лицевые все.xls`**, **`лицевые все.xlsx`** | Локальные файлы импорта. |

> [!TIP]
> **Настройка фильтра исключений в WinSCP**:
> Нажмите в WinSCP `Ctrl + Alt + F` (Transfer Settings -> Mask) и добавьте в исключения:
> `.env; receipts/; logs/; *.sqlite3; *.db; __pycache__/; .git/; .pytest_cache/; nginx/ssl/*; *.xls; *.xlsx`

---

## 🛡️ 3. Создание бэкапа перед обновлением (через SSH)

Перед применением изменений откройте терминал SSH (PuTTY / WinSCP Terminal / встроенный OpenSSH) на сервере и выполните:

```bash
# 1. Переходим в директорию проекта
cd /opt/kvit

# 2. Создаем директорию для бэкапов (если её нет)
mkdir -p /opt/kvit_backups

# 3. Делаем бэкап боевого .env файла
cp .env /opt/kvit_backups/.env_backup_$(date +%Y%m%d_%H%M%S)

# 4. Делаем горячий дамп PostgreSQL (если используется Docker PostgreSQL)
docker exec -t kvit-postgres pg_dump -U ${POSTGRES_USER:-kvit_user} ${POSTGRES_DB:-kvit_db} > /opt/kvit_backups/db_backup_$(date +%Y%m%d_%H%M%S).sql

# 5. Делаем снапшот предыдущей версии кода (без тяжелых квитанций)
tar -czf /opt/kvit_backups/code_prev_$(date +%Y%m%d_%H%M%S).tar.gz \
    --exclude='./receipts' \
    --exclude='./logs' \
    --exclude='./data/*.sqlite3' \
    --exclude='./.git' .
```

---

## 🔄 4. Развертывание новой версии (Deployment)

После того как файлы скопированы через WinSCP:

### Вариант А: Standalone Production (`docker-compose.yml`)
*(Postgres + Redis + API + Worker + Nginx в одном Compose)*

```bash
cd /opt/kvit

# 1. Пересобираем Docker-образы с новым кодом
docker compose build kvit-api kvit-worker

# 2. Перезапускаем контейнеры без остановки БД и Redis
docker compose up -d --no-deps kvit-api kvit-worker

# 3. Мягко перезагружаем конфигурацию Nginx (Zero-Downtime)
docker compose exec nginx nginx -s reload
```

### Вариант Б: Enterprise Production (`docker-compose.prod.yml`)
*(Внешний Managed PostgreSQL + Managed Redis)*

```bash
cd /opt/kvit

# 1. Сборка образов
docker compose -f docker-compose.prod.yml build

# 2. Обновление с горизонтальным масштабированием (например, 4 API + 2 Worker)
docker compose -f docker-compose.prod.yml up -d --scale kvit-api=4 --scale kvit-worker=2

# 3. Мягкая перезагрузка Nginx
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

---

## ✅ 5. Чек-лист проверки после обновления (Verification)

Выполните эти команды по очереди на сервере:

### 1. Проверка API и статуса серверов
```bash
curl -i http://localhost/health
```
*Ожидаемый результат:* HTTP-код `200 OK`, JSON `{"status": "ok"}`, заголовок `X-Backend-Instance: ...`.

### 2. Проверка PostgreSQL
```bash
docker exec -it kvit-postgres psql -U ${POSTGRES_USER:-kvit_user} -d ${POSTGRES_DB:-kvit_db} -c "
SELECT 
    (SELECT count(*) FROM receipts) AS total_receipts,
    (SELECT count(*) FROM accounts) AS total_accounts;
"
```
*Ожидаемый результат:* Количество квитанций и счетов **не обнулилось** и совпадает с состоянием до обновления.

### 3. Проверка Redis
```bash
docker exec -it kvit-redis redis-cli ping
docker exec -it kvit-redis redis-cli zcard kvit:tasks:processing
```
*Ожидаемый результат:* `PONG`, зависших задач `0`.

### 4. Проверка логов воркера и API
```bash
# Логи API (не должно быть Traceback и ошибок подключения)
docker compose logs --tail=30 kvit-api

# Логи Воркера (должен сообщить о готовности воркеров)
docker compose logs --tail=30 kvit-worker
```

### 5. Проверка поиска и скачивания реального PDF
1. Откройте в браузере сайт: `https://ваш-домен/`
2. Введите любой реальный лицевой счет абонента и нажмите **Найти**.
3. Убедитесь, что найдены квитанции за предыдущие месяцы.
4. Нажмите кнопку **Скачать PDF**:
   - Файл должен мгновенно открыться/скачаться.
   - В ответе Nginx должен использовать `X-Accel-Redirect` (быстрая отдача без нагрузки на Python).

---

## ⏪ 6. Экстренный откат (Rollback Procedure)

Если после обновления что-то пошло не так:

```bash
cd /opt/kvit

# 1. Восстанавливаем предыдущую версию кода из архива
LATEST_BACKUP=$(ls -t /opt/kvit_backups/code_prev_*.tar.gz | head -1)
tar -xzf $LATEST_BACKUP -C /opt/kvit/

# 2. Быстро пересобираем и запускаем стабильные контейнеры
docker compose build kvit-api kvit-worker
docker compose up -d kvit-api kvit-worker

# 3. Перезагружаем Nginx
docker compose exec nginx nginx -s reload

# 4. (Только если сломалась схема БД) Восстановление дампа базы:
# LATEST_DB=$(ls -t /opt/kvit_backups/db_backup_*.sql | head -1)
# docker exec -i kvit-postgres psql -U ${POSTGRES_USER:-kvit_user} -d ${POSTGRES_DB:-kvit_db} < $LATEST_DB
```

---

## 🚫 7. Команды, КАТЕГОРИЧЕСКИ ЗАПРЕЩЕННЫЕ на Production

| ❌ Опасная команда | Почему её нельзя выполнять |
| :--- | :--- |
| `docker compose down -v` | Флаг `-v` **УДАЛЯЕТ ВСЕ ТОМА**: базу данных PostgreSQL, очередь Redis и сохраненные квитанции! |
| `docker system prune -a --volumes` | Уничтожает все неактивные и постоянные volumes на хосте. |
| `rm -rf receipts/*` / `rm -rf /opt/kvit` | Безвозвратно удаляет PDF-архив и файлы проекта. |
| `git reset --hard` на сервере | Затрёт боевой `.env` и локальные настройки. |
| `DROP DATABASE ...` / `TRUNCATE receipts;` | Удалит данные всех абонентов. |

---

## 📊 Справка: Где физически хранятся постоянные данные

| Данные | Docker Volume / Каталог | Что внутри |
| :--- | :--- | :--- |
| **База данных** | `postgres-data` (`/var/lib/postgresql/data`) | Таблицы абонентов, квитанций, прав, пользователей |
| **PDF-файлы** | `kvit-receipts` (`/opt/kvit/receipts`) | Шардированные PDF-файлы (`/80/01/800101_*.pdf`) |
| **Очередь** | `redis-data` (`/data`) | AOF-журнал и snapshot Redis-очереди |
| **Конфиг** | `/opt/kvit/.env` | Секретные ключи, пароли, хеши |
| **SSL-сертификаты** | `/etc/letsencrypt` или `./nginx/ssl` | Публичные и приватные ключи HTTPS |
| **Логи** | `kvit-logs` (`/opt/kvit/logs`) | Логи запросов и ошибок |

---
*Документ подготовлен для штатной эксплуатации и регулярных обновлений без прерывания обслуживания потребителей.*
