"""THE DESK's price tape: the day's real tickers at the moment of making (CoinGecko, public, no key).
Usage: python3 -I COMMON/tools/tape.py qc/tape.json [extra coingecko ids …]
Writes [{"s": "BTC", "p": "97,412", "c": 2.13}, …]; desk_engine.py loads qc/tape.json as DATA.tape and
the HUD shows it (DESK.reel({tape}) overrides). Run it in the morning of the build, never reuse an old one.
Prices: Latin digits, thousands with commas, as an exchange shows them."""

import json
import sys
import urllib.request

BASE = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "dogecoin", "toncoin", "cardano"]


def fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.4f}"


def main() -> None:
    ids = list(dict.fromkeys(sys.argv[2:] + BASE))[:10]
    url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&price_change_percentage=24h&ids="
           + ",".join(ids))
    req = urllib.request.Request(url, headers={"User-Agent": "zarib100x-kit/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.load(r)
    order = {k: i for i, k in enumerate(ids)}
    rows.sort(key=lambda d: order.get(d["id"], 99))
    out = [{"s": d["symbol"].upper(), "p": fmt(d["current_price"]), "c": round(d.get("price_change_percentage_24h") or 0, 2)}
           for d in rows]
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(len(out), "tickers", out[:2])


if __name__ == "__main__":
    main()
