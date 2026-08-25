import base64
import html
import ipaddress
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

def _decode_env_val(val: str) -> str:
    """Декодирует значение, если оно закодировано в формате B64:... или ENC(...)."""
    if not val or not isinstance(val, str):
        return val

    clean_val = val.strip().strip("'\"")
    if clean_val.startswith('ENC(') and clean_val.endswith(')'):
        inner = clean_val[4:-1].strip()
        if inner.lower().startswith(('b64:', 'base64:')):
            inner = inner.split(':', 1)[1].strip()
        try:
            return base64.b64decode(inner.encode('ascii')).decode('utf-8')
        except Exception:
            return clean_val

    for prefix in ('B64:', 'b64:', 'BASE64:', 'base64:', 'ENC:b64:', 'enc:b64:'):
        if clean_val.startswith(prefix):
            encoded = clean_val[len(prefix):].strip()
            try:
                return base64.b64decode(encoded.encode('ascii')).decode('utf-8')
            except Exception:
                return clean_val

    return clean_val

def _load_env():
    """Загружает переменные окружения из файла .env, поддерживая автоматическое декодирование."""
    env_path = os.path.join(BASE, '.env')
    if os.path.isfile(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    decoded_val = _decode_env_val(val)
                    # Устанавливаем только если не переопределено системным окружением
                    if key not in os.environ:
                        os.environ[key] = decoded_val
        except Exception:
            pass

_load_env()

# ────────────────────── Пути к файлам и БД ──────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.environ.get('DB_PATH', 'data.sqlite3')
DB = DB_PATH if os.path.isabs(DB_PATH) else os.path.join(BASE, DB_PATH)

RECEIPTS_PATH = os.environ.get('RECEIPTS_DIR', 'receipts')
RECEIPTS_DIR = RECEIPTS_PATH if os.path.isabs(RECEIPTS_PATH) else os.path.join(BASE, RECEIPTS_PATH)

# ────────────────────── OCR Настройки ──────────────────────
# ────────────────────── OCR Настройки и Защита от DoS ──────────────────────
OCR_ENABLED = os.environ.get('OCR_ENABLED', 'true').lower() in ('true', '1', 'yes')
OCR_LANGUAGES = os.environ.get('OCR_LANGUAGES', 'rus+kaz+eng')
OCR_DPI = int(os.environ.get('OCR_DPI', '150'))
MAX_OCR_DPI = int(os.environ.get('MAX_OCR_DPI', '200'))  # Жесткий потолок DPI
OCR_FALLBACK_ON_NO_TEXT = os.environ.get('OCR_FALLBACK_ON_NO_TEXT', 'true').lower() in ('true', '1', 'yes')

# Бюджет ресурсов на OCR (Защита от исчерпания CPU / RAM)
MAX_OCR_PAGES_PER_DOC = int(os.environ.get('MAX_OCR_PAGES_PER_DOC', '50'))          # Макс. 50 страниц на OCR в одном PDF
MAX_OCR_DOC_TIME_BUDGET = float(os.environ.get('MAX_OCR_DOC_TIME_BUDGET', '60.0'))    # 60 сек суммарно на один документ
MAX_OCR_PAGE_TIME = float(os.environ.get('MAX_OCR_PAGE_TIME', '10.0'))             # 10 сек макс. на одну страницу
MAX_OCR_IMAGE_PIXELS = int(os.environ.get('MAX_OCR_IMAGE_PIXELS', '16000000'))       # 16 Мегапикселей макс. на страницу
MAX_OCR_CONCURRENT_WORKERS = int(os.environ.get('MAX_OCR_CONCURRENT_WORKERS', '2'))  # Макс. 2 параллельных потока OCR на сервере


# ────────────────────── Шардирование квитанций ──────────────────────

def get_receipt_shard_parts(account: str):
    """
    Возвращает двухуровневые компоненты директории для лицевого счёта: (shard1, shard2).
    Например, для счёта '800146' -> ('80', '01').
    """
    acc_clean = re.sub(r'\D', '', str(account or ''))
    if len(acc_clean) >= 4:
        return acc_clean[:2], acc_clean[2:4]
    elif len(acc_clean) == 3:
        return acc_clean[:2], acc_clean[2].ljust(2, '0')
    elif len(acc_clean) == 2:
        return acc_clean[:2], '00'
    elif len(acc_clean) == 1:
        return acc_clean.zfill(2), '00'
    else:
        return 'misc', '00'

def get_sharded_receipt_rel_path(account: str, filename: str) -> str:
    """
    Возвращает относительный путь к файлу квитанции в POSIX-формате (через прямой слэш):
    '80/01/800146_hash.pdf'.
    """
    s1, s2 = get_receipt_shard_parts(account)
    return f"{s1}/{s2}/{filename}"

# ────────────────────── Сетевые настройки ──────────────────────
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8000'))
TRUST_PROXY = os.environ.get('TRUST_PROXY', 'false').lower() in ('true', '1', 'yes')
# Список доверенных IP и подсетей обратных прокси через запятую (например: 127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16)
TRUSTED_PROXIES_RAW = os.environ.get('TRUSTED_PROXIES', '127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7')

# Опциональная встроенная TLS/HTTPS терминация (для прямого запуска без Reverse Proxy)
USE_HTTPS = os.environ.get('USE_HTTPS', 'false').lower() in ('true', '1', 'yes')
SSL_CERT_PATH = os.environ.get('SSL_CERT_PATH', '')
SSL_KEY_PATH = os.environ.get('SSL_KEY_PATH', '')

def _parse_trusted_proxies(raw: str):
    nets = []
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        try:
            if '/' in item:
                nets.append(ipaddress.ip_network(item, strict=False))
            else:
                nets.append(ipaddress.ip_network(item + ('/32' if ':' not in item else '/128'), strict=False))
        except ValueError:
            pass
    return nets

TRUSTED_PROXY_NETWORKS = _parse_trusted_proxies(TRUSTED_PROXIES_RAW)


# ────────────────────── gRPC Microservice ──────────────────────
GRPC_HOST = os.environ.get('GRPC_HOST', '127.0.0.1')  # nosec B104
GRPC_PORT = int(os.environ.get('GRPC_PORT', '50051'))
GRPC_API_KEY = os.environ.get('GRPC_API_KEY', '').strip()
GRPC_USE_TLS = os.environ.get('GRPC_USE_TLS', 'false').lower() in ('true', '1', 'yes')
GRPC_CERT_PATH = os.environ.get('GRPC_CERT_PATH', '')
GRPC_KEY_PATH = os.environ.get('GRPC_KEY_PATH', '')

# ────────────────────── Аутентификация и CSRF ──────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', '').strip() or 'kvit_secret_signing_key_2026'
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '').strip()
SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME', str(24 * 60 * 60)))  # 24 часа
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'auto').strip().lower()  # 'true', 'false', или 'auto' (по HTTPS/X-Forwarded-Proto)
CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'true').strip().lower() in ('true', '1', 'yes')

