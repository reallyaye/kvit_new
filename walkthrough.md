# Отчёт о проведении аудита и устранении замечаний на портале krec.kz

**Дата проверки и актуализации:** 8 сентября 2026 г.  
**Субъект:** ТОО «Карагандинская Региональная Энергетическая Компания» (ТОО «КРЭК», БИН `031140001297`)  
**Правовой статус:** Субъект естественной монополии в сфере передачи и распределения электрической энергии в Карагандинской области  
**Статус внедрения:** Основные меры комплаенса и безопасности внедрены; устранены дефекты почтового сервиса, планировщика, линтера и БД перед очередным деплоем (`Ruff: All checks passed!`, тесты пройдены)

---

## 1. Резюме устранённых замечаний

| № | Выявленное замечание | Выполненные действия по устранению | Статус |
|---|---|---|:---:|
| 1 | **Собственная аналитика работала до согласия** (на первом визите сервер вызывал `record_visit()` при отсутствии cookie) | В [server.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/server.py#L543) внедрена строгая модель **Opt-in**: вызов `record_visit()` осуществляется **только** при наличии явного согласия пользователя `krec_analytics=1` в Cookie. При первом посещении или отсутствии cookie сбор статистики полностью отключен. | **Устранено** |
| 2 | **Google Fonts загружались до согласия** (импорт с `fonts.googleapis.com` в `style.css` и `heroui.css`) | Все 28 WOFF2 файлов гарнитуры Inter скачаны локально в `static/fonts/`. Создан локальный файл [static/css/inter.css](file:///c:/Users/zhunis/Desktop/portal/kvit_new/static/css/inter.css). В `style.css` и `heroui.css` внешние запросы к Google заменены на `@import url('/css/inter.css');`. В [server.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/server.py#L487) добавлен статический маршрут `/fonts/`. | **Устранено** |
| 3 | **Отзыв согласия был неполным** (установка `krec_analytics=0` не останавливала Метрику и не очищала cookies/хранилище) | В [portal_layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/portal_layout.py#L173) и [layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/layout.py#L110) внедрена функция `purgeTrackingData()`. При отзыве вызывается деструктор счётчика `window.yaCounter51197381.destructor()`, принудительно удаляются все cookie `_ym_*`, `yabs*`, `krec_analytics` по всем доменам и путям, и очищаются ключи `localStorage` и `sessionStorage`. | **Устранено** |
| 4 | **Очистка данных не была автоматической** (функции `purge_old_visits()` и `purge_expired_appeals()` вызывались только в тестах) | Разработан модуль фонового планировщика [services/retention_scheduler.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/retention_scheduler.py). Фоновый поток запускается в [app.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/app.py#L187) и [worker.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/worker.py#L53) и раз в сутки автоматически удаляет логи старше 90 дней и глубоко обезличивает обращения старше 3 лет. | **Устранено** |
| 5 | **Обезличивание обращений было неполным** (оставались `account_number`, `admin_comment`, `assigned_to`) | В [appeal_service.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/appeals/appeal_service.py#L323) функция `purge_expired_appeals()` расширена: теперь безвозвратно очищаются `account_number = NULL`, `admin_comment = 'Обезличено по истечении срока хранения'`, `assigned_to = NULL`, `service_address = 'Обезличено'`, а статус принудительно выставляется в `CLOSED`. | **Устранено** |
| 6 | **Версию согласия можно было подделать** (принималась из клиентского скрытого поля формы) | В [appeal_service.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/services/appeals/appeal_service.py#L68) версия согласия назначается сервером: `ACTIVE_CONSENT_VERSION = 'v1.0-2026-kz'`. Клиентское значение игнорируется. В [migrations.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/database/migrations.py#L189) для старых исторических записей установлено значение по умолчанию `'legacy-unversioned'`. | **Устранено** |
| 7 | **Политика противоречила реализации** (трансграничная передача, Google Fonts, дата редакции, ст. 8 Закона № 94-V) | В [privacy_views.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/privacy_views.py) и [appeals_views.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/appeals_views.py) дата редакции обновлена на **8 сентября 2026 года**. Описана локализация шрифтов. Прямо раскрыта трансграничная передача по ст. 16 Закона № 94-V: Яндекс.Метрика (РФ/Нидерланды, только при Opt-in) и Mail.ru SMTP (ООО «ВК», РФ, только при указании email). Форма согласия в `/appeals` приведена в полное соответствие со ст. 8 Закона № 94-V. | **Устранено** |
| 8 | **Раздел `/kvit/` использовал другой шаблон** (отсутствовали баннер cookie, ссылки `/privacy`, `/terms`, БИН) | Шаблон [templates/layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/layout.py) полностью синхронизирован: добавлены баннер Cookie (`krecCookieBanner`), модальное окно настроек (`krecCookieModal`), футер с реквизитами ТОО «КРЭК», БИН `031140001297`, ссылками на `/privacy`, `/terms` и кнопкой управления согласием. | **Устранено** |
| 9 | **Безопасность HTTP не была завершена** (отсутствовали HSTS и CSP, 400 Bad Request на HTTP-SSL, раскрытие версий) | В [nginx/nginx.conf](file:///c:/Users/zhunis/Desktop/portal/kvit_new/nginx/nginx.conf) добавлены: `server_tokens off;`, `Strict-Transport-Security` (max-age=31536000; includeSubDomains), `Content-Security-Policy`, `error_page 497 =301 https://$host$request_uri;` (автоматический редирект при HTTP-запросе на порт SSL), глобальный редирект с порта 80, и директивы `proxy_hide_header` для исключения дублирования заголовков и скрытия `X-Backend-Instance`. | **Устранено** |
| 10 | **Schema.org содержала неверное поле** (`leiCode` для БИН) | В [templates/portal_layout.py](file:///c:/Users/zhunis/Desktop/portal/kvit_new/templates/portal_layout.py) удалено ошибочное поле `"leiCode": "031140001297"`, оставлен корректный международный тег налогового идентификатора `"taxID": "031140001297"`. | **Устранено** |
| 11 | **Замечания к кодовой базе, линтерам и безопасности** (`ruff`, Bandit, пароли в `scratch/`, `DOCS_LICENSES.md`) | В [pyproject.toml](file:///c:/Users/zhunis/Desktop/portal/kvit_new/pyproject.toml) исключение `receipts` исправлено на `"/receipts"`. В `receipt_service.py` отсортированы импорты и удалена неиспользуемая переменная `query_str_norm`. Из скриптов в `scratch/` полностью удалены хардкод-пароли SSH. В [DOCS_LICENSES.md](file:///c:/Users/zhunis/Desktop/portal/kvit_new/DOCS_LICENSES.md) детально зафиксированы правовые основания по служебным произведениям (ст. 14 Закона РК об авторском праве). | **Устранено** |

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
# Выявлено 39 предупреждений уровня Low (стандартные предупреждения о биндинге 0.0.0.0 внутри Docker и хелперах).
```

### 2.3. Модульное и интеграционное тестирование
Полный прогон тестового набора (`python run_tests.py`):
```
ИТОГИ: Успешно: 94, Провалено: 0
```
Специализированные тесты приватности и законодательного соответствия (`tests/test_compliance_privacy.py`):
```
9 passed in 7.10s (100% SUCCESS)
- test_schema_and_cookie_consent_in_portal_layout PASSED
- test_sensitive_pages_shield_in_portal_layout PASSED
- test_search_inputs_protected PASSED
- test_stats_service_salt_rotation_and_ua_minimization PASSED
- test_appeals_consent_version_and_ip_anonymization PASSED
- test_privacy_and_terms_pages PASSED
- test_font_localization PASSED
- test_kvit_layout_unification PASSED
- test_deep_anonymization_appeals PASSED
```

---

## 3. Юридические аспекты и статус ТОО «КРЭК»

1. **Статус субъекта естественной монополии:**
   ТОО «КРЭК» включено в Государственный регистр субъектов естественных монополий по Карагандинской области (услуги по передаче и распределению электрической энергии).
2. **Сроки рассмотрения обращений:**
   Срок рассмотрения обращений потребителей составляет **до 15 рабочих дней** в соответствии со ст. 24 Закона РК «О естественных монополиях» и ст. 76 Административного процедурно-процессуального кодекса РК (АППК РК), с правом продления при необходимости истребования дополнительных материалов. Запросы на отзыв согласия на обработку персональных данных рассматриваются в течение **15 календарных дней** в соответствии со ст. 24 Закона РК «О персональных данных и их защите».
3. **Авторские права на медиа-активы:**
   Производственные фотографии оборудования, подстанций и ремонтных бригад (файлы 1.1–5.74, тепловизоры, РЕТОМ, передвижные лаборатории) являются служебными произведениями согласно ст. 14 Закона РК «Об авторском праве и смежных правах», созданными работниками предприятия во исполнение служебных обязанностей по приказам об утверждении ремонтных и инвестиционных программ ТОО «КРЭК».
