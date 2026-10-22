"""Review of prompt 6 (06.1 §2-§3), the Code Workshop's control plane and the
managed adapter: the grant's actions in the adapter, the agent's permission
settings, every ask an approval, a queued session under a lock or an expired
grant, the advisor's reach, a lost cursor, the command's duration, /live
?after, the drivers' names and the events' company in the database."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pytest

from hq_api.domain import decisions as Dec
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.workshop import commands, service
from hq_api.workshop import domain as WS
from hq_api.workshop.runtime import FakeRuntime, permission_problems_of

from .conftest import agent_headers, idem, step_up
from .test_control_treasury_stream import serve
from .test_workshop import (  # noqa: F401 - fixtures
    FakeAnthropic,
    events,
    fake,
    grant,
    managed,
    open_session,
    owner,
    session,
    setup,
    tool,
)

SYSTEM = Principal(kind="service", code="test", role="service")


@pytest.fixture(autouse=True)
async def _finish_managed(su: Any) -> Any:
    """The fake Managed Agents API gives every session the id sesn_01: what a
    test leaves running is finished afterwards, so no later poll sees it."""
    yield
    await su.execute(
        """UPDATE workshop.sessions SET state = 'stopped', finished_at = now()
           WHERE runtime = 'managed' AND state NOT IN ('done', 'failed', 'stopped')"""
    )


def at(seconds: float) -> str:
    return (datetime(2026, 10, 22, 8, 0, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat()


# ------------------------------------------------- the grant in the adapter --
@pytest.mark.parametrize(
    ("cmd", "need"),
    [
        ("cat README.md", set()),
        ("grep -rn -i login src", set()),
        ("git status && git diff", set()),
        ("pytest -q", {"run"}),
        ("git commit -m fix", {"edit"}),
        ("sed -i s/a/b/ x.py", {"edit"}),
        ("echo hi > notes.txt", {"edit"}),
        ("ruff check --fix .", {"run", "edit"}),
        ("git push origin hq/S-0001", {"push_branch"}),
        ("gh pr create --fill", {"open_pr"}),
        ("ls 2>&1 | head", set()),
    ],
)
def test_what_each_command_needs_of_the_grant(cmd: str, need: set[str]) -> None:
    assert commands.needs(cmd) == need


async def test_a_read_only_grant_never_edits_pushes_or_opens_a_pr(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    su: Any,
) -> None:
    api = FakeAnthropic()
    hub.workshop = managed(api)
    try:
        g = await grant(client, hub, owner_session, setup["ws"], actions=["read"])
        r = await open_session(client, owner, g["ref"])
        assert r.status_code == 201, r.text
        ref = r.json()["ref"]
        assert "خواندن" in api.sent[0]["content"][0]["text"]  # the session is told its grant
        api.stream = [
            {"id": "sevt_1", "type": "agent.tool_use", "name": "write", "evaluated_permission": "ask",
             "input": {"file_path": "/workspace/repo/a.py"}},
            tool(2, "git commit -am fix"),
            tool(3, f"git push origin hq/{ref}"),
            tool(4, "gh pr create --fill"),
            tool(5, "pytest -q"),
            tool(6, "cat README.md"),
            {"id": "sevt_7", "type": "agent.tool_use", "name": "grep", "evaluated_permission": "ask",
             "input": {"pattern": "login"}},
        ]  # fmt: skip
        await service.sync(hub)
        sent = {e["tool_use_id"]: e["result"] for e in api.sent if e.get("tool_use_id")}
        assert sent == {
            "sevt_1": "deny",
            "sevt_2": "deny",
            "sevt_3": "deny",  # not even asked of the owner: the grant does not push
            "sevt_4": "deny",
            "sevt_5": "deny",
            "sevt_6": "allow",
            "sevt_7": "allow",
        }
        evs = await events(client, owner, ref)
        assert not [e for e in evs if e["type"] in ("approval_request", "file_change")]
        assert [e["data"]["code"] for e in evs if e["type"] == "error"] == ["not_granted"] * 5
        # ... and it takes no part of the work lock (it writes nothing).
        assert not await su.fetchval("SELECT writes FROM workshop.sessions WHERE ref = $1", ref)
    finally:
        hub.workshop = None


async def test_the_fake_runtime_keeps_to_the_grant_too(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    fake: FakeRuntime,  # noqa: F811
) -> None:
    g = await grant(client, hub, owner_session, setup["ws"], actions=["read"])
    ref = (await open_session(client, owner, g["ref"])).json()["ref"]
    kinds = {e["type"] for e in await events(client, owner, ref)}
    assert not kinds & {"command", "file_change", "approval_request"}
    g = await grant(client, hub, owner_session, setup["ws"])
    ref = (await open_session(client, owner, g["ref"], area="docs")).json()["ref"]
    [cmd, *_] = [e for e in await events(client, owner, ref) if e["type"] == "command"]
    assert cmd["data"] == {"cmd": "pytest -q", "exit_code": 0, "duration_s": 4.2}


# ------------------------------------------- the runtime's permission settings --
def test_only_an_agent_that_asks_before_every_tool_is_used() -> None:
    ask = {"type": "always_ask"}
    ok = {
        "tools": [{"type": "agent_toolset_20260401", "default_config": {"permission_policy": ask}}]
    }
    assert permission_problems_of(ok) == []
    assert permission_problems_of({"tools": [{"type": "agent_toolset_20260401"}]})  # always_allow
    one = {"tools": [{"type": "agent_toolset_20260401", "default_config": {"permission_policy": ask},
                      "configs": [{"name": "bash", "permission_policy": {"type": "auto"}}]}]}  # fmt: skip
    assert permission_problems_of(one) == ["agent_toolset_20260401/bash: auto"]
    off = {"tools": [{"type": "agent_toolset_20260401", "default_config": {"enabled": False},
                      "configs": [{"name": "read", "enabled": True, "permission_policy": ask}]}]}  # fmt: skip
    assert permission_problems_of(off) == []
    mcp = {"tools": [{"type": "mcp_toolset", "mcp_server_name": "gh",
                      "configs": [{"name": "merge", "permission_policy": {"type": "always_allow"}}]}]}  # fmt: skip
    assert permission_problems_of(mcp) == ["mcp gh/merge: always_allow"]
    assert permission_problems_of({"tools": [{"type": "custom", "name": "x"}]})


async def test_a_runtime_whose_agent_runs_tools_unasked_stays_off(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
) -> None:
    from types import SimpleNamespace

    class Bao:
        async def read_kv(self, path: str) -> dict[str, Any]:
            return {"api_key": "test-key", "agent_id": "agent_01", "environment_id": "e"}

    api = FakeAnthropic()
    api.agent["tools"][0]["default_config"]["permission_policy"] = {"type": "always_allow"}
    shell = SimpleNamespace(settings=SimpleNamespace(workshop_runtime="managed"), bao=Bao())
    assert await service.build(shell, transport=httpx.MockTransport(api.handler)) is None
    # Changed after the runtime was built: the session does not start.
    hub.workshop = managed(api)
    try:
        g = await grant(client, hub, owner_session, setup["ws"])
        ref = (await open_session(client, owner, g["ref"])).json()["ref"]
        assert (await session(client, owner, ref))["state"] == "failed"
        assert not [q for q in api.requests if q.url.path == "/v1/sessions"]
    finally:
        hub.workshop = None


async def test_every_other_ask_becomes_an_approval_and_unasked_runs_stop(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
) -> None:
    api = FakeAnthropic()
    hub.workshop = managed(api)
    try:
        g = await grant(client, hub, owner_session, setup["ws"])
        ref = (await open_session(client, owner, g["ref"])).json()["ref"]
        api.stream = [
            {"id": "sevt_1", "type": "agent.tool_use", "name": "web_fetch",
             "evaluated_permission": "ask", "input": {"url": "https://docs.python.org/3/"}},
            {"id": "sevt_2", "type": "agent.mcp_tool_use", "name": "create_issue",
             "server_name": "github", "evaluated_permission": "ask", "input": {}},
            {"id": "sevt_3", "type": "agent.tool_use", "name": "something_new",
             "evaluated_permission": "ask", "input": {}},
        ]  # fmt: skip
        await service.sync(hub)
        evs = await events(client, owner, ref)
        asks = [e for e in evs if e["type"] == "approval_request"]
        assert [a["data"]["action"] for a in asks] == ["command"] * 3
        assert (
            "docs.python.org" in asks[0]["data"]["detail"] and "github" in asks[1]["data"]["detail"]
        )
        assert (await session(client, owner, ref))["state"] == "waiting_approval"
        # A tool that ran without asking (the agent was changed): the session stops.
        api.stream.append(
            {"id": "sevt_4", "type": "agent.tool_use", "name": "bash",
             "evaluated_permission": "allow", "input": {"command": "rm -rf /"}}
        )  # fmt: skip
        await service.sync(hub)
        s = await session(client, owner, ref)
        assert s["state"] == "failed"
        assert {"type": "user.interrupt"} in api.sent
        assert any(
            e["type"] == "error" and e["data"].get("code") == "runtime_permission"
            for e in await events(client, owner, ref)
        )
    finally:
        hub.workshop = None


# --------------------------------------------- the command's duration, cursor --
async def test_commands_carry_their_duration_and_a_lost_cursor_never_doubles(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    su: Any,
) -> None:
    api = FakeAnthropic()
    hub.workshop = managed(api)
    try:
        g = await grant(client, hub, owner_session, setup["ws"])
        ref = (await open_session(client, owner, g["ref"])).json()["ref"]
        api.stream = [
            {**tool(1, "pytest -q"), "processed_at": at(0)},
            {"id": "sevt_2", "type": "agent.tool_result", "tool_use_id": "sevt_1",
             "is_error": False, "processed_at": at(12.5)},
            {"id": "sevt_3", "type": "span.model_request_end",
             "model_usage": {"input_tokens": 100, "output_tokens": 20}},
            tool(4, f"git push origin hq/{ref}"),
        ]  # fmt: skip
        await service.sync(hub)
        evs = await events(client, owner, ref)
        [cmd] = [e for e in evs if e["type"] == "command"]
        assert cmd["data"] == {"cmd": "pytest -q", "exit_code": 0, "duration_s": 12.5}
        # The runtime no longer lists the cursor: it replays everything.
        api.sent.clear()
        await su.execute(
            "UPDATE workshop.sessions SET external_cursor = 'sevt_gone' WHERE ref = $1", ref
        )
        api.stream.append(
            {"id": "sevt_5", "type": "user.tool_confirmation", "tool_use_id": "sevt_1",
             "result": "allow"}
        )  # fmt: skip
        await service.sync(hub)
        assert not [e for e in api.sent if e.get("tool_use_id") == "sevt_1"]  # answered already
        n = await su.fetchval(
            """SELECT count(*) FROM workshop.approvals a JOIN workshop.sessions s
               ON s.id = a.session_id WHERE s.ref = $1""",
            ref,
        )
        assert n == 1  # one approval for the push, however often it is reported
        s = await session(client, owner, ref)
        assert s["usage"]["input_tokens"] == 100  # never counted twice
    finally:
        hub.workshop = None


# ------------------------------------------- a queued session never starts --
async def _kill(
    client: httpx.AsyncClient, headers: dict[str, str], co: str, state: str, **h: str
) -> None:
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**headers, **h, **idem()},
        json={"scope": f"company:{co}", "state": state, "reason": "test"},
    )
    assert r.status_code == 200, r.text


async def test_a_queued_session_waits_out_a_lock_and_dies_with_its_grant(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    fake: FakeRuntime,  # noqa: F811
) -> None:
    fake.ask_push = False
    co = setup["co"]["code"]
    g = await grant(client, hub, owner_session, setup["ws"])
    a = (await open_session(client, owner, g["ref"])).json()
    b = (await open_session(client, owner, g["ref"])).json()
    assert b["held"] == "work_lock"
    await _kill(client, owner, co, "engaged")
    try:
        await client.post(
            f"/api/v1/workshop/sessions/{a['ref']}/stop", headers={**owner, **idem()}, json={}
        )
        assert b["ref"] not in fake.log_  # A's area is free, but the company is locked
        assert (await session(client, owner, b["ref"]))["state"] == "starting"
    finally:
        tok = await step_up(
            hub, owner_session["session_id"], "kill_switch.release", f"company:{co}"
        )
        await _kill(client, owner, co, "released", **tok)
    assert fake.log_[b["ref"]][0]["kind"] == "start"  # lifted: it starts by itself
    # A grant that expires while its session waits in line.
    short = await grant(
        client, hub, owner_session, setup["ws"],
        expires_at=(datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
    )  # fmt: skip
    await client.post(
        f"/api/v1/workshop/sessions/{b['ref']}/stop", headers={**owner, **idem()}, json={}
    )
    c = (await open_session(client, owner, short["ref"], area="src")).json()
    d = (await open_session(client, owner, short["ref"], area="src/x")).json()
    assert c["held"] is None and d["held"] == "work_lock"
    await asyncio.sleep(3.5)
    await client.post(
        f"/api/v1/workshop/sessions/{c['ref']}/stop", headers={**owner, **idem()}, json={}
    )
    d2 = await session(client, owner, d["ref"])
    assert d2["state"] == "stopped" and d["ref"] not in fake.log_
    assert (await events(client, owner, d["ref"]))[-1]["data"] == {"code": "grant_expired"}


# ------------------------------------------------------------- the advisor --
async def test_the_advisor_drives_no_other_companys_session(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    fake: FakeRuntime,  # noqa: F811
    su: Any,
) -> None:
    from .test_workshop import grant_body, signed_post

    r = await signed_post(
        client, hub, owner_session, "/api/v1/workshop/grants",
        grant_body(setup["ws"], driver="HQ-ADV"), "workshop.grant",
    )  # fmt: skip
    assert r.status_code == 422 and "driver" in r.text
    # Even a grant written past the api (an old row): the domain refuses the advisor.
    g = await su.fetchrow(
        """INSERT INTO workshop.grants (company_id, workspace_id, actions, driver_kind, driver_code,
               budget_usd, expires_at, granted_by_kind, granted_by_code)
           SELECT w.company_id, w.id, ARRAY['read'], 'agent', 'HQ-ADV', 1, now() + interval '1 day',
                  'owner', 'owner'
           FROM workshop.workspaces w WHERE w.code = $1
           RETURNING ref""",
        setup["ws"],
    )
    r = await client.post(
        "/internal/v1/workshop/sessions",
        headers={**await agent_headers("HQ-ADV"), **idem()},
        json={"grant": g["ref"], "title": "t"},
    )
    assert r.status_code in (403, 404), r.text  # its own company's rows only (RLS, OPA)
    await su.execute(  # the test's own run of the advisor ends, so later tests can run it
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = 'HQ-ADV' AND r.state = 'running'
             AND r.reason = 'test'"""
    )
    holding = await hub.companies.holding()
    adv = Principal(kind="agent", code="HQ-ADV", role="advisor", company=holding.code,
                    company_id=holding.id, scope="holding")  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:  # past RLS too: the domain refuses
        with pytest.raises(ApiError) as err:
            await WS.open_session(
                tx, adv, WS.direct_audit(adv), grant_ref=g["ref"], title="t", brief="",
                area="", model="m", effort="low", runtime="fake",
            )  # fmt: skip
    assert err.value.status == 403


