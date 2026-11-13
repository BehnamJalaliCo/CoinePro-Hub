# -*- coding: utf-8 -*-
"""Local copy of the hub's anti-repeat rule, stricter on purpose.

Hub rule (topic.claim): same words in any order, or four words of five in common = same topic.
Here: normalise Persian, keep every word (stop words too, as the hub may), and flag a pair when
  - the word sets are equal, or
  - common >= 4, or
  - common >= 2 and common / min(len) >= 0.75.
"""
import re

ZWNJ = "‌"
_AR2FA = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا"})
_SUFFIXES = ("‌های", "‌ها", "‌ی", "های", "ها")


def words(title):
    t = title.translate(_AR2FA).lower()
    t = re.sub(r"[ً-ْ]", "", t)  # diacritics
    t = re.sub(r"[«»:؛،,.!?؟()\[\]\-–—/\"']", " ", t)
    out = []
    for w in t.split():
        for s in _SUFFIXES:
            if w.endswith(s) and len(w) > len(s) + 1:
                w = w[: -len(s)]
                break
        w = w.replace(ZWNJ, "")
        if w:
            out.append(w)
    return set(out)


def clash(a, b):
    A, B = words(a), words(b)
    if not A or not B:
        return False
    common = len(A & B)
    if A == B:
        return True
    if common >= 4:
        return True
    return common >= 2 and common / min(len(A), len(B)) >= 0.75


def find_clashes(titles):
    bad = []
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            if clash(titles[i], titles[j]):
                bad.append((i, j, titles[i], titles[j]))
    return bad


if __name__ == "__main__":
    import sys, json
    titles = json.load(open(sys.argv[1], encoding="utf-8"))
    for i, j, a, b in find_clashes(titles):
        print(f"{i+1} <-> {j+1}: {a}  |  {b}")
