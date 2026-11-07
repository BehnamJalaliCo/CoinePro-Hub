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
from hq_api.domain import groups as GR
from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import recurrence
from hq_api.domain.connections import KINDS as CONNECTION_KINDS
from hq_api.errors import ApiError
from hq_api.schemas import Model
from hq_api.talk.scrub import clean

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
DEFAULT_TOKENS = 40_000
MAX_SEATS, MAX_ROUTINES, MAX_KPIS, MAX_RULES, MAX_CONNECTIONS = 12, 12, 12, 20, 10
LAST_TURNS = 30
TURN_CHARS = 1_200
NOT_FOUND_FA = "این کارگروه پیدا نشد."
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


class PlaybookPatch(Model):
    """PATCH /playbooks/{ref} (draft only): any field of the shape but ref, state, source."""

    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    purpose_fa: str | None = Field(default=None, max_length=2000)
    platform: Platform | None = None
    seats: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_SEATS)
    routines: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_ROUTINES)
    kpis: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_KPIS)
    connections: list[str] | None = Field(default=None, max_length=MAX_CONNECTIONS)
    rules_fa: list[str] | None = Field(default=None, max_length=MAX_RULES)


class PlaybookApplyIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    platform: Platform | None = None
    note_fa: str | None = Field(default=None, max_length=2000)
    as_is: bool = False


class PlaybookApplied(BaseModel):
    playbook: Playbook
    # as_is: the membership made; else the new session (its order and its talk)
    member: PlaybookMember | None = None
    order: str | None = None
    conversation: str | None = None


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
    }


def definition_json(d: dict[str, Any]) -> str:
    """The stored part of a normalised shape (the rest are the row's own columns)."""
    keys = ("seats", "routines", "kpis", "connections", "rules_fa")
    return json.dumps({k: d[k] for k in keys}, ensure_ascii=False)


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
        """SELECT c.code, c.name_fa, m.state
           FROM growth.memberships m JOIN core.companies c ON c.id = m.company_id
           WHERE m.group_id = :g ORDER BY m.joined_at""",
        g=row["group_id"],
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
            )
        )
    return out


async def render(tx: Tx, row: dict[str, Any]) -> Playbook:
    d = _j(row["definition"]) or {}
    src = _j(row["source"]) or {}
    group = None
    if row.get("group_id") is not None:
        group = await tx.scalar("SELECT key FROM growth.groups WHERE id = :g", g=row["group_id"])
    return Playbook(
        ref=row["ref"],
        title_fa=row["title_fa"],
        purpose_fa=row["purpose_fa"],
        state=row["state"],
        version=row["version"],
        platform=row["platform"],
        seats=[PlaybookSeat(**s) for s in d.get("seats") or []],
        routines=[PlaybookRoutine(**r) for r in d.get("routines") or []],
        kpis=[PlaybookKpi(**k) for k in d.get("kpis") or []],
        connections=list(d.get("connections") or []),
        rules_fa=list(d.get("rules_fa") or []),
        source=PlaybookSource(
            order=str(src.get("order") or ""),
            company=src.get("company"),
            conversation=src.get("conversation"),
        ),
        members=await members_of(tx, row),
        parent=row.get("parent"),
        created_at=row["created_at"],
        sealed_at=row.get("sealed_at"),
        retired_at=row.get("retired_at"),
        group=group,
        note_fa=row.get("note_fa"),
    )


