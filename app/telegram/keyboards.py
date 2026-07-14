def confirmation_keyboard(operation_id: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "Создать поставку", "callback_data": f"supply:confirm:{operation_id}"},
        {"text": "Отмена", "callback_data": f"supply:cancel:{operation_id}"},
    ]]}


def supply_menu() -> dict:
    return {"inline_keyboard": [
        [{"text": "Создать поставку", "callback_data": "supply:start"}],
        [{"text": "Предложить по продажам", "callback_data": "supply:suggest"}],
        [{"text": "Статус поставок", "callback_data": "supply:status"}],
        [{"text": "История и метрики", "callback_data": "supply:history"}],
        [{"text": "Остатки по кластерам", "callback_data": "inventory:clusters"}],
        [{"text": "Проверить обновление", "callback_data": "system:update"}],
    ]}


def recommendation_keyboard(cluster_ids: list[int]) -> dict:
    rows = [[{"text": f"Создать по рекомендации · кластер {cluster_id}", "callback_data": f"supply:recommend:{cluster_id}"}] for cluster_id in cluster_ids]
    return {"inline_keyboard": rows + [[{"text": "Отмена", "callback_data": "supply:status"}]]}


def update_keyboard(version: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "Обновить", "callback_data": f"update:apply:{version}"},
        {"text": "Позже", "callback_data": "update:later"},
        {"text": "Подробнее", "callback_data": f"update:details:{version}"},
    ]]}
