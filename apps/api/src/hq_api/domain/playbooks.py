"""From the session: a playbook, a working group as data the owner can give to any company or
platform (contract §40.2-§40.3, v1.22; the owner, 2026-11-07: «میخوام اون نتیجه به یه اسکیل تبدیل
بشه، به یه فرمان قابل اجرا … که بتونم اونو به شرکت‌های دیگه هم بدم … همون مدل رو برای یوتیوب … برای
تلگرام»).

    draft       POST /orders/{ref}/playbook: the holder's one model call (task class
                `playbook_draft`) over the session's memory, plan, hires, automations, lines and
                the last turns; what comes back is checked by code (a seat's role must be a real
                charter — the company's roles through automations.normalize_role; a routine's
                RRULE through recurrence.parse; anything unknown is dropped with a note). Stored
                `draft`, a `playbook` card «کارگروه از این جلسه» posted in the session. Without
                the model: the skeleton code builds from the hires and the automations.
    edit        PATCH /playbooks/{ref} (draft only); in words: the holder offers a `playbook`
                card with the full new draft (talk.cards runs `rewrite`).
    seal        POST /playbooks/{ref}/seal 🔏 playbook.seal: a growth.groups row (key pb_…,
                eligibility `chosen`: nobody joins by itself) and the session's company its first
                member, the seats resolved to the session's hires, the empty ones to automatic
                hiring (§29.10) inside the envelope; its routines run on the groups' tick as
                every group's do. A draft from a session opened by `apply` records `parent`.
    apply       POST /playbooks/{ref}/apply: `as_is` (sealed only) joins the company to the group
                at once; else a new order for that company whose first word is the playbook as
                Markdown and the owner's note (its session records `source`).
    retire      POST /playbooks/{ref}/retire 🔏 playbook.retire: the group `off` (its routines stop
                for every member), the playbook `retired`; nothing is deleted.

The playbooks are the holding's rows (RLS); every write is audited by the routes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import automations as AU
from hq_api.domain import flow_shapes as FS
from hq_api.domain import groups as GR
from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import playbook_versions as PV
from hq_api.domain import recurrence
from hq_api.domain.connections import KINDS as CONNECTION_KINDS
from hq_api.errors import ApiError
from hq_api.schemas import Model
from hq_api.talk.scrub import clean
from hq_common import persian

log = logging.getLogger("hq_api.playbooks")

TASK_CLASS = "playbook_draft"
PLATFORMS = ("instagram", "youtube", "telegram", "site", "any")
PLATFORM_FA = {"instagram": "اینستاگرام", "youtube": "یوتیوب", "telegram": "تلگرام", "site": "سایت",
               "any": "هر پلتفرمی"}  # fmt: skip
HELPERS = ("gpt", "gemini", "deepseek", "aistudio")
# a seat is a person of a company: an employee, a department's manager or the CEO (never a
# system role or one of the holding's fixed personas)
SEAT_KINDS = ("employee", "manager", "ceo")
STATES = ("draft", "sealed", "retired")
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
REF = re.compile(r"^PB-[0-9]{4,}$")
# ⟨2026-11-08⟩ audit M5: a routine's default budget is a media director's floor (three real
# steps of 40 000), never below a seat's floor (work.raise_to_floor at each run)
DEFAULT_TOKENS = 120_000
MAX_SEATS, MAX_ROUTINES, MAX_KPIS, MAX_RULES, MAX_CONNECTIONS = 12, 12, 12, 20, 10
LAST_TURNS = 30
TURN_CHARS = 1_200
NOT_FOUND_FA = "این کارگروه پیدا نشد."
SYSTEM_FA = "سامانه"
Platform = Literal["instagram", "youtube", "telegram", "site", "any"]
State = Literal["draft", "sealed", "retired"]


# ------------------------------------------------------------------ shapes --
class PlaybookSeat(BaseModel):
    seat: str
    role: str
    title_fa: str
    duties_fa: str = ""
    helpers: list[str] = Field(default_factory=list)
    model: str | None = None


class PlaybookRoutine(BaseModel):
    key: str
    title_fa: str
    seat: str
    schedule: str  # RRULE, the owner's time zone
    brief_md: str
    # ⟨additive⟩ the run's budget (a group routine's max_tokens)
    max_tokens: int = DEFAULT_TOKENS


class PlaybookKpi(BaseModel):
    key: str
    title_fa: str
    source: str
    # ⟨additive⟩ the figure's unit (a group KPI's)
    unit: str = ""


class PlaybookSource(BaseModel):
    order: str
    company: str | None
    conversation: str | None


class PlaybookMember(BaseModel):
    company: str
    name_fa: str
    state: Literal["on", "paused"]
    order: str | None = None
    # ⟨§45⟩ the owner's standing word on publishing for this company (`ask` unless he said `auto`)
    publish: GR.MemberPublish = Field(default_factory=GR.MemberPublish)
    # ⟨1.37⟩ §59.1 the version this company runs, and its flow automation
    version: int | None = None
    automation: str | None = None


class Playbook(BaseModel):
    ref: str
    title_fa: str
    purpose_fa: str
    state: State
    version: int
    platform: Platform
    seats: list[PlaybookSeat] = Field(default_factory=list)
    routines: list[PlaybookRoutine] = Field(default_factory=list)
    kpis: list[PlaybookKpi] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    rules_fa: list[str] = Field(default_factory=list)
    source: PlaybookSource
    members: list[PlaybookMember] = Field(default_factory=list)
    parent: str | None = None
    created_at: datetime
    sealed_at: datetime | None = None
    # ⟨additive⟩ when it was retired; the working group it became (growth.groups key); the
    # drafter's notes (what was dropped and why, the model missing)
    retired_at: datetime | None = None
    group: str | None = None
    note_fa: str | None = None
    # ⟨1.37⟩ §59.1 `version` is the number of THIS body (v1 at the first seal); `edits` what it
    # counted before (each PATCH of a draft); a newer draft's number; every version newest
    # first; the flow, the package and the lessons (empty in the list); the last 30 days of its
    # flow runs; the member companies' names
    edits: int = 0
    draft_version: int | None = None
    versions: list[FS.VersionRef] = Field(default_factory=list)
    steps: list[FS.FlowStep] = Field(default_factory=list)
    package: list[FS.PackageFile] = Field(default_factory=list)
    lessons: list[FS.Lesson] = Field(default_factory=list)
    stats: FS.PlaybookStats = Field(default_factory=FS.PlaybookStats)
    companies_fa: list[str] = Field(default_factory=list)


class StepIn(FS.FlowStep):
    """A step as PATCH takes it: `settings` left out keeps the step's own (the app 1.1.0 does not
    carry them)."""

    settings: dict[str, object] | None = None  # type: ignore[assignment]


class PlaybookPatch(Model):
    """PATCH /playbooks/{ref} (the newest draft only): any field of the shape but ref, state,
    source; ⟨1.37⟩ `steps`, `package` and `lessons` too, each list whole."""

    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    purpose_fa: str | None = Field(default=None, max_length=2000)
    platform: Platform | None = None
    seats: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_SEATS)
    routines: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_ROUTINES)
    kpis: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_KPIS)
    connections: list[str] | None = Field(default=None, max_length=MAX_CONNECTIONS)
    rules_fa: list[str] | None = Field(default=None, max_length=MAX_RULES)
    steps: list[StepIn] | None = Field(default=None, max_length=PV.MAX_STEPS)
    package: list[FS.PackageFile] | None = Field(default=None, max_length=PV.MAX_PACKAGE)
    lessons: list[FS.Lesson] | None = Field(default=None, max_length=PV.MAX_LESSONS)


class PublishRuleIn(Model):
    """⟨§45⟩ The owner's standing word on publishing for one company in the working group."""

    mode: Literal["ask", "auto"]
    account: str | None = Field(default=None, max_length=65)
    story: bool = False
    # ⟨§46⟩ «HH:MM» in the owner's zone: the hour each day's package goes out at
    at: str | None = Field(default=None, max_length=5)
    # ⟨§49⟩ the hour the account's own posts did best at, once there is a month of them
    best: bool = False


class PlaybookApplyIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    platform: Platform | None = None
    note_fa: str | None = Field(default=None, max_length=2000)
    as_is: bool = False
    # ⟨§45⟩ with `as_is`: his standing word on publishing for that company
    publish: PublishRuleIn | None = None


class PlaybookApplied(BaseModel):
    playbook: Playbook
    # as_is: the membership made; else the new session (its order and its talk)
    member: PlaybookMember | None = None
    order: str | None = None
    conversation: str | None = None


class DraftIn(Model):
    """⟨1.37⟩ §59.3 POST /orders/{ref}/playbook: `playbook` makes the draft that playbook's next
    version; `log_md` the session's fault log when the hub cannot read it itself (a direct
    session's NOTES.md lives in its workshop folder)."""

    playbook: str | None = Field(default=None, pattern=r"^PB-[0-9]{4,}$")
    log_md: str | None = Field(default=None, max_length=60_000)


class MemberVersionIn(Model):
    version: int = Field(ge=1)


class PlaybookCopyIn(Model):
    version: int | None = Field(default=None, ge=1)
    platform: Platform | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    note_fa: str | None = Field(default=None, max_length=2000)


# ----------------------------------------------------------------- normalise --
def _slug(raw: Any, fallback: str) -> str | None:
    word = " ".join(str(raw or "").split()).lower().replace("-", "_").replace(" ", "_")
    word = re.sub(r"[^a-z0-9_]", "", word)[:40]
    if KEY.match(word):
        return word
    return fallback if KEY.match(fallback) else None


def _text(v: Any, limit: int) -> str:
    return clean(" ".join(str(v or "").split()))[0][:limit]


def _md(v: Any, limit: int) -> str:
    return clean(str(v or "").strip())[0][:limit]


