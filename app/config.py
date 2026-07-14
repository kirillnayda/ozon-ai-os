from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os

from dotenv import load_dotenv

from app.core.errors import ConfigurationError

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Не задана обязательная настройка {name}")
    return value


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} должен быть целым числом") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} должен быть от {minimum} до {maximum}")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default).lower()).strip().lower()
    if raw not in {"true", "false"}:
        raise ConfigurationError(f"{name} должен быть true или false")
    return raw == "true"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    ozon_client_id: str
    ozon_api_key: str
    report_hour: int
    timezone: str
    live_mode: bool
    supplier_name: str
    supply_lead_days: int
    min_stock_days: int
    comfort_stock_days: int
    critical_stock_days: int
    purchase_group_size: int
    github_repository: str
    current_version: str
    update_check_minutes: int


def load_settings(env_file: Path = ENV_FILE) -> Settings:
    load_dotenv(env_file, override=False)
    try:
        chat_id = int(_required("TELEGRAM_CHAT_ID"))
    except ValueError as exc:
        raise ConfigurationError("TELEGRAM_CHAT_ID должен быть числом") from exc
    timezone_name = os.getenv("TIMEZONE", "Europe/Moscow").strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"Неизвестная временная зона: {timezone_name}") from exc

    critical = _integer("CRITICAL_STOCK_DAYS", 7, 0, 365)
    minimum = _integer("MIN_STOCK_DAYS", 30, 1, 365)
    comfort = _integer("COMFORT_STOCK_DAYS", 45, 1, 730)
    if not critical <= minimum <= comfort:
        raise ConfigurationError("Требуется CRITICAL_STOCK_DAYS <= MIN_STOCK_DAYS <= COMFORT_STOCK_DAYS")

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=chat_id,
        ozon_client_id=_required("OZON_CLIENT_ID"),
        ozon_api_key=_required("OZON_API_KEY"),
        report_hour=_integer("REPORT_HOUR", 9, 0, 23),
        timezone=timezone_name,
        live_mode=_boolean("LIVE_MODE", False),
        supplier_name=os.getenv("SUPPLIER_NAME", "НБХОЗ").strip() or "НБХОЗ",
        supply_lead_days=_integer("SUPPLY_LEAD_DAYS", 7, 0, 365),
        min_stock_days=minimum,
        comfort_stock_days=comfort,
        critical_stock_days=critical,
        purchase_group_size=_integer("PURCHASE_GROUP_SIZE", 6, 1, 100),
        github_repository=os.getenv("GITHUB_REPOSITORY", "").strip(),
        current_version=os.getenv("CURRENT_VERSION", "1.1.0").strip(),
        update_check_minutes=_integer("UPDATE_CHECK_MINUTES", 60, 5, 10080),
    )
