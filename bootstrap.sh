#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/kirillnayda/ozon-ai-os.git}"
INSTALL_VERSION="${INSTALL_VERSION:-latest}"
WORK_DIR="$(mktemp -d)"
TRUST_FILE="${WORK_DIR}/allowed_signers"
trap 'rm -rf -- "${WORK_DIR}"' EXIT

[[ "${EUID}" -eq 0 ]] || { echo "Запустите: sudo bash bootstrap.sh"; exit 1; }
[[ "${REPOSITORY_URL}" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$ ]] || { echo "Разрешён только HTTPS GitHub repository"; exit 2; }

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates
git clone --filter=blob:none --no-checkout "${REPOSITORY_URL}" "${WORK_DIR}/source"
if [[ "${INSTALL_VERSION}" == latest ]]; then
  INSTALL_VERSION="$(git -C "${WORK_DIR}/source" tag --list 'v*' --sort=-version:refname | sed -n '1p')"
fi
[[ "${INSTALL_VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Не найден корректный release tag"; exit 3; }
git -C "${WORK_DIR}/source" fetch --force origin "refs/tags/${INSTALL_VERSION}:refs/tags/${INSTALL_VERSION}"
git -C "${WORK_DIR}/source" checkout --detach "${INSTALL_VERSION}"
printf '%s\n' 'kirill.nayda@gmail.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMM8tk9iD6QAoCP5cLe7HmCbKPHI2bZ5el7Pc6M5lLYi' > "${TRUST_FILE}"
git -C "${WORK_DIR}/source" -c gpg.format=ssh -c gpg.ssh.allowedSignersFile="${TRUST_FILE}" verify-tag "${INSTALL_VERSION}"
REPOSITORY_URL="${REPOSITORY_URL}" bash "${WORK_DIR}/source/install.sh"
