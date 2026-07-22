import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock

from app.updater.startup_notify import StartupUpdateNotifier


class StartupUpdateNotifierTest(unittest.TestCase):
    def test_notifies_once_per_version_after_successful_send(self):
        with TemporaryDirectory() as directory:
            client = AsyncMock()
            state = Path(directory) / "update-notified-version"

            first = asyncio.run(StartupUpdateNotifier(client, 42, "1.3.4", state).notify_once())
            second = asyncio.run(StartupUpdateNotifier(client, 42, "1.3.4", state).notify_once())

            self.assertTrue(first)
            self.assertFalse(second)
            client.send_message.assert_awaited_once()
            self.assertEqual(state.read_text(encoding="utf-8").strip(), "1.3.4")

    def test_failed_send_does_not_mark_version_as_notified(self):
        with TemporaryDirectory() as directory:
            client = AsyncMock()
            client.send_message.side_effect = RuntimeError("telegram unavailable")
            state = Path(directory) / "update-notified-version"

            with self.assertRaises(RuntimeError):
                asyncio.run(StartupUpdateNotifier(client, 42, "1.3.4", state).notify_once())

            self.assertFalse(state.exists())
