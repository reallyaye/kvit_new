#!/bin/bash
set -e

TOKEN="YOUR_TELEGRAM_BOT_TOKEN_HERE"

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
