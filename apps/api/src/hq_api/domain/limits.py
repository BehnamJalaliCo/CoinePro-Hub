"""⟨1.33⟩ §55.3 The limit at a glance: the owner's Claude accounts and today's meter.

Nothing here decides anything: the accounts are read as `servers.runner_claude_account` reads
them (the same rule, by code), and the day's spend is the sum the agents' daily cap is checked
against (`agents.runner.EFFECTIVE_SQL` over the router's ledger). No token, no key and no
address ever leaves: an account is its name, how full its window is, and when it resets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.domain import servers as SV

ACCOUNT_FA = ("اکانت اصلی", "اکانت دوم")
WINDOW_FA = {"h5": "پنجره‌ی ۵ ساعته", "d7": "پنجره‌ی هفتگی", "five_hour": "پنجره‌ی ۵ ساعته",
             "seven_day": "پنجره‌ی هفتگی", "weekly": "پنجره‌ی هفتگی"}  # fmt: skip
WARM = Decimal("0.70")
NEAR = Decimal("0.90")
NOTE_FA = {
    "calm": "مصرف امروز آرام است.",
    "warm": "از ۷۰ درصد سقف امروز گذشت.",
    "near": "نزدیک سقف امروز است؛ کارهای کم‌اهمیت‌تر صبر میکنند.",
    "full": "سقف امروز پر شد؛ کارها تا نیمه‌شب (به وقت جهانی) صبر میکنند.",
    "open": "برای امروز سقفی گذاشته نشده است.",
}
ROWS_SQL = """SELECT c.key, c.status AS connection_status, c.fallback_priority, q.status,
       q.utilization, q.window_kind, q.resets_at, q.observed_at, q.windows
  FROM llm.connections c LEFT JOIN llm.quota_status q ON q.connection_id = c.id
 WHERE c.key = ANY(CAST(:keys AS text[]))"""
USABLE = ("enabled", "ready", "quota_exhausted")


class ClaudeAccount(BaseModel):
    key: str
    name_fa: str
    # working: the one the hub is on now; ready: has room and can take work; full: until its window
    # resets; off: switched off on the hub, not stored, or (the second one) not a fallback of the
    # router: the owner reads «خاموش», nothing technical
    state: Literal["working", "ready", "full", "off"]
    utilization: Decimal | None = None
    window_fa: str | None = None
    resets_at: datetime | None = None
    observed_at: datetime | None = None


class TodayMeter(BaseModel):
    spent: int = 0
    cap: int = 0
    share: Decimal = Decimal("0")
    state: Literal["calm", "warm", "near", "full"] = "calm"
    resets_at: datetime
    note_fa: str = NOTE_FA["calm"]


class Limits(BaseModel):
    accounts: list[ClaudeAccount] = Field(default_factory=list)
    # every account is full: Claude Code jobs (and the hub's own calls) wait for a window
    waiting: bool = False
    today: TodayMeter


def _full(row: dict[str, Any] | None, now: datetime) -> bool:
    """As `servers.runner_claude_account` reads one account: refused by the provider until its
    window resets, or at 99% of it."""
    if row is not None and row["connection_status"] == "quota_exhausted":
        resets = row.get("resets_at")
        return resets is None or resets > now
    return SV.account_full(row, now)


def usable(row: dict[str, Any] | None, stored: bool, *, main: bool) -> bool:
    """⟨2026-11-11⟩ «ready» means usable (audit C2): its token is stored, it is switched on on the
    hub (as llm-router routes: enabled, ready, or out of quota until its reset), and an account
    other than the main one is a fallback of the router (it has a fallback_priority), since only
    then does the router ever move a call to it."""
    if not stored or row is None:
        return False
    if row.get("connection_status") not in USABLE:
        return False
    return main or row.get("fallback_priority") is not None


async def accounts(tx: Tx, hub: Any, now: datetime) -> tuple[list[ClaudeAccount], bool]:
    sec = getattr(hub, "secrets", None)
    keys = [k for k, _ in SV.RUNNER_ACCOUNTS]
    rows = {str(r["key"]): dict(r) for r in await tx.all(ROWS_SQL, keys=keys)}
    out: list[ClaudeAccount] = []
    picked = False
    usable = 0
    for n, (key, attr) in enumerate(SV.RUNNER_ACCOUNTS):
        r = rows.get(key)
        # the token in OpenBao (kv/claude-runtime/oauth[-2]): the same secret claude-runtime reads
        # at its start (`make claude-token` restarts it), so stored here is configured there
        stored = bool(str(getattr(sec, attr, "") or ""))
        if r is None and not stored:
            continue  # this account does not exist on this hub
        off = not usable(r, stored, main=n == 0)
        full = not off and _full(r, now)
        if off:
            state: Literal["working", "ready", "full", "off"] = "off"
        elif full:
            state, usable = "full", usable + 1
        elif not picked:
            state, picked, usable = "working", True, usable + 1
        else:
            state, usable = "ready", usable + 1
        resets = (r or {}).get("resets_at")
        util = (r or {}).get("utilization")
        out.append(
            ClaudeAccount(
                key=key,
                name_fa=ACCOUNT_FA[n] if n < len(ACCOUNT_FA) else f"اکانت {n + 1}",
                state=state,
                utilization=(
                    min(Decimal("1"), max(Decimal("0"), Decimal(str(util))))
                    if util is not None and (resets is None or resets > now)
                    else (Decimal("0") if util is not None else None)
                ),
                window_fa=WINDOW_FA.get(str((r or {}).get("window_kind") or "")),
                resets_at=resets if resets is not None and resets > now else None,
                observed_at=(r or {}).get("observed_at"),
            )
        )
    return out, usable > 0 and not picked


async def today(tx: Tx, cap: int, now: datetime) -> TodayMeter:
    from hq_api.agents.runner import EFFECTIVE_SQL  # the sum the daily cap is checked against

    spent = int(
        await tx.scalar(
            f"""SELECT COALESCE(sum({EFFECTIVE_SQL}), 0) FROM llm.calls
                WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                  AND meta ? 'run_id'"""  # noqa: S608 - a constant expression
        )
        or 0
    )
    midnight = (now.astimezone(UTC) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if cap <= 0:
        return TodayMeter(spent=spent, cap=0, resets_at=midnight, note_fa=NOTE_FA["open"])
    share = (Decimal(spent) / Decimal(cap)).quantize(Decimal("0.001"))
    state: Literal["calm", "warm", "near", "full"] = (
        "full" if share >= 1 else "near" if share >= NEAR else "warm" if share >= WARM else "calm"
    )
    return TodayMeter(
        spent=spent, cap=cap, share=share, state=state, resets_at=midnight, note_fa=NOTE_FA[state]
    )


async def read(tx: Tx, hub: Any) -> Limits:
    now = await tx.scalar("SELECT now()")
    rows, waiting = await accounts(tx, hub, now)
    return Limits(
        accounts=rows,
        waiting=waiting,
        today=await today(tx, int(hub.settings.agent_daily_token_cap), now),
    )
