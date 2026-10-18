"""Prompt 06 §4: the Code Workshop's control plane (contract §17.3, §17.7), with
the `fake` runtime and the `managed` adapter against a fake HTTP server."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.db import Database
from hq_api.domain import decisions as D
from hq_api.hub import Hub
from hq_api.workshop import commands, service
from hq_api.workshop import domain as WS
from hq_api.workshop.runtime import FakeRuntime, ManagedRuntime, SessionSpec

from .conftest import agent_headers, body_bytes, idem, step_up
from .test_control_treasury_stream import serve

GH_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # a credential shape, not a real one
PAT = "github_pat_" + "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"


# ---------------------------------------------------------------- helpers --
@pytest.fixture
def owner(owner_session: dict[str, Any]) -> dict[str, str]:
    """The same owner session as `owner_session` (its step-ups are bound to it)."""
    headers: dict[str, str] = owner_session["headers"]
    return headers


@pytest.fixture
def fake(hub: Hub) -> Any:
    rt = FakeRuntime()
    hub.workshop = rt
    yield rt
    hub.workshop = None


async def workspace(owner_db: Database, co: dict[str, Any], suffix: str = "APP") -> str:
    code = f"{co['code']}-{suffix}"
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await tx.exec(
            """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
               VALUES (:co, :code, :repo, 'main', 'ریپوی آزمایشی', CAST(:p AS jsonb))""",
            co=co["id"],
            code=code,
            repo=f"behnamjalalico/{co['code']}",
            p=json.dumps(WS.DEFAULT_POLICY),
        )
    return code


async def signed_post(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    path: str,
    body: Any,
    action: str,
    *,
    target: str | None = None,
) -> httpx.Response:
    content = body_bytes(body)
    su = await step_up(
        hub, owner_session["session_id"], action, target or hashlib.sha256(content).hexdigest()
    )
    return await client.post(
        path,
        content=content,
        headers={**owner_session["headers"], **su, **idem(), "Content-Type": "application/json"},
    )


def grant_body(ws: str, **over: Any) -> dict[str, Any]:
    return {
        "workspace": ws,
        "actions": ["read", "edit", "run", "push_branch", "open_pr"],
        "driver": None,
        "budget_usd": 5,
        "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        **over,
    }


async def grant(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ws: str, **over: Any
) -> dict[str, Any]:
    r = await signed_post(
        client,
        hub,
        owner_session,
        "/api/v1/workshop/grants",
        grant_body(ws, **over),
        "workshop.grant",
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def open_session(
    client: httpx.AsyncClient, owner: dict[str, str], g: str, **over: Any
) -> httpx.Response:
    return await client.post(
        "/api/v1/workshop/sessions",
        headers={**owner, **idem()},
        json={"grant": g, "title": "رفع باگ ورود", "brief": "صفحه‌ی ورود را درست کن", **over},
    )


async def session(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/workshop/sessions/{ref}", headers=owner)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def events(
    client: httpx.AsyncClient, owner: dict[str, str], ref: str
) -> list[dict[str, Any]]:
    r = await client.get(f"/api/v1/workshop/sessions/{ref}/events", headers=owner)
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


async def outbox(su: Any, type_: str, ref: str) -> list[dict[str, Any]]:
    rows = await su.fetch(
        "SELECT payload FROM core.outbox WHERE subject LIKE $1 AND payload->>'ref' = $2",
        f"%.{type_}",
        ref,
    )
    return [json.loads(r["payload"]) for r in rows]


@pytest.fixture
async def setup(
    new_company: Callable[..., Any], owner_db: Database
) -> AsyncIterator[dict[str, Any]]:
    co = await new_company()
    yield {"co": co, "ws": await workspace(owner_db, co)}


# ------------------------------------------------------------ discovery --
async def test_meta_says_null_and_sessions_wait_for_the_owner(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
) -> None:
    assert hub.workshop is None
    meta = (await client.get("/api/v1/meta", headers=owner)).json()
    assert meta["workshop"] == {"runtime": None}
    # Workspaces, grants and history work without a runtime ...
    g = await grant(client, hub, owner_session, setup["ws"])
    r = await open_session(client, owner, g["ref"])
    # ... sessions do not.
    assert r.status_code == 503, r.text
    p = r.json()
    assert p["code"] == "runtime_not_configured" and "مدیر کل" in p["message_fa"]


async def test_seeded_workspaces_one_per_company_plus_the_hub(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str]
) -> None:
    # As the migrate step does (a migration round-trip test may have emptied the table).
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await WS.seed(tx)
    listed = {
        w["code"]: w
        for w in (await client.get("/api/v1/workshop/workspaces", headers=owner)).json()
    }
    companies = {c.code for c in await hub.companies.all()}
    for w in WS.load_seed():
        if w["company"] in companies:
            assert listed[w["code"]]["repo"] == w["repo"], w["code"]
            assert listed[w["code"]]["policy"]["merge"] == "owner_seal"
    assert listed["HQ-HUB"]["repo"].endswith("/CoinePro-Hub")
    by_company = (
        await client.get("/api/v1/workshop/workspaces", headers=owner, params={"company": "HQ"})
    ).json()
    assert {w["company"] for w in by_company} == {"HQ"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await WS.seed(tx) == 0  # idempotent: nothing added twice, nothing overwritten


async def test_put_workspaces_is_bound_to_the_exact_body(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    current = (await client.get("/api/v1/workshop/workspaces", headers=h)).json()
    keep = [
        {
            k: w[k]
            for k in ("code", "company", "repo", "default_branch", "title_fa", "policy", "status")
        }
        for w in current
    ]
    mine = {
        "code": f"{co['code']}-WEB",
        "company": co["code"],
        "repo": "behnamjalalico/Example",
        "default_branch": "main",
        "title_fa": "سایت نمونه",
    }
    body = [*keep, mine]
    r = await client.put("/api/v1/workshop/workspaces", headers=h, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_other = await step_up(
        hub, owner_session["session_id"], "workshop.workspaces", hashlib.sha256(b"[]").hexdigest()
    )
    r = await client.put(
        "/api/v1/workshop/workspaces",
        content=body_bytes(body),
        headers={**h, **su_other, "Content-Type": "application/json"},
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    content = body_bytes(body)
    su_ok = await step_up(
        hub, owner_session["session_id"], "workshop.workspaces", hashlib.sha256(content).hexdigest()
    )
    r = await client.put(
        "/api/v1/workshop/workspaces",
        content=content,
        headers={**h, **su_ok, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    got = {w["code"]: w for w in r.json()}
    assert got[mine["code"]]["status"] == "active"
    assert {w["code"]: w["status"] for w in current} == {
        c: got[c]["status"] for c in (w["code"] for w in current)
    }
    # Left out -> paused, never deleted; the change is audited with its step-up.
    content = body_bytes(keep)
    su_ok = await step_up(
        hub, owner_session["session_id"], "workshop.workspaces", hashlib.sha256(content).hexdigest()
    )
    r = await client.put(
        "/api/v1/workshop/workspaces",
        content=content,
        headers={**h, **su_ok, "Content-Type": "application/json"},
    )
    assert {w["code"]: w["status"] for w in r.json()}[mine["code"]] == "paused"
    rows = await su.fetch(
        "SELECT summary, step_up FROM audit.entries WHERE action = 'workshop.workspaces' AND target_ref = $1",
        mine["code"],
    )
    assert len(rows) == 2 and all(r["step_up"] for r in rows)
    # A workspace keeps its company; the branch prefix stays hq/.
    bad = [*keep, {**mine, "company": "TY"}]
    content = body_bytes(bad)
    su_ok = await step_up(
        hub, owner_session["session_id"], "workshop.workspaces", hashlib.sha256(content).hexdigest()
    )
    r = await client.put(
        "/api/v1/workshop/workspaces",
        content=content,
        headers={**h, **su_ok, "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    r = await client.put(
        "/api/v1/workshop/workspaces",
        headers=h,
        json=[{**mine, "policy": {"branch_prefix": "main/"}}],
    )
    assert r.status_code == 422


# ----------------------------------------------------------------- grants --
async def test_no_grant_without_the_owners_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    body = grant_body(setup["ws"])
    r = await client.post("/api/v1/workshop/grants", headers={**h, **idem()}, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    # A step-up for another body does not cover this one.
    r = await signed_post(
        client,
        hub,
        owner_session,
        "/api/v1/workshop/grants",
        body,
        "workshop.grant",
        target="0" * 64,
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    # An agent never grants (internal API has no such route; the public one is owner-only).
    r = await client.post(
        "/api/v1/workshop/grants",
        headers={**await agent_headers(f"{setup['co']['code']}-CEO"), **idem()},
        json=body,
    )
    assert r.status_code in (401, 403)
    assert (
        await su.fetchval(
            "SELECT count(*) FROM workshop.grants g JOIN workshop.workspaces w ON w.id = g.workspace_id WHERE w.code = $1",
            setup["ws"],
        )
        == 0
    )
    # Sealed: the grant; replaying the same key returns it again.
    content = body_bytes(body)
    key = idem()
    su_tok = await step_up(
        hub, owner_session["session_id"], "workshop.grant", hashlib.sha256(content).hexdigest()
    )
    hdr = {**h, **su_tok, **key, "Content-Type": "application/json"}
    first = await client.post("/api/v1/workshop/grants", content=content, headers=hdr)
    assert first.status_code == 201, first.text
    g = first.json()
    assert g["ref"].startswith("G-") and g["granted_by"]["kind"] == "owner" and g["driver"] is None
    again = await client.post("/api/v1/workshop/grants", content=content, headers=hdr)
    assert again.json()["ref"] == g["ref"] and again.headers.get("Idempotent-Replay") == "true"
    audit = await su.fetchrow(
        "SELECT action_class, step_up FROM audit.entries WHERE action = 'workshop.grant' AND target_ref = $1",
        g["ref"],
    )
    assert audit["action_class"] == "A2" and audit["step_up"]
    # The driver belongs to the workspace's company; at most 90 days.
    for over in (
        {"driver": "TY-CEO"},
        {"expires_at": (datetime.now(UTC) + timedelta(days=120)).isoformat()},
        {"actions": ["deploy"]},
    ):
        r = await signed_post(
            client,
            hub,
            owner_session,
            "/api/v1/workshop/grants",
            grant_body(setup["ws"], **over),
            "workshop.grant",
        )
        assert r.status_code == 422, over
    listed = (
        await client.get(
            "/api/v1/workshop/grants", headers=h, params={"workspace": setup["ws"], "active": True}
        )
    ).json()
    assert [x["ref"] for x in listed] == [g["ref"]]


async def test_a_sealed_code_session_decision_creates_the_grant(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    su: Any,
) -> None:
    co = setup["co"]["code"]
    ceo = await agent_headers(f"{co}-CEO")
    payload = {
        "workspace": setup["ws"],
        "actions": ["read", "edit", "run"],
        "budget_usd": "3.5",
        "days": 3,
    }
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={
            "kind": "code_session",
            "title": "رفع باگ ورود",
            "why": "کاربرها وارد نمیشوند",
            "payload": payload,
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["kind"] == "code_session" and d["action_class"] == "A1"
    # Another company's workspace: refused at proposal time.
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={"kind": "code_session", "title": "x", "payload": {**payload, "workspace": "HQ-HUB"}},
    )
    assert r.status_code == 422
    h = owner_session["headers"]
    r = await client.post(f"/api/v1/decisions/{d['ref']}/approve", headers={**h, **idem()}, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_tok = await step_up(hub, owner_session["session_id"], "decision.approve", d["ref"])
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**h, **su_tok, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, d["ref"], SYSTEM)
        assert (await D.apply_effect(tx, d["ref"], SYSTEM))["changed"] is False  # idempotent
    g = (
        await client.get("/api/v1/workshop/grants", headers=h, params={"workspace": setup["ws"]})
    ).json()
    assert [x["ref"] for x in g] == [out["grant"]]
    assert g[0]["decision_ref"] == d["ref"] and g[0]["driver"]["code"] == f"{co}-CEO"
    assert g[0]["actions"] == ["read", "edit", "run"] and g[0]["budget_usd"] == 3.5
    left = datetime.fromisoformat(g[0]["expires_at"]) - datetime.now(UTC)
    assert timedelta(days=2, hours=23) < left <= timedelta(days=3)
    assert await su.fetchval(
        "SELECT step_up FROM audit.entries WHERE action = 'workshop.grant' AND target_ref = $1",
        g[0]["ref"],
    )


# --------------------------------------------------------------- sessions --
async def test_a_session_outside_its_grant_is_refused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
) -> None:
    co = setup["co"]["code"]
    g = await grant(client, hub, owner_session, setup["ws"], driver=f"{co}-CEO")
    # Not the grant's driver.
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(
        "/internal/v1/workshop/sessions",
        headers={**mgr, **idem()},
        json={"grant": g["ref"], "title": "t"},
    )
    assert r.status_code == 403 and r.json()["code"] == "policy_denied", r.text
    # Another company's agent does not even see the grant.
    r = await client.post(
        "/internal/v1/workshop/sessions",
        headers={**await agent_headers("TY-CEO"), **idem()},
        json={"grant": g["ref"], "title": "t"},
    )
    assert r.status_code in (403, 404)
    # The driver opens one through the internal API.
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/workshop/sessions",
        headers={**ceo, **idem()},
        json={"grant": g["ref"], "title": "t"},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["driver"]["code"] == f"{co}-CEO" and s["opened_by"]["kind"] == "agent"
    listed = (await client.get("/internal/v1/workshop/sessions", headers=ceo)).json()["items"]
    assert s["ref"] in [x["ref"] for x in listed]
    # Unknown, revoked or expired grants open nothing.
    assert (await open_session(client, owner, "G-999999")).status_code == 404
    r = await client.post(
        f"/api/v1/workshop/grants/{g['ref']}/revoke", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 200 and r.json()["revoked_at"]
    assert (await session(client, owner, s["ref"]))["state"] == "stopped"  # its sessions stop
    r = await open_session(client, owner, g["ref"])
    assert r.status_code == 409


async def test_a_fake_session_end_to_end_with_approvals(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
    su: Any,
) -> None:
    g = await grant(client, hub, owner_session, setup["ws"])
    r = await open_session(client, owner, g["ref"], area="src")
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    s = await session(client, owner, ref)
    assert s["state"] == "waiting_approval" and s["runtime"] == "fake"
    assert s["usage"]["usd"] == 0.4 and s["usage"]["input_tokens"] == 12000
    evs = await events(client, owner, ref)
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    types = [e["type"] for e in evs]
    for t in ("state", "progress", "command", "file_change", "approval_request"):
        assert t in types, types
    ask = next(e for e in evs if e["type"] == "approval_request")
    ap = ask["data"]["approval_id"]
    assert ask["data"]["action"] == "push_branch" and f"hq/{ref}" in ask["data"]["detail"]
    assert await outbox(su, "workshop.approval", ref)
    assert {e["data"]["state"] for e in await outbox(su, "workshop.session", ref)} >= {
        "starting",
        "working",
        "waiting_approval",
    }
    # To allow: 🔏 bound to "S-…/AP-…".
    path = f"/api/v1/workshop/sessions/{ref}/approvals/{ap}"
    r = await client.post(path, headers={**owner, **idem()}, json={"allow": True})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, owner_session["session_id"], "workshop.approval", f"{ref}/AP-0000")
    r = await client.post(path, headers={**owner, **wrong, **idem()}, json={"allow": True})
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    ok = await step_up(hub, owner_session["session_id"], "workshop.approval", f"{ref}/{ap}")
    r = await client.post(
        path, headers={**owner, **ok, **idem()}, json={"allow": True, "note": "باشه"}
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["type"] == "approval_result"
        and r.json()["data"]["allow"] is True
        and "allowed" not in r.json()["data"]
    )
    s = await session(client, owner, ref)
    assert s["branch"] == f"hq/{ref}" and s["state"] == "idle"
    assert fake.log_[ref][-1] == {"kind": "answer", "approval": f"fake-{ref}-push", "allow": True}
    # Answered once only.
    again = await step_up(hub, owner_session["session_id"], "workshop.approval", f"{ref}/{ap}")
    r = await client.post(path, headers={**owner, **again, **idem()}, json={"allow": True})
    assert r.status_code == 409
    # The owner steers; then stops (the branch stays).
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/messages",
        headers={**owner, **idem()},
        json={"body": "تست‌ها را هم اضافه کن"},
    )
    assert (
        r.status_code == 201
        and r.json()["type"] == "message"
        and r.json()["actor"]["kind"] == "owner"
    )
    assert fake.log_[ref][-1] == {"kind": "message", "text": "تست‌ها را هم اضافه کن"}
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/stop", headers={**owner, **idem()}, json={}
    )
    assert (
        r.status_code == 200
        and r.json()["state"] == "stopped"
        and r.json()["branch"] == f"hq/{ref}"
    )
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/messages", headers={**owner, **idem()}, json={"body": "x"}
    )
    assert r.status_code == 409
    # Rule 7: the transcript is in storage, owner-readable; events stay append-only.
    s = await session(client, owner, ref)
    assert s["transcript_file"]
    r = await client.get(f"/api/v1/workshop/sessions/{ref}/transcript", headers=owner)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    assert "تست‌ها را هم اضافه کن" in r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        with pytest.raises(Exception):  # noqa: B017 - the trigger refuses any change
            await tx.exec(
                "UPDATE workshop.events SET summary_fa = 'x' WHERE session_id = :s", s=s["id"]
            )
    audit = await su.fetch(
        "SELECT action FROM audit.entries WHERE target_ref = $1 OR target_ref LIKE $2 ORDER BY at",
        ref,
        f"{ref}/%",
    )
    assert {"workshop.session", "workshop.approval", "workshop.message", "workshop.stop"} <= {
        a["action"] for a in audit
    }


async def test_a_denial_needs_no_step_up(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
) -> None:
    g = await grant(client, hub, owner_session, setup["ws"])
    ref = (await open_session(client, owner, g["ref"])).json()["ref"]
    ap = next(e for e in await events(client, owner, ref) if e["type"] == "approval_request")
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/approvals/{ap['data']['approval_id']}",
        headers={**owner, **idem()},
        json={"allow": False, "note": "نه"},
    )
    assert r.status_code == 200 and r.json()["data"]["allow"] is False
    s = await session(client, owner, ref)
    assert s["branch"] is None and s["state"] == "idle"


async def test_live_resumes_after_last_event_id(
    app: Any,
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
) -> None:
    g = await grant(client, hub, owner_session, setup["ws"])
    ref = (await open_session(client, owner, g["ref"])).json()["ref"]
    await client.post(f"/api/v1/workshop/sessions/{ref}/stop", headers={**owner, **idem()}, json={})
    total = len(await events(client, owner, ref))
    async with (
        serve(app) as url,
        httpx.AsyncClient(base_url=url, timeout=20) as c,
        c.stream(
            "GET", f"/api/v1/workshop/sessions/{ref}/live", headers={**owner, "Last-Event-ID": "2"}
        ) as resp,
    ):
        assert resp.status_code == 200
        got: list[tuple[int, str]] = []
        cur: dict[str, Any] = {}
        async for line in resp.aiter_lines():
            if line.startswith("id: "):
                cur["id"] = int(line[4:])
            elif line.startswith("event: "):
                cur["event"] = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                assert data["seq"] == cur["id"] and data["type"] == cur["event"]
                got.append((cur["id"], cur["event"]))
    # Everything after seq 2, in order, then the stream ends (the session is finished).
    assert [i for i, _ in got] == list(range(3, total + 1))


async def test_a_kill_switch_or_freeze_pauses_sessions_and_refuses_new_ones(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
) -> None:
    co = setup["co"]["code"]
    g = await grant(client, hub, owner_session, setup["ws"], driver=f"{co}-CEO")
    ref = (await open_session(client, owner, g["ref"])).json()["ref"]
    scope = f"company:{co}"
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": scope, "state": "engaged", "reason": "test"},
    )
    assert r.status_code == 200, r.text
    try:
        s = await session(client, owner, ref)
        assert s["held"] == "company_locked" and s["state"] == "idle"
        assert (await events(client, owner, ref))[-1]["data"] == {
            "state": "idle",
            "held": "company_locked",
        }
        r = await open_session(client, owner, g["ref"])
        assert r.status_code == 423 and r.json()["code"] == "company_locked"
        r = await client.post(
            f"/api/v1/workshop/sessions/{ref}/messages",
            headers={**owner, **idem()},
            json={"body": "ادامه"},
        )
        assert r.status_code == 423
        r = await client.post(
            "/internal/v1/workshop/sessions",
            headers={**await agent_headers(f"{co}-CEO"), **idem()},
            json={"grant": g["ref"], "title": "t"},
        )
        assert r.status_code == 423
    finally:
        su_tok = await step_up(hub, owner_session["session_id"], "kill_switch.release", scope)
        r = await client.post(
            "/api/v1/control/kill-switch",
            headers={**owner, **su_tok, **idem()},
            json={"scope": scope, "state": "released", "reason": "done"},
        )
        assert r.status_code == 200, r.text
    # Lifted: the owner's next word lets it go on.
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/messages",
        headers={**owner, **idem()},
        json={"body": "ادامه"},
    )
    assert r.status_code == 201, r.text
    s = await session(client, owner, ref)
    assert s["held"] is None and s["state"] == "idle"
    # A deploy freeze pauses it the same way.
    until = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    r = await client.post(
        "/api/v1/control/deploy-freeze",
        headers=owner,
        json={"company": co, "until": until, "reason": "x"},
    )
    assert r.status_code == 200, r.text
    try:
        assert (await session(client, owner, ref))["held"] == "company_locked"
        assert (await open_session(client, owner, g["ref"])).status_code == 423
    finally:
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        await client.post(
            "/api/v1/control/deploy-freeze",
            headers=owner,
            json={"company": co, "until": past, "reason": "x"},
        )


async def test_the_budget_cap_stops_the_session(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
    su: Any,
) -> None:
    fake.usd_per_turn = Decimal("3")
    fake.ask_push = False
    g = await grant(client, hub, owner_session, setup["ws"], budget_usd=5)
    ref = (await open_session(client, owner, g["ref"])).json()["ref"]
    s = await session(client, owner, ref)
    assert s["state"] == "idle" and s["usage"]["usd"] == 3
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/messages",
        headers={**owner, **idem()},
        json={"body": "ادامه بده"},
    )
    assert r.status_code == 201
    s = await session(client, owner, ref)
    assert s["state"] == "stopped" and s["held"] == "budget" and s["usage"]["usd"] == 6
    last = (await events(client, owner, ref))[-1]
    assert last["type"] == "error" and last["data"] == {"code": "budget_reached"}
    assert fake.log_[ref][-1] == {"kind": "stop"}  # stopped on the runtime too
    n = await su.fetchrow(
        "SELECT level, title_fa FROM notify.notifications WHERE link_ref = $1", ref
    )
    assert n["level"] == "decision" and ref in n["title_fa"]


async def test_one_writing_session_per_area_the_others_queue(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
) -> None:
    fake.ask_push = False
    writer = await grant(client, hub, owner_session, setup["ws"])
    reader = await grant(client, hub, owner_session, setup["ws"], actions=["read", "run"])
    a = (await open_session(client, owner, writer["ref"], area="src")).json()
    b = (await open_session(client, owner, writer["ref"], area="src/api")).json()
    c = (await open_session(client, owner, writer["ref"], area="docs")).json()
    d = (await open_session(client, owner, reader["ref"], area="src")).json()
    assert a["held"] is None and c["held"] is None and d["held"] is None
    assert b["held"] == "work_lock" and b["state"] == "starting"
    assert b["ref"] not in fake.log_  # never started while A writes there
    assert "در صف" in (await events(client, owner, b["ref"]))[0]["summary_fa"]
    await client.post(
        f"/api/v1/workshop/sessions/{a['ref']}/stop", headers={**owner, **idem()}, json={}
    )
    b2 = await session(client, owner, b["ref"])
    assert b2["held"] is None and b2["state"] == "idle"
    assert fake.log_[b["ref"]][0]["kind"] == "start"
    assert WS.overlaps("", "x") and WS.overlaps("a/b", "a") and not WS.overlaps("ab", "a")


async def test_no_credential_reaches_events_logs_or_responses(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    fake: FakeRuntime,
    su: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rule 2 and 7: an automatic scan of every event, log line, API response,
    stream envelope and the transcript for the GitHub credential shapes."""
    caplog.set_level(logging.DEBUG)
    fake.output = f"12 passed; remote https://x-access-token:{GH_TOKEN}@github.com/o/r"
    g = await grant(client, hub, owner_session, setup["ws"])
    seen: list[str] = []
    r = await open_session(client, owner, g["ref"], brief=f"use {PAT} to push")
    seen.append(r.text)
    ref = r.json()["ref"]
    r = await client.post(
        f"/api/v1/workshop/sessions/{ref}/messages",
        headers={**owner, **idem()},
        json={"body": f"token is {GH_TOKEN}"},
    )
    seen.append(r.text)
    seen.append((await client.get(f"/api/v1/workshop/sessions/{ref}", headers=owner)).text)
    seen.append((await client.get(f"/api/v1/workshop/sessions/{ref}/events", headers=owner)).text)
    seen.append((await client.get("/api/v1/workshop/sessions", headers=owner)).text)
    await client.post(f"/api/v1/workshop/sessions/{ref}/stop", headers={**owner, **idem()}, json={})
    seen.append(
        (await client.get(f"/api/v1/workshop/sessions/{ref}/transcript", headers=owner)).text
    )
    rows = await su.fetch(
        """SELECT e.summary_fa || ' ' || e.data::text AS t FROM workshop.events e
           JOIN workshop.sessions s ON s.id = e.session_id WHERE s.ref = $1""",
        ref,
    )
    seen += [r["t"] for r in rows]
    seen += [
        str(r["x"])
        for r in await su.fetch(
            "SELECT brief || title AS x FROM workshop.sessions WHERE ref = $1", ref
        )
    ]
    seen += [
        json.dumps(p)
        for t in ("workshop.session", "workshop.approval")
        for p in await outbox(su, t, ref)
    ]
    seen.append(caplog.text)
    blob = "\n".join(seen)
    assert ref in blob and "[token]" in blob  # it was there, masked
    for secret in (GH_TOKEN, PAT, GH_TOKEN[4:20], PAT[11:30]):
        assert secret not in blob


