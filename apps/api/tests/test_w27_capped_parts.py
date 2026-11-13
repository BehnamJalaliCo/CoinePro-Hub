"""⟨2026-11-13⟩ F-0018 P5: a part of a session that reaches its run's cap goes on by itself.

In F-0018 IG's parts of the session (W-000413 for IG's CEO, W-000415 for its CTO) each stopped at
their run's token cap half way, with a partial output. That output woke the session's holder, who
issued the part again as a new work (W-000414, W-000416); each new run began from nothing and
stopped at its cap again. Now the part's own next run is queued at once, reads what the last run
did and goes on from there, and the holder is not woken for it; after two such runs in a row the
holder is woken and decides, as before.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.agents import runner as R
from hq_api.domain import session_activity as SA

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w15_step_hold import off_the_day, queued_of  # noqa: F401 - the fixture


def _step(summary: str) -> dict[str, Any]:
    return {"summary_fa": summary, "actions": [], "done": False}


def _last_run_block(text: str) -> str | None:
    """The «last run stopped at its cap» part of a run's context (its lines are one block)."""
    at = text.find("# Your last run of this work stopped at its cap")
    if at < 0:
        return None
    block = text[at:]
    return block[: block.find("\n\n")] if "\n\n" in block else block


async def _capped_run(
    su: Any, agents: Any, run_id: Any, who: str, tag: str, steps: int = 1
) -> list[str]:
    """Claims and runs `run_id` with a cap of `steps` steps and steps that never end; answers the
    text of each model call the run made."""
    claim = await agents.runner.claim(str(run_id))
    assert claim.state == "running", claim
    await su.execute("UPDATE agents.runs SET steps_cap = $2 WHERE id = $1", run_id, steps)
    agents.fake.enqueue(who, *[_step(f"{tag} قدم {n}") for n in ("یک", "دو")[:steps]])
    before = len(agents.fake.calls)
    out = await agents.runner.execute(str(run_id))
    assert out == {"state": "done", "code": "limit_reached"}, out
    return [
        "".join(m.content for m in c.messages)
        for c in agents.fake.calls[before:]
        if c.actor_ref == who
    ]


@pytest.mark.parametrize("shape", ["requested", "delegated"])
async def test_a_part_that_reached_its_cap_goes_on_in_its_own_next_run(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
    off_the_day: None,  # noqa: F811
    shape: str,
) -> None:
    """`requested`: F-0018's own shape (the holder asked another company's people with
    work.request; the holder was woken by order_turns.on_child_closed). `delegated`: a child
    work (the deliverable trigger, agents.wake_on_deliverable, woke the parent's assignee)."""
    co = (await new_company())["code"]
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="auto"
    )
    [route] = out["routes"]
    holder, colleague = route["to"], f"{co}-TECH-MGR"
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    title = "ساختن دو قاعده در IG-Hub"
    if shape == "delegated":
        r = await client.post(
            f"/internal/v1/work/{root}/delegate",
            headers=await agent_headers(holder),
            json={"to": colleague, "title": title},
        )
        assert r.status_code == 201, r.text
        child_ref = r.json()["ref"]
    else:
        r = await client.post(
            "/internal/v1/work",
            headers={**await agent_headers(holder), **idem()},
            json={"to": colleague, "title": title, "requested_by_work_id": str(root)},
        )
        assert r.status_code == 201, r.text
        child_ref = r.json()["work"]["ref"]
    child = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", child_ref)
    # a part of an owner's order has no token budget of its own (W-000413 had none)
    await su.execute("UPDATE work.work SET budget_tokens = NULL WHERE id = $1", child)
    await su.execute(  # the holder's own queued run is not this test's business
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        root,
    )

    # 1. the first run stops at its cap: its next run is queued, the holder is not woken
    first = await queued_of(su, child)
    texts = await _capped_run(su, agents, first["id"], colleague, "اول", steps=2)
    assert texts and _last_run_block(texts[0]) is None  # nothing before it to go on from
    nxt = await queued_of(su, child)
    assert nxt is not None and nxt["reason"] == f"{R.CAPPED_REASON}{child_ref}", nxt
    body = await su.fetchval(
        """SELECT body FROM cartable.deliverables WHERE work_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        child,
    )
    assert body.startswith("سقف قدم یا توکن") and R.GOES_ON_FA.strip() in body
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", child) == "in_progress"
    assert await queued_of(su, root) is None  # before: child_delivered woke him to issue it again
    assert SA.start_text(nxt["reason"], "") == "دور قبل به سقفش رسید؛ از همان‌جا ادامه میدهد"

    # 2. the next run reads what the last one did, near the top, and goes on from there
    texts = await _capped_run(su, agents, nxt["id"], colleague, "دوم")
    seen = texts[0]
    block = _last_run_block(seen)
    assert block is not None and "stopped at its cap (limit_reached)" in block
    assert "1. اول قدم یک" in block and "2. اول قدم دو" in block
    assert seen.index("stopped at its cap") < seen.index("# Work")
    third = await queued_of(su, child)
    assert third is not None and third["reason"].startswith(R.CAPPED_REASON)
    assert await queued_of(su, root) is None

    # 3. a third capped run in a row: no more by itself; the holder is woken and decides
    texts = await _capped_run(su, agents, third["id"], colleague, "سوم")
    block = _last_run_block(texts[0])
    assert block is not None and "1. دوم قدم یک" in block and "اول" not in block
    assert await queued_of(su, child) is None
    body = await su.fetchval(
        """SELECT body FROM cartable.deliverables WHERE work_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        child,
    )
    assert R.GOES_ON_FA.strip() not in body
    woke = await queued_of(su, root)
    assert woke is not None and woke["reason"].startswith(f"child_delivered:{child_ref}"), woke

    # a whole run in between counts the row again from nothing
    whole = await su.fetchval("SELECT work.wake_assignee($1, $2)", child, "test_wake")
    assert (await agents.runner.claim(str(whole))).state == "running"
    agents.fake.enqueue(colleague, {"summary_fa": "تمام", "actions": [], "done": True})
    assert (await agents.runner.execute(str(whole))) == {"state": "done", "code": None}
    again = await su.fetchval("SELECT work.wake_assignee($1, $2)", child, "test_wake")
    texts = await _capped_run(su, agents, again, colleague, "چهارم")
    assert _last_run_block(texts[0]) is None  # its last run with a step was a whole one
    assert (await queued_of(su, child))["reason"].startswith(R.CAPPED_REASON)


async def test_the_holders_own_work_and_a_work_of_no_session_are_not_continued(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
    off_the_day: None,  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="auto"
    )
    [route] = out["routes"]
    holder = route["to"]
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    # the holder's own work: the session's sweep wakes it (§41.3), not this (a classic run here,
    # not a turn of the workshop: a reason the direct session leaves alone)
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        root,
    )
    run = await su.fetchval("SELECT work.wake_assignee($1, $2)", root, "direct_failed:test")
    await _capped_run(su, agents, run, holder, "مسئول")
    assert await queued_of(su, root) is None
    # a work of no session at all (the owner's plain work item): its budget decides, as before
    r = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co, "title": "سفارش مالک", "brief": "شرح"},
    )
    assert r.status_code == 201, r.text
    plain = r.json()["id"]
    run = await queued_of(su, plain)
    await _capped_run(su, agents, run["id"], holder, "تنها")
    assert await queued_of(su, plain) is None
