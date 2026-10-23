"""Owner settings and interactions, the inbox summary, push registrations."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.channels import generate_vapid_keys
from hq_api.hub import Hub

from .test_notifications import API, khalvat, owner_settings, raise_


async def test_inbox_summary_is_cheap_and_counts(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    before = (await client.get(f"{API}/inbox/summary", headers=owner)).json()
    await raise_(hub, co, "urgent")
    await raise_(hub, co, "info")
    started = time.perf_counter()
    r = await client.get(f"{API}/inbox/summary", headers=owner)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert r.status_code == 200
    after = r.json()
    assert after["notifications"]["urgent"] == before["notifications"]["urgent"] + 1
    assert after["notifications"]["info"] == before["notifications"]["info"] + 1
    assert set(after) == {
        "decisions_pending",
        "decisions_by_risk",
        "deliverables_unrated",
        "messages_unread",
        "notifications",
        "khalvat",
    }
    assert set(after["decisions_by_risk"]) == {"low", "medium", "high"}
    assert after["khalvat"] is False
    assert elapsed_ms < 500  # generous for CI; the query itself is one round trip
    async with khalvat(client, owner):
        assert (await client.get(f"{API}/inbox/summary", headers=owner)).json()["khalvat"] is True


async def test_owner_settings_validation_and_versions(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    cur = await client.get(f"{API}/owner/settings", headers=owner)
    assert cur.status_code == 200
    s = cur.json()
    assert cur.headers["etag"] == f'"{s["version"]}"'
    assert set(s) == {
        "timezone",
        "morning_report_at",
        "digest_minutes",
        "ceo_daily_attention",
        "learning_daily_cap",
        "calendars",
        "watch_after_hours",
        "provision_ssh_sources",
        # ⟨1.5⟩ prompt 12 part A (contract §21.12)
        "advisor",
        "substitutes",
        "version",
        # ⟨1.5⟩ prompt 12 part B (contract §21.12)
        "audio_briefings",
        "ceo_weekly_letter",
        "reminders",
        # ⟨1.5⟩ prompt 12 §3, §13 (contract §21.12)
        "weekly_review",
        "digital_ceo",
    }
    v = {"If-Match": str(s["version"])}
    assert (await client.put(f"{API}/owner/settings", json={}, headers=owner)).status_code == 428
    for bad in (
        {"timezone": "Mars/Base"},
        {"morning_report_at": "25:00"},
        {"digest_minutes": 1},
        {"calendars": []},
    ):
        r = await client.put(f"{API}/owner/settings", json=bad, headers={**owner, **v})
        assert r.status_code == 422, bad
    stale = await client.put(
        f"{API}/owner/settings", json={"digest_minutes": 30}, headers={**owner, "If-Match": "0"}
    )
    assert stale.status_code == 409
    async with owner_settings(
        client, owner, morning_report_at="07:30", calendars=["gregorian", "jalali"]
    ):
        now = (await client.get(f"{API}/owner/settings", headers=owner)).json()
        assert now["morning_report_at"] == "07:30" and now["timezone"] == s["timezone"]
        assert now["calendars"] == ["gregorian", "jalali"] and now["version"] == s["version"] + 1
    restored = (await client.get(f"{API}/owner/settings", headers=owner)).json()
    assert restored["morning_report_at"] == s["morning_report_at"]
    log = (
        await client.get(f"{API}/owner/interactions", params={"kind": "setting"}, headers=owner)
    ).json()
    assert any(i["action"] == "owner.settings" for i in log["items"])


async def test_interactions_page_with_a_cursor(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    async with khalvat(client, owner):
        pass  # on + off: two interactions at least
    first = (
        await client.get(f"{API}/owner/interactions", params={"limit": 1}, headers=owner)
    ).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = (
        await client.get(
            f"{API}/owner/interactions",
            params={"limit": 1, "cursor": first["next_cursor"]},
            headers=owner,
        )
    ).json()
    assert second["items"][0]["id"] != first["items"][0]["id"]
    assert second["items"][0]["at"] <= first["items"][0]["at"]
    presence = [
        i
        for i in (await client.get(f"{API}/owner/interactions", headers=owner)).json()["items"]
        if i["kind"] == "presence"
    ]
    assert {"presence.khalvat_on", "presence.khalvat_off"} <= {i["action"] for i in presence}
    bad = await client.get(f"{API}/owner/interactions", params={"cursor": "%%%"}, headers=owner)
    assert bad.status_code == 422


async def test_push_registrations(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    saved = (hub.secrets.vapid_private_pem, hub.secrets.vapid_public_key)
    try:
        hub.secrets.vapid_private_pem, hub.secrets.vapid_public_key = "", ""
        off = await client.get(f"{API}/push/vapid-public-key", headers=owner)
        assert off.status_code == 503 and off.json()["code"] == "channel_not_configured"
        hub.secrets.vapid_private_pem, hub.secrets.vapid_public_key = generate_vapid_keys()
        on = await client.get(f"{API}/push/vapid-public-key", headers=owner)
        assert on.status_code == 200 and on.json()["public_key"] == hub.secrets.vapid_public_key
    finally:
        hub.secrets.vapid_private_pem, hub.secrets.vapid_public_key = saved

    sub = {
        "endpoint": f"https://push.example.test/api-{time.time_ns()}",
        "keys": {"p256dh": "B" + "A" * 86, "auth": "c2VjcmV0c2VjcmV0"},
        "device_name": "Laptop",
    }
    created = await client.post(f"{API}/push/web-subscriptions", json=sub, headers=owner)
    assert created.status_code == 201 and created.json()["revoked_at"] is None
    sid = created.json()["id"]
    plain = await client.post(
        f"{API}/push/web-subscriptions", json={**sub, "endpoint": "http://x"}, headers=owner
    )
    assert plain.status_code == 422
    assert (
        await client.post(f"{API}/push/web-subscriptions/{sid}/revoke", headers=owner)
    ).status_code == 204
    again = await client.post(f"{API}/push/web-subscriptions", json=sub, headers=owner)
    assert again.json()["id"] == sid and again.json()["revoked_at"] is None  # re-activated
    assert (
        await client.post(f"{API}/push/web-subscriptions/{sid}/revoke", headers=owner)
    ).status_code == 204
    missing = "00000000-0000-0000-0000-000000000001"
    assert (
        await client.post(f"{API}/push/web-subscriptions/{missing}/revoke", headers=owner)
    ).status_code == 404

    tok = await client.post(
        f"{API}/push/fcm-tokens",
        json={"token": f"fcm-{time.time_ns()}-abcdefghij", "device_name": "Pixel"},
        headers=owner,
    )
    assert tok.status_code == 201
    assert (
        await client.post(f"{API}/push/fcm-tokens/{tok.json()['id']}/revoke", headers=owner)
    ).status_code == 204
    assert (
        await client.post(f"{API}/push/fcm-tokens/{missing}/revoke", headers=owner)
    ).status_code == 404
    short = await client.post(
        f"{API}/push/fcm-tokens", json={"token": "x", "device_name": "P"}, headers=owner
    )
    assert short.status_code == 422

    log = (
        await client.get(f"{API}/owner/interactions", params={"kind": "setting"}, headers=owner)
    ).json()
    assert {"push.web_subscribe", "push.web_revoke", "push.fcm_register", "push.fcm_revoke"} <= {
        i["action"] for i in log["items"]
    }


async def test_owner_endpoints_need_a_session(client: httpx.AsyncClient) -> None:
    for path in (
        "/notifications",
        "/inbox/summary",
        "/owner/presence",
        "/owner/settings",
        "/owner/away-summary",
        "/owner/interactions",
        "/notification-settings",
        "/push/vapid-public-key",
    ):
        r = await client.get(f"{API}{path}")
        assert r.status_code == 401 and r.json()["code"] == "unauthenticated", path
