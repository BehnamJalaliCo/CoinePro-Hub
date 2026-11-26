#!/usr/bin/env python3
"""@behnamjalali.tech: each reel published on Instagram -> ONE public YouTube Short on @behnamjalali-tech, its
thumbnail the reel's own Instagram cover (stdlib + ffprobe/ffmpeg).

The owner (2026-11-19): every reel of the page also goes to the page's YouTube channel as a Short, with its
Instagram cover as the Short's thumbnail. A sibling of DotCoin's automations/sites/dotcoin/youtube.py (site commit
c3680b82) for the browser profile `youtube-bj` (the page's own Google account; recipe
infra/egress/recipes/youtube-bj.yaml), without the site steps. It shares youtube_long.py's lock (one profile, one
job at a time), its egress client, its spool into the profile browser and its channel guard.

One pass (bjtech-shorts.timer, every 15 minutes, user Hub):
  1. finds the page's reels published on Instagram (infra.server_jobs: kind publish, account behnamjalali.tech,
     kind reel, result.url set; the hub DB is only read) that the state lacks;
  2. THE CHANNEL GUARD (youtube_long.py's): uploads only while the profile's active channel is the page's
     (`youtube_channel_name` and `youtube_channel_handle` in automations/kits/bjtech-common/brand/config.json);
  3. reads the reel's video (docker exec, checked against its sha256); the original goes up as it is when YouTube
     takes it whole as a Short (H.264 yuv420p, 9:16, 1-180 s, at most 90 MB), else an upload copy (H.264 1080x1920
     about 5.5 Mbit/s, 30 fps, AAC, faststart);
  4. writes the Persian title (the caption's first line, <= 90 characters + " #Shorts") and the description (the
     caption without its Instagram call to action, the Telegram channel, the Instagram page, 3-5 hashtags; links
     from bjtech-common/brand/config.json only);
  5. refuses a second upload: its key and its video's sha256 (here and in the long videos' state), its title in the
     channel's Shorts (task `titles`); then ONE `upload` (Public), the file spooled into the profile browser;
  6. sets the Short's thumbnail to the reel's own Instagram cover (its publication's thumbnail in the hub, else the
     publish job's cover file; at most 2 MB, task `thumbnail`), on the same pass and on later passes (at most 3
     tries; `thumb_set` yes / no / none).

Never a duplicate and never a stray draft: one source -> one upload, keyed `youtube:@behnamjalali-tech|instagram:
<work ref>`, and one video file (its sha256) -> one upload. YouTube keeps a draft from the moment the file is
attached, so only an upload that failed before that step is tried again (at most 3 times); any later failure is
state `check` (a person looks in Studio), never retried by itself. State: /home/Hub/sites/bjtech-shorts.json (600).
An idle pass reads one query, logs nothing and exits. Never prints a cookie or a token (a failed step's screenshot
is kept in /home/Hub/sites/bjtech-youtube-shots for the SRE).

    youtube.py                      one pass (the timer)
    youtube.py --dry-run            find, check, build the title and description and print them; no profile job
    youtube.py --only W-000635      limit the pass to one reel
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _long():
    """youtube_long.py of this directory (the lock, the egress client, the spool, the channel guard)."""
    spec = importlib.util.spec_from_file_location("bj_youtube_long", Path(__file__).with_name("youtube_long.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("youtube_long.py not found beside youtube.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _long()

HOME, LOCK, SHOTS = L.HOME, L.LOCK, L.SHOTS
STATE, LONG_STATE = HOME / "bjtech-shorts.json", L.STATE
API, PROFILE = "coinepro-hq-api-1", L.PROFILE
ACCOUNT, CHANNEL = "behnamjalali.tech", "youtube:@behnamjalali-tech"
RECIPE = L.REPO / "infra" / "egress" / "recipes" / "youtube-bj.yaml"
FFMPEG_IMAGE = "jrottenberg/ffmpeg:7.1-alpine"
MAX_VIDEO = 300 * 1024 * 1024  # a reel's original (read limit)
UPLOAD_CAP = 90 * 1024 * 1024  # under egress's upload cap (recipes.TASK_FILE_BYTES["upload"], 96 MB)
MAX_COVER = 25 * 1024 * 1024  # a reel's cover (read limit)
MAX_THUMB = 2 * 1024 * 1024  # YouTube's own cap for a custom thumbnail
TRIES, THUMB_TRIES = 3, 3
# the custom thumbnail, checked on YouTube's public side (Studio's answer once said «saved» for a Short whose
# custom picture never took, W-000651 2026-11-19): YouTube serves a Short's custom picture as sardefault.jpg
VERIFY_AFTER, VERIFY_GIVE_UP = timedelta(minutes=10), timedelta(minutes=40)
PUBLIC_THUMB = "https://i.ytimg.com/vi/{id}/sardefault.jpg"
SIGNED_OUT_WAIT_S = 2 * 3600  # a signed-out profile: tried again after this
TERMINAL = ("done", "exists", "check", "failed")

WS_RE = re.compile(r"W-\d{3,9}")
KEY_RE = re.compile(r"[0-9a-f]{16,64}")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
IG_URL = re.compile(r"https://www\.instagram\.com/\S{3,200}")
YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
# pictographs, dingbats, variation selectors and the zero-width joiner (never in a title)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")
HASHTAG = re.compile(r"#[^\s#]{2,40}")
# an Instagram call to action: never in the description
DROP = re.compile(r"کامنت|فالو|دایرکت|بیو|لایک|سیو|ذخیره کن|شیر کن|@|follow|comment|link in bio", re.I)
# a link or the caption's own line about the Telegram channel (the description gives its links once)
LINKED = re.compile(r"https?://|t\.me/|تلگرام|telegram", re.I)
BASE_TAGS = ["#هوش_مصنوعی", "#تکنولوژی", "#AI"]
# what the thumbnail area says when the channel may not set one (English and Persian Studio)
NO_THUMB = re.compile(r"verify|verification|not eligible|phone|تأیید|تایید|شماره(?:‌| )?ی? ?تلفن", re.I)

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
      -- the reel's Instagram cover (the Short's thumbnail): its publication's thumbnail (media.publications,
      -- the chain that holds this job), else the chain's publish job's cover file
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


def log(msg: str) -> None:
    L.log(msg)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the hub (read only)
def published_reels() -> list[dict]:
    return [r for r in L.sql(REELS_SQL) if WS_RE.fullmatch(str(r.get("w") or ""))
            and UUID_RE.fullmatch(str(r.get("video") or "")) and IG_URL.fullmatch(str(r.get("url") or ""))]


def read_file(key: str, sha: str | None, size: int, cap: int, dest: Path) -> None:
    """A file of the hub's storage (docker exec) into `dest`, checked against its sha256."""
    key = str(key)
    if not KEY_RE.fullmatch(key) or not 0 < int(size) <= cap:
        raise ValueError("unexpected storage key or size")
    with open(dest, "wb") as out:
        r = subprocess.run(["docker", "exec", API, "cat", f"/data/files/{key[:2]}/{key}"], stdout=out,
                           stderr=subprocess.PIPE, timeout=300)
    if r.returncode:
        raise RuntimeError(f"read failed: {L.tail(r.stderr, 1)}")
    if sha and L.sha256(dest) != sha:
        raise ValueError("sha256 mismatch")


