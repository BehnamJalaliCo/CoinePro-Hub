"""Hiring: the owner opens it, the CEOs hire (contract §18.11, v1.4.2-1.4.3;
prompt 5.1 §1.3 and its review).

The state is one row of core.hiring for the holding (migration 0010); no
row reads "closed". While closed, an agent's hire proposal is refused before
any card exists (403 hiring_closed, here and in OPA hq.internal). The state
is read FOR SHARE in the proposing transaction, so a close committing
meanwhile waits for it and then withdraws the card it made. The owner opens
hiring in one of two modes:

  proposals  hiring opens to agents and the owner decides every card; each
             CEO (and each holding head with a hiring duty,
             seed/bootstrap/hiring_proposals.yaml) gets one work item
             "propose your first month's team" (a second start adds none)
  delegated  each CEO decides inside the company's monthly envelope (prompt
             8 §8): every active operating company needs a monthly envelope
             first (422 envelope_required); an operating company's hire card
             gets its CEO as approver and a work item "decide D-…" for it;
             holding cards stay with the owner; the owner may decide any
             card first

The owner hires directly in any state (POST /org/hires). Closing (always
safe, no step-up) withdraws every pending hire card through
cartable.withdraw_pending_hires, the same function the migration used.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from hq_api import bootstrap, events
from hq_api.db import Tx
from hq_api.domain import notify, stories
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor
from hq_api.worker.jalali import to_jalali

NOTE = "مالک: استخدام با شروع خود مالک"
PROPOSALS_KEY = "hiring_proposals"

Mode = Literal["proposals", "delegated"]  # proposals first: the one served (examples)


class Envelope(BaseModel):
    """One operating company's monthly token envelope (contract §18.11)."""

    company: str
    tokens_month: int | None  # the company's monthly budget (llm.budgets), if set
    committed_month: int  # monthly estimates of its approved hires: active, or not made yet
    used_month: int  # tokens used this Jalali month
    hires_month: int  # hire cards approved this Jalali month


class Hiring(BaseModel):
    state: Literal["closed", "open"]
    mode: Mode | None
    changed_at: datetime | None
    changed_by: Actor | None
    withdrawn: list[str]
    envelopes: list[Envelope] = Field(default_factory=list)


async def state(tx: Tx) -> str:
    """ "open" or "closed" for any caller (a definer function: an agent's own
    company-scoped transaction cannot see the holding's row)."""
    value: str | None = await tx.scalar("SELECT core.hiring_state()")
    return value or "closed"


async def require_open(tx: Tx, who: Principal, kind: str) -> None:
    """An agent's hire proposal while hiring is closed: 403 hiring_closed. The
    holding's row is read FOR SHARE: a concurrent close (an UPDATE of it)
    waits for this transaction and then withdraws the card it made."""
    if kind != "hire" or not who.is_agent:
        return
    if await tx.scalar("SELECT core.hiring_state_for_share()") != "open":
        raise ApiError(403, "hiring_closed")


async def mode(tx: Tx) -> str | None:
    """The mode while hiring is open (None while closed), for any caller."""
    value: str | None = await tx.scalar("SELECT core.hiring_mode()")
    return value


async def require_envelopes(tx: Tx, mode_: str) -> None:
    """`delegated` needs a monthly envelope for every active operating company
    (checked before any step-up is consumed): 422 envelope_required naming them."""
    if mode_ != "delegated":
        return
    missing = [e.company for e in await envelopes(tx) if not e.tokens_month]
    if missing:
        raise ApiError(422, "envelope_required", fields={"envelopes": ", ".join(missing)})


async def approver_for(tx: Tx, company_id: UUID, company_kind: str) -> str | None:
    """Who decides a new hire card: an operating company's CEO while hiring is
    delegated (contract §18.11), else the owner (None)."""
    if company_kind != "company" or await mode(tx) != "delegated":
        return None
    ceo: str | None = await tx.scalar(
        """SELECT code FROM core.employees
           WHERE company_id = :co AND kind = 'ceo' AND status = 'active' ORDER BY hired_at LIMIT 1""",
        co=company_id,
    )
    return ceo


MAX_HIRES_PER_DAY = 5  # per company: a loop guard (contract §18.11)


