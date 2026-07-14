from __future__ import annotations

from dataclasses import replace
import asyncio
import json
from time import monotonic
from uuid import uuid4

from app.core.security import WritePolicy, idempotency_key
from app.ozon import endpoints
from app.ozon.transport import JsonTransport
from app.storage.models import OperationState, SupplyOperation
from app.storage.repositories import AuditRepository, OperationRepository
from app.supplies.models import SupplyIntent


class SupplyWorkflow:
    def __init__(self, transport: JsonTransport, operations: OperationRepository, audit: AuditRepository, policy: WritePolicy, *, test_mode: bool = False, timeout_seconds: float = 30, poll_interval: float = 1) -> None:
        self.transport, self.operations, self.audit, self.policy = transport, operations, audit, policy
        self.test_mode, self.timeout_seconds, self.poll_interval = test_mode, timeout_seconds, poll_interval

    def prepare(self, chat_id: int, intent: SupplyIntent, selection: dict[str, str] | None = None) -> SupplyOperation:
        payload = {"destination": intent.destination, "lines": [{"offer_id": x.offer_id, "quantity": x.quantity, "units_per_box": x.units_per_box, "boxes": x.boxes} for x in intent.lines], **(selection or {})}
        key = idempotency_key(chat_id, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        existing = self.operations.get_by_key(key)
        if existing:
            return existing
        operation = SupplyOperation(str(uuid4()), key, chat_id, OperationState.DRAFT_CREATED, intent.destination, json.dumps(payload, ensure_ascii=False))
        self.operations.add(operation)
        operation = replace(operation, state=OperationState.AWAITING_CONFIRMATION)
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.prepare", "awaiting_confirmation", operation.id)
        return operation

    def cancel(self, chat_id: int, operation_id: str) -> SupplyOperation:
        operation = self._owned_operation(chat_id, operation_id)
        if operation.state != OperationState.AWAITING_CONFIRMATION:
            return operation
        operation = replace(operation, state=OperationState.CANCELLED)
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.cancel", "cancelled", operation.id)
        return operation

    def edit_line(self, chat_id: int, operation_id: str, offer_id: str, quantity: int, units_per_box: int) -> SupplyOperation:
        operation = self._owned_operation(chat_id, operation_id)
        if operation.state != OperationState.AWAITING_CONFIRMATION:
            raise ValueError("Редактировать можно только неподтверждённый черновик")
        if quantity <= 0 or units_per_box <= 0 or quantity % units_per_box:
            raise ValueError("Количество должно быть положительным и делиться на размер коробки")
        payload = json.loads(operation.payload_json)
        replacement = {"offer_id": offer_id, "quantity": quantity, "units_per_box": units_per_box, "boxes": quantity // units_per_box}
        lines = payload["lines"]
        for index, line in enumerate(lines):
            if line["offer_id"] == offer_id:
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
        operation = replace(operation, payload_json=json.dumps(payload, ensure_ascii=False))
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.edit", "updated", operation.id)
        return operation

    def remove_line(self, chat_id: int, operation_id: str, offer_id: str) -> SupplyOperation:
        operation = self._owned_operation(chat_id, operation_id)
        if operation.state != OperationState.AWAITING_CONFIRMATION:
            raise ValueError("Редактировать можно только неподтверждённый черновик")
        payload = json.loads(operation.payload_json)
        payload["lines"] = [line for line in payload["lines"] if line["offer_id"] != offer_id]
        if not payload["lines"]:
            raise ValueError("В поставке должна остаться хотя бы одна позиция")
        operation = replace(operation, payload_json=json.dumps(payload, ensure_ascii=False))
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.edit", "removed", operation.id)
        return operation

    async def confirm(self, chat_id: int, operation_id: str) -> SupplyOperation:
        operation = self._owned_operation(chat_id, operation_id)
        if operation.state not in {OperationState.AWAITING_CONFIRMATION, OperationState.CREATING, OperationState.WAITING_FOR_OZON}:
            return operation
        self._authorize(chat_id)
        payload = json.loads(operation.payload_json)
        # Payload разрешается только mock transport, пока production-контракт не подтверждён.
        try:
            if not operation.draft_operation_id:
                operation = replace(operation, state=OperationState.CREATING)
                self.operations.save(operation)
                response = await self.transport.request(endpoints.DRAFT_DIRECT_CREATE, payload, allow_mutation=True)
                draft_operation_id = str(response.get("operation_id") or response.get("draft_id") or "")
                operation = replace(operation, state=OperationState.WAITING_FOR_OZON, external_id=draft_operation_id, draft_operation_id=draft_operation_id)
                self.operations.save(operation)
            draft = await self._poll(endpoints.DRAFT_INFO, {"operation_id": operation.draft_operation_id})
            draft_id = str(draft.get("draft_id") or operation.draft_id or operation.draft_operation_id or "")
            operation = replace(operation, draft_id=draft_id)
            self.operations.save(operation)
            if not operation.supply_operation_id:
                supply = await self.transport.request(endpoints.SUPPLY_CREATE, {"draft_id": draft_id}, allow_mutation=True)
                supply_operation_id = str(supply.get("operation_id") or supply.get("supply_id") or "")
                operation = replace(operation, supply_operation_id=supply_operation_id)
                self.operations.save(operation)
            status = await self._poll(endpoints.SUPPLY_CREATE_STATUS, {"operation_id": operation.supply_operation_id})
        except Exception as exc:
            self._fail(chat_id, operation, exc)
            raise
        external_id = str(status.get("supply_id") or operation.supply_operation_id)
        operation = replace(operation, state=OperationState.SUPPLY_CREATED, external_id=external_id)
        self.operations.save(operation)
        self.audit.record(str(chat_id), "supply.create", "created", operation.id)
        return operation

    async def poll_unfinished(self) -> list[tuple[int, str, bytes]]:
        recovered: list[tuple[int, str, bytes]] = []
        for operation in self.operations.unfinished():
            if operation.state in {OperationState.CREATING, OperationState.WAITING_FOR_OZON}:
                try:
                    operation = await self.confirm(operation.chat_id, operation.id)
                except Exception:
                    continue
            if operation.state in {OperationState.SUPPLY_CREATED, OperationState.LABELS_REQUESTED, OperationState.LABELS_READY}:
                try:
                    completed, pdf = await self.create_cargoes_and_labels_mockable(operation.chat_id, operation.id)
                    if completed.state == OperationState.COMPLETED and pdf:
                        recovered.append((operation.chat_id, operation.id, pdf))
                except Exception:
                    continue
        return recovered

    async def create_cargoes_and_labels_mockable(self, chat_id: int, operation_id: str) -> tuple[SupplyOperation, bytes | None]:
        """Продолжает подтверждённую операцию; production остаётся fail-closed до DTO verification."""
        operation = self._owned_operation(chat_id, operation_id)
        self._authorize(chat_id)
        if operation.state not in {OperationState.SUPPLY_CREATED, OperationState.WAITING_FOR_OZON, OperationState.LABELS_REQUESTED, OperationState.LABELS_READY}:
            return operation, None
        payload = json.loads(operation.payload_json)
        try:
            if not operation.cargo_operation_id:
                cargo = await self.transport.request(endpoints.CARGOES_CREATE, {"supply_id": operation.external_id, "cargoes": payload["lines"]}, allow_mutation=True)
                operation = replace(operation, state=OperationState.WAITING_FOR_OZON, cargo_operation_id=str(cargo.get("operation_id") or ""))
                self.operations.save(operation)
            await self._poll(endpoints.CARGOES_STATUS, {"operation_id": operation.cargo_operation_id})
            if not operation.label_operation_id:
                label = await self.transport.request(endpoints.LABELS_CREATE, {"supply_id": operation.external_id}, allow_mutation=True)
                operation = replace(operation, state=OperationState.LABELS_REQUESTED, label_operation_id=str(label.get("operation_id") or ""))
                self.operations.save(operation)
            label_status = await self._poll(endpoints.LABELS_GET, {"operation_id": operation.label_operation_id})
            file_guid = str(label_status.get("file_guid") or operation.file_guid or "")
            if not file_guid:
                return operation, None
            operation = replace(operation, state=OperationState.LABELS_READY, file_guid=file_guid)
            self.operations.save(operation)
            file_endpoint = replace(endpoints.LABELS_FILE, path=endpoints.LABELS_FILE.path.format(file_guid=file_guid))
            pdf = await self.transport.download(file_endpoint)
            if not pdf.startswith(b"%PDF"):
                raise ValueError("Файл этикеток не является PDF")
        except Exception as exc:
            self._fail(chat_id, operation, exc)
            raise
        operation = replace(operation, state=OperationState.COMPLETED)
        self.operations.save(operation)
        self.operations.queue_pdf(operation.id, chat_id, pdf)
        self.audit.record(str(chat_id), "supply.labels", "completed", operation.id)
        return operation, pdf

    def _owned_operation(self, chat_id: int, operation_id: str) -> SupplyOperation:
        operation = self.operations.get(operation_id)
        if not operation or operation.chat_id != chat_id:
            raise PermissionError("Операция не найдена")
        return operation

    def _authorize(self, chat_id: int) -> None:
        if self.test_mode:
            if chat_id != self.policy.allowed_chat_id:
                raise PermissionError("Чат не авторизован")
            return
        self.policy.require(chat_id, confirmed=True)

    async def _poll(self, endpoint, payload: dict) -> dict:
        deadline = monotonic() + self.timeout_seconds
        while True:
            response = await self.transport.request(endpoint, payload)
            status = str(response.get("status") or "").lower()
            if status in {"success", "ready", "completed", "done"} or response.get("file_guid"):
                return response
            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError("Ozon operation failed")
            if monotonic() >= deadline:
                raise TimeoutError("Ozon operation timeout")
            await asyncio.sleep(self.poll_interval)

    def _fail(self, chat_id: int, operation: SupplyOperation, exc: Exception) -> SupplyOperation:
        # Текст исключения может содержать данные внешнего сервиса; сохраняем только безопасный тип.
        failed = replace(operation, state=OperationState.FAILED, error=type(exc).__name__, retry_count=operation.retry_count + 1)
        self.operations.save(failed)
        self.audit.record(str(chat_id), "supply.workflow", "failed", failed.id)
        return failed
