from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import socket

from app.config import Settings
from app.core.security import html_escape
from app.ozon.read_api import OzonReadApi
from app.storage.models import OperationState
from app.storage.repositories import OperationRepository
from app.supply.report import render_report
from app.supply.service import SupplyManager
from app.supplies.parser import parse_supply_intent
from app.supplies.dialog import SupplyDialogService
from app.supplies.service import SupplyWorkflow
from app.telegram.keyboards import confirmation_keyboard, supply_menu, update_keyboard
from app.updater.checker import GitHubReleaseChecker
from app.updater.request import UpdateRequestWriter


@dataclass
class HandlerResult:
    text: str
    keyboard: dict | None = None
    document_name: str | None = None
    document: bytes | None = None


class CommandHandlers:
    def __init__(self, settings: Settings, ozon: OzonReadApi, supply: SupplyManager, workflow: SupplyWorkflow, dialogs: SupplyDialogService, operations: OperationRepository, updates: GitHubReleaseChecker, update_writer: UpdateRequestWriter) -> None:
        self.settings, self.ozon, self.supply, self.workflow = settings, ozon, supply, workflow
        self.dialogs, self.operations, self.updates, self.update_writer = dialogs, operations, updates, update_writer
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
                return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", supply_menu())
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
            return HandlerResult("<b>Ozon AI OS 1.0</b>\n/status /supplies /supply_status /supply_cancel /supply_test /supply_suggest /supply_report /critical_stock /purchase_plan /clusters /check_update /settings /ozon_test\n\nМожно написать: «Создать поставку» или «Предложи поставку».\n\nDeveloper Agent: /dev /dev_status /dev_queue /dev_plan /dev_cancel", supply_menu())
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
        if command == "/supplies":
            return HandlerResult("<b>Менеджер FBO-поставок</b>\nВыберите действие.", supply_menu())
        if command == "/supply_test":
            if self.settings.live_mode:
                return HandlerResult("Команда /supply_test доступна только при LIVE_MODE=false.")
            return HandlerResult(self.dialogs.start(chat_id).text)
        if command == "/supply_suggest":
            items = [x for group in self.supply.purchase_groups() for x in group]
            return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", supply_menu())
        if command == "/supply_cancel":
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                return HandlerResult(self.dialogs.cancel(chat_id).text)
            operation = self.workflow.cancel(chat_id, parts[1].strip())
            return HandlerResult(f"Поставка отменена · {html_escape(operation.id)}" if operation.state == OperationState.CANCELLED else f"Поставку уже нельзя отменить: {operation.state.value}")
        if command == "/supply_status":
            rows = self.operations.unfinished()
            return HandlerResult("<b>Незавершённые поставки</b>\n" + ("\n".join(f"{html_escape(x.id)} · {x.state.value} · {html_escape(x.destination)}" for x in rows) or "Нет"))
        if command == "/check_update":
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
            return HandlerResult(render_report(items) if items else "Недостаточно данных о продажах и остатках для рекомендации.", supply_menu())
        if data == "supply:status":
            rows = self.operations.unfinished()
            return HandlerResult("<b>Незавершённые поставки</b>\n" + ("\n".join(f"{html_escape(x.id)} · {x.state.value} · {html_escape(x.destination)}" for x in rows) or "Нет"))
        parts = data.split(":", 2)
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
            )
        if len(parts) == 3 and parts[:2] == ["supply", "cancel"]:
            operation = self.workflow.cancel(chat_id, parts[2])
            if operation.state == OperationState.CANCELLED:
                return HandlerResult(f"Поставка отменена · {html_escape(operation.id)}")
            return HandlerResult(f"Поставку уже нельзя отменить: {operation.state.value} · {html_escape(operation.id)}")
        if len(parts) == 3 and parts[:2] == ["update", "apply"]:
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
