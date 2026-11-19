#!/usr/bin/env python3
"""@behnamjalali.tech — the always-awake breaking-news watcher (owner 2026-11-18; stdlib only, rules only, no model).

The owner: «یک ایجنت که روی سرور همیشه بیداره: به محض اینکه مدل جدید یا ریلیز مهمی اومد (OpenAI، Anthropic، Google
و بقیه) سریع با عکس رسمی خود سایت پست بشه، بعد ریلز کاملش». «اول قاعده، آخر هوش مصنوعی»: this pass is code; only a
real new release starts the AI sessions.

A pass (bjtech-breaking.timer, every 4 minutes, as Hub):
  1. reads the due sources (SOURCES: the vendors' own feeds, API changelogs, model pages and Hugging Face orgs;
     researched and fetched 2026-11-18, automations/kits/bjtech-reels/sources.md) THROUGH THE HUB'S EGRESS (the
     worker's /v1/read, the path the agents' web reads take: no new hole), each at its own interval;
  2. finds candidates: a feed item announcing a model or a major release (launch words + a model family, fresh,
     not a partnership / event / customer story), a NEW model id in an API changelog or models page, a new
     flagship repo on a vendor's Hugging Face org (no quantised copies, no drafts);
  3. folds every candidate into ONE news event per vendor + family + version («openai:gpt-6.2»), whatever the
     source, and keeps the earliest link and the official image (the page's og:image, read through egress);
  4. starts the hub's event flows for a NEW event: bjtech_flash (the flash story, out at once),
     bjtech_tg_breaking (⟨2026-11-19⟩ the Telegram channel's breaking post, out at once) and
     bjtech_breaking (the full reel): domain/flow_events.start_event inside the api container (`docker exec`),
     which itself refuses a second run of the same event (and is a no-op while a flow is switched off).
Never twice: the state (HOME/bjtech-breaking/state.json) keeps every event fired, forever, and every item seen
(30 days); the hub keeps one run per event and flow. Limits: at most 4 events a day, 30 minutes apart (a later one
waits in the queue, dropped after 6 hours: then it is no longer breaking). The first pass ever records what is
there and fires nothing (the baseline).

    breaking.py --pass             one pass (the timer)
    breaking.py --pass --dry-run   the same, fetching and reporting, firing nothing and saving nothing
    breaking.py --status           the state in short: sources, last pass, events, the queue
    breaking.py --fire <event-id>  start a queued event now (by hand; the same limits are skipped)
"""
from __future__ import annotations

import argparse
import email.utils
import fcntl
import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path(os.environ.get("BJ_BREAKING_HOME", "/home/Hub/sites/bjtech-breaking"))
STATE, LOCK = HOME / "state.json", HOME / "state.lock"
WORKER, API = "coinepro-hq-worker-1", "coinepro-hq-api-1"
# the flash story first (out in minutes), the Telegram channel's breaking post (⟨2026-11-19⟩, out the moment
# its package is in), then the full reel; a flow missing or off answers "off" and the others go on
FLOWS = ("bjtech_flash", "bjtech_tg_breaking", "bjtech_breaking")
MAX_A_DAY, GAP_MIN, STALE_H, FRESH_H = 4, 30, 6, 12
SEEN_DAYS = 30
UTC = timezone.utc