async def listing(tx: Tx, state: str | None) -> list[Playbook]:
    rows = await tx.all(
        """SELECT * FROM owner.playbooks WHERE (CAST(:st AS text) IS NULL OR state = :st)
           ORDER BY created_at DESC LIMIT 200""",
        st=state,
    )
    return [await render(tx, dict(r)) for r in rows]


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
    "routines."
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
    automations = [
        {"ref": r["ref"], "sentence_fa": r["sentence_fa"], "rule": _j(r["rule"])}
        for r in await tx.all(
            "SELECT ref, sentence_fa, rule FROM growth.automations WHERE ref = ANY(:refs)",
            refs=made.get("automation") or [],
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
    }
    return {
        "company_code": holding,
        "actor_ref": f"playbook:{m.order}",
        "task_class": TASK_CLASS,
        "priority": 2,
        "effort": "medium",
        "system": SYSTEM,
        "prompt": json.dumps(prompt, ensure_ascii=False),
        "json_schema": SCHEMA,
        "max_output_tokens": 8_000,
        "timeout_s": 90,
        "meta": {"purpose": "playbook_draft", "order": m.order},
    }


NO_MODEL_FA = "مدل پیش‌نویس نداد؛ این پیش‌نویس را کد از روی آدم‌ها و خودکارسازی‌های جلسه ساخت."


async def draft(ctx: Any, order_ref: str) -> tuple[dict[str, Any], Material, list[str]]:
    """The holder's one call over the session's material, outside any transaction; what comes
    back normalised by code (or the code's skeleton when the model gives nothing). Answers
    (the definition, the material, the notes)."""
    from hq_api import workflows_client

    async with ctx.tx() as tx:
        m = await material(tx, ctx.hub, order_ref)
        roles = await AU.company_roles(tx, ctx.hub, m.company) if m.company else None
    holding = await ctx.hub.companies.holding()
    out = await workflows_client.model_call(ctx.hub, body_of(m, holding.code), timeout_s=120)
    notes: list[str] = []
    raw = out if isinstance(out, dict) and out.get("seats") is not None else None
    if raw is None:
        notes.append(NO_MODEL_FA)
        raw = m.skeleton
    return normalise(raw, roles, ctx.hub.charters, notes), m, notes


async def store_draft(
    tx: Tx, holding_id: UUID, m: Material, d: dict[str, Any], notes: list[str]
) -> dict[str, Any]:
    """The draft stored (its `parent` the playbook the session was opened from, if any), one step
    and one `playbook` card in the session."""
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE
    from hq_api.talk import store

    rep = await OR.ensure(tx, m.order)
    assert rep is not None
    row = dict(
        await tx.one(
            """INSERT INTO owner.playbooks (company_id, title_fa, purpose_fa, platform, definition, source,
                   parent, note_fa)
               VALUES (:co, :t, :p, :pl, CAST(:d AS jsonb), CAST(:s AS jsonb), :parent, :note)
               RETURNING *""",
            co=holding_id,
            t=d["title_fa"],
            p=d["purpose_fa"],
            pl=d["platform"],
            d=definition_json(d),
            s=json.dumps(
                {"order": m.order, "company": m.company, "conversation": m.conversation},
                ensure_ascii=False,
            ),
            parent=rep.get("source_playbook"),
            note="\n".join(notes)[:2000] or None,
        )
    )
    ref = str(row["ref"])
    line = f"کارگروه از این جلسه پیش‌نویس شد: {ref} «{d['title_fa']}»"
    if rep.get("closed_at") is None:
        await SE.step(tx, m.order, SE.OWNER_FA, line, remember_line=line)
    else:
        await OR._append_steps(tx, rep["id"], [OR._step(SE.OWNER_FA, line)])
    if m.conversation:
        conv = await store.conversation(tx, m.conversation, lock=True)
        key = OT.holder_key(conv)
        say = f"کارگروه از این جلسه آماده است: {ref}. باز کنید، ویرایش کنید و مُهر بزنید."
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
    await _emit(tx, ref, "draft")
    return row


async def _emit(tx: Tx, ref: str, state: str, **more: Any) -> None:
    holding = await OR._holding(tx)
    await events.emit(tx, holding["code"], "group.playbook", ref, {"state": state, **more})


# ------------------------------------------------------------------- edits --
async def patch(
    tx: Tx, hub: Any, ref: str, body: dict[str, Any], *, notes: list[str] | None = None
) -> dict[str, Any]:
    """PATCH /playbooks/{ref} and the holder's rewrite: the given fields over the draft, the
    whole normalised again (a dropped item leaves a note); the version counts up."""
    row = await row_of(tx, ref, lock=True)
    if row["state"] != "draft":
        raise ApiError(409, "validation_failed", "the playbook is not a draft",
                       message_fa="این کارگروه مُهر شده است؛ پیش‌نویسش دیگر عوض نمیشود.")  # fmt: skip
    cur = {
        "title_fa": row["title_fa"],
        "purpose_fa": row["purpose_fa"],
        "platform": row["platform"],
        **(_j(row["definition"]) or {}),
    }
    given = {k: v for k, v in body.items() if v is not None}
    if not given:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"},
                       message_fa="چیزی برای تغییر داده نشد.")  # fmt: skip
    src = _j(row["source"]) or {}
    company = src.get("company")
    roles = await AU.company_roles(tx, hub, str(company)) if company else None
    notes = [] if notes is None else notes
    d = normalise({**cur, **given}, roles, hub.charters, notes)
    out = await tx.one(
        """UPDATE owner.playbooks SET title_fa = :t, purpose_fa = :p, platform = :pl,
               definition = CAST(:d AS jsonb), version = version + 1, note_fa = :note, updated_at = now()
           WHERE id = :id RETURNING *""",
        t=d["title_fa"],
        p=d["purpose_fa"],
        pl=d["platform"],
        d=definition_json(d),
        note="\n".join(notes)[:2000] or None,
        id=row["id"],
    )
    await _emit(tx, ref, "draft", version=int(out["version"]))
    return dict(out)


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
    tx: Tx, grow: dict[str, Any], company: Any, *, hires: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A company joins the playbook's group: the membership (on), its seats first to the session's
    hires (`hires`: {role, code}), then resolved and filled by automatic hiring (§29.10)."""
    await tx.exec(
        """INSERT INTO growth.memberships (company_id, group_id) VALUES (:co, :g)
           ON CONFLICT (group_id, company_id) DO NOTHING""",
        co=company.id,
        g=grow["id"],
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
    """POST /playbooks/{ref}/seal (the route consumed 🔏 playbook.seal): the group in the database,
    the session's company its first member with the seats of the session's hires, the routines
    from their next time (the groups' tick). Answers the playbook's row."""
    from hq_api.domain import sessions as SE

    row = await row_of(tx, ref, lock=True)
    if row["state"] != "draft":
        raise ApiError(409, "validation_failed", f"the playbook is {row['state']}",
                       message_fa="این کارگروه پیش از این مُهر شده است.")  # fmt: skip
    holding = await hub.companies.holding()
    grow = await _group_row(tx, holding.id, row)
    src = _j(row["source"]) or {}
    member = None
    company = (
        await hub.companies.find(str(src.get("company") or "")) if src.get("company") else None
    )
    if company is not None and company.kind != "holding":
        conv = None
        if src.get("conversation"):
            conv = await tx.first(
                "SELECT * FROM talk.conversations WHERE ref = :r", r=src["conversation"]
            )
            conv = dict(conv) if conv is not None else None
        hires = await _hires(tx, conv, company.code)
        member = await join(tx, grow, company, hires=hires)
    out = dict(
        await tx.one(
            """UPDATE owner.playbooks SET state = 'sealed', sealed_at = now(), group_id = :g,
                   updated_at = now() WHERE id = :id RETURNING *""",
            g=grow["id"],
            id=row["id"],
        )
    )
    rep = await OR.ensure(tx, str(src.get("order") or ""))
    if rep is not None:
        line = f"کارگروه {ref} مُهر شد و راه افتاد"
        if member is not None:
            filled = sum(1 for s in member.get("seats") or [] if s.get("employee"))
            line += f"؛ {filled} جایگاه از {len(member.get('seats') or [])} پر است"
        if rep.get("closed_at") is None:
            await SE.step(tx, str(rep["ref"]), SE.OWNER_FA, line, remember_line=line)
        else:
            await OR._append_steps(tx, rep["id"], [OR._step(SE.OWNER_FA, line)])
    await _emit(tx, ref, "sealed", group=grow["key"])
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
                       message_fa="عضویت مستقیم فقط برای کارگروه مُهرشده است؛ این یکی را اول مُهر بزنید.")  # fmt: skip
    grow = dict(await tx.one("SELECT * FROM growth.groups WHERE id = :g", g=row["group_id"]))
    if grow["state"] != "on":
        await tx.exec("UPDATE growth.groups SET state = 'on', updated_at = now() WHERE id = :id",
                      id=grow["id"])  # fmt: skip
        grow["state"] = "on"
    return await join(tx, grow, company)


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
    every member; the playbook retired; nothing deleted."""
    row = await row_of(tx, ref, lock=True)
    if row["state"] == "retired":
        raise ApiError(409, "validation_failed", "retired already",
                       message_fa="این کارگروه پیش از این بازنشسته شده است.")  # fmt: skip
    if row.get("group_id") is not None:
        await tx.exec(
            "UPDATE growth.groups SET state = 'off', updated_at = now() WHERE id = :id",
            id=row["group_id"],
        )
    out = dict(
        await tx.one(
            """UPDATE owner.playbooks SET state = 'retired', retired_at = now(), updated_at = now()
               WHERE id = :id RETURNING *""",
            id=row["id"],
        )
    )
    await _emit(tx, ref, "retired")
    return out


def title_line(row: dict[str, Any]) -> str:
    return HZ.humanize(f"{row['ref']} «{row['title_fa']}»") or str(row["ref"])
