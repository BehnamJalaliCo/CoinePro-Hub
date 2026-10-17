"""Control (423, kill switch, deploy freeze), policy (A4, fail-closed), audit,
Token Treasury, the live stream, and "no text or secret leaves" checks."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import uvicorn

from hq_api.app import create_app
from hq_api.hub import Hub
from hq_api.policy import Policy

from .conftest import agent_headers, idem, signed_put, step_up


async def _work_for_ceo(
    client: httpx.AsyncClient, owner: dict[str, str], co: str
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/work", headers={**owner, **idem()}, json={"company": co, "title": "کار"}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_company_kill_switch_locks_agents_and_release_needs_step_up(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    w = await _work_for_ceo(client, h, co)
    ceo = agent_headers(f"{co}-CEO")
    engage = {"scope": f"company:{co}", "state": "engaged", "reason": "حادثه"}
    assert (
        await client.post("/api/v1/control/kill-switch", headers=h, json=engage)
    ).status_code == 422  # key
    r = await client.post("/api/v1/control/kill-switch", headers={**h, **idem()}, json=engage)
    assert r.status_code == 200
    assert next(c for c in r.json()["companies"] if c["company"] == co)["state"] == "engaged"

    r = await client.post(f"/internal/v1/work/{w['id']}/accept", headers=ceo)
    assert r.status_code == 423 and r.json()["code"] == "company_locked"
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={"kind": "proposal", "title": "x", "payload": {}},
    )
    assert r.status_code == 423
    assert (await client.get(f"/internal/v1/context/{co}-CEO", headers=ceo)).json()["company"][
        "locked"
    ] == "company"
    # the owner is never locked out
    assert (
        await client.post(
            "/api/v1/work", headers={**h, **idem()}, json={"company": co, "title": "مالک"}
        )
    ).status_code == 201

    release = {**engage, "state": "released", "reason": "حل شد"}
    r = await client.post("/api/v1/control/kill-switch", headers={**h, **idem()}, json=release)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su = await step_up(hub, sid, "kill_switch.release", f"company:{co}")
    r = await client.post(
        "/api/v1/control/kill-switch", headers={**h, **su, **idem()}, json=release
    )
    assert r.status_code == 200
    assert (
        await client.post(f"/internal/v1/work/{w['id']}/accept", headers=ceo)
    ).status_code == 200

    audit = (
        await client.get(
            "/api/v1/audit", headers=h, params={"company": co, "action": "kill_switch.release"}
        )
    ).json()
    assert audit["items"][0]["step_up"] is True
    v = (await client.get("/api/v1/audit/verify", headers=h)).json()
    assert v["ok"] is True and v["checked"] > 0 and v["first_bad_seq"] is None


async def test_ceo_switch_own_company_only_and_holding_switch(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co, other = (await new_company())["code"], (await new_company())["code"]
    ceo = agent_headers(f"{co}-CEO")
    own = {"scope": f"company:{co}", "state": "engaged", "reason": "x"}
    assert (
        await client.post("/internal/v1/control/kill-switch", headers={**ceo, **idem()}, json=own)
    ).status_code == 200
    r = await client.post(
        "/internal/v1/control/kill-switch",
        headers={**ceo, **idem()},
        json={**own, "state": "released"},
    )
    assert r.status_code == 200  # a CEO may release its own company too
    for scope in (f"company:{other}", "holding"):
        r = await client.post(
            "/internal/v1/control/kill-switch",
            headers={**ceo, **idem()},
            json={**own, "scope": scope},
        )
        assert r.status_code == 403, scope
    mgr = agent_headers(f"{co}-TECH-MGR")
    assert (
        await client.post("/internal/v1/control/kill-switch", headers={**mgr, **idem()}, json=own)
    ).status_code == 403

    w = await _work_for_ceo(client, h, other)
    try:
        r = await client.post(
            "/api/v1/control/kill-switch",
            headers={**h, **idem()},
            json={"scope": "holding", "state": "engaged", "reason": "توقف کامل"},
        )
        assert r.json()["holding"]["state"] == "engaged"
        r = await client.post(
            f"/internal/v1/work/{w['id']}/accept", headers=agent_headers(f"{other}-CEO")
        )
        assert r.status_code == 423 and "holding" in r.json()["detail"]
    finally:
        su = await step_up(hub, sid, "kill_switch.release", "holding")
        r = await client.post(
            "/api/v1/control/kill-switch",
            headers={**h, **su, **idem()},
            json={"scope": "holding", "state": "released", "reason": "پایان"},
        )
        assert r.json()["holding"]["state"] == "released"


async def test_deploy_freeze(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    w = await _work_for_ceo(client, owner, co)
    until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await client.post(
        "/api/v1/control/deploy-freeze",
        headers=owner,
        json={"company": co, "until": until, "reason": "deploy"},
    )
    assert r.json()["active"] is True
    state = (await client.get("/api/v1/control/state", headers=owner)).json()
    assert any(f["company"] == co for f in state["deploy_freezes"])
    assert (
        await client.post(f"/internal/v1/work/{w['id']}/accept", headers=agent_headers(f"{co}-CEO"))
    ).status_code == 423
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    r = await client.post(
        "/api/v1/control/deploy-freeze",
        headers=owner,
        json={"company": co, "until": past, "reason": "done"},
    )
    assert r.json()["active"] is False
    assert (
        await client.post(f"/internal/v1/work/{w['id']}/accept", headers=agent_headers(f"{co}-CEO"))
    ).status_code == 200


async def test_a4_is_always_denied_for_agents(hub: Hub) -> None:
    agent = {
        "kind": "agent",
        "code": "TY-CEO",
        "role": "ceo",
        "company": "TY",
        "department": None,
        "status": "active",
    }
    owner = {"kind": "owner", "code": "owner", "role": "owner", "company": None, "department": None}
    for name in (
        "trade.execute",
        "money.withdraw",
        "data.delete",
        "backup.delete",
        "access.change",
    ):
        v = await hub.policy.query(
            "actions",
            {
                "principal": agent,
                "action": {"class": "A4", "name": name, "company": "TY"},
                "context": {"escrow_classes": ["A0", "A1", "A2"], "company_locked": False},
            },
        )
        assert not v.allow and "a4_forbidden_for_ai" in v.reasons
    v = await hub.policy.query(
        "actions",
        {
            "principal": owner,
            "action": {"class": "A4", "name": "data.delete", "company": "TY"},
            "context": {"escrow_classes": [], "company_locked": True},
        },
    )
    assert v.allow


async def test_policy_down_means_denied(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = (await new_company())["code"]
    dead = replace(hub, policy=Policy("http://127.0.0.1:9", timeout=0.5))
    app = create_app(dead)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://hq.test"
    ) as c:
        r = await c.post(
            "/internal/v1/decisions",
            headers={**agent_headers(f"{co}-CEO"), **idem()},
            json={"kind": "proposal", "title": "x", "payload": {}},
        )
    assert r.status_code == 503 and r.json()["code"] == "policy_unavailable"
    await dead.policy.aclose()


class FakeBao:
    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def write_kv(self, path: str, data: dict[str, Any]) -> None:
        self.writes.append((path, data))


async def test_treasury_read_side_and_owner_controls(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = await new_company()
    conn_id = await su.fetchval("SELECT id FROM llm.connections WHERE key = 'claude-max'")
    for i, (actor, inp, out, cost) in enumerate(
        [("A-1", 1000, 200, "0.0040"), ("A-2", 5000, 1000, "0.0200")]
    ):
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, task_class, priority, caller,
                   connection_id, model, effort, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                   equiv_cost_usd, status)
               VALUES ($1, now() - make_interval(mins => $2), now(), $3, $4, 'general', 3, 'test', $5,
                       'claude-sonnet-5-5', 'medium', $6, $7, 0, 0, $8::numeric, 'ok')""",
            uuid.uuid4(),
            i,
            co["id"],
            f"{co['code']}-{actor}",
            conn_id,
            inp,
            out,
            cost,
        )
    s = (
        await client.get(
            "/api/v1/treasury/summary", headers=h, params={"company": co["code"], "period": "day"}
        )
    ).json()
    assert (
        s["totals"]["calls"] == 2
        and s["totals"]["input_tokens"] == 6000
        and float(s["totals"]["equiv_cost_usd"]) == 0.024
    )
    assert s["top_consumers"][0]["actor"] == f"{co['code']}-A-2"
    b = (
        await client.get(
            "/api/v1/treasury/breakdown", headers=h, params={"by": "actor", "company": co["code"]}
        )
    ).json()
    assert len(b) == 2
    calls = (
        await client.get(
            "/api/v1/treasury/calls", headers=h, params={"company": co["code"], "limit": 1}
        )
    ).json()
    assert len(calls["items"]) == 1 and calls["next_cursor"]
    assert "prompt" not in json.dumps(calls) and "response" not in calls["items"][0]
    more = (
        await client.get(
            "/api/v1/treasury/calls",
            headers=h,
            params={"company": co["code"], "cursor": calls["next_cursor"]},
        )
    ).json()
    assert len(more["items"]) == 1
    wi = (
        await client.get(
            "/api/v1/treasury/what-if",
            headers=h,
            params={"model": "claude-haiku-5-5", "company": co["code"]},
        )
    ).json()
    # 6000 input x 0.10 + 1200 output x 0.50 per 1M = 0.0012 on Haiku 5.5 instead of 0.024
    assert wi["priced_calls"] == 2 and float(wi["what_if_usd"]) == pytest.approx(0.0012)
    assert wi["source_url"].startswith("https://")

    conns = (await client.get("/api/v1/connections", headers=h)).json()
    assert conns[0]["key"] == "claude-max" and all("api_key" not in json.dumps(c) for c in conns)
    api = next(c for c in conns if c["key"] == "anthropic-api")
    patch = {"display_name": "Anthropic API (owner)"}
    assert (
        await client.patch(
            f"/api/v1/connections/{api['id']}",
            headers={**h, "If-Match": str(api["version"])},
            json=patch,
        )
    ).status_code == 403
    st = await step_up(hub, sid, "connection.update", api["id"])
    r = await client.patch(
        f"/api/v1/connections/{api['id']}",
        headers={**h, **st, "If-Match": str(api["version"])},
        json=patch,
    )
    assert r.status_code == 200 and r.json()["display_name"] == "Anthropic API (owner)"

    secret = "sk-test-SECRET-MARKER-" + uuid.uuid4().hex
    fake = FakeBao()
    hub.bao = fake
    try:
        assert (
            await client.post(
                f"/api/v1/connections/{api['id']}/secret", headers=h, json={"secret": secret}
            )
        ).status_code == 403
        st = await step_up(hub, sid, "connection.secret", api["id"])
        r = await client.post(
            f"/api/v1/connections/{api['id']}/secret", headers={**h, **st}, json={"secret": secret}
        )
        assert r.status_code == 200 and r.json() == {"connection": "anthropic-api", "stored": True}
        assert fake.writes == [("llm-connections/anthropic-api", {"api_key": secret})]
        audit = (
            await client.get("/api/v1/audit", headers=h, params={"action": "connection.secret"})
        ).json()
        assert secret not in json.dumps(audit)
    finally:
        hub.bao = None

    a = (await client.get("/api/v1/assignments", headers=h)).json()
    assert any(
        x["company"] == co["code"] and x["department"] is None and x["connection"] == "claude-max"
        for x in a["resolved"]
    )
    r = await signed_put(
        client,
        hub,
        owner_session,
        "/api/v1/assignments",
        {"assignments": [{"scope_type": "company", "scope_ref": co["code"], "effort": "low"}]},
        "assignments.update",
    )
    assert r.status_code == 200
    assert (
        next(
            x
            for x in r.json()["resolved"]
            if x["company"] == co["code"] and x["department"] is None
        )["effort"]
        == "low"
    )


