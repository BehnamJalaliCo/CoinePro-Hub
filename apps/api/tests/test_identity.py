"""Passkeys, sessions and step-up (contract §2, prompt 04 §4), with a software
authenticator: the full cycle and every rejection path."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from hq_api import enroll
from hq_api.app import create_app
from hq_api.errors import install as install_errors
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.security import agent_tokens, deps
from hq_common.tokens import digest

from .conftest import ORIGIN, agent_headers, service_headers, settings
from .soft_authenticator import SoftAuthenticator, unb64url

BASE = "/api/v1/auth"
WEB = {"X-HQ-Client": "web", "Origin": ORIGIN}


# ----------------------------------------------------------------- helpers --
async def enrolment_token(hub: Hub) -> str:
    token, _ = await enroll.issue(hub.db, 900)
    return token


async def register(
    client: httpx.AsyncClient, auth: SoftAuthenticator, token: str, **knobs: Any
) -> httpx.Response:
    opts = await client.post(f"{BASE}/passkey/register/options", json={"enrolment_token": token})
    assert opts.status_code == 200, opts.text
    cred = auth.register(opts.json(), **knobs)
    return await client.post(
        f"{BASE}/passkey/register/verify", json={"credential": cred, "device_name": "test phone"}
    )


async def enrolled(hub: Hub, client: httpx.AsyncClient) -> SoftAuthenticator:
    auth = SoftAuthenticator()
    r = await register(client, auth, await enrolment_token(hub))
    assert r.status_code == 201, r.text
    return auth


async def login(
    client: httpx.AsyncClient,
    auth: SoftAuthenticator,
    headers: dict[str, str] | None = None,
    **knobs: Any,
) -> httpx.Response:
    opts = await client.post(f"{BASE}/passkey/login/options", headers=headers or {})
    assert opts.status_code == 200, opts.text
    cred = auth.sign(opts.json(), **knobs)
    return await client.post(
        f"{BASE}/passkey/login/verify", json={"credential": cred}, headers=headers or {}
    )


async def bearer(client: httpx.AsyncClient, auth: SoftAuthenticator) -> dict[str, str]:
    r = await login(client, auth)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session']['token']}"}


async def session_id(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    r = await client.get(f"{BASE}/session", headers=headers)
    assert r.status_code == 200, r.text
    return str(r.json()["device"]["id"])


async def step_up(
    client: httpx.AsyncClient,
    auth: SoftAuthenticator,
    headers: dict[str, str],
    action: str,
    target: str,
) -> str:
    opts = await client.post(
        f"{BASE}/step-up/options", json={"action": action, "target": target}, headers=headers
    )
    assert opts.status_code == 200, opts.text
    r = await client.post(
        f"{BASE}/step-up/verify", json={"credential": auth.sign(opts.json())}, headers=headers
    )
    assert r.status_code == 200, r.text
    return str(r.json()["step_up_token"])


def code(r: httpx.Response) -> str:
    return str(r.json().get("code"))


# ------------------------------------------------------------------- cycle --
async def test_full_cycle_enrol_login_step_up_revoke(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    auth = await enrolled(hub, client)
    a = await bearer(client, auth)
    b = await bearer(client, auth)
    sid_a, sid_b = await session_id(client, a), await session_id(client, b)
    me = (await client.get(f"{BASE}/session", headers=a)).json()
    assert me["principal"] == {"kind": "owner", "code": "owner"} and me["device"]["current"] is True

    devices = (await client.get(f"{BASE}/devices", headers=a)).json()["items"]
    assert {d["id"] for d in devices} >= {sid_a, sid_b}
    assert any(d["kind"] == "passkey" and d["name"] == "test phone" for d in devices)

    token = await step_up(client, auth, a, "device.revoke", sid_b)
    r = await client.post(f"{BASE}/devices/{sid_b}/revoke", headers={**a, "X-Step-Up": token})
    assert r.status_code == 204, r.text
    assert (await client.get(f"{BASE}/session", headers=b)).status_code == 401
    assert (await client.get(f"{BASE}/session", headers=a)).status_code == 200

    actions = {
        r["action"]
        for r in await su.fetch(
            "SELECT action FROM audit.entries WHERE target_ref = ANY($1::text[])", [sid_a, sid_b]
        )
    }
    assert {"auth.login", "auth.device_revoke"} <= actions
    revoke = await su.fetchrow(
        "SELECT step_up, action_class FROM audit.entries WHERE action = 'auth.device_revoke' AND target_ref = $1",
        sid_b,
    )
    assert revoke["step_up"] is True and revoke["action_class"] == "A4"
    rows = await su.fetch(
        "SELECT action FROM owner.interactions WHERE kind = 'security' AND target_ref = $1", sid_b
    )
    assert sorted(r["action"] for r in rows) == ["auth.device_revoke", "auth.login"]


async def test_second_passkey_needs_session_and_step_up(
    hub: Hub, client: httpx.AsyncClient
) -> None:
    auth = await enrolled(hub, client)
    h = await bearer(client, auth)
    r = await client.post(f"{BASE}/passkey/register/options", json={}, headers=h)
    assert r.status_code == 403 and code(r) == "step_up_required"
    token = await step_up(client, auth, h, "passkey.register", "self")
    opts = await client.post(
        f"{BASE}/passkey/register/options", json={}, headers={**h, "X-Step-Up": token}
    )
    assert opts.status_code == 200
    excluded = {e["id"] for e in opts.json()["excludeCredentials"]}
    assert auth.credential_id.hex() in {unb64url(e).hex() for e in excluded}
    laptop = SoftAuthenticator()
    cred = laptop.register(opts.json())
    # the verify belongs to the session that asked: another caller cannot finish it
    r = await client.post(
        f"{BASE}/passkey/register/verify", json={"credential": cred, "device_name": "laptop"}
    )
    assert r.status_code == 401
    r = await client.post(
        f"{BASE}/passkey/register/verify",
        json={"credential": cred, "device_name": "laptop"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert (await login(client, laptop)).status_code == 200
    # without anything at all, registration is closed
    r = await client.post(f"{BASE}/passkey/register/options", json={})
    assert r.status_code == 401


# --------------------------------------------------------------- rejections --
async def test_stale_challenge_is_rejected(hub: Hub, client: httpx.AsyncClient, su: Any) -> None:
    auth = await enrolled(hub, client)
    opts = (await client.post(f"{BASE}/passkey/login/options")).json()
    await su.execute(
        "UPDATE auth.challenges SET expires_at = now() - interval '1 second' WHERE challenge = $1",
        unb64url(opts["challenge"]),
    )
    r = await client.post(f"{BASE}/passkey/login/verify", json={"credential": auth.sign(opts)})
    assert r.status_code == 401 and code(r) == "unauthenticated"


async def test_wrong_origin_rp_and_missing_uv_are_rejected(
    hub: Hub, client: httpx.AsyncClient
) -> None:
    auth = await enrolled(hub, client)
    for knobs in ({"origin": "https://evil.test"}, {"uv": False}, {"rp_id": "evil.test"}):
        r = await login(client, auth, **knobs)
        assert r.status_code == 401, knobs
    for knobs in ({"origin": "https://evil.test"}, {"uv": False}):
        r = await register(client, SoftAuthenticator(), await enrolment_token(hub), **knobs)
        assert r.status_code == 422 and code(r) == "validation_failed", knobs
    assert (await login(client, auth)).status_code == 200


async def test_replay_unknown_credential_and_cloned_counter(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    auth = await enrolled(hub, client)
    opts = (await client.post(f"{BASE}/passkey/login/options")).json()
    cred = auth.sign(opts)
    assert (
        await client.post(f"{BASE}/passkey/login/verify", json={"credential": cred})
    ).status_code == 200
    assert (
        await client.post(f"{BASE}/passkey/login/verify", json={"credential": cred})
    ).status_code == 401
    assert (await login(client, SoftAuthenticator())).status_code == 401
    # a clone that did not advance its counter: refused, flagged, audited, 🔴
    counts = """SELECT (SELECT count(*) FROM auth.passkeys WHERE flagged_at IS NOT NULL),
                       (SELECT count(*) FROM audit.entries WHERE action = 'auth.passkey_clone_suspected'),
                       (SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_kind = 'device')"""
    before = tuple(await su.fetchrow(counts))
    r = await login(client, auth, bump=False)
    assert r.status_code == 401
    assert tuple(await su.fetchrow(counts)) == tuple(n + 1 for n in before)
    garbage = {"credential": {"id": "x", "rawId": "x", "type": "public-key", "response": {}}}
    assert (await client.post(f"{BASE}/passkey/login/verify", json=garbage)).status_code == 401


async def test_step_up_is_bound_single_use_and_short_lived(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    auth = await enrolled(hub, client)
    a, b = await bearer(client, auth), await bearer(client, auth)
    sid_b = await session_id(client, b)
    path = f"{BASE}/devices/{sid_b}/revoke"

    r = await client.post(path, headers=a)
    assert r.status_code == 403 and code(r) == "step_up_required"
    wrong_target = await step_up(client, auth, a, "device.revoke", str(uuid.uuid4()))
    assert (
        code(await client.post(path, headers={**a, "X-Step-Up": wrong_target})) == "step_up_invalid"
    )
    wrong_action = await step_up(client, auth, a, "company.archive", sid_b)
    assert (
        code(await client.post(path, headers={**a, "X-Step-Up": wrong_action})) == "step_up_invalid"
    )
    other_session = await step_up(client, auth, b, "device.revoke", sid_b)
    assert (
        code(await client.post(path, headers={**a, "X-Step-Up": other_session}))
        == "step_up_invalid"
    )

    expired = await step_up(client, auth, a, "device.revoke", sid_b)
    await su.execute(
        "UPDATE auth.step_ups SET expires_at = now() - interval '1 second' WHERE token_sha256 = $1",
        digest(expired),
    )
    assert code(await client.post(path, headers={**a, "X-Step-Up": expired})) == "step_up_invalid"

    good = await step_up(client, auth, a, "device.revoke", sid_b)
    assert (await client.post(path, headers={**a, "X-Step-Up": good})).status_code == 204
    assert code(await client.post(path, headers={**a, "X-Step-Up": good})) == "step_up_invalid"

    # the step-up assertion itself cannot be replayed
    opts = (
        await client.post(
            f"{BASE}/step-up/options", json={"action": "x.y", "target": "t"}, headers=a
        )
    ).json()
    cred = auth.sign(opts)
    assert (
        await client.post(f"{BASE}/step-up/verify", json={"credential": cred}, headers=a)
    ).status_code == 200
    r = await client.post(f"{BASE}/step-up/verify", json={"credential": cred}, headers=a)
    assert r.status_code == 403 and code(r) == "step_up_invalid"
    bad = await client.post(
        f"{BASE}/step-up/verify", json={"credential": {**cred, "response": {}}}, headers=a
    )
    assert code(bad) == "step_up_invalid"
    opts = (
        await client.post(
            f"{BASE}/step-up/options", json={"action": "x.y", "target": "t"}, headers=a
        )
    ).json()
    r = await client.post(
        f"{BASE}/step-up/verify", json={"credential": auth.sign(opts, uv=False)}, headers=a
    )
    assert code(r) == "step_up_invalid"


async def test_expired_session_and_revoked_passkey(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    auth = await enrolled(hub, client)
    h = await bearer(client, auth)
    sid = await session_id(client, h)
    await su.execute(
        "UPDATE auth.sessions SET expires_at = now() - interval '1 second' WHERE id = $1",
        uuid.UUID(sid),
    )
    assert (await client.get(f"{BASE}/session", headers=h)).status_code == 401

    h = await bearer(client, auth)
    pk = await su.fetchval(
        "SELECT id FROM auth.passkeys WHERE credential_id = $1", auth.credential_id
    )
    token = await step_up(client, auth, h, "device.revoke", str(pk))
    r = await client.post(f"{BASE}/devices/{pk}/revoke", headers={**h, "X-Step-Up": token})
    assert r.status_code == 204
    assert (
        await client.get(f"{BASE}/session", headers=h)
    ).status_code == 401  # its sessions die with it
    assert (await login(client, auth)).status_code == 401
    assert (
        await client.post(
            f"{BASE}/devices/{uuid.uuid4()}/revoke", headers=await bearer_any(hub, client)
        )
    ).status_code == 403  # no step-up: refused before looking


async def bearer_any(hub: Hub, client: httpx.AsyncClient) -> dict[str, str]:
    return await bearer(client, await enrolled(hub, client))


async def test_revoking_an_unknown_device_is_404(hub: Hub, client: httpx.AsyncClient) -> None:
    auth = await enrolled(hub, client)
    h = await bearer(client, auth)
    missing = str(uuid.uuid4())
    token = await step_up(client, auth, h, "device.revoke", missing)
    r = await client.post(f"{BASE}/devices/{missing}/revoke", headers={**h, "X-Step-Up": token})
    assert r.status_code == 404


async def test_enrolment_token_is_single_use_and_expires(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    token = await enrolment_token(hub)
    assert (await register(client, SoftAuthenticator(), token)).status_code == 201
    r = await client.post(f"{BASE}/passkey/register/options", json={"enrolment_token": token})
    assert r.status_code == 401
    stale = await enrolment_token(hub)
    await su.execute(
        "UPDATE auth.enrolment_tokens SET expires_at = now() - interval '1 second' WHERE token_sha256 = $1",
        digest(stale),
    )
    r = await client.post(f"{BASE}/passkey/register/options", json={"enrolment_token": stale})
    assert r.status_code == 401
    # two parallel ceremonies on one token: only the first to finish registers
    twin = await enrolment_token(hub)
    o1 = (
        await client.post(f"{BASE}/passkey/register/options", json={"enrolment_token": twin})
    ).json()
    o2 = (
        await client.post(f"{BASE}/passkey/register/options", json={"enrolment_token": twin})
    ).json()
    first = SoftAuthenticator().register(o1)
    second = SoftAuthenticator().register(o2)
    ok = await client.post(
        f"{BASE}/passkey/register/verify", json={"credential": first, "device_name": "a"}
    )
    late = await client.post(
        f"{BASE}/passkey/register/verify", json={"credential": second, "device_name": "b"}
    )
    assert (ok.status_code, late.status_code) == (201, 401)


# ---------------------------------------------------------------- web/CSRF --
async def test_web_login_uses_a_strict_cookie_and_csrf(hub: Hub, client: httpx.AsyncClient) -> None:
    auth = await enrolled(hub, client)
    evil = {"X-HQ-Client": "web", "Origin": "https://evil.test"}
    bad = await client.post(f"{BASE}/passkey/login/options", headers=evil)
    assert bad.status_code == 403 and code(bad) == "csrf_rejected"
    opts = (await client.post(f"{BASE}/passkey/login/options", headers=WEB)).json()
    bad = await client.post(
        f"{BASE}/passkey/login/verify", json={"credential": auth.sign(opts)}, headers=evil
    )
    assert bad.status_code == 403 and code(bad) == "csrf_rejected"
    r = await login(client, auth, headers=WEB)
    assert r.status_code == 200 and r.json()["session"]["token"] is None
    cookie = r.headers["set-cookie"].lower()
    for part in ("hq_session=", "httponly", "secure", "samesite=strict", "path=/api"):
        assert part in cookie, part
    assert (await client.get(f"{BASE}/session")).status_code == 200  # cookie only
    r = await client.post(f"{BASE}/logout")
    assert r.status_code == 403 and code(r) == "csrf_rejected"
    r = await client.post(
        f"{BASE}/logout", headers={"X-HQ-Client": "web", "Origin": "https://evil.test"}
    )
    assert r.status_code == 403 and code(r) == "csrf_rejected"
    r = await client.post(f"{BASE}/logout", headers=WEB)
    assert r.status_code == 204
    client.cookies.clear()
    assert (await client.get(f"{BASE}/session")).status_code == 401


async def test_android_logout_needs_no_csrf_headers(hub: Hub, client: httpx.AsyncClient) -> None:
    h = await bearer(client, await enrolled(hub, client))
    assert (await client.post(f"{BASE}/logout", headers=h)).status_code == 204
    assert (await client.get(f"{BASE}/session", headers=h)).status_code == 401


# --------------------------------------------------------------- no domain --
async def test_login_is_off_without_a_domain(hub: Hub, owner: dict[str, str]) -> None:
    off = Hub(
        settings=settings(public_origin="", rp_id=""),
        db=hub.db,
        companies=hub.companies,
        secrets=hub.secrets,
        policy=hub.policy,
        storage=hub.storage,
        bus=hub.bus,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(off)), base_url=ORIGIN
    ) as c:
        for path, body, headers in (
            ("/passkey/login/options", None, {}),
            ("/passkey/login/verify", {}, {}),
            ("/passkey/register/options", {"enrolment_token": "x" * 20}, {}),
            ("/passkey/register/verify", {}, {}),
            ("/step-up/options", {"action": "a.b", "target": "t"}, owner),
            ("/step-up/verify", {}, owner),
        ):
            r = await c.post(f"{BASE}{path}", json=body, headers=headers)
            assert r.status_code == 503 and code(r) == "origin_not_configured", path
        assert (await c.get("/api/v1/health")).status_code == 200


def test_login_configured_needs_https_and_a_matching_rp() -> None:
    assert settings().login_configured
    assert not settings(public_origin="http://hq.test").login_configured
    assert not settings(rp_id="other.test").login_configured
    assert settings(public_origin="https://app.hq.test").login_configured


# ------------------------------------------------------------ open surface --
async def test_no_endpoint_works_without_authentication(
    app: Any, client: httpx.AsyncClient
) -> None:
    open_ok = {
        ("GET", "/api/v1/health"): {200},
        ("POST", "/api/v1/auth/passkey/login/options"): {200},
        ("POST", "/api/v1/auth/passkey/login/verify"): {422},
        ("POST", "/api/v1/auth/passkey/register/verify"): {422},
    }
    checked = 0
    # Every published operation (the OpenAPI document lists them all).
    for path, ops in app.openapi()["paths"].items():
        concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
        for method in ops:
            r = await client.request(method.upper(), concrete, json={})
            allowed = open_ok.get((method.upper(), path), {401})
            assert r.status_code in allowed, (method, path, r.status_code, r.text[:200])
            checked += 1
    assert checked >= 13


# ------------------------------------------------------------------ enroll --
class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_enroll_cli_refuses_without_tty_or_domain() -> None:
    err = io.StringIO()
    assert enroll.run(settings(), io.StringIO(), err) == 2
    assert "interactive terminal" in err.getvalue()
    err = io.StringIO()
    assert enroll.run(settings(public_origin=""), _Tty(), err) == 3
    assert "HQ_SITE_ADDRESS" in err.getvalue()


async def test_enroll_cli_prints_a_working_link_only_to_the_terminal(
    caplog: pytest.LogCaptureFixture, su: Any, hub: Hub, client: httpx.AsyncClient
) -> None:
    out = _Tty()
    with caplog.at_level(logging.INFO):
        # run() owns its event loop (asyncio.run): give it a thread of its own
        assert await asyncio.to_thread(enroll.run, settings(), out, io.StringIO()) == 0
    text = out.getvalue()
    assert f"{ORIGIN}/enroll#token=" in text
    token = text.split("#token=", 1)[1].split()[0]
    assert token not in caplog.text and "enrolment link issued" in caplog.text
    row = await su.fetchrow(
        "SELECT used_at, expires_at - created_at AS ttl FROM auth.enrolment_tokens WHERE token_sha256 = $1",
        digest(token),
    )
    assert row is not None and row["used_at"] is None
    assert abs(row["ttl"].total_seconds() - 900) < 5
    assert (await register(client, SoftAuthenticator(), token)).status_code == 201


# ------------------------------------------------- agent and service tokens --
def test_agent_tokens_are_signed_bound_and_short_lived() -> None:
    key = b"k" * 32
    t = agent_tokens.mint(key, "TY-CEO", "run-1", ttl_s=60, now=1_000_000)
    claims = agent_tokens.verify(key, t, now=1_000_030)
    assert (claims.employee, claims.run, claims.exp) == ("TY-CEO", "run-1", 1_000_060)
    capped = agent_tokens.verify(
        key, agent_tokens.mint(key, "X-Y", "r", ttl_s=99_999, now=0), now=1
    )
    assert capped.exp == agent_tokens.MAX_TTL_S
    head, payload, sig = t.split(".")
    for bad in (
        t + "x",  # signature changed
        f"{head}.{payload}x.{sig}",  # payload changed
        f"hqa0.{payload}.{sig}",  # wrong version
        "hqa1.only-two",
        f"{head}.!!!.{sig}",
    ):
        with pytest.raises(agent_tokens.InvalidToken):
            agent_tokens.verify(key, bad, now=1_000_030)
    with pytest.raises(agent_tokens.InvalidToken):
        agent_tokens.verify(key, t, now=1_000_061)  # expired
    with pytest.raises(agent_tokens.InvalidToken):
        agent_tokens.verify(b"other" * 8, t, now=1_000_030)
    with pytest.raises(agent_tokens.InvalidToken):
        agent_tokens.verify(b"", t)
    with pytest.raises(agent_tokens.InvalidToken):
        agent_tokens.mint(b"", "TY-CEO", "r")


async def test_internal_principals(hub: Hub, new_company: Any, su: Any) -> None:
    probe = FastAPI()
    probe.state.hub = hub
    install_errors(probe)

    @probe.get("/who")
    async def who(p: Principal = Depends(deps.internal)) -> dict[str, Any]:
        return {
            "kind": p.kind,
            "code": p.code,
            "role": p.role,
            "company": p.company,
            "department": p.department,
            "run": p.run_id,
        }

    co = await new_company()
    mgr = f"{co['code']}-GROWTH-MGR"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=probe), base_url=ORIGIN) as c:
        r = await c.get("/who", headers=agent_headers(mgr))
        assert r.status_code == 200, r.text
        assert r.json() | {"run": None} == {
            "kind": "agent",
            "code": mgr,
            "role": "manager",
            "company": co["code"],
            "department": "GROWTH",
            "run": None,
        }
        r = await c.get("/who", headers=service_headers())
        assert r.json()["kind"] == "service" and r.json()["code"] == "test-service"
        for headers in (
            {},
            {"Authorization": "Bearer nope"},
            {"Authorization": "Basic abc"},
            agent_headers("NOBODY-X"),
            {"Authorization": "Bearer hqa1.bad.token"},
        ):
            assert (await c.get("/who", headers=headers)).status_code == 401, headers
        await su.execute(
            "UPDATE core.employees SET status = 'dismissed', dismissed_at = now() WHERE code = $1",
            mgr,
        )
        assert (await c.get("/who", headers=agent_headers(mgr))).status_code == 401


async def test_auth_rate_limit_answers_429_with_retry_after(hub: Hub) -> None:
    tight = Hub(
        settings=settings(auth_rate_per_ip=2),
        db=hub.db,
        companies=hub.companies,
        secrets=hub.secrets,
        policy=hub.policy,
        storage=hub.storage,
        bus=hub.bus,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tight)), base_url=ORIGIN
    ) as c:
        codes = [(await c.post(f"{BASE}/passkey/login/options")).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        r = await c.post(f"{BASE}/passkey/login/options")
        assert code(r) == "rate_limited" and int(r.headers["retry-after"]) >= 1
