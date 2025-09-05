# FunPay Bot (Telegram + Parsing with Descriptions)

A simple bot to parse FunPay lots (titles, prices, subscribers, and descriptions) and optionally publish lots via FunPay API. Includes Telegram polling for control.

## Requirements

- Python 3.10+
- See `requirements.txt` for Python packages.
- The code references `FunPayAPI.account.Account`. Install your implementation/package or adjust the code to your own API.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Create `funpay_config.json` in the project root. Minimal example:

```json
{
  "tg_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "tg_chat_id": "", 
  "golden_key": "YOUR_FUNPAY_GOLDEN_KEY",
  "create_lot_url": "https://funpay.com/lots/offerEdit?node=700",
  "parse_lot_url": "https://funpay.com/lots/700/",
  "markup_percent": 15,
  "price_min": 0,
  "price_max": 0
}
```

- `tg_token` can be left empty; the bot will wait until you add it and then start polling.
- `golden_key` is required for posting lots.
- `create_lot_url` should target the node where you create offers.
- `parse_lot_url` is the listing to parse (items are sorted by subscribers).

## Run

```bash
python funpay_bot.py
```

Control via Telegram commands/buttons:
- /status
- /gk <key>
- /create_url <url>
- /parse_url <url>
- /markup <percent>
- /range <min> <max>
- /post
- /file
- /stop

The parsed items with descriptions are saved to `funpay_items.txt`.