# --------------------------------------------- names, /live?after, the database --
async def test_drivers_have_names_live_takes_after_and_events_keep_their_company(
    app: Any,
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],  # noqa: F811
    owner_session: dict[str, Any],
    setup: dict[str, Any],  # noqa: F811
    fake: FakeRuntime,  # noqa: F811
    su: Any,
) -> None:
    co = setup["co"]["code"]
    title = await su.fetchval("SELECT title_fa FROM core.employees WHERE code = $1", f"{co}-CEO")
    g = await grant(client, hub, owner_session, setup["ws"], driver=f"{co}-CEO")
    assert g["driver"] == {"kind": "agent", "code": f"{co}-CEO", "display_fa": title}
    r = await client.post(
        "/internal/v1/workshop/sessions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"grant": g["ref"], "title": "رفع باگ"},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["driver"]["display_fa"] == title and s["opened_by"]["display_fa"] == title
    ref = s["ref"]
    await client.post(f"/api/v1/workshop/sessions/{ref}/stop", headers={**owner, **idem()}, json={})
    total = len(await events(client, owner, ref))
    async with (
        serve(app) as url,
        httpx.AsyncClient(base_url=url, timeout=20) as c,
        c.stream("GET", f"/api/v1/workshop/sessions/{ref}/live?after=3", headers=owner) as resp,
    ):
        assert resp.status_code == 200
        seqs = [int(line[4:]) async for line in resp.aiter_lines() if line.startswith("id: ")]
    assert seqs == list(range(4, total + 1))
    other = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    sid = await su.fetchval("SELECT id FROM workshop.sessions WHERE ref = $1", ref)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await su.execute(
            """INSERT INTO workshop.events (session_id, company_id, seq, type, actor_kind,
                   actor_code) VALUES ($1, $2, 999, 'progress', 'system', 'x')""",
            sid,
            other,
        )


# -------------------------------------------------------- the card's seal --
async def test_a_code_session_card_grants_only_when_sealed(
    client: httpx.AsyncClient,
    hub: Hub,
    setup: dict[str, Any],  # noqa: F811
    su: Any,
) -> None:
    co = setup["co"]["code"]
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"kind": "code_session", "title": "رفع باگ", "why": "x",
              "payload": {"workspace": setup["ws"], "actions": ["read"], "budget_usd": "1"}},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    # Approved past the 🔏 route (no step-up): its effect makes no grant.
    await su.execute(
        """UPDATE cartable.decisions SET status = 'approved', decided_at = now(),
               decided_by_kind = 'owner', decided_by_code = 'owner', effect_status = 'pending'
           WHERE ref = $1""",
        ref,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        with pytest.raises(Exception) as err:
            await Dec.apply_effect(tx, ref, SYSTEM)
    assert "sealed" in str(err.value)
    assert not await su.fetchval(
        "SELECT 1 FROM workshop.grants g JOIN cartable.decisions d ON d.id = g.decision_id WHERE d.ref = $1",
        ref,
    )
