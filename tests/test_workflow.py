import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core.security import WritePolicy
from app.ozon.endpoints import CARGOES_CREATE, CARGOES_STATUS, DRAFT_DIRECT_CREATE, LABELS_CREATE, LABELS_FILE, LABELS_GET
from app.ozon.transport import MockTransport
from app.storage.models import OperationState
from app.storage.sqlite import SQLiteStorage
from app.supplies.parser import parse_supply_intent
from app.supplies.service import SupplyWorkflow


class WorkflowTest(unittest.TestCase):
    def test_mock_creation_and_deduplication(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            transport = MockTransport({
                DRAFT_DIRECT_CREATE.path: [{"operation_id": "op-1"}],
                CARGOES_CREATE.path: [{"operation_id": "cargo-1"}],
                CARGOES_STATUS.path: [{"status": "success"}],
                LABELS_CREATE.path: [{"operation_id": "label-1"}],
                LABELS_GET.path: [{"file_guid": "file-1"}],
                LABELS_FILE.path.format(file_guid="file-1"): [b"%PDF-1.7 mock"],
            })
            workflow = SupplyWorkflow(transport, storage, storage, WritePolicy(True, 42))
            intent = parse_supply_intent("Создай поставку в Москву:\nST-6 120 шт., по 30 в коробке")
            first = workflow.prepare(42, intent)
            second = workflow.prepare(42, intent)
            self.assertEqual(first.id, second.id)
            created = asyncio.run(workflow.confirm(42, first.id))
            self.assertEqual(created.state, OperationState.CREATED)
            self.assertEqual(created.external_id, "op-1")
            completed, pdf = asyncio.run(workflow.create_cargoes_and_labels_mockable(42, created.id))
            self.assertEqual(completed.state, OperationState.COMPLETED)
            self.assertTrue(pdf.startswith(b"%PDF"))

    def test_cancel_is_terminal_and_does_not_call_transport(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            transport = MockTransport({})
            workflow = SupplyWorkflow(transport, storage, storage, WritePolicy(False, 42))
            intent = parse_supply_intent("Создай поставку в Москву:\nST-6 120 шт., по 30 в коробке")
            operation = workflow.prepare(42, intent)

            cancelled = workflow.cancel(42, operation.id)

            self.assertEqual(cancelled.state, OperationState.CANCELLED)
            self.assertEqual(workflow.cancel(42, operation.id).state, OperationState.CANCELLED)
            self.assertEqual(storage.unfinished(), [])
            self.assertEqual(transport.calls, [])

    def test_transport_error_marks_operation_failed(self):
        class FailingTransport(MockTransport):
            async def request(self, endpoint, payload, *, allow_mutation=False):
                raise RuntimeError("temporary failure")

        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            workflow = SupplyWorkflow(FailingTransport({}), storage, storage, WritePolicy(True, 42))
            intent = parse_supply_intent("Создай поставку в Москву:\nST-6 120 шт., по 30 в коробке")
            operation = workflow.prepare(42, intent)

            with self.assertRaises(RuntimeError):
                asyncio.run(workflow.confirm(42, operation.id))

            failed = storage.get(operation.id)
            self.assertEqual(failed.state, OperationState.FAILED)
            self.assertIn("RuntimeError", failed.error)
            self.assertEqual(storage.unfinished(), [])
