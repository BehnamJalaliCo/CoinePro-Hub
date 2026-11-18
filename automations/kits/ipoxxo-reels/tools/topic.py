#!/usr/bin/env python3
"""The ipoxxo topic bank (KIT/topics.md): take the next free topic, mark it, never repeat one.

usage (python3 -I KIT/tools/topic.py …; stdlib only):
  next --slot noon|afternoon|evening
                                  the first `free` row of the slot's lane (another lane's when it is used up)
  mark <#> --slot noon|afternoon|evening --publish "۲۸ آبان"
                                  the topic is taken for that publish day: the day and month exactly as the order
                                  writes them (Jalali; the nearest such date to today) -> used:<YYYY-MM-DD>:<slot>
  mark <#> <status>               set a row's status: used:<YYYY-MM-DD>:<slot> · taken · free · sample:<date>
  day today|<YYYY-MM-DD>|"۲۸ آبان"  the topics marked for that publish day (the stories' teaser: `day today`)
  check                           the table is sound (columns, numbers, statuses); exit 1 otherwise
  merge <old topics.md>           (sync.sh) this file with every non-free status of the old copy, to stdout
  --file PATH                     another topics.md (default: the kit's own)

The status column is the ONLY thing a session changes in the kit (README step 1). A mark takes a lock and
writes the file atomically, so the day's two sessions never trip over each other; the lanes keep them apart.
"""
import fcntl
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROW = re.compile(r"^\|\s*(\d+)\s*\|")
STATUS = re.compile(r"^(free|taken|used:\d{4}-\d{2}-\d{2}:(noon|afternoon|evening)|sample:\d{4}-\d{2}-\d{2})$")
LANES = ("noon", "afternoon", "evening")
COLS = ("#", "status", "lane", "topic", "hook", "payoff", "ending", "source")


MONTHS_FA = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_jalali(d):
    """Gregorian -> Jalali, the hub's own algorithm (apps/api/src/hq_api/worker/jalali.py)."""
    gy, gm, gd = d.year, d.month, d.day
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd
            + (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def tehran_today():
    return datetime.now(ZoneInfo("Asia/Tehran")).date()


def day_of(text):
    """«۲۸ آبان» (the order's words) / «today» / YYYY-MM-DD -> a date; the Jalali day nearest to today."""
    t = text.strip()
    if t == "today":
        return tehran_today()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return date.fromisoformat(t)
    m = re.search(r"(\d{1,2})\s*(" + "|".join(MONTHS_FA) + ")", t.translate(FA_DIGITS))
    if not m:
        sys.exit(f"cannot read the day «{text}» (e.g. «۲۸ آبان», today, 2026-11-19)")
    jd, jm = int(m.group(1)), MONTHS_FA.index(m.group(2)) + 1
    base = tehran_today()
    for k in range(0, 200):
        for d in (base + timedelta(days=k), base - timedelta(days=k)):
            if to_jalali(d)[1:] == (jm, jd):
                return d
    sys.exit(f"no date near today is {jd} {MONTHS_FA[jm - 1]}")


def path_of(args):
    if "--file" in args:
        i = args.index("--file")
        p = args[i + 1]
        del args[i:i + 2]
        return p
    return os.path.join(HERE, "topics.md")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def rows(text):
    out = []
    for k, line in enumerate(text.splitlines()):
        if ROW.match(line):
            c = cells(line)
            out.append({"line": k, "n": int(c[0]), "cells": c})
    return out


def show(r):
    c = r["cells"]
    return "\n".join(f"{name}: {val}" for name, val in zip(COLS, c))


def check(text):
    errs, seen = [], set()
    for r in rows(text):
        c = r["cells"]
        if len(c) != len(COLS):
            errs.append(f"#{r['n']}: {len(c)} columns, not {len(COLS)}")
            continue
        if r["n"] in seen:
            errs.append(f"#{r['n']}: the number is used twice")
        seen.add(r["n"])
        if not STATUS.match(c[1]):
            errs.append(f"#{r['n']}: bad status «{c[1]}»")
        if c[2] not in LANES:
            errs.append(f"#{r['n']}: bad lane «{c[2]}»")
        if not c[3] or not c[6] or not c[7].startswith("http"):
            errs.append(f"#{r['n']}: a topic, its ending and a source are required")
    return errs


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".topics.", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)


def main():
    args = sys.argv[1:]
    path = path_of(args)
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "merge":
        new = open(path, encoding="utf-8").read()
        old = {r["n"]: r["cells"][1] for r in rows(open(args[1], encoding="utf-8").read())}
        lines = new.splitlines()
        for r in rows(new):
            st = old.get(r["n"])
            if st and st != "free" and r["cells"][1] == "free" and STATUS.match(st):
                c = r["cells"]
                c[1] = st
                lines[r["line"]] = "| " + " | ".join(c) + " |"
        sys.stdout.write("\n".join(lines) + "\n")
        return
    lock = open(path + ".lock" if os.access(os.path.dirname(os.path.abspath(path)), os.W_OK) else os.devnull, "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    text = open(path, encoding="utf-8").read()
    if cmd == "check":
        errs = check(text)
        rs = rows(text)
        free = {ln: sum(1 for r in rs if r["cells"][1] == "free" and r["cells"][2] == ln) for ln in LANES}
        print(f"{len(rs)} topics; free: " + ", ".join(f"{free[ln]} {ln}" for ln in LANES))
        for e in errs:
            print("ERROR", e)
        sys.exit(1 if errs else 0)
    if cmd == "next":
        slot = args[args.index("--slot") + 1] if "--slot" in args else "noon"
        if slot not in LANES:
            sys.exit("--slot noon|afternoon|evening")
        rs = [r for r in rows(text) if r["cells"][1] == "free"]
        pick = next((r for r in rs if r["cells"][2] == slot), None) or (rs[0] if rs else None)
        if pick is None:
            sys.exit("the bank is used up: invent a topic in the same spirit, add it at the end, then mark it")
        print(show(pick))
        return
    if cmd == "mark":
        n = int(args[1])
        if "--publish" in args:
            slot = args[args.index("--slot") + 1] if "--slot" in args else ""
            if slot not in LANES:
                sys.exit("--slot noon|afternoon|evening")
            st = f"used:{day_of(args[args.index('--publish') + 1]).isoformat()}:{slot}"
        else:
            st = args[2]
        if not STATUS.match(st):
            sys.exit(f"bad status «{st}» (used:<YYYY-MM-DD>:<slot> · taken · free · sample:<date>)")
        lines = text.splitlines()
        for r in rows(text):
            if r["n"] == n:
                c = r["cells"]
                was, c[1] = c[1], st
                lines[r["line"]] = "| " + " | ".join(c) + " |"
                write_atomic(path, "\n".join(lines) + "\n")
                print(f"#{n}: {was} -> {st} ({c[3]})")
                return
        sys.exit(f"no row #{n}")
    if cmd == "day":
        day = day_of(" ".join(args[1:])).isoformat()
        for r in rows(text):
            if r["cells"][1].startswith(f"used:{day}:"):
                print(f"{r['cells'][1].split(':')[2]}: #{r['n']} {r['cells'][3]} | {r['cells'][4]}")
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
