# -*- coding: utf-8 -*-
"""Builds the 365-day ProChart reels topic bank: calendar, checks, CSV/JSON and the phone PDF HTML."""
import csv, json, sys, html, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_general import PATTERNS, MISTAKES, RISK, MYTHS
from data_app import (DAY1, TOOLS, INDICATORS, HOWTO, COMPARE, SCENARIOS, TIPS, AI, FAQ)
from check_dupes import find_clashes

FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
def fa(n): return str(n).translate(FA)

SERIES = {
    "intro": "شروع",
    "tool": "ابزار روز",
    "ind": "اندیکاتور و ترسیم",
    "howto": "آموزش قدم‌به‌قدم",
    "cmp": "مقایسه‌ی منصفانه",
    "scn": "سناریوی کاربر",
    "tip": "ترفند حرفه‌ای",
    "mis": "اشتباه رایج",
    "pat": "الگو و مفهوم",
    "ai": "هوش مصنوعی پروچارت",
    "risk": "ریسک و روانشناسی",
    "faq": "پرسش شما",
    "myth": "باور غلط",
}

def need(name, lst, n):
    if len(lst) != n:
        raise SystemExit(f"{name}: has {len(lst)}, needs {n}")

need("TOOLS", TOOLS, 52); need("INDICATORS", INDICATORS, 52); need("HOWTO", HOWTO, 52)
need("COMPARE", COMPARE, 26); need("SCENARIOS", SCENARIOS, 26); need("TIPS", TIPS, 26)
need("MISTAKES", MISTAKES, 26); need("PATTERNS", PATTERNS, 52)
need("AI", AI, 13); need("RISK", RISK, 13); need("FAQ", FAQ, 13); need("MYTHS", MYTHS, 13)

days = [dict(day=1, slot="—", series="intro", title=DAY1[0], angle=DAY1[1], anchor=DAY1[2])]
fri_cycle = [("ai", AI), ("risk", RISK), ("faq", FAQ), ("myth", MYTHS)]
for w in range(52):
    base = 2 + w * 7
    week = [
        ("tool", TOOLS[w]),
        ("ind", INDICATORS[w]),
        ("howto", HOWTO[w]),
        ("cmp", COMPARE[w // 2]) if w % 2 == 0 else ("scn", SCENARIOS[w // 2]),
        ("tip", TIPS[w // 2]) if w % 2 == 0 else ("mis", MISTAKES[w // 2]),
        ("pat", PATTERNS[w]),
        (fri_cycle[w % 4][0], fri_cycle[w % 4][1][w // 4]),
    ]
    for k, (s, item) in enumerate(week):
        days.append(dict(day=base + k, slot=k + 1, series=s, title=item[0], angle=item[1], anchor=item[2]))

assert len(days) == 365, len(days)
titles = [d["title"] for d in days]
if len(set(titles)) != len(titles):
    from collections import Counter
    raise SystemExit("exact duplicates: " + str([t for t, c in Counter(titles).items() if c > 1]))
clashes = find_clashes(titles)
if clashes:
    for i, j, a, b in clashes:
        print(f"CLASH day {i+1} <-> day {j+1}: {a} | {b}")
    raise SystemExit(f"{len(clashes)} clashes")

here = os.path.dirname(os.path.abspath(__file__))
json.dump(days, open(os.path.join(here, "bank.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(here, "bank.csv"), "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["روز", "سری", "عنوان (همین در دفتر ضدتکرار ثبت میشود)", "زاویه", "جای آن در پروچارت"])
    for d in days:
        wr.writerow([d["day"], SERIES[d["series"]], d["title"], d["angle"], d["anchor"]])

from collections import Counter
cnt = Counter(d["series"] for d in days)
print("OK 365 days, no clashes;", {SERIES[k]: v for k, v in cnt.items()})
