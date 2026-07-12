from __future__ import annotations

from typing import Any

import httpx


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.AsyncClient(timeout=40)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_me(self) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/getMe")
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", "Ошибка Telegram"))
        return data["result"]

    async def delete_webhook(self) -> None:
        response = await self.client.post(
            f"{self.base_url}/deleteWebhook",
            json={"drop_pending_updates": False},
        )
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", "Не удалось удалить webhook"))

    async def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": 30,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset

        response = await self.client.post(
            f"{self.base_url}/getUpdates",
            json=payload,
            timeout=40,
        )
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", "Ошибка getUpdates"))
        return data["result"]

    async def send_message(self, chat_id: int, text: str) -> None:
        response = await self.client.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", "Ошибка sendMessage"))
