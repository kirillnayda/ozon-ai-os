import re

from app.supplies.models import SupplyIntent, SupplyLine

HEADER = re.compile(r"^\s*создай\s+поставку\s+в\s+([^:]+):\s*$", re.IGNORECASE)
LINE = re.compile(r"^\s*([\w.-]+)\s+(\d+)\s*шт\.?\s*,?\s*по\s+(\d+)\s+в\s+коробке\s*$", re.IGNORECASE)


def parse_supply_intent(text: str) -> SupplyIntent:
    rows = [row.strip() for row in text.strip().splitlines() if row.strip()]
    if len(rows) < 2 or not (header := HEADER.match(rows[0])):
        raise ValueError("Формат: Создай поставку в <город>:\nАРТИКУЛ 120 шт., по 30 в коробке")
    lines: list[SupplyLine] = []
    for row in rows[1:]:
        match = LINE.match(row)
        if not match:
            raise ValueError(f"Не удалось разобрать строку: {row}")
        line = SupplyLine(match.group(1), int(match.group(2)), int(match.group(3)))
        if line.quantity <= 0 or line.units_per_box <= 0:
            raise ValueError("Количество должно быть положительным")
        _ = line.boxes
        lines.append(line)
    return SupplyIntent(header.group(1).strip(), tuple(lines))

