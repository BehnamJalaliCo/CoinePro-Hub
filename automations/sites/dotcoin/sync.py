#!/usr/bin/env python3
"""DotCoin.me: the hub's daily lessons -> the live site (stdlib only; run as user Hub on the hub).

Every educational DotCoin reel's session leaves `out/article.md` (kit dotcoin-reels, seo/ARTICLE_BRIEF.md).
One pass (dotcoin-site-sync.timer, every 10 minutes):
  1. finds the article.md files of DotCoin outputs not synced yet (files.files, by the workspace the
     file came from: a `dotcoin_reels` work, or the work of a dotcoin.me reel's publish job);
  2. reads the bytes through `docker exec` (the hub DB is only read);
  3. validates the front matter and the slug (an invalid article is skipped with a log line);
  4. writes content/auto/<slug>.md in the content worktree (branch site/dotcoin-content);
  5. puts the reel's Instagram URL in `reel:` once its publish job has `result.url`;
  6. if anything changed: build check, commit, push the branch, deploy.sh (Cloudflare over IPv4).
State: /home/Hub/sites/dotcoin-sync.json. One lock; idempotent; never prints a secret.

    sync.py                                       one pass
    sync.py --dry-run                             find and validate only; write nothing
    sync.py --import FILE --workspace W-000583    take a local article as if the hub had made it
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

WT = Path(os.environ.get("DOTCOIN_CONTENT_WT", "/home/Hub/sites/dotcoin-content"))
SITE = WT / "automations" / "sites" / "dotcoin"
AUTO = SITE / "content" / "auto"
REL_AUTO = "automations/sites/dotcoin/content/auto"
HOME = Path(os.environ.get("DOTCOIN_SYNC_HOME", "/home/Hub/sites"))
STATE, LOCK = HOME / "dotcoin-sync.json", HOME / "dotcoin-sync.lock"
BRANCH = "site/dotcoin-content"
API, PG = "coinepro-hq-api-1", "coinepro-hq-postgres-1"
ACCOUNT, FLOWS = "dotcoin.me", ("dotcoin_reels",)
SITEMAP = "https://dotcoin.me/sitemap.xml"
GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.30.1"

PILLARS = {"basics", "security", "exchange", "market", "defi", "myths", "terms"}
MOTIFS = {"chain", "vault", "halving", "peg", "generic"}
RESERVED = {"basics", "security", "exchange", "market", "defi", "myths", "terms", "page", "tag", "feed",
            "go", "search"}
REQUIRED = ("title", "seo_title", "slug", "pillar", "date", "en", "motif", "description", "lead", "answer")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,3}")
WS_RE = re.compile(r"W-\d{3,9}")
KEY_RE = re.compile(r"[0-9a-f]{16,64}")


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: int = 120,
        data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, input=data, capture_output=True, timeout=timeout)


def tail(b: bytes, n: int = 4) -> str:
    lines = [ln for ln in b.decode("utf-8", "replace").splitlines() if ln.strip()]
    return " / ".join(ln.strip()[:160] for ln in lines[-n:])


# ------------------------------------------------------------------ the hub (read only)
def sql(query: str) -> list[dict]:
    q = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t"
    r = run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", PG,
             "psql", "-U", "postgres", "-d", "hq", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", q], timeout=60)
    if r.returncode:
        raise RuntimeError(f"db query failed: {tail(r.stderr, 2)}")
    return json.loads(r.stdout.decode() or "[]")


def candidates() -> list[dict]:
    flows = ",".join(f"'{f}'" for f in FLOWS)
    return sql(f"""
        WITH ws AS (
          SELECT ref AS w FROM work.work WHERE run_meta -> 'flow' ->> 'key' IN ({flows})
          UNION
          SELECT j.args -> 'session' ->> 'work' FROM infra.server_jobs j
           WHERE j.kind = 'publish' AND j.args ->> 'account' = '{ACCOUNT}' AND j.args ->> 'kind' = 'reel'
             AND j.created_at > now() - interval '30 days')
        SELECT f.id::text AS id, f.storage_key AS key, f.sha256 AS sha, f.size, f.meta ->> 'workspace' AS w
          FROM files.files f JOIN ws ON ws.w = f.meta ->> 'workspace'
         WHERE lower(f.name) = 'article.md' AND f.variant = 'original'
           AND f.created_at > now() - interval '30 days'
         ORDER BY f.created_at""")


def reel_urls(workspaces: list[str]) -> dict[str, str]:
    ws = [w for w in workspaces if WS_RE.fullmatch(w)]
    if not ws:
        return {}
    arr = ",".join(f"'{w}'" for w in ws)
    rows = sql(f"""
        SELECT DISTINCT ON (j.args -> 'session' ->> 'work') j.args -> 'session' ->> 'work' AS w,
               j.result ->> 'url' AS url
          FROM infra.server_jobs j
         WHERE j.kind = 'publish' AND j.args ->> 'account' = '{ACCOUNT}' AND j.args ->> 'kind' = 'reel'
           AND j.result ->> 'url' LIKE 'https://www.instagram.com/%'
           AND j.args -> 'session' ->> 'work' IN ({arr})
         ORDER BY j.args -> 'session' ->> 'work', j.updated_at DESC""")
    return {r["w"]: r["url"] for r in rows if re.fullmatch(r"https://www\.instagram\.com/\S{3,200}", r["url"])}


def file_bytes(row: dict) -> bytes:
    key = str(row["key"])
    if not KEY_RE.fullmatch(key) or int(row["size"]) > 300_000:
        raise ValueError("unexpected storage key or size")
    r = run(["docker", "exec", API, "cat", f"/data/files/{key[:2]}/{key}"], timeout=60)
    if r.returncode:
        raise RuntimeError(f"read failed: {tail(r.stderr, 1)}")
    if row.get("sha") and hashlib.sha256(r.stdout).hexdigest() != row["sha"]:
        raise ValueError("sha256 mismatch")
    return r.stdout


# ------------------------------------------------------------------ the article
def parse(text: str) -> tuple[dict, str]:
    """The same front matter reader as build.py's parse_doc."""
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        raise ValueError("no front matter")
    end = text.index("\n---", 4)
    head, body = text[4:end], text[end + 4:].lstrip("\n")
    meta: dict = {}
    key = None
    for line in head.split("\n"):
        if not line.strip():
            continue
        if line.startswith("- ") and key:
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(line[2:].strip())
            continue
        k, sep, v = line.partition(":")
        if not sep:
            raise ValueError(f"bad front matter line: {line[:40]!r}")
        key = k.strip()
        meta[key] = v.strip()
    return meta, body


