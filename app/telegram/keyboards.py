def confirmation_keyboard(operation_id: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "Подтвердить", "callback_data": f"supply:confirm:{operation_id}"},
        {"text": "Отмена", "callback_data": f"supply:cancel:{operation_id}"},
    ]]}


def update_keyboard(version: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "Обновить", "callback_data": f"update:apply:{version}"},
        {"text": "Позже", "callback_data": "update:later"},
        {"text": "Подробнее", "callback_data": f"update:details:{version}"},
    ]]}

