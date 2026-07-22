import unittest

from app.core.errors import LiveModeRequired
from app.core.security import WritePolicy, html_escape, idempotency_key, safe_error_metadata


class SecurityTest(unittest.TestCase):
    def test_html_escape(self):
        self.assertEqual(html_escape("<x>&"), "&lt;x&gt;&amp;")

    def test_live_mode_is_required(self):
        with self.assertRaises(LiveModeRequired):
            WritePolicy(False, 42).require(42, True)

    def test_idempotency_is_stable(self):
        self.assertEqual(idempotency_key("a", 1), idempotency_key("a", 1))

    def test_safe_error_metadata_keeps_fields_but_not_values(self):
        metadata = safe_error_metadata({"code": 3, "message": "warehouse_type must be between 1 and 100; SECRET-SKU rejected; request abc-987", "details": [{"field": "warehouse_type"}]})
        rendered = str(metadata)
        self.assertIn("warehouse_type", metadata["field_identifiers"])
        self.assertIn("response_shape", metadata)
        self.assertNotIn("SECRET-SKU", rendered)
        self.assertNotIn("required;", rendered)
        self.assertEqual(metadata["numeric_constraints"], ["1", "100"])
        self.assertNotIn("987", metadata["numeric_constraints"])
