from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.storage.sqlite import SQLiteStorage


class StorageTest(unittest.TestCase):
    def test_migrations_are_idempotent(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            storage.migrate()
            storage.record("test", "migrate", "ok")

    def test_pdf_outbox_and_metrics(self):
        with TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "test.sqlite3")
            storage.migrate()
            item = storage.queue_pdf("operation-1", 42, b"%PDF-test")
            self.assertEqual(len(storage.pending_pdfs()), 1)
            self.assertTrue(Path(item.path).is_file())
            self.assertEqual(storage.supply_metrics()["pending_pdf"], 1)
            storage.mark_pdf_delivered(item.id)
            self.assertFalse(Path(item.path).exists())
            self.assertEqual(storage.pending_pdfs(), [])
