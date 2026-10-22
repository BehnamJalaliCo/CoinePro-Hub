"""The revenue radar (prompt 10 §2, contract §19.1): affiliate accounts, the
daily pulls, RevenueDay, the summary against the Token Treasury, the alerts.

    accounts      revenue.accounts maps {company, exchange} onto an adapter and
                  a §18.13 service account whose policy is a signer
                  (inject.kind "signer", signer "lbank-v2"); the key stays in
                  OpenBao and reaches egress only (affiliate.py)
    pulls         revenue.pulls: scheduled (07:00 Tehran, the day before),
                  retry (11:00 and 18:00, days still incomplete), manual (the
                  owner, at most REVENUE_PULL_MAX_DAYS, Idempotency-Key) and
                  backfill (the first run: REVENUE_BACKFILL_DAYS, slowly: the
                  exchange's rate limit is egress's bucket). Every pull asks
                  hq_api.domain.gate first: while the holding (or the
                  company) is locked it is recorded `skipped` and nothing
                  leaves the hub
    days          revenue.days (RevenueDay): per coin, valued in USDT at the
                  day's close (`price_source`); `complete` only when every
                  page of every endpoint answered
    invitees      revenue.invitees: the subject (pseudonym of `uid:<exchange>`)
                  and meets_minimum only; the UID is dropped at once
    summary       RevenueSummary: token_cost_usd from the Token Treasury
                  (llm.calls, never an agent's report); net_usd = usdt - cost
                  (USDT taken as USD)
    alerts        one per incident (revenue.alerts.incident_key), `report`
                  level, to the company's CEO (a system line in its thread)
                  and the owner's digest: commission below 60% of the
                  trailing 28-day median of the same weekday; two failed
                  pulls in a row (and a task for the platform SRE); a day
                  still incomplete 36 h after its settlement
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import affiliate as A
from hq_api.domain import decisions as D
from hq_api.domain import funnel as F
from hq_api.domain import gate, notify
from hq_api.domain import revenue_checks as _pr103  # noqa: F401 - registers PR-103's check
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_common import pseudonym

log = logging.getLogger("hq_api.revenue")
SYSTEM = audit.SYSTEM
DROP_SHARE = Decimal("0.6")
PULL_KINDS = ("scheduled", "retry", "manual", "backfill")
SRE_ROLES = ("hub_platform_sre",)
RETRY_DAYS = 3  # how far back a retry looks for incomplete days
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBER = re.compile(r"(?<![\d.])(\d{1,12}(?:[.,]\d{1,8})?)(?![\d.])")


# ----------------------------------------------------------------- policy --
async def min_balance(tx: Tx, company_id: UUID | str) -> Decimal | None:
    """The company's ONE minimum balance: the first number of its approved,
    current `policy` article with key vip.min_balance (owner-sealed). No
    sealed article, no number: meets_minimum stays unknown (never guessed)."""
    row = await tx.first(
        """SELECT answer_md FROM support.kb_articles
           WHERE company_id = :co AND kind = 'policy' AND key = 'vip.min_balance'
             AND status = 'approved' AND expires_at > now()
           ORDER BY version DESC LIMIT 1""",
        co=company_id,
    )
    if row is None:
        return None
    text = str(row["answer_md"]).translate(_DIGITS).replace("٬", "").replace("٫", ".")
    m = _NUMBER.search(text.replace(",", "") if re.search(r"\d,\d{3}", text) else text)
    return Decimal(m.group(1).replace(",", ".")) if m else None


# --------------------------------------------------------------- accounts --
async def accounts(tx: Tx, company_id: UUID | str | None = None) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT a.*, c.code AS company FROM revenue.accounts a
           JOIN core.companies c ON c.id = a.company_id
           WHERE CAST(:co AS uuid) IS NULL OR a.company_id = CAST(:co AS uuid)
           ORDER BY c.code, a.exchange""",
        co=str(company_id) if company_id else None,
    )


