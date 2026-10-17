"""The agents' internet on the api's side (prompt 07 §2, contract §18.7): the
data guard, the limits, the service accounts and the egress log."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx

from hq_api.hub import Hub
from hq_common.openbao import SecretNotFound

from .conftest import agent_headers, idem

SECRET = "acct-secret-" + "K" * 28


class FakeBao:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets

    async def read_kv(self, path: str) -> dict[str, Any]:
        key = path.removeprefix("tools/accounts/")
        if key not in self.secrets:
            raise SecretNotFound(path)
        return {"secret": self.secrets[key]}


async def _reserve(client: httpx.AsyncClient, h: dict[str, str], **body: Any) -> httpx.Response:
    return await client.post(
        "/internal/v1/egress/reserve", headers=h, json={"tool": "web.search", "class": "A0", **body}
    )


ENTRY = {"tool": "web.read", "method": "GET", "host": "example.com", "kind": "request", "status": 200,
         "bytes_in": 1200, "bytes_out": 0, "ms": 40, "class": "A0"}  # fmt: skip


async def test_the_data_guard_refuses_and_logs(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    ok = await _reserve(client, h, strings=["persian calendar", "COVID-19 GPT-4 SHA-256 ISO 9001"])
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["account"] is None and body["max_bytes"] > 0 and body["requests_left"] > 0
    for text in (
        "status of W-000123 please",
        "decision D-000004",
        f"what does {co['code']}-TECH-MGR think",
        "write to ali.rezaei@example.com",
        "call 09123456789",
        "token ghp_" + "a" * 36,
    ):
        r = await _reserve(client, h, strings=[text])
        assert r.status_code == 403 and r.json()["code"] == "internal_data", text
    r = await _reserve(client, h, url="https://example.com/?ref=W-000777")
    assert r.status_code == 403
    blocked = await su.fetchval(
        "SELECT count(*) FROM egress.log WHERE company_id = $1 AND blocked_reason = 'internal_data'",
        co["id"],
    )
    assert blocked == 7
    # A query never reaches the log: only the tool, the method and the host.
    rows = await su.fetch("SELECT * FROM egress.log WHERE company_id = $1", co["id"])
    assert "W-000123" not in json.dumps([dict(r) for r in rows], default=str)


async def test_log_limits_and_who_reads_the_log(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    code = f"{co['code']}-TECH-MGR"
    h = await agent_headers(code)
    r = await client.post(
        "/internal/v1/egress/log",
        headers=h,
        json={"tool": "web.read", "class": "A0", "entries": [ENTRY] * 3},
    )
    assert r.status_code == 204, r.text
    rows = await su.fetch(
        "SELECT actor, host, class, run_id FROM egress.log WHERE company_id = $1", co["id"]
    )
    assert len(rows) == 3 and rows[0]["actor"] == code and rows[0]["run_id"] is not None
    audits = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE company_id = $1 AND action = 'egress.request'",
        co["id"],
    )
    assert audits == 3
    real = hub.settings
    hub.settings = replace(real, egress_run_requests=3)
    try:
        r = await _reserve(client, h, strings=["more"])
        assert r.status_code == 429 and r.json()["code"] == "egress_limit"
    finally:
        hub.settings = real
    hub.settings = replace(real, egress_day_bytes=3000)
    try:
        assert (await _reserve(client, h, strings=["x y"])).status_code == 429
    finally:
        hub.settings = real
    # The owner's log and summary.
    page = (
        await client.get("/api/v1/egress", headers=owner, params={"company": co["code"]})
    ).json()
    assert len(page["items"]) >= 5 and page["items"][0]["class"] in ("A0", "A2")
    only = (
        await client.get(
            "/api/v1/egress", headers=owner, params={"company": co["code"], "blocked": True}
        )
    ).json()
    assert only["items"] and all(i["blocked_reason"] for i in only["items"])
    day = (await client.get("/api/v1/egress/summary", headers=owner)).json()
    mine = next(d for d in day if d["company"] == co["code"])
    assert mine["requests"] >= 5 and mine["blocked"] >= 2 and mine["bytes"] >= 3600
    # egress.recent: a holding-scope reader, not a company's CTO.
    r = await client.get("/internal/v1/egress/recent", headers=h)
    assert r.status_code == 403
    r = await client.get(
        "/internal/v1/egress/recent",
        headers=await agent_headers("HQ-ADV"),
        params={"company": co["code"]},
    )
    assert r.status_code == 200 and len(r.json()["items"]) >= 5


async def test_service_accounts(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co, other = await new_company(), await new_company()
    body = {
        "key": f"crm-{co['code'].lower()}",
        "site": "api.crm.example",
        "title_fa": "حساب CRM",
        "companies": [co["code"]],
        "policy": {
            "inject": {"kind": "header", "name": "X-API-Key"},
            "allow": [{"methods": ["POST"], "path_prefix": "/v1/drafts"}],
        },
    }
    r = await client.post("/api/v1/tools/accounts", headers={**owner, **idem()}, json=body)
    assert r.status_code == 201, r.text
    acct = r.json()
    assert acct["has_secret"] is False and acct["companies"] == [co["code"]]
    assert "secret" not in json.dumps(acct).lower().replace("has_secret", "")
    bad = {**body, "key": "crm-bad", "companies": ["NOPE9"]}
    assert (
        await client.post("/api/v1/tools/accounts", headers={**owner, **idem()}, json=bad)
    ).status_code == 422
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    key = body["key"]
    r = await _reserve(client, h, tool="web.browse", account=key, **{"class": "A2"})
    assert r.status_code == 409 and r.json()["code"] == "account_not_configured"
    hub.bao = FakeBao({key: SECRET})
    try:
        r = await _reserve(client, h, tool="web.browse", account=key, **{"class": "A2"})
        assert r.status_code == 200 and r.json()["account"]["secret"] == SECRET
        assert r.json()["account"]["inject"] == {"kind": "header", "name": "X-API-Key"}
        listed = (await client.get("/api/v1/tools/accounts", headers=owner)).json()
        assert next(a for a in listed if a["key"] == key)["has_secret"] is True
        assert SECRET not in json.dumps(listed)
        # Another company may not use it.
        r = await _reserve(client, await agent_headers(f"{other['code']}-TECH-MGR"), account=key)
        assert r.status_code == 403
        # A call other than GET: only where the policy says it commits to nothing.
        post = {"tool": "http.request", "class": "A2", "method": "POST", "account": key}
        r = await client.post("/internal/v1/egress/reserve", headers=h,
                              json={**post, "url": "https://api.crm.example/v1/drafts/1"})  # fmt: skip
        assert r.status_code == 200
        for url in ("https://api.crm.example/v1/send", "https://evil.example/v1/drafts"):
            r = await client.post(
                "/internal/v1/egress/reserve", headers=h, json={**post, "url": url}
            )
            assert r.status_code == 403 and r.json()["code"] == "needs_owner", url
        no_acct = {**post, "account": None, "url": "https://api.crm.example/v1/drafts/1"}
        r = await client.post("/internal/v1/egress/reserve", headers=h, json=no_acct)
        assert r.json()["code"] == "needs_owner"
    finally:
        hub.bao = None
