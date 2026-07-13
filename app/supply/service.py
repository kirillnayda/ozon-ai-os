from __future__ import annotations

from collections import defaultdict
import math

from app.storage.models import DemandSnapshot, StockSnapshot
from app.storage.repositories import SnapshotRepository
from app.supply.models import StockLevel, SupplyRecommendation


class SupplyManager:
    def __init__(self, repository: SnapshotRepository, critical_days: int = 7, minimum_days: int = 30, comfort_days: int = 45, group_size: int = 6) -> None:
        self.repository = repository
        self.critical_days = critical_days
        self.minimum_days = minimum_days
        self.comfort_days = comfort_days
        self.group_size = group_size

    def recommendations(self) -> list[SupplyRecommendation]:
        stocks: dict[tuple[int, int], list[StockSnapshot]] = defaultdict(list)
        demand: dict[tuple[int, int], list[DemandSnapshot]] = defaultdict(list)
        for item in self.repository.latest_stocks():
            stocks[(item.sku, item.cluster_id)].append(item)
        for item in self.repository.latest_demand():
            demand[(item.sku, item.cluster_id)].append(item)

        result: list[SupplyRecommendation] = []
        for key in sorted(set(stocks) | set(demand)):
            stock_rows, demand_rows = stocks[key], demand[key]
            available = sum(max(0, row.present - row.reserved) for row in stock_rows)
            total_units = sum(row.units for row in demand_rows)
            total_days = max((row.period_days for row in demand_rows), default=0)
            daily = total_units / total_days if total_days else 0.0
            days = available / daily if daily else None
            if daily == 0:
                level = StockLevel.NO_DEMAND
            elif days is not None and days <= self.critical_days:
                level = StockLevel.CRITICAL
            elif days is not None and days < self.minimum_days:
                level = StockLevel.LOW
            elif days is not None and days <= self.comfort_days:
                level = StockLevel.COMFORT
            else:
                level = StockLevel.EXCESS
            recommended = max(0, math.ceil(daily * self.comfort_days - available))
            exemplar = stock_rows[0] if stock_rows else demand_rows[0]
            result.append(SupplyRecommendation(key[0], exemplar.offer_id, key[1], getattr(exemplar, "cluster_name", str(key[1])), available, daily, days, recommended, level))
        return result

    def purchase_groups(self) -> list[list[SupplyRecommendation]]:
        items = [item for item in self.recommendations() if item.recommended_quantity > 0]
        items.sort(key=lambda item: (item.level != StockLevel.CRITICAL, item.stock_days or 0))
        return [items[index:index + self.group_size] for index in range(0, len(items), self.group_size)]