# ------------------------------------------------------------------ the video and the cover
def tool(args: list[str], work: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Host ffmpeg/ffprobe when installed, else the docker image (work mounted at the same path)."""
    if shutil.which(args[0]):
        return L.run(["nice", "-n", "10", *args], timeout=timeout)
    return L.run(["docker", "run", "--rm", "-v", f"{work}:{work}", "--entrypoint", args[0], FFMPEG_IMAGE,
                  *args[1:]], timeout=timeout)


def probe(path: Path, work: Path) -> dict:
    r = tool(["ffprobe", "-v", "error", "-show_entries",
              "format=duration:stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate", "-of", "json", str(path)], work)
    try:
        return json.loads(r.stdout.decode() or "{}")
    except ValueError:
        return {}


def whole_short(info: dict, size: int) -> bool:
    """YouTube takes the reel's original whole as a Short (owner 2026-11-26: the highest quality, no second
    encode): H.264 yuv420p, 9:16, 1-180 s, at most UPLOAD_CAP."""
    v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    try:
        dur = float((info.get("format") or {}).get("duration") or 0)
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    except (TypeError, ValueError):
        return False
    return (v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p" and w > 0 and w * 16 == h * 9
            and 1 <= dur <= 180 and 0 < size <= UPLOAD_CAP)


def frame_rate(v: dict) -> float:
    try:
        a, _, b = str(v.get("r_frame_rate") or "30/1").partition("/")
        return float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


def make_upload_copy(src: Path, dest: Path, work: Path, info: dict) -> None:
    """Only when the original is not a Short as it is: 1080x1920 H.264 High CRF 16 at the reel's own frame rate
    (at most 60), BT.709, the VBV cap that keeps it under UPLOAD_CAP, AAC 192k 48 kHz stereo, faststart."""
    try:
        dur = float((info.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        raise RuntimeError("ffprobe could not read the video") from None
    if not 1 <= dur <= 180:
        raise ValueError(f"a Short is 1-180 s, this is {dur:.0f} s")
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in streams)
    kbps = max(2000, min(16000, int(UPLOAD_CAP * 8 * 0.92 / dur / 1000) - 192))
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos+accurate_rnd+full_chroma_int,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black," + ("fps=60," if frame_rate(v) > 60.5 else "")
          + "format=yuv420p,setsar=1")
    sound = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"] if audio else ["-an"]
    r = tool(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
              "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-profile:v", "high", "-threads", "4",
              "-maxrate", f"{kbps}k", "-bufsize", f"{kbps}k", "-x264-params", "aq-mode=3", "-color_primaries", "bt709",
              "-color_trc", "bt709", "-colorspace", "bt709", *sound, "-movflags", "+faststart", str(dest)],
             work, timeout=1500)
    if r.returncode or not dest.is_file():
        raise RuntimeError(f"ffmpeg: {L.tail(r.stderr)}")
    if dest.stat().st_size > UPLOAD_CAP:
        raise ValueError("the upload copy is over its cap")


def upload_file(row: dict, work: Path) -> Path:
    """The reel's original when YouTube takes it whole as a Short, else its upload copy."""
    src = work / "in.mp4"
    read_file(row["key"], row.get("sha"), row["size"], MAX_VIDEO, src)
    info = probe(src, work)
    if whole_short(info, src.stat().st_size):
        return src
    make_upload_copy(src, work / "short.mp4", work, info)
    return work / "short.mp4"


