from __future__ import annotations

from collections import defaultdict
import math
import statistics

from app.storage.models import DemandSnapshot, StockSnapshot
from app.storage.repositories import SnapshotRepository
from app.supply.models import StockLevel, SupplyRecommendation


class SupplyManager:
    def __init__(self, repository: SnapshotRepository, critical_days: int = 7, minimum_days: int = 30, comfort_days: int = 45, group_size: int = 6, lead_days: int = 7) -> None:
        self.repository = repository
        self.critical_days = critical_days
        self.minimum_days = minimum_days
        self.comfort_days = comfort_days
        self.group_size = group_size
        self.lead_days = lead_days

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
            daily_samples = [row.units / row.period_days for row in demand_rows if row.period_days > 0]
            weights = [3 if row.period_days <= 7 else 2 if row.period_days <= 14 else 1 for row in demand_rows if row.period_days > 0]
            daily = sum(value * weight for value, weight in zip(daily_samples, weights)) / sum(weights) if weights else 0.0
            deviation = statistics.pstdev(daily_samples) if len(daily_samples) > 1 else 0.0
            safety_stock = math.ceil(1.65 * deviation * math.sqrt(max(1, self.lead_days)))
            trend = "growing" if len(daily_samples) > 1 and daily_samples[0] > daily_samples[-1] * 1.15 else "declining" if len(daily_samples) > 1 and daily_samples[0] < daily_samples[-1] * .85 else "stable"
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
            in_transit = 0  # Contract boundary: ожидаемые поставки требуют подтверждённого DTO Ozon.
            recommended = max(0, math.ceil(daily * max(self.comfort_days, self.lead_days) + safety_stock - available - in_transit))
            exemplar = stock_rows[0] if stock_rows else demand_rows[0]
            stock_text = "нет спроса" if days is None else f"запас на {days:.1f} дн."
            reason = f"{stock_text}; прогноз {daily:.2f} шт./день; срок поставки {self.lead_days} дн.; страховой запас {safety_stock} шт."
            result.append(SupplyRecommendation(key[0], exemplar.offer_id, key[1], getattr(exemplar, "cluster_name", str(key[1])), available, daily, days, recommended, level, safety_stock, in_transit, trend, reason))
        return result

    def purchase_groups(self) -> list[list[SupplyRecommendation]]:
        items = [item for item in self.recommendations() if item.recommended_quantity > 0]
        items.sort(key=lambda item: (item.level != StockLevel.CRITICAL, item.stock_days or 0))
        return [items[index:index + self.group_size] for index in range(0, len(items), self.group_size)]
