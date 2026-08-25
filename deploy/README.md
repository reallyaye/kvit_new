# Руководство по развертыванию (Production Deployment Guide)

Инструкция по развертыванию портала ТОО «КРЭК» и сервиса квитанций на сервере под управлением Linux (Ubuntu / Debian).

---

## 📁 Расположение файлов на сервере

```
/var/www/
├── krec/               # PHP-сайт (каталог www/krec)
├── kvit_test/          # Python-микросервис квитанций
├── deploy/             # Скрипты и конфиги деплоя
│   ├── kvit.service
│   └── setup_production.sh
└── nginx_kvit.conf     # Конфиг веб-сервера Nginx
```

---

## 🚀 Быстрый запуск в 3 шага

### Шаг 1: Запуск скрипта автоматической настройки
Выполните под `root` или через `sudo`:
```bash
chmod +x /var/www/deploy/setup_production.sh
sudo /var/www/deploy/setup_production.sh
```

### Шаг 2: Установка надежного пароля администратора
Сгенерируйте PBKDF2-хеш для пароля администратора:
```bash
/var/www/kvit_test/venv/bin/python -c "from services.security.auth_service import hash_password; print(hash_password('ваш_надежный_пароль'))"
```
Скопируйте полученную строку и вставьте в `/var/www/kvit_test/.env`:
```ini
ADMIN_PASSWORD_HASH=pbkdf2_sha256$600000$...
```
Перезапустите службу:
```bash
sudo systemctl restart kvit
```

### Шаг 3: Получение бесплатного SSL-сертификата (HTTPS)
1. Откройте `/etc/nginx/sites-available/krec` и замените `your-domain.kz` на ваш реальный домен.
2. Выпустите сертификат через Certbot:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.kz -d www.your-domain.kz
```

---

## 🛠️ Полезные команды управления

* **Статус сервиса квитанций**: `sudo systemctl status kvit`
* **Просмотр логов в реальном времени**: `sudo journalctl -u kvit -f`
* **Перезапуск Nginx**: `sudo nginx -t && sudo systemctl reload nginx`
