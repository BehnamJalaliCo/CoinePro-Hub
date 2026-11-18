#!/usr/bin/env python3
"""DotCoin.me: each reel published on Instagram -> ONE public YouTube Short on @DotCoin-me (stdlib + ffmpeg).

The YouTube API keeps an unaudited app's uploads private, so the upload runs in the hub's signed-in
browser profile `youtube-web` (YouTube Studio; egress recipe infra/egress/recipes/youtube-web.yaml).
One pass (dotcoin-youtube.timer, every 15 minutes, user Hub):
  1. finds dotcoin.me reels published on Instagram (infra.server_jobs: kind publish, account
     dotcoin.me, kind reel, result.url set; the hub DB is only read) that the state file lacks;
  2. reads the reel's video through `docker exec` (checked against its sha256) and makes the upload
     copy: H.264 1080x1920, about 5.5 Mbit/s, 30 fps, AAC, faststart;
  3. writes the Persian title (the lesson's title, else the caption's first line; <= 90 characters
     + " #Shorts") and the description (the caption without its Instagram call to action, the
     article's link on dotcoin.me, the Instagram page, 3-5 hashtags);
  4. asks the channel for its Shorts' titles (task `titles`): a video of the same title is never
     uploaded again; then uploads (task `upload`) through egress from inside the hub's network
     (`docker exec` into the worker, the hub's own path to POST /v1/substitutes/web) and records
     the video's link;
  5. ⟨2026-11-18⟩ sets the Short's thumbnail to its reel's own Instagram cover (the reel's
     publication's thumbnail in the hub, read like the video; task `thumbnail`: Studio's per-video
     custom thumbnail, then Save), on the same pass, and on later passes for a Short without it yet
     (at most 3 tries; state `thumb_set` yes / no); a Short is never uploaded again for it;
  6. puts the link in the article's `youtube:` field in the content worktree (under the site sync's
     own lock), commits, and runs the site sync once (push, build, deploy).

Never a duplicate: one source -> one upload, keyed `<channel>|<external id>` (today
`youtube:@DotCoin-me|instagram:<the reel's work ref>`; a long video later gets its own external id),
and one video file (its sha256) -> one upload. A failed upload is tried again at most 3 times, and
never once its job may have reached the Publish click (state `check`: a person looks). State:
/home/Hub/sites/dotcoin-youtube.json. One lock. An idle run reads one query, logs nothing and exits.
Never prints a cookie, a token or a screenshot (a failed step's screenshot is saved for the SRE).

    youtube.py                       one pass
    youtube.py --dry-run             find, build the title and description, print them; upload nothing
    youtube.py --task channel|titles one read-only job in the profile (its text printed)
    youtube.py --only W-000583       limit the pass to one reel
    youtube.py --only W-000583 --unlisted   a check upload: Unlisted (state `unlisted`; no article link)
    youtube.py --make-public W-000583       an Unlisted check upload made Public (then `done`)
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WT = Path(os.environ.get("DOTCOIN_CONTENT_WT", "/home/Hub/sites/dotcoin-content"))
SITE = WT / "automations" / "sites" / "dotcoin"
ARTS, AUTO = SITE / "content" / "articles", SITE / "content" / "auto"
HOME = Path(os.environ.get("DOTCOIN_SYNC_HOME", "/home/Hub/sites"))
STATE, LOCK = HOME / "dotcoin-youtube.json", HOME / "dotcoin-youtube.lock"
SYNC_STATE, SYNC_LOCK = HOME / "dotcoin-sync.json", HOME / "dotcoin-sync.lock"
SHOTS = HOME / "dotcoin-youtube-shots"
API, PG, WORKER = "coinepro-hq-api-1", "coinepro-hq-postgres-1", "coinepro-hq-worker-1"
ACCOUNT, PROFILE = "dotcoin.me", "youtube-web"
CHANNEL = "youtube:@DotCoin-me"
RECIPE = Path(os.environ.get("DOTCOIN_YT_RECIPE", "/home/Hub/CoinePro-Hub/infra/egress/recipes/youtube-web.yaml"))
ARTICLE_URL = "https://dotcoin.me/learn/{slug}/"
INSTAGRAM = "https://www.instagram.com/dotcoin.me"
FFMPEG_IMAGE = "jrottenberg/ffmpeg:7.1-alpine"
MAX_VIDEO = 300 * 1024 * 1024  # a reel's original (read limit)
UPLOAD_CAP = 90 * 1024 * 1024  # under egress's upload cap (recipes.TASK_FILE_BYTES, 96 MB)
MAX_COVER = 25 * 1024 * 1024  # a reel's cover (read limit)
MAX_THUMB = 2 * 1024 * 1024  # YouTube's own cap for a custom thumbnail
TRIES = 3
SIGNED_OUT_WAIT_S = 2 * 3600  # a signed-out profile: tried again after this

WS_RE = re.compile(r"W-\d{3,9}")
KEY_RE = re.compile(r"[0-9a-f]{16,64}")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
IG_URL = re.compile(r"https://www\.instagram\.com/\S{3,200}")
YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
YT_URL = re.compile(r"https://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,5}")
# pictographs, dingbats, variation selectors and the zero-width joiner (never in a title)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")
HASHTAG = re.compile(r"#[^\s#]{2,40}")
# an Instagram call to action, a disclaimer or a hype line: never in the description
DROP = re.compile(r"کامنت|فالو|دایرکت|بیو|لایک|سیو|ذخیره کن|شیر کن|@|توصیه[‌ ]?ی? مالی|مشاوره[‌ ]?ی? مالی|"
                  r"سلب مسئولیت|پیش[‌ ]?بینی قیمت|سود تضمینی|پولدار|موشک|follow|comment|link in bio", re.I)
BASE_TAGS = ["#دات_کوین", "#ارز_دیجیتال", "#کریپتو"]


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], *, timeout: int = 120, stdin=None, stdout=subprocess.PIPE, cwd: Path | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout, cwd=cwd, env=env)


def tail(b: bytes | None, n: int = 2) -> str:
    lines = [ln for ln in (b or b"").decode("utf-8", "replace").splitlines() if ln.strip()]
    return " / ".join(ln.strip()[:160] for ln in lines[-n:])


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the hub (read only)
def sql(query: str) -> list[dict]:
    q = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t"
    r = run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", PG,
             "psql", "-U", "postgres", "-d", "hq", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", q], timeout=60)
    if r.returncode:
        raise RuntimeError(f"db query failed: {tail(r.stderr)}")
    return json.loads(r.stdout.decode() or "[]")


REELS_SQL = f"""
    SELECT DISTINCT ON (j.args -> 'session' ->> 'work')
           j.args -> 'session' ->> 'work' AS w, j.id::text AS job, j.args -> 'meta' ->> 'key' AS chain,
           j.args -> 'session' ->> 'file_id' AS video,
           -- the chain's caption (a follow-up job that records the published URL carries none)
           (SELECT c.args ->> 'caption' FROM infra.server_jobs c
             WHERE c.kind = 'publish' AND c.args -> 'session' ->> 'work' = j.args -> 'session' ->> 'work'
               AND coalesce(c.args ->> 'caption', '') <> '' ORDER BY c.created_at DESC LIMIT 1) AS caption,
           j.result ->> 'url' AS url, f.storage_key AS key, f.sha256 AS sha, f.size AS size,
           cover.storage_key AS cover_key, cover.sha256 AS cover_sha, cover.size AS cover_size,
           cover.mime AS cover_mime
      FROM infra.server_jobs j
      JOIN files.files f ON f.id::text = j.args -> 'session' ->> 'file_id'
      -- ⟨2026-11-18⟩ the reel's Instagram cover (the Short's thumbnail): its publication's thumbnail
      -- (media.publications, the chain that holds this job), else the chain's publish job's cover file
      LEFT JOIN LATERAL (
           SELECT cf.storage_key, cf.sha256, cf.size, cf.mime FROM files.files cf
            WHERE cf.id = coalesce(
                  (SELECT p.thumb_file_id FROM media.publications p
                    WHERE p.kind = 'reel' AND p.chain @> ARRAY[j.id] AND p.thumb_file_id IS NOT NULL
                    ORDER BY p.updated_at DESC LIMIT 1),
                  (SELECT (x ->> 'file_id')::uuid FROM infra.server_jobs c,
                          jsonb_array_elements(CASE WHEN jsonb_typeof(c.args -> 'files') = 'array'
                                                    THEN c.args -> 'files' ELSE '[]'::jsonb END) x
                    WHERE c.kind = 'publish' AND c.args -> 'session' ->> 'work' = j.args -> 'session' ->> 'work'
                      AND x ->> 'role' = 'cover' AND x ->> 'file_id' ~ '^[0-9a-f]{{8}}(-[0-9a-f]{{4}}){{3}}-[0-9a-f]{{12}}$'
                    ORDER BY c.created_at DESC LIMIT 1))) cover ON true
     WHERE j.kind = 'publish' AND j.args ->> 'account' = '{ACCOUNT}' AND j.args ->> 'kind' = 'reel'
       AND j.state = 'done' AND j.result ->> 'url' LIKE 'https://www.instagram.com/%'
       AND j.created_at > now() - interval '30 days'
     ORDER BY j.args -> 'session' ->> 'work', j.created_at DESC"""


def published_reels() -> list[dict]:
    return [r for r in sql(REELS_SQL) if WS_RE.fullmatch(str(r.get("w") or ""))
            and UUID_RE.fullmatch(str(r.get("video") or "")) and IG_URL.fullmatch(str(r.get("url") or ""))]


def read_file(key: str, sha: str | None, size: int, cap: int, dest: Path) -> None:
    """A file of the hub's storage (docker exec) into `dest`, checked against its sha256."""
    key = str(key)
    if not KEY_RE.fullmatch(key) or not 0 < int(size) <= cap:
        raise ValueError("unexpected storage key or size")
    with open(dest, "wb") as out:
        r = run(["docker", "exec", API, "cat", f"/data/files/{key[:2]}/{key}"], timeout=300, stdout=out)
    if r.returncode:
        raise RuntimeError(f"read failed: {tail(r.stderr, 1)}")
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if sha and h.hexdigest() != sha:
        raise ValueError("sha256 mismatch")