# ------------------------------------------------------------------ the sources (official only)
# kind: feed (RSS / Atom) · page (a changelog or models page: new model ids) · hf (a Hugging Face org's newest models)
SOURCES = [
    # OpenAI
    {"id": "openai-news", "vendor": "OpenAI", "kind": "feed", "every": 4, "url": "https://openai.com/news/rss.xml"},
    {"id": "openai-changelog", "vendor": "OpenAI", "kind": "page", "every": 8, "ids": "openai",
     "url": "https://developers.openai.com/api/docs/changelog", "link": "https://developers.openai.com/api/docs/changelog"},
    {"id": "openai-hf", "vendor": "OpenAI", "kind": "hf", "every": 12, "org": "openai"},
    # Anthropic
    {"id": "claude-release-notes", "vendor": "Anthropic", "kind": "feed", "every": 4,
     "url": "https://platform.claude.com/docs/en/release-notes/feed.xml"},
    {"id": "claude-articles", "vendor": "Anthropic", "kind": "feed", "every": 8, "url": "https://claude.com/resources/articles/rss.xml"},
    {"id": "claude-models", "vendor": "Anthropic", "kind": "page", "every": 12, "ids": "anthropic",
     "url": "https://platform.claude.com/docs/en/models/overview", "link": "https://www.anthropic.com/news"},
    # Google
    {"id": "deepmind", "vendor": "Google", "kind": "feed", "every": 4, "url": "https://deepmind.google/blog/rss.xml"},
    {"id": "google-gemini", "vendor": "Google", "kind": "feed", "every": 6, "url": "https://blog.google/products/gemini/rss/"},
    {"id": "google-ai", "vendor": "Google", "kind": "feed", "every": 8, "url": "https://blog.google/technology/ai/rss/"},
    {"id": "gemini-changelog", "vendor": "Google", "kind": "page", "every": 8, "ids": "google",
     "url": "https://aistudio.google.com/docs/changelog", "link": "https://aistudio.google.com/docs/changelog"},
    {"id": "google-hf", "vendor": "Google", "kind": "hf", "every": 12, "org": "google"},
    # Meta
    {"id": "meta-news", "vendor": "Meta", "kind": "feed", "every": 8, "url": "https://about.fb.com/news/feed/", "need": r"\b(AI|Muse|Llama)\b"},
    {"id": "meta-hf", "vendor": "Meta", "kind": "hf", "every": 15, "org": "meta-models"},
    # xAI
    {"id": "xai-release-notes", "vendor": "xAI", "kind": "page", "every": 10, "ids": "xai",
     "url": "https://docs.x.ai/developers/release-notes.md", "link": "https://docs.x.ai/developers/release-notes"},
    # Mistral
    {"id": "mistral-news", "vendor": "Mistral", "kind": "feed", "every": 8, "url": "https://mistral.ai/news/rss"},
    {"id": "mistral-hf", "vendor": "Mistral", "kind": "hf", "every": 15, "org": "mistralai"},
    # DeepSeek, Qwen, Moonshot, Zhipu, MiniMax (open weights: their Hugging Face orgs are the fastest official signal)
    {"id": "deepseek-hf", "vendor": "DeepSeek", "kind": "hf", "every": 10, "org": "deepseek-ai"},
    {"id": "qwen-hf", "vendor": "Qwen", "kind": "hf", "every": 10, "org": "Qwen"},
    {"id": "moonshot-hf", "vendor": "Moonshot", "kind": "hf", "every": 15, "org": "moonshotai"},
    {"id": "zai-hf", "vendor": "Zhipu", "kind": "hf", "every": 15, "org": "zai-org"},
    {"id": "minimax-hf", "vendor": "MiniMax", "kind": "hf", "every": 15, "org": "MiniMaxAI"},
    {"id": "zai-notes", "vendor": "Zhipu", "kind": "feed", "every": 30, "url": "https://docs.z.ai/release-notes/new-released/rss.xml"},
    # Microsoft, Apple
    {"id": "microsoft-ai", "vendor": "Microsoft", "kind": "feed", "every": 10, "url": "https://news.microsoft.com/source/topics/ai/feed/"},
    {"id": "apple-ml", "vendor": "Apple", "kind": "feed", "every": 20, "url": "https://machinelearning.apple.com/rss.xml"},
]

# ------------------------------------------------------------------ the rules
FAMILIES = (r"gpt|o\d|chatgpt|codex|sora|dall-?e|claude|opus|sonnet|haiku|fable|mythos|gemini|gemma|veo|imagen|"
            r"nano[\s-]?banana|lyria|genie|muse|llama|grok|aurora|mistral|magistral|devstral|codestral|voxtral|pixtral|"
            r"le\s?chat|deepseek|qwen|kimi|glm|minimax|hailuo|phi|mai|copilot|nemotron|apple intelligence")
