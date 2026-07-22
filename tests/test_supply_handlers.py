import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.config import Settings
from app.core.security import WritePolicy
from app.ozon.transport import SupplyTestTransport
from app.storage.sqlite import SQLiteStorage
from app.supplies.dialog import SnapshotProductCatalog, SupplyDialogService
from app.supplies.service import SupplyWorkflow
from app.supply.service import SupplyManager
from app.telegram.handlers import CommandHandlers
from app.inventory.gateway import MockInventoryGateway
from app.inventory.service import InventoryService
from app.core.errors import ContractNotVerified
from unittest.mock import AsyncMock


class SupplyHandlersTest(unittest.TestCase):
    def test_stock_sync_shows_safe_contract_reason(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            workflow = SupplyWorkflow(SupplyTestTransport(), storage, storage, WritePolicy(False, 42), test_mode=True)
            dialogs = SupplyDialogService(storage, SnapshotProductCatalog(storage, ("TEST-SKU",)), workflow, True)
            settings = Settings("token", 42, "client", "key", 9, "UTC", False, "test", 7, 30, 45, 7, 6, "", "1.0.0", 60)
            inventory = AsyncMock()
            inventory.sync.side_effect = ContractNotVerified("Неполный DTO /v1/analytics/stocks")
            handlers = CommandHandlers(settings, None, SupplyManager(storage), workflow, dialogs, storage, None, None, inventory)

            result = asyncio.run(handlers.message(42, "/stocks_sync"))

            self.assertIn("Неполный DTO /v1/analytics/stocks", result.text)
            self.assertIn("Внешний ответ не сохранён", result.text)
    def test_inventory_product_navigation_and_cluster_sales(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            inventory = InventoryService(MockInventoryGateway(), storage, storage)
            asyncio.run(inventory.sync("test"))
            workflow = SupplyWorkflow(SupplyTestTransport(), storage, storage, WritePolicy(False, 42), test_mode=True)
            dialogs = SupplyDialogService(storage, SnapshotProductCatalog(storage, ("TEST-SKU",)), workflow, True)
            settings = Settings("token", 42, "client", "key", 9, "UTC", False, "test", 7, 30, 45, 7, 6, "", "1.0.0", 60)
            handlers = CommandHandlers(settings, None, SupplyManager(storage), workflow, dialogs, storage, None, None, inventory)

            products = asyncio.run(handlers.callback(42, "inventory:clusters"))
            self.assertIn("Выберите товар", products.text)
            self.assertEqual(products.keyboard["inline_keyboard"][0][0]["callback_data"], "inventory:product:1001:0")
            detail = asyncio.run(handlers.callback(42, "inventory:product:1001:0"))
            self.assertIn("Москва</b>: 16 шт. · продажи 6.00 шт./день", detail.text)
            self.assertIn("Средние продажи всего: 6.00 шт./день", detail.text)
            self.assertEqual(detail.keyboard["inline_keyboard"][0][0]["callback_data"], "inventory:page:0")

    def test_test_mode_confirmation_returns_pdf_for_telegram(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            transport = SupplyTestTransport()
            workflow = SupplyWorkflow(transport, storage, storage, WritePolicy(False, 42), test_mode=True)
            dialogs = SupplyDialogService(storage, SnapshotProductCatalog(storage, ("TEST-SKU",)), workflow, True)
            settings = Settings("token", 42, "client", "key", 9, "UTC", False, "test", 7, 30, 45, 7, 6, "", "1.0.0", 60)
            handlers = CommandHandlers(settings, None, SupplyManager(storage), workflow, dialogs, storage, None, None)

            asyncio.run(handlers.message(42, "/supply_test"))
            for answer in ("Москва", "2026-07-20 10:00–12:00", "TEST-SKU", "120"):
                asyncio.run(handlers.message(42, answer))
            summary = asyncio.run(handlers.message(42, "30"))
            operation_id = summary.keyboard["inline_keyboard"][0][0]["callback_data"].split(":", 2)[2]

            result = asyncio.run(handlers.callback(42, f"supply:confirm:{operation_id}"))

            self.assertIn("Тестовая поставка завершена", result.text)
            self.assertEqual(result.document_name, f"ozon-cargo-labels-{operation_id}.pdf")
            self.assertTrue(result.document.startswith(b"%PDF"))

    def test_foreign_chat_cannot_start_supply(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            workflow = SupplyWorkflow(SupplyTestTransport(), storage, storage, WritePolicy(False, 42), test_mode=True)
            dialogs = SupplyDialogService(storage, SnapshotProductCatalog(storage, ("TEST-SKU",)), workflow, True)
            settings = Settings("token", 42, "client", "key", 9, "UTC", False, "test", 7, 30, 45, 7, 6, "", "1.0.0", 60)
            handlers = CommandHandlers(settings, None, SupplyManager(storage), workflow, dialogs, storage, None, None)
            self.assertIsNone(asyncio.run(handlers.message(7, "/supply_test")))
