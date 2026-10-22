"""Referral rescue (prompt 10 §3.4, contract §19.2): a customer who signed up
without our referral is brought back, by rule and sealed template only.

    open        a referral.check that answers "not our invitee" (support), or
                a product's `referral_failed` event (intake.events: applied
                as it arrives by intake.APPLIERS, domain/product_events.py;
                the follow-up job catches up any left `accepted`); one open
                case per company, exchange and subject
    follow-ups  hourly (hq-rescue-follow-ups), behind hq_api.domain.gate:
                under the company's ACTIVE `rescue` rule only, through the
                §7 sender (growth.send_template: sealed template, opt-outs,
                quiet hours, caps, a live channel, the guard with the safety
                line); the message it queues goes out through desk.send
                (gated again); the rescue specialist reviews cases and
                proposes templates but sends nothing
    close       a later check that says "our invitee" (or the product's own
                `referral_verified`) -> rescued; 30 days without a result or
                the rule's max_follow_ups -> lost; the customer's opt-out ->
                opted_out
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
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate, growth
from hq_common import pseudonym

LOST_AFTER = timedelta(days=30)
DEFAULT_AFTER_HOURS = 48
DEFAULT_MAX_FOLLOW_UPS = 3
OPEN = ("open", "contacted")
CLOSED = ("rescued", "lost", "opted_out")
NO_CHANNEL_RETRY = timedelta(hours=24)  # a customer no live channel reaches yet
EXCHANGE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
MAX_UIDS = 10  # UIDs kept on one support customer (support.customers.uids)
CONVERSATION_REF = re.compile(r"\bSC-[0-9]{6,}\b")


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
        if case["conversation_id"] is None and conversation_id is not None:
            # A product's case meets its customer in support: follow-ups can reach them now.
            case = await tx.one(
                """UPDATE growth.rescue_cases SET conversation_id = :conv, updated_at = now()
                   WHERE id = :id RETURNING *""",
                id=case["id"],
                conv=conversation_id,
            )
            await tx.exec(
                """UPDATE support.conversations SET rescue_case_id = :c, updated_at = now()
                   WHERE id = :id AND rescue_case_id IS NULL""",
                id=conversation_id,
                c=case["id"],
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


async def conversation_of_run(
    tx: Tx, company_id: UUID | str, run_id: str | None
) -> dict[str, Any] | None:
    """The open conversation a support agent's run is answering: its work
    item is the one desk.wake_agent made for that conversation (§4.5: the
    customer says they registered already and gives a UID)."""
    if not run_id:
        return None
    title = await tx.scalar(
        """SELECT w.title FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE r.id = CAST(:id AS uuid) AND r.company_id = :co""",
        id=run_id,
        co=company_id,
    )
    m = CONVERSATION_REF.search(str(title or ""))
    if m is None:
        return None
    return await tx.first(
        """SELECT id, ref, mystery, customer_id FROM support.conversations
           WHERE ref = :ref AND company_id = :co AND state <> 'closed'""",
        ref=m.group(0),
        co=company_id,
    )


async def link_uid(tx: Tx, customer_id: UUID, exchange: str, uid: str) -> None:
    """The UID a customer gave in a conversation, kept on their support
    customer row (the one place a raw UID lives, prompt 10 §1.2), so the
    next check finds the conversation and the guard knows the UID is theirs."""
    await tx.exec(
        """UPDATE support.customers
              SET uids = uids || jsonb_build_array(jsonb_build_object('exchange', CAST(:ex AS text),
                                                                      'uid', CAST(:uid AS text)))
            WHERE id = :id AND NOT uids @> CAST(:probe AS jsonb)
              AND jsonb_array_length(uids) < :cap""",
        id=customer_id,
        ex=exchange,
        uid=uid,
        probe=json.dumps([{"exchange": exchange, "uid": uid}]),
        cap=MAX_UIDS,
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


# -------------------------------------------------------- product events --
def event_exchange(ev: dict[str, Any]) -> str | None:
    """The exchange of a product event (CR-009/010: data.exchange). Its
    subject is the UID's pseudonym under `uid:<exchange>` only then
    (routes/intake.py), so without one no case can match a check."""
    raw = ev.get("data")
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}
    exchange = str(data.get("exchange") or "").lower()
    return exchange if exchange.isalnum() and EXCHANGE.match(exchange) else None


async def apply_referral_event(
    tx: Tx, company_id: UUID, company: str, ev: dict[str, Any]
) -> tuple[str, bool]:
    """A product's `referral_failed` opens a case (once); its
    `referral_verified` rescues the open one. -> (the event's state, a case
    opened?). An event without an exchange or a subject is `ignored`."""
    exchange = event_exchange(ev)
    if exchange is None or not ev.get("subject"):
        return "ignored", False
    if ev["kind"] == "referral_failed":
        _, created = await open_case(
            tx, company_id=company_id, company=company, source="product", exchange=exchange,
            subject=ev["subject"], note_fa="محصول گزارش داد: ثبت‌نام بی‌رفرال ما.",
        )  # fmt: skip
        return "applied", created
    case = await tx.first(
        """SELECT * FROM growth.rescue_cases WHERE company_id = :co AND exchange = :ex AND subject = :s
             AND state IN ('open', 'contacted') FOR UPDATE""",
        co=company_id,
        ex=exchange,
        s=ev["subject"],
    )
    if case is not None:
        await close_case(tx, case, company, "rescued", "product_verified",
                         "محصول تأیید کرد: حالا زیر رفرال ما است.", by_kind="rule", by_code="product")  # fmt: skip
    return "applied", False


# ------------------------------------------------------------ follow-ups --
async def apply_product_failures(tx: Tx, company_id: UUID, company: str) -> int:
    """The catch-up: product referral events still `accepted` (intake applies
    them as they arrive) open or rescue their cases, once each."""
    rows = await tx.all(
        """SELECT id, kind, subject, data FROM intake.events
           WHERE company_id = :co AND kind IN ('referral_failed', 'referral_verified')
             AND state = 'accepted'
           ORDER BY received_at LIMIT 200 FOR UPDATE SKIP LOCKED""",
        co=company_id,
    )
    n = 0
    for r in rows:
        state, created = await apply_referral_event(tx, company_id, company, dict(r))
        n += 1 if created else 0
        await tx.exec(
            "UPDATE intake.events SET state = :st, applied_at = now() WHERE id = :id",
            id=r["id"],
            st=state,
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
        "no_channel": 0, "blocked": 0, "queued": [],
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
        # The customer is the case's conversation (a case's own subject is
        # the UID's pseudonym, which reaches no channel by itself).
        sent = await growth.send_template(
            tx, hub, company_id=company_id, purpose="rescue", dedupe_key=f"rescue:{case['ref']}:{n}",
            conversation_id=case["conversation_id"], subject=case["subject"],
            rule_ref=str(rule["ref"]), rescue_case_id=case["id"], follow_up=n, now=now,
        )  # fmt: skip
        status, reason = sent["status"], sent.get("reason")
        if status in ("queued", "sent") and sent.get("message_id"):
            if status == "queued":
                out["queued"].append(sent["message_id"])  # desk.send, after the commit
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
        elif reason == "opted_out" or status == "opted_out":
            await close_case(tx, case, company, "opted_out", "opted_out", "مشتری لغو کرده است.")
            out["opted_out"] += 1
        else:
            # no_channel (no conversation or no live channel yet) and blocked
            # (the guard refused the sealed template: the owner fixes it) wait
            # a day; quiet hours and the daily cap (held, the sweep retries),
            # a rule or template not sealed, a lock: an hour.
            later = NO_CHANNEL_RETRY if status in ("no_channel", "blocked") else timedelta(hours=1)
            await tx.exec(
                "UPDATE growth.rescue_cases SET next_follow_up_at = :t WHERE id = :id",
                id=case["id"],
                t=now + later,
            )
            out[status if status in ("no_channel", "blocked") else "waiting"] += 1
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
    from hq_api.domain import desk  # the one sender of a queued message

    done: list[dict[str, Any]] = []
    skipped: list[str] = []
    for co in companies:
        async with txf() as tx:
            lock = await gate.automation_lock(tx, co["id"])
            if lock is not None:
                skipped.append(co["code"])
                continue
            result = await follow_up_company(tx, hub, co["id"], co["code"], now)
        sends = []
        for mid in result.pop("queued"):
            async with txf() as tx:  # desk.send asks the gate again
                sends.append(await desk.send(tx, hub, mid))
        done.append({**result, "sends": sends})
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