FAMILY = re.compile(rf"\b({FAMILIES})\b", re.I)
LAUNCH = re.compile(r"\b(introduc\w*|announc\w*|launch\w*|unveil\w*|releas\w*|meet|now available|available (now|today)|"
                    r"rolling out|is here|debut\w*|new model|ships?|open[- ]?(weights?|sourc\w+))\b", re.I)
NOT_NEWS = re.compile(r"\b(partner\w*|customer|case stud\w*|webinar|event|summit|conference|hiring|career|"
                      r"podcast|interview|award|grant|fellowship|policy|election|lawsuit|court|"
                      r"how to|tips|guide|tutorial|recap|year in review|available in \w+)\b", re.I)
VERSION = re.compile(rf"\b({FAMILIES})[\s-]*v?(\d+(?:\.\d+)?)", re.I)
MODEL_IDS = {
    "openai": re.compile(r"\b(gpt-\d+(?:\.\d+)?(?:-[a-z0-9]+)*|o\d+(?:-[a-z0-9]+)*|sora-\d+(?:-[a-z0-9]+)*)\b"),
    "anthropic": re.compile(r"\b(claude-(?:opus|sonnet|haiku|fable|mythos)-\d+(?:-\d+)?)\b"),
    "google": re.compile(r"\b((?:gemini|gemma|veo|imagen)-\d+(?:\.\d+)?(?:-[a-z0-9]+)*)\b"),
    "xai": re.compile(r"\b(grok-\d+(?:\.\d+)?(?:-[a-z0-9]+)*)\b"),
}
HF_SKIP = re.compile(r"(gguf|awq|gptq|fp8|nvfp4|int4|int8|mlx|bnb|onnx|draft|eagle|lora|adapter|-base-|test)", re.I)
HF_NEED = re.compile(rf"({FAMILIES})", re.I)
OG = re.compile(r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]*>""", re.I)
CONTENT = re.compile(r"""content=["']([^"']+)["']""", re.I)
GENERIC_IMAGES = ("6d4a0d28992ade92d6fa63646fd9c9d318245c6c",)  # (anthropic.com's generic site card)

# ------------------------------------------------------------------ egress (inside the hub's network)
# Runs in the worker (python -c): reads a JSON list of URLs on stdin, reads each through egress's /v1/read
# (mode html: the raw text of the page or feed), prints {url: {status, text}}. The worker reaches egress on its
# internal network; egress carries the request out with its guard and limits, as for every agent's web read.
CLIENT = r"""
import json, os, sys, httpx
from concurrent.futures import ThreadPoolExecutor
urls = json.loads(sys.stdin.read())
base = os.environ.get("SUPPORT_EGRESS_URL", "http://egress:8090").rstrip("/") + "/v1/read"
def one(u):
    body = {"ctx": {"company": "IG", "actor": "bjtech-watcher", "cls": "A0", "max_bytes": 4000000},
            "url": u, "mode": "html", "max_chars": 200000}
    try:
        r = httpx.post(base, json=body, timeout=45).json()
    except Exception as e:
        return u, {"status": 0, "error": type(e).__name__, "text": ""}
    d = r.get("data") or {}
    return u, {"status": int(d.get("status") or 0), "error": r.get("code"), "text": str(d.get("text") or "")}
with ThreadPoolExecutor(6) as ex:
    out = dict(ex.map(one, urls))