async def account(tx: Tx, account_id: UUID | str) -> dict[str, Any]:
    return await tx.one(
        """SELECT a.*, c.code AS company FROM revenue.accounts a
           JOIN core.companies c ON c.id = a.company_id WHERE a.id = CAST(:id AS uuid)""",
        id=str(account_id),
    )


def account_out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "company": r["company"],
        "exchange": r["exchange"],
        "adapter": r["adapter"],
        "service_account": r["service_account"],
        "title_fa": r["title_fa"],
        "status": r["status"],
        "last_pull_at": r["last_pull_at"],
        "last_error": r["last_error"],
        "version": r["version"],
    }


async def check_service_account(tx: Tx, adapter: str, key: str, company: str) -> None:
    """The service account must exist, be a signer of the adapter's kind and
    be usable by the company (422 otherwise)."""
    spec = A.ADAPTERS.get(adapter)
    if spec is None:
        raise ApiError(422, "validation_failed", fields={"adapter": "unknown adapter"})
    row = await tx.first("SELECT companies, policy FROM tools.accounts WHERE key = :k", k=key)
    if row is None:
        raise ApiError(422, "validation_failed", fields={"service_account": "no such account"})
    inject = (row["policy"] or {}).get("inject") or {}
    if inject.get("kind") != "signer" or inject.get("signer") != spec.signer:
        raise ApiError(
            422,
            "validation_failed",
            fields={
                "service_account": f"its policy must be inject.kind signer, signer {spec.signer}"
            },
        )
    if row["companies"] is not None and company not in row["companies"]:
        raise ApiError(422, "validation_failed", fields={"service_account": "not for this company"})


# ------------------------------------------------------------------ pulls --
async def create_pull(
    tx: Tx,
    acct: dict[str, Any],
    *,
    kind: str,
    from_day: date,
    to_day: date,
    by_kind: str = "service",
    by_code: str = "revenue",
    state: str = "queued",
    skipped_reason: str | None = None,
) -> dict[str, Any]:
    return await tx.one(
        """INSERT INTO revenue.pulls (company_id, account_id, kind, from_day, to_day, state,
               skipped_reason, requested_by_kind, requested_by_code, finished_at)
           VALUES (:co, :a, :k, :f, :t, :st, :sr, :bk, :bc,
                   CASE WHEN :st = 'skipped' THEN now() END)
           RETURNING *""",
        co=acct["company_id"],
        a=acct["id"],
        k=kind,
        f=from_day,
        t=to_day,
        st=state,
        sr=skipped_reason,
        bk=by_kind,
        bc=by_code[:64],
    )


def pull_out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "account": str(r["account_id"]),
        "kind": r["kind"],
        "from": r["from_day"].isoformat(),
        "to": r["to_day"].isoformat(),
        "state": r["state"],
        "skipped_reason": r["skipped_reason"],
        "days_complete": r["days_complete"],
        "days_incomplete": r["days_incomplete"],
        "error_code": r["error_code"],
        "created_at": r["created_at"],
        "finished_at": r["finished_at"],
    }


