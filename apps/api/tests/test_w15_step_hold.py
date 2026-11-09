"""⟨2026-11-09⟩ «با من» holds the whole session while it waits for the owner.

The owner: «یه جلسه باز کردم … دکمه با من رو زدم و شروع کرده برای خودش کار رو جلو بردن». The
holder asked him after its step, but the part it had handed to a colleague (the company's CTO)
went on running. In a step-by-step order, while the owner has not answered, nothing of the order
runs: not its holder, not a colleague; the runs come back the moment he answers, says «ادامه بده»
or makes the order «خودکار». A general order («خودکار») is never held.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import order_report as OR
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture


async def queued_of(su: Any, work_id: Any) -> Any:
    return await su.fetchrow(
        """SELECT id, reason FROM agents.runs WHERE work_id = $1 AND state = 'queued'
           ORDER BY queued_at DESC LIMIT 1""",
        work_id,
    )


async def ask(client: httpx.AsyncClient, ref: str, holder: str, q: str) -> None:
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask",
        headers=await agent_headers(holder),
        json={"question_fa": q},
    )
    assert r.status_code == 200, r.text


async def test_a_step_session_holds_everything_until_the_owner_answers(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    text = f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    out = await post_order(client, owner, text, pace="step")
    ref = out["ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    assert holder == f"{co}-CEO", route
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)

    # the holder hands a part of its step to a colleague (the screenshot: the CTO reading numbers)
    r = await client.post(
        f"/internal/v1/work/{root}/delegate",
        headers=await agent_headers(holder),
        json={"to": f"{co}-TECH-MGR", "title": "خواندن عددهای روزانه"},
    )
    assert r.status_code == 201, r.text
    child = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", r.json()["ref"])
    part = await queued_of(su, child)
    assert part is not None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, child) is None  # nothing asked yet

    # the holder asks the owner: the whole session now waits for him
    await ask(client, ref, holder, "گام ۲ تمام شد؛ گام ۳ را شروع کنم؟")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        waiting = await OR.owner_turn(tx, child)
    assert waiting is not None and waiting["askers"] == {holder} and waiting["since"] is not None
    claim = await agents.runner.claim(str(part["id"]))
    assert (claim.state, claim.code) == ("final", "owner_turn")
    # the requeue sweep does not bring it back while he has not answered
    from hq_api.worker.activities import Activities

    acts = Activities(
        agents.whub, None, router=agents.router, gateway=agents.gateway, live=agents.live
    )
    await acts.requeue_runs()
    assert await queued_of(su, child) is None
    # a wake his own word started is never held (here: his «ادامه بده» reason)
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        root,
    )
    rid = await su.fetchval(
        "SELECT work.wake_assignee($1, $2)", root, f"child_delivered:{work_ref}:O-000001"
    )
    assert (await agents.runner.claim(str(rid))).code == "owner_turn"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert not await OR.held_for_owner(
            tx, {"trigger": "work", "work_id": root, "reason": f"nudge:{ref}"}
        )
        assert not await OR.held_for_owner(  # the owner's talk with the holder is never held
            tx, {"trigger": "talk", "work_id": root, "reason": "talk"}
        )

    # the owner answers: the holder runs with his word, and the colleague's part goes on
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "بله، ادامه بده"}
    )
    assert r.status_code == 200, r.text
    resumed = await queued_of(su, child)
    assert resumed is not None and resumed["reason"] == f"{OR.OWNER_TURN_REASON}{ref}"
    assert (await queued_of(su, root))["reason"] == f"owner_reply:{ref}"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, child) is None
    assert (await agents.runner.claim(str(resumed["id"]))).state == "running"

    # «ادامه بده» while a question is open answers it: the turn is cleared
    await ask(client, ref, holder, "گام ۴ را شروع کنم؟")
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT turn FROM owner.order_reports WHERE ref = $1", ref) is None

    # a general order («خودکار») is never held, an open question or not
    await ask(client, ref, holder, "گام ۵ را شروع کنم؟")
    r = await client.post(
        f"/api/v1/orders/{ref}/pace", headers={**owner, **idem()}, json={"pace": "auto"}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, root) is None
