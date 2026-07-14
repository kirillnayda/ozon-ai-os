from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
import sqlite3
import json

from app.storage.models import DemandSnapshot, OperationState, StockSnapshot, SupplyDialog, SupplyOperation


class SQLiteStorage:
    def __init__(self, path: Path, migrations_dir: Path | None = None) -> None:
        self.path = path
        self.migrations_dir = migrations_dir or Path(__file__).with_name("migrations")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                if migration.name in applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (migration.name, datetime.now(timezone.utc).isoformat()),
                )

    def record(self, actor: str, action: str, result: str, details: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(created_at, actor, action, result, details) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), actor, action, result, details[:4000]),
            )

    def replace_stocks(self, snapshots: list[StockSnapshot]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM stock_snapshots")
            connection.executemany(
                "INSERT INTO stock_snapshots(captured_at,sku,offer_id,cluster_id,cluster_name,warehouse_id,warehouse_name,present,reserved) VALUES (?,?,?,?,?,?,?,?,?)",
                [(s.captured_at.isoformat(), s.sku, s.offer_id, s.cluster_id, s.cluster_name, s.warehouse_id, s.warehouse_name, s.present, s.reserved) for s in snapshots],
            )

    def replace_demand(self, snapshots: list[DemandSnapshot]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM demand_snapshots")
            connection.executemany(
                "INSERT INTO demand_snapshots(captured_at,sku,offer_id,cluster_id,units,period_days) VALUES (?,?,?,?,?,?)",
                [(s.captured_at.isoformat(), s.sku, s.offer_id, s.cluster_id, s.units, s.period_days) for s in snapshots],
            )

    def latest_stocks(self) -> list[StockSnapshot]:
        with self._connect() as connection:
            return [StockSnapshot(datetime.fromisoformat(r["captured_at"]), r["sku"], r["offer_id"], r["cluster_id"], r["cluster_name"], r["warehouse_id"], r["warehouse_name"], r["present"], r["reserved"]) for r in connection.execute("SELECT * FROM stock_snapshots")]

    def latest_demand(self) -> list[DemandSnapshot]:
        with self._connect() as connection:
            return [DemandSnapshot(datetime.fromisoformat(r["captured_at"]), r["sku"], r["offer_id"], r["cluster_id"], r["units"], r["period_days"]) for r in connection.execute("SELECT * FROM demand_snapshots")]

    def add(self, operation: SupplyOperation) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("INSERT INTO supply_operations VALUES (?,?,?,?,?,?,?,?,?,?)", (operation.id, operation.idempotency_key, operation.chat_id, operation.state.value, operation.destination, operation.payload_json, operation.external_id, operation.error, now, now))

    def get(self, operation_id: str) -> SupplyOperation | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM supply_operations WHERE id=?", (operation_id,)).fetchone()
        return self._operation(row) if row else None

    def get_by_key(self, key: str) -> SupplyOperation | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM supply_operations WHERE idempotency_key=?", (key,)).fetchone()
        return self._operation(row) if row else None

    def save(self, operation: SupplyOperation) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE supply_operations SET state=?, external_id=?, error=?, updated_at=? WHERE id=?", (operation.state.value, operation.external_id, operation.error, datetime.now(timezone.utc).isoformat(), operation.id))

    def unfinished(self) -> list[SupplyOperation]:
        terminal = (OperationState.COMPLETED.value, OperationState.CANCELLED.value, OperationState.FAILED.value)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM supply_operations WHERE state NOT IN (?, ?, ?)", terminal).fetchall()
        return [self._operation(row) for row in rows]

    def get_dialog(self, chat_id: int) -> SupplyDialog | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM supply_dialogs WHERE chat_id=?", (chat_id,)).fetchone()
        return SupplyDialog(row["chat_id"], row["step"], json.loads(row["data_json"])) if row else None

    def save_dialog(self, dialog: SupplyDialog) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO supply_dialogs(chat_id, step, data_json, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET step=excluded.step, data_json=excluded.data_json, updated_at=excluded.updated_at",
                (dialog.chat_id, dialog.step, json.dumps(dialog.data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )

    def delete_dialog(self, chat_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM supply_dialogs WHERE chat_id=?", (chat_id,))

    @staticmethod
    def _operation(row: sqlite3.Row) -> SupplyOperation:
        return SupplyOperation(row["id"], row["idempotency_key"], row["chat_id"], OperationState(row["state"]), row["destination"], row["payload_json"], row["external_id"], row["error"])
