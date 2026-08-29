#!/usr/bin/env python3
"""
Утилита для быстрой установки пароля администратора портала.
Использование:
    python set_password.py [новый_пароль]
Пример:
    python set_password.py admin123
"""

import sys
import os
import re
from services.security.auth_service import hash_password

def set_admin_password(new_pwd: str):
    new_pwd = new_pwd.strip()
    if not new_pwd:
        print("❌ Ошибка: Пароль не может быть пустым.")
        sys.exit(1)

    pwd_hash = hash_password(new_pwd)
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

    # Обновляем или добавляем в .env
    lines = []
    found = False
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('ADMIN_PASSWORD_HASH='):
                    lines.append(f'ADMIN_PASSWORD_HASH={pwd_hash}\n')
                    found = True
                else:
                    lines.append(line)
    
    if not found:
        lines.append(f'ADMIN_PASSWORD_HASH={pwd_hash}\n')

    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"✅ Пароль администратора успешно установлен!")
    print(f"🔑 Пароль: {new_pwd}")
    print(f"🔒 PBKDF2 Хеш записан в .env: {pwd_hash}")

if __name__ == '__main__':
    pwd = sys.argv[1] if len(sys.argv) > 1 else 'admin123'
    set_admin_password(pwd)