def validate(text: str, taken: set[str]) -> tuple[dict, list[str], list[str]]:
    """(meta, errors, warnings). Errors skip the article; warnings are only logged."""
    errs: list[str] = []
    warn: list[str] = []
    try:
        m, body = parse(text)
    except ValueError as e:
        return {}, [str(e)], []
    for k in REQUIRED:
        if not isinstance(m.get(k), str) or not m.get(k):
            errs.append(f"missing {k}")
    slug = m.get("slug") if isinstance(m.get("slug"), str) else ""
    if not SLUG_RE.fullmatch(slug or "") or slug in RESERVED or slug.startswith("what-is"):
        errs.append(f"bad slug {slug[:40]!r}")
    elif slug in taken:
        errs.append(f"slug {slug} is taken")
    if m.get("pillar") not in PILLARS:
        errs.append("bad pillar")
    if m.get("motif") not in MOTIFS:
        errs.append("bad motif")
    for k in ("date", "updated"):
        if m.get(k):
            try:
                date.fromisoformat(str(m[k]))
            except ValueError:
                errs.append(f"bad {k}")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9 &'.-]{0,30}", str(m.get("en") or "")) or len(str(m.get("en")).split()) > 2:
        errs.append("bad en")
    if m.get("idea") and not str(m["idea"]).isdigit():
        errs.append("bad idea")
    src = m.get("sources") if isinstance(m.get("sources"), list) else []
    if not 1 <= len(src) <= 3 or any(not re.fullmatch(r"https://\S+", s.rpartition("|")[2].strip()) for s in src):
        errs.append("sources: 1-3 lines «label | https://…»")
    summ = m.get("summary") if isinstance(m.get("summary"), list) else []
    if not 3 <= len(summ) <= 5:
        errs.append("summary: 3-5 lines")
    steps = m.get("steps") if isinstance(m.get("steps"), list) else []
    if len(steps) != 5 or any("|" not in s for s in steps):
        errs.append("steps: exactly 5 «title | sentence»")
    low = text.lower()
    if "<script" in low or "<iframe" in low or "javascript:" in low:
        errs.append("raw script")
    for href in re.findall(r"\]\(([^)\s]+)\)", body):
        if not (href.startswith("/") or href.startswith("https://")) or href.startswith("//"):
            errs.append(f"bad link {href[:40]}")
        elif href.startswith("/go/") or "dotcoin.me/go/" in href:
            errs.append("a /go/ link in a lesson")
    n_words = len(re.findall(r"\S+", body))
    if n_words < 300:
        errs.append(f"too short ({n_words} words)")
    if "## پرسش‌های پرتکرار" not in body:
        warn.append("no FAQ section")
    d = len(str(m.get("description") or ""))
    if not 110 <= d <= 165:
        warn.append(f"description {d} chars")
    a = len(str(m.get("answer") or "").split())
    if not 35 <= a <= 70:
        warn.append(f"answer {a} words")
    if len(str(m.get("seo_title") or "")) > 60:
        warn.append("seo_title over 60 chars")
    return m, errs, warn


