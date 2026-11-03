"""What the holding spends, by domain (prompt 20.1, contract §28.6): every row
of the Token Treasury (llm.calls) falls in one domain, by rule (no model), so
the owner sees where the tokens went: the catalogue and the watch must never
again be the largest share (prompt 20 finding 6: 97.6% in one hour).

    catalogue   the servers' catalogue (their own Claude Code, the company's quota)
    server      any other Claude Code session on a company server
    oversight   the overseer, QC and inspector, their protocols and the watch
    advisor     the advisor, the digital CEO and the owner zone's memos
    council     the substitute players (the council, errands)
    meetings    the meeting room
    media       the media studio's steps and roles
    work        everything else: the owner's orders and the companies' work
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from hq_api.db import Tx

OVERSIGHT_ROLES = ("overseer", "inspector", "ai_safety", "fact_checker")
ADVISOR_ROLES = ("advisor", "dceo")
MEDIA_ROLES = (
    "media_director",
    "scriptwriter",
    "video_director",
    "motion_designer",
    "voice_producer",
    "visual_designer",
    "ui_designer",
)

DOMAINS: tuple[tuple[str, str], ...] = (
    ("work", "کار فرمان‌ها و شرکت‌ها"),
    ("media", "رسانه"),
    ("council", "شورا و بازیکن‌ها"),
    ("meetings", "جلسه‌ها"),
    ("advisor", "مشاور"),
    ("oversight", "نظارت و دیده‌بان"),
    ("catalogue", "کاتالوگ سرورها"),
    ("server", "Claude روی سرورها"),
)
DOMAIN_FA = dict(DOMAINS)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


# One CASE over llm.calls `c` (the charter's role is the part of meta.charter
# before its version); the first rule that matches wins.
DOMAIN_SQL = f"""CASE
    WHEN c.task_class = 'server_claude'
         AND (c.meta->>'via' = 'catalogue' OR c.actor_ref = 'catalogue') THEN 'catalogue'
    WHEN c.task_class = 'server_claude' THEN 'server'
    WHEN c.meta ? 'protocol' OR split_part(c.meta->>'charter', '@', 1) IN ({_in(OVERSIGHT_ROLES)})
         THEN 'oversight'
    WHEN c.caller = 'substitutes' THEN 'council'
    WHEN c.meta ? 'meeting' THEN 'meetings'
    WHEN c.task_class LIKE 'media\\_%' OR split_part(c.meta->>'charter', '@', 1) IN ({_in(MEDIA_ROLES)})
         THEN 'media'
    WHEN c.task_class LIKE 'advisor%' OR c.task_class LIKE 'dceo%'
         OR split_part(c.meta->>'charter', '@', 1) IN ({_in(ADVISOR_ROLES)}) THEN 'advisor'
    ELSE 'work' END"""

TOKENS_SQL = """COALESCE(sum(COALESCE(c.input_tokens, 0) + COALESCE(c.output_tokens, 0)
    + COALESCE(c.cache_read_tokens, 0) + COALESCE(c.cache_write_tokens, 0)), 0)"""


async def by_domain(
    tx: Tx, start: datetime, end: datetime, company_id: Any = None
) -> list[dict[str, Any]]:
    """Tokens, calls and cost per domain in [start, end), largest first, each
    with its share of the whole (percent, one decimal)."""
    rows = await tx.all(
        f"""SELECT {DOMAIN_SQL} AS domain, count(*) AS calls, {TOKENS_SQL} AS tokens,
                   COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd
            FROM llm.calls c
            WHERE c.started_at >= :s AND c.started_at < :e
              AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
            GROUP BY 1 ORDER BY tokens DESC""",  # noqa: S608 - constants only
        s=start,
        e=end,
        co=company_id,
    )
    total = sum(int(r["tokens"]) for r in rows) or 0
    return [
        {
            "domain": r["domain"],
            "title_fa": DOMAIN_FA.get(r["domain"], r["domain"]),
            "calls": int(r["calls"]),
            "tokens": int(r["tokens"]),
            "usd": str(Decimal(r["usd"]).quantize(Decimal("0.0001"))),
            "share_pct": round(100.0 * int(r["tokens"]) / total, 1) if total else 0.0,
        }
        for r in rows
    ]


def lines(rows: list[dict[str, Any]]) -> list[str]:
    """One plain Persian line per domain (numbers in Latin digits)."""
    if not rows:
        return ["- مصرفی ثبت نشده است."]
    out = [f"- **{r['title_fa']}:** {r['tokens']:,} توکن ({r['share_pct']}٪)" for r in rows]
    top = rows[0]
    if top["domain"] in ("catalogue", "oversight", "server"):
        out.append(
            f"- ⚠️ بیشترین سهم با «{top['title_fa']}» است، نه با کار شرکت‌ها؛ "
            "مدیر فنی پلتفرم باید بررسی کند."
        )
    return out