async def run_pull(hub: Any, txf: Any, conn: A.Connector, pull_id: UUID | str) -> dict[str, Any]:
    """Carry out one queued pull, a day at a time (each day in its own short
    transaction, never one held across a network call)."""
    async with txf() as tx:
        p = await tx.first(
            "SELECT * FROM revenue.pulls WHERE id = CAST(:id AS uuid) FOR UPDATE", id=str(pull_id)
        )
        if p is None or p["state"] != "queued":
            return {"pull": str(pull_id), "skipped": True, "reason": "not_queued"}
        lock = await gate.automation_lock(tx, p["company_id"])
        if lock is not None:
            await tx.exec(
                """UPDATE revenue.pulls SET state = 'skipped', skipped_reason = :r, finished_at = now()
                   WHERE id = :id""",
                id=p["id"],
                r=gate.REASONS.get(lock, lock),
            )
            return gate.skipped(lock, pull=str(p["id"]))
        acct = await account(tx, p["account_id"])
        if not hub.secrets.support_pseudonym_key:  # no subject can be made: nothing is pulled
            await tx.exec(
                """UPDATE revenue.pulls SET state = 'failed', error_code = 'not_ready',
                       finished_at = now() WHERE id = :id""",
                id=p["id"],
            )
            return {"pull": str(p["id"]), "state": "failed", "error_code": "not_ready"}
        floor = await min_balance(tx, acct["company_id"])
        await tx.exec(
            "UPDATE revenue.pulls SET state = 'running', started_at = now() WHERE id = :id",
            id=p["id"],
        )
    complete = incomplete = requests = 0
    errors: list[str] = []
    answered_any = False
    stopped: str | None = None  # the gate closed while the pull ran
    day = p["from_day"]
    while day <= p["to_day"]:
        async with txf() as tx:  # the lock is asked again before every day
            lock = await gate.automation_lock(tx, acct["company_id"])
        if lock is not None:
            stopped = gate.REASONS.get(lock, lock)
            break
        try:
            got = await A.pull_day(
                conn,
                company=acct["company"],
                exchange=acct["exchange"],
                adapter=acct["adapter"],
                day=day,
                min_balance=str(floor) if floor is not None else None,
            )
        except A.ConnectorError as e:
            errors.append(e.code)
            incomplete += 1
            day += timedelta(days=1)
            continue
        requests += got.requests
        if got.answered:
            answered_any = True
            async with txf() as tx:
                await store_day(tx, hub, acct, got, floor)
            complete += 1 if got.complete else 0
            incomplete += 0 if got.complete else 1
        else:
            incomplete += 1
            errors.extend(g["error"] for g in got.gaps[:1])
        day += timedelta(days=1)
    if stopped is not None:
        state = "incomplete" if answered_any else "skipped"
    else:
        state = "failed" if not answered_any else ("ok" if incomplete == 0 else "incomplete")
    error_code = (errors[0] if errors else None) if state not in ("ok", "skipped") else None
    if stopped is not None and not answered_any:  # nothing left the hub: no failure, no alert
        async with txf() as tx:
            await tx.exec(
                """UPDATE revenue.pulls SET state = 'skipped', skipped_reason = :r, finished_at = now()
                   WHERE id = :id""",
                id=p["id"],
                r=stopped,
            )
        return gate.skipped(lock or "holding", pull=str(p["id"]))
    async with txf() as tx:
        await tx.exec(
            """UPDATE revenue.pulls SET state = :st, days_complete = :c, days_incomplete = :i,
                   requests = :n, error_code = :e, finished_at = now() WHERE id = :id""",
            id=p["id"],
            st=state,
            c=complete,
            i=incomplete,
            n=requests,
            e=error_code,
        )
        failures = 0 if state != "failed" else int(acct["failures_in_row"]) + 1
        await tx.exec(
            """UPDATE revenue.accounts SET status = :st, last_pull_at = now(), last_error = :e,
                   failures_in_row = :f, updated_at = now(),
                   backfilled_at = CASE WHEN :k = 'backfill' AND :st2 <> 'failed' THEN now()
                                        ELSE backfilled_at END
               WHERE id = :id""",
            id=acct["id"],
            st="error" if state == "failed" else "ok",
            st2=state,
            e=(error_code or None),
            f=failures,
            k=p["kind"],
        )
        if stopped is None:
            if failures >= 2:
                await _pull_failed_alert(tx, hub, acct, error_code or "failed", p["to_day"])
            await incomplete_alerts(tx, hub, acct)
            await F.detect_leaks(tx, acct["company_id"], acct["company"])
        await audit.record(
            tx,
            SYSTEM,
            company_id=acct["company_id"],
            action="revenue.pull",
            action_class="A0",
            target_kind="revenue_account",
            target_ref=str(acct["id"]),
            summary=f"{p['kind']} {p['from_day']}..{p['to_day']}: {state}",
        )
    return {
        "pull": str(p["id"]),
        "state": state,
        "days_complete": complete,
        "days_incomplete": incomplete,
        "requests": requests,
    }


