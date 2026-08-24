#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилита для кодирования и декодирования файла .env.
Использование:
    python encrypt_env.py --encode   # Закодировать все значения в .env в Base64 (B64:...)
    python encrypt_env.py --decode   # Декодировать .env в исходный открытый вид
"""

import argparse
import os
import sys

from services.security.env_crypto import decode_env_content, encode_env_content

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, '.env')

def main():
    parser = argparse.ArgumentParser(description="Кодирование / декодирование файла .env")
    parser.add_argument('--encode', action='store_true', help="Закодировать значения в .env (B64:...)")
    parser.add_argument('--decode', action='store_true', help="Декодировать значения в .env в открытый вид")
    parser.add_argument('--file', default=ENV_PATH, help="Путь к файлу .env (по умолчанию: .env в корне)")
    args = parser.parse_args()

    target_file = os.path.abspath(args.file)
    if not os.path.isfile(target_file):
        print(f"❌ Файл не найден: {target_file}")
        sys.exit(1)

    with open(target_file, 'r', encoding='utf-8') as f:
        content = f.read()

    if args.decode:
        decoded = decode_env_content(content)
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(decoded)
        print(f"✅ Файл {os.path.basename(target_file)} успешно декодирован в открытый вид.")
    else:
        # По умолчанию --encode
        encoded = encode_env_content(content)
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(encoded)
        print(f"🔒 Все значения в {os.path.basename(target_file)} успешно закодированы (Base64).")

if __name__ == '__main__':
    main()