def normalise(
    raw: dict[str, Any], roles: AU.Roles | None, lib: Any, notes: list[str]
) -> dict[str, Any]:
    """The Playbook shape from what a model (or the owner) wrote: a seat's role a real charter
    (the company's roles, as an automation's role is read), a routine on a kept seat with a
    schedule the calendar holds, a KPI with its source, known connection kinds; anything else is
    dropped with a plain note. Never refuses."""
    title = _text(raw.get("title_fa"), 200) or "کارگروه از این جلسه"
    purpose = _text(raw.get("purpose_fa"), 2000)
    platform = str(raw.get("platform") or "any").strip().lower()
    if platform not in PLATFORMS:
        if platform:
            notes.append(f"پلتفرم «{platform[:30]}» شناخته نیست؛ «هر پلتفرمی» گذاشته شد.")
        platform = "any"
    seats: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, s in enumerate(raw.get("seats") or []):
        if not isinstance(s, dict) or len(seats) >= MAX_SEATS:
            continue
        role, note = AU.normalize_role(s.get("role"), roles)
        charter = lib.get(role) if lib is not None and role else None
        if role is None or note is not None or charter is None or charter.kind not in SEAT_KINDS:
            word = _text(s.get("role") or s.get("title_fa"), 40) or f"#{i + 1}"
            notes.append(f"جایگاه «{word}» حذف شد: کسی با این نقش منشور ندارد.")
            continue
        key = _slug(s.get("seat"), role)
        if key is None or key in seen:
            key = role if role not in seen else f"{role}_{len(seats) + 1}"
        if key in seen:
            continue
        seen.add(key)
        helpers = [h for h in (s.get("helpers") or []) if isinstance(h, str) and h in HELPERS]
        seat_fa = _text(s.get("title_fa"), 200) or str(charter.title_fa)
        for h in s.get("helpers") or []:
            if h not in HELPERS and str(h).strip():
                notes.append(f"ابزار «{str(h)[:30]}» در هاب نیست و از «{seat_fa[:40]}» برداشته شد.")
        model = _text(s.get("model"), 60) or None
        seats.append(
            {
                "seat": key,
                "role": role,
                "title_fa": _text(s.get("title_fa"), 200) or str(charter.title_fa),
                "duties_fa": _text(s.get("duties_fa"), 1000),
                "helpers": list(dict.fromkeys(helpers)),
                "model": model,
            }
        )
    routines: list[dict[str, Any]] = []
    rkeys: set[str] = set()
    for i, r in enumerate(raw.get("routines") or []):
        if not isinstance(r, dict) or len(routines) >= MAX_ROUTINES:
            continue
        title_r = _text(r.get("title_fa"), 200) or f"روال {i + 1}"
        seat = _slug(r.get("seat"), "")
        if seat is None or seat not in seen:
            # the seat written as a role or a title: the kept seat of that role
            role, _ = AU.normalize_role(r.get("seat"), roles)
            seat = next((s["seat"] for s in seats if s["role"] == role), None)
        if seat is None:
            notes.append(f"روال «{title_r[:40]}» حذف شد: جایگاهش در کارگروه نیست.")
            continue
        schedule = _text(r.get("schedule"), 200).upper().removeprefix("RRULE:")
        try:
            recurrence.parse(schedule)
        except ApiError:
            notes.append(f"روال «{title_r[:40]}» حذف شد: زمان‌بندی‌اش (RRULE) درست نیست.")
            continue
        brief = _md(r.get("brief_md"), 6000)
        if len(brief) < 3:
            notes.append(f"روال «{title_r[:40]}» حذف شد: شرح کار ندارد.")
            continue
        key = _slug(r.get("key"), f"routine_{i + 1}")
        if key is None or key in rkeys:
            key = f"routine_{len(routines) + 1}"
        rkeys.add(key)
        try:
            tokens = int(r.get("max_tokens") or DEFAULT_TOKENS)
        except (TypeError, ValueError):
            tokens = DEFAULT_TOKENS
        routines.append(
            {
                "key": key,
                "title_fa": title_r,
                "seat": seat,
                "schedule": schedule,
                "brief_md": brief,
                "max_tokens": max(1_000, min(tokens, 2_000_000)),
            }
        )
    kpis: list[dict[str, Any]] = []
    kkeys: set[str] = set()
    for i, k in enumerate(raw.get("kpis") or []):
        if not isinstance(k, dict) or len(kpis) >= MAX_KPIS:
            continue
        title_k = _text(k.get("title_fa"), 200)
        source = _text(k.get("source"), 200)
        key = _slug(k.get("key"), f"kpi_{i + 1}")
        if not title_k or not source or key is None or key in kkeys:
            notes.append(f"شاخص «{title_k[:40] or f'#{i + 1}'}» حذف شد: عنوان یا منبع ندارد.")
            continue
        kkeys.add(key)
        kpis.append({"key": key, "title_fa": title_k, "source": source,
                     "unit": _text(k.get("unit"), 40)})  # fmt: skip
    connections: list[str] = []
    for c in raw.get("connections") or []:
        kind = str(c or "").strip().lower()
        if kind in CONNECTION_KINDS and kind not in connections:
            connections.append(kind)
        elif kind:
            notes.append(f"اتصال «{kind[:30]}» شناخته نیست و حذف شد.")
    rules = [
        _text(x, 300) for x in (raw.get("rules_fa") or []) if isinstance(x, str) and _text(x, 300)
    ]
    return {
        "title_fa": title,
        "purpose_fa": purpose,
        "platform": platform,
        "seats": seats,
        "routines": routines,
        "kpis": kpis,
        "connections": connections[:MAX_CONNECTIONS],
        "rules_fa": rules[:MAX_RULES],
        # ⟨1.37⟩ §59.1 the flow, the package and the lessons, checked the same way
        **PV.normalise_flow(raw, seats, notes),
    }


def definition_json(d: dict[str, Any]) -> str:
    """The stored part of a normalised shape (the rest are the row's own columns)."""
    return json.dumps(PV.definition_of(d), ensure_ascii=False)


# ------------------------------------------------------------------- reads --
def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def row_of(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM owner.playbooks WHERE ref = :r" + (" FOR UPDATE" if lock else ""),  # noqa: S608
        r=ref,
    )
    if row is None:
        raise ApiError(404, "not_found", "unknown playbook", message_fa=NOT_FOUND_FA)
    return dict(row)


async def members_of(tx: Tx, row: dict[str, Any]) -> list[PlaybookMember]:
    if row.get("group_id") is None:
        return []
    rows = await tx.all(
        """SELECT c.id, c.code, c.name_fa, m.state, m.publish, m.version, m.automation,
                  (SELECT a.ref FROM growth.automations a
                   WHERE a.kind = 'flow' AND a.playbook = :p AND a.company_id = c.id
                   ORDER BY a.created_at DESC LIMIT 1) AS flow
           FROM growth.memberships m JOIN core.companies c ON c.id = m.company_id
           WHERE m.group_id = :g ORDER BY m.joined_at""",
        g=row["group_id"],
        p=row["ref"],
    )
    src = _j(row["source"]) or {}
    out = []
    for r in rows:
        # the session the playbook came from (its own company), else the session that adapted
        # the playbook for this company, if any
        order_ref = src.get("order") if r["code"] == src.get("company") else None
        order_ref = order_ref or await tx.scalar(
            """SELECT r.ref FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
               WHERE r.source_playbook = :p AND o.routes @> CAST(:j AS jsonb)
               ORDER BY r.created_at DESC LIMIT 1""",
            p=row["ref"],
            j=json.dumps([{"company": r["code"]}]),
        )
        out.append(
            PlaybookMember(
                company=r["code"],
                name_fa=r["name_fa"] or r["code"],
                state=r["state"],
                order=order_ref,
                publish=GR.member_publish(r["publish"]),
                # a member from before 1.37 runs v1 (every playbook then had one body)
                version=int(r["version"] or 1),
                automation=r["automation"] or r["flow"],
            )
        )
    return out


async def stats_of(tx: Tx, ref: str) -> FS.PlaybookStats:
    """§59.1 the last 30 days of the playbook's flow runs, every member together: the runs of
    the lines its flow automations run (growth.automations kind `flow`), dry and skipped ones
    left out; the cost and the time of the finished ones."""
    r = await tx.one(
        """WITH a AS (SELECT company_id, line FROM growth.automations
                      WHERE kind = 'flow' AND playbook = :p),
                x AS (SELECT DISTINCT x.id, x.state, x.at, x.started_at, x.ended_at, x.usd_equiv
                      FROM a JOIN lines.lines l ON l.ref = a.line
                      JOIN lines.runs x ON x.line_id = l.id
                      WHERE NOT x.dry AND x.at >= now() - interval '30 days'
                        AND x.state NOT IN ('skipped', 'cancelled'))
           SELECT (SELECT count(*) FROM x) AS runs,
                  (SELECT count(*) FROM x WHERE state = 'done') AS done,
                  (SELECT count(*) FROM x WHERE state IN ('done', 'failed')) AS finished,
                  (SELECT avg(usd_equiv) FROM x WHERE state IN ('done', 'failed')) AS cost,
                  (SELECT avg(EXTRACT(EPOCH FROM ended_at - started_at) / 60.0) FROM x
                   WHERE state = 'done' AND started_at IS NOT NULL AND ended_at IS NOT NULL)
                      AS minutes,
                  (SELECT max(at) FROM x) AS last_at,
                  (SELECT count(DISTINCT company_id) FROM a) AS companies""",
        p=ref,
    )
    finished = int(r["finished"] or 0)
    return FS.PlaybookStats(
        runs=int(r["runs"] or 0),
        done=int(r["done"] or 0),
        success_pct=round(100.0 * int(r["done"] or 0) / finished, 1) if finished else None,
        avg_cost_usd=round(float(r["cost"]), 4) if r["cost"] is not None else None,
        avg_minutes=round(float(r["minutes"]), 1) if r["minutes"] is not None else None,
        last_run_at=r["last_at"],
        companies=int(r["companies"] or 0),
    )


