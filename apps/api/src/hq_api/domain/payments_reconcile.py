"""⟨1.15⟩ Prompt 24 (contract §33.2): the reconcile, by code, and its alerts.

A ledger row with a transaction hash that is on chain, to one of the company's addresses, with
enough confirmations and an amount at least the ledger's amount is `matched` (a hash pays once:
two ledger rows naming it share its amount, the earliest first); a ledger row the
scan has passed without finding is `ledger_only` (an approved payment without money: an alert); a
transfer to our address with no ledger row is `chain_only` (money without a customer: shown for the
company to claim); a lower amount is `amount_mismatch`; a transfer that is not deep enough yet, or
a time the scan has not reached, is `pending_chain`. The amount to compare with is the ledger's
own `amount_usdt` (what the company credited). Alerts go to the company's CEO and FIN manager as a
work item each; the owner sees only a weekly line, unless a `ledger_only` is above the critical
amount (a critical notification of the money domain).

No model is called and nothing is changed in a company system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import payments as P

log = logging.getLogger("hq_api.payments.reconcile")

STATUS_FA = {
    "matched": "مطابق",
    "ledger_only": "بدون پول روی زنجیره",
    "chain_only": "پول بدون مشتری",
    "amount_mismatch": "مبلغ کمتر",
    "pending_chain": "در انتظار زنجیره",
}


@dataclass(frozen=True)
class Seen:
    """What the chain showed for one hash: the total that reached our addresses and the
    least confirmations among its transfers."""

    amount: Decimal
    confirmations: int


@dataclass(frozen=True)
class Coverage:
    """The time the scan of a network has really covered, over all its sources."""

    from_at: datetime | None
    to_at: datetime | None


def judge(
    amount: Decimal,
    paid_at: datetime,
    seen: Seen | None,
    cover: Coverage | None,
    *,
    threshold: int,
    grace: timedelta,
) -> tuple[str, Decimal | None, str | None]:
    """(status, the amount that reached the address, a plain Persian note) of one ledger row."""
    if seen is not None:
        if seen.confirmations < threshold:
            return (
                "pending_chain",
                seen.amount,
                f"روی زنجیره است؛ هنوز {seen.confirmations} از {threshold} تأیید را دارد.",
            )
        if seen.amount >= amount:
            return "matched", seen.amount, None
        return (
            "amount_mismatch",
            seen.amount,
            f"فقط {_fmt(seen.amount)} از {_fmt(amount)} تتر رسیده است.",
        )
    if cover is None or cover.to_at is None or cover.from_at is None:
        return "pending_chain", None, "آدرس زنجیره‌ی این شبکه هنوز خوانده نشده است."
    if paid_at < cover.from_at:
        return "pending_chain", None, "قدیمی‌تر از بازه‌ای است که زنجیره از آن خوانده شده."
    if cover.to_at >= paid_at + grace:
        return "ledger_only", None, "تراکنش این پرداخت روی زنجیره به آدرس ما پیدا نشد."
    return "pending_chain", None, "زنجیره هنوز تا زمان این پرداخت خوانده نشده است."


def _fmt(d: Decimal) -> str:
    return format(d.normalize(), "f") if d != 0 else "0"


async def _coverage(tx: Tx, company_id: UUID) -> dict[str, Coverage]:
    """Per network: the latest start and the earliest end over its enabled sources (all of them
    must have looked). A network with a source never read has none."""
    rows = await tx.all(
        """SELECT network, count(*) AS n, count(scanned_to_at) AS read, max(scan_from_at) AS f,
                  min(scanned_to_at) AS t
           FROM money.payment_sources
           WHERE company_id = :co AND kind = 'chain' AND enabled GROUP BY network""",
        co=company_id,
    )
    return {r["network"]: Coverage(r["f"], r["t"] if r["read"] == r["n"] else None) for r in rows}


async def reconcile(tx: Tx, company_id: UUID, at: datetime | None = None) -> dict[str, int]:
    """Judges every ledger payment of the window again, makes the `chain_only` rows, drops the
    ones a ledger row has since claimed, and recounts the days. Returns the counts by status."""
    at = at or P.now()
    conf = P.cfg()["reconcile"]
    since = at - timedelta(days=int(conf["window_days"]))
    grace = timedelta(minutes=int(conf["grace_minutes"]))
    cover = await _coverage(tx, company_id)
    chain = {
        (r["network"], r["tx_hash"]): Seen(Decimal(r["amount"]), int(r["conf"]))
        for r in await tx.all(
            """SELECT network, tx_hash, sum(amount_usdt) AS amount, min(confirmations) AS conf
               FROM money.chain_transfers WHERE company_id = :co GROUP BY network, tx_hash""",
            co=company_id,
        )
    }
    counts = dict.fromkeys(P.STATUSES, 0)
    unchanged: list[UUID] = []
    ledger = await tx.all(
        """SELECT id, ext_id, customer, amount_usdt, network, tx_hash, paid_at, status,
                  chain_amount, note_fa
           FROM money.payments
           WHERE company_id = :co AND origin = 'ledger' AND kind = 'crypto' AND paid_at >= :since
           ORDER BY paid_at, ext_id, id""",
        co=company_id,
        since=since,
    )
    # One transfer pays one ledger row: a hash is a pool the rows use up in order (the earliest
    # first), so a hash named by two approved payments never counts its money twice. Rows of the
    # same hash older than the window have used their share already.
    pool = {
        (r["network"], r["tx_hash"]): Decimal(r["amount"])
        for r in await tx.all(
            """SELECT network, tx_hash, sum(amount_usdt) AS amount FROM money.payments
               WHERE company_id = :co AND origin = 'ledger' AND kind = 'crypto'
                 AND paid_at < :since AND tx_hash = ANY(:hashes) GROUP BY network, tx_hash""",
            co=company_id,
            since=since,
            hashes=sorted({p["tx_hash"] for p in ledger if p["tx_hash"]}),
        )
    }
    for p in ledger:
        net = p["network"]
        key = (net, p["tx_hash"])
        amount = Decimal(p["amount_usdt"])
        seen = chain.get(key)
        claimed = pool.get(key, Decimal(0))
        if seen is not None:
            pool[key] = claimed + amount
            if claimed > 0:
                seen = Seen(max(seen.amount - claimed, Decimal(0)), seen.confirmations)
        status, got, note = judge(
            amount,
            p["paid_at"],
            seen,
            cover.get(net),
            threshold=int(P.networks()[net]["confirmations"]),
            grace=grace,
        )
        if status == "amount_mismatch" and claimed > 0:
            note = (
                "این تراکنش برای پرداخت دیگری از دفتر هم آمده است؛ "
                f"فقط {_fmt(got or Decimal(0))} از {_fmt(amount)} تتر برای این یکی مانده."
            )
        counts[status] += 1
        if (status, got, note) != (p["status"], p["chain_amount"], p["note_fa"]):
            await tx.exec(
                """UPDATE money.payments SET status = :s, chain_amount = :g, note_fa = :n,
                       checked_at = :at WHERE id = :id""",
                id=p["id"],
                s=status,
                g=got,
                n=note,
                at=at,
            )
            if status == "matched" and p["status"] != "matched":
                # §33.4: `paid` is set by code when the money of a pseudonym has arrived
                await P._lead_paid(tx, company_id, p["customer"], amount)
        else:
            unchanged.append(p["id"])
    if unchanged:
        await tx.exec(
            "UPDATE money.payments SET checked_at = :at WHERE id = ANY(:ids)", ids=unchanged, at=at
        )
    counts["chain_only"] = await _chain_only(tx, company_id, since, at)
    await recount_days(tx, company_id, since, at)
    return counts


async def _chain_only(tx: Tx, company_id: UUID, since: datetime, at: datetime) -> int:
    """Transfers to our addresses that no ledger row names, deep enough to count as paid: one
    `chain_only` row per source and hash. A row whose hash a ledger row has since claimed goes
    (it was only ever derived)."""
    await tx.exec(
        """DELETE FROM money.payments c WHERE c.company_id = :co AND c.origin = 'chain'
             AND EXISTS (SELECT 1 FROM money.payments l WHERE l.company_id = c.company_id
                           AND l.origin = 'ledger' AND l.tx_hash = c.tx_hash)""",
        co=company_id,
    )
    for net, conf in P.networks().items():
        made = await tx.all(
            """INSERT INTO money.payments (company_id, source_id, ext_id, origin, kind, amount_usdt,
                   network, tx_hash, paid_at, status, chain_amount, note_fa, checked_at)
               SELECT t.company_id, t.source_id, 'chain:' || t.tx_hash, 'chain', 'crypto',
                      sum(t.amount_usdt), t.network, t.tx_hash, min(t.at), 'chain_only',
                      sum(t.amount_usdt), 'پولی که مشتری ندارد؛ شرکت باید ادعایش کند.', :at
               FROM money.chain_transfers t
               WHERE t.company_id = :co AND t.network = :n AND t.at >= :since
                 AND NOT EXISTS (SELECT 1 FROM money.payments l WHERE l.company_id = t.company_id
                                   AND l.origin = 'ledger' AND l.tx_hash = t.tx_hash)
               GROUP BY t.company_id, t.source_id, t.network, t.tx_hash
               HAVING min(t.confirmations) >= :th
               ON CONFLICT (company_id, source_id, ext_id) DO UPDATE SET
                   amount_usdt = EXCLUDED.amount_usdt, chain_amount = EXCLUDED.chain_amount,
                   checked_at = EXCLUDED.checked_at
               RETURNING tx_hash, amount_usdt, (xmax = 0) AS inserted""",
            co=company_id,
            n=net,
            since=since,
            th=int(conf["confirmations"]),
            at=at,
        )
        for m in made:  # §33.4: money without a customer is a lead to claim
            if m["inserted"]:
                await _chain_lead(tx, company_id, m["tx_hash"], Decimal(m["amount_usdt"]))
    return int(
        await tx.scalar(
            "SELECT count(*) FROM money.payments WHERE company_id = :co AND origin = 'chain'",
            co=company_id,
        )
    )


async def _chain_lead(tx: Tx, company_id: UUID, tx_hash: str, amount: Decimal) -> None:
    """A `chain_only` payment makes a lead in the first stage (a pseudonym of the hash, never an
    address), for the company to find its customer."""
    from hq_api.domain import leads
    from hq_api.errors import ApiError

    try:
        async with tx.conn.begin_nested():
            await leads.from_payment(
                tx, company_id, "tx-" + tx_hash.removeprefix("0x")[:40], amount, paid=False
            )
    except ApiError as exc:
        log.warning("lead of a chain payment refused", extra={"code": exc.code})


def day_note(c: dict[str, int]) -> str:
    """The day in one Persian line (Latin digits, as the rest of the app)."""
    parts = []
    for key, text in (
        ("matched", "مطابق"),
        ("ledger_only", "بدون پول روی زنجیره"),
        ("chain_only", "پول بدون مشتری"),
        ("amount_mismatch", "مبلغ کمتر"),
        ("pending_chain", "در انتظار زنجیره"),
    ):
        if c.get(key):
            parts.append(f"{c[key]} {text}")
    return "، ".join(parts) if parts else "پرداختی نبود."


async def recount_days(tx: Tx, company_id: UUID, since: datetime, at: datetime) -> None:
    """money.reconcile_days for every UTC day from `since`: the counts by status."""
    rows = await tx.all(
        """SELECT (paid_at AT TIME ZONE 'UTC')::date AS day,
                  count(*) FILTER (WHERE origin = 'ledger' AND kind = 'crypto') AS ledger_count,
                  count(*) FILTER (WHERE status = 'matched' AND kind = 'crypto') AS matched,
                  count(*) FILTER (WHERE status = 'ledger_only') AS ledger_only,
                  count(*) FILTER (WHERE status = 'chain_only') AS chain_only,
                  count(*) FILTER (WHERE status = 'amount_mismatch') AS amount_mismatch,
                  count(*) FILTER (WHERE status = 'pending_chain') AS pending_chain
           FROM money.payments WHERE company_id = :co AND paid_at >= :since GROUP BY 1""",
        co=company_id,
        since=since,
    )
    chain = {
        r["day"]: int(r["n"])
        for r in await tx.all(
            """SELECT (at AT TIME ZONE 'UTC')::date AS day, count(DISTINCT (source_id, tx_hash)) AS n
               FROM money.chain_transfers WHERE company_id = :co AND at >= :since GROUP BY 1""",
            co=company_id,
            since=since,
        )
    }
    for r in rows:
        c = {k: int(r[k]) for k in r if k != "day"}
        c["chain_count"] = chain.pop(r["day"], 0)
        await _put_day(tx, company_id, r["day"], c, at)
    for day, n in chain.items():  # a day with transfers and no payment row
        await _put_day(tx, company_id, day, {"chain_count": n}, at)


async def _put_day(tx: Tx, company_id: UUID, day: date, c: dict[str, int], at: datetime) -> None:
    keys = ("ledger_count", "chain_count", "matched", "ledger_only", "chain_only",
            "amount_mismatch", "pending_chain")  # fmt: skip
    full = {k: int(c.get(k, 0)) for k in keys}
    await tx.exec(
        """INSERT INTO money.reconcile_days (company_id, day, ledger_count, chain_count, matched,
               ledger_only, chain_only, amount_mismatch, pending_chain, note_fa, computed_at)
           VALUES (:co, :d, :lc, :cc, :m, :lo, :co2, :am, :pc, :n, :at)
           ON CONFLICT (company_id, day) DO UPDATE SET ledger_count = EXCLUDED.ledger_count,
               chain_count = EXCLUDED.chain_count, matched = EXCLUDED.matched,
               ledger_only = EXCLUDED.ledger_only, chain_only = EXCLUDED.chain_only,
               amount_mismatch = EXCLUDED.amount_mismatch, pending_chain = EXCLUDED.pending_chain,
               note_fa = EXCLUDED.note_fa, computed_at = EXCLUDED.computed_at""",
        co=company_id,
        d=day,
        lc=full["ledger_count"],
        cc=full["chain_count"],
        m=full["matched"],
        lo=full["ledger_only"],
        co2=full["chain_only"],
        am=full["amount_mismatch"],
        pc=full["pending_chain"],
        n=day_note(full),
        at=at,
    )


# ----------------------------------------------------------------- alerts --
async def recipients(tx: Tx, company_id: UUID) -> list[str]:
    """The company's CEO and its FIN manager (the codes that exist and are active)."""
    rows = await tx.all(
        """SELECT e.code FROM core.employees e
           LEFT JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND e.status = 'active'
             AND (e.kind = 'ceo' OR (e.kind = 'manager' AND d.code = 'FIN'))
           ORDER BY (e.kind = 'ceo') DESC, e.code""",
        co=company_id,
    )
    return [r["code"] for r in rows]


