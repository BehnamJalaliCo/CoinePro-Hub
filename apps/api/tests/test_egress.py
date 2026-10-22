"""The agents' internet on the api's side (prompt 07 §2, contract §18.7): the
data guard, the limits, the service accounts and the egress log."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from hq_api.domain import egress as G
from hq_api.hub import Hub
from hq_common.openbao import SecretNotFound

from .conftest import agent_headers, body_bytes, idem, step_up

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
    # Encoded, it is the same data (7.1 §1.6).
    code = co["code"]
    for text in (
        "ali%40example.com",
        f"{code}%2DTECH%2DMGR",
        "W%2D000123",
        "W%252D000123",  # twice
        quote("تماس ۰۹۱۲۳۴۵۶۷۸۹"),
        f"{code.lower()}-tech-mgr",  # a known code, any case
        f"{code}\uff0dTECH\uff0dMGR",  # full-width hyphens
        "W\u2011000123",  # a non-breaking hyphen
        base64.b64encode(b"ali.rezaei@example.com").decode(),
        "q=" + b"status of W-000123".hex(),
    ):
        r = await _reserve(client, h, url=f"https://example.com/search?q={text}")
        assert r.status_code == 403 and r.json()["code"] == "internal_data", text
    for text in (f"{code.lower()}-rates", "fx-rates 2026", "ZmFzdCBjYXJz"):  # not internal
        assert (await _reserve(client, h, strings=[text])).status_code == 200, text
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
        # 7.1 §2.22: when it could go: a run's own cap never comes back in the run.
        assert r.headers["Retry-After"] == str(G.RUN_RETRY_AFTER_S)
    finally:
        hub.settings = real
    hub.settings = replace(real, egress_day_bytes=3000)
    try:
        r = await _reserve(client, h, strings=["x y"])
        assert r.status_code == 429
        assert 1 <= int(r.headers["Retry-After"]) <= 86_400  # the owner's next day
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
    try:
        r = await client.get(
            "/internal/v1/egress/recent",
            headers=await agent_headers("HQ-ADV"),
            params={"company": co["code"]},
        )
        assert r.status_code == 200 and len(r.json()["items"]) >= 5
    finally:  # the advisor's test run must not stay running for the next tests
        await su.execute(
            """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
               WHERE e.id = r.employee_id AND e.code = 'HQ-ADV' AND r.state = 'running'
                 AND r.reason = 'test'"""
        )


async def put_account(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    body: dict[str, Any],
    key: dict[str, str] | None = None,
) -> httpx.Response:
    """POST /tools/accounts sealed: 🔏 `account.put` on the body's SHA-256 (7.1 §2.14)."""
    import hashlib

    content = body_bytes(body)
    seal = await step_up(
        hub, owner_session["session_id"], "account.put", hashlib.sha256(content).hexdigest()
    )
    return await client.post(
        "/api/v1/tools/accounts",
        content=content,
        headers={**owner_session["headers"], **seal, **(key or idem()),
                 "Content-Type": "application/json"},
    )  # fmt: skip


async def test_an_account_change_is_sealed_and_idempotent(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any]
) -> None:
    """7.1 §2.13-§2.14: a new site, allow rule or port widens what a stored
    secret can do, so POST /tools/accounts needs the owner's seal on the exact
    body; the Idempotency-Key is claimed before the seal is spent, so the
    same key and body answer the first 201 again."""
    body = {"key": "seal-test", "site": "api.seal.example", "title_fa": "حساب"}
    h = owner_session["headers"]
    r = await client.post("/api/v1/tools/accounts", headers={**h, **idem()}, json=body)
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    other = await step_up(hub, owner_session["session_id"], "account.put", "0" * 64)
    r = await client.post("/api/v1/tools/accounts", headers={**h, **other, **idem()}, json=body)
    assert (r.status_code, r.json()["code"]) == (403, "step_up_invalid")
    same = idem()
    first = await put_account(client, hub, owner_session, body, same)
    assert first.status_code == 201, first.text
    content = body_bytes(body)
    again = await client.post(
        "/api/v1/tools/accounts",
        content=content,
        headers={**h, **same, "Content-Type": "application/json"},  # no new seal: a replay
    )
    assert again.status_code == 201 and again.headers.get("Idempotent-Replay") == "true"
    assert again.json() == first.json()
    wider = {**body, "policy": {"ports": [8443]}}
    r = await client.post("/api/v1/tools/accounts", headers={**h, **idem()}, json=wider)
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    assert (await put_account(client, hub, owner_session, wider)).status_code == 201


