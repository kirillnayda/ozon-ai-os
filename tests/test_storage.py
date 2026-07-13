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

