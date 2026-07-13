#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

[[ "${EUID}" -eq 0 ]] || { echo "Запустите через sudo"; exit 1; }
[[ $# -eq 1 ]] || { echo "Использование: sudo bash scripts/install-developer-agent.sh https://github.com/OWNER/REPO.git"; exit 2; }
REPOSITORY="$1"
[[ "${REPOSITORY}" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$ ]] || { echo "Разрешён только HTTPS GitHub repository"; exit 2; }
command -v codex >/dev/null || { echo "Сначала установите Codex CLI из официального источника"; exit 3; }

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
AGENT_DIR=/opt/ozon-ai-developer-agent
WORKSPACE=/opt/ozon-ai-dev
STATE_DIR=/var/lib/ozon-ai-developer
LOG_DIR=/var/log/ozon-ai-developer

getent group ozonaidev >/dev/null || groupadd --system ozonaidev
id codexdev >/dev/null 2>&1 || useradd --system --create-home --home-dir "${STATE_DIR}" --shell /usr/sbin/nologin -g ozonaidev codexdev
usermod -a -G ozonaidev ozonai
install -d -o root -g root -m 0755 "${AGENT_DIR}"
install -d -o codexdev -g ozonaidev -m 2770 "${WORKSPACE}" "${STATE_DIR}" "${LOG_DIR}"
install -d -o codexdev -g codexdev -m 0700 "${STATE_DIR}/codex-home"

rsync -a --delete --exclude .git --exclude .env --exclude .venv --exclude venv --exclude data --exclude logs "${SOURCE_DIR}/" "${AGENT_DIR}/"
python3 -m venv "${AGENT_DIR}/venv"
"${AGENT_DIR}/venv/bin/pip" install -r "${AGENT_DIR}/requirements.txt"

if [[ ! -d "${WORKSPACE}/.git" ]]; then
  rmdir "${WORKSPACE}" || { echo "${WORKSPACE} не пуст и не является Git clone"; exit 4; }
  sudo -u codexdev git clone -- "${REPOSITORY}" "${WORKSPACE}"
fi
if [[ -f "${STATE_DIR}/tasks.sqlite3" ]]; then
  chown codexdev:ozonaidev "${STATE_DIR}/tasks.sqlite3" "${STATE_DIR}/tasks.sqlite3-wal" "${STATE_DIR}/tasks.sqlite3-shm" 2>/dev/null || true
  chmod 0660 "${STATE_DIR}/tasks.sqlite3" "${STATE_DIR}/tasks.sqlite3-wal" "${STATE_DIR}/tasks.sqlite3-shm" 2>/dev/null || true
fi
sudo -u codexdev git -C "${WORKSPACE}" config user.name "Ozon AI Developer Agent"
sudo -u codexdev git -C "${WORKSPACE}" config user.email "codexdev@localhost"

install -d -o root -g root -m 0755 /etc/ozon-ai-developer
if [[ ! -f /etc/ozon-ai-developer/config.env ]]; then
  install -o root -g root -m 0644 "${AGENT_DIR}/deploy/developer-agent.env.example" /etc/ozon-ai-developer/config.env
fi
install -o root -g root -m 0644 "${AGENT_DIR}/deploy/ozon-ai-developer.service" /etc/systemd/system/ozon-ai-developer.service
systemctl daemon-reload
systemctl enable --now ozon-ai-developer.service
echo "Настройте Codex auth отдельно для CODEX_HOME=${STATE_DIR}/codex-home, затем перезапустите службу."
