# Eldorado Sniper

Telegram notifier that monitors [Eldorado.gg](https://www.eldorado.gg/buy-robux/g/70-0-0) Robux listings (can be edited to works with everything) and sends alerts when offers fall below a configured price threshold.

Eldorado serves offer data through a JSON API. The public HTML page is a client-rendered application and does not include listing data in the initial response.

## Features

- Polls the Eldorado predefined offers API on a fixed interval
- Sends a startup summary on every process launch
- Sends Telegram alerts for new offers below the threshold
- Sends Telegram alerts when a tracked offer price decreases below the threshold
- Interactive `/start` control panel for whitelisted users
- Live stats and top-offer views from inline menus
- Runtime adjustment of threshold and poll interval (persisted to `runtime_config.json`)
- Persists known offer prices locally to avoid duplicate notifications

## Requirements

- Python 3.10+
- A Telegram bot token
- A Telegram chat ID for alerts
- At least one whitelisted Telegram user ID for bot commands

## Installation

```bash
git clone https://github.com/kyrazzx/eldorado-sniper.git
cd eldorado-sniper
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set the required values.

### Telegram setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Obtain a chat ID from [@userinfobot](https://t.me/userinfobot) or by calling `getUpdates` after messaging the bot:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

3. Add your Telegram user ID to `WHITELIST_USER_IDS` to access `/start` and the control panel.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | — | Chat ID for alert messages |
| `WHITELIST_USER_IDS` | Yes | — | Comma-separated Telegram user IDs allowed to use `/start` |
| `PRICE_CURRENCY` | No | `EUR` | Currency used for threshold comparison (`EUR` or `USD`) |
| `MAX_PRICE` | No | `0.00450` | Maximum price per Robux in `PRICE_CURRENCY` |
| `MAX_PRICE_USD` | No | — | Legacy fallback when `PRICE_CURRENCY=USD` |
| `POLL_INTERVAL` | No | `60` | Poll interval in seconds (minimum 15) |
| `GAME_ID` | No | `70` | Eldorado game ID for Roblox Robux |
| `STATE_FILE` | No | `state.json` | Path to the local offer state file |
| `RUNTIME_CONFIG_FILE` | No | `runtime_config.json` | Path to persisted runtime settings |

`MAX_PRICE=0.00450` with `PRICE_CURRENCY=EUR` matches the per-unit EUR price shown on Eldorado (for example `€0.00455 / unit`).

Eldorado also exposes a converted `pricePerUnitInUSD` field. That value uses Eldorado's internal exchange rate, which may differ from market rates shown by external converters.

Offers are sorted by native `pricePerUnit` (EUR on the EU storefront), not by converted USD.

Threshold and poll interval can also be changed from the Telegram settings menu. Updates are saved to `runtime_config.json` and override `.env` defaults on restart.

## Usage

```bash
python main.py
```

A startup summary is sent to `TELEGRAM_CHAT_ID` on every launch.

Whitelisted users can send `/start` to open the control panel:

- **Live stats** — uptime, best price, offers below threshold, check count
- **Top 5 offers** — cheapest current listings
- **Settings** — adjust threshold and poll interval

On the first run only, existing offers are recorded without generating threshold alerts. Subsequent runs emit alerts for new qualifying offers or price decreases.

Delete `state.json` to reset tracked offer history.

## API

The monitor queries:

```
GET https://www.eldorado.gg/api/predefinedOffers/augmentedGame/offers
    ?gameId=70&category=Currency&pageIndex=1&pageSize=150
```

Offers are sorted by `pricePerUnitInUSD` before evaluation.

## Disclaimer

This project is not affiliated with Eldorado.gg or Roblox Corporation. Use at your own risk. Automated polling may be subject to rate limits or policy changes on the target platform.

## License

MIT
