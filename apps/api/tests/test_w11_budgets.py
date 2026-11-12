"""W11 F (2026-11-08): no token budget stops an owner's order. The owner, on F-0011: «کلا بودجه رو
سقفشو بردار … همش برای یه کاری باید کار بخوابه، روشم میزنم عمل نمیکنه».

- a work of an owner's order, its collaborators' works, a child delegated or requested under it:
  no token budget (NULL); the secretary's estimate is a figure for the preview, never a cap;
- the `budget` blocker is never raised for an order's work; the runner never parks such a work;
- `POST /orders/{ref}/fix {action: budget.add}` without `tokens` (the apps send none) lifts the
  work's cap and wakes it (200, a step); with tokens the old behaviour;
- `python -m hq_api.ops_uncap_orders`: the open works of open orders uncapped once, holders woken;
- a card's «تصمیم درباره‌ی D-…» item carries no budget.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx

from hq_api import ops_uncap_orders as UNCAP
from hq_api.agents import runner
from hq_api.domain import decisions as D
from hq_api.domain import order_report as OR
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_routing_orders import (  # noqa: F401
    _blocked_run,
    all_tx,
    envelope,
    make_order,
    report,
)
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import refuse_queued


async def budget_of(su: Any, ref: str) -> Any:
    return await su.fetchval("SELECT budget_tokens FROM work.work WHERE ref = $1", ref)


async def test_an_owners_order_and_everything_under_it_has_no_token_budget(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    other = (await new_company())["code"]
    # no department named: the CEO holds it (and may delegate to a manager, request from a CEO)
    out = await post_order(client, owner, f"برای {co} برنامه‌ی سه ماه آینده را آماده کن {words()}")
    root, *children = out["routes"]
    assert out["route"]["budget_tokens"]  # the secretary's estimate stays a figure for the preview
    assert await budget_of(su, root["work_ref"]) is None
    for c in children:
        if c.get("work_ref"):
            assert await budget_of(su, c["work_ref"]) is None
    assert "بودجه" not in (out["route"]["preview_fa"] or "")
    # the holder delegates with a budget: the child has none (nothing under an order is capped)
    holder = root["to"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root["work_ref"])
    h = await agent_headers(holder)
    r = await client.post(
        f"/internal/v1/work/{wid}/delegate", headers={**h, **idem()},
        json={"to": f"{co}-FIN-MGR", "title": "عددها", "brief": "x", "budget": {"tokens": 50_000}},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["budget"] is None or r.json()["budget"].get("tokens") is None
    # a request to another company's CEO from the order's work: no budget either
    r = await client.post(
        "/internal/v1/work", headers={**h, **idem()},
        json={"company": other, "title": "همکاری", "brief": "x", "requested_by_work_id": str(wid),
              "budget": {"tokens": 30_000}},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["work"]["budget"] is None or r.json()["work"]["budget"].get("tokens") is None
    # outside an order the delegation budget is as before (a bound against endless wake-ups)
    plain = await make_order(hub, company, "کار عادی", department="TECH", budget=200_000)
    assert await budget_of(su, plain["work"]["ref"]) == 200_000


async def test_the_budget_blocker_is_never_raised_and_the_runner_never_parks_an_orders_work(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "یک کار", department="TECH", budget=100_000)
    ref, w = o["ref"], o["work"]
    await _blocked_run(su, company, w["id"], "budget_used_up", who="TECH-MGR")
    await _blocked_run(su, company, w["id"], "daily_cap", who="TECH-MGR")
    rep = await report(client, owner, ref)
    assert "budget" not in {b["kind"] for b in rep["blockers"]}, rep["blockers"]
    assert rep["session"]["badge"] != "your_turn"
    # the runner's budget stop: nothing for a work of an owner's order (it stays open, no CEO item)
    rn = runner.Runner(hub, None, None, None)  # type: ignore[arg-type]
    rc = SimpleNamespace(
        charter=SimpleNamespace(
            limits=SimpleNamespace(tokens_per_run=160_000, tokens_per_step=40_000)
        ),
        emp={"code": f"{co}-TECH-MGR"},
    )
    await rn._budget_stop(rc, w["ref"])  # type: ignore[arg-type]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) == "queued"
    assert not await su.fetchval(
        "SELECT 1 FROM work.work WHERE title LIKE 'بودجه کم است%' AND company_id = $1",
        company["id"],
    )
    # a plain work of the company (no order) still parks on its budget as before
    async with await all_tx(hub) as tx:
        from hq_api.domain import work as W

        plain = await W.create(
            tx, OR.SERVICE, company_id=company["id"], company_code=co, title="کار معمولی",
            brief="x", kind="one_off", priority="P3", assignee_code=f"{co}-TECH-MGR",
            budget=W.BudgetIn(tokens=50_000),
        )  # fmt: skip
    await rn._budget_stop(rc, plain["ref"])  # type: ignore[arg-type]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", plain["id"]) == "waiting"


async def test_budget_add_without_a_figure_lifts_the_cap_and_the_work_goes_on(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "کار با سقف", department="TECH", budget=100_000)
    ref, w = o["ref"], o["work"]
    await su.execute("UPDATE work.work SET status = 'waiting' WHERE id = $1", w["id"])
    await refuse_queued(su, w["ref"])
    # the Android session's «بودجه را بیشتر کن» sends no figure: 200, the cap gone, the work woken
    r = await client.post(
        f"/api/v1/orders/{ref}/fix",
        headers=owner,
        json={"action": "budget.add", "target": w["ref"]},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert await budget_of(su, w["ref"]) is None
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) == "in_progress"
    assert rep["steps"][-1]["what_fa"] == "سقف مصرف این کار برداشته شد؛ کار ادامه دارد"
    assert (
        await su.fetchval(
            """SELECT count(*) FROM agents.runs r WHERE r.work_id = $1 AND r.state = 'queued'
           AND r.reason = $2""",
            w["id"],
            f"uncapped:{w['ref']}",
        )
        == 1
    )
    # with a figure: today's behaviour (+X on the work; on no cap, still no cap)
    o2 = await make_order(hub, company, "کار دوم", department="FIN", budget=100_000)
    r = await client.post(
        f"/api/v1/orders/{o2['ref']}/fix", headers=owner,
        json={"action": "budget.add", "target": o2["work"]["ref"], "tokens": 50_000},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert await budget_of(su, o2["work"]["ref"]) == 150_000
    r = await client.post(
        f"/api/v1/orders/{ref}/fix", headers=owner,
        json={"action": "budget.add", "target": w["ref"], "tokens": 50_000},
    )  # fmt: skip
    assert r.status_code == 200 and await budget_of(su, w["ref"]) is None
    # a closed work of the order: 409 as before
    await su.execute(
        "UPDATE work.work SET status = 'cancelled', closed_at = now() WHERE id = $1",
        o2["work"]["id"],
    )
    r = await client.post(
        f"/api/v1/orders/{o2['ref']}/fix", headers=owner,
        json={"action": "budget.add", "target": o2["work"]["ref"]},
    )  # fmt: skip
    assert r.status_code == 409
    del co


async def test_uncap_under_a_capped_parent_lifts_the_parents_cap_first(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """A child of a capped work (it took what its parent had left): uncap lifts the parent's cap
    first, the root first, never a 409 from work.before_update (HQB01)."""
    from hq_api.domain import work as W

    company = await new_company()
    co = company["code"]
    async with await all_tx(hub) as tx:
        root = await W.create(
            tx, OR.SERVICE, company_id=company["id"], company_code=co, title="ریشه با سقف",
            brief="x", kind="one_off", priority="P3", assignee_code=f"{co}-TECH-MGR",
            budget=W.BudgetIn(tokens=100_000),
        )  # fmt: skip
        # the deepest a work goes (delegation depth 2 under the root)
        leaf = await W.create(
            tx, OR.SERVICE, company_id=company["id"], company_code=co, title="برگ",
            brief="x", kind="one_off", priority="P3", assignee_code=f"{co}-TECH-MGR", parent=root,
        )  # fmt: skip
    assert await budget_of(su, leaf["ref"]) == 100_000  # all its parent had left
    async with await all_tx(hub) as tx:
        await W.uncap(tx, leaf, OR.SERVICE)
    assert [await budget_of(su, w["ref"]) for w in (root, leaf)] == [None, None]
    await refuse_queued(su, root["ref"], leaf["ref"])


async def test_the_one_off_uncaps_the_open_orders_and_wakes_their_holders(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    open_o = await make_order(hub, company, "فرمان باز", department="TECH", budget=100_000)
    closed_o = await make_order(hub, company, "فرمان بسته", department="FIN", budget=100_000)
    r = await client.post(
        f"/api/v1/orders/{closed_o['ref']}/close",
        headers={**owner, **idem()},
        json={"verdict": "cancel"},
    )
    assert r.status_code == 200, r.text
    await refuse_queued(su, open_o["work"]["ref"])
    async with await all_tx(hub) as tx:
        dry = await UNCAP.uncap_open_orders(tx, dry_run=True)
    assert open_o["work"]["ref"] in dry["works"] and open_o["ref"] in dry["orders"]
    assert closed_o["work"]["ref"] not in dry["works"] and dry["woken"] == []
    assert await budget_of(su, open_o["work"]["ref"]) == 100_000  # a dry run changes nothing
    async with await all_tx(hub) as tx:
        out = await UNCAP.uncap_open_orders(tx)
    assert open_o["ref"] in out["orders"] and open_o["ref"] in out["woken"]
    assert await budget_of(su, open_o["work"]["ref"]) is None
    assert (
        await su.fetchval(
            "SELECT count(*) FROM agents.runs WHERE work_id = $1 AND state = 'queued'",
            open_o["work"]["id"],
        )
        == 1
    )
    rep = await report(client, owner, open_o["ref"])
    assert rep["steps"][-1]["what_fa"] == OR.UNCAPPED_FA and rep["session"]["badge"] == "moving"
    # idempotent: a second run finds nothing of this order
    async with await all_tx(hub) as tx:
        again = await UNCAP.uncap_open_orders(tx)
    assert open_o["ref"] not in again["orders"]


def test_a_decide_item_has_no_budget_of_its_own() -> None:
    assert not hasattr(D, "DECIDE_TOKENS")
    import inspect

    src = inspect.getsource(D)
    assert "تصمیم درباره‌ی" in src and "budget=W.BudgetIn(tokens=DECIDE" not in src