def _line(p: dict[str, Any]) -> str:
    amount = _fmt(Decimal(p["amount_usdt"])) if p["amount_usdt"] is not None else "؟"
    tail = f" ({p['note_fa']})" if p["note_fa"] else ""
    return f"- {p['ext_id']}: {amount} تتر، {p['paid_at'].date().isoformat()}{tail}"


async def raise_alerts(hub: Any, tx: Tx, company: Any) -> dict[str, Any]:
    """One alert row per payment and kind, told once: a work item per recipient and kind
    listing the payments (so a first big read is not a flood). A `ledger_only` above the
    critical amount also reaches the owner as one critical notification. Returns what was told;
    `push` holds the notifications to deliver after the commit."""
    from hq_api.domain import notify
    from hq_api.domain import work as W
    from hq_api.errors import ApiError

    conf = P.cfg()["reconcile"]
    critical_above = Decimal(str(conf["critical_ledger_only_usdt"]))
    out: dict[str, Any] = {"alerts": 0, "critical": 0, "push": []}
    fresh = await tx.all(
        """SELECT p.* FROM money.payments p
           WHERE p.company_id = :co AND p.status IN ('ledger_only', 'chain_only', 'amount_mismatch')
             AND NOT EXISTS (SELECT 1 FROM money.alerts a WHERE a.payment_id = p.id AND a.kind = p.status)
           ORDER BY p.paid_at, p.id""",
        co=company.id,
    )
    if not fresh:
        return out
    to = await recipients(tx, company.id)
    for kind in ("ledger_only", "amount_mismatch", "chain_only"):
        group = [p for p in fresh if p["status"] == kind]
        if not group:
            continue
        total = sum((Decimal(p["amount_usdt"] or 0) for p in group), Decimal(0))
        critical = [
            p
            for p in group
            if kind == "ledger_only" and Decimal(p["amount_usdt"] or 0) > critical_above
        ]
        critical_ids = {p["id"] for p in critical}
        shown = group[: int(conf["max_lines_per_alert"])]
        title = {
            "ledger_only": f"{len(group)} پرداخت تأییدشده، بدون پول روی زنجیره",
            "amount_mismatch": f"{len(group)} پرداخت با مبلغ کمتر از دفتر",
            "chain_only": f"{len(group)} واریز بدون مشتری روی زنجیره",
        }[kind]
        brief = (
            f"{title} (جمع {_fmt(total)} تتر).\n"
            + "\n".join(_line(p) for p in shown)
            + ("\n..." if len(group) > len(shown) else "")
            + "\nدفتر شرکت را با زنجیره مقایسه کن؛ ستاد هیچ پرداختی را تأیید یا رد نمیکند."
        )
        work_ids: list[UUID] = []
        for code in to:
            try:
                async with tx.conn.begin_nested():
                    w = await W.create(
                        tx,
                        P.SERVICE,
                        company_id=company.id,
                        company_code=company.code,
                        title=title[:300],
                        brief=brief[:5000],
                        kind="one_off",
                        priority="P1" if kind == "ledger_only" else "P2",
                        assignee_code=code,
                    )
                work_ids.append(UUID(str(w["id"])))
            except ApiError as exc:  # a refused item never stops the alert itself
                log.warning("payment alert work refused", extra={"code": exc.code})
        for p in group:
            await tx.exec(
                """INSERT INTO money.alerts (company_id, payment_id, kind, critical, work_ids)
                   VALUES (:co, :p, :k, :c, :w) ON CONFLICT DO NOTHING""",
                co=company.id,
                p=p["id"],
                k=kind,
                c=p["id"] in critical_ids,
                w=work_ids,
            )
            await events.emit(
                tx,
                company.code,
                "payment.alert",
                p["ext_id"],
                {"kind": kind, "payment": str(p["id"]), "critical": p["id"] in critical_ids},
            )
        out["alerts"] += len(group)
        if critical:
            row = await notify.raise_notification(
                tx,
                company_id=company.id,
                company_code=company.code,
                level="urgent",
                title_fa=f"{len(critical)} پرداخت تأییدشده بدون پول روی زنجیره ({company.code})",
                body_fa=(
                    f"جمع {_fmt(sum((Decimal(p['amount_usdt']) for p in critical), Decimal(0)))} تتر؛ "
                    "هر کدام بیش از "
                    f"{_fmt(critical_above)} تتر است. مدیرعامل و مدیر مالی شرکت خبر دارند."
                ),
                source_kind="system",
                source_code="money",
                domain="revenue",
                critical_reason="money",
            )
            out["critical"] += len(critical)
            if row.get("push_now"):
                out["push"].append(row["id"])
    return out


async def weekly_line(tx: Tx, since: datetime) -> str:
    """The owner's weekly line (Persian): how many payments were judged since `since`, and the
    problems among them, all companies. One line, from the stored statuses."""
    r = await tx.one(
        """SELECT count(*) FILTER (WHERE status = 'matched' AND kind = 'crypto') AS matched,
                  count(*) FILTER (WHERE status = 'ledger_only') AS ledger_only,
                  count(*) FILTER (WHERE status = 'chain_only') AS chain_only,
                  count(*) FILTER (WHERE status = 'amount_mismatch') AS amount_mismatch
           FROM money.payments WHERE paid_at >= :s""",
        s=since,
    )
    bad = r["ledger_only"] + r["chain_only"] + r["amount_mismatch"]
    if bad == 0:
        return f"پرداخت‌ها: {r['matched']} پرداخت با زنجیره مطابق بود و مغایرتی نبود."
    return (
        f"پرداخت‌ها: {r['matched']} مطابق؛ {r['ledger_only']} بدون پول روی زنجیره، "
        f"{r['chain_only']} واریز بدون مشتری، {r['amount_mismatch']} با مبلغ کمتر."
    )


def utc_day(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), UTC)
