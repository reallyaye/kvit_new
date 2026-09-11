#!/usr/bin/env python3
"""
update_blacklists.py

Автоматическое обновление баз вредоносных IP-адресов, фишинговых сетей,
ботнетов и сканеров уязвимостей для Nginx (Threat Intelligence Blocklist).

Источники:
  1. Spamhaus DROP  - https://www.spamhaus.org/drop/drop.txt
  2. Spamhaus EDROP - https://www.spamhaus.org/drop/edrop.txt
  3. FireHOL Level 1 - https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level1.netset
  4. Blocklist.de   - https://lists.blocklist.de/lists/all.txt
  5. Ручной список  - nginx/lists/manual_blocklist.conf

Запуск:
  python3 scripts/update_blacklists.py
  python3 scripts/update_blacklists.py --dry-run
"""

import argparse
import datetime
import ipaddress
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

FEEDS = {
    "Spamhaus DROP": "https://www.spamhaus.org/drop/drop.txt",
    "Spamhaus EDROP": "https://www.spamhaus.org/drop/edrop.txt",
    "FireHOL Level 1": "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level1.netset",
    "Blocklist.de": "https://lists.blocklist.de/lists/all.txt",
}

# Резервные захардкоженные опасные подсети на случай полной недоступности интернета
FALLBACK_SUBNETS = [
    "45.148.10.247/32",  # DMZHOST AS48090 сканер
]

def setup_logger(log_file: str = None) -> logging.Logger:
    logger = logging.getLogger("blacklist_updater")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    # Если лог-файл задан, пишем строго в него, избегая дублирования при перенаправлении в shell
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    else:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


