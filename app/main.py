from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import httpx
import signal
import socket
import sys

from app.config import load_settings
from app.database import init_database, log_event
from app.ozon_client import OzonApiError, OzonClient
from app.telegram_client import TelegramClient, TelegramError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ozon-ai-os")


class OzonAiOs:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.telegram = TelegramClient(self.settings.telegram_bot_token)
        self.ozon = OzonClient(
            self.settings.ozon_client_id,
            self.settings.ozon_api_key,
        )
        self.running = True
        self.started_at = datetime.now()

    async def close(self) -> None:
        await self.telegram.close()
        await self.ozon.close()

    def stop(self) -> None:
        self.running = False

    def is_allowed_chat(self, chat_id: int) -> bool:
        return chat_id == self.settings.telegram_chat_id

    async def handle_command(self, chat_id: int, text: str) -> None:
        if not self.is_allowed_chat(chat_id):
            logger.warning("Отклонён запрос из чужого чата: %s", chat_id)
            return

        command = text.strip().split()[0].lower()
        if "@" in command:
            command = command.split("@", 1)[0]

        if command in {"/start", "/help"}:
            answer = (
                "<b>Ozon AI OS запущен ✅</b>\n\n"
                "Доступные команды:\n"
                "/status — статус системы\n"
                "/ozon_test — проверить подключение к Ozon\n"
                "/settings — правила Supply Manager"
            )
        elif command == "/status":
            uptime = datetime.now() - self.started_at
            answer = (
                "<b>Статус Ozon AI OS</b>\n\n"
                f"Сервер: <code>{socket.gethostname()}</code>\n"
                f"Работает: {str(uptime).split('.')[0]}\n"
                f"Безопасный режим: {'нет' if self.settings.live_mode else 'да'}\n"
                "Supply Manager: подготовлен\n"
                "Изменения в Ozon: запрещены"
            )
        elif command == "/settings":
            answer = (
                "<b>Правила AI Supply Manager</b>\n\n"
                f"Поставщик: {self.settings.supplier_name}\n"
                f"Срок поставки: {self.settings.supply_lead_days} дней\n"
                f"Критический запас: {self.settings.critical_stock_days} дней\n"
                f"Минимальный запас: {self.settings.min_stock_days} дней\n"
                f"Комфортный запас: {self.settings.comfort_stock_days} дней\n"
                f"Размер объединённой закупки: около "
                f"{self.settings.purchase_group_size} товаров"
            )
        elif command == "/ozon_test":
            await self.telegram.send_message(
                chat_id,
                "Проверяю подключение к Ozon Seller API…",
            )
            try:
                result = await self.ozon.test_connection()
                answer = (
                    "<b>Ozon подключён ✅</b>\n\n"
                    f"Получено товаров в тестовом запросе: "
                    f"{result['items_received']}\n"
                    f"Всего товаров по ответу API: {result['total']}"
                )
                log_event("ozon_test_success", str(result))
            except OzonApiError as exc:
                answer = (
                    "<b>Ошибка подключения к Ozon ❌</b>\n\n"
                    f"<code>{str(exc)}</code>"
                )
                log_event("ozon_test_error", str(exc))
        else:
            answer = (
                "Команда пока не распознана.\n"
                "Используй /start, чтобы увидеть список команд."
            )

        await self.telegram.send_message(chat_id, answer)

    async def run(self) -> None:
        init_database()
        bot = await self.telegram.get_me()
        logger.info("Бот подключён: @%s", bot.get("username"))
        log_event("service_started", f"@{bot.get('username')}")

        # Long polling и webhook взаимоисключающие, поэтому очищаем старый webhook.
        await self.telegram.delete_webhook()

        await self.telegram.send_message(
            self.settings.telegram_chat_id,
            "<b>Ozon AI OS запущен на сервере ✅</b>\n"
            "Отправь /status для проверки.",
        )

        offset: int | None = None
        while self.running:
            try:
                updates = await self.telegram.get_updates(offset)
                for update in updates:
                    offset = int(update["update_id"]) + 1
                    message = update.get("message") or {}
                    chat = message.get("chat") or {}
                    text = message.get("text")
                    chat_id = chat.get("id")
                    if isinstance(chat_id, int) and isinstance(text, str):
                        await self.handle_command(chat_id, text)
            except (TelegramError, httpx.HTTPError) as exc:
                logger.exception("Ошибка Telegram: %s", exc)
                log_event("telegram_error", str(exc))
                await asyncio.sleep(5)
            except Exception as exc:
                logger.exception("Непредвиденная ошибка: %s", exc)
                log_event("unexpected_error", repr(exc))
                await asyncio.sleep(5)


async def async_main() -> None:
    app = OzonAiOs()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, app.stop)

    try:
        await app.run()
    finally:
        await app.close()


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
