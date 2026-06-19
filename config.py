import json
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    whitelist_user_ids: frozenset[int]
    max_price: float
    price_currency: str
    poll_interval: int
    game_id: str
    state_file: str
    runtime_config_file: str

def parse_whitelist(raw: str) -> frozenset[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return frozenset(ids)

def load_runtime_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = ("max_price", "max_price_usd", "price_currency", "poll_interval")
        return {k: data[k] for k in allowed if k in data}
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return {}

def save_runtime_overrides(
    path: Path,
    max_price: float,
    price_currency: str,
    poll_interval: int,
) -> None:
    path.write_text(
        json.dumps(
            {
                "max_price": max_price,
                "price_currency": price_currency,
                "poll_interval": poll_interval,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

def resolve_price_settings(overrides: dict) -> tuple[float, str]:
    currency = str(
        overrides.get("price_currency", os.getenv("PRICE_CURRENCY", "EUR"))
    ).upper()
    if "max_price" in overrides:
        return float(overrides["max_price"]), currency
    if "max_price_usd" in overrides:
        return float(overrides["max_price_usd"]), "USD"
    if os.getenv("MAX_PRICE"):
        return float(os.getenv("MAX_PRICE", "0.00450")), currency
    if currency == "USD" or os.getenv("MAX_PRICE_USD"):
        return float(os.getenv("MAX_PRICE_USD", "0.005")), "USD"
    return float(os.getenv("MAX_PRICE_EUR", "0.00450")), "EUR"

def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    whitelist_raw = os.getenv("WHITELIST_USER_IDS", "").strip()
    if not token or not chat_id:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required. "
            "Copy .env.example to .env and set the values."
        )
    whitelist = parse_whitelist(whitelist_raw)
    if not whitelist:
        raise ValueError("WHITELIST_USER_IDS must contain at least one Telegram user ID.")
    if chat_id.lstrip("-").isdigit():
        whitelist = whitelist | {int(chat_id)}
    runtime_config_file = os.getenv("RUNTIME_CONFIG_FILE", "runtime_config.json")
    overrides = load_runtime_overrides(Path(runtime_config_file))
    max_price, price_currency = resolve_price_settings(overrides)
    poll_interval = int(overrides.get("poll_interval", os.getenv("POLL_INTERVAL", "60")))
    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        whitelist_user_ids=whitelist,
        max_price=max_price,
        price_currency=price_currency,
        poll_interval=max(15, poll_interval),
        game_id=os.getenv("GAME_ID", "70"),
        state_file=os.getenv("STATE_FILE", "state.json"),
        runtime_config_file=runtime_config_file,
    )
