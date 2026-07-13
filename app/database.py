"""Совместимый фасад старого API базы данных."""
from pathlib import Path

from app.storage.sqlite import SQLiteStorage

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "ozon_ai_os.sqlite3"
storage = SQLiteStorage(DB_PATH)


def init_database() -> None:
    storage.migrate()


def log_event(event_type: str, details: str) -> None:
    storage.record("system", event_type, "recorded", details)
