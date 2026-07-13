from dataclasses import dataclass
from enum import StrEnum


class StockLevel(StrEnum):
    NO_DEMAND = "no_demand"
    CRITICAL = "critical"
    LOW = "low"
    COMFORT = "comfort"
    EXCESS = "excess"


@dataclass(frozen=True)
class SupplyRecommendation:
    sku: int
    offer_id: str
    cluster_id: int
    cluster_name: str
    available: int
    daily_demand: float
    stock_days: float | None
    recommended_quantity: int
    level: StockLevel

