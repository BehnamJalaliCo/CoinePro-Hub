#!/usr/bin/env python3
"""DotCoin.me: the hub's daily reels -> their articles on the live site (stdlib + ffmpeg; user Hub).

Every DotCoin reel's session (kit dotcoin-reels; educational and informational) leaves
`out/article.md`. One pass (dotcoin-site-sync.timer, every 15 minutes):
  1. finds the article.md files of dotcoin.me reels not synced yet (files.files by the workspace the
     file came from, joined to the reel's publish job on infra.server_jobs; the hub DB is only read);
  2. reads the bytes through `docker exec`, validates the front matter, the slug and the topic;
  3. writes content/auto/<slug>.md in the content worktree (branch site/dotcoin-content), or, for
     `attach: <slug>`, binds the reel to a lesson that already exists;
  4. makes the reel's web copy (/media/<slug>.mp4 + .jpg poster + .json, H.264 720x1280, about
     2 Mbit/s, faststart) in /home/Hub/sites/dotcoin-media (never in git; build.py copies it);
     ⟨2026-11-19⟩ the poster is the reel's REAL cover: its publication's cover in the hub (the one the
     owner's app and the Short show; a cover made or replaced after publishing too), else the
     publish job's cover; a video frame only when the reel has no cover at all. When the cover
     changes later (or a frame poster gets a cover), the poster alone is made again (state `poster`:
     the cover's file id, or `frame`);
  5. puts the Instagram URL in `reel:` once the publish job has `result.url`;
  6. only if something changed: build check, commit, push the branch, deploy.sh (Cloudflare, IPv4).

Never a duplicate: one source (`<channel>:<id>`, today `instagram:<the reel's work ref>`; later
`youtube:<video id>`) -> one slug, a slug or a topic is never published twice, an article bound to
another source is never overwritten. State: /home/Hub/sites/dotcoin-sync.json. One lock. An idle
run reads two queries, logs nothing and exits. Never prints a secret.

    sync.py                                       one pass
    sync.py --dry-run                             find and validate only; write nothing
    sync.py --import FILE --workspace W-000583    take a local article.md as if the hub had made it
    sync.py --check FILE                          the session's self-check (kit dotcoin-reels): exit 1 on
                                                  an error; needs no worktree, no hub, no lock
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
ARTS, AUTO = SITE / "content" / "articles", SITE / "content" / "auto"
REL_AUTO = "automations/sites/dotcoin/content/auto"
HOME = Path(os.environ.get("DOTCOIN_SYNC_HOME", "/home/Hub/sites"))
MEDIA = Path(os.environ.get("DOTCOIN_MEDIA", "/home/Hub/sites/dotcoin-media"))
STATE, LOCK = HOME / "dotcoin-sync.json", HOME / "dotcoin-sync.lock"
BRANCH = "site/dotcoin-content"
API, PG = "coinepro-hq-api-1", "coinepro-hq-postgres-1"
ACCOUNT = "dotcoin.me"
# ⟨2026-11-26⟩ the owner's new Instagram page @DotCoinMe (dotcoinme) replaced @dotcoin.me: reels of both count
ACCOUNTS_SQL = "'dotcoin.me', 'dotcoinme'"
SITEMAP = "https://dotcoin.me/sitemap.xml"
GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.30.1"
FFMPEG_IMAGE = "jrottenberg/ffmpeg:7.1-alpine"

PILLARS = {"basics", "security", "exchange", "market", "defi", "myths", "terms", "news"}
MOTIFS = {"chain", "vault", "halving", "peg", "generic"}
RESERVED = {"basics", "security", "exchange", "market", "defi", "myths", "terms", "news", "page", "tag",
            "feed", "go", "search", "media"}
REQUIRED = ("title", "seo_title", "slug", "pillar", "date", "en", "motif", "description", "lead", "answer")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,5}")
WS_RE = re.compile(r"W-\d{3,9}")
KEY_RE = re.compile(r"[0-9a-f]{16,64}")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
IG_URL = re.compile(r"https://www\.instagram\.com/\S{3,200}")


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: int = 120,
        stdout=subprocess.PIPE) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout)


def tail(b: bytes | None, n: int = 4) -> str:
    lines = [ln for ln in (b or b"").decode("utf-8", "replace").splitlines() if ln.strip()]
    return " / ".join(ln.strip()[:160] for ln in lines[-n:])


# ------------------------------------------------------------------ the hub (read only)
def sql(query: str) -> list[dict]:
    q = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t"
    r = run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", PG,
             "psql", "-U", "postgres", "-d", "hq", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", q], timeout=60)
    if r.returncode:
        raise RuntimeError(f"db query failed: {tail(r.stderr, 2)}")
    return json.loads(r.stdout.decode() or "[]")


JOBS_SQL = f"""
    SELECT DISTINCT ON (j.args -> 'session' ->> 'work')
           j.args -> 'session' ->> 'work' AS w, j.id::text AS job, j.args -> 'session' ->> 'file_id' AS video,
           -- ⟨2026-11-19⟩ the reel's real cover: its publication's cover (role cover: never the hub's
           -- frame, role thumb), else the publish job's own cover file
           coalesce(
             (SELECT x ->> 'file_id' FROM media.publications p, jsonb_array_elements(p.files) x
               WHERE p.kind = 'reel' AND p.chain @> ARRAY[j.id] AND x ->> 'role' = 'cover'
               ORDER BY p.updated_at DESC LIMIT 1),
             (SELECT x ->> 'file_id' FROM jsonb_array_elements(
                     CASE WHEN jsonb_typeof(j.args -> 'files') = 'array' THEN j.args -> 'files' ELSE '[]'::jsonb END) x
               WHERE x ->> 'role' = 'cover' LIMIT 1)) AS cover,
           j.args -> 'meta' ->> 'scheduled_at' AS at, j.result ->> 'url' AS url
      FROM infra.server_jobs j
     WHERE j.kind = 'publish' AND j.args ->> 'account' IN ({ACCOUNTS_SQL}) AND j.args ->> 'kind' = 'reel'
       AND j.state <> 'cancelled' AND j.created_at > now() - interval '30 days'
     ORDER BY j.args -> 'session' ->> 'work', (j.result ->> 'url' IS NOT NULL) DESC, j.created_at DESC"""


def reel_jobs() -> dict[str, dict]:
    """The reel publish job of each dotcoin.me work (the newest, one with a URL first)."""
    return {r["w"]: r for r in sql(JOBS_SQL) if WS_RE.fullmatch(str(r.get("w") or ""))}


def new_articles(done: set[str]) -> list[dict]:
    rows = sql(f"""
        WITH ws AS (SELECT DISTINCT j.args -> 'session' ->> 'work' AS w FROM infra.server_jobs j
                     WHERE j.kind = 'publish' AND j.args ->> 'account' IN ({ACCOUNTS_SQL}) AND j.args ->> 'kind' = 'reel'
                       AND j.created_at > now() - interval '30 days')
        SELECT f.id::text AS id, f.storage_key AS key, f.sha256 AS sha, f.size, f.meta ->> 'workspace' AS w
          FROM files.files f JOIN ws ON ws.w = f.meta ->> 'workspace'
         WHERE lower(f.name) = 'article.md' AND f.variant = 'original'
           AND f.created_at > now() - interval '30 days'
         ORDER BY f.created_at""")
    return [r for r in rows if r["id"] not in done and WS_RE.fullmatch(str(r.get("w") or ""))]


def file_row(fid: str) -> dict | None:
    if not UUID_RE.fullmatch(fid or ""):
        return None
    rows = sql(f"SELECT id::text AS id, storage_key AS key, sha256 AS sha, size FROM files.files WHERE id = '{fid}'")
    return rows[0] if rows else None


def fetch(row: dict, dest: Path | None = None, limit: int = 300_000) -> bytes:
    """A hub file's bytes (docker exec), checked against its sha256; to `dest` when given."""
    key = str(row["key"])
    if not KEY_RE.fullmatch(key) or int(row["size"]) > limit:
        raise ValueError("unexpected storage key or size")
    cmd = ["docker", "exec", API, "cat", f"/data/files/{key[:2]}/{key}"]
    if dest is None:
        r = run(cmd, timeout=120)
        data = r.stdout
    else:
        with open(dest, "wb") as out:
            r = run(cmd, timeout=300, stdout=out)
        data = dest.read_bytes()
    if r.returncode:
        raise RuntimeError(f"read failed: {tail(r.stderr, 1)}")
    if row.get("sha") and hashlib.sha256(data).hexdigest() != row["sha"]:
        raise ValueError("sha256 mismatch")
    return data


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


