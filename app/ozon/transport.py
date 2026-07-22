from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx

from app.core.errors import ContractNotVerified, ExternalServiceError
from app.core.security import safe_error_metadata
from app.ozon.endpoints import Endpoint


class JsonTransport(Protocol):
    async def request(self, endpoint: Endpoint, payload: dict[str, Any], *, allow_mutation: bool = False) -> dict[str, Any]: ...
    async def download(self, endpoint: Endpoint) -> bytes: ...
    async def close(self) -> None: ...


class OzonHttpTransport:
    def __init__(self, client_id: str, api_key: str, timeout: float = 30, retries: int = 3) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api-seller.ozon.ru",
            headers={"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
            timeout=httpx.Timeout(timeout, connect=10),
        )
        self._retries = retries

    async def request(self, endpoint: Endpoint, payload: dict[str, Any], *, allow_mutation: bool = False) -> dict[str, Any]:
        if endpoint.mutating and not allow_mutation:
            raise PermissionError("Изменяющий запрос не разрешён")
        if endpoint.mutating and not endpoint.contract_verified:
            raise ContractNotVerified(f"Production-контракт {endpoint.path} требует проверки в кабинете")
        response = await self._send(lambda: self._client.post(endpoint.path, json=payload))
        try:
            data = response.json()
        except ValueError as exc:
            raise ExternalServiceError("Ozon вернул некорректный JSON") from exc
        if not isinstance(data, dict):
            raise ExternalServiceError("Ozon вернул неожиданный формат ответа")
        return data

    async def download(self, endpoint: Endpoint) -> bytes:
        response = await self._send(lambda: self._client.get(endpoint.path))
        if "pdf" not in response.headers.get("content-type", "").lower():
            raise ExternalServiceError("Ozon не вернул PDF")
        return response.content

    async def _send(self, call: Callable[[], Awaitable[httpx.Response]]) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                response = await call()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self._retries:
                    raise ExternalServiceError("Ozon API временно недоступен") from exc
                await asyncio.sleep(min(2 ** attempt, 30) + random.uniform(0, 0.25))
                continue
            if response.status_code < 400:
                return response
            if response.status_code in {401, 403}:
                raise ExternalServiceError("Ozon отклонил авторизацию", status_code=response.status_code)
            if response.status_code in {409, 429} or response.status_code >= 500:
                if attempt < self._retries:
                    delay = min(float(response.headers.get("Retry-After", 2 ** attempt)), 30) + random.uniform(0, 0.25)
                    await asyncio.sleep(delay)
                    continue
            try:
                error_data = response.json()
            except ValueError:
                error_data = None
            metadata = safe_error_metadata(error_data) if isinstance(error_data, (dict, list)) else {}
            raise ExternalServiceError(f"Ozon API вернул HTTP {response.status_code}", status_code=response.status_code, metadata=metadata)
        raise ExternalServiceError("Исчерпаны попытки обращения к Ozon")

    async def close(self) -> None:
        await self._client.aclose()


class MockTransport:
    def __init__(self, responses: dict[str, list[dict[str, Any] | bytes]]) -> None:
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def request(self, endpoint: Endpoint, payload: dict[str, Any], *, allow_mutation: bool = False) -> dict[str, Any]:
        if endpoint.mutating and not allow_mutation:
            raise PermissionError("Изменяющий запрос не разрешён")
        self.calls.append((endpoint.path, payload))
        value = self.responses[endpoint.path].pop(0)
        if not isinstance(value, dict):
            raise TypeError("Ожидался JSON mock")
        return value

    async def download(self, endpoint: Endpoint) -> bytes:
        value = self.responses[endpoint.path].pop(0)
        if not isinstance(value, bytes):
            raise TypeError("Ожидался bytes mock")
        return value

    async def close(self) -> None:
        return None


class SupplyTestTransport:
    """Deterministic offline contract double; never performs network I/O."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._counter = 0

    async def request(self, endpoint: Endpoint, payload: dict[str, Any], *, allow_mutation: bool = False) -> dict[str, Any]:
        if endpoint.mutating and not allow_mutation:
            raise PermissionError("Изменяющий тестовый запрос не разрешён")
        self.calls.append((endpoint.path, payload))
        self._counter += 1
        if "label/get" in endpoint.path:
            return {"status": "ready", "file_guid": "test-label"}
        if endpoint.path.endswith("/create/info") or endpoint.path.endswith("/create/status"):
            return {"status": "success", "supply_id": "test-supply"}
        if endpoint.path.endswith("/create"):
            return {"operation_id": f"test-operation-{self._counter}"}
        return {"status": "success"}

    async def download(self, endpoint: Endpoint) -> bytes:
        self.calls.append((endpoint.path, {}))
        return b"%PDF-1.7\n% Ozon AI OS test cargo label\n"

    async def close(self) -> None:
        return None
