#!/usr/bin/env python3
"""A @behnamjalali.tech topic bank (KIT/topics.md): take the next free topic, mark it, never repeat one.

The bank names its own lanes and slots in two comment lines near its top:
  <!-- lanes: repo tool trick model explain behind -->
  <!-- slots: day night -->
A lane is the kind of topic (a reel's «نوع امروز» picks it); a slot is which daily flow took it.

usage (python3 -I KIT/tools/topic.py …; stdlib only):
  next --lane <lane> [--lane <lane2> …]
                                  the first `free` row of the first lane that has one (never another lane's)
  find <words…>                   rows whose topic or source holds every word (a duplicate check before inventing)
  mark <#> --slot <slot> --publish "۲۸ آبان"
                                  the topic is taken for that publish day: the day and month exactly as the order
                                  writes them (Jalali; the nearest such date to today) -> used:<YYYY-MM-DD>:<slot>
  mark <#> <status>               set a row's status: used:<YYYY-MM-DD>:<slot> · taken · free · sample:<date>
  add <lane> "<topic>" "<hook>" "<payoff>" "<ending>" <source-url>
                                  a new row at the end (the next number, free), then `mark` it
  day today|<YYYY-MM-DD>|"۲۸ آبان"  the topics marked for that publish day (the stories read it)
  check                           the table is sound (columns, numbers, statuses, lanes); exit 1 otherwise
  merge <old topics.md>           (sync.sh) this file with every non-free status of the old copy, to stdout
  --file PATH                     another bank (default: the kit's own topics.md)

The status column is the ONLY thing a session changes in the kit (and `add` appends a row). A mark takes a
lock and writes the file atomically, so two sessions never trip over each other.
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
COLS = ("#", "status", "lane", "topic", "hook", "payoff", "ending", "source")
LANES: tuple = ()
SLOTS: tuple = ()
STATUS = re.compile(r"^$")


def configure(text):
    """The bank's own lanes and slots (its two comment lines)."""
    global LANES, SLOTS, STATUS
    lanes = re.search(r"<!--\s*lanes:\s*([a-z0-9_ ]+?)\s*-->", text)
    slots = re.search(r"<!--\s*slots:\s*([a-z0-9_ ]+?)\s*-->", text)
    if not lanes or not slots:
        sys.exit("the bank has no `<!-- lanes: … -->` / `<!-- slots: … -->` lines")
    LANES, SLOTS = tuple(lanes.group(1).split()), tuple(slots.group(1).split())
    STATUS = re.compile(r"^(free|taken|used:\d{4}-\d{2}-\d{2}:(" + "|".join(SLOTS)
                        + r")|sample:\d{4}-\d{2}-\d{2})$")


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
    topics = {}
    for r in rows(text):
        k = re.sub(r"\W+", " ", r["cells"][3].lower()).strip() if len(r["cells"]) > 3 else ""
        if k and k in topics:
            errs.append(f"#{r['n']}: the same topic as #{topics[k]}")
        topics.setdefault(k, r["n"])
    return errs


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".topics.", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)


def clean(v):
    return " ".join(str(v).replace("|", "/").split())


def main():
    args = sys.argv[1:]
    path = path_of(args)
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "merge":
        new = open(path, encoding="utf-8").read()
        configure(new)
        old = {r["n"]: r["cells"][1] for r in rows(open(args[1], encoding="utf-8").read())}
        lines = new.splitlines()
        for r in rows(new):
            st = old.get(r["n"])
            if st and st != "free" and r["cells"][1] == "free" and STATUS.match(st):
                c = r["cells"]
                c[1] = st
                lines[r["line"]] = "| " + " | ".join(c) + " |"
        # rows a session added on the workshop (numbers past the source's) are kept at the end
        top = max((r["n"] for r in rows(new)), default=0)
        for r in rows(open(args[1], encoding="utf-8").read()):
            if r["n"] > top and len(r["cells"]) == len(COLS):
                lines.append("| " + " | ".join(r["cells"]) + " |")
        sys.stdout.write("\n".join(lines) + "\n")
        return
    lock = open(path + ".lock" if os.access(os.path.dirname(os.path.abspath(path)), os.W_OK) else os.devnull, "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    text = open(path, encoding="utf-8").read()
    configure(text)
    if cmd == "check":
        errs = check(text)
        rs = rows(text)
        free = {ln: sum(1 for r in rs if r["cells"][1] == "free" and r["cells"][2] == ln) for ln in LANES}
        print(f"{len(rs)} topics; free: " + ", ".join(f"{free[ln]} {ln}" for ln in LANES))
        for e in errs:
            print("ERROR", e)
        sys.exit(1 if errs else 0)
    if cmd == "next":
        lanes = [args[k + 1] for k, a in enumerate(args) if a == "--lane" and k + 1 < len(args)]
        bad = [ln for ln in lanes if ln not in LANES]
        if not lanes or bad:
            sys.exit("--lane " + "|".join(LANES))
        rs = [r for r in rows(text) if r["cells"][1] == "free"]
        pick = next((r for ln in lanes for r in rs if r["cells"][2] == ln), None)
        if pick is None:
            sys.exit("the lane is used up: `find` the idea first, then `add` a topic in the same spirit and mark it")
        print(show(pick))
        return
    if cmd == "find":
        words = [w.lower() for w in args[1:]]
        for r in rows(text):
            hay = (r["cells"][3] + " " + r["cells"][-1]).lower()
            if words and all(w in hay for w in words):
                print(f"#{r['n']} [{r['cells'][1]}] {r['cells'][2]}: {r['cells'][3]}")
        return
    if cmd == "add":
        if len(args) != 7 or args[1] not in LANES or not args[6].startswith("http"):
            sys.exit('add <lane> "<topic>" "<hook>" "<payoff>" "<ending>" <source-url>')
        n = max((r["n"] for r in rows(text)), default=0) + 1
        row = "| " + " | ".join([str(n), "free", args[1], *(clean(a) for a in args[2:6]), clean(args[6])]) + " |"
        out = text.rstrip("\n") + "\n" + row + "\n"
        errs = check(out)
        if errs:
            sys.exit("; ".join(errs))
        write_atomic(path, out)
        print(f"#{n} added ({args[2]})")
        return
    if cmd == "mark":
        n = int(args[1])
        if "--publish" in args:
            slot = args[args.index("--slot") + 1] if "--slot" in args else ""
            if slot not in SLOTS:
                sys.exit("--slot " + "|".join(SLOTS))
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
                print(f"{r['cells'][1].split(':')[2]}: #{r['n']} {r['cells'][2]} · {r['cells'][3]} | {r['cells'][4]}")
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
