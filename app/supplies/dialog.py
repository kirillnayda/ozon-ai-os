from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.security import html_escape
from app.storage.models import SupplyDialog, SupplyOperation
from app.storage.repositories import SnapshotRepository, SupplyDialogRepository
from app.supplies.models import SupplyIntent, SupplyLine
from app.supplies.service import SupplyWorkflow


class ProductCatalog(Protocol):
    def exists(self, offer_id: str) -> bool: ...


class SnapshotProductCatalog:
    def __init__(self, snapshots: SnapshotRepository, test_offer_ids: tuple[str, ...] = ()) -> None:
        self.snapshots = snapshots
        self.test_offer_ids = frozenset(test_offer_ids)

    def exists(self, offer_id: str) -> bool:
        return offer_id in self.test_offer_ids or any(row.offer_id == offer_id for row in self.snapshots.latest_stocks())


@dataclass(frozen=True)
class DialogResult:
    text: str
    operation: SupplyOperation | None = None


class SupplyDialogService:
    """Persisted Telegram wizard. It performs no Ozon mutations."""

    def __init__(self, dialogs: SupplyDialogRepository, catalog: ProductCatalog, workflow: SupplyWorkflow, test_mode: bool, *, test_clusters: tuple[str, ...] = ("Москва", "Санкт-Петербург"), test_slots: tuple[str, ...] = ("2026-07-20 10:00–12:00", "2026-07-21 14:00–16:00")) -> None:
        self.dialogs, self.catalog, self.workflow, self.test_mode = dialogs, catalog, workflow, test_mode
        self.test_clusters, self.test_slots = test_clusters, test_slots

    def start(self, chat_id: int) -> DialogResult:
        self.dialogs.save_dialog(SupplyDialog(chat_id, "destination", {}))
        mode = "\n🧪 Тестовый режим: реальная поставка создана не будет." if self.test_mode else ""
        choices = "\nДоступные тестовые кластеры: " + ", ".join(html_escape(item) for item in self.test_clusters) if self.test_mode else ""
        return DialogResult("<b>Новая FBO-поставка</b>" + mode + choices + "\n\nУкажите кластер или направление поставки.")

    def cancel(self, chat_id: int) -> DialogResult:
        self.dialogs.delete_dialog(chat_id)
        return DialogResult("Создание поставки отменено.")

    def active(self, chat_id: int) -> bool:
        return self.dialogs.get_dialog(chat_id) is not None

    def answer(self, chat_id: int, text: str) -> DialogResult:
        dialog = self.dialogs.get_dialog(chat_id)
        if not dialog:
            return DialogResult("Нет активного сценария. Используйте /supplies.")
        value = text.strip()
        if not value:
            return DialogResult("Значение не может быть пустым. Попробуйте ещё раз.")
        data = dict(dialog.data)

        if dialog.step == "destination":
            if self.test_mode and value not in self.test_clusters:
                return DialogResult("Недоступный тестовый кластер. Выберите: " + ", ".join(html_escape(item) for item in self.test_clusters))
            data["destination"] = value
            slots = "\n".join(f"• <code>{html_escape(item)}</code>" for item in self.test_slots)
            return self._advance(dialog, "slot", data, "Выберите доступный таймслот:\n" + slots if self.test_mode else "Укажите дату и доступный таймслот.")
        if dialog.step == "slot":
            if self.test_mode and value not in self.test_slots:
                return DialogResult("Этот тестовый таймслот недоступен. Выберите один из показанных выше.")
            data["timeslot"] = value
            return self._advance(dialog, "articles", data, "Введите артикулы через запятую, например <code>TEST-SKU, SKU-2</code>.")
        if dialog.step == "articles":
            articles = [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
            if not articles:
                return DialogResult("Не найдено ни одного артикула.")
            unknown = [item for item in articles if not self.catalog.exists(item)]
            if unknown:
                return DialogResult("Неизвестный артикул: " + ", ".join(html_escape(item) for item in unknown) + ". Проверьте список.")
            data.update({"articles": articles, "lines": [], "article_index": 0})
            return self._advance(dialog, "quantity", data, f"Количество для <code>{html_escape(articles[0])}</code>?")
        if dialog.step == "quantity":
            quantity = self._positive_int(value, "Количество")
            if isinstance(quantity, str):
                return DialogResult(quantity)
            data["current_quantity"] = quantity
            article = data["articles"][data["article_index"]]
            return self._advance(dialog, "units_per_box", data, f"Сколько единиц <code>{html_escape(article)}</code> в одной коробке?")
        if dialog.step == "units_per_box":
            units_per_box = self._positive_int(value, "Размер коробки")
            if isinstance(units_per_box, str):
                return DialogResult(units_per_box)
            quantity = int(data["current_quantity"])
            if quantity % units_per_box:
                return DialogResult(f"Количество {quantity} не делится на размер коробки {units_per_box}. Введите другой размер коробки.")
            index = int(data["article_index"])
            article = data["articles"][index]
            data["lines"].append({"offer_id": article, "quantity": quantity, "units_per_box": units_per_box})
            index += 1
            if index < len(data["articles"]):
                data["article_index"] = index
                data.pop("current_quantity", None)
                return self._advance(dialog, "quantity", data, f"Количество для <code>{html_escape(data['articles'][index])}</code>?")
            intent = SupplyIntent(data["destination"], tuple(SupplyLine(**line) for line in data["lines"]))
            operation = self.workflow.prepare(chat_id, intent, {"timeslot": data["timeslot"]})
            self.dialogs.delete_dialog(chat_id)
            lines = ["<b>Проверьте состав поставки</b>", f"Кластер: {html_escape(data['destination'])}", f"Таймслот: {html_escape(data['timeslot'])}", ""]
            lines.extend(f"<code>{html_escape(line.offer_id)}</code>: {line.quantity} шт. / {line.units_per_box} = {line.boxes} кор." for line in intent.lines)
            lines.append(f"\nВсего коробок: {intent.boxes}")
            if self.test_mode:
                lines.append("🧪 После подтверждения будет создана только тестовая операция и тестовая PDF-этикетка.")
            return DialogResult("\n".join(lines), operation)
        return DialogResult("Состояние сценария повреждено. Выполните /supply_cancel и начните заново.")

    def _advance(self, current: SupplyDialog, step: str, data: dict, prompt: str) -> DialogResult:
        self.dialogs.save_dialog(SupplyDialog(current.chat_id, step, data))
        return DialogResult(prompt)

    @staticmethod
    def _positive_int(value: str, label: str) -> int | str:
        try:
            parsed = int(value)
        except ValueError:
            return f"{label} должно быть целым числом."
        return parsed if parsed > 0 else f"{label} должно быть больше нуля."