async def store_day(
    tx: Tx, hub: Any, acct: dict[str, Any], got: A.DayPull, floor: Decimal | None
) -> None:
    """RevenueDay, its invitees (subjects only) and the funnel's two affiliate
    stages. A complete day is never overwritten by an incomplete re-pull."""
    source = {
        "adapter": acct["adapter"],
        "endpoints": sorted(set(got.endpoints)),
        "pages": got.pages,
        "min_balance": str(floor) if floor is not None else None,
    }
    deposits = got.deposits_usdt()
    row = await tx.first(
        """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, by_coin, fees_usdt,
               volume_usdt, new_invitees, min_balance_invitees, active_traders, deposits_usdt, complete,
               gaps, source, pulled_at)
           VALUES (:co, :a, :d, :cu, CAST(:bc AS jsonb), :fees, :vol, :ni, :mb, :at, :dep, :ok,
                   CAST(:gaps AS jsonb), CAST(:src AS jsonb), now())
           ON CONFLICT (account_id, day) DO UPDATE SET
               commission_usdt = EXCLUDED.commission_usdt, by_coin = EXCLUDED.by_coin,
               fees_usdt = EXCLUDED.fees_usdt, volume_usdt = EXCLUDED.volume_usdt,
               new_invitees = EXCLUDED.new_invitees, min_balance_invitees = EXCLUDED.min_balance_invitees,
               active_traders = EXCLUDED.active_traders, deposits_usdt = EXCLUDED.deposits_usdt,
               complete = EXCLUDED.complete, gaps = EXCLUDED.gaps, source = EXCLUDED.source,
               attempts = revenue.days.attempts + 1, pulled_at = now()
           WHERE NOT revenue.days.complete OR EXCLUDED.complete
           RETURNING complete""",
        co=acct["company_id"],
        a=acct["id"],
        d=got.day,
        cu=got.commission_usdt(),
        bc=json.dumps(got.by_coin()),
        fees=got.fees_usdt,
        vol=got.volume_usdt,
        ni=got.new_invitees(),
        mb=got.min_balance_invitees(),
        at=got.active_traders,
        dep=deposits,
        ok=got.complete,
        gaps=json.dumps(got.gaps),
        src=json.dumps(source),
    )
    if row is None:  # a complete day stays as it was; this attempt still counts
        await tx.exec(
            "UPDATE revenue.days SET attempts = attempts + 1 WHERE account_id = :a AND day = :d",
            a=acct["id"],
            d=got.day,
        )
        return
    key = hub.secrets.support_pseudonym_key
    for inv in got.invitees:
        subject = pseudonym.subject(
            key, str(acct["company_id"]), f"uid:{acct['exchange']}", inv["uid"]
        )
        await tx.exec(
            """INSERT INTO revenue.invitees (company_id, account_id, subject, invited_on, meets_minimum,
                   meets_minimum_since)
               VALUES (:co, :a, :s, :on, :m, CASE WHEN :m THEN CAST(:d AS date) END)
               ON CONFLICT (account_id, subject) DO UPDATE SET
                   invited_on = COALESCE(revenue.invitees.invited_on, EXCLUDED.invited_on),
                   meets_minimum = COALESCE(EXCLUDED.meets_minimum, revenue.invitees.meets_minimum),
                   meets_minimum_since = COALESCE(revenue.invitees.meets_minimum_since,
                                                  EXCLUDED.meets_minimum_since),
                   last_checked_at = now()""",
            co=acct["company_id"],
            a=acct["id"],
            s=subject,
            on=_as_day(inv.get("invited_on")) or got.day,
            m=inv.get("meets_minimum"),
            d=got.day,
        )
    got.invitees.clear()  # the UIDs go no further than this
    await F.record_affiliate_day(tx, acct["company_id"], got.day)
    await events.emit(
        tx,
        acct["company"],
        "revenue.day",
        got.day.isoformat(),
        {"account": str(acct["id"]), "complete": bool(row["complete"])},
    )
    if row["complete"]:
        await check_drop(tx, hub, acct, got.day)


