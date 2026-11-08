"""W12 (contract §42 ⟨1.24⟩): the holding live, the hub's data.

The topics and the holding view (§42.1); the five new events and server.state's additive fields
(§42.2) from the places that already write what they report; GET /live/summary (§42.3). Each test
makes its own companies (the test database outlives a run) and reads only its own events.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest

from hq_api import events
from hq_api.domain import live as LV
from hq_api.domain import servers as SV
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.routes.stream import HOLDING_FULL, holding_view, matches
from hq_api.worker.bridge import Bridge, Ticks, tick_data

from .conftest import agent_headers, idem
from .test_control_treasury_stream import serve
from .test_p17_runners import pair, take
from .test_worker import wait_for

IP = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")
SECRETISH = ("hqr1_", "sk-ant", "Bearer", "password", 'token":')


def clean(payload: Any) -> None:
    """§7: no address, no hostname, no secret in what the stream carries."""
    text = json.dumps(payload, ensure_ascii=False)
    assert not IP.search(text), text
    assert ".local" not in text and "hq.coinepro.com" not in text, text
    for s in SECRETISH:
        assert s not in text, (s, text)


async def outbox(su: Any, type_: str, where: str = "", *args: Any) -> list[dict[str, Any]]:
    rows = await su.fetch(
        f"SELECT payload FROM core.outbox WHERE payload->>'type' = $1 {where} ORDER BY id",
        type_,
        *args,
    )
    return [json.loads(r["payload"]) for r in rows]


async def _all(hub: Hub) -> list[Any]:
    return await hub.companies.ids()


# ------------------------------------------------------------ §42.1 topics --
@pytest.mark.parametrize(
    ("type_", "topic"),
    [
        ("session.updated", "orders"),
        ("session.activity", "orders"),
        ("order.routed", "orders"),
        ("holding.flow", "holding"),
        ("links.updated", "holding"),
        ("network.link", "servers"),
        ("server.state", "servers"),
        ("employee.state", "activity"),
        ("llm.tick", "llm"),
    ],
)
def test_each_event_reaches_its_topic(type_: str, topic: str) -> None:
    env = {"type": type_, "company": "AB"}
    assert matches(env, {topic}, None)
    assert not matches(env, set(events.TOPICS) - {topic}, None)  # one topic each
    assert matches(env, {topic}, {"AB"}) and not matches(env, {topic}, {"CD"})


def test_the_holding_view_passes_the_live_events_in_full() -> None:
    assert {
        "server.state", "network.link", "holding.flow", "employee.state", "llm.tick",
        "session.updated", "session.activity", "control.changed", "links.updated",
        "activity.changed",
    } == HOLDING_FULL  # fmt: skip
    for type_ in HOLDING_FULL:
        env = {"id": "x", "type": type_, "at": "t", "company": "AB", "ref": "r", "data": {"a": 1}}
        assert holding_view(env) == env
    env = {"id": "x", "type": "work.created", "at": "t", "company": "AB", "ref": "W", "data": {}}
    assert holding_view(env) == {"id": "x", "type": "work.created", "at": "t", "company": "AB"}


async def test_the_holding_view_streams_a_flow_in_full(
    app: Any, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any], relay: None
) -> None:
    a, b = await new_company(), await new_company()
    ref = f"W-{uuid.uuid4().hex[:8]}"
    got: list[dict[str, Any]] = []

    async def listen(url: str) -> None:
        async with (
            httpx.AsyncClient(base_url=url, timeout=20) as c,
            c.stream(
                "GET",
                "/api/v1/stream",
                headers=owner,
                params={"topics": "holding,work", "company": "*"},
            ) as resp,  # fmt: skip
        ):
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    env = json.loads(line[6:])
                    if env.get("ref") == ref or env.get("id") in seen:
                        got.append(env)
                    if len(got) >= 2:
                        return

    seen: set[str] = set()
    async with serve(app) as url:
        task = asyncio.create_task(listen(url))
        await asyncio.sleep(0.5)
        async with hub.db.tx(await _all(hub)) as tx:
            assert await LV.flow(tx, src=a["code"], dst=b["code"], kind="request", ref=ref,
                                 label_fa="درخواست کار")  # fmt: skip
            await events.emit(tx, a["code"], "work.updated", ref, {"status": "queued"})
            seen.update(
                str(r["event_id"])
                for r in await tx.all(
                    "SELECT event_id FROM core.outbox WHERE payload->>'ref' = :r", r=ref
                )
            )
        await asyncio.wait_for(task, 20)
    flow = next(e for e in got if e["type"] == "holding.flow")
    work = next(e for e in got if e["type"] == "work.updated")
    assert flow["data"]["from"] == a["code"] and flow["data"]["to"] == b["code"]  # in full
    assert set(work) == {"id", "type", "at", "company"}  # reduced


# --------------------------------------------------------- §42.2 holding.flow --
FLOW_KEYS = {"from", "to", "kind", "via", "ref", "root_ref", "label_fa"}


async def test_flow_ends_labels_and_the_hub(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    a = await new_company()
    holding = (await hub.companies.holding()).code
    ref = f"W-{uuid.uuid4().hex[:8]}"
    async with hub.db.tx(await _all(hub)) as tx:
        assert not await LV.flow(tx, src=holding, dst="hub", kind="order", ref=ref)  # one node
        assert await LV.flow(tx, src=holding, dst=a["code"], kind="order", ref=ref, root_ref="W-1",
                             label_fa="  یک   برچسب  " + "خیلی " * 30)  # fmt: skip
        assert await LV.flow(tx, src=a["code"], dst="outside", kind="publish", ref=ref)
    first, second = await outbox(su, "holding.flow", "AND payload->>'ref' = $2", ref)
    assert first["company"] == holding  # the holding's map
    assert set(first["data"]) == FLOW_KEYS
    assert first["data"]["from"] == "hub" and first["data"]["to"] == a["code"]
    assert first["data"]["via"] == "hub" and first["data"]["root_ref"] == "W-1"
    label = first["data"]["label_fa"]
    assert len(label) <= 60 and label.startswith("یک برچسب خیلی") and label.endswith("…")
    assert second["data"]["to"] == "outside" and second["data"]["label_fa"] is None
    assert LV.label("   ") is None and LV.label("کوتاه") == "کوتاه"


async def test_an_owner_order_flows_to_its_holder(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = (await new_company())["code"]
    r = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={
            "text": f"به مدیر مالی {co} بگو گزارش ماهانه را بفرستد",
            "source": "text",
            "company": co,
        },
    )
    assert r.status_code == 201, r.text
    order = r.json()
    (env,) = await outbox(su, "holding.flow", "AND payload->>'ref' = $2", order["ref"])
    d = env["data"]
    assert (d["from"], d["to"], d["kind"]) == ("hub", co, "order")
    assert d["root_ref"] == order["routes"][0]["work_ref"]
    assert d["label_fa"] and len(d["label_fa"]) <= 60 and "سفارش" not in d["label_fa"]
    clean(env)


async def test_a_cross_company_request_is_asked_accepted_and_delivered(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    mine = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": a, "title": "کار ما", "brief": "شرح", "budget": {"tokens": 400_000}},
    )
    assert mine.status_code == 201, mine.text
    r = await client.post(
        "/internal/v1/work",
        headers={**await agent_headers(f"{a}-CEO"), **idem()},
        json={
            "company": b,
            "title": "کمک",
            "brief": "متن درخواست",
            "requested_by_work_id": mine.json()["id"],
        },
    )
    assert r.status_code == 201, r.text
    theirs = r.json()["work"]
    bh = await agent_headers(f"{b}-CEO")
    assert (
        await client.post(f"/internal/v1/work/{theirs['id']}/accept", headers=bh)
    ).status_code == 200
    r = await client.post(
        f"/internal/v1/work/{theirs['id']}/deliver",
        headers={**bh, **idem()},
        json={"title": "پاسخ", "summary": "خلاصه", "body": "متن"},
    )
    assert r.status_code == 200, r.text
    flows = await outbox(su, "holding.flow", "AND payload->>'ref' = $2", theirs["ref"])
    assert [(f["data"]["kind"], f["data"]["from"], f["data"]["to"]) for f in flows] == [
        ("request", a, b), ("accept", b, a), ("deliver", b, a),
    ]  # fmt: skip
    root = await su.fetchval("SELECT COALESCE(r.ref, w.ref) FROM work.work w LEFT JOIN work.work r ON r.id = w.root_id WHERE w.id = $1",
                             uuid.UUID(mine.json()["id"]))  # fmt: skip
    for f in flows:
        assert set(f["data"]) == FLOW_KEYS and f["data"]["root_ref"] == root
        assert "متن درخواست" not in json.dumps(f, ensure_ascii=False)  # never the brief
        clean(f)


async def test_a_linked_read_flows_from_the_data_to_the_reader(
    client: httpx.AsyncClient, new_company: Callable[..., Any], su: Any
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    me = f"{a}-CEO"
    r = await client.get(
        "/internal/v1/linked/read", params={"company": b, "what": "kpis"},
        headers=await agent_headers(me),
    )  # fmt: skip
    assert r.status_code == 200, r.text
    (env,) = await outbox(
        su,
        "holding.flow",
        "AND payload->'data'->>'from' = $2 AND payload->'data'->>'to' = $3",
        b,
        a,
    )
    assert env["data"]["kind"] == "read" and env["data"]["ref"] == me  # no work: the reader
    assert "شاخص‌های" in env["data"]["label_fa"]
    # its own company: nothing crosses
    r = await client.get(
        "/internal/v1/linked/read", params={"company": a, "what": "kpis"},
        headers=await agent_headers(me),
    )  # fmt: skip
    assert r.status_code == 200
    assert not await outbox(su, "holding.flow", "AND payload->'data'->>'from' = $2", a)


async def test_playbook_and_publish_flows(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    pb = f"PB-{uuid.uuid4().int % 10**8:08d}"
    lr = f"LR-{uuid.uuid4().int % 10**8:08d}"
    async with hub.db.tx(await _all(hub)) as tx:
        assert await LV.playbook_flow(
            tx, {"ref": pb, "source": json.dumps({"company": a})}, b, "W-9"
        )
        assert await LV.playbook_flow(tx, {"ref": pb, "source": {}}, b, None)  # from the hub
        assert not await LV.playbook_flow(tx, {"ref": pb, "source": {"company": b}}, b, None)
        assert await LV.publish_flow(tx, {"company": a, "ref": lr, "platform": "instagram"},
                                     [{"platform": "instagram", "external_id": "1"}])  # fmt: skip
    given = await outbox(su, "holding.flow", "AND payload->>'ref' = $2", pb)
    assert [(g["data"]["from"], g["data"]["to"], g["data"]["root_ref"]) for g in given] == [
        (a, b, "W-9"), ("hub", b, None),
    ]  # fmt: skip
    (out,) = await outbox(su, "holding.flow", "AND payload->>'ref' = $2", lr)
    assert (out["data"]["from"], out["data"]["to"], out["data"]["kind"]) == (
        a,
        "outside",
        "publish",
    )
    assert out["data"]["label_fa"] == "انتشار در اینستاگرام"


# -------------------------------------------------------- §42.2 network.link --
LINK_KEYS = {"from", "to", "port", "ok", "ms", "error_fa", "since", "last_ok_at"}


async def _netcheck(client: httpx.AsyncClient, hub: Hub, rn: dict[str, Any], who: Principal | None,
                    results: list[dict[str, Any]]) -> None:  # fmt: skip
    """A netcheck job on `rn`'s runner (the owner's check, or `who`'s) answered with `results`."""
    if who is not None:
        async with hub.db.tx(await _all(hub)) as tx:
            await SV.queue_netchecks(tx, SV.hub_ip(), who)
    job = await take(client, rn)
    assert job["kind"] == "netcheck"
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "سنجش", "data": {"results": results}},
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text


