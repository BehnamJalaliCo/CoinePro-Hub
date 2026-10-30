"""Prompt 17 (contract §26 ⟨1.8⟩): company server runners, the hub side.

A runner is simulated through the real routes (pairing, long-poll, events,
result, classify); the owner and the agents through theirs. Each test makes
its own company and servers (the test database outlives a run).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api import events
from hq_api.domain import servers as SV
from hq_api.domain import studio_publish as P
from hq_api.domain.server_classify import classify, classify_detail, classify_path, is_deploy
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up

RUNNER_HEADERS = {
    "X-HQ-Runner-Via": "private",
    "X-HQ-Runner-Hub-Rtt-Ms": "1.7",
    "X-HQ-Runner-Version": "0.1.0",
}


def _ip() -> str:
    return f"10.{secrets.randbelow(250)}.{secrets.randbelow(250)}.{secrets.randbelow(250)}"


async def pair(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, Any],
    co: dict[str, Any],
    name: str = "web-1",
    private_ip: str | None = None,
) -> dict[str, Any]:
    """A paired server: its runner's headers and the server as the owner sees it."""
    xff = {"X-Forwarded-For": _ip()}
    r = await client.post(
        "/api/v1/runners/pair",
        json={
            "company": co["code"],
            "name": name,
            "hostname": f"{name}.local",
            "private_ip": private_ip or _ip(),
            "os": "Ubuntu 24.04",
            "runner_version": "0.1.0",
        },
        headers=xff,
    )
    assert r.status_code == 201, r.text
    p = r.json()
    su = await step_up(hub, owner["session_id"], "server.attach", f"company:{co['code']}")
    r = await client.post(
        "/api/v1/runners/approve",
        json={"user_code": p["user_code"].lower().replace("-", "")},
        headers={**owner["headers"], **su, **idem()},
    )
    assert r.status_code == 200, r.text
    server = r.json()["server"]
    r = await client.post(
        "/api/v1/runners/token", json={"device_code": p["device_code"]}, headers=xff
    )
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok["server_id"] == server["id"]
    return {
        "server": server,
        "h": {"Authorization": f"Bearer {tok['runner_token']}", **RUNNER_HEADERS},
        "device_code": p["device_code"],
        "user_code": p["user_code"],
    }


async def poll(client: httpx.AsyncClient, rn: dict[str, Any]) -> httpx.Response:
    return await client.get(
        "/api/v1/runners/jobs/next",
        params={"wait": 0, "via": "private", "hub_rtt_ms": "2.5", "slots": 2},
        headers=rn["h"],
    )


async def take(client: httpx.AsyncClient, rn: dict[str, Any]) -> dict[str, Any]:
    r = await poll(client, rn)
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert job is not None, r.json()
    return dict(job)


async def owner_exec(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], sid: str, body: dict[str, Any]
) -> httpx.Response:
    raw = json.dumps(body).encode()
    su = await step_up(hub, owner["session_id"], "server.exec", hashlib.sha256(raw).hexdigest())
    return await client.post(
        f"/api/v1/infra/servers/{sid}/exec",
        content=raw,
        headers={**owner["headers"], **su, **idem(), "Content-Type": "application/json"},
    )


def sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev and data is not None:
            out.append((ev, data))
    return out


async def agent_job(client: httpx.AsyncClient, code: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        "/internal/v1/servers/jobs",
        json={"wait_s": 0, **body},
        headers={**(await agent_headers(code)), **idem()},
    )


