from __future__ import annotations

from pathlib import Path
import subprocess

from app.developer_agent.task_models import TestRunResult


class TestRunner:
    def __init__(self, command: tuple[str, ...] = ("python", "scripts/check.py"), timeout_seconds: int = 600) -> None:
        self.command, self.timeout_seconds = command, timeout_seconds

    def run(self, workspace: Path) -> TestRunResult:
        try:
            result = subprocess.run(self.command, cwd=workspace, text=True, capture_output=True, timeout=self.timeout_seconds)
            output = (result.stdout + "\n" + result.stderr).strip()
            return TestRunResult(result.returncode, output[-12000:])
        except subprocess.TimeoutExpired as exc:
            output = f"{exc.stdout or ''}\n{exc.stderr or ''}"[-12000:]
            return TestRunResult(124, output, timed_out=True)


class MockTestRunner:
    def __init__(self, result: TestRunResult) -> None:
        self.result = result

    def run(self, workspace: Path) -> TestRunResult:
        return self.result

