#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

APP_DIR=/opt/ozon-ai-os
APP_USER=ozonai
SERVICE=ozon-ai-os
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/kirillnayda/ozon-ai-os.git}"

[[ "${EUID}" -eq 0 ]] || { echo "Запустите: sudo bash install.sh"; exit 1; }

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git rsync ca-certificates sqlite3
id "${APP_USER}" >/dev/null 2>&1 || useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
install -d -o "${APP_USER}" -g "${APP_USER}" -m 0750 "${APP_DIR}" "${APP_DIR}/data" "${APP_DIR}/logs"

rsync -a --delete \
  --exclude .env --exclude .venv --exclude venv \
  --exclude data --exclude logs --exclude backups \
  "${SOURCE_DIR}/" "${APP_DIR}/"

python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

ENV_FILE="${APP_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  read -r -s -p "Telegram Bot Token: " TELEGRAM_BOT_TOKEN; echo
  read -r -p "Telegram Chat ID: " TELEGRAM_CHAT_ID
  read -r -p "Ozon Client ID: " OZON_CLIENT_ID
  read -r -s -p "Ozon API Key: " OZON_API_KEY; echo
  for value in "${TELEGRAM_BOT_TOKEN}" "${TELEGRAM_CHAT_ID}" "${OZON_CLIENT_ID}" "${OZON_API_KEY}"; do
    [[ "${value}" != *$'\n'* && "${value}" != *$'\r'* ]] || { echo "Переводы строк запрещены"; exit 2; }
  done
  install -o "${APP_USER}" -g "${APP_USER}" -m 0600 /dev/null "${ENV_FILE}"
  {
    printf 'TELEGRAM_BOT_TOKEN="%s"\n' "${TELEGRAM_BOT_TOKEN//\"/\\\"}"
    printf 'TELEGRAM_CHAT_ID=%s\n' "${TELEGRAM_CHAT_ID}"
    printf 'OZON_CLIENT_ID="%s"\n' "${OZON_CLIENT_ID//\"/\\\"}"
    printf 'OZON_API_KEY="%s"\n' "${OZON_API_KEY//\"/\\\"}"
    sed -n '/^LIVE_MODE=/,$p' "${APP_DIR}/.env.example"
    printf 'GITHUB_REPOSITORY=%s\n' "${REPOSITORY_URL#https://github.com/}" | sed 's/\.git$//'
    printf 'CURRENT_VERSION=%s\n' "$(git -C "${APP_DIR}" describe --tags --exact-match HEAD | sed 's/^v//')"
  } > "${ENV_FILE}"
fi

chown -R root:"${APP_USER}" "${APP_DIR}"
chmod 0750 "${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/data" "${APP_DIR}/logs"
chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
chmod 0600 "${ENV_FILE}"

install -o root -g root -m 0750 "${APP_DIR}/scripts/ozon-ai-os-updater" /usr/local/sbin/ozon-ai-os-updater
install -o root -g root -m 0644 "${APP_DIR}/deploy/ozon-ai-os-updater.service" /etc/systemd/system/
install -o root -g root -m 0644 "${APP_DIR}/deploy/ozon-ai-os-updater.path" /etc/systemd/system/
install -d -o root -g root -m 0755 /etc/ozon-ai-os /run/ozon-ai-os
install -d -o "${APP_USER}" -g "${APP_USER}" -m 0700 /run/ozon-ai-os/update-requests
printf '%s\n' "${REPOSITORY_URL}" > /etc/ozon-ai-os/repository
install -o root -g root -m 0644 "${APP_DIR}/deploy/allowed_signers.example" /etc/ozon-ai-os/allowed_signers

cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
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
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${APP_DIR}/venv/bin/python -m app.main
Restart=on-failure
RestartSec=5
UMask=0007
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/logs /run/ozon-ai-os/update-requests
CapabilityBoundingSet=
LockPersonality=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF

"${APP_DIR}/venv/bin/python" "${APP_DIR}/scripts/check.py"
systemctl daemon-reload
systemctl enable --now "${SERVICE}.service" "ozon-ai-os-updater.path"
systemctl --no-pager --full status "${SERVICE}.service"
echo "Установка завершена. Напишите боту /status, затем /update. LIVE_MODE=false."
