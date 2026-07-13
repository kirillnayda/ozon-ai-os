from __future__ import annotations

from typing import Any
import httpx

from app.core.errors import ExternalServiceError


class TelegramClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10))

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(f"{self._base_url}/{method}", json=payload)
        except httpx.RequestError:
            raise ExternalServiceError("Telegram API недоступен") from None
        try:
            data = response.json()
        except ValueError as exc:
            raise ExternalServiceError("Telegram вернул некорректный ответ") from exc
        if response.status_code >= 400 or not data.get("ok"):
            raise ExternalServiceError(f"Ошибка Telegram HTTP {response.status_code}")
        return data["result"]

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe", {})

    async def delete_webhook(self) -> None:
        await self._call("deleteWebhook", {"drop_pending_updates": False})

    async def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        return await self._call("getUpdates", payload)

    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await self._call("sendMessage", payload)

    async def send_document(self, chat_id: int, filename: str, content: bytes) -> None:
        try:
            response = await self._client.post(f"{self._base_url}/sendDocument", data={"chat_id": str(chat_id)}, files={"document": (filename, content, "application/pdf")})
        except httpx.RequestError:
            raise ExternalServiceError("Telegram API недоступен") from None
        if response.status_code >= 400:
            raise ExternalServiceError(f"Ошибка Telegram HTTP {response.status_code}")

    async def answer_callback(self, callback_id: str, text: str = "") -> None:
        await self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    async def close(self) -> None:
        await self._client.aclose()
