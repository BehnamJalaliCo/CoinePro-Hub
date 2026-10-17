"""Agents at work (prompt 05 §2, §3, §12) with the FAKE model: triggers queue
runs, the runner thinks through llm-router and acts only through the Tool
Gateway, limits and locks hold, the token registry closes behind a run, and
nothing of the conversation reaches logs, audit or NATS."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.security import agent_tokens
from hq_common import charters

from .conftest import AGENT_KEY, idem

pytestmark = pytest.mark.usefixtures("relay")


def step(summary: str, *actions: tuple[str, dict[str, Any]], done: bool = True) -> dict[str, Any]:
    return {
        "summary_fa": summary,
        "actions": [{"tool": t, "args": a} for t, a in actions],
        "done": done,
    }


async def runs_of(su: Any, code: str) -> list[dict[str, Any]]:
    rows = await su.fetch(
        """SELECT r.* FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.code = $1 AND r.reason <> 'test' ORDER BY r.queued_at""",
        code,
    )
    return [dict(r) for r in rows]


async def run(env: Any, run_id: Any) -> dict[str, Any]:
    claim = await env.runner.claim(str(run_id))
    assert claim.state == "running", claim
    return dict(await env.runner.execute(str(run_id)))


async def order(
    client: httpx.AsyncClient, owner: dict[str, str], co: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={
            "company": co,
            "title": extra.pop("title", "سفارش مالک"),
            "brief": extra.pop("brief", "شرح"),
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


# --------------------------------------------------------------- triggers --
async def test_records_wake_the_right_agent(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    ceo = await runs_of(su, f"{co}-CEO")
    assert [(r["trigger"], r["state"], r["work_id"]) for r in ceo] == [
        ("work", "queued", uuid.UUID(w["id"]))
    ]
    # A second cause for the same employee and work joins the queued run.
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "گزارش بده"},
    )
    assert r.status_code == 201, r.text
    reply = r.json()["reply"]
    assert reply["state"] == "queued"
    assert len(await runs_of(su, f"{co}-CEO")) == 2  # work + message: two causes
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages", headers={**owner, **idem()}, json={"body": "و این"}
    )
    assert r.json()["reply"]["run_id"] == reply["run_id"]  # joins the queued message run
    # A department group and the report system wake nobody.
    r = await client.post(
        f"/api/v1/threads/{co}-TECH/messages",
        headers={**owner, **idem()},
        json={"body": "سلام تیم"},
    )
    assert r.json()["reply"] is None
    assert (
        await su.fetchval(
            """SELECT count(*) FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.kind = 'system'"""
        )
        == 0
    )


async def test_the_line_ceo_to_cto_and_back(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    marker = f"PROMPT-MARKER-{uuid.uuid4().hex[:8]}"
    w = await order(
        client,
        owner,
        co,
        title="سایت را بررسی کن",
        brief=f"شرح محرمانه {marker}",
        budget={"tokens": 500_000},
    )
    agents.fake.enqueue(
        f"{co}-CEO",
        step(
            "کار را پذیرفتم و به مدیر فنی سپردم.",
            ("work.accept", {"ref": w["ref"]}),
            (
                "work.delegate",
                {
                    "ref": w["ref"],
                    "to": f"{co}-TECH-MGR",
                    "title_fa": "بررسی فنی",
                    "brief_md": "بررسی کن",
                    "budget": 200_000,
                },
            ),
            ("activity.set", {"state": "waiting", "note": "منتظر فنی"}),
        ),
    )
    ceo_run = (await runs_of(su, f"{co}-CEO"))[-1]
    out = await run(agents, ceo_run["id"])
    assert out["state"] == "done", out
    child_ref = await su.fetchval(
        "SELECT ref FROM work.work WHERE parent_id = $1", uuid.UUID(w["id"])
    )
    assert child_ref
    cto_run = (await runs_of(su, f"{co}-TECH-MGR"))[-1]
    assert cto_run["trigger"] == "work" and cto_run["state"] == "queued"
    agents.fake.enqueue(
        f"{co}-TECH-MGR",
        step(
            "بررسی را شروع کردم.",
            ("work.accept", {"ref": child_ref}),
            ("health.sites", {}),
            done=False,
        ),
        step(
            "یادداشت فنی را تحویل دادم.",
            (
                "deliver",
                {
                    "work_ref": child_ref,
                    "title_fa": "یادداشت فنی",
                    "body_md": "همه چیز سالم است.",
                    "evidence": [{"kind": "metric", "ref": "uptime", "note": "100%"}],
                },
            ),
            ("memory.write", {"note_md": "سایت سالم بود", "tags": ["ops"]}),
        ),
    )
    out = await run(agents, cto_run["id"])
    assert out["state"] == "done", out
    # The child's deliverable woke the CEO (it did not wait).
    again = (await runs_of(su, f"{co}-CEO"))[-1]
    assert again["state"] == "queued" and again["reason"].startswith("child_delivered:")
    agents.fake.enqueue(
        f"{co}-CEO",
        step(
            "نتیجه را به مدیر کل تحویل دادم.",
            ("deliver", {"work_ref": w["ref"], "title_fa": "نتیجه", "body_md": "سالم است"}),
        ),
    )
    assert (await run(agents, again["id"]))["state"] == "done"
    # The records: steps with summaries and tool metadata only, usage on run and work.
    steps = await su.fetch(
        "SELECT n, summary_fa, actions, usage FROM agents.steps WHERE run_id = $1 ORDER BY n",
        cto_run["id"],
    )
    assert [s["n"] for s in steps] == [1, 2]
    actions = json.loads(steps[1]["actions"])
    assert [(a["tool"], a["outcome"], a["class"]) for a in actions] == [
        ("deliver", "ok", "A1"),
        ("memory.write", "ok", "A1"),
    ]
    assert actions[0]["ref"].startswith("O-")
    finished = await su.fetchrow("SELECT * FROM agents.runs WHERE id = $1", cto_run["id"])
    cto = charters.load().roles["cto"]
    assert finished["charter_role"] == "cto" and finished["charter_version"] == cto.version
    assert finished["input_tokens"] > 0 and finished["steps"] == 2 and finished["tool_calls"] == 4
    assert finished["model"] == cto.model and finished["effort"] == cto.effort
    used = await su.fetchval("SELECT tokens_used FROM work.work WHERE ref = $1", child_ref)
    assert used == sum(
        json.loads(s["usage"])["input"] + json.loads(s["usage"])["output"] for s in steps
    )
    ledger = await su.fetch(
        "SELECT meta FROM llm.calls WHERE actor_ref = $1 ORDER BY started_at", f"{co}-TECH-MGR"
    )
    metas = [json.loads(r["meta"]) for r in ledger]
    assert [m["charter"] for m in metas] == [cto.ref, cto.ref]
    assert [m["step"] for m in metas] == [1, 2]
    assert all(m["run_id"] == str(cto_run["id"]) for m in metas)
    audits = await su.fetch(
        "SELECT target_ref, summary FROM audit.entries WHERE action = 'tool.call' AND actor_code = $1",
        f"{co}-TECH-MGR",
    )
    assert sorted(a["target_ref"] for a in audits) == [
        "deliver",
        "health.sites",
        "memory.write",
        "work.accept",
    ]
    # Never the conversation: not in audit, steps, the outbox (NATS) or the employee's activity.
    for table, col in (
        ("audit.entries", "summary"),
        ("agents.steps", "summary_fa"),
        ("core.outbox", "payload::text"),
    ):
        assert not await su.fetchval(f"SELECT 1 FROM {table} WHERE {col} LIKE $1", f"%{marker}%"), (
            table
        )
    emp = await su.fetchrow("SELECT activity FROM core.employees WHERE code = $1", f"{co}-TECH-MGR")
    assert emp["activity"] == "sleeping"
    # The owner's view of runs and steps.
    from .conftest import owner_token

    r = await client.get(f"/api/v1/work/{w['id']}/runs", headers=owner)
    assert r.status_code == 200 and [x["state"] for x in r.json()] == ["done", "done"]
    assert r.json()[0]["steps_detail"][0]["actions"][1]["tool"] == "work.delegate"
    assert owner_token  # imported for type-checkers only
    r = await client.get(f"/api/v1/runs/{cto_run['id']}", headers=owner)
    body = r.json()
    assert (
        body["charter"] == "cto" and body["tokens"]["input"] > 0 and len(body["steps_detail"]) == 2
    )
    assert marker not in r.text


async def test_refusals_inside_a_run(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co, department="TECH")
    run_row = (await runs_of(su, f"{co}-TECH-MGR"))[-1]
    agents.fake.enqueue(
        f"{co}-TECH-MGR",
        step(
            "ابزارهای ممنوع",
            ("trade.execute", {"amount": 1}),  # unknown: no such tool, and A4 never exists
            ("kill_switch.set", {"scope": "holding"}),  # not a tool of the catalog
            ("audit.recent", {}),  # in the catalog, not in the CTO's charter
            (
                "work.delegate",
                {
                    "ref": w["ref"],
                    "to": f"{co}-TECH-MGR",
                    "title_fa": "x",
                    "brief_md": "",
                    "budget": 10**9,
                },
            ),
        ),
    )
    assert (await run(agents, run_row["id"]))["state"] == "done"
    actions = json.loads(
        await su.fetchval("SELECT actions FROM agents.steps WHERE run_id = $1", run_row["id"])
    )
    assert [(a["tool"], a["outcome"], a.get("code")) for a in actions] == [
        ("trade.execute", "denied", "unknown_tool"),
        ("kill_switch.set", "denied", "unknown_tool"),
        ("audit.recent", "denied", "tool_not_in_charter"),
        ("work.delegate", "denied", "policy_denied"),  # a manager delegates to employees only
    ]


async def test_depth_and_budget_hold_through_the_gateway(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    # A hired employee to delegate to.
    hire = await su.fetchrow(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
           SELECT c.id, d.id, $1, 'employee', 'مهندس پایداری', 'SRE', 'sre'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'TECH'
           WHERE c.code = $2 RETURNING id""",
        f"{co}-TECH-01",
        co,
    )
    assert hire
    w = await order(client, owner, co, department="TECH", budget={"tokens": 300_000})
    run_row = (await runs_of(su, f"{co}-TECH-MGR"))[-1]
    agents.fake.enqueue(
        f"{co}-TECH-MGR",
        step(
            "ارجاع با بودجه‌ی بیش از اندازه",
            (
                "work.delegate",
                {"ref": w["ref"], "to": f"{co}-TECH-01", "title_fa": "پایش", "budget": 900_000},
            ),
            (
                "work.delegate",
                {"ref": w["ref"], "to": f"{co}-TECH-01", "title_fa": "پایش", "budget": 50_000},
            ),
        ),
    )
    assert (await run(agents, run_row["id"]))["state"] == "done"
    actions = json.loads(
        await su.fetchval("SELECT actions FROM agents.steps WHERE run_id = $1", run_row["id"])
    )
    assert [(a["outcome"], a.get("code")) for a in actions] == [
        ("error", "budget_exceeded"),
        ("ok", None),
    ]
    child = actions[1]["ref"]
    # Depth 3: a manager holding a depth-2 item tries to delegate further.
    await su.execute(
        "UPDATE work.work SET assignee_id = (SELECT id FROM core.employees WHERE code = $1) WHERE ref = $2",
        f"{co}-TECH-MGR",
        child,
    )
    deep = (await runs_of(su, f"{co}-TECH-MGR"))[-1]
    assert deep["state"] == "queued"
    agents.fake.enqueue(
        f"{co}-TECH-MGR",
        step(
            "ارجاع سطح سوم",
            ("work.delegate", {"ref": child, "to": f"{co}-TECH-01", "title_fa": "سطح سوم"}),
        ),
    )
    assert (await run(agents, deep["id"]))["state"] == "done"
    actions = json.loads(
        await su.fetchval("SELECT actions FROM agents.steps WHERE run_id = $1", deep["id"])
    )
    assert (actions[0]["outcome"], actions[0]["code"]) == ("error", "delegation_depth_exceeded")


