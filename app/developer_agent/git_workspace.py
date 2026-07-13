from __future__ import annotations

from pathlib import Path
import re
import subprocess

BRANCH = re.compile(r"^feature/dev-\d+-[a-z0-9-]+$")


class GitWorkspace:
    def __init__(self, path: Path, base_branch: str = "main", timeout: int = 120) -> None:
        self.path, self.base_branch, self.timeout = path, base_branch, timeout

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(self.path), *args], text=True, capture_output=True, timeout=self.timeout, check=True)

    def prepare(self, branch: str) -> None:
        self._validate(branch)
        self._git("fetch", "--prune", "origin", self.base_branch)
        self._git("checkout", "-B", branch, f"origin/{self.base_branch}")
        self._git("clean", "-fdx")

    def changed_files(self) -> tuple[str, ...]:
        status = {line[3:] for line in self._status().splitlines() if len(line) > 3}
        committed = set(self._git("diff", "--name-only", f"origin/{self.base_branch}...HEAD").stdout.splitlines())
        return tuple(sorted(status | committed))

    def commit_task(self, task_id: int) -> None:
        if not self._status().strip():
            return
        self._git("add", "--all")
        self._git("commit", "-m", f"Developer Agent task #{task_id}")

    def _status(self) -> str:
        return self._git("status", "--porcelain=v1").stdout

    def checkout_existing(self, branch: str) -> None:
        self._validate(branch)
        self._git("checkout", branch)

    def push(self, branch: str) -> None:
        self._validate(branch)
        self._git("show-ref", "--verify", f"refs/heads/{branch}")
        ref = f"refs/heads/{branch}:refs/heads/{branch}"
        self._git("push", "origin", ref)

    @staticmethod
    def _validate(branch: str) -> None:
        if not BRANCH.fullmatch(branch):
            raise ValueError("Недопустимое имя ветки")
