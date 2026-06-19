import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
import httpx
from config import save_runtime_overrides
from eldorado import EldoradoClient, RobuxOffer
from runtime import SharedState
log = logging.getLogger("eldorado-sniper")

class TelegramBot:
    def __init__(
        self,
        token: str,
        alert_chat_id: str,
        whitelist_user_ids: frozenset[int],
        runtime: SharedState,
        runtime_config_path: Path,
        client_factory: Callable[[], EldoradoClient],
    ) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.alert_chat_id = alert_chat_id
        self.whitelist_user_ids = whitelist_user_ids
        self.runtime = runtime
        self.runtime_config_path = runtime_config_path
        self.client_factory = client_factory
        self._offset = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        httpx.post(f"{self.base_url}/deleteWebhook", json={"drop_pending_updates": False}, timeout=15)
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("Telegram command listener started")

    def stop(self) -> None:
        self._running = False

    def send(self, chat_id: str | int, text: str, reply_markup: dict | None = None) -> None:
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = httpx.post(f"{self.base_url}/sendMessage", json=payload, timeout=30)
        response.raise_for_status()

    def notify_startup(self, offers: list[RobuxOffer]) -> None:
        _, _, threshold, currency, _ = self.runtime.snapshot()
        if offers:
            best = offers[0]
            best_line = best.format_prices()
            offer_count = len(offers)
        else:
            best_line = "n/a"
            offer_count = 0
        self.send(
            self.alert_chat_id,
            "<b>Eldorado sniper started</b>\n\n"
            f"Current best price: <b>{best_line}</b> per Robux\n"
            f"Alert threshold: <b>{threshold:.5f} {currency}</b> per Robux\n"
            f"Offers tracked: {offer_count}\n\n"
            "Send /start to open the control panel.",
        )

    def notify_offer(self, offer: RobuxOffer, reason: str) -> None:
        unit_price = offer.comparison_price(self.runtime.price_currency)
        robux_per_unit = 1 / unit_price if unit_price else 0
        self.send(
            self.alert_chat_id,
            f"<b>Robux offer alert</b> ({reason})\n\n"
            f"Price: <b>{offer.format_prices()}</b> per Robux\n"
            f"Rate: ~{robux_per_unit:.0f} Robux per {self.runtime.price_currency}\n"
            f"Stock: {offer.quantity:,} (minimum {offer.min_quantity:,})\n"
            f"Delivery: {offer.delivery}\n"
            f"Seller: {offer.seller}\n\n"
            f'<a href="{offer.url}">Open offer on Eldorado</a>',
        )
        self.runtime.record_alert()

    def _poll_loop(self) -> None:
        while self._running:
            try:
                response = httpx.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 30},
                    timeout=40,
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    self._offset = update["update_id"] + 1
                    try:
                        self._handle_update(update)
                    except Exception:
                        log.exception("Telegram update handler failed")
            except Exception:
                log.exception("Telegram polling failed")
                time.sleep(3)

    def _handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            self._handle_callback(update["callback_query"])
            return
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        user_id = message.get("from", {}).get("id")
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        if user_id not in self.whitelist_user_ids:
            if text.startswith("/start"):
                log.warning(
                    "Ignored /start from user %s (chat %s). Add this user ID to WHITELIST_USER_IDS.",
                    user_id,
                    chat_id,
                )
                self.send(
                    chat_id,
                    f"Unauthorized. Your Telegram user ID is <code>{user_id}</code>.",
                )
            return
        if text.startswith("/start") or text.startswith("/menu"):
            self._send_main_menu(chat_id)

    def _handle_callback(self, query: dict) -> None:
        user_id = query.get("from", {}).get("id")
        if user_id not in self.whitelist_user_ids:
            self._answer_callback(query["id"], "Unauthorized")
            return
        data = query.get("data", "")
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        step = self.runtime.threshold_step()
        if data == "menu:main":
            self._edit_main_menu(chat_id, message_id)
        elif data == "menu:settings":
            self._edit_settings_menu(chat_id, message_id)
        elif data == "stats:live":
            self._edit_stats(chat_id, message_id, refresh=True)
        elif data == "stats:cached":
            self._edit_stats(chat_id, message_id, refresh=False)
        elif data == "offers:top5":
            self._edit_top_offers(chat_id, message_id, refresh=True)
        elif data == "threshold:dec":
            self._adjust_threshold(chat_id, message_id, -step)
        elif data == "threshold:inc":
            self._adjust_threshold(chat_id, message_id, step)
        elif data == "interval:dec":
            self._adjust_interval(chat_id, message_id, -15)
        elif data == "interval:inc":
            self._adjust_interval(chat_id, message_id, 15)
        self._answer_callback(query["id"])

    def _answer_callback(self, callback_id: str, text: str = "") -> None:
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        httpx.post(f"{self.base_url}/answerCallbackQuery", json=payload, timeout=15)

    def _edit(self, chat_id: int, message_id: int, text: str, reply_markup: dict) -> None:
        httpx.post(
            f"{self.base_url}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": reply_markup,
            },
            timeout=30,
        ).raise_for_status()

    def _main_keyboard(self) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "Live stats", "callback_data": "stats:live"},
                    {"text": "Top 5 offers", "callback_data": "offers:top5"},
                ],
                [{"text": "Settings", "callback_data": "menu:settings"}],
            ]
        }

    def _settings_keyboard(self) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "Threshold -", "callback_data": "threshold:dec"},
                    {"text": "Threshold +", "callback_data": "threshold:inc"},
                ],
                [
                    {"text": "Interval -15s", "callback_data": "interval:dec"},
                    {"text": "Interval +15s", "callback_data": "interval:inc"},
                ],
                [{"text": "Back", "callback_data": "menu:main"}],
            ]
        }

    def _send_main_menu(self, chat_id: int) -> None:
        stats, _, threshold, currency, interval = self.runtime.snapshot()
        text = (
            "<b>Eldorado Sniper</b>\n\n"
            f"Threshold: <b>{threshold:.5f} {currency}</b> per Robux\n"
            f"Poll interval: <b>{interval}s</b>\n"
            f"Checks completed: <b>{stats.checks_completed}</b>\n"
            f"Alerts sent: <b>{stats.alerts_sent}</b>"
        )
        self.send(chat_id, text, self._main_keyboard())

    def _edit_main_menu(self, chat_id: int, message_id: int) -> None:
        stats, _, threshold, currency, interval = self.runtime.snapshot()
        text = (
            "<b>Eldorado Sniper</b>\n\n"
            f"Threshold: <b>{threshold:.5f} {currency}</b> per Robux\n"
            f"Poll interval: <b>{interval}s</b>\n"
            f"Checks completed: <b>{stats.checks_completed}</b>\n"
            f"Alerts sent: <b>{stats.alerts_sent}</b>"
        )
        self._edit(chat_id, message_id, text, self._main_keyboard())

    def _edit_settings_menu(self, chat_id: int, message_id: int) -> None:
        _, _, threshold, currency, interval = self.runtime.snapshot()
        step = self.runtime.threshold_step()
        text = (
            "<b>Settings</b>\n\n"
            f"Alert threshold: <b>{threshold:.5f} {currency}</b> per Robux\n"
            f"Threshold step: <b>{step:.4f} {currency}</b>\n"
            f"Poll interval: <b>{interval}s</b> (minimum 15s)"
        )
        self._edit(chat_id, message_id, text, self._settings_keyboard())

    def _edit_stats(self, chat_id: int, message_id: int, *, refresh: bool) -> None:
        if refresh:
            try:
                offers = self.client_factory().fetch_offers()
                self.runtime.update_offers(offers)
            except Exception:
                log.exception("Live stats refresh failed")
        stats, offers, threshold, currency, interval = self.runtime.snapshot()
        uptime = int(time.time() - stats.started_at)
        last_check = (
            time.strftime("%H:%M:%S", time.localtime(stats.last_check_at))
            if stats.last_check_at
            else "n/a"
        )
        if stats.best_price is not None and offers:
            best_line = f"{offers[0].format_prices()} ({stats.last_best_seller})"
        else:
            best_line = "n/a"
        text = (
            "<b>Live stats</b>\n\n"
            f"Uptime: <b>{uptime}s</b>\n"
            f"Last check: <b>{last_check}</b>\n"
            f"Best price: <b>{best_line}</b>\n"
            f"Offers listed: <b>{stats.offer_count}</b>\n"
            f"Below threshold: <b>{stats.below_threshold}</b>\n"
            f"Threshold: <b>{threshold:.5f} {currency}</b>\n"
            f"Poll interval: <b>{interval}s</b>\n"
            f"Checks: <b>{stats.checks_completed}</b>\n"
            f"Alerts sent: <b>{stats.alerts_sent}</b>"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "Refresh", "callback_data": "stats:live"}],
                [{"text": "Back", "callback_data": "menu:main"}],
            ]
        }
        self._edit(chat_id, message_id, text, keyboard)

    def _edit_top_offers(self, chat_id: int, message_id: int, *, refresh: bool) -> None:
        if refresh:
            try:
                offers = self.client_factory().fetch_offers()
                self.runtime.update_offers(offers)
            except Exception:
                log.exception("Top offers refresh failed")
        _, offers, threshold, currency, _ = self.runtime.snapshot()
        lines = ["<b>Top 5 cheapest offers</b>\n"]
        if not offers:
            lines.append("No offer data available.")
        else:
            for index, offer in enumerate(offers[:5], start=1):
                marker = " *" if offer.comparison_price(currency) <= threshold else ""
                lines.append(
                    f"{index}. <b>{offer.format_prices()}</b> — "
                    f"{offer.seller} ({offer.quantity:,} stock){marker}"
                )
            lines.append(f"\n* at or below {threshold:.5f} {currency}")
        keyboard = {
            "inline_keyboard": [
                [{"text": "Refresh", "callback_data": "offers:top5"}],
                [{"text": "Back", "callback_data": "menu:main"}],
            ]
        }
        self._edit(chat_id, message_id, "\n".join(lines), keyboard)

    def _persist_runtime(self) -> None:
        _, _, threshold, currency, interval = self.runtime.snapshot()
        save_runtime_overrides(self.runtime_config_path, threshold, currency, interval)

    def _adjust_threshold(self, chat_id: int, message_id: int, delta: float) -> None:
        _, _, threshold, _, _ = self.runtime.snapshot()
        self.runtime.set_max_price(threshold + delta)
        self._persist_runtime()
        self._edit_settings_menu(chat_id, message_id)

    def _adjust_interval(self, chat_id: int, message_id: int, delta: int) -> None:
        _, _, _, _, interval = self.runtime.snapshot()
        self.runtime.set_poll_interval(interval + delta)
        self._persist_runtime()
        self._edit_settings_menu(chat_id, message_id)