# ----------------------------------------------------------------- alerts --
async def raise_alert(
    tx: Tx,
    hub: Any,
    acct: dict[str, Any],
    *,
    kind: str,
    day: date | None,
    incident_key: str,
    note_fa: str,
    data: dict[str, Any] | None = None,
    sre_task: bool = False,
) -> dict[str, Any] | None:
    """One alert per incident: the row (UNIQUE incident_key), a `report` for
    the owner's digest, a system line in the CEO's thread, the stream; for a
    failing account also a task for the platform SRE. None if it existed."""
    row = await tx.first(
        """INSERT INTO revenue.alerts (company_id, account_id, kind, day, incident_key, note_fa, data)
           VALUES (:co, :a, :k, :d, :ik, :n, CAST(:data AS jsonb))
           ON CONFLICT (company_id, incident_key) DO NOTHING RETURNING id""",
        co=acct["company_id"],
        a=acct["id"],
        k=kind,
        d=day,
        ik=incident_key[:200],
        n=note_fa[:500],
        data=json.dumps(data or {}, default=str),
    )
    if row is None:
        return None
    n = await notify.raise_notification(
        tx,
        company_id=acct["company_id"],
        company_code=acct["company"],
        level="report",
        title_fa=f"رادار درآمد {acct['company']}: {note_fa}"[:300],
        body_fa=note_fa,
        link_kind="revenue_alert",
        link_ref=str(row["id"]),
        source_kind="service",
        source_code="revenue",
    )
    work_id = None
    if sre_task:
        holding = await hub.companies.holding()
        sre = await tx.scalar(
            """SELECT code FROM core.employees WHERE company_id = :co AND role = ANY(:roles)
                 AND status = 'active' ORDER BY hired_at LIMIT 1""",
            co=holding.id,
            roles=list(SRE_ROLES),
        )
        if sre:
            w = await W.create(
                tx,
                SYSTEM,
                company_id=holding.id,
                company_code=holding.code,
                title=f"pull درآمد {acct['company']}/{acct['exchange']} دو بار پشت‌سرهم شکست خورد"[
                    :200
                ],
                brief=(
                    f"{note_fa}\n\nحساب: {acct['id']} ({acct['adapter']}، حساب سرویس "
                    f"{acct['service_account']}). کلید را نبین و نخوان؛ وضعیت whitelist IP هاب و "
                    "`has_secret` حساب سرویس را بررسی کن و به مالک گزارش بده."
                ),
                kind="one_off",
                priority="P2",
                assignee_code=str(sre),
            )
            work_id = w["id"]
    await tx.exec(
        "UPDATE revenue.alerts SET notification_id = :n, work_id = :w WHERE id = :id",
        id=row["id"],
        n=n["id"],
        w=work_id,
    )
    ceo_thread = await tx.scalar(
        """SELECT t.code FROM msg.threads t JOIN core.employees e ON e.id = t.employee_id
           WHERE e.company_id = :co AND e.kind = 'ceo' AND e.status = 'active' LIMIT 1""",
        co=acct["company_id"],
    )
    if ceo_thread:
        await D.post_system_message(tx, str(ceo_thread), f"هشدار رادار درآمد: {note_fa}", {})
    await events.emit(
        tx,
        acct["company"],
        "revenue.alert",
        str(row["id"]),
        {"kind": kind, "account": str(acct["id"]), "day": day.isoformat() if day else None},
    )
    return {"id": row["id"], "kind": kind}


async def check_drop(tx: Tx, hub: Any, acct: dict[str, Any], day: date) -> dict[str, Any] | None:
    """Commission below 60% of the trailing 28-day median of the same weekday."""
    rows = await tx.all(
        """SELECT day, commission_usdt FROM revenue.days
           WHERE account_id = :a AND complete AND day = ANY(:days)""",
        a=acct["id"],
        days=[day - timedelta(days=7 * k) for k in range(5)],
    )
    by_day = {r["day"]: Decimal(r["commission_usdt"]) for r in rows}
    today = by_day.pop(day, None)
    if today is None or len(by_day) < 2:
        return None
    median = Decimal(statistics.median(by_day.values()))
    if median <= 0 or today >= DROP_SHARE * median:
        return None
    share = int((today / median) * 100)
    return await raise_alert(
        tx,
        hub,
        acct,
        kind="drop",
        day=day,
        incident_key=f"drop:{acct['id']}:{day.isoformat()}",
        note_fa=(
            f"کمیسیون {day.isoformat()} ({acct['exchange']}) {today:.2f} USDT است: {share}٪ میانه‌ی "
            f"همان روزِ هفته در ۲۸ روز گذشته ({median:.2f})."
        ),
        data={"usdt": str(today), "median": str(median)},
    )


