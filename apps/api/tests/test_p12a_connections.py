"""Prompt 12 §9 (contract §21.7, §21.14): adding a connection, sealed on its
body; its key by the write-only route or the owner's terminal; verified by
the router at no token cost (llm_router.verify, run here with a fake
provider); never a secret in a response, a log or an audit row."""

from __future__ import annotations

import hashlib
import json
import random
import sys
import uuid
from dataclasses import replace
from typing import Any

import httpx

from hq_api.hub import Hub

from .conftest import _su_pool, body_bytes, step_up

SECRET = "sk-test-p12a-" + "z" * 32


class FakeBao:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    async def write_kv(self, path: str, data: dict[str, Any]) -> None:
        self.data[path] = dict(data)

    async def read_kv(self, path: str) -> dict[str, Any]:
        if path not in self.data:
            raise KeyError(path)
        return self.data[path]


def _body(key: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "key": key,
        "provider": "openai",
        "kind": "api_key",
        "display_name": "OpenAI (آزمایشی)",
        "models": ["gpt-x-1", "gpt-x-mini"],
        "default_model": "gpt-x-1",
        "pricing": {"gpt-x-1": {"input_per_mtok": "2.00", "output_per_mtok": "8.00"}},
        "limits": {"rpm": 60, "daily_usd": "5"},
    }
    body.update(over)
    return body


async def _post(client: httpx.AsyncClient, hub: Hub, s: dict[str, Any], body: dict[str, Any],
                key: str | None = None, seal: bool = True) -> httpx.Response:  # fmt: skip
    raw = body_bytes(body)
    headers = {
        **s["headers"],
        "Content-Type": "application/json",
        "Idempotency-Key": key or str(uuid.uuid4()),
    }
    if seal:
        headers.update(
            await step_up(
                hub, s["session_id"], "connection.create", hashlib.sha256(raw).hexdigest()
            )
        )
    return await client.post("/api/v1/connections", headers=headers, content=raw)


