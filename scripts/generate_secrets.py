#!/usr/bin/env python3
"""
CLI-утилита для генерации криптостойких секретов и хеша пароля администратора.
Использование:
    python scripts/generate_secrets.py
    python scripts/generate_secrets.py --password "МойНовыйПароль2026!"
    python scripts/generate_secrets.py --write-env
"""

import argparse
import os
import secrets
import sys

# Добавляем корень проекта в sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.security.auth_service import hash_password  # noqa: E402


def generate_all_secrets(admin_password: str | None = None) -> tuple[str, str, str, str]:
    """Генерирует криптостойкие ключи и PBKDF2-хеш пароля."""
    secret_key = secrets.token_hex(32)  # 64 hex символа
    grpc_api_key = secrets.token_hex(32)  # 64 hex символа

    if not admin_password:
        admin_password = secrets.token_urlsafe(16)

    admin_hash = hash_password(admin_password)
    return secret_key, grpc_api_key, admin_password, admin_hash


def update_env_file(env_path: str, updates: dict[str, str]) -> None:
    """Безопасно обновляет или добавляет переменные в .env файл."""
    lines = []
    keys_updated = set()

    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                updated_line = line
                for k, v in updates.items():
                    if stripped.startswith(f"{k}=") or stripped.startswith(f"export {k}="):
                        prefix = "export " if stripped.startswith("export ") else ""
                        updated_line = f"{prefix}{k}={v}\n"
                        keys_updated.add(k)
                        break
                lines.append(updated_line)

    # Добавляем переменные, которых еще не было в .env
    for k, v in updates.items():
        if k not in keys_updated:
            lines.append(f"{k}={v}\n")

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def main():
    parser = argparse.ArgumentParser(description="Генератор криптостойких секретов для Kvit-App")
    parser.add_argument("--password", "-p", help="Пароль администратора (если не указан, будет сгенерирован автоматически)")
    parser.add_argument("--write-env", action="store_true", help="Автоматически записать сгенерированные ключи в .env")
    parser.add_argument("--env-file", default=os.path.join(BASE_DIR, ".env"), help="Путь к целевому файлу .env")

    args = parser.parse_args()

    secret_key, grpc_api_key, raw_password, admin_hash = generate_all_secrets(args.password)

    print("=" * 70)
    print("🔐 СГЕНЕРИРОВАНЫ КРИПТОСТОЙКИЕ СЕКРЕТЫ ДЛЯ KVIT-APP")
    print("=" * 70)
    print("\n1. Пароль администратора (сохраните в надежном месте!):")
    print(f"   {raw_password}\n")
    print("2. Переменные для файла .env или production окружения:\n")
    print(f"SECRET_KEY={secret_key}")
    print(f"ADMIN_PASSWORD_HASH={admin_hash}")
    print(f"GRPC_API_KEY={grpc_api_key}")
    print("\n" + "=" * 70)

    if args.write_env:
        updates = {
            "SECRET_KEY": secret_key,
            "ADMIN_PASSWORD_HASH": admin_hash,
            "GRPC_API_KEY": grpc_api_key,
        }
        update_env_file(args.env_file, updates)
        print(f"✅ Успешно обновлен файл конфигурации: {args.env_file}")
    else:
        print("💡 Подсказка: запустите с флагом --write-env для автоматической записи в .env")


if __name__ == "__main__":
    main()
