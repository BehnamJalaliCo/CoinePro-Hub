"""⟨1.37⟩ Contract §59.9 (prompt 38): what a flow run's publication did, read by code.

One `growth.run_results` row per flow run that published (a `lines.runs` row of a flow's line with
entries in `published`). Its figures are read, never guessed (a figure nobody gave stays null and
the apps show «—»):

- likes and comments: the post's own numbers that IG-Hub already gives the hub (§49.1,
  `growth.ig_posts`, read once a day by domain/best_hour.py);
- everything IG-Hub's `stats` command prints (IGHUB_04, not on IG-Hub yet): one read-only `exec`
  job on IG-Hub's server, `<publish command> stats <media_id> [rule_key …]`, which prints ONE line
  `{"post": {id, permalink, media_type, posted_at, like_count, comments_count, reach, views, saved,
  shares, read_at}, "rules": {"<key>": {sent, clicks, last_sent_at}}}`. `parse_stats` is the one
  place that reads it; until IG-Hub has the command its job fails and those figures stay null
  (asked again at most every STATS_BACKOFF while the last one failed).

When: every hour for the first day after the post went out, then at 24 h and at 7 days
(`next_read_at`; null once the 7-day read is asked). The hourly connections' read
(`hq-connections-read`, worker/growth_activities.py) calls `read_due`; it never raises.
"""

from __future__ import annotations

import json
import logging
import shlex
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import servers as SV
from hq_api.domain.flow_shapes import RunResults

log = logging.getLogger("hq_api.run_results")

ACTOR = "run-results"
HOURLY_FOR = timedelta(hours=24)
WEEK = timedelta(days=7)
LOOKBACK = timedelta(days=8)  # a run older than its last read is never picked up again
JOB_TIMEOUT_S = 120
JOB_STALE = timedelta(hours=2)
STATS_BACKOFF = timedelta(hours=6)
RULES_MAX = 20
FIGURES = ("comments", "dms_sent", "clicks", "views", "reach", "likes", "saves", "shares")


