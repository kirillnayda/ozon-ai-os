from __future__ import annotations

from dataclasses import dataclass
from html import escape
import hashlib
import hmac
import re
from typing import Any

from app.core.errors import ConfirmationRequired, LiveModeRequired


def html_escape(value: object) -> str:
    return escape(str(value), quote=True)


def redact(value: str, secrets: tuple[str, ...]) -> str:
    result = value
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def safe_error_metadata(value: Any) -> dict[str, Any]:
    """Retain error JSON shape and field-like identifiers, never scalar values."""
    identifiers: set[str] = set()
    numeric_constraints: set[str] = set()

    def sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): sanitize(child) for key, child in item.items()}
        if isinstance(item, list):
            return [sanitize(child) for child in item[:3]]
        if isinstance(item, str):
            identifiers.update(re.findall(r"\b[a-z][a-z0-9_]{1,63}\b", item))
            numeric_constraints.update(re.findall(r"(?<![A-Za-z0-9_-])\d+(?:\.\d+)?(?![A-Za-z0-9_-])", item))
            return "sample"
        if isinstance(item, bool):
            return item
        if isinstance(item, int):
            return 1
        if isinstance(item, float):
            return 1.5
        return item

    shape = sanitize(value)
    return {"response_shape": shape, "field_identifiers": sorted(identifiers), "numeric_constraints": sorted(numeric_constraints, key=float)}


@dataclass(frozen=True)
class WritePolicy:
    live_mode: bool
    allowed_chat_id: int

    def require(self, chat_id: int, confirmed: bool) -> None:
        if chat_id != self.allowed_chat_id:
            raise PermissionError("Чат не авторизован")
        if not self.live_mode:
            raise LiveModeRequired("LIVE_MODE=false: реальные операции запрещены")
        if not confirmed:
            raise ConfirmationRequired("Требуется явное подтверждение")


def idempotency_key(*parts: object) -> str:
    raw = "\x1f".join(str(part).strip() for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())
