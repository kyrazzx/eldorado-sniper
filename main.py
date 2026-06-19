import json
import logging
import time
from pathlib import Path
from config import Settings, load_settings
from eldorado import EldoradoClient, RobuxOffer
from runtime import SharedState
from telegram_bot import TelegramBot
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("eldorado-sniper")

def load_state(path: Path, price_currency: str) -> dict[str, float]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored_currency = str(data.get("price_currency", "USD")).upper()
        if stored_currency != price_currency.upper():
            return {}
        return {str(k): float(v) for k, v in data.get("known_prices", {}).items()}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}

def save_state(path: Path, known_prices: dict[str, float], price_currency: str) -> None:
    path.write_text(
        json.dumps(
            {"price_currency": price_currency.upper(), "known_prices": known_prices},
            indent=2,
        ),
        encoding="utf-8",
    )

def should_notify(
    offer: RobuxOffer,
    known_prices: dict[str, float],
    threshold: float,
    price_currency: str,
) -> str | None:
    price = offer.comparison_price(price_currency)
    if price > threshold:
        return None
    previous = known_prices.get(offer.id)
    if previous is None:
        return "new offer"
    if price < previous - 1e-9:
        return f"price drop ({previous:.5f} -> {price:.5f} {price_currency})"
    return None

def run_check(
    client: EldoradoClient,
    bot: TelegramBot,
    runtime: SharedState,
    known_prices: dict[str, float],
    price_currency: str,
    *,
    seed_only: bool = False,
) -> dict[str, float]:
    offers = client.fetch_offers()
    runtime.update_offers(offers)
    if not offers:
        log.warning("No offers returned")
        return known_prices
    best = offers[0]
    _, _, threshold, _, _ = runtime.snapshot()
    log.info(
        "Best price: %s per Robux (%s), %d offers",
        best.format_prices(),
        best.seller,
        len(offers),
    )
    if seed_only:
        for offer in offers:
            known_prices[offer.id] = offer.comparison_price(price_currency)
        return known_prices
    updated = dict(known_prices)
    for offer in offers:
        reason = should_notify(offer, known_prices, threshold, price_currency)
        if reason:
            log.info(
                "Alert: %s, %s (%s)",
                offer.seller,
                reason,
                offer.format_prices(),
            )
            bot.notify_offer(offer, reason)
        updated[offer.id] = offer.comparison_price(price_currency)
    return updated

def main() -> None:
    settings = load_settings()
    state_path = Path(settings.state_file)
    runtime_config_path = Path(settings.runtime_config_file)
    known_prices = load_state(state_path, settings.price_currency)
    runtime = SharedState(
        settings.max_price,
        settings.price_currency,
        settings.poll_interval,
    )
    client = EldoradoClient(game_id=settings.game_id)
    bot = TelegramBot(
        token=settings.telegram_bot_token,
        alert_chat_id=settings.telegram_chat_id,
        whitelist_user_ids=settings.whitelist_user_ids,
        runtime=runtime,
        runtime_config_path=runtime_config_path,
        client_factory=lambda: EldoradoClient(game_id=settings.game_id),
    )
    bot.start()
    seed_only = not known_prices
    try:
        offers = client.fetch_offers()
        runtime.update_offers(offers)
        bot.notify_startup(offers)
    except Exception:
        log.exception("Startup notification failed")
    log.info(
        "Started (threshold: %.5f %s per Robux, interval: %ds)",
        runtime.max_price,
        runtime.price_currency,
        runtime.poll_interval,
    )
    while True:
        try:
            known_prices = run_check(
                client,
                bot,
                runtime,
                known_prices,
                runtime.price_currency,
                seed_only=seed_only,
            )
            save_state(state_path, known_prices, runtime.price_currency)
            seed_only = False
        except Exception:
            log.exception("Check failed")
        _, _, _, _, interval = runtime.snapshot()
        time.sleep(interval)

if __name__ == "__main__":
    main()
