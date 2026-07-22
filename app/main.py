from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import signal
import sys

from app.config import load_settings
from app.core.logging import configure_logging
from app.core.scheduler import Scheduler
from app.core.security import WritePolicy
from app.database import DB_PATH
from app.developer_agent.report_builder import build_task_report
from app.developer_agent.task_repository import SQLiteDeveloperTaskRepository
from app.developer_agent.telegram_handlers import DeveloperAgentTelegramHandlers, task_keyboard
from app.inventory.gateway import OzonAnalyticsInventoryGateway
from app.inventory.service import InventoryService
from app.ozon.read_api import OzonReadApi
from app.ozon.transport import OzonHttpTransport, SupplyTestTransport
from app.storage.sqlite import SQLiteStorage
from app.supply.service import SupplyManager
from app.supplies.service import SupplyWorkflow
from app.supplies.dialog import SnapshotProductCatalog, SupplyDialogService
from app.supplies.contracts import MockSupplyPlanningGateway, UnverifiedOzonSupplyPlanningGateway
from app.telegram.client import TelegramClient
from app.telegram.handlers import CommandHandlers
from app.updater.checker import GitHubReleaseChecker
from app.updater.request import UpdateRequestWriter
from app.updater.startup_notify import StartupUpdateNotifier

logger = logging.getLogger("ozon-ai-os")


