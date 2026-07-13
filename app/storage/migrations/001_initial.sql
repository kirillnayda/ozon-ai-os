CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_events_created_at ON events(created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_created_at ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS stock_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    sku INTEGER NOT NULL,
    offer_id TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    cluster_name TEXT NOT NULL,
    warehouse_id INTEGER NOT NULL,
    warehouse_name TEXT NOT NULL,
    present INTEGER NOT NULL,
    reserved INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_stock_sku_cluster ON stock_snapshots(sku, cluster_id);

CREATE TABLE IF NOT EXISTS demand_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    sku INTEGER NOT NULL,
    offer_id TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    units INTEGER NOT NULL,
    period_days INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_demand_sku_cluster ON demand_snapshots(sku, cluster_id);

CREATE TABLE IF NOT EXISTS supply_operations (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    destination TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    external_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_supply_state ON supply_operations(state);

CREATE TABLE IF NOT EXISTS update_requests (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    state TEXT NOT NULL,
    requested_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT
);

