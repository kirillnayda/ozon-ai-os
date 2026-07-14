ALTER TABLE supply_operations ADD COLUMN draft_operation_id TEXT;
ALTER TABLE supply_operations ADD COLUMN draft_id TEXT;
ALTER TABLE supply_operations ADD COLUMN supply_operation_id TEXT;
ALTER TABLE supply_operations ADD COLUMN cargo_operation_id TEXT;
ALTER TABLE supply_operations ADD COLUMN label_operation_id TEXT;
ALTER TABLE supply_operations ADD COLUMN file_guid TEXT;
ALTER TABLE supply_operations ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS supply_pdf_outbox (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_supply_pdf_outbox_state ON supply_pdf_outbox(state);
