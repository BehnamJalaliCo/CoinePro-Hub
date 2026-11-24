#!/usr/bin/env python3
"""DotCoin.me's daily SEO automation, the hub's host side (stdlib; user Hub; dotcoin-seo.timer).

The owner (2026-11-18): «اتوماسیون سئو سایت دات کوین … فوق متخصص … هر روز بیشتر دیده شدن و به صفحه
اول گوگل اومدن». The flow `dotcoin_seo` (automations.flows, kind `article`) makes one SEO day a
day on the workshop (kit dotcoin-seo). This script does what the session cannot:

  BEFORE the day's build (from PREP_BEFORE ahead of its build hour), once per day: reads Search
  Console in the hub's signed-in profile `youtube-web` (egress recipe tasks gsc_28d, gsc_7d: the
  Performance export; gsc_pages: Page indexing; gsc_sitemap: the sitemap submitted again and its
  status; gsc_inspect: URL inspection of the pages that need a look), TradeYar's public record (the
  VIP page's numbers), the live sitemap; keeps every day's raw data in /home/Hub/sites/dotcoin-seo;
  and hands the session its input pack: /home/studio/seo-inputs/dotcoin/<day>/ (as the studio
  user): the site's source at the content branch's HEAD (site.tar + BASE), the private brand
  files to build with, the Search Console history, the index state, what the previous days'
  packages did (applied.json) and what could not be read (errors.json).

  AFTER, at the day's publish hour: each queued run (flows._queue_article: run_meta.flow.site =
  queued) once: its out/package.zip checked (tools/seo_pack.py: only content and seo/auto, no
  deletion, no slug change, no long-video slug, lesson rules of sync.py), applied to the content
  worktree with a 3-way merge per file (a file changed since the snapshot and in conflict is left
  out and reported), the VIP numbers refreshed, the whole site built (bidi lint) and every touched
  page reviewed at 390 px light and dark (tools/review.py: no overflow; screenshots kept), else
  everything is put back; then one commit, the site sync (push, build, deploy), the new pages
  checked live, IndexNow (Bing, Yandex) for every new or changed URL, the sitemap submitted again
  and «Request indexing» in Search Console for the day's most important URLs (Google's own daily
  cap: stops at its first refusal).

Never prints a secret. One lock. An idle pass is one database read. State:
/home/Hub/sites/dotcoin-seo.json; the browser's lock is youtube.py's (one job in the profile).

    seo.py --due                 the timer's pass (prepare when due, then apply what is due)
    seo.py --prepare [--day D]   the input pack of day D now (default: the next SEO day)
    seo.py --apply W-000700      apply one run again (after a fix; never twice once done)
    seo.py --vip-stats           refresh content/vip_stats.json from TradeYar's public API
    seo.py --status              the state, short
"""
from __future__ import annotations

import argparse
import fcntl
import base64
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import youtube as Y  # noqa: E402  (its database read, egress client, browser lock, logging)
import seo_pack as P  # noqa: E402  (the package's rules)

WT, SITE, HOME = Y.WT, Y.SITE, Y.HOME
REL_SITE = "automations/sites/dotcoin"
STATE, LOCK = HOME / "dotcoin-seo.json", HOME / "dotcoin-seo.lock"
DATA = HOME / "dotcoin-seo"  # every day's raw Search Console data, reviews, the session's reports
INPUTS = Path("/home/studio/seo-inputs/dotcoin")  # the studio user's (sudo -n -u studio)
WORKSPACE = Path("/home/studio/hq-workspace")
STUDIO_PY = "/home/studio/kits/prochart-reels/venv-render/bin/python"
PW_PATH = "/home/studio/kits/prochart-reels/ms-playwright"
FONTS_NOTE = "private/: the fonts and the logo made from the studio's own kit files (deploy.sh)"
TZ = ZoneInfo("Asia/Tehran")
ACCOUNT = "dotcoin.me"
URL = "https://dotcoin.me"
PREP_BEFORE, PREP_AFTER = timedelta(minutes=150), timedelta(hours=8)
KEEP_DAYS = 120  # the history the pack carries (the raw data stays on the host)
INSPECT_MAX = 12  # URL inspections a day (each about 30 s in the browser)
REQUEST_MAX = 8  # «Request indexing» a day (Google's own cap is about ten)
OUT_FILES = ("package.zip", "summary.fa.txt", "report.md", "topic.txt", "week.fa.txt")
TY_API = "https://tradeyar.trade-future.ir/api/v1/public/performance/summary"
INDEXNOW = "https://api.indexnow.org/indexnow"
CF_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
SECRETS = Path(os.environ.get("DOTCOIN_SECRETS", "/home/Hub/.secrets/dotcoin"))
REF_RE = re.compile(r"W-\d{3,9}")
log, tail, run = Y.log, Y.tail, Y.run

