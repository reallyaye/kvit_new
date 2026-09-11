#!/usr/bin/env bash
# ==============================================================================
# update_blacklists.sh - Ежедневное обновление черных списков Threat Intelligence
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/update_blacklists.log"

mkdir -p "${LOG_DIR}"

echo "==============================================================================" >> "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск автообновления черных списков Nginx" >> "${LOG_FILE}"
echo "==============================================================================" >> "${LOG_FILE}"

# Запуск Python-скрипта
python3 "${PROJECT_DIR}/scripts/update_blacklists.py" --dir "${PROJECT_DIR}" --log "${LOG_FILE}" >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?

if [ ${EXIT_CODE} -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Автообновление успешно завершено." >> "${LOG_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ОШИБКА: Автообновление завершилось с кодом ${EXIT_CODE}!" >> "${LOG_FILE}"
fi

exit ${EXIT_CODE}
