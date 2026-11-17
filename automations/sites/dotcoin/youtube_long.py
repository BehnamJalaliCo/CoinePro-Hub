#!/usr/bin/env python3
"""DotCoin.me: one LONG video (16:9, 8-10 minutes, 3 a week) -> ONE upload on @DotCoin-me (stdlib + ffprobe).

The upload runs in the hub's signed-in browser profile `youtube-web` (YouTube Studio; egress recipe
infra/egress/recipes/youtube-web.yaml, task `upload_long`), never through the YouTube Data API (an
unaudited project's uploads are locked Private). By hand, never by a timer:
  1. checks the files without re-encoding them (ffprobe): the video MP4, H.264 1920x1080, AAC,
     60 s - 20 min, at most 1 GB; the thumbnail JPEG or PNG, 16:9, at most 2 MB; and meta.json;
  2. refuses a second upload: the key `youtube:@DotCoin-me|long:<slug>` already in the state, the
     same file (its sha256) already uploaded, or the title or the slug already in the channel's long
     videos in Studio (task `videos`: every visibility, drafts too);
  3. reads the channel's feature eligibility (task `features`): no custom thumbnails, no thumbnail
     sent;
  4. copies the video and the thumbnail into the profile browser's spool (docker exec, streamed,
     checked by sha256; a 300 MB video never travels base64 through two JSON hops) and runs ONE
     `upload_long` job through egress from inside the hub's network (docker exec into the worker,
     as youtube.py); the job's end removes the spooled files;
  5. records the video's link and whether the thumbnail was set (yes / no / unknown), then puts the
     link in the article's `youtube:` field in the content worktree (youtube.py's link_article: the
     site sync's lock, commit, push, build, deploy), when the article exists.

Never a duplicate, never retried by itself. A job that failed after its file went in leaves a
Private draft in Studio (state `failed`); one that may have passed the Done click without a link is
state `check` (a person looks in Studio). `--retry` runs either again, after the same duplicate check.
State: /home/Hub/sites/dotcoin-youtube.json (youtube.py's `uploads` map, `kind: long`), youtube.py's
lock (the 15-minute Shorts pass waits). If the profile is signed out the job answers `expired`: the
run stops, nobody signs in by itself (the owner: `make youtube-web-login`).

    youtube_long.py --features                        read only: the channel's feature eligibility
    youtube_long.py --videos                          read only: the channel's long videos in Studio
    youtube_long.py --video V.mp4 --thumb T.jpg --meta meta.json --unlisted [--dry-run] [--retry]
    youtube_long.py --video V.mp4 --thumb T.jpg --meta meta.json --public    (the owner's word only)
    youtube_long.py --make-public SLUG                an Unlisted long video made Public (owner's word only)
    youtube_long.py --link SLUG                       its link on the article, once the article exists
    youtube_long.py --due                             the automation's pass (dotcoin-longform.timer): each
                                                      queued run of the flow dotcoin_long at its hour, Public,
                                                      after its checks; then tags, language and subtitles
    youtube_long.py --finish SLUG                     only the tags, language and subtitles of one video

meta.json: {"slug": "what-is-bitcoin", "topic": "…", "title": "≤ 100 characters",
            "description": "≤ 5000 bytes, chapters as `00:00 …` lines", "tags": ["…", "…"],
            "category": "Education"}
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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube as Y  # noqa: E402  (the Shorts uploader: its state, lock, egress client and article link)

BROWSER = "coinepro-hq-browser-web-1"
SPOOL = "/profiles/.spool/" + Y.PROFILE  # browser_web.spool_dir(account), on the profiles' volume
TIMEOUT_S = 1500  # recipes.TASK_CAP_S["upload_long"]
MAX_VIDEO = 1024 * 1024 * 1024  # recipes.TASK_FILE_BYTES["upload_long"]
MAX_THUMB = 2 * 1024 * 1024  # YouTube's own cap for a custom thumbnail
DURATION_S = (60, 20 * 60)
OVER_15_MIN = 15 * 60  # longer needs the channel's intermediate features (phone verification)
TITLE_CHARS, DESCRIPTION_BYTES, TAG_CHARS = 100, 5000, 450  # YouTube: 100 chars, 5000 bytes, 500 tag chars
LOCK_WAIT_S = 600
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,11}")
SPOOL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")  # browser_web.SPOOL_NAME
VIDEO_URL = re.compile(
    r"https://(?:www\.)?(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|video/))([A-Za-z0-9_-]{11})")
CHAPTER = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+\S", re.M)
# what a thumbnail area says when the channel may not set one (English and Persian Studio)
NO_THUMB = re.compile(r"verify|verification|not eligible|phone|تأیید|تایید|شماره(?:‌| )?ی? ?تلفن", re.I)
DONE = ("unlisted", "done")  # an upload that went out (Unlisted, or Public)
# Put a spooled file: stdin -> <spool>/<name> (written as .<name>.part, then renamed), its sha256 printed.
PUT = r"""
import hashlib, os, sys
d, name, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.umask(0o077)
os.makedirs(d, mode=0o700, exist_ok=True)
part = os.path.join(d, "." + name + ".part")
h, n = hashlib.sha256(), 0
with open(part, "wb") as f:
    while True:
        b = sys.stdin.buffer.read(1 << 20)
        if not b or n + len(b) > size:
            n += len(b)
            break
        n += len(b)
        h.update(b)
        f.write(b)
if n != size:
    os.unlink(part)
    sys.exit("size %d, not %d" % (n, size))
