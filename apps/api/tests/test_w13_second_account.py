"""⟨2026-11-09⟩ The owner's two Claude subscriptions and the company servers. The companies have no
subscription of their own: a Claude Code job a company server's runner picks up runs on the account
the hub itself is on — the main one (kv/claude-runtime/oauth) while it has room, the second
(kv/claude-runtime/oauth-2) once the main is at 99% or refused, the main again once its window
resets. Both full: the job waits in the queue. The token goes with the job at pickup only, never in
the stored args."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import asyncpg

from hq_api.domain import servers as SV

MAIN = "sk-ant-oat01-" + "m" * 95
SECOND = "sk-ant-oat01-" + "s" * 95


def _job(kind: str) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "kind": kind,
        "args": {"brief": "x"} if kind == "claude" else {"cmd": "uptime"},
        "timeout_s": 600,
        "created_at": datetime.now(UTC),
        "session_ref": None,
        "actor_kind": "owner",
        "actor_code": "OWNER",
        "server_id": uuid4(),
        "company": "PC",
    }


def _hub(main: str = MAIN, second: str = SECOND) -> Any:
    return SimpleNamespace(
        secrets=SimpleNamespace(runner_claude_token_main=main, runner_claude_token=second)
    )


def test_a_claude_job_carries_the_token_it_is_given_and_only_a_claude_job() -> None:
    job = _job("claude")
    out = SV.runner_job(job, _hub(), claude_token=SECOND)
    assert out["claude_oauth"] == SECOND
    assert "claude_oauth" not in job["args"] and "claude_oauth" not in out["args"]
    assert "claude_oauth" not in SV.runner_job(_job("exec"), _hub(), claude_token=SECOND)
    assert "claude_oauth" not in SV.runner_job(_job("claude"), _hub(), claude_token="")


def test_a_window_is_full_at_99_percent_or_refused_until_it_resets() -> None:
    now = datetime.now(UTC)
    later, before = now + timedelta(days=2), now - timedelta(minutes=1)

    def row(status: str, util: str | None, resets: datetime | None) -> dict[str, Any]:
        u = Decimal(util) if util is not None else None
        return {"status": status, "utilization": u, "resets_at": resets, "observed_at": now}

    assert not SV.account_full(None, now)
    assert not SV.account_full(row("warning", "0.94", later), now)
    assert SV.account_full(row("warning", "0.99", later), now)
    assert SV.account_full(row("limited", None, later), now)
    # Wednesday midnight: the window reset, the account has room again
    assert not SV.account_full(row("limited", None, before), now)
    assert not SV.account_full(row("warning", "0.995", before), now)
    # an old "ok" reading no longer decides
    stale = {**row("ok", "0.995", None), "observed_at": now - timedelta(hours=7)}
    assert not SV.account_full(stale, now)


async def _quota(su: asyncpg.Connection, key: str, status: str, util: str, resets: str) -> None:
    cid = await su.fetchval("SELECT id FROM llm.connections WHERE key = $1", key)
    await su.execute(
        f"""INSERT INTO llm.quota_status (connection_id, status, window_kind, utilization,
                resets_at, source, observed_at)
            VALUES ($1, $2, 'seven_day', $3, now() + interval '{resets}', 'sdk_rate_limit_event', now())
            ON CONFLICT (connection_id) DO UPDATE SET status = EXCLUDED.status,
                utilization = EXCLUDED.utilization, resets_at = EXCLUDED.resets_at,
                observed_at = EXCLUDED.observed_at""",
        cid,
        status,
        Decimal(util),
    )


async def test_the_company_servers_follow_the_hubs_account(
    hub: Any, su: asyncpg.Connection
) -> None:
    keys = ["claude-max", "claude-max-2"]
    before = await su.fetch("SELECT key, status FROM llm.connections WHERE key = ANY($1)", keys)
    saved = await su.fetch(
        """SELECT q.* FROM llm.quota_status q JOIN llm.connections c ON c.id = q.connection_id
           WHERE c.key = ANY($1)""",
        keys,
    )
    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = ANY($1)", keys)
    await su.execute(
        """DELETE FROM llm.quota_status
           WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))""",
        keys,
    )

    async def pick(h: Any) -> tuple[str, bool]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await SV.runner_claude_account(tx, h)

    try:
        # nothing known yet: the main account
        assert await pick(_hub()) == (MAIN, False)
        # the main one at 94%: still the main one
        await _quota(su, "claude-max", "warning", "0.94", "2 days")
        assert await pick(_hub()) == (MAIN, False)
        # the main one at 99%: the second one, as the hub moves
        await _quota(su, "claude-max", "warning", "0.99", "2 days")
        assert await pick(_hub()) == (SECOND, False)
        # the second one full too: Claude Code jobs wait (they do not fail)
        await _quota(su, "claude-max-2", "limited", "1", "1 day")
        assert await pick(_hub()) == ("", True)
        # the main one's window resets (Wednesday midnight): everything back on the main one,
        # whatever the second one's state
        await _quota(su, "claude-max", "warning", "0.99", "-1 minute")
        assert await pick(_hub()) == (MAIN, False)
        # only one account stored: it, while it has room
        assert await pick(_hub(main="")) == ("", True)
        await _quota(su, "claude-max-2", "warning", "0.50", "1 day")
        assert await pick(_hub(main="")) == (SECOND, False)
        # the second one switched off on the hub: never handed out
        await _quota(su, "claude-max", "limited", "1", "1 day")
        await su.execute(
            "UPDATE llm.connections SET status = 'disabled' WHERE key = 'claude-max-2'"
        )
        assert await pick(_hub()) == ("", True)
        # no account stored at all: the server's own login, nothing waits
        assert await pick(_hub(main="", second="")) == ("", False)
    finally:
        await su.execute(
            """DELETE FROM llm.quota_status
               WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))""",
            keys,
        )
        for r in saved:
            cols = list(r.keys())
            await su.execute(
                f"INSERT INTO llm.quota_status ({', '.join(cols)}) VALUES "
                f"({', '.join(f'${i + 1}' for i in range(len(cols)))})",
                *[r[c] for c in cols],
            )
        for r in before:
            await su.execute(
                "UPDATE llm.connections SET status = $2 WHERE key = $1", r["key"], r["status"]
            )
