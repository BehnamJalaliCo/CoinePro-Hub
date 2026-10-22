"""Prompt 07 §3 and its review 7.1 §2.10-§2.16, §3 (contract §18.7, §18.10,
§18.13): MCP servers exist for agents only after the owner's two seals; the
api tells the gateway the sealed class of a tool (an A3 tool becomes an
`a3_action` decision, and its approval runs that one call once), pins the
server's listing and, when it changes, switches the server off and raises a
`tool_enable` card; the three POSTs are idempotent; the catalog; PDF text for
files.read."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hq_api.domain import mcp as M
from hq_api.hub import Hub

from .conftest import agent_headers, body_bytes, idem, step_up

SECRET = "mcp-owner-secret-" + "q" * 24
PHONE = "0912" + "345" + "6789"
LONG_AGO = "2000-01-01T00:00:00.123456789Z"


class FakeBao:
    """OpenBao as the api sees it: the owner's secret for one server, and when
    it was written (KV version metadata)."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.written: dict[str, str] = {}

    def put(self, path: str, data: dict[str, Any]) -> None:
        """A new version now (RFC 3339 with nanoseconds, as OpenBao writes it)."""
        self.data[path] = data
        self.written[path] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"

    async def read_kv(self, path: str) -> dict[str, Any]:
        return (await self.read_kv_meta(path))[0]

    async def read_kv_meta(self, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if path not in self.data:
            raise KeyError(path)
        return self.data[path], {"created_time": self.written.get(path, LONG_AGO), "version": 1}


@pytest.fixture
async def bao(hub: Hub) -> AsyncIterator[FakeBao]:
    real = hub.bao
    hub.bao = FakeBao()
    yield hub.bao
    hub.bao = real


def server_body(key: str, companies: Any = "all", **over: Any) -> dict[str, Any]:
    body = {
        "key": key,
        "title_fa": "سرور آزمایشی",
        "transport": "http",
        "url": "https://crm.example.com/mcp",
        "tools": [
            {"name": "lookup", "class": "A0"},
            {"name": "update_note", "class": "A2"},
            {"name": "send_email", "class": "A3"},
            {"name": "old_tool", "class": "A0", "enabled": False},
        ],
        "companies": companies,
        "auth_header": "Authorization",
    }
    body.update(over)
    return body


async def add(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    body: dict[str, Any],
    key: dict[str, str] | None = None,
) -> httpx.Response:
    content = body_bytes(body)
    su = await step_up(
        hub, owner_session["session_id"], "mcp.add", hashlib.sha256(content).hexdigest()
    )
    return await client.post(
        "/api/v1/tools/mcp",
        content=content,
        headers={
            **owner_session["headers"], **su, **(key or idem()), "Content-Type": "application/json",
        },
    )  # fmt: skip


async def enable(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], key: str
) -> httpx.Response:
    su = await step_up(hub, owner_session["session_id"], "mcp.enable", key)
    return await client.post(
        f"/api/v1/tools/mcp/{key}/enable", headers={**owner_session["headers"], **su, **idem()}
    )


async def disable(
    client: httpx.AsyncClient, owner_session: dict[str, Any], key: str
) -> httpx.Response:
    return await client.post(
        f"/api/v1/tools/mcp/{key}/disable", headers={**owner_session["headers"], **idem()}
    )


def key() -> str:
    return "t" + uuid.uuid4().hex[:10]


