import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check


class CheckScriptTest(unittest.TestCase):
    def test_main_does_not_depend_on_current_directory(self):
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch("scripts.check.subprocess.call", return_value=0) as call:
                    self.assertEqual(check.main(), 0)
            finally:
                os.chdir(original_directory)

        call.assert_called_once_with(
            [
                check.sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
            cwd=check.PROJECT_ROOT,
        )


if __name__ == "__main__":
    unittest.main()
