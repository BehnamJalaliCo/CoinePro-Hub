"""The monthly HR round (prompt 12 §6, contract §21.5) and PR-082.

On the 1st of each Jalali month (10:00, owner zone; after the monthly stars
roll-up) a round HR-0001 opens for every active operating company and the
holding: the facts of each employee are gathered by code, the flags are
rules, and the evaluator gets one work item (due in 20 h):

  promote_candidate  score >= 8.5 two months running, stars >= 4, no open high finding
  coach              a drop >= 1.5, or a score in [5, 6)
  demote_candidate   score < 5 two months running
  dismiss_candidate  score < 3.5 two months running, or probation ended with score < 5
  probation_end      the probation period is over

The evaluator (the company's HR manager, else its CEO; for the holding the AI
Ops head) delivers the monthly HR report and proposes `evaluation` cards for
flagged employees only; a card for an unflagged one needs evidence and an
`override_reason` and is marked `unflagged: true`. `coach` makes no card: an
academy teaching draft for the AI Ops head.

Approving a card is the owner's (🔏 decision.approve). promote / demote
apply `change` under the hire checks of §18.11 (an enabled connection offers
the model; the envelope still fits, else 409 envelope_exceeded and nothing
changes); dismiss is the dismissal of §3.3 with `transfer_to`; confirm clears
probation_until.

Scores are kept per Gregorian month (core.employee_scores): the round reads
the latest one as this month's and the one before it as last month's.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import hiring, org
from hq_api.domain import oversight_checks as C
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.worker.jalali import to_jalali

SERVICE = Principal(kind="service", code="hr", role="service")
FLAGS = ("promote_candidate", "coach", "demote_candidate", "dismiss_candidate", "probation_end")
CARD_FLAGS = {
    "promote": ("promote_candidate",),
    "demote": ("demote_candidate",),
    "dismiss": ("dismiss_candidate",),
    "confirm": ("probation_end",),
}
DUE_HOURS = 20
FIRST_DAY = 1  # the round opens on the 1st of the Jalali month


# ------------------------------------------------------------------ rules --
def flags(
    score: float | None,
    prev: float | None,
    stars: float | None,
    high_open: int,
    probation_until: datetime | None,
    now: datetime,
) -> list[str]:
    """The rule flags of one employee (pure)."""
    out: list[str] = []
    ended = probation_until is not None and probation_until <= now
    if score is not None and prev is not None:
        if score >= 8.5 and prev >= 8.5 and (stars or 0) >= 4 and high_open == 0:
            out.append("promote_candidate")
        if prev - score >= 1.5 or 5 <= score < 6:
            out.append("coach")
        if score < 5 and prev < 5:
            out.append("demote_candidate")
        if (score < 3.5 and prev < 3.5) or (ended and score < 5):
            out.append("dismiss_candidate")
    elif score is not None:
        if 5 <= score < 6:
            out.append("coach")
        if ended and score < 5:
            out.append("dismiss_candidate")
    if ended:
        out.append("probation_end")
    return out


def month_key(day: date) -> str:
    y, m, _ = to_jalali(day)
    return f"{y:04d}-{m:02d}"


async def evaluator(tx: Tx, company_id: UUID, kind: str) -> tuple[str, str] | None:
    """(kind, code) of who evaluates: HR manager, else the CEO; the holding's AI Ops head."""
    if kind == "holding":
        code = await tx.scalar(
            """SELECT code FROM core.employees WHERE company_id = :co AND status = 'active'
                 AND role = 'aiops_head' ORDER BY created_at LIMIT 1""",
            co=company_id,
        )
        return ("agent", str(code)) if code else None
    code = await tx.scalar(
        """SELECT e.code FROM core.employees e JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND e.status = 'active' AND e.kind = 'manager' AND d.code = 'HR'
           ORDER BY e.created_at LIMIT 1""",
        co=company_id,
    )
    if code is None:
        code = await tx.scalar(
            """SELECT code FROM core.employees WHERE company_id = :co AND status = 'active'
                 AND kind = 'ceo' ORDER BY created_at LIMIT 1""",
            co=company_id,
        )
    return ("agent", str(code)) if code else None


