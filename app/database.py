from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ozon_ai_os.sqlite3"


def init_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        connection.commit()


def log_event(event_type: str, details: str) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO events (created_at, event_type, details) VALUES (?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                event_type,
                details[:4000],
            ),
        )
        connection.commit()
