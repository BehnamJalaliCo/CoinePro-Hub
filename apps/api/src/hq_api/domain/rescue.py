"""Referral rescue (prompt 10 §3.4, contract §19.2): a customer who signed up
without our referral is brought back, by rule and sealed template only.

    open        a referral.check that answers "not our invitee" (support), or
                a product's `referral_failed` event (intake.events; applied
                by the follow-up job, idempotently); one open case per
                company, exchange and subject
    follow-ups  hourly (hq-rescue-follow-ups), behind hq_api.domain.gate:
                under the company's ACTIVE `rescue` rule only, through the
                §7 sender (template_send.send_template: sealed template,
                opt-outs, quiet hours, caps, the guard); the rescue
                specialist reviews cases and proposes templates but sends
                nothing
    close       a later check that says "our invitee" -> rescued; 30 days
                without a result or the rule's max_follow_ups -> lost; the
                customer's opt-out -> opted_out
    rate        rescued / (rescued + lost) over a period (mystery cases never
                count)

referral.check {company, exchange, uid} answers {invitee, meets_minimum}
only, never a balance: the connector reduces the answer in egress
(invite/user/info). At most REFERRAL_CHECKS_PER_HOUR calls a company, an
answer reused for REFERRAL_CHECK_CACHE_S (growth.referral_checks keeps both:
cached rows do not count against the cap).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate, template_send
from hq_common import pseudonym

LOST_AFTER = timedelta(days=30)
DEFAULT_AFTER_HOURS = 48
DEFAULT_MAX_FOLLOW_UPS = 3
OPEN = ("open", "contacted")
CLOSED = ("rescued", "lost", "opted_out")


def subject_of(hub: Any, company_id: UUID | str, exchange: str, uid: str) -> str:
    """The same person has one subject across the team list, referral.check
    and the products' events (channel uid:<exchange>)."""
    return pseudonym.subject(
        hub.secrets.support_pseudonym_key, str(company_id), f"uid:{exchange}", uid
    )


async def add_step(
    tx: Tx,
    case: dict[str, Any],
    kind: str,
    result_fa: str,
    *,
    by_kind: str,
    by_code: str,
    template: str | None = None,
) -> None:
    await tx.exec(
        """INSERT INTO growth.rescue_steps (case_id, company_id, kind, template, result_fa, by_kind, by_code)
           VALUES (:c, :co, :k, :t, :r, :bk, :bc)""",
        c=case["id"],
        co=case["company_id"],
        k=kind,
        t=template,
        r=result_fa[:1000],
        bk=by_kind,
        bc=by_code[:64],
    )


async def _emit(tx: Tx, company: str, case: dict[str, Any], change: str) -> None:
    await events.emit(
        tx, company, "rescue.updated", case["ref"], {"state": case["state"], "change": change}
    )


async def open_case(
    tx: Tx,
    *,
    company_id: UUID | str,
    company: str,
    source: str,
    exchange: str,
    subject: str,
    conversation_id: UUID | None = None,
    mystery: bool = False,
    by_kind: str = "rule",
    by_code: str = "rescue",
    note_fa: str = "دعوت‌شده‌ی ما نیست.",
) -> tuple[dict[str, Any], bool]:
    """(the open case, created?): a second "not ours" adds a step to it."""
    row = await tx.first(
        """INSERT INTO growth.rescue_cases (company_id, source, conversation_id, exchange, subject, mystery)
           VALUES (:co, :src, :conv, :ex, :s, :m)
           ON CONFLICT (company_id, exchange, subject) WHERE state IN ('open', 'contacted') DO NOTHING
           RETURNING *""",
        co=company_id,
        src=source,
        conv=conversation_id,
        ex=exchange,
        s=subject,
        m=mystery,
    )
    created = row is not None
    if row is None:
        row = await tx.one(
            """SELECT * FROM growth.rescue_cases WHERE company_id = :co AND exchange = :ex
                 AND subject = :s AND state IN ('open', 'contacted')""",
            co=company_id,
            ex=exchange,
            s=subject,
        )
    await add_step(tx, row, "check", note_fa, by_kind=by_kind, by_code=by_code)
    if created:
        if conversation_id is not None:
            await tx.exec(
                """UPDATE support.conversations SET rescue_case_id = :c, updated_at = now()
                   WHERE id = :id AND rescue_case_id IS NULL""",
                id=conversation_id,
                c=row["id"],
            )
        await _emit(tx, company, row, "opened")
    return row, created