async def _pull_failed_alert(
    tx: Tx, hub: Any, acct: dict[str, Any], code: str, day: date
) -> dict[str, Any] | None:
    started = await tx.scalar(
        """SELECT min(created_at) FROM revenue.pulls
           WHERE account_id = :a AND state = 'failed'
             AND created_at > COALESCE((SELECT max(created_at) FROM revenue.pulls
                                        WHERE account_id = :a AND state IN ('ok', 'incomplete')),
                                       '-infinity')""",
        a=acct["id"],
    )
    since = (started or datetime.now(UTC)).date().isoformat()
    return await raise_alert(
        tx,
        hub,
        acct,
        kind="pull_failed",
        day=day,
        incident_key=f"pull_failed:{acct['id']}:{since}",
        note_fa=f"دو pull پشت‌سرهم حساب {acct['exchange']} شکست خورد (آخرین خطا: {code}).",
        data={"code": code, "since": since},
        sre_task=True,
    )


async def incomplete_alerts(tx: Tx, hub: Any, acct: dict[str, Any]) -> int:
    """Days of the last week that a pull tried (not one skipped by the gate)
    and that are still incomplete, or never came, 36 h after their
    settlement: one alert each."""
    now = datetime.now(UTC)
    first = acct["created_at"].astimezone(A.UTC8).date()
    since = max(first, A.last_settled_day(now) - timedelta(days=7))
    rows = await tx.all(
        "SELECT day, complete FROM revenue.days WHERE account_id = :a AND day >= :f",
        a=acct["id"],
        f=since,
    )
    state = {r["day"]: r["complete"] for r in rows}
    tried = await tx.all(
        """SELECT from_day, to_day FROM revenue.pulls WHERE account_id = :a AND to_day >= :f
             AND state IN ('ok', 'incomplete', 'failed')""",
        a=acct["id"],
        f=since,
    )
    n = 0
    day = max(first, A.last_settled_day(now) - timedelta(days=7))
    while day <= A.last_settled_day(now):
        overdue = now >= A.settled_at(day) + timedelta(hours=A.INCOMPLETE_ALERT_HOURS)
        attempted = any(t["from_day"] <= day <= t["to_day"] for t in tried)
        if overdue and attempted and state.get(day) is not True:
            got = await raise_alert(
                tx,
                hub,
                acct,
                kind="incomplete",
                day=day,
                incident_key=f"incomplete:{acct['id']}:{day.isoformat()}",
                note_fa=f"روز {day.isoformat()} حساب {acct['exchange']} ۳۶ ساعت بعد از تسویه هنوز ناقص است.",
            )
            n += 1 if got else 0
        day += timedelta(days=1)
    return n


# ---------------------------------------------------------------- reading --
def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    """day = the last settled day; week = its 7 days; month = its 30."""
    to = today or A.last_settled_day()
    span = {"day": 1, "week": 7, "month": 30}[period]
    return to - timedelta(days=span - 1), to


def _window(start: date, end: date) -> tuple[datetime, datetime]:
    """The UTC+8 days [start, end] as instants (the treasury's window)."""
    a = datetime.combine(start, datetime.min.time(), A.UTC8)
    b = datetime.combine(end + timedelta(days=1), datetime.min.time(), A.UTC8)
    return a, b