# ----------------------------------------------------------------- the shapes --
def _j(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def _count(v: Any) -> int | None:
    """A figure as IG-Hub gave it: a whole number >= 0, else None (never 0 for «not read»)."""
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return max(0, int(v))


def _link(v: Any) -> str | None:
    s = str(v or "").strip()
    return s[:1000] if s.startswith("https://") else None


def _when(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def entries(published: Any) -> list[dict[str, Any]]:
    """A run's `published` entries ({platform, kind, external_id, at, url, permalink?})."""
    got = _j(published)
    return [p for p in got if isinstance(p, dict)] if isinstance(got, list) else []


def main_entry(published: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(the post or reel, the story) a run published, each its first."""
    items = entries(published)
    story = next((p for p in items if p.get("kind") == "story"), None)
    post = next((p for p in items if p.get("kind") != "story"), None)
    return post, story


def permalink_of(entry: dict[str, Any] | None) -> str | None:
    if entry is None:
        return None
    return _link(entry.get("permalink")) or _link(entry.get("url"))


def render(row: dict[str, Any] | None) -> RunResults | None:
    if row is None:
        return None
    return RunResults(
        permalink=row.get("permalink"),
        story_permalink=row.get("story_permalink"),
        read_at=row.get("read_at"),
        **{k: row.get(k) for k in FIGURES},
    )


async def results_of(tx: Tx, run_ids: list[UUID]) -> dict[UUID, RunResults]:
    """The figures of these runs (only the runs that have a row: a run that did not publish has
    none)."""
    if not run_ids:
        return {}
    rows = await tx.all(
        "SELECT * FROM growth.run_results WHERE run_id = ANY(CAST(:ids AS uuid[]))",
        ids=[str(i) for i in run_ids],
    )
    out: dict[UUID, RunResults] = {}
    for r in rows:
        got = render(r)
        if got is not None:
            out[r["run_id"]] = got
    return out


# ---------------------------------------------------------------- IG-Hub stats --
def stats_command(publish_command: str, media_id: str, rule_keys: list[str]) -> str:
    """The read-only command for one post's figures (IGHUB_04 `stats`)."""
    keys = "".join(" " + shlex.quote(k) for k in rule_keys[:RULES_MAX])
    return f"{publish_command.strip()} stats {shlex.quote(media_id)}{keys}"


def parse_stats(text: str) -> dict[str, Any] | None:
    """IG-Hub's `stats` line → the figures it gives (a key it does not give is None), or None when
    the output is not that line. dms_sent and clicks are the sums over the rules it names (None
    when no rule gave a number)."""
    raw = text.strip()
    start = raw.find("{")
    try:
        data = json.loads(raw[start:]) if start >= 0 else None
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("post"), dict):
        return None
    post = data["post"]
    given = data.get("rules")
    rules: dict[str, Any] = given if isinstance(given, dict) else {}

    def total(key: str) -> int | None:
        got = [_count(r.get(key)) for r in rules.values() if isinstance(r, dict)]
        nums = [n for n in got if n is not None]
        return sum(nums) if nums else None

    return {
        "permalink": _link(post.get("permalink")),
        "likes": _count(post.get("like_count")),
        "comments": _count(post.get("comments_count")),
        "views": _count(post.get("views")),
        "reach": _count(post.get("reach")),
        "saves": _count(post.get("saved")),
        "shares": _count(post.get("shares")),
        "dms_sent": total("sent"),
        "clicks": total("clicks"),
    }


async def rule_keys(tx: Tx, media_ids: list[str]) -> list[str]:
    """The keys of the rules the hub sent for these posts (session_publish.queue_rule:
    `rule:<trigger>:<media id>:<words>`)."""
    ids = [m for m in media_ids if m]
    if not ids:
        return []
    rows = await tx.all(
        """SELECT DISTINCT j.args -> 'meta' ->> 'key' AS key FROM infra.server_jobs j
           WHERE j.kind = 'publish' AND j.args -> 'meta' ->> 'kind' = 'rule'
             AND split_part(j.args -> 'meta' ->> 'key', ':', 3) = ANY(:ids)
           ORDER BY 1 LIMIT :n""",
        ids=ids,
        n=RULES_MAX,
    )
    return [str(r["key"]) for r in rows if r["key"]]


async def _stdout(tx: Tx, job_id: UUID) -> str:
    lines = await tx.all(
        """SELECT data ->> 'text' AS text FROM infra.server_job_events
           WHERE job_id = :j AND type = 'stdout' ORDER BY seq""",
        j=job_id,
    )
    return "\n".join(str(r["text"] or "") for r in lines)


async def _backing_off(tx: Tx, now: datetime) -> bool:
    """IG-Hub refused the last `stats` (it has no such command yet): not asked again so soon."""
    last = await tx.first(
        """SELECT state, created_at FROM infra.server_jobs
           WHERE kind = 'exec' AND actor_code = :a AND state IN ('done', 'failed', 'cancelled')
           ORDER BY created_at DESC LIMIT 1""",
        a=ACTOR,
    )
    return last is not None and last["state"] != "done" and last["created_at"] > now - STATS_BACKOFF


def next_read(base: datetime, now: datetime) -> datetime | None:
    """Hourly for the first day after the post, then at 24 h and at 7 days, then never."""
    if now < base + HOURLY_FOR:
        return min(now + timedelta(hours=1), base + HOURLY_FOR)
    if now < base + WEEK:
        return base + WEEK
    return None


# ------------------------------------------------------------------ the rows --
CANDIDATES_SQL = """
SELECT r.id, r.company_id, r.published, r.ended_at, r.at, a.ref AS automation
FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
JOIN growth.automations a ON a.kind = 'flow' AND a.line = l.ref
WHERE r.dry = false AND jsonb_array_length(r.published) > 0 AND r.at > :since
  AND NOT EXISTS (SELECT 1 FROM growth.run_results x WHERE x.run_id = r.id)
ORDER BY r.at LIMIT 200"""


async def ensure_rows(tx: Tx, now: datetime) -> int:
    """A row (due now) for each flow run that published and has none yet."""
    made = 0
    for r in await tx.all(CANDIDATES_SQL, since=now - LOOKBACK):
        post, story = main_entry(r["published"])
        made += await tx.exec(
            """INSERT INTO growth.run_results (run_id, company_id, automation, permalink,
                   story_permalink, next_read_at)
               VALUES (:r, :co, :a, :pl, :spl, :n) ON CONFLICT (run_id) DO NOTHING""",
            r=r["id"], co=r["company_id"], a=r["automation"], pl=permalink_of(post),
            spl=permalink_of(story), n=now,
        )  # fmt: skip
    return made


async def _apply(tx: Tx, run_id: UUID, figures: dict[str, Any], read_at: datetime) -> None:
    """Writes the figures that were given (None never overwrites a number read before)."""
    given = {k: v for k, v in figures.items() if v is not None and k in (*FIGURES, "permalink")}
    sets = "".join(f", {k} = :{k}" for k in given)
    await tx.exec(
        f"UPDATE growth.run_results SET read_at = :t{sets} WHERE run_id = :r",  # noqa: S608 - names from code
        r=run_id, t=read_at, **given,
    )  # fmt: skip


async def read_one(tx: Tx, row: dict[str, Any], now: datetime) -> str:
    """One run's read: collect IG-Hub's answer to the last `stats` asked, take the post's likes
    and comments the hub already has (§49.1), and when it is due, ask the next `stats`."""
    run = await tx.first(
        "SELECT published, ended_at, at FROM lines.runs WHERE id = :r", r=row["run_id"]
    )
    if run is None:
        return "skipped"
    post, story = main_entry(run["published"])
    media = str((post or {}).get("external_id") or "")
    story_media = str((story or {}).get("external_id") or "")
    found = {"permalink": permalink_of(post)}
    if row.get("story_permalink") is None and permalink_of(story):
        await tx.exec(
            "UPDATE growth.run_results SET story_permalink = :s WHERE run_id = :r",
            s=permalink_of(story), r=row["run_id"],
        )  # fmt: skip
    cfg = await tx.first(
        """SELECT c.config, co.code FROM growth.connections c JOIN core.companies co
               ON co.id = c.company_id
           WHERE c.company_id = :co AND c.kind = 'instagram'""",
        co=row["company_id"],
    )
    conf = _j(cfg["config"]) if cfg is not None else {}
    conf = conf if isinstance(conf, dict) else {}
    base = CN.publish_command_of(conf) or ""
    cmd = stats_command(base, media, []) if base and media else ""
    state = "fresh"
    if cmd:
        job = await tx.first(
            """SELECT id, state, created_at, finished_at FROM infra.server_jobs
               WHERE kind = 'exec' AND actor_code = :a AND args ->> 'cmd' LIKE :p
               ORDER BY created_at DESC LIMIT 1""",
            a=ACTOR, p=cmd.replace("%", r"\%").replace("_", r"\_") + "%",
        )  # fmt: skip
        if (
            job is not None
            and job["state"] == "done"
            and (row.get("read_at") is None or (job["finished_at"] or now) > row["read_at"])
        ):
            got = parse_stats(await _stdout(tx, job["id"]))
            if got is not None:
                await _apply(tx, row["run_id"], got, job["finished_at"] or now)
                state = "read"
        live = job is not None and job["state"] in ("queued", "running", "awaiting_seal")
        if live and job is not None and job["created_at"] > now - JOB_STALE:
            return "waiting"
    if row["next_read_at"] is None or row["next_read_at"] > now:
        return state
    # due: the numbers the hub already has, then the next question to IG-Hub
    if media:
        ig = await tx.first(
            """SELECT likes, comments, permalink FROM growth.ig_posts
               WHERE company_id = :co AND post_id = :p ORDER BY updated_at DESC LIMIT 1""",
            co=row["company_id"], p=media,
        )  # fmt: skip
        if ig is not None:
            found |= {"likes": ig["likes"], "comments": ig["comments"]}
            found["permalink"] = found["permalink"] or _link(ig["permalink"])
            await _apply(tx, row["run_id"], found, now)
            state = "read"
        elif found["permalink"] and row.get("permalink") is None:
            await tx.exec(
                "UPDATE growth.run_results SET permalink = :p WHERE run_id = :r",
                p=found["permalink"], r=row["run_id"],
            )  # fmt: skip
    asked = await _ask(tx, row, conf, cfg["code"] if cfg else None, base, media, story_media, now)
    when = _when(post.get("at")) if post else None
    nxt = next_read(when or run["ended_at"] or row["created_at"], now)
    await tx.exec(
        """UPDATE growth.run_results SET reads = reads + 1, next_read_at = :n
           WHERE run_id = :r""",
        n=nxt, r=row["run_id"],
    )  # fmt: skip
    return "asked" if asked else state


async def _ask(
    tx: Tx, row: dict[str, Any], conf: dict[str, Any], company: str | None, base: str,
    media: str, story_media: str, now: datetime,
) -> bool:  # fmt: skip
    """One read-only `stats` job on IG-Hub's server, when the company's path is there."""
    if not base or not media or await _backing_off(tx, now):
        return False
    cmd = stats_command(base, media, await rule_keys(tx, [media, story_media]))
    if not CN.read_only(cmd):
        return False
    where = CN.ig_server(conf, company)
    if where is None:
        return False
    try:
        srv = await SV.load_server(tx, where[1], company=where[0])
    except Exception:  # noqa: BLE001 - no such server yet: the technical team's work, not a fault here
        return False
    if SV.state_of(srv) != "online":
        return False
    await SV.create_job(
        tx,
        server=srv,
        kind="exec",
        args={"cmd": cmd, "timeout_s": JOB_TIMEOUT_S},
        actor_kind="service",
        actor_code=ACTOR,
        summary="read-only: what one post of a flow did (contract §59.9)",
        timeout_s=JOB_TIMEOUT_S,
    )
    return True


async def read_due(hub: Any, now: datetime | None = None) -> dict[str, int]:
    """Hourly: rows for the flow runs that published, then each due row (or one with a `stats`
    answer to collect) read; each run in its own savepoint; never raises."""
    now = now or datetime.now(UTC)
    out = {"made": 0, "asked": 0, "read": 0, "waiting": 0, "failed": 0}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        try:
            async with tx.conn.begin_nested():
                out["made"] = await ensure_rows(tx, now)
        except Exception:  # noqa: BLE001 - the reads below still run
            log.warning("run results: new rows failed")
        rows = await tx.all(
            """SELECT * FROM growth.run_results
               WHERE (next_read_at IS NOT NULL AND next_read_at <= :now)
                  OR (created_at > :since AND (read_at IS NULL OR read_at < :hour))
               ORDER BY next_read_at NULLS LAST LIMIT 200""",
            now=now, since=now - LOOKBACK, hour=now - timedelta(minutes=50),
        )  # fmt: skip
        for row in rows:
            try:
                async with tx.conn.begin_nested():
                    got = await read_one(tx, row, now)
                if got in out:
                    out[got] += 1
            except Exception:  # noqa: BLE001 - one run never stops the others
                out["failed"] += 1
                log.warning("run results read failed", extra={"run": str(row["run_id"])})
    return out