@contextlib.asynccontextmanager
async def serve(app: Any) -> AsyncIterator[str]:
    """A real HTTP server (SSE needs streaming, which ASGITransport buffers)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:  # noqa: ASYNC110 - uvicorn only exposes a flag
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def _events(
    url: str, headers: dict[str, str], params: dict[str, Any], n: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async with (
        httpx.AsyncClient(base_url=url, timeout=20) as c,
        c.stream("GET", "/api/v1/stream", headers=headers, params=params) as resp,
    ):
        assert resp.status_code == 200 and resp.headers["content-type"].startswith(
            "text/event-stream"
        )
        current: dict[str, Any] = {}
        async for line in resp.aiter_lines():
            if line.startswith("id: "):
                current["id"] = int(line[4:])
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
            elif line == "" and "data" in current:
                out.append(current)
                current = {}
                if len(out) >= n:
                    break
    return out


async def test_stream_filters_and_resumes(
    app: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    relay: None,
) -> None:
    co = (await new_company())["code"]
    async with serve(app) as url:
        listener = asyncio.create_task(_events(url, owner, {"topics": "work", "company": co}, 2))
        await asyncio.sleep(0.5)
        w1 = await _work_for_ceo(client, owner, co)
        await client.post(
            f"/internal/v1/work/{w1['id']}/progress",
            headers=agent_headers(f"{co}-CEO"),
            json={"note": "x"},
        )
        got = await asyncio.wait_for(listener, 20)
        assert [e["event"] for e in got] == ["work.created", "work.updated"]
        assert got[0]["data"]["ref"] == w1["ref"] and got[0]["data"]["company"] == co
        assert "brief" not in json.dumps(got) and "title" not in got[0]["data"]["data"]
        # Resume after the first event: the second comes back, nothing is lost.
        again = await _events(
            url, {**owner, "Last-Event-ID": str(got[0]["id"])}, {"topics": "work", "company": co}, 1
        )
        assert again[0]["id"] == got[1]["id"]
        # The holding view: counters only.
        listener = asyncio.create_task(_events(url, owner, {"topics": "work", "company": "*"}, 1))
        await asyncio.sleep(0.5)
        await _work_for_ceo(client, owner, co)
        summary = await asyncio.wait_for(listener, 20)
        assert set(summary[0]["data"]) == {"id", "type", "at", "company"}
        r = await client.get("/api/v1/stream", headers=owner, params={"topics": "gossip"})
        assert r.status_code == 422


async def test_no_text_or_secret_in_logs_audit_or_events(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
    su: Any,
    relay: None,
) -> None:
    co = (await new_company())["code"]
    marker = "BODY-MARKER-" + uuid.uuid4().hex
    caplog.set_level(logging.DEBUG)
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": f"متن {marker}"},
    )
    assert r.status_code == 201
    await client.post(
        f"/internal/v1/threads/{co}-CEO/messages",
        headers={**agent_headers(f"{co}-CEO"), **idem()},
        json={"body": f"پاسخ {marker}"},
    )
    w = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co, "title": "عنوان", "brief": marker},
    )
    await client.post(
        "/internal/v1/activity",
        headers=agent_headers(f"{co}-CEO"),
        json={"employee": f"{co}-CEO", "activity": "working", "note": marker},
    )
    await client.post(
        "/internal/v1/decisions",
        headers={**agent_headers(f"{co}-CEO"), **idem()},
        json={"kind": "proposal", "title": "t", "what": marker, "why": marker, "payload": {}},
    )
    await asyncio.sleep(1.5)  # let the relay publish

    assert marker not in caplog.text
    rows = await su.fetch(
        "SELECT summary, target_ref FROM audit.entries WHERE company_id = (SELECT id FROM core.companies WHERE code = $1)",
        co,
    )
    assert rows and all(marker not in (r["summary"] + r["target_ref"]) for r in rows)
    outbox = await su.fetch(
        "SELECT payload::text AS p FROM core.outbox WHERE subject LIKE $1", f"hq.core.{co}.%"
    )
    assert outbox and all(marker not in r["p"] for r in outbox)
    sub = await hub.bus.js.subscribe(f"hq.core.{co}.>", stream="HQ_CORE", ordered_consumer=True)  # type: ignore[union-attr]
    seen = 0
    with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
        while True:
            msg = await sub.next_msg(timeout=2)
            assert marker.encode() not in msg.data
            seen += 1
    await sub.unsubscribe()
    assert seen >= 5 and w.status_code == 201