async def close_case(
    tx: Tx,
    case: dict[str, Any],
    company: str,
    state: str,
    reason: str,
    result_fa: str,
    *,
    by_kind: str = "rule",
    by_code: str = "rescue",
) -> dict[str, Any]:
    assert state in CLOSED
    row = await tx.one(
        """UPDATE growth.rescue_cases SET state = :st, close_reason = :r, closed_at = now(),
               rescued_at = CASE WHEN :st = 'rescued' THEN now() END, next_follow_up_at = NULL,
               updated_at = now()
           WHERE id = :id RETURNING *""",
        id=case["id"],
        st=state,
        r=reason[:60],
    )
    await add_step(tx, row, "check" if state == "rescued" else "note", result_fa, by_kind=by_kind,
                by_code=by_code)  # fmt: skip
    await _emit(tx, company, row, state)
    return row


async def apply_check(
    tx: Tx,
    *,
    company_id: UUID | str,
    company: str,
    exchange: str,
    subject: str,
    invitee: bool,
    conversation_id: UUID | None,
    mystery: bool,
    opens: bool,
    by_code: str,
) -> dict[str, Any] | None:
    """What a referral.check answer does to the cases: "ours" rescues the
    open one; "not ours" opens one (in a conversation) or notes the check."""
    case = await tx.first(
        """SELECT * FROM growth.rescue_cases WHERE company_id = :co AND exchange = :ex AND subject = :s
             AND state IN ('open', 'contacted') FOR UPDATE""",
        co=company_id,
        ex=exchange,
        s=subject,
    )
    if invitee:
        if case is None:
            return None
        return await close_case(tx, case, company, "rescued", "invitee",
                                "چک بعدی: حالا دعوت‌شده‌ی ما است.", by_kind="agent", by_code=by_code)  # fmt: skip
    if case is not None:
        await add_step(
            tx, case, "check", "هنوز دعوت‌شده‌ی ما نیست.", by_kind="agent", by_code=by_code
        )
        return case
    if not opens:
        return None
    row, _ = await open_case(
        tx,
        company_id=company_id,
        company=company,
        source="support",
        exchange=exchange,
        subject=subject,
        conversation_id=conversation_id,
        mystery=mystery,
        by_kind="agent",
        by_code=by_code,
    )
    return row


async def conversation_of(
    tx: Tx, company_id: UUID | str, exchange: str, uid: str
) -> dict[str, Any] | None:
    """The open conversation of the customer who gave this UID (support
    keeps the UID on its customer row, the only place a raw UID lives)."""
    return await tx.first(
        """SELECT c.id, c.ref, c.mystery FROM support.conversations c
           JOIN support.customers u ON u.id = c.customer_id
           WHERE c.company_id = :co AND c.state <> 'closed'
             AND u.uids @> CAST(:probe AS jsonb)
           ORDER BY c.last_message_at DESC LIMIT 1""",
        co=company_id,
        probe=json.dumps([{"exchange": exchange, "uid": uid}]),
    )