# ------------------------------------------------------------------ pairing --
async def test_pairing_codes_step_up_and_token_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    xff = {"X-Forwarded-For": _ip()}
    body = {"company": co["code"], "name": "app-1", "hostname": "app-1", "private_ip": "10.10.1.7",
            "os": "Ubuntu 24.04", "runner_version": "0.1.0"}  # fmt: skip
    # Exactly the §26.4 fields: nothing else is taken.
    r = await client.post("/api/v1/runners/pair", json={**body, "via": "private"}, headers=xff)
    assert r.status_code == 422
    r = await client.post("/api/v1/runners/pair", json={**body, "company": "NOPE"}, headers=xff)
    assert r.status_code == 422
    r = await client.post("/api/v1/runners/pair", json=body, headers=xff)
    assert r.status_code == 201, r.text
    p = r.json()
    assert set(p) == {"device_code", "user_code", "expires_in", "interval"}
    assert p["expires_in"] == 900 and p["interval"] == 5
    assert len(p["user_code"]) == 9 and p["user_code"][4] == "-"
    stored = await su.fetchrow(
        "SELECT device_sha256, user_code FROM infra.runner_pairings WHERE user_code = $1",
        p["user_code"],
    )
    assert stored["device_sha256"] == hashlib.sha256(p["device_code"].encode()).hexdigest()
    # Pending: 428 authorization_pending.
    r = await client.post(
        "/api/v1/runners/token", json={"device_code": p["device_code"]}, headers=xff
    )
    assert r.status_code == 428 and r.json()["code"] == "authorization_pending"
    # Approving needs the passkey, on company:<CODE>.
    r = await client.post(
        "/api/v1/runners/approve", json={"user_code": p["user_code"]}, headers={**h, **idem()}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, owner_session["session_id"], "server.attach", "company:OTHER")
    r = await client.post(
        "/api/v1/runners/approve",
        json={"user_code": p["user_code"]},
        headers={**h, **wrong, **idem()},
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    r = await client.post(
        "/api/v1/runners/approve", json={"user_code": "ZZZZ-9999"}, headers={**h, **wrong, **idem()}
    )
    assert r.status_code == 404 and r.json()["code"] == "invalid_user_code"
    ok = await step_up(hub, owner_session["session_id"], "server.attach", f"company:{co['code']}")
    r = await client.post(
        "/api/v1/runners/approve", json={"user_code": p["user_code"]}, headers={**h, **ok, **idem()}
    )
    assert r.status_code == 200, r.text
    server = r.json()["server"]
    assert server["state"] == "pending" and server["origin"] == "attached"
    assert server["company"] == co["code"] and server["name"] == "app-1"
    # The credential once, then 410.
    r = await client.post(
        "/api/v1/runners/token", json={"device_code": p["device_code"]}, headers=xff
    )
    assert r.status_code == 200, r.text
    token = r.json()["runner_token"]
    assert token.startswith("hqr1_")
    r = await client.post(
        "/api/v1/runners/token", json={"device_code": p["device_code"]}, headers=xff
    )
    assert r.status_code == 410 and r.json()["code"] == "expired_token"
    assert (
        await su.fetchval(
            "SELECT count(*) FROM infra.runners WHERE token_sha256 = $1",
            hashlib.sha256(token.encode()).hexdigest(),
        )
        == 1
    )
    # A code already approved cannot be approved again.
    again = await step_up(
        hub, owner_session["session_id"], "server.attach", f"company:{co['code']}"
    )
    r = await client.post(
        "/api/v1/runners/approve",
        json={"user_code": p["user_code"]},
        headers={**h, **again, **idem()},
    )
    assert r.status_code == 409 and r.json()["code"] == "code_used"
    # An expired code: 410 at approval.
    r = await client.post("/api/v1/runners/pair", json={**body, "name": "app-2"}, headers=xff)
    late = r.json()
    await su.execute(
        "UPDATE infra.runner_pairings SET expires_at = now() - interval '1 second' WHERE user_code = $1",
        late["user_code"],
    )
    exp = await step_up(hub, owner_session["session_id"], "server.attach", f"company:{co['code']}")
    r = await client.post(
        "/api/v1/runners/approve",
        json={"user_code": late["user_code"]},
        headers={**h, **exp, **idem()},
    )
    assert r.status_code == 410 and r.json()["code"] == "expired_token"
    r = await client.post(
        "/api/v1/runners/token", json={"device_code": late["device_code"]}, headers=xff
    )
    assert r.status_code == 410
    # Rotation: a new credential; the old one keeps working for the grace.
    rh = {"Authorization": f"Bearer {token}", **RUNNER_HEADERS}
    r = await client.post("/api/v1/runners/rotate", headers=rh)
    assert r.status_code == 200 and r.json()["runner_token"] != token
    assert (
        await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=rh)
    ).status_code == 204
    # A bad credential is 401 (pair again).
    bad = {"Authorization": "Bearer hqr1_" + "x" * 40}
    assert (
        await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=bad)
    ).status_code == 401


