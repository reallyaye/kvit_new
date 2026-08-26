#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Secrets Generator & Safety Auditor
- Генерирует криптографически стойкие секреты для Production (.env).
- Проверяет отсутствие утечек секретов в Git.
"""
import argparse
import hashlib
import os
import secrets
import subprocess
import sys

def generate_strong_password(length: int = 32) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*(-_=+)"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def generate_hex_token(nbytes: int = 32) -> str:
    return secrets.token_hex(nbytes)

def check_git_status():
    """Проверяет, что .env файл не закоммичен и игнорируется git."""
    res = subprocess.run(["git", "status", "--porcelain", ".env"], capture_output=True, text=True)
    if ".env" in res.stdout:
        print("⚠ ВНИМАНИЕ: Файл .env виден git! Проверьте .gitignore.")
    else:
        print("✅ .env корректно изолирован от Git.")

def main():
    parser = argparse.ArgumentParser(description="Генератор секретов для Production")
    parser.add_argument("--output", "-o", default=".env", help="Имя выходного файла (по умолчанию .env)")
    parser.add_argument("--force", "-f", action="store_true", help="Перезаписать существующий файл")
    parser.add_argument("--admin-pass", help="Пароль администратора (если не указан, будет сгенерирован)")
    args = parser.parse_args()

    out_path = os.path.abspath(args.output)
    if os.path.exists(out_path) and not args.force:
        print(f"❌ Файл {out_path} уже существует! Используйте флаг --force для перезаписи.")
        sys.exit(1)

    secret_key = generate_hex_token(32)
    grpc_api_key = generate_hex_token(32)
    db_password = generate_strong_password(32)
    admin_password = args.admin_pass or generate_strong_password(24)
    admin_password_hash = hashlib.sha256(admin_password.encode('utf-8')).hexdigest()

    env_content = f"""# ==============================================================================
# Production Environment Variables (Auto-generated)
# Created at: {subprocess.run(['date', '/t'], shell=True, capture_output=True, text=True).stdout.strip() or 'Deployment'}
# ==============================================================================

APP_ENV=production
LOG_LEVEL=INFO

# Секретный ключ для подписи сессий и CSRF
SECRET_KEY={secret_key}

# Учетные данные администратора
# (Пароль в открытом виде для справки: {admin_password})
ADMIN_PASSWORD_HASH={admin_password_hash}

# API ключ для gRPC шлюза
GRPC_API_KEY={grpc_api_key}

# ────────────────────── PostgreSQL ──────────────────────
DB_TYPE=postgres
POSTGRES_DB=kvit_db
POSTGRES_USER=kvit_admin
POSTGRES_PASSWORD={db_password}
DATABASE_URL=postgresql://kvit_admin:{db_password}@postgres:5432/kvit_db

# ────────────────────── Redis & Tasks ───────────────────
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
QUEUE_VISIBILITY_TIMEOUT=600

# ────────────────────── Workers & OCR ───────────────────
WORKER_COUNT=4
MAX_OCR_CONCURRENT_WORKERS=2

# ────────────────────── Nginx & X-Accel ─────────────────
TRUST_PROXY=true
ENABLE_X_ACCEL_REDIRECT=true
X_ACCEL_PREFIX=/internal_receipts/
RECEIPTS_DIR=/app/receipts
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"✅ Файл секретов успешно сгенерирован: {out_path}")
    print(f"🔑 Пароль администратора (сохраните в защищенном месте!): {admin_password}")
    check_git_status()

if __name__ == "__main__":
    main()
