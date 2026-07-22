import unittest
import asyncio
from pathlib import Path
from unittest.mock import Mock

from app.updater.checker import GitHubReleaseChecker
from app.updater.notify import _notify


class UpdaterTest(unittest.TestCase):
    def test_checkout_repairs_service_read_permissions(self):
        updater = (Path(__file__).resolve().parents[1] / "scripts" / "ozon-ai-os-updater").read_text(encoding="utf-8")
        self.assertIn("repair_source_permissions", updater)
        self.assertIn('chmod g+rX "${APP_DIR}/${path}"', updater)
        self.assertIn('git -C "${APP_DIR}" checkout --detach "${VERSION}"\nrepair_source_permissions', updater)

    def test_success_notification_is_sent_after_service_health_check(self):
        updater = (Path(__file__).resolve().parents[1] / "scripts" / "ozon-ai-os-updater").read_text(encoding="utf-8")
        health_check = 'systemctl is-active --quiet "${SERVICE}"'
        notification = 'notify "✅ Ozon AI OS обновлён до ${VERSION}. Проверки пройдены, бот снова работает."'
        self.assertLess(updater.index(health_check), updater.index(notification))

    def test_version_parser(self):
        self.assertGreater(GitHubReleaseChecker._tuple("v1.2.0"), GitHubReleaseChecker._tuple("1.1.9"))

    def test_rejects_non_semver(self):
        with self.assertRaises(ValueError):
            GitHubReleaseChecker._tuple("main")

    def test_notification_rejects_foreign_chat(self):
        with unittest.mock.patch("app.updater.notify.load_settings", return_value=Mock(telegram_chat_id=42)):
            with self.assertRaises(PermissionError):
                asyncio.run(_notify(7, "message"))
