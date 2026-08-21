import os, html

BASE = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    """Загружает переменные окружения из файла .env, если он существует."""
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
                    val = val.strip().strip("'\"")
                    # Устанавливаем только если не переопределено системным окружением
                    if key not in os.environ:
                        os.environ[key] = val
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
OCR_ENABLED = os.environ.get('OCR_ENABLED', 'true').lower() in ('true', '1', 'yes')
OCR_LANGUAGES = os.environ.get('OCR_LANGUAGES', 'rus+kaz+eng')
OCR_DPI = int(os.environ.get('OCR_DPI', '200'))
OCR_FALLBACK_ON_NO_TEXT = os.environ.get('OCR_FALLBACK_ON_NO_TEXT', 'true').lower() in ('true', '1', 'yes')

# ────────────────────── Шардирование квитанций ──────────────────────
import re

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
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8000'))
TRUST_PROXY = os.environ.get('TRUST_PROXY', 'false').lower() in ('true', '1', 'yes')
# Список доверенных IP и подсетей обратных прокси через запятую (например: 127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16)
TRUSTED_PROXIES_RAW = os.environ.get('TRUSTED_PROXIES', '127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7')

import ipaddress
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
GRPC_HOST = os.environ.get('GRPC_HOST', '0.0.0.0')
GRPC_PORT = int(os.environ.get('GRPC_PORT', '50051'))
GRPC_API_KEY = os.environ.get('GRPC_API_KEY', '').strip()
GRPC_USE_TLS = os.environ.get('GRPC_USE_TLS', 'false').lower() in ('true', '1', 'yes')
GRPC_CERT_PATH = os.environ.get('GRPC_CERT_PATH', '')
GRPC_KEY_PATH = os.environ.get('GRPC_KEY_PATH', '')

# ────────────────────── Аутентификация ──────────────────────
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')
SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME', str(24 * 60 * 60)))  # 24 часа

PROTECTED_PATHS = {'/upload', '/reconcile', '/import-folder', '/api/upload-batch', '/api/sync-receipts', '/api/clear-receipts'}

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

# ────────────────────── Логирование ──────────────────────
LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', str(5 * 1024 * 1024))) # 5 МБ
LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '5'))            # 5 ротированных файлов



