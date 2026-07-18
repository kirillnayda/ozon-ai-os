from __future__ import annotations

import asyncio
import sys

from app.config import load_settings
from app.core.security import html_escape
from app.telegram.client import TelegramClient


async def _notify(chat_id: int, message: str) -> None:
    settings = load_settings()
    if chat_id != settings.telegram_chat_id:
        raise PermissionError("Telegram chat is not allowed")
    client = TelegramClient(settings.telegram_bot_token)
    try:
        await client.send_message(chat_id, html_escape(message))
    finally:
        await client.close()


def main() -> int:
    if len(sys.argv) != 3:
        return 64
    asyncio.run(_notify(int(sys.argv[1]), sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
