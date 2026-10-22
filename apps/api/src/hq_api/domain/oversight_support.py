"""The overseer's support and revenue protocols (prompt 10 §11; contract
§19.9; agents/protocols/oversight.yaml). All are seeded from the file as it
is, PAUSED (each until its feature is live, ⟨1.4.4⟩): PR-043, PR-101,
PR-102, PR-103. What runs when the owner switches one on:

  PR-043  mystery customer (method mystery, weekly): before the overseer is
          woken, GATES decides: the holding locked -> `skipped` (no model, no
          run); no company with a live customer channel -> `deferred` (not a
          failure); else the overseer's work names the companies to test with
          support.mystery
  PR-101  zero wrong codes and links (rule, daily, critical): every outbound
          customer message of the last day sent automatically is checked again
          by the outbound guard against the company's approved links and codes
          of now; a refusal for an unknown code or link that the owner never
          looked at is undecided (the overseer judges it)
  PR-102  sampled answers match the KB (sample, weekly): skipped when no
          answer went out automatically in the week (PRECHECKS)
  PR-103  revenue figures match the raw pages (reconcile, daily): yesterday's
          days that say complete but carry gaps, or whose commission is not the
          sum of its coins
Registered on import (worker/oversight_activities.py imports this module).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from hq_api.db import Tx
from hq_api.domain import gate, kb
from hq_api.domain import oversight_checks as C
from hq_common import outbound_guard as G

# Protocols that may not wake anyone right now: (result, notes) or None.
Gate = Callable[[Tx], Awaitable[tuple[str, str] | None]]
GATES: dict[str, Gate] = {}


async def _mystery_gate(tx: Tx) -> tuple[str, str] | None:
    lock = await gate.holding_lock(tx)
    if lock is not None:
        return "skipped", gate.REASONS.get(lock, lock)
    live = await tx.scalar(
        "SELECT count(DISTINCT company_id) FROM support.channels WHERE state = 'live' AND kind <> 'mystery'"
    )
    if not live:
        return "deferred", "no company has a live support channel"
    return None


GATES["PR-043"] = _mystery_gate


async def _auto_answers_this_week(tx: Tx) -> bool:
    return bool(
        await tx.scalar(
            """SELECT 1 FROM support.messages m JOIN support.conversations c ON c.id = m.conversation_id
               WHERE m.direction = 'out' AND m.status = 'sent' AND m.author IN ('agent', 'rule')
                 AND NOT c.mystery AND m.at > now() - interval '7 days' LIMIT 1"""
        )
    )


C.PRECHECKS["PR-102"] = _auto_answers_this_week


@C.check("PR-101")
async def no_wrong_codes_or_links(ctx: C.CheckCtx) -> C.Checked:
    problems: list[C.Problem] = []
    unclear: list[C.Problem] = []
    checked = 0
    for code, company_id in C._ops(ctx).items():
        rows = await ctx.tx.all(
            """SELECT m.id, m.body, c.ref FROM support.messages m
               JOIN support.conversations c ON c.id = m.conversation_id
               WHERE m.company_id = :co AND m.direction = 'out' AND m.status = 'sent'
                 AND m.author IN ('agent', 'rule') AND NOT c.mystery AND m.body IS NOT NULL
                 AND m.at > now() - interval '1 day'
               ORDER BY m.at LIMIT 2000""",
            co=company_id,
        )
        approved = await kb.guard_context(ctx.tx, company_id)
        for r in rows:
            checked += 1
            v = G.check(r["body"], approved)
            bad = [x for x in v.reasons if x in ("unknown_link", "unknown_code")]
            if bad:
                problems.append(
                    C.Problem(
                        company_id=company_id,
                        company=code,
                        title_fa=f"پیام خودکار {r['ref']} کد یا لینک تأییدنشده داشت",
                        body_md=f"Outbound message {r['id']} fails the guard now: {', '.join(bad)}.",
                        key=f"msg:{r['id']}",
                        evidence=[
                            {"kind": "support_message", "ref": str(r["id"])},
                            {"kind": "conversation", "ref": r["ref"]},
                        ],
                    )
                )
        refused = await ctx.tx.all(
            """SELECT m.id, c.ref FROM support.messages m
               JOIN support.conversations c ON c.id = m.conversation_id
               WHERE m.company_id = :co AND m.direction = 'out' AND m.status = 'blocked'
                 AND (m.blocked_reasons && ARRAY['unknown_link', 'unknown_code'])
                 AND m.at > now() - interval '1 day' AND NOT c.mystery
                 AND NOT EXISTS (SELECT 1 FROM support.messages o WHERE o.conversation_id = c.id
                                   AND o.author = 'owner' AND o.at > m.at)
               LIMIT 50""",
            co=company_id,
        )
        for r in refused:
            unclear.append(
                C.Problem(
                    company_id=company_id,
                    company=code,
                    title_fa=f"ردِ نگهبان در {r['ref']} توضیح ندارد",
                    body_md=f"The guard refused message {r['id']} for an unknown code or link and "
                    "nobody has answered the conversation since.",
                    key=f"refused:{r['id']}",
                    evidence=[{"kind": "support_message", "ref": str(r["id"])}],
                )
            )
    return C.Checked(problems, C._ops(ctx), data={"checked": checked}, unclear=unclear)


@C.check("PR-103")
async def revenue_days_reconcile(ctx: C.CheckCtx) -> C.Checked:
    problems: list[C.Problem] = []
    rows = await ctx.tx.all(
        """SELECT company_id, account_id, day, commission_usdt, by_coin, gaps, complete
           FROM revenue.days WHERE day >= (now() AT TIME ZONE 'UTC')::date - 2"""
    )
    for r in rows:
        coins: list[dict[str, Any]] = r["by_coin"] if isinstance(r["by_coin"], list) else []
        total = sum((Decimal(str(c.get("usdt") or 0)) for c in coins), Decimal(0))
        wrong_sum = coins and abs(total - Decimal(r["commission_usdt"])) > Decimal("0.01")
        gaps = r["gaps"] if isinstance(r["gaps"], list) else []
        if (r["complete"] and gaps) or wrong_sum:
            code = C._code_of(ctx, r["company_id"])
            problems.append(
                C.Problem(
                    company_id=r["company_id"],
                    company=code,
                    title_fa=f"روز درآمد {r['day']} با داده‌ی خام نمیخواند",
                    body_md=(
                        f"Account {r['account_id']}, day {r['day']}: "
                        + ("marked complete with missing pages; " if r["complete"] and gaps else "")
                        + (
                            f"commission {r['commission_usdt']} != coins {total}"
                            if wrong_sum
                            else ""
                        )
                    ),
                    key=f"day:{r['account_id']}:{r['day']}",
                    evidence=[{"kind": "revenue_day", "ref": f"{r['account_id']}:{r['day']}"}],
                )
            )
    return C.Checked(problems, C._ops(ctx), data={"days": len(rows)})
