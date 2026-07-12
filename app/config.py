from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задана обязательная настройка {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть целым числом") from exc


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


def load_settings() -> Settings:
    chat_id_raw = _required("TELEGRAM_CHAT_ID")
    try:
        chat_id = int(chat_id_raw)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_CHAT_ID должен быть числом") from exc

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=chat_id,
        ozon_client_id=_required("OZON_CLIENT_ID"),
        ozon_api_key=_required("OZON_API_KEY"),
        report_hour=_int("REPORT_HOUR", 9),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
        live_mode=os.getenv("LIVE_MODE", "false").strip().lower() == "true",
        supplier_name=os.getenv("SUPPLIER_NAME", "НБХОЗ").strip(),
        supply_lead_days=_int("SUPPLY_LEAD_DAYS", 7),
        min_stock_days=_int("MIN_STOCK_DAYS", 30),
        comfort_stock_days=_int("COMFORT_STOCK_DAYS", 45),
        critical_stock_days=_int("CRITICAL_STOCK_DAYS", 7),
        purchase_group_size=_int("PURCHASE_GROUP_SIZE", 6),
    )