def cover_file(row: dict, work: Path) -> Path:
    """The reel's Instagram cover as the Short's thumbnail: the cover itself (a JPEG or PNG of at most 2 MB,
    YouTube's own cap), else a JPEG made from it (same picture, at most 1080 wide)."""
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
            raise RuntimeError(f"ffmpeg (cover): {L.tail(r.stderr)}")
        if dest.stat().st_size <= MAX_THUMB:
            return dest
    raise ValueError("the cover is over YouTube's 2 MB even as a JPEG")


# ------------------------------------------------------------------ title and description
def clean(line: str) -> str:
    return re.sub(r"\s{2,}", " ", EMOJI.sub("", line)).replace("<", "").replace(">", "").strip(" -–—|:؛،.•")


def make_title(caption: str) -> str:
    first = next((clean(ln) for ln in caption.splitlines()
                  if clean(HASHTAG.sub("", ln)) and not HASHTAG.fullmatch(ln.strip())), "")
    base = clean(HASHTAG.sub("", first)) or "هوش مصنوعی و تکنولوژی"
    if len(base) > 90:
        base = base[:89].rsplit(" ", 1)[0].rstrip(" ،؛:") + "…"
    return f"{base} #Shorts"


def make_description(caption: str, links: dict) -> str:
    lines: list[str] = []
    for ln in caption.splitlines():
        s = ln.strip()
        if not s or HASHTAG.sub("", s).strip() == "" or DROP.search(s) or LINKED.search(s):
            continue  # (a caption's own link lines: the description's link block says them once)
        lines.append(HASHTAG.sub("", s).strip())
        if len(lines) == 8:
            break
    out = []
    if links.get("telegram"):
        out.append(f"خبرهای روزانه‌ی هوش مصنوعی در کانال تلگرام: {links['telegram']}")
    if links.get("instagram"):
        out.append(f"اینستاگرام: {links['instagram']}")
    tags: list[str] = []
    for t in HASHTAG.findall(caption) + BASE_TAGS:
        if t not in tags and t.lower() not in ("#shorts", "#reels", "#reel"):
            tags.append(t)
    blocks = ["\n".join(lines), "\n".join(out), " ".join(tags[:5])]
    text = "\n\n".join(b for b in blocks if b)
    return text.replace("<", "").replace(">", "")[:4900]  # YouTube refuses angle brackets


