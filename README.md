# Ozon AI OS 1.1

Серверная система управления магазином Ozon через Telegram. Первый релиз включает read-only FBO Supply Manager, безопасный workflow поставок, проверку обновлений и SQLite-аудит.

По умолчанию `LIVE_MODE=false`: реальные операции записи в Ozon запрещены. Даже в live mode требуется подтверждение разрешённого Telegram-чата.

## Быстрый старт

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check.py
.venv/bin/python -m app.main
```

## Команды

- `/status`, `/version`, `/settings`, `/ozon_test` — состояние, версия и проверка подключения;
- `/supply_report`, `/critical_stock`, `/purchase_plan`, `/supply_suggest` — анализ среднесуточных продаж и рекомендации;
- `/supplies`, `/supply_test`, `/supply_status`, `/supply_history`, `/supply_metrics`, `/supply_cancel` — пошаговый менеджер FBO-поставок;
- `/supply_edit ID SKU QTY BOX` и `/supply_remove ID SKU` — корректировка до подтверждения;
- `/update` — проверка GitHub Release и безопасный запрос обновления;
- `/stocks`, `/stocks_sync`, `/cluster_report`, `/stock_alerts` — FBO-остатки и контроль дефицита по кластерам;
- `/clusters`, `/supplies` — Ozon FBO;
- `/check_update` — GitHub releases.

Формат поставки:

```text
Создай поставку в Москву:
ST-6 120 шт., по 30 в коробке
```

Подробности: [архитектура](docs/architecture-v1.md), [развёртывание](docs/deployment.md).

## Developer Agent

Команды `/dev`, `/dev_status`, `/dev_queue`, `/dev_plan`, `/dev_cancel` создают изолированные задачи разработки. Worker работает от `codexdev`, запускает `codex exec` в `workspace-write`, создаёт отдельную ветку и возвращает отчёт после тестов. Автоматические merge и deploy отсутствуют.

Установка и модель безопасности описаны в [docs/developer-agent.md](docs/developer-agent.md).
