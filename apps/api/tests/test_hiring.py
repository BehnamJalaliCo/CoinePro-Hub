"""Prompt 5.1 §1.3: hiring starts with the owner (contract §18.11, v1.4.2)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import bootstrap
from hq_api.domain import hiring
from hq_api.domain import work as W

from .conftest import API_DIR, HOST, agent_headers, body_bytes, idem, step_up

pytestmark = pytest.mark.usefixtures("relay")


def _hire(co: str, n: int = 0) -> dict[str, Any]:
    return {
        "kind": "hire",
        "title": f"استخدام {n}",
        "payload": {
            "company": co,
            "department": "TECH",
            "role": "sre",
            "title_fa": f"کارشناس {n}",
            "title_en": "Specialist",
            "reason": "need",
            "model": "claude-sonnet-5-5",
            "effort": "low",
        },
    }


def _alembic(*args: str) -> None:
    env = {
        **os.environ,
        "DB_HOST": HOST,
        "DB_USER": "hq",
        "DB_PASSWORD": os.environ["HQ_DB_PASSWORD"],
        "PYTHONPATH": "/w/hq-common/src:/api/src",
        "LOG_LEVEL": "warning",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]


async def _set_hiring(su: Any, state: str) -> None:
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode)
           SELECT id, $1, CASE WHEN $1 = 'open' THEN 'proposals' END FROM core.companies
           WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET state = EXCLUDED.state, mode = EXCLUDED.mode""",
        state,
    )


# ------------------------------------------------------------- migration --
@pytest.fixture
def reseeded() -> Any:
    """The round trip below recreates every table after 0009 empty; the seed
    runs again afterwards, as the api's migrate does on a deploy (prompt 12's
    substitute players, prompt 11's meeting types and the rest), so the tests
    after this one find the hub as it is."""
    from .conftest import _run

    yield
    _run("hq_api.migrate", API_DIR, "hq", "HQ_DB_PASSWORD", "/api/src")


