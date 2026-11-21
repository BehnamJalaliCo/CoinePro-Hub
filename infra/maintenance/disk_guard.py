#!/usr/bin/env python3
"""infra/maintenance/disk_guard.py: what is posted leaves the disk; the disk never fills again.

The disk hit 100% on 2026-11-19 and again on 11-20 07:42Z; Postgres stopped and every publication
waited. The owner, 11-20: «چه ریلز چه ویدیو بلند رو به محض ارسال … بعدش اتوماتیک پاک بشه و از پست
شدنش قبلش اطمینان حاصل بکنه». Run every 15 minutes by coinepro-hq-disk-guard.timer, as root (the
workshop is studio's, the file volume is the api's).

1. A posted video leaves the file store. A video file (files.files, video/*) goes when EVERY
   publication that uses it is `published` with its post's URL or id (IG-Hub / Telegram confirmed it)
   at least GRACE_MIN ago, or `cancelled`, and at least one is published; no publish job still
   queued or running carries it; and a reel of a page that mirrors its reels to YouTube Shorts
   (SHORTS) has its Short uploaded (that page's state file says `done` for the reel's work or for
   the file's sha256), unless the reel is older than the Shorts window. Only the bytes go: the
   files.files row is append-only and stays (the app then answers «file content missing», 404), the
   cover, the thumbnails and the caption stay. The archive's copy of it (the §58.4 publication
   record) is destroyed the archive's way (destroyed_at, hashes kept), never while a hold exists.
2. A workshop folder (/home/studio/hq-workspace/W-…) goes once its work is no longer queued or in
   progress, quiet QUIET_MIN, every publication made from it is published or cancelled, and a long
   video it holds is uploaded (bjtech-youtube.json / dotcoin-youtube.json say `done`); a long video
   still waiting keeps out/ (only build/ and ch/ go). A finished work with no publication and no
   long video waits NOPUB_QUIET_H (its output may still wait for the owner).
3. The job homes (.hq/W-…) of a work that is gone or finished: after HOME_QUIET_D quiet days.
4. A long video's upload copy (sites/bjtech-longform-tmp, sites/longform-tmp) once uploaded.
5. At EMERGENCY_PCT or more: every local pg_dump set but the newest (all are in restic and on
   Drive), build cache unused for 24 h, the journal down to 200M. Below that it never touches them.

Never: a Docker volume, restic, wal, hourly, kits, a work in progress, anything not yet posted.
Every removal is one line in LOG (what, why, bytes, the post's URL). Usage: disk_guard.py [--dry-run] [--verbose]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PG = "coinepro-hq-postgres-1"
FILES = Path("/var/lib/docker/volumes/coinepro-hq_hq-files/_data")
WS = Path("/home/studio/hq-workspace")
SITES = Path("/home/Hub/sites")
BACKUPS = Path("/home/Hub/backups")
LOG = Path("/var/lib/coinepro-hq/disk-guard.jsonl")
TEXTFILE = Path("/var/lib/coinepro-hq/textfile/hq_disk_guard.prom")
GRACE_MIN = 30
QUIET_MIN = 60
NOPUB_QUIET_H = 24
HOME_QUIET_D = 7
SHORTS_DAYS = 30  # the Shorts mirrors only look at reels of the last 30 days (REELS_SQL)
SHORTS = {"behnamjalali.tech": SITES / "bjtech-shorts.json", "dotcoin.me": SITES / "dotcoin-youtube.json"}
LONG_STATES = ((SITES / "bjtech-youtube.json", "runs"), (SITES / "dotcoin-youtube.json", "long_runs"))
LONG_TMPS = (SITES / "bjtech-longform-tmp", SITES / "longform-tmp")
ACTIVE_WORK = ("cancelled", "delivered", "done")  # the terminal ones; anything else is still running
EMERGENCY_PCT = 90
REF = re.compile(r"W-\d{6,9}")
KEY = re.compile(r"[0-9a-f]{32}")
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")

DRY = "--dry-run" in sys.argv[1:]
NOW = datetime.now(timezone.utc)
freed = 0


def say(msg: str) -> None:
    print(f"{NOW:%Y-%m-%dT%H:%M:%SZ} disk-guard: {msg}", flush=True)


def note(what: str, path: str, size: int, why: str, **extra: object) -> None:
    global freed
    freed += size
    say(f"{'would remove' if DRY else 'removed'} {what} {path} ({size / 1e6:.0f} MB): {why}")
    if not DRY:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        "at": NOW.isoformat(timespec="seconds"),
                        "what": what,
                        "path": path,
                        "bytes": size,
                        "why": why,
                        **extra,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )


def sql(query: str, *, write: bool = False) -> list[dict]:
    if write:
        q = query
    else:
        q = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t"
    r = subprocess.run(
        ["docker", "exec", "-i", PG, "psql", "-U", "postgres", "-d", "hq", "-v", "ON_ERROR_STOP=1", "-At"],
        input=q,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"psql: {r.stderr.strip()[:300]}")
    return [] if write else json.loads(r.stdout.strip() or "[]")


def lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def ts(v: object) -> datetime | None:
    if not v:
        return None
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def du(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def quiet_for(p: Path, minutes: float) -> bool:
    """Nothing under p changed in the last `minutes`."""
    edge = time.time() - minutes * 60
    for root, dirs, files in os.walk(p):
        for n in dirs + files:
            try:
                if os.lstat(os.path.join(root, n)).st_mtime > edge:
                    return False
            except OSError:
                pass
    try:
        return p.stat().st_mtime <= edge
    except OSError:
        return True


def rm(p: Path) -> None:
    if DRY:
        return
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        p.unlink(missing_ok=True)


def long_done(ref: str) -> str | None:
    """The long video of `ref` is uploaded: its URL, else None."""
    for path, key in LONG_STATES:
        run = (load(path).get(key) or {}).get(ref) or {}
        if run.get("status") == "done":
            return str(run.get("url") or "done")
    return None


# ------------------------------------------------------------------ 1. posted videos
def posted_videos() -> None:
    rows = sql("""
        SELECT f.id::text AS id, f.storage_key AS key, f.sha256 AS sha, f.size AS size,
               json_agg(json_build_object('ref', p.ref, 'state', p.state, 'account', p.account, 'kind', p.kind,
                        'published_at', p.published_at, 'url', coalesce(p.url, p.external_id),
                        'work', p.source ->> 'work')) AS pubs
          FROM files.files f
          JOIN media.publications p ON f.id = ANY(p.file_ids)
         WHERE f.mime LIKE 'video/%'
         GROUP BY f.id""")
    busy = " ".join(
        r["a"]
        for r in sql("SELECT args::text AS a FROM infra.server_jobs WHERE state NOT IN ('done', 'failed', 'cancelled')")
    )
    shorts = {acc: load(p).get("uploads") or {} for acc, p in SHORTS.items()}
    holds = sql("SELECT count(*) AS n FROM archive.holds")[0]["n"]
    for f in rows:
        if not KEY.fullmatch(str(f["key"] or "")):
            continue
        path = FILES / f["key"][:2] / f["key"]
        pubs = f["pubs"]
        why = None
        if any(p["state"] not in ("published", "cancelled") for p in pubs):
            why = "a publication still waits"
        elif not any(p["state"] == "published" for p in pubs):
            why = "never published"
        elif any(
            p["state"] == "published"
            and (
                not p["url"] or not ts(p["published_at"]) or ts(p["published_at"]) > NOW - timedelta(minutes=GRACE_MIN)
            )
            for p in pubs
        ):
            why = "published < grace or no post URL"
        elif f["id"] in busy:
            why = "a publish job still carries it"
        else:
            why = short_waits(pubs, f["sha"], shorts)
        if why:
            if "--verbose" in sys.argv[1:]:
                say(
                    f"kept video {f['id']} ({f['size'] / 1e6:.0f} MB, {', '.join(p['ref'] + ':' + p['state'] for p in pubs)}): {why}"
                )
            continue
        try:
            purge(f, path, pubs, holds)
        except Exception as exc:  # one file failing never stops the others
            say(f"video {f['id']} not purged: {exc}")


def short_waits(pubs: list[dict], sha: str, shorts: dict[str, dict]) -> str | None:
    """A reel of a page that mirrors its reels to YouTube Shorts whose Short is not uploaded yet."""
    for p in pubs:
        at = ts(p.get("published_at") or p.get("at"))
        if p["state"] == "published" and p["kind"] == "reel" and p["account"] in SHORTS and at \
                and at > NOW - timedelta(days=SHORTS_DAYS):  # fmt: skip
            if not any(u.get("status") == "done" and (u.get("source") == f"instagram:{p['work']}" or u.get("sha") == sha)
                       for u in shorts[p["account"]].values()):  # fmt: skip
                return f"its YouTube Short ({p['account']}) is not uploaded yet"
    return None


def destroy_copy(c: dict, why: str, **extra: object) -> None:
    """One archive copy, the archive's way: destroyed_at with the hashes kept, storage_key / wrapped_dek /
    text cleared (record_files_check1), then the bytes."""
    if not UUID.fullmatch(c["id"]):
        return
    cpath = FILES / c["key"][:2] / c["key"] if KEY.fullmatch(str(c["key"] or "")) else None
    size = cpath.stat().st_size if cpath and cpath.exists() else 0
    if not DRY:
        sql(
            "UPDATE archive.record_files SET destroyed_at = now(), storage_key = NULL, wrapped_dek = NULL,"
            f" text = NULL WHERE id = {lit(c['id'])} AND destroyed_at IS NULL",
            write=True,
        )
        if cpath:
            rm(cpath)
    note("archive copy", str(cpath), size, why, record=c["record"], **extra)


def purge(f: dict, path: Path, pubs: list[dict], holds: int) -> None:
    posts = [p["url"] for p in pubs if p["state"] == "published"]
    refs = [p["ref"] for p in pubs]
    if path.exists():
        size = path.stat().st_size
        rm(path)
        note("video", str(path), size, "posted", file_id=f["id"], publications=refs, posts=posts)
    # its §58.4 archive copy (same bytes, same sha256), destroyed the archive's way: destroyed_at with
    # the hashes kept, storage_key / wrapped_dek / text cleared (record_files_check1), then the bytes
    if holds:
        return
    copies = sql(f"""
        SELECT r.id::text AS id, r.storage_key AS key, a.ref AS record
          FROM archive.record_files r JOIN archive.records a ON a.id = r.record_id
         WHERE r.sha256 = {lit(f["sha"])} AND r.mime LIKE 'video/%' AND r.destroyed_at IS NULL
           AND a.ref IN (SELECT record_ref FROM files.publish_keep WHERE record_ref IS NOT NULL)""")
    for c in copies:
        destroy_copy(c, "posted", file_id=f["id"], posts=posts)


# ------------------------------------------------------------------ 1b. everything else of a past day
# Whose time is past the owner's yesterday (Tehran): what the app still shows (publications.SHOWN_DAYS)
SINCE_SQL = """(SELECT ((date_trunc('day', now() AT TIME ZONE z) - interval '1 day') AT TIME ZONE z)
                  FROM (SELECT coalesce((SELECT timezone FROM owner.settings WHERE id = 1), 'Asia/Tehran') AS z) t)"""


def posted_days_ago() -> None:
    """Every other file of a publication (a story's picture, a cover, a set's frame, the thumbnail, the
    kept caption, their thumb/poster/frame children) and its archive copies leave the disk once every
    publication using it is final (posted with its post's URL/id, cancelled or failed), every one's time
    is before the owner's yesterday, no publish job still carries it, and a reel's Short is
    uploaded. The app no longer shows these (publications.SHOWN_SQL)."""
    rows = sql(f"""
        WITH since AS (SELECT {SINCE_SQL} AS s),
        refs AS (
          SELECT p.id AS pid, x.fid FROM media.publications p, LATERAL (
              SELECT unnest(p.file_ids) AS fid
              UNION SELECT p.thumb_file_id WHERE p.thumb_file_id IS NOT NULL
              UNION SELECT (e ->> 'file_id')::uuid FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(p.files) = 'array' THEN p.files ELSE '[]'::jsonb END) e
                     WHERE e ->> 'file_id' ~ '^[0-9a-f]{{8}}(-[0-9a-f]{{4}}){{3}}-[0-9a-f]{{12}}$'
              UNION SELECT unnest(k.kept) FROM files.publish_keep k WHERE p.chain @> ARRAY[k.job_id]) x)
        SELECT f.id::text AS id, f.storage_key AS key, f.sha256 AS sha,
               bool_and(p.state IN ('published', 'cancelled', 'failed') AND p.at < (SELECT s FROM since)) AS past,
               bool_or(p.state = 'published') AS posted,
               bool_and(p.state <> 'published' OR coalesce(p.url, p.external_id) IS NOT NULL) AS confirmed,
               json_agg(json_build_object('ref', p.ref, 'state', p.state, 'account', p.account, 'kind', p.kind,
                        'published_at', p.published_at, 'at', p.at, 'work', p.source ->> 'work',
                        'url', coalesce(p.url, p.external_id))) AS pubs,
               (SELECT coalesce(json_agg(c.storage_key), '[]'::json) FROM files.files c WHERE c.parent_id = f.id) AS kids
          FROM refs r JOIN files.files f ON f.id = r.fid JOIN media.publications p ON p.id = r.pid
         GROUP BY f.id""")
    busy = " ".join(
        r["a"]
        for r in sql("SELECT args::text AS a FROM infra.server_jobs WHERE state NOT IN ('done', 'failed', 'cancelled')")
    )
    shorts = {acc: load(p).get("uploads") or {} for acc, p in SHORTS.items()}
    for f in rows:
        # a cancelled or failed one is final too: the app no longer shows it, nothing will send it
        if not (f["past"] and f["confirmed"]) or f["id"] in busy:
            continue
        if short_waits(f["pubs"], f["sha"], shorts):
            continue
        size, gone = 0, []
        for key in [f["key"], *f["kids"]]:
            if not KEY.fullmatch(str(key or "")):
                continue
            path = FILES / key[:2] / key
            if path.exists():
                size += path.stat().st_size
                rm(path)
                gone.append(key)
        if gone:
            note("past media", str(FILES / f["key"][:2] / f["key"]), size, "final, before yesterday",
                 file_id=f["id"], files=len(gone), publications=[p["ref"] for p in f["pubs"]],
                 posts=[p["url"] for p in f["pubs"] if p["state"] == "published"])  # fmt: skip
    # the §58.4 archive records of those publications: every copy (the video, the cover, caption.txt)
    if sql("SELECT count(*) AS n FROM archive.holds")[0]["n"]:
        return
    copies = sql(f"""
        WITH since AS (SELECT {SINCE_SQL} AS s)
        SELECT r.id::text AS id, r.storage_key AS key, a.ref AS record
          FROM files.publish_keep k JOIN archive.records a ON a.ref = k.record_ref
          JOIN archive.record_files r ON r.record_id = a.id
         WHERE r.destroyed_at IS NULL
           AND EXISTS (SELECT 1 FROM media.publications p WHERE p.chain @> ARRAY[k.job_id])
           AND NOT EXISTS (SELECT 1 FROM media.publications p WHERE p.chain @> ARRAY[k.job_id]
                            AND (p.state NOT IN ('published', 'cancelled', 'failed') OR p.at >= (SELECT s FROM since)))""")
    for c in copies:
        try:
            destroy_copy(c, "final, before yesterday")
        except Exception as exc:  # one copy failing never stops the others
            say(f"archive copy {c['id']} not destroyed: {exc}")


# ------------------------------------------------------------------ 2-3. the workshop
def workshop() -> None:
    if not WS.is_dir():
        return
    dirs = sorted(d.name for d in WS.iterdir() if d.is_dir() and REF.fullmatch(d.name))
    homes = (
        sorted(d.name for d in (WS / ".hq").iterdir() if d.is_dir() and REF.fullmatch(d.name))
        if (WS / ".hq").is_dir()
        else []
    )
    refs = sorted(set(dirs) | set(homes))
    if not refs:
        return
    info = {
        r["ref"]: r
        for r in sql(f"""
        SELECT w.ref, w.status, w.run_meta -> 'flow' ->> 'youtube' AS yt,
               w.run_meta -> 'flow' ->> 'kind' AS fkind,
               (SELECT json_agg(p.state) FROM media.publications p WHERE p.source ->> 'work' = w.ref) AS pubs
          FROM work.work w WHERE w.ref IN ({",".join(lit(r) for r in refs)})""")
    }
    for ref in dirs:
        d, w = WS / ref, info.get(ref)  # a ref the owner's wipe removed counts as finished
        if w and w["status"] not in ACTIVE_WORK:
            continue
        if not quiet_for(d, QUIET_MIN):
            continue
        pubs = (w or {}).get("pubs") or []
        if any(s not in ("published", "cancelled") for s in pubs):
            continue
        url = long_done(ref)
        # ⟨2026-11-21⟩ W-000752 was removed here (11-21 08:00Z, 745 MB): the hub had never marked its day
        # `youtube: queued` (a bug, 475e02db), so it read as «nothing to post». A long video's folder (a
        # `video` flow, or any out/video.mp4 not uploaded) now stays until its upload is done, whatever
        # the flags say; only its drafts go.
        big_out = (d / "out" / "video.mp4").is_file()
        long_kind = bool(w and w.get("fkind") == "video")
        if not url and (long_kind or (w and w["yt"] == "queued") or (big_out and not pubs)):
            for sub in ("build", "ch"):
                if (d / sub).is_dir():
                    note("workshop drafts", str(d / sub), du(d / sub), "long video not uploaded yet: out/ kept")
                    rm(d / sub)
            continue
        if not pubs and not url and not quiet_for(d, NOPUB_QUIET_H * 60):
            continue
        note(
            "workshop folder",
            str(d),
            du(d),
            f"work {(w or {}).get('status', 'wiped')}, posted or nothing to post",
            youtube=url,
        )
        rm(d)
    for ref in homes:
        h, w = WS / ".hq" / ref, info.get(ref)
        if (WS / ref).exists() or (w and w["status"] not in ACTIVE_WORK):
            continue
        if quiet_for(h, HOME_QUIET_D * 24 * 60):
            note("job home", str(h), du(h), f"work {(w or {}).get('status', 'wiped')}, {HOME_QUIET_D} quiet days")
            rm(h)


# ------------------------------------------------------------------ 4. long upload copies
def long_tmps() -> None:
    for root in LONG_TMPS:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if d.is_dir() and REF.fullmatch(d.name):
                url = long_done(d.name)
                if url:
                    note("long upload copy", str(d), du(d), "uploaded", youtube=url)
                    rm(d)


# ------------------------------------------------------------------ 5. emergency
def used_pct() -> int:
    st = os.statvfs("/")
    return round(100 * (1 - st.f_bavail / st.f_blocks))


def emergency() -> None:
    pct = used_pct()
    if pct < EMERGENCY_PCT:
        return
    say(f"EMERGENCY: / is {pct}% used")
    sets = sorted(d for d in BACKUPS.iterdir() if d.is_dir() and re.fullmatch(r"\d{8}T\d{6}Z", d.name))
    for s in sets[:-1]:
        note("pg_dump set", str(s), du(s), f"emergency at {pct}%: the newest set, restic and Drive keep it")
        rm(s)
    if not DRY:
        subprocess.run(["docker", "builder", "prune", "-f", "--filter", "until=24h"], capture_output=True, timeout=900)
        subprocess.run(["journalctl", "--vacuum-size=200M"], capture_output=True, timeout=300)


def main() -> int:
    before = used_pct()
    for step in (posted_videos, posted_days_ago, workshop, long_tmps, emergency):
        try:
            step()
        except Exception as exc:  # one step failing never stops the others
            say(f"{step.__name__} failed: {exc}")
    after = used_pct()
    say(f"/ was {before}%, now {after}% ({freed / 1e9:.2f} GB {'would be ' if DRY else ''}freed)")
    if not DRY and TEXTFILE.parent.is_dir():
        tmp = TEXTFILE.with_suffix(".tmp")
        tmp.write_text(
            "# HELP hq_disk_guard_last_run_timestamp_seconds The last disk guard pass.\n"
            "# TYPE hq_disk_guard_last_run_timestamp_seconds gauge\n"
            f"hq_disk_guard_last_run_timestamp_seconds {int(time.time())}\n"
            "# HELP hq_disk_guard_freed_bytes Bytes the last pass freed.\n"
            "# TYPE hq_disk_guard_freed_bytes gauge\n"
            f"hq_disk_guard_freed_bytes {freed}\n"
        )
        os.chmod(tmp, 0o644)
        tmp.replace(TEXTFILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