def norm(s) -> str:
    s = str(s or "").replace("ي", "ی").replace("ك", "ک").lower()
    return re.sub(r"[\s‌‏‎؟?،,.:;!«»\"'()|-]+", "", s)


def topics(meta: dict, aliases: bool = False) -> set[str]:
    """The topic keys of an article: its keyword and title; with `aliases`, also its `keywords`
    (a lesson's own near-synonyms, e.g. «رمز ارز چیست» for «ارز دیجیتال چیست»)."""
    vals = [meta.get("keyword"), meta.get("title")]
    if aliases:
        kw = meta.get("keywords")
        vals += kw if isinstance(kw, list) else str(kw or "").split("،" if "،" in str(kw or "") else ",")
    return {norm(v) for v in vals if norm(v)}


def same_lesson(meta: dict, lessons: dict[str, dict]) -> str | None:
    """The lesson already on the site that this reel's article is about: the same slug, the same
    idea (ideas.json id) or the same topic. Such a reel joins that lesson (never a second article)."""
    slug = str(meta.get("slug") or "")
    if slug in lessons:
        return slug
    idea = str(meta.get("idea") or "")
    if idea.isdigit():
        hit = next((s for s, m in lessons.items() if str(m.get("idea") or "") == idea), None)
        if hit:
            return hit
    mine = topics(meta)
    return next((s for s, m in lessons.items() if mine & topics(m, aliases=True)), None) if mine else None


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
        errs.append(f"slug {slug} is taken: if this reel teaches that lesson, write only `attach: {slug}`")
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
    if m.get("youtube") and not re.match(r"(https://(www\.|m\.)?(youtube\.com|youtu\.be)/\S+|[A-Za-z0-9_-]{11})$",
                                         str(m["youtube"])):
        errs.append("bad youtube")
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