def _items(model: type[BaseModel], raw: Any) -> list[Any]:
    """A stored list read leniently: an item that no longer holds is left out, never a 500."""
    out = []
    for x in raw or []:
        try:
            out.append(model.model_validate(x))
        except ValueError:
            continue
    return out


async def render(
    tx: Tx, row: dict[str, Any], version: int | None = None, *, full: bool = True
) -> Playbook:
    """One playbook at a version (without: its current body, the newest sealed, else the newest
    draft), with every version, its members and the last 30 days of its flow. `full=False` (the
    library list) leaves the steps, the package and the lessons out."""
    vs = await PV.versions(tx, row["id"])
    v = PV.at_version(vs, version) if vs else None
    if v is None:  # a row without its bodies (never after 0066): the row is its own v1
        body: dict[str, Any] = {"title_fa": row["title_fa"], "purpose_fa": row["purpose_fa"],
                                "platform": row["platform"], **(_j(row["definition"]) or {})}  # fmt: skip
        number, state, sealed_at = int(row["version"]), str(row["state"]), row.get("sealed_at")
    else:
        body, number = v.body, v.version
        state = v.state if version is not None else str(row["state"])
        sealed_at = v.sealed_at or row.get("sealed_at")
    src = _j(row["source"]) or {}
    group = None
    members = await members_of(tx, row)
    if row.get("group_id") is not None:
        group = await tx.scalar("SELECT key FROM growth.groups WHERE id = :g", g=row["group_id"])
    on: dict[int | None, int] = {}
    for m in members:
        on[m.version] = on.get(m.version, 0) + 1
    draft = PV.newest_draft(vs)
    parent = row.get("parent")
    if parent and src.get("parent_version"):
        parent = f"{parent}@{int(src['parent_version'])}"
    return Playbook(
        ref=row["ref"],
        title_fa=str(body.get("title_fa") or row["title_fa"]),
        purpose_fa=str(
            body.get("purpose_fa") if body.get("purpose_fa") is not None else row["purpose_fa"]
        ),
        state=state,
        version=number,
        platform=str(body.get("platform") or row["platform"]),
        seats=_items(PlaybookSeat, body.get("seats")),
        routines=_items(PlaybookRoutine, body.get("routines")),
        kpis=_items(PlaybookKpi, body.get("kpis")),
        connections=list(body.get("connections") or []),
        rules_fa=list(body.get("rules_fa") or []),
        source=PlaybookSource(
            order=str(src.get("order") or ""),
            company=src.get("company"),
            conversation=src.get("conversation"),
        ),
        members=members,
        parent=parent,
        created_at=row["created_at"],
        sealed_at=sealed_at,
        retired_at=row.get("retired_at"),
        group=group,
        note_fa=(str(body.get("note_fa") or "") or None)
        if "note_fa" in body
        else row.get("note_fa"),
        edits=int(row.get("edits") or 0),
        draft_version=draft.version if draft is not None and row["state"] != "retired" else None,
        versions=[
            FS.VersionRef(
                version=x.version,
                state=x.state,
                at=x.sealed_at or x.at,
                by_fa=x.by_fa,
                changelog_fa=x.changelog_fa,
                members=on.get(x.version, 0),
            )
            for x in vs
        ],
        steps=_items(FS.FlowStep, body.get("steps")) if full else [],
        package=_items(FS.PackageFile, body.get("package")) if full else [],
        lessons=_items(FS.Lesson, body.get("lessons")) if full else [],
        stats=await stats_of(tx, str(row["ref"])),
        companies_fa=[m.name_fa for m in members],
    )


def _words(text: str) -> str:
    return " ".join(persian.words(text or ""))


async def listing(
    tx: Tx,
    state: str | None,
    platform: str | None = None,
    company: str | None = None,
    q: str | None = None,
) -> list[Playbook]:
    """§59.1 the library, newest first: `state`, `platform`, `company` (a member or the source
    company) and `q` (Persian-normalised words over the title and the purpose, every word)."""
    rows = await tx.all(
        """SELECT * FROM owner.playbooks p
           WHERE (CAST(:st AS text) IS NULL OR p.state = :st)
             AND (CAST(:pl AS text) IS NULL OR p.platform = :pl)
             AND (CAST(:co AS text) IS NULL OR p.source ->> 'company' = :co
                  OR EXISTS (SELECT 1 FROM growth.memberships m
                             JOIN core.companies c ON c.id = m.company_id
                             WHERE m.group_id = p.group_id AND c.code = :co))
           ORDER BY p.created_at DESC LIMIT 200""",
        st=state,
        pl=platform,
        co=company,
    )
    want = _words(q or "").split()
    out = []
    for r in rows:
        if want:
            hay = _words(f"{r['title_fa']} {r['purpose_fa']}")
            if not all(w in hay for w in want):
                continue
        out.append(await render(tx, dict(r), full=False))
    return out


async def of_order(tx: Tx, order_ref: str) -> list[dict[str, Any]]:
    """The playbooks drafted from a session (the holder's context names them)."""
    rows = await tx.all(
        """SELECT ref, state, title_fa, platform FROM owner.playbooks
           WHERE source->>'order' = :o ORDER BY created_at""",
        o=order_ref,
    )
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ the draft --
SYSTEM = (
    "You are the holder of a working session of a holding's owner (مدیر کل). The session reached a "
    "result; turn it into a PLAYBOOK: a reusable working group as data that the owner can give to "
    "any company or platform. Answer exactly one JSON object: {title_fa, purpose_fa, platform, "
    "seats: [{seat, role, title_fa, duties_fa, helpers, model}], routines: [{key, title_fa, seat, "
    "schedule, brief_md}], kpis: [{key, title_fa, source, unit}], connections: [kind], rules_fa: "
    "[str]}. Rules: `role` is one of the `roles` keys given (the company's real charters; never "
    "invent one); `seat` is a short lowercase key; `helpers` only from gpt, gemini, deepseek, "
    "aistudio (as the session decided, e.g. the topic finder works with ChatGPT); `schedule` is an "
    "RRULE in the owner's time zone with FREQ=DAILY|WEEKLY|MONTHLY|HOURLY, BYHOUR, BYMINUTE, BYDAY "
    "(MO..SU, weekly only), BYMONTHDAY (monthly only), no other parts; `brief_md` is the routine's "
    "full instruction to the seat's employee in English, concrete (what to read, what to deliver, "
    "by when), {company_name} and {company} as placeholders for the company it runs in; "
    "`connections` only from the kinds given; `rules_fa` the standing rules the owner set in the "
    "session, in plain Persian. Persian for every *_fa field, Latin digits. Keep what the session "
    "decided; invent nothing it did not; leave out what it did not settle. At most 12 seats and 12 "
    "routines. "
    # ⟨1.37⟩ §59.2-§59.3 the flow, its package and its lessons
    "Also `steps`: the daily FLOW, the owner's own steps in HIS order as the `plan` lists them "
    "(one step per recurring part of the work, never a one-off fix): {key, title_fa, seat, kind, "
    "helper, model, effort, input_fa, output_fa, rules_fa, inputs, gate, optional, max_attempts}; "
    "`kind` one of `step_kinds`; `seat` a seat key above; `helper` one of gpt, gemini, aistudio, "
    "workshop, code, ighub, model or null; `effort` `max` only where the session said the "
    "highest effort (the video's workshop build), else low|medium|high or null; `inputs` the keys "
    "of earlier steps it reads; `gate` `ask` only where the owner wants to approve. `package`: "
    "the files one run hands over [{name, title_fa, step, required}]. `lessons`: from "
    "`fault_log` (each entry: title_fa, cause_fa, fix_fa, rule_fa, the step key it belongs to "
    "or null); a lesson's rule_fa is a short standing rule. When `current_playbook` is given, "
    "this is its NEXT VERSION: start from it, keep what still holds, change what the session "
    "changed, and write `summary_fa`, one plain Persian line of what this version changes."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title_fa", "purpose_fa", "platform", "seats", "routines"],
    "properties": {
        "title_fa": {"type": "string", "maxLength": 200},
        "purpose_fa": {"type": "string", "maxLength": 2000},
        "platform": {"type": "string", "enum": list(PLATFORMS)},
        "seats": {
            "type": "array",
            "maxItems": MAX_SEATS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["seat", "role", "title_fa", "duties_fa", "helpers"],
                "properties": {
                    "seat": {"type": "string", "maxLength": 40},
                    "role": {"type": "string", "maxLength": 60},
                    "title_fa": {"type": "string", "maxLength": 200},
                    "duties_fa": {"type": "string", "maxLength": 1000},
                    "helpers": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(HELPERS)},
                    },
                    "model": {"type": ["string", "null"], "maxLength": 60},
                },
            },
        },
        "routines": {
            "type": "array",
            "maxItems": MAX_ROUTINES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "title_fa", "seat", "schedule", "brief_md"],
                "properties": {
                    "key": {"type": "string", "maxLength": 40},
                    "title_fa": {"type": "string", "maxLength": 200},
                    "seat": {"type": "string", "maxLength": 60},
                    "schedule": {"type": "string", "maxLength": 200},
                    "brief_md": {"type": "string", "maxLength": 6000},
                },
            },
        },
        "kpis": {
            "type": "array",
            "maxItems": MAX_KPIS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "title_fa", "source"],
                "properties": {
                    "key": {"type": "string", "maxLength": 40},
                    "title_fa": {"type": "string", "maxLength": 200},
                    "source": {"type": "string", "maxLength": 200},
                    "unit": {"type": "string", "maxLength": 40},
                },
            },
        },
        "connections": {"type": "array", "items": {"type": "string", "maxLength": 40}},
        "rules_fa": {
            "type": "array",
            "maxItems": MAX_RULES,
            "items": {"type": "string", "maxLength": 300},
        },
        # ⟨1.37⟩ §59.2-§59.3
        "steps": {
            "type": "array",
            "maxItems": PV.MAX_STEPS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "title_fa", "seat", "kind"],
                "properties": {
                    "key": {"type": "string", "maxLength": 40},
                    "title_fa": {"type": "string", "maxLength": 200},
                    "seat": {"type": "string", "maxLength": 60},
                    "kind": {"type": "string", "enum": list(PV.STEP_KINDS)},
                    "helper": {
                        "type": ["string", "null"],
                        "enum": [*sorted(PV.FLOW_HELPERS), None],
                    },
                    "model": {"type": ["string", "null"], "maxLength": 80},
                    "effort": {
                        "type": ["string", "null"],
                        "enum": ["low", "medium", "high", "max", None],
                    },
                    "input_fa": {"type": "string", "maxLength": 500},
                    "output_fa": {"type": "string", "maxLength": 500},
                    "rules_fa": {"type": "array", "items": {"type": "string", "maxLength": 300}},
                    "inputs": {"type": "array", "items": {"type": "string", "maxLength": 40}},
                    "gate": {"type": "string", "enum": ["auto", "ask"]},
                    "optional": {"type": "boolean"},
                    "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3},
                },
            },
        },
        "package": {
            "type": "array",
            "maxItems": PV.MAX_PACKAGE,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "title_fa"],
                "properties": {
                    "name": {"type": "string", "maxLength": 120},
                    "title_fa": {"type": "string", "maxLength": 200},
                    "step": {"type": ["string", "null"], "maxLength": 40},
                    "required": {"type": "boolean"},
                },
            },
        },
        "lessons": {
            "type": "array",
            "maxItems": PV.MAX_LESSONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title_fa", "rule_fa"],
                "properties": {
                    "title_fa": {"type": "string", "maxLength": 300},
                    "cause_fa": {"type": "string", "maxLength": 1000},
                    "fix_fa": {"type": "string", "maxLength": 1000},
                    "rule_fa": {"type": "string", "maxLength": 300},
                    "step": {"type": ["string", "null"], "maxLength": 40},
                },
            },
        },
        "summary_fa": {"type": "string", "maxLength": 300},
    },
}


