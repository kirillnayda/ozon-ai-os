from pathlib import Path
from unittest.mock import patch
import unittest

from app.config import load_settings
from app.core.errors import ConfigurationError


BASE = {
    "TELEGRAM_BOT_TOKEN": "token",
    "TELEGRAM_CHAT_ID": "42",
    "OZON_CLIENT_ID": "client",
    "OZON_API_KEY": "key",
    "TIMEZONE": "UTC",
}


class ConfigTest(unittest.TestCase):
    def test_live_mode_defaults_to_false(self):
        with patch.dict("os.environ", BASE, clear=True):
            settings = load_settings(Path("missing.env"))
            self.assertFalse(settings.live_mode)
            self.assertEqual(settings.current_version, "1.1.2")

    def test_invalid_boolean_is_rejected(self):
        with patch.dict("os.environ", {**BASE, "LIVE_MODE": "yes"}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_settings(Path("missing.env"))

    def test_threshold_order_is_validated(self):
        with patch.dict("os.environ", {**BASE, "CRITICAL_STOCK_DAYS": "40", "MIN_STOCK_DAYS": "30"}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_settings(Path("missing.env"))