async def test_service_accounts(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co, other = await new_company(), await new_company()
    body = {
        "key": f"crm-{co['code'].lower()}",
        "site": "api.crm.example",
        "title_fa": "حساب CRM",
        "companies": [co["code"]],
        "policy": {
            "inject": {"kind": "header", "name": "X-API-Key"},
            "allow": [
                {"methods": ["POST"], "path_prefix": "/v1/drafts"},
                {"methods": ["POST"], "path_prefix": "/api/search"},
            ],
        },
    }
    r = await put_account(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    acct = r.json()
    assert acct["has_secret"] is False and acct["companies"] == [co["code"]]
    assert "secret" not in json.dumps(acct).lower().replace("has_secret", "")
    bad = {**body, "key": "crm-bad", "companies": ["NOPE9"]}
    assert (await put_account(client, hub, owner_session, bad)).status_code == 422
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    key = body["key"]
    r = await _reserve(client, h, tool="web.browse", account=key, **{"class": "A2"})
    assert r.status_code == 409 and r.json()["code"] == "account_not_configured"
    hub.bao = FakeBao({key: SECRET})
    try:
        r = await _reserve(client, h, tool="web.browse", account=key, **{"class": "A2"})
        assert r.status_code == 200 and r.json()["account"]["secret"] == SECRET
        assert r.json()["account"]["inject"] == {"kind": "header", "name": "X-API-Key"}
        # The browser gets the allow rules: it refuses any other call (7.1 §1.4).
        assert r.json()["account"]["allow"][1] == {
            "methods": ["POST"],
            "path_prefix": "/api/search",
        }
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
        for url in ("https://api.crm.example/v1/send", "https://evil.example/v1/drafts",
                    # Dot segments: httpx would send /pay (7.1 §1.4).
                    "https://api.crm.example/api/search/../../pay",
                    "https://api.crm.example/api/search/%2e%2e/%2e%2e/pay",
                    "https://api.crm.example/api/search/%252e%252e/pay",
                    "https://api.crm.example/api/search//x", "https://api.crm.example/api/search/./x"):  # fmt: skip
            r = await client.post(
                "/internal/v1/egress/reserve", headers=h, json={**post, "url": url}
            )
            assert r.status_code == 403 and r.json()["code"] == "needs_owner", url
        no_acct = {**post, "account": None, "url": "https://api.crm.example/v1/drafts/1"}
        r = await client.post("/internal/v1/egress/reserve", headers=h, json=no_acct)
        assert r.json()["code"] == "needs_owner"
    finally:
        hub.bao = None


def test_the_data_guard_decodes() -> None:
    codes, known = {"FX", "HQ"}, frozenset({"FX-TECH-MGR", "HQ-ADV"})
    for text in ("ali%40example.com", "FX%2DTECH%2DMGR", "W%2D000123", "fx-tech-mgr", "Hq-Adv",
                 "FX\uff0dTECH\uff0dMGR", "FX\u200b-TECH-MGR", quote("۰۹۱۲۳۴۵۶۷۸۹"),
                 quote("٠٩١٢٣٤٥٦٧٨٩"), "ali+rezaei%40example.com",
                 base64.urlsafe_b64encode(b"FX-TECH-MGR is here").decode(),
                 b"call 09123456789 now".hex()):  # fmt: skip
        assert G.internal_data([text], codes, known), text
    for text in ("fx-rates", "hq-office hours", "COVID-19", "a%20b", "deadbeefdeadbeefdeadbeef"):
        assert G.internal_data([text], codes, known) is None, text
    assert G.clean_path("/api/search/x") == "/api/search/x"
    for bad in ("/api/search/../../pay", "/a/./b", "/a//b", "/a/%2e%2e/b", "/a%2fb", "/a\\b"):
        assert G.clean_path(bad) is None, bad


async def test_a_call_counts_before_its_answer(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    """7.1 §1.3: reserve writes the call's row before the request leaves; the
    call's entries settle it, so a lost answer counts and a logged one once."""
    co = await new_company()
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await _reserve(client, h, tool="web.read", url="https://slow.example/x")
    assert r.status_code == 200, r.text
    res = r.json()["reservation"]
    row = await su.fetchrow("SELECT * FROM egress.log WHERE id = $1", UUID(res))
    assert row["call_id"] == row["id"] and row["host"] == "slow.example"
    assert row["status"] is None and row["blocked_reason"] is None and row["run_id"] is not None

    async def requests() -> int:
        day = (await client.get("/api/v1/egress/summary", headers=owner)).json()
        return next(d["requests"] for d in day if d["company"] == co["code"])

    async def hosts() -> list[str]:
        page = (await client.get("/api/v1/egress", headers=owner,
                                 params={"company": co["code"]})).json()  # fmt: skip
        return sorted(i["host"] for i in page["items"])

    assert await requests() == 1 and await hosts() == ["slow.example"]  # no answer yet: it counts
    real = hub.settings
    hub.settings = replace(real, egress_run_requests=1)
    try:
        assert (await _reserve(client, h, strings=["more"])).status_code == 429
    finally:
        hub.settings = real
    # Its entries arrive: they settle it (counted once, listed as themselves).
    log = {"tool": "web.read", "class": "A0", "reservation": res, "entries": [ENTRY]}
    assert (await client.post("/internal/v1/egress/log", headers=h, json=log)).status_code == 204
    assert await requests() == 2  # the entry and the 429's refusal
    assert await hosts() == ["-", "example.com"]
    # A summed row counts its requests; a reservation settles only once.
    summed = {**ENTRY, "host": "(several)", "method": "MULTI", "requests": 40}
    r = await client.post("/internal/v1/egress/log", headers=h,
                          json={**log, "entries": [summed]})  # fmt: skip
    assert r.status_code == 204
    assert await requests() == 42
    calls = await su.fetch(
        "SELECT call_id FROM egress.log WHERE company_id = $1 AND call_id IS NOT NULL", co["id"]
    )
    assert len(calls) == 2  # the reservation and its one entry
    bad = {**ENTRY, "method": "VERYLONGMETHOD"}
    r = await client.post("/internal/v1/egress/log", headers=h, json={**log, "entries": [bad]})
    assert r.status_code == 422  # the gateway and egress shape rows before they get here


async def test_every_refusal_is_audited_and_no_run_keeps_its_caps(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """7.1 §3: a refused reserve writes its egress row AND an audit row (an
    account refusal too); an empty run_id never switches the per-run caps off."""
    co = await new_company()
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    assert (await _reserve(client, h, strings=["status of W-000123"])).status_code == 403
    r = await _reserve(client, h, tool="web.browse", account="no-such-account", **{"class": "A2"})
    assert r.status_code == 404
    real = hub.settings
    hub.settings = replace(real, egress_run_requests=1)
    try:
        assert (await _reserve(client, h, strings=["x"])).status_code == 429
    finally:
        hub.settings = real
    rows = await su.fetch(
        "SELECT blocked_reason FROM egress.log WHERE company_id = $1 ORDER BY at", co["id"]
    )
    assert [r["blocked_reason"] for r in rows] == ["internal_data", "not_found", "egress_limit"]
    audits = await su.fetch(
        """SELECT action_class, target_kind, summary FROM audit.entries
           WHERE company_id = $1 AND action = 'egress.refused' ORDER BY seq""",
        co["id"],
    )
    assert [a["summary"].rsplit(": ", 1)[1] for a in audits] == [
        "internal_data",
        "not_found",
        "egress_limit",
    ]
    assert audits[1]["action_class"] == "A2" and audits[0]["target_kind"] == "host"
    # No run: the actor's run-less rows of the day are one run (never zero).
    for _ in range(3):
        await su.execute(
            """INSERT INTO egress.log (company_id, actor, run_id, tool, kind, class, method, host)
               VALUES ($1, 'NO-RUN-ACTOR', NULL, 'web.read', 'request', 'A0', 'GET', 'x.example')""",
            co["id"],
        )
    async with hub.db.tx([co["id"]]) as tx:
        none = await tx.one(G.USAGE_SQL, run=None, co=co["id"], actor="NO-RUN-ACTOR")
        other = await tx.one(G.USAGE_SQL, run=None, co=co["id"], actor="SOMEONE-ELSE")
    assert none["run_requests"] == 3 and other["run_requests"] == 0
    assert 0 < none["day_reset_s"] <= 86_400
    assert G.limits_left(replace(real, egress_run_requests=3), none)["requests"] <= 0


async def test_a_signed_in_profile_account_needs_no_secret_and_browses_only(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    """Prompt 12 §9.1 (contract §21.13): a `profile` account (the substitute
    players' signed-in browser profiles) has no secret in OpenBao; it serves
    web.browse only (in the profile browser, on its site's own hosts)."""
    co = await new_company()
    body = {"key": f"profile-{co['code'].lower()}", "site": "chat.example", "title_fa": "پروفایل",
            "policy": {"browse": {"kind": "profile"}}}  # fmt: skip
    r = await put_account(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    for bad in (
        {"browse": {"kind": "profile", "login_url": "https://chat.example/login"}},
        {"browse": {"kind": "profile"}, "ports": [8443]},
        {"browse": {"kind": "profile"}, "inject": {"kind": "signer", "signer": "lbank-v2"}},
    ):
        bad_body = {**body, "key": "profile-bad", "policy": bad}
        assert (await put_account(client, hub, owner_session, bad_body)).status_code == 422, bad
    h = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await _reserve(client, h, tool="web.browse", account=body["key"], **{"class": "A2"})
    assert r.status_code == 200, r.text
    acct = r.json()["account"]
    assert acct["secret"] is None and acct["browse"] == {"kind": "profile"}
    for tool in ("http.request", "web.read"):
        r = await _reserve(client, h, tool=tool, account=body["key"], url="https://chat.example/",
                           **{"class": "A2"})  # fmt: skip
        assert (r.status_code, r.json()["code"]) == (403, "policy_denied"), tool