PROTECTED_PATHS = {'/upload', '/reconcile', '/import-folder', '/api/upload-batch', '/api/sync-receipts', '/api/purge-missing-receipts', '/api/clear-receipts'}
CSRF_PROTECTED_PATHS = {'/upload', '/import-folder', '/api/upload-batch', '/api/sync-receipts', '/api/purge-missing-receipts', '/api/clear-receipts'}


# ────────────────────── WebSocket ──────────────────────
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_SOCKET_TIMEOUT = float(os.environ.get('WS_SOCKET_TIMEOUT', '60.0'))  # 60 сек таймаут сокета для защиты от зависаний

# ────────────────────── Лимиты безопасности ──────────────────────
RATE_LIMIT_API = int(os.environ.get('RATE_LIMIT_API', '60'))        # 60 запросов в минуту для API
RATE_LIMIT_LOGIN = int(os.environ.get('RATE_LIMIT_LOGIN', '10'))    # 10 попыток в минуту для логина
RATE_LIMIT_SEARCH = int(os.environ.get('RATE_LIMIT_SEARCH', '60'))  # 60 запросов в минуту для поиска/квитанций
RATE_LIMIT_GRPC = int(os.environ.get('RATE_LIMIT_GRPC', '120'))        # 120 запросов в минуту для gRPC
RATE_LIMIT_GRPC_RECONCILE = int(os.environ.get('RATE_LIMIT_GRPC_RECONCILE', '30')) # 30 запросов в минуту для тяжелой gRPC сверки