async def check_approval(
    tx: Tx, d: dict[str, Any], payload: dict[str, Any], charters: Any, *, by_ceo: bool
) -> None:
    """The hard checks of every hire approval, whoever approves, in the
    approving transaction (contract §18.11); a refusal is a stable code and
    no employee is made. The charter's fit is checked by the caller first.

    Every approval of a company runs under one per-company lock (contract
    §18.15): a second approval waits until the first commits, then counts its
    card (approved, employee not made yet) in `committed` and in the five a
    day, so two approvals can never both fit an envelope only one fits."""
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"hire:{d['company_id']}"
    )
    model = str(payload.get("model") or "")
    if not await tx.scalar(
        "SELECT EXISTS (SELECT 1 FROM llm.connections WHERE status = 'enabled' AND models ? :m)",
        m=model,
    ):
        raise ApiError(
            422, "validation_failed", fields={"payload.model": "no enabled connection offers it"}
        )
    charter = charters.get(payload.get("role")) if charters is not None else None
    estimate = (payload.get("quota_estimate_month") or {}).get("tokens")
    floor = charter.limits.tokens_per_run if charter is not None else 1
    if not estimate or int(estimate) < floor:
        raise ApiError(
            422,
            "validation_failed",
            fields={
                "payload.quota_estimate_month": f"a monthly token estimate of at least {floor}"
            },
        )
    env = next((e for e in await envelopes(tx) if e.company == d["company"]), None)
    if env is not None and env.tokens_month:
        if env.committed_month + int(estimate) > env.tokens_month:
            raise ApiError(
                409,
                "envelope_exceeded",
                f"{env.committed_month} committed + {estimate} > {env.tokens_month}",
            )
    elif by_ceo:
        raise ApiError(422, "envelope_required", fields={"envelopes": d["company"]})
    lock = await tx.scalar("SELECT control.lock_state(:co)", co=d["company_id"])
    if lock in ("company", "holding"):
        raise ApiError(423, "company_locked")
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    today = await tx.scalar(
        """SELECT count(*) FROM cartable.decisions
           WHERE company_id = :co AND kind = 'hire' AND status = 'approved'
             AND (decided_at AT TIME ZONE :tz)::date = (now() AT TIME ZONE :tz)::date""",
        co=d["company_id"],
        tz=tz,
    )
    if int(today) >= MAX_HIRES_PER_DAY:
        raise ApiError(429, "rate_limited", f"at most {MAX_HIRES_PER_DAY} hires a day per company")


def jalali_month_start(today: date) -> date:
    """The Gregorian date of the first day of today's Jalali month."""
    _, _, day = to_jalali(today)
    return today - timedelta(days=day - 1)


async def envelopes(tx: Tx) -> list[Envelope]:
    """Every active operating company's envelope (contract §18.11). The month
    is the owner's Jalali month, from midnight in the owner's time zone."""
    tz = ZoneInfo(
        str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran")
    )
    start = jalali_month_start(datetime.now(tz).date())
    rows = await tx.all(
        """SELECT c.code,
                  (SELECT b.token_limit FROM llm.budgets b
                    WHERE b.company_id = c.id AND b.scope_type = 'company' AND b.scope_ref = c.code
                      AND b.period = 'month' AND b.enabled) AS tokens_month,
                  (SELECT COALESCE(sum(COALESCE((COALESCE(d.amendments->'quota_estimate_month',
                                                          d.payload->'quota_estimate_month')
                                                 ->>'tokens')::bigint, 0)), 0)
                     FROM cartable.decisions d
                     LEFT JOIN core.employees e ON e.hired_by_decision_id = d.id
                    WHERE d.company_id = c.id AND d.kind = 'hire' AND d.status = 'approved'
                      AND (e.status = 'active'
                           OR (e.id IS NULL AND d.effect_status = 'pending'))) AS committed_month,
                  (SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                                       + COALESCE(k.cache_read_tokens, 0)
                                       + COALESCE(k.cache_write_tokens, 0)), 0)
                     FROM llm.calls k WHERE k.company_id = c.id AND k.started_at >= :start) AS used_month,
                  (SELECT count(*) FROM cartable.decisions d
                    WHERE d.company_id = c.id AND d.kind = 'hire' AND d.status = 'approved'
                      AND d.decided_at >= :start) AS hires_month
           FROM core.companies c WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code""",
        start=datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC),
    )
    return [
        Envelope(
            company=r["code"],
            tokens_month=int(r["tokens_month"]) if r["tokens_month"] is not None else None,
            committed_month=int(r["committed_month"]),
            used_month=int(r["used_month"]),
            hires_month=int(r["hires_month"]),
        )
        for r in rows
    ]


