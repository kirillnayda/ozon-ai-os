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
from app.ozon.read_api import OzonReadApi
from app.ozon.transport import OzonHttpTransport
from app.storage.sqlite import SQLiteStorage
from app.supply.service import SupplyManager
from app.supplies.service import SupplyWorkflow
from app.telegram.client import TelegramClient
from app.telegram.handlers import CommandHandlers
from app.updater.checker import GitHubReleaseChecker
from app.updater.request import UpdateRequestWriter

logger = logging.getLogger("ozon-ai-os")


class Application:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.storage = SQLiteStorage(DB_PATH)
        self.telegram = TelegramClient(self.settings.telegram_bot_token)
        self.transport = OzonHttpTransport(self.settings.ozon_client_id, self.settings.ozon_api_key)
        self.ozon = OzonReadApi(self.transport)
        supply = SupplyManager(self.storage, self.settings.critical_stock_days, self.settings.min_stock_days, self.settings.comfort_stock_days, self.settings.purchase_group_size)
        workflow = SupplyWorkflow(self.transport, self.storage, self.storage, WritePolicy(self.settings.live_mode, self.settings.telegram_chat_id))
        self.handlers = CommandHandlers(self.settings, self.ozon, supply, workflow, self.storage, GitHubReleaseChecker(self.settings.github_repository, self.settings.current_version), UpdateRequestWriter())
        configured_developer_db = Path(os.getenv("DEVELOPER_AGENT_DB_PATH", str(DB_PATH.with_name("developer_tasks.sqlite3"))))
        developer_db = configured_developer_db if configured_developer_db.parent.exists() else DB_PATH.with_name("developer_tasks.sqlite3")
        self.developer_repository = SQLiteDeveloperTaskRepository(developer_db)
        self.developer_handlers = DeveloperAgentTelegramHandlers(self.developer_repository, self.settings.telegram_chat_id, int(os.getenv("DEVELOPER_AGENT_MAX_ATTEMPTS", "2")))
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
        self.scheduler.every(300, self.workflow.poll_unfinished, "ozon-operations")
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

    async def _background_update_check(self) -> None:
        release = await self.handlers.updates.check()
        if release:
            result = await self.handlers.message(self.settings.telegram_chat_id, "/check_update")
            if result:
                await self.telegram.send_message(self.settings.telegram_chat_id, result.text, result.keyboard)

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
