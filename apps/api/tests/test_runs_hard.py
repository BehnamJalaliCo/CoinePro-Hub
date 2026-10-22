"""Prompt 5.1 §2.1, §2.5-§2.7: what a model reads is masked, a long answer
keeps its run alive, locks and caps are hard, and a deliverable's usage comes
from the ledger."""

from __future__ import annotations

import asyncio
import itertools
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import DBAPIError

from hq_api.agents import runner as R
from hq_api.agents.clients import ModelCall
from hq_common import charters
from hq_common.redact import MASK

from .conftest import agent_headers, idem
from .test_agents import order, run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")


def _fake_secrets() -> list[str]:
    """Secret and personal-data shapes, assembled here (never a real value)."""
    return [
        "DB_PASSWORD=" + "q8Zr" * 4,
        "sk-" + "ant-" + "api03-" + "Ab9" * 14,
        "hvs." + "Q7w" * 9,
        "۰۹۱۲" + "۳۴۵" + "۶۷۸۹",
        "owner.private" + "@" + "example.com",
        "Authorization: Bearer " + "z" * 12 + "." + "y" * 20,
    ]


def _prompts(agents: Any, actor: str, since: int) -> str:
    return "\n".join(
        (c.system or "") + "".join(m.content for m in c.messages)
        for c in agents.fake.calls[since:]
        if c.actor_ref == actor
    )


# ------------------------------------------------------------ §2.1 masking --
async def test_no_secret_reaches_the_model_and_summaries_are_masked(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    secrets = _fake_secrets()
    w = await order(client, owner, co, title="کار حساس", brief="اطلاعات: " + " ".join(secrets))
    ceo = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co}-CEO")
    await su.execute(
        "INSERT INTO core.employee_memory (company_id, employee_id, note) VALUES ($1, $2, $3)",
        company["id"],
        ceo,
        "یادداشت قدیمی " + secrets[1],
    )
    (row,) = await runs_of(su, f"{co}-CEO")
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        f"{co}-CEO", step("خواندم؛ رمز " + secrets[0], ("work.get", {"ref": w["ref"]}))
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    seen = _prompts(agents, f"{co}-CEO", since)
    assert MASK in seen and "کار حساس" in seen
    for s in secrets:
        assert s not in seen, s
    summary = await su.fetchval(
        "SELECT summary_fa FROM agents.steps WHERE run_id = $1 AND n = 1", row["id"]
    )
    assert secrets[0] not in summary and MASK in summary


async def test_live_deltas_to_the_owner_are_masked(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, hub: Any, agents: Any
) -> None:
    phone, key = "۰۹۱۲" + "۳۴۵" + "۶۷۸۹", "sk-" + "ant-" + "api03-" + "Zz7" * 14
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "شماره؟"}
    )
    run_id = r.json()["reply"]["run_id"]
    agents.fake.enqueue("HQ-ADV", step("پاسخ"), f"شماره‌ی او {phone} است و کلید {key}.\nپایان")
    q = hub.live.subscribe("A")
    try:
        assert (await run(agents, run_id))["state"] == "done"
        seen = []
        while not q.empty():
            seen.append(q.get_nowait())
    finally:
        hub.live.unsubscribe("A", q)
    text = "".join(d["text"] for t, d in seen if t == "reply.delta")
    assert "پایان" in text and "[phone]" in text and phone not in text and key not in text
    body = await su.fetchval(
        "SELECT body FROM msg.messages WHERE ref = $1", seen[-1][1]["message_ref"]
    )
    assert phone not in body and key not in body


# ----------------------------------------------------------- §2.5 heartbeat --
async def test_a_long_streamed_answer_keeps_beating_and_is_stored(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, agents: Any
) -> None:
    """A real Opus answer may stream for minutes against the activity's 3-minute
    heartbeat timeout; here time is scaled down (beat every 50 ms, a 1 s
    silence before the first delta) and the beats must keep coming."""
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "طولانی بنویس"}
    )
    run_id = r.json()["reply"]["run_id"]
    agents.fake.enqueue("HQ-ADV", step("فکر"), "پاسخ بلند و کامل.")
    beats: list[float] = []
    real_stream = agents.router.stream

    async def slow_stream(body: dict[str, Any], timeout_s: int, on_delta: Any) -> ModelCall:
        await asyncio.sleep(1.0)
        out: ModelCall = await real_stream(body, timeout_s, on_delta)
        return out

    agents.router.stream = slow_stream
    agents.runner.heartbeat, agents.runner.heartbeat_every_s = (
        lambda: beats.append(time.monotonic()),
        0.05,
    )
    try:
        assert (await run(agents, run_id))["state"] == "done"
    finally:
        agents.router.stream = real_stream
        agents.runner.heartbeat, agents.runner.heartbeat_every_s = (
            lambda: None,
            R.HEARTBEAT_EVERY_S,
        )
    gaps = [b - a for a, b in itertools.pairwise(beats)]
    assert len(beats) >= 10 and max(gaps) < 0.5
    stored = await su.fetchval(
        """SELECT count(*) FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = 'A' AND m.author_code = 'HQ-ADV' AND m.body = 'پاسخ بلند و کامل.'"""
    )
    assert stored >= 1


