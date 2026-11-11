"""⟨2026-11-11⟩ W23 (the 12-hour stall, audits C and E(b)): a full Claude account never stops work
silently, and an agent never claims a refused action.

- A runner's Claude Code job reports the CLI's rate-limit events: each is an observation of the
  account the job runs on (llm.quota_status, the router's own shape); a turn the usage limit
  stopped runs once more on the other account; its usage is booked to the account it ran on.
- The account choice reads every window; «ready» on the limits screen means usable.
- Quota-failed runs come back after their reset, a passing failure once.
- A step with a refused action does not end the run: the next step is told what did not happen,
  what claims success after the failure is not run, and «آنچه انجام شد» lists only what happened.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest

from hq_api.agents import runner as R
from hq_api.agents.clients import ModelCall
from hq_api.domain import direct as DR
from hq_api.domain import limits as LM
from hq_api.domain import servers as SV
from hq_api.hub import Hub
from hq_api.worker import activities as ACT

from .test_agents import order, run, runs_of, step
from .test_p17_runners import pair, take

API = "/api/v1"
MAIN = "sk-ant-oat01-" + "m" * 95
SECOND = "sk-ant-oat01-" + "s" * 95
KEYS = ["claude-max", "claude-max-2"]


# ------------------------------------------------------------------ helpers --
@pytest.fixture
async def accounts(hub: Hub, su: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Both of the owner's accounts stored and switched on, nothing observed yet; restored after.
    (Migration 0062 lets the api write llm.quota_status; granted here too for an older test DB.)"""
    await su.execute("GRANT INSERT, UPDATE ON llm.quota_status TO hq_api")
    before = await su.fetch(
        "SELECT key, status, fallback_priority FROM llm.connections WHERE key = ANY($1)", KEYS
    )
    saved = await su.fetch(
        """SELECT q.* FROM llm.quota_status q JOIN llm.connections c ON c.id = q.connection_id
           WHERE c.key = ANY($1)""",
        KEYS,
    )
    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = ANY($1)", KEYS)
    await _clear(su)
    monkeypatch.setattr(hub.secrets, "runner_claude_token_main", MAIN)
    monkeypatch.setattr(hub.secrets, "runner_claude_token", SECOND)
    yield
    await _clear(su)
    for r in saved:
        cols = list(r.keys())
        await su.execute(
            f"INSERT INTO llm.quota_status ({', '.join(cols)}) VALUES "
            f"({', '.join(f'${i + 1}' for i in range(len(cols)))})",
            *[r[c] for c in cols],
        )
    for r in before:
        await su.execute(
            "UPDATE llm.connections SET status = $2, fallback_priority = $3 WHERE key = $1",
            r["key"],
            r["status"],
            r["fallback_priority"],
        )


async def _clear(su: asyncpg.Connection) -> None:
    await su.execute(
        """DELETE FROM llm.quota_status
           WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))""",
        KEYS,
    )


async def _quota(su: asyncpg.Connection, key: str) -> dict[str, Any] | None:
    row = await su.fetchrow(
        """SELECT q.status, q.windows FROM llm.quota_status q
           JOIN llm.connections c ON c.id = q.connection_id WHERE c.key = $1""",
        key,
    )
    if row is None:
        return None
    return {"status": row["status"], "windows": json.loads(row["windows"])}


async def _claude_job(hub: Hub, server_id: str, **args: Any) -> str:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        server = await SV.load_server(tx, uuid.UUID(server_id))
        j = await SV.create_job(
            tx, server=server, kind="claude", args={"brief": "یک کاور بساز", **args},
            actor_kind="owner", actor_code="owner", timeout_s=600,
        )  # fmt: skip
    return str(j["id"])


def _command_event(seq: int) -> Any:
    """The turn ran a command on its server (it did something)."""
    return {
        "seq": seq,
        "type": "session_event",
        "data": {"type": "command", "summary_fa": "فرمان",
                 "data": {"cmd": "systemctl restart app", "exit_code": 0, "duration_s": 1}},
    }  # fmt: skip


