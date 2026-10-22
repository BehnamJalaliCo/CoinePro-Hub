"""The change and release calendar (prompt 11 §9, contract §20.9, M6).

events     governance.calendar_events (CE-0001). Code fills it: a deploy card
           with a window (at its proposal), the deploy freezes, the hub's
           nightly backup and weekly restore test, the official holidays
           (apps/api/seed/calendar/holidays.yaml); campaigns and events come
           from calendar.add (the CEO, the GROWTH manager, a holding head) or
           the owner. Holding-wide events belong to the holding.
conflicts  code, with a severity:
             a deploy inside a freeze                             high
             a deploy during the same company's campaign or event high
             two deploys of one company or one service (repo)     medium
             a deploy on a blackout day (authority matrix)        medium
             a deploy on a holiday                                medium
             maintenance during a deploy                          medium
           A deploy card carries its conflicts in payload.calendar_conflicts
           and risk_note; every new conflict is a `calendar.conflict` event.
           The calendar never decides: the card stays the owner's (PR-113
           looks at deploys that went ahead with a `high` conflict).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gov_authority as AU
from hq_api.domain import gov_common as G
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

HOLIDAYS_FILE = Path(__file__).resolve().parents[3] / "seed" / "calendar" / "holidays.yaml"
Kind = Literal["deploy", "campaign", "event", "maintenance", "meeting", "freeze", "holiday"]
AGENT_KINDS = ("campaign", "event", "maintenance")
WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday() order
BACKUP_AHEAD_DAYS = 14
NIGHTLY = (time(2, 30), timedelta(minutes=30), "UTC", "پشتیبان کامل شبانه‌ی هاب")
RESTORE = (time(6, 0), timedelta(hours=1), "Asia/Tehran", "تست بازیابی هفتگی هاب")
FAR = timedelta(days=400)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str | None = Field(default=None, pattern=r"^D-[0-9]{4,}$")
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")
    meeting: str | None = Field(default=None, pattern=r"^MT-[0-9]{4,}$")
    order: str | None = Field(default=None, max_length=40)


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    kind: Kind
    title_fa: str = Field(min_length=1, max_length=300)
    starts_at: datetime
    ends_at: datetime
    source: SourceRef = Field(default_factory=SourceRef)
    risk: Literal["low", "medium", "high"] = "low"

    @model_validator(mode="after")
    def _order(self) -> EventIn:
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at is before starts_at")
        if self.ends_at - self.starts_at > FAR:
            raise ValueError("at most 400 days")
        return self


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: str | None = Field(default=None, min_length=1, max_length=300)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: Literal["planned", "done", "cancelled"] | None = None
    risk: Literal["low", "medium", "high"] | None = None


class CalendarEvent(BaseModel):
    id: UUID
    ref: str
    company: str | None
    kind: str
    title_fa: str
    starts_at: datetime
    ends_at: datetime
    source: dict[str, Any]
    status: str
    risk: str
    created_by: Actor
    version: int


class Conflict(BaseModel):
    a: str
    b: str
    rule: str
    severity: Literal["medium", "high"]
    note_fa: str


class Calendar(BaseModel):
    events: list[CalendarEvent]
    conflicts: list[Conflict]


SQL = """
    SELECT e.*, c.code AS company, c.kind AS company_kind FROM governance.calendar_events e
    JOIN core.companies c ON c.id = e.company_id