@pytest.mark.usefixtures("reseeded")
async def test_migration_withdraws_pending_hire_cards_once(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    mgr = await agent_headers(f"{co}-TECH-MGR")
    await _set_hiring(su, "open")
    refs = []
    for n in range(7):
        r = await client.post(
            "/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, n)
        )
        assert r.status_code == 201, r.text
        refs.append(r.json()["ref"])
    # Cards that must not move: a decided hire card and a pending card of another kind.
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, 99))
    decided = r.json()["ref"]
    r = await client.post(
        f"/api/v1/decisions/{decided}/reject", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"kind": "proposal", "title": "پیشنهاد", "payload": {}},
    )
    other = r.json()["ref"]
    untouched = (
        """SELECT ref, status, version FROM cartable.decisions WHERE ref = ANY($1) ORDER BY ref"""
    )
    kept = [dict(x) for x in await su.fetch(untouched, [decided, other])]
    await _set_hiring(su, "closed")
    # A month-1 setup item still open, with an open child: both cancelled by the
    # migrations, their queued runs refused.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await bootstrap.apply(tx, bootstrap.load("month1"), charters=hub.charters)
        mine = [c["ref"] for c in out["created"] if c["assignee"] == f"{co}-TECH-MGR"]
        assert len(mine) == 1
        parent = await W.load(
            tx, await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=mine[0])
        )
        child = await W.create(
            tx,
            bootstrap.BOOTSTRAP,
            company_id=parent["company_id"],
            company_code=co,
            title="بخش فرزند",
            brief="",
            kind="one_off",
            priority="P3",
            assignee_code=f"{co}-TECH-MGR",
            parent=parent,
        )
    before = await su.fetchval("SELECT count(*) FROM cartable.decisions")

    _alembic("downgrade", "0009")
    _alembic("upgrade", "head")

    rows = await su.fetch(
        "SELECT ref, status, decided_by_kind, decided_by_code, note FROM cartable.decisions WHERE ref = ANY($1)",
        refs,
    )
    assert {(r["status"], r["decided_by_code"], r["note"]) for r in rows} == {
        ("withdrawn", "system", hiring.NOTE)
    }
    assert len(rows) == 7 and await su.fetchval("SELECT count(*) FROM cartable.decisions") == before
    assert not await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE kind = 'hire' AND status = 'pending'"
    )
    withdrawn = await su.fetchval(
        "SELECT withdrawn FROM core.hiring h JOIN core.companies c ON c.id = h.company_id WHERE c.kind = 'holding'"
    )
    assert set(refs) <= set(withdrawn)
    events = await su.fetch(
        "SELECT payload FROM core.outbox WHERE subject LIKE '%.decision.updated' AND payload->>'ref' = ANY($1)",
        refs,
    )
    assert len(events) == 7
    assert {json.loads(e["payload"])["data"]["status"] for e in events} == {"withdrawn"}
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'decision.withdraw' AND target_ref = ANY($1)",
            refs,
        )
        == 7
    )
    w = await su.fetchrow("SELECT status, close_reason FROM work.work WHERE ref = $1", mine[0])
    assert (w["status"], w["close_reason"]) == ("cancelled", hiring.NOTE)
    c = await su.fetchrow("SELECT status, close_reason FROM work.work WHERE id = $1", child["id"])
    assert (c["status"], c["close_reason"]) == ("cancelled", hiring.NOTE)
    assert [dict(x) for x in await su.fetch(untouched, [decided, other])] == kept
    # decision.decided (status withdrawn) is what clients follow (§7), once per card.
    decided_events = await su.fetch(
        """SELECT payload FROM core.outbox WHERE subject LIKE '%.decision.decided'
             AND payload->>'ref' = ANY($1) AND payload->'data'->>'status' = 'withdrawn'""",
        refs,
    )
    assert len(decided_events) == 7
    assert not await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE w.ref = $1 AND r.state = 'queued'""",
        mine[0],
    )
    # Run again: nothing left to change.
    versions = {
        r["ref"]: r["version"]
        for r in await su.fetch(
            "SELECT ref, version FROM cartable.decisions WHERE ref = ANY($1)", refs
        )
    }
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await hiring.withdraw_pending(tx) == []
    _alembic("downgrade", "0009")
    _alembic("upgrade", "head")
    assert {
        r["ref"]: r["version"]
        for r in await su.fetch(
            "SELECT ref, version FROM cartable.decisions WHERE ref = ANY($1)", refs
        )
    } == versions
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'decision.withdraw' AND target_ref = ANY($1)",
            refs,
        )
        == 7
    )


# ------------------------------------------------------------------ gate --
async def test_agents_cannot_propose_a_hire_while_hiring_is_closed(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    for who in (f"{co}-TECH-MGR", f"{co}-CEO"):
        r = await client.post(
            "/internal/v1/decisions",
            headers={**await agent_headers(who), **idem()},
            json=_hire(co),
        )
        assert r.status_code == 403 and r.json()["code"] == "hiring_closed", r.text
        assert "استخدام بسته است" in r.json()["message_fa"]
    assert not await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE company_id = $1", company["id"]
    )
    # Every other kind is unaffected.
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"kind": "proposal", "title": "پیشنهاد", "payload": {}},
    )
    assert r.status_code == 201, r.text


async def test_company_state_tells_agents_the_hiring_state(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    h = await agent_headers(f"{co}-CEO")
    r = await client.get("/internal/v1/company/state", headers=h)
    assert r.status_code == 200 and r.json()["hiring"] == "closed"
    await _set_hiring(su, "open")
    try:
        assert (await client.get("/internal/v1/company/state", headers=h)).json()[
            "hiring"
        ] == "open"
        r = await client.get(
            "/internal/v1/company/state", headers=await agent_headers("HQ-OVS-MGR")
        )
        assert r.json()["hiring"] == "open" and r.json()["companies"]
    finally:
        await _set_hiring(su, "closed")


# ----------------------------------------------------------------- start --
async def test_start_needs_its_step_up_and_proposals_wake_each_head_once(
    client: httpx.AsyncClient, hub: Any, su: Any, owner_session: dict[str, Any]
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    assert (
        await client.post("/api/v1/owner/hiring/start", json={"mode": "proposals"})
    ).status_code == 401
    r = await client.post("/api/v1/owner/hiring/start", headers=h, json={"mode": "proposals"})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, sid, "hiring.start", "TY")
    r = await client.post(
        "/api/v1/owner/hiring/start", headers={**h, **wrong}, json={"mode": "proposals"}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    agent = await agent_headers("HQ-OVS-MGR")
    r = await client.post("/api/v1/owner/hiring/start", headers=agent, json={"mode": "proposals"})
    assert r.status_code == 403
    tagged = """SELECT count(*) FROM work.work_events
                WHERE kind = 'bootstrap' AND data->>'tag' LIKE 'bootstrap:hiring_proposals:%'"""
    before = await su.fetchval(tagged)
    try:
        su_h = await step_up(hub, sid, "hiring.start", "holding")
        r = await client.post(
            "/api/v1/owner/hiring/start", headers={**h, **su_h}, json={"mode": "proposals"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "open" and body["mode"] == "proposals"
        assert body["changed_by"]["kind"] == "owner"
        items = bootstrap.load(hiring.PROPOSALS_KEY)["items"]
        heads = 0
        for item in items:
            heads += await su.fetchval(
                """SELECT count(DISTINCT c.id) FROM core.employees e
                   JOIN core.companies c ON c.id = e.company_id
                   WHERE e.status = 'active' AND e.role = $1 AND c.kind = $2""",
                item["role"],
                {"companies": "company", "holding": "holding"}[item["for"]],
            )
        made = await su.fetchval(tagged)
        assert made == heads and len(body["work"]) == heads - before  # one per head
        ceo_item = await su.fetchrow(
            """SELECT w.priority, w.budget_tokens, w.created_by_kind FROM work.work w
               JOIN work.work_events e ON e.work_id = w.id
               WHERE e.data->>'tag' = 'bootstrap:hiring_proposals:ceo' LIMIT 1"""
        )
        assert ceo_item["priority"] == hub.charters.roles["ceo"].priority
        ceo_budget = next(i["budget_tokens"] for i in items if i["role"] == "ceo")
        assert ceo_item["created_by_kind"] == "owner" and ceo_item["budget_tokens"] == ceo_budget
        # Starting again adds nothing.
        su_h = await step_up(hub, sid, "hiring.start", "holding")
        r = await client.post(
            "/api/v1/owner/hiring/start", headers={**h, **su_h}, json={"mode": "proposals"}
        )
        assert r.status_code == 200 and r.json()["work"] == []
        assert await su.fetchval(tagged) == heads
        events = await su.fetch(
            "SELECT payload FROM core.outbox WHERE subject LIKE '%.hiring.changed' ORDER BY id DESC LIMIT 2"
        )
        assert {json.loads(e["payload"])["data"]["state"] for e in events} == {"open"}
    finally:
        r = await client.post("/api/v1/owner/hiring/close", headers=h)
        assert r.status_code == 200 and r.json()["state"] == "closed"


# ----------------------------------------------------------------- close --
async def test_close_withdraws_pending_hire_cards(
    client: httpx.AsyncClient, su: Any, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    await _set_hiring(su, "open")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},
        json=_hire(co),
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    r = await client.post("/api/v1/owner/hiring/close", headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "closed" and ref in r.json()["withdrawn"]
    d = (await client.get(f"/api/v1/decisions/{ref}", headers=owner)).json()
    assert d["status"] == "withdrawn" and d["note"] == hiring.NOTE
    assert d["decided_by"]["code"] == "system"
    assert (await client.get("/api/v1/owner/hiring", headers=owner)).json()["state"] == "closed"
    msgs = (await client.get(f"/api/v1/threads/{co}-TECH-MGR/messages", headers=owner)).json()
    assert ref in msgs["items"][-1]["body"]


# ----------------------------------------------------------- direct hire --
async def test_owner_hires_directly_with_a_body_bound_step_up(
    client: httpx.AsyncClient,
    hub: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    body = {
        "company": co,
        "department": "TECH",
        "role": "sre",
        "title_fa": "کارشناس پایداری",
        "quota_estimate_month": {"tokens": 150000},  # >= the charter's tokens_per_run (v1.4.3)
    }
    content = body_bytes(body)
    target = hashlib.sha256(content).hexdigest()

    async def post(content: bytes, extra: dict[str, str]) -> httpx.Response:
        return await client.post(
            "/api/v1/org/hires",
            content=content,
            headers={**h, **extra, "Content-Type": "application/json"},
        )

    other = body_bytes({**body, "title_fa": "کس دیگر"})
    r = await post(other, await step_up(hub, sid, "hire.direct", target))
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    r = await post(content, await step_up(hub, sid, "hire.direct", target))
    assert r.status_code == 201, r.text
    out = r.json()
    d, e = out["decision"], out["employee"]
    sre = hub.charters.roles["sre"]
    assert d["status"] == "approved" and d["kind"] == "hire" and d["resolution"].startswith("M-")
    assert d["proposer"]["kind"] == "owner" and d["decided_by"]["kind"] == "owner"
    assert d["seal"]["method"] == "passkey_uv" and d["effect_status"] == "applied"
    assert d["payload"]["model"] == sre.model and d["payload"]["effort"] == sre.effort
    assert d["payload"]["title_en"] == sre.title_en and d["payload"]["reason"]
    assert e["status"] == "active" and e["code"] == f"{co}-TECH-01"
    assert e["charter"] == {"role": "sre", "version": sre.version}
    assert e["hired_by_decision"] == d["ref"] and e["reports_to"]["code"] == f"{co}-TECH-MGR"
    # A role that does not fit the company or the department: 422 (step-up untouched).
    for bad in (
        {**body, "department": "GROWTH"},
        {**body, "role": "inspector"},
        {**body, "role": "nobody_here"},
    ):
        c = body_bytes(bad)
        su_h = await step_up(hub, sid, "hire.direct", hashlib.sha256(c).hexdigest())
        r = await post(c, su_h)
        assert r.status_code == 422, (bad, r.text)
    # An agent may not.
    r = await client.post(
        "/api/v1/org/hires",
        content=content,
        headers={**await agent_headers(f"{co}-CEO"), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


async def test_direct_hire_reports_to_and_validation(
    client: httpx.AsyncClient,
    hub: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    body = {
        "company": co,
        "department": "TECH",
        "role": "sre",
        "title_fa": "کارشناس",
        "title_en": "Engineer",
        "model": "claude-sonnet-5-5",
        "effort": "medium",
        "reason": "آزمایش",
        "duties": ["پایش"],
        "reports_to": f"{co}-CEO",
        "quota_estimate_month": {"tokens": 150000},
    }
    content = body_bytes(body)
    su_h = await step_up(hub, sid, "hire.direct", hashlib.sha256(content).hexdigest())
    r = await client.post(
        "/api/v1/org/hires",
        content=content,
        headers={**h, **su_h, "Content-Type": "application/json"},
    )
    assert r.status_code == 201, r.text
    e = r.json()["employee"]
    assert e["reports_to"]["code"] == f"{co}-CEO" and e["model"]["effort"] == "medium"
    assert r.json()["decision"]["quota_estimate"]["tokens"] == 150000
    bad = body_bytes({**body, "reports_to": f"{co}-NOPE-01"})
    su_h = await step_up(hub, sid, "hire.direct", hashlib.sha256(bad).hexdigest())
    r = await client.post(
        "/api/v1/org/hires", content=bad, headers={**h, **su_h, "Content-Type": "application/json"}
    )
    assert r.status_code == 422 and "payload.reports_to" in r.json()["fields"]


# ---------------------------------------------------------- v1.4.3 shape --
async def test_delegated_without_envelopes_spends_no_step_up(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    """Prompt 8 §8: `delegated` needs every active operating company's monthly
    envelope; without one: 422 envelope_required naming it, nothing spent."""
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    await su.execute(
        """DELETE FROM llm.budgets b USING core.companies c
           WHERE c.id = b.company_id AND c.code = $1 AND b.scope_type = 'company'""",
        co,
    )
    su_h = await step_up(hub, sid, "hiring.start", "holding")
    r = await client.post(
        "/api/v1/owner/hiring/start", headers={**h, **su_h}, json={"mode": "delegated"}
    )
    assert (r.status_code, r.json()["code"]) == (422, "envelope_required")
    assert co in r.json()["fields"]["envelopes"]
    assert (await client.get("/api/v1/owner/hiring", headers=h)).json()["state"] == "closed"
    r = await client.post(
        "/api/v1/owner/hiring/start", headers={**h, **su_h}, json={"mode": "self"}
    )
    assert r.status_code == 422  # v1.4.3: delegated | proposals
    try:
        key = idem()
        r = await client.post(
            "/api/v1/owner/hiring/start",
            headers={**h, **su_h, **key},
            json={"mode": "proposals"},
        )
        assert r.status_code == 200, r.text  # the same step-up: never consumed above
        again = await client.post(
            "/api/v1/owner/hiring/start",
            headers={**h, **su_h, **key},
            json={"mode": "proposals"},
        )
        assert again.status_code == 200 and again.json() == r.json()  # replayed, not 403
    finally:
        await client.post("/api/v1/owner/hiring/close", headers=h)


async def test_hiring_shows_each_companys_envelope(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    company = await new_company()
    co = company["code"]
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', 2000000)""",
        company["id"],
        co,
    )
    body = {
        "company": co,
        "department": "TECH",
        "role": "sre",
        "title_fa": "کارشناس",
        "quota_estimate_month": {"tokens": 150000},
    }
    content = body_bytes(body)
    su_h = await step_up(hub, sid, "hire.direct", hashlib.sha256(content).hexdigest())
    headers = {**h, **su_h, **idem(), "Content-Type": "application/json"}
    r = await client.post("/api/v1/org/hires", content=content, headers=headers)
    assert r.status_code == 201, r.text
    # A retry after a lost answer gets the same answer (the step-up is single-use).
    again = await client.post("/api/v1/org/hires", content=content, headers=headers)
    assert again.status_code == 201 and again.json() == r.json()
    assert r.json()["decision"]["approver"] is None  # the owner decides (§5.1)
    assert r.json()["employee"]["probation_until"] is None  # not a delegated hire
    env = {
        e["company"]: e
        for e in (await client.get("/api/v1/owner/hiring", headers=h)).json()["envelopes"]
    }
    assert env[co] == {
        "company": co,
        "tokens_month": 2000000,
        "committed_month": 150000,
        "used_month": 0,
        "hires_month": 1,
    }
    holding = (await hub.companies.holding()).code
    assert holding not in env  # operating companies only


