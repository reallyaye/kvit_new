#!/bin/bash
set -e

TOKEN="${1:-${TELEGRAM_BOT_TOKEN:-}}"

if [ -z "$TOKEN" ]; then
    echo "Ошибка: токен Telegram не задан!" >&2
    echo "Использование: $0 <TELEGRAM_BOT_TOKEN>" >&2
    echo "Или задайте переменную окружения TELEGRAM_BOT_TOKEN перед запуском." >&2
    exit 1
fi

if [ -f .env ]; then
    if grep -q "TELEGRAM_BOT_TOKEN=" .env; then
        sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${TOKEN}|" .env
    else
        echo "TELEGRAM_BOT_TOKEN=${TOKEN}" >> .env
    fi
else
    echo "TELEGRAM_BOT_TOKEN=${TOKEN}" > .env
fi

echo "[OK] .env updated with new Telegram Bot Token."
docker compose up -d kvit-api kvit-worker
echo "[OK] kvit-api and kvit-worker restarted successfully."
