"""The coin's facts at the moment of making (CoinGecko + LBank public APIs, no key):
price, 24h/7d/30d/1y change, rank, ATH, supply, genesis, and the REAL daily price series of the past
year (`series_1y`: [[YYYY-MM-DD, usd], …], for THE DESK's charts: DESK.lineChart). Usage:
  python3 -I tools/coin_facts.py <coingecko id> <lbank symbol> out.json
Every number in the reel comes from this file; say «در لحظه‌ی ساخت این ویدیو»."""

import json
import sys
import urllib.request
from datetime import UTC, datetime


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "zaribsad-kit/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> None:
    cg_id, lb_sym, out = sys.argv[1], sys.argv[2], sys.argv[3]
    d = get(f"https://api.coingecko.com/api/v3/coins/{cg_id}?localization=false&tickers=false"
            "&community_data=false&developer_data=false")
    m = d["market_data"]
    facts = {
        "at_utc": datetime.now(UTC).isoformat(timespec="minutes"),
        "name": d.get("name"), "symbol": str(d.get("symbol", "")).upper(),
        "rank": d.get("market_cap_rank"), "genesis": d.get("genesis_date"),
        "price_usd": m["current_price"]["usd"],
        "change_pct": {k: m.get(f"price_change_percentage_{k}") for k in ("24h", "7d", "30d", "1y")},
        "ath_usd": m["ath"]["usd"], "ath_date": str(m["ath_date"]["usd"])[:10],
        "circulating": m.get("circulating_supply"), "max_supply": m.get("max_supply"),
        "market_cap_usd": m["market_cap"]["usd"],
        "categories": d.get("categories"),
        "homepage": (d.get("links") or {}).get("homepage", [None])[0],
        # the coin's OFFICIAL logo (never let an AI draw a logo): download it with curl
        "logo": (d.get("image") or {}).get("large"),
    }
    try:  # the real series for the charts on screen (one point a day, the last year)
        ch = get(f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=365&interval=daily")
        facts["series_1y"] = [[datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d"), round(v, 8)]
                              for ms, v in ch.get("prices", [])]
    except Exception as e:  # noqa: BLE001
        facts["series_1y"] = []
        facts["series_error"] = str(e)[:200]
    try:
        t = get(f"https://api.lbkex.com/v2/ticker/24hr.do?symbol={lb_sym}")["data"][0]["ticker"]
        facts["lbank"] = {"last": float(t["latest"]), "change_24h_pct": float(t["change"])}
    except Exception as e:  # noqa: BLE001
        facts["lbank"] = {"error": str(e)[:200]}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: facts[k] for k in ("symbol", "price_usd", "change_pct", "rank")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
