import asyncio
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core.security import WritePolicy
from app.ozon.transport import SupplyTestTransport
from app.storage.models import DemandSnapshot, OperationState, StockSnapshot
from app.storage.sqlite import SQLiteStorage
from app.supplies.dialog import SnapshotProductCatalog, SupplyDialogService
from app.supplies.service import SupplyWorkflow


class SupplyDialogTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.storage = SQLiteStorage(Path(self.directory.name) / "test.sqlite3")
        self.storage.migrate()
        now = datetime.now(timezone.utc)
        self.storage.replace_stocks([StockSnapshot(now, 1, "SKU-1", 1, "Москва", 1, "Хоругвино", 5)])
        self.storage.replace_demand([DemandSnapshot(now, 1, "SKU-1", 1, 30, 30)])
        self.transport = SupplyTestTransport()
        self.workflow = SupplyWorkflow(self.transport, self.storage, self.storage, WritePolicy(False, 42), test_mode=True, timeout_seconds=.01, poll_interval=0)
        self.dialog = SupplyDialogService(self.storage, SnapshotProductCatalog(self.storage), self.workflow, True)

    def tearDown(self):
        self.directory.cleanup()

    def _prepare(self):
        self.dialog.start(42)
        self.dialog.answer(42, "Москва")
        self.dialog.answer(42, "2026-07-20 10:00–12:00")
        self.dialog.answer(42, "SKU-1")
        self.dialog.answer(42, "120")
        return self.dialog.answer(42, "30")

    def test_successful_test_scenario_and_pdf(self):
        result = self._prepare()
        self.assertIn("Москва", result.text)
        self.assertIn("4 кор.", result.text)
        operation = asyncio.run(self.workflow.confirm(42, result.operation.id))
        completed, pdf = asyncio.run(self.workflow.create_cargoes_and_labels_mockable(42, operation.id))
        self.assertEqual(completed.state, OperationState.COMPLETED)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_cancel_before_creation(self):
        self.dialog.start(42)
        self.dialog.cancel(42)
        self.assertFalse(self.dialog.active(42))
        self.assertEqual(self.transport.calls, [])

    def test_unknown_article_and_non_divisible_quantity(self):
        self.dialog.start(42)
        self.dialog.answer(42, "Москва")
        self.dialog.answer(42, "2026-07-20 10:00–12:00")
        unknown = self.dialog.answer(42, "NO-SUCH-SKU")
        self.assertIn("Неизвестный", unknown.text)
        self.dialog.answer(42, "SKU-1")
        self.dialog.answer(42, "121")
        invalid = self.dialog.answer(42, "30")
        self.assertIn("не делится", invalid.text)

    def test_dialog_survives_service_restart(self):
        self.dialog.start(42)
        self.dialog.answer(42, "Москва")
        restarted = SupplyDialogService(self.storage, SnapshotProductCatalog(self.storage), self.workflow, True)
        result = restarted.answer(42, "2026-07-20 10:00–12:00")
        self.assertIn("артикулы", result.text)

    def test_supply_operation_survives_workflow_restart(self):
        result = self._prepare()
        created = asyncio.run(self.workflow.confirm(42, result.operation.id))
        restarted = SupplyWorkflow(self.transport, self.storage, self.storage, WritePolicy(False, 42), test_mode=True)
        completed, pdf = asyncio.run(restarted.create_cargoes_and_labels_mockable(42, created.id))
        self.assertEqual(completed.state, OperationState.COMPLETED)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_background_recovery_returns_pdf_for_delivery(self):
        result = self._prepare()
        asyncio.run(self.workflow.confirm(42, result.operation.id))
        restarted = SupplyWorkflow(self.transport, self.storage, self.storage, WritePolicy(False, 42), test_mode=True)
        recovered = asyncio.run(restarted.poll_unfinished())
        self.assertEqual(recovered[0][0:2], (42, result.operation.id))
        self.assertTrue(recovered[0][2].startswith(b"%PDF"))

    def test_foreign_chat_is_forbidden_even_in_test_mode(self):
        result = self._prepare()
        with self.assertRaises(PermissionError):
            asyncio.run(self.workflow.confirm(7, result.operation.id))

    def test_repeated_confirmation_does_not_repeat_requests(self):
        result = self._prepare()
        operation = asyncio.run(self.workflow.confirm(42, result.operation.id))
        calls = len(self.transport.calls)
        repeated = asyncio.run(self.workflow.confirm(42, operation.id))
        self.assertEqual(repeated.state, OperationState.SUPPLY_CREATED)
        self.assertEqual(len(self.transport.calls), calls)

    def test_timeout_marks_operation_failed(self):
        class PendingTransport(SupplyTestTransport):
            async def request(self, endpoint, payload, *, allow_mutation=False):
                if not endpoint.mutating:
                    return {"status": "pending"}
                return await super().request(endpoint, payload, allow_mutation=allow_mutation)

        result = self._prepare()
        workflow = SupplyWorkflow(PendingTransport(), self.storage, self.storage, WritePolicy(False, 42), test_mode=True, timeout_seconds=0, poll_interval=0)
        with self.assertRaises(TimeoutError):
            asyncio.run(workflow.confirm(42, result.operation.id))
        self.assertEqual(self.storage.get(result.operation.id).state, OperationState.FAILED)

    def test_api_error_marks_operation_failed(self):
        class FailingTransport(SupplyTestTransport):
            async def request(self, endpoint, payload, *, allow_mutation=False):
                raise RuntimeError("external response must not be stored")

        result = self._prepare()
        workflow = SupplyWorkflow(FailingTransport(), self.storage, self.storage, WritePolicy(False, 42), test_mode=True)
        with self.assertRaises(RuntimeError):
            asyncio.run(workflow.confirm(42, result.operation.id))
        failed = self.storage.get(result.operation.id)
        self.assertEqual(failed.error, "RuntimeError")
        self.assertNotIn("external response", failed.error)