def local_articles(skip: str = "") -> dict[str, dict]:
    """slug -> front matter of every lesson in the worktree (by hand and auto), but `skip`."""
    out: dict[str, dict] = {}
    for d in (ARTS, AUTO):
        try:
            files = sorted(d.glob("*.md"))
        except OSError:  # --check as the studio user: no access to the hub's worktree
            continue
        for p in files:
            try:
                m = parse(p.read_text("utf-8"))[0]
            except (ValueError, OSError):
                m = {}
            slug = m.get("slug") or p.stem
            if slug != skip:
                out[slug] = m
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


def build_ok() -> tuple[bool, str]:
    """build.py into a throwaway dist, with the new files already in place."""
    tmp = Path(tempfile.mkdtemp(prefix="dotcoin-build-"))
    try:
        env = dict(os.environ, DOTCOIN_DIST=str(tmp / "dist"), DOTCOIN_MEDIA=str(MEDIA))
        r = run([sys.executable, "-I", str(SITE / "build.py")], cwd=SITE, env=env, timeout=300)
        return r.returncode == 0, tail(r.stdout + r.stderr, 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def secrets_clean(name: str, text: str) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="dotcoin-leaks-"))
    try:
        (tmp / name).write_text(text, "utf-8")
        os.chmod(tmp, 0o755)
        r = run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{tmp}:/scan:ro",
                 GITLEAKS_IMAGE, "dir", "--no-banner", "--redact", "--exit-code", "1", "--log-level", "error",
                 "/scan"], timeout=300)
        return r.returncode == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ the reel's web copy
