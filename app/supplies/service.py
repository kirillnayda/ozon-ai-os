from __future__ import annotations

from dataclasses import replace
import json
from uuid import uuid4

from app.core.security import WritePolicy, idempotency_key
from app.ozon import endpoints
from app.ozon.transport import JsonTransport
from app.storage.models import OperationState, SupplyOperation
from app.storage.repositories import AuditRepository, OperationRepository
from app.supplies.models import SupplyIntent


class SupplyWorkflow:
    def __init__(self, transport: JsonTransport, operations: OperationRepository, audit: AuditRepository, policy: WritePolicy) -> None:
        self.transport, self.operations, self.audit, self.policy = transport, operations, audit, policy

    def prepare(self, chat_id: int, intent: SupplyIntent) -> SupplyOperation:
        payload = {"destination": intent.destination, "lines": [{"offer_id": x.offer_id, "quantity": x.quantity, "units_per_box": x.units_per_box, "boxes": x.boxes} for x in intent.lines]}
        key = idempotency_key(chat_id, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        existing = self.operations.get_by_key(key)
        if existing:
            return existing
        operation = SupplyOperation(str(uuid4()), key, chat_id, OperationState.AWAITING_CONFIRMATION, intent.destination, json.dumps(payload, ensure_ascii=False))
        self.operations.add(operation)
        self.audit.record(str(chat_id), "supply.prepare", "awaiting_confirmation", operation.id)
        return operation

    async def confirm(self, chat_id: int, operation_id: str) -> SupplyOperation:
        operation = self.operations.get(operation_id)
        if not operation or operation.chat_id != chat_id:
            raise PermissionError("Операция не найдена")
        if operation.state != OperationState.AWAITING_CONFIRMATION:
            return operation
        self.policy.require(chat_id, confirmed=True)
        operation = replace(operation, state=OperationState.CREATING)
        self.operations.save(operation)
        payload = json.loads(operation.payload_json)
        # Payload разрешается только mock transport, пока production-контракт не подтверждён.
        response = await self.transport.request(endpoints.DRAFT_DIRECT_CREATE, payload, allow_mutation=True)
        external_id = str(response.get("operation_id") or response.get("draft_id") or "")
        operation = replace(operation, state=OperationState.CREATED, external_id=external_id)
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.create", "created", operation.id)
        return operation

    async def poll_unfinished(self) -> None:
        for operation in self.operations.unfinished():
            if operation.state == OperationState.CREATING and operation.external_id:
                await self.transport.request(endpoints.SUPPLY_CREATE_STATUS, {"operation_id": operation.external_id})

    async def create_cargoes_and_labels_mockable(self, chat_id: int, operation_id: str) -> tuple[SupplyOperation, bytes | None]:
        """Продолжает подтверждённую операцию; production остаётся fail-closed до DTO verification."""
        operation = self.operations.get(operation_id)
        if not operation or operation.chat_id != chat_id:
            raise PermissionError("Операция не найдена")
        self.policy.require(chat_id, confirmed=True)
        if operation.state != OperationState.CREATED:
            return operation, None
        payload = json.loads(operation.payload_json)
        cargo = await self.transport.request(endpoints.CARGOES_CREATE, {"supply_id": operation.external_id, "cargoes": payload["lines"]}, allow_mutation=True)
        cargo_operation_id = str(cargo.get("operation_id") or "")
        operation = replace(operation, state=OperationState.CARGOES_CREATING)
        self.operations.save(operation)
        await self.transport.request(endpoints.CARGOES_STATUS, {"operation_id": cargo_operation_id})
        label = await self.transport.request(endpoints.LABELS_CREATE, {"supply_id": operation.external_id}, allow_mutation=True)
        label_operation_id = str(label.get("operation_id") or "")
        operation = replace(operation, state=OperationState.LABELS_CREATING)
        self.operations.save(operation)
        label_status = await self.transport.request(endpoints.LABELS_GET, {"operation_id": label_operation_id})
        file_guid = str(label_status.get("file_guid") or "")
        if not file_guid:
            return operation, None
        file_endpoint = replace(endpoints.LABELS_FILE, path=endpoints.LABELS_FILE.path.format(file_guid=file_guid))
        pdf = await self.transport.download(file_endpoint)
        if not pdf.startswith(b"%PDF"):
            raise ValueError("Файл этикеток не является PDF")
        operation = replace(operation, state=OperationState.COMPLETED)
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.labels", "completed", operation.id)
        return operation, pdf
