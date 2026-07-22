from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.core.errors import ContractNotVerified
from app.storage.models import DemandSnapshot, StockSnapshot
from app.ozon.read_api import OzonReadApi


class InventoryGateway(Protocol):
    async def stock_snapshots(self) -> list[StockSnapshot]: ...
    async def demand_snapshots(self) -> list[DemandSnapshot]: ...


class MockInventoryGateway:
    async def stock_snapshots(self) -> list[StockSnapshot]:
        now = datetime.now(timezone.utc)
        return [
            StockSnapshot(now, 1001, "TEST-SKU", 1, "Москва", 0, "Назначается Ozon", 18, 2),
            StockSnapshot(now, 1002, "TEST-SKU-2", 2, "Санкт-Петербург", 0, "Назначается Ozon", 40, 5),
        ]

    async def demand_snapshots(self) -> list[DemandSnapshot]:
        now = datetime.now(timezone.utc)
        return [DemandSnapshot(now, 1001, "TEST-SKU", 1, 84, 14), DemandSnapshot(now, 1002, "TEST-SKU-2", 2, 30, 30)]


class UnverifiedOzonInventoryGateway:
    """Production boundary pending official response fixtures from the seller cabinet."""

    async def stock_snapshots(self) -> list[StockSnapshot]:
        raise ContractNotVerified("DTO FBO-остатков требует contract fixture из кабинета Ozon")

    async def demand_snapshots(self) -> list[DemandSnapshot]:
        raise ContractNotVerified("DTO кластерного спроса требует contract fixture из кабинета Ozon")


class OzonAnalyticsInventoryGateway:
    """Read-only adapter verified against a sanitized cabinet fixture on 2026-07-22."""

    DEMAND_PRECISION = 1000

    def __init__(self, api: OzonReadApi) -> None:
        self.api = api
        self._stocks: list[StockSnapshot] | None = None
        self._demand: list[DemandSnapshot] | None = None

    async def stock_snapshots(self) -> list[StockSnapshot]:
        await self._load()
        return list(self._stocks or [])

    async def demand_snapshots(self) -> list[DemandSnapshot]:
        await self._load()
        demand = list(self._demand or [])
        self._stocks = None
        self._demand = None
        return demand

    async def _load(self) -> None:
        if self._stocks is not None and self._demand is not None:
            return
        skus = await self._product_skus()
        now = datetime.now(timezone.utc)
        stocks: list[StockSnapshot] = []
        demand_by_cluster: dict[tuple[int, int], DemandSnapshot] = {}
        for start in range(0, len(skus), 100):
            response = await self.api.analytics_stocks(skus[start:start + 100])
            items = response.get("items")
            if not isinstance(items, list):
                raise ContractNotVerified("В /v1/analytics/stocks отсутствует массив items")
            for item in items:
                stock, demand = self._parse_item(item, now)
                stocks.append(stock)
                demand_by_cluster[(demand.sku, demand.cluster_id)] = demand
        self._stocks = stocks
        self._demand = list(demand_by_cluster.values())

    async def _product_skus(self) -> list[int]:
        result: list[int] = []
        last_id = ""
        while True:
            response = await self.api.products(limit=100, last_id=last_id)
            body = response.get("result")
            items = body.get("items") if isinstance(body, dict) else None
            if not isinstance(items, list):
                raise ContractNotVerified("В /v3/product/list отсутствует result.items")
            for item in items:
                if isinstance(item, dict) and item.get("has_fbo_stocks") is True and isinstance(item.get("sku"), int) and item["sku"] > 0:
                    result.append(item["sku"])
            next_id = body.get("last_id") if isinstance(body, dict) else None
            if not items or not isinstance(next_id, str) or not next_id or next_id == last_id:
                break
            last_id = next_id
        return list(dict.fromkeys(result))

    def _parse_item(self, item: object, captured_at: datetime) -> tuple[StockSnapshot, DemandSnapshot]:
        if not isinstance(item, dict):
            raise ContractNotVerified("Элемент /v1/analytics/stocks должен быть объектом")
        required = ("sku", "offer_id", "warehouse_id", "warehouse_name", "cluster_id", "cluster_name", "available_stock_count", "ads_cluster")
        if any(key not in item for key in required):
            raise ContractNotVerified("Неполный DTO /v1/analytics/stocks")
        sku = self._integer(item, "sku")
        offer_id = self._text(item, "offer_id")
        warehouse_id = self._integer(item, "warehouse_id")
        warehouse_name = self._text(item, "warehouse_name")
        cluster_id = self._integer(item, "cluster_id")
        cluster_name = self._text(item, "cluster_name")
        available = max(0, self._integer(item, "available_stock_count"))
        daily = self._nullable_number(item, "ads_cluster")
        stock = StockSnapshot(captured_at, sku, offer_id, cluster_id, cluster_name, warehouse_id, warehouse_name, available, 0)
        demand = DemandSnapshot(captured_at, sku, offer_id, cluster_id, round(daily * self.DEMAND_PRECISION), self.DEMAND_PRECISION)
        return stock, demand

    @staticmethod
    def _integer(item: dict, field: str) -> int:
        value = item[field]
        if isinstance(value, bool):
            raise ContractNotVerified(f"Некорректный тип поля {field} в /v1/analytics/stocks")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ContractNotVerified(f"Некорректный тип поля {field} в /v1/analytics/stocks") from exc

    @staticmethod
    def _text(item: dict, field: str) -> str:
        value = item[field]
        if not isinstance(value, str):
            raise ContractNotVerified(f"Некорректный тип поля {field} в /v1/analytics/stocks")
        return value

    @staticmethod
    def _nullable_number(item: dict, field: str) -> float:
        value = item[field]
        if value is None:
            return 0.0
        if isinstance(value, bool):
            raise ContractNotVerified(f"Некорректный тип поля {field} в /v1/analytics/stocks")
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError) as exc:
            raise ContractNotVerified(f"Некорректный тип поля {field} в /v1/analytics/stocks") from exc
