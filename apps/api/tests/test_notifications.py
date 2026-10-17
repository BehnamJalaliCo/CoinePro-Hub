"""Notification rules (OPERATING_MODEL §1.7, contract §6): levels, Khalvat,
mutes, CEO attention quota, learning cap, digest batches and the rhythm.

owner.presence, owner.settings and notify.settings are session-wide
singletons: every test restores them, and assertions are scoped to the
companies the test creates.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest

from hq_api.domain import notify
from hq_api.domain.notify import LevelSetting, decide, level_setting, raise_notification
from hq_api.hub import Hub

from .conftest import superuser
from .test_channels import push_channels

API = "/api/v1"


async def raise_(hub: Hub, co: dict[str, Any], level: str, **kw: Any) -> dict[str, Any]:
    async with hub.db.tx([co["id"]]) as tx:
        return await raise_notification(
            tx,
            company_id=co["id"],
            company_code=co["code"],
            level=level,
            title_fa=kw.pop("title_fa", f"اعلان {level}"),
            **kw,
        )


async def fetch(hub: Hub, nid: UUID) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await tx.one("SELECT * FROM notify.notifications WHERE id = :id", id=nid)


async def backdate(nid: UUID, minutes: int) -> None:
    conn = await superuser()
    try:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL session_replication_role = replica"
            )  # created_at is immutable
            await conn.execute(
                "UPDATE notify.notifications SET created_at = created_at - make_interval(mins => $1) WHERE id = $2",
                minutes,
                nid,
            )
    finally:
        await conn.close()


async def learning_shown(hub: Hub) -> int:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        n = await tx.scalar(
            """SELECT count(*) FROM notify.notifications n, owner.settings s
               WHERE n.level = 'learning' AND n.delivered_in_app
                 AND n.created_at >= date_trunc('day', now() AT TIME ZONE s.timezone) AT TIME ZONE s.timezone"""
        )
    return int(n)


@contextlib.asynccontextmanager
async def owner_settings(
    client: httpx.AsyncClient, owner: dict[str, str], **changes: Any
) -> AsyncIterator[None]:
    cur = (await client.get(f"{API}/owner/settings", headers=owner)).json()
    keep = {k: cur[k] for k in changes}
    r = await client.put(
        f"{API}/owner/settings", json=changes, headers={**owner, "If-Match": str(cur["version"])}
    )
    assert r.status_code == 200, r.text
    try:
        yield
    finally:
        now = (await client.get(f"{API}/owner/settings", headers=owner)).json()
        r = await client.put(
            f"{API}/owner/settings", json=keep, headers={**owner, "If-Match": str(now["version"])}
        )
        assert r.status_code == 200, r.text


@contextlib.asynccontextmanager
async def matrix(
    client: httpx.AsyncClient, owner: dict[str, str], m: dict[str, Any]
) -> AsyncIterator[None]:
    cur = (await client.get(f"{API}/notification-settings", headers=owner)).json()
    r = await client.put(
        f"{API}/notification-settings",
        json={"matrix": {**cur["matrix"], **m}},
        headers={**owner, "If-Match": str(cur["version"])},
    )
    assert r.status_code == 200, r.text
    try:
        yield
    finally:
        now = (await client.get(f"{API}/notification-settings", headers=owner)).json()
        r = await client.put(
            f"{API}/notification-settings",
            json={"matrix": cur["matrix"]},
            headers={**owner, "If-Match": str(now["version"])},
        )
        assert r.status_code == 200, r.text


@contextlib.asynccontextmanager
async def khalvat(client: httpx.AsyncClient, owner: dict[str, str]) -> AsyncIterator[None]:
    r = await client.put(f"{API}/owner/presence", json={"khalvat": True}, headers=owner)
    assert r.status_code == 200 and r.json()["khalvat"] is True
    try:
        yield
    finally:
        await client.put(f"{API}/owner/presence", json={"khalvat": False}, headers=owner)


# ------------------------------------------------------------------- pure rules --

NOW = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)
PLAIN = LevelSetting(in_app=True, push=True, sound=False, muted_until=None)


@pytest.mark.parametrize(
    ("level", "kw", "expect"),
    [
        ("urgent", {"khalvat": True}, ("delivered", None, True, True)),
        ("decision", {"khalvat": True}, ("held", "khalvat", False, False)),
        ("decision", {}, ("queued", "digest", True, False)),
        ("report", {}, ("queued", "rhythm", True, False)),
        ("info", {}, ("delivered", None, True, False)),
        ("learning", {"learning_over_cap": True}, ("suppressed", "learning_cap", False, False)),
        ("info", {"ceo_over_quota": True}, ("queued", "attention_quota", False, False)),
        ("urgent", {"ceo_over_quota": True}, ("delivered", None, True, True)),
    ],
)
def test_decide(level: str, kw: dict[str, Any], expect: tuple[Any, ...]) -> None:
    args = {"khalvat": False, "ceo_over_quota": False, "learning_over_cap": False, **kw}
    d = decide(level=level, setting=PLAIN, now=NOW, **args)
    assert (d["state"], d["queue_reason"], d["in_app"], d["push"]) == expect


def test_level_settings_merge_and_mute() -> None:
    m = {
        "*": {"info": {"push": True}, "decision": {"push": False}},
        "TY": {"info": {"in_app": False}, "report": {"muted_until": "2026-10-18T00:00:00Z"}},
    }
    info = level_setting(m, "TY", "info")
    assert (info.in_app, info.push, info.sound) == (False, True, False)
    assert level_setting(m, "FX", "decision").push is False
    assert level_setting(m, "TY", "report").muted(NOW) is True
    assert level_setting(m, "TY", "report").muted(NOW + timedelta(days=2)) is False
    assert level_setting({"*": {"info": {"muted_until": "bad"}}}, "TY", "info").muted_until is None
    off = LevelSetting(in_app=False, push=False, sound=False, muted_until=None)
    assert (
        decide(
            level="info",
            khalvat=False,
            setting=off,
            now=NOW,
            ceo_over_quota=False,
            learning_over_cap=False,
        )["state"]
        == "suppressed"
    )
    quiet = LevelSetting(in_app=True, push=False, sound=False, muted_until=None)
    for level in ("decision", "report"):
        d = decide(
            level=level,
            khalvat=False,
            setting=quiet,
            now=NOW,
            ceo_over_quota=False,
            learning_over_cap=False,
        )
        assert d["state"] == "delivered"


async def test_unknown_level_is_refused(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    with pytest.raises(ValueError, match="unknown level"):
        await raise_(hub, co, "loud")


# ------------------------------------------------------------- Khalvat (prompt §11.5) --


async def test_khalvat_sends_only_urgent_and_away_summary_counts(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with push_channels(hub) as (cap, browser):
        assert browser is not None
        async with khalvat(client, owner):
            start = (await client.get(f"{API}/owner/presence", headers=owner)).json()["since"]
            decision = await raise_(hub, co, "decision", link_kind="decision", link_ref="D-000001")
            urgent = await raise_(hub, co, "urgent", title_fa="خرابی پرداخت")
            assert decision["state"] == "held" and decision["queue_reason"] == "khalvat"
            assert urgent["state"] == "delivered" and urgent["push_now"] is True
            sent = await notify.deliver_pending(hub, [urgent["id"], decision["id"]])
            assert sent == {"pushed": 1, "considered": 1}
            u, d = await fetch(hub, urgent["id"]), await fetch(hub, decision["id"])
            assert u["delivered_in_app"] and u["delivered_web_push"] and u["sound"]
            assert not d["delivered_in_app"] and not d["delivered_web_push"]
            assert [browser.decrypt(r.content)["title"] for r in cap.to(browser.endpoint)] == [
                "خرابی پرداخت"
            ]
            # still in Khalvat: the digest pass releases nothing
            assert (await notify.flush_digest(hub))["khalvat"] is True
            assert (await fetch(hub, decision["id"]))["state"] == "held"
            listed = (
                await client.get(
                    f"{API}/notifications", params={"company": co["code"]}, headers=owner
                )
            ).json()
            assert [i["level"] for i in listed["items"]] == ["urgent"]
        # Khalvat off: the held decision appears (and joins the next digest)
        d = await fetch(hub, decision["id"])
        assert d["delivered_in_app"] and d["state"] == "queued" and d["queue_reason"] == "digest"
        away = (
            await client.get(f"{API}/owner/away-summary", params={"since": start}, headers=owner)
        ).json()
        mine = next(c for c in away["companies"] if c["company"] == co["code"])
        assert mine["notifications_new"] == 2
        assert away["notifications"]["by_level"]["urgent"] >= 1
        assert any(t["id"] == str(urgent["id"]) for t in away["notifications"]["top"])
        default = await client.get(f"{API}/owner/away-summary", headers=owner)
        assert default.status_code == 200 and default.json()["since"] is not None


async def test_presence_changes_are_announced_to_every_company(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    before = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1",
        f"hq.core.{co['code']}.presence.changed",
    )
    async with khalvat(client, owner):
        again = await client.put(f"{API}/owner/presence", json={"khalvat": True}, headers=owner)
        assert again.status_code == 200  # no second announcement for the same state
    after = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1",
        f"hq.core.{co['code']}.presence.changed",
    )
    assert after - before == 2  # on, then off
    bad = await client.put(
        f"{API}/owner/presence",
        json={"khalvat": True, "until": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        headers=owner,
    )
    assert bad.status_code == 422
    assert (await client.get(f"{API}/owner/presence", headers=owner)).json()["khalvat"] is False


# ----------------------------------------------------------------- quotas, caps --


async def test_ceo_attention_quota_queues_for_the_digest(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ceo = f"{co['code']}-CEO"
    async with owner_settings(client, owner, ceo_daily_attention=2):
        states = [
            (await raise_(hub, co, "info", source_kind="agent", source_code=ceo))["state"]
            for _ in range(3)
        ]
        assert states == ["delivered", "delivered", "queued"]
        urgent = await raise_(hub, co, "urgent", source_kind="agent", source_code=ceo)
        assert urgent["state"] == "delivered"  # urgent never waits
        other = await raise_(
            hub, co, "info", source_kind="agent", source_code=f"{co['code']}-TECH-MGR"
        )
        assert other["state"] == "delivered"  # the quota is the CEO's, not the company's
        last = await raise_(hub, co, "info", source_kind="agent", source_code=ceo)
        assert last["queue_reason"] == "attention_quota" and not last["delivered_in_app"]
        await backdate(last["id"], 120)
        await notify.flush_digest(hub)
        released = await fetch(hub, last["id"])
        assert (
            released["state"] == "delivered"
            and released["delivered_in_app"]
            and released["batch_id"]
        )


async def test_learning_questions_are_capped_per_day(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    shown = await learning_shown(hub)
    if shown + 1 > 20:
        pytest.skip("too many learning questions today in this session")
    choices = [{"id": "cost", "label_fa": "هزینه"}, {"id": "risk", "label_fa": "ریسک"}]
    async with owner_settings(client, owner, learning_daily_cap=int(shown) + 1):
        first = await raise_(hub, co, "learning", choices=choices)
        second = await raise_(hub, co, "learning", choices=choices)
        assert first["state"] == "delivered" and first["delivered_in_app"]
        assert second["state"] == "suppressed" and second["queue_reason"] == "learning_cap"


async def test_mutes_hold_until_they_end(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    async with matrix(
        client, owner, {co["code"]: {"info": {"muted_until": until}, "report": {"in_app": False}}}
    ):
        held = await raise_(hub, co, "info")
        hidden = await raise_(hub, co, "report")
        urgent = await raise_(hub, co, "urgent")
        assert (held["state"], held["queue_reason"]) == ("held", "muted")
        assert hidden["state"] == "suppressed"
        assert urgent["state"] == "delivered"
        await notify.flush_digest(hub)
        assert (await fetch(hub, held["id"]))["state"] == "held"  # still muted
    await notify.flush_digest(hub)  # the mute is gone now
    assert (await fetch(hub, held["id"]))["delivered_in_app"] is True


async def test_digest_sends_one_batch_per_company(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    a, b = await new_company(), await new_company()
    async with (
        push_channels(hub) as (cap, browser),
        owner_settings(client, owner, digest_minutes=30),
    ):
        assert browser is not None
        rows = [
            await raise_(hub, a, "decision"),
            await raise_(hub, a, "decision"),
            await raise_(hub, b, "decision"),
        ]
        fresh = await raise_(hub, a, "decision")  # too new for this batch
        for r in rows:
            assert r["state"] == "queued" and r["delivered_in_app"]
            await backdate(r["id"], 45)
        result = await notify.flush_digest(hub)
        assert result["khalvat"] is False and result["batches"] >= 2
        batches = await su.fetch(
            """SELECT c.code, b.items FROM notify.digest_batches b JOIN core.companies c ON c.id = b.company_id
               WHERE c.code = ANY($1::text[]) ORDER BY c.code""",
            [a["code"], b["code"]],
        )
        assert sorted((r["code"], r["items"]) for r in batches) == sorted(
            [(a["code"], 2), (b["code"], 1)]
        )
        assert (await fetch(hub, fresh["id"]))["state"] == "queued"
        pushes = [browser.decrypt(r.content) for r in cap.to(browser.endpoint)]
        assert {p["company"] for p in pushes} >= {a["code"], b["code"]}
        mine = [p for p in pushes if p["company"] in (a["code"], b["code"])]
        assert sorted((p["company"], p["count"]) for p in mine) == sorted(
            [(a["code"], "2"), (b["code"], "1")]
        )
        assert all(p["level"] == "decision" for p in mine)  # one push per batch
        assert (await fetch(hub, rows[0]["id"]))["delivered_web_push"] is True
        # idempotent: nothing more for these two companies
        await notify.flush_digest(hub)
        again = await su.fetchval(
            """SELECT count(*) FROM notify.digest_batches b JOIN core.companies c ON c.id = b.company_id
               WHERE c.code = ANY($1::text[])""",
            [a["code"], b["code"]],
        )
        assert again == 2


async def test_reports_wait_for_the_rhythm(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    report = await raise_(hub, co, "report")
    assert (report["state"], report["queue_reason"], report["delivered_in_app"]) == (
        "queued",
        "rhythm",
        True,
    )
    async with push_channels(hub, web=False, telegram=True) as (cap, _):
        out = await notify.flush_rhythm(hub)
        assert out["reports"] >= 1
        assert len(cap.to("https://api.telegram.org/")) == 1
    row = await fetch(hub, report["id"])
    assert row["state"] == "delivered" and row["batch_id"] is not None and row["delivered_telegram"]
    assert await notify.flush_rhythm(hub) == {"reports": 0}
    assert await notify.deliver_pending(hub, []) == {"pushed": 0}


# ------------------------------------------------------------------- endpoints --


async def test_list_read_answer_and_read_all(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    info = await raise_(hub, co, "info", link_kind="work", link_ref="W-000009", body_fa="متن")
    shown = await learning_shown(hub)
    if shown + 1 > 20:
        pytest.skip("too many learning questions today in this session")
    async with owner_settings(client, owner, learning_daily_cap=shown + 1):
        question = await raise_(
            hub,
            co,
            "learning",
            choices=[{"id": "cost", "label_fa": "هزینه"}, {"id": "risk", "label_fa": "ریسک"}],
        )
    assert question["state"] == "delivered"
    page = await client.get(
        f"{API}/notifications", params={"company": co["code"], "limit": 1}, headers=owner
    )
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 1 and body["next_cursor"]
    rest = await client.get(
        f"{API}/notifications",
        params={"company": co["code"], "cursor": body["next_cursor"]},
        headers=owner,
    )
    ids = [body["items"][0]["id"], *[i["id"] for i in rest.json()["items"]]]
    assert set(ids) == {str(info["id"]), str(question["id"])}
    first = next(i for i in [body["items"][0], *rest.json()["items"]] if i["id"] == str(info["id"]))
    assert (
        first["link"] == {"kind": "work", "ref": "W-000009"}
        and first["delivered"]["in_app"] is True
    )

    r = await client.post(f"{API}/notifications/{info['id']}/read", headers=owner)
    assert r.status_code == 200 and r.json()["read_at"] is not None
    again = await client.post(f"{API}/notifications/{info['id']}/read", headers=owner)
    assert again.json()["read_at"] == r.json()["read_at"]

    wrong = await client.post(
        f"{API}/notifications/{question['id']}/answer", json={"choice_id": "x"}, headers=owner
    )
    assert wrong.status_code == 422 and wrong.json()["code"] == "validation_failed"
    ok = await client.post(
        f"{API}/notifications/{question['id']}/answer", json={"choice_id": "risk"}, headers=owner
    )
    assert ok.status_code == 200 and ok.json()["answer"] == "risk" and ok.json()["read_at"]
    dup = await client.post(
        f"{API}/notifications/{question['id']}/answer", json={"choice_id": "cost"}, headers=owner
    )
    assert dup.status_code == 409

    unread = await client.get(
        f"{API}/notifications", params={"company": co["code"], "unread": True}, headers=owner
    )
    assert unread.json()["items"] == []
    extra = await raise_(hub, co, "info")
    marked = await client.post(
        f"{API}/notifications/read-all", json={"level": "info"}, headers=owner
    )
    assert marked.status_code == 200 and marked.json()["updated"] >= 1
    assert (await fetch(hub, extra["id"]))["read_at"] is not None
    missing = await client.post(
        f"{API}/notifications/00000000-0000-0000-0000-000000000000/read", headers=owner
    )
    assert missing.status_code == 404
    bad = await client.get(f"{API}/notifications", params={"company": "NOPE1"}, headers=owner)
    assert bad.status_code == 422

    log = (
        await client.get(f"{API}/owner/interactions", params={"kind": "answer"}, headers=owner)
    ).json()
    assert any(i["data"].get("notification") == str(question["id"]) for i in log["items"])


async def test_settings_need_the_current_version(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    cur = (await client.get(f"{API}/notification-settings", headers=owner)).json()
    body = {"matrix": cur["matrix"]}
    missing = await client.put(f"{API}/notification-settings", json=body, headers=owner)
    assert missing.status_code == 428 and missing.json()["fields"] == {"If-Match": "required"}
    stale = await client.put(
        f"{API}/notification-settings",
        json=body,
        headers={**owner, "If-Match": str(cur["version"] - 1)},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    junk = await client.put(
        f"{API}/notification-settings", json=body, headers={**owner, "If-Match": "abc"}
    )
    assert junk.status_code == 422
    unknown = await client.put(
        f"{API}/notification-settings",
        json={"matrix": {"NOPE2": {"info": {"push": True}}}},
        headers={**owner, "If-Match": str(cur["version"])},
    )
    assert unknown.status_code == 422
    bad_scope = await client.put(
        f"{API}/notification-settings",
        json={"matrix": {"ty!": {"info": {"push": True}}}},
        headers={**owner, "If-Match": str(cur["version"])},
    )
    assert bad_scope.status_code == 422
    ok = await client.put(
        f"{API}/notification-settings",
        json=body,
        headers={**owner, "If-Match": f'W/"{cur["version"]}"'},
    )
    assert ok.status_code == 200 and ok.json()["version"] == cur["version"] + 1
    assert ok.headers["etag"] == f'"{cur["version"] + 1}"'
