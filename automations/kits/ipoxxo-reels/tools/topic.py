#!/usr/bin/env python3
"""The ipoxxo topic bank (KIT/topics.md): take the next free topic, mark it, never repeat one.

usage (python3 -I KIT/tools/topic.py …; stdlib only):
  next --slot noon|evening        the first `free` row of the slot's lane (the other lane when it is used up)
  mark <#> <status>               set a row's status: used:<YYYY-MM-DD>:<noon|evening> · taken · free · sample:<date>
  day <YYYY-MM-DD>                the topics marked for that publish day (the stories' teaser reads it)
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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROW = re.compile(r"^\|\s*(\d+)\s*\|")
STATUS = re.compile(r"^(free|taken|used:\d{4}-\d{2}-\d{2}:(noon|evening)|sample:\d{4}-\d{2}-\d{2})$")
LANES = ("noon", "evening")
COLS = ("#", "status", "lane", "topic", "hook", "payoff", "source")


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
        if not c[3] or not c[6].startswith("http"):
            errs.append(f"#{r['n']}: a topic and a source are required")
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
        print(f"{len(rs)} topics; free: {free['noon']} noon, {free['evening']} evening")
        for e in errs:
            print("ERROR", e)
        sys.exit(1 if errs else 0)
    if cmd == "next":
        slot = args[args.index("--slot") + 1] if "--slot" in args else "noon"
        if slot not in LANES:
            sys.exit("--slot noon|evening")
        rs = [r for r in rows(text) if r["cells"][1] == "free"]
        pick = next((r for r in rs if r["cells"][2] == slot), None) or (rs[0] if rs else None)
        if pick is None:
            sys.exit("the bank is used up: invent a topic in the same spirit, add it at the end, then mark it")
        print(show(pick))
        return
    if cmd == "mark":
        n, st = int(args[1]), args[2]
        if not STATUS.match(st):
            sys.exit(f"bad status «{st}» (used:<YYYY-MM-DD>:<noon|evening> · taken · free · sample:<date>)")
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
        day = args[1]
        for r in rows(text):
            if r["cells"][1].startswith(f"used:{day}:"):
                print(f"{r['cells'][1].split(':')[2]}: #{r['n']} {r['cells'][3]} | {r['cells'][4]}")
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