def sha_of(args: Any) -> str:
    canon = json.dumps(args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


async def resolve(
    client: httpx.AsyncClient, code: str, server: str, tool: str, args: Any = None
) -> httpx.Response:
    return await client.post(
        "/internal/v1/tools/mcp/resolve",
        headers=await agent_headers(code),
        json={
            "server": server,
            "tool": tool,
            "args_sha256": sha_of(args),
            "preview": json.dumps(args or {}, ensure_ascii=False),
            "args": args or {},
        },
    )


async def listing(
    client: httpx.AsyncClient, code: str, server: str, tools: dict[str, str]
) -> httpx.Response:
    """What the gateway reports: per tool its digest; the listing's digest."""
    rows = [{"name": n, "description": f"{n} tool", "sha256": d} for n, d in sorted(tools.items())]
    return await client.post(
        f"/internal/v1/tools/mcp/{server}/listing",
        headers=await agent_headers(code),
        json={
            "listing_sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            "tools": sorted(tools),
            "listing": rows,
        },
    )


async def decide(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str, verdict: str
) -> httpx.Response:
    headers = {**owner_session["headers"], **idem()}
    if verdict == "approve":
        headers.update(await step_up(hub, owner_session["session_id"], "decision.approve", ref))
    return await client.post(f"/api/v1/decisions/{ref}/{verdict}", headers=headers, json={})


async def _finish_runs(su: Any, codes: list[str]) -> None:
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'running'
             AND r.reason = 'test'""",
        codes,
    )


async def test_a_server_needs_both_seals(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], bao: FakeBao
) -> None:
    k = key()
    body = server_body(k)
    r = await client.post(
        "/api/v1/tools/mcp", json=body, headers={**owner_session["headers"], **idem()}
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    # A step-up for another body is no seal for this one.
    other = await step_up(hub, owner_session["session_id"], "mcp.add", "0" * 64)
    r = await client.post(
        "/api/v1/tools/mcp", json=body, headers={**owner_session["headers"], **other, **idem()}
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_invalid")
    r = await add(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["status"], s["has_secret"], s["version"]) == ("pending", False, 1)
    assert [t["class"] for t in s["tools"]] == ["A0", "A2", "A3", "A0"]
    bao.data[f"hq-api/tools/mcp/{k}"] = {"token": SECRET}
    listed = (await client.get("/api/v1/tools/mcp", headers=owner_session["headers"])).json()
    mine = next(x for x in listed if x["key"] == k)
    assert mine["has_secret"] is True and SECRET not in json.dumps(listed)
    r = await client.post(
        f"/api/v1/tools/mcp/{k}/enable", headers={**owner_session["headers"], **idem()}
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    r = await enable(client, hub, owner_session, k)
    assert (r.status_code, r.json()["status"]) == (200, "enabled")
    # The same body again (7.1 §3): nothing changes, the server stays enabled.
    r = await add(client, hub, owner_session, body)
    assert (r.status_code, r.json()["status"], r.json()["version"]) == (201, "enabled", 2)
    # Another body for the same key is a new version, pending again.
    r = await add(client, hub, owner_session, server_body(k, title_fa="نسخه‌ی دوم"))
    assert (r.json()["status"], r.json()["version"]) == ("pending", 3)
    assert r.json()["status_reason"] == "registration changed"
    r = await disable(client, owner_session, k)
    assert r.json()["status"] == "disabled"
    assert (await disable(client, owner_session, "nope-nope")).status_code == 404


async def test_the_three_posts_are_idempotent(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    """7.1 §2.13: Idempotency-Key is required and claimed before the seal is
    consumed, so the same key and body answer the first 201 again (the
    step-up was spent once) with Idempotent-Replay."""
    k = key()
    body = server_body(k)
    content = body_bytes(body)
    seal = await step_up(
        hub, owner_session["session_id"], "mcp.add", hashlib.sha256(content).hexdigest()
    )
    headers = {**owner_session["headers"], **seal, "Content-Type": "application/json"}
    r = await client.post("/api/v1/tools/mcp", content=content, headers=headers)
    assert (r.status_code, r.json()["fields"]) == (422, {"Idempotency-Key": "required"})
    same = idem()
    first = await client.post("/api/v1/tools/mcp", content=content, headers={**headers, **same})
    again = await client.post("/api/v1/tools/mcp", content=content, headers={**headers, **same})
    assert (first.status_code, again.status_code) == (201, 201), again.text
    assert again.headers.get("Idempotent-Replay") == "true" and again.json() == first.json()
    assert again.json()["tools"][0]["class"] == "A0"  # the replay keeps the aliases
    assert await su.fetchval("SELECT version FROM tools.mcp_servers WHERE key = $1", k) == 1
    # The same key with another body is a conflict, not a replay.
    other = body_bytes(server_body(k, title_fa="دیگر"))
    r = await client.post("/api/v1/tools/mcp", content=other, headers={**headers, **same})
    assert (r.status_code, r.json()["code"]) == (409, "idempotency_conflict")
    # enable and disable: required, and replayed the same way.
    for path in (f"/api/v1/tools/mcp/{k}/enable", f"/api/v1/tools/mcp/{k}/disable"):
        r = await client.post(path, headers=owner_session["headers"])
        assert (r.status_code, r.json()["code"]) == (422, "validation_failed"), path
    seal = await step_up(hub, owner_session["session_id"], "mcp.enable", k)
    same = {**owner_session["headers"], **seal, **idem()}
    first = await client.post(f"/api/v1/tools/mcp/{k}/enable", headers=same)
    again = await client.post(f"/api/v1/tools/mcp/{k}/enable", headers=same)
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.headers.get("Idempotent-Replay") == "true" and again.json() == first.json()


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"url": "http://crm.example.com/mcp"}, "https"),
        ({"url": "https://hq.coinepro.com/internal/x"}, "hub"),
        ({"url": "https://hq.coinepro.com./internal/x"}, "hub"),  # the root's dot (7.1 §3)
        ({"url": "https://api.hq.coinepro.com/x"}, "hub"),
        ({"url": "https://crm.example.com:8443/mcp"}, "443"),  # only 443 (7.1 §3)
        ({"url": "https://10.10.1.1/mcp"}, "address"),
        ({"url": "https://user:pw@crm.example.com/mcp"}, "credentials"),
        ({"transport": "container", "url": "http://postgres:5432/"}, "container"),
        ({"tools": [{"name": "a", "class": "A0"}, {"name": "a", "class": "A1"}]}, "once"),
        ({"tools": [{"name": "a", "class": "A4"}]}, "class"),
        ({"companies": ["nope"]}, "company"),
    ],
)
async def test_bad_registrations_are_refused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    over: dict[str, Any],
    field: str,
) -> None:
    body = server_body(key(), **over)
    r = await add(client, hub, owner_session, body)
    assert r.status_code == 422, (over, r.text)
    assert field in r.text.lower() or r.json()["code"] == "validation_failed"


def test_the_url_check() -> None:
    M.check_url("http", "https://crm.example.com:443/mcp")  # the default port, written out
    assert M.host_of("https://CRM.Example.com./mcp") == "crm.example.com"


async def test_another_host_voids_the_secret(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    bao: FakeBao,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """7.1 §3: a registration that moves the server to another host never
    sends it the old host's secret; the owner writes it again."""
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    path = f"hq-api/tools/mcp/{k}"
    bao.put(path, {"token": SECRET})
    await add(client, hub, owner_session, server_body(k))
    r = await add(client, hub, owner_session, server_body(k, title_fa="همان میزبان"))
    assert r.json()["has_secret"] is True  # the same host: the secret stays
    r = await add(client, hub, owner_session, server_body(k, url="https://other.example.org/mcp"))
    assert r.json()["has_secret"] is False
    assert (await enable(client, hub, owner_session, k)).status_code == 200
    out = (await resolve(client, me, k, "lookup")).json()
    assert out["server"]["url"] == "https://other.example.org/mcp", out
    assert out["server"]["secret"] is None  # nothing for the new host
    bao.put(path, {"token": SECRET + "-new"})  # the owner writes it again
    listed = (await client.get("/api/v1/tools/mcp", headers=owner_session["headers"])).json()
    assert next(x for x in listed if x["key"] == k)["has_secret"] is True
    assert (await resolve(client, me, k, "lookup")).json()["server"]["secret"] == SECRET + "-new"
    await _finish_runs(su, [me])


async def test_a_container_server_is_not_runnable_yet(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any]
) -> None:
    """7.1 §2.15: no hq-mcp network and no stdio bridge in this build."""
    k = key()
    body = server_body(k, transport="container", url="http://mcp-time:8000/mcp", auth_header=None)
    r = await add(client, hub, owner_session, body)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert r.json()["status_reason"].startswith("not runnable yet")
    r = await enable(client, hub, owner_session, k)
    assert (r.status_code, r.json()["code"]) == (409, "not_ready")
    assert "not runnable yet" in r.json()["detail"]
    items = {
        t["name"]: t
        for t in (
            await client.get("/api/v1/tools/catalog", headers=owner_session["headers"])
        ).json()
    }
    lookup = items[f"{k}/lookup"]
    assert lookup["status"] == "channel_not_configured"
    assert "هنوز اجراشدنی نیست" in lookup["description"]
    assert "not runnable yet" in lookup["description"]