def set_field(text: str, key: str, value: str) -> str:
    end = text.index("\n---", 4)
    head, rest = text[:end], text[end:]
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    line = f"{key}: {value}".rstrip()
    head = pat.sub(lambda _: line, head, count=1) if pat.search(head) else f"{head}\n{line}"
    return head + rest


def local_slugs(skip: Path | None = None) -> set[str]:
    out = set()
    for d in (SITE / "content" / "articles", AUTO):
        for p in d.glob("*.md"):
            if skip is not None and p == skip:
                continue
            try:
                out.add(parse(p.read_text("utf-8"))[0].get("slug") or p.stem)
            except (ValueError, OSError):
                out.add(p.stem)
    return out


def live_slugs() -> set[str] | None:
    """The /learn/ slugs in the live sitemap (IPv4 only), None when it cannot be read."""
    orig = socket.getaddrinfo

    def v4(host, *a, **k):
        return [r for r in orig(host, *a, **k) if r[0] == socket.AF_INET]

    socket.getaddrinfo = v4
    try:
        req = urllib.request.Request(SITEMAP, headers={"User-Agent": "dotcoin-sync/1"})
        xml = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    except OSError as e:
        log(f"sitemap not read ({type(e).__name__}); local slugs only")
        return None
    finally:
        socket.getaddrinfo = orig
    return set(re.findall(r"<loc>https://dotcoin\.me/learn/([a-z0-9-]+)/</loc>", xml))


def build_ok(paths: list[Path]) -> tuple[bool, str]:
    """build.py into a throwaway dist, with the new files already in place."""
    tmp = Path(tempfile.mkdtemp(prefix="dotcoin-build-"))
    try:
        env = dict(os.environ, DOTCOIN_DIST=str(tmp / "dist"))
        r = run([sys.executable, "-I", str(SITE / "build.py")], cwd=SITE, env=env, timeout=300)
        return r.returncode == 0, tail(r.stdout + r.stderr, 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def secrets_clean(texts: dict[str, str]) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="dotcoin-leaks-"))
    try:
        for name, t in texts.items():
            (tmp / name).write_text(t, "utf-8")
        os.chmod(tmp, 0o755)
        r = run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{tmp}:/scan:ro",
                 GITLEAKS_IMAGE, "dir", "--no-banner", "--redact", "--exit-code", "1", "--log-level", "error",
                 "/scan"], timeout=300)
        return r.returncode == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ git and deploy
def git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(WT), *args], timeout=timeout)


def commit(msg: str) -> bool:
    git("add", "-A", "--", REL_AUTO)
    if git("diff", "--cached", "--quiet").returncode == 0:
        return False
    r = git("commit", "-q", "-m", msg)
    if r.returncode:
        raise RuntimeError(f"commit failed: {tail(r.stderr, 2)}")
    return True


def push() -> None:
    head = git("rev-parse", "HEAD").stdout.strip()
    remote = git("rev-parse", "-q", "--verify", f"refs/remotes/origin/{BRANCH}").stdout.strip()
    if head == remote:
        return
    r = git("push", "-q", "origin", f"HEAD:{BRANCH}", timeout=180)
    log("pushed" if r.returncode == 0 else f"push failed (retry next run): {tail(r.stderr, 1)}")


def deploy(state: dict) -> None:
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    if state.get("deployed") == head:
        return
    log("deploy …")
    r = run(["bash", str(SITE / "deploy.sh")], cwd=SITE, timeout=1500)
    out = r.stdout + r.stderr
    url = re.findall(rb"https://[0-9a-f]{8}\.dotcoin\.pages\.dev", out)
    if r.returncode:
        log(f"deploy failed (retry next run): {tail(out, 2)}")
        return
    state["deployed"] = head
    log(f"deployed {head[:8]}" + (f" ({url[-1].decode()})" if url else ""))


# ------------------------------------------------------------------ one pass
def load_state() -> dict:
    try:
        s = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("files", {})
    s.setdefault("articles", {})
    return s