sys.stdout.write(json.dumps(out))
"""

# Runs in the api (python -c): one event (JSON on stdin) -> flow_events.start_event for each flow, in order.
TRIGGER = r"""
import asyncio, json, sys
ev = json.loads(sys.stdin.read())
async def main():
    try:
        from hq_api.domain import flow_events as EV
    except ImportError:
        print(json.dumps({"ok": False, "why": "hub_not_ready"})); return
    from hq_api.__main__ import build
    from hq_api.config import Settings
    hub, _ = await build(Settings())
    out = {}
    try:
        for key in ev.pop("_flows"):
            try:
                got = await EV.start_event(hub, key, ev)
                out[key] = {k: got.get(k) for k in ("order", "work", "publish_at", "why_fa", "new")}
            except Exception as e:  # (one flow's refusal never stops the other)
                out[key] = {"error": type(e).__name__, "detail": str(e)[:200]}
    finally:
        if hub.bus is not None:
            await hub.bus.close()
        await hub.db.close()
    print(json.dumps({"ok": True, "flows": out}, ensure_ascii=False))
asyncio.run(main())
"""


def now() -> datetime:
    return datetime.now(UTC)


def log(msg: str) -> None:
    print(f"{now():%Y-%m-%dT%H:%M:%SZ} {msg}", flush=True)


def run(cmd: list[str], stdin: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin.encode(), capture_output=True, timeout=timeout)


def fetch(urls: list[str]) -> dict:
    if not urls:
        return {}
    try:
        r = run(["docker", "exec", "-i", WORKER, "python", "-c", CLIENT], json.dumps(urls), 240)
        return json.loads(r.stdout.decode() or "{}")
    except (subprocess.TimeoutExpired, ValueError) as e:
        log(f"egress read failed: {type(e).__name__}")
        return {}


# ------------------------------------------------------------------ parsing
def _text(el, *names: str) -> str:
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text and x.text.strip():
                return x.text.strip()
            if x.get("href"):
                return x.get("href")
    return ""


def parse_feed(text: str) -> list[dict]:
    """RSS 2.0 or Atom items: {key, title, link, date, summary}. A bad feed gives []."""
    start = min((i for i in (text.find("<rss"), text.find("<feed"), text.find("<?xml")) if i >= 0), default=-1)
    if start < 0:
        return []
    body = text[start:]
    # a feed cut at 200,000 characters: keep the whole items before the cut
    for tag in ("</item>", "</entry>"):
        last = body.rfind(tag)
        if last > 0 and not body.rstrip().endswith(("</rss>", "</feed>")):
            body = body[:last + len(tag)] + ("</channel></rss>" if tag == "</item>" else "</feed>")
            break
    body = re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", body)
    body = re.sub(r"<(/?)\w+:(\w+)", r"<\1\2", body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out = []
    for it in list(root.iter("item")) + list(root.iter("entry")):
        title = html.unescape(_text(it, "title"))
        link = _text(it, "link")
        if not link:
            ln = it.find("link")
            link = ln.get("href", "") if ln is not None else ""
        date = _text(it, "pubDate", "published", "updated", "date")
        summary = re.sub(r"<[^>]+>", " ", html.unescape(_text(it, "description", "summary", "content")))[:600]
        key = _text(it, "guid", "id") or link or title
        if title:
            out.append({"key": key, "title": " ".join(title.split()), "link": link.strip(), "date": date,
                        "summary": " ".join(summary.split())})
    return out


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


STOP = {"and", "is", "now", "the", "model", "models", "for", "with", "in", "on", "to", "of", "a", "an", "are", "open",
        "weights", "available", "here", "launch", "today", "update", "preview"}


def event_id(vendor: str, text: str, fallback: str) -> str:
    """One id per release: vendor + family + version + its variant name when it has one («openai:gpt-6.2-astra»,
    «google:gemini-4-hydrogen», «anthropic:fable-5.2»); no version: the family and its next word («meta:muse-wonder»);
    else a slug of the text. `coarse()` of it is the release line (vendor + family + version) the 24-hour cooldown
    holds (GPT-6.2 Astra and Sol launched together are one news)."""
    s = text.replace("‑", "-")
    m = VERSION.search(s)
    if m:
        fam = re.sub(r"\s+", "-", m.group(1).lower())
        rest = re.findall(r"[A-Za-z]+", s[m.end():m.end() + 40])
        var = next((w.lower() for w in rest[:1] if w.lower() not in STOP and len(w) > 2), "")
        return f"{vendor.lower()}:{fam}-{m.group(2)}" + (f"-{var}" if var else "")
    f = FAMILY.search(s)
    if f:
        rest = [w.lower() for w in re.findall(r"[A-Za-z]+", s[f.end():f.end() + 30]) if w.lower() not in STOP and len(w) > 2]
        fam = re.sub(r"\s+", "-", f.group(1).lower())
        if rest:
            return f"{vendor.lower()}:{fam}-{rest[0]}"
    slug = re.sub(r"[^a-z0-9]+", "-", fallback.lower()).strip("-")[:60] or hashlib.sha1(fallback.encode()).hexdigest()[:10]
    return f"{vendor.lower()}:{slug}"


def coarse(eid: str) -> str:
    m = re.match(r"^([a-z0-9]+:[a-z0-9-]+?-\d+(?:\.\d+)?)(?:-[a-z]+)?$", eid)
    return m.group(1) if m else eid


def candidates(src: dict, text: str, seen: dict, t: datetime) -> list[dict]:
    """The source's news candidates not seen before (and every item it has, marked seen)."""
    out = []
    kind = src["kind"]
    if kind == "feed":
        for it in parse_feed(text):
            k = f"{src['id']}|{hashlib.sha1(it['key'].encode()).hexdigest()[:16]}"
            if k in seen:
                continue
            seen[k] = t.isoformat()
            d = parse_date(it["date"])
            if d is not None and t - d > timedelta(hours=FRESH_H):
                continue
            blob = f"{it['title']} {it['summary'][:300]}"
            if src.get("need") and not re.search(src["need"], blob):
                continue
            if not FAMILY.search(blob) or not LAUNCH.search(it["title"] + " " + it["summary"][:200]):
                continue
            if NOT_NEWS.search(it["title"]):
                continue
            out.append({"vendor": src["vendor"], "title": it["title"], "url": it["link"], "summary": it["summary"][:300],
                        "published": it["date"], "source": src["id"],
                        "id": event_id(src["vendor"], it["title"], it["title"])})
    elif kind == "page":
        rx = MODEL_IDS[src["ids"]]
        found = sorted(set(m.lower() for m in rx.findall(text)))
        fresh = []
        for mid in found:
            k = f"{src['id']}|{mid}"
            if k in seen:
                continue
            seen[k] = t.isoformat()
            fresh.append(mid)
        groups: dict[str, list[str]] = {}
        for mid in fresh:
            norm = re.sub(r"(\d)-(\d)", r"\1.\2", mid).replace("-", " ")  # claude-fable-5-2 -> claude fable 5.2
            groups.setdefault(event_id(src["vendor"], norm, mid), []).append(mid)
        for eid, ids in groups.items():
            out.append({"vendor": src["vendor"], "title": f"{src['vendor']}: {', '.join(ids[:4])}", "url": src["link"],
                        "summary": f"new model id(s) on {src['url']}", "published": "", "source": src["id"], "id": eid,
                        "model_ids": ids[:6]})
    elif kind == "hf":
        try:
            models = json.loads(text)
        except ValueError:
            return []
        for m in models if isinstance(models, list) else []:
            mid = str(m.get("id") or m.get("modelId") or "")
            k = f"{src['id']}|{mid}"
            if not mid or k in seen:
                continue
            seen[k] = t.isoformat()
            created = parse_date(str(m.get("createdAt") or ""))
            name = mid.split("/", 1)[-1]
            if HF_SKIP.search(name) or not HF_NEED.search(name):
                continue
            if created is not None and t - created > timedelta(hours=24):
                continue
            out.append({"vendor": src["vendor"], "title": f"{name} (open weights on Hugging Face)",
                        "url": f"https://huggingface.co/{mid}", "summary": f"new model repo {mid}", "published": str(m.get("createdAt") or ""),
                        "source": src["id"], "id": event_id(src["vendor"], name.replace("-", " "), name)})
    return out


