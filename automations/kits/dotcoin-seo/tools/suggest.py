#!/usr/bin/env python3
"""Google's own autocomplete in Persian (what people really type; never a volume):

    python3 -I KIT/tools/suggest.py "سیگنال ارز دیجیتال" [--deep]

Prints the suggestions for the phrase, and with --deep for the phrase followed by the question
words (چیست، چطور، چگونه، آیا، بهترین، فرق، یعنی) and by each Persian letter: the long tail and the
FAQ questions of a cluster. One request a second (Google's public endpoint, no key).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

URL = "https://suggestqueries.google.com/complete/search?client=firefox&hl=fa&gl=ir&q="
WORDS = ["چیست", "چطور", "چگونه", "آیا", "بهترین", "فرق", "یعنی", "کجا", "چرا"]
LETTERS = list("ابپتجچحخدرزسشصطعفقکگلمنوهی")


def ask(q: str) -> list[str]:
    req = urllib.request.Request(URL + urllib.parse.quote(q), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return [s for s in json.loads(r.read().decode("utf-8", "replace"))[1] if s != q]
    except (OSError, ValueError, IndexError):
        return []


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    q = sys.argv[1].strip()
    seen: dict[str, str] = {}
    probes = [q] + ([f"{q} {w}" for w in WORDS] + [f"{q} {c}" for c in LETTERS] if "--deep" in sys.argv else [])
    for p in probes:
        for s in ask(p):
            seen.setdefault(s, p)
        time.sleep(1)
    for s, p in seen.items():
        print(f"{s}\t(from «{p}»)")
    print(f"# {len(seen)} suggestions", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
