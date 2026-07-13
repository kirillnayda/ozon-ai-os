# Developer Agent MVP

## Поток

1. `/dev <задача>` сохраняет запись `queued` в SQLite.
2. Единственный worker атомарно переводит её в `analysing`.
3. `GitWorkspace` создаёт `feature/dev-<id>-<slug>` от `origin/main`.
4. `CodexRunner` запускает `codex exec --sandbox workspace-write --ephemeral --ignore-user-config --json`.
5. Supervisor запускает фиксированную команду `python scripts/check.py`.
6. При успехе supervisor создаёт локальный commit и состояние `ready`.
7. Основной бот отправляет отчёт и кнопки push/reject.
8. Push выполняет worker только для сохранённой ready-ветки и точного refspec.

## Состояния

`queued → analysing → coding → testing → ready`; ошибки Codex и тестов приводят к повтору до лимита, затем к `failed`. Отмена приводит к `cancelled`. После аварийного рестарта active-задача возвращается в очередь, если лимит попыток ещё не исчерпан.

## Изоляция

- Unix user `codexdev`, без root и interactive shell.
- Clone: `/opt/ozon-ai-dev`.
- Runtime: `/opt/ozon-ai-developer-agent`.
- State/Codex auth: `/var/lib/ozon-ai-developer`.
- Logs: `/var/log/ozon-ai-developer/<task-id>/attempt-<n>/{codex.jsonl,tests.log}`.
- systemd закрывает `/opt/ozon-ai-os`; production `.env` недоступен.
- Нет auto merge/deploy, dangerous sandbox bypass и произвольных shell-команд.

## Ограничения MVP

Codex auth настраивается оператором отдельно. Для push требуется credential только с правом записи в целевой GitHub repository. Защиту веток и review policy настраивают в GitHub. SQLite-файл должен быть доступен группам `ozonai` и `codexdev` через `ozonaidev`.