"""


def render(r: dict[str, Any]) -> CalendarEvent:
    by = actor(
        "system" if r["created_by_kind"] == "rule" else r["created_by_kind"], r["created_by_code"]
    )
    assert by is not None
    return CalendarEvent(
        id=r["id"],
        ref=r["ref"],
        company=None if r["kind"] == "holiday" else r["company"],
        kind=r["kind"],
        title_fa=r["title_fa"],
        starts_at=r["starts_at"],
        ends_at=r["ends_at"],
        source=r["source"] or {},
        status=r["status"],
        risk=r["risk"],
        created_by=by,
        version=r["version"],
    )


# -------------------------------------------------------------- conflicts --
def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(a["starts_at"] < b["ends_at"] and b["starts_at"] < a["ends_at"])


def _days(e: dict[str, Any], tz: str) -> set[str]:
    z = G.zone(tz)
    d = e["starts_at"].astimezone(z).date()
    last = max(d, (e["ends_at"] - timedelta(seconds=1)).astimezone(z).date())
    out: set[str] = set()
    while d <= last and len(out) < 7:
        out.add(WEEKDAY[d.weekday()])
        d += timedelta(days=1)
    return out


def conflicts_of(
    dep: dict[str, Any], others: list[dict[str, Any]], blackout: list[str], tz: str
) -> list[Conflict]:
    """A deploy against the other events (rows with company_id, company_kind, kind, repo, ...)."""
    out: list[Conflict] = []
    if dep["status"] == "cancelled":
        return out
    hub = dep.get("company_kind") == "holding"
    days = _days(dep, tz) & set(blackout)
    if days:
        out.append(Conflict(a=dep["ref"], b=dep["ref"], rule="blackout_day", severity="medium",
                            note_fa=f"انتشار در روز ممنوع ماتریس اختیار ({', '.join(sorted(days))})"))  # fmt: skip
    for e in others:
        if e["id"] == dep["id"] or e["status"] == "cancelled" or not _overlap(dep, e):
            continue
        same = e["company_id"] == dep["company_id"]
        holding_wide = e.get("company_kind") == "holding"
        if e["kind"] == "freeze" and (same or holding_wide):
            out.append(Conflict(a=dep["ref"], b=e["ref"], rule="deploy_in_freeze", severity="high",
                                note_fa=f"انتشار داخل فریز {e['ref']}: {e['title_fa']}"))  # fmt: skip
        elif e["kind"] in ("campaign", "event") and same:
            out.append(Conflict(a=dep["ref"], b=e["ref"], rule="deploy_during_campaign", severity="high",
                                note_fa=f"انتشار هم‌زمان با {e['title_fa']} ({e['ref']})"))  # fmt: skip
        elif e["kind"] == "deploy" and (
            same or (e.get("repo") and e.get("repo") == dep.get("repo"))
        ):
            out.append(Conflict(a=dep["ref"], b=e["ref"], rule="two_deploys", severity="medium",
                                note_fa=f"دو انتشار هم‌زمان ({e['ref']})"))  # fmt: skip
        elif e["kind"] == "holiday":
            out.append(Conflict(a=dep["ref"], b=e["ref"], rule="holiday", severity="medium",
                                note_fa=f"انتشار در تعطیلی رسمی: {e['title_fa']}"))  # fmt: skip
        elif e["kind"] == "maintenance" and (same or holding_wide or hub):
            out.append(Conflict(a=dep["ref"], b=e["ref"], rule="maintenance", severity="medium",
                                note_fa=f"نگه‌داری هم‌زمان: {e['title_fa']} ({e['ref']})"))  # fmt: skip
    return out


async def _around(tx: Tx, dep: dict[str, Any]) -> list[dict[str, Any]]:
    """The events that could clash with a deploy: of its company, the holding's,
    and other companies' deploys of the same service."""
    return [
        dict(r)
        for r in await tx.all(
            SQL
            + """ WHERE e.status <> 'cancelled' AND e.starts_at < :b AND e.ends_at > :a
                    AND (e.company_id = :co OR c.kind = 'holding' OR (e.kind = 'deploy' AND e.repo = :repo))""",
            a=dep["starts_at"],
            b=dep["ends_at"],
            co=dep["company_id"],
            repo=dep.get("repo"),
        )
    ]


async def blackout(tx: Tx) -> list[str]:
    return await AU.list_value(tx, "deploy.blackout_days", ["fri"])


async def conflicts_for(tx: Tx, dep: dict[str, Any]) -> list[Conflict]:
    if dep["kind"] != "deploy":
        return []
    return conflicts_of(dep, await _around(tx, dep), await blackout(tx), await G.owner_tz(tx))


