"""⟨2026-11-26⟩ Trial Reels: every reel a page publishes on Instagram goes out once more, the same
day, as an Instagram Trial Reel (the owner: shown to non-followers only, a trial for good: never
moved to the page's grid, so never a duplicate there; IG-Hub sends `trial_params` MANUAL, never
SS_PERFORMANCE).

The copy is the SAME reel, never made again (the owner's hard rule), changed very slightly so
Instagram does not take it for the same upload: made with ffmpeg (on the hub host: hq_api.trial_copy,
the coinepro-hq-trial-copy timer) from the reel's own video
(a 1.2-2 % centre zoom, a ~1 % shift of brightness/contrast/saturation, 2-4 frames off the start,
no metadata) at the reels' own top quality (x264 CRF 14, aq-mode 3, the VBV cap of 16 Mbit/s or
less so the file stays under ~180 MB, the same size and frame rate, BT.709, sound AAC 256k), with
its cover changed as slightly and its caption the same words (the hashtags in another order, a
small mark on the first line).

    tick()   the worker, every 5 minutes (hq-trial-reels): the trials of cancelled or failed
             reels are cancelled; then ONE reel without its trial (scheduled or out: its video is
             still on the disk, disk_guard keeps it for this) gets its copy and its `publish` job,
             set for its own hour:
               - the reel's own day (Tehran), at least GAP_OWN after the reel, between OPEN (08:10)
                 and LAST (23:40) (the owner's night rule: nothing 00:00-08:00), at least
                 GAP_FEED from the page's other reels and posts (scheduled, out, or still planned
                 by a flow; GAP_FEED_MIN when the day is too full), GAP_STORY from its stories,
                 picked at random among the hours that fit (seeded by the reel);
               - a reel out too late for that: the next morning on, by the same rules;
               - a day that went by (the hub was down): the next day still; later never.

Each trial is a row of media.publications with `source.trial_of` = its reel's ref (title «ریلز
آزمایشی · …»), and IG-Hub's publication says `trial`; no flow, no topic gate, no day rule ever
reads it (flows.PUBLISHED_SQL, DONE_SQL, REPEAT_SQL, tg_posts.REELS_SQL leave it out). One trial
per reel: the job's IG-Hub key is the same on every try (never posted twice); a trial that failed
is tried once more under a new key (TRIES), never more. A page Meta does not let post trials
(IG-Hub: `trial_not_eligible`, Meta 10/2207081) is left alone the rest of that day (Tehran), then
tried again every day (⟨2026-11-28⟩ the owner: «ریلز آزمایشی هر روز تست شود»; was every three
days) with ONE trial a day, its probe, until Meta lets one through; its reels are never touched.

⟨2026-11-28⟩ A page in PER_DAY (the owner: @oneoxxo 5 reels a day → 3 trials, @fxbyfx 4 → 2) gets
that many trials a day, not one per reel: copies of that many of the day's reels (the reel's own
Tehran day; out, scheduled or still planned by a flow), picked spread through the day (`spread`);
a picked reel that gets none (no hour, its video gone) leaves its place to a later one. Such a page's
day is full, so its trial may sit as close as GAP_FEED_TIGHT to its other reels and posts when no
hour two hours clear is left. Every other page: one trial per reel, as before.
Off: `trial_reels` in owner.settings.flows_off.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import audit
from hq_api import trial_copy as TC
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.domain import quiet_hours as QH
from hq_api.media import ff_input, run_tool

log = logging.getLogger("hq_api.trial_reels")

TEHRAN = ZoneInfo("Asia/Tehran")
SINCE = date(2026, 11, 27)  # the first day with trials (the owner's order of 2026-11-26)
OFF_KEY = "trial_reels"  # in owner.settings.flows_off: no trials
OPEN = QH.OPEN_AT  # 08:10 Tehran: IG-Hub's ±6 min stays after 08:00
LAST = time(23, 40)  # ±6 min stays the same day
GAP_OWN = timedelta(hours=2, minutes=30)
GAP_FEED = timedelta(hours=3)
GAP_FEED_MIN = timedelta(hours=2)
GAP_STORY = timedelta(minutes=20)
STEP = timedelta(minutes=5)
LEAD = timedelta(minutes=30)  # the copy is made and sent before its hour
LOOK_BACK = timedelta(hours=40)  # a reel of yesterday evening still gets its trial today
TRIES = 2
LOOK = 40  # reels read per tick (a capped page's reels without a trial stay among them)
# ⟨2026-11-28⟩ the owner: trials a day for these pages (any other page: one per reel)
PER_DAY: dict[str, int] = {"oneoxxo": 3, "fxbyfx": 2}
GAP_FEED_TIGHT = timedelta(hours=1)  # a PER_DAY page's full day: the last resort
FEED_STATES = ("scheduled", "publishing", "published", "held")
PROBE_LIMIT_S = 30.0
MARKS = ("👀", "✨", "📌", "🎬", "🔥")
HASHTAG = re.compile(r"(?<![\w#])#[\w‌]+")

# IG-Hub's word that Meta does not let the page post trials, as its command printed it (stderr of
# one of the trial's jobs): `trial_not_eligible`
CANDIDATES_SQL = """
SELECT p.id, p.ref, p.company_id, c.code AS company, p.account, p.state, p.title_fa, p.topic_fa,
       p.caption, p.files, p.chain, p.scheduled_at, p.published_at, p.external_id, p.at
  FROM media.publications p JOIN core.companies c ON c.id = p.company_id
 WHERE p.channel = 'instagram' AND p.kind = 'reel' AND NOT p.source ? 'trial_of'
   AND p.state = ANY(:states) AND p.at >= :lo
   AND NOT EXISTS (SELECT 1 FROM media.publications t WHERE t.source ->> 'trial_of' = p.ref
                    AND (t.state <> 'failed' OR EXISTS (
                        SELECT 1 FROM infra.server_job_events e WHERE e.job_id = ANY(t.chain)
                           AND e.type = 'stderr' AND e.data ->> 'text' LIKE '%trial_not_eligible%')))
   AND (SELECT count(*) FROM media.publications t WHERE t.source ->> 'trial_of' = p.ref) < :tries
   AND NOT EXISTS (SELECT 1 FROM media.publications t WHERE t.account = p.account
                    AND t.source ? 'trial_of' AND t.state = 'failed' AND t.updated_at > :refused_since
                    AND EXISTS (
                        SELECT 1 FROM infra.server_job_events e WHERE e.job_id = ANY(t.chain)
                           AND e.type = 'stderr' AND e.data ->> 'text' LIKE '%trial_not_eligible%'))
 ORDER BY p.at LIMIT :n"""
# a page's reels of one day (Tehran) and how many of them have (or still may get) their trial
DAY_REELS_SQL = """
SELECT ref, at FROM media.publications
 WHERE account = :a AND channel = 'instagram' AND kind = 'reel' AND NOT source ? 'trial_of'
   AND state = ANY(:states) AND at >= :lo AND at < :hi"""
USED_SQL = """
SELECT count(*) FROM (
  SELECT count(*) AS n, bool_or(t.state NOT IN ('cancelled', 'failed')) AS live,
         bool_or(t.state = 'failed') AS failed
    FROM media.publications t JOIN media.publications p ON p.ref = t.source ->> 'trial_of'
   WHERE t.account = :a AND t.source ? 'trial_of' AND p.at >= :lo AND p.at < :hi
   GROUP BY t.source ->> 'trial_of') x
 WHERE live OR (failed AND n < :tries)"""
# Meta's last refusal of a page's trial; then whether one went through since, and whether a trial
# of the page is still on its way or was made today (that day's probe)
REFUSED_SQL = """
SELECT max(t.updated_at) FROM media.publications t
 WHERE t.account = :a AND t.source ? 'trial_of' AND t.state = 'failed' AND EXISTS (
       SELECT 1 FROM infra.server_job_events e WHERE e.job_id = ANY(t.chain)
          AND e.type = 'stderr' AND e.data ->> 'text' LIKE '%trial_not_eligible%')"""
PROBE_SQL = """
SELECT EXISTS (SELECT 1 FROM media.publications t WHERE t.account = :a AND t.source ? 'trial_of'
                  AND t.state = 'published' AND t.published_at > :refused) AS through,
       EXISTS (SELECT 1 FROM media.publications t WHERE t.account = :a AND t.source ? 'trial_of'
                  AND (t.state IN ('scheduled', 'held', 'publishing') OR t.created_at >= :today))
         AS on_way"""
ORPHANS_SQL = """
SELECT t.ref, t.chain[1] AS job FROM media.publications t
  JOIN media.publications p ON p.ref = t.source ->> 'trial_of'
 WHERE t.source ? 'trial_of' AND t.state IN ('scheduled', 'held')
   AND p.state IN ('cancelled', 'failed')
   AND NOT EXISTS (SELECT 1 FROM infra.server_jobs j WHERE j.id = ANY(t.chain)
                    AND j.args -> 'meta' ? 'cancel' AND j.created_at > now() - interval '1 hour')"""
BUSY_SQL = """
SELECT kind, coalesce(published_at, scheduled_at, created_at) AS at FROM media.publications
 WHERE account = :a AND channel = 'instagram' AND state = ANY(:states) AND id <> :own
   AND coalesce(published_at, scheduled_at, created_at) BETWEEN :lo AND :hi"""
FIRST_JOB_SQL = "SELECT id, args, work_ref FROM infra.server_jobs WHERE id = :id"
FILE_SQL = """SELECT id, name, mime, size, storage_key, width, height, duration_s
  FROM files.files WHERE id = :id AND company_id = :co"""


@dataclass
class Source:
    """What the copy is made from: the reel's row, its first job's args, its video and cover."""

    row: dict[str, Any]
    args: dict[str, Any]
    video: dict[str, Any]
    video_path: Path
    cover: dict[str, Any] | None
    cover_path: Path | None
    n: int  # this try (1, or 2 after a failed one)


@dataclass
class Made:
    video: Path
    cover: Path | None
    width: int
    height: int
    duration_s: float | None
    recipe: dict[str, Any]
    kept: list[str] = field(default_factory=list)  # storage keys committed by _send


# ------------------------------------------------------------------ the hour --
def _at(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=TEHRAN).astimezone(UTC)


def pick_slot(
    *,
    own_at: datetime,
    feed: list[datetime],
    stories: list[datetime],
    now: datetime,
    seed: str,
    tight: bool = False,
) -> datetime | None:
    """The trial's hour (UTC): the reel's own day if it fits there, else the next morning on;
    None when neither day has one (or both went by). `tight` (a PER_DAY page): a day with no hour
    GAP_FEED_MIN clear takes its widest gap of at least GAP_FEED_TIGHT."""
    rng = random.Random(seed)  # noqa: S311 - a spread of hours, not a secret
    first_day = own_at.astimezone(TEHRAN).date()
    for day in (first_day, first_day + timedelta(days=1)):
        t, end = _at(day, OPEN), _at(day, LAST)
        fits: list[tuple[datetime, timedelta]] = []
        while t <= end:
            if t >= own_at + GAP_OWN and t >= now + LEAD and not QH.is_quiet(t):
                far = min((abs(t - x) for x in feed), default=timedelta(days=1))
                near_story = min((abs(t - x) for x in stories), default=timedelta(days=1))
                if near_story >= GAP_STORY:
                    fits.append((t, far))
            t += STEP
        good = [t for t, far in fits if far >= GAP_FEED]
        if good:
            return rng.choice(good)
        least = GAP_FEED_TIGHT if tight else GAP_FEED_MIN
        ok = [(t, far) for t, far in fits if far >= least]
        if ok:
            return max(ok, key=lambda x: (x[1], -x[0].timestamp()))[0]
    return None


def spread(n: int, k: int) -> set[int]:
    """Which of a day's `n` reels (in their order) get the day's `k` trials: spread through the
    day, the earlier of two equal picks (its trial still has its own day): 5/3 → 1st, 2nd, 4th;
    4/2 → 1st, 3rd."""
    return set(range(n)) if n <= k else {i * n // k for i in range(k)}


async def busy(
    tx: Tx, account: str, own_id: Any, around: datetime
) -> tuple[list[datetime], list[datetime]]:
    """The page's reels and posts (any, a trial too) and its stories near the reel's day, and what
    its flows still plan for that day and the next."""
    from hq_api.domain import publications as PB

    lo, hi = around - timedelta(days=1), around + timedelta(days=3)
    rows = await tx.all(BUSY_SQL, a=account, states=list(FEED_STATES), own=own_id, lo=lo, hi=hi)
    feed = [r["at"] for r in rows if r["kind"] != "story"]
    stories = [r["at"] for r in rows if r["kind"] == "story"]
    first = around.astimezone(TEHRAN).date()
    for day in (first, first + timedelta(days=1)):
        try:
            async with tx.conn.begin_nested():
                for p in await PB.planned_today(tx, day):
                    if p.account == account:
                        (stories if p.kind == "story" else feed).append(p.publish_at)
        except Exception:  # noqa: BLE001 - what is out or scheduled is still known
            log.warning("the flows' plan was not read", extra={"day": day.isoformat()})
    return feed, stories


# ------------------------------------------------------------------ the text --
def vary_caption(caption: str, seed: str) -> str:
    """The same words: the hashtags in another order (each where a hashtag was), and a small mark
    at the end of the first line (or the one there taken off)."""
    rng = random.Random(seed)  # noqa: S311
    text = caption.strip()
    tags = HASHTAG.findall(text)
    if len(tags) >= 2:
        order = tags[:]
        for _ in range(5):
            rng.shuffle(order)
            if order != tags:
                break
        it = iter(order)
        text = HASHTAG.sub(lambda _m: next(it), text)
    lines = text.split("\n")
    i = next((k for k, line in enumerate(lines) if line.strip()), None)
    if i is not None:
        line = lines[i].rstrip()
        ending = next((m for m in MARKS if line.endswith(m)), None)
        if ending is not None:
            lines[i] = line[: -len(ending)].rstrip()
        else:
            lines[i] = f"{line} {rng.choice(MARKS)}"
    out = "\n".join(lines)
    return out if len(out) <= 2200 else caption


# ------------------------------------------------------------------ the copy --
# The video is made on the hub host (hq_api.trial_copy: x264 on a 1080x1920 reel needs more memory
# than the worker holds): the worker asks in the file volume, the host makes it, the worker takes it.
# HQ_TRIAL_INLINE=1 (the tests) makes it here instead.
INLINE = os.environ.get("HQ_TRIAL_INLINE") == "1"
ASK_AGAIN = timedelta(hours=2)  # an ask nobody answered is written again
ERR_AGAIN = timedelta(hours=1)  # a failed copy is asked again


async def probe(path: Path) -> dict[str, Any]:
    code, out, _ = await run_tool(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
        *ff_input(path), limit_s=PROBE_LIMIT_S,
    )  # fmt: skip
    if code != 0:
        raise ValueError("ffprobe could not read the reel")
    return TC.info_of(json.loads(out or b"{}"))


def _cover_copy(src: Path, out: Path, r: dict[str, Any]) -> tuple[int, int]:
    from PIL import Image, ImageEnhance, ImageOps

    with Image.open(src) as raw:
        img = (ImageOps.exif_transpose(raw) or raw).convert("RGB")
    w, h = img.size
    dx, dy = int(w * r["cover_zoom"] / 2), int(h * r["cover_zoom"] / 2)
    img = img.crop((dx, dy, w - dx, h - dy)).resize((w, h), Image.Resampling.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(r["cover_light"])
    img = ImageEnhance.Contrast(img).enhance(1 + (r["cover_light"] - 1) / 2)
    img.save(out, "JPEG", quality=95, optimize=True, subsampling=0)
    return w, h


def _queue(hub: Any) -> Path:
    """<the file volume>/trial-copies (the host's hq_api.trial_copy reads it)."""
    q = Path(hub.storage.local_path("0" * 32)).parent.parent / TC.QUEUE
    q.mkdir(mode=0o700, exist_ok=True)
    return q


def _rid(src: Source) -> str:
    return f"{src.row['ref']}-{src.n}"


async def _inline_video(hub: Any, src: Source, r: dict[str, Any]) -> Path:
    info = await probe(src.video_path)
    out: Path = hub.storage.scratch()
    for crf in TC.CRF:
        code, _, err = await run_tool(
            *TC.ffmpeg_args(src.video_path, out, info, r, crf), limit_s=TC.ENCODE_LIMIT_S
        )
        if code != 0 or not await asyncio.to_thread(out.exists):
            await asyncio.to_thread(out.unlink, True)
            raise ValueError("ffmpeg: " + err.decode("utf-8", "replace")[-300:])
        if (await asyncio.to_thread(out.stat)).st_size <= TC.SIZE_MAX:
            r["crf"] = crf
            return out
    await asyncio.to_thread(out.unlink, True)
    raise ValueError("the copy stays past IG-Hub's 200 MB")


def _hosted(q: Path, rid: str, key: str, r: dict[str, Any], now: float) -> Path | None:
    """The host's copy when it is there; else the ask is (re)written and None."""
    done, err, ask = q / f"{rid}.mp4", q / f"{rid}.err", q / f"{rid}.json"
    if done.is_file() and done.stat().st_size > 0:
        return done
    if err.exists():
        if now - err.stat().st_mtime < ERR_AGAIN.total_seconds():
            return None
        log.warning(
            "the trial copy failed on the host", extra={"rid": rid, "why": err.read_text()[:300]}
        )
        err.unlink(missing_ok=True)
        ask.unlink(missing_ok=True)
    if not ask.exists() or now - ask.stat().st_mtime > ASK_AGAIN.total_seconds():
        tmp = q / f"{rid}.json.tmp"
        tmp.write_text(json.dumps({"key": key, "recipe": r}), encoding="utf-8")
        tmp.replace(ask)
    return None


async def make_copy(hub: Any, src: Source) -> Made | None:
    """The copy's files (the video in the file volume, the cover a scratch file), or None while
    the host is still making the video."""
    r = TC.recipe_of(f"{src.row['ref']}:{src.n}")
    if INLINE:
        video = await _inline_video(hub, src, r)
    else:
        q = await asyncio.to_thread(_queue, hub)
        got = await asyncio.to_thread(
            _hosted, q, _rid(src), str(src.video["storage_key"]), r, datetime.now(UTC).timestamp()
        )
        if got is None:
            return None
        video = got
    cover = None
    if src.cover_path is not None:
        cover = hub.storage.scratch()
        try:
            await asyncio.to_thread(_cover_copy, src.cover_path, cover, r)
        except Exception:  # noqa: BLE001 - a reel goes without its own cover (Meta picks a frame)
            log.warning("the trial's cover was not made", extra={"ref": src.row["ref"]})
            await asyncio.to_thread(cover.unlink, True)
            cover = None
    got_info = await probe(video)
    return Made(video, cover, got_info["width"], got_info["height"], got_info["duration_s"], r)


def _done_with(hub: Any, src: Source) -> None:
    """The ask and its leftovers go once the copy is in the store (or its reel has a trial)."""
    if INLINE:
        return
    q = _queue(hub)
    for ext in (".json", ".err", ".mp4", ".part"):
        (q / f"{_rid(src)}{ext}").unlink(missing_ok=True)


# ------------------------------------------------------------------ the tick --
def _j(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


async def is_on(tx: Tx) -> bool:
    off = await tx.scalar("SELECT flows_off FROM owner.settings WHERE id = 1")
    return OFF_KEY not in (off or [])


async def _source(tx: Tx, hub: Any, row: dict[str, Any]) -> Source | None:
    """The reel's video and cover still on the disk, and its first job; None when gone."""
    files = _j(row["files"]) or []
    video = next((f for f in files if f.get("role") == "video"), None)
    if video is None or not row["chain"]:
        return None
    job = await tx.first(FIRST_JOB_SQL, id=row["chain"][0])
    if job is None:
        return None
    vf = await tx.first(FILE_SQL, id=video["file_id"], co=row["company_id"])
    if vf is None or not vf["storage_key"]:
        return None
    vpath = Path(hub.storage.local_path(str(vf["storage_key"])))
    if not await asyncio.to_thread(vpath.is_file):
        return None
    cover = next((f for f in files if f.get("role") == "cover"), None)
    cf = await tx.first(FILE_SQL, id=cover["file_id"], co=row["company_id"]) if cover else None
    cpath = (
        Path(hub.storage.local_path(str(cf["storage_key"]))) if cf and cf["storage_key"] else None
    )
    if cpath is not None and not await asyncio.to_thread(cpath.is_file):
        cpath = None
    tried = await tx.scalar(
        "SELECT count(*) FROM media.publications WHERE source ->> 'trial_of' = :r", r=row["ref"]
    )
    return Source(
        row=row, args=_j(job["args"]) or {}, video=dict(vf), video_path=vpath,
        cover=dict(cf) if cf else None, cover_path=cpath, n=int(tried or 0) + 1,
    )  # fmt: skip


async def _slot(tx: Tx, row: dict[str, Any], now: datetime) -> datetime | None:
    own = row["published_at"] or row["scheduled_at"] or row["at"]
    feed, stories = await busy(tx, row["account"], row["id"], own)
    return pick_slot(
        own_at=own, feed=feed, stories=stories, now=now, seed=str(row["ref"]),
        tight=row["account"] in PER_DAY,
    )  # fmt: skip


def _day_of(t: datetime) -> tuple[datetime, datetime]:
    day = t.astimezone(TEHRAN).date()
    return _at(day, time(0, 0)), _at(day + timedelta(days=1), time(0, 0))


async def _probe_ok(tx: Tx, account: str, now: datetime) -> tuple[bool, bool]:
    """(may a trial of this page be made now, is the page on its daily probe). A page Meta refused
    gets none the day of the refusal, then one a day (none while one is on its way) until one is
    let through."""
    refused = await tx.scalar(REFUSED_SQL, a=account)
    if refused is None:
        return True, False
    today, _ = _day_of(now)
    if refused >= today:
        return False, True
    got = await tx.one(PROBE_SQL, a=account, refused=refused, today=today)
    if got["through"]:
        return True, False
    return not got["on_way"], True


async def _day_reels(
    tx: Tx, account: str, lo: datetime, hi: datetime
) -> list[tuple[datetime, str]]:
    """The page's reels of that day in their order: out or scheduled (their ref), and still to be
    made by its flows ("")."""
    from hq_api.domain import publications as PB

    out = [(r["at"], str(r["ref"])) for r in await tx.all(
        DAY_REELS_SQL, a=account, states=list(FEED_STATES), lo=lo, hi=hi)]  # fmt: skip
    try:
        async with tx.conn.begin_nested():
            for p in await PB.planned_today(tx, lo.astimezone(TEHRAN).date()):
                if p.account == account and p.kind == "reel" and lo <= p.publish_at < hi:
                    out.append((p.publish_at, ""))
    except Exception:  # noqa: BLE001 - the reels out or scheduled are still known
        log.warning("the flows' plan was not read", extra={"account": account})
    return sorted(out)


async def _cap_ok(tx: Tx, row: dict[str, Any]) -> bool:
    """A PER_DAY page: is this reel one of its day's picks (`spread`), or needed to reach the day's
    number; any other page: yes."""
    cap = PER_DAY.get(str(row["account"]))
    if cap is None:
        return True
    lo, hi = _day_of(row["published_at"] or row["scheduled_at"] or row["at"])
    used = int(await tx.scalar(USED_SQL, a=row["account"], lo=lo, hi=hi, tries=TRIES) or 0)
    if used >= cap:
        return False
    reels = await _day_reels(tx, str(row["account"]), lo, hi)
    i = next((k for k, (_, ref) in enumerate(reels) if ref == row["ref"]), None)
    if i is None:
        return True
    return i in spread(len(reels), cap) or len(reels) - i - 1 < cap - used


async def _allowed(tx: Tx, row: dict[str, Any], now: datetime) -> tuple[bool, bool]:
    """(may this reel's trial be made now, one at a time for its page: a capped page or one on
    its daily probe)."""
    ok, probing = await _probe_ok(tx, str(row["account"]), now)
    if not ok:
        return False, True
    capped = row["account"] in PER_DAY
    return await _cap_ok(tx, row), probing or capped


async def _cancel_orphans(tx: Tx) -> int:
    """A trial whose reel was cancelled or failed is cancelled too (asked once an hour at most)."""
    from hq_api.domain import session_publish as SPB

    n = 0
    for r in await tx.all(ORPHANS_SQL):
        try:
            async with tx.conn.begin_nested():
                await SPB.cancel(tx, SPB.SERVICE, UUID(str(r["job"])))
                n += 1
        except Exception:  # noqa: BLE001 - asked again next tick
            log.warning("a trial of a cancelled reel was not cancelled", extra={"ref": r["ref"]})
    return n


async def _plan(tx: Tx, hub: Any, now: datetime) -> list[Source]:
    """The reels whose trial is due to be made now (an hour is left for it, their video is
    still on the disk), oldest first."""
    lo = max(_at(SINCE, time(0, 0)), now - LOOK_BACK)
    rows = await tx.all(
        CANDIDATES_SQL, states=list(FEED_STATES), lo=lo, tries=TRIES,
        refused_since=_day_of(now)[0], n=LOOK,
    )  # fmt: skip
    out: list[Source] = []
    one_each: set[str] = set()  # pages whose trials are made one at a time (one this tick)
    for r in rows:
        row = dict(r)
        if row["account"] in one_each:
            continue
        if await gate.automation_lock(tx, row["company_id"]) is not None:
            continue
        ok, single = await _allowed(tx, row, now)
        if not ok:
            continue
        if await _slot(tx, row, now) is None:
            continue
        src = await _source(tx, hub, row)
        if src is not None:
            out.append(src)
            if single:
                one_each.add(str(row["account"]))
    return out


async def _send(tx: Tx, hub: Any, src: Source, made: Made, now: datetime) -> dict[str, Any] | None:
    """The copy's files and its `publish` job, in one transaction; None when its reel has a trial
    already, or no hour is left for it."""
    from hq_api.domain import files as F
    from hq_api.domain import session_publish as SPB

    row = src.row
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k="trial-page:" + row["account"]
    )
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k="trial:" + row["ref"])
    standing = await tx.scalar(
        "SELECT count(*) FROM media.publications WHERE source ->> 'trial_of' = :r", r=row["ref"]
    )
    if int(standing or 0) >= src.n:
        return None
    fresh = dict(await tx.one("SELECT * FROM media.publications WHERE id = :id", id=row["id"]))
    if fresh["state"] not in FEED_STATES:
        return None
    if not (await _allowed(tx, {**row, **fresh}, now))[0]:
        return None  # the page's day has its trials, or its probe is out
    slot = await _slot(tx, {**row, **fresh}, now)
    if slot is None:
        return None
    route = await SPB._route(tx, row["company_id"])
    if not route["ready"] or row["account"] not in route["accounts"]:
        return None
    key, sha, size = await hub.storage.commit(made.video)
    made.kept.append(key)
    vid = await F.insert(
        tx, company_id=row["company_id"], name="video_trial.mp4", mime="video/mp4", size=size,
        sha256=sha, storage_key=key, kind="video", by_kind="service", by_code=SPB.SERVICE.code,
        width=made.width, height=made.height, duration_s=made.duration_s,
        meta={"trial_of": str(src.video["id"]), "trial_of_publication": row["ref"],
              "recipe": made.recipe},
    )  # fmt: skip
    cover = None
    if made.cover is not None:
        ckey, csha, csize = await hub.storage.commit(made.cover)
        made.kept.append(ckey)
        cid = await F.insert(
            tx, company_id=row["company_id"], name="cover_trial.jpg", mime="image/jpeg",
            size=csize, sha256=csha, storage_key=ckey, kind="image", by_kind="service",
            by_code=SPB.SERVICE.code, width=(src.cover or {}).get("width"),
            height=(src.cover or {}).get("height"),
            meta={"trial_of": str((src.cover or {}).get("id")), "trial_of_publication": row["ref"]},
        )  # fmt: skip
        cover = {"id": cid, "name": "cover_trial.jpg", "mime": "image/jpeg"}
    s = src.args.get("session") or {}
    meta = src.args.get("meta") or {}
    d = {
        "ref": s.get("output") or row["ref"], "title": row["title_fa"],
        "company_id": row["company_id"], "company": row["company"], "work_ref": None,
    }  # fmt: skip
    ext = str(fresh.get("external_id") or "")
    caption = str(row["caption"] or src.args.get("caption") or "")
    j = await SPB._send(
        tx, SPB.SERVICE, d, {"id": vid, "name": "video_trial.mp4", "mime": "video/mp4"}, cover,
        hub=hub, what="reel", account=row["account"],
        caption=vary_caption(caption, f"{row['ref']}:{src.n}"),
        route=route, order=None, scheduled_at=slot,
        comment=meta.get("comment") if isinstance(meta.get("comment"), dict) else None,
        first_comment=meta.get("first_comment"),
        publication={"topic_fa": row["topic_fa"]} if row["topic_fa"] else None,
        trial={"of": row["ref"], "n": src.n, "day": slot.astimezone(TEHRAN).date().isoformat(),
               "of_ext": ext if ext and not ext.startswith("cancelled:") else None},
    )  # fmt: skip
    await audit.record(
        tx, SPB.SERVICE, company_id=row["company_id"], action="publish.trial", action_class="A2",
        target_kind="publication", target_ref=row["ref"],
        summary=(f"trial reel of {row['ref']} to @{row['account']} at {slot.isoformat()} "
                 f"(try {src.n}; job {j['id']}; recipe {json.dumps(made.recipe)})")[:500],
    )  # fmt: skip
    return {
        "reel": row["ref"],
        "account": row["account"],
        "at": slot.isoformat(),
        "job": str(j["id"]),
    }