async def facts(tx: Tx, company_id: UUID, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Each active employee's facts for the month [start, end), by code."""
    rows = await tx.all(
        """SELECT e.id, e.code, e.title_fa, e.probation_until,
               (SELECT value FROM core.employee_scores s WHERE s.employee_id = e.id
                 ORDER BY month DESC LIMIT 1) AS score,
               (SELECT value FROM core.employee_scores s WHERE s.employee_id = e.id
                 ORDER BY month DESC OFFSET 1 LIMIT 1) AS score_prev,
               (SELECT avg(st.stars) FROM people.stars st WHERE st.employee_id = e.id AND st.counted
                  AND st.week >= (:s AT TIME ZONE 'UTC')::date - 6 AND st.week < (:e AT TIME ZONE 'UTC')::date)
                 AS stars,
               e.score_owner_avg AS owner_avg,
               (SELECT count(*) FROM agents.runs r WHERE r.employee_id = e.id
                  AND r.queued_at >= :s AND r.queued_at < :e AND r.state IN ('done', 'failed', 'refused')) AS runs,
               (SELECT count(*) FROM agents.runs r WHERE r.employee_id = e.id
                  AND r.queued_at >= :s AND r.queued_at < :e AND r.state IN ('failed', 'refused')) AS failed,
               (SELECT count(*) FROM oversight.findings f WHERE f.answerable_code = e.code
                  AND f.status NOT IN ('verified', 'closed')) AS findings_open,
               (SELECT count(*) FROM oversight.findings f WHERE f.answerable_code = e.code
                  AND f.status NOT IN ('verified', 'closed') AND f.severity IN ('high', 'critical'))
                 AS findings_high,
               (SELECT count(*) FROM quality.claims q WHERE q.employee_id = e.id
                  AND q.verdict = 'refuted' AND q.at >= :s AND q.at < :e) AS refuted_claims
           FROM core.employees e
           WHERE e.company_id = :co AND e.status = 'active' AND e.kind NOT IN ('system')
           ORDER BY e.code""",
        co=company_id,
        s=start,
        e=end,
    )
    now = datetime.now(UTC)
    out = []
    for r in rows:
        score = float(r["score"]) if r["score"] is not None else None
        prev = float(r["score_prev"]) if r["score_prev"] is not None else None
        stars = round(float(r["stars"]), 2) if r["stars"] is not None else None
        out.append(
            {
                "code": r["code"],
                "title_fa": r["title_fa"],
                "score": score,
                "score_prev": prev,
                "stars": stars,
                "efficiency": None,
                "owner_avg": float(r["owner_avg"]) if r["owner_avg"] is not None else None,
                "failed_share": round(int(r["failed"]) / int(r["runs"]), 3)
                if int(r["runs"])
                else 0.0,
                "findings_open": int(r["findings_open"]),
                "refuted_claims": int(r["refuted_claims"]),
                "probation_until": r["probation_until"].isoformat()
                if r["probation_until"]
                else None,
                "flags": flags(
                    score, prev, stars, int(r["findings_high"]), r["probation_until"], now
                ),
            }
        )
    return out


async def efficiency_of(tx: Tx, key: str) -> dict[str, float]:
    """The employees' efficiency of the last monthly roll-up (§18.4), by code."""
    row = await tx.first(
        "SELECT data FROM people.star_rollups WHERE period = 'month' AND key = :k", k=key
    )
    return {
        e["code"]: e["efficiency"]
        for e in ((row or {}).get("data") or {}).get("employees", [])
        if e.get("efficiency") is not None
    }


# ------------------------------------------------------------- the round --
def brief(round_ref: str, company: str, month: str, employees: list[dict[str, Any]]) -> str:
    flagged = [e for e in employees if e["flags"]]
    lines = [
        f"دور ارزیابی ماهانه‌ی {round_ref} برای {company}، ماه {month}.",
        "۱) خروجی ماهانه‌ی HR را با deliver بنویس (نوع hr_monthly): وضعیت هر کارمند با شاهد.",
        "۲) فقط برای کارمندهای پرچم‌خورده کارت evaluation بساز (propose kind=evaluation، "
        f'payload.round="{round_ref}"؛ recommendation: promote | demote | dismiss | confirm؛ '
        "evidence[] اجباری). برای کارمند بی‌پرچم فقط با شاهد و override_reason.",
        "۳) پرچم coach کارت ندارد: پیش‌نویس آموزش آکادمی برای مدیر AI Ops ساخته شده است.",
        "",
        "واقعیت‌ها (با کد):",
        "```json",
        json.dumps(employees, ensure_ascii=False, default=str)[:20000],
        "```",
        f"پرچم‌خورده‌ها: {', '.join(e['code'] for e in flagged) or 'هیچ'}",
    ]
    return "\n".join(lines)


async def open_round(
    tx: Tx, company: dict[str, Any], today: date, zone: Any
) -> dict[str, Any] | None:
    """The round of the Jalali month that just ended, for one company (or the
    holding). Idempotent per (company, month). The caller checks the lock."""
    from hq_api.domain.stars import at, month_window

    # The facts are of the month that just ended; the round is named after the
    # Jalali month it runs in (contract §21.14).
    start_day, end_day = month_window(today - timedelta(days=1))
    key = month_key(today)
    if await tx.scalar(
        "SELECT 1 FROM people.hr_rounds WHERE company_id = :co AND month = :m",
        co=company["id"],
        m=key,
    ):
        return None
    who = await evaluator(tx, company["id"], company["kind"])
    if who is None:
        return None
    start, end = at(start_day, zone), at(end_day, zone)
    employees = await facts(tx, company["id"], start, end)
    eff = await efficiency_of(tx, month_key(start_day))  # the ended month's roll-up
    for e in employees:
        e["efficiency"] = eff.get(e["code"])
    due = datetime.now(UTC) + timedelta(hours=DUE_HOURS)
    row = await tx.one(
        """INSERT INTO people.hr_rounds (company_id, month, evaluator_kind, evaluator_code, due_at, employees)
           VALUES (:co, :m, :ek, :ec, :due, CAST(:emps AS jsonb)) RETURNING *""",
        co=company["id"],
        m=key,
        ek=who[0],
        ec=who[1],
        due=due,
        emps=json.dumps(employees, ensure_ascii=False, default=str),
    )
    w = await W.create(
        tx,
        SERVICE,
        company_id=company["id"],
        company_code=company["code"],
        title=f"ارزیابی ماهانه‌ی HR {key} ({row['ref']})",
        brief=brief(row["ref"], company["code"], key, employees),
        kind="one_off",
        priority="P2",
        assignee_code=who[1],
        due_at=due,
        budget=W.BudgetIn(tokens=100_000),
    )
    teachings = []
    for e in employees:
        if "coach" in e["flags"]:
            ref = await _coach_draft(tx, row["ref"], e, company)
            if ref:
                teachings.append(ref)
    await tx.exec(
        "UPDATE people.hr_rounds SET work_id = :w, teachings = :t, updated_at = now() WHERE id = :id",
        w=w["id"],
        t=teachings,
        id=row["id"],
    )
    await events.emit(
        tx,
        company["code"],
        "hr.round",
        row["ref"],
        {"month": key, "state": "drafting", "flagged": sum(1 for e in employees if e["flags"])},
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=company["id"],
        action="hr.round_open",
        action_class="A1",
        target_kind="hr_round",
        target_ref=row["ref"],
        summary=f"{key}: {len(employees)} employee(s), evaluator {who[1]}",
    )
    return {"ref": row["ref"], "work": w["ref"], "teachings": teachings}


async def _coach_draft(
    tx: Tx, round_ref: str, e: dict[str, Any], company: dict[str, Any]
) -> str | None:
    """A teaching draft for the AI Ops head (academy §18.6), no card."""
    from hq_api.domain import academy as A

    holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    text = (
        f"ارزیابی {round_ref}: {e['code']} ({e['title_fa']}) پرچم coach گرفت "
        f"(امتیاز {e['score']}، ماه قبل {e['score_prev']}). یک آموزش دقیق برای بهتر شدن کارش پیشنهاد بده."
    )
    row = await tx.one(
        """INSERT INTO academy.teachings (company_id, target, source, text_md, created_by_kind, created_by_code)
           VALUES (:co, CAST(:t AS jsonb), 'text', :text, 'service', 'hr') RETURNING id, ref""",
        co=holding["id"],
        t=json.dumps({"kind": "employee", "ref": e["code"]}),
        text=text,
    )
    work = await A.wake(
        tx,
        SERVICE,
        holding_id=holding["id"],
        holding_code=holding["code"],
        suffix="AIOPS-MGR",
        title=f"Draft teaching {row['ref']} ({round_ref})",
        brief=(
            f"HR round {round_ref} flagged {e['code']} of {company['code']} `coach`. Turn it into one "
            "precise proposal with teach.draft. Facts:\n\n" + text
        ),
    )
    if work:
        await tx.exec(
            "UPDATE academy.teachings SET work_id = (SELECT id FROM work.work WHERE ref = :w) WHERE id = :id",
            w=work,
            id=row["id"],
        )
    await events.emit(tx, holding["code"], "academy.teaching", row["ref"], {"status": "drafting"})
    return str(row["ref"])


async def close_rounds(tx: Tx) -> int:
    """A round whose report is in and whose cards are all decided is done."""
    return await tx.exec(
        """UPDATE people.hr_rounds r SET state = 'done', updated_at = now()
           WHERE r.state = 'proposed' AND NOT EXISTS (
               SELECT 1 FROM cartable.decisions d WHERE d.ref = ANY(r.decisions) AND d.status = 'pending')"""
    )


async def on_delivered(tx: Tx, w: dict[str, Any], deliverable_ref: str) -> None:
    """The deliver route's hook: the evaluator's monthly HR report arrived."""
    r = await tx.first(
        "SELECT * FROM people.hr_rounds WHERE work_id = :w AND state = 'drafting' FOR UPDATE",
        w=w["id"],
    )
    if r is None:
        return
    await tx.exec(
        """UPDATE people.hr_rounds SET state = 'proposed', deliverable_ref = :d, updated_at = now()
           WHERE id = :id""",
        d=deliverable_ref,
        id=r["id"],
    )
    await events.emit(
        tx,
        w["company"],
        "hr.round",
        r["ref"],
        {"state": "proposed", "deliverable": deliverable_ref},
    )


# ------------------------------------------------------- evaluation cards --
async def check_proposal(tx: Tx, payload: dict[str, Any], company_id: UUID) -> dict[str, Any]:
    """An `evaluation` card (payload v2): its round, its employee's flags; an
    unflagged employee only with evidence and override_reason (then marked
    `unflagged: true`). Returns the payload as stored."""
    ref = payload.get("round")
    if not ref:
        raise ApiError(422, "validation_failed", fields={"payload.round": "the HR round HR-…"})
    r = await tx.first(
        "SELECT * FROM people.hr_rounds WHERE ref = :r AND company_id = :co", r=ref, co=company_id
    )
    if r is None:
        raise ApiError(422, "validation_failed", fields={"payload.round": "no such round here"})
    emp = next((e for e in r["employees"] if e["code"] == payload["employee"]), None)
    rec = payload["recommendation"]
    flagged = emp is not None and any(f in (emp.get("flags") or []) for f in CARD_FLAGS[rec])
    out = dict(payload)
    out.pop("unflagged", None)
    if not flagged:
        if not payload.get("evidence") or not payload.get("override_reason"):
            raise ApiError(
                422,
                "validation_failed",
                fields={
                    "payload.override_reason": (
                        f"{payload['employee']} has no {'/'.join(CARD_FLAGS[rec])} flag in {ref}: "
                        "evidence and override_reason are required"
                    )
                },
            )
        out["unflagged"] = True
    if rec in ("promote", "demote") and not (payload.get("change") or {}):
        raise ApiError(422, "validation_failed", fields={"payload.change": "what changes"})
    return out


async def on_proposed(tx: Tx, d: dict[str, Any]) -> None:
    ref = (d["payload"] or {}).get("round")
    if ref:
        await tx.exec(
            """UPDATE people.hr_rounds SET decisions = array_append(decisions, :d), updated_at = now()
               WHERE ref = :r AND NOT (:d = ANY(decisions))""",
            d=d["ref"],
            r=ref,
        )


async def _current_estimate(tx: Tx, code: str) -> int:
    v = await tx.scalar(
        """SELECT COALESCE(
               (SELECT (ev.payload->'change'->'quota_estimate_month'->>'tokens')::bigint
                  FROM cartable.decisions ev
                 WHERE ev.kind = 'evaluation' AND ev.status = 'approved' AND ev.payload->>'employee' = :c
                   AND ev.payload->'change'->'quota_estimate_month'->>'tokens' IS NOT NULL
                 ORDER BY ev.decided_at DESC LIMIT 1),
               (SELECT COALESCE((COALESCE(d.amendments->'quota_estimate_month',
                                          d.payload->'quota_estimate_month')->>'tokens')::bigint, 0)
                  FROM core.employees e JOIN cartable.decisions d ON d.id = e.hired_by_decision_id
                 WHERE e.code = :c), 0)""",
        c=code,
    )
    return int(v or 0)


async def check_approval(tx: Tx, d: dict[str, Any], payload: dict[str, Any]) -> None:
    """At the seal, before anything changes: promote / demote under the hire
    checks of §18.11 (an enabled connection offers the model; the envelope
    still fits, else 409 envelope_exceeded)."""
    if payload["recommendation"] not in ("promote", "demote"):
        return
    change = payload.get("change") or {}
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"hire:{d['company_id']}"
    )
    if change.get("model") and not await tx.scalar(
        "SELECT EXISTS (SELECT 1 FROM llm.connections WHERE status = 'enabled' AND models ? :m)",
        m=change["model"],
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.change.model": "no enabled connection offers it"},
        )
    new = (change.get("quota_estimate_month") or {}).get("tokens")
    if new is None:
        return
    env = next((e for e in await hiring.envelopes(tx) if e.company == d["company"]), None)
    if env is None or not env.tokens_month:
        return
    current = await _current_estimate(tx, payload["employee"])
    committed = env.committed_month - current + int(new)
    if committed > env.tokens_month:
        raise ApiError(
            409,
            "envelope_exceeded",
            f"{env.committed_month} committed - {current} + {new} > {env.tokens_month}",
        )


