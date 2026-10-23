"""The premium advisor (prompt 12 §1, contract §21.1): decision memos, the
devil's advocate and proactive notes. Rules first, AI last: what wakes the
advisor, when, how often and with which facts is code; the advisor only
writes the prose.

Decision memo (advisor.memos, DM-0001)
  - On the owner's request: POST /decisions/{ref}/memo {mode} -> 202, the
    same (card, mode, card version) again is the same memo.
  - Automatic: a card for the owner with risk `high` or kind deploy,
    company_found or server_plan gets one (owner_settings.advisor.auto_memo,
    default on, at most 3 a day in the owner's time zone). The cap is not
    carried over: the 4th card of the day gets only the request button.
  - The memo is bound to the card's version: a changed card makes it `stale`
    (database trigger advisor.stale_on_change); an automatic memo is written
    again for the new version only while the automatic condition holds.
  - The advisor writes it with `memo.write` (A1, pending cards only) in a run
    of task class advisor_memo capped at 80K tokens; `against_md` is never
    empty and every citation is checked server-side (an invented one is
    dropped and counted).
  - Beside it, by code: the substitute players' second (GPT) and third
    (DeepSeek) opinions on the same masked facts pack, never shown the memo;
    `agrees` is code. A player that is off, signed out or over its seat's
    daily cap leaves the opinion null.
Devil's advocate: an owner message in thread A with `mode: "devil"`; the
runner adds the instruction to that run only and the reply carries
`meta.mode: "devil"`. A `devil` memo argues why not.
Proactive notes (advisor.triggers): rules with no model fire a trigger whose
key is unique per day; the advisor is woken once per key with the facts
gathered beforehand (task class advisor_proactive, 50K tokens) and writes one
short message in A (`meta.proactive: {kind, key}`) with a `report`-level
notification, never `urgent`. At most owner_settings.advisor.proactive_per_day
(default 3) a day; the rest are `capped`.

The launch gate (docs/OWNER_REQUESTS_2026-10-17.md round 8 #8): nothing here
wakes a model while the holding's kill switch is engaged. Automatic memos are
not made, triggers are recorded `deferred` (the rules themselves read the
database only), and the owner's own request answers 423.
The owner zone's share (prompt 12 §15): once the zone's automatic runs have
used OWNER_ZONE_DAILY_SHARE of the daily cap, automatic memos wait and
triggers are `deferred`; the owner's own requests always run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate, notify
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model
from hq_common import owner_zone
from hq_common.redact import redact, scrub

log = logging.getLogger("hq_api.domain.advisor")

AUTO_KINDS = ("deploy", "company_found", "server_plan")
MEMO_TOKENS = 80_000
PROACTIVE_TOKENS = 50_000
SERVICE = Principal(kind="service", code="advisor-rules", role="service")
Mode = Literal["standard", "devil"]
Rec = Literal["approve", "reject", "return", "ask"]
Level3 = Literal["low", "medium", "high"]
TRIGGER_KINDS = (
    "budget",
    "quota",
    "compliance",
    "incident",
    "revenue",
    "waiting_decisions",
    "finding",
    "okr",
)
DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_memo": {"enabled": True, "max_per_day": 3},
    "proactive_per_day": 3,
}
# What the runner adds to the system prompt of a devil's-advocate run only.
DEVIL_INSTRUCTION = (
    "# Devil's advocate (this run only)\n"
    "The owner asked for the devil's advocate. Argue the strongest honest case AGAINST what is "
    "proposed or assumed. The citation rules do not relax: every weakness you name needs evidence "
    "from the record and a citation; no invented weakness and no rhetoric without evidence."
)
# A memo older than this whose run ended without memo.write is `failed`.
FAILED_AFTER = timedelta(minutes=5)


# ------------------------------------------------------------------ shapes --
class MemoIn(Model):
    mode: Mode = "standard"


class Option(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    pros_md: str = Field(default="", max_length=4000)
    cons_md: str = Field(default="", max_length=4000)


class Risk(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    likelihood: Level3
    impact: Level3
    mitigation_fa: str = Field(default="", max_length=2000)


class MemoCitation(Model):
    kind: Literal["decision", "resolution", "deliverable", "work", "message", "audit"]
    ref: str = Field(min_length=1, max_length=40)


class MemoWrite(Model):
    """memo.write (A1, the advisor only; agents/tools.md)."""

    decision: str = Field(pattern=r"^D-[0-9]{4,9}$")
    decision_version: int = Field(ge=1)
    mode: Mode = "standard"
    summary_fa: str = Field(min_length=1, max_length=4000)
    recommendation: Rec
    confidence: float = Field(ge=0, le=1)
    options: list[Option] = Field(default_factory=list, max_length=8)
    against_md: str = Field(max_length=20000)
    risks: list[Risk] = Field(default_factory=list, max_length=20)
    questions: list[str] = Field(default_factory=list, max_length=20)
    citations: list[MemoCitation] = Field(default_factory=list, max_length=50)

    @field_validator("questions")
    @classmethod
    def _questions(cls, v: list[str]) -> list[str]:
        return [q.strip()[:500] for q in v if q.strip()]


class Opinion(BaseModel):
    player: str
    model: str
    recommendation: Rec
    confidence: float
    summary_fa: str
    differences: list[str]
    agrees: bool


class Usage(BaseModel):
    tokens: int
    usd: str


class DecisionMemo(BaseModel):
    id: UUID
    ref: str
    decision: str
    decision_version: int
    mode: Mode
    state: Literal["writing", "ready", "failed", "stale"]
    trigger: Literal["owner", "auto"]
    summary_fa: str
    recommendation: Rec | None
    confidence: float | None
    options: list[dict[str, Any]]
    against_md: str
    risks: list[dict[str, Any]]
    questions: list[str]
    citations: list[dict[str, Any]]
    citations_dropped: int
    usage: Usage
    second_opinion: Opinion | None
    third_opinion: Opinion | None = None
    state_reason: str | None = None
    created_at: datetime


class MemoBrief(BaseModel):
    """What a Decision card shows of its memos (contract §21.1)."""

    ref: str
    mode: Mode
    state: str


class AdvisorTrigger(BaseModel):
    id: UUID
    key: str
    kind: str
    company: str | None
    fired_at: datetime
    facts: dict[str, Any]
    message_ref: str | None
    state: Literal["sent", "deferred", "capped"]


MEMO_SQL = """
    SELECT m.* FROM advisor.memos m
