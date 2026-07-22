import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core.errors import ContractNotVerified
from app.inventory.gateway import MockInventoryGateway, UnverifiedOzonInventoryGateway
from app.inventory.service import InventoryService
from app.storage.sqlite import SQLiteStorage


class InventoryTest(unittest.TestCase):
    def test_mock_sync_and_cluster_report(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            service = InventoryService(MockInventoryGateway(), storage, storage)
            counts = asyncio.run(service.sync("test"))
            self.assertEqual(counts, (2, 2))
            clusters = service.clusters()
            self.assertEqual([row.cluster_name for row in clusters], ["Москва", "Санкт-Петербург"])
            self.assertEqual(clusters[0].available, 16)
            products = service.products()
            self.assertEqual([(row.offer_id, row.available) for row in products], [("TEST-SKU", 16), ("TEST-SKU-2", 35)])
            details = service.product_clusters(1001)
            self.assertEqual(details[0].cluster_name, "Москва")
            self.assertEqual(details[0].daily_sales, 6.0)
            self.assertFalse(service.stale())

    def test_production_gateway_is_fail_closed_without_fixture(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            service = InventoryService(UnverifiedOzonInventoryGateway(), storage, storage)
            with self.assertRaises(ContractNotVerified):
                asyncio.run(service.sync("test"))
            self.assertEqual(service.last_error, "ContractNotVerified")
