#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/ozon-ai-os"
APP_USER="ozonai"
SERVICE_NAME="ozon-ai-os"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запусти установщик через sudo: sudo bash install.sh"
  exit 1
fi

echo "=========================================="
echo "      OZON AI OS — INSTALLER 0.1.0"
echo "=========================================="

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip git rsync ca-certificates

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home \
    --home-dir "${APP_DIR}" \
    --shell /usr/sbin/nologin \
    "${APP_USER}"
fi

mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude ".git" \
  --exclude ".env" \
  ./ "${APP_DIR}/"

python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

ENV_FILE="${APP_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo
  read -r -p "Telegram Bot Token: " TELEGRAM_BOT_TOKEN
  read -r -p "Telegram Chat ID (число): " TELEGRAM_CHAT_ID
  read -r -p "Ozon Client ID: " OZON_CLIENT_ID
  read -r -s -p "Ozon API Key: " OZON_API_KEY
  echo

  cat > "${ENV_FILE}" <<EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
OZON_CLIENT_ID=${OZON_CLIENT_ID}
OZON_API_KEY=${OZON_API_KEY}

REPORT_HOUR=9
TIMEZONE=Europe/Moscow
LIVE_MODE=false

SUPPLIER_NAME=НБХОЗ
SUPPLY_LEAD_DAYS=7
MIN_STOCK_DAYS=30
COMFORT_STOCK_DAYS=45
CRITICAL_STOCK_DAYS=7
PURCHASE_GROUP_SIZE=6
EOF
else
  echo "Существующий .env сохранён."
fi

mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 600 "${ENV_FILE}"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Ozon AI OS Telegram Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/venv/bin/python -m app.main
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 3
echo
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Установка завершена."
echo "Журнал: journalctl -u ${SERVICE_NAME} -n 100 --no-pager"
