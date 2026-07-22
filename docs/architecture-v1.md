# Архитектура Ozon AI OS 1.0

## Границы системы

Система управляется одним разрешённым Telegram-чатом, читает данные Ozon FBO и формирует рекомендации. Запись в Ozon проходит через state machine, `LIVE_MODE`, явное callback-подтверждение и уникальный idempotency key.

## Пакеты

- `app/core` — ошибки, безопасность, structured logging, scheduler.
- `app/telegram` — Bot API transport, handlers и inline keyboards.
- `app/ozon` — endpoint registry, retrying HTTP transport, read/write adapters.
- `app/supply` — чистая логика days-of-stock и purchase plan.
- `app/supplies` — parser и state machine FBO-поставки.
- `app/updater` — GitHub release checker и односторонний запрос updater.
- `app/storage` — repository protocols, SQLite adapter и миграции.

`app/main.py` только собирает зависимости и запускает event loop.

## Supply Manager

Ключ агрегации — `(sku, cluster_id)`. Доступный остаток равен `present - reserved`. Среднесуточный спрос рассчитывается без сезонности. Рекомендация доводит запас до 45 дней. Пороги: critical ≤ 7, low < 30, comfort ≤ 45. Позиции к закупке сортируются по срочности и группируются по 6.

## State machine поставки

`draft_created → awaiting_confirmation → creating → waiting_for_ozon → supply_created → labels_requested → labels_ready → completed`, при ошибке — `failed`. Из `awaiting_confirmation` локальный черновик можно перевести в терминальное состояние `cancelled`; запрос к Ozon при этом не выполняется.

Пошаговый Telegram-сценарий хранится в `supply_dialogs`, поэтому выбор кластера, таймслота и состава не теряется при перезапуске. Конкретный склад пользователь не выбирает: его должен вернуть Ozon после обработки draft. При `LIVE_MODE=false` используется сетево-изолированный `SupplyTestTransport`, который проходит тот же orchestration и возвращает тестовый PDF. При `LIVE_MODE=true` используется production transport, но mutating endpoints остаются fail-closed (`contract_verified=False`) до проверки DTO и contract-тестов в реальном кабинете.

ID каждого асинхронного шага сохраняются отдельно. PDF помещается в файловый outbox рядом с SQLite и удаляется только после успешной отправки в Telegram. Рекомендации используют взвешенный среднесуточный спрос, тренд и страховой запас; ожидаемые поставки, сезонность, стоимость, весогабаритные ограничения и статусы приёмки остаются contract boundaries до появления подтверждённых источников данных.

Повторный одинаковый intent того же чата возвращает сохранённую операцию. Terminal state не запускается повторно. Реальный transport не вызывает mutating endpoint, пока его контракт не помечен проверенным.

## Seller API mapping

Проверено 12 июля 2026 года по официальной документации и официальному журналу изменений Ozon Seller API:

| Возможность | Метод |
|---|---|
| Кластеры | `POST /v2/cluster/list` |
| FBO-склады для поставок | `POST /v1/warehouse/fbo/seller/list` |
| FBO-остатки по складам | `POST /v1/product/info/stocks-by-warehouse/fbo` |
| Создание direct draft | `POST /v1/draft/direct/create` |
| Информация о draft | `POST /v2/draft/create/info` |
| Таймслоты | `POST /v2/draft/timeslot/info` |
| Создание supply из draft | `POST /v2/draft/supply/create` |
| Статус создания | `POST /v2/draft/supply/create/status` |
| Создание грузомест | `POST /v1/cargoes/create` |
| Статус грузомест | `POST /v1/cargoes/create/info` |
| Запрос этикеток | `POST /v1/cargoes-label/create` |
| Статус/ID файла | `POST /v1/cargoes-label/get` |
| PDF | `GET /v1/cargoes-label/file/{file_guid}` |

Старые `/v1/draft/create`, `/v1/draft/create/info`, `/v1/draft/timeslot/info`, `/v1/draft/supply/create`, `/v1/draft/supply/create/status` отключены 16 марта 2026 года.

Ozon параллельно развивает FBP API `/v1/fbp/*`. Переход на него должен быть отдельным адаптером и ADR, а не частичной заменой endpoints одного workflow.

## Fail-closed ограничения

Интерактивная документация Ozon не предоставила полные request/response schemas без авторизованного кабинета. Поэтому изменяющие методы зарегистрированы, но production transport блокирует их через `contract_verified=False`. Mock transport проверяет orchestration. Перед включением требуется снять fixtures ответов тестового кабинета, добавить contract DTO/tests и только затем разрешить каждый endpoint.

Аналогично, новый `/v1/product/info/stocks-by-warehouse/fbo` подтверждён официальным журналом, но его полная схема ещё не опубликована в доступном статическом представлении. Данные snapshots и расчётный сервис готовы, однако автоматический production-import остатков и спроса по кластерам не активируется до фиксации DTO. Это осознанный fail-closed рубеж, а не попытка интерпретировать неизвестные поля.

Повторная проверка 14 июля 2026 года: публичная страница [Ozon Seller API](https://docs.ozon.ru/api/seller/) не отдала статические request/response DTO без авторизованного кабинета. Поэтому `UnverifiedOzonInventoryGateway` и production planning gateway намеренно возвращают `ContractNotVerified`; mock gateway и contract-тесты покрывают внутренний нормализованный формат.

Contract probe кабинета от 22 июля 2026 года подтвердил validation-ограничения: `/v1/analytics/stocks` требует массив от 1 до 100 элементов, а `/v1/product/info/stocks-by-warehouse/fbo` — от 1 до 1000 элементов. До получения успешной обезличенной response fixture production-import остаётся fail-closed.

Повторная fixture показала, что `1…100` для `/v1/analytics/stocks` относится к обязательному массиву элементов, а не к `limit`: запрос с `limit=100` также возвращает HTTP 400. Для подтверждения источника SKU contract probe дополнительно снимает схему уже зарегистрированного `POST /v3/product/list`.

Fixture `/v3/product/list` от 22 июля 2026 года подтвердила числовое поле `result.items[].sku`. Contract probe использует до 100 этих SKU для проверки request/response DTO `/v1/analytics/stocks` и `/v1/product/info/stocks-by-warehouse/fbo`; это остаётся диагностикой, пока успешные response fixtures не закреплены contract-тестами.

Успешная fixture `/v1/analytics/stocks` от 22 июля 2026 года подтвердила request `{skus: int[]}` (1–100) и поля `sku`, `offer_id`, `warehouse_id`, `warehouse_name`, `cluster_id`, `cluster_name`, `available_stock_count`, `ads_cluster`. `OzonAnalyticsInventoryGateway` использует этот read-only контракт; `ads_cluster` дедуплицируется по `(sku, cluster_id)`. Неполный или изменившийся DTO блокируется contract validation без частичного сохранения снимков.

## Хранилище

SQLite работает в WAL mode с busy timeout. Repository protocols не зависят от SQLite и допускают PostgreSQL adapter. Секреты не хранянятся. Audit log отделён от operational state.

## Updater trust boundary

Бот пишет атомарный JSON `{version, chat_id}` в `/run/ozon-ai-os/update-requests`. Root-owned path unit запускает фиксированный updater. Updater читает доверенный repository URL из root-owned `/etc/ozon-ai-os/repository`, принимает только semver, проверяет подписанный Git tag, создаёт backup, запускает тесты и health-check. Произвольных аргументов и shell-команд из Telegram нет.