def brand_links() -> dict:
    c = L.config()
    return {k: str(c.get(k) or "") for k in ("telegram", "instagram") if str(c.get(k) or "").startswith("https://")}


def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("#Shorts", "")).strip()


# ------------------------------------------------------------------ retry rule
def attach_step() -> int:
    """The index of the `upload` task's first attach step: from it on, YouTube keeps a draft."""
    try:
        text = RECIPE.read_text("utf-8")
    except OSError:
        return 0
    body = text.split("\n  upload:", 1)[-1]
    steps = [ln for ln in body.splitlines() if ln.strip().startswith("- {do:")]
    return next((i for i, ln in enumerate(steps) if "do: attach" in ln), 0)


def may_retry(ans: dict, first_attach: int) -> bool:
    """True when the upload surely stopped before its file reached YouTube (no draft); never after it."""
    err = str(ans.get("error") or "")
    if ans.get("ok"):
        return False
    if err in ("busy", "expired", "refused") or err.startswith("http_"):
        return True  # egress or the profile refused the job: nothing ran on the page
    if err == "off":
        return "in time" not in str(ans.get("detail") or "")  # no answer in time: it may have run
    head = str(ans.get("step") or "").split(":", 1)[0]
    return head.isdigit() and int(head) < first_attach


def why(ans: dict) -> str:
    extra = f" (screenshot {ans['screenshot_file']})" if ans.get("screenshot_file") else ""
    return f"{ans.get('error')}: {str(ans.get('detail') or '')[:160]} at step {ans.get('step')}{extra}"


# ------------------------------------------------------------------ state
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
    tmp.chmod(0o600)
    tmp.replace(STATE)


def long_shas() -> set[str]:
    """The long videos' sha256s (youtube_long.py's state, read only)."""
    try:
        ups = json.loads(LONG_STATE.read_text("utf-8")).get("uploads") or {}
    except (OSError, ValueError):
        return set()
    return {str(u.get("sha")) for u in ups.values() if isinstance(u, dict) and u.get("sha")}


# ------------------------------------------------------------------ the profile's jobs
def guard() -> str:
    """'' when the profile's active channel is the page's, else why not (nothing is uploaded blind)."""
    want, handle = L.channel_name(), L.channel_handle()
    if not want:
        return "no youtube_channel_name in bjtech-common/brand/config.json"
    active, ans = L.active_channel()
    if ans.get("error") == "expired":
        return "expired"
    switcher = str((ans.get("notes") or {}).get("channels") or "")
    if not ans.get("ok") or want not in active or (handle and handle not in switcher):
        return f"the active channel is not {want!r} {handle}: {active[:80]!r} ({ans.get('error') or 'ok'})"
    return ""