# ---------------------------------------------------------------- managed --
class FakeAnthropic:
    """The Managed Agents API as far as the adapter uses it."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.sent: list[dict[str, Any]] = []
        self.created: dict[str, Any] = {}
        self.stream: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert request.headers["anthropic-beta"] == "managed-agents-2026-04-01"
        if request.method == "POST" and request.url.path == "/v1/sessions":
            self.created = json.loads(request.content)
            return httpx.Response(200, json={"id": "sesn_01", "status": "idle"})
        if request.method == "POST" and request.url.path == "/v1/sessions/sesn_01/events":
            self.sent += json.loads(request.content)["events"]
            return httpx.Response(200, json={"data": []})
        if request.method == "GET" and request.url.path == "/v1/sessions/sesn_01/events":
            return httpx.Response(200, json={"data": self.stream, "next_page": None})
        return httpx.Response(404, json={"error": {"type": "not_found"}})


def managed(fake_api: FakeAnthropic) -> ManagedRuntime:
    async def token(workspace: str) -> str | None:
        return GH_TOKEN

    return ManagedRuntime(
        api_key=lambda: "test-key",
        agent_id="agent_01",
        environment_id="env_01",
        github_token=token,
        base_url="https://api.anthropic.test",
        transport=httpx.MockTransport(fake_api.handler),
    )


def tool(i: int, cmd: str, permission: str = "ask") -> dict[str, Any]:
    return {
        "id": f"sevt_{i}",
        "type": "agent.tool_use",
        "name": "bash",
        "input": {"command": cmd},
        "evaluated_permission": permission,
    }


async def test_the_managed_adapter_against_a_fake_server(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
    su: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    api = FakeAnthropic()
    hub.workshop = managed(api)
    try:
        assert (await client.get("/api/v1/meta", headers=owner)).json()["workshop"] == {
            "runtime": "managed"
        }
        g = await grant(client, hub, owner_session, setup["ws"], budget_usd=4)
        r = await open_session(client, owner, g["ref"])
        assert r.status_code == 201, r.text
        ref = r.json()["ref"]
        # The session: the repository as a github_repository resource whose token
        # goes to the managed side only; the platform's own budget; the rules first.
        res = api.created["resources"][0]
        assert res["type"] == "github_repository" and res["authorization_token"] == GH_TOKEN
        assert res["url"] == f"https://github.com/behnamjalalico/{setup['co']['code']}"
        assert api.created["budget"]["max_list_cost"] == {"amount": "400", "currency": "USD"}
        first = api.sent[0]
        assert first["type"] == "user.message" and f"hq/{ref}" in first["content"][0]["text"]
        s = await session(client, owner, ref)
        assert s["state"] == "working" and s["runtime"] == "managed"
        # always_ask: the allow-list is answered by the hub, push and PR go to the owner,
        # production and other branches are refused outright.
        api.stream = [
            {"id": "sevt_0", "type": "session.status_running"},
            tool(1, "pytest -q"),
            tool(2, "ssh deploy@10.10.1.2"),
            tool(3, "git push origin main"),
            tool(4, f"git push origin hq/{ref}"),
            {
                "id": "sevt_5",
                "type": "agent.message",
                "content": [{"type": "text", "text": f"done {GH_TOKEN}"}],
            },
            {
                "id": "sevt_6",
                "type": "span.model_request_end",
                "model_usage": {"input_tokens": 100, "output_tokens": 20},
            },
            {
                "id": "sevt_7",
                "type": "session.usage",
                "list_cost": {"amount": "150", "currency": "USD"},
            },
            {
                "id": "sevt_8",
                "type": "session.status_idle",
                "stop_reason": {"type": "requires_action"},
            },
        ]
        assert await service.sync(hub) == 8  # the last idle (requires_action) maps to nothing
        confirmations = {
            e["tool_use_id"]: e["result"] for e in api.sent if e["type"] == "user.tool_confirmation"
        }
        assert confirmations == {"sevt_1": "allow", "sevt_2": "deny", "sevt_3": "deny"}
        s = await session(client, owner, ref)
        assert s["state"] == "waiting_approval" and s["usage"]["usd"] == 1.5
        assert s["usage"]["input_tokens"] == 100 and s["usage"]["output_tokens"] == 20
        evs = await events(client, owner, ref)
        ask = next(e for e in evs if e["type"] == "approval_request")
        assert ask["data"]["action"] == "push_branch"
        assert [e["data"].get("code") for e in evs if e["type"] == "error"] == [
            "command_refused"
        ] * 2
        # Polling again sees nothing new (the cursor).
        assert await service.sync(hub) == 0
        ok = await step_up(
            hub,
            owner_session["session_id"],
            "workshop.approval",
            f"{ref}/{ask['data']['approval_id']}",
        )
        r = await client.post(
            f"/api/v1/workshop/sessions/{ref}/approvals/{ask['data']['approval_id']}",
            headers={**owner, **ok, **idem()},
            json={"allow": True},
        )
        assert r.status_code == 200, r.text
        assert api.sent[-1] == {
            "type": "user.tool_confirmation",
            "tool_use_id": "sevt_4",
            "result": "allow",
        }
        # The platform's budget stop is the hub's too.
        api.stream.append(
            {
                "id": "sevt_9",
                "type": "session.status_idle",
                "stop_reason": {"type": "budget_reached"},
            }
        )
        await service.sync(hub)
        s = await session(client, owner, ref)
        assert s["state"] == "stopped" and s["held"] == "budget"
        assert api.sent[-1] == {"type": "user.interrupt"}
        # The credential lives on the managed side only.
        blob = "\n".join(
            [
                caplog.text,
                json.dumps(await events(client, owner, ref)),
                json.dumps(s),
                *[
                    str(r["t"])
                    for r in await su.fetch(
                        "SELECT data::text || summary_fa AS t FROM workshop.events"
                    )
                ],
                *[
                    str(r["p"])
                    for r in await su.fetch(
                        "SELECT payload::text AS p FROM core.outbox WHERE subject LIKE '%.workshop.%'"
                    )
                ],
            ]
        )
        assert GH_TOKEN not in blob
    finally:
        hub.workshop = None


async def test_managed_runtime_errors_fail_the_session_not_the_request(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    setup: dict[str, Any],
) -> None:
    api = FakeAnthropic()
    rt = managed(api)

    async def no_token(workspace: str) -> str | None:
        return None

    rt.github_token = no_token
    hub.workshop = rt
    try:
        g = await grant(client, hub, owner_session, setup["ws"])
        r = await open_session(client, owner, g["ref"])
        assert r.status_code == 201
        s = await session(client, owner, r.json()["ref"])
        assert s["state"] == "failed"
        assert not api.requests  # nothing reached the platform without a credential
    finally:
        hub.workshop = None


async def test_service_build_stays_off_without_the_owners_choice(hub: Hub) -> None:
    assert await service.build(hub) is None  # WORKSHOP_RUNTIME is empty by default
    assert service.meta_runtime(hub) is None


# --------------------------------------------------------------- commands --
@pytest.mark.parametrize(
    ("cmd", "verdict", "action"),
    [
        ("pytest -q", "allow", "command"),
        ("ruff check . && mypy src", "allow", "command"),
        ("git status", "allow", "command"),
        ("git commit -m 'fix login'", "allow", "command"),
        ("git push origin hq/S-0007", "ask", "push_branch"),
        ("git push -u origin HEAD:refs/heads/hq/S-0007", "ask", "push_branch"),
        ("gh pr create --fill", "ask", "open_pr"),
        ("curl https://example.com", "ask", "command"),
        ("terraform plan", "deny", "command"),
        ("git push origin main", "deny", "command"),
        ("git push --force origin hq/S-0007", "deny", "command"),
        ("git push origin +hq/S-0007", "deny", "command"),
        ("gh pr merge 12", "deny", "command"),
        ("ssh root@10.10.1.1", "deny", "command"),
        ("cat .env", "deny", "command"),
        ("printenv", "deny", "command"),
        ("ls && docker ps", "deny", "command"),
        ("echo $(whoami)", "ask", "command"),
        ("unknowntool --x", "ask", "command"),
    ],
)
def test_the_command_rules(cmd: str, verdict: str, action: str) -> None:
    r = commands.classify(cmd, session_ref="S-0007")
    assert (r.verdict, r.action) == (verdict, action), r


def test_the_fake_runtime_spec_needs_nothing() -> None:
    spec = SessionSpec(
        ref="S-1", workspace="X-APP", repo="o/r", default_branch="main", branch="hq/S-1",
        title="t", brief="b", model="m", effort="low", budget_usd=Decimal(1), actions=["read"],
    )  # fmt: skip
    assert spec.branch_prefix == "hq/"


async def test_managed_reads_the_owner_secrets_under_the_kv_mount() -> None:
    """read_kv adds the `kv` mount itself: the paths are relative to it (a
    `kv/` prefix would ask for kv/data/kv/... and never find them)."""
    from types import SimpleNamespace

    from hq_api.workshop import service

    asked: list[str] = []

    class Bao:
        async def read_kv(self, path: str) -> dict[str, Any]:
            asked.append(path)
            if path == "hq-api/workshop/managed":
                return {"api_key": "k", "agent_id": "a", "environment_id": "e"}
            return {"token": "t"}

    hub = SimpleNamespace(settings=SimpleNamespace(workshop_runtime="managed"), bao=Bao())
    rt = await service.build(hub)
    assert rt is not None and asked == ["hq-api/workshop/managed"]
    assert all(not p.startswith("kv/") for p in asked)
