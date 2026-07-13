from __future__ import annotations

from dataclasses import dataclass
from html import escape
import hashlib
import hmac

from app.core.errors import ConfirmationRequired, LiveModeRequired


def html_escape(value: object) -> str:
    return escape(str(value), quote=True)


def redact(value: str, secrets: tuple[str, ...]) -> str:
    result = value
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


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