class Application:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.storage = SQLiteStorage(DB_PATH)
        self.telegram = TelegramClient(self.settings.telegram_bot_token)
        self.transport = OzonHttpTransport(self.settings.ozon_client_id, self.settings.ozon_api_key)
        self.supply_transport = self.transport if self.settings.live_mode else SupplyTestTransport()
        self.ozon = OzonReadApi(self.transport)
        supply = SupplyManager(self.storage, self.settings.critical_stock_days, self.settings.min_stock_days, self.settings.comfort_stock_days, self.settings.purchase_group_size, self.settings.supply_lead_days)
        workflow = SupplyWorkflow(self.supply_transport, self.storage, self.storage, WritePolicy(self.settings.live_mode, self.settings.telegram_chat_id), test_mode=not self.settings.live_mode)
        catalog = SnapshotProductCatalog(self.storage, ("TEST-SKU",) if not self.settings.live_mode else ())
        planning = UnverifiedOzonSupplyPlanningGateway() if self.settings.live_mode else MockSupplyPlanningGateway()
        dialogs = SupplyDialogService(self.storage, catalog, workflow, test_mode=not self.settings.live_mode, planning=planning)
        inventory_gateway = OzonAnalyticsInventoryGateway(self.ozon)
        self.inventory = InventoryService(inventory_gateway, self.storage, self.storage)
        self.handlers = CommandHandlers(self.settings, self.ozon, supply, workflow, dialogs, self.storage, GitHubReleaseChecker(self.settings.github_repository, self.settings.current_version, self.settings.github_token), UpdateRequestWriter(), self.inventory)
        configured_developer_db = Path(os.getenv("DEVELOPER_AGENT_DB_PATH", str(DB_PATH.with_name("developer_tasks.sqlite3"))))
        developer_db = configured_developer_db if configured_developer_db.parent.exists() else DB_PATH.with_name("developer_tasks.sqlite3")
        self.developer_repository = SQLiteDeveloperTaskRepository(developer_db)
        self.developer_handlers = DeveloperAgentTelegramHandlers(self.developer_repository, self.settings.telegram_chat_id, int(os.getenv("DEVELOPER_AGENT_MAX_ATTEMPTS", "2")))
        self.startup_notifier = StartupUpdateNotifier(self.telegram, self.settings.telegram_chat_id, self.settings.current_version, DB_PATH.with_name("update-notified-version"))
        self.workflow = workflow
        self.scheduler = Scheduler()
        self.running = True

    def stop(self) -> None:
        self.running = False

    async def run(self) -> None:
        self.storage.migrate()
        bot = await self.telegram.get_me()
        logger.info("Telegram bot connected: %s", bot.get("username"))
        await self.telegram.delete_webhook()
        self.scheduler.every(60, self._notify_started_version, "update-startup-notification")
        self.scheduler.every(300, self._recover_supply_operations, "ozon-operations")
        self.scheduler.every(60, self._deliver_pdf_outbox, "supply-pdf-outbox")
        self.scheduler.every(900, self.inventory.sync, "inventory-sync")
        self.scheduler.every(self.settings.update_check_minutes * 60, self._background_update_check, "updates")
        self.scheduler.every(5, self._developer_reports, "developer-reports")
        self.scheduler.daily(self.settings.report_hour, self.settings.timezone, self._morning_report, "morning-report")
        offset: int | None = None
        while self.running:
            try:
                for update in await self.telegram.get_updates(offset):
                    offset = int(update["update_id"]) + 1
                    await self._dispatch(update)
            except Exception:
                logger.exception("Polling iteration failed")
                await asyncio.sleep(5)

    async def _dispatch(self, update: dict) -> None:
        if callback := update.get("callback_query"):
            message = callback.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            if isinstance(chat_id, int):
                callback_data = str(callback.get("data") or "")
                developer_result = await self.developer_handlers.callback(chat_id, callback_data)
                if developer_result:
                    await self.telegram.answer_callback(str(callback.get("id")), "Принято")
                    await self.telegram.send_message(chat_id, developer_result.text, developer_result.keyboard)
                    return
                result = await self.handlers.callback(chat_id, callback_data)
                await self.telegram.answer_callback(str(callback.get("id")), "Принято")
                if result:
                    await self.telegram.send_message(chat_id, result.text, result.keyboard)
                    if result.document and result.document_name:
                        await self.telegram.send_document(chat_id, result.document_name, result.document)
                        if result.operation_id:
                            self.storage.mark_operation_pdf_delivered(result.operation_id)
            return
        message = update.get("message") or {}
        chat_id, text = (message.get("chat") or {}).get("id"), message.get("text")
        if isinstance(chat_id, int) and isinstance(text, str):
            developer_result = await self.developer_handlers.message(chat_id, text)
            if developer_result:
                await self.telegram.send_message(chat_id, developer_result.text, developer_result.keyboard)
                return
            result = await self.handlers.message(chat_id, text)
            if result:
                await self.telegram.send_message(chat_id, result.text, result.keyboard)
                if result.document and result.document_name:
                    await self.telegram.send_document(chat_id, result.document_name, result.document)
                    if result.operation_id:
                        self.storage.mark_operation_pdf_delivered(result.operation_id)

    async def _background_update_check(self) -> None:
        release = await self.handlers.updates.check()
        if release:
            result = await self.handlers.message(self.settings.telegram_chat_id, "/check_update")
            if result:
                await self.telegram.send_message(self.settings.telegram_chat_id, result.text, result.keyboard)

    async def _notify_started_version(self) -> None:
        try:
            await self.startup_notifier.notify_once()
        except Exception as exc:
            logger.warning("Update startup notification failed: %s", type(exc).__name__)

    async def _recover_supply_operations(self) -> None:
        for chat_id, operation_id, pdf in await self.workflow.poll_unfinished():
            await self.telegram.send_message(chat_id, f"Поставка восстановлена после перезапуска и завершена · <code>{operation_id}</code>")
            await self.telegram.send_document(chat_id, f"ozon-cargo-labels-{operation_id}.pdf", pdf)
            self.storage.mark_operation_pdf_delivered(operation_id)

    async def _deliver_pdf_outbox(self) -> None:
        for item in self.storage.pending_pdfs():
            path = Path(item.path)
            if not path.is_file():
                continue
            await self.telegram.send_document(item.chat_id, f"ozon-cargo-labels-{item.operation_id}.pdf", path.read_bytes())
            self.storage.mark_pdf_delivered(item.id)

    async def _morning_report(self) -> None:
        result = await self.handlers.message(self.settings.telegram_chat_id, "/supply_report")
        if result:
            await self.telegram.send_message(self.settings.telegram_chat_id, result.text, result.keyboard)

    async def _developer_reports(self) -> None:
        for task in self.developer_repository.pending_reports():
            keyboard = task_keyboard(task.id) if task.state.value == "ready" and not task.pushed else None
            await self.telegram.send_message(task.chat_id, build_task_report(task), keyboard)
            self.developer_repository.update(task.id, report_sent=True)

    async def close(self) -> None:
        await self.scheduler.close()
        await self.telegram.close()
        await self.transport.close()
        if self.supply_transport is not self.transport:
            await self.supply_transport.close()


async def async_main() -> None:
    app = Application()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, app.stop)
    try:
        await app.run()
    finally:
        await app.close()


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(async_main())
    except RuntimeError as exc:
        logger.error("Startup failed: %s", exc)
        sys.exit(1)