def upload_one(state: dict, row: dict, titles: str, first_attach: int) -> None:
    key = f"{CHANNEL}|instagram:{row['w']}"
    up = state["uploads"].setdefault(key, {"source": f"instagram:{row['w']}", "w": row["w"]})
    caption = row.get("caption") or ""
    title = make_title(caption)
    up.update(job=row["job"], chain=row.get("chain"), sha=row["sha"], instagram=row["url"], title=title)
    if norm_title(title) and norm_title(title) in norm_title(titles):
        up.update(status="exists", why="the channel has a Short of this title", at=now())
        log(f"{row['w']}: the channel already has \"{title}\": not uploaded")
        return
    desc = make_description(caption, brand_links())
    work = Path(tempfile.mkdtemp(prefix="bjtech-short-"))
    name = f"bjs-{str(row['sha'])[:16]}.mp4"
    try:
        video = upload_file(row, work)
        size = video.stat().st_size
        log(f"{row['w']}: uploading \"{title}\" ({size / 1e6:.1f} MB, {'original' if video.name == 'in.mp4' else 'copy'})")
        up["tries"] = up.get("tries", 0) + 1
        up["tried_at"] = now()
        save_state(state)  # a crash from here on still counts the try
        L.spool_put(video, name)
        ans = L.call({"account": PROFILE, "task": "upload", "prompt": title, "description": desc,
                      "visibility": "public", "spooled": [name], "timeout_s": 600})
    finally:
        L.spool_drop([name])
        shutil.rmtree(work, ignore_errors=True)
    m = L.VIDEO_URL.search(str(ans.get("text_md") or "") + " " + str(ans.get("partial") or ""))
    if ans.get("ok") and m:
        up.update(status="done", url=f"https://youtube.com/shorts/{m.group(1)}", video_id=m.group(1), at=now())
        up.pop("why", None)
        log(f"{row['w']}: uploaded Public {up['url']}")
        return
    if ans.get("error") == "expired":
        state["signed_out_at"] = now()
    if not may_retry(ans, first_attach):
        up.update(status="check", why=f"may be on YouTube as a draft or a Short: {why(ans)}", at=now())
        log(f"{row['w']}: CHECK Studio by hand, the upload got past its file ({up['why']})")
    elif up["tries"] >= TRIES:
        up.update(status="failed", why=why(ans), at=now())
        log(f"{row['w']}: upload failed {TRIES} times before its file went in, given up ({why(ans)})")
    else:
        up["why"] = why(ans)
        log(f"{row['w']}: upload failed before its file went in, tried again next run ({why(ans)})")


def thumb_due(up: dict) -> bool:
    return (up.get("status") == "done" and bool(YT_ID.fullmatch(str(up.get("video_id") or "")))
            and up.get("thumb_set") not in ("yes", "none") and up.get("thumb_tries", 0) < THUMB_TRIES)


def set_thumbnail(state: dict, up: dict, row: dict) -> None:
    """The Short's custom thumbnail: its reel's own Instagram cover (`thumb_set` yes / no; `none`: the reel has
    no cover in the hub, YouTube's own frame stays)."""
    if not row.get("cover_key"):
        up.update(thumb_set="none", thumb_why="the reel has no cover in the hub", thumb_at=now())
        log(f"{row['w']}: the reel has no cover in the hub: YouTube's own frame stays")
        return
    up["thumb_tries"] = up.get("thumb_tries", 0) + 1
    save_state(state)  # a crash from here on still counts the try
    work = Path(tempfile.mkdtemp(prefix="bjtech-short-thumb-"))
    name = ""
    try:
        pic = cover_file(row, work)
        name = f"bjs-{up['video_id']}-cover{pic.suffix}"
        L.spool_put(pic, name)
        ans = L.call({"account": PROFILE, "task": "thumbnail", "prompt": "thumbnail", "video_id": up["video_id"],
                      "spooled": [name], "timeout_s": 180})
    finally:
        if name:
            L.spool_drop([name])
        shutil.rmtree(work, ignore_errors=True)
    if ans.get("error") in ("busy", "expired", "refused") or str(ans.get("error") or "").startswith("http_"):
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