async def token_costs(
    tx: Tx, start: date, end: date, company_id: UUID | str | None = None
) -> dict[str, Decimal]:
    """USD spent per company from the Token Treasury (llm.calls): API cost
    plus the subscription equivalent, as the treasury's own totals add them."""
    a, b = _window(start, end)
    rows = await tx.all(
        """SELECT co.code, COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd
           FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
           WHERE c.started_at >= :a AND c.started_at < :b
             AND (CAST(:co AS uuid) IS NULL OR c.company_id = CAST(:co AS uuid))
           GROUP BY co.code""",
        a=a,
        b=b,
        co=str(company_id) if company_id else None,
    )
    return {r["code"]: Decimal(r["usd"]) for r in rows}


async def summary(tx: Tx, period: str, company_id: UUID | str | None = None) -> dict[str, Any]:
    start, end = period_range(period)
    span = (end - start).days + 1
    prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)
    co = str(company_id) if company_id else None
    days = await tx.all(
        """SELECT d.day, d.account_id, d.commission_usdt, c.code AS company FROM revenue.days d
           JOIN core.companies c ON c.id = d.company_id
           WHERE d.day BETWEEN :s AND :e AND (CAST(:co AS uuid) IS NULL OR d.company_id = CAST(:co AS uuid))""",
        s=start,
        e=end,
        co=co,
    )
    prev = await tx.scalar(
        """SELECT sum(commission_usdt) FROM revenue.days
           WHERE day BETWEEN :s AND :e AND (CAST(:co AS uuid) IS NULL OR company_id = CAST(:co AS uuid))""",
        s=prev_start,
        e=prev_end,
        co=co,
    )
    costs = await token_costs(tx, start, end, company_id)
    by_company: dict[str, Decimal] = {}
    by_account: dict[tuple[str, str], Decimal] = {}
    trend: dict[date, Decimal] = {start + timedelta(days=i): Decimal(0) for i in range(span)}
    for r in days:
        usdt = Decimal(r["commission_usdt"])
        by_company[r["company"]] = by_company.get(r["company"], Decimal(0)) + usdt
        key = (str(r["account_id"]), r["company"])
        by_account[key] = by_account.get(key, Decimal(0)) + usdt
        trend[r["day"]] += usdt
    total = sum(by_company.values(), Decimal(0))
    names = sorted(set(by_company) | set(costs))
    alerts = await tx.all(
        """SELECT a.kind, c.code AS company, a.account_id, a.note_fa FROM revenue.alerts a
           JOIN core.companies c ON c.id = a.company_id
           WHERE (a.day BETWEEN :s AND :e OR (a.day IS NULL AND a.created_at >= :since))
             AND (CAST(:co AS uuid) IS NULL OR a.company_id = CAST(:co AS uuid))
           ORDER BY a.created_at DESC LIMIT 50""",
        s=start,
        e=end,
        since=_window(start, end)[0],
        co=co,
    )
    return {
        "period": period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "total_usdt": total,
        "prev_total_usdt": Decimal(prev) if prev is not None else None,
        "by_company": [
            {
                "company": c,
                "usdt": by_company.get(c, Decimal(0)),
                "token_cost_usd": costs.get(c, Decimal(0)),
                "net_usd": by_company.get(c, Decimal(0)) - costs.get(c, Decimal(0)),
                "share": float(by_company.get(c, Decimal(0)) / total) if total > 0 else None,
            }
            for c in names
        ],
        "by_account": [
            {"account": a, "company": c, "usdt": v} for (a, c), v in sorted(by_account.items())
        ],
        "trend": [{"day": d.isoformat(), "usdt": v} for d, v in sorted(trend.items())],
        "alerts": [
            {
                "kind": r["kind"],
                "company": r["company"],
                "account": str(r["account_id"]) if r["account_id"] else None,
                "note_fa": r["note_fa"],
            }
            for r in alerts
        ],
    }