PROBATION_DAYS = 7
REVIEW_HOURS = 24  # the overseer's hire review (protocol PR-098)


async def after_hire(
    tx: Tx, d: dict[str, Any], employee_code: str, payload: dict[str, Any]
) -> None:
    """After an approved hire: its `hire` story (every hire, contract §18.12);
    after a delegated one (a card its CEO decides) also the 7-day probation,
    one `report` line for the owner's digest (never an urgent push) and a
    review item for the Chief Overseer (PR-098, 24 h, only while PR-098 is
    active). A card the owner approved first is the owner's hire: no
    probation and no «… استخدام کرد» line (contract §18.15)."""
    estimate = (payload.get("quota_estimate_month") or {}).get("tokens")
    await stories.system(
        tx,
        company_id=d["company_id"],
        company_code=d["company"],
        kind="hire",
        title_fa=f"استخدام: {payload['title_fa']}",
        body_fa=str(payload.get("reason") or ""),
        figures=[
            {"label_fa": "نقش", "value": str(payload.get("role") or "-")},
            {
                "label_fa": "مدل",
                "value": f"{str(payload['model']).removeprefix('claude-')}·{payload['effort']}",
            },
            {"label_fa": "برآورد ماهانه", "value": stories.short(estimate)},
        ],
        links={"employee": employee_code, "decision": d["ref"]},
        event_key=f"hire:{d['ref']}",
    )
    if d.get("decided_by_kind") != "agent":
        return
    ceo = str(d["decided_by_code"])
    await tx.exec(
        """UPDATE core.employees SET probation_until = now() + make_interval(days => :n)
           WHERE code = :c""",
        n=PROBATION_DAYS,
        c=employee_code,
    )
    await notify.raise_notification(
        tx,
        company_id=d["company_id"],
        company_code=d["company"],
        level="report",
        title_fa=f"{ceo} استخدام کرد: {employee_code} ({payload['title_fa']})"[:300],
        body_fa=(
            f"{payload['model']} / {payload['effort']} · برآورد ماهانه {stories.short(estimate)} توکن"
            " · دوره‌ی آزمایشی ۷ روز. برگرداندن: صفحه‌ی کارمند یا استوری."
        ),
        link_kind="employee",
        link_ref=employee_code,
        source_kind="service",
        source_code="hiring",
    )
    holding = await tx.first(
        """SELECT c.id, c.code, (SELECT e.code FROM core.employees e
                                  WHERE e.company_id = c.id AND e.kind = 'overseer' AND e.status = 'active'
                                  ORDER BY e.hired_at LIMIT 1) AS overseer
           FROM core.companies c WHERE c.kind = 'holding'"""
    )
    if holding is None or not holding["overseer"]:
        return
    from hq_api.domain import oversight  # the review is PR-098's: none while it is not active

    if await oversight.protocol_in_force(tx, "PR-098") is None:
        return
    await W.create(
        tx,
        Principal(kind="service", code="hiring", role="service"),
        company_id=holding["id"],
        company_code=holding["code"],
        title=f"بازبینی استخدام {employee_code} ({d['ref']}) · PR-098"[:300],
        brief=(
            f"{ceo} با تصمیم {d['ref']} کارمند {employee_code} ({payload['title_fa']}، "
            f"نقش {payload.get('role')}، {payload['model']} / {payload['effort']}، برآورد ماهانه "
            f"{estimate}) را در {d['company']} استخدام کرد. ظرف ۲۴ ساعت بررسی کن: پاکت، انتخاب مدل، "
            "دلیل و نیاز واقعی. اگر لازم است hold کن یا یافته باز کن؛ تأیید یا آزاد کردن با مالک است."
        ),
        kind="one_off",
        priority="P2",
        assignee_code=holding["overseer"],
        due_at=await tx.scalar("SELECT now() + make_interval(hours => :h)", h=REVIEW_HOURS),
    )


