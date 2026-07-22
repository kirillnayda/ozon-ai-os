def confirmation_keyboard(operation_id: str) -> dict:
    return {"inline_keyboard": [
        [
            {"text": "Создать поставку", "callback_data": f"supply:confirm:{operation_id}"},
            {"text": "Отмена", "callback_data": f"supply:cancel:{operation_id}"},
        ],
        [{"text": "← В главное меню", "callback_data": "menu:main"}],
    ]}


def supply_menu() -> dict:
    return {"inline_keyboard": [
        [{"text": "Создать поставку", "callback_data": "supply:start"}],
        [{"text": "Предложить по продажам", "callback_data": "supply:suggest"}],
        [{"text": "Статус поставок", "callback_data": "supply:status"}],
        [{"text": "История и метрики", "callback_data": "supply:history"}],
        [{"text": "Остатки по кластерам", "callback_data": "inventory:clusters"}],
        [{"text": "Проверить API остатков", "callback_data": "inventory:contracts"}],
        [{"text": "Проверить обновление", "callback_data": "system:update"}],
    ]}


def back_to_menu_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "← Назад в меню", "callback_data": "menu:main"}]]}


def inventory_products_keyboard(products: list[tuple[int, str]], page: int, pages: int) -> dict:
    rows = [[{"text": offer_id, "callback_data": f"inventory:product:{sku}:{page}"}] for sku, offer_id in products]
    navigation = []
    if page > 0:
        navigation.append({"text": "← Назад", "callback_data": f"inventory:page:{page - 1}"})
    if page + 1 < pages:
        navigation.append({"text": "Вперёд →", "callback_data": f"inventory:page:{page + 1}"})
    if navigation:
        rows.append(navigation)
    rows.append([{"text": "← В главное меню", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


def inventory_product_keyboard(page: int) -> dict:
    return {"inline_keyboard": [
        [{"text": "← Назад к товарам", "callback_data": f"inventory:page:{page}"}],
        [{"text": "В главное меню", "callback_data": "menu:main"}],
    ]}


def recommendation_keyboard(cluster_ids: list[int]) -> dict:
    rows = [[{"text": f"Создать по рекомендации · кластер {cluster_id}", "callback_data": f"supply:recommend:{cluster_id}"}] for cluster_id in cluster_ids]
    return {"inline_keyboard": rows + [[{"text": "← В главное меню", "callback_data": "menu:main"}]]}


def update_keyboard(version: str) -> dict:
    return {"inline_keyboard": [
        [
            {"text": "Обновить", "callback_data": f"update:apply:{version}"},
            {"text": "Позже", "callback_data": "update:later"},
            {"text": "Подробнее", "callback_data": f"update:details:{version}"},
        ],
        [{"text": "← В главное меню", "callback_data": "menu:main"}],
    ]}