FLOW_SQL = """SELECT f.key, f.ref, f.state, f.schedule, f.skips, f.paused_until
                FROM automations.flows f WHERE f.kind = 'article' AND f.account = 'dotcoin.me'
               ORDER BY f.ref"""
DUE_SQL = """
    SELECT w.ref, w.run_meta -> 'flow' ->> 'key' AS key, w.run_meta -> 'flow' ->> 'day' AS day,
           w.run_meta -> 'flow' ->> 'publish_at' AS publish_at
      FROM work.work w
     WHERE w.run_meta -> 'flow' ->> 'kind' = 'article' AND w.run_meta -> 'flow' ->> 'account' = 'dotcoin.me'
       AND w.run_meta -> 'flow' ->> 'site' = 'queued'
       AND (w.run_meta -> 'flow' ->> 'publish_at')::timestamptz <= now()
       AND w.created_at > now() - interval '14 days'
     ORDER BY w.created_at"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ state
def load_state() -> dict:
    try:
        s = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    for k in ("runs", "prep", "requests", "inspected"):
        s.setdefault(k, {})
    return s


def save_state(s: dict) -> None:
    s["last_change"] = Y.now()
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(STATE)


# ------------------------------------------------------------------ the network (IPv4: the Cloudflare token is IPv4-bound)
def http(url: str, *, data: bytes | None = None, headers: dict | None = None, timeout: int = 30,
         method: str | None = None) -> tuple[int, bytes]:
    orig = socket.getaddrinfo

    def v4(host, *a, **k):
        return [r for r in orig(host, *a, **k) if r[0] == socket.AF_INET]

    socket.getaddrinfo = v4
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "dotcoin-seo/1", **(headers or {})},
                                     method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:4000]
    except OSError as e:
        return 0, str(type(e).__name__).encode()
    finally:
        socket.getaddrinfo = orig


# ------------------------------------------------------------------ the flow and its days
def flows() -> list[dict]:
    out = []
    for r in Y.sql(FLOW_SQL):
        sch = r["schedule"] if isinstance(r["schedule"], dict) else json.loads(r["schedule"] or "{}")
        r["schedule"] = sch
        out.append(r)
    return out


def build_at(flow: dict, day: date) -> datetime:
    """When the order of `day` is placed (flows.trigger_of): its trigger_at (Tehran) that day when
    same_day, else the day before."""
    sch = flow["schedule"]
    hh, mm = (int(x) for x in str(sch.get("trigger_at") or "22:00").split(":"))
    on = day if sch.get("same_day") else day - timedelta(days=1)
    return datetime.combine(on, time(hh, mm), TZ).astimezone(timezone.utc)


def day_held(flow: dict, day: date) -> bool:
    sch = flow["schedule"]
    if str(flow.get("state")) == "off":
        return True
    if day < date.fromisoformat(str(sch.get("start") or "2000-01-01")):
        return True
    if str(day) in {str(x) for x in flow.get("skips") or []}:
        return True
    days = sch.get("days") or list(range(7))
    if (day.weekday() + 2) % 7 not in days:
        return True
    pu = flow.get("paused_until")
    return str(flow.get("state")) == "paused" and (pu is None or str(day) < str(pu))


def next_day(flow: dict, now: datetime) -> date | None:
    """The SEO day whose inputs are due now: its build within [build - PREP_BEFORE, build + PREP_AFTER]."""
    today = now.astimezone(TZ).date()
    for d in (today - timedelta(days=1), today, today + timedelta(days=1), today + timedelta(days=2)):
        if day_held(flow, d):
            continue
        b = build_at(flow, d)
        if b - PREP_BEFORE <= now <= b + PREP_AFTER:
            return d
    return None


# ------------------------------------------------------------------ Search Console through the profile browser
def gsc(task: str, prompt: str, timeout_s: int) -> dict:
    """One Search Console job in the youtube-web profile (youtube.py's lock: one job at a time)."""
    with lock_browser():
        ans = Y.egress(task, prompt, timeout_s)
    if not ans.get("ok") and ans.get("error") == "off" and task_in_recipe(task):
        ans["detail"] = f"egress has not loaded the task yet (rebuild egress): {ans.get('detail') or ''}"[:300]
    return ans


def task_in_recipe(task: str) -> bool:
    try:
        return f"\n  {task}:\n" in Y.RECIPE.read_text("utf-8")
    except OSError:
        return False


class lock_browser:
    """youtube.py's lock (the Shorts and long-video passes use the same profile), waited for."""

    def __enter__(self):
        import time as _t

        HOME.mkdir(parents=True, exist_ok=True)
        self.f = open(Y.LOCK, "w")  # noqa: SIM115
        end = _t.monotonic() + 900
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if _t.monotonic() > end:
                    self.f.close()
                    raise RuntimeError("the YouTube pass holds the browser for over 15 minutes") from None
                _t.sleep(5)

    def __exit__(self, *exc):
        self.f.close()


def unzip_csvs(b64: str) -> dict[str, list[dict]]:
    """Search Console's export (a ZIP of CSV files) -> {name: rows}."""
    import csv

    data = base64.b64decode(b64)
    out: dict[str, list[dict]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            text = z.read(name).decode("utf-8-sig", "replace")
            out[name[:-4]] = list(csv.DictReader(io.StringIO(text)))
    return out


INSPECT_FIELDS = {
    "verdict": r"(URL is on Google|URL is not on Google|URL is unknown to Google|URL is on Google, but has issues)",
    "coverage": r"Page indexing\s+(Page is indexed|Page is not indexed: [^\n]+?)(?:\s{2,}|\s+Discovery|\s+Enhancements|$)",
    "last_crawl": r"Last crawl\s+([0-9]{1,2} [A-Z][a-z]{2} [0-9]{4}, [0-9:]+)",
    "sitemaps": r"Sitemaps\s+(No referring sitemaps detected|https://\S+)",
    "canonical_google": r"Google-selected canonical\s+(https://\S+|Inspected URL|N/A)",
}


def parse_inspect(text: str) -> dict:
    out = {}
    flat = re.sub(r"[ \t]+", " ", text)
    for k, rx in INSPECT_FIELDS.items():
        m = re.search(rx, flat)
        if m:
            out[k] = m.group(1).strip()
    out["indexed"] = "URL is on Google" in flat and "is not on Google" not in flat
    return out


def sitemap_urls() -> tuple[list[str], str]:
    st, body = http(f"{URL}/sitemap.xml")
    xml = body.decode("utf-8", "replace") if st == 200 else ""
    return re.findall(r"<loc>(https://dotcoin\.me/[^<]*)</loc>", xml), xml


def read_search_console(day: date, state: dict, errors: list[str]) -> dict:
    """Today's reads into DATA/gsc/<today>/ (once a day; a later pass the same day reuses them)."""
    stamp = now_utc().date().isoformat()
    folder = DATA / "gsc" / stamp
    folder.mkdir(parents=True, exist_ok=True)
    got: dict = {}
    for task, name in (("gsc_28d", "28d"), ("gsc_7d", "7d")):
        f = folder / f"{name}.json"
        if f.exists():
            got[name] = json.loads(f.read_text("utf-8"))
            continue
        ans = gsc(task, "export", 150)
        file = ans.get("file") or {}
        if ans.get("ok") and file.get("mime") == "application/zip":
            rows = unzip_csvs(file["b64"])
            f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
            got[name] = rows
        else:
            errors.append(f"{task}: {Y.why(ans)}"[:300])
    for task, name, prompt in (("gsc_pages", "pages", "pages"), ("gsc_sitemap", "sitemap", "sitemap.xml")):
        f = folder / f"{name}.txt"
        if f.exists():
            continue
        ans = gsc(task, prompt, 120)
        if ans.get("ok") and ans.get("text_md"):
            f.write_text(str(ans["text_md"]), "utf-8")
        else:
            errors.append(f"{task}: {Y.why(ans)}"[:300])
    # URL inspection: the pages never looked at first (a new page is one), then the oldest look
    urls, _ = sitemap_urls()
    seen = state["inspected"]
    newest = sorted(urls, key=lambda u: seen.get(u, {}).get("at", ""))[:INSPECT_MAX]
    done_today = [u for u, v in seen.items() if str(v.get("at", "")).startswith(stamp)]
    for u in newest:
        if len(done_today) >= INSPECT_MAX or u in done_today:
            continue
        ans = gsc("gsc_inspect", u, 150)
        if ans.get("ok") and ans.get("text_md"):
            seen[u] = {**parse_inspect(str(ans["text_md"])), "at": Y.now()}
            done_today.append(u)
        else:
            errors.append(f"gsc_inspect {u}: {Y.why(ans)}"[:300])
            if ans.get("error") in ("expired", "off"):
                break
    (folder / "inspect.json").write_text(json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    return got


# ------------------------------------------------------------------ TradeYar's VIP numbers, the VIP clicks
def vip_stats() -> dict | None:
    st, body = http(TY_API, timeout=30)
    if st != 200:
        return None
    try:
        d = json.loads(body)
        s = d["summary"]
        w30 = (d.get("windows") or {}).get("30d") or {}
    except (ValueError, KeyError):
        return None

    def v(x, k):
        return (x.get(k) or {}).get("value")

    if not v(s, "trades"):
        return None
    return {"_note": "TradeYar's public record (its own public API, no key); written by seo.py --vip-stats, never by hand.",
            "source": TY_API, "methodology": (d.get("provenance") or {}).get("methodology_version"),
            "as_of": s["window"]["observed_end"], "from": s["window"]["observed_start"],
            "days": round(float(s["window"]["days"])), "trades": v(s, "trades"),
            "win_rate_pct": round(float(v(s, "win_rate_pct")), 1), "profit_factor": round(float(v(s, "profit_factor")), 2),
            "symbols": v(s, "symbols_covered"), "published_to_telegram": v(s, "published_to_telegram"),
            "d30_trades": v(w30, "trades"),
            "d30_win_rate_pct": round(float(v(w30, "win_rate_pct")), 1) if v(w30, "win_rate_pct") is not None else None}


def vip_clicks(days: int = 7) -> dict:
    """Clicks on the site's /go/vip-* links from Cloudflare's zone analytics; unavailable while the
    site's token has no Analytics Read (it is told so, never guessed)."""
    try:
        tok = (SECRETS / "cloudflare.token").read_text().strip()
        zone = json.loads((SECRETS / "cloudflare.ids").read_text())["zone_id"]
    except (OSError, ValueError, KeyError):
        return {"available": False, "why": "no Cloudflare token on this host"}
    end = now_utc().replace(minute=0, second=0, microsecond=0)
    q = {"query": """query($z:String!,$a:Time!,$b:Time!){viewer{zones(filter:{zoneTag:$z}){
            httpRequestsAdaptiveGroups(limit:200,filter:{datetime_geq:$a,datetime_lt:$b,requestSource:"eyeball",
            clientRequestPath_like:"/go/%"}){count dimensions{clientRequestPath}}}}}""",
         "variables": {"z": zone, "a": (end - timedelta(days=min(days, 1))).isoformat().replace("+00:00", "Z"),
                       "b": end.isoformat().replace("+00:00", "Z")}}
    st, body = http(CF_GRAPHQL, data=json.dumps(q).encode(), timeout=30,
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        d = json.loads(body)
    except ValueError:
        return {"available": False, "why": f"Cloudflare answered {st}"}
    if d.get("errors"):
        msg = str(d["errors"][0].get("message") or "")
        why = ("the site's Cloudflare token has no Analytics Read (the owner can add it to the token)"
               if "analytics" in msg.lower() or "permission" in msg.lower() else msg[:200])
        return {"available": False, "why": why}
    rows = (((d.get("data") or {}).get("viewer") or {}).get("zones") or [{}])[0].get("httpRequestsAdaptiveGroups") or []
    by = {}
    for r in rows:
        path = str((r.get("dimensions") or {}).get("clientRequestPath") or "").rstrip("/")
        by[path] = by.get(path, 0) + int(r.get("count") or 0)
    return {"available": True, "window_hours": 24, "until": end.isoformat(), "clicks": dict(sorted(by.items()))}


def refresh_vip_stats() -> bool:
    """content/vip_stats.json from TradeYar's API in the worktree (no commit); True when it changed."""
    new = vip_stats()
    path = SITE / "content" / "vip_stats.json"
    if new is None or not (SITE / "content" / "vip.json").exists():
        return False
    text = json.dumps(new, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text("utf-8") == text:
        return False
    path.write_text(text, "utf-8")
    return True


# ------------------------------------------------------------------ the input pack (as the studio user)
def as_studio(cmd: list[str], *, data: bytes | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    """A command as the studio user (the workshop's files); `data` goes to its stdin."""
    return subprocess.run(["sudo", "-n", "-u", "studio", *cmd], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)


def git_out(*args: str) -> str:
    r = run(["git", "-C", str(WT), *args], timeout=120)
    if r.returncode:
        raise RuntimeError(f"git {args[0]} failed: {tail(r.stderr, 1)}")
    return r.stdout.decode().strip()


def prepare(flow: dict, day: date, state: dict, *, force: bool = False) -> str:
    """The day's input pack into /home/studio/seo-inputs/dotcoin/<day>/, then `latest` -> it."""
    key = day.isoformat()
    if state["prep"].get(key, {}).get("done") and not force:
        return "ready"
    errors: list[str] = []
    gsc_got = read_search_console(day, state, errors)
    stats = vip_stats()
    clicks = vip_clicks()
    urls, xml = sitemap_urls()
    st, robots = http(f"{URL}/robots.txt")
    with tempfile.TemporaryDirectory(prefix="dotcoin-seo-pack-") as tmp:
        t = Path(tmp)
        base = git_out("rev-parse", "HEAD")
        (t / "BASE").write_text(base + "\n")
        arch = run(["git", "-C", str(WT), "archive", "--format=tar", "HEAD", REL_SITE,
                    "automations/kits/dotcoin-reels/bank/ideas.json"], timeout=120)
        if arch.returncode:
            raise RuntimeError(f"git archive failed: {tail(arch.stderr, 1)}")
        (t / "site.tar").write_bytes(arch.stdout)
        (t / "longform_topics.md").write_text(longform_topics(), "utf-8")
        with tarfile.open(t / "private.tar", "w") as tf:
            tf.add(SITE / "private", arcname="private")
        g = t / "gsc"
        g.mkdir()
        cutoff = (now_utc().date() - timedelta(days=KEEP_DAYS)).isoformat()
        for d in sorted((DATA / "gsc").glob("*")):
            if d.is_dir() and d.name >= cutoff:
                shutil.copytree(d, g / d.name)
        (t / "index").mkdir()
        (t / "index" / "inspected.json").write_text(json.dumps(state["inspected"], ensure_ascii=False, indent=1,
                                                               sort_keys=True), "utf-8")
        (t / "live").mkdir()
        (t / "live" / "sitemap.xml").write_text(xml, "utf-8")
        (t / "live" / "robots.txt").write_bytes(robots if st == 200 else b"")
        (t / "vip.json").write_text(json.dumps({"stats": stats, "clicks": clicks}, ensure_ascii=False, indent=1), "utf-8")
        (t / "applied.json").write_text(json.dumps(
            {"runs": dict(sorted(state["runs"].items())[-30:]), "requests": dict(sorted(state["requests"].items())[-14:])},
            ensure_ascii=False, indent=1), "utf-8")
        (t / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1), "utf-8")
        (t / "README.txt").write_text(
            f"DotCoin.me SEO input pack for {key}, made {Y.now()} by the hub (seo.py --prepare).\n"
            "BASE: the commit of site.tar (branch site/dotcoin-content); package against it.\n"
            "site.tar: the site's source + the reel bank's ideas.json. longform_topics.md: the long videos' "
            "topic bank as the workshop holds it (its slugs are reserved: never an SEO page).\n"
            f"private.tar: {FONTS_NOTE}.\n"
            "gsc/<UTC day>/: 28d.json, 7d.json (Search Console's Performance export: Chart, Queries, Pages, "
            "Countries, Devices, Search appearance), pages.txt (Page indexing), sitemap.txt (Sitemaps), "
            "inspect.json (URL inspection of every page looked at so far).\n"
            "index/inspected.json: the newest inspection of each URL. live/: the live sitemap and robots.\n"
            "vip.json: TradeYar's public record now, and the VIP links' clicks when readable.\n"
            "applied.json: what the hub did with each earlier day's package (applied, left out, why; "
            "IndexNow; «Request indexing» results). errors.json: what could not be read today.\n", "utf-8")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            tf.add(t, arcname=key)
        as_studio(["mkdir", "-p", str(INPUTS)])
        as_studio(["rm", "-rf", str(INPUTS / key)])
        r = as_studio(["tar", "-C", str(INPUTS), "-xf", "-"], data=buf.getvalue())
        if r.returncode:
            raise RuntimeError(f"the pack was not written: {tail(r.stderr, 1)}")
        as_studio(["ln", "-sfn", key, str(INPUTS / "latest")])
        # older packs: the last 10 days stay
        r = as_studio(["ls", str(INPUTS)])
        old = sorted(n for n in (r.stdout or b"").decode().split() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n))[:-10]
        for n in old:
            as_studio(["rm", "-rf", str(INPUTS / n)])
    state["prep"][key] = {"done": True, "at": Y.now(), "base": base, "errors": errors,
                          "gsc": sorted(gsc_got), "pages": len(urls)}
    for k in sorted(state["prep"])[:-20]:
        state["prep"].pop(k, None)
    log(f"input pack {key}: base {base[:10]}, {len(urls)} pages, {len(errors)} read errors")
    return "ready"


def longform_topics() -> str:
    """The long videos' topic bank as the workshop holds it (its statuses), else the repo's copy."""
    r = as_studio(["cat", "/home/studio/kits/dotcoin-longform/topics.md"], timeout=30)
    if r.returncode == 0 and r.stdout:
        return r.stdout.decode("utf-8", "replace")
    p = Path("/home/Hub/CoinePro-Hub") / P.TOPICS
    return p.read_text("utf-8") if p.is_file() else ""


# ------------------------------------------------------------------ the package onto the site
def fetch_out(ref: str, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    missing = []
    for name in OUT_FILES:
        src = WORKSPACE / ref / "out" / name
        if run(["sudo", "-n", "test", "-f", str(src)]).returncode:
            missing.append(name)
            continue
        run(["sudo", "-n", "cp", str(src), str(dest / name)])
        run(["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(dest / name)])
    return missing


def urls_of(paths: list[str]) -> list[str]:
    """The site URLs the changed files make (a lesson, a page, the glossary), sorted, once each."""
    return sorted({u for u in (P.url_of(p) for p in paths) if u})


def merge3(current: bytes, base: bytes, new: bytes) -> bytes | None:
    """git merge-file of three versions: the merged bytes, or None on a conflict."""
    with tempfile.TemporaryDirectory(prefix="dotcoin-merge-") as tmp:
        t = Path(tmp)
        (t / "cur").write_bytes(current)
        (t / "base").write_bytes(base)
        (t / "new").write_bytes(new)
        r = run(["git", "merge-file", "-p", str(t / "cur"), str(t / "base"), str(t / "new")], timeout=60)
        return r.stdout if r.returncode == 0 else None


def apply_files(man: dict, files: dict[str, bytes]) -> tuple[list[str], list[str], list[str]]:
    """Into the worktree: (applied paths, added paths, left out with why)."""
    applied, added, left = [], [], []
    for f in man["files"]:
        path, act = str(f["path"]), str(f["action"])
        dest = WT / path
        new = files[path]
        cur = dest.read_bytes() if dest.exists() else None
        if act == "add":
            if cur is not None:
                left.append(f"{path}: made by someone else meanwhile")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new)
            applied.append(path)
            added.append(path)
            continue
        base = run(["git", "-C", str(WT), "show", f"{man['base']}:{path}"]).stdout
        if cur is None:
            left.append(f"{path}: gone from the site")
            continue
        if cur == base or cur == new:
            out = new
        else:
            out = merge3(cur, base, new)
            if out is None:
                left.append(f"{path}: changed meanwhile and in conflict")
                continue
        if out != cur:
            dest.write_bytes(out)
            applied.append(path)
    return applied, added, left


def undo(applied: list[str], added: list[str]) -> None:
    for p in added:
        (WT / p).unlink(missing_ok=True)
    keep = [p for p in applied if p not in added]
    if keep:
        run(["git", "-C", str(WT), "checkout", "--", *keep], timeout=60)


def build_check() -> tuple[bool, str, Path | None]:
    """The whole site built from the worktree into a throwaway dist (the bidi lint included)."""
    tmp = Path(tempfile.mkdtemp(prefix="dotcoin-seo-build-"))
    env = dict(os.environ, DOTCOIN_DIST=str(tmp / "dist"), DOTCOIN_MEDIA=str(Y.HOME / "dotcoin-media"))
    r = run([sys.executable, "-I", str(SITE / "build.py")], cwd=SITE, env=env, timeout=600)
    if r.returncode:
        shutil.rmtree(tmp, ignore_errors=True)
        return False, tail(r.stderr or r.stdout, 4), None
    return True, "", tmp


def review(dist_parent: Path, urls: list[str], ref: str) -> tuple[int, str]:
    """The phone review, once more when it did not run at all (2026-11-24: Chromium closed its
    page in the middle of W-001134's shots, «Target page, context or browser has been closed»,
    and the day's package was blocked with -1 findings; 11-21's W-000780 the same way). A real
    finding is never retried away: only a review that wrote no answer runs again."""
    n, out = review_once(dist_parent, urls, ref)
    if n == -1:
        log(f"  {ref}: the phone review did not run; once more")
        n, out = review_once(dist_parent, urls, ref)
    return n, out


def review_once(dist_parent: Path, urls: list[str], ref: str) -> tuple[int, str]:
    """tools/review.py as the studio user (the studio's Chromium): (findings, where the shots are)."""
    out = DATA / "reviews" / ref
    (out / "review.json").unlink(missing_ok=True)  # (an earlier pass's answer is never read as this one's)
    stmp = Path("/home/studio/tmp-seo-gate") / ref  # (its own folder: never another review's)
    as_studio(["rm", "-rf", str(stmp)])
    as_studio(["mkdir", "-p", str(stmp)])
    tarb = run(["tar", "-C", str(dist_parent), "--exclude=dist/media", "-cf", "-", "dist"], timeout=300).stdout
    as_studio(["tar", "-C", str(stmp), "-xf", "-"], data=tarb)
    tools = run(["tar", "-C", str(SITE), "-cf", "-", "tools/review.py", "tools/render.py"], timeout=60).stdout
    as_studio(["tar", "-C", str(stmp), "-xf", "-"], data=tools)
    r = as_studio(["env", f"PLAYWRIGHT_BROWSERS_PATH={PW_PATH}", STUDIO_PY, "-I", str(stmp / "tools" / "review.py"),
                   "check", str(stmp / "dist"), str(stmp / "out"), *urls], timeout=1800)
    out.mkdir(parents=True, exist_ok=True)
    shots = as_studio(["tar", "-C", str(stmp / "out"), "-cf", "-", "."], timeout=300).stdout
    if shots:
        with tarfile.open(fileobj=io.BytesIO(shots)) as tf:
            tf.extractall(out, filter="data")
    as_studio(["rm", "-rf", str(stmp)])
    try:
        n = int(json.loads((out / "review.json").read_text("utf-8")).get("findings") or 0)
    except (OSError, ValueError):
        n = -1  # the review did not run: treated as a finding
        log(f"  review did not run: {tail(r.stderr or r.stdout, 2)}")
    return n, str(out)


def live_ok(path: str) -> bool:
    for _ in range(3):
        st, body = http(URL + path, timeout=30)
        if st == 200 and b"<title>" in body:
            return True
        import time as _t

        _t.sleep(10)
    return False


def indexnow(urls: list[str]) -> str:
    try:
        key = json.loads((SITE / "content" / "site.json").read_text("utf-8")).get("indexnow") or ""
    except (OSError, ValueError):
        key = ""
    if not key or not urls:
        return "skipped"
    body = json.dumps({"host": "dotcoin.me", "key": key, "keyLocation": f"{URL}/{key}.txt",
                       "urlList": [URL + u for u in urls][:1000]}).encode()
    st, resp = http(INDEXNOW, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, timeout=30)
    return f"{st}" + ("" if st in (200, 202) else f" {resp[:120].decode('utf-8', 'replace')}")


def request_indexing(urls: list[str], state: dict) -> list[dict]:
    """«Request indexing» for the day's first URLs, within the day's cap; stops at the first refusal
    (Google's quota or its «problem submitting»: the rest wait for tomorrow's package)."""
    today = now_utc().date().isoformat()
    done = state["requests"].setdefault(today, [])
    out = []
    for u in urls:
        if len(done) >= REQUEST_MAX:
            break
        if any(x.get("url") == URL + u and x.get("result") == "requested" for v in state["requests"].values() for x in v):
            continue
        ans = gsc("gsc_request", URL + u, 240)
        text = str(ans.get("text_md") or ans.get("detail") or "")
        result = ("requested" if re.search(r"requested|priority crawl", text, re.I) else
                  "quota" if re.search(r"quota", text, re.I) else "refused" if ans.get("ok") else "failed")
        row = {"url": URL + u, "result": result, "said": text[:160], "at": Y.now()}
        done.append(row)
        out.append(row)
        if result != "requested":
            break
    for k in sorted(state["requests"])[:-30]:
        state["requests"].pop(k, None)
    return out


def apply_run(ref: str, row: dict, state: dict) -> None:
    run_s = state["runs"].setdefault(ref, {"day": row.get("day"), "key": row.get("key")})
    if run_s.get("status") in ("done", "blocked"):
        return
    work = Y.HOME / "dotcoin-seo-tmp" / ref
    shutil.rmtree(work, ignore_errors=True)
    missing = fetch_out(ref, work)
    if "package.zip" in missing:
        run_s.update(status="waiting", why="out/ lacks package.zip", at=Y.now())
        return
    keep = DATA / "packages" / f"{row.get('day')}-{ref}"
    keep.mkdir(parents=True, exist_ok=True)
    for name in OUT_FILES:
        if (work / name).exists():
            shutil.copy2(work / name, keep / name)
    man, files, errs = P.check(work / "package.zip", WT, longform_topics())
    if errs:
        run_s.update(status="blocked", why="; ".join(errs)[:900], at=Y.now())
        log(f"{ref}: BLOCKED by the package's rules: {run_s['why'][:300]}")
        return
    with open(Y.SYNC_LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if run(["git", "-C", str(WT), "status", "--porcelain", "--", REL_SITE + "/content", REL_SITE + "/seo"]).stdout.strip():
            run_s.update(status="waiting", why="the content worktree has uncommitted changes", at=Y.now())
            return
        applied, added, left = apply_files(man, files)
        vip_changed = refresh_vip_stats()
        touched = list(applied) + ([f"{REL_SITE}/content/vip_stats.json"] if vip_changed else [])
        if not applied:
            if vip_changed:
                run(["git", "-C", str(WT), "checkout", "--", f"{REL_SITE}/content/vip_stats.json"])
            run_s.update(status="blocked", why="nothing could be applied: " + "; ".join(left)[:700], at=Y.now())
            log(f"{ref}: BLOCKED: {run_s['why'][:300]}")
            return
        ok, why, tmp = build_check()
        urls = sorted(set(urls_of(applied)) | {"/vip/"})
        findings, shots = (review(tmp, urls, ref) if ok and tmp else (0, ""))
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        if not ok or findings:
            undo(applied, added)
            if vip_changed:
                run(["git", "-C", str(WT), "checkout", "--", f"{REL_SITE}/content/vip_stats.json"])
            why = why if not ok else f"the phone review found {findings} problem(s) (shots: {shots})"
            run_s.update(status="blocked", why=why[:900], left_out=left, at=Y.now())
            log(f"{ref}: BLOCKED, nothing published: {why[:300]}")
            return
        topic = str(man.get("topic") or "").strip()
        msg = (f"DotCoin SEO {row.get('day')}: {len(applied)} files"
               + (f", new {', '.join(man.get('new_urls') or [])}" if man.get("new_urls") else "")
               + (f" ({topic[:80]})" if topic else "") + f" (seo.py, {ref})")
        run(["git", "-C", str(WT), "add", "--", *touched], timeout=60)
        r = run(["git", "-C", str(WT), "commit", "-q", "-m", msg, "--", *touched], timeout=60)
        if r.returncode:
            undo(applied, added)
            run_s.update(status="waiting", why=f"git commit failed: {tail(r.stderr, 1)}", at=Y.now())
            return
        commit = git_out("rev-parse", "HEAD")
    run_s.update(status="committed", commit=commit, applied=applied, left_out=left, shots=shots, at=Y.now())
    save_state(state)
    log(f"{ref}: {len(applied)} files committed {commit[:10]}" + (f"; left out: {left}" if left else ""))
    # the site sync pushes the branch, builds and deploys (its own lock)
    r = run([sys.executable, "-I", str(SITE / "sync.py")], timeout=1800, cwd=WT)
    for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines()[-4:]:
        log(f"  sync: {ln[:200]}")
    new_urls = list(man.get("new_urls") or [])
    changed = [u for u in urls_of(applied) if u not in new_urls]
    live = {u: live_ok(u) for u in new_urls}
    run_s.update(live=live, deployed=all(live.values()) if live else r.returncode == 0)
    run_s["indexnow"] = indexnow(new_urls + changed + ["/vip/"] if vip_changed else new_urls + changed)
    sm = gsc("gsc_sitemap", "sitemap.xml", 120)
    run_s["sitemap"] = "submitted" if sm.get("ok") else Y.why(sm)[:200]
    first = [u for u in (man.get("index_first") or []) if u in new_urls + changed]
    order = list(dict.fromkeys(first + new_urls + changed))
    run_s["requests"] = request_indexing(order, state)
    run_s.update(status="done", at=Y.now())
    log(f"{ref}: done; live {live}; IndexNow {run_s['indexnow']}; requests "
        + ", ".join(f"{x['url'][len(URL):]} {x['result']}" for x in run_s["requests"]))
    shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ the passes
def due_pass(force_day: date | None = None) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state = load_state()
        for flow in flows():
            if str(flow.get("state")) == "off":
                continue
            day = force_day or next_day(flow, now_utc())
            if day is not None and not state["prep"].get(day.isoformat(), {}).get("done"):
                try:
                    prepare(flow, day, state, force=force_day is not None)
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                    log(f"input pack {day}: not made ({str(e)[:200]})")
                save_state(state)
        for row in Y.sql(DUE_SQL):
            ref = str(row.get("ref") or "")
            if not REF_RE.fullmatch(ref) or state["runs"].get(ref, {}).get("status") in ("done", "blocked", "committed"):
                continue
            try:
                apply_run(ref, row, state)
            except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError) as e:
                state["runs"].setdefault(ref, {})["why"] = f"error: {str(e)[:300]}"
                log(f"{ref}: error {str(e)[:300]}")
            save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--day")
    ap.add_argument("--apply")
    ap.add_argument("--vip-stats", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    try:
        if a.status:
            s = load_state()
            print(json.dumps({"prep": s["prep"], "runs": s["runs"], "requests": s["requests"]}, ensure_ascii=False, indent=1)[:6000])
            return 0
        if a.vip_stats:
            with open(Y.SYNC_LOCK, "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                changed = refresh_vip_stats()
                if changed:
                    rel = f"{REL_SITE}/content/vip_stats.json"
                    run(["git", "-C", str(WT), "add", "--", rel])
                    run(["git", "-C", str(WT), "commit", "-q", "-m", "DotCoin site: the VIP's numbers from TradeYar's public record (seo.py)", "--", rel])
            log("vip stats " + ("updated" if changed else "unchanged"))
            return 0
        if a.prepare:
            state = load_state()
            day = date.fromisoformat(a.day) if a.day else None
            fl = flows()
            if not fl:
                log("no SEO flow (automations.flows kind article for dotcoin.me)")
                return 1
            day = day or next_day(fl[0], now_utc()) or (now_utc().astimezone(TZ).date() + timedelta(days=1))
            HOME.mkdir(parents=True, exist_ok=True)
            DATA.mkdir(parents=True, exist_ok=True)
            with open(LOCK, "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                prepare(fl[0], day, state, force=True)
                save_state(state)
            return 0
        if a.apply:
            if not REF_RE.fullmatch(a.apply):
                ap.error("--apply W-…")
            state = load_state()
            rows = [r for r in Y.sql(DUE_SQL) if r.get("ref") == a.apply]
            if not rows:
                log(f"{a.apply}: not a queued SEO run whose hour has come")
                return 1
            if state["runs"].get(a.apply, {}).get("status") == "blocked":  # (fixed by hand: try again)
                state["runs"][a.apply].pop("status", None)
            with open(LOCK, "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                apply_run(a.apply, rows[0], state)
                save_state(state)
            return 0
        return due_pass()
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        log(f"error: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
