#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/ozon-ai-os"
SERVICE_NAME="ozon-ai-os"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запусти: sudo bash update.sh"
  exit 1
fi

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "Не найден ${APP_DIR}/.env. Сначала выполни установку."
  exit 1
fi

rsync -a --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude "data" \
  ./ "${APP_DIR}/"

"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
chown -R ozonai:ozonai "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"
systemctl restart "${SERVICE_NAME}"
systemctl --no-pager --full status "${SERVICE_NAME}"
