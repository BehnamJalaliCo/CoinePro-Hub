#!/usr/bin/env python3
"""@behnamjalali.tech: the daily long video (flow bjtech_long) -> ONE upload on its YouTube channel (stdlib + ffprobe).

The upload runs in the hub's signed-in browser profile `youtube-bj` (its own Google account; recipe
infra/egress/recipes/youtube-bj.yaml), never through the YouTube Data API (an unaudited project's uploads are
locked Private). A sibling of DotCoin's automations/sites/dotcoin/youtube_long.py without the site steps.

A due pass (bjtech-longform.timer, every 10 minutes, as Hub) for each run of the flow whose package is queued
(`youtube: queued`, the hub's _queue_video) and whose hour has come:
  1. copies its out/ from the workshop (sudo: the studio user's) and checks the files (ffprobe: H.264 1920x1080,
     8-16 minutes, at most 1 GB; the thumbnail JPEG/PNG 16:9 at most 2 MB; meta.json; subtitles.fa.srt);
  2. refuses a soundtrack with a click, a cut or a burst (the kit's audio_qc, as the studio user);
  3. THE CHANNEL GUARD: reads the profile's active channel (task `channel`) and uploads only when it is the
     page's channel (`youtube_channel_name` in automations/kits/bjtech-common/brand/config.json; empty = nothing is
     ever uploaded): never a video on the wrong channel;
  4. refuses a second upload (its key and sha256 in the state; its title in the channel's list, task `videos`);
  5. spools the video and the thumbnail into the profile browser and runs ONE `upload_long` (Public);
  6. then the video's tags and language (`details`), its Persian subtitles (`subtitles`) and, when the upload did
     not take it, its thumbnail (`thumbnail`), each tried again on later passes (at most 3 times).
State: /home/Hub/sites/bjtech-youtube.json. Never retried by itself after the Done click (state `check`).

    youtube_long.py --channel        read only: the switcher's channels and the active channel
    youtube_long.py --due            the timer's pass
    youtube_long.py --due --dry-run  the same, checking and reporting, uploading nothing
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("BJ_SYNC_HOME", "/home/Hub/sites"))
STATE, LOCK = HOME / "bjtech-youtube.json", HOME / "bjtech-youtube.lock"
TMP, SHOTS = HOME / "bjtech-longform-tmp", HOME / "bjtech-youtube-shots"
REPO = Path(os.environ.get("BJ_REPO", "/home/Hub/CoinePro-Hub"))
CONFIG = REPO / "automations" / "kits" / "bjtech-common" / "brand" / "config.json"
PROFILE, WORKER, BROWSER, PG = "youtube-bj", "coinepro-hq-worker-1", "coinepro-hq-browser-web-1", "coinepro-hq-postgres-1"
SPOOL = "/profiles/.spool/" + PROFILE
WORKSPACE = Path("/home/studio/hq-workspace")
STUDIO_PY = "/home/studio/kits/prochart-reels/asr/venv/bin/python"
AUDIO_QC = "/home/studio/kits/prochart-reels/tools/audio_qc.py"
QC_DIR = Path("/home/studio/longform-qc")
OUT_FILES = ("video.mp4", "thumbnail.jpg", "meta.json", "subtitles.fa.srt")
DURATION_S, MAX_VIDEO, MAX_THUMB = (7 * 60, 16 * 60 + 30), 1024 ** 3, 2 * 1024 * 1024
FINISH_TRIES = 3
REF_RE = re.compile(r"W-\d{3,9}")
VIDEO_URL = re.compile(r"https://(?:www\.)?(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|video/))([A-Za-z0-9_-]{11})")
DUE_SQL = """
    SELECT w.ref, w.run_meta -> 'flow' ->> 'day' AS day, w.run_meta -> 'flow' ->> 'publish_at' AS publish_at
      FROM work.work w
     WHERE w.run_meta -> 'flow' ->> 'key' = 'bjtech_long' AND w.run_meta -> 'flow' ->> 'youtube' = 'queued'
       AND (w.run_meta -> 'flow' ->> 'publish_at')::timestamptz <= now()
       AND w.created_at > now() - interval '7 days'
     ORDER BY w.created_at"""
# the egress client (in the worker): one JSON job on stdin -> egress's /v1/substitutes/web answer
CLIENT = r"""
import json, os, sys, httpx
job = json.loads(sys.stdin.readline())
url = os.environ.get("SUPPORT_EGRESS_URL", "http://egress:8090").rstrip("/") + "/v1/substitutes/web"
try:
    r = httpx.post(url, json=job, timeout=job["timeout_s"] + 60)
    sys.stdout.write(r.text)