def og_image(text: str) -> str:
    for tag in OG.findall(text[:150000]):
        m = CONTENT.search(tag)
        if m and m.group(1).startswith("https://") and not any(g in m.group(1) for g in GENERIC_IMAGES):
            return html.unescape(m.group(1))
    return ""


# ------------------------------------------------------------------ state
def load() -> dict:
    try:
        return json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save(st: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    cut = (now() - timedelta(days=SEEN_DAYS)).isoformat()
    st["seen"] = {k: v for k, v in st.get("seen", {}).items() if v >= cut}
    st["log"] = st.get("log", [])[-300:]
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def fire(ev: dict, dry: bool) -> dict:
    payload = dict(ev, _flows=list(FLOWS))
    for k in ("source", "first_seen", "sources", "model_ids"):
        payload.pop(k, None)
    if dry:
        return {"ok": True, "dry": True}
    try:
        r = run(["docker", "exec", "-i", "-w", "/tmp", API, "python", "-c", TRIGGER], json.dumps(payload, ensure_ascii=False), 300)
        lines = [ln for ln in r.stdout.decode().splitlines() if ln.startswith("{")]
        return json.loads(lines[-1]) if lines else {"ok": False, "why": f"no answer ({r.stderr.decode()[-200:]})"}
    except (subprocess.TimeoutExpired, ValueError) as e:
        return {"ok": False, "why": type(e).__name__}


# ------------------------------------------------------------------ the pass
def one_pass(dry: bool) -> int:
    t = now()
    st = load()
    baseline = "baseline_at" not in st
    st.setdefault("seen", {})
    st.setdefault("last", {})
    st.setdefault("fired", {})
    st.setdefault("queue", [])
    st.setdefault("based", [])
    due = [s for s in SOURCES if baseline or (t - datetime.fromisoformat(st["last"].get(s["id"], "2000-01-01T00:00:00+00:00"))
                                              >= timedelta(minutes=s["every"]) - timedelta(seconds=40))]
    urls = {s["id"]: (s["url"] if s["kind"] != "hf" else
                      f"https://huggingface.co/api/models?author={s['org']}&sort=createdAt&direction=-1&limit=8")
            for s in due}
    got = fetch(sorted(set(urls.values())))
    found: list[dict] = []
    errors = []
    for s in due:
        r = got.get(urls[s["id"]]) or {}
        if r.get("status") != 200 or not r.get("text"):
            errors.append(f"{s['id']}:{r.get('status')}")
            continue
        st["last"][s["id"]] = t.isoformat()
        got_c = candidates(s, r["text"], st["seen"], t)
        if s["id"] not in st["based"]:  # a source's first good read only records what is there
            st["based"].append(s["id"])
            continue
        found += got_c
    if baseline:
        st["baseline_at"] = t.isoformat()
        st["log"] = [f"{t.isoformat()} baseline: {len(st['seen'])} items seen, {len(due)} sources, errors {errors}"]
        log(f"baseline: {len(st['seen'])} items recorded, nothing fired; unread: {errors or 'none'}")
        if not dry:
            save(st)
        return 0
    # fold the candidates into events (one per vendor + family + version), never one already fired or queued
    queued = {q["id"] for q in st["queue"]}
    new = {}
    for c in found:
        if c["id"] in st["fired"] or c["id"] in queued:
            continue
        line = coarse(c["id"])
        recent = [k for k, v in st["fired"].items() if coarse(k) == line and t - datetime.fromisoformat(v["fired_at"]) < timedelta(hours=24)]
        if recent or any(coarse(q) == line for q in queued) or any(coarse(k) == line and k != c["id"] for k in new):
            st["seen"][f"cooldown|{c['id']}"] = t.isoformat()
            continue
        ev = new.setdefault(c["id"], dict(c, first_seen=t.isoformat(), sources=[]))
        ev["sources"].append(c["source"])
        if c["url"] and "huggingface.co" in ev.get("url", "") and "huggingface.co" not in c["url"]:
            ev.update(url=c["url"], title=c["title"], summary=c["summary"])  # (the vendor's own page wins)
    # the official image of each new event's page (through egress)
    pages = [ev["url"] for ev in new.values() if ev.get("url", "").startswith("https://")]
    if pages:
        got = fetch(pages)
        for ev in new.values():
            r = got.get(ev.get("url")) or {}
            if r.get("status") == 200:
                ev["image"] = og_image(r.get("text") or "")
    st["queue"] += list(new.values())
    # fire from the queue, oldest first, within the limits
    day = t.date().isoformat()
    today = [e for e in st["fired"].values() if e.get("fired_at", "")[:10] == day and e.get("result", {}).get("ok")]
    last = max((e.get("fired_at", "") for e in st["fired"].values()), default="")
    keep = []
    for ev in st["queue"]:
        age = t - datetime.fromisoformat(ev["first_seen"])
        if age > timedelta(hours=STALE_H):
            st["log"].append(f"{t.isoformat()} dropped (stale): {ev['id']}")
            continue
        gap_ok = not last or t - datetime.fromisoformat(last) >= timedelta(minutes=GAP_MIN)
        if len(today) >= MAX_A_DAY or not gap_ok:
            keep.append(ev)
            continue
        res = fire(ev, dry)
        if res.get("ok") is False and res.get("why") == "hub_not_ready":
            keep.append(ev)
            st["log"].append(f"{t.isoformat()} waiting for the hub: {ev['id']}")
            continue
        st["fired"][ev["id"]] = {"title": ev["title"], "url": ev.get("url"), "vendor": ev["vendor"], "image": ev.get("image", ""),
                                 "fired_at": t.isoformat(), "result": res, "sources": ev.get("sources", [])}
        st["log"].append(f"{t.isoformat()} fired {ev['id']} ({ev['title'][:80]}): {json.dumps(res, ensure_ascii=False)[:300]}")
        log(f"fired {ev['id']}: {ev['title'][:80]} -> {json.dumps(res, ensure_ascii=False)[:300]}")
        if res.get("ok"):
            today.append(st["fired"][ev["id"]])
            last = t.isoformat()
    st["queue"] = keep
    st["last_pass"] = {"at": t.isoformat(), "sources": len(due), "errors": errors, "candidates": len(found),
                       "new_events": len(new), "queued": len(keep)}
    log(f"pass: {len(due)} sources, {len(found)} candidates, {len(new)} new events, {len(keep)} queued; unread {errors or 'none'}")
    if not dry:
        save(st)
    return 0


def status() -> int:
    st = load()
    print(json.dumps({"baseline_at": st.get("baseline_at"), "last_pass": st.get("last_pass"),
                      "seen": len(st.get("seen", {})), "queue": [q["id"] for q in st.get("queue", [])],
                      "fired": {k: {"at": v.get("fired_at"), "ok": v.get("result", {}).get("ok")} for k, v in st.get("fired", {}).items()},
                      "log": st.get("log", [])[-8:]}, ensure_ascii=False, indent=1))
    return 0


def fire_now(eid: str) -> int:
    st = load()
    ev = next((q for q in st.get("queue", []) if q["id"] == eid), None)
    if ev is None:
        print(f"{eid} is not queued")
        return 1
    res = fire(ev, False)
    st["fired"][eid] = {"title": ev["title"], "url": ev.get("url"), "vendor": ev["vendor"], "fired_at": now().isoformat(), "result": res}
    st["queue"] = [q for q in st["queue"] if q["id"] != eid]
    save(st)
    print(json.dumps(res, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fire")
    a = ap.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another pass is running")
            return 0
        if a.status:
            return status()
        if a.fire:
            return fire_now(a.fire)
        if a.pass_:
            time.sleep(random.uniform(0, 3))
            return one_pass(a.dry_run)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