async def tick(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """One turn: orphans cancelled; then each reel due a trial has its copy asked of the host, and
    each copy the host made is taken and sent, set for its hour (the module). `sent`: the first
    one sent (None: none)."""
    now = now or datetime.now(UTC)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if not await is_on(tx):
            return {"off": True}
        if (lock := await gate.holding_lock(tx)) is not None:
            return gate.skipped(lock)
        cancelled = await _cancel_orphans(tx)
        plans = await _plan(tx, hub, now)
    out: dict[str, Any] = {"cancelled": cancelled, "sent": None, "all": [], "making": []}
    for src in plans:
        try:
            made = await make_copy(hub, src)
        except Exception as exc:  # noqa: BLE001 - tried again next tick
            why = str(exc)[:300]
            log.warning("the trial copy was not made", extra={"ref": src.row["ref"], "why": why})
            out["error"] = why
            continue
        if made is None:
            out["making"].append(_rid(src))
            continue
        sent = await _take(hub, src, made)
        if sent:
            log.info("trial reel set", extra=sent)
            out["all"].append(sent)
            out["sent"] = out["sent"] or sent
        if INLINE:
            break  # one copy made here per turn
    return out


async def _take(hub: Any, src: Source, made: Made) -> dict[str, Any] | None:
    """The copy into the store and its job sent, in one transaction; the queue cleared after."""
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            sent = await _send(tx, hub, src, made, datetime.now(UTC))
    except Exception:
        for key in made.kept:  # stored for a transaction that did not commit
            with contextlib.suppress(Exception):
                await hub.storage.destroy(key)
        log.warning("the trial was not sent", extra={"ref": src.row["ref"]}, exc_info=True)
        return None
    finally:
        if made.cover is not None:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(made.cover.unlink, True)
        if INLINE:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(made.video.unlink, True)
    with contextlib.suppress(OSError):
        await asyncio.to_thread(_done_with, hub, src)
    return sent