except httpx.HTTPError as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "off", "detail": type(e).__name__}))
"""
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
        if not b:
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


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}", flush=True)


def run(cmd: list[str], *, timeout: int = 120, stdin=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def tail(b: bytes | None, n: int = 2) -> str:
    lines = [ln for ln in (b or b"").decode("utf-8", "replace").splitlines() if ln.strip()]
    return " / ".join(ln.strip()[:160] for ln in lines[-n:])


def sql(query: str) -> list[dict]:
    q = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t"
    r = run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", PG,
             "psql", "-U", "postgres", "-d", "hq", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", q], timeout=60)
    if r.returncode:
        raise RuntimeError(f"db query failed: {tail(r.stderr)}")
    return json.loads(r.stdout.decode() or "[]")


def call(job: dict) -> dict:
    with tempfile.TemporaryFile() as stdin:
        stdin.write(json.dumps(job, ensure_ascii=False).encode() + b"\n")
        stdin.seek(0)
        try:
            r = run(["docker", "exec", "-i", WORKER, "python", "-c", CLIENT], stdin=stdin, timeout=int(job["timeout_s"]) + 120)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "off", "detail": "no answer from egress in time"}
    try:
        out = json.loads(r.stdout.decode() or "{}")
    except ValueError:
        out = {}
    if not isinstance(out, dict) or "ok" not in out:
        return {"ok": False, "error": "off", "detail": f"no answer from egress ({tail(r.stderr, 1)})"}
    shot = out.pop("screenshot", None)
    if isinstance(shot, dict) and shot.get("b64"):  # for the SRE who fixes the recipe; never printed
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{job['task']}.jpg"
        path.write_bytes(base64.b64decode(shot["b64"]))
        out["screenshot_file"] = str(path)
    return out


def load_state() -> dict:
    try:
        s = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("uploads", {})
    s.setdefault("runs", {})
    return s


def save_state(s: dict) -> None:
    s["last_change"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def channel_name() -> str:
    try:
        return str(json.loads(CONFIG.read_text("utf-8")).get("youtube_channel_name") or "").strip()
    except (OSError, ValueError):
        return ""


def active_channel() -> tuple[str, dict]:
    ans = call({"account": PROFILE, "task": "channel", "prompt": "read", "timeout_s": 110})
    text = str(ans.get("text_md") or ans.get("text") or "")
    return " ".join(text.split())[:200], ans


def sudo(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return run(["sudo", "-n", *cmd], timeout=timeout)


def fetch_out(ref: str, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    missing = []
    for name in OUT_FILES:
        src = WORKSPACE / ref / "out" / name
        if sudo(["test", "-f", str(src)]).returncode or sudo(["cp", str(src), str(dest / name)]).returncode:
            missing.append(name)
            continue
        sudo(["chown", f"{os.getuid()}:{os.getgid()}", str(dest / name)])
    return missing


def probe(path: Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
             "-of", "json", str(path)], timeout=60)
    return json.loads(r.stdout.decode() or "{}")


def check_files(work: Path) -> str:
    v, t = work / "video.mp4", work / "thumbnail.jpg"
    p = probe(v)
    vs = next((s for s in p.get("streams", []) if s.get("codec_type") == "video"), {})
    dur = float((p.get("format") or {}).get("duration") or 0)
    if vs.get("codec_name") != "h264" or (vs.get("width"), vs.get("height")) != (1920, 1080):
        return f"the video is {vs.get('codec_name')} {vs.get('width')}x{vs.get('height')}, not h264 1920x1080"
    if not DURATION_S[0] <= dur <= DURATION_S[1]:
        return f"the video is {dur / 60:.1f} minutes"
    if v.stat().st_size > MAX_VIDEO or t.stat().st_size > MAX_THUMB:
        return "a file is over its size"
    meta = json.loads((work / "meta.json").read_text("utf-8"))
    if not meta.get("title") or not meta.get("description"):
        return "meta.json has no title or description"
    return ""


def audio_clean(ref: str) -> str:
    sudo(["-u", "studio", "mkdir", "-p", str(QC_DIR)])
    wav = QC_DIR / f"{ref}.wav"
    r = sudo(["-u", "studio", "ffmpeg", "-v", "error", "-y", "-i", str(WORKSPACE / ref / "out" / "video.mp4"), "-vn",
              "-ac", "2", "-ar", "48000", str(wav)], timeout=900)
    if r.returncode:
        return f"the soundtrack could not be read ({tail(r.stderr, 1)})"
    r = sudo(["-u", "studio", STUDIO_PY, "-I", AUDIO_QC, str(wav), str(QC_DIR / f"{ref}.audioqc.json")], timeout=1200)
    sudo(["-u", "studio", "rm", "-f", str(wav)])
    try:
        got = json.loads((r.stdout or b"").decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return f"audio_qc gave no answer ({tail(r.stderr, 1)})"
    n = {k: int(got.get(k) or 0) for k in ("clicks", "cuts", "bursts")}
    return "" if not any(n.values()) else f"audio_qc: {n['clicks']} clicks, {n['cuts']} cuts, {n['bursts']} bursts"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def spool_put(src: Path, name: str) -> str:
    with open(src, "rb") as f:
        r = run(["docker", "exec", "-i", BROWSER, "python3", "-c", PUT, SPOOL, name, str(src.stat().st_size)], stdin=f, timeout=900)
    got = r.stdout.decode().strip()
    if r.returncode or got != sha256(src):
        raise RuntimeError(f"spool copy of {name} failed: {tail(r.stderr, 1) or 'sha256 differs'}")
    return got


def spool_drop(names: list[str]) -> None:
    if names:
        run(["docker", "exec", BROWSER, "python3", "-c", DROP, SPOOL, *names], timeout=60)


def upload(ref: str, work: Path, state: dict, dry: bool) -> str:
    meta = json.loads((work / "meta.json").read_text("utf-8"))
    sha = sha256(work / "video.mp4")
    key = f"youtube:@behnamjalali-tech|long:{meta.get('slug') or sha[:12]}"
    if key in state["uploads"] or any(u.get("sha") == sha for u in state["uploads"].values()):
        return "already uploaded (state)"
    listed = call({"account": PROFILE, "task": "videos", "prompt": "read", "timeout_s": 110})
    if not listed.get("ok"):
        return f"the channel's list could not be read ({listed.get('error')}: {listed.get('detail')})"
    if meta["title"].strip() in str(listed.get("text_md") or listed.get("text") or ""):
        return "a video with this title is already on the channel"
    if dry:
        return "dry-run: would upload"
    v_name, t_name = f"bj-{sha[:16]}.mp4", f"bj-{sha[:16]}.jpg"
    spool_put(work / "video.mp4", v_name)
    spool_put(work / "thumbnail.jpg", t_name)
    up = {"key": key, "sha": sha, "run": ref, "title": meta["title"], "status": "uploading",
          "tags": list(meta.get("tags") or []), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    state["uploads"][key] = up
    save_state(state)
    try:
        ans = call({"account": PROFILE, "task": "upload_long", "prompt": meta["title"][:100],
                    "description": meta["description"], "tags": ",".join(up["tags"]) + ",", "visibility": "PUBLIC",
                    "spooled": [v_name, t_name], "timeout_s": 1500})
    finally:
        spool_drop([v_name, t_name])
    m = VIDEO_URL.search(json.dumps(ans))
    if ans.get("ok") and m:
        # (the thumbnail is set again by its own task: the upload dialog's answer does not say for sure)
        up.update(status="done", url=f"https://youtu.be/{m.group(1)}", video_id=m.group(1), thumb_set="no")
        keep = HOME / "bjtech-longform" / ref
        keep.mkdir(parents=True, exist_ok=True)
        for name in ("subtitles.fa.srt", "meta.json", "thumbnail.jpg"):
            (keep / name).write_bytes((work / name).read_bytes())
        up.update(srt=str(keep / "subtitles.fa.srt"), thumb=str(keep / "thumbnail.jpg"))
        save_state(state)
        return ""
    up.update(status="check", why=f"{ans.get('error')}: {str(ans.get('detail'))[:200]} step {ans.get('step')}")
    save_state(state)
    return f"the upload did not finish ({up['why']}); a person looks in Studio (state check)"


def finish(state: dict, up: dict) -> None:
    """Tags and language, the Persian subtitles, the thumbnail: each at most FINISH_TRIES times."""
    vid = up.get("video_id")
    if not vid:
        return
    if up.get("tags_saved") != "yes" and up.get("tag_tries", 0) < FINISH_TRIES:
        up["tag_tries"] = up.get("tag_tries", 0) + 1
        ans = call({"account": PROFILE, "task": "details", "prompt": "details", "timeout_s": 240, "video_id": vid,
                    "tags": ",".join(up.get("tags") or []) + ","})
        up["tags_saved"] = "yes" if ans.get("ok") else "no"
    for task, flag, path, cap in (("subtitles", "subs", up.get("srt"), 300), ("thumbnail", "thumb_set", up.get("thumb"), 180)):
        if up.get(flag) == "yes" or up.get(f"{task}_tries", 0) >= FINISH_TRIES or not path or not Path(path).exists():
            continue
        up[f"{task}_tries"] = up.get(f"{task}_tries", 0) + 1
        name = f"bj-{vid}{Path(path).suffix}"
        try:
            spool_put(Path(path), name)
            ans = call({"account": PROFILE, "task": task, "prompt": task, "timeout_s": cap, "video_id": vid, "spooled": [name]})
        finally:
            spool_drop([name])
        up[flag] = "yes" if ans.get("ok") else "no"
    save_state(state)


def due(dry: bool) -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state = load_state()
        rows = [r for r in sql(DUE_SQL) if REF_RE.fullmatch(str(r.get("ref") or ""))]
        for row in rows:
            ref = row["ref"]
            run_ = state["runs"].setdefault(ref, {"day": row["day"], "publish_at": row["publish_at"]})
            if run_.get("status") in ("done", "check"):
                continue
            want = channel_name()
            if not want:
                run_.update(status="waiting", why="no youtube_channel_name in bjtech-common/brand/config.json yet")
                save_state(state)
                log(f"{ref}: waiting: the page's channel is not set (nothing is uploaded blind)")
                continue
            active, ans = active_channel()
            if ans.get("error") == "expired":
                run_.update(status="waiting", why="youtube-bj is signed out")
                save_state(state)
                log(f"{ref}: waiting: youtube-bj is signed out")
                continue
            if want not in active:
                run_.update(status="waiting", why=f"the active channel is not {want!r}: {active[:80]!r}")
                save_state(state)
                log(f"{ref}: waiting: the active channel is not the page's")
                continue
            work = TMP / ref
            missing = fetch_out(ref, work)
            why = (f"out/ lacks {', '.join(missing)}" if missing else "") or check_files(work) or audio_clean(ref)
            if why:
                run_.update(status="blocked" if not missing else "waiting", why=why[:300])
                save_state(state)
                log(f"{ref}: not uploaded: {why[:200]}")
                continue
            why = upload(ref, work, state, dry)
            state = load_state()
            run_ = state["runs"].setdefault(ref, run_)
            run_.update(status="done" if not why else ("check" if "check" in why else "blocked"), why=why[:300])
            save_state(state)
            log(f"{ref}: {why or 'uploaded Public'}")
        for up in list(state["uploads"].values()):
            if up.get("status") == "done" and not dry:
                finish(state, up)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", action="store_true")
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    if a.channel:
        active, ans = active_channel()
        print(json.dumps({"ok": ans.get("ok"), "error": ans.get("error"), "channels": (ans.get("notes") or {}).get("channels"),
                          "active": active[:200], "expected": channel_name()}, ensure_ascii=False, indent=1))
        return 0
    if a.due:
        return due(a.dry_run)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