def fetch(row: dict, dest: Path) -> None:
    """The reel's original bytes into `dest`, checked against its sha256."""
    read_file(row["key"], row.get("sha"), row["size"], MAX_VIDEO, dest)


def cover_file(row: dict, work: Path) -> Path:
    """The reel's Instagram cover as the Short's thumbnail: the cover itself (a JPEG or PNG of at most
    2 MB, YouTube's own cap), else a JPEG made from it (same picture, at most 1080x1920)."""
    if not row.get("cover_key"):
        raise ValueError("the reel has no cover in the hub")
    mime = str(row.get("cover_mime") or "")
    src = work / ("cover.png" if mime == "image/png" else "cover.jpg" if mime == "image/jpeg" else "cover.img")
    read_file(row["cover_key"], row.get("cover_sha"), row["cover_size"], MAX_COVER, src)
    if src.suffix in (".jpg", ".png") and src.stat().st_size <= MAX_THUMB:
        return src
    dest = work / "thumb.jpg"
    for q in (2, 4, 7):
        r = tool(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-frames:v", "1", "-vf",
                  "scale='min(1080,iw)':-2:flags=lanczos,format=yuvj420p", "-q:v", str(q), str(dest)], work, timeout=120)
        if r.returncode or not dest.is_file():
            raise RuntimeError(f"ffmpeg (cover): {tail(r.stderr)}")
        if dest.stat().st_size <= MAX_THUMB:
            return dest
    raise ValueError("the cover is over YouTube's 2 MB even as a JPEG")


