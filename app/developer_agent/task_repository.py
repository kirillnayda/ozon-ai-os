from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from collections.abc import Iterator
from uuid import uuid4

from app.developer_agent.task_models import ACTIVE_STATES, DeveloperTask, DeveloperTaskState

SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    slug TEXT NOT NULL,
    branch TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    plan TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    changed_files TEXT NOT NULL DEFAULT '[]',
    test_output TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    log_path TEXT NOT NULL DEFAULT '',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    push_requested INTEGER NOT NULL DEFAULT 0,
    pushed INTEGER NOT NULL DEFAULT 0,
    report_sent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_developer_tasks_state ON developer_tasks(state, id);
"""


def make_slug(description: str, limit: int = 36) -> str:
    value = description.lower().replace("ё", "е")
    value = re.sub(r"[^a-z0-9а-я]+", "-", value, flags=re.IGNORECASE).strip("-")
    transliteration = str.maketrans({
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh","з":"z","и":"i","й":"y",
        "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
        "ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    })
    value = value.translate(transliteration)
    value = re.sub(r"[^a-z0-9-]+", "", value).strip("-")
    return (value[:limit].rstrip("-") or "task")


class SQLiteDeveloperTaskRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    def create(self, chat_id: int, description: str, max_attempts: int = 2) -> DeveloperTask:
        description = description.strip()
        if not 5 <= len(description) <= 4000:
            raise ValueError("Описание задачи должно содержать от 5 до 4000 символов")
        if not 1 <= max_attempts <= 5:
            raise ValueError("Лимит попыток должен быть от 1 до 5")
        now = datetime.now(timezone.utc).isoformat()
        slug = make_slug(description)
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO developer_tasks(chat_id,description,slug,branch,state,max_attempts,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (chat_id, description, slug, f"pending-{uuid4()}", DeveloperTaskState.QUEUED.value, max_attempts, now, now),
            )
            task_id = int(cursor.lastrowid)
            branch = f"feature/dev-{task_id}-{slug}"
            connection.execute("UPDATE developer_tasks SET branch=? WHERE id=?", (branch, task_id))
        task = self.get(task_id)
        assert task is not None
        return task

    def get(self, task_id: int) -> DeveloperTask | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM developer_tasks WHERE id=?", (task_id,)).fetchone()
        return self._from_row(row) if row else None

    def latest_for_chat(self, chat_id: int) -> DeveloperTask | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM developer_tasks WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_recent(self, chat_id: int, limit: int = 10) -> list[DeveloperTask]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM developer_tasks WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
        return [self._from_row(row) for row in rows]

    def claim_next(self) -> DeveloperTask | None:
        active = tuple(state.value for state in ACTIVE_STATES)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM developer_tasks WHERE state IN (?,?,?) LIMIT 1", active).fetchone():
                return None
            row = connection.execute(
                "SELECT * FROM developer_tasks WHERE state=? AND cancel_requested=0 ORDER BY id LIMIT 1",
                (DeveloperTaskState.QUEUED.value,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE developer_tasks SET state=?, attempts=attempts+1, updated_at=? WHERE id=? AND state=?",
                (DeveloperTaskState.ANALYSING.value, datetime.now(timezone.utc).isoformat(), row["id"], DeveloperTaskState.QUEUED.value),
            )
        return self.get(int(row["id"]))

    def recover_interrupted(self) -> None:
        """Возвращает прерванные worker-процессом задачи в очередь.

        В штатной работе одновременно существует не более одной active-задачи,
        однако после SIGKILL её состояние остаётся в SQLite. Восстановление
        выполняется один раз при запуске worker и учитывает лимит попыток.
        """
        now = datetime.now(timezone.utc).isoformat()
        active = tuple(state.value for state in ACTIVE_STATES)
        with self._connection() as connection:
            connection.execute(
                "UPDATE developer_tasks SET state=?, updated_at=? "
                "WHERE state IN (?,?,?) AND cancel_requested=1",
                (DeveloperTaskState.CANCELLED.value, now, *active),
            )
            connection.execute(
                "UPDATE developer_tasks SET state=?, error=?, updated_at=? "
                "WHERE state IN (?,?,?) AND cancel_requested=0 AND attempts>=max_attempts",
                (DeveloperTaskState.FAILED.value, "Worker был прерван; лимит попыток исчерпан", now, *active),
            )
            connection.execute(
                "UPDATE developer_tasks SET state=?, error=?, updated_at=? "
                "WHERE state IN (?,?,?) AND cancel_requested=0 AND attempts<max_attempts",
                (DeveloperTaskState.QUEUED.value, "Worker был прерван; задача возвращена в очередь", now, *active),
            )

    def update(self, task_id: int, **fields: object) -> DeveloperTask:
        allowed = {"state", "plan", "summary", "changed_files", "test_output", "error", "log_path", "cancel_requested", "push_requested", "pushed", "report_sent"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Недопустимые поля: {sorted(unknown)}")
        values: dict[str, object] = dict(fields)
        if isinstance(values.get("state"), DeveloperTaskState):
            values["state"] = values["state"].value
        if "changed_files" in values:
            values["changed_files"] = json.dumps(list(values["changed_files"]), ensure_ascii=False)
        for key in {"cancel_requested", "push_requested", "pushed", "report_sent"} & values.keys():
            values[key] = int(bool(values[key]))
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ",".join(f"{name}=?" for name in values)
        with self._connection() as connection:
            connection.execute(f"UPDATE developer_tasks SET {assignments} WHERE id=?", (*values.values(), task_id))
        task = self.get(task_id)
        if not task:
            raise KeyError(task_id)
        return task

    def request_cancel(self, task_id: int, chat_id: int) -> DeveloperTask:
        task = self.get(task_id)
        if not task or task.chat_id != chat_id:
            raise PermissionError("Задача не найдена")
        if task.state == DeveloperTaskState.QUEUED:
            return self.update(task_id, cancel_requested=True, state=DeveloperTaskState.CANCELLED)
        if task.state in ACTIVE_STATES:
            return self.update(task_id, cancel_requested=True)
        return task

    def pending_reports(self) -> list[DeveloperTask]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM developer_tasks WHERE state IN (?,?,?) AND report_sent=0 ORDER BY id",
                (DeveloperTaskState.READY.value, DeveloperTaskState.FAILED.value, DeveloperTaskState.CANCELLED.value),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def requested_pushes(self) -> list[DeveloperTask]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM developer_tasks WHERE state=? AND push_requested=1 AND pushed=0", (DeveloperTaskState.READY.value,)).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DeveloperTask:
        return DeveloperTask(
            id=row["id"], chat_id=row["chat_id"], description=row["description"], slug=row["slug"], branch=row["branch"],
            state=DeveloperTaskState(row["state"]), attempts=row["attempts"], max_attempts=row["max_attempts"],
            plan=row["plan"], summary=row["summary"], changed_files=tuple(json.loads(row["changed_files"])),
            test_output=row["test_output"], error=row["error"], log_path=row["log_path"],
            cancel_requested=bool(row["cancel_requested"]), push_requested=bool(row["push_requested"]),
            pushed=bool(row["pushed"]), report_sent=bool(row["report_sent"]),
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        )