async def test_a_new_connection_is_sealed_waits_for_its_key_and_is_verified_at_no_cost(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    s = owner_session
    key = f"p12a-{random.randint(10**5, 10**6)}"
    body = _body(key)
    assert (await _post(client, hub, s, body, seal=False)).status_code == 403
    private = await _post(
        client, hub, s, _body(key, provider="openai_compatible", base_url="https://10.10.1.2/v1")
    )
    assert private.status_code == 422, private.text
    plain = await _post(
        client,
        hub,
        s,
        _body(key, provider="openai_compatible", base_url="http://llm.example.org/v1"),
    )
    assert plain.status_code == 422
    base_wrong = await _post(client, hub, s, _body(key, base_url="https://llm.example.org/v1"))
    assert base_wrong.status_code == 422
    sub = await _post(client, hub, s, _body(key, kind="subscription"))
    assert sub.status_code == 409 and sub.json()["code"] == "not_ready"
    idem_key = str(uuid.uuid4())
    r = await _post(client, hub, s, body, key=idem_key)
    assert r.status_code == 201, r.text
    conn = r.json()
    assert (
        conn["status"] == "pending_secret"
        and conn["kind"] == "api"
        and conn["has_secret_ref"] is True
    )
    again = await _post(client, hub, s, body, key=idem_key)
    assert again.status_code == 201 and again.json()["id"] == conn["id"]
    assert await su.fetchval("SELECT count(*) FROM llm.connections WHERE key = $1", key) == 1
    dup = await _post(client, hub, s, body)
    assert dup.status_code == 409 and dup.json()["code"] == "version_conflict"
    # The key: the write-only route moves it to verifying (the owner's default route).
    bao = FakeBao()
    saved_bao, hub.bao = hub.bao, bao
    try:
        sec = await client.post(
            f"/api/v1/connections/{conn['id']}/secret",
            headers={
                **s["headers"],
                **await step_up(hub, s["session_id"], "connection.secret", conn["id"]),
            },
            json={"secret": SECRET},
        )
        assert sec.status_code == 200 and SECRET not in sec.text, sec.text
        assert bao.data[f"llm-connections/{key}"] == {"api_key": SECRET}
        assert (
            await su.fetchval("SELECT status FROM llm.connections WHERE key = $1", key)
            == "verifying"
        )
        # It is not routable or assignable by hand before its verification.
        listed = {
            c["key"]: c
            for c in (await client.get("/api/v1/connections", headers=s["headers"])).json()
        }
        assert listed[key]["status"] == "verifying" and SECRET not in json.dumps(listed)
        # llm-router's verification (its own module, a fake provider): ready.
        sys.path.insert(0, "/w/llm-router/src")
        from llm_router import verify

        class Db:
            pool: Any = None

        Db.pool = await _su_pool()

        def provider(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/models")
            return httpx.Response(200, json={"data": [{"id": "gpt-x-1"}]})

        async def resolve(host: str, port: int) -> list[str]:
            return ["93.184.216.34"]

        async def unlocked(_: str) -> None:
            return None

        async def locked(_: str) -> str:
            return "holding"

        http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
        assert (await verify.scan(Db, bao.read_kv, locked, client=http, resolve=resolve))[
            "checked"
        ] == 0
        assert (
            await su.fetchval("SELECT status FROM llm.connections WHERE key = $1", key)
            == "verifying"
        )
        out = await verify.scan(Db, bao.read_kv, unlocked, client=http, resolve=resolve)
        assert out["ready"] >= 1
        row = await su.fetchrow(
            "SELECT status, status_reason, verified_at FROM llm.connections WHERE key = $1", key
        )
        assert (
            row["status"] == "ready"
            and row["verified_at"] is not None
            and SECRET not in row["status_reason"]
        )
        # No response, log or audit row carries the key.
        audit = await su.fetch("SELECT summary FROM audit.entries WHERE target_ref = $1", key)
        assert {a["summary"] for a in audit} >= {"key replaced"} and all(
            SECRET not in (a["summary"] or "") for a in audit
        )
        inter = await su.fetch("SELECT data FROM owner.interactions WHERE target_ref = $1", key)
        assert all(SECRET not in json.dumps(i["data"]) for i in inter)
    finally:
        hub.bao = saved_bao
        await su.execute("UPDATE llm.connections SET status = 'disabled' WHERE key = $1", key)


async def test_terminal_only_keeps_a_new_connections_key_off_the_api(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    s = owner_session
    key = f"p12a-t-{random.randint(10**5, 10**6)}"
    conn = (await _post(client, hub, s, _body(key))).json()
    saved, saved_bao = hub.settings, hub.bao
    hub.settings, hub.bao = replace(saved, connection_secret_route="terminal"), FakeBao()
    try:
        r = await client.post(
            f"/api/v1/connections/{conn['id']}/secret",
            headers={
                **s["headers"],
                **await step_up(hub, s["session_id"], "connection.secret", conn["id"]),
            },
            json={"secret": SECRET},
        )
        assert r.status_code == 409 and r.json()["code"] == "validation_failed"
        assert "make connection-secret" in r.text and SECRET not in r.text
    finally:
        hub.settings, hub.bao = saved, saved_bao
        await su.execute("UPDATE llm.connections SET status = 'disabled' WHERE key = $1", key)


async def test_a_substitute_subscription_is_never_assigned_or_enabled(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    s = owner_session
    body = {
        "assignments": [
            {"scope_type": "task_class", "scope_ref": "summarize", "connection": "chatgpt-plus"}
        ]
    }
    raw = body_bytes(body)
    r = await client.put(
        "/api/v1/assignments",
        headers={**s["headers"], "Content-Type": "application/json",
                 **await step_up(hub, s["session_id"], "assignments.update", hashlib.sha256(raw).hexdigest())},
        content=raw,
    )  # fmt: skip
    assert r.status_code == 422 and "substitute" in r.text, r.text
    c = await su.fetchrow("SELECT id, version FROM llm.connections WHERE key = 'chatgpt-plus'")
    p = await client.patch(
        f"/api/v1/connections/{c['id']}",
        headers={**s["headers"], "If-Match": str(c["version"]),
                 **await step_up(hub, s["session_id"], "connection.update", str(c["id"]))},
        json={"status": "enabled"},
    )  # fmt: skip
    assert p.status_code == 409 and p.json()["code"] == "not_ready"
