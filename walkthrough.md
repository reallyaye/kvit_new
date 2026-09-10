# Отчёт о проведении аудита и устранении замечаний на портале krec.kz

**Дата проверки и актуализации:** 8 сентября 2026 г.  
**Субъект:** ТОО «Карагандинская Региональная Энергетическая Компания» (ТОО «КРЭК», БИН `031140001297`)  
**Правовой статус:** Субъект естественной монополии в сфере передачи и распределения электрической энергии в Карагандинской области  
**Статус внедрения:** Все критические замечания по комплаенсу, безопасности, Nginx-логированию и развёртыванию устранены на production-сервере. Ревизия `9990996` успешно собрана и запущена.

---

## 1. Резюме устранённых замечаний

| № | Выявленное замечание | Выполненные действия по устранению | Статус |
|---|---|---|:---:|
| 1 | **Собственная аналитика работала до согласия** (на первом визите сервер вызывал `record_visit()` при отсутствии cookie) | В [server.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/server.py#L543) внедрена строгая модель **Opt-in**: вызов `record_visit()` осуществляется **только** при наличии явного согласия пользователя `krec_analytics=1` в Cookie. При первом посещении или отсутствии cookie сбор статистики полностью отключен. | **Устранено** |
| 2 | **Google Fonts загружались до согласия** (импорт с `fonts.googleapis.com` в `style.css` и `heroui.css`) | Все 28 WOFF2 файлов гарнитуры Inter скачаны локально в `static/fonts/`. Создан локальный файл [static/css/inter.css](file:///c:/Users/zhunis/Desktop/portal/kvit_new/static/css/inter.css). В `style.css` и `heroui.css` внешние запросы к Google заменены на `@import url('/css/inter.css');`. В [server.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/server.py#L487) добавлен статический маршрут `/fonts/`. | **Устранено** |
| 3 | **Отзыв согласия был неполным** (установка `krec_analytics=0` не останавливала Метрику и не очищала cookies/хранилище) | В [portal_layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/portal_layout.py#L173) и [layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/layout.py#L110) внедрена функция `purgeTrackingData()`. При отзыве вызывается деструктор счётчика `window.yaCounter51197381.destructor()`, принудительно удаляются все cookie `_ym_*`, `yabs*`, `krec_analytics` по всем доменам и путям, и очищаются ключи `localStorage` и `sessionStorage`. | **Устранено** |
| 4 | **Очистка данных не была автоматической** (функции `purge_old_visits()` и `purge_expired_appeals()` вызывались только в тестах) | Разработан модуль фонового планировщика [services/retention_scheduler.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/retention_scheduler.py). Фоновый поток запускается в [app.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/app.py#L187) и [worker.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/worker.py#L53) и раз в сутки автоматически удаляет логи старше 90 дней и глубоко обезличивает обращения старше 3 лет с защитой через PostgreSQL Advisory Lock. | **Устранено** |
| 5 | **Обезличивание обращений было неполным** (оставались `account_number`, `admin_comment`, `assigned_to`) | В [appeal_service.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/appeals/appeal_service.py#L323) функция `purge_expired_appeals()` расширена: теперь безвозвратно очищаются `account_number = NULL`, `admin_comment = 'Обезличено по истечении срока хранения'`, `assigned_to = NULL`, `service_address = 'Обезличено'`, а статус принудительно выставляется в `CLOSED`. | **Устранено** |
| 6 | **Версию согласия можно было подделать** (принималась из клиентского скрытого поля формы) | В [appeal_service.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/appeals/appeal_service.py#L68) версия согласия назначается сервером: `ACTIVE_CONSENT_VERSION = 'v1.0-2026-kz'`. Клиентское значение игнорируется. В [migrations.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/database/migrations.py#L189) для старых исторических записей установлено значение по умолчанию `'legacy-unversioned'`. | **Устранено** |
| 7 | **Политика противоречила реализации** (трансграничная передача, Google Fonts, дата редакции, ст. 8 Закона № 94-V) | В [privacy_views.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/privacy_views.py) и [appeals_views.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/appeals_views.py) дата редакции обновлена на **8 сентября 2026 года**. Описана локализация шрифтов. Прямо раскрыта трансграничная передача по ст. 16 Закона № 94-V: Яндекс.Метрика (РФ/Нидерланды, только при Opt-in) и Mail.ru SMTP (ООО «ВК», РФ, только при указании email). Форма согласия в `/appeals` приведена в полное соответствие со ст. 8 Закона № 94-V. | **Устранено** |
| 8 | **Раздел `/kvit/` использовал другой шаблон** (отсутствовали баннер cookie, ссылки `/privacy`, `/terms`, БИН) | Шаблон [templates/layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/layout.py) полностью синхронизирован: добавлены баннер Cookie (`krecCookieBanner`), модальное окно настроек (`krecCookieModal`), футер с реквизитами ТОО «КРЭК», БИН `031140001297`, ссылками на `/privacy`, `/terms` и кнопкой управления согласием. | **Устранено** |
| 9 | **Безопасность HTTP не была завершена** (отсутствовали HSTS и CSP, 400 Bad Request на HTTP-SSL, раскрытие версий) | В [nginx/nginx.conf](file:///c:/Users/zhunis/Desktop/portal/kvit_new/nginx/nginx.conf) добавлены: `server_tokens off;`, `Strict-Transport-Security` (max-age=31536000; includeSubDomains), `Content-Security-Policy`, `error_page 497 =301 https://$host$request_uri;` (автоматический редирект при HTTP-запросе на порт SSL), глобальный редирект с порта 80, и директивы `proxy_hide_header` для исключения дублирования заголовков и скрытия `X-Backend-Instance`. | **Устранено** |
| 10 | **Schema.org содержала неверное поле** (`leiCode` для БИН) | В [templates/portal_layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/portal_layout.py) удалено ошибочное поле `"leiCode": "031140001297"`, оставлен корректный международный тег налогового идентификатора `"taxID": "031140001297"`. | **Устранено** |
| 11 | **Замечания к кодовой базе, линтерам и безопасности** (`ruff`, Bandit, пароли в `scratch/`, `DOCS_LICENSES.md`) | В [pyproject.toml](file:///c:/Users/zhunis/Desktop/portal/kvit_new/pyproject.toml) исключение `receipts` исправлено на `"/receipts"`. В `receipt_service.py` отсортированы импорты и удалена неиспользуемая переменная `query_str_norm`. В `services/mail/test_delivery.py` закрыто замечание Bandit B310. Из скриптов в `scratch/` полностью удалены хардкод-пароли SSH. В [DOCS_LICENSES.md](file:///c:/Users/zhunis/Desktop/portal/kvit_new/DOCS_LICENSES.md) детально зафиксированы правовые основания по служебным произведениям (ст. 14 Закона РК об авторском праве). | **Устранено** |
| 12 | **Фактическая ротация Nginx-логов отсутствовала** (активные `access.log` и `error.log` не ротировались и могли превысить лимит 90 дней) | Создан [nginx/Dockerfile](file:///c:/Users/zhunis/Desktop/portal/kvit_new/nginx/Dockerfile) на базе Alpine с установкой пакетов `logrotate`, `gzip`, `tzdata`. Разработан скрипт [nginx/rotate-logs.sh](file:///c:/Users/zhunis/Desktop/portal/kvit_new/nginx/rotate-logs.sh), выполняющий atomic rename файлов логов, сигнал `nginx -s reopen`, сжатие `gzip` и удаление файлов старше 90 дней (`find ... -mtime +90 -delete`). В [docker-compose.yml](file:///c:/Users/zhunis/Desktop/portal/kvit_new/docker-compose.yml) настроен образ `kvit-nginx:latest` и фоновый суточный вызов ротации. | **Устранено** |
| 13 | **Связка каталогов загрузки `data/uploads` и права доступа** (риск ошибки создания root-владельца при чистом деплое) | Зафиксированы файлы `.gitkeep` в [data/uploads/.gitkeep](file:///c:/Users/zhunis/Desktop/portal/kvit_new/data/uploads/.gitkeep) и `static/images/uploads/.gitkeep`. В `.gitignore` добавлено исключение `!/data/uploads/.gitkeep`. В [Dockerfile](file:///c:/Users/zhunis/Desktop/portal/kvit_new/Dockerfile) и скрипте деплоя добавлено автоматическое создание каталогов с правами `775` и `chown -R appuser:appuser` (UID/GID 1000). | **Устранено** |
| 14 | **Отключение требования верификации адреса по лицевому счету** (пользователю выводилось предупреждение «Требуется уточнить адрес: Для доступа к квитанции введите номер дома или квартиры») | В [config.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/config.py) значение по умолчанию `REQUIRE_RECEIPT_VERIFICATION` установлено в `False`. В [server.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/server.py) удалено условие `or config.IS_PRODUCTION` из всех обработчиков поиска. Теперь при вводе лицевого счёта пользователь сразу получает квитанцию (`EXACT_MATCH`), без запросов номеров дома/квартиры. В [templates/search_views.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/search_views.py) обновлена обработка AJAX-ответов. Проверено на боевом сервере. | **Устранено** |

---

## 2. Результаты статического анализа и тестов

### 2.1. Линтер Ruff
Все модули проекта проверены:
```bash
python -m ruff check .
# Результат: All checks passed!
```

### 2.2. Анализатор безопасности Bandit
Просканировано **14 789 строк** исходного кода:
```bash
python -m bandit -r services database templates server.py app.py worker.py -ll
# Результат: No issues identified (High: 0, Medium: 0).
```

### 2.3. Модульное и интеграционное тестирование
Полный прогон тестового набора (`python run_tests.py`):
```
ИТОГИ: Успешно: 94, Провалено: 0
```
Специализированные тесты приватности и законодательного соответствия (`tests/test_compliance_privacy.py`):
```
9 passed in 7.10s (100% SUCCESS)
```

---

## 3. Инфраструктурные и юридические аспекты

1. **Статус субъекта естественной монополии:**
   ТОО «КРЭК» включено в Государственный регистр субъектов естественных монополий по Карагандинской области (услуги по передаче и распределению электрической энергии).
2. **Сроки рассмотрения обращений:**
   Срок рассмотрения обращений потребителей составляет **до 15 рабочих дней** в соответствии со ст. 24 Закона РК «О естественных монополиях» и ст. 76 Административного процедурно-процессуального кодекса РК (АППК РК). Запросы на отзыв согласия на обработку персональных данных рассматриваются в течение **15 календарных дней** в соответствии со ст. 24 Закона РК «О персональных данных и их защите».
3. **Авторские права на медиа-активы:**
   Служебные произведения согласно ст. 14 Закона РК «Об авторском праве и смежных правах».
4. **Статус доменной почты `@krec.kz` и DNS:**
   - **Исходящая отправка:** Работает в штатном режиме через SMTP Mail.ru (`smtp.mail.ru:465`) под служебным ящиком отправителя. Уведомления об обращениях успешно доставляются.
   - **Входящая почта на `info@krec.kz` и `dpo@krec.kz`:** На DNS-серверах зоны `krec.kz` (`ns1.hosting.ismet.kz`, `ns2.hosting.ismet.kz`) отсутствуют MX-записи. Это не препятствует работе портала (основными рабочими каналами являются форма подачи обращений на сайте, телефон канцелярии и физический приём), однако приём почты на адреса `@krec.kz` требует настройки DNS-записей (MX, SPF, DKIM) в личном кабинете хостинг-провайдера Ismet.kz.

---

## 4. Развёртывание на сервере (Production)

- **Ревизия в Git:** [6cf3c74](https://github.com/reallyaye/kvit_new/commit/6cf3c74) (`main` и `origin/main` синхронизированы).
- **Состояние контейнеров на сервере `172.30.0.2`:**
  ```text
  NAMES                    STATUS                    PORTS
  kvit-nginx               Up (healthy)              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
  kvit_new-kvit-api-1      Up (healthy)              8000/tcp, 50051/tcp
  kvit_new-kvit-worker-1   Up (healthy)              8000/tcp, 50051/tcp
  kvit-postgres            Up 7 days (healthy)       5432/tcp
  kvit-redis               Up 7 days (healthy)       6379/tcp
  kvit-certbot             Up 7 days                 80/tcp, 443/tcp
  ```
- **Проверка живого сервиса:**
  - **Health probe:** `HTTP 200` (`{"status": "ok", "service": "kvit-service"}`).
  - **Поиск квитанции по лицевому счёту (без запроса адреса):** Запрос `/api/search?account=800146` возвращает `STATUS: EXACT_MATCH`, адрес и токен доступа к квитанции без запроса дома/квартиры.
  - **Страница обращений `/appeals`:** `HTTP 200`, длина HTML 59 615 байт.
  - **Тестирование ротации логов Nginx:** Скрипт `/usr/local/bin/rotate-logs.sh` выполнен внутри `kvit-nginx`. Старые файлы (65 МБ `access.log` и 5.9 МБ `error.log`) отротированы и сжаты в `gz`, активные файлы логов атомарно переоткрыты через сигнал Nginx и очищены. Срок хранения 90 дней обеспечивается суточным циклом контейнера.
  - **Безопасность Cookie:** Флаг `; Secure` подтверждён в боевом коде страниц (`SameSite=Lax` + `Secure`).
  - **HTTP-редирект с порта 80:** `Location: https://krec.kz/` подтверждён.

---

## 5. Устранение ошибки детекции квитанций-сирот при `known_accounts=None`

### 5.1. Анализ проблемы
1. **Потеря результата запроса в `pdf_processor.py` (строка 280):**
   При `known_accounts=None` (штатный режим работы воркера фоновой загрузки) выполнялся запрос в БД `SELECT account_number FROM accounts WHERE account_number IN (...)`, но результат `{row[0] for row in rows}` не присваивался переменной `known_accounts`.
2. **Ложное срабатывание проверки `is_orphan`:**
   В строке 393 проверялось `is_orphan = (known_accounts is not None and account not in known_accounts)`. Из-за того, что `known_accounts` оставался `None`, выражение вычислялось в `False`. В результате неизвестный лицевой счёт ошибочно считался валидным (`added=1`, `orphan=0`).
3. **Авторегистрация счетов-сирот в `atomic_importer.py`:**
   В цикле фиксации транзакции выполнялась безусловная вставка `INSERT INTO accounts`, создававшая в реестре ошибочно распознанный номер счёта.

### 5.2. Реализованные исправления
1. **[pdf_processor.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/services/pdf/pdf_processor.py):**
   - Результат запроса счетов теперь корректно присваивается: `known_accounts = {str(row[0]).strip() for row in rows}` (или `set()` если список пуст).
   - Проверка `is_orphan` строго определяет сирот: `is_orphan = (str(account).strip() not in known_accounts)`.
2. **[atomic_importer.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/services/pdf/atomic_importer.py):**
   - Добавлено условие `if r.account and not r.is_orphan:`, гарантирующее, что квитанция с несуществующим счётом сохраняется в `receipts`, но **не создаёт** ложную запись в таблице `accounts`.
3. **[tests/test_pdf_processor.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/tests/test_pdf_processor.py):**
   - Добавлен сквозной тест `test_pdf_processor_orphan_when_known_accounts_is_none`:
     - Несуществующий счёт при `known_accounts=None` получает `orphan=1`, `added=0`.
     - Счёт не попадает в `accounts`, квитанция попадает в `receipts` и учитывается в `reconcile_service.get_reconciliation_data(filt='orphans')`.
     - Существующий счёт при `known_accounts=None` получает `added=1`, `orphan=0`.
4. **[run_tests.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/run_tests.py):**
   - Добавлен `tests/test_pdf_processor.py` в список запуска по умолчанию (все 114 тестов проходят успешно: `114 passed in 91.47s`).

### 5.3. Деплой и доступ к боевой PostgreSQL
- **Подключение к серверу:**
  - SSH: `user@172.30.0.2`, порт **`22022`** (пароль задаётся системным администратором и хранится в защищённом хранилище секретов).
- **Подключение к боевой PostgreSQL:**
  - Контейнер: `kvit-postgres`.
  - Пользователь: **`kvit_admin`** (не `postgres` и не `kvit_user`).
  - База данных: **`kvit_db`**.
  - Пароль: определяется переменной `POSTGRES_PASSWORD` в файле `.env` на сервере.
  - Команда для проверки через SSH:
    ```bash
    docker exec -it kvit-postgres psql -U kvit_admin -d kvit_db -c "SELECT count(*) FROM accounts; SELECT count(*) FROM receipts;"
    ```
  - Текущие показатели боевой БД: **38 294** счёта в реестре, **34 408** квитанций.
- **Статус на боевом сервере:**
  - Изменения запушены в `main` ([7df3708](https://github.com/reallyaye/kvit_new/commit/7df3708)) и подтянуты на сервер через `git pull`.
  - Контейнеры `kvit-api` and `kvit-worker` перезапущены и находятся в статусе `healthy`.

---

## 6. Удаление квитанций оператором (карантин 30 дней, аудит и защита)

### 6.1. Архитектура решения
1. **Двухфазное удаление и карантин ([receipt_service.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/services/receipts/receipt_service.py)):**
   - Выполняется поиск и блокировка записи в транзакции (`FOR UPDATE` для PostgreSQL / эксклюзивная блокировка SQLite).
   - PDF-файл перемещается в закрытую директорию карантина `DELETED_RECEIPTS_DIR` (`data/deleted_receipts/`) с меткой времени, ID записи и хэш-префиксом токена.
   - Запись удаляется из таблицы `receipts`, исключая квитанцию из публичной выдачи и сверки.
   - **Compensating rollback:** при сбое транзакции БД файл автоматически возвращается из карантина на исходное место в хранилище.
   - Повторная загрузка квитанции разблокирована: после удаления записи и файла дубликат по хэшу/периоду не детектируется.

2. **Безопасность и ролевой доступ ([server.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/server.py)):**
   - Новый эндпоинт `POST /api/receipts/delete` защищён авторизацией (`operator` и `admin`) и обязательной валидацией CSRF-токена (`X-CSRF-Token`).
   - Каждое удаление логируется в `audit_logs` с указанием пользователя (`username`), IP-клиента, лицевого счёта, периода и признака перемещения в карантин.
   - Через WebSocket рассылается событие `receipt_deleted` для живого обновления интерфейсов.

3. **Интерфейс оператора ([reconcile_views.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/templates/reconcile_views.py)):**
   - Во вкладках сверки добавлена кнопка «Удалить» с подтверждением действия.
   - Массовые административные кнопки («Синхронизировать с диском», «Очистить отсутствующие») скрыты от оператора (`role == 'admin'`).

4. **Очистка карантина ([retention_scheduler.py](file:///C:/Users/zhunis/Desktop/portal/kvit_new/services/retention_scheduler.py)):**
   - Регулярный фоновый процесс вызывает `purge_deleted_receipt_files(days=30)` и удаляет файлы из карантина старше 30 дней.
   - Каталог `data/deleted_receipts` сохраняется на постоянном томе хоста (`./data:/app/data` в `docker-compose.yml`).

### 6.2. Результаты тестов и проверок
- **Автоматические тесты:** `python run_tests.py` — **`118 passed in 91.55s`** (включая специализированный набор `tests/test_receipt_delete.py`).
- **Линтер:** `ruff check .` — без ошибок (`All checks passed!`).
- **Анализ безопасности:** `bandit -r services/ server.py -ll` — замечаний Medium/High нет (`No issues identified`).
- **YAML конфигурация:** `docker-compose.yml` валиден.

### 6.3. Деплой на боевой сервер `172.30.0.2`
- Коммит [`d6f93da`](https://github.com/reallyaye/kvit_new/commit/d6f93da) отправлен в `origin/main`.
- На сервере выполнен `git pull` и перезапущены контейнеры `kvit_new-kvit-api-1` и `kvit_new-kvit-worker-1`.
- Оба контейнера успешно поднялись и находятся в статусе `Up (healthy)`.

---

## 7. Безопасность секретов и восстановление ежедневного резервного копирования

### 7.1. Устранение утечек секретов и ротация паролей
1. **Telegram-токен:**
   - Из скрипта `update_bot.sh` удалён захардкоженный токен.
   - Токен теперь передаётся строго через переменную окружения `TELEGRAM_BOT_TOKEN` или первым аргументом командной строки `$1`.
2. **Ротация паролей на сервере `172.30.0.2`:**
   - **SSH:** пароль пользователя `user` сменён на криптостойкий сгенерированный пароль. Проверена аутентификация по порту `22022`.
   - **PostgreSQL:** пароль роли `kvit_admin` сменён в СУБД (`ALTER ROLE kvit_admin WITH PASSWORD ...`), обновлён в `/home/user/portal/kvit_new/.env`, пересозданы и проверены контейнеры `kvit-api` и `kvit-worker` (оба в статусе `healthy`).
3. **Очистка истории Git:**
   - С помощью `git-filter-repo` из всей истории коммитов репозитория полностью вычищены старые пароли и рабочий токен Telegram.
   - Чистая история синхронизирована с GitHub (`git push --force origin main`) и обновлена на сервере (`git reset --hard origin/main`).

### 7.2. Исправление ежедневного резервного копирования
1. **Проблема прав доступа к `/var/log`:**
   - Пользователь `user` не имеет прав записи в общесистемный каталог `/var/log`, из-за чего запуск `daily_backup.sh` через cron в 03:00 молча падал.
2. **Решение:**
   - Скрипт `scripts/daily_backup.sh` обновлён: лог по умолчанию направляется в `$PROJECT_DIR/logs/kvit_backup.log`.
   - Каталог `logs/` создаётся автоматически.
   - Crontab пользователя `user` на сервере обновлён:
     ```cron
     0 3 * * * /home/user/portal/kvit_new/scripts/daily_backup.sh >> /home/user/portal/kvit_new/logs/kvit_backup.log 2>&1
     ```
   - Запущен свежий ручной backup с полной процедурой Disaster Recovery Drill: создание дампа PostgreSQL, архивация квитанций и CMS, проверка 100% PDF-файлов по сигнатуре `%PDF-` и тестовое восстановление базы в изолированную временную БД PostgreSQL.


