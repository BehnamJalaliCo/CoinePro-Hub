"""Today's market and news, fetched at the moment of making (public sources, no key):
CoinGecko global + BTC/ETH, the fear & greed index, Cointelegraph's feed, TradeYar's own Persian
news channel (@TradeYarNews, public preview). Usage: python3 -I tools/news_today.py out.json
Every number in the reel comes from this file («در لحظه‌ی ساخت این ویدیو»)."""

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

UA = {"User-Agent": "zaribsad-kit/1"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def safe(fn):  # one source down never stops the others
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def market() -> dict:
    g = json.loads(get("https://api.coingecko.com/api/v3/global"))["data"]
    p = json.loads(get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum"
                       "&vs_currencies=usd&include_24hr_change=true"))
    return {"total_mcap_usd": g["total_market_cap"]["usd"],
            "mcap_change_24h_pct": g["market_cap_change_percentage_24h_usd"],
            "btc_dominance_pct": g["market_cap_percentage"]["btc"],
            "btc": p["bitcoin"], "eth": p["ethereum"]}


def fear_greed() -> dict:
    d = json.loads(get("https://api.alternative.me/fng/?limit=2"))["data"]
    return {"today": d[0]["value"], "label": d[0]["value_classification"],
            "yesterday": d[1]["value"] if len(d) > 1 else None}


def cointelegraph() -> list:
    root = ET.fromstring(get("https://cointelegraph.com/rss"))
    out = []
    for it in root.iter("item"):
        out.append({"title": (it.findtext("title") or "").strip(), "at": it.findtext("pubDate"),
                    "link": it.findtext("link")})
        if len(out) >= 12:
            break
    return out


def tradeyar_news() -> list:
    page = get("https://t.me/s/TradeYarNews").decode("utf-8", "replace")
    posts = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', page, re.S)
    clean = [html.unescape(re.sub(r"<[^>]+>", " ", p)).strip() for p in posts]
    return [re.sub(r"\s+", " ", c)[:600] for c in clean[-12:]]


def main() -> None:
    out = {"at_utc": datetime.now(UTC).isoformat(timespec="minutes"), "market": safe(market),
           "fear_greed": safe(fear_greed), "cointelegraph": safe(cointelegraph),
           "tradeyar_news": safe(tradeyar_news)}
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    m = out["market"]
    print(json.dumps({"btc": m.get("btc"), "fng": out["fear_greed"],
                      "headlines": len(out["cointelegraph"]) if isinstance(out["cointelegraph"], list) else 0,
                      "ty_posts": len(out["tradeyar_news"]) if isinstance(out["tradeyar_news"], list) else 0},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