async def test_the_charter_token_cap_and_a_partial_deliverable(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co, budget={"tokens": 4_000})
    run_row = (await runs_of(su, f"{co}-CEO"))[-1]
    agents.fake.enqueue(f"{co}-CEO", *[step(f"قدم {i}", done=False) for i in range(10)])
    out = await run(agents, run_row["id"])
    assert out == {"state": "done", "code": "limit_reached"}, out
    r = await su.fetchrow("SELECT * FROM agents.runs WHERE id = $1", run_row["id"])
    assert r["partial"] is True and r["token_cap"] == 4_000
    per_step = max(
        json.loads(s["usage"])["input"] + json.loads(s["usage"])["output"]
        for s in await su.fetch("SELECT usage FROM agents.steps WHERE run_id = $1", run_row["id"])
    )
    spent = (
        r["input_tokens"] + r["output_tokens"] + r["cache_read_tokens"] + r["cache_write_tokens"]
    )
    assert spent <= r["token_cap"] + per_step  # never more than one step past the cap
    dl = await su.fetchrow(
        "SELECT title, body FROM cartable.deliverables WHERE work_id = $1", uuid.UUID(w["id"])
    )
    assert dl["title"].startswith("خروجی ناقص") and "قدم 0" in dl["body"]
    assert (
        await su.fetchval("SELECT status FROM work.work WHERE id = $1", uuid.UUID(w["id"]))
        == "delivered"
    )
    # Steps per run: the charter's limit, then failed (nothing to deliver for a message).
    r2 = await client.post(
        f"/api/v1/threads/{co}-CEO/messages", headers={**owner, **idem()}, json={"body": "؟"}
    )
    msg_run = r2.json()["reply"]["run_id"]
    agents.fake.enqueue(f"{co}-CEO", *[step(f"گفتگو {i}", done=False) for i in range(10)])
    assert (await run(agents, msg_run))["state"] == "failed"
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", uuid.UUID(msg_run)) == 6


