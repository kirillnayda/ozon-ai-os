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
        requests: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = {
            "clusters": self.api.clusters,
            "warehouses": self.api.warehouses,
            "fbo_stocks": self.api.fbo_stocks,
            "analytics_stocks": self.api.analytics_stocks,
        }
        fixtures: dict[str, dict[str, Any]] = {}
        for name, request in requests.items():
            try:
                fixtures[name] = {"status": "success", "response": sanitize_contract(await request())}
            except Exception as exc:
                fixtures[name] = {"status": "error", "error_type": type(exc).__name__}
                status_code = getattr(exc, "status_code", None)
                if isinstance(status_code, int):
                    fixtures[name]["http_status"] = status_code
                metadata = getattr(exc, "metadata", None)
                if isinstance(metadata, dict):
                    fixtures[name].update(metadata)
        return json.dumps(fixtures, ensure_ascii=False, indent=2).encode("utf-8")
