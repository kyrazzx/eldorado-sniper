from dataclasses import dataclass
import httpx
API_BASE = "https://www.eldorado.gg/api"
LISTING_URL = "https://www.eldorado.gg/buy-robux/g/70-0-0"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": LISTING_URL,
}

@dataclass(frozen=True)
class RobuxOffer:
    id: str
    seller: str
    price_per_unit_usd: float
    price_per_unit: float
    currency: str
    quantity: int
    min_quantity: int
    delivery: str
    url: str

    def comparison_price(self, price_currency: str) -> float:
        if price_currency.upper() == "USD":
            return self.price_per_unit_usd
        return self.price_per_unit

    def format_prices(self) -> str:
        native = f"{self.price_per_unit:.5f} {self.currency}"
        return f"{native} ({self.price_per_unit_usd:.5f} USD)"

class EldoradoClient:
    def __init__(self, game_id: str = "70") -> None:
        self.game_id = game_id

    def fetch_offers(self) -> list[RobuxOffer]:
        params = {
            "gameId": self.game_id,
            "category": "Currency",
            "pageIndex": 1,
            "pageSize": 150,
        }
        response = httpx.get(
            f"{API_BASE}/predefinedOffers/augmentedGame/offers",
            params=params,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        offers: list[RobuxOffer] = []
        for item in payload.get("results", []):
            offer = item["offer"]
            user = item.get("user", {})
            price = offer["pricePerUnit"]
            price_usd = offer.get("pricePerUnitInUSD", price)
            seo_alias = offer.get("gameSeoAlias", "buy-robux")
            offer_id = offer["id"]
            offers.append(
                RobuxOffer(
                    id=offer_id,
                    seller=user.get("username", "unknown"),
                    price_per_unit_usd=float(price_usd["amount"]),
                    price_per_unit=float(price["amount"]),
                    currency=price["currency"],
                    quantity=int(offer.get("quantity", 0)),
                    min_quantity=int(offer.get("minQuantity", 0)),
                    delivery=offer.get("guaranteedDeliveryTime", "unknown"),
                    url=f"https://www.eldorado.gg/{seo_alias}/og/{offer_id}",
                )
            )
        offers.sort(key=lambda o: o.price_per_unit)
        return offers