# ---------------------------------------------------------------- §2.6 locks --
async def test_a_deploy_freeze_refuses_the_claim_and_the_next_step(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    freeze = """INSERT INTO control.deploy_freezes (company_id, until, reason, created_by_kind, created_by_code)
                VALUES ($1, now() + interval '1 hour', 'test', 'owner', 'owner') RETURNING id"""
    await order(client, owner, co)
    (first,) = await runs_of(su, f"{co}-CEO")
    fid = await su.fetchval(freeze, company["id"])
    claim = await agents.runner.claim(str(first["id"]))
    assert (claim.state, claim.code) == ("final", "locked")
    await su.execute("UPDATE control.deploy_freezes SET lifted_at = now() WHERE id = $1", fid)
    await order(client, owner, co, title="دوم")
    second = (await runs_of(su, f"{co}-CEO"))[-1]
    real_call = agents.gateway.call

    async def call_then_freeze(token: str, n: int, i: int, tool: str, args: Any) -> dict[str, Any]:
        out: dict[str, Any] = await real_call(token, n, i, tool, args)
        await su.execute(freeze, company["id"])
        return out

    agents.gateway.call = call_then_freeze
    try:
        agents.fake.enqueue(
            f"{co}-CEO", step("قدم اول", ("company.state", {}), done=False), step("قدم دوم")
        )
        out = await run(agents, second["id"])
    finally:
        agents.gateway.call = real_call
        await su.execute(
            "UPDATE control.deploy_freezes SET lifted_at = now() WHERE company_id = $1",
            company["id"],
        )
    assert out == {"state": "refused", "code": "locked"}
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", second["id"]) == 1


async def test_the_daily_cap_is_checked_before_every_model_call(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    (row,) = await runs_of(su, f"{co}-CEO")
    spent = await su.fetchval(
        """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                               + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
           FROM llm.calls
           WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
             AND meta ? 'run_id'"""
    )
    settings = agents.runner.s
    agents.runner.s = replace(settings, agent_daily_token_cap=int(spent) + 1)
    try:
        agents.fake.enqueue(f"{co}-CEO", step("یک", done=False), step("دو", done=False))
        out = await run(agents, row["id"])
    finally:
        agents.runner.s = settings
    assert out == {"state": "failed", "code": "daily_cap"}
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", row["id"]) == 1


async def test_the_advisors_answer_counts_inside_its_steps(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, agents: Any
) -> None:
    cap = charters.load().roles["advisor"].limits.steps_per_run
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "تحقیق کن"}
    )
    run_id = uuid.UUID(r.json()["reply"]["run_id"])
    agents.fake.enqueue(
        "HQ-ADV", *[step(f"تحقیق {i}", done=False) for i in range(cap + 3)], "جمع‌بندی."
    )
    try:
        assert (await run(agents, run_id))["state"] == "done"
    finally:
        agents.fake.queues["HQ-ADV"].clear()
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", run_id) == cap
    caps = [c.max_output_tokens for c in agents.fake.calls[-cap:] if c.actor_ref == "HQ-ADV"]
    assert len(caps) == cap and all(c is not None and c > 0 for c in caps)