async def apply(tx: Tx, d: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """The effect of an approved `evaluation` card (idempotent by the caller)."""
    emp = await tx.one(
        """SELECT id, code, kind, status, company_id, department_id FROM core.employees
           WHERE code = :c FOR UPDATE""",
        c=p["employee"],
    )
    rec = p["recommendation"]
    result: dict[str, Any] = {"employee": emp["code"], "recommendation": rec}
    if rec in ("promote", "demote"):
        change = p.get("change") or {}
        if change.get("model") or change.get("effort"):
            await tx.exec(
                "SELECT llm.put_assignment('role', :ref, NULL, :model, :effort, :note)",
                ref=f"{d['company']}:{emp['code']}",
                model=change.get("model"),
                effort=change.get("effort"),
                note=f"{rec} by {d['ref']}",
            )
        if change.get("title_fa"):
            await tx.exec(
                "UPDATE core.employees SET title_fa = :t WHERE id = :id",
                t=change["title_fa"],
                id=emp["id"],
            )
        result["change"] = change
    elif rec == "dismiss":
        result.update(
            await org.dismiss(
                tx,
                emp,
                reason=f"{d['ref']}: {d['title']}"[:500],
                transfer_to=p.get("transfer_to"),
            )
        )
    elif rec == "confirm":
        await tx.exec(
            "UPDATE core.employees SET probation_until = NULL WHERE id = :id", id=emp["id"]
        )
    await events.emit(
        tx, d["company"], "employee.updated", emp["code"], {"change": rec, "decision": d["ref"]}
    )
    plain: dict[str, Any] = _plain(result)
    return plain


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, UUID | datetime | Decimal):
        return str(value)
    return value


