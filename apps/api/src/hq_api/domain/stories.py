"""Stories (contract §18.12, prompt 08 §9): the owner follows the companies the
way one follows accounts, a ring per company above «فرمان».

System stories, once per event (`event_key`): `hire` (every approved hire),
`deliverable` (the owner rated it 9-10), `stars` (Saturday's roll-up: the best
company and its best employee). A `milestone` from the system needs a KPI
store, which does not exist yet: CEOs post milestones with their evidence.
CEO stories (`story.post`): at most 3 per company per owner day, redacted, an
image only from the company's own files, no outside links. A story lives 24 h,
then moves to the company's archive. Stories are pulled, never pushed.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common.redact import scrub

DAILY_LIMIT = 3
TITLE_MAX = 60
BODY_MAX = 280
LINK_KEYS = ("employee", "deliverable", "decision", "work", "period", "metric")
PERIOD = r"^(week|month):[0-9]{4}-[0-9]{2}(-[0-9]{2})?$"  # as a lesson's period
METRIC = r"^[a-z][a-z0-9_]{1,40}$"  # a metric (KPI) by name, e.g. users_active
# A link out of the hub, with or without a scheme (contract §18.15): a URL
# scheme, `www.`, a host with a path (t.me/x, evil.com/promo), or a bare host
# under a common top-level domain (evil.com). Names like Next.js stay text.
TLDS = (
    "com|net|org|io|me|ir|co|app|dev|xyz|info|biz|ru|top|site|online|link|ly|gg|tv|to|"
    "us|uk|de|fr|ae|tr|in|cn|ai|so|cc|ws|pro|shop|store|live|news|blog|club|vip|cloud"
)
OUTSIDE = re.compile(
    r"(https?://|\bwww\.|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}/"
    rf"|\b(?:[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.)+(?:{TLDS})\b)",
    re.IGNORECASE,
)
# Hidden from the rings and the archive: a story the overseer holds, and one
# whose hold the owner cancelled (cancel = the story is withdrawn, §18.15).
NOT_HELD = """NOT EXISTS (SELECT 1 FROM oversight.holds h WHERE h.target_kind = 'story'
                                AND h.target_ref = s.ref AND h.state IN ('held', 'cancelled'))"""
REFS = {
    "work": ("work.work", r"^W-[0-9]{6,}$"),
    "deliverable": ("cartable.deliverables", r"^O-[0-9]{6,}$"),
    "decision": ("cartable.decisions", r"^D-[0-9]{6,}$"),
}

STORY_SQL = """
    SELECT s.*, c.code AS company FROM owner.stories s JOIN core.companies c ON c.id = s.company_id
"""


def short(n: float | int | None) -> str:
    """A short figure: 1.6M, 820K, 42."""
    if n is None:
        return "-"
    v = float(n)
    for unit, size in (("M", 1_000_000), ("K", 1_000)):
        if abs(v) >= size:
            return f"{v / size:.1f}".rstrip("0").rstrip(".") + unit
    return f"{v:.0f}" if v == int(v) else f"{v:.2f}"


def figures_ok(figures: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"label_fa": str(f["label_fa"])[:40], "value": str(f["value"])[:16]}
        for f in figures[:3]
        if str(f.get("label_fa") or "").strip() and str(f.get("value") or "").strip()
    ]


async def system(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    kind: str,
    title_fa: str,
    body_fa: str,
    figures: list[dict[str, Any]],
    links: dict[str, str],
    event_key: str,
) -> str | None:
    """A system story, once per event (a second call for the same event does
    nothing). Returns the new ref, or None when it already existed."""
    ref: str | None = await tx.scalar(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa, body_fa,
               figures, links, event_key)
           VALUES (:co, :kind, 'service', 'system', :t, :b, CAST(:f AS jsonb), CAST(:l AS jsonb), :key)
           ON CONFLICT (event_key) DO NOTHING RETURNING ref""",
        co=company_id,
        kind=kind,
        t=scrub(title_fa)[:TITLE_MAX],
        b=scrub(body_fa)[:BODY_MAX],
        f=json.dumps(figures_ok(figures), ensure_ascii=False),
        l=json.dumps({k: v for k, v in links.items() if k in LINK_KEYS and v}),
        key=event_key[:120],
    )
    if ref:
        await events.emit(
            tx, company_code, "story.created", ref, {"kind": kind, "author": "system"}
        )
    return ref


