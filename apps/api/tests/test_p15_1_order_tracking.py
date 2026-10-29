"""Prompt 15.1: tracking the owner's orders (contract §4 ⟨1.7.4⟩).

`GET /work?created_by=`, a work's children two levels down with their
progress and deliverables, `GET /work/{id}/tree-events` (time order, depth 2,
run steps as summaries only, owner only), `GET /deliverables?work=`, and the
order's root on every work.* and deliverable.created stream event."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_org_work import hire


async def _tree(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], co: str
) -> dict[str, Any]:
    """An owner's order to the CEO, delegated to the TECH manager and on to
    an employee, who reports progress and delivers."""
    h = owner_session["headers"]
    emp = await hire(hub, client, owner_session, co)
    root = (
        await client.post(
            "/api/v1/work",
            headers={**h, **idem()},
            json={"company": co, "title": "فرمان پیگیری", "brief": "x", "priority": "P2"},
        )
    ).json()
    ceo, mgr = await agent_headers(f"{co}-CEO"), await agent_headers(f"{co}-TECH-MGR")
    await client.post(f"/internal/v1/work/{root['id']}/accept", headers=ceo)
    child = (
        await client.post(
            f"/internal/v1/work/{root['id']}/delegate",
            headers=ceo,
            json={"to": f"{co}-TECH-MGR", "title": "بخش فنی"},
        )
    ).json()
    grand = (
        await client.post(
            f"/internal/v1/work/{child['id']}/delegate",
            headers=mgr,
            json={"to": emp, "title": "پیاده‌سازی"},
        )
    ).json()
    me = await agent_headers(emp)
    r = await client.post(
        f"/internal/v1/work/{grand['id']}/progress", headers=me, json={"note": "نیمه", "pct": 40}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/internal/v1/work/{grand['id']}/deliver",
        headers={**me, **idem()},
        json={
            "title": "تحویل",
            "summary": "s",
            "body": "متن",
            "produced_with": {
                "connection": "claude-max",
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
        },
    )
    assert r.status_code == 200, r.text
    return {
        "root": root,
        "child": child,
        "grand": grand,
        "emp": emp,
        "deliverable": r.json()["deliverable"],
    }


@pytest.mark.usefixtures("hiring_open")  # the tree's employee is hired (§18.11)
async def test_orders_children_tree_and_deliverables(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    t = await _tree(client, hub, owner_session, co)
    root, child, grand = t["root"], t["child"], t["grand"]

    # §1.1 created_by: the owner's orders, or one agent's
    mine = (
        await client.get("/api/v1/work", headers=h, params={"created_by": "owner", "company": co})
    ).json()["items"]
    assert [w["ref"] for w in mine] == [root["ref"]]
    ceo = (
        await client.get(
            "/api/v1/work", headers=h, params={"created_by": f"{co}-CEO", "company": co}
        )
    ).json()["items"]
    assert [w["ref"] for w in ceo] == [child["ref"]]
    bad = await client.get("/api/v1/work", headers=h, params={"created_by": "anyone; drop"})
    assert bad.status_code == 422

    # §1.2 children, two levels down, with progress and deliverable refs
    d = (await client.get(f"/api/v1/work/{root['id']}", headers=h)).json()
    assert [c["ref"] for c in d["children"]] == [child["ref"]]
    c1 = d["children"][0]
    assert c1["title"] == "بخش فنی" and c1["assignee"]["code"] == f"{co}-TECH-MGR"
    assert c1["progress"] is None and c1["deliverable_refs"] == [] and c1["updated_at"]
    g = c1["children"][0]
    assert g["ref"] == grand["ref"] and g["progress"] == 0.4 and g["status"] == "delivered"
    assert g["deliverable_refs"] == [t["deliverable"]] and g["children"] == []
    gd = (await client.get(f"/api/v1/work/{grand['id']}", headers=h)).json()
    assert gd["deliverable_refs"] == [t["deliverable"]] and len(gd["deliverable_ids"]) == 1

    # §1.4 deliverables of one work, by id or by ref
    for key in (grand["id"], grand["ref"]):
        items = (await client.get("/api/v1/deliverables", headers=h, params={"work": key})).json()[
            "items"
        ]
        assert [x["ref"] for x in items] == [t["deliverable"]], key
    none = (await client.get("/api/v1/deliverables", headers=h, params={"work": root["id"]})).json()
    assert none["items"] == []
    assert (
        await client.get("/api/v1/deliverables", headers=h, params={"work": "x"})
    ).status_code == 422

    # §1.5 the root on the stream's work.* and deliverable.created events
    rows = await su.fetch(
        "SELECT payload FROM core.outbox WHERE payload->>'type' IN ('work.updated', 'work.created',"
        " 'work.delegated', 'deliverable.created') AND payload->>'ref' = ANY($1::text[])",
        [child["ref"], grand["ref"], t["deliverable"]],
    )
    payloads = [
        json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"] for r in rows
    ]
    assert payloads and any(p["type"] == "deliverable.created" for p in payloads)
    for p in payloads:
        assert p["data"]["root_id"] == root["id"] and p["data"]["root_ref"] == root["ref"], p


@pytest.mark.usefixtures("hiring_open")
async def test_tree_events_in_time_order_with_run_steps_as_summaries(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    t = await _tree(client, hub, owner_session, co["code"])
    root, grand = t["root"], t["grand"]
    # A run of the employee on the grandchild, with one step whose action
    # carries a payload that must never come back.
    run = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, state, started_at,
               finished_at)
           SELECT $1, e.id, $2, 'work', 'done', now(), now() FROM core.employees e WHERE e.code = $3
           RETURNING id""",
        co["id"],
        grand["id"],
        t["emp"],
    )
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, summary_fa, actions)
           VALUES ($1, $2, 1, 'جست‌وجوی منابع', $3::jsonb)""",
        run,
        co["id"],
        json.dumps(
            [{"tool": "web.search", "class": "A0", "outcome": "ok", "args": {"q": "secret query"}}]
        ),
    )
    # Another order elsewhere stays out of this tree.
    await client.post(
        "/api/v1/work", headers={**h, **idem()}, json={"company": co["code"], "title": "دیگری"}
    )

    full = (
        await client.get(f"/api/v1/work/{root['id']}/tree-events", headers=h, params={"limit": 200})
    ).json()
    items = full["items"]
    assert full["next_cursor"] is None
    times = [x["at"] for x in items]
    assert times == sorted(times)
    refs = {x["work_ref"] for x in items}
    assert refs == {root["ref"], t["child"]["ref"], grand["ref"]}
    assert {x["depth"] for x in items} == {0, 1, 2}
    kinds = [x["kind"] for x in items if x["work_ref"] == grand["ref"]]
    assert kinds[0] == "work.created" and "work.progress" in kinds and "work.delivered" in kinds
    step = next(x for x in items if x["kind"] == "run.step")
    assert step["work_ref"] == grand["ref"] and step["actor_code"] == t["emp"]
    assert step["data"]["summary_fa"] == "جست‌وجوی منابع" and step["data"]["n"] == 1
    assert step["data"]["actions"] == [{"tool": "web.search", "class": "A0", "outcome": "ok"}]
    assert "secret query" not in json.dumps(full, ensure_ascii=False)

    # The same events, page by page
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        page = (
            await client.get(f"/api/v1/work/{root['id']}/tree-events", headers=h, params=params)
        ).json()
        seen += [x["id"] for x in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [x["id"] for x in items]

    # A child's tree holds only its own branch (depth 2 below it at most)
    sub = (await client.get(f"/api/v1/work/{grand['id']}/tree-events", headers=h)).json()["items"]
    assert {x["work_ref"] for x in sub} == {grand["ref"]}

    # Owner only: an agent's token is refused (the owner's API)
    agent = await agent_headers(f"{co['code']}-CEO")
    r = await client.get(f"/api/v1/work/{root['id']}/tree-events", headers=agent)
    assert r.status_code in (401, 403)
    assert (
        await client.get(
            f"/api/v1/work/{root['id']}/tree-events", headers=h, params={"cursor": "x"}
        )
    ).status_code == 422