async def test_pairing_is_rate_limited(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    xff = {"X-Forwarded-For": _ip()}
    body = {"company": co["code"], "name": "rl", "hostname": "rl", "private_ip": "10.0.0.9", "os": "x",
            "runner_version": "0.1.0"}  # fmt: skip
    codes = [
        (await client.post("/api/v1/runners/pair", json=body, headers=xff)).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [201] * 10 and codes[-1] == 429


async def test_server_list_shape_and_detach(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "shop", "10.10.1.21")
    assert (await poll(client, rn)).status_code == 204
    h = owner_session["headers"]
    items = (await client.get("/api/v1/infra/servers", headers=h)).json()["items"]
    s = next(x for x in items if x["id"] == rn["server"]["id"])
    for key in ("id", "company", "name", "origin", "private_ip", "user", "hostname", "runner_version",
                "via", "state", "last_seen_at", "map_at"):  # fmt: skip
        assert key in s, key
    assert s["state"] == "online" and s["via"] == "private" and s["origin"] == "attached"
    assert s["hub_rtt_ms"] == 2.5 and s["runner_version"] == "0.1.0"
    assert s["private_ip"] == "10.10.1.21" and s["map_at"] is None
    assert (await client.get(f"/api/v1/infra/servers/{s['id']}/map", headers=h)).status_code == 404
    # Detach: 🔏 server.detach on <CODE>:<server>; the runner gets 410 runner_revoked.
    r = await client.delete(f"/api/v1/infra/servers/{s['id']}", headers={**h, **idem()})
    assert r.status_code == 403
    tok = await step_up(hub, owner_session["session_id"], "server.detach", f"{co['code']}:shop")
    r = await client.delete(f"/api/v1/infra/servers/{s['id']}", headers={**h, **tok, **idem()})
    assert r.status_code == 200 and r.json()["state"] == "revoked", r.text
    r = await poll(client, rn)
    assert r.status_code == 410 and r.json()["code"] == "runner_revoked"
    assert (
        await su.fetchval("SELECT count(*) FROM infra.servers WHERE id = $1", uuid.UUID(s["id"]))
        == 1
    )


# -------------------------------------------------------------------- jobs --
async def test_exec_job_lifecycle_and_sse_shape(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    sid = rn["server"]["id"]
    body = {"cmd": "uname -a", "cwd": "/srv", "timeout_s": 60, "sudo": False}
    # The step-up is bound to the exact body.
    other = await step_up(hub, owner_session["session_id"], "server.exec", "0" * 64)
    r = await client.post(
        f"/api/v1/infra/servers/{sid}/exec",
        json=body,
        headers={**owner_session["headers"], **other, **idem()},
    )
    assert r.status_code == 403
    task = asyncio.create_task(owner_exec(client, hub, owner_session, sid, body))
    job = None
    for _ in range(50):
        r = await poll(client, rn)
        if r.status_code == 200:
            job = r.json()["job"]
            break
        await asyncio.sleep(0.1)
    assert job is not None and job["kind"] == "exec" and job["args"]["cmd"] == "uname -a"
    assert job["actor"]["kind"] == "owner" and job["timeout_s"] == 60
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events",
        json={
            "events": [
                {"seq": 1, "type": "stdout", "data": {"text": "Linux web-1\n"}},
                {"seq": 2, "type": "stderr", "data": {"text": "warning\n"}},
                {"seq": 1, "type": "stdout", "data": {"text": "a replay is ignored\n"}},
            ]
        },
        headers=rn["h"],
    )
    assert r.status_code == 200 and r.json()["accepted"] == 2, r.text
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد"},
        headers=rn["h"],
    )
    assert r.status_code == 200 and r.json()["state"] == "done"
    resp = await asyncio.wait_for(task, 20)
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    evs = sse(resp.text)
    assert evs[0] == ("stdout", {"text": "Linux web-1\n"})
    assert evs[1] == ("stderr", {"text": "warning\n"})
    assert (
        evs[-1][0] == "exit" and evs[-1][1]["code"] == 0 and evs[-1][1]["duration_ms"] is not None
    )
    # A late event: 409 job_finished (the runner stops).
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events",
        json={"events": [{"seq": 3, "type": "stdout", "data": {"text": "x"}}]},
        headers=rn["h"],
    )
    assert r.status_code == 409 and r.json()["code"] == "job_finished"
    # The activity, the job, its transcript (owner-readable), the audit rows.
    h = owner_session["headers"]
    page = (await client.get(f"/api/v1/infra/servers/{sid}/activity", headers=h)).json()
    row = next(x for x in page["items"] if x["id"] == job["id"])
    assert row["tool"] == "server.exec" and row["state"] == "done" and row["exit_code"] == 0
    assert row["cmd_masked"] == "uname -a" and row["actor"]["kind"] == "owner"
    assert row["transcript_url"] == f"/api/v1/infra/servers/{sid}/jobs/{job['id']}/transcript"
    t = await client.get(row["transcript_url"], headers=h)
    assert t.status_code == 200 and "Linux web-1" in t.text
    assert (await client.get(f"/api/v1/infra/servers/{sid}/activity", params={"actor": "nobody"},
                             headers=h)).json()["items"] == []  # fmt: skip
    audits = await su.fetch(
        "SELECT action, summary FROM audit.entries WHERE target_ref = $1 ORDER BY seq", job["id"]
    )
    assert [a["action"] for a in audits][:1] == ["server.job"] and len(audits) >= 2
    assert "exit 0" in audits[-1]["summary"] and "sha256:" in audits[-1]["summary"]
    # The stream topic: servers carries server.* only.
    assert events.TOPICS["servers"] == ("server.",)
    calls = await su.fetch(
        """SELECT payload FROM core.outbox WHERE subject = $1 ORDER BY id DESC LIMIT 20""",
        f"hq.core.{co['code']}.server.call",
    )
    shapes = [json.loads(c["payload"])["data"] for c in calls]
    end = next(d for d in shapes if d["job"] == job["id"] and d["state"] == "done")
    assert set(end) >= {"server", "company", "actor", "tool", "summary_fa", "cmd_masked", "exit_code",
                        "duration_ms", "session_ref", "state"}  # fmt: skip
    assert any(d["job"] == job["id"] and d["state"] == "running" for d in shapes)


async def test_map_netcheck_and_network(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    a = await pair(client, hub, owner_session, co, "a", "10.10.9.1")
    b = await pair(client, hub, owner_session, co, "b", "10.10.9.2")
    for rn in (a, b):
        assert (await poll(client, rn)).status_code == 204
    h = owner_session["headers"]
    r = await client.post("/api/v1/infra/network/check", headers=h)
    assert r.status_code == 202 and r.json()["queued"] >= 2
    job = await take(client, a)
    assert job["kind"] == "netcheck"
    targets = job["args"]["targets"]
    assert targets[0] == {"to": "hub", "host": "10.10.1.4", "port": 443}
    assert {(t["to"], t["port"]) for t in targets[1:]} >= {
        (b["server"]["id"], p) for p in (22, 443, 80)
    }
    results = [
        {
            "to": "hub",
            "name": "hub",
            "ip": "10.10.1.4",
            "port": 443,
            "ok": True,
            "ms": 0.8,
            "error": None,
        },
        {
            "to": b["server"]["id"],
            "ip": "10.10.9.2",
            "port": 22,
            "ok": True,
            "ms": 0.4,
            "error": None,
        },
        {
            "to": b["server"]["id"],
            "ip": "10.10.9.2",
            "port": 80,
            "ok": False,
            "ms": None,
            "error": "timeout",
        },
        {
            "to": b["server"]["id"],
            "ip": "10.10.9.2",
            "port": None,
            "ok": True,
            "ms": 0.3,
            "error": None,
        },
    ]
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={
            "exit_code": 0,
            "summary_fa": "سنجش",
            "data": {"from": "a", "via": "private", "results": results},
        },
        headers=a["h"],
    )
    assert r.status_code == 200 and r.json()["state"] == "done"
    net = (await client.get("/api/v1/infra/network", headers=h)).json()
    assert set(net) == {"at", "nodes", "links"}
    hub_node = next(n for n in net["nodes"] if n["id"] == "hub")
    assert hub_node["private_ip"] == "10.10.1.4"
    node = next(n for n in net["nodes"] if n["id"] == a["server"]["id"])
    assert set(node) == {"id", "company", "name", "private_ip", "via", "state", "hub_rtt_ms"}
    assert node["via"] == "private" and node["hub_rtt_ms"] == 1.7  # its last request's header
    links = [x for x in net["links"] if x["from"] == a["server"]["id"]]
    assert {(x["to"], x["port"], x["ok"]) for x in links} == {
        ("hub", 443, True), (b["server"]["id"], 22, True), (b["server"]["id"], 80, False),
    }  # fmt: skip
    assert set(links[0]) == {"from", "to", "port", "ok", "ms", "error", "at"}
    # The map: queued by the owner, answered by the runner.
    r = await client.post(f"/api/v1/infra/servers/{b['server']['id']}/map", headers=h)
    assert r.status_code == 202 and r.json()["job"]["kind"] == "map"
    jobs = [await take(client, b) for _ in range(2)]
    m = next(j for j in jobs if j["kind"] == "map")
    the_map = {"os": "Ubuntu 24.04", "kernel": "6.8", "uptime_s": 10, "user": "forex",
               "cron": [{"user": "forex", "schedule": "* * * * *",
                         "cmd_masked": "curl -H 'Authorization: Bearer sk-ant-api03-" + "a" * 40 + "'"}],
               "repos": [{"path": "/home/forex/app", "remote": "x", "branch": "main", "dirty": False,
                          "last_commit_at": None}]}  # fmt: skip
    r = await client.post(
        f"/api/v1/runners/jobs/{m['id']}/result",
        json={"exit_code": 0, "summary_fa": "نقشه", "data": the_map},
        headers=b["h"],
    )
    assert r.status_code == 200
    got = (await client.get(f"/api/v1/infra/servers/{b['server']['id']}/map", headers=h)).json()
    assert got["map"]["os"] == "Ubuntu 24.04" and got["at"]
    assert "sk-ant-api03" not in json.dumps(got)
    s = next(x for x in (await client.get("/api/v1/infra/servers", headers=h)).json()["items"]
             if x["id"] == b["server"]["id"])  # fmt: skip
    assert s["user"] == "forex" and s["map_at"]