def load_whitelist(whitelist_path: str, logger: logging.Logger) -> set:
    """Загружает доверенные IP и подсети из whitelist.conf."""
    whitelist = set()
    if not os.path.exists(whitelist_path):
        return whitelist

    try:
        with open(whitelist_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # формат: IP 0; или CIDR 0;
                token = line.split()[0].rstrip(";")
                try:
                    net = ipaddress.ip_network(token, strict=False)
                    whitelist.add(net)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка чтения whitelist {whitelist_path}: {e}")

    return whitelist


def load_manual_blocklist(manual_path: str, logger: logging.Logger) -> set:
    """Загружает постоянные ручные блокировки из manual_blocklist.conf."""
    manual_nets = set()
    if not os.path.exists(manual_path):
        return manual_nets

    try:
        with open(manual_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                token = line.split()[0].rstrip(";")
                try:
                    net = ipaddress.ip_network(token, strict=False)
                    manual_nets.add(net)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка чтения manual_blocklist {manual_path}: {e}")

    return manual_nets


def fetch_feed(name: str, url: str, logger: logging.Logger, timeout: int = 15) -> set:
    """Скачивает и парсит один список угроз."""
    nets = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KrecSecurityThreatFeed/1.0; +https://krec.kz)"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                token = line.split(";")[0].split()[0]
                try:
                    net = ipaddress.ip_network(token, strict=False)
                    if net.is_private or net.is_loopback or net.is_multicast or net.is_link_local or net.is_unspecified:
                        continue
                    nets.add(net)
                except ValueError:
                    continue
        logger.info(f"  [OK] {name}: успешно загружено {len(nets)} уникальных сетей")
    except Exception as e:
        logger.error(f"  [FAIL] {name}: ошибка загрузки ({e})")

    return nets


def is_whitelisted(net: ipaddress.IPv4Network | ipaddress.IPv6Network, whitelist: set) -> bool:
    """Проверяет, не входит ли подсеть в белый список."""
    for w_net in whitelist:
        if net.overlaps(w_net):
            return True
    return False


def build_blocklist_conf(project_dir: str, dry_run: bool = False, no_reload: bool = False, logger: logging.Logger = None) -> bool:
    lists_dir = os.path.join(project_dir, "nginx", "lists")
    whitelist_path = os.path.join(lists_dir, "whitelist.conf")
    manual_path = os.path.join(lists_dir, "manual_blocklist.conf")
    target_conf = os.path.join(lists_dir, "blocklist.conf")

    os.makedirs(lists_dir, exist_ok=True)

    logger.info("=== Запуск обновления баз Threat Intelligence ===")

    # 1. Загрузка белого списка
    whitelist = load_whitelist(whitelist_path, logger)
    logger.info(f"Загружено {len(whitelist)} доверенных подсетей из whitelist.conf")

    # 2. Загрузка ручного списка
    manual_nets = load_manual_blocklist(manual_path, logger)
    logger.info(f"Загружено {len(manual_nets)} сетей из manual_blocklist.conf")

    # 3. Скачивание онлайн-баз
    all_nets = set()
    all_nets.update(manual_nets)

    for name, url in FEEDS.items():
        feed_nets = fetch_feed(name, url, logger)
        all_nets.update(feed_nets)

    # Если вообще все фиды упали (сбой сети/DNS), сохраняем текущую рабочую базу
    if len(all_nets) <= len(manual_nets):
        if os.path.exists(target_conf) and os.path.getsize(target_conf) > 100:
            logger.warning(
                f"Онлайн-фиды временно недоступны. Текущая активная рабочая база ({target_conf}) "
                "сохранена без изменений для непрерывной защиты."
            )
            return True
        else:
            logger.warning("Онлайн-фиды недоступны и локальная база пуста. Применяются резервные подсети.")
            for fb in FALLBACK_SUBNETS:
                all_nets.add(ipaddress.ip_network(fb, strict=False))

    # 4. Фильтрация по белому списку и приватным сетям
    filtered_nets = set()
    for net in all_nets:
        if net.is_private or net.is_loopback or net.is_multicast or net.is_link_local or net.is_unspecified:
            continue
        if is_whitelisted(net, whitelist):
            logger.info(f"Пропущена подсеть {net} (содержится в whitelist)")
            continue
        filtered_nets.add(net)

    # Исключаем ручные блокировки, так как они подключаются через manual_blocklist.conf
    dynamic_nets = [net for net in filtered_nets if net not in manual_nets]
    logger.info(f"Всего подготовлено {len(dynamic_nets)} уникальных динамических подсетей")

    # Сортировка по IP-адресу
    sorted_nets = sorted(dynamic_nets, key=lambda n: (n.version, int(n.network_address), n.prefixlen))

    # 5. Формирование содержимого конфига
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# =========================================================================",
        f"# Dynamic Threat Intelligence Blacklist (Auto-generated: {now})",
        f"# Источники: {', '.join(FEEDS.keys())}",
        f"# Всего записей: {len(sorted_nets)}",
        "# =========================================================================",
        "",
    ]

    for net in sorted_nets:
        lines.append(f"{net} 1;")

    content = "\n".join(lines) + "\n"

    if dry_run:
        logger.info(f"[DRY-RUN] Сгенерировано {len(sorted_nets)} строк. Запись в файл и перезагрузка Nginx пропущены.")
        return True

    # 6. Атомарная запись во временный файл и создание резервной копии
    with tempfile.NamedTemporaryFile("w", dir=lists_dir, delete=False, encoding="utf-8") as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name

    backup_path = target_conf + ".bak"
    if os.path.exists(target_conf):
        shutil.copyfile(target_conf, backup_path)

    # Перемещаем файл на место
    shutil.move(tmp_path, target_conf)
    logger.info(f"Файл {target_conf} успешно обновлён.")

    # 7. Проверка конфигурации Nginx и reload с гарантированным откатом
    if not no_reload:
        def do_rollback(reason: str):
            logger.error(f"ОШИБКА: {reason}")
            if os.path.exists(backup_path):
                logger.info("Выполняется откат к предыдущей рабочей версии blocklist.conf...")
                shutil.copyfile(backup_path, target_conf)
                try:
                    subprocess.run(
                        ["docker", "exec", "kvit-nginx", "nginx", "-t"],
                        capture_output=True, text=True, timeout=15
                    )
                    subprocess.run(
                        ["docker", "exec", "kvit-nginx", "nginx", "-s", "reload"],
                        capture_output=True, text=True, timeout=15
                    )
                    logger.info("Откат успешно завершен, предыдущая рабочая конфигурация активна.")
                except Exception as rb_err:
                    logger.error(f"Сбой при откате Nginx: {rb_err}")

        test_cmd = ["docker", "exec", "kvit-nginx", "nginx", "-t"]
        try:
            res = subprocess.run(test_cmd, capture_output=True, text=True, timeout=15)
            if res.returncode != 0:
                do_rollback(f"Проверка 'nginx -t' не прошла:\n{res.stderr}")
                return False
            logger.info("Проверка синтаксиса Nginx (nginx -t) успешно пройдена.")
        except Exception as e:
            do_rollback(f"Исключение при проверке nginx -t: {e}")
            return False

        # 8. Мягкая перезагрузка Nginx
        reload_cmd = ["docker", "exec", "kvit-nginx", "nginx", "-s", "reload"]
        try:
            res = subprocess.run(reload_cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                logger.info("Nginx успешно перезагружен (nginx -s reload). Новые правила активны!")
            else:
                do_rollback(f"Ошибка reload Nginx:\n{res.stderr}")
                return False
        except Exception as e:
            do_rollback(f"Исключение при перезагрузке Nginx: {e}")
            return False

    logger.info("=== Обновление баз успешно завершено ===")
    return True


def main():
    parser = argparse.ArgumentParser(description="Обновление черных списков Nginx")
    parser.add_argument("--dry-run", action="store_true", help="Только проверить скачивание без применения")
    parser.add_argument("--no-reload", action="store_true", help="Не перезагружать Nginx")
    parser.add_argument("--dir", default=None, help="Базовый каталог проекта (по умолчанию автоопределение)")
    parser.add_argument("--log", default=None, help="Путь к файлу логов")
    args = parser.parse_args()

    project_dir = args.dir
    if not project_dir:
        # Автоопределение каталога проекта (на уровень выше scripts/)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.abspath(os.path.join(script_dir, ".."))

    log_file = args.log
    if not log_file:
        log_file = os.path.join(project_dir, "logs", "update_blacklists.log")

    logger = setup_logger(log_file)
    success = build_blocklist_conf(project_dir, dry_run=args.dry_run, no_reload=args.no_reload, logger=logger)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