async def _result(client: httpx.AsyncClient, rn: dict[str, Any], jid: str, **body: Any) -> str:
    r = await client.post(f"{API}/runners/jobs/{jid}/result", json=body, headers=rn["h"])
    assert r.status_code == 200, r.text
    return str(r.json()["state"])


async def _moved(su: asyncpg.Connection, jid: str) -> str | None:
    v = await su.fetchval(
        "SELECT id::text FROM infra.server_jobs WHERE usage->>'retry_of' = $1", jid
    )
    return str(v) if v is not None else None


async def _job(su: asyncpg.Connection, job_id: str) -> dict[str, Any]:
    r = await su.fetchrow(
        "SELECT state, error_code, summary_fa, usage FROM infra.server_jobs WHERE id = $1",
        uuid.UUID(job_id),
    )
    return {**dict(r), "usage": json.loads(r["usage"]) if r["usage"] else None}


async def _pick(hub: Hub) -> SV.AccountPick:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await SV.runner_claude_pick(tx, hub)


def _limit_event(seq: int, status: str, window: str, in_s: int, util: float | None = None) -> Any:
    info: dict[str, Any] = {"status": status, "resetsAt": int(time.time()) + in_s,
                            "rateLimitType": window}  # fmt: skip
    if util is not None:
        info["utilization"] = util
    return {
        "seq": seq,
        "type": "session_event",
        "data": {"type": "progress", "summary_fa": "وضعیت سهمیه‌ی Claude",
                 "data": {"rate_limit": info}},
    }  # fmt: skip