async def test_kill_switch_cancels_and_refuses(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    mgr = f"{co['code']}-TECH-MGR"
    r = await agent_job(
        client, mgr, {"kind": "exec", "server": "web-1", "args": {"cmd": "sleep 100"}}
    )
    assert r.status_code == 201, r.text
    running = r.json()["job"]
    assert running["state"] == "queued" and running["actor"]["code"] == mgr
    assert (await take(client, rn))["id"] == running["id"]
    r = await agent_job(client, mgr, {"kind": "exec", "server": "web-1", "args": {"cmd": "ls"}})
    queued = r.json()["job"]
    h = owner_session["headers"]
    r = await client.post(
        "/api/v1/control/kill-switch",
        json={"scope": f"company:{co['code']}", "state": "engaged", "reason": "test"},
        headers={**h, **idem()},
    )
    assert r.status_code == 200, r.text
    r = await poll(client, rn)
    assert r.status_code == 200 and r.json()["job"] is None
    assert r.json()["cancels"] == [running["id"]]
    r = await client.post(
        f"/api/v1/runners/jobs/{running['id']}/events",
        json={"events": [{"seq": 1, "type": "stdout", "data": {"text": "x"}}]},
        headers=rn["h"],
    )
    assert r.status_code == 409 and r.json()["code"] == "job_cancelled"
    r = await client.post(
        f"/api/v1/runners/jobs/{running['id']}/result", json={"exit_code": 137}, headers=rn["h"]
    )
    assert r.status_code == 409
    view = await client.get(
        f"/internal/v1/servers/jobs/{queued['id']}",
        headers=await agent_headers(f"{co['code']}-CEO"),
    )
    assert view.json()["job"]["state"] == "cancelled"
    # New jobs: 423 company_locked, the owner's too.
    r = await agent_job(client, mgr, {"kind": "exec", "server": "web-1", "args": {"cmd": "ls"}})
    assert r.status_code == 423
    r = await owner_exec(
        client,
        hub,
        owner_session,
        rn["server"]["id"],
        {"cmd": "ls", "timeout_s": 10, "sudo": False},
    )
    assert r.status_code == 423 and r.json()["code"] == "company_locked"
    tok = await step_up(
        hub, owner_session["session_id"], "kill_switch.release", f"company:{co['code']}"
    )
    r = await client.post(
        "/api/v1/control/kill-switch",
        json={"scope": f"company:{co['code']}", "state": "released", "reason": "done"},
        headers={**h, **tok, **idem()},
    )
    assert r.status_code == 200


async def test_deploy_freeze_refuses_deploys_only(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    h = owner_session["headers"]
    until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await client.post(
        "/api/v1/control/deploy-freeze",
        json={"company": co["code"], "until": until, "reason": "release week"},
        headers={**h, **idem()},
    )
    assert r.status_code == 200, r.text
    sid = rn["server"]["id"]
    for cmd in ("cd /srv/app && git pull && docker compose up -d", "systemctl restart app-api",
                "bash scripts/deploy.sh"):  # fmt: skip
        r = await owner_exec(
            client, hub, owner_session, sid, {"cmd": cmd, "timeout_s": 60, "sudo": False}
        )
        assert r.status_code == 423 and r.json()["code"] == "deploy_frozen", cmd
    task = asyncio.create_task(
        owner_exec(
            client, hub, owner_session, sid, {"cmd": "docker ps", "timeout_s": 60, "sudo": False}
        )
    )
    job = None
    for _ in range(50):
        r = await poll(client, rn)
        if r.status_code == 200:
            job = r.json()["job"]
            break
        await asyncio.sleep(0.1)
    assert job is not None and job["args"]["cmd"] == "docker ps"
    await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result", json={"exit_code": 0}, headers=rn["h"]
    )
    assert (await asyncio.wait_for(task, 20)).status_code == 200
    # The Claude hook: a deploy under the freeze is refused (423), anything else is free.
    r = await client.post(
        "/api/v1/runners/classify", json={"cmd": "docker compose pull"}, headers=rn["h"]
    )
    assert r.status_code == 423 and r.json()["code"] == "deploy_frozen"
    r = await client.post("/api/v1/runners/classify", json={"cmd": "ls -la"}, headers=rn["h"])
    assert r.status_code == 200 and r.json()["category"] is None


DESTRUCTIVE = [
    ("db_drop", "docker exec db psql -U app -c 'DROP TABLE orders'"),
    ("volume_delete", "docker volume rm app_pgdata"),
    ("backup_delete", "rm -f /home/forex/backups/2026-10-29.sql.gz"),
    ("disk_wipe", "sudo mkfs.ext4 /dev/sdb1"),
    ("access_change", "echo 'ssh-ed25519 AAAA x' >> ~/.ssh/authorized_keys"),
    ("server_delete", "hcloud server delete coinepro-fx"),
]


@pytest.mark.parametrize(("category", "cmd"), DESTRUCTIVE)
async def test_each_destructive_category_waits_for_the_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    category: str,
    cmd: str,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "fx-1")
    sid = rn["server"]["id"]
    r = await owner_exec(
        client, hub, owner_session, sid, {"cmd": cmd, "timeout_s": 60, "sudo": False}
    )
    assert r.status_code == 202, r.text
    out = r.json()
    assert (
        out["decision_ref"].startswith("D-") and out["category"] == category and out["message_fa"]
    )
    assert (await poll(client, rn)).status_code == 204  # nothing runs before the seal
    h = owner_session["headers"]
    d = (await client.get(f"/api/v1/decisions/{out['decision_ref']}", headers=h)).json()
    assert d["kind"] == "server_destructive" and d["action_class"] == "A3"
    p = d["payload"]
    assert p["category"] == category and p["server"] == {"id": sid, "name": "fx-1"}
    assert p["server_name"] == "fx-1" and p["company"] == co["code"] and p["tool"] == "server.exec"
    assert p["detected_by"] == "pattern" and p["job"] == out["job"]
    # 🔏 server.destructive on <CODE>:<server> (decision.approve does not fit).
    wrong = await step_up(hub, owner_session["session_id"], "decision.approve", out["decision_ref"])
    r = await client.post(
        f"/api/v1/decisions/{out['decision_ref']}/approve",
        json={},
        headers={**h, **wrong, **idem()},
    )
    assert r.status_code == 403
    tok = await step_up(
        hub, owner_session["session_id"], "server.destructive", f"{co['code']}:fx-1"
    )
    r = await client.post(
        f"/api/v1/decisions/{out['decision_ref']}/approve", json={}, headers={**h, **tok, **idem()}
    )
    assert r.status_code == 200, r.text
    job = await take(client, rn)
    assert job["id"] == out["job"] and job["args"]["cmd"] == cmd
    seals = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'server.seal' AND target_ref = $1",
        out["decision_ref"],
    )
    assert seals == 1


