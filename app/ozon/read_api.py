from __future__ import annotations

from typing import Any

from app.ozon import endpoints
from app.ozon.transport import JsonTransport


class OzonReadApi:
    def __init__(self, transport: JsonTransport) -> None:
        self.transport = transport

    async def test_connection(self) -> dict[str, Any]:
        data = await self.transport.request(endpoints.PRODUCT_LIST, {"filter": {"visibility": "ALL"}, "last_id": "", "limit": 1})
        result = data.get("result") or {}
        return {"connected": True, "items_received": len(result.get("items") or []), "total": result.get("total")}

    async def clusters(self) -> dict[str, Any]:
        return await self.transport.request(endpoints.CLUSTERS, {})

    async def warehouses(self) -> dict[str, Any]:
        return await self.transport.request(endpoints.FBO_WAREHOUSES, {})

    async def fbo_stocks(self, skus: list[int] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if skus:
            payload["skus"] = skus
        return await self.transport.request(endpoints.FBO_STOCKS, payload)

    async def analytics_stocks(self, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
        return await self.transport.request(endpoints.ANALYTICS_STOCKS, {"limit": limit, "offset": offset})