def ffmpeg(args: list[str], work: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Host ffmpeg when installed, else the docker image (work mounted at the same path)."""
    tool = args[0]
    if shutil.which(tool):
        return run([tool, *args[1:]], timeout=timeout)
    return run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{work}:{work}",
                "--entrypoint", tool, FFMPEG_IMAGE, *args[1:]], timeout=timeout)


def make_media(slug: str, src: dict, job: dict) -> bool:
    """MEDIA/<slug>.mp4 (H.264 720x1280, ~2 Mbit/s, AAC, faststart), .jpg (the cover) and .json."""
    vrow, crow = file_row(str(job.get("video") or "")), file_row(str(job.get("cover") or ""))
    if not vrow:
        log(f"{slug}: the reel's video is not on the hub (any more)")
        return False
    MEDIA.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tmp-", dir=MEDIA))
    try:
        os.chmod(work, 0o777)
        fetch(vrow, work / "in.mp4", limit=300_000_000)
        out = work / "out.mp4"
        for rate in ("2M", "1200k"):  # well under Pages' 25 MB file limit
            r = ffmpeg(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(work / "in.mp4"),
                        "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,"
                               "pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=30",
                        "-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-pix_fmt", "yuv420p",
                        "-b:v", rate, "-maxrate", "2500k", "-bufsize", "5000k", "-c:a", "aac", "-b:a", "128k",
                        "-ac", "2", "-movflags", "+faststart", str(out)], work)
            if r.returncode:
                raise RuntimeError(f"ffmpeg: {tail(r.stderr, 2)}")
            if out.stat().st_size < 24_000_000:
                break
        else:
            raise RuntimeError("the web copy is over 24 MB")
        poster = poster_into(work, out, crow)
        r = ffmpeg(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], work)
        secs = round(float((r.stdout or b"0").decode().strip() or 0))
        shutil.move(out, MEDIA / f"{slug}.mp4")
        shutil.move(poster, MEDIA / f"{slug}.jpg")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    src["media"] = str(job.get("video"))
    src["poster"] = str(crow["id"]) if crow else "frame"
    src["duration"] = f"PT{secs // 60}M{secs % 60}S" if secs >= 60 else f"PT{secs}S"
    write_sidecar(slug, src, job)
    log(f"{slug}: video {round((MEDIA / f'{slug}.mp4').stat().st_size / 1e6, 1)} MB, {secs} s")
    return True


def poster_into(work: Path, video: Path, crow: dict | None) -> Path:
    """work/poster.jpg (720x1280, the site's poster): the reel's cover when it has one, else the video's
    frame at 1 s."""
    poster = work / "poster.jpg"
    if crow:
        fetch(crow, work / "cover.img", limit=30_000_000)
        src_img, seek = [str(work / "cover.img")], []
    else:  # no cover: a frame of the video
        src_img, seek = [str(video)], ["-ss", "1"]
    r = ffmpeg(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *seek, "-i", *src_img, "-frames:v", "1",
                "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
                "-q:v", "3", str(poster)], work)
    if r.returncode or not poster.is_file():
        raise RuntimeError(f"poster: {tail(r.stderr, 2)}")
    return poster


def poster_due(src: dict, job: dict) -> bool:
    """⟨2026-11-19⟩ The web copy is there but its poster is not the reel's current cover (a frame poster
    whose reel got a cover, or a cover replaced after publishing)."""
    cover = str(job.get("cover") or "")
    return (bool(UUID_RE.fullmatch(cover)) and src.get("poster") != cover and bool(src.get("slug"))
            and (MEDIA / f"{src['slug']}.mp4").is_file() and src.get("poster_tries", 0) < 3)


def make_poster(slug: str, src: dict, job: dict) -> bool:
    """MEDIA/<slug>.jpg again from the reel's current cover (the video stays as it is)."""
    crow = file_row(str(job.get("cover") or ""))
    if not crow:
        log(f"{slug}: the reel's cover is not on the hub (any more)")
        return False
    work = Path(tempfile.mkdtemp(prefix="tmp-", dir=MEDIA))
    try:
        os.chmod(work, 0o777)
        poster = poster_into(work, MEDIA / f"{slug}.mp4", crow)
        os.chmod(poster, 0o644)
        os.replace(poster, MEDIA / f"{slug}.jpg")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    old = src.get("poster") or "unknown"
    src["poster"] = str(crow["id"])
    src.pop("poster_tries", None)
    log(f"{slug}: poster = the reel's cover {crow['id'][:8]} (was {old[:8]})")
    return True


def write_sidecar(slug: str, src: dict, job: dict) -> None:
    side = {"key": src["key"], "job": job.get("job") or src.get("job"), "reel": src.get("reel") or "",
            "upload": job.get("at") or src.get("upload") or "", "duration": src.get("duration") or "",
            "width": 720, "height": 1280}
    src["upload"] = side["upload"]
    (MEDIA / f"{slug}.json").write_text(json.dumps(side, ensure_ascii=False, indent=1), "utf-8")


def media_print() -> str:
    """A fingerprint of the web copies (what deploy.sh uploads besides git)."""
    h = hashlib.sha256()
    if MEDIA.is_dir():
        for p in sorted(MEDIA.glob("*.*")):
            if p.suffix in (".mp4", ".jpg", ".json"):
                st = p.stat()
                h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}\n".encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ git and deploy
