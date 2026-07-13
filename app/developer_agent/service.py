from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sys

from app.developer_agent.codex_runner import CodexRunner
from app.developer_agent.git_workspace import GitWorkspace
from app.developer_agent.task_models import DeveloperTask, DeveloperTaskState
from app.developer_agent.task_repository import SQLiteDeveloperTaskRepository
from app.developer_agent.test_runner import TestRunner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeveloperAgentConfig:
    database_path: Path
    workspace: Path
    log_dir: Path
    task_timeout_seconds: int = 1800
    test_timeout_seconds: int = 600
    max_attempts: int = 2
    base_branch: str = "main"
    codex_executable: str = "codex"

    @classmethod
    def from_environment(cls) -> "DeveloperAgentConfig":
        return cls(
            database_path=Path(os.getenv("DEVELOPER_AGENT_DB_PATH", "/var/lib/ozon-ai-developer/tasks.sqlite3")),
            workspace=Path(os.getenv("DEVELOPER_AGENT_WORKSPACE", "/opt/ozon-ai-dev")),
            log_dir=Path(os.getenv("DEVELOPER_AGENT_LOG_DIR", "/var/log/ozon-ai-developer")),
            task_timeout_seconds=int(os.getenv("DEVELOPER_AGENT_TASK_TIMEOUT", "1800")),
            test_timeout_seconds=int(os.getenv("DEVELOPER_AGENT_TEST_TIMEOUT", "600")),
            max_attempts=int(os.getenv("DEVELOPER_AGENT_MAX_ATTEMPTS", "2")),
            base_branch=os.getenv("DEVELOPER_AGENT_BASE_BRANCH", "main"),
            codex_executable=os.getenv("CODEX_EXECUTABLE", "codex"),
        )


class DeveloperAgentService:
    def __init__(self, repository: SQLiteDeveloperTaskRepository, workspace: GitWorkspace, codex: CodexRunner, tests: TestRunner, log_dir: Path) -> None:
        self.repository, self.workspace, self.codex, self.tests, self.log_dir = repository, workspace, codex, tests, log_dir

    def process_one(self) -> DeveloperTask | None:
        task = self.repository.claim_next()
        if not task:
            return None
        task_logs = self.log_dir / str(task.id) / f"attempt-{task.attempts}"
        try:
            self.workspace.prepare(task.branch)
            plan = f"Изолированная реализация задачи #{task.id}; без merge, push и deploy."
            task = self.repository.update(task.id, state=DeveloperTaskState.CODING, plan=plan)
            prompt = self._prompt(task)
            result = self.codex.run(self.workspace.path, prompt, task_logs, lambda: bool((current := self.repository.get(task.id)) and current.cancel_requested))
            if result.cancelled:
                return self.repository.update(task.id, state=DeveloperTaskState.CANCELLED, log_path=result.log_path, summary="Задача отменена пользователем")
            if result.timed_out:
                return self._retry_or_fail(task, "Превышен таймаут Codex", result.log_path)
            if result.exit_code != 0:
                return self._retry_or_fail(task, f"Codex завершился с кодом {result.exit_code}", result.log_path)
            task = self.repository.update(task.id, state=DeveloperTaskState.TESTING, summary=result.last_message, log_path=result.log_path)
            test_result = self.tests.run(self.workspace.path)
            task_logs.mkdir(parents=True, exist_ok=True)
            (task_logs / "tests.log").write_text(test_result.output, encoding="utf-8")
            files = self.workspace.changed_files()
            current = self.repository.get(task.id)
            if current and current.cancel_requested:
                return self.repository.update(
                    task.id,
                    state=DeveloperTaskState.CANCELLED,
                    changed_files=files,
                    test_output=test_result.output,
                    summary="Задача отменена пользователем",
                )
            if test_result.exit_code != 0:
                reason = "Превышен таймаут тестов" if test_result.timed_out else "Тесты не прошли"
                task = self.repository.update(task.id, changed_files=files, test_output=test_result.output)
                return self._retry_or_fail(task, reason, result.log_path)
            self.workspace.commit_task(task.id)
            return self.repository.update(task.id, state=DeveloperTaskState.READY, changed_files=files, test_output=test_result.output)
        except Exception as exc:
            logger.exception("Developer task %s failed", task.id)
            return self._retry_or_fail(task, str(exc), str(task_logs))

    def process_pushes(self) -> None:
        for task in self.repository.requested_pushes():
            try:
                self.workspace.push(task.branch)
                self.repository.update(task.id, pushed=True, push_requested=False, summary=(task.summary + "\nВетка отправлена в GitHub.").strip(), report_sent=False)
            except Exception as exc:
                self.repository.update(task.id, push_requested=False, error=f"Push не выполнен: {exc}", report_sent=False)

    def _retry_or_fail(self, task: DeveloperTask, error: str, log_path: str) -> DeveloperTask:
        current = self.repository.get(task.id) or task
        if current.cancel_requested:
            return self.repository.update(task.id, state=DeveloperTaskState.CANCELLED, error=error, log_path=log_path)
        if current.attempts < current.max_attempts:
            return self.repository.update(task.id, state=DeveloperTaskState.QUEUED, error=error, log_path=log_path)
        return self.repository.update(task.id, state=DeveloperTaskState.FAILED, error=error, log_path=log_path)

    @staticmethod
    def _prompt(task: DeveloperTask) -> str:
        return f"""Ты работаешь как Developer Agent Ozon AI OS.

Задача #{task.id}: {task.description}

Ограничения:
- работай только в текущей ветке {task.branch};
- сначала изучи AGENTS.md и существующую архитектуру;
- реализуй минимальные безопасные изменения и тесты;
- не выполняй git push, merge, deploy и не читай секреты;
- не меняй .env;
- запусти релевантные локальные проверки, но итоговые тесты дополнительно запустит supervisor;
- в финале кратко опиши результат и ограничения.
"""


def build_service(config: DeveloperAgentConfig | None = None) -> DeveloperAgentService:
    config = config or DeveloperAgentConfig.from_environment()
    repository = SQLiteDeveloperTaskRepository(config.database_path)
    repository.migrate()
    repository.recover_interrupted()
    return DeveloperAgentService(
        repository,
        GitWorkspace(config.workspace, config.base_branch),
        CodexRunner(config.codex_executable, timeout_seconds=config.task_timeout_seconds),
        TestRunner((sys.executable, "scripts/check.py"), timeout_seconds=config.test_timeout_seconds),
        config.log_dir,
    )


if __name__ == "__main__":
    from app.core.logging import configure_logging
    from app.developer_agent.task_queue import TaskQueue
    import asyncio

    configure_logging()
    asyncio.run(TaskQueue(build_service()).run())