async def test_a_close_waits_for_a_hire_proposal_in_flight(
    hub: Any, su: Any, new_company: Callable[..., Any]
) -> None:
    """Review of 5.1: the proposing transaction reads the state FOR SHARE, so a
    close committing meanwhile waits, then withdraws the card: no pending hire
    card outlives a close."""
    from hq_api.domain import decisions as D
    from hq_api.principal import Principal

    company = await new_company()
    co = company["code"]
    await _set_hiring(su, "open")
    holding = await hub.companies.holding()
    agent = Principal(
        kind="agent",
        code=f"{co}-TECH-MGR",
        role="manager",
        company=co,
        company_id=company["id"],
    )
    owner_p = Principal(kind="owner", code="owner", role="owner")
    ids = await hub.companies.ids()

    async def close() -> list[str]:
        async with hub.db.tx(ids) as tx2:
            return await hiring.close(
                tx2, owner_p, holding_id=holding.id, holding_code=holding.code
            )

    async with hub.db.tx(ids) as tx1:
        await hiring.require_open(tx1, agent, "hire")
        closing = asyncio.create_task(close())
        await asyncio.sleep(0.5)
        assert not closing.done()  # waits for the proposal
        d = await D.propose(
            tx1,
            agent,
            company_id=company["id"],
            company_code=co,
            body=D.DecisionIn(**_hire(co)),
            thread_code=None,
            charters=hub.charters,
            company_kind="company",
        )
    refs = await asyncio.wait_for(closing, 10)
    assert d["ref"] in refs
    assert await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", d["ref"]) == (
        "withdrawn"
    )


async def test_a_retried_hire_proposal_while_closed_answers_the_same(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    h = {**await agent_headers(f"{co}-TECH-MGR"), **idem()}
    first = await client.post("/internal/v1/decisions", headers=h, json=_hire(co))
    again = await client.post("/internal/v1/decisions", headers=h, json=_hire(co))
    assert [x.json()["code"] for x in (first, again)] == ["hiring_closed", "hiring_closed"]