async def cached_check(
    tx: Tx, company_id: UUID | str, exchange: str, subject: str, cache_s: int
) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT invitee, meets_minimum FROM growth.referral_checks
           WHERE company_id = :co AND exchange = :ex AND subject = :s AND ok AND NOT mystery
             AND at > now() - make_interval(secs => :ttl)
           ORDER BY at DESC LIMIT 1""",
        co=company_id,
        ex=exchange,
        s=subject,
        ttl=cache_s,
    )


async def checks_last_hour(tx: Tx, company_id: UUID | str) -> int:
    return int(
        await tx.scalar(
            """SELECT count(*) FROM growth.referral_checks
               WHERE company_id = :co AND NOT cached AND NOT mystery AND at > now() - interval '1 hour'""",
            co=company_id,
        )
    )


async def record_check(
    tx: Tx,
    *,
    company_id: UUID | str,
    exchange: str,
    subject: str,
    ok: bool,
    invitee: bool | None,
    meets_minimum: bool | None,
    cached: bool,
    error_code: str | None,
    conversation_id: UUID | None,
    rescue_case_id: UUID | None,
    mystery: bool,
    by_kind: str,
    by_code: str,
) -> None:
    await tx.exec(
        """INSERT INTO growth.referral_checks (company_id, exchange, subject, ok, invitee, meets_minimum,
               cached, error_code, conversation_id, rescue_case_id, mystery, by_kind, by_code)
           VALUES (:co, :ex, :s, :ok, :inv, :mm, :c, :e, :conv, :rc, :m, :bk, :bc)""",
        co=company_id,
        ex=exchange,
        s=subject,
        ok=ok,
        inv=invitee if ok else None,
        mm=meets_minimum if ok else None,
        c=cached,
        e=error_code,
        conv=conversation_id,
        rc=rescue_case_id,
        m=mystery,
        bk=by_kind,
        bc=by_code[:64],
    )


# ------------------------------------------------------------ follow-ups --
async def apply_product_failures(tx: Tx, company_id: UUID, company: str) -> int:
    """`referral_failed` events from a product (intake) open cases, once each."""
    rows = await tx.all(
        """SELECT id, subject, data FROM intake.events
           WHERE company_id = :co AND kind = 'referral_failed' AND state = 'accepted'
             AND subject IS NOT NULL
           ORDER BY received_at LIMIT 200 FOR UPDATE SKIP LOCKED""",
        co=company_id,
    )
    n = 0
    for r in rows:
        data = r["data"] if isinstance(r["data"], dict) else {}
        exchange = str(data.get("exchange") or "lbank")[:30].lower()
        if not exchange.replace("_", "").replace("-", "").isalnum() or not exchange[:1].isalpha():
            exchange = "lbank"
        _, created = await open_case(
            tx, company_id=company_id, company=company, source="product", exchange=exchange,
            subject=r["subject"], note_fa="محصول گزارش داد: ثبت‌نام بی‌رفرال ما.",
        )  # fmt: skip
        n += 1 if created else 0
        await tx.exec(
            "UPDATE intake.events SET state = 'applied', applied_at = now() WHERE id = :id",
            id=r["id"],
        )
    return n


async def _rescue_rule(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT * FROM growth.rules WHERE company_id = :co AND kind = 'rescue' AND status = 'active'
           ORDER BY version DESC LIMIT 1""",
        co=company_id,
    )


def _limit(rule: dict[str, Any] | None, key: str, default: int) -> int:
    if rule is None:
        return default
    src = rule["limits"] if key == "max_follow_ups" else rule["trigger"]
    value = (src or {}).get(key)
    return int(value) if isinstance(value, int) and value > 0 else default


async def follow_up_company(
    tx: Tx, hub: Any, company_id: UUID, company: str, now: datetime | None = None
) -> dict[str, Any]:
    """One company's due cases (its caller has asked the gate)."""
    now = now or datetime.now(UTC)
    opened = await apply_product_failures(tx, company_id, company)
    rule = await _rescue_rule(tx, company_id)
    max_n = _limit(rule, "max_follow_ups", DEFAULT_MAX_FOLLOW_UPS)
    after = timedelta(hours=_limit(rule, "after_hours", DEFAULT_AFTER_HOURS))
    cases = await tx.all(
        """SELECT * FROM growth.rescue_cases
           WHERE company_id = :co AND state IN ('open', 'contacted')
             AND (next_follow_up_at IS NULL OR next_follow_up_at <= :now)
           ORDER BY opened_at LIMIT 200 FOR UPDATE SKIP LOCKED""",
        co=company_id,
        now=now,
    )
    out: dict[str, Any] = {
        "company": company, "opened": opened, "sent": 0, "lost": 0, "opted_out": 0, "waiting": 0,
    }  # fmt: skip
    for case in cases:
        if await tx.scalar(
            "SELECT 1 FROM growth.opt_outs WHERE company_id = :co AND subject = :s",
            co=company_id,
            s=case["subject"],
        ):
            await close_case(
                tx, case, company, "opted_out", "opted_out", "مشتری لغو کرد؛ دیگر پیامی نمیرود."
            )
            out["opted_out"] += 1
            continue
        if case["opened_at"] <= now - LOST_AFTER or case["follow_ups"] >= max_n:
            why = "30_days" if case["opened_at"] <= now - LOST_AFTER else "max_follow_ups"
            await close_case(tx, case, company, "lost", why,
                             "۳۰ روز بی‌نتیجه." if why == "30_days" else "پیگیری‌ها تمام شد.")  # fmt: skip
            out["lost"] += 1
            continue
        if rule is None or case["mystery"]:
            # No sealed rescue rule: nothing is ever sent (the case waits).
            await tx.exec(
                "UPDATE growth.rescue_cases SET next_follow_up_at = :t WHERE id = :id",
                id=case["id"],
                t=now + timedelta(hours=6),
            )
            out["waiting"] += 1
            continue
        n = case["follow_ups"] + 1
        sent = await template_send.send_template(
            tx,
            hub,
            company_id=company_id,
            kind="rescue",
            subject=case["subject"],
            dedupe_key=f"rescue:{case['ref']}:{n}",
            rescue_case_id=case["id"],
        )
        if sent["status"] == "sent":
            row = await tx.one(
                """UPDATE growth.rescue_cases SET state = 'contacted', follow_ups = :n, last_contact_at = :now,
                       next_follow_up_at = :next, updated_at = now() WHERE id = :id RETURNING *""",
                id=case["id"],
                n=n,
                now=now,
                next=now + after,
            )
            await add_step(tx, row, "message" if n == 1 else "follow_up", f"پیگیری {n} فرستاده شد.",
                        by_kind="rule", by_code=str(rule["ref"]), template=sent.get("template"))  # fmt: skip
            await _emit(tx, company, row, "contacted")
            out["sent"] += 1
        elif sent["status"] == "opted_out":
            await close_case(tx, case, company, "opted_out", "opted_out", "مشتری لغو کرده است.")
            out["opted_out"] += 1
        else:  # quiet hours, a cap, a template not sealed yet, no sender: later
            await tx.exec(
                "UPDATE growth.rescue_cases SET next_follow_up_at = :t WHERE id = :id",
                id=case["id"],
                t=now + timedelta(hours=1),
            )
            out["waiting"] += 1
    return out


