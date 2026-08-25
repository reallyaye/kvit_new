# Развертывание портала ТОО «КРЭК» и сервиса квитанций

Единая микросервисная архитектура портала на **Python (HTTP / gRPC / WebSockets)** + **Nginx** без устаревшего PHP.

## Архитектура
- **Единый бэкенд**: Python 3.11+ (`kvit_test/server.py`) обслуживает как информационный портал компании, так и реестр документов, Telegram-бота, OCR-обработку и сервис онлайн-квитанций.
- **Статика и Nginx**: Nginx выполняет роль reverse proxy, TLS-терминатора и высокопроизводительного отдачика статических файлов (`/css/`, `/images/`, `/files/`).
- **Служба systemd**: `kvit.service` обеспечивает автозапуск, мониторинг и перезапуск при сбоях.

## Быстрый старт на сервере (Ubuntu / Debian)

1. Клонируйте репозиторий в `/var/www`:
```bash
cd /var/www
git clone https://github.com/reallyaye/kvit_new.git .
```

2. Запустите скрипт автоматической установки:
```bash
sudo bash deploy/setup_production.sh
```

3. Укажите хеш пароля администратора в `/var/www/kvit_test/.env`:
```bash
python3 -c "import sys; sys.path.append('/var/www/kvit_test'); from services.security.auth_service import hash_password; print(hash_password('ваш_пароль'))"
```
И вставьте полученный хеш в `ADMIN_PASSWORD_HASH=...`.

4. Перезапустите службу:
```bash
sudo systemctl restart kvit
```

## Управление службой
- Статус службы: `sudo systemctl status kvit`
- Перезапуск: `sudo systemctl restart kvit`
- Просмотр логов: `journalctl -u kvit -f`
- Логи приложения: `tail -f /var/www/kvit_test/logs/app.log`
