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
