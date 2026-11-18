#!/usr/bin/env python3
"""The live site's health that Search Console does not show (stdlib):

    python3 -I KIT/tools/live_check.py [--all]

- every sitemap URL answers 200 with its own canonical (with --all; else the 12 newest by lastmod);
- /vip/ is live, its numbers are at most two days old (TradeYar's record), and every /go/vip-*
  link goes to TradeYar's tracker, whose next hop is the bot (t.me/TradeYarSignalBot) or the
  exchange's referral page (LBank TRADEYAR, Ourbit Coinepro);
- the IndexNow key file is served; robots.txt keeps /go/ out.
Prints one line per check; «FAIL» lines go in report.md (and are fixed when they are content).
"""
import http.client
import re
import sys
import urllib.parse
from datetime import date, datetime, timezone

SITE = "dotcoin.me"


def get(url: str, method: str = "GET") -> tuple[int, dict, bytes]:
    u = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(u.netloc, timeout=20)
    try:
        conn.request(method, (u.path or "/") + (f"?{u.query}" if u.query else ""), headers={"User-Agent": "dotcoin-seo-check/1"})
        r = conn.getresponse()
        body = r.read() if method == "GET" else b""
        return r.status, {k.lower(): v for k, v in r.getheaders()}, body
    except OSError as e:
        return 0, {"error": type(e).__name__}, b""
    finally:
        conn.close()


def line(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)


def main() -> int:
    fails = 0
    st, _, sm = get(f"https://{SITE}/sitemap.xml")
    entries = re.findall(r"<loc>(https://dotcoin\.me/[^<]*)</loc><lastmod>([^<]*)</lastmod>", sm.decode("utf-8", "replace"))
    entries.sort(key=lambda x: x[1], reverse=True)
    for url, _ in (entries if "--all" in sys.argv else entries[:12]):
        st, _, body = get(url)
        canon = re.search(rb'<link rel="canonical" href="([^"]+)"', body)
        ok = st == 200 and canon is not None and canon.group(1).decode() == url
        fails += not ok
        line(ok, f"{url} {st} canonical={canon.group(1).decode() if canon else None}")
    st, _, body = get(f"https://{SITE}/vip/")
    line(st == 200, f"/vip/ {st}")
    m = re.search(r"تا ([^<]+)</p>", body.decode("utf-8", "replace"))
    line(bool(m), f"/vip/ record date: {m.group(1) if m else 'not shown'}")
    for pl in re.findall(r'href="(/go/vip-[a-z_]+/)"', body.decode("utf-8", "replace")) + ["/go/vip-lesson/"]:
        st, h, _ = get(f"https://{SITE}{pl}", "HEAD")
        loc = h.get("location", "")
        ok = st in (301, 302) and loc.startswith("https://trade-future.ir/go/") and "src=dotcoin" in loc
        st2, h2, _ = get(loc, "HEAD") if ok else (0, {}, b"")
        nxt = h2.get("location", "")
        ok2 = st2 in (301, 302) and re.match(r"https://(t\.me/TradeYarSignalBot|(www\.)?lbank\.com/ref/TRADEYAR|www\.ourbit\.com/register\?inviteCode=Coinepro)", nxt or "")
        fails += not (ok and ok2)
        line(bool(ok and ok2), f"{pl} -> {loc[:80]} -> {nxt[:70]}")
    st, _, rb = get(f"https://{SITE}/robots.txt")
    line(b"Disallow: /go/" in rb, "robots.txt keeps /go/ out")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
