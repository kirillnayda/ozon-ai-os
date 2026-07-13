from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import unittest
from unittest.mock import patch

from app.developer_agent.codex_runner import MockCodexRunner
from app.developer_agent.git_workspace import GitWorkspace
from app.developer_agent.service import DeveloperAgentService
from app.developer_agent.task_models import CodexRunResult, DeveloperTaskState, TestRunResult
from app.developer_agent.task_repository import SQLiteDeveloperTaskRepository, make_slug
from app.developer_agent.test_runner import MockTestRunner
from app.developer_agent.telegram_handlers import DeveloperAgentTelegramHandlers


class FakeWorkspace:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.branches: list[str] = []
        self.commits: list[int] = []
        self.pushed: list[str] = []

    def prepare(self, branch: str) -> None: self.branches.append(branch)
    def changed_files(self) -> tuple[str, ...]: return ("app/example.py", "tests/test_example.py")
    def commit_task(self, task_id: int) -> None: self.commits.append(task_id)
    def checkout_existing(self, branch: str) -> None: self.branches.append(branch)
    def push(self, branch: str) -> None: self.pushed.append(branch)


class DeveloperAgentTest(unittest.TestCase):
    @patch("app.developer_agent.git_workspace.subprocess.run")
    def test_git_push_uses_only_exact_saved_refspec(self, run):
        branch = "feature/dev-17-safe-task"
        workspace_path = Path("workspace")
        workspace = GitWorkspace(workspace_path)
        workspace.push(branch)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            commands[-1],
            ["git", "-C", str(workspace_path), "push", "origin", f"refs/heads/{branch}:refs/heads/{branch}"],
        )

    def test_slug_and_unique_branches(self):
        self.assertEqual(make_slug("Исправить статус бота"), "ispravit-status-bota")
        with TemporaryDirectory() as directory:
            repo = SQLiteDeveloperTaskRepository(Path(directory) / "tasks.sqlite3")
            repo.migrate()
            first = repo.create(42, "Исправить статус бота")
            second = repo.create(42, "Исправить статус бота")
            self.assertNotEqual(first.branch, second.branch)

    def test_only_one_active_task_is_claimed(self):
        with TemporaryDirectory() as directory:
            repo = SQLiteDeveloperTaskRepository(Path(directory) / "tasks.sqlite3")
            repo.migrate()
            repo.create(42, "Первая задача")
            repo.create(42, "Вторая задача")
            self.assertIsNotNone(repo.claim_next())
            self.assertIsNone(repo.claim_next())

    def test_interrupted_task_is_recovered_without_exceeding_retry_limit(self):
        with TemporaryDirectory() as directory:
            retry_repo = SQLiteDeveloperTaskRepository(Path(directory) / "retry.sqlite3")
            retry_repo.migrate()
            retryable = retry_repo.create(42, "Повторить прерванную задачу", max_attempts=2)
            retry_repo.claim_next()
            retry_repo.recover_interrupted()
            self.assertEqual(retry_repo.get(retryable.id).state, DeveloperTaskState.QUEUED)

            failed_repo = SQLiteDeveloperTaskRepository(Path(directory) / "failed.sqlite3")
            failed_repo.migrate()
            exhausted = failed_repo.create(42, "Не повторять исчерпанную задачу", max_attempts=1)
            failed_repo.claim_next()
            failed_repo.recover_interrupted()
            self.assertEqual(failed_repo.get(exhausted.id).state, DeveloperTaskState.FAILED)

    def test_mock_codex_reaches_ready_and_push_is_exact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repo = SQLiteDeveloperTaskRepository(root / "tasks.sqlite3")
            repo.migrate()
            task = repo.create(42, "Добавить безопасный тест")
            workspace = FakeWorkspace(root)
            codex = MockCodexRunner(CodexRunResult(0, "Тест добавлен", str(root / "codex.jsonl")))
            service = DeveloperAgentService(repo, workspace, codex, MockTestRunner(TestRunResult(0, "OK")), root / "logs")
            result = service.process_one()
            self.assertEqual(result.state, DeveloperTaskState.READY)
            self.assertEqual(result.changed_files, ("app/example.py", "tests/test_example.py"))
            self.assertEqual(workspace.commits, [task.id])
            repo.update(task.id, push_requested=True)
            service.process_pushes()
            self.assertEqual(workspace.pushed, [task.branch])
            self.assertTrue(repo.get(task.id).pushed)

    def test_cancel_queued_task(self):
        with TemporaryDirectory() as directory:
            repo = SQLiteDeveloperTaskRepository(Path(directory) / "tasks.sqlite3")
            repo.migrate()
            task = repo.create(42, "Отменяемая задача")
            cancelled = repo.request_cancel(task.id, 42)
            self.assertEqual(cancelled.state, DeveloperTaskState.CANCELLED)

    def test_failed_tests_are_retried_and_logged(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repo = SQLiteDeveloperTaskRepository(root / "tasks.sqlite3")
            repo.migrate()
            task = repo.create(42, "Задача с временно упавшими тестами", max_attempts=2)
            service = DeveloperAgentService(
                repo,
                FakeWorkspace(root),
                MockCodexRunner(CodexRunResult(0, "Готово", str(root / "codex.jsonl"))),
                MockTestRunner(TestRunResult(1, "FAILED")),
                root / "logs",
            )
            result = service.process_one()
            self.assertEqual(result.state, DeveloperTaskState.QUEUED)
            self.assertEqual((root / "logs" / str(task.id) / "attempt-1" / "tests.log").read_text(), "FAILED")

    def test_telegram_allowlist_and_push_callback(self):
        with TemporaryDirectory() as directory:
            repo = SQLiteDeveloperTaskRepository(Path(directory) / "tasks.sqlite3")
            handlers = DeveloperAgentTelegramHandlers(repo, 42)
            self.assertIsNone(asyncio.run(handlers.message(7, "/dev Запрещённая задача")))
            created = asyncio.run(handlers.message(42, "/dev Разрешённая задача"))
            self.assertIn("Задача #1", created.text)
            repo.update(1, state=DeveloperTaskState.READY)
            result = asyncio.run(handlers.callback(42, "dev:push:1"))
            self.assertIn("поставлен в очередь", result.text)
            self.assertTrue(repo.get(1).push_requested)

    def test_cancel_accepts_explicit_task_id_and_reject_preserves_failed(self):
        with TemporaryDirectory() as directory:
            repo = SQLiteDeveloperTaskRepository(Path(directory) / "tasks.sqlite3")
            handlers = DeveloperAgentTelegramHandlers(repo, 42)
            first = repo.create(42, "Первая задача для отмены")
            repo.create(42, "Вторая задача остаётся в очереди")
            result = asyncio.run(handlers.message(42, f"/dev_cancel {first.id}"))
            self.assertIn(f"#{first.id}", result.text)
            self.assertEqual(repo.get(first.id).state, DeveloperTaskState.CANCELLED)
            failed = repo.create(42, "Уже завершившаяся с ошибкой задача")
            repo.update(failed.id, state=DeveloperTaskState.FAILED)
            result = asyncio.run(handlers.callback(42, f"dev:reject:{failed.id}"))
            self.assertIn("уже завершена", result.text)
            self.assertEqual(repo.get(failed.id).state, DeveloperTaskState.FAILED)