async def test_resolve_gives_the_sealed_class_and_makes_a3_a_decision(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    bao: FakeBao,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    bao.data[f"hq-api/tools/mcp/{k}"] = {"token": SECRET}
    assert (
        await add(client, hub, owner_session, server_body(k, companies=[co]))
    ).status_code == 201
    # Pending: nothing for the agents yet.
    r = await resolve(client, me, k, "lookup")
    assert (r.status_code, r.json()["code"]) == (503, "channel_not_configured")
    await enable(client, hub, owner_session, k)
    r = await resolve(client, me, k, "lookup", {"name": "Sara"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["class"] == "A0" and out["server"]["secret"] == SECRET  # for the gateway's header
    assert out["server"]["url"] == "https://crm.example.com/mcp"
    assert out["server"]["listing_sha256"] is None  # not pinned yet
    assert (await resolve(client, me, k, "update_note")).json()["class"] == "A2"
    # A tool the owner did not seal (or sealed off), a company it is not for, an unknown server.
    for tool in ("delete_all", "old_tool"):
        r = await resolve(client, me, k, tool)
        assert (r.status_code, r.json()["code"]) == (403, "policy_denied"), tool
    r = await resolve(client, f"{other}-TECH-MGR", k, "lookup")
    assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    r = await resolve(client, me, "no-such-server", "lookup")
    assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    # An A3 tool: an a3_action decision, once while it is pending; nothing for the gateway to run.
    args = {"to": "someone@example.com", "body": f"pay 1500 USD, call {PHONE}"}
    first = (await resolve(client, me, k, "send_email", args)).json()
    again = (await resolve(client, me, k, "send_email", args)).json()
    assert first["class"] == "A3" and first["server"] is None
    assert first["decision"].startswith("D-") and again["decision"] == first["decision"]
    d = await su.fetchrow(
        "SELECT kind, payload, proposer_code, status FROM cartable.decisions WHERE ref = $1",
        first["decision"],
    )
    assert (d["kind"], d["proposer_code"], d["status"]) == ("a3_action", me, "pending")
    payload = json.loads(d["payload"])
    assert payload["action"] == "mcp_call" and payload["target"] == f"{k}/send_email"
    assert (payload["server"], payload["tool"]) == (k, "send_email")
    assert len(payload["args_sha256"]) == 64 and SECRET not in json.dumps(payload)
    assert len(payload["registration_sha256"]) == 64
    # The owner sees the recipient and the amount (only secrets are masked).
    assert payload["args"] == args and "someone@example.com" in payload["preview"]
    other_args = (await resolve(client, me, k, "send_email", {"to": "b@example.com"})).json()
    assert other_args["decision"] != first["decision"]
    await _finish_runs(su, [me, f"{other}-TECH-MGR"])


async def test_an_approved_a3_card_runs_its_call_exactly_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    bao: FakeBao,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """7.1 §2.10: the follow-up run's identical call (any run) consumes the
    approved card once; the next identical call needs a new card; a token in
    the arguments is masked on the card; a rejected card answers denied
    without a new card."""
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    bao.data[f"hq-api/tools/mcp/{k}"] = {"token": SECRET}
    await add(client, hub, owner_session, server_body(k))
    await enable(client, hub, owner_session, k)
    token = "sk-ant-" + "z" * 30
    args = {"to": "sara@example.com", "amount": 1500, "api_key": token}
    shown = {"to": "sara@example.com", "amount": 1500, "api_key": token}
    card = (await resolve(client, me, k, "send_email", shown)).json()["decision"]
    payload = json.loads(
        await su.fetchval("SELECT payload FROM cartable.decisions WHERE ref = $1", card)
    )
    assert payload["args"]["to"] == "sara@example.com" and payload["args"]["amount"] == 1500
    assert token not in json.dumps(payload) and payload["args"]["api_key"] == "[redacted]"
    assert (await decide(client, hub, owner_session, card, "approve")).status_code == 200
    # The follow-up is another run of the same agent.
    await _finish_runs(su, [me])
    r = await resolve(client, me, k, "send_email", args)
    assert r.status_code == 200, r.text
    ran = r.json()
    assert (ran["class"], ran["decision"]) == ("A3", card)
    assert (
        ran["server"]["url"] == "https://crm.example.com/mcp" and ran["server"]["secret"] == SECRET
    )
    used = await su.fetch(
        """SELECT c.outcome FROM tools.mcp_calls c JOIN cartable.decisions d ON d.id = c.decision_id
           WHERE d.ref = $1 ORDER BY c.at""",
        card,
    )
    assert [u["outcome"] for u in used] == ["decision", "approved"]
    # Once: the same call again is a new card, not a second run.
    nxt = (await resolve(client, me, k, "send_email", args)).json()
    assert nxt["server"] is None and nxt["decision"] not in (None, card)
    # A changed argument is not the approved call either.
    changed = (await resolve(client, me, k, "send_email", {**args, "amount": 15000})).json()
    assert changed["server"] is None and changed["decision"] not in (card, nxt["decision"])
    # Rejected: denied, and no new card for the same call.
    assert (await decide(client, hub, owner_session, nxt["decision"], "reject")).status_code == 200
    cards = "SELECT count(*) FROM cartable.decisions WHERE kind = 'a3_action' AND payload ->> 'server' = $1"
    before = await su.fetchval(cards, k)
    r = await resolve(client, me, k, "send_email", args)
    assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    assert nxt["decision"] in r.json()["message_fa"] and await su.fetchval(cards, k) == before
    await _finish_runs(su, [me])


async def test_caps(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    await add(client, hub, owner_session, server_body(k, auth_header=None))
    await enable(client, hub, owner_session, k)
    real = hub.settings
    hub.settings = replace(real, mcp_calls_per_run=2)
    try:
        answers = [await resolve(client, me, k, "lookup") for _ in range(3)]
        # A3 is capped too (7.1 §3): no card past the cap.
        a3 = await resolve(client, me, k, "send_email", {"to": "x@example.com"})
    finally:
        hub.settings = real
    assert [a.status_code for a in answers] == [200, 200, 429]
    assert (
        answers[2].json()["code"] == "rate_limited" and int(answers[2].headers["Retry-After"]) > 0
    )
    assert a3.status_code == 429 and a3.headers.get("Retry-After")
    hub.settings = replace(real, mcp_calls_per_company_day=0)
    try:
        r = await resolve(client, me, k, "lookup")
    finally:
        hub.settings = real
    assert r.status_code == 429 and 0 < int(r.headers["Retry-After"]) <= 86400
    r = await resolve(client, me, k, "lookup")
    assert r.status_code == 200 and r.json()["server"]["secret"] is None  # no auth header: none
    await _finish_runs(su, [me])


async def test_a_changed_listing_raises_a_tool_enable_card(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """7.1 §2.16: the first listing after an enable is pinned; a changed one
    switches the server off and raises a `tool_enable` card with the diff; a
    listing changed again before the seal supersedes the card (409
    decision_not_pending) and raises a new one; the seal re-enables the server
    with exactly that listing. A company the server is not for cannot report."""
    co = (await new_company())["code"]
    outsider = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    await add(client, hub, owner_session, server_body(k, companies=[co]))
    await enable(client, hub, owner_session, k)
    v1 = {"lookup": "1" * 64, "send_email": "2" * 64}
    r = await listing(client, me, k, v1)
    assert r.json() == {"status": "enabled"}
    pin = await su.fetchval("SELECT listing_sha256 FROM tools.mcp_servers WHERE key = $1", k)
    assert (await resolve(client, me, k, "lookup")).json()["server"]["listing_sha256"] == pin
    assert (await listing(client, me, k, v1)).json() == {"status": "enabled"}
    # Another company's agent cannot switch it off.
    r = await listing(client, f"{outsider}-TECH-MGR", k, {"x": "9" * 64})
    assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    # The server changed: one tool added, one changed.
    v2 = {"lookup": "1" * 64, "send_email": "3" * 64, "transfer_money": "4" * 64}
    assert (await listing(client, me, k, v2)).json() == {"status": "disabled"}
    row = await su.fetchrow("SELECT * FROM tools.mcp_servers WHERE key = $1", k)
    assert row["status_reason"] == "tools changed" and "transfer_money" in row["listed_tools"]
    cards = await su.fetch(
        """SELECT ref, status, payload, company_id, proposer_kind FROM cartable.decisions
           WHERE kind = 'tool_enable' AND payload ->> 'key' = $1 ORDER BY created_at""",
        k,
    )
    assert len(cards) == 1 and cards[0]["status"] == "pending"
    first = json.loads(cards[0]["payload"])
    assert first["key"] == k and first["listing_sha256"] == row["listed_sha256"] != pin
    assert first["diff"] == {"added": ["transfer_money"], "removed": [], "changed": ["send_email"]}
    holding = (await hub.companies.holding()).id
    assert cards[0]["company_id"] == holding and cards[0]["proposer_kind"] == "service"
    r = await resolve(client, me, k, "lookup")
    assert (r.status_code, r.json()["code"]) == (503, "channel_not_configured")
    # The listing changes again before the seal: that card is superseded.
    v3 = {"lookup": "1" * 64, "send_email": "3" * 64}
    assert (await listing(client, me, k, v3)).json() == {"status": "disabled"}
    r = await decide(client, hub, owner_session, cards[0]["ref"], "approve")
    assert (r.status_code, r.json()["code"]) == (409, "decision_not_pending")
    cards = await su.fetch(
        """SELECT ref, status, payload FROM cartable.decisions
           WHERE kind = 'tool_enable' AND payload ->> 'key' = $1 ORDER BY created_at""",
        k,
    )
    assert [c["status"] for c in cards] == ["withdrawn", "pending"]
    second = json.loads(cards[1]["payload"])
    assert second["diff"] == {"added": [], "removed": [], "changed": ["send_email"]}
    # Without its seal the approval is refused; with it the server is back with that listing.
    r = await client.post(
        f"/api/v1/decisions/{cards[1]['ref']}/approve",
        headers={**owner_session["headers"], **idem()},
        json={},
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    r = await decide(client, hub, owner_session, cards[1]["ref"], "approve")
    assert r.status_code == 200, r.text
    assert r.json()["effect_status"] == "applied"
    row = await su.fetchrow("SELECT * FROM tools.mcp_servers WHERE key = $1", k)
    assert (row["status"], row["listing_sha256"]) == ("enabled", second["listing_sha256"])
    out = (await resolve(client, me, k, "lookup")).json()
    assert out["server"]["listing_sha256"] == second["listing_sha256"]
    assert (await listing(client, me, k, v3)).json() == {"status": "enabled"}  # exactly that one
    assert (await listing(client, me, k, v2)).json() == {"status": "disabled"}  # anything else: off
    # The owner's own enable seal withdraws the open card (it is moot).
    await enable(client, hub, owner_session, k)
    statuses = await su.fetch(
        """SELECT status FROM cartable.decisions WHERE kind = 'tool_enable'
           AND payload ->> 'key' = $1 ORDER BY created_at""",
        k,
    )
    assert [s["status"] for s in statuses] == ["withdrawn", "approved", "withdrawn"]
    assert (await resolve(client, me, k, "lookup")).json()["server"]["listing_sha256"] is None
    listed = (await client.get("/api/v1/tools/mcp", headers=owner_session["headers"])).json()
    mine = next(x for x in listed if x["key"] == k)
    assert {"name": "send_email", "description": "send_email tool"} in mine["listed_tools"]
    await _finish_runs(su, [me, f"{outsider}-TECH-MGR"])


async def test_the_catalog(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], bao: FakeBao
) -> None:
    k = key()
    bao.data[f"hq-api/tools/mcp/{k}"] = {"token": SECRET}
    await add(client, hub, owner_session, server_body(k))
    r = await client.get("/api/v1/tools/catalog", headers=owner_session["headers"])
    assert r.status_code == 200
    items = {t["name"]: t for t in r.json()}
    assert SECRET not in r.text
    assert items["work.get"]["status"] == "live" and items["work.get"]["class"] == "A0"
    assert items["files.read"]["status"] == "live" and "cto" in items["files.read"]["roles"]
    assert items["github.read"]["status"] == "channel_not_configured"
    browse = items["web.browse"]
    assert (browse["class"], browse["per_call"], browse["source"]) == ("A0/A2", True, "web")
    assert items["mcp.call"]["class"] == "per tool" and items["mcp.call"]["source"] == "mcp"
    sealed = items[f"{k}/send_email"]
    assert (sealed["class"], sealed["status"], sealed["server"]) == ("A3", "pending", k)
    assert "cto" in sealed["roles"] and items[f"{k}/old_tool"]["status"] == "off"
    await enable(client, hub, owner_session, k)
    items = {
        t["name"]: t
        for t in (
            await client.get("/api/v1/tools/catalog", headers=owner_session["headers"])
        ).json()
    }
    assert items[f"{k}/lookup"]["status"] == "live" and items["mcp.call"]["status"] == "live"


# --------------------------------------------------------- PDF for files.read --
def pdf_with(text: str) -> bytes:
    """A one-page PDF with `text` in Helvetica (ASCII only)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


async def test_pdf_text_reaches_files_read_masked(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    # An agent's own PDF.
    r = await client.post(
        "/internal/v1/files",
        params={"name": "contract.pdf"},
        headers={**await agent_headers(me), "Content-Type": "application/pdf"},
        content=pdf_with(f"Contract total 500 call {PHONE}"),
    )
    assert r.status_code == 201, r.text
    meta = (
        await client.get(
            f"/internal/v1/files/{r.json()['id']}/meta", headers=await agent_headers(me)
        )
    ).json()
    assert "Contract total 500" in meta["text"] and PHONE not in meta["text"]
    # A broken PDF: stored, no text, no error.
    r = await client.post(
        "/internal/v1/files",
        params={"name": "broken.pdf"},
        headers={**await agent_headers(me), "Content-Type": "application/pdf"},
        content=b"%PDF-1.4\n garbage",
    )
    assert r.status_code == 201
    meta = (
        await client.get(
            f"/internal/v1/files/{r.json()['id']}/meta", headers=await agent_headers(me)
        )
    ).json()
    assert meta["text"] is None
    # The owner's PDF: text at upload, in files.processing (files.files stays append-only).
    r = await client.post(
        "/api/v1/files",
        content=pdf_with("Owner plan for Q4"),
        headers={**owner, **idem(), "Content-Type": "application/pdf", "X-File-Name": "plan.pdf"},
    )
    assert r.status_code == 201, r.text
    row = await su.fetchrow(
        "SELECT status, text FROM files.processing WHERE file_id = $1", uuid.UUID(r.json()["id"])
    )
    assert row["status"] == "ready" and "Owner plan for Q4" in row["text"]
    assert r.json()["status"] == "ready"
    await _finish_runs(su, [me])


def test_the_proposed_servers_are_valid_registrations() -> None:
    """apps/api/seed/mcp_proposals.yaml: what the owner may register as it is."""
    from pathlib import Path

    import yaml

    from hq_api.domain import mcp as M

    data = yaml.safe_load((Path(__file__).parents[1] / "seed" / "mcp_proposals.yaml").read_text())
    keys = []
    for p in data["proposals"]:
        body = {k: p[k] for k in ("key", "title_fa", "transport", "url", "tools", "companies")}
        M.McpServerIn.model_validate(body)
        keys.append(p["key"])
    assert keys == ["github-read", "search-console", "analytics", "time", "fetch"]