def _row(
    to: str, port: int, ok: bool, ms: float | None = 0.5, error: str | None = None
) -> dict[str, Any]:
    return {"to": to, "ip": "10.10.1.4", "port": port, "ok": ok, "ms": ms, "error": error}


async def test_network_link_on_change_once_a_minute_and_every_owner_result(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    a = await pair(client, hub, owner_session, co, "la")
    b = await pair(client, hub, owner_session, co, "lb")
    aid, bid = a["server"]["id"], b["server"]["id"]
    oversight = Principal(kind="service", code="oversight", role="service")

    async def links() -> list[dict[str, Any]]:
        return await outbox(su, "network.link", "AND payload->'data'->>'from' = $2", aid)

    # The owner's check: every result goes out.
    r = await client.post("/api/v1/infra/network/check", headers=owner_session["headers"])
    assert r.status_code == 202
    await _netcheck(client, hub, a, None, [
        _row("hub", 443, True, 0.8), _row(bid, 22, True), _row(bid, 80, False, None, "Connection refused"),
    ])  # fmt: skip
    got = await links()
    assert len(got) == 3
    for env in got:
        assert set(env["data"]) == LINK_KEYS and env["company"] == co["code"]
        clean(env)
    refused = next(e["data"] for e in got if e["data"]["port"] == 80)
    assert refused["ok"] is False and refused["error_fa"] == "درگاه بسته است؛ اتصال را رد کرد"
    assert refused["last_ok_at"] is None and refused["to"] == bid
    hub443 = next(e["data"] for e in got if e["data"]["to"] == "hub")
    assert hub443["ok"] and hub443["last_ok_at"] and hub443["since"]
    # Not the owner's: the same results say nothing.
    await _netcheck(client, hub, a, oversight, [
        _row("hub", 443, True, 0.9), _row(bid, 22, True), _row(bid, 80, False, None, "timeout"),
    ])  # fmt: skip
    assert len(await links()) == 3
    # A change within the minute waits; after it, it goes out (once).
    fails = [
        _row("hub", 443, True, 0.9),
        _row(bid, 22, False, None, "timeout"),
        _row(bid, 80, False, None, "x"),
    ]
    await _netcheck(client, hub, a, oversight, fails)
    assert len(await links()) == 3
    await su.execute(
        "UPDATE infra.network_links SET emitted_at = now() - interval '2 minutes' WHERE from_server_id = $1",
        uuid.UUID(aid),
    )
    await _netcheck(client, hub, a, oversight, fails)
    got = await links()
    assert len(got) == 4 and (got[-1]["data"]["port"], got[-1]["data"]["ok"]) == (22, False)
    assert got[-1]["data"]["error_fa"] == "در زمانش جواب نداد"
    since = await su.fetchval(
        "SELECT since FROM infra.network_links WHERE from_server_id = $1 AND port = 22",
        uuid.UUID(aid),
    )
    assert got[-1]["data"]["since"] == since.isoformat()
    # Crossing the slow line is a change too.
    await su.execute(
        "UPDATE infra.network_links SET emitted_at = now() - interval '2 minutes' WHERE from_server_id = $1",
        uuid.UUID(aid),
    )
    await _netcheck(client, hub, a, oversight, [_row("hub", 443, True, 950.0), *fails[1:]])
    got = await links()
    assert len(got) == 5 and got[-1]["data"]["to"] == "hub" and got[-1]["data"]["ms"] == 950.0


# -------------------------------------------------------- §42.2 server.state --
STATE_KEYS = {
    "server", "company", "name", "state", "via", "last_seen_at",
    "prev_state", "since", "reason", "reason_fa", "hub_rtt_ms", "open_jobs",
}  # fmt: skip


async def _poll(client: httpx.AsyncClient, rn: dict[str, Any], via: str, rtt: str) -> None:
    r = await client.get(
        "/api/v1/runners/jobs/next",
        params={"wait": 0, "via": via, "hub_rtt_ms": rtt, "slots": 0},
        headers=rn["h"],
    )
    assert r.status_code in (200, 204), r.text


async def test_server_state_says_since_why_and_how_far(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    a = await pair(client, hub, owner_session, co, "sa")
    b = await pair(client, hub, owner_session, co, "sb")
    aid, bid = a["server"]["id"], b["server"]["id"]

    async def states(sid: str) -> list[dict[str, Any]]:
        return [
            e["data"] for e in await outbox(su, "server.state", "AND payload->>'ref' = $2", sid)
        ]

    first = await states(aid)
    assert [s["state"] for s in first] == ["pending", "online"]
    on = first[-1]
    assert set(on) == STATE_KEYS and on["prev_state"] == "pending" and on["since"]
    assert on["reason"] is None and on["reason_fa"] is None and on["open_jobs"] == 0
    for env in await outbox(su, "server.state", "AND payload->>'ref' = $2", aid):
        clean(env)  # never the hostname or the address
    # The round trip changes tier: told, `slow`; the same tier again: not told.
    await _poll(client, a, "private", "900")
    await _poll(client, a, "private", "950")
    got = await states(aid)
    assert len(got) == 3 and got[-1]["reason"] == "slow" and got[-1]["hub_rtt_ms"] == 900.0
    assert got[-1]["prev_state"] == "online" and got[-1]["reason_fa"]
    # The public fallback.
    await _poll(client, a, "public", "20")
    got = await states(aid)
    assert got[-1]["via"] == "public" and got[-1]["reason"] == "fallback_public"
    # b's runner goes silent: offline since its last contact, `no_poll` (nobody measured since).
    seen = datetime.now(UTC) - timedelta(minutes=10)
    await su.execute(
        "UPDATE infra.servers SET last_seen_at = $2 WHERE id = $1", uuid.UUID(bid), seen
    )
    async with hub.db.tx(await _all(hub)) as tx:
        await SV.sweep(tx)
    off = (await states(bid))[-1]
    assert (off["state"], off["prev_state"], off["reason"]) == ("offline", "online", "no_poll")
    assert datetime.fromisoformat(off["since"]) == seen
    # a still reaches b's ports: the runner stopped, the server is up.
    await _netcheck(client, hub, a, Principal(kind="service", code="oversight", role="service"),
                    [_row("hub", 443, True), _row(bid, 22, True), _row(bid, 443, False, None, "timeout")])  # fmt: skip
    off = (await states(bid))[-1]
    assert off["reason"] == "runner_stopped" and off["prev_state"] == "offline"
    # nobody reaches it any more: unreachable (told once, not again for the same reason).
    bad = [_row("hub", 443, True), _row(bid, 22, False, None, "timeout"), _row(bid, 443, False, None, "timeout"),
           _row(bid, 80, False, None, "timeout")]  # fmt: skip
    for _ in range(2):
        await _netcheck(
            client, hub, a, Principal(kind="service", code="oversight", role="service"), bad
        )
    told = [s["reason"] for s in await states(bid)]
    assert told[-2:] == ["runner_stopped", "server_unreachable"]
    assert (
        SV.rtt_tier(None) is None and SV.rtt_tier(299.9) == "normal" and SV.rtt_tier(300) == "slow"
    )


# ------------------------------------------------------ §42.2 employee.state --
EMP_KEYS = {
    "employee",
    "company",
    "department",
    "state",
    "since",
    "work_ref",
    "root_ref",
    "stuck_fa",
}


def _d(co: dict[str, Any], code: str, state: str, **more: Any) -> dict[str, Any]:
    return {"employee": code, "company": co["code"], "company_id": co["id"], "department": "TECH",
            "state": state, "work_ref": more.get("work_ref"), "root_ref": more.get("root_ref"),
            "stuck_fa": more.get("stuck_fa")}  # fmt: skip


async def test_employee_state_is_coalesced_to_one_per_two_seconds(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    code = f"{co['code']}-TECH-MGR"
    eid = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", code)

    async def step(state: str, **more: Any) -> int:
        async with hub.db.tx([co["id"]]) as tx:
            return await LV.apply(tx, [eid], {eid: _d(co, code, state, **more)})

    async def told() -> list[str]:
        return [
            e["data"]["state"]
            for e in await outbox(su, "employee.state", "AND payload->>'ref' = $2", code)
        ]

    assert await step("idle") == 0  # never seen and idle: nothing to tell
    assert await step("thinking", work_ref="W-1", root_ref="W-0") == 1  # the first: at once
    assert await step("working", work_ref="W-1", root_ref="W-0") == 0  # inside 2 s: waits
    assert await step("idle") == 0
    assert await told() == ["thinking"]
    async with hub.db.tx([co["id"]]) as tx:
        assert await LV.flush(tx) == 0  # the window is still open
        assert await LV.flush(tx, window_s=0) == 1  # (the window passed): the latest, once
        assert await LV.flush(tx, window_s=0) == 0
    assert await told() == ["thinking", "idle"]
    assert (
        await step("stuck", work_ref="W-1", root_ref="W-0", stuck_fa="بودجه تمام شد") == 1
    )  # at once
    assert await step("done") == 1  # at once, too
    assert await step("done") == 0  # no change
    assert await told() == ["thinking", "idle", "stuck", "done"]
    envs = await outbox(su, "employee.state", "AND payload->>'ref' = $2", code)
    for env in envs:
        assert set(env["data"]) == EMP_KEYS and env["company"] == co["code"]
        clean(env)
    assert envs[0]["data"]["work_ref"] == "W-1" and envs[0]["data"]["root_ref"] == "W-0"
    assert envs[2]["data"]["stuck_fa"] == "بودجه تمام شد"
    assert envs[1]["data"]["work_ref"] is None and envs[1]["data"]["since"].endswith("Z")


async def test_employee_state_follows_the_events_that_move_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    code = f"{co['code']}-CEO"
    h = await agent_headers(code)  # a running run in the registry: a model call may be in flight
    r = await client.post(
        "/internal/v1/activity", headers=h, json={"employee": code, "activity": "working"}
    )
    assert r.status_code == 200, r.text
    (env,) = await outbox(su, "employee.state", "AND payload->>'ref' = $2", code)
    assert env["data"]["state"] == "thinking" and env["data"]["company"] == co["code"]
    # The run ends: idle, inside the window (pending), then out once the window passed.
    await su.execute(
        """UPDATE agents.runs SET state = 'done', finished_at = now()
           WHERE employee_id = (SELECT id FROM core.employees WHERE code = $1) AND state = 'running'""",
        code,
    )
    async with hub.db.tx([co["id"]]) as tx:
        await events.emit(tx, co["code"], "run.finished", "r", {"employee": code, "state": "done"})
    assert len(await outbox(su, "employee.state", "AND payload->>'ref' = $2", code)) == 1
    assert await su.fetchval(
        "SELECT pending FROM core.employee_live l JOIN core.employees e ON e.id = l.employee_id WHERE e.code = $1",
        code,
    )
    async with hub.db.tx(await _all(hub)) as tx:
        await LV.flush(tx, window_s=0)
    states = [
        e["data"]["state"]
        for e in await outbox(su, "employee.state", "AND payload->>'ref' = $2", code)
    ]
    assert states == ["thinking", "idle"]
    # What no event says (a lock with open work) the reconcile finds.
    r = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co["code"], "title": "کار", "brief": "شرح"},
    )
    assert r.status_code == 201, r.text
    await su.execute(
        """INSERT INTO control.kill_switches (company_id, state, reason, changed_by_kind, changed_by_code)
           VALUES ($1, 'engaged', 'test', 'owner', 'owner')
           ON CONFLICT (company_id) DO UPDATE SET state = 'engaged'""",
        co["id"],
    )
    try:
        async with hub.db.tx(await _all(hub)) as tx:
            assert await LV.reconcile(tx) >= 1
        last = (await outbox(su, "employee.state", "AND payload->>'ref' = $2", code))[-1]["data"]
        assert last["state"] == "stuck" and last["stuck_fa"] and last["work_ref"]
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", co["id"]
        )