# ------------------------------------------------------------------ the upload copy
def tool(args: list[str], work: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Host ffmpeg/ffprobe when installed, else the docker image (work mounted at the same path)."""
    if shutil.which(args[0]):
        return run(["nice", "-n", "10", *args], timeout=timeout)
    return run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{work}:{work}",
                "--entrypoint", args[0], FFMPEG_IMAGE, *args[1:]], timeout=timeout)


def duration_s(path: Path, work: Path) -> float:
    r = tool(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], work)
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        raise RuntimeError("ffprobe could not read the video") from None


def has_audio(path: Path, work: Path) -> bool:
    r = tool(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
              str(path)], work)
    return bool(r.stdout.strip())


def make_upload_copy(src: Path, dest: Path, work: Path) -> float:
    """1080x1920 H.264 High at about 5.5 Mbit/s (less when a long reel would pass the cap), 30 fps,
    yuv420p, AAC 160k 48 kHz, faststart. Returns the duration."""
    dur = duration_s(src, work)
    if not 1 <= dur <= 180:
        raise ValueError(f"a Short is 1-180 s, this is {dur:.0f} s")
    kbps = min(5500, int(UPLOAD_CAP * 8 * 0.9 / dur / 1000) - 160)
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1")
    audio = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"] if has_audio(src, work) else ["-an"]
    r = tool(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
              "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-threads", "4",
              "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.1)}k", "-bufsize", f"{kbps * 2}k", "-g", "60",
              *audio, "-movflags", "+faststart", str(dest)], work, timeout=1200)
    if r.returncode or not dest.is_file():
        raise RuntimeError(f"ffmpeg: {tail(r.stderr)}")
    if dest.stat().st_size > UPLOAD_CAP:
        raise ValueError("the upload copy is over its cap")
    return dur


# ------------------------------------------------------------------ title and description
def clean(line: str) -> str:
    return re.sub(r"\s{2,}", " ", EMOJI.sub("", line)).strip(" -–—|:؛،.")


def lesson(slug: str) -> dict:
    """The article's front matter (title only is used), or {} when the site has no such lesson."""
    for d in (AUTO, ARTS):
        p = d / f"{slug}.md"
        if p.is_file():
            text = p.read_text("utf-8")
            m = re.search(r"^title:\s*(.+)$", text.split("\n---", 2)[0] if text.startswith("---") else "", re.M)
            return {"path": p, "title": (m.group(1).strip().strip("'\"") if m else "")}
    return {}


def make_title(caption: str, art: dict) -> str:
    first = next((clean(ln) for ln in caption.splitlines() if clean(ln) and not HASHTAG.fullmatch(ln.strip())), "")
    base = clean(art.get("title") or "") or first or "دات‌کوین"
    if len(base) > 90:
        base = base[:89].rsplit(" ", 1)[0].rstrip(" ،؛:") + "…"
    return f"{base} #Shorts"


def make_description(caption: str, slug: str | None) -> str:
    lines: list[str] = []
    for ln in caption.splitlines():
        s = ln.strip()
        if not s or HASHTAG.sub("", s).strip() == "" or DROP.search(s):
            continue
        lines.append(HASHTAG.sub("", s).strip())
        if len(lines) == 6:
            break
    links = ([f"مقاله‌ی کامل: {ARTICLE_URL.format(slug=slug)}"] if slug else []) + [f"اینستاگرام: {INSTAGRAM}"]
    tags: list[str] = []
    for t in HASHTAG.findall(caption) + BASE_TAGS:
        if t not in tags and t.lower() not in ("#shorts", "#reels"):
            tags.append(t)
    blocks = ["\n".join(lines), "\n".join(links), " ".join(tags[:5])]
    text = "\n\n".join(b for b in blocks if b)
    return text.replace("<", "").replace(">", "")[:4900]  # YouTube refuses angle brackets


# ------------------------------------------------------------------ egress (inside the hub's network)
# Runs in the worker (python -c): reads one JSON line (the job) then the video's raw bytes from stdin,
# streams the request body (the video base64-encoded in chunks: the worker never holds it whole)
# to egress's POST /v1/substitutes/web, and prints egress's answer.
CLIENT = r"""
import base64, json, os, sys, httpx
job = json.loads(sys.stdin.buffer.readline())
name = job.pop("file_name", None)
url = os.environ.get("SUPPORT_EGRESS_URL", "http://egress:8090").rstrip("/") + "/v1/substitutes/web"
def body():
    if not name:
        yield json.dumps(job).encode()
        return
    yield json.dumps(job)[:-1].encode() + b', "files": [{"name": ' + json.dumps(name).encode() + b', "b64": "'
    while True:
        chunk = sys.stdin.buffer.read(3 * 1024 * 1024)
        if not chunk:
            break
        yield base64.b64encode(chunk)
    yield b'"}]}'
try:
    r = httpx.post(url, content=body(), headers={"content-type": "application/json"}, timeout=job["timeout_s"] + 60)
    sys.stdout.write(r.text)
except httpx.HTTPError as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "off", "detail": type(e).__name__}))
"""


def egress(task: str, prompt: str, timeout_s: int, *, description: str | None = None,
           video: Path | None = None, visibility: str | None = None, video_id: str | None = None,
           file: Path | None = None, file_name: str | None = None) -> dict:
    """One job in the profile; `video` (an upload) or `file` (named `file_name`, e.g. a thumbnail) is
    the job's one file."""
    job: dict = {"account": PROFILE, "task": task, "prompt": prompt, "timeout_s": timeout_s}
    if description:
        job["description"] = description
    if visibility:
        job["visibility"] = visibility
    if video_id:
        job["video_id"] = video_id
    if video is not None:
        file, file_name = video, "dotcoin-short.mp4"
    if file is not None:
        job["file_name"] = file_name or file.name
    with tempfile.TemporaryFile() as stdin:
        stdin.write(json.dumps(job, ensure_ascii=False).encode() + b"\n")
        if file is not None:
            with open(file, "rb") as f:
                shutil.copyfileobj(f, stdin)
        stdin.seek(0)
        r = run(["docker", "exec", "-i", WORKER, "python", "-c", CLIENT], stdin=stdin, timeout=timeout_s + 120)
    try:
        out = json.loads(r.stdout.decode() or "{}")
    except ValueError:
        out = {}
    if not isinstance(out, dict) or "ok" not in out:
        return {"ok": False, "error": "off", "detail": f"no answer from egress ({tail(r.stderr, 1)})"}
    shot = out.pop("screenshot", None)
    if isinstance(shot, dict) and shot.get("b64"):  # for the SRE who fixes the recipe; never printed
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{task}.jpg"
        path.write_bytes(base64.b64decode(shot["b64"]))
        out["screenshot_file"] = str(path)
    return out


def why(ans: dict) -> str:
    extra = f" (screenshot {ans['screenshot_file']})" if ans.get("screenshot_file") else ""
    return f"{ans.get('error')}: {str(ans.get('detail') or '')[:160]} at step {ans.get('step')}{extra}"


def publish_step() -> int:
    """The index of the upload task's first step that may publish (the visibility choice); a job
    that failed at or after it is never retried."""
    try:
        text = RECIPE.read_text("utf-8")
    except OSError:
        return 0
    body = text.split("\n  upload:", 1)[-1]
    steps = [ln for ln in body.splitlines() if ln.strip().startswith("- {do:")]
    for i, ln in enumerate(steps):
        if "name='PUBLIC'" in ln and "do: click" in ln:
            return i
    return 0


def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("#Shorts", "")).strip()