THROTTLE_MAX_CONCURRENT = int(os.environ.get('THROTTLE_MAX_CONCURRENT', '5')) # Макс. 5 одновременных запросов с одного IP
THROTTLE_BURST_RPS = int(os.environ.get('THROTTLE_BURST_RPS', '10'))          # Макс. 10 запросов в секунду с одного IP (всплеск)

# ────────────────────── Лимиты загрузки и PDF (DoS Protection) ──────────────────────
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_BYTES', 100 * 1024 * 1024))  # 100 MB максимум на весь multipart запрос
MAX_FILES_PER_REQUEST = int(os.environ.get('MAX_FILES_PER_REQUEST', '500'))   # Максимум 500 файлов в одной пачке
MAX_PDF_PAGES = int(os.environ.get('MAX_PDF_PAGES', '2000'))                  # Максимум 2000 страниц в одном PDF (PDF Bomb protection)
MAX_PDF_OUTPUT_SIZE = int(os.environ.get('MAX_PDF_OUTPUT_SIZE', 25 * 1024 * 1024)) # 25 MB максимум на одну сохраненную квитанцию
MAX_OCR_TIME = float(os.environ.get('MAX_OCR_TIME', '30.0'))                 # 30 сек таймаут OCR на одну страницу/документ


# ────────────────────── Безопасность импорта из папки ──────────────────────
# Каталоги, из которых разрешён импорт (по умолчанию: корень приложения)
ALLOWED_IMPORT_DIRS_RAW = os.environ.get('ALLOWED_IMPORT_DIRS', BASE)
ALLOWED_IMPORT_DIRS = [
    os.path.realpath(p.strip()) for p in ALLOWED_IMPORT_DIRS_RAW.split(os.pathsep) if p.strip()
]
MAX_IMPORT_FILES = int(os.environ.get('MAX_IMPORT_FILES', '5000'))
MAX_IMPORT_DEPTH = int(os.environ.get('MAX_IMPORT_DEPTH', '5'))

def is_safe_import_path(raw_path: str):
    """
    Проверяет путь на безопасность:
    - существование каталога
    - отсутствие выхода за пределы ALLOWED_IMPORT_DIRS (Path Traversal Protection)
    Возвращает: (is_safe: bool, real_path: str, error_msg: str)
    """
    if not raw_path or not isinstance(raw_path, str):
        return False, '', 'Путь к папке не указан.'

    raw_clean = raw_path.strip()
    target = raw_clean if os.path.isabs(raw_clean) else os.path.join(BASE, raw_clean)
    real_target = os.path.realpath(target)

    if not os.path.isdir(real_target):
        return False, '', f'Папка не найдена: <code>{html.escape(raw_clean)}</code>'

    is_allowed = False
    for allowed in ALLOWED_IMPORT_DIRS:
        if real_target == allowed or real_target.startswith(allowed + os.sep):
            is_allowed = True
            break

    if not is_allowed:
        allowed_desc = ", ".join(f"<code>{html.escape(d)}</code>" for d in ALLOWED_IMPORT_DIRS)
        return False, '', f'Доступ запрещён. Импорт разрешён только из разрешённых каталогов: {allowed_desc}'

    return True, real_target, ''

# ────────────────────── Telegram Bot ──────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_ADMIN_IDS_RAW = os.environ.get('TELEGRAM_ADMIN_IDS', '').strip()
TELEGRAM_POLLING_TIMEOUT = int(os.environ.get('TELEGRAM_POLLING_TIMEOUT', '30'))

def _parse_telegram_admin_ids(raw: str) -> set[int]:
    ids = set()
    if not raw:
        return ids
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit() or (part.startswith('-') and part[1:].isdigit()):
            try:
                ids.add(int(part))
            except ValueError:
                pass
    return ids

TELEGRAM_ADMIN_IDS = _parse_telegram_admin_ids(TELEGRAM_ADMIN_IDS_RAW)
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)

# ────────────────────── Логирование ──────────────────────
LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', str(5 * 1024 * 1024))) # 5 МБ
LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '5'))            # 5 ротированных файлов