def git(*args: str, timeout: int = 120) -> str:
    r = run(["git", "-C", str(WT), *args], timeout=timeout)
    if r.returncode and args[0] != "rev-parse":
        raise RuntimeError(f"git {args[0]} failed: {tail(r.stderr, 2)}")
    return r.stdout.decode().strip() if r.returncode == 0 else ""


def commit(msg: str) -> bool:
    git("add", "-A", "--", REL_AUTO)
    if run(["git", "-C", str(WT), "diff", "--cached", "--quiet"]).returncode == 0:
        return False
    git("commit", "-q", "-m", msg)
    return True


def push() -> None:
    if git("rev-parse", "HEAD") == git("rev-parse", "-q", "--verify", f"refs/remotes/origin/{BRANCH}"):
        return
    r = run(["git", "-C", str(WT), "push", "-q", "origin", f"HEAD:{BRANCH}"], timeout=180)
    log("pushed" if r.returncode == 0 else f"push failed (retry next run): {tail(r.stderr, 1)}")


def fingerprint() -> str:
    return f"{git('rev-parse', 'HEAD')}:{media_print()}"


def deploy(state: dict) -> None:
    fp = fingerprint()
    if state.get("deployed") == fp:
        return
    log("deploy …")
    r = run(["bash", str(SITE / "deploy.sh")], cwd=SITE, env=dict(os.environ, DOTCOIN_MEDIA=str(MEDIA)), timeout=1500)
    out = (r.stdout or b"") + (r.stderr or b"")
    if r.returncode:
        log(f"deploy failed (retry next run): {tail(out, 2)}")
        return
    url = re.findall(rb"https://[0-9a-f]{8}\.dotcoin\.pages\.dev", out)
    state["deployed"] = fp
    log(f"deployed {fp[:8]}" + (f" ({url[-1].decode()})" if url else ""))


# ------------------------------------------------------------------ one pass
def load_state() -> dict:
    try:
        s = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("files", {})
    s.setdefault("sources", {})
    return s


