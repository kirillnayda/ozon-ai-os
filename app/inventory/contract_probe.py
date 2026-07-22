from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from app.ozon.read_api import OzonReadApi


def sanitize_contract(value: Any) -> Any:
    """Keep the response shape and types without retaining seller data."""
    if isinstance(value, dict):
        return {str(key): sanitize_contract(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_contract(item) for item in value[:3]]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return 1
    if isinstance(value, float):
        return 1.5
    if isinstance(value, str):
        return "sample"
    return value


class OzonContractProbe:
    def __init__(self, api: OzonReadApi) -> None:
        self.api = api

    async def capture(self) -> bytes:
        fixtures: dict[str, dict[str, Any]] = {}
        products = await self._capture(fixtures, "products", self.api.products)
        skus = self._product_skus(products)[:100]
        requests: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = {
            "clusters": self.api.clusters,
            "warehouses": self.api.warehouses,
        }
        for name, request in requests.items():
            await self._capture(fixtures, name, request)
        if skus:
            await self._capture(fixtures, "fbo_stocks", lambda: self.api.fbo_stocks(skus))
            await self._capture(fixtures, "analytics_stocks", lambda: self.api.analytics_stocks(skus))
        else:
            fixtures["fbo_stocks"] = {"status": "skipped", "reason": "products_without_sku"}
            fixtures["analytics_stocks"] = {"status": "skipped", "reason": "products_without_sku"}
        return json.dumps(fixtures, ensure_ascii=False, indent=2).encode("utf-8")

    async def _capture(self, fixtures: dict[str, dict[str, Any]], name: str, request: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any] | None:
        try:
            response = await request()
            fixtures[name] = {"status": "success", "response": sanitize_contract(response)}
            return response
        except Exception as exc:
            fixtures[name] = {"status": "error", "error_type": type(exc).__name__}
            status_code = getattr(exc, "status_code", None)
            if isinstance(status_code, int):
                fixtures[name]["http_status"] = status_code
            metadata = getattr(exc, "metadata", None)
            if isinstance(metadata, dict):
                fixtures[name].update(metadata)
            return None

    @staticmethod
    def _product_skus(response: dict[str, Any] | None) -> list[int]:
        result = response.get("result") if isinstance(response, dict) else None
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            return []
        return [item["sku"] for item in items if isinstance(item, dict) and isinstance(item.get("sku"), int) and item["sku"] > 0]
