"""TradeYar's signal record at the moment of making (its own public API, no key), for the proof
story. Usage: python3 -I tools/ty_proof.py out.json
Only these numbers go on a story; each with its window (7/30/90 days, all) and its end date."""

import json
import sys
import urllib.request

API = "https://tradeyar.trade-future.ir/api/v1/public"
UA = {"User-Agent": "zaribsad-kit/1"}
KEYS = ("trades", "wins", "losses", "win_rate_pct", "profit_factor", "payoff_ratio",
        "longest_win_streak", "longest_loss_streak", "symbols_covered", "max_drawdown_pct")


def get(path: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(f"{API}{path}", headers=UA), timeout=30) as r:
        return json.loads(r.read())


def main(out: str) -> None:
    s = get("/performance/summary")
    got: dict = {"source": f"{API}/performance/summary", "methodology": s.get("provenance", {}).get("methodology_version")}
    for key, w in (s.get("windows") or {}).items():
        row = {k: (w.get(k) or {}).get("value") for k in KEYS}
        win = w.get("window") or {}
        row["from"], row["to"], row["days"] = win.get("observed_start"), win.get("observed_end"), win.get("days")
        reach = w.get("reach_pct") or {}
        row["tp_reach_pct"] = {tp: (v or {}).get("value") for tp, v in reach.items()}
        got[key] = row
    try:
        a = get("/btc-analysis")
        first = (a.get("items") or [{}])[0]
        got["btc_analysis"] = {"date": first.get("date"), "title": first.get("title"), "summary": first.get("summary")}
    except Exception as e:  # noqa: BLE001 - the record stands without it
        got["btc_analysis"] = {"error": str(e)[:200]}
    json.dump(got, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    w = got.get("30d") or {}
    print(f"30d: {w.get('trades')} trades, win {w.get('win_rate_pct')}%, PF {w.get('profit_factor')}, to {w.get('to')}")


if __name__ == "__main__":
    main(sys.argv[1])