async def days_list(
    tx: Tx,
    *,
    company_id: UUID | str | None,
    account_id: UUID | str | None,
    start: date,
    end: date,
    limit: int = 400,
) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT d.*, c.code AS company FROM revenue.days d JOIN core.companies c ON c.id = d.company_id
           WHERE d.day BETWEEN :s AND :e
             AND (CAST(:co AS uuid) IS NULL OR d.company_id = CAST(:co AS uuid))
             AND (CAST(:a AS uuid) IS NULL OR d.account_id = CAST(:a AS uuid))
           ORDER BY d.day DESC, c.code LIMIT :n""",
        s=start,
        e=end,
        co=str(company_id) if company_id else None,
        a=str(account_id) if account_id else None,
        n=limit,
    )
    return [day_out(r) for r in rows]


def day_out(r: dict[str, Any]) -> dict[str, Any]:
    src = r["source"] or {}
    return {
        "company": r["company"],
        "account": str(r["account_id"]),
        "day": r["day"].isoformat(),
        "commission_usdt": r["commission_usdt"],
        "by_coin": r["by_coin"] or [],
        "fees_usdt": r["fees_usdt"],
        "volume_usdt": r["volume_usdt"],
        "new_invitees": r["new_invitees"],
        "active_traders": r["active_traders"],
        "deposits_usdt": r["deposits_usdt"],
        "complete": r["complete"],
        "pulled_at": r["pulled_at"],
        "source": {"adapter": src.get("adapter"), "endpoints": list(src.get("endpoints") or [])},
    }


# ------------------------------------------------------------- schedules --
async def plan_pulls(
    tx: Tx, kind: str, *, backfill_days: int, now: datetime | None = None
) -> list[dict[str, Any]]:
    """What a scheduled run starts. While the holding is locked every account
    gets one `skipped` row for the 07:00 run (the owner sees why) and nothing
    else happens; a retry while locked records nothing."""
    now = now or datetime.now(UTC)
    yesterday = A.last_settled_day(now)
    out: list[dict[str, Any]] = []
    holding = await gate.holding_lock(tx)
    for acct in await accounts(tx):
        lock = holding or await gate.automation_lock(tx, acct["company_id"])
        if lock is not None:
            if kind == "scheduled":
                out.append(
                    await create_pull(tx, acct, kind="scheduled", from_day=yesterday, to_day=yesterday,
                                      state="skipped", skipped_reason=gate.REASONS.get(lock, lock))
                )  # fmt: skip
            continue
        if kind == "scheduled":
            if acct["backfilled_at"] is None and not await _has_backfill(tx, acct["id"]):
                out.append(
                    await create_pull(tx, acct, kind="backfill", to_day=yesterday,
                                      from_day=yesterday - timedelta(days=max(1, backfill_days) - 1))
                )  # fmt: skip
            else:
                out.append(
                    await create_pull(
                        tx, acct, kind="scheduled", from_day=yesterday, to_day=yesterday
                    )
                )
            continue
        # retry: the last few days still incomplete or missing
        have = {
            r["day"]: r["complete"]
            for r in await tx.all(
                "SELECT day, complete FROM revenue.days WHERE account_id = :a AND day >= :f",
                a=acct["id"],
                f=yesterday - timedelta(days=RETRY_DAYS - 1),
            )
        }
        first = acct["created_at"].astimezone(A.UTC8).date() - timedelta(days=1)
        missing = [
            yesterday - timedelta(days=k)
            for k in range(RETRY_DAYS)
            if have.get(yesterday - timedelta(days=k)) is not True
            and yesterday - timedelta(days=k) >= first
        ]
        if missing:
            out.append(
                await create_pull(
                    tx, acct, kind="retry", from_day=min(missing), to_day=max(missing)
                )
            )
    # Manual pulls whose workflow never started are carried out with the run
    # (not while the holding is locked: they wait, queued).
    if holding is None:
        out += await tx.all(
            """SELECT * FROM revenue.pulls WHERE state = 'queued' AND kind = 'manual'
                 AND created_at < now() - interval '10 minutes'"""
        )
    return out


async def _has_backfill(tx: Tx, account_id: UUID) -> bool:
    return bool(
        await tx.scalar(
            """SELECT 1 FROM revenue.pulls WHERE account_id = :a AND kind = 'backfill'
                 AND state IN ('queued', 'running') LIMIT 1""",
            a=account_id,
        )
    )


def _as_day(value: Any) -> date | None:
    """An invite day as egress reduced it (ISO date), or None."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def parse_day(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={name: "a date (YYYY-MM-DD)"}) from exc