async def test_a_refused_seal_cancels_the_job(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    r = await owner_exec(client, hub, owner_session, rn["server"]["id"],
                         {"cmd": "dropdb prod", "timeout_s": 60, "sudo": False})  # fmt: skip
    assert r.status_code == 202
    ref = r.json()["decision_ref"]
    h = owner_session["headers"]
    r = await client.post(
        f"/api/v1/decisions/{ref}/reject", json={"reason_code": "risk"}, headers={**h, **idem()}
    )
    assert r.status_code == 200, r.text
    j = (await client.get(f"/api/v1/infra/servers/{rn['server']['id']}/jobs/{r.json()['payload']['job']}",
                          headers=h)).json()  # fmt: skip
    assert j["state"] == "cancelled" and j["error_code"] == "seal_refused"
    assert (await poll(client, rn)).status_code == 204


async def test_the_policy_decides_what_waits(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    cur = (await client.get("/api/v1/control/server-policy", headers=h)).json()
    assert set(cur["seal_required"]) <= set(SV.CATEGORIES)
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    body = {"seal_required": [c for c in SV.CATEGORIES if c != "backup_delete"]}
    raw = json.dumps(body).encode()
    r = await client.put("/api/v1/control/server-policy", content=raw,
                         headers={**h, "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 403
    tok = await step_up(
        hub, owner_session["session_id"], "server.policy", hashlib.sha256(raw).hexdigest()
    )
    r = await client.put("/api/v1/control/server-policy", content=raw,
                         headers={**h, **tok, "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 200 and "backup_delete" not in r.json()["seal_required"]
    try:
        r = await client.post(
            "/api/v1/runners/classify", json={"cmd": "rm /srv/backups/x.sql.gz"}, headers=rn["h"]
        )
        assert r.json()["category"] is None and r.json()["detected"] == "backup_delete"
        r = await client.post("/api/v1/runners/classify", json={"cmd": "dropdb x"}, headers=rn["h"])
        assert r.json()["category"] == "db_drop"
    finally:
        back = json.dumps({"seal_required": list(SV.CATEGORIES)}).encode()
        tok = await step_up(
            hub, owner_session["session_id"], "server.policy", hashlib.sha256(back).hexdigest()
        )
        r = await client.put("/api/v1/control/server-policy", content=back,
                             headers={**h, **tok, "Content-Type": "application/json"})  # fmt: skip
        assert r.status_code == 200


async def test_secrets_are_masked_in_events_and_audit(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    key = "sk-ant-api03-" + "Q" * 60
    mgr = f"{co['code']}-TECH-MGR"
    r = await agent_job(client, mgr, {"kind": "exec", "server": "web-1",
                                      "args": {"cmd": f"ANTHROPIC_API_KEY={key} ./check.sh"}})  # fmt: skip
    assert r.status_code == 201, r.text
    assert key not in r.text
    job = await take(client, rn)
    assert (
        job["args"]["cmd"].endswith("./check.sh") and key in job["args"]["cmd"]
    )  # the runner runs it as given
    await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events",
        json={
            "events": [
                {
                    "seq": 1,
                    "type": "stdout",
                    "data": {"text": f"token={key}\nDB_PASSWORD=hunter2hunter2\n"},
                }
            ]
        },
        headers=rn["h"],
    )
    await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result", json={"exit_code": 0}, headers=rn["h"]
    )
    stored = await su.fetch("SELECT data::text AS d FROM infra.server_job_events WHERE job_id = $1",
                            uuid.UUID(job["id"]))  # fmt: skip
    assert stored and all(key not in s["d"] and "hunter2hunter2" not in s["d"] for s in stored)
    audits = await su.fetch("SELECT summary FROM audit.entries WHERE target_ref = $1", job["id"])
    assert audits and all(key not in a["summary"] for a in audits)
    h = owner_session["headers"]
    page = (
        await client.get(f"/api/v1/infra/servers/{rn['server']['id']}/activity", headers=h)
    ).text
    assert key not in page
    view = await client.get(
        f"/internal/v1/servers/jobs/{job['id']}", headers=await agent_headers(mgr)
    )
    assert view.status_code == 200 and key not in view.text


async def test_runners_and_agents_stay_in_their_company(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    a, b = await new_company(), await new_company()
    ra = await pair(client, hub, owner_session, a, "srv")
    rb = await pair(client, hub, owner_session, b, "srv")
    r = await agent_job(
        client, f"{b['code']}-TECH-MGR", {"kind": "exec", "server": "srv", "args": {"cmd": "ls"}}
    )
    jb = r.json()["job"]
    assert jb["server"] == rb["server"]["id"]  # the name is the agent's own company's server
    # A's runner never sees B's job (RLS: the runner's own company only).
    assert (await poll(client, ra)).status_code == 204
    r = await client.post(
        f"/api/v1/runners/jobs/{jb['id']}/events",
        json={"events": [{"seq": 1, "type": "stdout", "data": {"text": "x"}}]},
        headers=ra["h"],
    )
    assert r.status_code == 404
    r = await client.post(
        f"/api/v1/runners/jobs/{jb['id']}/result", json={"exit_code": 0}, headers=ra["h"]
    )
    assert r.status_code == 404
    async with hub.db.tx([a["id"]]) as tx:
        assert (
            await tx.scalar(
                "SELECT count(*) FROM infra.server_jobs WHERE id = :j", j=uuid.UUID(jb["id"])
            )
            == 0
        )
        assert await tx.scalar("SELECT count(*) FROM infra.servers WHERE id = :s",
                               s=uuid.UUID(rb["server"]["id"])) == 0  # fmt: skip
    # An agent of A on B's server: refused without an accepted request.
    r = await agent_job(client, f"{a['code']}-TECH-MGR",
                        {"kind": "exec", "server": "srv", "company": b["code"], "args": {"cmd": "ls"}})  # fmt: skip
    assert r.status_code == 403 and "other_company" in r.text
    r = await client.get(
        f"/internal/v1/servers/jobs/{jb['id']}",
        headers=await agent_headers(f"{a['code']}-TECH-MGR"),
    )
    assert r.status_code == 403
    # A role without the tool in its charter: refused.
    r = await agent_job(
        client, f"{a['code']}-SALES-MGR", {"kind": "exec", "server": "srv", "args": {"cmd": "ls"}}
    )
    assert r.status_code == 403


async def test_cross_company_through_an_accepted_request(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    a, b = await new_company(), await new_company()
    rb = await pair(client, hub, owner_session, b, "ig")
    me = f"{a['code']}-TECH-MGR"
    mine = await su.fetchrow(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, assignee_id,
               status, accepted_at)
           SELECT company_id, 'one_off', 'p17 cross', 'owner', 'owner', id, 'in_progress', now()
           FROM core.employees WHERE code = $1 RETURNING id, ref""",
        me,
    )
    body = {"kind": "read", "server": "ig", "company": b["code"], "via_work": mine["ref"],
            "args": {"path": "/srv/ig/config.yml"}}  # fmt: skip
    r = await agent_job(client, me, body)
    assert r.status_code == 403  # no request of B's CEO yet
    await su.execute(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, assignee_id,
               status, accepted_at, requested_by_work_id)
           SELECT company_id, 'one_off', 'p17 request', 'agent', $2, id, 'in_progress', now(), $3
           FROM core.employees WHERE code = $1""",
        f"{b['code']}-CEO",
        me,
        mine["id"],
    )
    r = await agent_job(client, me, body)
    assert r.status_code == 201, r.text
    job = r.json()["job"]
    assert job["actor"]["code"] == f"{b['code']}-CEO" and job["on_behalf"] == me
    assert job["server"] == rb["server"]["id"]


async def test_holding_platform_sre_on_every_server(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    await pair(client, hub, owner_session, co, "box")
    holding = await su.fetchval("SELECT code FROM core.companies WHERE kind = 'holding'")
    code = f"{holding}-P17S" + secrets.token_hex(2).upper()
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, role, title_fa, title_en, status)
           SELECT c.id, d.id, $1, 'employee', 'hub_platform_sre', 'SRE سکو', 'Platform SRE', 'active'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'AIOPS'
           WHERE c.kind = 'holding'""",
        code,
    )
    r = await agent_job(client, code, {"kind": "map", "server": "box", "company": co["code"]})
    assert r.status_code == 201, r.text
    assert r.json()["job"]["kind"] == "map" and r.json()["job"]["actor"]["code"] == code
    r = await client.get("/internal/v1/servers", headers=await agent_headers(code))
    assert r.status_code == 200 and any(s["name"] == "box" for s in r.json())


async def test_owner_session_on_a_company_server(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "repo-box")
    h = owner_session["headers"]
    r = await client.post(
        "/api/v1/workshop/sessions",
        json={
            "runtime": "company_server",
            "server": rn["server"]["id"],
            "company": co["code"],
            "driver": None,
            "title": "رفع خطا",
            "brief": "تست‌ها را درست کن",
            "attachments": [],
            "cwd": "/home/forex/app",
        },
        headers={**h, **idem()},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["runtime"] == "company_server" and s["server"] == rn["server"]["id"]
    assert s["company"] == co["code"] and s["workspace"] == "" and s["grant"] == ""
    assert s["state"] == "starting" and s["driver"]["kind"] == "owner"
    job = await take(client, rn)
    assert job["kind"] == "claude" and job["args"]["cwd"] == "/home/forex/app"
    assert job["args"]["brief"] == "تست‌ها را درست کن" and job["session_ref"] == s["ref"]
    # The hook: a free command, then a destructive one (the card, once per command).
    r = await client.post("/api/v1/runners/classify", json={"cmd": "pytest -q"},
                          headers={**rn["h"], "X-HQ-Runner-Job": job["id"]})  # fmt: skip
    assert r.json()["category"] is None
    hdr = {**rn["h"], "X-HQ-Runner-Job": job["id"]}
    r = await client.post(
        "/api/v1/runners/classify", json={"cmd": "docker volume prune -f"}, headers=hdr
    )
    assert r.json()["category"] == "volume_delete" and r.json()["decision_ref"]
    ref = r.json()["decision_ref"]
    r = await client.post(
        "/api/v1/runners/classify", json={"cmd": "docker volume prune -f"}, headers=hdr
    )
    assert r.json()["decision_ref"] == ref
    events_ = [
        {"seq": 1, "type": "session_event", "data": {"type": "state", "summary_fa": "آغاز",
                                                     "data": {"state": "working", "session_id": "cs-1"}}},
        {"seq": 2, "type": "session_event", "data": {"type": "command", "summary_fa": "دستور",
                                                     "data": {"cmd": "pytest -q"}}},
    ]  # fmt: skip
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events", json={"events": events_}, headers=rn["h"]
    )
    assert r.status_code == 200 and r.json()["accepted"] == 2
    usage = {"input_tokens": 1200, "output_tokens": 300, "cache_read_tokens": 50, "cache_write_tokens": 10,
             "thinking_tokens": 20, "cost_usd": 0.042, "model": "claude-opus-5-5"}  # fmt: skip
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد", "usage": usage,
              "data": {"session_id": "cs-1", "result_fa": "درست شد", "files_changed": ["a.py"]}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    s = (await client.get(f"/api/v1/workshop/sessions/{s['ref']}", headers=h)).json()
    assert s["state"] == "idle" and s["usage"]["input_tokens"] == 1200
    ledger = await su.fetchrow(
        "SELECT caller, task_class, thinking_tokens, equiv_cost_usd FROM llm.calls WHERE meta ->> 'server_job' = $1",
        job["id"],
    )
    assert ledger["caller"] == "company_runner" and ledger["task_class"] == "server_claude"
    assert ledger["thinking_tokens"] == 20 and float(ledger["equiv_cost_usd"]) == pytest.approx(
        0.042
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'server.command' AND target_ref = $1",
            job["id"],
        )
        == 1
    )
    # The owner's message resumes it: the next claude job with --resume.
    r = await client.post(f"/api/v1/workshop/sessions/{s['ref']}/messages", json={"body": "حالا lint"},
                          headers={**h, **idem()})  # fmt: skip
    assert r.status_code == 201, r.text
    nxt = await take(client, rn)
    assert (
        nxt["kind"] == "claude"
        and nxt["args"]["resume"] == "cs-1"
        and nxt["args"]["brief"] == "حالا lint"
    )
    r = await client.post(f"/api/v1/workshop/sessions/{s['ref']}/messages", json={"body": "و بعد"},
                          headers={**h, **idem()})  # fmt: skip
    assert r.status_code == 409  # a turn still runs
    r = await client.post(f"/api/v1/workshop/sessions/{s['ref']}/stop", headers={**h, **idem()})
    assert r.status_code == 200 and r.json()["state"] == "stopped"
    r = await poll(client, rn)
    assert nxt["id"] in r.json()["cancels"]


async def test_publish_through_a_runner(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "ig-hub")
    target = {"channel": "runner", "account": "runner-ig-hub", "placement": "instagram_post",
              "server": "ig-hub", "command": "/home/ig/bin/publish"}  # fmt: skip
    fid = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code) VALUES ($1, 'post.png', 'image/png', 3, repeat('a', 64), $2, 'service', 'media')
           RETURNING id""",
        co["id"],
        f"p17-{uuid.uuid4().hex}",
    )
    series = await su.fetchval(
        """INSERT INTO media.series (company_id, title_fa, kind, targets, schedule, format, checks,
               max_per_day, digest, sealed_digest, sealed_at, status, auto_publish, proposed_by_kind,
               proposed_by_code)
           VALUES ($1, 'پست', 'post', $2::jsonb, 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0', '{"aspect": "1:1"}',
                   '{brand}', 3, repeat('c', 64), repeat('c', 64), now(), 'sealed', true, 'owner', 'owner')
           RETURNING id""",
        co["id"],
        json.dumps([target]),
    )
    ref = await su.fetchval(
        """INSERT INTO media.items (company_id, series_id, kind, title_fa, state, created_by_kind,
               created_by_code, publish_at, outputs)
           VALUES ($1, $2, 'post', 'پست آزمایشی', 'scheduled', 'owner', 'owner', now() - interval '1 minute',
                   $3::jsonb) RETURNING ref""",
        co["id"],
        series,
        json.dumps(
            [
                {
                    "placement": "instagram_post",
                    "file_id": str(fid),
                    "name": "post.png",
                    "mime": "image/png",
                    "kind": "image",
                }
            ]
        ),
    )
    out = await P.publish_due(hub, only=ref)
    assert out["published"] == [ref], out
    job = await take(client, rn)
    assert job["kind"] == "publish" and job["args"]["command"] == "/home/ig/bin/publish"
    f = job["args"]["files"][0]
    assert f["url"].startswith("https://hq.test/public/v1/media/") and "caption" in job["args"]
    assert P.verify(hub, f["url"].rsplit("/", 1)[1]) == fid
    state = await su.fetchval("SELECT state FROM media.items WHERE ref = $1", ref)
    assert state == "scheduled"  # waits for the runner
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "منتشر شد",
              "data": {"external_id": "1789", "url": "https://instagram.com/p/xyz"}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    row = await su.fetchrow("SELECT state, publish FROM media.items WHERE ref = $1", ref)
    assert row["state"] == "published"
    pub = json.loads(row["publish"]) if isinstance(row["publish"], str) else row["publish"]
    assert pub[0]["external_id"] == "1789" and pub[0]["url"] == "https://instagram.com/p/xyz"
    log = await su.fetchrow(
        "SELECT channel, via, outcome, external_id FROM media.publish_log WHERE item_id = (SELECT id FROM media.items WHERE ref = $1)",
        ref,
    )
    assert (log["channel"], log["via"], log["outcome"], log["external_id"]) == (
        "runner",
        "runner",
        "ok",
        "1789",
    )


# ---------------------------------------------------------- classification --
CLASSIFY_TABLE: dict[str, str | None] = {
    "psql -c 'DROP TABLE users'": "db_drop",
    'docker exec db psql -U app -c "drop database prod"': "db_drop",
    "TRUNCATE orders;": "db_drop",
    "truncate -s 0 /var/log/app.log": None,
    "dropdb prod": "db_drop",
    "sudo -u postgres dropdb prod": "db_drop",
    "redis-cli FLUSHALL": "db_drop",
    "docker volume rm app_data": "volume_delete",
    "docker volume prune -f": "volume_delete",
    "docker compose down -v": "volume_delete",
    "docker compose down": None,
    "docker-compose -f x.yml down --volumes": "volume_delete",
    "rm -rf /var/lib/docker/volumes/x": "volume_delete",
    "cd /srv/app && sudo rm -rf data/": "volume_delete",
    "rm -rf ./node_modules": None,
    "rm -rf /tmp/build": None,
    "rm /home/forex/backups/2026-10-01.sql.gz": "backup_delete",
    "restic forget --prune --keep-last 3": "backup_delete",
    "rm -rf /": "disk_wipe",
    "sudo rm -rf /*": "disk_wipe",
    "mkfs.ext4 /dev/sdb1": "disk_wipe",
    "wipefs -a /dev/sdb": "disk_wipe",
    "fdisk /dev/sda": "disk_wipe",
    "fdisk -l": None,
    "parted -l": None,
    "parted /dev/sdb mklabel gpt": "disk_wipe",
    "dd if=/dev/zero of=/dev/sda bs=1M": "disk_wipe",
    "dd if=/dev/sda of=/tmp/x.img": None,
    "echo 'x' >> ~/.ssh/authorized_keys": "access_change",
    "cat ~/.ssh/authorized_keys": None,
    "sudo nano /etc/ssh/sshd_config": "access_change",
    "grep PermitRoot /etc/ssh/sshd_config": None,
    "useradd bob": "access_change",
    "sudo passwd forex": "access_change",
    "ufw allow 22": "access_change",
    "sudo ufw status": None,
    "iptables -A INPUT -j DROP": "access_change",
    "sudo iptables -L -n": None,
    "nft flush ruleset": "access_change",
    "nft list ruleset": None,
    "systemctl stop ssh": "access_change",
    "hcloud server delete web-1": "server_delete",
    "curl -X DELETE -H 'Authorization: Bearer x' https://api.hetzner.cloud/v1/servers/42": "server_delete",
    "shutdown -h now": None,
    "poweroff": None,
    "docker ps -a": None,
    "git status && git log -1": None,
    "ls -la /var/lib/docker/volumes": None,
}


@pytest.mark.parametrize(("cmd", "category"), list(CLASSIFY_TABLE.items()))
def test_classify_table(cmd: str, category: str | None) -> None:
    assert classify(cmd) == category, classify_detail(cmd)


def test_classify_paths_and_deploys() -> None:
    assert classify_path("/etc/ssh/sshd_config") == ("access_change", "sshd_config")
    assert classify_path("/home/forex/.ssh/authorized_keys")[0] == "access_change"  # type: ignore[index]
    assert classify_path("/srv/app/.env") is None
    for cmd in ("docker compose up -d", "docker compose pull", "git pull && docker compose up -d --build",
                "systemctl restart coinepro-api", "bash scripts/deploy.sh", "./deploy-prod.sh", "make deploy",
                "service app restart"):  # fmt: skip
        assert is_deploy(cmd), cmd
    for cmd in (
        "docker ps",
        "git log",
        "sudo systemctl restart docker",
        "service ssh restart",
        "ls",
    ):
        assert not is_deploy(cmd), cmd