# ------------------------------------------------------ the runner's limit --
async def test_a_runners_limit_is_seen_booked_and_the_turn_runs_once_on_the_other_account(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: asyncpg.Connection,
    accounts: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    first = await _claude_job(hub, rn["server"]["id"])
    job = await take(client, rn)
    assert job["id"] == first and job["claude_oauth"] == MAIN
    assert (await _job(su, first))["usage"] == {"account": "claude-max"}

    # the CLI says the main account is nearly full, then refused: the hub records both windows
    r = await client.post(
        f"{API}/runners/jobs/{first}/events",
        json={"events": [_limit_event(1, "allowed_warning", "seven_day", 86_400, 0.82),
                         _limit_event(2, "rejected", "five_hour", 7_200)]},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["accepted"] == 2, r.text
    q = await _quota(su, "claude-max")
    assert q is not None and q["status"] == "limited"
    assert q["windows"]["sdk:five_hour"]["status"] == "limited"
    assert q["windows"]["sdk:seven_day"]["utilization"] == "0.8200"
    pick = await _pick(hub)
    assert (pick.key, pick.token, pick.hold) == ("claude-max-2", SECOND, False)

    # the turn ends with the limit: never a generic exit-1 failure; it runs once more on the
    # other account, as a new job; its usage is the main account's
    r = await client.post(
        f"{API}/runners/jobs/{first}/result",
        json={"exit_code": 1, "summary_fa": "نشست Claude با کد خروج 1 تمام شد.",
              "usage": {"input_tokens": 40, "output_tokens": 2, "model": "claude-opus-5-5"},
              "data": {"result_fa": f"Claude AI usage limit reached|{int(time.time()) + 7200}"}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["state"] == "failed", r.text
    old = await _job(su, first)
    assert (old["state"], old["error_code"], old["summary_fa"]) == (
        "failed", SV.USAGE_LIMIT, SV.MOVED_FA,
    )  # fmt: skip
    assert old["usage"]["account"] == "claude-max" and old["usage"]["input_tokens"] == 40
    booked = await su.fetchrow(
        """SELECT n.key, c.meta FROM llm.calls c LEFT JOIN llm.connections n ON n.id = c.connection_id
           WHERE c.meta->>'server_job' = $1""",
        first,
    )
    assert booked["key"] == "claude-max"
    meta = json.loads(booked["meta"])
    assert meta["quota"] == "hub_account" and meta["account"] == "claude-max"
    q = await _quota(su, "claude-max")
    assert q is not None and "quota_guard" in q["windows"]
    again = await su.fetchval(
        "SELECT id::text FROM infra.server_jobs WHERE usage->>'retry_of' = $1 AND state = 'queued'",
        first,
    )
    assert again is not None

    job = await take(client, rn)
    assert job["id"] == again and job["claude_oauth"] == SECOND
    assert (await _job(su, again))["usage"]["account"] == "claude-max-2"

    # the second account's turn "ends well" with the CLI's notice as its answer: that is the limit
    # too, never the turn's answer, and it is not moved a second time
    r = await client.post(
        f"{API}/runners/jobs/{again}/result",
        json={"exit_code": 0, "summary_fa": "نشست Claude روی سرور تمام شد.",
              "usage": {"input_tokens": 30, "output_tokens": 1},
              "data": {"result_fa": "You've hit your limit · resets 5pm (UTC)"}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["state"] == "failed", r.text
    last = await _job(su, again)
    assert (last["state"], last["error_code"], last["summary_fa"]) == (
        "failed", SV.USAGE_LIMIT, SV.LIMIT_FAILED_FA,
    )  # fmt: skip
    assert not await su.fetchval(
        "SELECT 1 FROM infra.server_jobs WHERE usage->>'retry_of' = $1", again
    )
    q2 = await _quota(su, "claude-max-2")
    assert q2 is not None and q2["status"] == "limited"
    booked2 = await su.fetchval(
        """SELECT n.key FROM llm.calls c JOIN llm.connections n ON n.id = c.connection_id
           WHERE c.meta->>'server_job' = $1""",
        again,
    )
    assert booked2 == "claude-max-2"
    # both full now: Claude Code jobs wait, and the session can say until when
    assert (await _pick(hub)).hold
    async with hub.db.tx(await hub.companies.ids()) as tx:
        room = await SV.room_at(tx, hub)
    assert room is not None and room > datetime.now(UTC)


async def test_an_observation_never_fails_the_runners_call(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: asyncpg.Connection,
    accounts: Any,
) -> None:
    """Before the api may write llm.quota_status (or on any error), the events still land."""
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    jid = await _claude_job(hub, rn["server"]["id"])
    await take(client, rn)
    await su.execute("REVOKE INSERT, UPDATE ON llm.quota_status FROM hq_api")
    try:
        r = await client.post(
            f"{API}/runners/jobs/{jid}/events",
            json={"events": [_limit_event(1, "rejected", "five_hour", 600)]},
            headers=rn["h"],
        )
        assert r.status_code == 200 and r.json()["accepted"] == 1, r.text
        assert await _quota(su, "claude-max") is None
    finally:
        await su.execute("GRANT INSERT, UPDATE ON llm.quota_status TO hq_api")


async def test_a_turn_that_already_did_something_is_never_run_again_whole(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: asyncpg.Connection,
    accounts: Any,
) -> None:
    """The limit came mid-turn, after a command on the company's server: the turn ends as a
    usage-limit failure (its holder is told as for any failed turn); the limit is recorded, so the
    next turn takes the other account. A workshop turn (hands, not direct) may move: its folder
    is its state."""
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    jid = await _claude_job(hub, rn["server"]["id"])
    assert (await take(client, rn))["claude_oauth"] == MAIN
    r = await client.post(
        f"{API}/runners/jobs/{jid}/events",
        json={"events": [_command_event(1), _limit_event(2, "rejected", "five_hour", 3600)]},
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    state = await _result(
        client, rn, jid, exit_code=1, data={"result_fa": "API Error: 429 rate_limit_error"}
    )
    assert state == "failed"
    j = await _job(su, jid)
    assert (j["error_code"], j["summary_fa"]) == (SV.USAGE_LIMIT, SV.MIDWAY_FA)
    assert await _moved(su, jid) is None
    assert (await _pick(hub)).key == "claude-max-2"  # the next turn takes the other account

    # a workshop turn (hands) that had run commands in its folder moves all the same
    await _clear(su)
    hands = await _claude_job(hub, rn["server"]["id"], hands=True, workspace="W-0")
    assert (await take(client, rn))["id"] == hands
    r = await client.post(
        f"{API}/runners/jobs/{hands}/events", json={"events": [_command_event(1)]}, headers=rn["h"]
    )
    assert r.status_code == 200, r.text
    await _result(client, rn, hands, exit_code=1,
                  data={"result_fa": f"Claude AI usage limit reached|{int(time.time()) + 600}"})  # fmt: skip
    assert (await _job(su, hands))["summary_fa"] == SV.MOVED_FA
    again = await _moved(su, hands)
    assert again is not None and (await take(client, rn))["claude_oauth"] == SECOND


async def test_a_servers_own_limit_is_never_the_subscriptions(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: asyncpg.Connection,
    accounts: Any,
) -> None:
    """«Disk usage limit reached», «disk quota exceeded»: the turn's own words about its server.
    Taken for the account's limit, both accounts would be marked full one after the other and
    every Claude Code job would wait for hours."""
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    done = await _claude_job(hub, rn["server"]["id"])
    await take(client, rn)
    said = {"result_fa": "Disk usage limit reached; cleaned /var/log."}
    assert await _result(client, rn, done, exit_code=0, data=said) == "done"
    failed = await _claude_job(hub, rn["server"]["id"])
    await take(client, rn)
    said = {"result_fa": "rsync: write failed: Disk quota exceeded (122)"}
    assert await _result(client, rn, failed, exit_code=1, data=said) == "failed"
    assert (await _job(su, failed))["error_code"] == "exit_nonzero"
    assert await _moved(su, failed) is None and await _moved(su, done) is None
    assert await _quota(su, "claude-max") is None and await _quota(su, "claude-max-2") is None
    pick = await _pick(hub)
    assert (pick.key, pick.hold) == ("claude-max", False)


def test_the_account_choice_reads_every_window() -> None:
    now = datetime.now(UTC)
    later = (now + timedelta(hours=2)).isoformat()

    def win(status: str, util: str | None, resets: str | None, seen: datetime = now) -> Any:
        return {"status": status, "utilization": util, "resets_at": resets,
                "observed_at": seen.isoformat()}  # fmt: skip

    # the summary row shows seven-day at 82%; five-hour is refused: full
    row = {"status": "warning", "utilization": Decimal("0.82"), "resets_at": now + timedelta(days=3),
           "observed_at": now,
           "windows": {"sdk:seven_day": win("warning", "0.8200", later),
                       "sdk:five_hour": win("limited", None, later)}}  # fmt: skip
    assert SV.account_full(row, now)
    # the windows as JSON text (asyncpg's jsonb), 99% of one of them: full
    row = {
        "status": "ok",
        "windows": json.dumps({"sdk:five_hour": win("warning", "0.9900", later)}),
    }
    assert SV.account_full(row, now)
    # a window that has reset, an old "ok" at 99%: room
    gone = (now - timedelta(minutes=1)).isoformat()
    old = now - timedelta(hours=7)
    row = {"status": None, "windows": {"a": win("limited", None, gone),
                                       "b": win("ok", "0.9950", None, old)}}  # fmt: skip
    assert not SV.account_full(row, now)
    assert not SV.account_full({"status": None, "windows": "not json"}, now)


def test_a_limit_notice_is_not_an_answer() -> None:
    assert SV.limit_notice("Claude AI usage limit reached|1800000000")
    assert SV.limit_notice("5-hour limit reached ∙ resets 3pm")
    assert SV.limit_notice("You\u2019ve hit your limit · resets 5pm")
    assert SV.limit_notice("Claude usage limit reached. Your limit will reset at 3pm.")
    assert not SV.limit_notice("## ساخته شد\nکاور و متن آماده است.")
    assert not SV.limit_notice("usage limit reached, resets 3pm " + "x" * 500)  # an answer
    # a server's own limits are the turn's word, never the subscription's
    for text in ("Disk usage limit reached; cleaned /var/log.", "disk quota exceeded",
                 "write failed: Disk quota exceeded", "usage limit", "limit reached"):  # fmt: skip
        assert not SV.limit_notice(text), text
    assert SV.flagged_usage_limit({"error_code": SV.USAGE_LIMIT})
    assert not SV.flagged_usage_limit({"error_code": "exit_nonzero"})
    assert DR.EMPTY_FA.endswith("بگو.") and "شما" not in DR.WAITS_FA + DR.EMPTY_FA


# --------------------------------------------------- «ready» means usable --
async def test_ready_means_usable(hub: Hub, su: asyncpg.Connection, accounts: Any) -> None:
    async def states() -> list[str]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            rows, _ = await LM.accounts(tx, hub, await tx.scalar("SELECT now()"))
        return [a.state for a in rows]

    assert await states() == ["working", "ready"]
    # not a fallback of the router: the router never moves a call to it, so it is off
    await su.execute(
        "UPDATE llm.connections SET fallback_priority = NULL WHERE key = 'claude-max-2'"
    )
    assert await states() == ["working", "off"]
    await su.execute("UPDATE llm.connections SET fallback_priority = 1 WHERE key = 'claude-max-2'")
    assert await states() == ["working", "ready"]
    # its token missing: off
    hub.secrets.runner_claude_token = ""
    assert await states() == ["working", "off"]
    assert LM.can_work({"connection_status": "enabled"}, True, main=True)
    assert not LM.can_work({"connection_status": "enabled"}, False, main=True)
    assert not LM.can_work(
        {"connection_status": "disabled", "fallback_priority": 1}, True, main=False
    )
    assert not LM.can_work(None, True, main=True)


# ------------------------------------------------------ runs come back --
async def test_which_failed_runs_come_back() -> None:
    now = datetime.now(UTC)

    class Tx:
        def __init__(self, at: str | None) -> None:
            self.at = at

        async def scalar(self, sql: str, **kw: Any) -> Any:
            return self.at

    def r(code: str, ago_min: int, state: str = "failed", **kw: Any) -> dict[str, Any]:
        return {"id": uuid.uuid4(), "trigger": "work", "state": state, "error_code": code,
                "reason": "owner_reply:F-1", "finished_at": now - timedelta(minutes=ago_min),
                **kw}  # fmt: skip

    async def check() -> None:
        soon, past = (
            (now + timedelta(hours=1)).isoformat(),
            (now - timedelta(minutes=1)).isoformat(),
        )
        # a quota refusal: after its reset (stored on its last step), never before five minutes
        assert await ACT.comes_back(Tx(soon), r("usage_limit", 10), now) is None
        assert await ACT.comes_back(Tx(past), r("usage_limit", 10), now) == ACT.REQUEUE
        assert await ACT.comes_back(Tx(past), r("usage_limit", 3), now) is None
        # its reset unknown: 30 minutes apart (12 of them outlast the router's 5-hour hold)
        assert await ACT.comes_back(Tx(None), r("quota_throttled", 10), now) is None
        assert await ACT.comes_back(Tx(None), r("quota_throttled", 31), now) == ACT.REQUEUE
        assert timedelta(hours=5) <= ACT.QUOTA_REQUEUES * ACT.QUOTA_UNKNOWN_GAP
        assert await ACT.comes_back(Tx(None), r("circuit_open", 2), now) is None
        many = r("quota_exhausted", 40, reason=ACT.REQUEUE * ACT.QUOTA_REQUEUES)
        assert await ACT.comes_back(Tx(None), many, now) is None
        # every account full: not before one has room again (a weekly window too)
        monday = now + timedelta(days=3)
        assert await ACT.comes_back(Tx(past), r("usage_limit", 40), now, monday) is None
        week = r("usage_limit", 3 * 24 * 60, queued_at=now - timedelta(days=3))
        assert await ACT.comes_back(Tx(None), week, now) == ACT.REQUEUE
        # older than a day, a passing failure is not looked at any more
        old = r("model_error", 26 * 60, queued_at=now - timedelta(hours=26))
        assert await ACT.comes_back(Tx(None), old, now) is None
        # a passing failure: once, five minutes later
        assert await ACT.comes_back(Tx(None), r("model_error", 6), now) == ACT.RETRY
        assert await ACT.comes_back(Tx(None), r("api_529", 6), now) == ACT.RETRY
        assert await ACT.comes_back(Tx(None), r("model_error", 2), now) is None
        assert await ACT.comes_back(Tx(None), r("model_error", 6, reason="retry:x"), now) is None
        assert await ACT.comes_back(Tx(None), r("busy_timeout", 6, "refused"), now) == ACT.RETRY
        assert await ACT.comes_back(Tx(None), r("invalid_output", 6, "refused"), now) is None
        # never a direct turn, a talk or a meeting run, never a cause that does not pass
        assert await ACT.comes_back(Tx(None), r("model_error", 6, trigger="direct"), now) is None
        assert await ACT.comes_back(Tx(None), r("auth_failed", 6), now) is None

    await check()


async def _failed(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    co: str,
    code: str,
    ago_min: int,
    retry_at: datetime | None = None,
) -> dict[str, Any]:
    """An order's CEO run that failed with `code` `ago_min` minutes ago (its last step names the
    reset when one is given)."""
    await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    assert (await agents.runner.claim(str(row["id"]))).state == "running"
    await su.execute(
        """UPDATE agents.runs SET state = 'failed', error_code = $2,
               finished_at = now() - make_interval(mins => $3)
           WHERE id = $1""",
        row["id"], code, ago_min,
    )  # fmt: skip
    if retry_at is not None:
        await su.execute(
            """INSERT INTO agents.steps (run_id, company_id, n, usage)
               VALUES ($1, $2, 1, $3::jsonb)""",
            row["id"], row["company_id"],
            json.dumps({"status": "refused", "code": code, "retry_at": retry_at.isoformat()}),
        )  # fmt: skip
    return row


async def test_quota_failed_runs_come_back_after_the_reset_and_a_passing_failure_once(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
    accounts: Any,  # an account has room (none full): the stored resets decide
) -> None:
    acts = ACT.Activities(
        agents.whub, None, router=agents.router, gateway=agents.gateway, live=agents.live
    )
    now = datetime.now(UTC)
    waits = (await new_company())["code"]
    w_row = await _failed(
        client, owner, su, agents, waits, "usage_limit", 10, now + timedelta(hours=1)
    )
    due = (await new_company())["code"]
    d_row = await _failed(
        client, owner, su, agents, due, "usage_limit", 10, now - timedelta(minutes=1)
    )
    flaky = (await new_company())["code"]
    f_row = await _failed(client, owner, su, agents, flaky, "model_error", 10)
    # a weekly window: the refusal three days ago comes back once its reset passed (nothing of its
    # cause ran since); the look-back of the other requeues stays one day
    weekly = (await new_company())["code"]
    k_row = await _failed(
        client, owner, su, agents, weekly, "usage_limit", 3 * 24 * 60, now - timedelta(hours=1)
    )
    stale = (await new_company())["code"]
    s_row = await _failed(client, owner, su, agents, stale, "model_error", 3 * 24 * 60)
    await su.execute("SET session_replication_role = replica")  # queued_at is immutable
    try:
        await su.execute(
            "UPDATE agents.runs SET queued_at = now() - interval '3 days' WHERE id = ANY($1)",
            [k_row["id"], s_row["id"]],
        )
    finally:
        await su.execute("SET session_replication_role = DEFAULT")
    await acts.requeue_runs()
    back_weekly = (await runs_of(su, f"{weekly}-CEO"))[-1]
    assert back_weekly["id"] != k_row["id"] and back_weekly["reason"].startswith(ACT.REQUEUE)
    assert (await runs_of(su, f"{stale}-CEO"))[-1]["id"] == s_row["id"]
    assert (await runs_of(su, f"{waits}-CEO"))[-1]["id"] == w_row["id"]  # its reset has not come
    back = (await runs_of(su, f"{due}-CEO"))[-1]
    assert back["id"] != d_row["id"] and back["reason"].startswith(ACT.REQUEUE)
    retried = (await runs_of(su, f"{flaky}-CEO"))[-1]
    assert retried["id"] != f_row["id"] and retried["reason"].startswith(ACT.RETRY)
    # the retry fails the same way: no loop
    assert (await agents.runner.claim(str(retried["id"]))).state == "running"
    await su.execute(
        """UPDATE agents.runs SET state = 'failed', error_code = 'model_error',
               finished_at = now() - interval '10 minutes' WHERE id = $1""",
        retried["id"],
    )
    await acts.requeue_runs()
    assert (await runs_of(su, f"{flaky}-CEO"))[-1]["id"] == retried["id"]


async def test_a_refused_model_call_stores_when_to_retry(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    real = agents.router.run

    async def refused(body: dict[str, Any], timeout_s: int) -> ModelCall:
        return ModelCall(False, "refused", "quota_throttled", None, None, None, None, None, None,
                         retry_after=900)  # fmt: skip

    agents.router.run = refused
    try:
        assert await run(agents, row["id"]) == {"state": "failed", "code": "quota_throttled"}
    finally:
        agents.router.run = real
    usage = json.loads(
        await su.fetchval("SELECT usage FROM agents.steps WHERE run_id = $1 AND n = 1", row["id"])
    )
    assert usage["code"] == "quota_throttled"
    at = datetime.fromisoformat(usage["retry_at"])
    assert timedelta(minutes=14) < at - datetime.now(UTC) <= timedelta(minutes=15)


# ------------------------------------------- a refused action is never claimed --
async def test_a_step_with_a_refused_action_gets_one_more_step_and_claims_nothing(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        f"{co}-CEO",
        step(
            "متن از ChatGPT گرفته شد و قدم ۳ تمام شد",
            ("nope.tool", {}),
            ("order.progress", {"ref": "F-0", "step_fa": "قدم ۳ تمام شد", "done": [3]}),
            ("work.get", {"ref": w["ref"]}),
        ),
        step("نشد؛ همین را به مدیر کل میگویم"),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    steps = await su.fetch(
        "SELECT n, summary_fa, actions, usage FROM agents.steps WHERE run_id = $1 ORDER BY n",
        row["id"],
    )
    assert [s["n"] for s in steps] == [1, 2]  # done:true next to a refusal did not end the run
    acts = json.loads(steps[0]["actions"])
    assert [a["outcome"] for a in acts] == ["denied", R.SKIPPED, "ok"]
    assert acts[0]["code"] == "unknown_tool"
    assert json.loads(steps[0]["usage"])["any_failed"] is True
    assert "any_failed" not in json.loads(steps[1]["usage"])
    # the model was told plainly what did not happen
    told = "".join(
        m.content
        for c in agents.fake.calls[since:]
        if c.actor_ref == f"{co}-CEO"
        for m in c.messages
    )
    assert "did NOT happen" in told and f"order.progress: {R.SKIPPED}" in told


async def test_an_owners_card_is_waiting_never_did_not_happen(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    """The gateway answers `denied / a3_requires_decision` when it raised the owner's card: the
    model is told it waits for his decision and must not call it again (a second card), not that
    it did not happen; alone, it does not keep the run going."""
    real = agents.gateway.call

    async def gateway(token: str, step_n: int, index: int, tool: str, args: Any) -> Any:
        if tool == "mcp.card":
            return {"outcome": "denied", "class": "A3", "code": R.DECISION, "ref": "D-0042",
                    "hint_fa": "کارت تصمیم برای مدیر کل رفت"}  # fmt: skip
        return await real(token, step_n, index, tool, args)

    agents.gateway.call = gateway
    try:
        co = (await new_company())["code"]
        await order(client, owner, co)
        alone = (await runs_of(su, f"{co}-CEO"))[-1]
        agents.fake.enqueue(f"{co}-CEO", step("کارت تصمیم رفت", ("mcp.card", {})))
        assert (await run(agents, alone["id"]))["state"] == "done"
        n = await su.fetchval("SELECT count(*) FROM agents.steps WHERE run_id = $1", alone["id"])
        assert n == 1  # nothing failed: the run ends on its done
        usage = json.loads(
            await su.fetchval("SELECT usage FROM agents.steps WHERE run_id = $1", alone["id"])
        )
        assert "any_failed" not in usage

        co2 = (await new_company())["code"]
        await order(client, owner, co2)
        row = (await runs_of(su, f"{co2}-CEO"))[-1]
        since = len(agents.fake.calls)
        agents.fake.enqueue(
            f"{co2}-CEO",
            step(
                "کارت رفت و قدم تمام شد",
                ("mcp.card", {}),
                ("order.progress", {"ref": "F-0", "step_fa": "تمام شد"}),
            ),
            step("منتظر تصمیم مدیر کل"),
        )
        assert (await run(agents, row["id"]))["state"] == "done"
        told = "".join(
            m.content
            for c in agents.fake.calls[since:]
            if c.actor_ref == f"{co2}-CEO"
            for m in c.messages
        )
        assert "mcp.card: waits for the owner's decision D-0042; a card was raised" in told
        assert "do not call it again" in told
        assert f"order.progress: {R.SKIPPED}" in told  # the claim after it is still not run
        assert "mcp.card: denied" not in told.split("did NOT happen", 1)[-1]
    finally:
        agents.gateway.call = real
    text = R.not_done_text([], True, [{"tool": "x", "code": R.DECISION, "ref": "D-1"}])
    assert "waits for the owner's decision D-1" in text and "did NOT happen" not in text
    assert R.not_done_text([], True, []) == ""
    assert not R.did_not_happen({"outcome": "denied", "code": R.DECISION})
    assert R.done_lines("کارت رفت", [{"tool": "x", "outcome": "denied", "code": R.DECISION}]) == [
        "کارت رفت"
    ]


def test_a_partial_output_lists_only_what_happened() -> None:
    ok = {"tool": "work.get", "outcome": "ok"}
    bad = {"tool": "nope.tool", "outcome": "denied", "code": "unknown_tool"}
    assert R.done_lines("قدم کامل", [ok]) == ["قدم کامل"]
    assert R.done_lines("فکر کردم", []) == ["فکر کردم"]
    assert R.done_lines("همه انجام شد", [bad]) == []
    lines = R.done_lines("همه انجام شد", [bad, ok])
    assert lines and "همه انجام شد" not in lines[0]
    assert R.claims("order.progress") and R.claims("message.owner") and R.claims("deliver")
    assert not R.claims("work.get") and not R.claims("order.ask")
    text = R.not_done_text([{**bad, "outcome": "denied"}], True)
    assert "nope.tool: denied (unknown_tool)" in text and "Your step said done" in text


def test_a_quota_refusal_carries_its_wait() -> None:
    from hq_api.agents.clients import _model_call

    body = {"status": "quota_exhausted", "error_class": "usage_limit", "retry_after": 1200,
            "call_id": "c", "connection": "claude-max"}  # fmt: skip
    call = _model_call(200, body)
    assert (call.ok, call.code, call.retry_after) == (False, "usage_limit", 1200)
    assert _model_call(200, {**body, "retry_after": True}).retry_after is None
    assert _model_call(503, {"error": "quota_throttled"}, "300").retry_after == 300
