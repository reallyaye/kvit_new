#!/bin/bash
# ==============================================================================
# KREC Portal - Daily Backup Cron Runner
# Рекомендуемая запись в crontab (запуск ежедневно в 03:00):
# 0 3 * * * /home/user/portal/kvit_new/scripts/daily_backup.sh >> /home/user/portal/kvit_new/logs/kvit_backup.log 2>&1
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${BACKUP_LOG_FILE:-$PROJECT_DIR/logs/kvit_backup.log}"
mkdir -p "$(dirname "$LOG_FILE")"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
REMOTE_TARGET="${BACKUP_REMOTE_TARGET:-}"

echo "=============================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск ежедневного резервного копирования KREC"
echo "Проект: $PROJECT_DIR"
echo "Каталог бэкапов: $BACKUP_DIR"
echo "Срок хранения: $RETENTION_DAYS дней"
echo "=============================================================================="

cd "$PROJECT_DIR"

# Активация виртуального окружения, если оно есть
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

ARGS="--dir $BACKUP_DIR --retention-days $RETENTION_DAYS"
if [ -n "$REMOTE_TARGET" ]; then
    ARGS="$ARGS --remote-target $REMOTE_TARGET"
fi

# Запуск backup_manager с верификацией восстановления
python3 "$SCRIPT_DIR/backup_manager.py" $ARGS

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Резервное копирование успешно завершено."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ОШИБКА: Резервное копирование завершилось с кодом $EXIT_CODE" >&2
fi

exit $EXIT_CODE