async def test_kill_switch_mid_run_refuses_the_next_step(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await order(client, owner, co)
    run_row = (await runs_of(su, f"{co}-CEO"))[-1]

    real_call = agents.gateway.call

    async def call_then_engage(
        token: str, step_n: int, index: int, tool: str, args: Any
    ) -> dict[str, Any]:
        out = await real_call(token, step_n, index, tool, args)
        await su.execute(
            """UPDATE control.kill_switches SET state = 'engaged', changed_by_kind = 'owner',
                   changed_by_code = 'owner', reason = 'test' WHERE company_id = $1""",
            company["id"],
        )
        return out

    agents.gateway.call = call_then_engage
    try:
        agents.fake.enqueue(
            f"{co}-CEO", step("قدم اول", ("company.state", {}), done=False), step("قدم دوم")
        )
        out = await run(agents, run_row["id"])
    finally:
        agents.gateway.call = real_call
    assert out == {"state": "refused", "code": "locked"}
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", run_row["id"]) == 1
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'run.refused' AND target_ref = $1",
            str(run_row["id"]),
        )
        == 1
    )
    # A new run of a locked company is refused at once; release -> requeued by Maintenance.
    await order(client, owner, co)
    queued = (await runs_of(su, f"{co}-CEO"))[-1]
    claim = await agents.runner.claim(str(queued["id"]))
    assert (claim.state, claim.code) == ("final", "locked")
    await su.execute(
        "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", company["id"]
    )
    from hq_api.worker.activities import Activities

    acts = Activities(
        agents.whub, None, router=agents.router, gateway=agents.gateway, live=agents.live
    )
    assert (await acts.requeue_runs())["requeued"] >= 1
    assert (await runs_of(su, f"{co}-CEO"))[-1]["reason"].startswith("requeue:")


