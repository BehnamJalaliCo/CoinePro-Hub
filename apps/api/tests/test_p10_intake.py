"""Prompt 10 §9 (contract §19.8): the three public webhooks under /intake/v1
and the owner's intake sources. A bad signature, a stale timestamp, a
repeated id or an address outside the list is refused and stores nothing but
one counted refusal; a good Telegram update becomes a masked support message."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from hq_api.hub import Hub
from hq_api.routes import intake as I

from .conftest import body_bytes, idem, step_up
from .p10_support import holding_switch

TG_IP = "149.154.167.220"  # inside Telegram's published 149.154.160.0/20
SECRET = "intake-test-secret-" + "a" * 24
TG_SECRET = "tg-webhook-secret-" + "b" * 24


class FakeBao:
    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data

    async def read_kv(self, path: str) -> dict[str, Any]:
        return dict(self.data.get(path, {}))


@pytest.fixture
async def bao(hub: Hub) -> AsyncIterator[FakeBao]:
    fake = FakeBao({})
    saved = hub.bao
    hub.bao = fake
    try:
        yield fake
    finally:
        hub.bao = saved


async def _source(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], body: dict[str, Any]
) -> httpx.Response:
    content = body_bytes(body)
    su_h = await step_up(
        hub, owner_session["session_id"], "intake.source", hashlib.sha256(content).hexdigest()
    )
    return await client.post(
        "/api/v1/intake/sources",
        content=content,
        headers={**owner_session["headers"], **su_h, **idem(), "Content-Type": "application/json"},
    )


def _signed(
    body: dict[str, Any], *, ts: int | None = None, secret: str = SECRET
) -> tuple[bytes, str, str]:
    raw = json.dumps(body).encode()
    stamp = str(ts if ts is not None else int(time.time()))
    sig = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, stamp, f"sha256={sig}"


async def _counts(su: Any, company_id: Any) -> tuple[int, int, int]:
    return (
        int(
            await su.fetchval(
                "SELECT count(*) FROM intake.events WHERE company_id = $1", company_id
            )
        ),
        int(
            await su.fetchval(
                "SELECT count(*) FROM support.messages WHERE company_id = $1", company_id
            )
        ),
        int(
            await su.fetchval(
                "SELECT count(*) FROM intake.rejections WHERE company_id = $1", company_id
            )
        ),
    )


async def test_sources_need_step_up_and_put_their_channel_in_shadow(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, bao: FakeBao,
) -> None:  # fmt: skip
    co = await new_company()
    body = {
        "company": co["code"],
        "kind": "telegram",
        "channel": "telegram_bot",
        "allowed_ips": [],
        "kinds": [],
    }
    r = await client.post(
        "/api/v1/intake/sources", headers={**owner_session["headers"], **idem()}, json=body
    )
    assert r.status_code == 403
    r = await _source(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    assert (r.json()["configured"], r.json()["channel"]) == (False, "telegram_bot")
    bao.data[f"support/telegram/{co['code']}/telegram_bot"] = {"webhook_secret": TG_SECRET}
    listed = (await client.get("/api/v1/intake/sources", headers=owner_session["headers"])).json()
    mine = [s for s in listed if s["company"] == co["code"]]
    assert (
        len(mine) == 1 and mine[0]["configured"] is True
    )  # the secret's presence, never its value
    assert TG_SECRET not in json.dumps(listed)
    state = await su.fetchval(
        "SELECT state FROM support.channels WHERE company_id = $1 AND kind = 'telegram_bot'",
        co["id"],
    )
    assert state == "shadow"  # never live from here


async def test_the_telegram_webhook_checks_its_secret_ip_and_update_id(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, bao: FakeBao,
) -> None:  # fmt: skip
    co = await new_company()
    body = {
        "company": co["code"],
        "kind": "telegram",
        "channel": "telegram_bot",
        "allowed_ips": [],
        "kinds": [],
    }
    assert (await _source(client, hub, owner_session, body)).status_code == 201
    bao.data[f"support/telegram/{co['code']}/telegram_bot"] = {"webhook_secret": TG_SECRET}
    path = f"/intake/v1/telegram/{co['code']}/telegram_bot"
    update = {
        "update_id": 4001,
        "message": {"message_id": 11, "chat": {"id": 555, "type": "private"},
                    "from": {"id": 555, "username": "buyer_one", "first_name": "علی"},
                    "text": "سلام، کارتم 4111 1111 1111 1111 است"},
    }  # fmt: skip
    ok_headers = {"X-Telegram-Bot-Api-Secret-Token": TG_SECRET, "X-Forwarded-For": TG_IP}
    r = await client.post(
        path, json=update, headers={**ok_headers, "X-Telegram-Bot-Api-Secret-Token": "wrong"}
    )
    assert r.status_code == 401 and "detail" not in r.json()
    assert await _counts(su, co["id"]) == (0, 0, 1)
    r = await client.post(path, json=update, headers={**ok_headers, "X-Forwarded-For": "8.8.8.8"})
    assert r.status_code == 403
    assert await _counts(su, co["id"]) == (0, 0, 2)
    r = await client.post(path, json=update, headers=ok_headers)
    assert r.status_code == 200 and r.json() == {"ok": True}
    events, msgs, _ = await _counts(su, co["id"])
    assert (events, msgs) == (1, 1)
    stored = await su.fetchrow(
        "SELECT body, masked FROM support.messages WHERE company_id = $1", co["id"]
    )
    assert "4111" not in stored["body"] and "card" in stored["masked"]
    cust = await su.fetchrow(
        "SELECT handle, started_at FROM support.customers WHERE company_id = $1", co["id"]
    )
    assert cust["handle"] == "@buyer_one" and cust["started_at"] is not None
    r = await client.post(path, json=update, headers=ok_headers)  # Telegram's retry
    assert r.status_code == 200 and r.json()["duplicate"] is True
    assert await _counts(su, co["id"]) == (1, 1, 3)
    r = await client.post(
        f"/intake/v1/telegram/{co['code']}/telegram_business", json=update, headers=ok_headers
    )
    assert r.status_code == 401  # no such source


async def test_signed_product_events_stale_and_repeated_ids_are_refused(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, bao: FakeBao,
) -> None:  # fmt: skip
    co = await new_company()
    body = {"company": co["code"], "kind": "product", "allowed_ips": ["10.20.0.0/16"],
            "kinds": ["referral_failed", "support_message"]}  # fmt: skip
    assert (await _source(client, hub, owner_session, body)).status_code == 201
    bao.data[f"support/intake/{co['code']}/product"] = {"secret": SECRET}
    path = f"/intake/v1/product/{co['code']}"
    events = {"events": [
        {"id": "ev-1", "kind": "referral_failed", "subject": "88123456", "data": {"exchange": "lbank"}},
        {"id": "ev-2", "kind": "signup", "subject": "88123456", "data": {}},
    ]}  # fmt: skip
    raw, ts, sig = _signed(events)
    inside = {"X-Forwarded-For": "10.20.3.4", "Content-Type": "application/json"}
    r = await client.post(
        path,
        content=raw,
        headers={**inside, "X-HQ-Timestamp": ts, "X-HQ-Signature": "sha256=" + "0" * 64},
    )
    assert r.status_code == 401
    raw_old, ts_old, sig_old = _signed(events, ts=int(time.time()) - 900)
    r = await client.post(
        path,
        content=raw_old,
        headers={**inside, "X-HQ-Timestamp": ts_old, "X-HQ-Signature": sig_old},
    )
    assert r.status_code == 401
    r = await client.post(
        path,
        content=raw,
        headers={"X-Forwarded-For": "1.2.3.4", "X-HQ-Timestamp": ts, "X-HQ-Signature": sig},
    )
    assert r.status_code == 403
    assert await _counts(su, co["id"]) == (0, 0, 3)
    reasons = [r["reason"] for r in await su.fetch(
        "SELECT reason FROM intake.rejections WHERE company_id = $1 ORDER BY at", co["id"])]  # fmt: skip
    assert reasons == ["bad_signature", "stale", "ip_not_allowed"]
    r = await client.post(
        path, content=raw, headers={**inside, "X-HQ-Timestamp": ts, "X-HQ-Signature": sig}
    )
    assert r.status_code == 200 and r.json() == {"accepted": 1, "duplicates": 0, "ignored": 1}
    ev = await su.fetchrow(
        "SELECT subject, data, state FROM intake.events WHERE company_id = $1", co["id"]
    )
    assert len(ev["subject"]) == 64 and "88123456" not in json.dumps(
        dict(ev)
    )  # the UID's pseudonym only
    r = await client.post(
        path, content=raw, headers={**inside, "X-HQ-Timestamp": ts, "X-HQ-Signature": sig}
    )
    assert r.status_code == 200 and r.json() == {"accepted": 0, "duplicates": 1, "ignored": 1}
    assert (await _counts(su, co["id"]))[0] == 1  # nothing new
    # A product's support message enters the desk on product_bot (CR-011).
    msg = {
        "events": [
            {
                "id": "ev-3",
                "kind": "support_message",
                "subject": "u-77",
                "data": {"text": "سلام از ربات"},
            }
        ]
    }
    raw, ts, sig = _signed(msg)
    r = await client.post(
        path, content=raw, headers={**inside, "X-HQ-Timestamp": ts, "X-HQ-Signature": sig}
    )
    assert r.status_code == 200 and r.json()["accepted"] == 1
    assert (
        await su.fetchval(
            "SELECT channel FROM support.conversations WHERE company_id = $1", co["id"]
        )
        == "product_bot"
    )


async def test_product_referral_events_open_and_rescue_a_case_as_they_arrive(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, bao: FakeBao,
) -> None:  # fmt: skip
    """§3.4 meets §9 (intake.APPLIERS, domain/product_events.py): a signed
    `referral_failed` opens the rescue case as it arrives, the product's
    later `referral_verified` of the same UID closes it rescued, a signup is
    kept for the funnel and an event without an exchange is ignored. A
    database write only (no model, no outside call): it runs while locked."""
    co = await new_company()
    body = {"company": co["code"], "kind": "product", "allowed_ips": ["10.20.0.0/16"],
            "kinds": ["referral_failed", "referral_verified", "signup"]}  # fmt: skip
    assert (await _source(client, hub, owner_session, body)).status_code == 201
    bao.data[f"support/intake/{co['code']}/product"] = {"secret": SECRET}
    inside = {"X-Forwarded-For": "10.20.3.4", "Content-Type": "application/json"}

    async def post(events: list[dict[str, Any]]) -> httpx.Response:
        raw, ts, sig = _signed({"events": events})
        return await client.post(f"/intake/v1/product/{co['code']}", content=raw,
                                 headers={**inside, "X-HQ-Timestamp": ts, "X-HQ-Signature": sig})  # fmt: skip

    async with holding_switch(su, "engaged"):
        r = await post([
            {"id": "rf-1", "kind": "referral_failed", "subject": "77001122", "data": {"exchange": "lbank"}},
            {"id": "su-1", "kind": "signup", "subject": "77001122", "data": {}},
            {"id": "rf-2", "kind": "referral_failed", "subject": "77009999", "data": {}},
        ])  # fmt: skip
        assert r.status_code == 200 and r.json()["accepted"] == 3
        states = {e["event_id"]: e["state"] for e in await su.fetch(
            "SELECT event_id, state FROM intake.events WHERE company_id = $1", co["id"])}  # fmt: skip
        assert states == {"rf-1": "applied", "su-1": "applied", "rf-2": "ignored"}
        case = await su.fetchrow(
            "SELECT ref, source, state, subject FROM growth.rescue_cases WHERE company_id = $1",
            co["id"],
        )
        assert (case["source"], case["state"]) == ("product", "open")
        assert "77001122" not in case["subject"] and len(case["subject"]) == 64
        r = await post([
            {"id": "rv-1", "kind": "referral_verified", "subject": "77001122", "data": {"exchange": "lbank"}},
        ])  # fmt: skip
        assert r.status_code == 200 and r.json()["accepted"] == 1
    row = await su.fetchrow(
        "SELECT state, close_reason FROM growth.rescue_cases WHERE ref = $1", case["ref"]
    )
    assert (row["state"], row["close_reason"]) == ("rescued", "product_verified")
    assert (
        await su.fetchval("SELECT count(*) FROM growth.sends WHERE company_id = $1", co["id"]) == 0
    )


async def test_a_chatwoot_message_is_signed_and_stored(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, bao: FakeBao,
) -> None:  # fmt: skip
    co = await new_company()
    body = {"company": co["code"], "kind": "chatwoot", "allowed_ips": [], "kinds": []}
    assert (await _source(client, hub, owner_session, body)).status_code == 201
    bao.data[f"support/intake/{co['code']}/chatwoot"] = {"secret": SECRET}
    event = {"event": "message_created", "id": 9001, "message_type": "incoming", "private": False,
             "content": "سلام از سایت", "sender": {"id": 42, "name": "مهمان"},
             "conversation": {"id": 7}, "account": {"id": 1}}  # fmt: skip
    raw, ts, sig = _signed(event)
    headers = {
        "X-Chatwoot-Timestamp": ts,
        "X-Chatwoot-Signature": sig,
        "Content-Type": "application/json",
    }
    r = await client.post(f"/intake/v1/chatwoot/{co['code']}", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    conv = await su.fetchrow(
        "SELECT channel, external FROM support.conversations WHERE company_id = $1", co["id"]
    )
    assert conv["channel"] == "chatwoot" and json.loads(conv["external"]) == {
        "account_id": 1,
        "conversation_id": 7,
    }
    r = await client.post(f"/intake/v1/chatwoot/{co['code']}", content=raw, headers=headers)
    assert r.json()["duplicate"] is True


async def test_unknown_companies_and_oversized_bodies_say_nothing(
    client: httpx.AsyncClient, hub: Hub
) -> None:
    r = await client.post("/intake/v1/product/NOSUCH", json={"events": []})
    assert r.status_code == 401 and "detail" not in r.json()
    assert I._ip_ok(TG_IP, [], telegram=True) and not I._ip_ok("8.8.8.8", [], telegram=True)
    assert I._signed(SECRET, "abc", b"{}", "sha256=00", 300) == "bad_signature"
    # /internal is not an intake route.
    r = await client.post("/intake/v1/internal/x", json={})
    assert r.status_code in (404, 405)


async def test_the_egress_sender_gives_the_token_to_egress_only(
    hub: Hub, new_company: Callable[..., Any], bao: FakeBao
) -> None:
    from hq_api.domain import desk

    co = await new_company()
    bao.data[f"support/telegram/{co['code']}/telegram_bot"] = {
        "bot_token": "123456:" + "x" * 35, "webhook_secret": TG_SECRET,
    }  # fmt: skip
    seen: list[dict[str, Any]] = []

    def egress(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        if seen[-1]["body"]["payload"].get("chat_id") == 2:
            return httpx.Response(200, json={"outcome": "error", "code": "no_channel", "data": {}})
        return httpx.Response(200, json={"outcome": "ok", "data": {"message_id": 77}})

    sender = desk.EgressSender(httpx.MockTransport(egress))
    channel = {"kind": "telegram_bot", "config": {}}
    ok = await sender.send(
        hub, company=co["code"], channel=channel, conv={"external": {"chat_id": 1}}, text="سلام"
    )
    assert (ok.ok, ok.external_id) == (True, "77")
    assert seen[0]["url"].endswith("/v1/support/send")
    assert seen[0]["body"]["method"] == "sendMessage" and seen[0]["body"]["token"].startswith(
        "123456:"
    )
    refused = await sender.send(
        hub, company=co["code"], channel=channel, conv={"external": {"chat_id": 2}}, text="x"
    )
    assert (refused.ok, refused.code) == (False, "no_channel")
    hook = await sender.set_webhook(
        hub,
        company=co["code"],
        channel="telegram_bot",
        url=f"https://hq.test/intake/v1/telegram/{co['code']}/telegram_bot",
    )
    assert hook.ok and seen[-1]["body"]["payload"]["secret_token"] == TG_SECRET
    no_secret = await sender.send(
        hub, company="NOSUCH", channel=channel, conv={"external": {"chat_id": 1}}, text="x"
    )
    assert (no_secret.ok, no_secret.code) == (False, "no_channel")


async def test_the_sweep_sets_a_telegram_webhook_once_and_only_while_unlocked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    from hq_api.worker.activities import _ScopedTx
    from hq_api.worker.desk_activities import DeskActivities

    from .p10_support import fake_telegram, holding_switch

    co = await new_company()
    src = await su.fetchval(
        """INSERT INTO intake.sources (company_id, kind, channel) VALUES ($1, 'telegram', 'telegram_bot')
           RETURNING id""",
        co["id"],
    )
    assert src
    await su.execute(
        "INSERT INTO support.channels (company_id, kind, state) VALUES ($1, 'telegram_bot', 'shadow')",
        co["id"],
    )
    acts = DeskActivities(hub, None, lambda: _ScopedTx(hub))
    async with fake_telegram() as tg:
        async with holding_switch(su, "engaged"):
            assert (await acts.support_sweep())["skipped"] is True
        assert not tg.calls
        async with holding_switch(su, "released"):
            first = await acts.support_sweep()
            second = await acts.support_sweep()
    hooks = [c for c in tg.calls if c.get("webhook") and c["company"] == co["code"]]
    assert len(hooks) == 1 and hooks[0]["webhook"].endswith(
        f"/intake/v1/telegram/{co['code']}/telegram_bot"
    )
    assert (
        f"{co['code']}/telegram_bot" in first["webhooks"]
        and f"{co['code']}/telegram_bot" not in second["webhooks"]
    )
    state = await su.fetchval(
        "SELECT state FROM support.channels WHERE company_id = $1 AND kind = 'telegram_bot'",
        co["id"],
    )
    assert state == "shadow"  # a webhook makes nothing live
