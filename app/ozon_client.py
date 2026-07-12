from __future__ import annotations

from typing import Any

import httpx


class OzonApiError(RuntimeError):
    pass


class OzonClient:
    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, client_id: str, api_key: str) -> None:
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Client-Id": client_id,
                "Api-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=40,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def test_connection(self) -> dict[str, Any]:
        # Метод используется только для безопасной проверки ключей и чтения 1 товара.
        response = await self.client.post(
            "/v3/product/list",
            json={
                "filter": {"visibility": "ALL"},
                "last_id": "",
                "limit": 1,
            },
        )

        if response.status_code >= 400:
            body = response.text[:1000]
            raise OzonApiError(
                f"Ozon API вернул HTTP {response.status_code}: {body}"
            )

        data = response.json()
        result = data.get("result") or {}
        items = result.get("items") or []
        return {
            "connected": True,
            "items_received": len(items),
            "total": result.get("total"),
        }
