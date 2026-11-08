"""Company links and the owner's canvas (contract §35.6, §35.7), the owner, 2026-11-06: companies
are linked to each other and all to the hub, and he shapes the links.

- The owner's routes: GET /links (the canvas), POST /links, PATCH /links/{id} (off, never deleted),
  PUT /canvas/nodes/{code}; Persian errors; every write audited (A1) and told to the stream.
- The canvas: a node for every active company and the holding, one plain line each, the works open
  along each link.
- Honoured: the secretary's preview suggests collaborators along fitting `on` links (only in the
  preview); a cross-company request along an `on` link is accepted for a manager only while
  `links_enforced` is on, and the old rule (CEO to CEO) stays otherwise; company.state lists them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from hq_api import events as EV
from hq_api.domain import humanize
from hq_api.domain import links as L
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model, post_order, preview, words  # noqa: F401 - the fixture


@pytest.fixture
async def enforced(su: Any) -> AsyncIterator[None]:
    """`links_enforced` on for a test; off again afterwards (it is off for every other test)."""
    await su.execute("UPDATE owner.settings SET links_enforced = true WHERE id = 1")
    yield
    await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")


async def link(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    a: str,
    b: str,
    kind: str = "serves",
    **extra: Any,
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/links", headers=owner, json={"from": a, "to": b, "kind": kind, **extra}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def canvas(client: httpx.AsyncClient, owner: dict[str, str]) -> dict[str, Any]:
    r = await client.get("/api/v1/links", headers=owner)
    assert r.status_code == 200, r.text
    return dict(r.json())


# ----------------------------------------------------------------- routes --
async def test_the_owner_draws_links_and_turns_them_off_but_never_deletes(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    made = await link(client, owner, a, b, "publishes", purpose_fa="  پست‌های   ما را منتشر کن ")
    assert made["from"] == a and made["to"] == b and made["kind"] == "publishes"
    assert made["purpose_fa"] == "پست‌های ما را منتشر کن"  # spaces tidied
    assert made["state"] == "on" and made["open_works"] == 0 and made["id"] and made["updated_at"]
    # the same link again: 409, in Persian, and the way out
    r = await client.post(
        "/api/v1/links", headers=owner, json={"from": a, "to": b, "kind": "publishes"}
    )
    assert r.status_code == 409 and r.json()["message_fa"], r.text
    # another kind between the same two is another link
    other = await link(client, owner, a, b, "feeds")
    assert other["id"] != made["id"]
    # off, then on again, then a new purpose and kind
    r = await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "off"})
    assert r.status_code == 200 and r.json()["state"] == "off", r.text
    r = await client.post(
        "/api/v1/links", headers=owner, json={"from": a, "to": b, "kind": "publishes"}
    )
    assert r.status_code == 409 and "خاموش" in r.json()["message_fa"]
    r = await client.patch(
        f"/api/v1/links/{made['id']}",
        headers=owner,
        json={"state": "on", "purpose_fa": "تازه", "kind": "sells"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["purpose_fa"], r.json()["kind"]) == ("on", "تازه", "sells")
    assert r.json()["updated_at"] >= made["updated_at"]
    # a kind that is taken between the same two
    r = await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"kind": "feeds"})
    assert r.status_code == 409 and r.json()["message_fa"]
    # nothing to change, an unknown link, an unknown kind
    r = await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={})
    assert r.status_code == 422 and r.json()["message_fa"]
    r = await client.patch(
        "/api/v1/links/00000000-0000-0000-0000-000000000001", headers=owner, json={"state": "off"}
    )
    assert r.status_code == 404
    r = await client.post("/api/v1/links", headers=owner, json={"from": a, "to": b, "kind": "owns"})
    assert r.status_code == 422
    # it appears on the canvas, off links too
    c = await canvas(client, owner)
    ids = {x["id"] for x in c["links"]}
    assert {made["id"], other["id"]} <= ids
    # nothing is deleted: the database refuses
    with pytest.raises(Exception, match=r".+"):
        await su.execute("DELETE FROM core.company_links WHERE id = $1", made["id"])
    # every write was audited (A1)
    n = await su.fetchval(
        """SELECT count(*) FROM audit.entries WHERE action = 'link.write' AND action_class = 'A1'
           AND target_ref = $1""",
        made["id"],
    )
    assert n == 3  # made, off, on-and-changed (the two refusals wrote nothing)


async def test_a_link_must_be_between_two_real_companies_and_not_the_hub(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
) -> None:
    a = (await new_company())["code"]
    holding = (await hub.companies.holding()).code
    for frm, to, _field in ((a, a, "to"), (a, "NOPEX", "company"), (a, holding, "from")):
        r = await client.post(
            "/api/v1/links", headers=owner, json={"from": frm, "to": to, "kind": "serves"}
        )
        assert r.status_code == 422 and r.json()["message_fa"], (frm, to, r.text)
    # the hub is linked to every company already: no row for it
    c = await canvas(client, owner)
    assert not [x for x in c["links"] if holding in (x["from"], x["to"])]
    # the owner only
    r = await client.get("/api/v1/links")
    assert r.status_code == 401
    r = await client.post("/api/v1/links", json={"from": a, "to": a, "kind": "serves"})
    assert r.status_code == 401
    r = await client.put("/api/v1/canvas/nodes/" + a, json={"x": 0.5, "y": 0.5})
    assert r.status_code == 401


async def test_the_owner_places_nodes_on_the_canvas(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a = (await new_company())["code"]
    node = next(n for n in (await canvas(client, owner))["nodes"] if n["code"] == a)
    assert node["x"] is None and node["y"] is None  # not placed yet
    r = await client.put(f"/api/v1/canvas/nodes/{a}", headers=owner, json={"x": 0.25, "y": 0.75})
    assert r.status_code == 200 and r.json() == {"code": a, "x": 0.25, "y": 0.75}, r.text
    r = await client.put(f"/api/v1/canvas/nodes/{a}", headers=owner, json={"x": 1, "y": 0})
    assert r.status_code == 200
    node = next(n for n in (await canvas(client, owner))["nodes"] if n["code"] == a)
    assert (node["x"], node["y"]) == (1.0, 0.0)
    for bad in ({"x": 1.2, "y": 0.5}, {"x": 0.5, "y": -0.1}, {"x": 0.5}):
        r = await client.put(f"/api/v1/canvas/nodes/{a}", headers=owner, json=bad)
        assert r.status_code == 422, bad
    r = await client.put("/api/v1/canvas/nodes/NOPEX", headers=owner, json={"x": 0.5, "y": 0.5})
    assert r.status_code == 404 and r.json()["message_fa"]
    assert (
        await su.fetchval(
            """SELECT count(*) FROM audit.entries WHERE action = 'canvas.place' AND target_ref = $1""",
            a,
        )
        == 2
    )
    # the stream: topic holding carries links.* and ⟨1.24⟩ §42.1 holding.*
    assert EV.TOPICS["holding"] == ("links.", "holding.")
    assert (
        await su.fetchval(
            """SELECT count(*) FROM core.outbox WHERE subject LIKE '%.links.updated'
               AND payload->'data'->>'node' = $1""",
            a,
        )
        == 2
    )


# ----------------------------------------------------------------- canvas --
async def test_the_canvas_has_every_company_the_hub_and_plain_lines(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    holding = (await hub.companies.holding()).code
    made = await link(client, owner, a, b, "feeds", purpose_fa="آمار بده")
    c = await canvas(client, owner)
    assert set(c) == {"nodes", "links"}
    nodes = {n["code"]: n for n in c["nodes"]}
    assert nodes[holding]["kind"] == "holding" and nodes[a]["kind"] == "company" and b in nodes
    assert c["nodes"][0]["code"] == holding  # the hub first
    for n in (nodes[holding], nodes[a], nodes[b]):
        assert set(n) == {"code", "name_fa", "kind", "x", "y", "line_fa", "open_sessions"}
        assert n["name_fa"] and n["line_fa"] and isinstance(n["open_sessions"], int)
        assert humanize.check(n["line_fa"]) == [], n["line_fa"]
    assert nodes[a]["line_fa"] == "کار بازی ندارد"
    # a work of A asks B (the way the dispatcher does): the link counts it, both nodes say so
    wa = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
           SELECT id, 'one_off', 'root', 'owner', 'owner' FROM core.companies WHERE code = $1
           RETURNING id""",
        a,
    )
    wb = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code,
               requested_by_work_id)
           SELECT id, 'one_off', 'asked', 'owner', 'owner', $2 FROM core.companies WHERE code = $1
           RETURNING id""",
        b,
        wa,
    )
    c = await canvas(client, owner)
    [mine] = [x for x in c["links"] if x["id"] == made["id"]]
    assert mine["open_works"] == 1
    nodes = {n["code"]: n for n in c["nodes"]}
    assert nodes[a]["line_fa"] == "۱ کار باز" and nodes[b]["line_fa"] == "۱ کار باز"
    # the owner's open order whose work is in A counts as an open session of A
    ref = await su.fetchval("SELECT ref FROM work.work WHERE id = $1", wa)
    order = await su.fetchval(
        """INSERT INTO owner.orders (company_id, text, source)
           SELECT id, 'x', 'text' FROM core.companies WHERE code = $1 RETURNING id""",
        holding,
    )
    await su.execute(
        """INSERT INTO owner.order_reports (company_id, order_id, ref, work_refs)
           SELECT o.company_id, o.id, o.ref, ARRAY[$2::text] FROM owner.orders o WHERE o.id = $1""",
        order,
        ref,
    )
    nodes = {n["code"]: n for n in (await canvas(client, owner))["nodes"]}
    assert nodes[a]["open_sessions"] == 1 and nodes[b]["open_sessions"] == 0
    assert "فرمان شما" in nodes[a]["line_fa"] and humanize.check(nodes[a]["line_fa"]) == []
    # a finished work no longer counts
    await su.execute("UPDATE work.work SET status = 'cancelled' WHERE id = $1", wb)
    [mine] = [x for x in (await canvas(client, owner))["links"] if x["id"] == made["id"]]
    assert mine["open_works"] == 0


async def test_linked_and_links_of_see_only_on_links_either_way(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
) -> None:
    a, b, c = await new_company(), await new_company(), await new_company()
    made = await link(client, owner, a["code"], b["code"], "supports", purpose_fa="پشتیبان")
    async with hub.db.tx([a["id"]]) as tx:  # an agent's scope: its own company only
        assert await L.linked(tx, a["id"], b["id"]) and await L.linked(tx, b["id"], a["id"])
        assert not await L.linked(tx, a["id"], c["id"])
        [mine] = await L.links_of(tx, a["id"])
        assert mine == {
            "company": b["code"],
            "name_fa": f"شرکت آزمایشی {b['code']}",
            "kind": "supports",
            "purpose_fa": "پشتیبان",
            "outgoing": True,
        }
        [theirs] = await L.links_of(tx, b["id"])
        assert theirs["company"] == a["code"] and theirs["outgoing"] is False
    await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "off"})
    async with hub.db.tx([a["id"]]) as tx:
        assert not await L.linked(tx, a["id"], b["id"]) and await L.links_of(tx, a["id"]) == []
    assert L.kind_for("reel", None) == "publishes" and L.kind_for("report", None) == "feeds"
    assert L.kind_for("plan", "SALES") == "sells" and L.kind_for("other", "SUPPORT") == "supports"
    assert L.kind_for("other", None) == "serves" and L.fa(1205) == "۱۲۰۵"


# --------------------------------------------------------- the preview --
async def test_the_preview_suggests_collaborators_along_fitting_links_only(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    a, b, c, d = [(await new_company())["code"] for _ in range(4)]
    text = f"برای {a} سه پست آموزشی بساز {words()}"
    plain = await preview(client, owner, text)
    assert plain["companies"] == [a] and plain["collaborators"] == []
    await link(client, owner, b, a, "publishes", purpose_fa="منتشر کن")  # into A: either way counts
    feeds = await link(client, owner, a, c, "feeds")  # a data link does not fit posts
    off = await link(client, owner, a, d, "publishes")
    await client.patch(f"/api/v1/links/{off['id']}", headers=owner, json={"state": "off"})
    got = await preview(client, owner, text)
    assert got["companies"] == [a] and got["collaborators"] == [b], got
    assert b in got["preview_fa"] and c not in got["preview_fa"] and d not in got["preview_fa"]
    assert "پیشنهاد" in got["why_fa"] and humanize.check(got["preview_fa"]) == []
    # a report fits `feeds`
    report = await preview(client, owner, f"برای {a} گزارش هفتگی بساز {words()}")
    assert report["output_kind"] == "report" and report["collaborators"] == [c], report
    assert feeds["id"]
    # only a suggestion: an order sent without the route is not widened ...
    out = await post_order(client, owner, f"برای {a} سه پست آموزشی بساز {words()}")
    assert [r["company"] for r in out["routes"]] == [a]
    # ... and the route the owner sends back is followed exactly
    sent = dict(got)
    sent["collaborators"] = []
    out = await post_order(client, owner, text, route=sent)
    assert [r["company"] for r in out["routes"]] == [a]
    out = await post_order(client, owner, text, route=got)
    assert [r["company"] for r in out["routes"]] == [a, b]


# ----------------------------------------------------- the policy (agents) --
async def test_a_manager_asks_anywhere_while_off_and_along_an_on_link_while_enforced(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b, c = (
        (await new_company())["code"],
        (await new_company())["code"],
        (await new_company())["code"],
    )
    made = await link(client, owner, a, b, "serves")
    mgr = await agent_headers(f"{a}-GROWTH-MGR")
    ceo = await agent_headers(f"{a}-CEO")

    async def ask(headers: dict[str, str], co: str, **extra: Any) -> httpx.Response:
        return await client.post(
            "/internal/v1/work",
            headers={**headers, **idem()},
            json={"company": co, "title": "کمک", "brief": "x", **extra},
        )

    # off (the default): every company reaches every other (audit 2026-11-08 B4, as linked.read):
    # a CEO or a manager asks the other company's CEO or a department's manager
    assert await su.fetchval("SELECT links_enforced FROM owner.settings WHERE id = 1") is False
    assert (await ask(mgr, b)).status_code == 201
    assert (await ask(mgr, c)).status_code == 201
    assert (await ask(ceo, b)).status_code == 201  # CEO to CEO, as ever
    assert (await ask(ceo, b, department="TECH")).status_code == 201
    assert (await ask(ceo, b, to=f"{b}-TECH-MGR")).status_code == 403  # never a named person

    # on: along the link a manager, and a CEO to a department's manager
    await su.execute("UPDATE owner.settings SET links_enforced = true WHERE id = 1")
    try:
        r = await ask(mgr, b)
        assert r.status_code == 201, r.text
        assert (
            r.json()["work"]["company"] == b and r.json()["work"]["assignee"]["code"] == f"{b}-CEO"
        )
        assert r.json()["work"]["status"] == "queued"  # accepted at once: no extra gate
        r = await ask(ceo, b, department="TECH")
        assert r.status_code == 201, r.text
        assert r.json()["work"]["assignee"]["code"] == f"{b}-TECH-MGR"
        # never a named person, even along a link
        assert (await ask(ceo, b, to=f"{b}-TECH-MGR")).status_code == 403
        # no link, or an `off` one: as before
        assert (await ask(mgr, c)).status_code == 403
        assert (await ask(ceo, c)).status_code == 201
        assert (await ask(ceo, c, department="TECH")).status_code == 403
        await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "off"})
        assert (await ask(mgr, b)).status_code == 403
        assert (await ask(ceo, b, department="TECH")).status_code == 403
        assert (await ask(ceo, b)).status_code == 201
        # the other end is linked too (either direction)
        await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "on"})
        back = await agent_headers(f"{b}-GROWTH-MGR")
        assert (await ask(back, a)).status_code == 201
    finally:
        await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")
    assert (await ask(mgr, c)).status_code == 201  # off again: open again
    # the audit says which requests went along a link
    n = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'work.create' AND summary LIKE '%along a link%'"
    )
    assert n >= 3


async def test_the_owner_turns_enforcement_on_in_his_settings(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    r = await client.get("/api/v1/owner/settings", headers=owner)
    assert r.status_code == 200 and r.json()["links_enforced"] is False, r.text
    version = r.headers["ETag"].strip('"')
    try:
        r = await client.put(
            "/api/v1/owner/settings",
            headers={**owner, "If-Match": f'"{version}"'},
            json={"links_enforced": True},
        )
        assert r.status_code == 200 and r.json()["links_enforced"] is True, r.text
        assert await su.fetchval("SELECT links_enforced FROM owner.settings WHERE id = 1") is True
        # a later change that does not name it keeps it
        r = await client.put(
            "/api/v1/owner/settings",
            headers={**owner, "If-Match": r.headers["ETag"]},
            json={"digest_minutes": 30},
        )
        assert r.status_code == 200 and r.json()["links_enforced"] is True
    finally:
        await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")


# --------------------------------------------------------- company.state --
async def test_company_state_lists_the_companys_on_links(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    a, b, c = (
        (await new_company())["code"],
        (await new_company())["code"],
        (await new_company())["code"],
    )
    ceo = await agent_headers(f"{a}-CEO")
    state = (await client.get("/internal/v1/company/state", headers=ceo)).json()
    assert state["links"] == []
    await link(client, owner, a, b, "sells", purpose_fa="بفروش")
    gone = await link(client, owner, c, a, "serves")
    await client.patch(f"/api/v1/links/{gone['id']}", headers=owner, json={"state": "off"})
    state = (await client.get("/internal/v1/company/state", headers=ceo)).json()
    assert state["links"] == [
        {
            "company": b,
            "name_fa": f"شرکت آزمایشی {b}",
            "kind": "sells",
            "purpose_fa": "بفروش",
            "outgoing": True,
        }
    ]
    # the other end sees it too, with the direction turned
    other = await agent_headers(f"{b}-CEO")
    state = (await client.get("/internal/v1/company/state", headers=other)).json()
    assert [(x["company"], x["kind"], x["outgoing"]) for x in state["links"]] == [
        (a, "sells", False)
    ]
