"""⟨2026-11-27⟩ Gemini 4 Hydrogen (Antigravity, the runner's agy executor >= 0.4.0).

- A turn whose model is a Gemini one runs only on a runner that says it runs agy
  (X-HQ-Runner-Agy: 1), never with a Claude account, and its usage is booked to Google.
- The owner's fallback: while no Claude account has room, a Claude turn picked up by such a runner
  runs on gemini-4-hydrogen-xhigh (recorded on the job, its work and in Audit), and Claude takes the
  turns again once an account has room. A turn that a limit stopped before it did anything runs
  again on Hydrogen at once. `hydrogen_fallback` in owner.settings.flows_off switches it off.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import asyncpg
import httpx
import pytest

from hq_api.domain import servers as SV
from hq_api.hub import Hub

from .test_p17_runners import pair, poll
from .test_w23_quota import MAIN, SECOND, _claude_job, _job, accounts  # noqa: F401 - a fixture

API = "/api/v1"
AGY_HEADERS = {"X-HQ-Runner-Version": "0.4.0", "X-HQ-Runner-Agy": "1"}
NO_AGY_HEADERS = {"X-HQ-Runner-Version": "0.4.0"}


def test_the_rules_of_a_hydrogen_turn() -> None:
    hub = SimpleNamespace(
        secrets=SimpleNamespace(runner_claude_token_main=MAIN, runner_claude_token="")
    )
    none = SimpleNamespace(
        secrets=SimpleNamespace(runner_claude_token_main="", runner_claude_token="")
    )
    assert SV.claude_has_room(hub, SV.AccountPick(key="claude-max", token=MAIN))
    assert not SV.claude_has_room(hub, SV.AccountPick(hold=True))
    # every stored account switched off or refused: no room either
    assert not SV.claude_has_room(hub, SV.NO_PICK)
    # nothing stored at all: the server's own login, as before
    assert SV.claude_has_room(none, SV.NO_PICK)
    job = {"id": uuid.uuid4(), "kind": "claude", "args": {"brief": "x", "model": "gemini-4-hydrogen-xhigh"},
           "timeout_s": 600, "created_at": datetime.now(UTC), "session_ref": None,
           "actor_kind": "owner", "actor_code": "owner", "server_id": uuid.uuid4(), "company": "PC"}  # fmt: skip
    assert SV.is_agy_job(job) and not SV.is_agy_job({**job, "kind": "exec"})
    assert "claude_oauth" not in SV.runner_job(job, hub, claude_token=MAIN)
    args = {"brief": "x", "model": "claude-opus-5-5", "effort": "max"}
    mark = SV.hydrogen_mark(args, "no_room")
    moved = SV.hydrogen_args(args, mark)
    assert moved["model"] == SV.HYDROGEN and moved["fallback"]["from"] == "claude-opus-5-5"
    assert moved["fallback"]["why"] == "no_room" and moved["effort"] == "max"
    # a job the hub moved: the runner gets the Hydrogen model, never a Claude token
    claude = {**job, "args": args, "usage": {"hydrogen": mark}}
    assert SV.is_agy_job(claude)
    out = SV.runner_job(claude, hub, claude_token=MAIN)
    assert out["args"]["model"] == SV.HYDROGEN and "claude_oauth" not in out


async def _full(su: asyncpg.Connection, key: str) -> None:
    cid = await su.fetchval("SELECT id FROM llm.connections WHERE key = $1", key)
    await su.execute(
        """INSERT INTO llm.quota_status (connection_id, status, window_kind, utilization,
                resets_at, source, observed_at)
            VALUES ($1, 'limited', 'seven_day', 1, now() + interval '1 day', 'sdk_rate_limit_event', now())
            ON CONFLICT (connection_id) DO UPDATE SET status = 'limited', utilization = 1,
                resets_at = EXCLUDED.resets_at, observed_at = now(), windows = '{}'""",
        cid,
    )


async def _clear_quota(su: asyncpg.Connection) -> None:
    await su.execute(
        """DELETE FROM llm.quota_status WHERE connection_id IN
             (SELECT id FROM llm.connections WHERE key = ANY($1))""",
        ["claude-max", "claude-max-2"],
    )


async def _poll(client: httpx.AsyncClient, rn: dict[str, Any], extra: dict[str, str]) -> Any:
    r = await poll(client, {**rn, "h": {**rn["h"], **extra}})
    assert r.status_code in (200, 204), r.text
    return r.json()["job"] if r.status_code == 200 else None


async def _args(su: asyncpg.Connection, jid: str) -> dict[str, Any]:
    raw = await su.fetchval("SELECT args FROM infra.server_jobs WHERE id = $1", uuid.UUID(jid))
    return dict(json.loads(raw))


@pytest.mark.usefixtures("accounts")
async def test_gemini_turns_and_the_fallback(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: asyncpg.Connection,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    sid = rn["server"]["id"]
    off_before = await su.fetchval("SELECT flows_off FROM owner.settings WHERE id = 1")
    await su.execute(
        "UPDATE owner.settings SET flows_off = array_remove(flows_off, $1) WHERE id = 1",
        SV.HYDROGEN_OFF_KEY,
    )
    try:
        # 1. a Gemini turn waits for a runner that runs agy, and never carries a Claude token
        gem = await _claude_job(hub, sid, model="gemini-4-hydrogen-xhigh")
        assert await _poll(client, rn, NO_AGY_HEADERS) is None
        labels = await su.fetchval("SELECT labels FROM infra.servers WHERE id = $1", uuid.UUID(sid))
        assert json.loads(labels)["agy"] is False
        job = await _poll(client, rn, AGY_HEADERS)
        assert job is not None and job["id"] == gem and "claude_oauth" not in job
        assert job["args"]["model"] == "gemini-4-hydrogen-xhigh"
        assert "account" not in ((await _job(su, gem))["usage"] or {})
        r = await client.post(
            f"{API}/runners/jobs/{gem}/result",
            json={"exit_code": 0, "summary_fa": "نشست Hydrogen (Antigravity) روی سرور تمام شد.",
                  "usage": {"input_tokens": 23000, "output_tokens": 180, "thinking_tokens": 80,
                            "model": "gemini-4-hydrogen-xhigh", "executor": "agy",
                            "session_id": "agy:c5279625"},
                  "data": {"result_fa": "DONE", "session_id": "agy:c5279625", "executor": "agy"}},
            headers={**rn["h"], **AGY_HEADERS},
        )  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "done", r.text
        booked = await su.fetchrow(
            """SELECT provider, task_class, model, connection_id, meta FROM llm.calls
               WHERE meta->>'server_job' = $1""",
            gem,
        )
        assert (booked["provider"], booked["task_class"], booked["model"]) == (
            "google", "server_agy", "gemini-4-hydrogen-xhigh",
        )  # fmt: skip
        assert booked["connection_id"] is None
        assert json.loads(booked["meta"])["quota"] == "agy_google"

        # 2. Claude has room: a Claude turn runs on Claude, on the main account
        cl = await _claude_job(hub, sid, model="claude-opus-5-5")
        job = await _poll(client, rn, AGY_HEADERS)
        assert job["id"] == cl and job["claude_oauth"] == MAIN
        assert job["args"]["model"] == "claude-opus-5-5"
        await client.post(f"{API}/runners/jobs/{cl}/result", json={"exit_code": 0},
                          headers=rn["h"])  # fmt: skip

        # 3. both accounts full: the Claude turn runs on Hydrogen at once (not held)
        await _full(su, "claude-max")
        await _full(su, "claude-max-2")
        cl2 = await _claude_job(hub, sid, model="claude-opus-5-5", effort="max")
        # a runner without agy holds it, as before
        assert await _poll(client, rn, NO_AGY_HEADERS) is None
        job = await _poll(client, rn, AGY_HEADERS)
        assert job is not None and job["id"] == cl2 and "claude_oauth" not in job
        assert job["args"]["model"] == SV.HYDROGEN
        assert job["args"]["fallback"]["from"] == "claude-opus-5-5"
        assert job["args"]["fallback"]["why"] == "no_room"
        # the stored args stay as made; the move is booked beside the account
        assert (await _args(su, cl2))["model"] == "claude-opus-5-5"
        assert (await _job(su, cl2))["usage"]["hydrogen"]["why"] == "no_room"
        assert await su.fetchval(
            "SELECT 1 FROM audit.entries WHERE target_ref = $1 AND summary LIKE '%moved to gemini%'",
            cl2,
        )
        await client.post(f"{API}/runners/jobs/{cl2}/result", json={"exit_code": 0},
                          headers=rn["h"])  # fmt: skip

        # 4. the owner's switch off: the Claude turns wait again
        await su.execute(
            "UPDATE owner.settings SET flows_off = array_append(flows_off, $1) WHERE id = 1",
            SV.HYDROGEN_OFF_KEY,
        )
        cl3 = await _claude_job(hub, sid, model="claude-opus-5-5")
        assert await _poll(client, rn, AGY_HEADERS) is None
        await su.execute(
            "UPDATE owner.settings SET flows_off = array_remove(flows_off, $1) WHERE id = 1",
            SV.HYDROGEN_OFF_KEY,
        )

        # 5. Claude has room again: back on Claude by itself
        await _clear_quota(su)
        job = await _poll(client, rn, AGY_HEADERS)
        assert job["id"] == cl3 and job["claude_oauth"] == MAIN
        assert job["args"]["model"] == "claude-opus-5-5"

        # 6. a turn the limit stopped before it did anything, the other account full: the same
        # turn again on Hydrogen at once
        await _full(su, "claude-max-2")
        r = await client.post(
            f"{API}/runners/jobs/{cl3}/result",
            json={"exit_code": 1, "summary_fa": "نشست Claude با کد خروج 1 تمام شد.",
                  "usage": {"input_tokens": 40, "output_tokens": 2, "model": "claude-opus-5-5"},
                  "data": {"result_fa": f"Claude AI usage limit reached|{int(time.time()) + 7200}"}},
            headers=rn["h"],
        )  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "failed", r.text
        old = await _job(su, cl3)
        assert (old["error_code"], old["summary_fa"]) == (SV.USAGE_LIMIT, SV.HYDROGEN_MOVED_FA)
        again = await su.fetchval(
            "SELECT id::text FROM infra.server_jobs WHERE usage->>'retry_of' = $1 AND state = 'queued'",
            cl3,
        )
        assert again is not None
        assert (await _job(su, again))["usage"]["hydrogen"]["why"] == "limit"
        job = await _poll(client, rn, AGY_HEADERS)
        assert job["id"] == again and "claude_oauth" not in job
        assert job["args"]["model"] == SV.HYDROGEN and job["args"]["fallback"]["why"] == "limit"
        # a Hydrogen turn's usage is never booked to a Claude account
        r = await client.post(
            f"{API}/runners/jobs/{again}/result",
            json={"exit_code": 0, "usage": {"input_tokens": 9, "output_tokens": 1,
                                            "model": SV.HYDROGEN, "executor": "agy"},
                  "data": {"result_fa": "ok"}},
            headers=rn["h"],
        )  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "done", r.text
        prov = await su.fetchval(
            "SELECT provider FROM llm.calls WHERE meta->>'server_job' = $1", again
        )
        assert prov == "google"
    finally:
        await _clear_quota(su)
        await su.execute("UPDATE owner.settings SET flows_off = $1 WHERE id = 1", off_before or [])
        await su.execute(
            "UPDATE infra.server_jobs SET state = 'cancelled' WHERE server_id = $1 AND state IN ('queued', 'running')",
            uuid.UUID(sid),
        )