"""


def _opinion(v: Any) -> Opinion | None:
    if not isinstance(v, dict):
        return None
    try:
        return Opinion.model_validate(v)
    except ValueError:
        return None


def render(r: dict[str, Any]) -> DecisionMemo:
    return DecisionMemo(
        id=r["id"],
        ref=r["ref"],
        decision=r["decision_ref"],
        decision_version=r["decision_version"],
        mode=r["mode"],
        state=r["state"],
        trigger=r["trigger"],
        summary_fa=r["summary_fa"] or "",
        recommendation=r["recommendation"],
        confidence=float(r["confidence"]) if r["confidence"] is not None else None,
        options=list(r["options"] or []),
        against_md=r["against_md"] or "",
        risks=list(r["risks"] or []),
        questions=[str(q) for q in r["questions"] or []],
        citations=list(r["citations"] or []),
        citations_dropped=r["citations_dropped"],
        usage=Usage(tokens=int(r["usage_tokens"]), usd=str(r["usage_usd"])),
        second_opinion=_opinion(r["second_opinion"]),
        third_opinion=_opinion(r["third_opinion"]),
        state_reason=r["state_reason"],
        created_at=r["created_at"],
    )


def render_trigger(r: dict[str, Any]) -> AdvisorTrigger:
    return AdvisorTrigger(
        id=r["id"],
        key=r["key"],
        kind=r["kind"],
        company=r.get("company"),
        fired_at=r["fired_at"],
        facts=dict(r["facts"] or {}),
        message_ref=r["message_ref"],
        state=r["state"],
    )


# --------------------------------------------------------------- settings --
async def settings(tx: Tx) -> tuple[dict[str, Any], str]:
    """(owner_settings.advisor with its defaults, the owner's time zone)."""
    row = await tx.one("SELECT advisor, timezone FROM owner.settings WHERE id = 1")
    s = {**DEFAULT_SETTINGS, **(row["advisor"] or {})}
    s["auto_memo"] = {**DEFAULT_SETTINGS["auto_memo"], **(s.get("auto_memo") or {})}
    return s, str(row["timezone"] or "Asia/Tehran")


def owner_day(tz: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


async def zone_tokens_today(tx: Tx) -> int:
    """The owner zone's tokens of this UTC day (the router's ledger)."""
    n = await tx.scalar(
        """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                               + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
           FROM llm.calls
           WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
             AND task_class = ANY(:tc)""",
        tc=list(owner_zone.TASK_CLASSES),
    )
    return int(n or 0)


async def zone_spent(tx: Tx, hub: Any) -> bool:
    s = hub.settings
    return owner_zone.spent(
        await zone_tokens_today(tx), s.agent_daily_token_cap, s.owner_zone_daily_share
    )


# ------------------------------------------------------------ facts pack --
def _iso(v: Any) -> str | None:
    return v.isoformat() if isinstance(v, datetime) else None


def facts_pack(d: dict[str, Any]) -> dict[str, Any]:
    """The masked facts the advisor and the substitutes' opinions all read:
    the card as it is now (secrets and personal data masked; texts cut)."""
    return {
        "card": {
            "ref": d["ref"],
            "company": d["company"],
            "kind": d["kind"],
            "title": scrub(str(d["title"]))[:300],
            "what": scrub(str(d["what"] or ""))[:4000],
            "why": scrub(str(d["why"] or ""))[:4000],
            "risk": d["risk"],
            "risk_note": scrub(str(d["risk_note"]))[:2000] if d.get("risk_note") else None,
            "reversible": d["reversible"],
            "quota_estimate": {
                "tokens": d["quota_tokens"],
                "usd": str(d["quota_usd"]) if d["quota_usd"] is not None else None,
            },
            "payload": redact(d["payload"] or {}, max_string=2000, max_list=50),
            "proposer": f"{d['proposer_kind']}:{d['proposer_code']}",
            "created_at": _iso(d["created_at"]),
            "expires_at": _iso(d.get("expires_at")),
            "version": d["version"],
        }
    }


def _sha(value: Any) -> str:
    canon = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canon.encode()).hexdigest()


OPINION_PROMPT = (
    "You give an independent opinion on one decision card of a holding company, for its owner. "
    "You see only the masked facts below; nobody else's opinion. Answer with ONE JSON object and "
    'nothing else: {"recommendation": "approve"|"reject"|"return"|"ask", "confidence": 0..1, '
    '"summary_fa": "<at most 600 characters, Persian>", "key_points": ["<short reason>", ...]}.\n\n'
    "Facts (JSON):\n"
)


def opinion_input(facts: dict[str, Any]) -> str:
    return OPINION_PROMPT + json.dumps(facts, ensure_ascii=False, sort_keys=True)


def parse_opinion(text: str, player: str, model: str) -> dict[str, Any] | None:
    """The substitute's JSON answer, checked; None when it is not one."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("recommendation") not in (
        "approve",
        "reject",
        "return",
        "ask",
    ):
        return None
    try:
        conf = min(max(float(raw.get("confidence", 0)), 0.0), 1.0)
    except (TypeError, ValueError):
        conf = 0.0
    raw_points = raw.get("key_points")
    points: list[Any] = raw_points if isinstance(raw_points, list) else []
    return {
        "player": player,
        "model": model,
        "recommendation": raw["recommendation"],
        "confidence": round(conf, 3),
        "summary_fa": scrub(str(raw.get("summary_fa") or ""))[:600],
        "key_points": [scrub(str(p))[:300] for p in points[:8]],
        "differences": [],
        "agrees": False,
    }


def with_agreement(opinion: dict[str, Any] | None, rec: str | None) -> dict[str, Any] | None:
    """`agrees` is code: the same recommendation as the memo. A disagreeing
    opinion lists its own key points as the differences to weigh."""
    if opinion is None:
        return None
    out = dict(opinion)
    agrees = rec is not None and out.get("recommendation") == rec
    out["agrees"] = agrees
    out["differences"] = [] if agrees or rec is None else list(out.get("key_points") or [])[:8]
    return out


# ------------------------------------------------------------------ memos --
async def _advisor_code(tx: Tx) -> str | None:
    code: str | None = await tx.scalar(
        """SELECT e.code FROM msg.threads t JOIN core.employees e ON e.id = t.employee_id
           WHERE t.code = 'A' AND e.status = 'active'"""
    )
    return code


async def memos_of(tx: Tx, decision_ids: list[UUID]) -> dict[UUID, list[MemoBrief]]:
    if not decision_ids:
        return {}
    rows = await tx.all(
        """SELECT decision_id, ref, mode, state FROM advisor.memos
           WHERE decision_id = ANY(:ids) ORDER BY created_at""",
        ids=decision_ids,
    )
    out: dict[UUID, list[MemoBrief]] = {}
    for r in rows:
        out.setdefault(r["decision_id"], []).append(
            MemoBrief(ref=r["ref"], mode=r["mode"], state=r["state"])
        )
    return out


async def find(tx: Tx, decision_id: UUID, mode: str, version: int) -> dict[str, Any] | None:
    return await tx.first(
        MEMO_SQL + " WHERE m.decision_id = :d AND m.mode = :m AND m.decision_version = :v",
        d=decision_id,
        m=mode,
        v=version,
    )


async def request(
    tx: Tx,
    hub: Any,
    who: Principal,
    d: dict[str, Any],
    mode: str,
    trigger: Literal["owner", "auto"],
) -> tuple[dict[str, Any], bool]:
    """(memo, created). The same card, mode and version is the same memo."""
    if d["status"] != "pending":
        raise ApiError(409, "decision_not_pending", f"{d['ref']} is {d['status']}")
    existing = await find(tx, d["id"], mode, d["version"])
    if existing is not None:
        return existing, False
    lock = await gate.automation_lock(tx)
    if lock is not None:
        raise ApiError(
            423,
            "company_locked",
            "the holding's kill switch is engaged: no model runs until the owner launches the hub",
        )
    advisor = await _advisor_code(tx)
    if advisor is None:
        raise ApiError(409, "not_ready", "the advisor is not seated")
    holding = await hub.companies.holding()
    facts = facts_pack(d)
    memo = await tx.one(
        """INSERT INTO advisor.memos (company_id, decision_id, decision_ref, decision_version, mode,
               trigger, facts, facts_sha256, created_by_kind, created_by_code)
           VALUES (:co, :d, :ref, :v, :mode, :trig, CAST(:facts AS jsonb), :sha, :ck, :cc)
           RETURNING *""",
        co=holding.id,
        d=d["id"],
        ref=d["ref"],
        v=d["version"],
        mode=mode,
        trig=trigger,
        facts=json.dumps(facts, ensure_ascii=False, default=str),
        sha=_sha(facts),
        ck=who.kind,
        cc=who.code,
    )
    devil = mode == "devil"
    brief = (
        f"Write the decision memo {memo['ref']} for card {d['ref']} (version {d['version']}, "
        f"mode {mode}) with memo.write, then finish (done).\n"
        "- The answer first: `recommendation` (approve | reject | return | ask) and `confidence`.\n"
        "- `options` with their pros and cons; `against_md` ALWAYS filled with the strongest case "
        "against your own recommendation; `risks` with likelihood, impact and mitigation; "
        "`questions` the owner should ask the proposer; a citation for every fact from the record.\n"
        + (
            "- Mode devil: argue why NOT: the recommendation is the strongest honest case against "
            "the card.\n"
            if devil
            else ""
        )
        + f"- Pass decision={d['ref']}, decision_version={d['version']}, mode={mode}.\n"
        "- A second opinion from a substitute player is written beside your memo by code; you "
        "never see or edit it.\n\n"
        "Facts pack (masked JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)[:6000]
    )
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding.id,
        company_code=holding.code,
        title=f"یادداشت تصمیم {memo['ref']} برای {d['ref']}"[:300],
        brief=brief,
        kind="one_off",
        priority="P2",
        assignee_code=advisor,
        budget=W.BudgetIn(tokens=MEMO_TOKENS),
    )
    await tx.exec(
        "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
        id=w["id"],
        m=json.dumps(
            {
                "task_class": "advisor_memo",
                "owner_zone": owner_zone.DIRECT if trigger == "owner" else owner_zone.AUTO,
                "memo": memo["ref"],
                "mode": mode,
            }
        ),
    )
    memo = await tx.one(
        "UPDATE advisor.memos SET work_id = :w, updated_at = now() WHERE id = :id RETURNING *",
        w=w["id"],
        id=memo["id"],
    )
    await audit.record(
        tx,
        who,
        company_id=holding.id,
        action="memo.request",
        action_class="A1",
        target_kind="memo",
        target_ref=memo["ref"],
        summary=f"{d['ref']} v{d['version']} {mode} ({trigger})",
    )
    await events.emit(
        tx,
        holding.code,
        "memo.requested",
        memo["ref"],
        {"decision": d["ref"], "mode": mode, "trigger": trigger},
    )
    # The substitutes' independent opinions on the same facts (never the memo).
    from hq_api.domain import substitutes as S

    for seat in ("advisor_second_opinion", "third_opinion"):
        await S.seat_call(
            tx,
            hub,
            SERVICE,
            seat=seat,
            input_md=opinion_input(facts),
            company_id=holding.id,
            purpose=("memo", memo["ref"]),
        )
    return memo, True


async def apply_opinion(tx: Tx, memo_ref: str, seat: str, call: dict[str, Any]) -> None:
    """A substitute's finished seat call on a memo: its opinion, with
    `agrees` against the memo when the memo is written already."""
    memo = await tx.first(MEMO_SQL + " WHERE m.ref = :r FOR UPDATE", r=memo_ref)
    if memo is None:
        return
    result = call.get("result") or {}
    opinion = None
    if call["state"] == "done":
        opinion = parse_opinion(
            str(result.get("text_md") or ""), str(call["player"]), str(call["model"] or "")
        )
    if opinion is None:
        return
    rec = memo["recommendation"] if memo["state"] == "ready" else None
    column = "second_opinion" if seat == "advisor_second_opinion" else "third_opinion"
    await tx.exec(
        f"UPDATE advisor.memos SET {column} = CAST(:o AS jsonb), updated_at = now() WHERE id = :id",  # noqa: S608 - one of two columns
        o=json.dumps(with_agreement(opinion, rec), ensure_ascii=False),
        id=memo["id"],
    )


async def write(tx: Tx, read: Any, who: Principal, body: MemoWrite, hub: Any) -> dict[str, Any]:
    """memo.write: the advisor's memo on a pending card. `read` is the
    advisor's read-scope transaction (for the citations)."""
    from hq_api.domain import decisions as D
    from hq_api.routes.messages import Citation, validate_citations

    if not body.against_md.strip():
        raise ApiError(
            422,
            "validation_failed",
            fields={"against_md": "the strongest case against: never empty"},
        )
    d = await D.load(tx, body.decision, lock=True)
    if d["status"] != "pending":
        raise ApiError(409, "decision_not_pending", f"{d['ref']} is {d['status']}")
    if body.decision_version != d["version"]:
        raise ApiError(
            409, "version_conflict", f"{d['ref']} is at version {d['version']}: the memo is stale"
        )
    memo = await find(tx, d["id"], body.mode, d["version"])
    if memo is not None and memo["state"] in ("ready", "stale"):
        raise ApiError(409, "version_conflict", f"{memo['ref']} is {memo['state']} already")
    holding = await hub.companies.holding()
    if memo is None:  # the owner asked in the thread: the advisor writes it on its own
        facts = facts_pack(d)
        memo = await tx.one(
            """INSERT INTO advisor.memos (company_id, decision_id, decision_ref, decision_version, mode,
                   trigger, facts, facts_sha256, created_by_kind, created_by_code)
               VALUES (:co, :d, :ref, :v, :mode, 'owner', CAST(:facts AS jsonb), :sha, :ck, :cc)
               RETURNING *""",
            co=holding.id,
            d=d["id"],
            ref=d["ref"],
            v=d["version"],
            mode=body.mode,
            facts=json.dumps(facts, ensure_ascii=False, default=str),
            sha=_sha(facts),
            ck=who.kind,
            cc=who.code,
        )
    cites = [Citation(kind=c.kind, ref=c.ref) for c in body.citations]
    kept, dropped = await validate_citations(read, cites)
    tokens, usd = 0, Decimal(0)
    if who.run_id:
        spent = await tx.first(
            """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                                   + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
                          AS tokens,
                      COALESCE(sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)), 0) AS usd
               FROM llm.calls WHERE meta->>'run_id' = :run""",
            run=who.run_id,
        )
        if spent:
            tokens, usd = int(spent["tokens"]), Decimal(spent["usd"])
    second = with_agreement(memo["second_opinion"], body.recommendation)
    third = with_agreement(memo["third_opinion"], body.recommendation)
    row = await tx.one(
        """UPDATE advisor.memos SET state = 'ready', state_reason = NULL, summary_fa = :s,
               recommendation = :rec, confidence = :conf, options = CAST(:opt AS jsonb), against_md = :ag,
               risks = CAST(:risks AS jsonb), questions = CAST(:q AS jsonb), citations = CAST(:cit AS jsonb),
               citations_dropped = :dropped, usage_tokens = :tok, usage_usd = :usd,
               second_opinion = CAST(:so AS jsonb), third_opinion = CAST(:to AS jsonb),
               written_by_code = :by, written_at = now(), updated_at = now()
           WHERE id = :id RETURNING *""",
        s=scrub(body.summary_fa),
        rec=body.recommendation,
        conf=round(body.confidence, 3),
        opt=json.dumps([o.model_dump() for o in body.options], ensure_ascii=False),
        ag=scrub(body.against_md),
        risks=json.dumps([r.model_dump() for r in body.risks], ensure_ascii=False),
        q=json.dumps([scrub(q) for q in body.questions], ensure_ascii=False),
        cit=json.dumps([c.model_dump() for c in kept]),
        dropped=dropped,
        tok=tokens,
        usd=usd,
        so=json.dumps(second, ensure_ascii=False) if second else None,
        to=json.dumps(third, ensure_ascii=False) if third else None,
        by=who.code,
        id=memo["id"],
    )
    if row["work_id"] is not None:
        await _close_work(tx, row["work_id"], row["ref"], who, "memo written")
    await audit.record(
        tx,
        who,
        company_id=holding.id,
        action="memo.write",
        action_class="A1",
        target_kind="memo",
        target_ref=row["ref"],
        summary=f"{d['ref']} v{d['version']} {body.mode}: {body.recommendation}"
        + (f" ({dropped} citations dropped)" if dropped else ""),
    )
    await events.emit(
        tx,
        holding.code,
        "memo.ready",
        row["ref"],
        {"decision": d["ref"], "mode": row["mode"], "recommendation": body.recommendation},
    )
    return row


async def _close_work(tx: Tx, work_id: UUID, ref: str, who: Principal, note: str) -> None:
    w = await W.load(tx, work_id, lock=True)
    if w["status"] in W.CLOSED:
        return
    await tx.exec(
        """UPDATE work.work SET status = 'done', closed_at = now(),
               evidence = evidence || CAST(:ev AS jsonb) WHERE id = :id""",
        ev=json.dumps([{"kind": "link", "ref": ref, "note": note}]),
        id=work_id,
    )
    await W.event(tx, w, "completed", who, {"ref": ref})


# ------------------------------------------------------- the advisor's replies --
async def reply_meta(tx: Tx, who: Principal, thread: str) -> dict[str, Any]:
    """What the advisor's message in thread A carries (contract §21.14):
    `proactive` when its run answers a trigger, `mode: devil` when it answers
    the owner's devil's-advocate message."""
    if thread != "A" or not who.is_agent or not who.run_id:
        return {}
    run = await tx.first(
        "SELECT trigger, work_id FROM agents.runs WHERE id = CAST(:r AS uuid)", r=who.run_id
    )
    if run is None:
        return {}
    if run["work_id"] is not None:
        t = await tx.first(
            "SELECT kind, key FROM advisor.triggers WHERE work_id = :w", w=run["work_id"]
        )
        if t is not None:
            return {"proactive": {"kind": t["kind"], "key": t["key"]}}
    if run["trigger"] == "message":
        mode = await tx.scalar(
            """SELECT m.meta->>'mode' FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
               WHERE t.code = 'A' AND m.author_kind = 'owner' ORDER BY m.seq DESC LIMIT 1"""
        )
        if mode == "devil":
            return {"mode": "devil"}
    return {}


async def after_reply(
    tx: Tx, who: Principal, message: dict[str, Any], meta: dict[str, Any]
) -> None:
    """A proactive note is posted: the trigger keeps its message, the owner
    gets one `report`-level notification (never urgent), the work is done."""
    pro = meta.get("proactive")
    if not pro:
        return
    t = await tx.first("SELECT * FROM advisor.triggers WHERE key = :k FOR UPDATE", k=pro["key"])
    if t is None or t["message_ref"] is not None:
        return
    await tx.exec(
        "UPDATE advisor.triggers SET message_ref = :m, updated_at = now() WHERE id = :id",
        m=message["ref"],
        id=t["id"],
    )
    holding_code = await tx.scalar(
        "SELECT code FROM core.companies WHERE id = :id", id=t["company_id"]
    )
    await notify.raise_notification(
        tx,
        company_id=t["company_id"],
        company_code=str(holding_code),
        level="report",
        title_fa=f"یادداشت مشاور: {KIND_FA.get(t['kind'], t['kind'])}",
        body_fa=f"{message['ref']} در رشته‌ی مشاور",
        link_kind="message",
        link_ref=message["ref"],
        source_kind="agent",
        source_code=who.code,
    )
    await events.emit(
        tx,
        str(holding_code),
        "advisor.proactive",
        message["ref"],
        {"kind": t["kind"], "key": t["key"]},
    )
    if t["work_id"] is not None:
        await _close_work(tx, t["work_id"], message["ref"], who, "proactive note written")


KIND_FA = {
    "budget": "بودجه",
    "quota": "سهمیه‌ی اشتراک",
    "compliance": "افت انطباق",
    "incident": "حادثه‌ی sev1",
    "revenue": "افت کمیسیون",
    "waiting_decisions": "کارت‌های منتظر",
    "finding": "یافته‌ی critical",
    "okr": "OKR عقب",
}


# ---------------------------------------------------------------- triggers --
async def detect(tx: Tx, today: date) -> list[dict[str, Any]]:
    """Every trigger the rules fire now (no model): [{key, kind, company_id, facts}]."""
    day = today.isoformat()
    out: list[dict[str, Any]] = []
    # A company's or the holding's month at or above 90% of its budget.
    for r in await tx.all(
        """SELECT b.scope_type, b.scope_ref, b.company_id, b.token_limit, b.usd_limit,
                  u.tokens, u.usd
           FROM llm.budgets b
           JOIN llm.usage u ON u.scope_type = b.scope_type AND u.scope_ref = b.scope_ref
                           AND u.period = 'month'
                           AND u.period_start = date_trunc('month', now() AT TIME ZONE 'UTC')::date
           WHERE b.enabled AND b.period = 'month' AND b.scope_type IN ('company', 'holding')
             AND ((b.token_limit IS NOT NULL AND u.tokens >= 0.9 * b.token_limit)
                  OR (b.usd_limit IS NOT NULL AND u.usd >= 0.9 * b.usd_limit))"""
    ):
        pct = max(
            (r["tokens"] / r["token_limit"]) if r["token_limit"] else 0,
            float(r["usd"] / r["usd_limit"]) if r["usd_limit"] else 0,
        )
        out.append(
            {
                "key": f"budget:{r['scope_ref']}:{day}",
                "kind": "budget",
                "company_id": r["company_id"],
                "facts": {
                    "scope": f"{r['scope_type']}:{r['scope_ref']}",
                    "percent": round(100 * pct, 1),
                    "tokens": int(r["tokens"]),
                    "usd": str(r["usd"]),
                },
            }
        )
    # A subscription's quota `limited` for more than 2 hours.
    for r in await tx.all(
        """SELECT c.key, q.changed_at, q.resets_at FROM llm.quota_status q
           JOIN llm.connections c ON c.id = q.connection_id
           WHERE q.status = 'limited' AND q.changed_at < now() - interval '2 hours'"""
    ):
        out.append(
            {
                "key": f"quota:{r['key']}:{day}",
                "kind": "quota",
                "company_id": None,
                "facts": {
                    "connection": r["key"],
                    "limited_since": _iso(r["changed_at"]),
                    "resets_at": _iso(r["resets_at"]),
                },
            }
        )
    # A company's compliance score down 10 points or more in a day.
    for r in await tx.all(
        """SELECT t.company_id, c.code, t.score AS today, y.score AS yesterday
           FROM oversight.compliance t
           JOIN oversight.compliance y ON y.company_id = t.company_id AND y.day = t.day - 1
           JOIN core.companies c ON c.id = t.company_id
           WHERE t.day = :d AND y.score - t.score >= 10""",
        d=today,
    ):
        out.append(
            {
                "key": f"compliance:{r['code']}:{day}",
                "kind": "compliance",
                "company_id": r["company_id"],
                "facts": {
                    "company": r["code"],
                    "today": str(r["today"]),
                    "yesterday": str(r["yesterday"]),
                },
            }
        )
    # A sev1 incident open for more than 30 minutes.
    for r in await tx.all(
        """SELECT i.ref, i.company_id, c.code, i.opened_at FROM ops.incidents i
           JOIN core.companies c ON c.id = i.company_id
           WHERE i.closed_at IS NULL AND i.severity = 'sev1' AND i.opened_at < now() - interval '30 minutes'"""
    ):
        out.append(
            {
                "key": f"incident:{r['ref']}:{day}",
                "kind": "incident",
                "company_id": r["company_id"],
                "facts": {
                    "incident": r["ref"],
                    "company": r["code"],
                    "opened_at": _iso(r["opened_at"]),
                },
            }
        )
    # The day's commission under 60% of the same weekday's 28-day median (§19.1):
    # the revenue radar's own `drop` alert of the last day.
    for r in await tx.all(
        """SELECT a.company_id, c.code, a.day, a.data FROM revenue.alerts a
           JOIN core.companies c ON c.id = a.company_id
           WHERE a.kind = 'drop' AND a.created_at >= now() - interval '24 hours'"""
    ):
        out.append(
            {
                "key": f"revenue:{r['code']}:{day}",
                "kind": "revenue",
                "company_id": r["company_id"],
                "facts": {
                    "company": r["code"],
                    "day": r["day"].isoformat() if r["day"] else None,
                    "data": redact(r["data"] or {}, max_string=200, max_list=10),
                },
            }
        )
    # Three or more of the owner's cards waiting more than 72 hours.
    waiting = await tx.first(
        """SELECT count(*) AS n, (array_agg(ref ORDER BY created_at))[1:10] AS refs
           FROM cartable.decisions
           WHERE status = 'pending' AND approver_code IS NULL AND created_at < now() - interval '72 hours'"""
    )
    if waiting and int(waiting["n"]) >= 3:
        out.append(
            {
                "key": f"waiting_decisions:{day}",
                "kind": "waiting_decisions",
                "company_id": None,
                "facts": {"count": int(waiting["n"]), "oldest": list(waiting["refs"] or [])},
            }
        )
    # A critical finding open for more than 24 hours.
    for r in await tx.all(
        """SELECT f.ref, f.company_id, c.code, f.opened_at FROM oversight.findings f
           JOIN core.companies c ON c.id = f.company_id
           WHERE f.severity = 'critical' AND f.status NOT IN ('fixed', 'verified', 'closed')
             AND f.opened_at < now() - interval '24 hours'"""
    ):
        out.append(
            {
                "key": f"finding:{r['ref']}:{day}",
                "kind": "finding",
                "company_id": r["company_id"],
                "facts": {
                    "finding": r["ref"],
                    "company": r["code"],
                    "opened_at": _iso(r["opened_at"]),
                },
            }
        )
    out += await _okr_behind(tx, today)
    return out


# Prompt 11's key results (contract §20.5; migration 0026_1): a key result
# under 70% of its pace in the second half of its quarter. Until the table
# exists (prompt 11 merged under this one) this rule fires nothing.
OKR_TABLE = "governance.key_results"


def okr_progress(start: float, target: float, current: float | None) -> float:
    """A key result's progress as prompt 11 computes it (gov_okr.progress):
    (current - start) / (target - start), clamped to 0..1."""
    if current is None:
        return 0.0
    if target == start:
        return 1.0 if current == target else 0.0
    return max(0.0, min(1.0, (current - start) / (target - start)))


def jalali_to_gregorian(y: int, m: int, d: int) -> date:
    """The Gregorian day of a Jalali date (searched around its estimate)."""
    from hq_api.worker.jalali import to_jalali

    offset = (m - 1) * 31 if m <= 7 else 6 * 31 + (m - 7) * 30
    guess = date(y + 621, 3, 21) + timedelta(days=offset + d - 1)
    for delta in (0, -1, 1, -2, 2, -3, 3):
        g = guess + timedelta(days=delta)
        if to_jalali(g) == (y, m, d):
            return g
    raise ValueError(f"not a Jalali date: {y}-{m}-{d}")


def quarter_span(quarter: str) -> tuple[date, date] | None:
    """A Jalali quarter ("1405-Q3") as [first day, first day of the next)."""
    m = re.fullmatch(r"(\d{4})-Q([1-4])", quarter)
    if not m:
        return None
    y, q = int(m.group(1)), int(m.group(2))
    start = jalali_to_gregorian(y, 3 * q - 2, 1)
    end = jalali_to_gregorian(y + 1, 1, 1) if q == 4 else jalali_to_gregorian(y, 3 * q + 1, 1)
    return start, end


async def _okr_behind(tx: Tx, today: date) -> list[dict[str, Any]]:
    if not await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=OKR_TABLE):
        return []
    out: list[dict[str, Any]] = []
    # A KPI-linked key result takes the KPI's last value, a metric its own
    # check-in (prompt 11's kr_current).
    rows = await tx.all(
        f"""SELECT kr.ref, kr.company_id, c.code, o.quarter, kr.start, kr.target,
                   CASE WHEN kr.kpi_key IS NOT NULL
                        THEN (SELECT k.last_value FROM governance.kpis k
                               WHERE k.company_id = kr.company_id AND k.key = kr.kpi_key)
                        ELSE kr.current END AS current
            FROM {OKR_TABLE} kr
            JOIN governance.objectives o ON o.id = kr.objective_id
            JOIN core.companies c ON c.id = kr.company_id
            WHERE o.status = 'active'"""  # noqa: S608 - a constant table name
    )
    for r in rows:
        span = quarter_span(str(r["quarter"]))
        if span is None:
            continue
        start, end = span
        total = (end - start).days or 1
        elapsed = (today - start).days / total
        if elapsed < 0.5 or elapsed > 1:
            continue
        progress = okr_progress(
            float(r["start"]),
            float(r["target"]),
            None if r["current"] is None else float(r["current"]),
        )
        pace = progress / elapsed
        if pace < 0.7:
            out.append(
                {
                    "key": f"okr:{r['ref']}:{today.isoformat()}",
                    "kind": "okr",
                    "company_id": r["company_id"],
                    "facts": {
                        "key_result": r["ref"],
                        "company": r["code"],
                        "progress": round(progress, 3),
                        "pace": round(pace, 2),
                    },
                }
            )
    return out


