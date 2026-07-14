from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OperationState(StrEnum):
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    CREATING = "creating"
    CREATED = "created"
    CARGOES_CREATING = "cargoes_creating"
    LABELS_CREATING = "labels_creating"
    LABELS_READY = "labels_ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class StockSnapshot:
    captured_at: datetime
    sku: int
    offer_id: str
    cluster_id: int
    cluster_name: str
    warehouse_id: int
    warehouse_name: str
    present: int
    reserved: int = 0


@dataclass(frozen=True)
class DemandSnapshot:
    captured_at: datetime
    sku: int
    offer_id: str
    cluster_id: int
    units: int
    period_days: int


@dataclass(frozen=True)
class SupplyOperation:
    id: str
    idempotency_key: str
    chat_id: int
    state: OperationState
    destination: str
    payload_json: str
    external_id: str | None = None
    error: str | None = None
