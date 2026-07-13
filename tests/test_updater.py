import unittest

from app.updater.checker import GitHubReleaseChecker


class UpdaterTest(unittest.TestCase):
    def test_version_parser(self):
        self.assertGreater(GitHubReleaseChecker._tuple("v1.2.0"), GitHubReleaseChecker._tuple("1.1.9"))

    def test_rejects_non_semver(self):
        with self.assertRaises(ValueError):
            GitHubReleaseChecker._tuple("main")