def save_state(s: dict) -> None:
    s["last_change"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(STATE)


def owner_of(state: dict, slug: str) -> str | None:
    return next((k for k, s in state["sources"].items() if s.get("slug") == slug), None)


def ingest(state: dict, fid: str, ws: str, raw: bytes, job: dict, dry: bool, live: set[str] | None) -> str:
    """One article.md of a reel: '' (nothing written to git) or a commit-message part."""
    key = f"instagram:{ws}"
    src = state["sources"].get(key) or {}
    own = src.get("slug")

    def skip(why: str) -> str:
        if not dry:
            state["files"][fid] = {"w": ws, "status": "invalid", "why": why[:300]}
        log(f"skip {fid[:8]} ({ws}): {why[:200]}")
        return ""

    try:
        text = raw.decode("utf-8").replace("\r\n", "\n").lstrip("﻿").strip() + "\n"
        meta = parse(text)[0]
    except (UnicodeDecodeError, ValueError) as e:
        return skip(f"unreadable: {e}")
    def join(slug: str, how: str) -> str:
        """Bind this reel (its video, later its Short) to a lesson already on the site."""
        if own and own != slug:
            return skip(f"this reel already has its article {own}")
        if slug not in local_articles():
            return skip(f"attach: no lesson {slug}")
        if (k := owner_of(state, slug)) and k != key:
            return skip(f"{how}: {slug} already belongs to {k}")
        if not dry:
            state["sources"][key] = {**src, "key": key, "slug": slug, "job": job.get("job"), "w": ws}
            state["files"][fid] = {"w": ws, "status": "ok", "slug": slug, "attach": True, "how": how}
        log(f"reel {ws} -> existing lesson {slug} ({how})")
        return ""

    # `attach: <slug>`: the reel's lesson is already on the site (written by hand before the reel)
    if meta.get("attach"):
        return join(str(meta["attach"]).strip(), "attach")
    others = local_articles(skip=own or "")
    # a full article about a lesson that is already there (same slug, idea or topic): the reel joins
    # that lesson instead of becoming a second article on the same topic
    if not own and (hit := same_lesson(meta, others)):
        return join(hit, "same lesson")
    taken = set(others) | ((live or set()) - ({own} if own else set()))
    meta, errs, warns = validate(text, taken)
    slug = meta.get("slug") or ""
    if own and slug != own and not errs:
        errs.append(f"slug changed from {own}: a published slug never changes")
    if (k := owner_of(state, slug)) and k != key:
        errs.append(f"{slug} belongs to another reel ({k})")
    dup = next((s for s, m in others.items() if topics(m) & topics(meta)), None)
    if dup:
        errs.append(f"same topic as {dup}")
    if errs:
        return skip("; ".join(errs))
    if warns:
        log(f"{slug}: warn {'; '.join(warns)}")
    text = set_field(text, "reel", src.get("reel") or "")
    if dry:
        log(f"would write {slug} ({ws})")
        return ""
    if not secrets_clean(f"{slug}.md", text):
        return skip("gitleaks finding")
    AUTO.mkdir(parents=True, exist_ok=True)
    path = AUTO / f"{slug}.md"
    old = path.read_text("utf-8") if path.exists() else None
    state["sources"][key] = {**src, "key": key, "slug": slug, "job": job.get("job"), "w": ws}
    if old == text:
        state["files"][fid] = {"w": ws, "status": "ok", "slug": slug}
        return ""
    path.write_text(text, "utf-8")
    ok, why = build_ok()
    if not ok:
        if old is None:
            path.unlink()
            if not own:
                state["sources"].pop(key, None)
        else:
            path.write_text(old, "utf-8")
        return skip(f"build failed: {why}")
    state["files"][fid] = {"w": ws, "status": "ok", "slug": slug}
    log(f"{'updated' if old else 'new'} article {slug} ({ws})")
    return f"{'update' if old else 'article'} {slug}"


def one_pass(args) -> int:
    state = load_state()
    before = json.dumps(state, sort_keys=True)
    msgs: list[str] = []
    if args.import_file:
        if not WS_RE.fullmatch(args.workspace or ""):
            log("--import needs --workspace W-…")
            return 2
        raw = Path(args.import_file).read_bytes()
        rows = [{"id": "import-" + hashlib.sha256(raw).hexdigest()[:16], "w": args.workspace, "raw": raw}]
    else:
        rows = new_articles(set(state["files"]))
    jobs = reel_jobs()  # ⟨2026-11-19⟩ every run: a reel's cover may change after its article (the poster)
    live = live_slugs() if rows else None
    for r in rows:
        if r["id"] in state["files"]:
            continue
        job = jobs.get(r["w"])
        if not job:
            log(f"wait {r['id'][:8]} ({r['w']}): no reel publish job yet")
            continue
        try:
            raw = r.get("raw") or fetch(r)
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"skip {r['id'][:8]} ({r['w']}): {e}")  # not marked: tried again next run
            continue
        if part := ingest(state, r["id"], r["w"], raw, job, args.dry_run, live):
            msgs.append(part)
    if args.dry_run:
        return 0
    # each reel's web copy and its Instagram link
    for src in state["sources"].values():
        slug, job = src.get("slug"), jobs.get(src.get("w") or "")
        if not slug or not job:
            continue
        if (src.get("media") != job.get("video") or not (MEDIA / f"{slug}.mp4").is_file()) \
                and src.get("media_tries", 0) < 3:
            try:
                if not make_media(slug, src, job):
                    src["media_tries"] = src.get("media_tries", 0) + 1
            except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                src["media_tries"] = src.get("media_tries", 0) + 1
                log(f"{slug}: video not made ({str(e)[:160]})")
        elif poster_due(src, job):
            try:
                if not make_poster(slug, src, job):
                    src["poster_tries"] = src.get("poster_tries", 0) + 1
            except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                src["poster_tries"] = src.get("poster_tries", 0) + 1
                log(f"{slug}: poster not made ({str(e)[:160]})")
        url = job.get("url") or ""
        if IG_URL.fullmatch(url) and src.get("reel") != url:
            src["reel"] = url
            if (MEDIA / f"{slug}.json").is_file():
                write_sidecar(slug, src, job)
            path = AUTO / f"{slug}.md"
            if path.exists():  # a hand-written lesson takes it from the sidecar
                path.write_text(set_field(path.read_text("utf-8"), "reel", url), "utf-8")
                msgs.append(f"reel link {slug}")
            log(f"{slug}: reel {url}")
    if msgs and commit("DotCoin site: " + ", ".join(msgs) + " (sync.py)"):
        log("committed")
    if json.dumps(state, sort_keys=True) != before:
        save_state(state)
    push()
    deploy(state)
    if json.dumps(state, sort_keys=True) != before:
        save_state(state)
    return 0