def public_thumb(video_id: str) -> bool | None:
    """True when YouTube serves the Short's custom thumbnail publicly, False when it does not (404), None when
    the check itself failed."""
    req = urllib.request.Request(PUBLIC_THUMB.format(id=video_id), method="HEAD",
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except (urllib.error.URLError, OSError):
        return None


def verify_thumbnail(up: dict) -> None:
    """A thumbnail Studio said it saved, checked on YouTube's public side: `thumb_verified` yes once it is
    there; still missing VERIFY_GIVE_UP after its Save, it is set again (thumb_set no, within THUMB_TRIES)."""
    if (up.get("status") != "done" or up.get("thumb_set") != "yes" or up.get("thumb_verified") == "yes"
            or not YT_ID.fullmatch(str(up.get("video_id") or "")) or not up.get("thumb_at")):
        return
    age = datetime.now(timezone.utc) - datetime.fromisoformat(str(up["thumb_at"]))
    if age < VERIFY_AFTER:
        return
    got = public_thumb(str(up["video_id"]))
    if got:
        up.update(thumb_verified="yes", thumb_verified_at=now())
        log(f"{up.get('w')}: its Instagram cover is the Short's public thumbnail ({up.get('url')})")
    elif got is False and age >= VERIFY_GIVE_UP:
        up.update(thumb_set="no", thumb_why=f"YouTube shows no custom thumbnail {int(age.total_seconds() // 60)} min "
                                            "after Studio said saved (sardefault.jpg 404): set again")
        log(f"{up.get('w')}: {up['thumb_why']}")


# ------------------------------------------------------------------ one pass
def one_pass(args) -> int:
    state = load_state()
    before = json.dumps(state, sort_keys=True)
    signed_out = state.get("signed_out_at")
    if signed_out and not args.dry_run and (datetime.now(timezone.utc) - datetime.fromisoformat(signed_out)
                                            ).total_seconds() < SIGNED_OUT_WAIT_S:
        return 0
    state.pop("signed_out_at", None)
    rows = [r for r in published_reels() if not args.only or r["w"] == args.only]
    shas = long_shas()
    todo = []
    for row in rows:
        key = f"{CHANNEL}|instagram:{row['w']}"
        if (state["uploads"].get(key) or {}).get("status") in TERMINAL:
            continue
        other = next((k for k, u in state["uploads"].items() if k != key and u.get("sha") == row["sha"]), None)
        if other or row["sha"] in shas:
            if not args.dry_run:
                state["uploads"].setdefault(key, {"source": f"instagram:{row['w']}", "w": row["w"]}).update(
                    status="exists", sha=row["sha"], why=f"the same video as {other or 'a long video'}", at=now())
            log(f"{row['w']}: skipped, the same video as {other or 'a long video'}")
            continue
        todo.append(row)
    for row in rows:  # (a thumbnail Studio said it saved: is it on YouTube's public side?)
        if not args.dry_run:
            verify_thumbnail(state["uploads"].get(f"{CHANNEL}|instagram:{row['w']}") or {})
    thumbs = [r for r in rows if thumb_due(state["uploads"].get(f"{CHANNEL}|instagram:{r['w']}") or {})]
    if args.dry_run:
        for row in todo:
            log(f"--- {CHANNEL}|instagram:{row['w']} ({row['url']}; cover {'yes' if row.get('cover_key') else 'NO'})\n"
                f"{make_title(row.get('caption') or '')}\n\n{make_description(row.get('caption') or '', brand_links())}\n")
        return 0
    if todo or thumbs:
        why_not = guard()
        if why_not:
            if why_not == "expired":
                state["signed_out_at"] = now()
                log("youtube-bj is signed out: nothing uploaded (the owner signs in once with `make youtube-bj-login`)")
            else:
                log(f"waiting: {why_not}")
            todo, thumbs = [], []
    titles = ""
    if todo:
        listed = L.call({"account": PROFILE, "task": "titles", "prompt": "the channel's Shorts", "timeout_s": 90})
        if not listed.get("ok"):
            if listed.get("error") == "expired":
                state["signed_out_at"] = now()
            log(f"the channel's Shorts could not be read, tried again next run ({why(listed)})")
            todo = []
        titles = str(listed.get("text_md") or "")
    first_attach = attach_step()
    for row in todo:
        try:
            upload_one(state, row, titles, first_attach)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log(f"{row['w']}: {str(e)[:200]} (tried again next run)")
        save_state(state)
        if state.get("signed_out_at"):
            break
        up = state["uploads"].get(f"{CHANNEL}|instagram:{row['w']}") or {}
        if thumb_due(up) and row not in thumbs:
            thumbs.append(row)
    # each uploaded Short's thumbnail: its reel's Instagram cover (the owner, 2026-11-19)
    for row in thumbs:
        up = state["uploads"].get(f"{CHANNEL}|instagram:{row['w']}") or {}
        if not thumb_due(up) or state.get("signed_out_at"):
            continue
        try:
            set_thumbnail(state, up, row)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log(f"{row['w']}: thumbnail: {str(e)[:200]} (tried again next run)")
        save_state(state)
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
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()
    if quiet_now() and not (args.dry_run or args.only):
        log("night (00:00 to 08:10 Tehran): nothing goes out now")
        return 0
    if args.only and not WS_RE.fullmatch(args.only):
        ap.error("--only takes a work ref, e.g. W-000635")
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the long-video uploader (or another pass) has the profile
        try:
            return one_pass(args)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"error: {str(e)[:200]}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
