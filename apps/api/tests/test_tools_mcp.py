"""Prompt 07 §3 (contract §18.7, §18.10): MCP servers exist for agents only
after the owner's two seals; the api tells the gateway the sealed class of a
tool (an A3 tool becomes an `a3_action` decision), pins the server's listing
and switches it off when it changes; the catalog; PDF text for files.read."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from hq_api.hub import Hub

from .conftest import agent_headers, body_bytes, idem, step_up

SECRET = "mcp-owner-secret-" + "q" * 24
PHONE = "0912" + "345" + "6789"


class FakeBao:
    """OpenBao as the api sees it: the owner's secret for one server."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    async def read_kv(self, path: str) -> dict[str, Any]:
        if path not in self.data:
            raise KeyError(path)
        return self.data[path]


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
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], body: dict[str, Any]
) -> httpx.Response:
    content = body_bytes(body)
    su = await step_up(
        hub, owner_session["session_id"], "mcp.add", hashlib.sha256(content).hexdigest()
    )
    return await client.post(
        "/api/v1/tools/mcp",
        content=content,
        headers={**owner_session["headers"], **su, "Content-Type": "application/json"},
    )


async def enable(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], key: str
) -> httpx.Response:
    su = await step_up(hub, owner_session["session_id"], "mcp.enable", key)
    return await client.post(
        f"/api/v1/tools/mcp/{key}/enable", headers={**owner_session["headers"], **su}
    )


def key() -> str:
    return "t" + uuid.uuid4().hex[:10]


async def resolve(
    client: httpx.AsyncClient, code: str, server: str, tool: str, args: Any = None
) -> httpx.Response:
    canon = json.dumps(args or {}, sort_keys=True, separators=(",", ":"))
    return await client.post(
        "/internal/v1/tools/mcp/resolve",
        headers=await agent_headers(code),
        json={
            "server": server,
            "tool": tool,
            "args_sha256": hashlib.sha256(canon.encode()).hexdigest(),
            "preview": canon,
        },
    )


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
    r = await client.post("/api/v1/tools/mcp", json=body, headers=owner_session["headers"])
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    # A step-up for another body is no seal for this one.
    other = await step_up(hub, owner_session["session_id"], "mcp.add", "0" * 64)
    r = await client.post(
        "/api/v1/tools/mcp", json=body, headers={**owner_session["headers"], **other}
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
    r = await client.post(f"/api/v1/tools/mcp/{k}/enable", headers=owner_session["headers"])
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    r = await enable(client, hub, owner_session, k)
    assert (r.status_code, r.json()["status"]) == (200, "enabled")
    # A new registration of the same key is a new version, pending again.
    r = await add(client, hub, owner_session, server_body(k, title_fa="نسخه‌ی دوم"))
    assert (r.json()["status"], r.json()["version"]) == ("pending", 3)
    r = await client.post(f"/api/v1/tools/mcp/{k}/disable", headers=owner_session["headers"])
    assert r.json()["status"] == "disabled"
    assert (
        await client.post("/api/v1/tools/mcp/nope-nope/disable", headers=owner_session["headers"])
    ).status_code == 404


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"url": "http://crm.example.com/mcp"}, "https"),
        ({"url": "https://hq.coinepro.com/internal/x"}, "hub"),
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
    # An A3 tool: an a3_action decision, once per run and arguments; nothing for the gateway to run.
    args = {"to": "someone@example.com", "body": f"call {PHONE}"}
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
    assert len(payload["args_sha256"]) == 64 and SECRET not in json.dumps(payload)
    other_args = (await resolve(client, me, k, "send_email", {"to": "b@example.com"})).json()
    assert other_args["decision"] != first["decision"]
    await _finish_runs(su, [me, f"{other}-TECH-MGR"])


async def test_caps(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    k = key()
    await add(client, hub, owner_session, server_body(k, auth_header=None))
    await enable(client, hub, owner_session, k)
    real = hub.settings
    hub.settings = replace(real, mcp_calls_per_run=2)
    try:
        codes = [
            (await resolve(client, f"{co}-TECH-MGR", k, "lookup")).status_code for _ in range(3)
        ]
    finally:
        hub.settings = real
    assert codes == [200, 200, 429]
    r = await resolve(client, f"{co}-TECH-MGR", k, "lookup")
    assert r.status_code == 200 and r.json()["server"]["secret"] is None  # no auth header: none
    await _finish_runs(su, [f"{co}-TECH-MGR"])


async def test_the_listing_is_pinned_and_a_change_switches_the_server_off(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    k = key()
    await add(client, hub, owner_session, server_body(k))
    await enable(client, hub, owner_session, k)
    pin = "a" * 64
    url = f"/internal/v1/tools/mcp/{k}/listing"
    r = await client.post(
        url, headers=await agent_headers(me), json={"listing_sha256": pin, "tools": ["lookup"]}
    )
    assert r.json() == {"status": "enabled"}
    assert (await resolve(client, me, k, "lookup")).json()["server"]["listing_sha256"] == pin
    same = await client.post(url, headers=await agent_headers(me), json={"listing_sha256": pin})
    assert same.json() == {"status": "enabled"}
    r = await client.post(
        url,
        headers=await agent_headers(me),
        json={"listing_sha256": "b" * 64, "tools": ["lookup", "transfer_money"]},
    )
    assert r.json() == {"status": "disabled"}
    row = await su.fetchrow(
        "SELECT status, status_reason, listed_tools FROM tools.mcp_servers WHERE key = $1", k
    )
    assert row["status_reason"] == "tools changed" and "transfer_money" in row["listed_tools"]
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_kind = 'mcp_server' AND link_ref = $1",
        k,
    )
    r = await resolve(client, me, k, "lookup")
    assert (r.status_code, r.json()["code"]) == (503, "channel_not_configured")
    # Sealed again: enabled, a fresh pin on the next listing.
    await enable(client, hub, owner_session, k)
    r = await resolve(client, me, k, "lookup")
    assert r.json()["server"]["listing_sha256"] is None
    await _finish_runs(su, [me])


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