def test_moved_employee_reads_each_event() -> None:
    m = events.moved_employee
    assert m("run.started", "r", {"employee": "AB-CEO"}) == "AB-CEO"
    assert m("activity.changed", "AB-CEO", {"activity": "working"}) == "AB-CEO"
    assert m("server.call", "s", {"actor": {"kind": "agent", "code": "AB-CEO"}}) == "AB-CEO"
    assert m("server.call", "s", {"actor": {"kind": "owner", "code": "owner"}}) is None
    assert m("run.step", "r", {"employee": "AB-CEO"}) is None
    assert m("work.created", "W", {"assignee": "AB-CEO"}) is None


# ---------------------------------------------------------- §42.2 llm.tick --
def _fin(**usage: int) -> dict[str, Any]:
    return {"usage": usage, "cost_usd": "0.01", "equiv_cost_usd": None}


def test_ticks_are_five_second_windows_per_company() -> None:
    t = Ticks()
    assert t.due(1000.0) == []  # nothing when idle
    t.add("AA", "started", {}, now=1000.2)
    t.add("AA", "finished", _fin(input_tokens=10, output_tokens=5, cache_read_tokens=100,
                                 thinking_tokens=3), now=1001.0)  # fmt: skip
    t.add("BB", "finished", _fin(input_tokens=1), now=1004.9)
    t.add("AA", "finished", _fin(output_tokens=7), now=1005.1)  # the next window
    assert t.due(1004.99) == []
    due = t.due(1005.0)
    assert [(c, w.start, w.calls) for c, w in due] == [("AA", 1000, 1), ("BB", 1000, 1)]
    aa = due[0][1]
    assert aa.tokens == {
        "input": 10,
        "output": 5,
        "cache_read": 100,
        "cache_write": 0,
        "thinking": 3,
    }
    assert float(aa.usd) == 0.01
    assert [(c, w.start, w.calls) for c, w in t.due(1010.0)] == [("AA", 1005, 1)]
    assert t.due(1100.0) == []
    data = tick_data("AA", aa, {"tokens": 1000, "cache_read": 500, "usd": 2.5, "in_flight": 2,
                                "budget_usd": 10}, 5)  # fmt: skip
    assert data["day"] == {"tokens": 1000, "effective_tokens": 550, "equiv_usd": "2.500000",
                           "budget_usd": "10.000000", "pct": 25.0}  # fmt: skip
    assert data["equiv_usd"] == "0.010000"  # money: a decimal string of 6 places (§1)
    assert data["in_flight"] == 2 and data["window_s"] == 5 and data["calls"] == 1
    assert tick_data("AA", aa, None, 5)["day"]["budget_usd"] is None
    assert tick_data("AA", aa, None, 5)["day"]["pct"] is None


