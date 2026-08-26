#!/usr/bin/env bash
# ==============================================================================
# Скрипт первоначальной настройки и деплоя единого портала КРЭК на Python (Debian/Ubuntu)
# ==============================================================================

set -euo pipefail

echo "========================================================="
echo "   Развертывание портала КРЭК и сервиса квитанций"
echo "   (Единый стек Python + Nginx)"
echo "========================================================="

PROJECT_DIR="/var/www"
KVIT_DIR="$PROJECT_DIR/kvit_test"
NGINX_CONF_SRC="$PROJECT_DIR/deploy/nginx_kvit.conf"

# 1. Установка системных зависимостей
echo "[*] Обновление пакетов и установка зависимостей..."
apt-get update -y
apt-get install -y nginx tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz python3 python3-venv python3-pip

# 2. Настройка прав и каталогов
echo "[*] Настройка прав доступа к файлам веб-сервера..."
chown -R www-data:www-data "$KVIT_DIR"
chmod 755 "$KVIT_DIR"

# 3. Настройка виртуального окружения Python
echo "[*] Создание Python venv и установка зависимостей..."
if [[ ! -d "$KVIT_DIR/venv" ]]; then
    python3 -m venv "$KVIT_DIR/venv"
fi
"$KVIT_DIR/venv/bin/pip" install --upgrade pip
"$KVIT_DIR/venv/bin/pip" install -r "$KVIT_DIR/requirements.txt"

# 4. Настройка файла переменных окружения (.env)
if [[ ! -f "$KVIT_DIR/.env" ]]; then
    echo "[*] Создание .env из шаблона..."
    cp "$KVIT_DIR/.env.example" "$KVIT_DIR/.env"
    
    # Генерация боевых ключей SECRET_KEY и gRPC
    SECRET_KEY_VAL=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    GRPC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY_VAL/" "$KVIT_DIR/.env"
    sed -i "s/^GRPC_API_KEY=.*/GRPC_API_KEY=$GRPC_KEY/" "$KVIT_DIR/.env"
    
    echo "[!] Сгенерированы SECRET_KEY и GRPC_API_KEY. Не забудьте задать ADMIN_PASSWORD_HASH!"
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
if [[ -f "$NGINX_CONF_SRC" ]]; then
    cp "$NGINX_CONF_SRC" /etc/nginx/sites-available/krec
    ln -sf /etc/nginx/sites-available/krec /etc/nginx/sites-enabled/krec
    nginx -t && systemctl reload nginx
fi

echo "========================================================="
echo "✅ Развертывание успешно завершено!"
echo "Проверьте статус сервиса: systemctl status kvit"
echo "========================================================="
