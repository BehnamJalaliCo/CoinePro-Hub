"""⟨1.31⟩ §49 The best hour to publish, by itself.

The owner's order (2026-11-10): «بعد از یک ماه صفحه را تحلیل کند و در ساعت‌های پربازدید طبق
زمان‌بندی منتشر کند». IG-Hub reads each account's posts from Meta; the hub reads them from IG-Hub
once a day (one read-only `exec` job on IG-Hub's server: the company's own publish command with
`posts <account>`, which prints IG-Hub's `GET /api/v1/posts`), keeps each post's numbers here
(`growth.ig_posts`: IG-Hub overwrites its own every 15 minutes and keeps no history), and
chooses the hour from them.

What is counted, said as it is: **likes and comments only**. IG-Hub does not read views, reach,
saves or shares (its code asks Meta for no insights), so «پربازدید» is, until it does, «the hour
whose posts drew the most likes and comments».

The rule, by code and never a model:
- the posts of the last WINDOW_DAYS that are at least SETTLE old (a fresh post is still counting);
- enough of them: MIN_POSTS over at least MIN_DAYS («بعد از یک ماه»);
- each hour of the owner's day scored by its posts' mean engagement, pulled toward the account's
  own mean by PRIOR (one lucky post does not make an hour), an hour needs HOUR_MIN posts;
- the best one; a tie goes to the hour with more posts, then the earlier.

Too little data is no fault and no blocker: the standing word then publishes at its fixed hour
when it has one, else as soon as the package is ready, and says which.
"""

from __future__ import annotations

import json
import logging
import shlex
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import order_report as OR
from hq_api.domain import servers as SV

log = logging.getLogger("hq_api.best_hour")

ACTOR = "best-hour"
WINDOW_DAYS = 90
SETTLE = timedelta(hours=48)
MIN_POSTS = 12
MIN_DAYS = 28
HOUR_MIN = 2
PRIOR = 2.0
READ_EVERY = timedelta(hours=20)
JOB_TIMEOUT_S = 120
JOB_STALE = timedelta(hours=2)
POSTS_LIMIT = 100
SOON = timedelta(minutes=2)

THIN_FA = (
    "هنوز داده‌ی کافی نیست ({posts} پست در {days} روز؛ دست‌کم {need} پست در {month} روز لازم است)"
)
BASIS_FA = "از روی لایک و کامنت {posts} پست در {days} روز اخیر (بازدید و reach هنوز خوانده نمیشود)"
NO_READ_FA = OR.BestHour().note_fa


BestHour = OR.BestHour


def command(publish_command: str, account: str) -> str:
    """The read-only command the hub runs on IG-Hub's server for one account's posts."""
    return f"{publish_command.strip()} posts {shlex.quote(account.lstrip('@'))} {POSTS_LIMIT}"


def _count(v: Any) -> int:
    return max(0, int(v)) if isinstance(v, int | float) and not isinstance(v, bool) else 0


def _cfg(raw: Any) -> dict[str, Any]:
    got = json.loads(raw) if isinstance(raw, str) else raw
    return dict(got) if isinstance(got, dict) else {}


