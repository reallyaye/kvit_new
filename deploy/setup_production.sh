#!/usr/bin/env bash
# ==============================================================================
# Скрипт первоначальной настройки и деплоя KREC & Kvit-App на сервере (Debian/Ubuntu)
# ==============================================================================

set -euo pipefail

echo "========================================================="
echo "   Развертывание портала КРЭК и сервиса квитанций"
echo "========================================================="

PROJECT_DIR="/var/www"
SITE_DIR="$PROJECT_DIR/krec"
KVIT_DIR="$PROJECT_DIR/kvit_test"
NGINX_CONF_SRC="$SITE_DIR/../nginx_kvit.conf"

# 1. Установка системных зависимостей
echo "[*] Обновление пакетов и установка зависимостей..."
apt-get update -y
apt-get install -y nginx php8.1-fpm php8.1-cli tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz python3 python3-venv python3-pip

# 2. Настройка прав и каталогов
echo "[*] Настройка прав доступа к файлам веб-сервера..."
chown -R www-data:www-data "$SITE_DIR"
chown -R www-data:www-data "$KVIT_DIR"
chmod 755 "$SITE_DIR"
chmod 755 "$KVIT_DIR"

# 3. Настройка виртуального окружения Python
echo "[*] Создание Python venv и установка зависимостей..."
if [ ! -d "$KVIT_DIR/venv" ]; then
    python3 -m venv "$KVIT_DIR/venv"
fi
"$KVIT_DIR/venv/bin/pip" install --upgrade pip
"$KVIT_DIR/venv/bin/pip" install -r "$KVIT_DIR/requirements.txt"

# 4. Настройка файла переменных окружения (.env)
if [ ! -f "$KVIT_DIR/.env" ]; then
    echo "[*] Создание .env из шаблона..."
    cp "$KVIT_DIR/.env.example" "$KVIT_DIR/.env"
    
    # Генерация боевого ключа gRPC
    GRPC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^GRPC_API_KEY=.*/GRPC_API_KEY=$GRPC_KEY/" "$KVIT_DIR/.env"
    
    echo "[!] Сгенерирован GRPC_API_KEY. Не забудьте задать ADMIN_PASSWORD_HASH!"
fi
chmod 600 "$KVIT_DIR/.env"

# 5. Установка Systemd службы
echo "[*] Установка systemd службы kvit..."
cp "$PROJECT_DIR/deploy/kvit.service" /etc/systemd/system/kvit.service
systemctl daemon-reload
systemctl enable kvit
systemctl restart kvit

# 6. Настройка Nginx
echo "[*] Настройка конфигурации Nginx..."
if [ -f "$NGINX_CONF_SRC" ]; then
    cp "$NGINX_CONF_SRC" /etc/nginx/sites-available/krec
    ln -sf /etc/nginx/sites-available/krec /etc/nginx/sites-enabled/krec
    nginx -t && systemctl reload nginx
fi

echo "========================================================="
echo "✅ Развертывание успешно завершено!"
echo "Проверьте статус сервиса: systemctl status kvit"
echo "========================================================="