async def test_a_failed_calls_tokens_are_booked(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    from llm_router.backends.base import ERROR, BackendResult
    from llm_router.pricing import Usage

    co = (await new_company())["code"]
    await order(client, owner, co)
    (row,) = await runs_of(su, f"{co}-CEO")
    agents.fake.enqueue(
        f"{co}-CEO",
        BackendResult(ERROR, error_class="boom", usage=Usage(input_tokens=1234, output_tokens=7)),
    )
    out = await run(agents, row["id"])
    assert out["state"] == "failed"
    r = await su.fetchrow(
        "SELECT input_tokens, output_tokens FROM agents.runs WHERE id = $1", row["id"]
    )
    assert (r["input_tokens"], r["output_tokens"]) == (1234, 7)


class _Orig(Exception):
    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.sqlstate = state


async def test_book_treats_only_no_budget_left_as_the_end_of_the_budget() -> None:
    def runner_failing_with(state: str) -> R.Runner:
        class Tx:
            async def exec(self, sql: str, **_: Any) -> int:
                if "work.work" in sql:
                    raise DBAPIError("UPDATE work.work", {}, _Orig(state))
                return 1

        class Db:
            @asynccontextmanager
            async def tx(self, _ids: Any) -> AsyncIterator[Tx]:
                yield Tx()

        class Companies:
            async def ids(self) -> list[Any]:
                return []

        hub = SimpleNamespace(settings=SimpleNamespace(), db=Db(), companies=Companies())
        return R.Runner(hub, None, None)  # type: ignore[arg-type]

    def rc() -> R.RunCtx:
        return R.RunCtx(
            run={"id": uuid.uuid4(), "work_id": uuid.uuid4(), "token_cap": 5000},
            emp={},
            # The run's cap never exceeds its charter's (prompt 08 §2.3).
            charter=SimpleNamespace(limits=SimpleNamespace(tokens_per_run=200_000)),  # type: ignore[arg-type]
            token="",
        )

    call = ModelCall(True, "ok", None, None, None, None, None, None, None, input_tokens=100)
    ctx = rc()
    await runner_failing_with("HQB01")._book(ctx, call)
    assert ctx.used_tokens == 5000  # no budget left: the run stops spending
    with pytest.raises(DBAPIError):
        await runner_failing_with("23514")._book(rc(), call)


async def test_claim_refuses_closed_or_spent_work(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    (row,) = await runs_of(su, f"{co}-CEO")
    r = await client.post(
        f"/api/v1/work/{w['id']}/cancel", headers={**owner, **idem()}, json={"reason": "لغو"}
    )
    assert r.status_code == 200, r.text
    claim = await agents.runner.claim(str(row["id"]))
    assert (claim.state, claim.code) == ("final", "work_closed")
    w2 = await order(client, owner, co, title="دلاری", budget={"usd": "0.5"})
    row2 = (await runs_of(su, f"{co}-CEO"))[-1]
    await su.execute("UPDATE work.work SET usd_used = 0.5 WHERE id = $1", uuid.UUID(w2["id"]))
    claim = await agents.runner.claim(str(row2["id"]))
    assert (claim.state, claim.code) == ("final", "budget_used_up")


async def test_agent_requests_get_a_budget_and_a_bounded_chain(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Any,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w0 = await order(client, owner, co, budget={"tokens": 50_000})
    ceo = await agent_headers(f"{co}-CEO")

    async def request(origin: str, **extra: Any) -> httpx.Response:
        return await client.post(
            "/internal/v1/work",
            headers={**ceo, **idem()},
            json={
                "department": "TECH",
                "title": "درخواست",
                "requested_by_work_id": origin,
                **extra,
            },
        )

    r1 = await request(w0["id"])
    assert r1.status_code == 201, r1.text
    w1 = r1.json()["work"]
    assert w1["budget"]["tokens"] == 50_000  # what the requester had left
    r = await request(w0["id"], budget={"tokens": 10**9})
    assert r.status_code == 201
    assert r.json()["work"]["budget"]["tokens"] <= hub.settings.agent_request_budget_tokens
    r2 = await request(w1["id"])
    assert r2.status_code == 201, r2.text
    w2 = r2.json()["work"]
    r3 = await request(w2["id"])
    assert r3.status_code == 409 and r3.json()["code"] == "delegation_depth_exceeded"
    # Nothing left to hand on: refused, never a work item with a zero budget.
    spent = await order(client, owner, co, title="تمام‌شده", budget={"tokens": 1_000})
    await su.execute(
        "UPDATE work.work SET tokens_used = 1000 WHERE id = $1", uuid.UUID(spent["id"])
    )
    r4 = await request(spent["id"])
    assert r4.status_code == 409 and r4.json()["code"] == "budget_exceeded", r4.text


# ------------------------------------------------------------- §2.7 usage --
async def test_a_deliverables_usage_is_its_runs_ledger(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    (row,) = await runs_of(su, f"{co}-CEO")
    agents.fake.enqueue(
        f"{co}-CEO",
        step("بررسی", ("work.get", {"ref": w["ref"]}), done=False),
        step(
            "تحویل",
            (
                "deliver",
                {"work_ref": w["ref"], "title_fa": "گزارش", "body_md": "متن"},
            ),
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    dl = await su.fetchrow(
        "SELECT usage, produced_with FROM cartable.deliverables WHERE work_id = $1",
        uuid.UUID(w["id"]),
    )
    usage, produced = json.loads(dl["usage"]), json.loads(dl["produced_with"])
    ledger = await su.fetchrow(
        """SELECT sum(input_tokens) AS i, sum(output_tokens) AS o, count(*) AS n
           FROM llm.calls WHERE meta->>'run_id' = $1""",
        str(row["id"]),
    )
    assert ledger["n"] == 2
    assert (usage["input_tokens"], usage["output_tokens"]) == (ledger["i"], ledger["o"])
    assert produced["connection"] and produced["provider"] and produced["model"]
    # Straight through the internal API with a registered run: the agent's own
    # figures are ignored (that run has no ledger rows: zero).
    w2 = await order(client, owner, co, title="مستقیم")
    r = await client.post(
        f"/internal/v1/work/{w2['id']}/deliver",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={
            "title": "خروجی",
            "body": "متن",
            "usage": {"input_tokens": 999_999, "cost_usd": "12.5"},
            "produced_with": {"model": "made-up"},
        },
    )
    assert r.status_code == 200, r.text
    dl = await su.fetchrow(
        "SELECT usage, produced_with FROM cartable.deliverables WHERE ref = $1",
        r.json()["deliverable"],
    )
    assert json.loads(dl["usage"])["input_tokens"] == 0
    assert "made-up" not in dl["produced_with"]


async def test_done_next_to_a_refused_argument_gets_one_more_step(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    """A model that says `done` in the step whose deliver was refused for its
    arguments (as a real run did on the hub, 2026-10-17) sees the field errors
    and fixes them in the next step; the output is not lost."""
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    (row,) = await runs_of(su, f"{co}-CEO")
    bad = {"work_ref": w["ref"], "title_fa": "گزارش", "body_md": "متن کامل"}
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        f"{co}-CEO",
        step("تحویل", ("deliver", {**bad, "evidence": [{"kind": "tool", "ref": "health.hub"}]})),
        step(
            "تحویل درست", ("deliver", {**bad, "evidence": [{"kind": "log", "ref": "health.hub"}]})
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", row["id"]) == 2
    second = _prompts(agents, f"{co}-CEO", since + 1)
    assert "invalid_args" in second and "evidence" in second
    body = await su.fetchval(
        "SELECT body FROM cartable.deliverables WHERE work_id = $1", uuid.UUID(w["id"])
    )
    assert body == "متن کامل"


async def test_secrets_at_the_start_of_a_line_and_under_keys_never_reach_the_model(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    """Review of 5.1 (blocker 1): records are masked as values before they
    become JSON, where a line break turns into "\\n" right before a secret; a
    value under a secret key (mobile_number) is masked whatever it looks like."""
    co = (await new_company())["code"]
    line_starts = [
        "sk-" + "ant-" + "api03-" + "Qw8" * 14,
        "ghp_" + "Zx7" * 12,
        "AKIA" + "QWERTYUIOPASDFGH",
        "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjMifQ" + "." + "s1gN4tur3" * 3,
        "hvs." + "R4t" * 9,
        "Bearer " + "t0k" * 8,
    ]
    w = await order(
        client, owner, co, title="کار خط‌به‌خط", brief="\n".join(["سطر اول", *line_starts])
    )
    phone = "۰۹۱۲" + "۷۶۵" + "۴۳۲۱"
    card = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},  # not the CEO: it runs next
        json={
            "kind": "deploy",
            "title": "deploy",
            "payload": {
                "repo": "x/y",
                "pr_url": "https://example.com/pr/1",
                "head_sha": "0123abc",  # ⟨1.5⟩ required (prompt 11/12 §7)
                "ci": {"mobile_number": phone, "note": "ok"},
            },
        },
    )
    assert card.status_code == 201, card.text
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "این کارت را ببین", "links": {"decision": card.json()["ref"]}},
    )
    assert r.status_code == 201, r.text
    runs = await runs_of(su, f"{co}-CEO")
    since = len(agents.fake.calls)
    for row in runs:
        if row["state"] == "queued":
            agents.fake.enqueue(f"{co}-CEO", step("خواندم"))
            await run(agents, row["id"])
    seen = _prompts(agents, f"{co}-CEO", since)
    assert "کار خط‌به‌خط" in seen and "# Decision card to review" in seen
    for s in [*line_starts, phone]:
        assert s not in seen, s
    assert w["ref"] in seen