async def test_the_bridge_ticks_with_the_day_from_the_ledger(
    wk: dict[str, Any], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    now = datetime.now(UTC)
    for status, tokens in (("ok", (100, 50, 1000, 20)), ("running", (0, 0, 0, 0))):
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, task_class,
                   priority, caller, status, input_tokens, output_tokens, cache_read_tokens,
                   cache_write_tokens, cost_usd, equiv_cost_usd)
               VALUES ($1, $2::timestamptz, CASE WHEN $3::text = 'ok' THEN $2::timestamptz END, $4, 'X-CEO',
                       'agent_step', 2, 'test', $3,
                       $5, $6, $7, $8, 0.5, 0.25)""",
            uuid.uuid4(), now, status, co["id"], *tokens,
        )  # fmt: skip
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, usd_limit)
           VALUES ($1, 'company', $2, 'day', 3)""",
        co["id"],
        co["code"],
    )
    bridge = Bridge(wk["hub"])
    t0 = time.time()
    bridge.ticks.add(co["code"], "finished", {"usage": {"input_tokens": 100, "output_tokens": 50,
                                                         "cache_read_tokens": 1000, "cache_write_tokens": 20},
                                               "cost_usd": "0.5", "equiv_cost_usd": "0.25"}, now=t0)  # fmt: skip
    assert await bridge.flush_ticks(now=t0) == 0  # the window is still open
    assert await bridge.flush_ticks(now=t0 + 5) == 1
    msg = await wk["hub"].bus.js.get_last_msg("HQ_CORE", f"hq.core.{co['code']}.llm.tick")
    env = json.loads(msg.data)
    assert env["type"] == "llm.tick" and env["company"] == co["code"]
    d = env["data"]
    assert set(d) == {"company", "window_s", "calls", "in_flight", "tokens", "equiv_usd", "day"}
    assert d["calls"] == 1 and d["in_flight"] == 1 and d["equiv_usd"] == "0.750000"
    assert d["tokens"] == {
        "input": 100,
        "output": 50,
        "cache_read": 1000,
        "cache_write": 20,
        "thinking": 0,
    }
    assert d["day"] == {"tokens": 1170, "effective_tokens": 270, "equiv_usd": "1.500000",
                        "budget_usd": "3.000000", "pct": 50.0}  # fmt: skip
    assert await bridge.flush_ticks(now=t0 + 60) == 0  # idle: nothing
    clean(env)