def quiet_now() -> bool:
    """⟨2026-11-26⟩ The owner: nothing goes out between 00:00 and 08:00 Tehran (any channel); the
    morning opens at 08:10, like the hub's quiet_hours. Making things in the night is fine."""
    from datetime import datetime as _dt
    from datetime import time as _time
    from zoneinfo import ZoneInfo as _Z

    return _dt.now(_Z("Asia/Tehran")).time() < _time(8, 10)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--import", dest="import_file")
    ap.add_argument("--workspace")
    ap.add_argument("--check")
    args = ap.parse_args()
    if quiet_now() and not (args.dry_run or args.import_file or args.workspace or args.check):
        log("night (00:00 to 08:10 Tehran): nothing goes out now")
        return 0
    if args.check:
        text = Path(args.check).read_text("utf-8").replace("\r\n", "\n").lstrip("﻿")
        try:
            meta = parse(text)[0]
        except ValueError as e:
            log(f"error: {e}")
            return 1
        live = live_slugs()
        if meta.get("attach"):
            ok = str(meta["attach"]) in (live or set())
            log("ok (attach)" if ok else f"error: no lesson {meta['attach']} on the site")
            return 0 if ok else 1
        others = local_articles()
        meta, errs, warns = validate(text, (live or set()) | set(others))
        for w in warns:
            log(f"warn: {w}")
        for e in errs:
            log(f"error: {e}")
        log("ok" if not errs else "NOT OK: fix the errors (an invalid article never reaches the site)")
        return 1 if errs else 0
    if not SITE.is_dir():
        log(f"no content worktree at {WT}")
        return 1
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            return one_pass(args)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"error: {str(e)[:200]}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
