from datetime import datetime, timezone
import unittest

from app.storage.models import DemandSnapshot, StockSnapshot
from app.supply.models import StockLevel
from app.supply.service import SupplyManager


class MemorySnapshots:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.stocks = [StockSnapshot(now, 1, "ST-6", 10, "Москва", 100, "Хоругвино", 10, 0)]
        self.demand = [DemandSnapshot(now, 1, "ST-6", 10, 30, 30)]

    def latest_stocks(self): return self.stocks
    def latest_demand(self): return self.demand


class SupplyManagerTest(unittest.TestCase):
    def test_critical_and_replenishment_to_comfort(self):
        repo = MemorySnapshots()
        repo.stocks[0] = StockSnapshot(repo.stocks[0].captured_at, 1, "ST-6", 10, "Москва", 100, "Хоругвино", 5, 0)
        item = SupplyManager(repo).recommendations()[0]
        self.assertEqual(item.level, StockLevel.CRITICAL)
        self.assertEqual(item.recommended_quantity, 40)

    def test_groups_are_limited(self):
        manager = SupplyManager(MemorySnapshots(), group_size=1)
        self.assertEqual(len(manager.purchase_groups()), 1)

