"""The meeting room, by code (prompt 11 §1, contract §20.1): the types, the
agenda and its speakers, the budget estimate and its trim, the shapes the
apps read. The live flow (turns, claims, closing, the war room, standups and
the schedule) is hq_api.domain.meeting_flow.

Rules this module keeps:
- Speakers per item, by rule: the concerned companies' CEO (or the item's
  owner and the managers it concerns), the relevant holding head, the devil's
  advocate from oversight LAST (the inspector, or the overseer when the type
  says so); at most `max_speakers` per item. Every other concerned company
  gives a written statement (its records, no model), so the size of a
  meeting never depends on the number of companies.
- Estimate = turn_cap x (speakers x rounds + the devil's challenge + the
  advisor's whispers) per item + the secretary's summary. Over the budget the
  code trims: first the last round of the least important items, then
  speakers (to written statements), then the whispers; `trimmed_fa` says what.
- Only the owner raises a budget (POST /meetings/{ref}/control); PATCH only
  lowers it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import Actor, Model

TYPES = ("board", "company", "standup", "war_room", "postmortem", "strategy")
TypeKey = Literal["board", "company", "standup", "war_room", "postmortem", "strategy"]
ADHOC = ("board", "company", "strategy")
HOLDING_TYPES = ("board", "strategy")  # held in the holding company
SUMMARY_CAP = 20_000  # the secretary's run (input + output), from the meeting's budget
STANDUP_SUMMARY_CAP = 5_000
MIN_SUMMARY = 2_000  # less left than this: the minutes stay code-only
MAX_ITEMS = 8
PREP_AHEAD = timedelta(hours=24)
SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "meetings" / "types.yaml"
IMPORTANCE = {"low": 0, "normal": 1, "high": 2}


# ------------------------------------------------------------------ shapes --
class MeetingType(BaseModel):
    key: str
    title_fa: str
    schedule: str | None
    calendar: str = "gregorian"
    members: dict[str, Any]
    max_rounds: int
    max_speakers: int
    budget_tokens: int | None
    turn_cap_tokens: int
    owner_presence: str
    model_summary: bool = False
    enabled: bool
    version: int


class MeetingTypeIn(Model):
    key: TypeKey
    version: int = Field(ge=1)
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    schedule: str | None = Field(default=None, min_length=6, max_length=200)
    members: dict[str, Any] | None = None
    max_rounds: int | None = Field(default=None, ge=1, le=3)
    max_speakers: int | None = Field(default=None, ge=2, le=8)
    budget_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    turn_cap_tokens: int | None = Field(default=None, ge=500, le=50_000)
    owner_presence: Literal["live", "summary", "audio"] | None = None
    model_summary: bool | None = None
    enabled: bool | None = None


class MeetingSettingsIn(Model):
    types: list[MeetingTypeIn] = Field(min_length=1, max_length=6)


class MeetingParticipant(BaseModel):
    actor: Actor
    role_fa: str
    speaker: bool
    devil: bool


class MeetingBudget(BaseModel):
    cap: int | None
    estimate: int
    reserved: int
    used: int


class MeetingItem(BaseModel):
    id: UUID
    n: int
    title_fa: str
    brief_md: str
    sources: list[dict[str, Any]]
    time_box_min: int
    speakers: list[Actor]
    round: int
    state: str


class MeetingClaim(BaseModel):
    id: UUID
    text_fa: str
    source: dict[str, str] | None
    status: str


class MeetingTurn(BaseModel):
    id: UUID
    meeting: str
    item: UUID | None
    n: int
    round: int
    speaker: Actor
    kind: str
    statement_md: str
    claims: list[MeetingClaim]
    draft_md: str | None
    stance: dict[str, Any] | None
    run_id: UUID | None
    tokens: int
    at: datetime


class MeetingWhisper(BaseModel):
    id: UUID
    meeting: str
    item: UUID
    text_md: str
    sources: list[dict[str, Any]]
    at: datetime


class MeetingDraft(BaseModel):
    id: UUID
    meeting: str
    item: UUID
    text_md: str
    proposer: Actor
    votes: dict[str, int]
    decision: str | None


class MeetingMinutes(BaseModel):
    deliverable: str | None
    summary_md: str | None


class Meeting(BaseModel):
    id: UUID
    ref: str
    type: str
    company: str
    department: str | None = None
    title_fa: str
    starts_at: datetime
    state: str
    mode: str
    budget: MeetingBudget
    trimmed_fa: str | None
    items: list[MeetingItem]
    participants: list[MeetingParticipant]
    owner_presence: str
    # ⟨1.5⟩ "audio" is "summary" until text-to-speech exists (prompt 12)
    presence_note_fa: str | None = None
    minutes: MeetingMinutes | None
    incident: str | None
    drafts: list[MeetingDraft] = Field(default_factory=list)
    version: int
    created_at: datetime


class MeetingTurnsPage(BaseModel):
    items: list[MeetingTurn]
    whispers: list[MeetingWhisper] | None = None
    next_cursor: str | None = None


# --------------------------------------------------------------- the types --
TYPE_SQL = "SELECT * FROM meetings.types"


def render_type(r: dict[str, Any]) -> MeetingType:
    return MeetingType(
        key=r["key"],
        title_fa=r["title_fa"],
        schedule=r["schedule"],
        calendar=r["calendar"],
        members=dict(r["members"] or {}),
        max_rounds=r["max_rounds"],
        max_speakers=r["max_speakers"],
        budget_tokens=r["budget_tokens"],
        turn_cap_tokens=r["turn_cap_tokens"],
        owner_presence=r["owner_presence"],
        model_summary=r["model_summary"],
        enabled=r["enabled"],
        version=r["version"],
    )


def seed_types() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("types") or [])


async def seed(tx: Tx, holding_id: UUID) -> int:
    """The six types of the seed file whose key the holding does not have yet
    (the owner's edits are never overwritten)."""
    added = 0
    for t in seed_types():
        added += await tx.exec(
            """INSERT INTO meetings.types (company_id, key, title_fa, schedule, calendar, members, max_rounds,
                   max_speakers, budget_tokens, turn_cap_tokens, owner_presence, model_summary, enabled)
               VALUES (:co, :key, :title, :sched, :cal, CAST(:members AS jsonb), :rounds, :speakers, :budget,
                       :turn, :presence, :summary, true)
               ON CONFLICT (company_id, key) DO NOTHING""",
            co=holding_id,
            key=t["key"],
            title=t["title_fa"],
            sched=t.get("schedule"),
            cal=t.get("calendar", "gregorian"),
            members=json.dumps(t.get("members") or {}, ensure_ascii=False),
            rounds=int(t.get("max_rounds", 2)),
            speakers=int(t.get("max_speakers", 6)),
            budget=t.get("budget_tokens"),
            turn=int(t.get("turn_cap_tokens", 6000)),
            presence=t.get("owner_presence", "summary"),
            summary=bool(t.get("model_summary", False)),
        )
    return added


async def types(tx: Tx) -> list[dict[str, Any]]:
    holding = await holding_id(tx)
    rows = await tx.all(TYPE_SQL + " WHERE company_id = :co", co=holding)
    if len(rows) < len(TYPES):  # the api's start seeds them; here too if one is missing
        await seed(tx, holding)
        rows = await tx.all(TYPE_SQL + " WHERE company_id = :co", co=holding)
    order = {k: i for i, k in enumerate(TYPES)}
    return sorted(rows, key=lambda r: order.get(r["key"], 99))


async def type_row(tx: Tx, key: str) -> dict[str, Any]:
    hid = await holding_id(tx)
    row = await tx.first(TYPE_SQL + " WHERE company_id = :co AND key = :k", co=hid, k=key)
    if row is None and key in TYPES:
        await seed(tx, hid)
        row = await tx.first(TYPE_SQL + " WHERE company_id = :co AND key = :k", co=hid, k=key)
    if row is None:
        raise ApiError(404, "not_found", f"no meeting type {key}")
    return row


def check_schedule(key: str, calendar: str, schedule: str | None) -> None:
    from hq_api.domain import recurrence as R

    if key in ("war_room", "postmortem"):
        if schedule is not None:
            raise ApiError(
                422, "validation_failed", fields={"schedule": f"{key} is opened by an event"}
            )
        return
    if schedule is None:
        raise ApiError(422, "validation_failed", fields={"schedule": f"{key} needs a schedule"})
    if calendar == "jalali":
        if parse_jalali_monthly(schedule) is None:
            raise ApiError(
                422,
                "validation_failed",
                fields={"schedule": "FREQ=MONTHLY;BYDAY=-1TH;BYHOUR=h(;BYMINUTE=m)"},
            )
        return
    R.parse(schedule)


def parse_jalali_monthly(schedule: str) -> tuple[int, int, int] | None:
    """(weekday 0=Mon, hour, minute) of FREQ=MONTHLY;BYDAY=-1XX: the last such
    day of each Jalali month (the strategy meeting: the last Thursday)."""
    days = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    parts = dict(p.split("=", 1) for p in schedule.split(";") if "=" in p)
    if parts.get("FREQ") != "MONTHLY" or not parts.get("BYDAY", "").startswith("-1"):
        return None
    day = parts["BYDAY"][2:]
    if day not in days or set(parts) - {"FREQ", "BYDAY", "BYHOUR", "BYMINUTE"}:
        return None
    try:
        hour, minute = int(parts.get("BYHOUR", "10")), int(parts.get("BYMINUTE", "0"))
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return days.index(day), hour, minute


async def update_types(tx: Tx, body: MeetingSettingsIn, by_code: str) -> list[dict[str, Any]]:
    """The owner's edit (🔏 meetings.settings): every row carries its version."""
    for t in body.types:
        row = await type_row(tx, t.key)
        if row["version"] != t.version:
            raise ApiError(409, "version_conflict", f"{t.key}: current version is {row['version']}")
        new = {
            **row,
            **{
                k: v
                for k, v in t.model_dump(exclude_unset=True).items()
                if k not in ("key", "version")
            },
        }
        if t.key == "war_room":
            new["budget_tokens"] = (
                None if "budget_tokens" not in t.model_fields_set else t.budget_tokens
            )
            if new["budget_tokens"] is not None:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={"budget_tokens": "the war room has no meeting cap"},
                )
        elif new["budget_tokens"] is None:
            raise ApiError(
                422, "validation_failed", fields={"budget_tokens": f"{t.key} needs a budget"}
            )
        check_schedule(t.key, new["calendar"], new["schedule"])
        members = new["members"] or {}
        if not isinstance(members, dict) or members.get("devil", "inspector") not in (
            "inspector",
            "overseer",
        ):
            raise ApiError(
                422, "validation_failed", fields={"members.devil": "inspector or overseer"}
            )
        await tx.exec(
            """UPDATE meetings.types SET title_fa = :title, schedule = :sched, members = CAST(:members AS jsonb),
                   max_rounds = :rounds, max_speakers = :speakers, budget_tokens = :budget, turn_cap_tokens = :turn,
                   owner_presence = :presence, model_summary = :summary, enabled = :enabled,
                   updated_by_kind = 'owner', updated_by_code = :by
               WHERE id = :id""",
            title=new["title_fa"],
            sched=new["schedule"],
            members=json.dumps(members, ensure_ascii=False),
            rounds=new["max_rounds"],
            speakers=new["max_speakers"],
            budget=new["budget_tokens"],
            turn=new["turn_cap_tokens"],
            presence=new["owner_presence"],
            summary=new["model_summary"],
            enabled=new["enabled"],
            by=by_code,
            id=row["id"],
        )
    return await types(tx)


