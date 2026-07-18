import unittest
import asyncio
from unittest.mock import Mock

from app.updater.checker import GitHubReleaseChecker
from app.updater.notify import _notify


class UpdaterTest(unittest.TestCase):
    def test_version_parser(self):
        self.assertGreater(GitHubReleaseChecker._tuple("v1.2.0"), GitHubReleaseChecker._tuple("1.1.9"))

    def test_rejects_non_semver(self):
        with self.assertRaises(ValueError):
            GitHubReleaseChecker._tuple("main")

    def test_notification_rejects_foreign_chat(self):
        with unittest.mock.patch("app.updater.notify.load_settings", return_value=Mock(telegram_chat_id=42)):
            with self.assertRaises(PermissionError):
                asyncio.run(_notify(7, "message"))
