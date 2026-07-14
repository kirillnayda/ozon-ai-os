from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.core.errors import ContractNotVerified
from app.storage.models import DemandSnapshot, StockSnapshot


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