# ----------------------------------------------------------------- helpers --
async def holding_id(tx: Tx) -> UUID:
    hid: UUID = await tx.scalar(
        "SELECT id FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    return hid


async def people(tx: Tx, codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    rows = await tx.all(
        """SELECT e.code, e.title_fa, e.kind, e.role, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = ANY(:codes)""",
        codes=list(dict.fromkeys(codes)),
    )
    return {r["code"]: r for r in rows}


def who(code: str, known: dict[str, dict[str, Any]]) -> Actor:
    if code == "owner":
        return Actor(kind="owner", code="owner", display_fa="مدیر کل")
    p = known.get(code)
    return Actor(kind="agent", code=code, display_fa=p["title_fa"] if p else None)


async def role_holder(
    tx: Tx, company_id: UUID, *, role: str | None = None, kind: str | None = None
) -> str | None:
    code = await tx.scalar(
        """SELECT code FROM core.employees WHERE company_id = :co AND status = 'active'
             AND (CAST(:role AS text) IS NULL OR role = :role) AND (CAST(:kind AS text) IS NULL OR kind = :kind)
           ORDER BY created_at LIMIT 1""",
        co=company_id,
        role=role,
        kind=kind,
    )
    return str(code) if code else None


async def operating_companies(tx: Tx) -> list[dict[str, Any]]:
    """Every active operating company, by code (data: any number of them)."""
    return await tx.all(
        "SELECT id, code FROM core.companies WHERE kind = 'company' AND status = 'active' ORDER BY code"
    )


async def devil_of(tx: Tx, members: dict[str, Any]) -> str | None:
    """The devil's advocate: the inspector (QC), or the overseer if the owner asked."""
    hid = await holding_id(tx)
    if members.get("devil") == "overseer":
        return await role_holder(tx, hid, role="overseer") or await role_holder(
            tx, hid, role="inspector"
        )
    return await role_holder(tx, hid, role="inspector") or await role_holder(
        tx, hid, role="overseer"
    )


async def recent_reports(tx: Tx, company_id: UUID, *, limit: int = 2) -> list[dict[str, str]]:
    """The company CEO's latest outputs of the week (refs, never new text)."""
    rows = await tx.all(
        """SELECT d.ref FROM cartable.deliverables d JOIN core.employees e ON e.id = d.producer_id
           WHERE d.company_id = :co AND e.kind = 'ceo' AND d.created_at > now() - interval '7 days'
           ORDER BY d.created_at DESC LIMIT :n""",
        co=company_id,
        n=limit,
    )
    return [{"kind": "deliverable", "ref": r["ref"], "note": ""} for r in rows]


async def optional_rows(tx: Tx, table: str, sql: str, **params: Any) -> list[dict[str, Any]]:
    """Rows of a table another part of prompt 11 makes (OKRs, risks): none when
    it does not exist here, and a mismatch never breaks the agenda."""
    if not await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table):
        return []
    await tx.exec("SAVEPOINT optional_rows")
    try:
        rows = await tx.all(sql, **params)
    except Exception:  # noqa: BLE001 - another half's schema: skip, never fail the agenda
        await tx.exec("ROLLBACK TO SAVEPOINT optional_rows")
        return []
    await tx.exec("RELEASE SAVEPOINT optional_rows")
    return rows


# ------------------------------------------------------------------ agenda --
@dataclass
class Item:
    title_fa: str
    brief_md: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    time_box_min: int = 10
    importance: str = "normal"
    origin: str = "code"
    owner_code: str | None = None
    speakers: list[str] = field(default_factory=list)
    devil: str | None = None
    writers: list[str] = field(default_factory=list)
    rounds: int = 2
    request_id: UUID | None = None


def _speakers(
    first: list[str | None], devil: str | None, max_speakers: int
) -> tuple[list[str], list[str]]:
    """(speakers with the devil last, the overflow that writes instead)."""
    room = max_speakers - (1 if devil else 0)
    seen: list[str] = []
    for c in first:
        if c and c not in seen and c != devil:
            seen.append(c)
    speakers, overflow = seen[:room], seen[room:]
    if devil:
        speakers.append(devil)
    return speakers, overflow


async def _requests(tx: Tx, type_: str, for_company: UUID, limit: int) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT r.id, r.ref, r.title_fa, r.brief_md, r.sources, r.by_code, r.company_id, c.code AS company
           FROM meetings.requests r JOIN core.companies c ON c.id = r.company_id
           WHERE r.type = :t AND r.for_company_id = :co AND r.status = 'open' ORDER BY r.created_at LIMIT :n""",
        t=type_,
        co=for_company,
        n=limit,
    )


async def build_agenda(
    tx: Tx, m: dict[str, Any], t: dict[str, Any], *, owner_items: list[dict[str, Any]] | None = None
) -> list[Item]:
    """The agenda of a meeting by rule (T-24h, or at once for the owner's own)."""
    members = dict(t["members"] or {})
    max_sp, rounds = int(t["max_speakers"]), int(t["max_rounds"])
    devil = await devil_of(tx, members)
    hid = await holding_id(tx)
    head = await role_holder(tx, hid, role="aiops_head")
    items: list[Item] = []
    for o in owner_items or []:
        concerned = o.get("companies") or []
        heads = [
            await role_holder(tx, c["id"], kind="ceo")
            for c in await operating_companies(tx)
            if c["code"] in concerned
        ]
        sp, over = _speakers([*heads, head], devil, max_sp)
        items.append(
            Item(
                title_fa=o["title_fa"], brief_md=o.get("brief_md", ""), sources=o.get("sources") or [],
                importance="high", origin="owner", owner_code=sp[0] if sp and sp[0] != devil else head,
                speakers=sp, devil=devil, writers=over, rounds=rounds,
            )
        )  # fmt: skip
    if m["type"] in ("board", "strategy"):
        companies = await operating_companies(tx)
        ceos: list[str] = []
        for co in companies:
            ceo_code = await role_holder(tx, co["id"], kind="ceo")
            if ceo_code:
                ceos.append(ceo_code)
        if m["type"] == "board":
            sources = [s for co in companies for s in await recent_reports(tx, co["id"])]
            items.append(
                Item(
                    title_fa="گزارش هفتگی شرکت‌ها", brief_md="بیانیه‌ی نوشته‌ی هر شرکت با ارجاع به خروجی‌های هفته.",
                    sources=sources, importance="normal", writers=ceos, rounds=0,
                )
            )  # fmt: skip
            proposals = await tx.all(
                """SELECT d.ref, d.title, d.proposer_code, d.company_id, c.code AS company FROM cartable.decisions d
                   JOIN core.companies c ON c.id = d.company_id
                   WHERE d.kind = 'proposal' AND d.status = 'pending' AND c.kind = 'company'
                   ORDER BY d.created_at LIMIT :n""",
                n=MAX_ITEMS,
            )
            for p in proposals:
                ceo = await role_holder(tx, p["company_id"], kind="ceo")
                owner = p["proposer_code"] if await _active(tx, p["proposer_code"]) else ceo
                sp, over = _speakers([owner, ceo, head], devil, max_sp)
                items.append(
                    Item(
                        title_fa=f"پیشنهاد رشد: {p['title']}"[:300],
                        brief_md=f"پیشنهاد {p['ref']} ({p['company']}) در کارتابل.",
                        sources=[{"kind": "decision", "ref": p["ref"], "note": ""}], owner_code=owner,
                        speakers=sp, devil=devil, writers=over, rounds=rounds,
                    )
                )  # fmt: skip
        else:
            sp, over = _speakers([head, *ceos], devil, max_sp)
            items.append(
                Item(
                    title_fa="هدف‌های ماه بعد", brief_md="پیش‌نویس هدف‌های ماه بعد هر شرکت، از روی گزارش‌ها و کارت‌ها.",
                    sources=[s for co in companies for s in await recent_reports(tx, co["id"], limit=1)],
                    importance="high", owner_code=head or (sp[0] if sp else None),
                    speakers=sp, devil=devil, writers=over, rounds=rounds,
                )
            )  # fmt: skip
        for r in await _requests(tx, m["type"], m["company_id"], MAX_ITEMS):
            ceo = await role_holder(tx, r["company_id"], kind="ceo")
            sp, over = _speakers([r["by_code"], ceo, head], devil, max_sp)
            items.append(
                Item(
                    title_fa=r["title_fa"], brief_md=r["brief_md"], sources=list(r["sources"] or []), origin="agent",
                    importance="low", owner_code=r["by_code"], speakers=sp, devil=devil, writers=over,
                    rounds=rounds, request_id=r["id"],
                )
            )  # fmt: skip
    elif m["type"] == "company":
        co = m["company_id"]
        ceo = await role_holder(tx, co, kind="ceo")
        managers = [
            r["code"]
            for r in await tx.all(
                """SELECT e.code FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
                   WHERE e.company_id = :co AND e.kind = 'manager' AND e.status = 'active' ORDER BY d.sort, e.code""",
                co=co,
            )
        ]
        sp, over = _speakers([ceo], devil, max_sp)
        items.append(
            Item(
                title_fa=f"گزارش هفتگی {m['company']}", brief_md="گزارش هفته با ارجاع به خروجی‌ها.",
                sources=await recent_reports(tx, co), owner_code=ceo, speakers=sp, devil=devil, rounds=rounds,
            )
        )  # fmt: skip
        proposals = await tx.all(
            """SELECT ref, title, proposer_code FROM cartable.decisions
               WHERE company_id = :co AND kind = 'proposal' AND status = 'pending' ORDER BY created_at LIMIT :n""",
            co=co,
            n=MAX_ITEMS,
        )
        for p in proposals:
            owner = p["proposer_code"] if await _active(tx, p["proposer_code"]) else ceo
            sp, over = _speakers([ceo, owner], devil, max_sp)
            items.append(
                Item(
                    title_fa=f"پیشنهاد رشد: {p['title']}"[:300], brief_md=f"پیشنهاد {p['ref']} در کارتابل.",
                    sources=[{"kind": "decision", "ref": p["ref"], "note": ""}], importance="normal",
                    owner_code=owner, speakers=sp, devil=devil, writers=[], rounds=rounds,
                )
            )  # fmt: skip
        okrs = await optional_rows(
            tx,
            "governance.objectives",
            "SELECT ref FROM governance.objectives WHERE company_id = :co AND status = 'active' ORDER BY ref LIMIT 5",
            co=co,
        )
        if okrs:
            sp, _ = _speakers([ceo, *managers[:2]], devil, max_sp)
            items.append(
                Item(
                    title_fa="OKR فصل", brief_md="پیشرفت هدف‌ها و check-inهای دیرکرده.",
                    sources=[{"kind": "okr", "ref": r["ref"], "note": ""} for r in okrs], owner_code=ceo,
                    speakers=sp, devil=devil, rounds=rounds,
                )
            )  # fmt: skip
        risks = await optional_rows(
            tx,
            "governance.risks",
            """SELECT ref FROM governance.risks WHERE company_id = :co AND status NOT IN ('closed', 'accepted')
                 AND likelihood * impact >= 15 ORDER BY likelihood * impact DESC LIMIT 5""",
            co=co,
        )
        if risks:
            sp, _ = _speakers([ceo, *managers[:1]], devil, max_sp)
            items.append(
                Item(
                    title_fa="ریسک‌های باز بالای ۱۵", brief_md="ریسک‌های پرامتیاز و راه کاهششان.",
                    sources=[{"kind": "risk", "ref": r["ref"], "note": ""} for r in risks], owner_code=ceo,
                    speakers=sp, devil=devil, rounds=rounds,
                )
            )  # fmt: skip
        for r in await _requests(tx, "company", co, MAX_ITEMS):
            sp, over = _speakers([r["by_code"], ceo], devil, max_sp)
            items.append(
                Item(
                    title_fa=r["title_fa"], brief_md=r["brief_md"], sources=list(r["sources"] or []), origin="agent",
                    importance="low", owner_code=r["by_code"], speakers=sp, devil=devil, writers=over,
                    rounds=rounds, request_id=r["id"],
                )
            )  # fmt: skip
    elif m["type"] == "postmortem":
        items.append(await postmortem_item(tx, m, t, devil))
    return items[:MAX_ITEMS]


async def postmortem_item(tx: Tx, m: dict[str, Any], t: dict[str, Any], devil: str | None) -> Item:
    from hq_api.domain import meeting_flow as F

    inc = await tx.first("SELECT * FROM ops.incidents WHERE id = :id", id=m["incident_id"])
    room = await tx.first(
        "SELECT participants FROM meetings.meetings WHERE incident_id = :id AND type = 'war_room'",
        id=m["incident_id"],
    )
    first = [
        p["actor"]["code"] for p in (room["participants"] if room else []) if not p.get("devil")
    ]
    if not first:
        first = [c for c in await F.responders(tx, m["company_id"]) if c]
    cto = await role_holder(tx, m["company_id"], role="cto")
    owner = cto if cto in first else (first[0] if first else None)
    sp, over = _speakers([owner, *first], devil, int(t["max_speakers"]))
    timeline = await F.timeline(tx, inc) if inc else ""
    work = (
        await tx.scalar("SELECT ref FROM work.work WHERE id = :w", w=inc["work_id"])
        if inc and inc["work_id"]
        else None
    )
    sources = [{"kind": "incident", "ref": m["incident_ref"], "note": ""}] + (
        [{"kind": "work", "ref": work, "note": ""}] if work else []
    )
    return Item(
        title_fa=f"کالبدشکافی {m['incident_ref']}", brief_md=timeline, sources=sources, importance="high",
        owner_code=owner, speakers=sp, devil=devil, writers=over, rounds=1,
    )  # fmt: skip


async def _active(tx: Tx, code: str | None) -> bool:
    if not code:
        return False
    return bool(
        await tx.scalar(
            "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active' AND kind <> 'system'",
            c=code,
        )
    )


# --------------------------------------------------- estimate and the trim --
def item_turns(it: Any, *, whispers: bool) -> int:
    speakers = [s for s in it.speakers if s != it.devil]
    r = int(it.rounds)
    if r <= 0 or not speakers:
        return 0
    return len(speakers) * r + (1 if it.devil else 0) + (r if whispers else 0)


def estimate(items: list[Any], turn_cap: int, *, whispers: bool) -> int:
    turns = sum(item_turns(it, whispers=whispers) for it in items)
    return turns * turn_cap + (SUMMARY_CAP if turns else 0)


def _fmt(n: int) -> str:
    return f"{n // 1000}K" if n >= 1000 else str(n)


def trim(
    items: list[Any], cap: int | None, turn_cap: int, *, whispers: bool
) -> tuple[bool, str | None]:
    """Fit the estimate under the cap by rule; (whispers kept, trimmed_fa)."""
    if cap is None:
        return whispers, None
    first = estimate(items, turn_cap, whispers=whispers)
    if first <= cap:
        return whispers, None
    order = sorted(items, key=lambda it: (IMPORTANCE.get(it.importance, 1), -it.n))
    dropped_rounds: list[str] = []
    dropped_speakers: list[str] = []
    while estimate(items, turn_cap, whispers=whispers) > cap:
        it = next((x for x in order if x.rounds > 1), None)
        if it is None:
            break
        it.rounds -= 1
        dropped_rounds.append(f"دور {it.rounds + 1} دستور {it.n}")
    while estimate(items, turn_cap, whispers=whispers) > cap:
        it = next(
            (
                x
                for x in order
                if len(x.speakers) > 2
                and [s for s in x.speakers if s not in (x.devil, x.owner_code)]
            ),
            None,
        )
        if it is None:
            break
        out = [s for s in it.speakers if s not in (it.devil, it.owner_code)][-1]
        it.speakers.remove(out)
        it.writers.append(out)
        dropped_speakers.append(f"{out} در دستور {it.n}")
    parts = []
    if dropped_rounds:
        parts.append("حذف " + "، ".join(dropped_rounds))
    if dropped_speakers:
        parts.append("بیانیه‌ی نوشته به‌جای نوبت برای " + "، ".join(dropped_speakers))
    if estimate(items, turn_cap, whispers=whispers) > cap and whispers:
        whispers = False
        parts.append("بی نجوای مشاور")
    final = estimate(items, turn_cap, whispers=whispers)
    text = (
        f"برآورد اول {_fmt(first)} بود و از بودجه‌ی {_fmt(cap)} بیشتر شد؛ طبق قاعده: "
        + "؛ ".join(parts or ["هیچ"])
    )
    if final > cap:
        text += f". هنوز {_fmt(final)} است: نوبتی که جا نشود اجرا نمیشود و جلسه به جمع‌بندی میرود"
    return whispers, (text + ".")[:2000]


# --------------------------------------------------- items in the database --
ITEM_SQL = "SELECT * FROM meetings.items"


async def items_of(tx: Tx, meeting_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(ITEM_SQL + " WHERE meeting_id = :m ORDER BY n", m=meeting_id)


@dataclass
class Row:
    """An item row as the estimate sees it (mutable for the trim)."""

    id: UUID
    n: int
    importance: str
    owner_code: str | None
    speakers: list[str]
    devil: str | None
    writers: list[str]
    rounds: int
    state: str


def as_rows(items: list[dict[str, Any]]) -> list[Row]:
    return [
        Row(
            id=r["id"], n=r["n"], importance=r["importance"], owner_code=r["owner_code"],
            speakers=list(r["speakers"] or []), devil=r["devil"], writers=list(r["writers"] or []),
            rounds=r["rounds"], state=r["state"],
        )
        for r in items
    ]  # fmt: skip


async def store_agenda(tx: Tx, m: dict[str, Any], t: dict[str, Any], items: list[Item]) -> None:
    for n, it in enumerate(items, 1):
        await tx.exec(
            """INSERT INTO meetings.items (company_id, meeting_id, n, title_fa, brief_md, sources, time_box_min,
                   importance, origin, owner_code, speakers, devil, writers, rounds, request_id)
               VALUES (:co, :m, :n, :title, :brief, CAST(:src AS jsonb), :tb, :imp, :origin, :owner,
                       CAST(:sp AS jsonb), :devil, CAST(:wr AS jsonb), :rounds, :req)""",
            co=m["company_id"],
            m=m["id"],
            n=n,
            title=it.title_fa[:300],
            brief=it.brief_md[:8000],
            src=json.dumps(it.sources[:20], ensure_ascii=False),
            tb=it.time_box_min,
            imp=it.importance,
            origin=it.origin,
            owner=it.owner_code,
            sp=json.dumps(it.speakers),
            devil=it.devil,
            wr=json.dumps(it.writers),
            rounds=min(it.rounds, int(t["max_rounds"])),
            req=it.request_id,
        )
        if it.request_id:
            await tx.exec(
                "UPDATE meetings.requests SET status = 'placed', meeting_ref = :ref, updated_at = now() WHERE id = :id",
                ref=m["ref"],
                id=it.request_id,
            )
    await refresh_budget(tx, m)


async def refresh_budget(tx: Tx, m: dict[str, Any]) -> dict[str, Any]:
    """Estimate, trim (persisting the trimmed rounds and speakers) and the
    participants, from the items as they are now."""
    settings = dict(m["settings"] or {})
    rows = [r for r in as_rows(await items_of(tx, m["id"])) if r.state != "skipped"]
    whispers = bool(settings.get("whispers_wanted", m["owner_presence"] == "live"))
    turn_cap = int(settings.get("turn_cap_tokens", 6000))
    whispers, trimmed = trim(rows, m["budget_cap"], turn_cap, whispers=whispers)
    for r in rows:
        await tx.exec(
            """UPDATE meetings.items SET rounds = :rounds, speakers = CAST(:sp AS jsonb),
                   writers = CAST(:wr AS jsonb)
               WHERE id = :id
                 AND (rounds, speakers, writers) IS DISTINCT FROM (:rounds, CAST(:sp AS jsonb), CAST(:wr AS jsonb))""",
            rounds=r.rounds,
            sp=json.dumps(r.speakers),
            wr=json.dumps(r.writers),
            id=r.id,
        )
    est = estimate(rows, turn_cap, whispers=whispers)
    settings["whispers"] = whispers
    codes = [c for r in rows for c in [*r.speakers, *r.writers]]
    known = await people(tx, codes)
    parts: dict[str, dict[str, Any]] = {}
    for r in rows:
        for c in r.speakers:
            p = parts.setdefault(c, {"code": c, "speaker": True, "devil": c == r.devil})
            p["speaker"] = True
        for c in r.writers:
            parts.setdefault(c, {"code": c, "speaker": False, "devil": False})
    participants = [
        {
            "actor": who(c, known).model_dump(),
            "role_fa": (known.get(c) or {}).get("title_fa") or c,
            "speaker": p["speaker"],
            "devil": p["devil"],
        }
        for c, p in sorted(parts.items(), key=lambda kv: (kv[1]["devil"], not kv[1]["speaker"]))
    ]
    await tx.exec(
        """UPDATE meetings.meetings SET estimate = :est, trimmed_fa = :tr, settings = CAST(:s AS jsonb),
               participants = CAST(:p AS jsonb)
           WHERE id = :id""",
        est=est,
        tr=trimmed,
        s=json.dumps(settings),
        p=json.dumps(participants, ensure_ascii=False),
        id=m["id"],
    )
    return await load(tx, m["ref"])


# ----------------------------------------------------------------- meetings --
MEETING_SQL = """
    SELECT m.*, c.code AS company FROM meetings.meetings m JOIN core.companies c ON c.id = m.company_id
"""
CALENDAR_SLOT = timedelta(hours=1)  # a meeting's place on the change calendar (§9.2)


async def calendar_cancelled(tx: Tx, ref: str) -> None:
    """A cancelled (missed) meeting leaves the change calendar."""
    await tx.exec(
        """UPDATE governance.calendar_events SET status = 'cancelled', updated_at = now()
           WHERE auto_key = :k AND status = 'planned'""",
        k=f"meeting:{ref}",
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        MEETING_SQL + " WHERE m.ref = :r" + (" FOR UPDATE OF m" if lock else ""), r=ref
    )


async def create(
    tx: Tx,
    *,
    t: dict[str, Any],
    company: dict[str, Any],
    starts_at: datetime,
    title_fa: str | None = None,
    origin: str = "schedule",
    slot_key: str | None = None,
    department: str | None = None,
    incident: dict[str, Any] | None = None,
    by_kind: str = "service",
    by_code: str = "meetings",
    state: str = "scheduled",
) -> dict[str, Any] | None:
    """A meeting row (None when its slot exists already: planning is idempotent)."""
    settings = {
        "max_rounds": t["max_rounds"],
        "max_speakers": t["max_speakers"],
        "turn_cap_tokens": t["turn_cap_tokens"],
        "devil": (t["members"] or {}).get("devil", "inspector"),
        "whispers_wanted": t["owner_presence"] == "live",
        "type_version": t["version"],
    }
    row = await tx.first(
        """INSERT INTO meetings.meetings (company_id, type, department, title_fa, starts_at, state, budget_cap,
               owner_presence, settings, origin, slot_key, incident_id, incident_ref, created_by_kind,
               created_by_code, started_at)
           VALUES (:co, :type, :dept, :title, :at, :state, :cap, :presence, CAST(:s AS jsonb), :origin, :slot,
                   :inc, :inc_ref, :bk, :bc, CASE WHEN :state = 'live' THEN now() END)
           ON CONFLICT (company_id, slot_key) DO NOTHING RETURNING ref""",
        co=company["id"],
        type=t["key"],
        dept=department,
        title=(
            title_fa
            or (
                t["title_fa"] if t["key"] in HOLDING_TYPES else f"{t['title_fa']} {company['code']}"
            )
        )[:300],
        at=starts_at,
        state=state,
        cap=t["budget_tokens"],
        presence=t["owner_presence"],
        s=json.dumps(settings),
        origin=origin,
        slot=slot_key,
        inc=incident["id"] if incident else None,
        inc_ref=incident["ref"] if incident else None,
        bk=by_kind,
        bc=by_code,
    )
    if row is None:
        return None
    m = await load(tx, row["ref"])
    if m["type"] != "standup":  # prompt 11 §9.2: meetings fill the change calendar (by code)
        from hq_api.domain import gov_calendar

        await gov_calendar.insert(
            tx,
            m["company_id"],
            kind="meeting",
            title_fa=m["title_fa"],
            starts_at=m["starts_at"],
            ends_at=m["starts_at"] + CALENDAR_SLOT,
            source={"meeting": m["ref"]},
            risk="low",
            by=("service", "meetings"),
            auto_key=f"meeting:{m['ref']}",
        )
    await events.emit(
        tx,
        m["company"],
        "meeting.scheduled",
        m["ref"],
        {"type": m["type"], "starts_at": m["starts_at"].isoformat(), "company": m["company"]},
    )
    return m


async def prepare(
    tx: Tx, m: dict[str, Any], *, owner_items: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """scheduled -> prep: the agenda by rule, its estimate and its trim."""
    t = await type_row(tx, m["type"])
    if not await tx.scalar("SELECT 1 FROM meetings.items WHERE meeting_id = :m", m=m["id"]):
        await store_agenda(tx, m, t, await build_agenda(tx, m, t, owner_items=owner_items))
    else:
        await refresh_budget(tx, m)
    await tx.exec(
        "UPDATE meetings.meetings SET state = 'prep' WHERE id = :id AND state = 'scheduled'",
        id=m["id"],
    )
    return await load(tx, m["ref"])


# ------------------------------------------------------------------ render --
async def render(tx: Tx, m: dict[str, Any]) -> Meeting:
    items = await items_of(tx, m["id"])
    known = await people(tx, [c for it in items for c in (it["speakers"] or [])])
    drafts = await tx.all(
        """SELECT d.*, i.id AS item_id FROM meetings.drafts d JOIN meetings.items i ON i.id = d.item_id
           WHERE d.meeting_id = :m ORDER BY i.n""",
        m=m["id"],
    )
    dknown = await people(tx, [d["proposer_code"] for d in drafts])
    minutes = (
        MeetingMinutes(deliverable=m["minutes_ref"], summary_md=m["summary_md"])
        if m["minutes_ref"] or m["summary_md"]
        else None
    )
    return Meeting(
        id=m["id"],
        ref=m["ref"],
        type=m["type"],
        company=m["company"],
        department=m["department"],
        title_fa=m["title_fa"],
        starts_at=m["starts_at"],
        state=m["state"],
        mode=m["mode"],
        budget=MeetingBudget(
            cap=m["budget_cap"], estimate=m["estimate"], reserved=m["reserved"], used=m["used"]
        ),
        trimmed_fa=m["trimmed_fa"],
        items=[
            MeetingItem(
                id=it["id"],
                n=it["n"],
                title_fa=it["title_fa"],
                brief_md=it["brief_md"],
                sources=list(it["sources"] or []),
                time_box_min=it["time_box_min"],
                speakers=[who(c, known) for c in it["speakers"] or []],
                round=it["round"],
                state=it["state"],
            )
            for it in items
        ],
        participants=[MeetingParticipant.model_validate(p) for p in m["participants"] or []],
        owner_presence=m["owner_presence"],
        presence_note_fa=(
            "نسخه‌ی صوتی به TTS پرامپت ۱۲ نیاز دارد؛ تا آن موقع خلاصه‌ی نوشته میاید."
            if m["owner_presence"] == "audio"
            else None
        ),
        minutes=minutes,
        incident=m["incident_ref"],
        drafts=[
            MeetingDraft(
                id=d["id"],
                meeting=m["ref"],
                item=d["item_id"],
                text_md=d["text_md"],
                proposer=who(d["proposer_code"], dknown),
                votes={k: int(v) for k, v in (d["votes"] or {}).items()},
                decision=d["decision_ref"],
            )
            for d in drafts
        ],
        version=m["version"],
        created_at=m["created_at"],
    )


async def render_turns(
    tx: Tx, m: dict[str, Any], *, item: UUID | None, after: int | None, limit: int, owner: bool
) -> MeetingTurnsPage:
    rows = await tx.all(
        """SELECT * FROM meetings.turns WHERE meeting_id = :m AND (CAST(:item AS uuid) IS NULL OR item_id = :item)
             AND (CAST(:after AS int) IS NULL OR n > :after) ORDER BY n LIMIT :lim""",
        m=m["id"],
        item=item,
        after=after,
        lim=limit + 1,
    )
    more = len(rows) > limit
    rows = rows[:limit]
    claims = await tx.all(
        "SELECT * FROM meetings.claims WHERE turn_id = ANY(:ids) ORDER BY turn_id, n",
        ids=[r["id"] for r in rows],
    )
    by_turn: dict[UUID, list[MeetingClaim]] = {}
    for c in claims:
        by_turn.setdefault(c["turn_id"], []).append(
            MeetingClaim(
                id=c["id"],
                text_fa=c["text_fa"],
                source={"kind": c["source_kind"], "ref": c["source_ref"]}
                if c["source_kind"]
                else None,
                status=c["status"],
            )
        )
    known = await people(tx, [r["speaker_code"] for r in rows])
    turns = [
        MeetingTurn(
            id=r["id"], meeting=m["ref"], item=r["item_id"], n=r["n"], round=r["round"],
            speaker=who(r["speaker_code"], known), kind=r["kind"], statement_md=r["statement_md"],
            claims=by_turn.get(r["id"], []), draft_md=r["draft_md"], stance=r["stance"], run_id=r["run_id"],
            tokens=int(r["tokens"]), at=r["at"],
        )
        for r in rows
    ]  # fmt: skip
    whispers = None
    if owner:  # the advisor's notes: the owner's only, never a speaker's
        ws = await tx.all(
            """SELECT * FROM meetings.whispers
               WHERE meeting_id = :m AND (CAST(:item AS uuid) IS NULL OR item_id = :item) ORDER BY at""",
            m=m["id"],
            item=item,
        )
        whispers = [
            MeetingWhisper(id=w["id"], meeting=m["ref"], item=w["item_id"], text_md=w["text_md"],
                    sources=list(w["sources"] or []), at=w["at"])
            for w in ws
        ]  # fmt: skip
    return MeetingTurnsPage(
        items=turns, whispers=whispers, next_cursor=str(turns[-1].n) if more and turns else None
    )