class Material(BaseModel):
    """What the holder reads to draft: the session, by code."""

    order: str
    text: str
    company: str | None
    conversation: str | None
    holder_key: str | None
    memory_md: str | None
    plan: list[str]
    hires: list[dict[str, Any]]  # the session's people of the company: {key, code, role, title_fa}
    automations: list[dict[str, Any]]
    lines: list[str]
    groups: list[str]
    turns: list[str]
    roles: dict[str, str]
    skeleton: dict[str, Any]
    # ⟨1.37⟩ §59.3 the playbook this draft is the next version of (its ref and the body it
    # starts from), the session's fault log, and the drafter's own summary line
    target: str | None = None
    current: dict[str, Any] | None = None
    fault_log: str | None = None
    summary: str | None = None


async def _hires(tx: Tx, conv: dict[str, Any] | None, company: str | None) -> list[dict[str, Any]]:
    """The session's people of its company (the holder and the participants `role@CODE`), with
    their employee codes: the seats resolve to them."""
    if conv is None or not company:
        return []
    keys = list(dict.fromkeys([str(conv.get("holder") or ""), *(conv.get("present") or [])]))
    out = []
    for key in keys:
        role, _, code = key.partition("@")
        if not role or code != company:
            continue
        emp = await tx.first(
            """SELECT e.code, e.role, e.title_fa FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id
               WHERE c.code = :co AND e.role = :r AND e.status = 'active'
               ORDER BY (e.code = :pref) DESC, e.hired_at LIMIT 1""",
            co=company,
            r=role,
            pref=str(conv.get("holder_code") or ""),
        )
        if emp is not None:
            out.append({"key": key, "code": emp["code"], "role": emp["role"],
                        "title_fa": emp["title_fa"]})  # fmt: skip
    return out


async def _made_by_cards(tx: Tx, conv: dict[str, Any] | None) -> dict[str, list[str]]:
    if conv is None:
        return {}
    rows = await tx.all(
        """SELECT kind, made FROM talk.cards WHERE conversation_id = :c AND state = 'done'
             AND kind IN ('automation', 'line', 'group') ORDER BY created_at""",
        c=conv["id"],
    )
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(str(r["kind"]), []).extend(str(x) for x in r["made"] or [])
    return out


def _skeleton(
    title: str, hires: list[dict[str, Any]], automations: list[dict[str, Any]]
) -> dict[str, Any]:
    """The draft code builds without a model: a seat per person hired into the session, a
    routine per scheduled automation that makes a work for a role."""
    seats = [{"seat": h["role"], "role": h["role"], "title_fa": h["title_fa"], "duties_fa": "",
              "helpers": []} for h in hires]  # fmt: skip
    routines: list[dict[str, Any]] = []
    for a in automations:
        rule = a.get("rule") or {}
        trig = rule.get("trigger") or {}
        for act in rule.get("actions") or []:
            args = act.get("args") or {}
            if (
                trig.get("kind") == "schedule"
                and act.get("kind") == "work.create"
                and args.get("role")
            ):
                routines.append(
                    {
                        "key": _slug(args.get("title_fa"), f"routine_{len(routines) + 1}"),
                        "title_fa": args.get("title_fa") or a.get("sentence_fa"),
                        "seat": args["role"],
                        "schedule": trig.get("rrule"),
                        "brief_md": args.get("brief_fa") or a.get("sentence_fa"),
                    }
                )
    return {"title_fa": title, "purpose_fa": "", "platform": "any", "seats": seats,
            "routines": routines, "kpis": [], "connections": [], "rules_fa": []}  # fmt: skip


async def material(tx: Tx, hub: Any, order_ref: str) -> Material:
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE

    rep = await OR.ensure(tx, order_ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa=SE.NOT_FOUND_FA)
    order = await OR.load_order(tx, order_ref)
    assert order is not None
    conv = None
    if rep.get("conversation_ref"):
        conv = await tx.first(
            "SELECT * FROM talk.conversations WHERE ref = :r", r=rep["conversation_ref"]
        )
        conv = dict(conv) if conv is not None else None
    h = await OT.holder(tx, order_ref)
    company = (
        str(h["company"]) if h is not None and h["company_kind"] != "holding" else None
    ) or OT._company_of(order)
    hires = await _hires(tx, conv, company)
    made = await _made_by_cards(tx, conv)
    # the automations its cards made and ⟨1.36⟩ §58.2 the standing routines said in it (§50)
    automations = [
        {"ref": r["ref"], "sentence_fa": r["sentence_fa"], "rule": _j(r["rule"])}
        for r in await tx.all(
            """SELECT ref, sentence_fa, rule FROM growth.automations
               WHERE ref = ANY(:refs) OR source ->> 'order' = :o ORDER BY created_at""",
            refs=made.get("automation") or [],
            o=order_ref,
        )
    ]
    turns: list[str] = []
    titles: dict[str, str] = {}
    if conv is not None:
        keys = list(dict.fromkeys([str(conv.get("holder") or ""), *(conv.get("present") or [])]))
        titles = {k: (await SE.title_of(tx, k))[0] for k in keys if k}
        rows = await tx.all(
            """SELECT by_kind, persona, text, say_fa, show_md FROM talk.turns
               WHERE conversation_id = :c AND state = 'done' ORDER BY n DESC LIMIT :l""",
            c=conv["id"],
            l=LAST_TURNS,
        )
        for r in reversed(rows):
            who = (
                "مدیر کل"
                if r["by_kind"] == "owner"
                else titles.get(str(r["persona"]), str(r["persona"]))
            )
            what = r["text"] if r["by_kind"] == "owner" else (r["show_md"] or r["say_fa"] or "")
            turns.append(clean(f"{who}: {what}")[0][:TURN_CHARS])
    roles = await AU.company_roles(tx, hub, company) if company else AU.Roles()
    tasks = await SE.tasks_of(tx, rep["order_id"])
    title = SE._title(order.get("text"))
    return Material(
        order=order_ref,
        text=" ".join(str(order.get("text") or "").split())[:1500],
        company=company,
        conversation=rep.get("conversation_ref"),
        holder_key=str(conv.get("holder")) if conv and conv.get("holder") else None,
        memory_md=rep.get("memory_md"),
        plan=[
            f"{t['n']}. {t['title_fa']} [{t['state']}]" for t in tasks if t["state"] != "dropped"
        ],
        hires=hires,
        automations=automations,
        lines=made.get("line") or [],
        groups=made.get("group") or [],
        turns=turns,
        roles=dict(sorted(roles.held.items())),
        skeleton=_skeleton(title, hires, automations),
    )


def body_of(m: Material, holding: str) -> dict[str, Any]:
    prompt = {
        "order": m.text,
        "company": m.company,
        "memory_md": m.memory_md or "",
        "plan": m.plan,
        "people_in_the_session": [{"role": h["role"], "title_fa": h["title_fa"]} for h in m.hires],
        "automations_made": [
            {"sentence_fa": a["sentence_fa"], "rule": a.get("rule")} for a in m.automations
        ],
        "lines_made": m.lines,
        "groups_joined": m.groups,
        "last_turns": m.turns,
        "roles": m.roles,
        "connection_kinds": list(CONNECTION_KINDS),
        "skeleton": m.skeleton,
        # ⟨1.37⟩ §59.2-§59.3
        "step_kinds": list(PV.STEP_KINDS),
    }
    if m.fault_log:
        prompt["fault_log"] = m.fault_log[:FAULT_LOG_CHARS]
    if m.current is not None:
        prompt["current_playbook"] = m.current
    return {
        "company_code": holding,
        "actor_ref": f"playbook:{m.order}",
        "task_class": TASK_CLASS,
        "priority": 2,
        "effort": "medium",
        "system": SYSTEM,
        "prompt": json.dumps(prompt, ensure_ascii=False),
        "json_schema": SCHEMA,
        "max_output_tokens": 16_000 if m.current is not None or m.fault_log else 8_000,
        "timeout_s": 90,
        "meta": {"purpose": "playbook_draft", "order": m.order},
    }


