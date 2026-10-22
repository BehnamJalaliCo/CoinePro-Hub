"""Prompt 12 part A in llm-router: the owner zone's share (§15, contract §21.0)
and a new connection verified at no token cost (§9, contract §21.7)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import asyncpg
import httpx
import pytest

from hq_common import owner_zone
from llm_router import verify
from llm_router.schemas import RunRequest
from llm_router.service import RouterError

from .conftest import FakeBackend, ok_result


def req(**kw: Any) -> RunRequest:
    base: dict[str, Any] = {
        "company_code": "HQ",
        "actor_ref": "HQ-ADV",
        "department": None,
        "role": "advisor",
        "task_class": "advisor_memo",
        "priority": 2,
        "prompt": "Say OK",
        "timeout_s": 30,
    }
    base.update(kw)
    return RunRequest(**base)


async def test_the_owner_zone_share_stops_automatic_runs_but_never_the_owners_own(
    su: asyncpg.Connection, make_service: Any
) -> None:
    # 0.25 of a 1000-token day = 250 tokens for the zone's automatic runs.
    svc = make_service(
        subscription=FakeBackend(
            ok_result(input_tokens=130, output_tokens=20),
            ok_result(input_tokens=100, output_tokens=20),
        )
    )
    svc.s = replace(svc.s, agent_daily_token_cap=1000, owner_zone_daily_share=0.25)
    auto = {"owner_zone": "auto", "run_id": "r1"}
    await svc.run(req(meta=auto), "t", 10_000)  # 150 used
    await svc.run(req(task_class="advisor_proactive", meta=auto), "t", 10_000)  # 270 used
    for tc in ("advisor_memo", "advisor_proactive", "advisor_review", "dceo_predict"):
        with pytest.raises(RouterError) as exc:
            await svc.run(req(task_class=tc, meta=auto), "t", 10_000)
        assert (exc.value.code, exc.value.status_code) == ("budget_exhausted", 429)
        assert exc.value.retry_after and exc.value.retry_after <= 86_400
        row = await su.fetchrow(
            "SELECT status, error_class FROM llm.calls WHERE id = $1", exc.value.call_id
        )
        assert tuple(row) == ("rejected_budget", "owner_zone_share")
    # A call without the flag is automatic too (the safe side).
    with pytest.raises(RouterError):
        await svc.run(req(), "t", 10_000)
    # What the owner asked for directly always runs (inside the overall cap).
    assert (await svc.run(req(meta={"owner_zone": "direct"}), "t", 10_000)).status == "ok"
    assert (await svc.run(req(task_class="ask_hub", meta={"owner_zone": "direct"}), "t", 10_000)).status == "ok"
    # Outside the zone nothing changes (the advisor's own conversation, a company).
    assert (await svc.run(req(task_class="advisor"), "t", 10_000)).status == "ok"
    assert (await svc.run(req(task_class="ceo_letter", company_code="TY", actor_ref="TY-CEO",
                              role="ceo"), "t", 10_000)).status == "ok"  # fmt: skip
    svc.s = replace(svc.s, agent_daily_token_cap=0)  # a cap of 0: no share either
    with pytest.raises(RouterError):
        await svc.run(req(meta={"owner_zone": "auto"}), "t", 10_000)


def test_owner_zone_parsing_and_the_zone() -> None:
    assert owner_zone.parse_share(None) == owner_zone.parse_share(" ") == 0.25
    assert owner_zone.parse_share("0.4") == 0.4
    for bad in ("-0.1", "1.01", "nan", "a quarter"):
        with pytest.raises(ValueError):
            owner_zone.parse_share(bad)
    assert owner_zone.limit(600_000, 0.25) == 150_000 and owner_zone.limit(0, 0.25) == 0
    assert owner_zone.applies("advisor_memo", "auto") and owner_zone.applies("ask_hub", None)
    assert not owner_zone.applies("advisor_memo", "direct")
    assert not owner_zone.applies("ceo_letter", "auto") and not owner_zone.applies("advisor", "auto")


# --------------------------------------------------------- a new connection --
async def _new_statuses(su: asyncpg.Connection) -> None:
    """The api's migration 0027 widens the router's tables; the router-only
    test database gets the same here."""
    await su.execute(
        """ALTER TABLE llm.connections ADD COLUMN IF NOT EXISTS verified_at timestamptz;
           ALTER TABLE llm.connections DROP CONSTRAINT IF EXISTS connections_status_check;
           ALTER TABLE llm.connections ADD CONSTRAINT connections_status_check
               CHECK (status IN ('enabled', 'disabled', 'quota_exhausted', 'pending_secret',
                                 'verifying', 'ready', 'error'));
           GRANT UPDATE (verified_at) ON llm.connections TO hq_llm_writer;"""
    )


async def _connection(su: asyncpg.Connection, key: str, provider: str, status: str,
                      base: str | None = None) -> None:  # fmt: skip
    await su.execute("DELETE FROM llm.connections WHERE key = $1", key)
    await su.execute(
        """INSERT INTO llm.connections (key, kind, provider, display_name, status, secret_ref, api_base,
               models, default_model)
           VALUES ($1, 'api', $2, $1, $3, 'kv/llm-connections/' || $1, $4, '["m-1"]', 'm-1')""",
        key,
        provider,
        status,
        base,
    )


class Pool:
    """The scan reads through db.pool.acquire() (the router's own pool)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool


async def test_a_new_connection_is_verified_by_its_model_list_and_never_while_locked(
    su: asyncpg.Connection, db: Any
) -> None:
    await _new_statuses(su)
    await _connection(su, "p12a-good", "openai", "verifying")
    await _connection(su, "p12a-bad", "mistral", "verifying")
    await _connection(su, "p12a-wait", "deepseek", "pending_secret")
    await _connection(su, "p12a-private", "openai_compatible", "verifying", "https://llm.example.org/v1")
    secrets = {
        "llm-connections/p12a-good": {"api_key": "sk-test-good-0000000000"},
        "llm-connections/p12a-bad": {"api_key": "sk-test-bad-00000000000"},
        "llm-connections/p12a-private": {"api_key": "sk-test-private-0000000"},
    }
    seen: list[httpx.Request] = []

    async def read(path: str) -> dict[str, Any]:
        if path not in secrets:
            raise KeyError(path)
        return secrets[path]

    def provider(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "mistral" in request.url.host:
            return httpx.Response(401, json={"error": "invalid key"})
        return httpx.Response(200, json={"data": [{"id": "m-1"}, {"id": "m-2"}]})

    async def resolve(host: str, port: int) -> list[str]:
        return ["10.10.1.2"] if host == "llm.example.org" else ["93.184.216.34"]

    client = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    locked = await verify.scan(db, read, _lock("holding"), client=client, resolve=resolve)
    assert locked == {"checked": 0, "skipped": "holding_locked"} and seen == []
    out = await verify.scan(db, read, _lock(None), client=client, resolve=resolve)
    assert out["ready"] == 1 and out["error"] == 2 and out["waiting"] == 1
    rows = {
        r["key"]: (r["status"], r["status_reason"], r["verified_at"] is not None)
        for r in await su.fetch(
            "SELECT key, status, status_reason, verified_at FROM llm.connections WHERE key LIKE 'p12a-%'"
        )
    }
    assert rows["p12a-good"] == ("ready", "verified: 2 models listed", True)
    assert rows["p12a-bad"][:2] == ("error", "the provider refused the key (401)")
    assert rows["p12a-private"][0] == "error" and "not public (private)" in rows["p12a-private"][1]
    assert rows["p12a-wait"][0] == "pending_secret"
    # One call each (the model list), never to the private address, and the key
    # only in the provider's own header; no reason carries it.
    assert [r.url.host for r in seen] == ["api.openai.com", "api.mistral.ai"]
    assert seen[0].headers["authorization"] == "Bearer sk-test-good-0000000000"
    assert "sk-test" not in json.dumps({k: v[1] for k, v in rows.items()})
    # The terminal route: the key appears in OpenBao -> verified on the next pass.
    secrets["llm-connections/p12a-wait"] = {"api_key": "sk-test-wait-0000000000"}
    await verify.scan(db, read, _lock(None), client=client, resolve=resolve)
    assert await su.fetchval("SELECT status FROM llm.connections WHERE key = 'p12a-wait'") == "ready"
    await su.execute("DELETE FROM llm.connections WHERE key LIKE 'p12a-%'")


def _lock(state: str | None) -> Any:
    async def lock_state(company_id: str) -> str | None:
        return state

    return lock_state


def test_the_guard_refuses_what_is_not_public() -> None:
    for addr, why in (("10.10.1.2", "private"), ("127.0.0.1", "loopback"),
                      ("169.254.169.254", "link_local"), ("100.64.0.1", "cgnat"),
                      ("::1", "loopback"), ("fd00::1", "private"), ("224.0.0.1", "reserved")):  # fmt: skip
        assert verify.not_public(addr) == why, addr
    assert verify.not_public("93.184.216.34") is None
    assert verify.models_url("google", None).startswith("https://generativelanguage.googleapis.com")
    assert verify.models_url("openai_compatible", "https://x.example/v1/") == "https://x.example/v1/models"
    with pytest.raises(ValueError):
        verify.models_url("openai_compatible", None)
    assert verify.auth_headers("anthropic", "k")["x-api-key"] == "k"


async def test_a_connection_not_verified_or_a_substitutes_never_takes_a_call(
    su: asyncpg.Connection, make_service: Any
) -> None:
    await _new_statuses(su)
    svc = make_service(subscription=FakeBackend(), api=FakeBackend(ok_result()))
    for status in ("pending_secret", "verifying", "error"):
        await su.execute("UPDATE llm.connections SET status = $1 WHERE key = 'claude-max'", status)
        with pytest.raises(RouterError) as exc:
            await svc.run(req(task_class="general", company_code="TY", actor_ref="TY-TECH-01",
                              role="sre", department="TECH"), "t", 10_000)  # fmt: skip
        assert exc.value.code == "connection_disabled"
    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = 'claude-max'")