# ------------------------------------------------------------------ reads --
def render(r: dict[str, Any], company: str) -> dict[str, Any]:
    """HrRound (contract §21.5)."""
    return {
        "id": r["id"],
        "ref": r["ref"],
        "company": company,
        "month": r["month"],
        "state": r["state"],
        "evaluator": {"kind": r["evaluator_kind"], "code": r["evaluator_code"]},
        "due_at": r["due_at"],
        "employees": list(r["employees"]),
        "deliverable_ref": r["deliverable_ref"],
        "decisions": list(r["decisions"] or []),
        "teachings": list(r["teachings"] or []),
    }


# ------------------------------------------------------------------ PR-082 --
@C.check("PR-082")
async def hr_rounds_ran(ctx: C.CheckCtx) -> C.Checked:
    """Last Jalali month's round ran for every active operating company and
    the holding, with its report, and a card for every flagged employee (an
    unflagged card only with evidence and override_reason). Code only."""
    today = ctx.now.date()
    key = month_key(today)  # this Jalali month's round (it opened on the 1st)
    problems: list[C.Problem] = []
    for code, cid in ctx.companies.items():
        r = await ctx.tx.first(
            "SELECT * FROM people.hr_rounds WHERE company_id = :co AND month = :m", co=cid, m=key
        )
        if r is None:
            problems.append(
                C.Problem(
                    cid, code, f"دور ارزیابی {key} اجرا نشد", "No HR round.", f"hr:{key}:none"
                )
            )
            continue
        if r["deliverable_ref"] is None:
            problems.append(
                C.Problem(
                    cid,
                    code,
                    f"گزارش ماهانه‌ی HR {r['ref']} نیامد",
                    "The round has no monthly HR report.",
                    f"hr:{key}:report",
                    [{"kind": "link", "ref": r["ref"], "note": "no deliverable"}],
                )
            )
        cards = await ctx.tx.all(
            "SELECT ref, payload FROM cartable.decisions WHERE kind = 'evaluation' AND ref = ANY(:refs)",
            refs=list(r["decisions"] or []),
        )
        carded = {c["payload"].get("employee") for c in cards}
        missing = [
            e["code"]
            for e in r["employees"]
            if set(e.get("flags") or []) - {"coach"} and e["code"] not in carded
        ]
        if missing:
            problems.append(
                C.Problem(
                    cid,
                    code,
                    f"کارت ارزیابی برای پرچم‌خورده‌ها در {r['ref']} نیست",
                    "Flagged without a card: " + ", ".join(missing[:30]),
                    f"hr:{key}:cards",
                    [{"kind": "link", "ref": r["ref"], "note": ", ".join(missing[:10])}],
                )
            )
        bad = [
            c["ref"]
            for c in cards
            if c["payload"].get("unflagged")
            and not (c["payload"].get("override_reason") and c["payload"].get("evidence"))
        ]
        if bad:
            problems.append(
                C.Problem(
                    cid,
                    code,
                    f"کارت بی‌پرچم بدون شاهد در {r['ref']}",
                    "Unflagged cards without evidence or override_reason: " + ", ".join(bad),
                    f"hr:{key}:unflagged",
                )
            )
    return C.Checked(problems, ctx.companies)
