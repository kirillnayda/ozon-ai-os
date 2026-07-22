from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import socket

from app.config import Settings
from app.inventory.service import InventoryService
from app.inventory.contract_probe import OzonContractProbe
from app.core.security import html_escape
from app.core.errors import ContractNotVerified
from app.ozon.read_api import OzonReadApi
from app.storage.models import OperationState
from app.storage.repositories import OperationRepository
from app.supply.report import render_report
from app.supply.service import SupplyManager
from app.supplies.parser import parse_supply_intent
from app.supplies.dialog import SupplyDialogService
from app.supplies.service import SupplyWorkflow
from app.telegram.keyboards import back_to_menu_keyboard, confirmation_keyboard, inventory_product_keyboard, inventory_products_keyboard, recommendation_keyboard, supply_menu, update_keyboard
from app.updater.checker import GitHubReleaseChecker
from app.updater.request import UpdateRequestWriter


@dataclass
class HandlerResult:
    text: str
    keyboard: dict | None = None
    document_name: str | None = None
    document: bytes | None = None
    operation_id: str | None = None


class CommandHandlers:
    STATE_LABELS = {
        OperationState.DRAFT_CREATED: "Черновик подготовлен",
        OperationState.AWAITING_CONFIRMATION: "Ожидает подтверждения",
        OperationState.CREATING: "Создаётся draft",
        OperationState.WAITING_FOR_OZON: "Ozon обрабатывает",
        OperationState.SUPPLY_CREATED: "Поставка создана",
        OperationState.LABELS_REQUESTED: "Формируются этикетки",
        OperationState.LABELS_READY: "Этикетки готовы",
        OperationState.COMPLETED: "Завершено",
        OperationState.CANCELLED: "Отменено",
        OperationState.FAILED: "Требуется внимание",
    }
    def __init__(self, settings: Settings, ozon: OzonReadApi, supply: SupplyManager, workflow: SupplyWorkflow, dialogs: SupplyDialogService, operations: OperationRepository, updates: GitHubReleaseChecker, update_writer: UpdateRequestWriter, inventory: InventoryService | None = None) -> None:
        self.settings, self.ozon, self.supply, self.workflow = settings, ozon, supply, workflow
        self.dialogs, self.operations, self.updates, self.update_writer = dialogs, operations, updates, update_writer
        self.inventory = inventory
        self.started_at = datetime.now()

    def allowed(self, chat_id: int) -> bool:
        return chat_id == self.settings.telegram_chat_id

    async def message(self, chat_id: int, text: str) -> HandlerResult | None:
        if not self.allowed(chat_id):
            return None
        stripped = text.strip()
        if not stripped:
            return HandlerResult("Пустое сообщение. Используйте /help")
        if not stripped.startswith("/"):
            if self.dialogs.active(chat_id):
                answer = self.dialogs.answer(chat_id, stripped)
                return HandlerResult(answer.text, confirmation_keyboard(answer.operation.id) if answer.operation else None)
            normalized = stripped.casefold()
            if "созда" in normalized and "постав" in normalized:
                return HandlerResult(self.dialogs.start(chat_id).text)
            if ("предлож" in normalized or "рекомен" in normalized) and "постав" in normalized:
                items = [x for group in self.supply.purchase_groups() for x in group]
                return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", recommendation_keyboard(sorted({x.cluster_id for x in items})) if items else supply_menu())
            if "истори" in normalized and "постав" in normalized:
                return self._history(chat_id)
            if "статус" in normalized and "постав" in normalized:
                return self._status()
            if "остат" in normalized:
                return self._inventory_report()
            try:
                intent = parse_supply_intent(stripped)
            except ValueError as exc:
                return HandlerResult(html_escape(exc))
            operation = self.workflow.prepare(chat_id, intent)
            lines = [f"<b>Черновик поставки в {html_escape(intent.destination)}</b>"]
            lines.extend(f"{html_escape(x.offer_id)}: {x.quantity} шт., {x.boxes} коробок" for x in intent.lines)
            lines.append(f"\nВсего грузомест: {intent.boxes}")
            lines.append("Реальная отправка требует LIVE_MODE=true и подтверждения.")
            return HandlerResult("\n".join(lines), confirmation_keyboard(operation.id))

        command = stripped.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command in {"/start", "/help"}:
            return HandlerResult("<b>Ozon AI OS 1.1</b>\n/status /version /supplies /stocks /stocks_sync /ozon_contracts /cluster_report /stock_alerts /supply_status /supply_history /supply_metrics /supply_test /supply_suggest /update /settings\n\nМожно написать: «Создать поставку», «Предложи поставку», «Покажи остатки».\n\nDeveloper Agent: /dev /dev_status /dev_queue /dev_plan /dev_cancel", supply_menu())
        if command == "/version":
            mode = "LIVE" if self.settings.live_mode else "TEST"
            return HandlerResult(f"<b>Ozon AI OS</b>\nВерсия: <code>{html_escape(self.settings.current_version)}</code>\nРежим: {mode}")
        if command == "/status":
            uptime = str(datetime.now() - self.started_at).split(".")[0]
            return HandlerResult(f"<b>Статус Ozon AI OS</b>\nСервер: <code>{html_escape(socket.gethostname())}</code>\nРаботает: {uptime}\nLIVE_MODE: {'включён' if self.settings.live_mode else 'выключен'}")
        if command == "/settings":
            return HandlerResult(f"<b>Правила AI Supply Manager</b>\nПоставщик: {html_escape(self.settings.supplier_name)}\nСрок: {self.settings.supply_lead_days} дн.\nКритический/минимальный/комфортный: {self.settings.critical_stock_days}/{self.settings.min_stock_days}/{self.settings.comfort_stock_days} дн.\nГруппа закупки: ≈{self.settings.purchase_group_size}")
        if command == "/ozon_test":
            result = await self.ozon.test_connection()
            return HandlerResult(f"Ozon подключён ✅\nПолучено: {result['items_received']} · всего: {html_escape(result['total'])}")
        if command in {"/supply_report", "/critical_stock", "/purchase_plan"}:
            items = self.supply.recommendations()
            if command == "/critical_stock":
                items = [x for x in items if x.level.value == "critical"]
            if command == "/purchase_plan":
                items = [x for group in self.supply.purchase_groups() for x in group]
            return HandlerResult(render_report(items) if items else "Нет синхронизированных данных или подходящих позиций.")
        if command == "/clusters":
            data = await self.ozon.clusters()
            clusters = data.get("clusters") or data.get("result") or []
            return HandlerResult("<b>Кластеры Ozon</b>\n" + "\n".join(html_escape(x.get("name") or x.get("cluster_name") or x) for x in clusters[:50]))
        if command in {"/stocks", "/cluster_report"}:
            return self._inventory_report()
        if command == "/stock_alerts":
            items = [item for item in self.supply.recommendations() if item.level.value in {"critical", "low"}]
            return HandlerResult(render_report(items) if items else "Критичных остатков нет.")
        if command == "/stocks_sync":
            if not self.inventory:
                return HandlerResult("Сервис остатков не настроен.")
            try:
                stocks, demand = await self.inventory.sync(str(chat_id))
            except ContractNotVerified as exc:
                return HandlerResult(f"Синхронизация заблокирована проверкой контракта: {html_escape(exc)}. Внешний ответ не сохранён.")
            except Exception as exc:
                return HandlerResult(f"Синхронизация заблокирована ({html_escape(type(exc).__name__)}). Внешний ответ не сохранён.")
            return HandlerResult(f"Остатки синхронизированы: {stocks}; срезов спроса: {demand}.")
        if command == "/ozon_contracts":
            return await self._ozon_contracts()
        if command == "/supplies":
            return HandlerResult("<b>Менеджер FBO-поставок</b>\nВыберите действие.", supply_menu())
        if command == "/supply_test":
            if self.settings.live_mode:
                return HandlerResult("Команда /supply_test доступна только при LIVE_MODE=false.")
            return HandlerResult(self.dialogs.start(chat_id).text)
        if command == "/supply_suggest":
            items = [x for group in self.supply.purchase_groups() for x in group]
            return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", recommendation_keyboard(sorted({x.cluster_id for x in items})) if items else supply_menu())
        if command == "/supply_edit":
            parts = stripped.split()
            if len(parts) != 5:
                return HandlerResult("Формат: <code>/supply_edit ID АРТИКУЛ КОЛИЧЕСТВО В_КОРОБКЕ</code>")
            try:
                operation = self.workflow.edit_line(chat_id, parts[1], parts[2], int(parts[3]), int(parts[4]))
            except (ValueError, PermissionError) as exc:
                return HandlerResult(html_escape(exc))
            return HandlerResult(f"Черновик обновлён · {html_escape(operation.id)}", confirmation_keyboard(operation.id))
        if command == "/supply_remove":
            parts = stripped.split()
            if len(parts) != 3:
                return HandlerResult("Формат: <code>/supply_remove ID АРТИКУЛ</code>")
            try:
                operation = self.workflow.remove_line(chat_id, parts[1], parts[2])
            except (ValueError, PermissionError) as exc:
                return HandlerResult(html_escape(exc))
            return HandlerResult(f"Позиция удалена · {html_escape(operation.id)}", confirmation_keyboard(operation.id))
        if command == "/supply_cancel":
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                return HandlerResult(self.dialogs.cancel(chat_id).text)
            operation = self.workflow.cancel(chat_id, parts[1].strip())
            return HandlerResult(f"Поставка отменена · {html_escape(operation.id)}" if operation.state == OperationState.CANCELLED else f"Поставку уже нельзя отменить: {operation.state.value}")
        if command == "/supply_status":
            return self._status()
        if command == "/supply_history":
            return self._history(chat_id)
        if command == "/supply_metrics":
            metrics = self.operations.supply_metrics()
            return HandlerResult("<b>Метрики поставок</b>\n" + "\n".join(f"{html_escape(key)}: {value}" for key, value in sorted(metrics.items())))
        if command in {"/check_update", "/update"}:
            release = await self.updates.check()
            if not release:
                return HandlerResult(f"Установлена актуальная версия {html_escape(self.settings.current_version)}")
            return HandlerResult(f"<b>Доступно обновление</b>\nтекущая версия: {html_escape(self.settings.current_version)}\nновая версия: {html_escape(release.version)}\n\n{html_escape(release.notes)}", update_keyboard(release.version))
        return HandlerResult("Неизвестная команда. Используйте /help")

    async def callback(self, chat_id: int, data: str) -> HandlerResult | None:
        if not self.allowed(chat_id):
            return None
        if data == "supply:start":
            return HandlerResult(self.dialogs.start(chat_id).text)
        if data == "supply:suggest":
            items = [x for group in self.supply.purchase_groups() for x in group]
            return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", recommendation_keyboard(sorted({x.cluster_id for x in items})) if items else supply_menu())
        if data == "supply:status":
            return self._status()
        if data == "supply:history":
            return self._history(chat_id)
        if data == "system:update":
            return await self.message(chat_id, "/update")
        if data == "menu:main":
            return HandlerResult("<b>Главное меню Ozon AI OS</b>\nВыберите действие.", supply_menu())
        if data == "inventory:clusters":
            return self._inventory_products(0)
        if data == "inventory:contracts":
            return await self._ozon_contracts()
        inventory_parts = data.split(":")
        if len(inventory_parts) == 3 and inventory_parts[:2] == ["inventory", "page"]:
            try:
                page = int(inventory_parts[2])
            except ValueError:
                return HandlerResult("Некорректная страница.", back_to_menu_keyboard())
            return self._inventory_products(page)
        if len(inventory_parts) == 4 and inventory_parts[:2] == ["inventory", "product"]:
            try:
                sku, page = int(inventory_parts[2]), int(inventory_parts[3])
            except ValueError:
                return HandlerResult("Некорректный товар.", back_to_menu_keyboard())
            return self._inventory_product(sku, page)
        parts = data.split(":", 2)
        if len(parts) == 3 and parts[:2] == ["supply", "recommend"]:
            try:
                cluster_id = int(parts[2])
            except ValueError:
                return HandlerResult("Некорректный кластер.")
            items = [x for group in self.supply.purchase_groups() for x in group if x.cluster_id == cluster_id]
            if not items:
                return HandlerResult("Рекомендация устарела. Обновите расчёт.")
            result = self.dialogs.start_recommended(chat_id, items[0].cluster_name, {x.offer_id: x.recommended_quantity for x in items})
            return HandlerResult(result.text)
        if len(parts) == 3 and parts[:2] == ["supply", "confirm"]:
            try:
                operation = await self.workflow.confirm(chat_id, parts[2])
                if operation.state != OperationState.SUPPLY_CREATED:
                    return HandlerResult(f"Поставка уже обработана: {operation.state.value} · {html_escape(operation.id)}")
                operation, pdf = await self.workflow.create_cargoes_and_labels_mockable(chat_id, operation.id)
            except TimeoutError:
                return HandlerResult("Ozon не завершил операцию вовремя. Поставка отмечена как failed; повторный запрос не отправлен.")
            except Exception as exc:
                return HandlerResult(f"Не удалось обработать поставку ({html_escape(type(exc).__name__)}). Детали внешнего ответа не сохранены.")
            return HandlerResult(
                ("🧪 Тестовая поставка завершена" if not self.settings.live_mode else "Поставка завершена") + f" · {html_escape(operation.id)}",
                document_name=f"ozon-cargo-labels-{operation.id}.pdf" if pdf else None,
                document=pdf,
                operation_id=operation.id,
            )
        if len(parts) == 3 and parts[:2] == ["supply", "cancel"]:
            operation = self.workflow.cancel(chat_id, parts[2])
            if operation.state == OperationState.CANCELLED:
                return HandlerResult(f"Поставка отменена · {html_escape(operation.id)}")
            return HandlerResult(f"Поставку уже нельзя отменить: {operation.state.value} · {html_escape(operation.id)}")
        if len(parts) == 3 and parts[:2] == ["update", "apply"]:
            release = await self.updates.check()
            if not release or release.version != parts[2]:
                return HandlerResult("Запрос обновления устарел. Выполните /update ещё раз.")
            self.update_writer.create(parts[2], chat_id)
            return HandlerResult(f"Обновление {html_escape(parts[2])} передано безопасному updater.")
        if len(parts) == 3 and parts[:2] == ["update", "details"]:
            release = await self.updates.check()
            if not release or release.version != parts[2]:
                return HandlerResult("Информация о релизе устарела. Выполните /check_update.")
            return HandlerResult(f"<b>{html_escape(release.version)}</b>\n{html_escape(release.notes)}\n{html_escape(release.url)}")
        if data == "update:later":
            return HandlerResult("Обновление отложено.")
        return HandlerResult("Действие устарело или не поддерживается.")

    def _status(self) -> HandlerResult:
        rows = self.operations.unfinished()
        return HandlerResult("<b>Активные поставки</b>\n" + ("\n".join(f"{html_escape(x.id)} · {self.STATE_LABELS[x.state]} · {html_escape(x.destination)}" for x in rows) or "Нет"), back_to_menu_keyboard())

    def _history(self, chat_id: int) -> HandlerResult:
        rows = self.operations.history(chat_id)
        return HandlerResult("<b>История поставок</b>\n" + ("\n".join(f"{html_escape(x.id)} · {self.STATE_LABELS[x.state]} · {html_escape(x.destination)}" for x in rows) or "История пуста"), back_to_menu_keyboard())

    def _inventory_report(self) -> HandlerResult:
        if not self.inventory:
            return HandlerResult("Сервис остатков не настроен.")
        rows = self.inventory.clusters()
        if not rows:
            return HandlerResult("Остатки ещё не синхронизированы. Используйте /stocks_sync.")
        lines = ["<b>FBO-остатки по кластерам</b>"]
        lines.extend(f"{html_escape(row.cluster_name)}: доступно {row.available}, резерв {row.reserved}, товаров {row.offers}" for row in rows)
        if self.inventory.stale():
            lines.append("\n⚠️ Данные устарели — выполните /stocks_sync.")
        return HandlerResult("\n".join(lines), back_to_menu_keyboard())

    def _inventory_products(self, page: int, page_size: int = 8) -> HandlerResult:
        if not self.inventory:
            return HandlerResult("Сервис остатков не настроен.", back_to_menu_keyboard())
        products = self.inventory.products()
        if not products:
            return HandlerResult("На складах нет синхронизированных товаров. Используйте /stocks_sync.", back_to_menu_keyboard())
        pages = (len(products) + page_size - 1) // page_size
        page = min(max(0, page), pages - 1)
        visible = products[page * page_size:(page + 1) * page_size]
        text = f"<b>Остатки по кластерам</b>\nВыберите товар · страница {page + 1}/{pages}"
        if self.inventory.stale():
            text += "\n\n⚠️ Данные устарели — выполните /stocks_sync."
        return HandlerResult(text, inventory_products_keyboard([(row.sku, row.offer_id) for row in visible], page, pages))

    def _inventory_product(self, sku: int, page: int) -> HandlerResult:
        if not self.inventory:
            return HandlerResult("Сервис остатков не настроен.", back_to_menu_keyboard())
        product = next((row for row in self.inventory.products() if row.sku == sku), None)
        if not product:
            return HandlerResult("Товар больше не найден в остатках.", inventory_product_keyboard(page))
        rows = self.inventory.product_clusters(sku)
        lines = [f"<b>{html_escape(product.offer_id)}</b>", f"Всего на складах: {product.available} шт.", ""]
        lines.extend(f"<b>{html_escape(row.cluster_name)}</b>: {row.available} шт. · продажи {row.daily_sales:.2f} шт./день" for row in rows)
        lines.append(f"\nСредние продажи всего: {sum(row.daily_sales for row in rows):.2f} шт./день")
        return HandlerResult("\n".join(lines), inventory_product_keyboard(page))

    async def _ozon_contracts(self) -> HandlerResult:
        if not self.ozon:
            return HandlerResult("Подключение к Ozon API не настроено.", back_to_menu_keyboard())
        document = await OzonContractProbe(self.ozon).capture()
        return HandlerResult(
            "Проверка завершена. Ответы API обезличены; ключи и реальные значения в файл не включены.",
            back_to_menu_keyboard(),
            document_name="ozon-contract-fixtures.json",
            document=document,
        )
