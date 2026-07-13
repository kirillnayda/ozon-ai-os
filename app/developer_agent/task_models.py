from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class DeveloperTaskState(StrEnum):
    QUEUED = "queued"
    ANALYSING = "analysing"
    CODING = "coding"
    TESTING = "testing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATES = (
    DeveloperTaskState.ANALYSING,
    DeveloperTaskState.CODING,
    DeveloperTaskState.TESTING,
)
TERMINAL_STATES = (
    DeveloperTaskState.READY,
    DeveloperTaskState.FAILED,
    DeveloperTaskState.CANCELLED,
)


@dataclass(frozen=True)
class DeveloperTask:
    id: int
    chat_id: int
    description: str
    slug: str
    branch: str
    state: DeveloperTaskState
    attempts: int = 0
    max_attempts: int = 2
    plan: str = ""
    summary: str = ""
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    test_output: str = ""
    error: str = ""
    log_path: str = ""
    cancel_requested: bool = False
    push_requested: bool = False
    pushed: bool = False
    report_sent: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CodexRunResult:
    exit_code: int
    last_message: str
    log_path: str
    timed_out: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class TestRunResult:
    exit_code: int
    output: str
    timed_out: bool = False