# ------------------------------------------------------- §42.3 /live/summary --
@dataclass(frozen=True)
class Co:
    id: Any
    code: str
    kind: str = "company"
    status: str = "active"
    name_fa: str | None = None


def _raw(**over: Any) -> dict[str, Any]:
    return {"employees": [], "sessions": [], "owner": {"approvals": 0, "urgent": 0, "budget_usd": None},
            "servers": {}, "tokens": {}, "locks": [], "last": {}, **over}  # fmt: skip


def test_summary_with_no_company() -> None:
    now = datetime.now(UTC)
    s = LV.assemble(_raw(), [Co(1, "HQ", kind="holding")], None, now)
    assert s.companies == [] and s.seq is None
    assert s.people.total == 0 and s.tokens.budget_usd is None and s.tokens.today == 0
    assert s.control.holding is False and s.control.companies_locked == []


def test_summary_with_one_and_several_companies() -> None:
    now = datetime.now(UTC)
    one = LV.assemble(
        _raw(
            employees=[{"company_id": 2, "state": "thinking"}, {"company_id": 2, "state": "idle"}]
        ),
        [Co(1, "HQ", kind="holding"), Co(2, "AA", name_fa="آ")],
        7,
        now,
    )
    assert one.seq == 7 and [c.code for c in one.companies] == ["AA"]
    (aa,) = one.companies
    assert (aa.working, aa.total, aa.state, aa.name_fa, aa.last_event_at) == (
        1,
        2,
        "busy",
        "آ",
        None,
    )
    cos = [Co(1, "HQ", kind="holding"), *(Co(i, f"C{i}") for i in range(2, 9)),
           Co(9, "ZZ", status="archived")]  # fmt: skip
    last = now - timedelta(minutes=3)
    raw = _raw(
        employees=[{"company_id": 2, "state": "working"}, {"company_id": 3, "state": "stuck"},
                   {"company_id": 4, "state": "waiting"}, {"company_id": 1, "state": "done"}],
        sessions=[{"badge": "moving", "company": "C2", "n": 2}, {"badge": "your_turn", "company": "C3", "n": 1},
                  {"badge": "ready", "company": None, "n": 1}],
        owner={"approvals": 3, "urgent": 1, "budget_usd": 20},
        servers={2: {"online": 1, "offline": 1, "total": 3}, 5: {"online": 2, "offline": 0, "total": 2}},
        tokens={2: {"tokens": 1000, "cache_read": 500, "usd": 1.25, "last_min": 40},
                1: {"tokens": 10, "cache_read": 0, "usd": 0.01, "last_min": 0}},
        locks=[{"code": "C4", "kind": "company"}],
        last={"C2": last},
    )  # fmt: skip
    s = LV.assemble(raw, cos, 99, now)
    assert [c.code for c in s.companies] == [f"C{i}" for i in range(2, 9)]  # no hub, no archived
    by = {c.code: c for c in s.companies}
    assert (by["C2"].state, by["C3"].state, by["C4"].state, by["C5"].state) == (
        "busy",
        "stuck",
        "locked",
        "ok",
    )
    assert (
        by["C2"].sessions_open == 2 and by["C3"].sessions_open == 1 and by["C5"].sessions_open == 0
    )
    c2 = by["C2"]
    assert (c2.servers_online, c2.servers_total, c2.spend_today_usd) == (1, 3, Decimal("1.25"))
    assert str(c2.spend_today_usd) == "1.250000" and str(by["C5"].spend_today_usd) == "0.000000"
    assert by["C2"].last_event_at == last and by["C3"].last_event_at is None
    assert s.people.model_dump() == {
        "working": 1,
        "thinking": 0,
        "waiting": 1,
        "stuck": 1,
        "total": 4,
    }
    assert s.sessions.model_dump() == {"moving": 2, "your_turn": 1, "stuck": 0, "ready": 1}
    assert s.servers.model_dump() == {"online": 3, "offline": 1, "total": 5}
    assert s.tokens.model_dump(mode="json") == {"today": 1010, "effective_today": 560, "per_min": 40,
                                                "equiv_usd_today": "1.260000", "budget_usd": "20.000000"}  # fmt: skip
    assert s.control.model_dump() == {"holding": False, "companies_locked": ["C4"]}
    held = LV.assemble(_raw(locks=[{"code": "HQ", "kind": "holding"}]), cos, 1, now)
    assert held.control.holding and {c.state for c in held.companies} == {"locked"}


