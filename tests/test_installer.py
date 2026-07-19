from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstallerTest(unittest.TestCase):
    def test_service_user_can_traverse_application_directory(self):
        installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('chown -R root:"${APP_USER}" "${APP_DIR}"', installer)
        self.assertNotIn('chown -R root:root "${APP_DIR}"', installer)
        self.assertIn('chmod 0750 "${APP_DIR}"', installer)


if __name__ == "__main__":
    unittest.main()