os.replace(part, os.path.join(d, name))
print(h.hexdigest())
"""
DROP = r"""
import os, sys
d = sys.argv[1]
for name in sys.argv[2:]:
    for p in (os.path.join(d, name), os.path.join(d, "." + name + ".part")):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
"""

log = Y.log


def key_of(slug: str) -> str:
    return f"{Y.CHANNEL}|long:{slug}"


# ------------------------------------------------------------------ the files (read only)
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> dict:
    r = Y.tool(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
               path.parent, timeout=120)
    try:
        return json.loads(r.stdout.decode() or "{}")
    except ValueError:
        return {}


def check_video(path: Path) -> tuple[float, list[str]]:
    """Its duration and the warnings; a ValueError for what YouTube or this channel would refuse."""
    if not path.is_file() or path.suffix.lower() != ".mp4":
        raise ValueError(f"{path}: not an .mp4 file")
    size = path.stat().st_size
    if not 0 < size <= MAX_VIDEO:
        raise ValueError(f"{path.name}: {size / 1e6:.0f} MB, at most {MAX_VIDEO / 1e6:.0f} MB")
    info = probe(path)
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = info.get("format") or {}
    if v is None or "mp4" not in str(fmt.get("format_name") or ""):
        raise ValueError(f"{path.name}: ffprobe found no MP4 video stream")
    if v.get("codec_name") != "h264":
        raise ValueError(f"{path.name}: video codec {v.get('codec_name')}, not H.264")
    if (v.get("width"), v.get("height")) != (1920, 1080):
        raise ValueError(f"{path.name}: {v.get('width')}x{v.get('height')}, not 1920x1080 (16:9)")
    if str(v.get("sample_aspect_ratio") or "1:1") not in ("1:1", "0:1", "N/A"):
        raise ValueError(f"{path.name}: pixel aspect {v.get('sample_aspect_ratio')}, not square")
    if a is None or a.get("codec_name") != "aac":
        raise ValueError(f"{path.name}: audio {a.get('codec_name') if a else 'missing'}, not AAC")
    try:
        dur = float(fmt.get("duration") or v.get("duration") or 0)
    except ValueError:
        dur = 0.0
    if not DURATION_S[0] <= dur <= DURATION_S[1]:
        raise ValueError(f"{path.name}: {dur:.0f} s, a long video is {DURATION_S[0]}-{DURATION_S[1]} s")
    warn = []
    if v.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        warn.append(f"pixel format {v.get('pix_fmt')} (yuv420p is YouTube's)")
    if dur > OVER_15_MIN:
        warn.append("over 15 minutes: the channel needs intermediate features (phone verification)")
    return dur, warn


def check_thumb(path: Path) -> None:
    if not path.is_file() or path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise ValueError(f"{path}: the thumbnail is a .jpg or .png file")
    size = path.stat().st_size
    if not 0 < size <= MAX_THUMB:
        raise ValueError(f"{path.name}: {size / 1e6:.2f} MB, a thumbnail is at most 2 MB")
    v = next((s for s in probe(path).get("streams") or [] if s.get("codec_type") == "video"), None)
    if v is None or v.get("codec_name") not in ("mjpeg", "png"):
        raise ValueError(f"{path.name}: not a JPEG or PNG image")
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if w < 640 or not h or abs(w / h - 16 / 9) > 0.01:
        raise ValueError(f"{path.name}: {w}x{h}, a thumbnail is 16:9 and at least 640 wide (1280x720)")


def load_meta(path: Path, duration: float) -> tuple[dict, list[str]]:
    """The checked meta (slug, topic, title, description, tags, category) and the warnings."""
    try:
        m = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: not a JSON file ({e})") from None
    if not isinstance(m, dict):
        raise ValueError(f"{path}: not a JSON object")
    slug = str(m.get("slug") or "")
    if not SLUG_RE.fullmatch(slug) or len(slug) > 80:
        raise ValueError(f"slug {slug!r}: lowercase words joined by '-' (at most 80 characters)")
    title = re.sub(r"\s+", " ", str(m.get("title") or "")).strip()
    desc = str(m.get("description") or "").replace("\r\n", "\n").strip()
    if not title or len(title.encode("utf-16-le")) // 2 > TITLE_CHARS:
        raise ValueError(f"title: 1-{TITLE_CHARS} characters ({len(title)})")
    if not desc or len(desc.encode("utf-8")) > DESCRIPTION_BYTES:
        raise ValueError(f"description: 1-{DESCRIPTION_BYTES} bytes (UTF-8: {len(desc.encode('utf-8'))})")
    if any(c in title + desc for c in "<>"):
        raise ValueError("YouTube refuses < and > in a title or a description")
    if str(m.get("category") or "Education") != "Education":
        raise ValueError("category: only Education (the recipe sets Education)")
    warn: list[str] = []
    tags: list[str] = []
    used = 0
    for t in m.get("tags") or []:
        t = re.sub(r"\s+", " ", str(t)).strip().lstrip("#")
        if not t or "," in t or any(c in t for c in "<>") or t in tags:
            warn.append(f"tag {t!r} left out (empty, a comma, < >, or twice)")
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if tags else 0)  # YouTube counts a spaced tag's quotes
        if used + cost > TAG_CHARS:
            warn.append(f"tag {t!r} left out (the tags' {TAG_CHARS} characters are used)")
            continue
        tags.append(t)
        used += cost
    marks = [int(h or 0) * 3600 + int(mi) * 60 + int(s) for h, mi, s in CHAPTER.findall(desc)]
    if len(marks) < 3 or marks[0] != 0 or any(b - a < 10 for a, b in zip(marks, marks[1:])) \
            or marks[-1] >= duration:
        warn.append("chapters: YouTube shows them only from 00:00, at least 3, each 10 s or more, inside the video")
    topic = re.sub(r"\s+", " ", str(m.get("topic") or "")).strip()[:200]
    return {"slug": slug, "topic": topic, "title": title, "description": desc, "tags": tags,
            "category": "Education"}, warn


# ------------------------------------------------------------------ egress (inside the hub's network)
def call(job: dict) -> dict:
    """One job through egress (youtube.py's client in the worker); a failed step's screenshot is saved
    for the SRE, never printed."""
    with tempfile.TemporaryFile() as stdin:
        stdin.write(json.dumps(job, ensure_ascii=False).encode() + b"\n")
        stdin.seek(0)
        try:
            r = Y.run(["docker", "exec", "-i", Y.WORKER, "python", "-c", Y.CLIENT], stdin=stdin,
                      timeout=int(job["timeout_s"]) + 120)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "off", "detail": "no answer from egress in time"}
    try:
        out = json.loads(r.stdout.decode() or "{}")
    except ValueError:
        out = {}
    if not isinstance(out, dict) or "ok" not in out:
        return {"ok": False, "error": "off", "detail": f"no answer from egress ({Y.tail(r.stderr, 1)})"}
    shot = out.pop("screenshot", None)
    if isinstance(shot, dict) and shot.get("b64"):
        Y.SHOTS.mkdir(parents=True, exist_ok=True)
        path = Y.SHOTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{job['task']}.jpg"
        path.write_bytes(base64.b64decode(shot["b64"]))
        out["screenshot_file"] = str(path)
    return out


def read_task(task: str) -> dict:
    return call({"account": Y.PROFILE, "task": task, "prompt": "read", "timeout_s": 120})


def signed_out(ans: dict) -> bool:
    if ans.get("error") == "expired":
        log("youtube-web is signed out (`expired`): stopped. Nobody signs in by itself; the owner signs in "
            "once with `make youtube-web-login`.")
        return True
    return False


def thumbs_allowed(text: str) -> str:
    """yes / no / unknown: whether the channel may set custom thumbnails (YouTube: intermediate
    features, unlocked by phone verification), read from Studio's feature eligibility text."""
    t = re.sub(r"\s+", " ", text).lower()
    for start, end in (("intermediate features", "advanced features"), ("ویژگی‌های متوسط", "ویژگی‌های پیشرفته"),
                       ("ویژگی های متوسط", "ویژگی های پیشرفته")):
        i = t.find(start)
        if i < 0:
            continue
        part = t[i + len(start): t.find(end, i) if t.find(end, i) > i else i + 400]
        if re.search(r"verify phone|get access|eligible|تأیید|تایید|غیرفعال|واجد شرایط", part):
            return "no"
        if re.search(r"\benabled\b|فعال", part):
            return "yes"
    return "unknown"


# ------------------------------------------------------------------ the spool (browser-web's volume)
def spool_put(src: Path, name: str, sha: str) -> None:
    if not SPOOL_NAME.fullmatch(name):
        raise ValueError(f"not a spool name: {name}")
    with open(src, "rb") as f:
        r = Y.run(["docker", "exec", "-i", BROWSER, "python3", "-c", PUT, SPOOL, name, str(src.stat().st_size)],
                  stdin=f, timeout=900)
    got = r.stdout.decode().strip()
    if r.returncode or got != sha:
        raise RuntimeError(f"spool copy of {name} failed: {Y.tail(r.stderr, 1) or 'sha256 differs'}")


def spool_drop(names: list[str]) -> None:
    if names:
        Y.run(["docker", "exec", BROWSER, "python3", "-c", DROP, SPOOL, *names], timeout=60)


# ------------------------------------------------------------------ the recipe's steps (how far a job got)
def recipe_marks() -> tuple[int, int]:
    """(the upload_long step that puts the video in, the Done click): before the first nothing is on
    YouTube; before the second a Private draft at most; from it on the video may be out. (0, 0) when
    the recipe cannot be read: every failure is then a `check`."""
    try:
        text = Y.RECIPE.read_text("utf-8")
    except OSError:
        return 0, 0
    body = re.split(r"\n  upload_long:\n", text, maxsplit=1)
    if len(body) < 2:
        return 0, 0
    steps: list[str] = []
    for ln in body[1].splitlines():
        if re.match(r"^  [a-z_]+:\s*$", ln):
            break  # the next task
        if ln.strip().startswith("- {do:"):
            steps.append(ln)
    attach = next((i for i, ln in enumerate(steps) if "do: attach" in ln), None)
    done = next((i for i, ln in enumerate(steps) if "#done-button" in ln), None)
    return (attach, done) if attach is not None and done is not None and attach < done else (0, 0)


def step_index(ans: dict) -> int | None:
    head = str(ans.get("step") or "").split(":", 1)[0]
    return int(head) if head.isdigit() else None


# ------------------------------------------------------------------ one long upload
def lock_hub() -> IO[str]:
    """youtube.py's lock (the Shorts pass waits while a long video uploads), waited for a while."""
    Y.HOME.mkdir(parents=True, exist_ok=True)
    f = open(Y.LOCK, "w")  # noqa: SIM115 (held until the process ends)
    end = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.monotonic() > end:
                raise RuntimeError("youtube.py's pass holds the lock for over 10 minutes: try again later") from None
            time.sleep(5)


def upload(args) -> int:
    video, meta_file = Path(args.video).resolve(), Path(args.meta).resolve()
    thumb = Path(args.thumb).resolve() if args.thumb else None
    dur, warn = check_video(video)
    if thumb is not None:
        check_thumb(thumb)
    meta, more = load_meta(meta_file, dur)
    warn += more
    slug, key = meta["slug"], key_of(meta["slug"])
    sha = sha256(video)
    visibility = "public" if args.public else "unlisted"
    art = Y.lesson(slug)
    tags_text = ",".join(meta["tags"]) + "," if meta["tags"] else ""
    log(f"{key}\n  video {video.name}: {dur / 60:.1f} min, {video.stat().st_size / 1e6:.0f} MB, sha256 {sha[:16]}…"
        f"\n  thumbnail: {thumb.name if thumb else 'none'}\n  visibility: {visibility.upper()}"
        f"\n  title ({len(meta['title'])}): {meta['title']}\n  tags ({len(meta['tags'])}): {tags_text}"
        f"\n  article: {art['path'] if art else 'not there yet'}")
    for w in warn:
        log(f"  warning: {w}")
    state = Y.load_state()
    refused = local_duplicate(state, key, sha, args.retry)
    if args.dry_run:
        log(f"--- description ({len(meta['description'].encode('utf-8'))} bytes)\n{meta['description']}\n---")
        log(f"dry run: {'REFUSED: ' + refused if refused else 'the state allows it'}; the channel was not asked, "
            "nothing was copied or uploaded")
        return 1 if refused else 0
    if refused:
        log(f"refused: {refused}")
        return 1
    with lock_hub():
        state = Y.load_state()  # (again, under the lock)
        refused = local_duplicate(state, key, sha, args.retry)
        if refused:
            log(f"refused: {refused}")
            return 1
        feats = read_task("features")
        if signed_out(feats):
            return 2
        allowed = thumbs_allowed(str(feats.get("text_md") or "")) if feats.get("ok") else "unknown"
        state["long_features"] = {"at": Y.now(), "thumbnails": allowed,
                                  "text": str(feats.get("text_md") or Y.tail(json.dumps(feats).encode()))[:1500]}
        log(f"custom thumbnails allowed: {allowed}" + (" (no thumbnail sent)" if allowed == "no" and thumb else ""))
        if dur > OVER_15_MIN and allowed == "no":
            log("refused: over 15 minutes needs the channel's intermediate features (phone verification)")
            Y.save_state(state)
            return 1
        listed = read_task("videos")
        if signed_out(listed):
            Y.save_state(state)
            return 2
        if not listed.get("ok"):
            log(f"refused: the channel's long videos could not be read, so no duplicate check ({Y.why(listed)})")
            Y.save_state(state)
            return 1
        have = Y.norm_title(str(listed.get("text_md") or ""))
        if Y.norm_title(meta["title"]) in have or re.search(rf"(?<![a-z0-9-]){re.escape(slug)}(?![a-z0-9-])", have):
            up = state["uploads"].setdefault(key, {})
            up.update(kind="long", slug=slug, topic=meta["topic"], title=meta["title"], sha=sha, status="exists",
                      why="the channel's Studio list already has this title (or a draft named for the slug)", at=Y.now())
            Y.save_state(state)
            log(f"refused: the channel already has \"{meta['title']}\" (or a draft named {slug}): not uploaded")
            return 1
        # ⟨2026-11-17⟩ the channel is phone-verified: the thumbnail always goes (its step stays optional)
        send_thumb = thumb is not None
        names = [f"{slug}.mp4"] + ([f"{slug}-thumb{thumb.suffix.lower()}"] if send_thumb and thumb else [])
        up = state["uploads"].setdefault(key, {})
        up.update(kind="long", slug=slug, topic=meta["topic"], title=meta["title"], sha=sha, visibility=visibility,
                  file=video.name, duration_s=round(dur), status="uploading", thumb_set="unknown",
                  article=str(art["path"].relative_to(Y.WT)) if art else None)
        up["tries"] = up.get("tries", 0) + 1
        up["tried_at"] = Y.now()
        for k in ("why", "url", "video_id", "site", "notes", "skipped"):
            up.pop(k, None)
        try:
            spool_put(video, names[0], sha)
            if send_thumb and thumb is not None:
                spool_put(thumb, names[1], sha256(thumb))
            Y.save_state(state)  # a crash from here on still counts the try
            log(f"uploading {names[0]} ({video.stat().st_size / 1e6:.0f} MB) as {visibility.upper()}: up to "
                f"{TIMEOUT_S // 60} minutes")
            ans = call({"account": Y.PROFILE, "task": "upload_long", "prompt": meta["title"], "timeout_s": TIMEOUT_S,
                        "description": meta["description"], "visibility": visibility, "spooled": names,
                        **({"tags": tags_text} if tags_text else {})})
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as e:
            up.update(status="not_sent", why=str(e)[:200], at=Y.now())
            Y.save_state(state)
            log(f"not uploaded (nothing reached YouTube): {str(e)[:200]}")
            return 1
        finally:
            spool_drop(names)
        return settle(state, up, ans, send_thumb, allowed, visibility)


def local_duplicate(state: dict, key: str, sha: str, retry: bool) -> str:
    """Why the state refuses this upload ('' when it allows it)."""
    up = state["uploads"].get(key) or {}
    st = up.get("status")
    if st in DONE or st == "exists":
        return f"{key} is already {st} ({up.get('url') or up.get('why')})"
    if st in ("failed", "check", "uploading") and not retry:
        return (f"{key} is `{st}` ({up.get('why') or 'no answer'}): look in Studio first (a Private draft or the "
                "video itself may be there); then --retry runs it again after the channel's duplicate check")
    other = next((k for k, u in state["uploads"].items() if k != key and u.get("sha") == sha), None)
    if other:
        return f"the same video file was uploaded as {other}"
    return ""


def settle(state: dict, up: dict, ans: dict, sent_thumb: bool, allowed: str, visibility: str) -> int:
    text = str(ans.get("text_md") or "") + " " + str(ans.get("partial") or "")
    m = VIDEO_URL.search(text)
    notes = ans.get("notes") if isinstance(ans.get("notes"), dict) else {}
    skipped = [str(s) for s in ans.get("skipped") or []]
    up.update(notes={k: str(v)[:500] for k, v in notes.items()}, skipped=skipped[:20])
    attach_at, done_at = recipe_marks()
    if ans.get("ok") and m:
        thumb = "no"
        if sent_thumb and not any(s.endswith(":attach") for s in skipped):
            thumb = "no" if NO_THUMB.search(str(notes.get("thumbnail") or "")) else \
                {"yes": "yes", "no": "no"}.get(allowed, "unknown")
        url = f"https://youtu.be/{m.group(1)}"
        status = "done" if visibility == "public" else "unlisted"
        up.update(status=status, url=url, video_id=m.group(1), thumb_set=thumb, at=Y.now())
        Y.save_state(state)
        log(f"uploaded ({status.upper()}): {url}\n  thumbnail set: {thumb}"
            + (f" (the area said: {str(notes.get('thumbnail'))[:160]!r})" if notes.get("thumbnail") else ""))
        if notes.get("sent"):
            log(f"  upload: {notes['sent']}")
        if any(s.split(":", 1)[0].isdigit() and int(s.split(":", 1)[0]) > done_at for s in skipped) and done_at:
            log("  note: Studio's closing dialog was not seen; check in Studio that the video is not a draft")
        link(state, up)
        return 0
    idx = step_index(ans)
    err = str(ans.get("error") or "")
    nothing = err in ("busy", "unsupported") or (err == "off" and "no reviewed recipe" in str(ans.get("detail"))) \
        or (idx is not None and idx < attach_at)
    if nothing:
        status, why_ = "not_sent", f"nothing reached YouTube: {Y.why(ans)}"
    elif idx is not None and idx < done_at:
        status, why_ = "failed", f"a Private draft may be in Studio: {Y.why(ans)}"
    else:
        status = "check"
        why_ = f"may be out: {Y.why(ans) if not ans.get('ok') else 'no link read'}"
    if m:
        up.update(url=f"https://youtu.be/{m.group(1)}", video_id=m.group(1))
    up.update(status=status, why=why_[:300], at=Y.now())
    Y.save_state(state)
    if err == "expired":
        signed_out(ans)
    log(f"NOT uploaded: {status}: {why_}" + (f"\n  link read before it stopped: {up['url']}" if m else ""))
    if status == "check":
        log("  CHECK the channel in Studio by hand; this video is never uploaded again by itself")
    return 1


# ------------------------------------------------------------------ the article's link
def link(state: dict, up: dict) -> None:
    if not up.get("url") or up.get("site") == up.get("url"):
        return
    if not Y.lesson(up["slug"]):
        log(f"  the article {up['slug']} is not there yet: link it later with --link {up['slug']}")
        return
    got = Y.link_article(up["slug"], up["url"])
    if got:
        log(f"  article link not set yet ({got}): run --link {up['slug']} again")
        return
    up["site"] = up["url"]
    Y.save_state(state)
    log(f"  article {up['slug']}: youtube: {up['url']}")


def link_only(slug: str) -> int:
    with lock_hub():
        state = Y.load_state()
        up = state["uploads"].get(key_of(slug)) or {}
        if up.get("status") not in DONE or not up.get("url"):
            log(f"{slug}: no uploaded long video in the state")
            return 1
        link(state, up)
        return 0 if up.get("site") == up.get("url") else 1


def make_public(slug: str) -> int:
    with lock_hub():
        state = Y.load_state()
        up = state["uploads"].get(key_of(slug)) or {}
        if up.get("status") != "unlisted" or not up.get("video_id"):
            log(f"{slug}: no Unlisted long video in the state")
            return 1
        ans = call({"account": Y.PROFILE, "task": "public", "prompt": "public", "timeout_s": 150,
                    "video_id": up["video_id"]})
        if not ans.get("ok"):
            signed_out(ans)
            log(f"{slug}: not made Public ({Y.why(ans)})")
            return 1
        up.update(status="done", visibility="public", public_at=Y.now())
        Y.save_state(state)
        log(f"{slug}: Public {up['url']}")
        return 0


def show(task: str) -> int:
    with lock_hub():
        ans = read_task(task)
    if signed_out(ans):
        return 2
    log(json.dumps({k: v for k, v in ans.items() if k != "file"}, ensure_ascii=False, indent=1))
    if task == "features" and ans.get("ok"):
        log(f"custom thumbnails allowed: {thumbs_allowed(str(ans.get('text_md') or ''))}")
    return 0 if ans.get("ok") else 1

# ------------------------------------------------------------------ the automation (dotcoin_long)
# ⟨2026-11-17⟩ The owner: long videos fully automatic. The hub's flow `dotcoin_long` (kind video) makes
# a day's video on the workshop and marks its run `youtube: queued` when out/ is in (flows._queue_video).
# This pass (dotcoin-longform.timer, every 10 minutes, user Hub) publishes each such run at its hour:
# its files from the session's out/, three checks (the audio has no click, cut or burst; the article
# passes sync.py --check AND the site build with its bidi lint; nothing of it is on the channel or the
# site yet), ONE Public upload (the key, the sha256, the channel's list), the article on the site with
# the video in it (content/auto, the sync deploys it), then the video's tags, language and subtitles
# (tasks `details`, `subtitles`; tried again on later passes, at most FINISH_TRIES times).
WORKSPACE = Path("/home/studio/hq-workspace")
STUDIO_PY = "/home/studio/kits/prochart-reels/asr/venv/bin/python"
AUDIO_QC = "/home/studio/kits/prochart-reels/tools/audio_qc.py"
QC_DIR = Path("/home/studio/longform-qc")  # the studio user's (sudo -n -u studio)
TMP = Y.HOME / "longform-tmp"
DUE_LOCK = Y.HOME / "dotcoin-longform.lock"
OUT_FILES = ("video.mp4", "thumbnail.jpg", "meta.json", "subtitles.fa.srt", "article.md")
FINISH_TRIES = 3
REF_RE = re.compile(r"W-\d{3,9}")
DUE_SQL = """
    SELECT w.ref, w.run_meta -> 'flow' ->> 'key' AS key, w.run_meta -> 'flow' ->> 'day' AS day,
           w.run_meta -> 'flow' ->> 'publish_at' AS publish_at
      FROM work.work w
     WHERE w.run_meta -> 'flow' ->> 'kind' = 'video' AND w.run_meta -> 'flow' ->> 'account' = 'dotcoin.me'
       AND w.run_meta -> 'flow' ? 'sent' AND (w.run_meta -> 'flow' ->> 'publish_at')::timestamptz <= now()
       AND w.created_at > now() - interval '14 days'
     ORDER BY w.created_at"""


def sudo(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return Y.run(["sudo", "-n", *cmd], timeout=timeout)


def fetch_out(ref: str, dest: Path) -> list[str]:
    """The run's out/ files (read with sudo: the workshop is the studio user's) into `dest`; what is
    missing."""
    dest.mkdir(parents=True, exist_ok=True)
    missing = []
    for name in OUT_FILES:
        src = WORKSPACE / ref / "out" / name
        if sudo(["test", "-f", str(src)]).returncode:
            missing.append(name)
            continue
        r = sudo(["cp", str(src), str(dest / name)])
        sudo(["chown", f"{os.getuid()}:{os.getgid()}", str(dest / name)])
        if r.returncode:
            missing.append(name)
    return missing


def audio_clean(ref: str) -> str:
    """'' when the video's own soundtrack has 0 clicks, 0 cuts and 0 bursts (the kit's audio_qc.py, as
    the studio user), else why not."""
    sudo(["-u", "studio", "mkdir", "-p", str(QC_DIR)])
    wav = QC_DIR / f"{ref}.wav"
    r = sudo(["-u", "studio", "ffmpeg", "-v", "error", "-y", "-i", str(WORKSPACE / ref / "out" / "video.mp4"), "-vn",
              "-ac", "2", "-ar", "48000", str(wav)], timeout=600)
    if r.returncode:
        return f"the soundtrack could not be read ({Y.tail(r.stderr, 1)})"
    r = sudo(["-u", "studio", STUDIO_PY, "-I", AUDIO_QC, str(wav), str(QC_DIR / f"{ref}.audioqc.json")], timeout=900)
    sudo(["-u", "studio", "rm", "-f", str(wav)])
    try:
        got = json.loads((r.stdout or b"").decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return f"audio_qc gave no answer ({Y.tail(r.stderr, 1)})"
    n = {k: int(got.get(k) or 0) for k in ("clicks", "cuts", "bursts")}
    return "" if not any(n.values()) else f"audio_qc: {n['clicks']} clicks, {n['cuts']} cuts, {n['bursts']} bursts"


def article_ok(article: Path, slug: str) -> str:
    """'' when the article passes sync.py --check and the whole site builds with it (bidi lint), else why."""
    r = Y.run([sys.executable, "-I", str(Y.SITE / "sync.py"), "--check", str(article)], timeout=120)
    if r.returncode or "ok" not in (r.stdout or b"").decode():
        return f"sync.py --check: {Y.tail(r.stdout or r.stderr, 3)}"
    if (Y.ARTS / f"{slug}.md").exists() or (Y.AUTO / f"{slug}.md").exists():
        return f"the site already has a lesson {slug}"
    with tempfile.TemporaryDirectory(prefix="dotcoin-lint-", dir=str(TMP)) as tmp:
        # the repo's layout (build.py reads the reel kit's ideas next to it): the site copied, the kits linked
        site = Path(tmp) / "automations" / "sites" / "dotcoin"
        shutil.copytree(Y.SITE, site, ignore=shutil.ignore_patterns("dist", "__pycache__"))
        (Path(tmp) / "automations" / "kits").symlink_to(Y.WT / "automations" / "kits")
        (site / "content" / "auto" / f"{slug}.md").write_text(
            set_youtube(article.read_text("utf-8"), "https://youtu.be/AAAAAAAAAAA"), "utf-8")
        env = {**os.environ, "DOTCOIN_DIST": str(Path(tmp) / "dist")}
        r = Y.run([sys.executable, "-I", str(site / "build.py")], timeout=600, cwd=site, env=env)
    if r.returncode:
        return f"the site build refused it: {Y.tail(r.stderr or r.stdout, 4)}"
    return ""


def set_youtube(text: str, url: str) -> str:
    if not text.startswith("---"):
        return text
    return Y.set_field(text, "youtube", url)


TOPICS = Path("/home/studio/kits/dotcoin-longform/topics.md")  # the workshop's copy of the kit's bank


def mark_topic(slug: str, day: str) -> str:
    """The bank's row of this slug marked `used:<day>` in the workshop's topics.md (as the studio user),
    so the next day's session takes the next one ('' when done). The sitemap rule keeps it used even if
    the kit is synced again from git before the row is marked there."""
    code = ("import re,sys;p,slug,day=sys.argv[1:4];s=open(p,encoding='utf-8').read();"
            "n=re.sub(r'(\\|\\s*\\d+\\s*\\|\\s*)free(\\s*\\|\\s*`'+re.escape(slug)+'`)',"
            "lambda m:m.group(1)+'used:'+day+m.group(2),s,count=1);"
            "open(p,'w',encoding='utf-8').write(n);print('marked' if n!=s else 'not found')")
    r = sudo(["-u", "studio", sys.executable, "-I", "-c", code, str(TOPICS), slug, day], timeout=30)
    out = (r.stdout or b"").decode().strip()
    return "" if out == "marked" else f"topics.md: {out or Y.tail(r.stderr, 1)}"


def put_article(article: Path, slug: str, url: str) -> str:
    """The article into the site (content/auto/<slug>.md, its video in it), committed under the sync's
    lock; then the sync pushes, builds and deploys. '' when done."""
    dest = Y.AUTO / f"{slug}.md"
    with open(Y.SYNC_LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(set_youtube(article.read_text("utf-8"), url), "utf-8")
            rel = str(dest.relative_to(Y.WT))
            for cmd in (["add", "--", rel], ["commit", "-q", "-m", f"DotCoin site: lesson {slug} with its long video "
                                                                  f"{url} (youtube_long.py --due)", "--", rel]):
                r = Y.run(["git", "-C", str(Y.WT), *cmd], timeout=60)
                if r.returncode:
                    return f"git {cmd[0]} failed: {Y.tail(r.stderr, 1)}"
    r = Y.run([sys.executable, "-I", str(Y.SITE / "sync.py")], timeout=1800, cwd=Y.WT)
    return "" if r.returncode == 0 else f"the site sync failed: {Y.tail(r.stdout or r.stderr, 2)}"


def task_live(task: str) -> bool:
    """Whether the live recipe (the file egress reads) has this task: one not deployed yet is waited
    for, no try counted."""
    try:
        return f"\n  {task}:\n" in Y.RECIPE.read_text("utf-8")
    except OSError:
        return False


def not_live(ans: dict) -> bool:
    return not ans.get("ok") and "the recipe has no" in str(ans.get("detail") or "")


def finish(state: dict, up: dict) -> None:
    """The uploaded video's tags and language (task `details`), then its subtitles (task `subtitles`,
    the .srt spooled); each tried again on a later pass, at most FINISH_TRIES times."""
    vid = up.get("video_id")
    if not vid:
        return
    pic = Path(str(up.get("thumb") or ""))
    if (up.get("thumb_set") != "yes" and up.get("thumb_tries", 0) < FINISH_TRIES and pic.is_file()
            and task_live("thumbnail")):
        up["thumb_tries"] = up.get("thumb_tries", 0) + 1
        name = f"{up['slug']}-thumb{pic.suffix.lower()}"
        try:
            spool_put(pic, name, sha256(pic))
            ans = call({"account": Y.PROFILE, "task": "thumbnail", "prompt": "thumbnail", "timeout_s": 180,
                        "video_id": vid, "spooled": [name]})
        finally:
            spool_drop([name])
        seen = str(ans.get("text_md") or "") + " " + str((ans.get("notes") or {}).get("thumbnail") or "")
        up.update(thumb_set="yes" if ans.get("ok") and not NO_THUMB.search(seen) else "no",
                  thumb_why=Y.why(ans) if not ans.get("ok") else seen[:200], thumb_at=Y.now())
        Y.save_state(state)
        log(f"  {up['slug']}: thumbnail {up['thumb_set']}" + (f": {up['thumb_why']}" if up["thumb_set"] != "yes" else ""))
        if signed_out(ans):
            return
    if up.get("tags_saved") != "yes" and up.get("tag_tries", 0) < FINISH_TRIES and up.get("tags") and task_live("details"):
        up["tag_tries"] = up.get("tag_tries", 0) + 1
        ans = call({"account": Y.PROFILE, "task": "details", "prompt": "details", "timeout_s": 240, "video_id": vid,
                    "tags": ",".join(up["tags"]) + ","})
        if not_live(ans):
            up["tag_tries"] -= 1
            log(f"  {up['slug']}: tags wait for the recipe's `details` task to be deployed")
            return
        shown = str(ans.get("text_md") or "") + " " + str((ans.get("notes") or {}).get("tags") or "")
        kept = sum(1 for t in up["tags"] if t in shown)
        up.update(tags_saved="yes" if ans.get("ok") and kept >= max(1, len(up["tags"]) // 2) else "no",
                  tags_seen=kept, tags_why=Y.why(ans) if not ans.get("ok") else "", tags_at=Y.now())
        Y.save_state(state)
        log(f"  {up['slug']}: tags {up['tags_saved']} ({kept} of {len(up['tags'])} seen)"
            + (f": {up['tags_why']}" if up["tags_why"] else ""))
        if signed_out(ans):
            return
    srt = Path(str(up.get("srt") or ""))
    if up.get("subs") != "yes" and up.get("sub_tries", 0) < FINISH_TRIES and srt.is_file() and task_live("subtitles"):
        up["sub_tries"] = up.get("sub_tries", 0) + 1
        name = f"{up['slug']}.fa.srt"
        try:
            spool_put(srt, name, sha256(srt))
            ans = call({"account": Y.PROFILE, "task": "subtitles", "prompt": "subtitles", "timeout_s": 300,
                        "video_id": vid, "spooled": [name]})
        finally:
            spool_drop([name])
        if not_live(ans):
            up["sub_tries"] -= 1
            log(f"  {up['slug']}: subtitles wait for the recipe's `subtitles` task to be deployed")
            return
        up.update(subs="yes" if ans.get("ok") else "no", subs_why=Y.why(ans) if not ans.get("ok") else "",
                  subs_seen=str(ans.get("text_md") or "")[:200], subs_at=Y.now())
        Y.save_state(state)
        log(f"  {up['slug']}: subtitles {up['subs']}" + (f": {up['subs_why']}" if up["subs_why"] else ""))
        signed_out(ans)


def due_pass(only_finish: str | None = None) -> int:
    """One pass of the timer: every queued run whose hour has come, then the finishing of every long
    video still missing its tags or subtitles. Quiet when there is nothing to do."""
    TMP.mkdir(parents=True, exist_ok=True)
    with open(DUE_LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state = Y.load_state()
        runs = state.setdefault("long_runs", {})
        rows = [] if only_finish else [r for r in Y.sql(DUE_SQL) if REF_RE.fullmatch(str(r.get("ref") or ""))]
        for row in rows:
            ref = row["ref"]
            run = runs.setdefault(ref, {"key": row["key"], "day": row["day"], "publish_at": row["publish_at"]})
            if run.get("status") in ("done", "blocked", "check"):
                continue
            work = TMP / ref
            missing = fetch_out(ref, work)
            if missing:
                run.update(status="waiting", why=f"out/ lacks {', '.join(missing)}", at=Y.now())
                Y.save_state(state)
                log(f"{ref}: waiting: out/ lacks {', '.join(missing)}")
                continue
            meta = json.loads((work / "meta.json").read_text("utf-8"))
            slug = str(meta.get("slug") or "")
            why = audio_clean(ref) or article_ok(work / "article.md", slug)
            if why:
                run.update(status="blocked", slug=slug, why=why[:400], at=Y.now())
                Y.save_state(state)
                log(f"{ref}: BLOCKED, not uploaded: {why[:300]}")
                continue
            log(f"{ref}: checks passed (audio 0/0/0, article and site build ok): uploading {slug} Public")
            rc = upload(argparse.Namespace(video=str(work / "video.mp4"), thumb=str(work / "thumbnail.jpg"),
                                           meta=str(work / "meta.json"), public=True, unlisted=False,
                                           dry_run=False, retry=False))
            state = Y.load_state()  # (upload() saved it)
            runs = state.setdefault("long_runs", {})
            run = runs[ref]
            up = state["uploads"].get(key_of(slug)) or {}
            if rc != 0 or not up.get("url"):
                run.update(status="check" if up.get("status") == "check" else "blocked", slug=slug,
                           why=f"the upload did not finish: {up.get('status')} {up.get('why') or ''}"[:400], at=Y.now())
                Y.save_state(state)
                continue
            keep = Y.HOME / "dotcoin-longform" / f"{row['day']}-{slug}"
            keep.mkdir(parents=True, exist_ok=True)
            for name in ("subtitles.fa.srt", "article.md", "meta.json", "thumbnail.jpg"):
                shutil.copy2(work / name, keep / name)
            up.update(srt=str(keep / "subtitles.fa.srt"), thumb=str(keep / "thumbnail.jpg"),
                      tags=list(meta.get("tags") or []), run=ref)
            got = put_article(keep / "article.md", slug, up["url"])
            up["site"] = up["url"] if not got else up.get("site")
            marked = mark_topic(slug, str(row["day"]))
            run.update(status="done", slug=slug, url=up["url"], article=got or "live", topic=marked or "used",
                       at=Y.now())
            Y.save_state(state)
            log(f"{ref}: Public {up['url']}; article: {got or 'on the site'}")
            shutil.rmtree(work, ignore_errors=True)
        todo = [u for u in state["uploads"].values() if u.get("kind") == "long" and u.get("status") in DONE
                and (not only_finish or u.get("slug") == only_finish)]
        if any(u.get("tags_saved") != "yes" or u.get("subs") != "yes" or u.get("thumb_set") != "yes" for u in todo):
            with lock_hub():
                state = Y.load_state()
                for u in state["uploads"].values():
                    if u.get("kind") == "long" and u.get("status") in DONE and (not only_finish or u.get("slug") == only_finish):
                        finish(state, u)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--features", action="store_true")
    ap.add_argument("--videos", action="store_true")
    ap.add_argument("--video")
    ap.add_argument("--thumb")
    ap.add_argument("--meta")
    vis = ap.add_mutually_exclusive_group()
    vis.add_argument("--unlisted", action="store_true")
    vis.add_argument("--public", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--make-public", dest="make_public")
    ap.add_argument("--link")
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--finish")
    args = ap.parse_args()
    try:
        if args.due or args.finish:
            return due_pass(args.finish)
        if args.features or args.videos:
            return show("features" if args.features else "videos")
        if args.make_public:
            return make_public(args.make_public)
        if args.link:
            return link_only(args.link)
        if not (args.video and args.meta):
            ap.error("an upload needs --video and --meta (and --thumb)")
        if not (args.unlisted or args.public or args.dry_run):
            ap.error("say the visibility: --unlisted (or --public, the owner's word only)")
        return upload(args)
    except ValueError as e:
        log(f"refused: {e}")
        return 1
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        log(f"error: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