async def fire_triggers(tx: Tx, hub: Any, now: datetime | None = None) -> dict[str, int]:
    """Record today's new triggers (unique keys) and wake the advisor for
    each one that fits: holding locked or the owner zone spent -> `deferred`,
    beyond proactive_per_day -> `capped`."""
    s, tz = await settings(tx)
    today = owner_day(tz, now)
    holding = await hub.companies.holding()
    counts = {"sent": 0, "deferred": 0, "capped": 0, "seen": 0}
    lock = await gate.automation_lock(tx)
    spent = lock is None and await zone_spent(tx, hub)
    advisor = await _advisor_code(tx)
    for t in await detect(tx, today):
        row = await tx.first(
            """INSERT INTO advisor.triggers (company_id, key, kind, subject_company_id, day, facts, state)
               VALUES (:co, :key, :kind, :sub, :day, CAST(:facts AS jsonb), 'deferred')
               ON CONFLICT (key) DO NOTHING RETURNING *""",
            co=holding.id,
            key=t["key"][:200],
            kind=t["kind"],
            sub=t["company_id"],
            day=today,
            facts=json.dumps(t["facts"], ensure_ascii=False, default=str),
        )
        if row is None:  # the same trigger today: the advisor is not woken again
            counts["seen"] += 1
            continue
        sent_today = int(
            await tx.scalar(
                "SELECT count(*) FROM advisor.triggers WHERE day = :d AND state = 'sent'", d=today
            )
            or 0
        )
        state, reason = "sent", None
        if lock is not None:
            state, reason = "deferred", gate.REASONS.get(lock, lock)
        elif sent_today >= int(s.get("proactive_per_day", 3)):
            state, reason = "capped", "proactive_per_day"
        elif spent:
            state, reason = "deferred", "owner_zone_share"
        elif advisor is None:
            state, reason = "deferred", "the advisor is not seated"
        work_id = None
        if state == "sent":
            assert advisor is not None
            w = await W.create(
                tx,
                SERVICE,
                company_id=holding.id,
                company_code=holding.code,
                title=f"یادداشت فعال مشاور: {KIND_FA.get(t['kind'], t['kind'])}"[:300],
                brief=(
                    f"A rule fired the trigger {t['key']} ({t['kind']}). Write ONE short message in "
                    'your thread with the owner (message.thread, thread "A"), citing the trigger '
                    "and the facts below; it goes to the owner at `report` level, never urgent. "
                    "Nothing else; then finish (done).\n\nFacts (gathered by code):\n"
                    + json.dumps(t["facts"], ensure_ascii=False, default=str)[:4000]
                ),
                kind="one_off",
                priority="P3",
                assignee_code=advisor,
                budget=W.BudgetIn(tokens=PROACTIVE_TOKENS),
            )
            work_id = w["id"]
            await tx.exec(
                "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
                id=work_id,
                m=json.dumps(
                    {
                        "task_class": "advisor_proactive",
                        "owner_zone": owner_zone.AUTO,
                        "trigger": t["key"],
                    }
                ),
            )
        await tx.exec(
            """UPDATE advisor.triggers SET state = :st, state_reason = :r, work_id = :w, updated_at = now()
               WHERE id = :id""",
            st=state,
            r=reason,
            w=work_id,
            id=row["id"],
        )
        counts[state] += 1
        await events.emit(
            tx, holding.code, "advisor.trigger", t["key"][:200], {"kind": t["kind"], "state": state}
        )
    return counts


