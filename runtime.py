import threading
import time
from dataclasses import dataclass, field
from eldorado import RobuxOffer

@dataclass
class LiveStats:
    started_at: float = field(default_factory=time.time)
    last_check_at: float | None = None
    best_price: float | None = None
    best_price_usd: float | None = None
    last_best_seller: str | None = None
    offer_count: int = 0
    below_threshold: int = 0
    checks_completed: int = 0
    alerts_sent: int = 0

class SharedState:
    def __init__(self, max_price: float, price_currency: str, poll_interval: int) -> None:
        self.lock = threading.Lock()
        self.max_price = max_price
        self.price_currency = price_currency.upper()
        self.poll_interval = poll_interval
        self.stats = LiveStats()
        self.offers: list[RobuxOffer] = []

    def _below_threshold(self, offer: RobuxOffer) -> bool:
        return offer.comparison_price(self.price_currency) <= self.max_price

    def update_offers(self, offers: list[RobuxOffer]) -> None:
        with self.lock:
            self.offers = list(offers)
            self.stats.last_check_at = time.time()
            self.stats.checks_completed += 1
            if offers:
                best = offers[0]
                self.stats.best_price = best.comparison_price(self.price_currency)
                self.stats.best_price_usd = best.price_per_unit_usd
                self.stats.last_best_seller = best.seller
                self.stats.offer_count = len(offers)
                self.stats.below_threshold = sum(1 for o in offers if self._below_threshold(o))
            else:
                self.stats.offer_count = 0
                self.stats.below_threshold = 0

    def record_alert(self) -> None:
        with self.lock:
            self.stats.alerts_sent += 1

    def set_max_price(self, value: float) -> float:
        with self.lock:
            self.max_price = max(0.0001, round(value, 5))
            self.stats.below_threshold = sum(1 for o in self.offers if self._below_threshold(o))
            return self.max_price

    def set_poll_interval(self, value: int) -> int:
        with self.lock:
            self.poll_interval = max(15, value)
            return self.poll_interval

    def threshold_step(self) -> float:
        return 0.0005 if self.price_currency == "USD" else 0.0001

    def snapshot(self) -> tuple[LiveStats, list[RobuxOffer], float, str, int]:
        with self.lock:
            return (
                LiveStats(**self.stats.__dict__),
                list(self.offers),
                self.max_price,
                self.price_currency,
                self.poll_interval,
            )
