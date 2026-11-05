"""A small CRM per company (contract §33.4 ⟨1.15⟩).

A lead holds a pseudonym and a display name, never a contact detail (those stay in
the company's own systems). Its stages are data per company: the default list is
`seed/sales/stages.yaml`, a kit may bring its own (`lead_stages`), and a company that
has none yet gets the default the first time it needs it.

Leads are made by code from:
  - the support desk (§19.3) and Telegram intake (§19.8): `from_inbound`, called once
    the first message of a new customer is stored (one lead per customer);
  - a payment (§33.2): `from_payment(tx, company, pseudonym, amount)`, for the money
    builder to call. A lead of the same pseudonym is set `paid` (the company's won
    stage); a payment with no lead makes one in that stage;
  - the owner's hand: `POST /companies/{code}/leads`.

Follow-up: `tick` (a worker schedule) makes a planner item (a work item with its due
time) for the assignee when `next_at` is reached, once per `next_at`. `draft` is one
mid-model call (task class `sales_followup`) in the company's voice; it returns the
text, checked by the outbound guard (§19.6), and never sends anything.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import statistics
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from hq_api import audit, events, workflows_client
from hq_api.db import Tx
from hq_api.domain import humanize
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Model, actor
from hq_common import outbound_guard as G
from hq_common.redact import scrub

log = logging.getLogger("hq_api.leads")


def mid_model() -> str:
    """The mid model of the one-sentence calls (the automations' choice), read lazily."""
    from hq_api.domain.automations import MODEL

    return MODEL

SEED = Path(__file__).resolve().parents[3] / "seed" / "sales" / "stages.yaml"
SERVICE = Principal(kind="service", code="sales", role="service")
SOURCES = ("support", "telegram", "site", "payment", "referral", "manual")
STAGE_KINDS = ("open", "won", "lost")
KEY = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
CONTACT = re.compile(r"^[A-Za-z0-9_:.-]{8,128}$")
MAX_STAGES = 12
TASK_CLASS = "sales_followup"
MAX_OUTPUT_TOKENS = 1200
Ask = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


# ------------------------------------------------------------------- shapes --
class LeadStage(BaseModel):
    key: str
    title_fa: str
    position: int
    kind: Literal["open", "won", "lost"]


class LeadEvent(BaseModel):
    at: datetime
    kind: str
    note_fa: str


class Lead(BaseModel):
    ref: str
    company: str
    source: Literal["support", "telegram", "site", "payment", "referral", "manual"]
    name_fa: str | None
    contact: str
    stage: str
    value_usdt: Decimal | None
    next_at: datetime | None
    next_fa: str | None
    assignee: Actor | None
    lost_reason_fa: str | None
    events: list[LeadEvent]
    created_at: datetime
    updated_at: datetime
    version: int


class LeadPipelineStage(BaseModel):
    stage: str
    title_fa: str
    kind: Literal["open", "won", "lost"]
    count: int
    value_usdt: Decimal
    median_days: float | None


class LeadPipeline(BaseModel):
    company: str
    total: int
    open_count: int
    open_value_usdt: Decimal
    won_count: int
    lost_count: int
    win_rate: float | None
    stages: list[LeadPipelineStage]


class LeadDraft(BaseModel):
    lead: str
    draft_fa: str
    guard_ok: bool
    blocked_reasons: list[str]
    sent: Literal[False] = False


# ------------------------------------------------------------------- stages --
def validate_stages(name: str, stages: Any) -> list[dict[str, str]]:
    """A stage list as a kit or the seed file gives it, or ValueError naming the fault."""
    if not isinstance(stages, list) or not 3 <= len(stages) <= MAX_STAGES:
        raise ValueError(f"{name}: lead_stages is a list of 3 to {MAX_STAGES} stages")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in stages:
        if not isinstance(s, dict) or set(s) - {"key", "title_fa", "kind"}:
            raise ValueError(f"{name}: a stage is {{key, title_fa, kind}}: {s!r}")
        key, title, kind = s.get("key"), s.get("title_fa"), s.get("kind", "open")
        if not isinstance(key, str) or not KEY.match(key) or key in seen:
            raise ValueError(f"{name}: stage key invalid or repeated: {key!r}")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
            raise ValueError(f"{name}: stage {key} needs title_fa (1 to 60 characters)")
        if kind not in STAGE_KINDS:
            raise ValueError(f"{name}: stage {key} kind is open, won or lost")
        seen.add(key)
        out.append({"key": key, "title_fa": title.strip(), "kind": kind})
    kinds = [s["kind"] for s in out]
    if kinds[0] != "open" or "won" not in kinds or "lost" not in kinds:
        raise ValueError(f"{name}: the first stage is open, and there is a won and a lost stage")
    return out


def default_stages() -> list[dict[str, str]]:
    data = yaml.safe_load(SEED.read_text(encoding="utf-8")) or {}
    return validate_stages("seed/sales/stages.yaml", data.get("stages"))


async def ensure_stages(
    tx: Tx, company_id: UUID, spec: list[dict[str, str]] | None = None
) -> list[dict[str, Any]]:
    """The company's stages; made from `spec` (a kit's), else the default list, when it
    has none. Existing stages are never changed here."""
    have = await tx.all(
        "SELECT key, title_fa, position, kind FROM sales.lead_stages WHERE company_id = :co ORDER BY position",
        co=company_id,
    )
    if have:
        return have
    for i, s in enumerate(spec or default_stages()):
        await tx.exec(
            """INSERT INTO sales.lead_stages (company_id, key, title_fa, position, kind)
               VALUES (:co, :k, :t, :p, :kind) ON CONFLICT DO NOTHING""",
            co=company_id,
            k=s["key"],
            t=s["title_fa"],
            p=i,
            kind=s["kind"],
        )
    return await ensure_stages(tx, company_id)


async def apply_kit(tx: Tx, company_id: UUID, kit: dict[str, Any]) -> int:
    """A company made from a kit starts with the kit's stages (when it names any)."""
    spec = kit.get("lead_stages")
    if not spec:
        return 0
    return len(await ensure_stages(tx, company_id, validate_stages(str(kit.get("key")), spec)))


def stage_of(stages: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    """The first stage of a kind (the first open one is where a lead starts)."""
    return next(s for s in stages if s["kind"] == kind)


# ------------------------------------------------------------------ storage --
LEAD_SQL = """SELECT l.*, c.code AS company FROM sales.leads l JOIN core.companies c ON c.id = l.company_id"""


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        LEAD_SQL + " WHERE l.ref = :r" + (" FOR UPDATE OF l" if lock else ""),
        r=ref,
    )


async def add_event(
    tx: Tx, lead: dict[str, Any], kind: str, note_fa: str = "", data: dict[str, Any] | None = None
) -> None:
    await tx.exec(
        """INSERT INTO sales.lead_events (company_id, lead_id, kind, note_fa, data)
           VALUES (:co, :l, :k, :n, CAST(:d AS jsonb))""",
        co=lead["company_id"],
        l=lead["id"],
        k=kind,
        n=note_fa[:500],
        d=json.dumps(data or {}, ensure_ascii=False, default=str),
    )


async def events_of(tx: Tx, lead_id: UUID, limit: int = 50) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT at, kind, note_fa FROM sales.lead_events WHERE lead_id = :l
           ORDER BY id DESC LIMIT :n""",
        l=lead_id,
        n=limit,
    )
    return list(reversed(rows))


def render(r: dict[str, Any], events_: list[dict[str, Any]]) -> Lead:
    return Lead(
        ref=r["ref"],
        company=r["company"],
        source=r["source"],
        name_fa=r["name_fa"],
        contact=r["contact"],
        stage=r["stage"],
        value_usdt=r["value_usdt"],
        next_at=r["next_at"],
        next_fa=r["next_fa"],
        assignee=actor(r["assignee_kind"], r["assignee_code"]),
        lost_reason_fa=r["lost_reason_fa"],
        events=[LeadEvent(at=e["at"], kind=e["kind"], note_fa=e["note_fa"]) for e in events_],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        version=r["version"],
    )


async def render_one(tx: Tx, ref: str) -> Lead:
    row = await load(tx, ref)
    return render(row, await events_of(tx, row["id"]))


async def _emit(tx: Tx, lead: dict[str, Any], what: str) -> None:
    await events.emit(
        tx,
        lead["company"],
        "lead.updated",
        lead["ref"],
        {"stage": lead["stage"], "change": what},
    )


async def company_row(tx: Tx, company: Any) -> dict[str, Any]:
    """The company as {id, code, name_fa}: `company` is a code, an id or an object with
    `id` and `code` (what the money builder has at hand)."""
    if isinstance(company, str) and re.match(r"^[A-Z][A-Z0-9]{1,9}$", company):
        row = await tx.first(
            "SELECT id, code, name_fa FROM core.companies WHERE code = :c AND kind <> 'holding'", c=company
        )
    elif isinstance(company, UUID):
        row = await tx.first(
            "SELECT id, code, name_fa FROM core.companies WHERE id = :i AND kind <> 'holding'", i=company
        )
    else:
        row = await tx.first(
            "SELECT id, code, name_fa FROM core.companies WHERE id = :i AND kind <> 'holding'",
            i=getattr(company, "id", None),
        )
    if row is None:
        raise ApiError(404, "not_found", "company not found", message_fa="این شرکت پیدا نشد.")
    return row


async def create(
    tx: Tx,
    who: Principal,
    company: dict[str, Any],
    *,
    source: str,
    contact: str | None = None,
    name_fa: str | None = None,
    value_usdt: Decimal | None = None,
    next_at: datetime | None = None,
    next_fa: str | None = None,
    assignee: tuple[str, str] | None = None,
    stage: str | None = None,
    note_fa: str = "",
) -> tuple[dict[str, Any], bool]:
    """(the lead, created). A lead of the same company and pseudonym is returned as it
    is (a customer who writes twice is one lead)."""
    if source not in SOURCES:
        raise ApiError(422, "validation_failed", fields={"source": "unknown"})
    contact = contact or f"m-{secrets.token_hex(8)}"
    if not CONTACT.match(contact):
        raise ApiError(
            422, "validation_failed", fields={"contact": "a pseudonym, never a phone or an address"}
        )
    stages = await ensure_stages(tx, company["id"])
    first = stage or stage_of(stages, "open")["key"]
    if first not in {s["key"] for s in stages}:
        raise ApiError(422, "validation_failed", fields={"stage": "unknown for this company"})
    name = " ".join(scrub(name_fa).split())[:200] if name_fa else None
    row = await tx.first(
        """INSERT INTO sales.leads (company_id, source, name_fa, contact, stage, value_usdt, next_at,
               next_fa, assignee_kind, assignee_code)
           VALUES (:co, :src, :name, :contact, :stage, :val, :next_at, :next_fa, :ak, :ac)
           ON CONFLICT (company_id, contact) DO NOTHING RETURNING id""",
        co=company["id"],
        src=source,
        name=name,
        contact=contact,
        stage=first,
        val=value_usdt,
        next_at=next_at,
        next_fa=(next_fa or None) and " ".join(scrub(next_fa).split())[:300],
        ak=assignee[0] if assignee else None,
        ac=assignee[1] if assignee else None,
    )
    if row is None:
        existing = await tx.one(
            LEAD_SQL + " WHERE l.company_id = :co AND l.contact = :c", co=company["id"], c=contact
        )
        return existing, False
    lead = await tx.one(LEAD_SQL + " WHERE l.id = :i", i=row["id"])
    await add_event(tx, lead, "created", note_fa or {"support": "از پشتیبانی آمد",
        "telegram": "از تلگرام آمد", "payment": "از یک پرداخت آمد", "site": "از سایت آمد",
        "referral": "از معرفی آمد", "manual": "دستی ثبت شد"}[source], {"source": source})
    await audit.record(
        tx,
        who,
        company_id=company["id"],
        action="lead.create",
        action_class="A1",
        target_kind="lead",
        target_ref=lead["ref"],
        summary=f"from {source}",
    )
    await _emit(tx, lead, "created")
    return lead, True


async def from_inbound(
    tx: Tx,
    company_id: UUID,
    *,
    channel: str,
    subject: str,
    display_name: str | None,
    mystery: bool = False,
) -> dict[str, Any] | None:
    """A customer's first message at the support desk or Telegram intake: one lead per
    customer (the mystery channel never makes one). The pseudonym is the customer's."""
    if mystery or channel == "mystery":
        return None
    company = await tx.first("SELECT id, code FROM core.companies WHERE id = :i AND kind <> 'holding'", i=company_id)
    if company is None:
        return None
    source = "telegram" if channel.startswith("telegram") else "support"
    async with tx.conn.begin_nested():
        lead, _ = await create(
            tx, SERVICE, company, source=source, contact=subject, name_fa=display_name
        )
    return lead


async def from_payment(
    tx: Tx, company: Any, pseudonym: str, amount: Decimal | float | int | str | None, *,
    paid: bool = True,
) -> dict[str, Any]:
    """For the payments (§33.2) to call; imports nothing of theirs. A lead of this
    pseudonym is set `paid` (the company's won stage, its value the amount); a payment
    that has no lead makes one. With `paid=False` (money no customer claimed yet) the new
    lead waits in the first stage with a note. Returns the lead row."""
    co = await company_row(tx, company)
    value = Decimal(str(amount)) if amount is not None else None
    if value is not None and value < 0:
        raise ApiError(422, "validation_failed", fields={"amount": "not negative"})
    stages = await ensure_stages(tx, co["id"])
    won = stage_of(stages, "won")
    lead, made = await create(
        tx,
        SERVICE,
        co,
        source="payment",
        contact=pseudonym,
        value_usdt=value,
        stage=won["key"] if paid else None,
        note_fa="" if paid else "پولی بدون مشتری رسید؛ مشتری‌اش پیدا شود",
    )
    lead = await tx.one(LEAD_SQL + " WHERE l.id = :i FOR UPDATE OF l", i=lead["id"])
    old_stage = lead["stage"]
    if paid and lead["paid_at"] is None:
        lead = await tx.one(
            """UPDATE sales.leads SET stage = :s, paid_at = now(), next_at = NULL, next_fa = NULL,
                   value_usdt = COALESCE(CAST(:v AS numeric), value_usdt)
               WHERE id = :i RETURNING id""",
            s=won["key"],
            v=value,
            i=lead["id"],
        )
        lead = await tx.one(LEAD_SQL + " WHERE l.id = :i", i=lead["id"])
        await add_event(
            tx,
            lead,
            "paid",
            "پرداخت رسید" + (f" ({value} تتر)" if value is not None else ""),
            {"amount": str(value) if value is not None else None, "created": made,
             "from": old_stage, "to": won["key"]},
        )
        await audit.record(
            tx, SERVICE, company_id=co["id"], action="lead.paid", action_class="A1",
            target_kind="lead", target_ref=lead["ref"], summary="a payment of the same pseudonym",
        )  # fmt: skip
        await _emit(tx, lead, "paid")
    elif not made and value is not None:
        await add_event(tx, lead, "payment", f"پرداخت دیگری رسید ({value} تتر)", {"amount": str(value)})
    return lead


# ------------------------------------------------------------------- change --
async def check_assignee(tx: Tx, company_id: UUID, a: dict[str, str] | None) -> tuple[str, str] | None:
    if a is None:
        return None
    kind, code = a.get("kind"), a.get("code")
    if kind == "owner" and code == "owner":
        return ("owner", "owner")
    if kind == "agent" and isinstance(code, str):
        ok = await tx.scalar(
            "SELECT 1 FROM core.employees WHERE code = :c AND company_id = :co AND status = 'active'",
            c=code,
            co=company_id,
        )
        if ok:
            return ("agent", code)
    raise ApiError(422, "validation_failed", fields={"assignee": "the owner or an active employee of this company"})


async def move(
    tx: Tx, lead: dict[str, Any], stage: str, *, lost_reason_fa: str | None = None
) -> dict[str, Any]:
    """Set the stage by hand. A `won` stage stamps paid_at only through a payment
    (`from_payment`); moving there by hand is the owner's word and stamps nothing."""
    stages = await ensure_stages(tx, lead["company_id"])
    target = next((s for s in stages if s["key"] == stage), None)
    if target is None:
        raise ApiError(
            422, "validation_failed", fields={"stage": "unknown for this company"},
            message_fa="این مرحله برای این شرکت تعریف نشده است.",
        )  # fmt: skip
    if target["key"] == lead["stage"]:
        return lead
    closes = target["kind"] != "open"
    row = await tx.one(
        """UPDATE sales.leads SET stage = :s,
               lost_reason_fa = CASE WHEN :k = 'lost' THEN CAST(:why AS text) ELSE NULL END,
               next_at = CASE WHEN :closes THEN NULL ELSE next_at END,
               next_fa = CASE WHEN :closes THEN NULL ELSE next_fa END
           WHERE id = :i RETURNING id""",
        s=stage,
        k=target["kind"],
        why=" ".join(scrub(lost_reason_fa).split())[:300] if lost_reason_fa else None,
        closes=closes,
        i=lead["id"],
    )
    moved = await tx.one(LEAD_SQL + " WHERE l.id = :i", i=row["id"])
    await add_event(
        tx, moved, "stage", f"به مرحله‌ی «{target['title_fa']}» رفت", {"from": lead["stage"], "to": stage}
    )
    await _emit(tx, moved, "stage")
    return moved


# ----------------------------------------------------------------- pipeline --
async def pipeline(tx: Tx, company: dict[str, Any], now: datetime | None = None) -> LeadPipeline:
    """Counts and value by stage, the win rate (won / (won + lost)), and the median days
    a lead stayed in each stage, all computed from the rows and their trail."""
    now = now or datetime.now(UTC)
    stages = await ensure_stages(tx, company["id"])
    rows = await tx.all(
        """SELECT stage, count(*) AS n, COALESCE(sum(value_usdt), 0) AS value
           FROM sales.leads WHERE company_id = :co GROUP BY stage""",
        co=company["id"],
    )
    by = {r["stage"]: r for r in rows}
    kinds = {s["key"]: s["kind"] for s in stages}
    trail = await tx.all(
        """SELECT e.lead_id, e.at, e.data FROM sales.lead_events e
           WHERE e.company_id = :co AND e.kind IN ('stage', 'paid') ORDER BY e.lead_id, e.id
           LIMIT 100000""",
        co=company["id"],
    )
    moves: dict[UUID, list[tuple[datetime, str | None, str | None]]] = {}
    for e in trail:
        d = e["data"] if isinstance(e["data"], dict) else json.loads(e["data"] or "{}")
        moves.setdefault(e["lead_id"], []).append((e["at"], d.get("from"), d.get("to")))
    spans: dict[str, list[float]] = {}

    def span(stage: str | None, a: datetime, b: datetime) -> None:
        if stage and kinds.get(stage) == "open":  # a closed stage has no duration to speak of
            spans.setdefault(stage, []).append(max(0.0, (b - a).total_seconds() / 86400))

    for r in await tx.all(
        "SELECT id, stage, created_at FROM sales.leads WHERE company_id = :co", co=company["id"]
    ):
        trail_of = moves.get(r["id"]) or []
        stage = trail_of[0][1] if trail_of else r["stage"]
        at = r["created_at"]
        for when, _, to in trail_of:
            span(stage, at, when)
            at, stage = when, to or stage
        span(stage, at, now)
    out: list[LeadPipelineStage] = []
    for s in stages:
        r = by.get(s["key"])
        days = spans.get(s["key"])
        out.append(
            LeadPipelineStage(
                stage=s["key"],
                title_fa=s["title_fa"],
                kind=s["kind"],
                count=int(r["n"]) if r else 0,
                value_usdt=Decimal(r["value"]) if r else Decimal(0),
                median_days=round(statistics.median(days), 1) if days else None,
            )
        )
    won = sum(s.count for s in out if s.kind == "won")
    lost = sum(s.count for s in out if s.kind == "lost")
    opens = [s for s in out if s.kind == "open"]
    return LeadPipeline(
        company=company["code"],
        total=sum(s.count for s in out),
        open_count=sum(s.count for s in opens),
        open_value_usdt=sum((s.value_usdt for s in opens), Decimal(0)),
        won_count=won,
        lost_count=lost,
        win_rate=round(won / (won + lost), 4) if won + lost else None,
        stages=out,
    )


# --------------------------------------------------------------- follow-up --
async def dept_head(tx: Tx, company_id: UUID, dept: str) -> str | None:
    code = await tx.scalar(
        """SELECT e.code FROM core.employees e JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND d.code = :d AND e.kind = 'manager' AND e.status = 'active'
           ORDER BY e.hired_at LIMIT 1""",
        co=company_id,
        d=dept,
    )
    return str(code) if code else None


async def ceo_of(tx: Tx, company_id: UUID) -> str | None:
    code = await tx.scalar(
        "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active' LIMIT 1",
        co=company_id,
    )
    return str(code) if code else None


async def planner_item(
    tx: Tx, company: dict[str, Any], dept: str, *, title: str, brief: str, due_at: datetime,
    assignee: tuple[str, str] | None = None,
) -> str | None:  # fmt: skip
    """A planner item (the planner is a view over work, §4): a work item due at
    `due_at` for the assignee, else the company's head of `dept`, else its CEO. Best
    effort: a refused item never stops the caller."""
    from hq_api.domain import work as W

    if assignee and assignee[0] == "owner":
        holding = await tx.one("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
        row = await tx.one(
            """INSERT INTO owner.planner_items (company_id, title_fa, at, note, created_by_kind,
                   created_by_code) VALUES (:co, :t, :at, :n, 'agent', 'sales') RETURNING ref""",
            co=holding["id"],
            t=title[:200],
            at=due_at,
            n=brief[:2000],
        )
        return str(row["ref"])
    code = (assignee[1] if assignee else None) or await dept_head(tx, company["id"], dept)
    code = code or await ceo_of(tx, company["id"])
    try:
        async with tx.conn.begin_nested():
            w = await W.create(
                tx, SERVICE, company_id=company["id"], company_code=company["code"],
                title=title[:300], brief=brief[:5000], kind="one_off", priority="P3",
                assignee_code=code, due_at=due_at,
            )  # fmt: skip
    except ApiError as exc:
        log.warning("planner item refused", extra={"code": exc.code, "company": company["code"]})
        return None
    return str(w["ref"])


async def tick(hub: Any, now: datetime | None = None) -> dict[str, int]:
    """The reminders due: a planner item for the assignee, once per `next_at`."""
    from hq_api.domain import gate

    now = now or datetime.now(UTC)
    made = 0
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await gate.holding_lock(tx) is not None:
            return {"reminders": 0, "locked": 1}
        rows = await tx.all(
            LEAD_SQL
            + """ JOIN sales.lead_stages s ON s.company_id = l.company_id AND s.key = l.stage
               WHERE l.next_at <= :now AND (l.reminded_for IS NULL OR l.reminded_for < l.next_at)
                 AND s.kind = 'open' ORDER BY l.next_at LIMIT 200 FOR UPDATE OF l SKIP LOCKED""",
            now=now,
        )
        for r in rows:
            company = await tx.one("SELECT id, code, name_fa FROM core.companies WHERE id = :i", i=r["company_id"])
            assignee = (r["assignee_kind"], r["assignee_code"]) if r["assignee_kind"] else None
            who = r["name_fa"] or r["ref"]
            ref = await planner_item(
                tx, company, "SALES",
                title=f"پیگیری سرنخ {who}",
                brief=(r["next_fa"] or "با این سرنخ تماس بگیرید.") + f"\n(سرنخ {r['ref']})",
                due_at=r["next_at"], assignee=assignee,
            )  # fmt: skip
            await tx.exec("UPDATE sales.leads SET reminded_for = next_at WHERE id = :i", i=r["id"])
            lead = await tx.one(LEAD_SQL + " WHERE l.id = :i", i=r["id"])
            await add_event(tx, lead, "reminder", "یادآوری پیگیری ساخته شد", {"item": ref})
            await _emit(tx, lead, "reminder")
            made += 1
    return {"reminders": made, "locked": 0}


FOLLOWUP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {"draft_fa": {"type": "string", "maxLength": 1500}},
                "required": ["draft_fa"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}
FOLLOWUP_SYSTEM = (
    "You draft ONE short follow-up message in Persian, in the voice of the company, for a person who "
    'showed interest. Answer exactly {"routes": [{"draft_fa": <the message>}]}. Warm, polite, plain, '
    "at most five sentences. Never promise profit or a result, never ask for a password, a key, a "
    "code or a card number, never write a link or a code that is not in the notes, never mention "
    "money you do not know. Use only the notes you are given; invent no fact. Put no preamble."
)


def followup_request(
    holding_code: str, company: dict[str, Any], lead: dict[str, Any], trail: list[dict[str, Any]],
    stage_title: str,
) -> dict[str, Any]:  # fmt: skip
    notes = [e["note_fa"] for e in trail if e["note_fa"]][-6:]
    return {
        "company_code": company["code"] or holding_code,
        "actor_ref": "sales",
        "task_class": TASK_CLASS,
        "priority": 3,
        "model": mid_model(),
        "effort": "low",
        "system": FOLLOWUP_SYSTEM,
        "prompt": json.dumps(
            {
                "company": company.get("name_fa") or company["code"],
                "person": lead["name_fa"],
                "stage": stage_title,
                "next_step": lead["next_fa"],
                "notes": [scrub(n) for n in notes],
            },
            ensure_ascii=False,
        ),
        "json_schema": FOLLOWUP_SCHEMA,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 60,
        "meta": {"purpose": "sales_followup", "lead": lead["ref"]},
    }


async def guard(tx: Tx, company_id: UUID, text: str) -> tuple[bool, list[str]]:
    from hq_api.domain import kb

    approved = await kb.guard_context(tx, company_id)
    v = G.check(text, approved)
    return v.ok, list(v.reasons)


def clean_draft(raw: Any) -> str | None:
    if not isinstance(raw, dict) or set(raw) - {"draft_fa"} or not isinstance(raw.get("draft_fa"), str):
        return None
    text = humanize.humanize(" ".join(raw["draft_fa"].split()))
    if len(text) < 5 or humanize.persian_share(text) < 0.4:
        return None
    return text[:1500]


async def draft(hub: Any, ref: str, ask: Ask | None = None) -> LeadDraft:
    """The follow-up text for a lead: one model call, the outbound guard over it. It is
    returned, not sent (sending goes through the guard and the approval rules of §19.6)."""
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lead = await load(tx, ref)
        company = await tx.one("SELECT id, code, name_fa FROM core.companies WHERE id = :i", i=lead["company_id"])
        stages = await ensure_stages(tx, lead["company_id"])
        title = next((s["title_fa"] for s in stages if s["key"] == lead["stage"]), lead["stage"])
        trail = await events_of(tx, lead["id"])
    req = followup_request(holding.code, company, lead, trail, title)
    call = ask or (lambda r: workflows_client.route_order(hub, r, 70.0))
    try:
        answer = await call(req)
    except Exception:  # noqa: BLE001 - a plain 422 below
        answer = None
    routes = (answer or {}).get("routes")
    text = clean_draft(routes[0] if isinstance(routes, list) and len(routes) == 1 else None)
    if text is None:
        raise ApiError(
            422, "validation_failed", "the model gave no usable draft",
            message_fa="پیش‌نویس ساخته نشد؛ کمی بعد دوباره امتحان کنید.",
            fields={"draft": "not made"},
        )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ok, reasons = await guard(tx, lead["company_id"], text)
        row = await load(tx, ref, lock=True)
        await add_event(tx, row, "draft", "پیش‌نویس پیگیری ساخته شد (فرستاده نشد)", {"guard_ok": ok})
        await audit.record(
            tx, SERVICE, company_id=row["company_id"], action="lead.draft", action_class="A0",
            target_kind="lead", target_ref=ref, summary="follow-up drafted, not sent",
        )  # fmt: skip
    return LeadDraft(lead=ref, draft_fa=text, guard_ok=ok, blocked_reasons=reasons)


# ---------------------------------------------------------------- in models --
class LeadIn(Model):
    source: Literal["site", "referral", "manual", "support", "telegram"] = "manual"
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    contact: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_:.-]{8,128}$")
    value_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    next_at: datetime | None = None
    next_fa: str | None = Field(default=None, max_length=300)
    assignee: Actor | None = None
    note_fa: str | None = Field(default=None, max_length=500)


class LeadPatch(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    stage: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,30}$")
    value_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    next_at: datetime | None = None
    next_fa: str | None = Field(default=None, max_length=300)
    assignee: Actor | None = None
    lost_reason_fa: str | None = Field(default=None, max_length=300)
    note_fa: str | None = Field(default=None, max_length=500)
