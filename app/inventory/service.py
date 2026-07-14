from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.inventory.gateway import InventoryGateway
from app.storage.repositories import AuditRepository, SnapshotRepository


@dataclass(frozen=True)
class ClusterInventory:
    cluster_id: int
    cluster_name: str
    offers: int
    present: int
    reserved: int
    available: int


class InventoryService:
    def __init__(self, gateway: InventoryGateway, snapshots: SnapshotRepository, audit: AuditRepository) -> None:
        self.gateway, self.snapshots, self.audit = gateway, snapshots, audit
        self.last_sync_at: datetime | None = None
        self.last_error: str | None = None

    async def sync(self, actor: str = "scheduler") -> tuple[int, int]:
        try:
            stocks = await self.gateway.stock_snapshots()
            demand = await self.gateway.demand_snapshots()
        except Exception as exc:
            self.last_error = type(exc).__name__
            self.audit.record(actor, "inventory.sync", "failed", self.last_error)
            raise
        self.snapshots.replace_stocks(stocks)
        self.snapshots.replace_demand(demand)
        self.last_sync_at = datetime.now(timezone.utc)
        self.last_error = None
        self.audit.record(actor, "inventory.sync", "completed", f"stocks={len(stocks)} demand={len(demand)}")
        return len(stocks), len(demand)

    def clusters(self) -> list[ClusterInventory]:
        grouped: dict[tuple[int, str], dict[str, int | set[str]]] = {}
        for row in self.snapshots.latest_stocks():
            item = grouped.setdefault((row.cluster_id, row.cluster_name), {"offers": set(), "present": 0, "reserved": 0})
            item["offers"].add(row.offer_id)  # type: ignore[union-attr]
            item["present"] += row.present  # type: ignore[operator]
            item["reserved"] += row.reserved  # type: ignore[operator]
        return [ClusterInventory(cluster_id, name, len(values["offers"]), int(values["present"]), int(values["reserved"]), max(0, int(values["present"]) - int(values["reserved"]))) for (cluster_id, name), values in sorted(grouped.items())]

    def stale(self, max_age_seconds: int = 3600) -> bool:
        stocks = self.snapshots.latest_stocks()
        if not stocks:
            return True
        newest = max(row.captured_at for row in stocks)
        return (datetime.now(timezone.utc) - newest).total_seconds() > max_age_seconds