async def _emit(tx: Tx, company: str, cs: list[Conflict], **extra: Any) -> None:
    for c in cs:
        await events.emit(tx, company, "calendar.conflict", c.a,
                          {"b": c.b, "rule": c.rule, "severity": c.severity, **extra})  # fmt: skip


# ------------------------------------------------------------------ write --
async def insert(
    tx: Tx,
    company_id: UUID,
    *,
    kind: str,
    title_fa: str,
    starts_at: datetime,
    ends_at: datetime,
    source: dict[str, Any],
    risk: str,
    by: tuple[str, str],
    repo: str | None = None,
    auto_key: str | None = None,
) -> dict[str, Any] | None:
    row = await tx.first(
        """INSERT INTO governance.calendar_events (company_id, kind, title_fa, starts_at, ends_at, source, risk,
               repo, auto_key, created_by_kind, created_by_code)
           VALUES (:co, :k, :t, :a, :b, CAST(:s AS jsonb), :r, :repo, :ak, :bk, :bc)
           ON CONFLICT (auto_key) DO NOTHING RETURNING id""",
        co=company_id,
        k=kind,
        t=title_fa[:300],
        a=starts_at,
        b=ends_at,
        s=json.dumps(source, ensure_ascii=False),
        r=risk,
        repo=repo,
        ak=auto_key,
        bk=by[0],
        bc=by[1],
    )
    if row is None:
        return None
    return dict(await tx.one(SQL + " WHERE e.id = :id", id=row["id"]))


async def add(
    tx: Tx, who: Principal, company_id: UUID, company: str, body: EventIn
) -> dict[str, Any]:
    """An event of the owner or of calendar.add; its new conflicts with the
    deploys around it are emitted (the calendar never decides)."""
    if who.is_agent and body.kind not in AGENT_KINDS:
        raise ApiError(422, "validation_failed", fields={"kind": "campaign, event or maintenance"})
    if not who.is_agent and body.kind == "deploy":
        raise ApiError(422, "validation_failed", fields={"kind": "a deploy comes from its card"})
    e = await insert(
        tx,
        company_id,
        kind=body.kind,
        title_fa=body.title_fa,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        source=body.source.model_dump(exclude_none=True),
        risk=body.risk,
        by=("agent" if who.is_agent else who.kind, who.code),
    )
    assert e is not None
    await _emit(tx, company, await clashes_with(tx, e))
    return e


async def clashes_with(tx: Tx, e: dict[str, Any]) -> list[Conflict]:
    """The conflicts a new or moved event makes with the deploys it overlaps."""
    if e["kind"] == "deploy":
        return await conflicts_for(tx, e)
    out: list[Conflict] = []
    for dep in await tx.all(
        SQL
        + " WHERE e.kind = 'deploy' AND e.status = 'planned' AND e.starts_at < :b AND e.ends_at > :a",
        a=e["starts_at"],
        b=e["ends_at"],
    ):
        out += [c for c in await conflicts_for(tx, dict(dep)) if e["ref"] in (c.a, c.b)]
    return out


async def patch(
    tx: Tx, who: Principal, ref: str, body: EventPatch, expected: int
) -> dict[str, Any]:
    e = await tx.first(SQL + " WHERE e.ref = :ref FOR UPDATE OF e", ref=ref)
    if e is None:
        raise ApiError(404, "not_found", f"no calendar event {ref}")
    if e["version"] != expected:
        raise ApiError(409, "version_conflict", f"current version is {e['version']}")
    sets = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    starts, ends = sets.get("starts_at", e["starts_at"]), sets.get("ends_at", e["ends_at"])
    if ends < starts:
        raise ApiError(422, "validation_failed", fields={"ends_at": "before starts_at"})
    if sets:
        assign = ", ".join(f"{k} = :{k}" for k in sets)
        await tx.exec(
            f"UPDATE governance.calendar_events SET {assign} WHERE id = :id",  # noqa: S608 - EventPatch names
            id=e["id"],
            **sets,
        )
    fresh = dict(await tx.one(SQL + " WHERE e.id = :id", id=e["id"]))
    if {"starts_at", "ends_at", "status"} & set(sets):
        await _emit(tx, fresh["company"], await clashes_with(tx, fresh))
    return fresh