async def test_the_token_dies_with_its_run(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    run_row = (await runs_of(su, f"{co}-CEO"))[-1]
    assert (await agents.runner.claim(str(run_row["id"]))).state == "running"
    token = agent_tokens.mint(AGENT_KEY, f"{co}-CEO", str(run_row["id"]))
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"/internal/v1/context/{co}-CEO", headers=h)).status_code == 200
    # Another employee's token for this run, or a run nobody started: refused.
    other = agent_tokens.mint(AGENT_KEY, f"{co}-TECH-MGR", str(run_row["id"]))
    assert (
        await client.get(
            f"/internal/v1/context/{co}-TECH-MGR", headers={"Authorization": f"Bearer {other}"}
        )
    ).status_code == 401
    agents.fake.enqueue(f"{co}-CEO", step("تمام"))
    assert (await agents.runner.execute(str(run_row["id"])))["state"] == "done"
    assert (await client.get(f"/internal/v1/context/{co}-CEO", headers=h)).status_code == 401
    expired = agent_tokens.mint(AGENT_KEY, f"{co}-CEO", str(uuid.uuid4()))
    assert (
        await client.get(
            f"/internal/v1/context/{co}-CEO", headers={"Authorization": f"Bearer {expired}"}
        )
    ).status_code == 401