class Counting:
    """A transaction that counts its statements (the summary's cost)."""

    def __init__(self, tx: Any) -> None:
        self.tx, self.n = tx, 0

    def __getattr__(self, name: str) -> Any:
        fn = getattr(self.tx, name)

        async def call(*args: Any, **kw: Any) -> Any:
            self.n += 1
            return await fn(*args, **kw)

        return call


async def test_live_summary_route_shape_cost_and_resume(
    app: Any,
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    relay: None,
) -> None:
    co = await new_company()
    r = await client.get("/api/v1/live/summary", headers=owner)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"seq", "at", "people", "sessions", "approvals", "urgent_unread", "servers",
                         "tokens", "control", "companies"}  # fmt: skip
    assert isinstance(body["seq"], int)
    mine = next(c for c in body["companies"] if c["code"] == co["code"])
    assert set(mine) == {"code", "name_fa", "working", "total", "sessions_open", "servers_online",
                         "servers_total", "spend_today_usd", "last_event_at", "state"}  # fmt: skip
    assert mine["total"] > 0 and mine["state"] == "ok" and mine["spend_today_usd"] == "0.000000"
    assert body["tokens"]["budget_usd"] is None or isinstance(body["tokens"]["budget_usd"], str)
    holding = (await hub.companies.holding()).code
    assert holding not in {c["code"] for c in body["companies"]}
    clean(body)
    assert (await client.get("/api/v1/live/summary")).status_code == 401
    # The same handful of statements whatever the number of companies.
    counts = []
    for _ in range(2):
        async with hub.db.tx(await _all(hub)) as tx:
            c = Counting(tx)
            await LV.summary(c, await hub.companies.all(), None)  # type: ignore[arg-type]
            counts.append(c.n)
        await new_company()
        await new_company()
    assert counts[0] == counts[1] == 8
    # Resume right after `seq`: the next event is the first one the stream sends.
    seq = (await client.get("/api/v1/live/summary", headers=owner)).json()["seq"]
    await client.post("/api/v1/work", headers={**owner, **idem()},
                      json={"company": co["code"], "title": "پس از خلاصه", "brief": "ب"})  # fmt: skip

    async def first() -> dict[str, Any]:
        async with (
            httpx.AsyncClient(base_url=url, timeout=20) as c,
            c.stream(
                "GET",
                "/api/v1/stream",
                headers={**owner, "Last-Event-ID": str(seq)},
                params={"topics": "all"},
            ) as resp,  # fmt: skip
        ):
            ev: dict[str, Any] = {}
            async for line in resp.aiter_lines():
                if line.startswith("id: "):
                    ev["id"] = int(line[4:])
                elif line.startswith("data: "):
                    ev["data"] = json.loads(line[6:])
                    return ev
        raise AssertionError("no event")

    async def published() -> bool:
        return not await su.fetchval(
            "SELECT count(*) FROM core.outbox WHERE published_at IS NULL AND subject LIKE $1",
            f"hq.core.{co['code']}.%",
        )

    await wait_for(published, 20)
    async with serve(app) as url:
        ev = await asyncio.wait_for(first(), 20)
    assert ev["id"] == seq + 1


async def test_no_secret_hostname_or_ip_in_any_new_payload(su: Any) -> None:
    """Every event of the five new types and server.state written by this run's tests."""
    for type_ in ("holding.flow", "network.link", "employee.state", "server.state"):
        for env in await outbox(su, type_, "AND (payload->>'at') > $2",
                                (datetime.now(UTC) - timedelta(hours=2)).isoformat()):  # fmt: skip
            clean(env)