def parse(text: str) -> list[dict[str, Any]] | None:
    """`{items: [{id, media_type, permalink, posted_at, like_count, comments_count}], hours}` as
    IG-Hub's command prints it: the posts, or None when the output is not that."""
    raw = text.strip()
    start = raw.find("{")
    try:
        data = json.loads(raw[start:]) if start >= 0 else None
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    out: list[dict[str, Any]] = []
    for it in data["items"][:500]:
        if not isinstance(it, dict):
            continue
        try:
            when = datetime.fromisoformat(str(it.get("posted_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        pid = str(it.get("id") or "").strip()
        if not pid or when.tzinfo is None:
            continue
        link = str(it.get("permalink") or "")
        out.append({
            "post_id": pid[:64], "posted_at": when,
            "media_type": str(it.get("media_type") or "")[:32] or None,
            "permalink": link[:500] if link.startswith("https://") else None,
            "likes": _count(it.get("like_count")), "comments": _count(it.get("comments_count")),
        })  # fmt: skip
    return out


async def store(tx: Tx, company_id: UUID, account: str, posts: list[dict[str, Any]]) -> int:
    for p in posts:
        await tx.exec(
            """INSERT INTO growth.ig_posts (company_id, account, post_id, media_type, permalink,
                   posted_at, likes, comments)
               VALUES (:co, :a, :p, :mt, :pl, :at, :l, :c)
               ON CONFLICT (company_id, account, post_id) DO UPDATE
               SET media_type = EXCLUDED.media_type, permalink = EXCLUDED.permalink,
                   posted_at = EXCLUDED.posted_at, likes = EXCLUDED.likes,
                   comments = EXCLUDED.comments, updated_at = now()""",
            co=company_id, a=account, p=p["post_id"], mt=p["media_type"], pl=p["permalink"],
            at=p["posted_at"], l=p["likes"], c=p["comments"],
        )  # fmt: skip
    return len(posts)


def choose(
    posts: list[tuple[datetime, int]], tz: str, now: datetime
) -> tuple[int | None, int, int]:
    """(the best hour of the owner's day or None, the posts counted, the days they span)."""
    from hq_api.domain.gov_common import zone

    z = zone(tz)
    used = [
        (t.astimezone(z), e)
        for t, e in posts
        if now - timedelta(days=WINDOW_DAYS) <= t <= now - SETTLE
    ]
    if not used:
        return None, 0, 0
    days = (max(t for t, _ in used) - min(t for t, _ in used)).days + 1
    if len(used) < MIN_POSTS or days < MIN_DAYS:
        return None, len(used), days
    mean = sum(e for _, e in used) / len(used)
    by: dict[int, list[int]] = {}
    for t, e in used:
        by.setdefault(t.hour, []).append(e)
    scored = [
        ((sum(v) + PRIOR * mean) / (len(v) + PRIOR), len(v), -h)
        for h, v in by.items()
        if len(v) >= HOUR_MIN
    ]
    if not scored:
        return None, len(used), days
    return -max(scored)[2], len(used), days


def next_at(hour: int, tz: str, now: datetime, *, tomorrow: bool = True) -> datetime | None:
    """The hour's next occurrence in the owner's zone. `tomorrow: False`: today only (None once
    it has passed: a standing package is never kept for the next day, when the next one comes)."""
    from hq_api.domain.gov_common import zone

    local = now.astimezone(zone(tz))
    t = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if t <= local + SOON:
        if not tomorrow:
            return None
        t += timedelta(days=1)
    return t.astimezone(UTC)


async def best(
    tx: Tx, company_id: UUID, account: str | None, tz: str, now: datetime | None = None
) -> BestHour:
    """Where a company's account stands. `account` None: the company's only registered one."""
    now = now or datetime.now(UTC)
    handle = (account or "").lstrip("@").lower()
    if not handle:
        return BestHour()
    read = await tx.first(
        "SELECT read_at FROM growth.ig_post_reads WHERE company_id = :co AND account = :a",
        co=company_id, a=handle,
    )  # fmt: skip
    rows = await tx.all(
        """SELECT posted_at, likes + comments AS e FROM growth.ig_posts
           WHERE company_id = :co AND account = :a
             AND posted_at > :since ORDER BY posted_at""",
        co=company_id, a=handle, since=now - timedelta(days=WINDOW_DAYS),
    )  # fmt: skip
    hour, n, days = choose([(r["posted_at"], int(r["e"])) for r in rows], tz, now)
    read_at = read["read_at"] if read else None
    if hour is None:
        note = (
            THIN_FA.format(posts=n, days=days, need=MIN_POSTS, month=MIN_DAYS)
            if read_at is not None or n
            else NO_READ_FA
        )
        return BestHour(account=handle, posts=n, days=days, note_fa=note, read_at=read_at)
    return BestHour(
        account=handle, hour=f"{hour:02d}:00", at=next_at(hour, tz, now), enough=True, posts=n,
        days=days, note_fa=BASIS_FA.format(posts=n, days=days), read_at=read_at,
    )  # fmt: skip


# ------------------------------------------------------------ the daily read --
async def _stdout(tx: Tx, job_id: UUID) -> str:
    lines = await tx.all(
        """SELECT data ->> 'text' AS text FROM infra.server_job_events
           WHERE job_id = :j AND type = 'stdout' ORDER BY seq""",
        j=job_id,
    )
    return "\n".join(str(r["text"] or "") for r in lines)


async def _note(tx: Tx, company_id: UUID, account: str, **cols: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    await tx.exec(
        f"""INSERT INTO growth.ig_post_reads (company_id, account, {names})
            VALUES (:co, :a, {values})
            ON CONFLICT (company_id, account) DO UPDATE SET {sets}""",  # noqa: S608 - column names from code
        co=company_id, a=account, **cols,
    )  # fmt: skip


async def read_one(
    tx: Tx, conn: dict[str, Any], account: str, now: datetime
) -> Literal["asked", "read", "waiting", "failed", "fresh", "skipped"]:
    """One account's daily read: collect the job that was asked, or ask a new one when the last
    read is old. The command is the company's own publish command with `posts <account>`."""
    cfg = _cfg(conn["config"])
    base = str(cfg.get("publish_command") or "").strip()
    handle = account.lstrip("@").lower()
    if not base or not handle:
        return "skipped"
    cmd = command(base, handle)
    if not CN.read_only(cmd):
        return "skipped"
    co = conn["company_id"]
    state = await tx.first(
        "SELECT * FROM growth.ig_post_reads WHERE company_id = :co AND account = :a FOR UPDATE",
        co=co, a=handle,
    )  # fmt: skip
    if state is not None and state["job_id"] is not None:
        job = await tx.first(
            "SELECT id, state, created_at FROM infra.server_jobs WHERE id = :id", id=state["job_id"]
        )
        if job is not None and job["state"] == "done":
            posts = parse(await _stdout(tx, job["id"]))
            if posts is None:
                await _note(tx, co, handle, job_id=None,
                            note_fa="خروجی دستور آمار IG-Hub خوانده نشد")  # fmt: skip
                return "failed"
            await store(tx, co, handle, posts)
            await _note(tx, co, handle, job_id=None, read_at=now, posts=len(posts), note_fa=None)
            return "read"
        live = job is not None and job["state"] in ("queued", "running", "awaiting_seal")
        if job is not None and live and job["created_at"] > now - JOB_STALE:
            return "waiting"
        await _note(tx, co, handle, job_id=None,
                    note_fa="دستور آمار روی IG-Hub انجام نشد؛ دوباره امتحان میشود")  # fmt: skip
        if job is not None and job["state"] not in ("queued", "running", "awaiting_seal"):
            return "failed"
    last = max(
        (t for t in ((state or {}).get("asked_at"), (state or {}).get("read_at")) if t is not None),
        default=None,
    )
    if last is not None and last > now - READ_EVERY:
        return "fresh"
    hubs = CN.ig_hub()
    srv_cfg = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    try:
        srv = await SV.load_server(
            tx, str((srv_cfg or {}).get("name") or hubs["server"]),
            company=str((srv_cfg or {}).get("company") or hubs["company"]),
        )  # fmt: skip
    except Exception:  # noqa: BLE001 - no such server yet: the technical team's work, not a fault here
        return "skipped"
    if SV.state_of(srv) != "online":
        return "skipped"
    j = await SV.create_job(
        tx,
        server=srv,
        kind="exec",
        args={"cmd": cmd, "timeout_s": JOB_TIMEOUT_S},
        actor_kind="service",
        actor_code=ACTOR,
        summary="read-only: the posts of one Instagram account, for the best hour (contract §49)",
        timeout_s=JOB_TIMEOUT_S,
    )
    await _note(tx, co, handle, job_id=j["id"], asked_at=now)
    return "asked"


async def read_due(hub: Any, now: datetime | None = None) -> dict[str, int]:
    """Every company whose Instagram publish path is registered: each account's posts, once a
    day. Each account in its own savepoint; never raises."""
    now = now or datetime.now(UTC)
    out = {"asked": 0, "read": 0, "waiting": 0, "failed": 0}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        conns = await tx.all(
            """SELECT c.company_id, c.config FROM growth.connections c
               JOIN core.companies co ON co.id = c.company_id
               WHERE c.kind = 'instagram' AND co.status = 'active'
                 AND c.config ->> 'publish_command' IS NOT NULL"""
        )
        for conn in conns:
            cfg = _cfg(conn["config"])
            for account in [str(a) for a in cfg.get("accounts") or []][:20]:
                try:
                    async with tx.conn.begin_nested():
                        got = await read_one(tx, dict(conn), account, now)
                    if got in out:
                        out[got] += 1
                except Exception:  # noqa: BLE001 - one account never stops the others
                    log.warning("best-hour read failed", extra={"account": account})
    return out
