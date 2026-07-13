from __future__ import annotations

from pathlib import Path
import os
import signal
import subprocess
import time
from collections.abc import Callable

from app.developer_agent.task_models import CodexRunResult


class CodexRunner:
    def __init__(self, executable: str = "codex", timeout_seconds: int = 1800) -> None:
        self.executable, self.timeout_seconds = executable, timeout_seconds

    def run(self, workspace: Path, prompt: str, log_dir: Path, cancelled: Callable[[], bool]) -> CodexRunResult:
        log_dir.mkdir(parents=True, exist_ok=True)
        event_log = log_dir / "codex.jsonl"
        last_message = log_dir / "last-message.txt"
        command = [self.executable, "exec", "--sandbox", "workspace-write", "--cd", str(workspace), "--ephemeral", "--ignore-user-config", "--color", "never", "--json", "--output-last-message", str(last_message), "-"]
        with event_log.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT, text=True, start_new_session=os.name != "nt")
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            started = time.monotonic()
            while process.poll() is None:
                if cancelled():
                    self._terminate(process)
                    return CodexRunResult(process.wait(), "", str(event_log), cancelled=True)
                if time.monotonic() - started > self.timeout_seconds:
                    self._terminate(process)
                    return CodexRunResult(process.wait(), "", str(event_log), timed_out=True)
                time.sleep(0.5)
        message = last_message.read_text(encoding="utf-8") if last_message.exists() else ""
        return CodexRunResult(process.returncode or 0, message.strip(), str(event_log))

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)


class MockCodexRunner:
    def __init__(self, result: CodexRunResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def run(self, workspace: Path, prompt: str, log_dir: Path, cancelled: Callable[[], bool]) -> CodexRunResult:
        self.calls.append(prompt)
        return self.result
