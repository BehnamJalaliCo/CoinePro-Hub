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
  7. ⟨2026-11-19, the owner⟩ once the video is PUBLIC (its id in the channel's public feed, which lists public
     videos only), ONE Instagram story on @behnamjalali.tech (a LUMEN story card made from the video's thumbnail:
     the bjtech-common card.py, type story) and ONE post on the page's Telegram channel (the thumbnail, the title,
     a hook from the description, the link as a button). Both go the hub's own ways, inside the api (`docker
     exec`, as breaking.py): the story is session_publish._send (IG-Hub's `publish` job, the stories flows'
     path), the post a scheduled `tg_post` publication (tg_posts: the worker's hq-telegram-tick sends it). Once
     per video: the state's `promo`, an advisory lock and a check of the hub's own records (the story's job,
     the post's fixed chain key); an upload older than PROMO_FROM or PROMO_MAX_AGE is never promoted.
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
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path(os.environ.get("BJ_SYNC_HOME", "/home/Hub/sites"))
STATE, LOCK = HOME / "bjtech-youtube.json", HOME / "bjtech-youtube.lock"
TMP, SHOTS = HOME / "bjtech-longform-tmp", HOME / "bjtech-youtube-shots"
REPO = Path(os.environ.get("BJ_REPO", "/home/Hub/CoinePro-Hub"))
CONFIG = REPO / "automations" / "kits" / "bjtech-common" / "brand" / "config.json"
PROFILE, WORKER, BROWSER, PG = "youtube-bj", "coinepro-hq-worker-1", "coinepro-hq-browser-web-1", "coinepro-hq-postgres-1"
API = "coinepro-hq-api-1"
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
# ⟨2026-11-19⟩ the owner: after each long video is Public, one story + one Telegram post about it
PROMO_FROM = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)  # (W-000636 of 11-18 is never promoted)
PROMO_MAX_AGE, PROMO_TRIES = timedelta(hours=48), 30
PUBLIC_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"  # public videos only
STUDIO_PROMO = Path("/home/studio/bjtech-promo")
RENDER_PY = "/home/studio/kits/prochart-reels/venv-render/bin/python"
CARD = "/home/studio/kits/bjtech-common/tools/card.py"
BROWSERS = "/home/studio/kits/prochart-reels/ms-playwright"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
# Runs in the api (python -c): one video (JSON on stdin) -> its story (IG-Hub publish job) and its Telegram post
PROMO = r"""
import asyncio, base64, json, sys, uuid
from datetime import UTC, datetime
job = json.loads(sys.stdin.read())
async def main():
    from hq_api.__main__ import build
    from hq_api.config import Settings
    from hq_api import audit
    from hq_api.domain import files as F, flows as FL, gate, publications as P, session_publish as SPB
    from hq_api.domain import tg_posts as TG
    hub, _ = await build(Settings())
    out = {"ok": True}
    try:
        vid, ref, account = job["video_id"], job["work"], job["account"]
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k="bjtech-promo:" + vid)
            co = await tx.first("SELECT id, code FROM core.companies WHERE code = :c", c=job["company"])
            lock = await gate.holding_lock(tx) or await gate.automation_lock(tx, co["id"])
            if lock is not None:
                print(json.dumps({"ok": False, "why": "held: " + str(lock)})); return
            async def put(name, raw, w, h):
                data = base64.b64decode(raw)
                key, sha = await hub.storage.put(data)
                fid = await F.insert(tx, company_id=co["id"], name=name, mime="image/jpeg", size=len(data),
                                     sha256=sha, storage_key=key, kind="image", by_kind="service",
                                     by_code=FL.FLOW.code, width=w, height=h, meta={"promo": "youtube:" + vid})
                return {"id": fid, "name": name, "mime": "image/jpeg", "size": len(data)}
            # the story: once (any job of it, whatever its end: never a second story of the same video)
            had = await tx.first(
                "SELECT j.id, j.state FROM infra.server_jobs j WHERE j.kind = 'publish' AND j.args ->> 'kind' = 'story'"
                " AND j.args -> 'session' ->> 'output' = :o AND j.args ->> 'account' = :a ORDER BY j.created_at LIMIT 1",
                o=ref, a=account)
            if had is not None:
                out["story"] = {"was": str(had["id"]), "state": had["state"]}
            else:
                route = await SPB._route(tx, co["id"])
                if not route["ready"]:
                    out["story"] = {"error": "route_not_ready"}
                else:
                    f = await put(f"yt_story_{ref}.jpg", job["story_b64"], 1080, 1920)
                    d = {"ref": ref, "company": co["code"], "company_id": co["id"], "title": job["title"][:200],
                         "work_ref": ref}
                    j = await SPB._send(tx, FL.FLOW, d, f, None, hub=hub, what="story", account=account,
                                        caption="", route=route, order=None,
                                        publication={"topic_fa": job["topic"], "day": job["day"]})
                    pub = await tx.scalar("SELECT ref FROM media.publications WHERE chain[1] = :j", j=j["id"])
                    out["story"] = {"job": str(j["id"]), "publication": pub}
            # the Telegram post: once (its chain key is fixed by the video)
            chain = str(uuid.uuid5(TG.NS, "youtube-promo:" + vid))
            had = await tx.first("SELECT ref, state FROM media.publications WHERE chain[1] = CAST(:c AS uuid)", c=chain)
            chat = await TG.channel_of(tx, co["id"], account)
            if had is not None:
                out["tg"] = {"was": had["ref"], "state": had["state"]}
            elif chat is None:
                out["tg"] = {"error": "no_channel"}
            else:
                f = await put(f"tg_yt_{ref}.jpg", job["photo_b64"], job["photo_w"], job["photo_h"])
                errors = []
                part = TG._part({"photo": f["name"], "text": job["caption"], "buttons": job["buttons"]},
                                {f["name"].lower(): f}, "پست", errors, True)
                if errors or part is None:
                    out["tg"] = {"error": "check", "errors": errors[:5]}
                else:
                    now = datetime.now(UTC)
                    post = {"type": "post", "parts": [part]}
                    caption = TG.read_html(job["caption"])[0]
                    pid = await tx.scalar(
                        P.INSERT_SQL, co=co["id"], channel="telegram", account=account, kind="tg_post",
                        state="scheduled", note=None, scheduled_at=now, published_at=None, url=None, ext=None,
                        title=job["topic"][:200], topic=job["topic"][:300], caption=caption, comment=None,
                        story_word=None, files=json.dumps([{**part["photo"], "role": "attachment"}]),
                        thumb=str(f["id"]), set_key=None, set_n=None,
                        source=json.dumps({"flow_key": job["flow_key"], "day": job["day"], "work": ref,
                                           "order": None, "n": 1, "type": "post", "chat": chat, "post": post,
                                           "promo": "youtube:" + vid}, ensure_ascii=False, default=str),
                        chain=[chain], search=P.search_of(job["topic"], job["topic"], caption, [], None),
                        created_at=None)
                    if pid is not None:
                        row = await tx.one("SELECT * FROM media.publications WHERE id = :id", id=pid)
                        await P._emit(tx, dict(row))
                        out["tg"] = {"publication": row["ref"]}
            await audit.record(tx, FL.FLOW, company_id=co["id"], action="flow.publish", action_class="A3",
                               target_kind="work", target_ref=ref,
                               summary=(f"YouTube {vid} is public: its story and Telegram post to @{account} "
                                        f"(the owner's order of 2026-11-19): {json.dumps(out, default=str)}")[:500])
    finally:
        if hub.bus is not None:
            await hub.bus.close()
        await hub.db.close()
    print(json.dumps(out, ensure_ascii=False, default=str))
asyncio.run(main())
"""
# the egress client (in the worker): one JSON job on stdin -> egress's /v1/substitutes/web answer
CLIENT = r"""
import json, os, sys, httpx
job = json.loads(sys.stdin.readline())
url = os.environ.get("SUPPORT_EGRESS_URL", "http://egress:8090").rstrip("/") + "/v1/substitutes/web"
try:
    r = httpx.post(url, json=job, timeout=job["timeout_s"] + 60)
    if r.status_code >= 400:  # (egress refused the job itself, e.g. 422 on a field: said as it is)
        sys.stdout.write(json.dumps({"ok": False, "error": "http_%d" % r.status_code, "detail": r.text[:600]}))
    else:
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
    raw = r.stdout.decode("utf-8", "replace")
    try:
        out = json.loads(raw or "{}")
    except ValueError:
        out = None
    if not raw.strip():
        return {"ok": False, "error": "off", "detail": f"no answer from egress ({tail(r.stderr, 1)})"}
    if not isinstance(out, dict) or "ok" not in out:  # an answer that is not a job's: egress's own refusal, plainly
        return {"ok": False, "error": "refused", "detail": f"egress answered: {raw.strip()[:500]}"}
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


def config() -> dict:
    try:
        return json.loads(CONFIG.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def channel_name() -> str:
    return str(config().get("youtube_channel_name") or "").strip()


def channel_handle() -> str:
    return str(config().get("youtube_channel_handle") or "").strip()


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
                    "description": meta["description"], "tags": ",".join(up["tags"]) + ",", "visibility": "public",
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


# ------------------------------------------------------------------ ⟨2026-11-19⟩ the story + Telegram post
def public_ids() -> set[str] | None:
    """The channel's PUBLIC videos (its feed lists nothing private, unlisted or scheduled); None: not read."""
    cid = str(config().get("youtube_channel_id") or "")
    if not cid:
        return None
    req = urllib.request.Request(PUBLIC_FEED.format(id=cid), headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return set(re.findall(r"<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>", r.read().decode("utf-8", "replace")))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def short_title(title: str) -> str:
    return " ".join(title.split("|")[0].split()) or " ".join(title.split())


def minutes_fa(meta: dict) -> str:
    try:
        n = max(1, round(float(meta.get("duration") or 0) / 60))
    except (TypeError, ValueError):
        return ""
    return str(n).translate(FA_DIGITS)


def hook_lines(meta: dict) -> list[str]:
    """The description's first paragraph (the session wrote it as the video's hook), at most 3 lines."""
    out = []
    for ln in str(meta.get("description") or "").split("\n"):
        ln = " ".join(ln.split())
        if not ln:
            if out:
                break
            continue
        if "http" in ln or ln.startswith(("📄", "🔗", "#")):
            break
        out.append(ln)
        if len(out) == 3:
            break
    return out


def render_story(ref: str, meta: dict, thumb: Path) -> bytes:
    """The story card (1080x1920, the page's LUMEN story family) with the video's thumbnail as its hero."""
    title = short_title(str(meta.get("title") or ""))
    mins = minutes_fa(meta)
    spec = {"type": "story", "pillar": "news", "accent": "#FF3B4E", "kicker": "ویدیوی تازه در یوتیوب",
            "layout": "hero", "image": str(STUDIO_PROMO / f"{ref}.thumb.jpg"), "image_h": 536, "fit": "cover",
            "title": title, "px": 70 if len(title) <= 60 else 60 if len(title) <= 85 else 52,
            "cta": f"ویدیوی کامل ({mins} دقیقه) در یوتیوب" if mins else "ویدیوی کامل در یوتیوب",
            "word": f"YouTube: {channel_handle() or '@behnamjalali-tech'}"}
    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "spec.json"
        sp.write_text(json.dumps(spec, ensure_ascii=False), "utf-8")
        sudo(["-u", "studio", "mkdir", "-p", str(STUDIO_PROMO)])
        names = [STUDIO_PROMO / f"{ref}.thumb.jpg", STUDIO_PROMO / f"{ref}.spec.json", STUDIO_PROMO / f"{ref}.story.jpg"]
        try:
            for src, dst in ((thumb, names[0]), (sp, names[1])):
                if sudo(["install", "-o", "studio", "-m", "644", str(src), str(dst)]).returncode:
                    raise RuntimeError(f"could not hand {src.name} to the studio user")
            r = sudo(["-u", "studio", "env", f"PLAYWRIGHT_BROWSERS_PATH={BROWSERS}", RENDER_PY, "-I", CARD,
                      str(names[1]), str(names[2])], timeout=300)
            if r.returncode or b" ok" not in (r.stdout or b""):
                raise RuntimeError(f"card.py: {tail(r.stdout) or tail(r.stderr)}")
            got = sudo(["cat", str(names[2])], timeout=60).stdout
        finally:
            sudo(["rm", "-f", *map(str, names)])
    if not got or got[:2] != b"\xff\xd8":
        raise RuntimeError("the story card is not a JPEG")
    return got


def tg_caption(meta: dict, url: str) -> tuple[str, list]:
    """The Telegram post (the bjtech-telegram kit's voice: HTML, the signature line, links as buttons)."""
    import html as H
    cfg = config()
    title = H.escape(short_title(str(meta.get("title") or "")), quote=False)
    hook = "\n".join(H.escape(x, quote=False) for x in hook_lines(meta))
    mins = minutes_fa(meta)
    text = (f"🎬 <b>ویدیوی تازه در یوتیوب</b>\n\n<b>{title}</b>\n\n" + (f"{hook}\n\n" if hook else "")
            + (f"⏱ {mins} دقیقه؛ ویدیوی کامل رو توی یوتیوب ببین 👇" if mins else "ویدیوی کامل رو توی یوتیوب ببین 👇")
            + "\n\n🆔 @behnamjalali_tech")
    buttons = [[{"text": "▶️ تماشای ویدیو در یوتیوب", "url": url}]]
    more = [{"text": t, "url": str(cfg.get(k))} for t, k in (("کانال یوتیوب", "youtube"), ("اینستاگرام", "instagram"))
            if str(cfg.get(k) or "").startswith("https://")]
    if more:
        buttons.append(more)
    return text, buttons


def promote(state: dict, up: dict, public: set[str] | None) -> None:
    """The video's story and Telegram post, once, after it is Public."""
    vid, ref = str(up.get("video_id") or ""), str(up.get("run") or "")
    pr = up.get("promo") or {}
    if up.get("status") != "done" or not vid or not REF_RE.fullmatch(ref) or pr.get("status") in ("done", "check", "skipped"):
        return
    try:
        at = datetime.fromisoformat(str(up.get("at")))
    except ValueError:
        return
    if at < PROMO_FROM or datetime.now(timezone.utc) - at > PROMO_MAX_AGE:
        if not pr:
            up["promo"] = {"status": "skipped", "why": "uploaded before the order or too long ago"}
            save_state(state)
        return
    if public is None or vid not in public:
        pr.update(status="waiting", why="not in the channel's public feed yet")
        up["promo"] = pr
        save_state(state)
        return
    keep = HOME / "bjtech-longform" / ref
    try:
        meta = json.loads((keep / "meta.json").read_text("utf-8"))
        story = render_story(ref, meta, keep / "thumbnail.jpg")
        caption, buttons = tg_caption(meta, f"https://youtu.be/{vid}")
        photo = (keep / "thumbnail.jpg").read_bytes()
        pv = probe(keep / "thumbnail.jpg")
        ps = next((s for s in pv.get("streams", []) if s.get("codec_type") == "video"), {})
        job = {"video_id": vid, "work": ref, "account": str(config().get("handle") or "behnamjalali.tech"),
               "company": "IG", "title": short_title(str(meta.get("title") or ""))[:200],
               "topic": f"ویدیوی یوتیوب: {short_title(str(meta.get('title') or ''))}"[:300],
               "day": state["runs"].get(ref, {}).get("day"), "flow_key": "bjtech_long",
               "story_b64": base64.b64encode(story).decode(), "photo_b64": base64.b64encode(photo).decode(),
               "photo_w": int(ps.get("width") or 1280), "photo_h": int(ps.get("height") or 720),
               "caption": caption, "buttons": buttons}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        pr.update(status="waiting", why=f"not made: {str(e)[:200]}", tries=pr.get("tries", 0) + 1)
        if pr["tries"] >= PROMO_TRIES:
            pr["status"] = "check"
        up["promo"] = pr
        save_state(state)
        log(f"{ref}: story/Telegram not made ({str(e)[:160]})")
        return
    with tempfile.TemporaryFile() as stdin:
        stdin.write(json.dumps(job, ensure_ascii=False).encode())
        stdin.seek(0)
        try:
            r = run(["docker", "exec", "-i", "-w", "/tmp", API, "python", "-c", PROMO], stdin=stdin, timeout=300)
            lines = [ln for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.startswith("{")]
            ans = json.loads(lines[-1]) if lines else {"ok": False, "why": f"no answer ({tail(r.stderr, 1)})"}
        except (subprocess.TimeoutExpired, ValueError) as e:
            ans = {"ok": False, "why": type(e).__name__}
    del job
    st, tg = ans.get("story") or {}, ans.get("tg") or {}
    pr.update(story=st, tg=tg, at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    made = lambda x: bool(x.get("job") or x.get("publication") or x.get("was"))  # noqa: E731
    if ans.get("ok") and made(st) and made(tg):
        pr.update(status="done", why="")
        log(f"{ref}: public on YouTube -> story {st.get('publication') or st.get('was')} and Telegram post "
            f"{tg.get('publication') or tg.get('was')}")
    else:
        pr.update(status="waiting", why=str(ans.get("why") or json.dumps(ans, ensure_ascii=False))[:300],
                  tries=pr.get("tries", 0) + 1)
        if pr["tries"] >= PROMO_TRIES:
            pr["status"] = "check"
        log(f"{ref}: story/Telegram not out yet: {pr['why'][:200]}")
    up["promo"] = pr
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
            handle = channel_handle()
            switcher = str((ans.get("notes") or {}).get("channels") or "")
            if want not in active or (handle and handle not in switcher):
                run_.update(status="waiting", why=f"the active channel is not {want!r} {handle}: {active[:80]!r}")
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
        if not dry:  # ⟨2026-11-19⟩ the story and the Telegram post of a video now public, once
            todo = [u for u in state["uploads"].values() if u.get("status") == "done"
                    and (u.get("promo") or {}).get("status") not in ("done", "check", "skipped")]
            public = public_ids() if todo else None
            for up in todo:
                promote(state, up, public)
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
                          "active": active[:200], "expected": channel_name(), "handle": channel_handle(),
                          "match": bool(channel_name()) and channel_name() in active
                          and (not channel_handle() or channel_handle() in str((ans.get("notes") or {}).get("channels") or ""))},
                         ensure_ascii=False, indent=1))
        return 0
    if a.due:
        return due(a.dry_run)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