# ------------------------------------------------------------ the sweep --
async def auto_memos(tx: Tx, hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """Automatic memos for the owner's qualifying cards of today (and a new
    version of a card whose automatic memo went stale), in creation order,
    up to the day's cap. Nothing while the holding is locked or the owner
    zone is spent."""
    s, tz = await settings(tx)
    if not s["auto_memo"].get("enabled", True):
        return {"made": 0, "skipped": "off"}
    lock = await gate.automation_lock(tx)
    if lock is not None:
        return gate.skipped(lock, made=0)
    if await zone_spent(tx, hub):
        return {"made": 0, "skipped": "owner_zone_share"}
    today = owner_day(tz, now)
    cap = int(s["auto_memo"].get("max_per_day", 3))
    made_today = int(
        await tx.scalar(
            """SELECT count(*) FROM advisor.memos
               WHERE trigger = 'auto' AND (created_at AT TIME ZONE :tz)::date = :d""",
            tz=tz,
            d=today,
        )
        or 0
    )
    from hq_api.domain import decisions as D

    rows = await tx.all(
        D.DECISION_SQL  # noqa: S608 - constant SQL, every value bound
        + """ WHERE d.status = 'pending' AND d.approver_code IS NULL
                AND (d.risk = 'high' OR d.kind = ANY(:kinds))
                AND ((d.created_at AT TIME ZONE :tz)::date = :d
                     OR EXISTS (SELECT 1 FROM advisor.memos s WHERE s.decision_id = d.id
                                AND s.trigger = 'auto' AND s.state = 'stale'))
                AND NOT EXISTS (SELECT 1 FROM advisor.memos m WHERE m.decision_id = d.id
                                AND m.mode = 'standard' AND m.decision_version = d.version)
              ORDER BY d.created_at, d.id""",
        kinds=list(AUTO_KINDS),
        tz=tz,
        d=today,
    )
    made: list[str] = []
    for d in rows:
        if made_today + len(made) >= cap:
            break
        memo, created = await request(tx, hub, SERVICE, d, "standard", "auto")
        if created:
            made.append(memo["ref"])
    return {"made": len(made), "memos": made, "cap": cap}


async def fail_orphans(tx: Tx) -> int:
    """A memo whose run ended (or whose work closed) without memo.write."""
    rows = await tx.all(
        """UPDATE advisor.memos m SET state = 'failed', state_reason = 'the advisor run ended without memo.write',
                  updated_at = now()
           FROM work.work w
           WHERE m.work_id = w.id AND m.state = 'writing' AND m.created_at < now() - make_interval(secs => :age)
             AND (w.status IN ('done', 'cancelled', 'failed')
                  OR (EXISTS (SELECT 1 FROM agents.runs r WHERE r.work_id = w.id
                              AND r.state IN ('done', 'failed', 'refused'))
                      AND NOT EXISTS (SELECT 1 FROM agents.runs r WHERE r.work_id = w.id
                                      AND r.state IN ('queued', 'running'))))
           RETURNING m.ref""",
        age=int(FAILED_AFTER.total_seconds()),
    )
    return len(rows)


async def fire_triggers_tx(hub: Any, now: datetime | None = None) -> dict[str, int]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await fire_triggers(tx, hub, now)


async def sweep(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The worker's advisor sweep (every few minutes): failed memos, the
    automatic memos, the proactive triggers. Rule-only until a run is made."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        failed = await fail_orphans(tx)
        memos = await auto_memos(tx, hub, now)
        triggers = await fire_triggers(tx, hub, now)
    return {"failed": failed, "auto_memos": memos, "triggers": triggers}
