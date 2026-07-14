# Развёртывание Ozon AI OS 1.0

## Требования

- Ubuntu 24.04, Python 3.11+;
- отдельный пользователь `ozonai`;
- Ozon API key с минимальными правами;
- Telegram bot и приватный `TELEGRAM_CHAT_ID`;
- подписанные Git release tags для updater.

## Первичная установка

1. Проверить код: `python3 scripts/check.py`.
2. Запустить `sudo bash install.sh` из корня checkout.
3. Заполнить `/opt/ozon-ai-os/.env` по `.env.example` и оставить `LIVE_MODE=false`.
4. Проверить `systemctl status ozon-ai-os` и `journalctl -u ozon-ai-os`.
5. В Telegram проверить `/status`, `/settings`, `/ozon_test`.

## Updater

1. Установить `scripts/ozon-ai-os-updater` как `/usr/local/sbin/ozon-ai-os-updater`, owner `root:root`, mode `0750`.
2. Создать `/etc/ozon-ai-os/repository`, owner `root:root`, mode `0644`, с единственной строкой `https://github.com/OWNER/REPO.git`.
   Для приватного репозитория используйте `git@github.com:OWNER/REPO.git` и отдельный read-only deploy key пользователя root. Не помещайте token в URL.
3. Создать `/etc/ozon-ai-os/allowed_signers`, owner `root:root`, mode `0644`. Добавить email release-maintainer и его SSH signing public key в формате `allowed_signers` из `deploy/allowed_signers.example`.
4. Установить units из `deploy/`, выполнить `systemctl daemon-reload` и `systemctl enable --now ozon-ai-os-updater.path`.
5. Каталог `/run/ozon-ai-os/update-requests` должен быть доступен на запись только `ozonai`, но units и updater — только root.

Updater доверяет только подписанным тегам. Ключи доверенных release maintainers настраиваются root отдельно.

### Обновление через Telegram

1. Задать `GITHUB_REPOSITORY=OWNER/REPO` и фактический `CURRENT_VERSION`.
   Для приватного репозитория также задать `GITHUB_TOKEN` с минимальным read-only доступом к metadata/releases. Значение не логируется.
2. Опубликовать GitHub Release с новым semver-тегом, например `v1.1.0`. Ветка без Release обновлением не считается.
3. В Telegram выполнить `/update` или нажать «Проверить обновление».
4. Кнопка «Обновить» создаёт только фиксированный JSON-запрос `{version, chat_id}`.
5. Root-owned updater проверяет тег, создаёт backup, запускает тесты и health-check. Произвольные команды из Telegram не принимаются.

Не следует обновлять production простым `git pull` из feature-ветки.

## LIVE_MODE

Включать только после contract-тестов с реальным кабинетом. Изменение производится вручную root/оператором в `.env`, затем сервис перезапускается. Telegram не может менять `LIVE_MODE`.

## Откат

Updater сохраняет `.env`, SQLite backup и Git bundle в `/var/backups/ozon-ai-os/<UTC timestamp>`. При сбое срабатывает автоматический rollback. Ручное восстановление должно выполняться оператором по runbook и никогда не через Telegram.

## Проверки реального кабинета

- доступность `/v2/cluster/list` и `/v1/warehouse/fbo/seller/list` для конкретного key role;
- фактические схемы direct/crossdock draft и выбор нужного delivery workflow;
- соответствие offer ID ↔ SKU;
- правила выбора кластера, склада и таймслота;
- поля operation ID и terminal statuses;
- формат cargoes и политика `delete_current_version`;
- lifecycle label job, `file_guid`, Content-Type и размер PDF;
- поведение 409/429, `Retry-After` и идемпотентность Ozon;
- лимиты API и максимальные размеры поставки.

## Developer Agent

```bash
sudo bash scripts/install-developer-agent.sh https://github.com/OWNER/REPO.git
```

После установки оператор отдельно настраивает Codex auth в `CODEX_HOME=/var/lib/ozon-ai-developer/codex-home` и credential для push с минимальными правами. Перезапустите основной `ozon-ai-os` после добавления пользователя в группу `ozonaidev`, чтобы бот получил доступ к общей SQLite-очереди. Подробности — в `docs/developer-agent.md`.