async def load(tx: Tx, holding_id: UUID) -> Hiring:
    row = await tx.first(
        """SELECT state, mode, changed_at, changed_by_kind, changed_by_code, withdrawn
           FROM core.hiring WHERE company_id = :co""",
        co=holding_id,
    )
    env = await envelopes(tx)
    if row is None:
        return Hiring(
            state="closed", mode=None, changed_at=None, changed_by=None, withdrawn=[], envelopes=env
        )
    return Hiring(
        state=row["state"],
        mode=row["mode"],
        changed_at=row["changed_at"],
        changed_by=actor(row["changed_by_kind"], row["changed_by_code"]),
        withdrawn=list(row["withdrawn"] or []),
        envelopes=env,
    )


async def _set(tx: Tx, holding_id: UUID, who: Principal, state_: str, mode: str | None) -> None:
    await tx.exec(
        """INSERT INTO core.hiring (company_id) VALUES (:co) ON CONFLICT (company_id) DO NOTHING""",
        co=holding_id,
    )
    await tx.exec(
        """UPDATE core.hiring SET state = :st, mode = :mode, changed_at = now(),
               changed_by_kind = :k, changed_by_code = :c
           WHERE company_id = :co""",
        co=holding_id,
        st=state_,
        mode=mode,
        k="owner" if who.is_owner else "service",
        c=who.code,
    )


DECIDE_TITLE = "تصمیم درباره‌ی {ref}:"  # the CEO's work item for a card (decisions.propose)


async def close_decide_items(tx: Tx, refs: list[str], reason: str) -> list[str]:
    """The CEOs' open «decide D-…» work items of these cards are closed
    (cancelled): the card was withdrawn, given back to the owner or decided
    by the owner first, so nothing is left for the CEO to decide."""
    if not refs:
        return []
    rows = await tx.all(
        """UPDATE work.work w SET status = 'cancelled', close_reason = :r, closed_at = now()
           FROM unnest(CAST(:refs AS text[])) AS x(ref)
           WHERE starts_with(w.title, replace(:t, '{ref}', x.ref))
             AND w.created_by_kind = 'service' AND w.created_by_code = 'hiring'
             AND w.status IN ('queued', 'in_progress', 'waiting')
           RETURNING w.ref""",
        refs=refs,
        t=DECIDE_TITLE,
        r=reason[:500],
    )
    return [str(r["ref"]) for r in rows]


async def return_to_owner(tx: Tx) -> list[str]:
    """Hiring switched to `proposals`: the pending hire cards a CEO was to
    decide return to the owner's cartable (approver cleared)."""
    rows = await tx.all(
        """UPDATE cartable.decisions SET approver_kind = NULL, approver_code = NULL
           WHERE kind = 'hire' AND status = 'pending' AND approver_code IS NOT NULL
           RETURNING ref"""
    )
    refs = [str(r["ref"]) for r in rows]
    await close_decide_items(tx, refs, "مالک: حالت استخدام «پیشنهاد» شد؛ تصمیم با مالک است")
    return refs


async def withdraw_pending(tx: Tx) -> list[str]:
    refs = await tx.scalar("SELECT cartable.withdraw_pending_hires(:note)", note=NOTE)
    return list(refs or [])


async def start(
    tx: Tx,
    who: Principal,
    *,
    holding_id: UUID,
    holding_code: str,
    mode: Mode,
    charters: Any,
) -> dict[str, Any]:
    """Open hiring in mode `proposals` or `delegated` (envelopes checked first).
    Switching to `proposals` gives every pending card back to the owner: its
    `approver` is cleared and its CEO's «decide D-…» item is closed (§18.15)."""
    await require_envelopes(tx, mode)
    await _set(tx, holding_id, who, "open", mode)
    if mode == "proposals":
        await return_to_owner(tx)
    out = await bootstrap.apply(tx, bootstrap.load(PROPOSALS_KEY), who=who, charters=charters)
    work: list[dict[str, str]] = out["created"]
    await events.emit(
        tx, holding_code, "hiring.changed", None, {"state": "open", "mode": mode, "work": work}
    )
    return {"work": work}


async def close(tx: Tx, who: Principal, *, holding_id: UUID, holding_code: str) -> list[str]:
    """Close hiring; pending hire cards are withdrawn (never deleted)."""
    await _set(tx, holding_id, who, "closed", None)
    refs = await withdraw_pending(tx)
    await close_decide_items(tx, refs, NOTE)
    await events.emit(
        tx,
        holding_code,
        "hiring.changed",
        None,
        {"state": "closed", "mode": None, "withdrawn": refs},
    )
    return refs
