#!/usr/bin/env python3
"""The day's Search Console digest from the hub's input pack (stdlib):

    python3 -I KIT/tools/gsc_digest.py in/ site/automations/sites/dotcoin > work/digest.md
    (+ work/digest.json beside it when --json PATH is given)

What it reads: in/gsc/<UTC day>/{28d,7d}.json (Search Console's own Performance export: Chart,
Queries, Pages, Countries, Devices, Search appearance; one folder per day the hub read it),
pages.txt (Page indexing), sitemap.txt, inspect.json (URL inspection), and the site's
seo/auto/EXPERIMENTS.json. What it gives, in this order: the totals and the daily trend (28 days),
day over day, week over week per query (today's 7-day export against the one 7 days earlier),
striking-distance queries (position 4.5–20), titles under their expected CTR, the pages, the queries
new this week, the index state of every sitemap URL, and the experiments due for judgement. It
never invents a number: a figure Search Console has not given is «—».
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

# the click-through rate an informational result usually earns at a position (a yardstick only)
EXPECTED_CTR = {1: 28.0, 2: 15.0, 3: 10.0, 4: 7.0, 5: 5.0, 6: 4.0, 7: 3.2, 8: 2.6, 9: 2.2, 10: 1.9}


def expected_ctr(pos: float) -> float:
    p = max(1, round(pos))
    return EXPECTED_CTR.get(p, 1.0 if p <= 20 else 0.4)


def num(v) -> float:
    s = str(v or "").replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def rows(snap: dict, name: str) -> list[dict]:
    return snap.get(name) or []


def table(snap: dict, name: str, key: str) -> dict[str, dict]:
    out = {}
    for r in rows(snap, name):
        k = str(r.get(key) or "").strip()
        if k:
            out[k] = {"clicks": num(r.get("Clicks")), "impressions": num(r.get("Impressions")),
                      "ctr": num(r.get("CTR")), "position": num(r.get("Position"))}
    return out


def load(gdir: Path) -> dict[str, dict]:
    """day -> {"28d": export, "7d": export}"""
    out: dict[str, dict] = {}
    for d in sorted(p for p in gdir.glob("*") if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)):
        one = {}
        for n in ("28d", "7d"):
            f = d / f"{n}.json"
            if f.exists():
                try:
                    one[n] = json.loads(f.read_text("utf-8"))
                except ValueError:
                    pass
        if one:
            out[d.name] = one
    return out


def f1(x: float) -> str:
    return f"{x:.1f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs")
    ap.add_argument("site")
    ap.add_argument("--json")
    a = ap.parse_args()
    inp, site = Path(a.inputs), Path(a.site)
    days = load(inp / "gsc")
    out: list[str] = ["# Search Console digest (dotcoin.me)", ""]
    data: dict = {"days": sorted(days)}
    if not days:
        out += ["No Search Console export in the pack yet (see in/errors.json). Work from the index state, "
                "the audit and research; say so in report.md.", ""]
    last = sorted(days)[-1] if days else None
    snap28 = days.get(last, {}).get("28d", {}) if last else {}
    snap7 = days.get(last, {}).get("7d", {}) if last else {}
    # ---- totals and trend
    chart = [r for r in rows(snap28, "Chart") if r.get("Date")]
    tot_c = sum(num(r.get("Clicks")) for r in chart)
    tot_i = sum(num(r.get("Impressions")) for r in chart)
    wpos = sum(num(r.get("Position")) * num(r.get("Impressions")) for r in chart)
    out += [f"## Totals, 28 days to the export of {last or '—'}", "",
            f"- clicks {int(tot_c)}, impressions {int(tot_i)}, CTR {f1(100 * tot_c / tot_i) if tot_i else '—'}%, "
            f"position {f1(wpos / tot_i) if tot_i else '—'} (impression-weighted)", ""]
    if chart:
        out += ["| day | clicks | impressions | CTR | position |", "|---|---|---|---|---|"]
        for r in chart[-14:]:
            out.append(f"| {r['Date']} | {r.get('Clicks')} | {r.get('Impressions')} | {r.get('CTR') or '—'} | {r.get('Position') or '—'} |")
        if len(chart) >= 2:
            a1, b1 = chart[-1], chart[-2]
            out += ["", f"Day over day ({b1['Date']} → {a1['Date']}): clicks {b1.get('Clicks')} → {a1.get('Clicks')}, "
                        f"impressions {b1.get('Impressions')} → {a1.get('Impressions')}"]
        out.append("")
    data["totals_28d"] = {"clicks": tot_c, "impressions": tot_i, "position": (wpos / tot_i) if tot_i else None}
    q28, q7 = table(snap28, "Queries", "Top queries"), table(snap7, "Queries", "Top queries")
    p28 = table(snap28, "Pages", "Top pages")
    # ---- week over week per query
    then = (date.fromisoformat(last) - timedelta(days=7)).isoformat() if last else ""
    prev = days.get(then, {}).get("7d") if then else None
    if prev is None and last:  # the nearest export 6-8 days before
        near = [d for d in days if 6 <= (date.fromisoformat(last) - date.fromisoformat(d)).days <= 8]
        prev = days[near[-1]].get("7d") if near else None
    out += ["## Week over week, per query (7-day exports)", ""]
    if prev:
        qp = table(prev, "Queries", "Top queries")
        moves = []
        for q in set(q7) | set(qp):
            n, o = q7.get(q, {}), qp.get(q, {})
            moves.append((n.get("impressions", 0) - o.get("impressions", 0), q, n, o))
        moves.sort(key=lambda x: -abs(x[0]))
        out += ["| query | impressions (then → now) | clicks | position |", "|---|---|---|---|"]
        for d_i, q, n, o in moves[:25]:
            out.append(f"| {q} | {int(o.get('impressions', 0))} → {int(n.get('impressions', 0))} | "
                       f"{int(o.get('clicks', 0))} → {int(n.get('clicks', 0))} | "
                       f"{f1(o['position']) if o.get('position') else '—'} → {f1(n['position']) if n.get('position') else '—'} |")
    else:
        out.append("Not yet: a 7-day export from a week ago is needed (the history grows by one a day).")
    out.append("")
    # ---- striking distance and CTR gaps
    sd = sorted(((q, v) for q, v in q28.items() if 4.5 <= v["position"] <= 20 and v["impressions"] >= 3),
                key=lambda x: -x[1]["impressions"])
    out += ["## Striking distance (position 4.5–20, 28 days): one better page, section or link can lift them", ""]
    out += [f"- {q}: {int(v['impressions'])} impressions, position {f1(v['position'])}, CTR {f1(v['ctr'])}%" for q, v in sd[:25]] or ["- none yet"]
    gaps = sorted(((p, v) for p, v in p28.items() if v["impressions"] >= 80 and v["ctr"] < 0.7 * expected_ctr(v["position"])),
                  key=lambda x: -x[1]["impressions"])
    out += ["", "## Titles and descriptions under their expected CTR (≥ 80 impressions; a yardstick, not a law)", ""]
    out += [f"- {p}: CTR {f1(v['ctr'])}% at position {f1(v['position'])} (about {f1(expected_ctr(v['position']))}% expected), "
            f"{int(v['impressions'])} impressions" for p, v in gaps[:15]] or ["- none yet"]
    out += ["", "## Pages (28 days)", "", "| page | clicks | impressions | CTR | position |", "|---|---|---|---|---|"]
    for p, v in sorted(p28.items(), key=lambda x: -x[1]["impressions"])[:40]:
        out.append(f"| {p} | {int(v['clicks'])} | {int(v['impressions'])} | {f1(v['ctr'])}% | {f1(v['position'])} |")
    if not p28:
        out.append("| — | | | | |")
    # ---- new queries this week
    if prev is not None:
        old28 = days.get(then, {}).get("28d") if then in days else None
        base_q = set(table(old28, "Queries", "Top queries")) if old28 else set(table(prev, "Queries", "Top queries"))
        new_q = sorted((q for q in q28 if q not in base_q), key=lambda q: -q28[q]["impressions"])
        out += ["", "## Queries new this week", ""] + ([f"- {q} ({int(q28[q]['impressions'])})" for q in new_q[:20]] or ["- none"])
    # ---- the index
    insp_f = inp / "index" / "inspected.json"
    insp = json.loads(insp_f.read_text("utf-8")) if insp_f.exists() else {}
    sm = (inp / "live" / "sitemap.xml").read_text("utf-8") if (inp / "live" / "sitemap.xml").exists() else ""
    urls = re.findall(r"<loc>(https://dotcoin\.me/[^<]*)</loc>", sm)
    out += ["", f"## The index: {sum(1 for u in urls if insp.get(u, {}).get('indexed'))} of {len(urls)} sitemap URLs "
                "seen on Google (URL inspection)", ""]
    for u in urls:
        i = insp.get(u)
        if not i:
            out.append(f"- {u}: not inspected yet")
        elif not i.get("indexed"):
            out.append(f"- {u}: {i.get('coverage') or i.get('verdict') or '?'}; sitemap: {i.get('sitemaps') or '—'}; "
                       f"last crawl {i.get('last_crawl') or '—'} (inspected {str(i.get('at'))[:10]})")
    if last:
        for name in ("pages", "sitemap"):
            f = inp / "gsc" / last / f"{name}.txt"
            if f.exists():
                text = " ".join(f.read_text("utf-8").split())
                out += ["", f"### {name}.txt (Search Console's own words)", "", text[:1500]]
    # ---- experiments due
    ex_f = site / "seo" / "auto" / "EXPERIMENTS.json"
    try:
        exps = json.loads(ex_f.read_text("utf-8")) if ex_f.exists() else []
    except ValueError:
        exps = []
    today = date.today().isoformat()
    due = [e for e in exps if isinstance(e, dict) and not e.get("verdict") and str(e.get("judge_on") or "9999") <= today]
    out += ["", f"## Experiments due for judgement: {len(due)}", ""]
    for e in due:
        page = str(e.get("page") or "")
        now = p28.get(f"https://dotcoin.me{page}") or p28.get(page) or {}
        out.append(f"- {e.get('id')}: {page} {e.get('change')}: baseline {e.get('baseline')} → now {now or '—'}")
    data.update(queries_28d=q28, queries_7d=q7, pages_28d=p28, striking=[q for q, _ in sd], ctr_gaps=[p for p, _ in gaps],
                due=[e.get("id") for e in due])
    print("\n".join(out))
    if a.json:
        Path(a.json).write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
