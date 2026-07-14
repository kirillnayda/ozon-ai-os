from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class OperationState(StrEnum):
    DRAFT_CREATED = "draft_created"
    DRAFT = "draft_created"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CREATING = "creating"
    WAITING_FOR_OZON = "waiting_for_ozon"
    SUPPLY_CREATED = "supply_created"
    CREATED = "supply_created"
    CARGOES_CREATING = "waiting_for_ozon"
    LABELS_REQUESTED = "labels_requested"
    LABELS_CREATING = "labels_requested"
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
    draft_operation_id: str | None = None
    draft_id: str | None = None
    supply_operation_id: str | None = None
    cargo_operation_id: str | None = None
    label_operation_id: str | None = None
    file_guid: str | None = None
    retry_count: int = 0


@dataclass(frozen=True)
class SupplyDialog:
    chat_id: int
    step: str
    data: dict[str, Any]


@dataclass(frozen=True)
class PdfOutboxItem:
    id: str
    operation_id: str
    chat_id: int
    path: str
    state: str
    attempts: int = 0
