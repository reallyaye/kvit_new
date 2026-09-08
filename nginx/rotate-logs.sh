#!/bin/sh
set -e

LOG_DIR="/var/log/nginx"
PID_FILE="/var/run/nginx.pid"
DATE=$(date +%Y-%m-%d_%H%M%S)

# 1. Попытка выполнить через официальный logrotate
if [ -x /usr/sbin/logrotate ] && [ -f /etc/logrotate.d/nginx ]; then
    logrotate -f /etc/logrotate.d/nginx 2>&1 || true
else
    # 2. Атомарное перемещение и reopen, если logrotate недоступен
    for logfile in "$LOG_DIR"/access.log "$LOG_DIR"/error.log; do
        if [ -s "$logfile" ]; then
            mv "$logfile" "${logfile}.${DATE}"
        fi
    done
    if [ -f "$PID_FILE" ]; then
        kill -USR1 "$(cat "$PID_FILE")" 2>/dev/null || true
    else
        nginx -s reopen 2>/dev/null || true
    fi
    for rotated in "$LOG_DIR"/*."${DATE}"; do
        if [ -f "$rotated" ]; then
            gzip -9 "$rotated" 2>/dev/null || true
        fi
    done
fi

# 3. Гарантированное удаление любых архивных файлов старше 90 дней
find "$LOG_DIR" -type f \( -name "*.gz" -o -name "*.old" -o -name "*.[0-9]*" -o -name "*_*" \) -mtime +90 -delete 2>/dev/null || true