async def post(
    tx: Tx,
    who: Principal,
    *,
    kind: str,
    title_fa: str,
    body_fa: str,
    figures: list[dict[str, Any]],
    file_id: UUID | None,
    links: dict[str, str],
) -> dict[str, Any]:
    """A CEO's (or a holding head's) story in its own company (story.post)."""
    assert who.company_id is not None
    title, body = scrub(title_fa.strip()), scrub(body_fa.strip())
    if (
        OUTSIDE.search(title)
        or OUTSIDE.search(body)
        or any(
            OUTSIDE.search(str(f.get("value", "")) + str(f.get("label_fa", ""))) for f in figures
        )
    ):
        raise ApiError(422, "validation_failed", fields={"body_fa": "no outside links in a story"})
    clean_links: dict[str, str] = {}
    for key, value in links.items():
        if key not in LINK_KEYS or not value:
            continue
        if key in ("period", "metric"):
            if not re.fullmatch(PERIOD if key == "period" else METRIC, value) or OUTSIDE.search(
                value
            ):
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={
                        f"links.{key}": "week:YYYY-MM-DD or month:YYYY-MM"
                        if key == "period"
                        else "a metric by name (lowercase, digits, _)"
                    },
                )
        elif key in REFS:
            table, pattern = REFS[key]
            if not re.fullmatch(pattern, value) or not await tx.scalar(
                f"SELECT 1 FROM {table} WHERE ref = :r AND company_id = :co",  # noqa: S608 - fixed tables
                r=value,
                co=who.company_id,
            ):
                raise ApiError(
                    422, "validation_failed", fields={f"links.{key}": "unknown in your company"}
                )
        elif key == "employee" and not await tx.scalar(
            "SELECT 1 FROM core.employees WHERE code = :c AND company_id = :co",
            c=value,
            co=who.company_id,
        ):
            raise ApiError(
                422, "validation_failed", fields={"links.employee": "unknown in your company"}
            )
        clean_links[key] = value[:40]
    figs = figures_ok(figures)
    # A milestone links its evidence: work, a deliverable or a metric (with its
    # figure); a figure alone is a claim, not evidence (contract §18.15).
    if kind == "milestone" and not (
        clean_links.get("work")
        or clean_links.get("deliverable")
        or (clean_links.get("metric") and figs)
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"links": "a milestone links work, a deliverable or a metric with its figure"},
        )
    if file_id is not None:
        f = await tx.first(
            "SELECT company_id, kind, variant FROM files.files WHERE id = :id", id=file_id
        )
        if f is None or f["company_id"] != who.company_id:
            raise ApiError(403, "policy_denied", "an image of your own company's files only")
        if f["kind"] != "image" or f["variant"] != "original":
            raise ApiError(422, "validation_failed", fields={"file_id": "an image"})
    # The owner's day, the company's agent stories: a lock per company keeps
    # the limit exact under concurrent posts.
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))",
        key=f"story:{who.company_id}",
    )
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    today = await tx.scalar("SELECT (now() AT TIME ZONE :tz)::date", tz=tz)
    posted = await tx.scalar(
        """SELECT count(*) FROM owner.stories
           WHERE company_id = :co AND author_kind = 'agent'
             AND (created_at AT TIME ZONE :tz)::date = :today""",
        co=who.company_id,
        tz=tz,
        today=today,
    )
    if int(posted) >= DAILY_LIMIT:
        raise ApiError(429, "story_limit")
    row = await tx.one(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa, body_fa,
               figures, media_file_id, links)
           VALUES (:co, :kind, 'agent', :code, :t, :b, CAST(:f AS jsonb), :file, CAST(:l AS jsonb))
           RETURNING id""",
        co=who.company_id,
        kind=kind,
        code=who.code,
        t=title[:TITLE_MAX],
        b=body[:BODY_MAX],
        f=json.dumps(figs, ensure_ascii=False),
        file=file_id,
        l=json.dumps(clean_links),
    )
    story = await tx.one(STORY_SQL + " WHERE s.id = :id", id=row["id"])
    await events.emit(
        tx, story["company"], "story.created", story["ref"], {"kind": kind, "author": who.code}
    )
    return dict(story)


async def live(tx: Tx) -> list[dict[str, Any]]:
    # A story the overseer holds (contract §18.1 hold kind `story`) is not shown
    # until the owner releases it.
    rows = await tx.all(
        STORY_SQL + " WHERE s.expires_at > now() AND " + NOT_HELD + " ORDER BY s.created_at, s.id"
    )
    return [dict(r) for r in rows]


def rings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One ring per company: unseen ones first, then the latest; items oldest first."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["company"], []).append(r)
    out = [
        {
            "company": company,
            "unseen": sum(1 for x in items if x["seen_at"] is None),
            "latest_at": max(x["created_at"] for x in items),
            "items": items,
        }
        for company, items in by.items()
    ]
    out.sort(key=lambda g: (g["unseen"] == 0, -g["latest_at"].timestamp()))
    return out