async def follow_ups(hub: Any, txf: Any, now: datetime | None = None) -> dict[str, Any]:
    """The hourly job: nothing at all while the holding is locked."""
    async with txf() as tx:
        lock = await gate.holding_lock(tx)
        if lock is not None:
            return gate.skipped(lock)
        companies = await tx.all(
            """SELECT DISTINCT c.id, c.code FROM core.companies c
               WHERE EXISTS (SELECT 1 FROM growth.rescue_cases r
                             WHERE r.company_id = c.id AND r.state IN ('open', 'contacted'))
                  OR EXISTS (SELECT 1 FROM intake.events e WHERE e.company_id = c.id
                             AND e.kind = 'referral_failed' AND e.state = 'accepted')"""
        )
    done: list[dict[str, Any]] = []
    skipped: list[str] = []
    for co in companies:
        async with txf() as tx:
            lock = await gate.automation_lock(tx, co["id"])
            if lock is not None:
                skipped.append(co["code"])
                continue
            done.append(await follow_up_company(tx, hub, co["id"], co["code"], now))
    return {"companies": done, "skipped": skipped}


# ---------------------------------------------------------------- reading --
async def rate(tx: Tx, company_id: UUID | str, start: date, end: date) -> dict[str, Any]:
    """rescued / (rescued + lost) of the cases closed in [start, end]."""
    row = await tx.one(
        """SELECT count(*) FILTER (WHERE state = 'rescued') AS rescued,
                  count(*) FILTER (WHERE state = 'lost') AS lost,
                  count(*) FILTER (WHERE state IN ('open', 'contacted')) AS open
           FROM growth.rescue_cases
           WHERE company_id = :co AND NOT mystery
             AND (state IN ('open', 'contacted') OR closed_at::date BETWEEN :s AND :e)""",
        co=company_id,
        s=start,
        e=end,
    )
    rescued, lost = int(row["rescued"]), int(row["lost"])
    return {
        "rescued": rescued,
        "lost": lost,
        "open": int(row["open"]),
        "rate": rescued / (rescued + lost) if rescued + lost else None,
    }


async def case_out(tx: Tx, r: dict[str, Any], *, steps: bool = True) -> dict[str, Any]:
    conv = None
    if r.get("conversation_id"):
        conv = await tx.scalar(
            "SELECT ref FROM support.conversations WHERE id = :id", id=r["conversation_id"]
        )
    out: dict[str, Any] = {
        "id": str(r["id"]),
        "ref": r["ref"],
        "company": r["company"],
        "source": r["source"],
        "conversation": conv,
        "exchange": r["exchange"],
        "subject": r["subject"],
        "state": r["state"],
        "steps": [],
        "opened_at": r["opened_at"],
        "rescued_at": r["rescued_at"],
        "closed_at": r["closed_at"],
    }
    if steps:
        out["steps"] = [
            {
                "at": s["at"],
                "kind": s["kind"],
                "template": s["template"],
                "result_fa": s["result_fa"],
            }
            for s in await tx.all(
                "SELECT at, kind, template, result_fa FROM growth.rescue_steps WHERE case_id = :c ORDER BY at, id",
                c=r["id"],
            )
        ]
    return out
