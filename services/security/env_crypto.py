# -*- coding: utf-8 -*-
"""
Утилита для кодирования и декодирования значений в файле .env (Base64 / Obfuscation).
Позволяет скрыть секреты, токены и конфигурацию от открытого отображения.
"""

import base64

PREFIXES = ('B64:', 'b64:', 'BASE64:', 'base64:', 'ENC:b64:', 'ENC(b64:')

def encode_val(val: str) -> str:
    """Кодирует значение в формат B64:<base64_string>."""
    if not val:
        return ""
    b64_str = base64.b64encode(val.encode('utf-8')).decode('ascii')
    return f"B64:{b64_str}"

def decode_val(val: str) -> str:
    """Декодирует значение, если оно закодировано в формате B64:... или ENC(...)."""
    if not val or not isinstance(val, str):
        return val

    clean_val = val.strip().strip("'\"")

    # Формат ENC(b64:...) или ENC(...)
    if clean_val.startswith('ENC(') and clean_val.endswith(')'):
        inner = clean_val[4:-1].strip()
        if inner.lower().startswith(('b64:', 'base64:')):
            inner = inner.split(':', 1)[1].strip()
        try:
            return base64.b64decode(inner.encode('ascii')).decode('utf-8')
        except Exception:
            return clean_val

    # Формат B64:... или BASE64:... или ENC:b64:...
    for prefix in ('B64:', 'b64:', 'BASE64:', 'base64:', 'ENC:b64:', 'enc:b64:'):
        if clean_val.startswith(prefix):
            encoded = clean_val[len(prefix):].strip()
            try:
                return base64.b64decode(encoded.encode('ascii')).decode('utf-8')
            except Exception:
                return clean_val

    return clean_val

def encode_env_content(content: str) -> str:
    """Кодирует все переменные в содержимом .env файла."""
    output_lines = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('#') or '=' not in line:
            output_lines.append(line)
            continue

        key, val = line.split('=', 1)
        key_strip = key.strip()
        val_clean = val.strip().strip("'\"")

        # Если значение уже закодировано, сначала декодируем
        raw_val = decode_val(val_clean)
        encoded_val = encode_val(raw_val)
        output_lines.append(f"{key_strip}={encoded_val}")

    return "\n".join(output_lines) + "\n"

def decode_env_content(content: str) -> str:
    """Декодирует все закодированные переменные в содержимом .env файла."""
    output_lines = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('#') or '=' not in line:
            output_lines.append(line)
            continue

        key, val = line.split('=', 1)
        key_strip = key.strip()
        val_clean = val.strip().strip("'\"")

        raw_val = decode_val(val_clean)
        output_lines.append(f"{key_strip}={raw_val}")

    return "\n".join(output_lines) + "\n"
