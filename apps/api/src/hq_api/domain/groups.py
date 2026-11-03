"""Working groups as data (contract §29.11 ⟨1.11⟩, docs/MANAGEMENT_REVIEW_2026-11.md §4).

A group is a file (apps/api/seed/groups/<key>.yaml): its seats, its daily
and weekly routines, its KPIs, the connections it needs and who is eligible.
A new group is a new file, no new code. `seed` loads every file (at startup
and on every tick): a changed file makes a new version (growth.group_versions
keeps each); the owner's pauses (a routine, a membership) survive it.

Members: every active company that is eligible (`has_channel`: at least one
publishing channel among its §29.12 connections) joins by itself, a new
company too; the owner may pause a membership. Each seat resolves to the
company's active employee with the seat's charter; an empty seat is filled
by automatic hiring (§29.10, `hiring.auto_fill`, prompt 21 part 1) and shows
in the readiness page (§29.9) until it is.

The tick (worker, every 10 minutes, rule-based, no model; nothing while the
holding is locked, nothing for a locked company): when a routine's
occurrence is due for a member, ONE small work item for the seat's employee
(its brief from the routine, `max_tokens` as its budget), recorded in
growth.routine_runs under a unique (group, company, routine, occurrence):
never twice for one period. The model runs only in that employee's run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate, recurrence
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.groups")

GROUPS_DIR = Path(__file__).resolve().parents[3] / "seed" / "groups"
SERVICE = Principal(kind="service", code="groups", role="service")
# A routine's occurrence still runs when the tick comes this late (a worker
# restart, a lock lifted); older ones are left (never a backlog of runs).
LOOKBACK = timedelta(hours=2)
# An empty seat asks automatic hiring at most once a day.
FILL_EVERY = timedelta(hours=24)
PUBLISHING = ("instagram", "telegram", "youtube", "x")
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
WORK_DONE = ("done", "delivered")
WORK_FAILED = ("failed", "cancelled")


# ------------------------------------------------------------------ shapes --
class Seat(BaseModel):
    seat: str
    role: str
    title_fa: str
    count: int = 1
    optional: bool = False


class Routine(BaseModel):
    key: str
    title_fa: str
    seat: str
    schedule: str  # RRULE in the owner's time zone
    brief_md: str
    max_tokens: int
    state: Literal["on", "paused"] = "on"
    # ⟨additive⟩ the router's class of the run where a media class fits; the
    # hub's condition for a run (sealed_series: something to publish in)
    task_class: str | None = None
    needs: str | None = None


class Kpi(BaseModel):
    key: str
    title_fa: str
    unit: str
    source: str
    seat: str | None = None  # ⟨additive⟩ whose KPI it is (§4.3)


class Group(BaseModel):
    key: str
    title_fa: str
    purpose_fa: str
    seats: list[Seat]
    routines: list[Routine]
    kpis: list[Kpi]
    connections: list[str]
    eligible: Literal["has_channel", "all"]
    state: Literal["on", "off"]
    # ⟨additive⟩ the definition's version (a changed file is a new one), the lead seat
    version: int = 1
    lead: str | None = None


class MemberSeat(BaseModel):
    seat: str
    role: str
    title_fa: str
    employee: str | None
    optional: bool = False


class Membership(BaseModel):
    group: str
    company: str
    state: Literal["on", "paused"]
    joined_at: datetime
    seats: list[MemberSeat]
    # ⟨additive⟩ the company's Persian name; the content lead's plan of the day (group.plan)
    name_fa: str | None = None
    plan: dict[str, Any] | None = None
    plan_at: datetime | None = None


class RoutineRun(BaseModel):
    id: UUID
    group: str
    company: str
    routine: str
    at: datetime
    work_ref: str | None
    state: Literal["queued", "done", "failed", "skipped"]
    note_fa: str | None
    # ⟨additive⟩ the period this run is for, and who it went to
    occurrence_at: datetime | None = None
    employee: str | None = None


class Experiment(BaseModel):
    id: UUID
    group: str
    company: str
    week: date
    hypothesis_fa: str
    metric: str
    target: float
    result: float | None
    kept: bool | None
    # ⟨additive⟩
    baseline: float | None = None
    note_fa: str | None = None
    closed_at: datetime | None = None


# ------------------------------------------------------------------- files --
def _canonical(data: dict[str, Any]) -> dict[str, Any]:
    """What a version covers (the file's meaning, not its comments)."""
    return {
        "title_fa": str(data.get("title_fa") or ""),
        "purpose_fa": " ".join(str(data.get("purpose_fa") or "").split()),
        "state": str(data.get("state") or "on"),
        "eligible": str(data.get("eligible") or "has_channel"),
        "lead": data.get("lead"),
        "seats": [Seat(**s).model_dump() for s in data.get("seats") or []],
        "routines": [
            Routine(**{k: v for k, v in r.items() if k != "state"}).model_dump(exclude={"state"})
            for r in data.get("routines") or []
        ],
        "kpis": [Kpi(**k).model_dump() for k in data.get("kpis") or []],
        "connections": [str(c) for c in data.get("connections") or []],
    }


def digest_of(definition: dict[str, Any]) -> str:
    raw = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def validate(key: str, d: dict[str, Any]) -> None:
    """A file that does not hold together is refused whole (never half a group)."""
    if not KEY.match(key):
        raise ValueError(f"group key {key!r}")
    seats = {s["seat"] for s in d["seats"]}
    if not seats:
        raise ValueError(f"{key}: no seats")
    for s in d["seats"]:
        if not KEY.match(s["seat"]) or not KEY.match(s["role"]):
            raise ValueError(f"{key}: seat {s['seat']!r}")
    for r in d["routines"]:
        if not KEY.match(r["key"]) or r["seat"] not in seats:
            raise ValueError(f"{key}: routine {r['key']!r} names no seat of the group")
        recurrence.parse(r["schedule"])  # ApiError on a rule the calendar cannot hold
        if not 1_000 <= int(r["max_tokens"]) <= 2_000_000:
            raise ValueError(f"{key}: routine {r['key']!r} max_tokens")
    if d["lead"] is not None and d["lead"] not in seats:
        raise ValueError(f"{key}: lead {d['lead']!r} is no seat")
    if d["eligible"] not in ("has_channel", "all") or d["state"] not in ("on", "off"):
        raise ValueError(f"{key}: eligible/state")


def load_files(root: Path | None = None) -> list[tuple[str, dict[str, Any]]]:
    """(key, definition) of every group file, in key order."""
    out = []
    for p in sorted((root or GROUPS_DIR).glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        key = str(data.get("key") or p.stem)
        d = _canonical(data)
        try:
            validate(key, d)
        except (ValueError, ApiError) as exc:
            log.warning("group file refused", extra={"file": p.name, "error": str(exc)[:200]})
            continue
        out.append((key, d))
    return out


@lru_cache(maxsize=1)
def _cached_files() -> tuple[tuple[str, str], ...]:
    return tuple((k, json.dumps(d, ensure_ascii=False)) for k, d in load_files())


async def seed(tx: Tx, holding_id: UUID, root: Path | None = None) -> int:
    """Every group file into growth.groups: a new one at version 1, a changed
    one as its next version (the owner's routine pauses kept). Idempotent."""
    files = (
        load_files(root) if root is not None else [(k, json.loads(d)) for k, d in _cached_files()]
    )
    changed = 0
    for key, d in files:
        digest = digest_of(d)
        cur = await tx.first(
            "SELECT id, version, digest FROM growth.groups WHERE key = :k FOR UPDATE", k=key
        )
        if cur is not None and cur["digest"] == digest:
            continue
        version = 1 if cur is None else int(cur["version"]) + 1
        body = json.dumps(d, ensure_ascii=False)
        if cur is None:
            gid = await tx.scalar(
                """INSERT INTO growth.groups (company_id, key, version, digest, title_fa, purpose_fa,
                       definition, state)
                   VALUES (:co, :k, 1, :dg, :t, :p, CAST(:d AS jsonb), :st)
                   ON CONFLICT (key) DO NOTHING RETURNING id""",
                co=holding_id,
                k=key,
                dg=digest,
                t=d["title_fa"],
                p=d["purpose_fa"],
                d=body,
                st=d["state"],
            )
            if gid is None:  # another process seeded it this very moment
                continue
        else:
            gid = cur["id"]
            await tx.exec(
                """UPDATE growth.groups SET version = :v, digest = :dg, title_fa = :t, purpose_fa = :p,
                       definition = CAST(:d AS jsonb), state = :st, updated_at = now()
                   WHERE id = :id""",
                id=gid,
                v=version,
                dg=digest,
                t=d["title_fa"],
                p=d["purpose_fa"],
                d=body,
                st=d["state"],
            )
        await tx.exec(
            """INSERT INTO growth.group_versions (company_id, group_id, version, digest, definition)
               VALUES (:co, :g, :v, :dg, CAST(:d AS jsonb)) ON CONFLICT (group_id, version) DO NOTHING""",
            co=holding_id,
            g=gid,
            v=version,
            dg=digest,
            d=body,
        )
        changed += 1
    return changed


# ------------------------------------------------------------------- reads --
def render(row: dict[str, Any]) -> Group:
    d = row["definition"]
    paused = row.get("routine_states") or {}
    routines = [
        Routine(**{**r, "state": "paused" if paused.get(r["key"]) == "paused" else "on"})
        for r in d.get("routines") or []
    ]
    return Group(
        key=row["key"],
        title_fa=row["title_fa"],
        purpose_fa=row["purpose_fa"],
        seats=[Seat(**s) for s in d.get("seats") or []],
        routines=routines,
        kpis=[Kpi(**k) for k in d.get("kpis") or []],
        connections=list(d.get("connections") or []),
        eligible=d.get("eligible") or "has_channel",
        state=row["state"],
        version=row["version"],
        lead=d.get("lead"),
    )


async def rows(tx: Tx) -> list[dict[str, Any]]:
    return await tx.all("SELECT * FROM growth.groups ORDER BY key")


async def row_of(tx: Tx, key: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        "SELECT * FROM growth.groups WHERE key = :k" + (" FOR UPDATE" if lock else ""),  # noqa: S608
        k=key,
    )


MEMBER_SQL = """
    SELECT m.*, g.key AS group_key, c.code AS company, c.name_fa, c.status AS company_status
    FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
    JOIN core.companies c ON c.id = m.company_id
"""


def render_member(r: dict[str, Any], g: Group | None = None) -> Membership:
    seats = {s["seat"]: s for s in r.get("seats") or []}
    order = g.seats if g is not None else [Seat(**{**s, "count": 1}) for s in seats.values()]
    return Membership(
        group=r["group_key"],
        company=r["company"],
        name_fa=r.get("name_fa"),
        state=r["state"],
        joined_at=r["joined_at"],
        seats=[
            MemberSeat(
                seat=s.seat,
                role=s.role,
                title_fa=s.title_fa,
                employee=(seats.get(s.seat) or {}).get("employee"),
                optional=s.optional,
            )
            for s in order
        ],
        plan=r.get("plan"),
        plan_at=r.get("plan_at"),
    )


async def members(tx: Tx, group_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(MEMBER_SQL + " WHERE m.group_id = :g ORDER BY c.code", g=group_id)


async def member(tx: Tx, group_id: UUID, company_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        MEMBER_SQL
        + " WHERE m.group_id = :g AND m.company_id = :co"
        + (" FOR UPDATE OF m" if lock else ""),
        g=group_id,
        co=company_id,
    )


def render_run(r: dict[str, Any]) -> RoutineRun:
    return RoutineRun(
        id=r["id"],
        group=r["group_key"],
        company=r["company"],
        routine=r["routine"],
        at=r["at"],
        work_ref=r.get("work_ref"),
        state=r["state"],
        note_fa=r.get("note_fa"),
        occurrence_at=r.get("occurrence_at"),
        employee=r.get("employee_code"),
    )


RUN_SQL = """
    SELECT x.*, g.key AS group_key, c.code AS company, w.ref AS work_ref
    FROM growth.routine_runs x JOIN growth.groups g ON g.id = x.group_id
    JOIN core.companies c ON c.id = x.company_id LEFT JOIN work.work w ON w.id = x.work_id
"""


def render_experiment(r: dict[str, Any]) -> Experiment:
    def num(v: Any) -> float | None:
        return float(v) if v is not None else None

    return Experiment(
        id=r["id"],
        group=r["group_key"],
        company=r["company"],
        week=r["week"],
        hypothesis_fa=r["hypothesis_fa"],
        metric=r["metric"],
        target=float(r["target"]),
        result=num(r["result"]),
        kept=r["kept"],
        baseline=num(r["baseline"]),
        note_fa=r["note_fa"],
        closed_at=r["closed_at"],
    )


EXPERIMENT_SQL = """
    SELECT x.*, g.key AS group_key, c.code AS company
    FROM growth.experiments x JOIN growth.groups g ON g.id = x.group_id
    JOIN core.companies c ON c.id = x.company_id
"""


# ---------------------------------------------------------------- members --
async def eligible(tx: Tx, g: Group) -> list[dict[str, Any]]:
    """The active operating companies the group takes (data: any number)."""
    if g.eligible == "all":
        return await tx.all(
            """SELECT id, code, name_fa FROM core.companies
               WHERE kind = 'company' AND status = 'active' ORDER BY code"""
        )
    return await tx.all(
        """SELECT c.id, c.code, c.name_fa FROM core.companies c
           WHERE c.kind = 'company' AND c.status = 'active'
             AND EXISTS (SELECT 1 FROM growth.connections k
                         WHERE k.company_id = c.id AND k.kind = ANY(:pub))
           ORDER BY c.code""",
        pub=list(PUBLISHING),
    )


async def seat_holders(tx: Tx, company_id: UUID, roles: list[str]) -> dict[str, str]:
    """role -> the company's first active employee with that charter."""
    found = await tx.all(
        """SELECT DISTINCT ON (e.role) e.role, e.code FROM core.employees e
           WHERE e.company_id = :co AND e.status = 'active' AND e.role = ANY(:roles)
           ORDER BY e.role, e.hired_at, e.code""",
        co=company_id,
        roles=roles,
    )
    return {r["role"]: r["code"] for r in found}


def _auto_filler() -> Any:
    """§29.10: prompt 21 part 1's hiring.auto_fill(tx, company_id, role,
    seat_title), or None while it is not there (not merged yet)."""
    try:
        from hq_api.domain import hiring
    except ImportError:  # pragma: no cover - the module is part of the api
        return None
    return getattr(hiring, "auto_fill", None)


async def _auto_fill(tx: Tx, fill: Any, company_id: UUID, role: str, seat_title: str) -> Any:
    """An empty seat filled by code. Called defensively: failing, the seat
    stays empty and readiness shows it."""
    try:
        async with tx.conn.begin_nested():
            return await fill(tx, company_id, role, seat_title)
    except Exception:  # noqa: BLE001 - a refused hire is the hiring module's to report
        log.warning("auto fill of a seat failed", extra={"role": role})
        return None


async def reconcile_members(
    tx: Tx, grow: dict[str, Any], *, now: datetime | None = None, fill: bool = True
) -> dict[str, int]:
    """Eligible companies join (a new one too); each member's seats resolve
    to employees; an empty required seat asks automatic hiring (once a day)."""
    now = now or datetime.now(UTC)
    g = render(grow)
    out = {"joined": 0, "filled": 0, "asked": 0}
    if g.state != "on":
        return out
    for co in await eligible(tx, g):
        made = await tx.scalar(
            """INSERT INTO growth.memberships (company_id, group_id) VALUES (:co, :g)
               ON CONFLICT (group_id, company_id) DO NOTHING RETURNING id""",
            co=co["id"],
            g=grow["id"],
        )
        if made is not None:
            out["joined"] += 1
            await events.emit(tx, co["code"], "group.run", None, {"group": g.key, "joined": True})
    roles = sorted({s.role for s in g.seats})
    filler = _auto_filler() if fill else None
    for m in await members(tx, grow["id"]):
        holders = await seat_holders(tx, m["company_id"], roles)
        before = {s["seat"]: s for s in m["seats"] or []}
        seats = []
        for s in g.seats:
            prev = before.get(s.seat) or {}
            emp = holders.get(s.role)
            entry: dict[str, Any] = {"seat": s.seat, "role": s.role, "employee": emp}
            asked = prev.get("asked_at")
            wants = (
                emp is None
                and not s.optional
                and fill
                and m["state"] == "on"
                and m["company_status"] == "active"
                and (asked is None or datetime.fromisoformat(asked) < now - FILL_EVERY)
            )
            if (
                wants
                and filler is not None
                and await gate.automation_lock(tx, m["company_id"]) is None
            ):
                await _auto_fill(tx, filler, m["company_id"], s.role, s.title_fa)
                asked = now.isoformat()
                out["asked"] += 1
                emp = (await seat_holders(tx, m["company_id"], [s.role])).get(s.role)
                entry["employee"] = emp
            if emp is not None and prev.get("employee") is None:
                out["filled"] += 1
            if asked is not None and emp is None:
                entry["asked_at"] = asked
            seats.append(entry)
        if seats != (m["seats"] or []):
            await tx.exec(
                """UPDATE growth.memberships SET seats = CAST(:s AS jsonb), updated_at = now()
                   WHERE id = :id""",
                id=m["id"],
                s=json.dumps(seats, ensure_ascii=False),
            )
    return out


# ---------------------------------------------------------------- routines --
def due_occurrence(rule: recurrence.Rule, tz: str, now: datetime) -> datetime | None:
    """The routine's latest occurrence within LOOKBACK of now, if any."""
    found = recurrence.occurrences(rule, tz, now - LOOKBACK, now + timedelta(seconds=1))
    return found[-1] if found else None


def brief_for(r: Routine, g: Group, company: dict[str, Any], occurrence: datetime) -> str:
    code = str(company.get("company") or company.get("code"))
    name = company.get("name_fa") or code
    body = r.brief_md.replace("{company_name}", str(name)).replace("{company}", code)
    return (
        f"{body.strip()}\n\n"
        f"(Working group «{g.title_fa}» ({g.key}), routine «{r.title_fa}» ({r.key}), "
        f"for {occurrence.isoformat()}; budget {r.max_tokens} tokens; contract §29.11.)"
    )


def _task_class(r: Routine) -> str | None:
    if not r.task_class:
        return None
    try:
        from hq_api.agents.runner import RUN_TASK_CLASSES
    except ImportError:  # pragma: no cover
        return None
    return r.task_class if r.task_class in RUN_TASK_CLASSES else None


async def has_sealed_series(tx: Tx, company_id: UUID) -> bool:
    return bool(
        await tx.scalar(
            "SELECT 1 FROM media.series WHERE company_id = :co AND status = 'sealed' LIMIT 1",
            co=company_id,
        )
    )


async def _record_run(
    tx: Tx,
    grow: dict[str, Any],
    m: dict[str, Any],
    r: Routine,
    occurrence: datetime,
    state: str,
    note_fa: str | None,
    employee: str | None,
) -> UUID | None:
    rid: UUID | None = await tx.scalar(
        """INSERT INTO growth.routine_runs (company_id, group_id, routine, occurrence_at, seat,
               employee_code, state, note_fa)
           VALUES (:co, :g, :r, :occ, :seat, :emp, :st, :note)
           ON CONFLICT (group_id, company_id, routine, occurrence_at) DO NOTHING RETURNING id""",
        co=m["company_id"],
        g=grow["id"],
        r=r.key,
        occ=occurrence,
        seat=r.seat,
        emp=employee,
        st=state,
        note=note_fa,
    )
    return rid


async def run_routine(
    tx: Tx, grow: dict[str, Any], m: dict[str, Any], r: Routine, occurrence: datetime
) -> str | None:
    """One occurrence of a routine for one member: a work item for the seat's
    employee, or a skipped run that says why. None when it ran already."""
    from hq_api.domain import work as W

    g = render(grow)
    seat = next(s for s in g.seats if s.seat == r.seat)
    emp = next((s.get("employee") for s in m["seats"] or [] if s.get("seat") == r.seat), None)
    note = None
    if r.needs == "sealed_series" and not await has_sealed_series(tx, m["company_id"]):
        note = "سری انتشار مُهرشده‌ای نیست؛ چیزی برای انتشار نیست."
    elif emp is None:
        note = f"جایگاه «{seat.title_fa}» هنوز خالی است؛ استخدام خودکار آن را پر میکند."
    if note is not None:
        rid = await _record_run(tx, grow, m, r, occurrence, "skipped", note, None)
        if rid is not None:
            await events.emit(
                tx, m["company"], "group.run", None,
                {"group": g.key, "routine": r.key, "state": "skipped"},
            )  # fmt: skip
        return "skipped" if rid is not None else None
    rid = await _record_run(tx, grow, m, r, occurrence, "queued", None, emp)
    if rid is None:
        return None
    try:
        async with tx.conn.begin_nested():
            w = await W.create(
                tx,
                SERVICE,
                company_id=m["company_id"],
                company_code=m["company"],
                title=f"{r.title_fa} · {g.title_fa}",
                brief=brief_for(r, g, m, occurrence),
                kind="one_off",
                priority="P3",
                assignee_code=emp,
                budget=W.BudgetIn(tokens=r.max_tokens),
            )
    except ApiError as exc:
        await tx.exec(
            "UPDATE growth.routine_runs SET state = 'failed', note_fa = :n WHERE id = :id",
            id=rid,
            n="کار این روال ساخته نشد؛ کارمند این جایگاه در دسترس نیست.",
        )
        log.warning("routine work refused", extra={"routine": r.key, "code": exc.code})
        return "failed"
    meta: dict[str, Any] = {
        "group": g.key,
        "routine": r.key,
        "occurrence": occurrence.isoformat(),
    }
    if (tc := _task_class(r)) is not None:
        meta["task_class"] = tc
    await tx.exec(
        "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
        id=w["id"],
        m=json.dumps(meta),
    )
    await tx.exec("UPDATE growth.routine_runs SET work_id = :w WHERE id = :id", id=rid, w=w["id"])
    await events.emit(
        tx,
        m["company"],
        "group.run",
        w["ref"],
        {"group": g.key, "routine": r.key, "state": "queued", "employee": emp},
    )
    return "queued"


async def settle_runs(tx: Tx) -> int:
    """Queued runs follow their work item: done or failed once it ends."""
    return await tx.exec(
        """UPDATE growth.routine_runs x SET state = CASE WHEN w.status = ANY(:done) THEN 'done'
                                                   ELSE 'failed' END
           FROM work.work w
           WHERE x.work_id = w.id AND x.state = 'queued' AND w.status = ANY(:final)""",
        done=list(WORK_DONE),
        final=[*WORK_DONE, *WORK_FAILED],
    )


async def tick(
    hub: Any, now: datetime | None = None, *, only: set[UUID] | None = None
) -> dict[str, Any]:
    """The groups' tick: seed the files, reconcile the members, run what is due
    (`only`: these companies' routines, for a test or a manual run)."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"seeded": 0, "joined": 0, "asked": 0, "queued": 0, "skipped": 0}
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        holding = await hub.companies.holding()
        out["seeded"] = await seed(tx, holding.id)
        tz = await owner_tz(tx)
        out["settled"] = await settle_runs(tx)
        for grow in await rows(tx):
            g = render(grow)
            rec = await reconcile_members(tx, grow, now=now)
            out["joined"] += rec["joined"]
            out["asked"] += rec["asked"]
            if g.state != "on":
                continue
            ms = [
                m
                for m in await members(tx, grow["id"])
                if m["state"] == "on"
                and m["company_status"] == "active"
                and (only is None or m["company_id"] in only)
            ]
            for r in g.routines:
                if r.state != "on":
                    continue
                occ = due_occurrence(recurrence.parse(r.schedule), tz, now)
                if occ is None:
                    continue
                for m in ms:
                    if await gate.automation_lock(tx, m["company_id"]) is not None:
                        continue
                    got = await run_routine(tx, grow, m, r, occ)
                    if got == "queued":
                        out["queued"] += 1
                    elif got == "skipped":
                        out["skipped"] += 1
    return out


# ------------------------------------------------------------- owner sets --
async def set_member_state(tx: Tx, grow: dict[str, Any], company_id: UUID, state: str) -> None:
    await tx.exec(
        """UPDATE growth.memberships SET state = :st, updated_at = now(),
               paused_at = CASE WHEN :st = 'paused' THEN now() ELSE NULL END
           WHERE group_id = :g AND company_id = :co""",
        g=grow["id"],
        co=company_id,
        st=state,
    )


async def set_routine_state(tx: Tx, grow: dict[str, Any], routine: str, state: str) -> None:
    g = render(grow)
    if routine not in {r.key for r in g.routines}:
        raise ApiError(404, "not_found", f"no routine {routine} in {g.key}")
    states = dict(grow.get("routine_states") or {})
    if state == "paused":
        states[routine] = "paused"
    else:
        states.pop(routine, None)
    await tx.exec(
        """UPDATE growth.groups SET routine_states = CAST(:s AS jsonb), updated_at = now()
           WHERE id = :id""",
        id=grow["id"],
        s=json.dumps(states),
    )


# ------------------------------------------------------------------- KPIs --
async def kpi_series(
    tx: Tx, company_id: UUID, k: Kpi, days: int, today: date
) -> list[dict[str, Any]]:
    """A KPI's daily series from growth.metrics_daily only (real figures;
    the sum over the kind's subjects, e.g. every channel's followers)."""
    kinds = [s.strip() for s in k.source.split(",") if s.strip()]
    found = await tx.all(
        """SELECT day, sum(value) AS value FROM growth.metrics_daily
           WHERE company_id = :co AND key = :k AND kind = ANY(:kinds)
             AND day > CAST(:today AS date) - CAST(:days AS int) AND day <= :today
           GROUP BY day ORDER BY day""",
        co=company_id,
        k=k.key,
        kinds=kinds,
        today=today,
        days=days,
    )
    return [{"day": r["day"], "value": float(r["value"])} for r in found]


# ------------------------------------------------------------- experiments --
async def write_experiment(
    tx: Tx,
    grow: dict[str, Any],
    company_id: UUID,
    *,
    week: date,
    by: str,
    hypothesis_fa: str | None = None,
    metric: str | None = None,
    target: float | None = None,
    baseline: float | None = None,
    result: float | None = None,
    kept: bool | None = None,
    note_fa: str | None = None,
) -> dict[str, Any]:
    """experiment.write: one experiment a week per company; a result closes it."""
    cur = await tx.first(
        """SELECT id, closed_at FROM growth.experiments
           WHERE group_id = :g AND company_id = :co AND week = :w FOR UPDATE""",
        g=grow["id"],
        co=company_id,
        w=week,
    )
    if cur is None:
        if not (hypothesis_fa and metric and target is not None):
            raise ApiError(
                422,
                "validation_failed",
                fields={
                    "hypothesis_fa": "a new experiment needs its hypothesis, metric and target"
                },
            )
        if result is not None:
            raise ApiError(
                422,
                "validation_failed",
                fields={"result": "write the experiment before closing it"},
            )
        eid = await tx.scalar(
            """INSERT INTO growth.experiments (company_id, group_id, week, hypothesis_fa, metric, target,
                   baseline, note_fa, created_by_code)
               VALUES (:co, :g, :w, :h, :m, :t, :b, :n, :by) RETURNING id""",
            co=company_id,
            g=grow["id"],
            w=week,
            h=hypothesis_fa,
            m=metric,
            t=target,
            b=baseline,
            n=note_fa,
            by=by,
        )
    else:
        eid = cur["id"]
        if cur["closed_at"] is not None:
            raise ApiError(409, "version_conflict", "this week's experiment is closed already")
        await tx.exec(
            """UPDATE growth.experiments SET
                   hypothesis_fa = COALESCE(:h, hypothesis_fa), metric = COALESCE(:m, metric),
                   target = COALESCE(CAST(:t AS numeric), target),
                   baseline = COALESCE(CAST(:b AS numeric), baseline),
                   note_fa = COALESCE(:n, note_fa), result = CAST(:res AS numeric),
                   kept = CASE WHEN CAST(:res AS numeric) IS NULL THEN kept ELSE :kept END,
                   closed_at = CASE WHEN CAST(:res AS numeric) IS NULL THEN NULL ELSE now() END,
                   updated_at = now()
               WHERE id = :id""",
            id=eid,
            h=hypothesis_fa,
            m=metric,
            t=target,
            b=baseline,
            n=note_fa,
            res=result,
            kept=kept,
        )
    return await tx.one(EXPERIMENT_SQL + " WHERE x.id = :id", id=eid)


async def store_plan(
    tx: Tx, grow: dict[str, Any], company_id: UUID, plan: dict[str, Any], at: datetime
) -> None:
    await tx.exec(
        """UPDATE growth.memberships SET plan = CAST(:p AS jsonb), plan_at = :at, updated_at = now()
           WHERE group_id = :g AND company_id = :co""",
        g=grow["id"],
        co=company_id,
        p=json.dumps(plan, ensure_ascii=False, default=str),
        at=at,
    )