# ------------------------------------------------------------------ the article's link
def set_field(text: str, key: str, value: str) -> str:
    end = text.index("\n---", 4)
    head, rest = text[:end], text[end:]
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    line = f"{key}: {value}".rstrip()
    head = pat.sub(lambda _: line, head, count=1) if pat.search(head) else f"{head}\n{line}"
    return head + rest


def link_article(slug: str, url: str) -> str:
    """'' when done (or nothing to do), else why not yet (tried again next run)."""
    art = lesson(slug)
    if not art:
        return "no article"
    with open(SYNC_LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "the site sync is running"
        path: Path = art["path"]
        text = path.read_text("utf-8")
        new = set_field(text, "youtube", url)
        if new != text:
            path.write_text(new, "utf-8")
            rel = str(path.relative_to(WT))
            for cmd in (["add", "--", rel], ["commit", "-q", "-m", f"DotCoin site: YouTube Short of {slug} (youtube.py)",
                                              "--", rel]):
                r = run(["git", "-C", str(WT), *cmd], timeout=60)
                if r.returncode:
                    return f"git {cmd[0]} failed: {tail(r.stderr, 1)}"
            log(f"{slug}: youtube link committed")
    # the site sync pushes the branch, builds and deploys (it takes its own lock)
    r = run([sys.executable, "-I", str(SITE / "sync.py")], timeout=1800, cwd=WT)
    for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines()[-4:]:
        log(f"  sync: {ln[:200]}")
    return "" if r.returncode == 0 else "the site sync failed"


# ------------------------------------------------------------------ one pass
def load_state() -> dict:
    try:
        s = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("uploads", {})
    return s


def save_state(s: dict) -> None:
    s["last_change"] = now()
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(STATE)


def sync_slugs() -> dict[str, str]:
    """The site sync's reel -> lesson map (`instagram:<work ref>` -> slug)."""
    try:
        src = json.loads(SYNC_STATE.read_text("utf-8")).get("sources") or {}
    except (OSError, ValueError):
        return {}
    return {k: str(v["slug"]) for k, v in src.items() if SLUG_RE.fullmatch(str(v.get("slug") or ""))}


def one(state: dict, row: dict, slugs: dict[str, str], dry: bool, unlisted: bool = False) -> None:
    source = f"instagram:{row['w']}"
    key = f"{CHANNEL}|{source}"
    up = state["uploads"].setdefault(key, {"source": source, "w": row["w"]}) if not dry else \
        dict(state["uploads"].get(key) or {})
    if up.get("status") in ("done", "unlisted", "exists", "check", "failed"):
        return
    other = next((k for k, u in state["uploads"].items() if k != key and u.get("sha") == row["sha"]), None)
    if other:
        up.update(status="exists", why=f"the same video as {other}", at=now())
        log(f"{row['w']}: skipped, the same video as {other}")
        return
    slug = slugs.get(source)
    art = lesson(slug) if slug else {}
    title = make_title(row.get("caption") or "", art)
    desc = make_description(row.get("caption") or "", slug if art else None)
    up.update(job=row["job"], chain=row.get("chain"), sha=row["sha"], instagram=row["url"], slug=slug if art else None,
              title=title)
    if dry:
        log(f"--- {key}\n{title}\n\n{desc}\n")
        return
    titles = egress("titles", "the channel's Shorts", 90)
    if not titles.get("ok"):
        if titles.get("error") == "expired":
            state["signed_out_at"] = now()
        log(f"{row['w']}: title check failed, tried again next run ({why(titles)})")
        return
    if norm_title(title) in norm_title(str(titles.get("text_md") or "")):
        up.update(status="exists", why="the channel has a video of this title", at=now())
        log(f"{row['w']}: the channel already has \"{title}\": not uploaded")
        return
    work = Path(tempfile.mkdtemp(prefix="dotcoin-yt-"))
    try:
        fetch(row, work / "in.mp4")
        make_upload_copy(work / "in.mp4", work / "short.mp4", work)
        size = (work / "short.mp4").stat().st_size
        log(f"{row['w']}: uploading \"{title}\" ({size / 1e6:.1f} MB)")
        up["tries"] = up.get("tries", 0) + 1
        up["tried_at"] = now()
        save_state(state)  # a crash from here on still counts the try
        ans = egress("upload", title, 600, description=desc, video=work / "short.mp4",
                     visibility="unlisted" if unlisted else "public")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    text = str(ans.get("text_md") or "")
    m = YT_URL.search(text)
    if ans.get("ok") and m:
        up.update(status="unlisted" if unlisted else "done", url=f"https://youtube.com/shorts/{m.group(1)}",
                  video_id=m.group(1), at=now())
        log(f"{row['w']}: uploaded{' (Unlisted)' if unlisted else ''} {up['url']}")
        return
    step = str(ans.get("step") or "")
    late = ans.get("ok") or (step.split(":", 1)[0].isdigit() and int(step.split(":", 1)[0]) >= publish_step())
    if ans.get("error") == "expired":
        state["signed_out_at"] = now()
    if late:
        up.update(status="check", why=f"may be published: {why(ans) if not ans.get('ok') else 'no link read'}", at=now())
        log(f"{row['w']}: CHECK the channel by hand, the upload may have gone out ({up['why']})")
    elif up["tries"] >= TRIES:
        up.update(status="failed", why=why(ans), at=now())
        log(f"{row['w']}: upload failed {TRIES} times, given up ({why(ans)})")
    else:
        log(f"{row['w']}: upload failed, tried again next run ({why(ans)})")


def make_public(state: dict, w: str) -> int:
    up = state["uploads"].get(f"{CHANNEL}|instagram:{w}") or {}
    if up.get("status") != "unlisted" or not up.get("video_id"):
        log(f"{w}: no Unlisted check upload in the state")
        return 1
    ans = egress("public", "public", 150, video_id=up["video_id"])
    if not ans.get("ok"):
        log(f"{w}: not made Public ({why(ans)})")
        return 1
    up.update(status="done", public_at=now())
    save_state(state)
    log(f"{w}: Public {up['url']}")
    return 0


# ------------------------------------------------------------------ the thumbnail (⟨2026-11-18⟩)
# The owner: a Short shows the same cover as its Instagram reel. Studio's own per-video custom
# thumbnail (task `thumbnail`: the reel's cover into the details page's thumbnail input, then Save;
# custom thumbnails are on since the channel's phone verification, 2026-11-17), set once the Short is
# up, on the same pass, and tried again on later passes at most THUMB_TRIES times. A Short uploaded
# before this (no `thumb_set` yet) gets its cover the same way: nothing is uploaded again.
# Seen on 2026-11-18 (TyYsNUfodio): Studio takes a custom picture for a Short, and the channel's
# Shorts tab then shows it whole, 9:16 (i.ytimg.com/vi/<id>/sardefault.jpg, not a frame's oarN.jpg).
# Any later page's Shorts uploader made from this file keeps this step (the owner's rule).
THUMB_TRIES = 3
# what the thumbnail area says when the channel may not set one (English and Persian Studio)
NO_THUMB = re.compile(r"verify|verification|not eligible|phone|تأیید|تایید|شماره(?:‌| )?ی? ?تلفن", re.I)


def thumb_due(up: dict) -> bool:
    return (up.get("status") in ("done", "unlisted") and bool(YT_ID.fullmatch(str(up.get("video_id") or "")))
            and up.get("thumb_set") not in ("yes", "none") and up.get("thumb_tries", 0) < THUMB_TRIES)


def set_thumbnail(state: dict, up: dict, row: dict) -> None:
    """The Short's custom thumbnail: its reel's own Instagram cover (`thumb_set` yes / no; `none`: the
    reel has no cover in the hub, YouTube's own frame stays)."""
    if not row.get("cover_key"):
        up.update(thumb_set="none", thumb_why="the reel has no cover in the hub", thumb_at=now())
        log(f"{row['w']}: the reel has no cover in the hub: YouTube's own frame stays")
        return
    up["thumb_tries"] = up.get("thumb_tries", 0) + 1
    save_state(state)  # a crash from here on still counts the try
    work = Path(tempfile.mkdtemp(prefix="dotcoin-yt-thumb-"))
    try:
        pic = cover_file(row, work)
        ans = egress("thumbnail", "thumbnail", 180, video_id=up["video_id"], file=pic,
                     file_name=f"{row['w']}-cover{pic.suffix}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if ans.get("error") in ("busy", "expired") or "the recipe has no" in str(ans.get("detail") or ""):
        up["thumb_tries"] -= 1  # not the page's answer: tried again next run, no try counted
        if ans.get("error") == "expired":
            state["signed_out_at"] = now()
        log(f"{row['w']}: thumbnail not set yet, tried again next run ({why(ans)})")
        return
    seen = f"{ans.get('text_md') or ''} {(ans.get('notes') or {}).get('thumbnail') or ''}".strip()
    ok = bool(ans.get("ok")) and not NO_THUMB.search(seen)
    up.update(thumb_set="yes" if ok else "no", thumb_sha=row.get("cover_sha"), thumb_at=now())
    if ok:
        up.pop("thumb_why", None)
        log(f"{row['w']}: thumbnail set (its Instagram cover) on {up.get('url')}")
    else:
        up["thumb_why"] = why(ans) if not ans.get("ok") else f"the thumbnail area said: {seen[:160]}"
        log(f"{row['w']}: thumbnail not set ({up['thumb_why']}; try {up['thumb_tries']} of {THUMB_TRIES})")


def one_pass(args) -> int:
    if args.make_public:
        return make_public(load_state(), args.make_public)
    if args.task:
        ans = egress(args.task, "read", 90)
        log(json.dumps({k: v for k, v in ans.items() if k != "file"}, ensure_ascii=False, indent=1))
        return 0 if ans.get("ok") else 1
    state = load_state()
    before = json.dumps(state, sort_keys=True)
    signed_out = state.get("signed_out_at")
    if signed_out and not args.dry_run and (datetime.now(timezone.utc) - datetime.fromisoformat(signed_out)
                                            ).total_seconds() < SIGNED_OUT_WAIT_S:
        return 0
    state.pop("signed_out_at", None)
    slugs = sync_slugs()
    rows = published_reels()
    for row in rows:
        if args.only and row["w"] != args.only:
            continue
        if state["uploads"].get(f"{CHANNEL}|instagram:{row['w']}", {}).get("status") in (
                "done", "unlisted", "exists", "check", "failed"):
            continue
        try:
            one(state, row, slugs, args.dry_run, unlisted=args.unlisted)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log(f"{row['w']}: {str(e)[:200]} (tried again next run)")
        if not args.dry_run and json.dumps(state, sort_keys=True) != before:
            save_state(state)
        if state.get("signed_out_at"):
            log("youtube-web is signed out: the owner signs in once with `make youtube-web-login`")
            break
    if args.dry_run:
        return 0
    # each uploaded Short's thumbnail: its reel's Instagram cover (⟨2026-11-18⟩, the owner)
    for row in rows:
        up = state["uploads"].get(f"{CHANNEL}|instagram:{row['w']}") or {}
        if (args.only and row["w"] != args.only) or not thumb_due(up) or state.get("signed_out_at"):
            continue
        try:
            set_thumbnail(state, up, row)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log(f"{row['w']}: thumbnail: {str(e)[:200]} (tried again next run)")
        save_state(state)
    # each uploaded Short's link on its article (tried again until it is there); ⟨2026-11-17⟩ a lesson
    # with a long video (youtube_long.py) keeps the long video's link
    long_slugs = {u.get("slug") for u in state["uploads"].values() if u.get("kind") == "long" and u.get("url")}
    for up in state["uploads"].values():
        if up.get("status") == "done" and up.get("slug") and up.get("site") != up.get("url"):
            if args.only and up.get("w") != args.only:
                continue
            if up.get("kind") != "long" and up.get("slug") in long_slugs:
                continue
            got = link_article(up["slug"], up["url"])
            if not got:
                up["site"] = up["url"]
            else:
                log(f"{up['slug']}: article link not set yet ({got})")
    if json.dumps(state, sort_keys=True) != before:
        save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--task", choices=("channel", "titles"))
    ap.add_argument("--only")
    ap.add_argument("--unlisted", action="store_true")
    ap.add_argument("--make-public", dest="make_public")
    args = ap.parse_args()
    if args.unlisted and not args.only:
        ap.error("--unlisted is a check upload of one reel: give --only W-…")
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