async def test_claim_refusals_and_busy(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    first = (await runs_of(su, f"{co}-CEO"))[-1]
    assert (await agents.runner.claim(str(first["id"]))).state == "running"
    assert (await agents.runner.claim(str(first["id"]))).state == "running"  # a retried claim
    await order(client, owner, co, title="دومی")
    second = (await runs_of(su, f"{co}-CEO"))[-1]
    assert (await agents.runner.claim(str(second["id"]))).state == "busy"  # one run at a time
    assert (await agents.runner.finish(str(first["id"]), "failed", "test"))["state"] == "failed"
    assert (await agents.runner.finish(str(first["id"]), "done", None))[
        "state"
    ] == "failed"  # final stays
    await su.execute("UPDATE core.employees SET status = 'paused' WHERE code = $1", f"{co}-CEO")
    c = await agents.runner.claim(str(second["id"]))
    assert (c.state, c.final, c.code) == ("final", "refused", "employee_inactive")
    assert (await agents.runner.claim(str(uuid.uuid4()))).code == "unknown_run"
    await su.execute("UPDATE core.employees SET status = 'active' WHERE code = $1", f"{co}-CEO")
    w = await order(client, owner, co, budget={"tokens": 10})
    await su.execute("UPDATE work.work SET tokens_used = 10 WHERE id = $1", uuid.UUID(w["id"]))
    c = await agents.runner.claim(str((await runs_of(su, f"{co}-CEO"))[-1]["id"]))
    assert c.code == "budget_used_up"


async def test_daily_cap_refuses_runs(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    from dataclasses import replace

    co = (await new_company())["code"]
    await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    real = agents.runner.s
    agents.runner.s = replace(real, agent_daily_token_cap=1)
    try:
        c = await agents.runner.claim(str(row["id"]))
    finally:
        agents.runner.s = real
    assert c.code == "daily_cap"
    # The day's spend counts everything the model read or wrote: through the
    # subscription most input arrives as cache writes and reads.
    want = await su.fetchval(
        """SELECT COALESCE(sum(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens), 0)
           FROM agents.runs WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"""
    )
    async with agents.runner.hub.db.tx(await agents.runner.hub.companies.ids()) as tx:
        assert await agents.runner._spent_today(tx) == want


async def test_bad_output_and_router_refusals(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    agents.fake.enqueue(f"{co}-CEO", "not json at all", "still not json")
    assert (await run(agents, row["id"])) == {"state": "failed", "code": "invalid_output"}
    await order(client, owner, co, title="بعدی")
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    agents.fake.enqueue(
        f"{co}-CEO",
        "garbage",
        'prefix {"summary_fa": "بازیابی", "actions": [], "done": true} suffix',
    )
    assert (await run(agents, row["id"]))["state"] == "done"  # the JSON found in text is accepted
    await order(client, owner, co, title="سوم")
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    from llm_router.backends.base import QUOTA, BackendResult

    agents.fake.enqueue(f"{co}-CEO", BackendResult(QUOTA, error_class="usage_limit"))
    out = await run(agents, row["id"])
    assert out["state"] == "failed" and out["code"] == "usage_limit"
    await su.execute(
        "UPDATE llm.connections SET status = 'enabled', quota_reset_at = NULL WHERE key = 'claude-max'"
    )
    agents.service.breakers.clear()
    agents.service.quota.states.clear()
