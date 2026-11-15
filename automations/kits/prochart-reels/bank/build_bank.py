# -*- coding: utf-8 -*-
"""Builds the ProChart reels topic bank: two reels a day, 730 entries.

Year one (data_app.py, data_general.py): days 1..365, weekly 7-series calendar, unchanged.
Year two (data_year2.py): days 366..730, same weekly scheme with its own series.
bank.json / bank.csv / titles.txt list them interleaved: old day 1, new day 366, old day 2, new 367, ...
so a session that takes "the next unused title in file order" gets two different kinds each day
(each pair shares the weekly slot, and the two years never put the same kind on the same slot).
Checks: list sizes, exact duplicates and the anti-repeat rule (check_dupes.find_clashes) over all 730.
"""
import csv, json, sys, html, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_general import PATTERNS, MISTAKES, RISK, MYTHS
from data_app import (DAY1, TOOLS, INDICATORS, HOWTO, COMPARE, SCENARIOS, TIPS, AI, FAQ)
from data_year2 import (SCHOOL, MARKETS, INDICATORS2, DRAWING, LAB, VIEW, HIDDEN, CANDLES)
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
    # year two (days 366..730)
    "edu": "مدرسه‌ی معامله‌گر",
    "mkt": "بازار زیر ذره‌بین",
    "ind2": "جعبه‌ی اندیکاتورها",
    "draw": "میز ترسیم",
    "lab": "آزمایشگاه استراتژی",
    "view": "نمای چارت",
    "more": "امکان کم‌دیده",
    "cnd": "کندل‌خوانی",
}

def need(name, lst, n):
    if len(lst) != n:
        raise SystemExit(f"{name}: has {len(lst)}, needs {n}")
    for e in lst:
        if len(e) != 3 or not all(isinstance(s, str) and s.strip() for s in e):
            raise SystemExit(f"{name}: bad entry {e!r} (needs title, angle, anchor)")

need("TOOLS", TOOLS, 52); need("INDICATORS", INDICATORS, 52); need("HOWTO", HOWTO, 52)
need("COMPARE", COMPARE, 26); need("SCENARIOS", SCENARIOS, 26); need("TIPS", TIPS, 26)
need("MISTAKES", MISTAKES, 26); need("PATTERNS", PATTERNS, 52)
need("AI", AI, 13); need("RISK", RISK, 13); need("FAQ", FAQ, 13); need("MYTHS", MYTHS, 13)
# year two: 53 + 5 x 52 + 26 + 26 = 365
need("SCHOOL", SCHOOL, 53); need("MARKETS", MARKETS, 52); need("INDICATORS2", INDICATORS2, 52)
need("DRAWING", DRAWING, 52); need("LAB", LAB, 52); need("CANDLES", CANDLES, 52)
need("VIEW", VIEW, 26); need("HIDDEN", HIDDEN, 26)

# ---- year one: days 1..365 (unchanged) ----
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

# ---- year two: days 366..730, same weekly slots; each slot holds a different kind than year one's ----
# slot 1 tool -> edu | 2 ind -> mkt | 3 howto -> ind2 | 4 cmp/scn -> draw | 5 tip/mis -> lab
# 6 pat -> view/more (alternate weeks) | 7 ai/risk/faq/myth -> cnd ; SCHOOL[0] pairs with the day-1 intro.
year2 = [dict(day=366, slot="—", series="edu", title=SCHOOL[0][0], angle=SCHOOL[0][1], anchor=SCHOOL[0][2])]
for w in range(52):
    base = 367 + w * 7
    week = [
        ("edu", SCHOOL[1 + w]),
        ("mkt", MARKETS[w]),
        ("ind2", INDICATORS2[w]),
        ("draw", DRAWING[w]),
        ("lab", LAB[w]),
        ("view", VIEW[w // 2]) if w % 2 == 0 else ("more", HIDDEN[w // 2]),
        ("cnd", CANDLES[w]),
    ]
    for k, (s, item) in enumerate(week):
        year2.append(dict(day=base + k, slot=k + 1, series=s, title=item[0], angle=item[1], anchor=item[2]))

assert len(year2) == 365, len(year2)
assert all(a["slot"] == b["slot"] and b["day"] == a["day"] + 365 for a, b in zip(days, year2))
assert all(set(SERIES) >= {d["series"]} for d in days + year2)

# ---- interleave: old 1, new 366, old 2, new 367, ... ----
days = [d for pair in zip(days, year2) for d in pair]
assert len(days) == 730, len(days)

titles = [d["title"] for d in days]
if len(set(titles)) != len(titles):
    from collections import Counter
    raise SystemExit("exact duplicates: " + str([t for t, c in Counter(titles).items() if c > 1]))
clashes = find_clashes(titles)
if clashes:
    for i, j, a, b in clashes:
        print(f"CLASH day {days[i]['day']} <-> day {days[j]['day']}: {a} | {b}")
    raise SystemExit(f"{len(clashes)} clashes")

here = os.path.dirname(os.path.abspath(__file__))
json.dump(days, open(os.path.join(here, "bank.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(here, "bank.csv"), "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["روز", "سری", "عنوان (همین در دفتر ضدتکرار ثبت میشود)", "زاویه", "جای آن در پروچارت"])
    for d in days:
        wr.writerow([d["day"], SERIES[d["series"]], d["title"], d["angle"], d["anchor"]])
# titles.txt: "<day>. <title>", one a line, in file order (the order sessions take them)
with open(os.path.join(here, "titles.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(f"{d['day']}. {d['title']}" for d in days))

from collections import Counter
cnt = Counter(d["series"] for d in days)
print("OK 730 entries (365 + 365 interleaved), no clashes;", {SERIES[k]: v for k, v in cnt.items()})
