CREATE TABLE IF NOT EXISTS supply_dialogs (
    chat_id INTEGER PRIMARY KEY,
    step TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

UPDATE supply_operations SET state = 'draft_created' WHERE state = 'draft';
UPDATE supply_operations SET state = 'awaiting_confirmation' WHERE state = 'confirmed';
UPDATE supply_operations SET state = 'supply_created' WHERE state = 'created';
UPDATE supply_operations SET state = 'waiting_for_ozon' WHERE state = 'cargoes_creating';
UPDATE supply_operations SET state = 'labels_requested' WHERE state = 'labels_creating';