NO_MODEL_FA = "مدل پیش‌نویس نداد؛ این پیش‌نویس را کد از روی آدم‌ها و خودکارسازی‌های جلسه ساخت."
NO_MODEL_NEXT_FA = (
    "مدل پیش‌نویس نداد؛ این نسخه همان نسخه‌ی قبل است و درس‌های دفتر خرابی را کد به آن افزود."
)
FAULT_LOG_CHARS = 30_000
DRAFTER_FA = "مسئول جلسه"


async def target_of(
    tx: Tx, m: Material, given: str | None, source_playbook: str | None
) -> dict[str, Any] | None:
    """⟨1.37⟩ §59.3 the playbook whose next version this session's draft is: the one given, else
    the one the session was opened from when the session is of that working group (its own
    company, a member, or a playbook of no company: a copy or a file). A session that adapts a
    playbook for a company outside its group drafts a playbook of its own with `parent` (§40.3)."""
    if given:
        row = await row_of(tx, given)
        if row["state"] == "retired":
            raise ApiError(409, "validation_failed", "the playbook is retired",
                           message_fa="این کارگروه بازنشسته شده است.")  # fmt: skip
        return row
    if not source_playbook:
        return None
    found = await tx.first("SELECT * FROM owner.playbooks WHERE ref = :r", r=source_playbook)
    if found is None or found["state"] == "retired":
        return None
    row = dict(found)
    company = (_j(row["source"]) or {}).get("company")
    if not company or company == m.company:
        return row
    if (
        m.company
        and row.get("group_id") is not None
        and await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM growth.memberships x JOIN core.companies c
               ON c.id = x.company_id WHERE x.group_id = :g AND c.code = :co)""",
            g=row["group_id"],
            co=m.company,
        )
    ):
        return row
    return None


def _with_log_lessons(raw: dict[str, Any], log_md: str | None) -> dict[str, Any]:
    """Code's lessons from the fault log joined to what came (a lesson the body already has, by
    its title, is kept as it is)."""
    found = PV.lessons_from_log(log_md)
    if not found:
        return raw
    have = [x for x in raw.get("lessons") or [] if isinstance(x, dict)]
    titles = {str(x.get("title_fa") or "") for x in have}
    return {**raw, "lessons": have + [x for x in found if x["title_fa"] not in titles]}


async def draft(
    ctx: Any, order_ref: str, *, playbook: str | None = None, log_md: str | None = None
) -> tuple[dict[str, Any], Material, list[str]]:
    """The holder's one call over the session's material, outside any transaction; what comes
    back normalised by code (or the code's skeleton when the model gives nothing). ⟨1.37⟩ §59.3
    with a target playbook (`playbook`, or the one the session came from) the call starts from
    its newest body and the draft is its next version (`Material.target`); the fault log
    (`log_md`) becomes `lessons`. Answers (the definition, the material, the notes)."""
    from hq_api import workflows_client

    async with ctx.tx() as tx:
        m = await material(tx, ctx.hub, order_ref)
        roles = await AU.company_roles(tx, ctx.hub, m.company) if m.company else None
        rep = await OR.ensure(tx, order_ref)
        target = await target_of(tx, m, playbook, (rep or {}).get("source_playbook"))
        if target is not None:
            vs = await PV.versions(tx, target["id"])
            base = PV.newest_draft(vs) or PV.current(vs)
            m.target = str(target["ref"])
            m.current = PV.shape_of(base.body) if base is not None else None
            src_company = (_j(target["source"]) or {}).get("company")
            if src_company and src_company != m.company:
                roles = await AU.company_roles(tx, ctx.hub, str(src_company))
    m.fault_log = (log_md or "").strip() or None
    holding = await ctx.hub.companies.holding()
    out = await workflows_client.model_call(ctx.hub, body_of(m, holding.code), timeout_s=120)
    notes: list[str] = []
    raw = out if isinstance(out, dict) and out.get("seats") is not None else None
    if raw is None:
        notes.append(NO_MODEL_FA if m.current is None else NO_MODEL_NEXT_FA)
        raw = dict(m.current) if m.current is not None else dict(m.skeleton)
    raw = _with_log_lessons(raw, m.fault_log)
    m.summary = _text(raw.get("summary_fa"), 300) or None
    return normalise(raw, roles, ctx.hub.charters, notes), m, notes


async def _insert(
    tx: Tx,
    company_id: UUID,
    d: dict[str, Any],
    source: dict[str, Any],
    *,
    parent: str | None,
    note: str | None,
    by_kind: str,
    by_fa: str,
    order: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """A new playbook and its v1 draft (⟨1.37⟩ every playbook has its bodies)."""
    row = dict(
        await tx.one(
            """INSERT INTO owner.playbooks (company_id, title_fa, purpose_fa, platform, definition,
                   source, parent, note_fa)
               VALUES (:co, :t, :p, :pl, CAST(:d AS jsonb), CAST(:s AS jsonb), :parent, :note)
               RETURNING *""",
            co=company_id,
            t=d["title_fa"],
            p=d["purpose_fa"],
            pl=d["platform"],
            d=definition_json(d),
            s=json.dumps(source, ensure_ascii=False),
            parent=parent,
            note=note,
        )
    )
    await PV.insert_version(
        tx, row, 1, PV.body_of(d, note_fa=note, summary_fa=summary, order=order),
        by_kind=by_kind, by_fa=by_fa,
    )  # fmt: skip
    return row


async def _in_session(
    tx: Tx, m: Material, ref: str, d: dict[str, Any], notes: list[str], line: str
) -> None:
    """The draft's step and its `playbook` card «کارگروه از این جلسه» in the session."""
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE
    from hq_api.talk import store

    rep = await OR.ensure(tx, m.order)
    assert rep is not None
    if rep.get("closed_at") is None:
        await SE.step(tx, m.order, SE.OWNER_FA, line, remember_line=line)
    else:
        await OR._append_steps(tx, rep["id"], [OR._step(SE.OWNER_FA, line)])
    if m.conversation:
        conv = await store.conversation(tx, m.conversation, lock=True)
        key = OT.holder_key(conv)
        say = f"کارگروه از این جلسه آماده است: {ref}. باز کن، ویرایش کن و مُهر بزن."
        show = say + ("\n\n" + "\n".join(f"- {n}" for n in notes) if notes else "")
        tid = await OT.post_turn(tx, conv, key, say, show)
        card = await store.add_card(
            tx,
            conversation_id=conv["id"],
            turn_id=tid,
            company_id=conv["company_id"],
            kind="playbook",
            title_fa=f"کارگروه از این جلسه: {d['title_fa']}"[:200],
            body_fa=(d["purpose_fa"] or say)[:8000],
            payload={"playbook": ref},
        )
        holding = await OR._holding(tx)
        await events.emit(tx, holding["code"], "talk.card", conv["ref"],
                          {"card": str(card["id"]), "kind": "playbook", "state": "offered"})  # fmt: skip


async def store_draft(
    tx: Tx, holding_id: UUID, m: Material, d: dict[str, Any], notes: list[str]
) -> dict[str, Any]:
    """The draft stored (its `parent` the playbook the session was opened from, if any), one step
    and one `playbook` card in the session. ⟨1.37⟩ §59.3 with `m.target`: that playbook's next
    version (its newest draft rewritten, else a new draft after its newest sealed one); the
    answer's `version` is that draft's number."""
    rep = await OR.ensure(tx, m.order)
    assert rep is not None
    note = "\n".join(notes)[:2000] or None
    if m.target is not None:
        row = await row_of(tx, m.target, lock=True)
        vs = await PV.versions(tx, row["id"], lock=True)
        body = PV.body_of(d, note_fa=note, summary_fa=m.summary, order=m.order)
        dr = PV.newest_draft(vs)
        if dr is not None:
            await PV.write_draft(tx, dr, body, by_kind="agent", by_fa=DRAFTER_FA)
            number = dr.version
            await tx.exec(
                "UPDATE owner.playbooks SET edits = edits + 1 WHERE id = :id", id=row["id"]
            )
        else:
            number = vs[0].version + 1 if vs else 1
            await PV.insert_version(tx, row, number, body, by_kind="agent", by_fa=DRAFTER_FA)
        out = await PV.mirror(tx, row["id"])
        ref = str(row["ref"])
        line = f"نسخه‌ی {number} کارگروه {ref} از این جلسه پیش‌نویس شد «{d['title_fa']}»"
        await _in_session(tx, m, ref, d, notes, line)
        await _emit(tx, ref, "draft", version=number)
        return {**out, "version": number}
    row = await _insert(
        tx, holding_id, d,
        {"order": m.order, "company": m.company, "conversation": m.conversation},
        parent=rep.get("source_playbook"), note=note, by_kind="agent", by_fa=DRAFTER_FA,
        order=m.order, summary=m.summary,
    )  # fmt: skip
    ref = str(row["ref"])
    line = f"کارگروه از این جلسه پیش‌نویس شد: {ref} «{d['title_fa']}»"
    await _in_session(tx, m, ref, d, notes, line)
    await _emit(tx, ref, "draft")
    return row


async def drafted_in(tx: Tx, row: dict[str, Any], order_ref: str) -> bool:
    """⟨1.37⟩ The playbook is this session's to rewrite in words: drafted from it, or its newest
    draft was (§59.3: a version drafted in a later session of the same working group)."""
    if str((_j(row["source"]) or {}).get("order") or "") == order_ref:
        return True
    dr = PV.newest_draft(await PV.versions(tx, row["id"]))
    return dr is not None and str(dr.body.get("order") or "") == order_ref


# ------------------------------------------------------- ⟨1.36⟩ §58.2 kept on close --
KEPT_FA = "کارگروه این جلسه در کتابخانه ماند"
AUTO_FA = (
    "این پیش‌نویس را کد هنگام بستن جلسه از روی آدم‌ها، روال‌ها و خروجی‌های آن ساخت؛ "
    "تا مُهر تو چیزی از آن اجرا نمیشود."
)


async def kept_of(tx: Tx, order_ref: str) -> str | None:
    """The playbook a session left in the library (its newest one not retired), or None."""
    ref: str | None = await tx.scalar(
        """SELECT ref FROM owner.playbooks WHERE source ->> 'order' = :o AND state <> 'retired'
           ORDER BY created_at DESC LIMIT 1""",
        o=order_ref,
    )
    return ref


async def worth_keeping(tx: Tx, order_ref: str) -> bool:
    """A session whose working group is worth keeping: people beyond its holder, a routine, or
    an output with a video or a picture."""
    rep = await tx.first(
        "SELECT conversation_ref FROM owner.order_reports WHERE ref = :r", r=order_ref
    )
    if rep is None:
        return False
    if rep["conversation_ref"]:
        conv = await tx.first(
            "SELECT present, holder FROM talk.conversations WHERE ref = :r",
            r=rep["conversation_ref"],
        )
        people = [
            k for k in (conv or {}).get("present") or []
            if k and k != (conv or {}).get("holder") and not str(k).startswith("player:")
        ]  # fmt: skip
        if people:
            return True
    if await tx.scalar(
        "SELECT EXISTS (SELECT 1 FROM growth.automations WHERE source ->> 'order' = :o)",
        o=order_ref,
    ):
        return True
    order = await OR.load_order(tx, order_ref)
    ids = [w["id"] for w in await OR.tree(tx, OR.root_refs(order or {}))]
    return bool(ids) and bool(
        await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM cartable.deliverables d
                 JOIN files.files f ON f.id = ANY(d.attachments)
                 WHERE d.work_id = ANY(:ids)
                   AND (f.mime LIKE 'video/%' OR f.mime LIKE 'image/%'))""",
            ids=ids,
        )
    )


async def keep_on_close(tx: Tx, hub: Any, order_ref: str) -> str | None:
    """⟨1.36⟩ §58.2 the session closed: its working group drafted by itself into the library
    (code's skeleton now; the holder's model refines it after the answer, refine_kept), when it
    is worth keeping and no playbook (⟨1.37⟩ nor a playbook's version) was drafted from it yet.
    Nothing runs before the owner's seal. Answers the playbook's ref, or None."""
    if await tx.scalar(
        """SELECT EXISTS (SELECT 1 FROM owner.playbooks WHERE source ->> 'order' = :o)
               OR EXISTS (SELECT 1 FROM owner.playbook_versions WHERE body ->> 'order' = :o)""",
        o=order_ref,
    ):
        return None
    if not await worth_keeping(tx, order_ref):
        return None
    m = await material(tx, hub, order_ref)
    roles = await AU.company_roles(tx, hub, m.company) if m.company else None
    notes: list[str] = []
    d = normalise(m.skeleton, roles, hub.charters, notes)
    rep = await OR.ensure(tx, order_ref)
    assert rep is not None
    holding = await OR._holding(tx)
    row = await _insert(
        tx, holding["id"], d,
        {"order": m.order, "company": m.company, "conversation": m.conversation},
        parent=rep.get("source_playbook"), note="\n".join([AUTO_FA, *notes])[:2000],
        by_kind="system", by_fa=SYSTEM_FA, order=m.order,
    )  # fmt: skip
    ref = str(row["ref"])
    await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, f"{KEPT_FA}: {ref}")])
    await _emit(tx, ref, "draft")
    return ref


async def refine_kept(hub: Any, order_ref: str, ref: str) -> None:
    """After the close's answer: the holder's one model call over the session (as POST
    /orders/{ref}/playbook) replaces the skeleton, while the draft is untouched (version 1).
    Without the model the skeleton stays; never fails."""
    from hq_api import workflows_client

    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            m = await material(tx, hub, order_ref)
        holding = await hub.companies.holding()
        out = await workflows_client.model_call(hub, body_of(m, holding.code), timeout_s=120)
        if not (isinstance(out, dict) and out.get("seats") is not None):
            return
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await row_of(tx, ref, lock=True)
            if row["state"] != "draft" or int(row.get("edits") or 0) != 0:
                return  # the owner changed or sealed it meanwhile: his stays
            given = {k: out.get(k) for k in ("title_fa", "purpose_fa", "platform", "seats",
                                             "routines", "kpis", "connections", "rules_fa")}  # fmt: skip
            await patch(tx, hub, ref, given)
    except Exception:  # noqa: BLE001 - the skeleton stays a good draft
        log.warning("the kept playbook was not refined", extra={"playbook": ref})


async def _emit(tx: Tx, ref: str, state: str, **more: Any) -> None:
    holding = await OR._holding(tx)
    await events.emit(tx, holding["code"], "group.playbook", ref, {"state": state, **more})


# ------------------------------------------------------------------- edits --
SEALED_FA = "این نسخه مُهر شده؛ تغییر، نسخه‌ی تازه میسازد"
RETIRED_FA = "این کارگروه بازنشسته شده است."


def _keep_settings(given: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    """PATCH's steps without `settings` keep the step's own (the app does not carry them)."""
    if given.get("steps") is None:
        return given
    old = {str(x.get("key")): x for x in cur.get("steps") or [] if isinstance(x, dict)}
    steps = []
    for st in given["steps"]:
        if isinstance(st, dict) and st.get("settings") is None:
            st = {**st, "settings": dict((old.get(str(st.get("key"))) or {}).get("settings") or {})}
        steps.append(st)
    return {**given, "steps": steps}


async def patch(
    tx: Tx, hub: Any, ref: str, body: dict[str, Any], *, notes: list[str] | None = None
) -> dict[str, Any]:
    """PATCH /playbooks/{ref} and the holder's rewrite: the given fields over the newest draft,
    the whole normalised again (a dropped item leaves a note); `edits` counts up. ⟨1.37⟩ §59.1 a
    sealed playbook with no draft refuses (409): a change makes the next version
    (POST …/revise). Answers the playbook's row with `version` the draft's number."""
    row = await row_of(tx, ref, lock=True)
    if row["state"] == "retired":
        raise ApiError(409, "validation_failed", "the playbook is retired", message_fa=RETIRED_FA)
    vs = await PV.versions(tx, row["id"], lock=True)
    dr = PV.newest_draft(vs)
    if dr is None:
        raise ApiError(409, "validation_failed", "the playbook is sealed and has no draft",
                       message_fa=SEALED_FA)  # fmt: skip
    cur = {"title_fa": row["title_fa"], "purpose_fa": row["purpose_fa"],
           "platform": row["platform"], **dr.body}  # fmt: skip
    given = {k: v for k, v in body.items() if v is not None}
    if not given:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"},
                       message_fa="چیزی برای تغییر داده نشد.")  # fmt: skip
    given = _keep_settings(given, cur)
    src = _j(row["source"]) or {}
    company = src.get("company")
    roles = await AU.company_roles(tx, hub, str(company)) if company else None
    notes = [] if notes is None else notes
    d = normalise({**cur, **given}, roles, hub.charters, notes)
    note = "\n".join(notes)[:2000] or None
    await PV.write_draft(
        tx, dr, PV.body_of(d, note_fa=note, summary_fa=cur.get("summary_fa"),
                           order=cur.get("order")),
    )  # fmt: skip
    await tx.exec(
        "UPDATE owner.playbooks SET edits = edits + 1, updated_at = now() WHERE id = :id",
        id=row["id"],
    )
    out = await PV.mirror(tx, row["id"])
    await _emit(tx, ref, "draft", version=dr.version, edits=int(out["edits"]))
    return {**out, "version": dr.version}


async def revise(tx: Tx, ref: str) -> tuple[dict[str, Any], int, bool]:
    """⟨1.37⟩ §59.1 POST /playbooks/{ref}/revise: the next version as a draft, a copy of the newest
    sealed body; the sealed one keeps running. A draft that is already there is answered as it
    is. Answers (the row, the draft's number, made now)."""
    row = await row_of(tx, ref, lock=True)
    if row["state"] == "retired":
        raise ApiError(409, "validation_failed", "the playbook is retired", message_fa=RETIRED_FA)
    vs = await PV.versions(tx, row["id"], lock=True)
    dr = PV.newest_draft(vs)
    if dr is not None:
        if len(vs) == 1:
            raise ApiError(409, "validation_failed", "not sealed yet",
                           message_fa="این کارگروه هنوز مُهر نشده؛ همین پیش‌نویس را عوض کن.")  # fmt: skip
        return row, dr.version, False
    sealed = vs[0]
    number = sealed.version + 1
    await PV.insert_version(tx, row, number, {**PV.shape_of(sealed.body), "note_fa": None})
    await _emit(tx, ref, "draft", version=number)
    return row, number, True


# -------------------------------------------------------------------- seal --
def group_key(ref: str) -> str:
    return "pb_" + ref.split("-", 1)[1].lower()


def group_definition(row: dict[str, Any]) -> dict[str, Any]:
    """The playbook as a group's definition (groups._canonical's shape), eligibility `chosen`."""
    d = _j(row["definition"]) or {}
    seats = [
        {"seat": s["seat"], "role": s["role"], "title_fa": s["title_fa"], "count": 1,
         "optional": False}
        for s in d.get("seats") or []
    ]  # fmt: skip
    routines = [
        {"key": r["key"], "title_fa": r["title_fa"], "seat": r["seat"], "schedule": r["schedule"],
         "brief_md": r["brief_md"], "max_tokens": int(r.get("max_tokens") or DEFAULT_TOKENS),
         "task_class": None, "needs": None}
        for r in d.get("routines") or []
    ]  # fmt: skip
    kpis = [
        {"key": k["key"], "title_fa": k["title_fa"], "unit": k.get("unit") or "", "source": k["source"],
         "seat": None}
        for k in d.get("kpis") or []
    ]  # fmt: skip
    return {
        "title_fa": str(row["title_fa"]),
        "purpose_fa": " ".join(str(row["purpose_fa"] or "").split()),
        "state": "on",
        "eligible": "chosen",
        "lead": seats[0]["seat"] if seats else None,
        "seats": seats,
        "routines": routines,
        "kpis": kpis,
        "connections": list(d.get("connections") or []),
        "playbook": str(row["ref"]),
    }


async def _group_row(tx: Tx, holding_id: UUID, row: dict[str, Any]) -> dict[str, Any]:
    """The group row of a sealed playbook: made at the seal, versioned on a later seal of the
    same playbook (never happens today: a draft seals once) as groups.seed versions a file."""
    key = group_key(str(row["ref"]))
    d = group_definition(row)
    try:
        GR.validate(key, d)
    except ValueError as exc:
        raise ApiError(
            422,
            "validation_failed",
            fields={"definition": str(exc)[:200]},
            message_fa="این کارگروه هنوز جایگاهی ندارد؛ دست‌کم یک جایگاه با نقش واقعی لازم است.",
        ) from exc
    digest = GR.digest_of(d)
    body = json.dumps(d, ensure_ascii=False)
    cur = await tx.first("SELECT id, version FROM growth.groups WHERE key = :k FOR UPDATE", k=key)
    if cur is None:
        gid = await tx.scalar(
            """INSERT INTO growth.groups (company_id, key, version, digest, title_fa, purpose_fa,
                   definition, state)
               VALUES (:co, :k, 1, :dg, :t, :p, CAST(:d AS jsonb), 'on') RETURNING id""",
            co=holding_id,
            k=key,
            dg=digest,
            t=d["title_fa"],
            p=d["purpose_fa"],
            d=body,
        )
        version = 1
    else:
        gid, version = cur["id"], int(cur["version"]) + 1
        await tx.exec(
            """UPDATE growth.groups SET version = :v, digest = :dg, title_fa = :t, purpose_fa = :p,
                   definition = CAST(:d AS jsonb), state = 'on', updated_at = now() WHERE id = :id""",
            id=gid,
            v=version,
            dg=digest,
            t=d["title_fa"],
            p=d["purpose_fa"],
            d=body,
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
    return dict(await tx.one("SELECT * FROM growth.groups WHERE id = :id", id=gid))


async def join(
    tx: Tx,
    grow: dict[str, Any],
    company: Any,
    *,
    hires: list[dict[str, Any]] | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    """A company joins the playbook's group: the membership (on), its seats first to the session's
    hires (`hires`: {role, code}), then resolved and filled by automatic hiring (§29.10).
    ⟨1.37⟩ a new member runs `version` (one already there keeps its own)."""
    await tx.exec(
        """INSERT INTO growth.memberships (company_id, group_id, version) VALUES (:co, :g, :v)
           ON CONFLICT (group_id, company_id) DO NOTHING""",
        co=company.id,
        g=grow["id"],
        v=version,
    )
    if version is not None:
        await tx.exec(
            """UPDATE growth.memberships SET version = COALESCE(version, :v)
               WHERE group_id = :g AND company_id = :co""",
            g=grow["id"],
            co=company.id,
            v=version,
        )
    await GR.set_member_state(tx, grow, company.id, "on")
    g = GR.render(grow)
    if hires:
        by_role: dict[str, str] = {}
        for h in hires:
            by_role.setdefault(str(h["role"]), str(h["code"]))
        seats = [{"seat": s.seat, "role": s.role, "employee": by_role.get(s.role)} for s in g.seats]
        await tx.exec(
            """UPDATE growth.memberships SET seats = CAST(:s AS jsonb), updated_at = now()
               WHERE group_id = :g AND company_id = :co""",
            g=grow["id"],
            co=company.id,
            s=json.dumps(seats, ensure_ascii=False),
        )
    await GR.reconcile_members(tx, grow, fill=True)
    await events.emit(tx, company.code, "group.run", None, {"group": g.key, "membership": "on"})
    return await GR.member(tx, grow["id"], company.id)


async def seal(tx: Tx, hub: Any, ref: str) -> dict[str, Any]:
    """POST /playbooks/{ref}/seal: ⟨1.37⟩ §59.1 the newest draft becomes version n, frozen, with
    its `changelog_fa` (code's lines against version n−1 and the drafter's summary). The first
    seal makes the group in the database, the session's company its first member (on v1) with
    the seats of the session's hires, the routines from their next time (the groups' tick). A
    later one moves the group's definition to the new body and fills a new seat; every member
    stays on the version it runs until the owner moves it. Answers the playbook's row."""
    from hq_api.domain import sessions as SE

    row = await row_of(tx, ref, lock=True)
    if row["state"] == "retired":
        raise ApiError(409, "validation_failed", "the playbook is retired", message_fa=RETIRED_FA)
    vs = await PV.versions(tx, row["id"], lock=True)
    dr = PV.newest_draft(vs)
    if dr is None:
        raise ApiError(409, "validation_failed", f"the playbook is {row['state']}",
                       message_fa="این کارگروه پیش از این مُهر شده است.")  # fmt: skip
    prev = next((v for v in vs if v.version == dr.version - 1), None)
    await tx.exec(
        """UPDATE owner.playbook_versions SET state = 'sealed', sealed_at = now(),
               changelog_fa = :cl WHERE id = :id""",
        id=dr.id,
        cl=PV.changelog(prev.body if prev is not None else None, dr.body),
    )
    row = await PV.mirror(tx, row["id"])
    holding = await hub.companies.holding()
    first = row.get("group_id") is None
    grow = await _group_row(tx, holding.id, row)
    src = _j(row["source"]) or {}
    member = None
    company = (
        await hub.companies.find(str(src.get("company") or "")) if src.get("company") else None
    )
    if not first:
        await GR.reconcile_members(tx, grow, fill=True)
        out = row
    else:
        if company is not None and company.kind != "holding":
            conv = None
            if src.get("conversation"):
                conv = await tx.first(
                    "SELECT * FROM talk.conversations WHERE ref = :r", r=src["conversation"]
                )
                conv = dict(conv) if conv is not None else None
            hires = await _hires(tx, conv, company.code)
            member = await join(tx, grow, company, hires=hires, version=dr.version)
        out = dict(
            await tx.one(
                """UPDATE owner.playbooks SET state = 'sealed', sealed_at = now(), group_id = :g,
                       updated_at = now() WHERE id = :id RETURNING *""",
                g=grow["id"],
                id=row["id"],
            )
        )
        if company is not None and src.get("order"):
            # ⟨§47⟩ what the session already said (its day one) is the group's from now on
            from hq_api.domain import topics as TP

            await TP.adopt(tx, str(src["order"]), company.id, grow["id"])
    rep = await OR.ensure(tx, str(dr.body.get("order") or src.get("order") or ""))
    if rep is not None:
        if first:
            line = f"کارگروه {ref} مُهر شد و راه افتاد"
            if member is not None:
                filled = sum(1 for s in member.get("seats") or [] if s.get("employee"))
                line += f"؛ {filled} جایگاه از {len(member.get('seats') or [])} پر است"
        else:
            line = f"نسخه‌ی {dr.version} کارگروه {ref} مُهر شد؛ هر شرکت روی نسخه‌ی خودش میماند"
        if rep.get("closed_at") is None:
            await SE.step(tx, str(rep["ref"]), SE.OWNER_FA, line, remember_line=line)
        else:
            await OR._append_steps(tx, rep["id"], [OR._step(SE.OWNER_FA, line)])
    await _emit(tx, ref, "sealed", group=grow["key"], version=dr.version)
    return out


# ------------------------------------------------------------------- apply --
HELPER_FA = {
    "gpt": "ChatGPT",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "aistudio": "Google AI Studio",
}


def _when_fa(rrule: str) -> str:
    """A routine's time in the owner's words (never the RRULE itself)."""
    try:
        return AU.when_fa(rrule)
    except Exception:  # noqa: BLE001 - an odd rule reads as «زمان‌بندی‌شده», never as code
        return "زمان‌بندی‌شده"


def markdown(pb: Playbook) -> str:
    """The playbook in the owner's words: the first word of the session that adapts it. No ref, no
    role key, no RRULE, no helper key (§29.7): titles, plain times and the helpers' names. The
    holder reads the playbook itself, with every key, from its brief (`source_playbook`)."""
    from hq_api.domain.connections import LABEL_FA as CONNECTION_FA

    lines = [f"# کارگروه «{pb.title_fa}»", ""]
    if pb.purpose_fa:
        lines += [pb.purpose_fa, ""]
    lines.append(f"پلتفرم: {PLATFORM_FA.get(pb.platform, pb.platform)}")
    seat_fa = {s.seat: s.title_fa for s in pb.seats}
    if pb.seats:
        lines += ["", "## چه کسانی"]
        for s in pb.seats:
            names = [HELPER_FA.get(h, h) for h in s.helpers]
            helpers = f" (با {' و '.join(names)})" if names else ""
            duties = f": {s.duties_fa}" if s.duties_fa else ""
            lines.append(f"- {s.title_fa}{helpers}{duties}")
    if pb.routines:
        lines += ["", "## کارهای همیشگی"]
        for r in pb.routines:
            who = seat_fa.get(r.seat, "")
            lines.append(f"- {r.title_fa}، {_when_fa(r.schedule)}" + (f"، با {who}" if who else ""))
    if pb.kpis:
        lines += ["", "## چه چیزی را میسنجیم"]
        lines += [f"- {k.title_fa}" for k in pb.kpis]
    if pb.connections:
        lines += ["", "از راه: " + "، ".join(CONNECTION_FA.get(c, c) for c in pb.connections)]
    if pb.rules_fa:
        lines += ["", "## قاعده‌ها"]
        lines += [f"- {x}" for x in pb.rules_fa]
    return "\n".join(lines)


def apply_text(pb: Playbook, company_fa: str, platform: str | None, note_fa: str | None) -> str:
    where = f" روی {PLATFORM_FA.get(platform, platform)}" if platform else ""
    head = f"این کارگروه را برای {company_fa}{where} پیاده کن"
    if note_fa:
        head += f": {' '.join(note_fa.split())}"
    text = head + "\n\n" + markdown(pb)
    return text[:9_900]


async def apply_as_is(tx: Tx, hub: Any, ref: str, company: Any) -> dict[str, Any]:
    row = await row_of(tx, ref, lock=True)
    if row["state"] != "sealed" or row.get("group_id") is None:
        raise ApiError(409, "validation_failed", f"the playbook is {row['state']}",
                       message_fa="عضویت مستقیم فقط برای کارگروه مُهرشده است؛ این یکی را اول مُهر بزن.")  # fmt: skip
    grow = dict(await tx.one("SELECT * FROM growth.groups WHERE id = :g", g=row["group_id"]))
    if grow["state"] != "on":
        await tx.exec("UPDATE growth.groups SET state = 'on', updated_at = now() WHERE id = :id",
                      id=grow["id"])  # fmt: skip
        grow["state"] = "on"
    # ⟨1.37⟩ a new member runs the newest sealed version (the row's current body)
    return await join(tx, grow, company, version=int(row["version"]))


async def mark_source(tx: Tx, order_ref: str, playbook_ref: str) -> None:
    rep = await OR.ensure(tx, order_ref)
    if rep is None:
        return
    await tx.exec(
        "UPDATE owner.order_reports SET source_playbook = :p, updated_at = now() WHERE id = :id",
        p=playbook_ref,
        id=rep["id"],
    )


# ------------------------------------------------------------------ retire --
async def retire(tx: Tx, ref: str) -> dict[str, Any]:
    """POST /playbooks/{ref}/retire (🔏 playbook.retire): the group off, so its routines stop for
    every member; ⟨1.37⟩ every member's flow automation off and the sealed versions `retired`;
    the playbook retired; nothing deleted."""
    row = await row_of(tx, ref, lock=True)
    if row["state"] == "retired":
        raise ApiError(409, "validation_failed", "retired already",
                       message_fa="این کارگروه پیش از این بازنشسته شده است.")  # fmt: skip
    if row.get("group_id") is not None:
        await tx.exec(
            "UPDATE growth.groups SET state = 'off', updated_at = now() WHERE id = :id",
            id=row["group_id"],
        )
    await tx.exec(
        """UPDATE owner.playbook_versions SET state = 'retired'
           WHERE playbook_id = :p AND state = 'sealed'""",
        p=row["id"],
    )
    flows = await tx.all(
        """UPDATE growth.automations a SET state = 'off', off_reason = 'owner', updated_at = now()
           FROM core.companies c
           WHERE c.id = a.company_id AND a.kind = 'flow' AND a.playbook = :p
             AND a.state IN ('on', 'paused')
           RETURNING a.ref, c.code""",
        p=ref,
    )
    for f in flows:
        await events.emit(tx, f["code"], "automation.changed", f["ref"], {"state": "off"})
    out = dict(
        await tx.one(
            """UPDATE owner.playbooks SET state = 'retired', retired_at = now(), updated_at = now()
               WHERE id = :id RETURNING *""",
            id=row["id"],
        )
    )
    await _emit(tx, ref, "retired", flows=len(flows))
    return out


# ------------------------------------------------------- ⟨1.37⟩ §59.1 a member's version --
async def set_member_version(tx: Tx, hub: Any, ref: str, code: str, version: int) -> PlaybookMember:
    """PUT /playbooks/{ref}/members/{code}/version: the company runs that sealed version from its
    flow's next run (its membership and its flow automation). A draft or a retired version is
    a 409."""
    row = await row_of(tx, ref, lock=True)
    company = await hub.companies.find(code)
    if company is None or row.get("group_id") is None:
        raise ApiError(
            404, "not_found", "not a member", message_fa="این شرکت عضو این کارگروه نیست."
        )
    m = await tx.first(
        "SELECT version FROM growth.memberships WHERE group_id = :g AND company_id = :co FOR UPDATE",
        g=row["group_id"],
        co=company.id,
    )
    if m is None:
        raise ApiError(
            404, "not_found", "not a member", message_fa="این شرکت عضو این کارگروه نیست."
        )
    v = PV.at_version(await PV.versions(tx, row["id"]), version)
    assert v is not None
    if v.state == "retired":
        raise ApiError(409, "validation_failed", "the version is retired",
                       message_fa="این نسخه کنار گذاشته شده است؛ نسخه‌ی دیگری را انتخاب کن.")  # fmt: skip
    if v.state != "sealed":
        raise ApiError(409, "validation_failed", "the version is a draft",
                       message_fa="این نسخه هنوز مُهر نشده است؛ اول مُهرش کن.")  # fmt: skip
    await tx.exec(
        """UPDATE growth.memberships SET version = :v, updated_at = now()
           WHERE group_id = :g AND company_id = :co""",
        v=version,
        g=row["group_id"],
        co=company.id,
    )
    flows = await tx.all(
        """UPDATE growth.automations SET playbook_version = :v, updated_at = now()
           WHERE kind = 'flow' AND playbook = :p AND company_id = :co RETURNING ref, state""",
        v=version,
        p=ref,
        co=company.id,
    )
    for f in flows:
        await events.emit(tx, company.code, "automation.changed", f["ref"],
                          {"state": f["state"], "version": version})  # fmt: skip
    await _emit(tx, ref, "member", company=company.code, version=version)
    member = next((x for x in await members_of(tx, row) if x.company == company.code), None)
    assert member is not None
    return member


# ---------------------------------------------------- ⟨1.37⟩ §59.1 copy, export, import --
def copy_text(pb: Playbook, platform: str | None, note_fa: str) -> str:
    """The first word of the session that adapts a copy (the holding's media lead, §59.1)."""
    where = f" برای {PLATFORM_FA.get(platform, platform)}" if platform else ""
    head = f"این کارگروه را{where} جور کن: {' '.join(note_fa.split())}"
    return (head + "\n\n" + markdown(pb))[:9_900]


async def body_at(
    tx: Tx, ref: str, version: int | None
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """(the row, the body, its number) at a version (without: the current body)."""
    row = await row_of(tx, ref)
    v = PV.at_version(await PV.versions(tx, row["id"]), version)
    if v is None:
        body = {"title_fa": row["title_fa"], "purpose_fa": row["purpose_fa"],
                "platform": row["platform"], **(_j(row["definition"]) or {})}  # fmt: skip
        return row, body, int(row["version"])
    return row, v.body, v.version


async def copy(
    tx: Tx,
    hub: Any,
    holding_id: UUID,
    ref: str,
    body: PlaybookCopyIn,
    *,
    order: str | None = None,
    conversation: str | None = None,
) -> dict[str, Any]:
    """POST /playbooks/{ref}/copy: a new playbook in draft (v1) from a version of this one, its
    steps and rules as they were, the platform (and the title) changed; `parent` this playbook
    at that version. With the session that adapts it (`order`), the copy is that session's."""
    _, src, number = await body_at(tx, ref, body.version)
    notes: list[str] = []
    raw = {**PV.shape_of(src)}
    if body.platform:
        raw["platform"] = body.platform
    if body.title_fa:
        raw["title_fa"] = body.title_fa
    d = normalise(raw, None, hub.charters, notes)
    head = f"کپی نسخه‌ی {number} کارگروه «{src.get('title_fa') or ref}»"
    note = "\n".join([head, *notes])[:2000]
    row = await _insert(
        tx, holding_id, d,
        {"order": order or "", "company": None, "conversation": conversation,
         "copy_of": ref, "parent_version": number},
        parent=ref, note=note, by_kind="owner", by_fa=PV.OWNER_FA, order=order,
    )  # fmt: skip
    await _emit(tx, str(row["ref"]), "draft", parent=ref)
    return row


async def import_file(tx: Tx, hub: Any, holding_id: UUID, doc: dict[str, Any]) -> dict[str, Any]:
    """POST /playbooks/import: a new playbook in draft (v1) from a `coinepro.playbook/1` file;
    `note_fa` says what was dropped (a role no charter has, a step kind the line engine does not
    run, a helper the hub does not have)."""
    notes: list[str] = []
    d = normalise(dict(doc["playbook"]), None, hub.charters, notes)
    try:
        number = int(doc.get("version") or 1)
    except (TypeError, ValueError):
        number = 1
    head = f"از فایل کارگروه (نسخه‌ی {number}) ساخته شد"
    note = "\n".join([head + ("؛ این‌ها کنار رفت:" if notes else "."), *notes])[:2000]
    row = await _insert(
        tx, holding_id, d,
        {"order": "", "company": None, "conversation": None,
         "imported": {"version": number, "exported_at": str(doc.get("exported_at") or "")[:40]}},
        parent=None, note=note, by_kind="owner", by_fa=PV.OWNER_FA,
    )  # fmt: skip
    await _emit(tx, str(row["ref"]), "draft", imported=True)
    return row


def title_line(row: dict[str, Any]) -> str:
    return HZ.humanize(f"{row['ref']} «{row['title_fa']}»") or str(row["ref"])