# ---------------------------------------------------------------- deploys --
async def deploy_proposed(
    tx: Tx, company_id: UUID, title: str, payload: dict[str, Any], risk: str, by: tuple[str, str]
) -> tuple[dict[str, Any] | None, list[Conflict]]:
    """A deploy card's window becomes an event before the card exists (its
    conflicts go into the card's payload); link() then names the card."""
    win = payload.get("window")
    if not win:
        return None, []
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await freeze_events(tx, [company_id, holding], datetime.now(UTC))  # a freeze set a moment ago
    e = await insert(
        tx,
        company_id,
        kind="deploy",
        title_fa=f"انتشار: {title}",
        starts_at=datetime.fromisoformat(str(win["from"]).replace("Z", "+00:00")),
        ends_at=datetime.fromisoformat(str(win["to"]).replace("Z", "+00:00")),
        source={},
        risk=risk,
        by=by,
        repo=str(payload.get("repo") or "")[:200] or None,
    )
    assert e is not None
    return e, await conflicts_for(tx, e)


async def link(tx: Tx, e: dict[str, Any], decision_ref: str, conflicts: list[Conflict]) -> None:
    await tx.exec(
        "UPDATE governance.calendar_events SET source = CAST(:s AS jsonb) WHERE id = :id",
        s=json.dumps({"decision": decision_ref}),
        id=e["id"],
    )
    await _emit(tx, e["company"], conflicts, decision=decision_ref)