def save_state(s: dict) -> None:
    s["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(STATE)


def ingest(state: dict, fid: str, ws: str, raw: bytes, dry: bool, live: set[str] | None) -> bool:
    """One article file: validate, write, build-check. True when content/auto changed."""
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n").lstrip("﻿").strip() + "\n"
    except UnicodeDecodeError:
        state["files"][fid] = {"w": ws, "status": "invalid", "why": "not utf-8"}
        log(f"skip {fid[:8]} ({ws}): not utf-8")
        return False
    own = next((s for s, a in state["articles"].items() if a.get("w") == ws), None)
    taken = local_slugs(AUTO / f"{own}.md" if own else None) | ((live or set()) - ({own} if own else set()))
    meta, errs, warns = validate(text, taken)
    slug = meta.get("slug") or ""
    if own and slug != own and not errs:
        errs.append(f"slug changed from {own}: a published slug never changes")
    if errs:
        state["files"][fid] = {"w": ws, "status": "invalid", "why": "; ".join(errs)[:300]}
        log(f"skip {fid[:8]} ({ws}): {'; '.join(errs)[:200]}")
        return False
    if warns:
        log(f"{slug}: warn {'; '.join(warns)}")
    reel = (state["articles"].get(slug) or {}).get("reel") or ""
    text = set_field(text, "reel", reel)
    if dry:
        log(f"would write {slug} ({ws})")
        return False
    if not secrets_clean({f"{slug}.md": text}):
        state["files"][fid] = {"w": ws, "status": "invalid", "why": "gitleaks finding"}
        log(f"skip {fid[:8]} ({ws}): gitleaks finding")
        return False
    AUTO.mkdir(parents=True, exist_ok=True)
    path = AUTO / f"{slug}.md"
    old = path.read_text("utf-8") if path.exists() else None
    if old == text:
        state["files"][fid] = {"w": ws, "status": "ok", "slug": slug}
        return False
    path.write_text(text, "utf-8")
    ok, why = build_ok([path])
    if not ok:
        if old is None:
            path.unlink()
        else:
            path.write_text(old, "utf-8")
        state["files"][fid] = {"w": ws, "status": "invalid", "why": f"build: {why}"[:300]}
        log(f"skip {fid[:8]} ({ws}): build failed: {why[:200]}")
        return False
    state["files"][fid] = {"w": ws, "status": "ok", "slug": slug}
    state["articles"][slug] = {"w": ws, "file": fid, "reel": reel}
    log(f"{'updated' if old else 'new'} article {slug} ({ws})")
    return True


def one_pass(args) -> int:
    state = load_state()
    msgs: list[str] = []
    rows = []
    if args.import_file:
        if not WS_RE.fullmatch(args.workspace or ""):
            log("--import needs --workspace W-…")
            return 2
        raw = Path(args.import_file).read_bytes()
        rows.append({"id": "import-" + hashlib.sha256(raw).hexdigest()[:16], "w": args.workspace, "raw": raw})
    else:
        rows = [r for r in candidates() if r["id"] not in state["files"] and WS_RE.fullmatch(str(r.get("w") or ""))]
    live = live_slugs() if rows else None
    for r in rows:
        if r["id"] in state["files"]:
            continue
        try:
            raw = r.get("raw") or file_bytes(r)
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"skip {r['id'][:8]} ({r['w']}): {e}")  # not marked: tried again next run
            continue
        if ingest(state, r["id"], r["w"], raw, args.dry_run, live):
            msgs.append(f"article {[s for s, a in state['articles'].items() if a['file'] == r['id']][0]}")
    # the reel's Instagram link, once out
    waiting = {s: a for s, a in state["articles"].items() if not a.get("reel")}
    urls = reel_urls(sorted({a["w"] for a in waiting.values()})) if waiting else {}
    for slug, a in waiting.items():
        url = urls.get(a["w"])
        path = AUTO / f"{slug}.md"
        if not url or not path.exists():
            continue
        if not args.dry_run:
            path.write_text(set_field(path.read_text("utf-8"), "reel", url), "utf-8")
            a["reel"] = url
            msgs.append(f"reel link {slug}")
        log(f"reel link {slug}: {url}")
    if args.dry_run:
        return 0
    if msgs and commit("DotCoin site: " + ", ".join(msgs) + " (sync.py)"):
        log("committed")
    save_state(state)
    push()
    deploy(state)
    save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--import", dest="import_file")
    ap.add_argument("--workspace")
    args = ap.parse_args()
    if not SITE.is_dir():
        log(f"no content worktree at {WT}")
        return 1
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another sync is running")
            return 0
        try:
            return one_pass(args)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"error: {str(e)[:200]}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
