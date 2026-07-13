import unittest

from app.core.errors import LiveModeRequired
from app.core.security import WritePolicy, html_escape, idempotency_key


class SecurityTest(unittest.TestCase):
    def test_html_escape(self):
        self.assertEqual(html_escape("<x>&"), "&lt;x&gt;&amp;")

    def test_live_mode_is_required(self):
        with self.assertRaises(LiveModeRequired):
            WritePolicy(False, 42).require(42, True)

    def test_idempotency_is_stable(self):
        self.assertEqual(idempotency_key("a", 1), idempotency_key("a", 1))