async def deploy_decided(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """A deploy card that was not approved takes its window off the calendar."""
    if verdict == "approved":
        return
    await tx.exec(
        """UPDATE governance.calendar_events SET status = 'cancelled'
           WHERE kind = 'deploy' AND source->>'decision' = :ref AND status = 'planned'""",
        ref=d["ref"],
    )


# ------------------------------------------------------------------- read --
async def listing(
    tx: Tx, *, company_id: UUID | None, start: datetime, end: datetime, kind: str | None
) -> Calendar:
    rows = [
        dict(r)
        for r in await tx.all(
            SQL
            + """ WHERE e.starts_at < :b AND e.ends_at > :a
                    AND (CAST(:co AS uuid) IS NULL OR e.company_id = :co OR c.kind = 'holding')
                    AND (CAST(:k AS text) IS NULL OR e.kind = :k)
                  ORDER BY e.starts_at, e.ref LIMIT 2000""",
            a=start,
            b=end,
            co=company_id,
            k=kind,
        )
    ]
    tz = await G.owner_tz(tx)
    off = await blackout(tx)
    seen: set[tuple[str, str, str]] = set()
    conflicts: list[Conflict] = []
    for dep in (r for r in rows if r["kind"] == "deploy"):
        for c in conflicts_of(dep, await _around(tx, dep), off, tz):
            key = (min(c.a, c.b), max(c.a, c.b), c.rule)
            if key not in seen:
                seen.add(key)
                conflicts.append(c)
    return Calendar(events=[render(r) for r in rows], conflicts=conflicts)


# --------------------------------------------------------------- the code --
def load_holidays(path: Path = HOLIDAYS_FILE) -> dict[date, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[date, list[str]] = {}
    for d in data.get("days") or []:
        out.setdefault(date.fromisoformat(str(d["date"])), []).append(str(d["title_fa"]))
    return out


async def seed_holidays(tx: Tx) -> int:
    """The holidays as `holiday` events of the holding (once per day)."""
    holding = await tx.scalar(
        "SELECT id FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    if holding is None:
        return 0
    tz = await G.owner_tz(tx)
    n = 0
    for day, titles in sorted(load_holidays().items()):
        e = await insert(
            tx,
            holding,
            kind="holiday",
            title_fa=" · ".join(dict.fromkeys(titles)),
            starts_at=G.local_midnight(day, tz),
            ends_at=G.local_midnight(day + timedelta(days=1), tz),
            source={},
            risk="low",
            by=("service", "seed"),
            auto_key=f"holiday:{day.isoformat()}",
        )
        n += e is not None
    return n


async def freeze_events(tx: Tx, company_ids: list[Any] | None, now: datetime) -> int:
    """Deploy freezes (control.deploy_freezes) as `freeze` events, once each; a
    lifted freeze ends at its lifting."""
    made = 0
    for f in await tx.all(
        """SELECT f.*, c.code FROM control.deploy_freezes f JOIN core.companies c ON c.id = f.company_id
           WHERE f.until > :since AND (CAST(:ids AS uuid[]) IS NULL OR f.company_id = ANY(:ids))""",
        since=now - timedelta(days=30),
        ids=company_ids,
    ):
        e = await insert(
            tx, f["company_id"], kind="freeze", title_fa=f"فریز انتشار: {f['reason']}"[:300],
            starts_at=f["created_at"], ends_at=f["lifted_at"] or f["until"], source={}, risk="high",
            by=(f["created_by_kind"], f["created_by_code"]), auto_key=f"freeze:{f['id']}",
        )  # fmt: skip
        if e is not None:
            made += 1
            await _emit(tx, e["company"], await clashes_with(tx, e))
        elif f["lifted_at"] is not None:
            await tx.exec(
                """UPDATE governance.calendar_events SET ends_at = greatest(starts_at, :t)
                   WHERE auto_key = :k AND ends_at > :t""",
                t=f["lifted_at"],
                k=f"freeze:{f['id']}",
            )
    return made


async def sync(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """Freezes and the hub's backup windows onto the calendar; deploy events
    of cards that expired or were withdrawn come off it."""
    now = now or datetime.now(UTC)
    freezes = await freeze_events(tx, None, now)
    holding = await tx.scalar(
        "SELECT id FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    windows = 0
    for i in range(BACKUP_AHEAD_DAYS):
        day = now.date() + timedelta(days=i)
        plans = [("backup", day, NIGHTLY)]
        if day.weekday() == 6:  # Sunday
            plans.append(("restore", day, RESTORE))
        for name, d, (at, length, tz, title) in plans:
            start = datetime.combine(d, at, G.zone(tz)).astimezone(UTC)
            e = await insert(
                tx, holding, kind="maintenance", title_fa=title, starts_at=start, ends_at=start + length,
                source={}, risk="low", by=("service", "calendar"), auto_key=f"{name}:{d.isoformat()}",
            )  # fmt: skip
            windows += e is not None
    gone = await tx.exec(
        """UPDATE governance.calendar_events e SET status = 'cancelled'
           FROM cartable.decisions d
           WHERE e.kind = 'deploy' AND e.status = 'planned' AND d.ref = e.source->>'decision'
             AND d.status IN ('rejected', 'returned', 'expired', 'withdrawn')"""
    )
    return {"freezes": freezes, "maintenance": windows, "cancelled": gone}


async def deploys_outside(tx: Tx, since: datetime) -> list[dict[str, Any]]:
    """PR-113: deploy cards approved since `since`, each with its calendar
    event (None: it ran outside the calendar) and its high conflicts."""
    out = []
    for d in await tx.all(
        """SELECT d.ref, d.company_id, c.code AS company FROM cartable.decisions d
           JOIN core.companies c ON c.id = d.company_id
           WHERE d.kind = 'deploy' AND d.status = 'approved' AND d.decided_at >= :s ORDER BY d.ref""",
        s=since,
    ):
        e = await tx.first(
            SQL + " WHERE e.kind = 'deploy' AND e.source->>'decision' = :r", r=d["ref"]
        )
        high = await conflicts_for(tx, dict(e)) if e else []
        out.append({**dict(d), "event": e["ref"] if e else None,
                    "high": [c for c in high if c.severity == "high"]})  # fmt: skip
    return out
