"""Prompt 8.1 (the review of prompt 8, contract §18.15): hiring under the
per-company lock, `hire.decide` only while delegated, protocol and
lesson_adoption cards, stories' links, the owner's welcome in the score,
rubric weights as numbers, half stars, a cancelled errand's card."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest

from hq_api.domain import decisions as D
from hq_api.domain import oversight as O
from hq_api.domain import scoring
from hq_api.domain import stars as S
from hq_api.domain import stories as ST
from hq_api.principal import Principal
from hq_common import charters

from .conftest import agent_headers, idem, step_up
from .test_people import PAST_WEEK, RUBRIC, _end_test_runs, _envelope, _hire

pytestmark = pytest.mark.usefixtures("relay", "no_watch")
SYSTEM = Principal(kind="service", code="system", role="system")


@pytest.fixture
async def no_watch(su: Any) -> AsyncIterator[None]:
    """Watch mode off (it holds high-risk cards; these tests decide them)."""
    await su.execute("UPDATE oversight.watch SET until = now() WHERE until IS NULL")
    yield


@pytest.fixture(autouse=True)
async def seeded(hub: Any, owner_db: Any) -> None:
    """The protocols (PR-080, PR-098): another file's migration round trip
    drops them for the rest of the session."""
    holding = await hub.companies.holding()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await O.seed_protocols(tx, holding.id, charters.load().root)


@pytest.fixture
async def delegated(
    client: httpx.AsyncClient, hub: Any, su: Any, owner_session: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    """Hiring opened `delegated`, every active operating company with an envelope."""
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           SELECT id, 'company', code, 'month', 50000000 FROM core.companies
           WHERE kind = 'company' AND status = 'active'
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET token_limit = 50000000, enabled = true"""
    )
    h, sid = owner_session["headers"], owner_session["session_id"]
    su_h = await step_up(hub, sid, "hiring.start", "holding")
    r = await client.post(
        "/api/v1/owner/hiring/start", headers={**h, **su_h}, json={"mode": "delegated"}
    )
    assert r.status_code == 200, r.text
    try:
        yield owner_session
    finally:
        await client.post("/api/v1/owner/hiring/close", headers=h)


async def _card(client: httpx.AsyncClient, co: str, estimate: int, n: int) -> str:
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, estimate, n)
    )
    assert r.status_code == 201, r.text
    assert r.json()["approver"]["code"] == f"{co}-CEO"
    return str(r.json()["ref"])


async def _decide(client: httpx.AsyncClient, ceo: dict[str, str], ref: str) -> httpx.Response:
    return await client.post(
        f"/internal/v1/hires/{ref}/decide", headers={**ceo, **idem()}, json={"verdict": "approve"}
    )


# ----------------------------------------------------------------- §1.4 --
async def test_two_approvals_over_the_envelope_one_is_refused(
    client: httpx.AsyncClient,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    """Two cards of 3M on a 5M envelope, approved at the same time: the lock
    makes the second count the first (approved, employee not made yet)."""
    company = await new_company()
    co = company["code"]
    await _envelope(su, company, 5_000_000)
    a, b = await _card(client, co, 3_000_000, 1), await _card(client, co, 3_000_000, 2)
    ceo = await agent_headers(f"{co}-CEO")
    got = await asyncio.gather(_decide(client, ceo, a), _decide(client, ceo, b))
    assert sorted(r.status_code for r in got) == [200, 409], [r.text for r in got]
    refused = next(r for r in got if r.status_code == 409)
    assert refused.json()["code"] == "envelope_exceeded"
    # Approved, no employee yet (the effect is the worker's): already committed.
    env = (await client.get("/api/v1/owner/hiring", headers=delegated["headers"])).json()
    mine = next(e for e in env["envelopes"] if e["company"] == co)
    assert mine["committed_month"] == 3_000_000
    # Sequentially too: a third card of 3M is refused before any effect ran.
    c = await _card(client, co, 3_000_000, 3)
    r = await _decide(client, ceo, c)
    assert (r.status_code, r.json()["code"]) == (409, "envelope_exceeded")
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO")


async def test_the_sixth_hire_of_the_day_is_refused_under_the_lock(
    client: httpx.AsyncClient,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await _envelope(su, company)
    for n in range(4):
        await su.execute(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
                   proposer_code, status, decided_at, payload)
               VALUES ($1, 'hire', 'A2', $2, 'agent', $3, 'approved', now(), '{}')""",
            company["id"],
            f"seed {n}",
            f"{co}-TECH-MGR",
        )
    a, b = await _card(client, co, 1_000_000, 5), await _card(client, co, 1_000_000, 6)
    ceo = await agent_headers(f"{co}-CEO")
    got = await asyncio.gather(_decide(client, ceo, a), _decide(client, ceo, b))
    assert sorted(r.status_code for r in got) == [200, 429], [r.text for r in got]
    assert next(r for r in got if r.status_code == 429).json()["code"] == "rate_limited"
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO")


# ----------------------------------------------------------------- §2.8 --
async def test_proposals_mode_returns_cards_to_the_owner_and_stops_hire_decide(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = delegated["headers"], delegated["session_id"]
    company = await new_company()
    co = company["code"]
    await _envelope(su, company)
    ref = await _card(client, co, 1_000_000, 1)
    item = f"%{ref}%"
    open_items = """SELECT count(*) FROM work.work WHERE title LIKE $1
                    AND status IN ('queued', 'in_progress', 'waiting')"""
    assert await su.fetchval(open_items, item) == 1
    r = await client.post(
        "/api/v1/owner/hiring/start",
        headers={**h, **await step_up(hub, sid, "hiring.start", "holding")},
        json={"mode": "proposals"},
    )
    assert r.status_code == 200 and r.json()["mode"] == "proposals", r.text
    card = (await client.get(f"/api/v1/decisions/{ref}", headers=h)).json()
    assert card["approver"] is None and card["status"] == "pending"
    mine = (await client.get("/api/v1/decisions", headers=h, params={"company": co})).json()
    assert ref in [d["ref"] for d in mine["items"]]  # back in the owner's cartable
    assert await su.fetchval(open_items, item) == 0  # the CEO's «decide D-…» item is closed
    ceo = await agent_headers(f"{co}-CEO")
    r = await _decide(client, ceo, ref)
    assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    # The owner approves it: the owner's hire (no probation, no «… استخدام کرد»).
    seal = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
    assert (
        await su.fetchval("SELECT probation_until FROM core.employees WHERE code = $1", emp) is None
    )
    assert not await su.fetchval(
        """SELECT count(*) FROM notify.notifications
           WHERE link_kind = 'employee' AND link_ref = $1 AND title_fa LIKE '%استخدام کرد%'""",
        emp,
    )
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO")


async def test_a_card_the_owner_approves_first_is_the_owners_hire(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = delegated["headers"], delegated["session_id"]
    company = await new_company()
    co = company["code"]
    await _envelope(su, company)
    ref = await _card(client, co, 1_000_000, 1)
    seal = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    assert not await su.fetchval(
        """SELECT count(*) FROM work.work WHERE title LIKE $1
           AND status IN ('queued', 'in_progress', 'waiting')""",
        f"%{ref}%",
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
    row = await su.fetchrow("SELECT probation_until FROM core.employees WHERE code = $1", emp)
    assert row["probation_until"] is None
    assert not await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_kind = 'employee' AND link_ref = $1",
        emp,
    )
    assert await su.fetchval(  # the hire story is every hire's
        "SELECT count(*) FROM owner.stories WHERE event_key = $1", f"hire:{ref}"
    )
    # The welcome is a small positive part of the employee's score (§18.15).
    await su.execute(
        """INSERT INTO work.work (company_id, department_id, kind, title, created_by_kind,
               created_by_code, assignee_id, status, closed_at, evidence)
           SELECT e.company_id, e.department_id, 'one_off', t.title, 'owner', 'owner', e.id, t.st,
                  now(), '[{"kind": "log", "ref": "test"}]'::jsonb
           FROM core.employees e, (VALUES ('ok', 'done'), ('no', 'failed')) AS t(title, st)
           WHERE e.code = $1""",
        emp,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        dept = await tx.scalar("SELECT department_id FROM core.employees WHERE code = :c", c=emp)
        await scoring.recompute_department(tx, dept)
    before = await su.fetchval("SELECT score FROM core.employees WHERE code = $1", emp)
    assert before == Decimal("5.00")  # one done, one failed
    story = await su.fetchval("SELECT ref FROM owner.stories WHERE event_key = $1", f"hire:{ref}")
    r = await client.post(f"/api/v1/stories/{story}/welcome", headers=h)
    assert r.status_code == 200 and r.json()["welcomed"], r.text
    row = await su.fetchrow(
        "SELECT score, score_components FROM core.employees WHERE code = $1", emp
    )
    assert row["score"] == Decimal("5.20")
    assert json.loads(row["score_components"])["owner_welcome"] == scoring.WELCOME_BONUS
    assert scoring.with_welcome(9.95, True) == 10.0 and scoring.with_welcome(None, True) is None
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO")


async def test_pr098_review_only_while_the_protocol_is_active(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await _envelope(su, company)
    ref = await _card(client, co, 1_000_000, 1)
    ceo = await agent_headers(f"{co}-CEO")
    assert (await _decide(client, ceo, ref)).status_code == 200
    owner = Principal(kind="owner", code="owner", role="owner")

    async def pause(tx: Any, protocol: str) -> None:
        current = await O.load_protocol(tx, protocol)
        holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
        fields = {k: current[k] for k in O.ProtocolIn.model_fields}
        await O.new_version(
            tx, owner, holding, {**fields, "status": "paused"}, ref=protocol, source="owner"
        )

    class Undo(Exception):
        """Rolls the test's transaction back: the protocols stay as they were."""

    with pytest.raises(Undo):
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await pause(tx, "PR-098")
            emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
            reviews = await tx.scalar(
                "SELECT count(*) FROM work.work WHERE title LIKE :t", t=f"%{emp}%PR-098%"
            )
            assert reviews == 0  # PR-098 paused: no review item
            # Inflation while PR-080 is paused: no finding either.
            await pause(tx, "PR-080")
            await S.star_inflation(tx, co, "week", PAST_WEEK.isoformat())
            assert not await tx.scalar(
                "SELECT count(*) FROM oversight.findings WHERE company_id = :co", co=company["id"]
            )
            raise Undo
    async with hub.db.tx(await hub.companies.ids()) as tx:  # active again: both run
        assert (await O.protocol_in_force(tx, "PR-098")) is not None
        emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
        assert await tx.scalar(
            "SELECT count(*) FROM work.work WHERE title LIKE :t", t=f"%{emp}%PR-098%"
        )
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO")


# ----------------------------------------------------------------- §2.1 --
async def test_the_overseer_proposes_a_protocol_and_the_owner_seals_it(
    client: httpx.AsyncClient, hub: Any, su: Any, owner_session: dict[str, Any]
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    ovr = await agent_headers("HQ-OVR")
    payload = {
        "title_fa": "بازبینی آزمایشی",
        "area": "quality",
        "check_md": "a test protocol, paused (8.1 §2.1)",
        "method": "rule",
        "schedule": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0",
        "scope": "holding",
        "severity": "low",
        "answerable": "ceo",
        "status": "paused",
    }
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ovr, **idem()},
        json={"kind": "protocol", "title": "پروتکل تازه", "payload": payload},
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    listed = (await client.get("/api/v1/decisions", headers=h, params={"kind": "protocol"})).json()
    assert ref in [d["ref"] for d in listed["items"]]
    r = await client.get("/api/v1/decisions", headers=h, params={"kind": "errand_action"})
    assert r.status_code == 200
    r = await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={})
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    seal = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, ref, SYSTEM)
    row = await su.fetchrow(
        """SELECT p.ref, p.status, p.source FROM oversight.protocols p
           JOIN cartable.decisions d ON d.id = p.decision_id WHERE d.ref = $1""",
        ref,
    )
    assert out["protocol"].startswith(row["ref"] + "@")
    assert (row["status"], row["source"]) == ("paused", "decision")
    await _end_test_runs(su, "HQ-OVR")


# ---------------------------------------------------------------- §2.16 --
async def test_lesson_adoption_needs_the_seal_and_reopens_after_return_or_expiry(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    wk: dict[str, Any],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    src, other = (await new_company())["code"], (await new_company())["code"]
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/lessons",
        headers={**ovr, **idem()},
        json={
            "source_company": src,
            "period": f"week:{PAST_WEEK.isoformat()}",
            "title_fa": "درس آزمایشی",
            "body_md": "متن درس",
        },
    )
    lesson = r.json()["ref"]
    ceo = await agent_headers(f"{other}-CEO")
    body = {"kind": "lesson_adoption", "title": "به‌کارگیری", "payload": {"lesson": lesson}}

    async def propose() -> str:
        r = await client.post("/internal/v1/decisions", headers={**ceo, **idem()}, json=body)
        assert r.status_code == 201, r.text
        return str(r.json()["ref"])

    first = await propose()
    r = await client.post(f"/api/v1/decisions/{first}/approve", headers={**h, **idem()}, json={})
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")  # sealed (§18.10)
    r = await client.post(
        f"/api/v1/decisions/{first}/return", headers={**h, **idem()}, json={"note": "دقیق‌تر"}
    )
    assert r.status_code == 200, r.text
    second = await propose()  # a returned card frees the lesson
    await su.execute(
        "UPDATE cartable.decisions SET expires_at = now() - interval '1 second' WHERE ref = $1",
        second,
    )
    assert (await wk["acts"].decision_expire(second))["expired"]
    third = await propose()  # an expired one too
    adoption = await su.fetchrow(
        """SELECT a.status, a.decision_ref FROM knowledge.lesson_adoptions a
           JOIN core.companies c ON c.id = a.company_id WHERE a.lesson_ref = $1 AND c.code = $2""",
        lesson,
        other,
    )
    assert (adoption["status"], adoption["decision_ref"]) == ("proposed", third)
    seal = await step_up(hub, sid, "decision.approve", third)
    r = await client.post(
        f"/api/v1/decisions/{third}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    r = await client.post("/internal/v1/decisions", headers={**ceo, **idem()}, json=body)
    assert r.status_code == 422  # decided (approved): not again
    await _end_test_runs(su, "HQ-OVR", f"{other}-CEO")


# ---------------------------------------------------------------- §2.17 --
def test_outside_links_with_or_without_a_scheme() -> None:
    for text in (
        "t.me/x",
        "evil.com/promo",
        "ببینید evil.com",
        "https://a.b",
        "www.example.org",
        "در sub.example.ir/a",
    ):
        assert ST.OUTSIDE.search(text), text
    for text in ("1.6M", "$4.20", "مهاجرت به Next.js", "رشد ۸۶٪", "v2.0 آماده شد", "e.g. همین"):
        assert not ST.OUTSIDE.search(text), text


async def test_story_period_metric_and_milestone_evidence(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    post = {"kind": "post", "title_fa": "خبر", "body_fa": "متن"}
    for bad, field in (
        ({**post, "body_fa": "کانال ما t.me/x"}, "body_fa"),
        ({**post, "body_fa": "ببینید evil.com/promo"}, "body_fa"),
        ({**post, "links": {"period": "t.me/x"}}, "links.period"),
        ({**post, "links": {"period": "week:soon"}}, "links.period"),
        ({**post, "links": {"metric": "evil.com"}}, "links.metric"),
        (  # a figure alone is a claim, not evidence
            {"kind": "milestone", "title_fa": "هدف", "figures": [{"label_fa": "x", "value": "1"}]},
            "links",
        ),
        (  # a metric without its figure
            {"kind": "milestone", "title_fa": "هدف", "links": {"metric": "users_active"}},
            "links",
        ),
    ):
        r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=bad)
        assert r.status_code == 422, (bad, r.text)
        assert any(k.endswith(field) for k in r.json()["fields"]), (field, r.json())
    ok = {
        "kind": "milestone",
        "title_fa": "۱۰۰۰ کاربر فعال",
        "figures": [{"label_fa": "کاربر", "value": "1000"}],
        "links": {"metric": "users_active", "period": f"week:{PAST_WEEK.isoformat()}"},
    }
    r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=ok)
    assert r.status_code == 201, r.text
    assert r.json()["links"] == ok["links"]
    await _end_test_runs(su, f"{co}-CEO")


async def test_a_cancelled_story_hold_hides_it_from_rings_and_archive(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    """Cancel cancels the action itself (§18.15): a story whose hold the owner
    cancelled is withdrawn, never shown (live or after expiry)."""
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/stories",
        headers={**ceo, **idem()},
        json={"kind": "post", "title_fa": "خبر", "body_fa": "متن"},
    )
    live = r.json()["ref"]
    old = await su.fetchval(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa,
               created_at, expires_at)
           SELECT id, 'post', 'agent', $2, 'دیروز', now() - interval '25 hours', now() - interval '1 hour'
           FROM core.companies WHERE code = $1 RETURNING ref""",
        co,
        f"{co}-CEO",
    )
    ovr = await agent_headers("HQ-OVR")
    for ref in (live, old):
        r = await client.post(
            "/internal/v1/oversight/holds",
            headers={**ovr, **idem()},
            json={"target": {"kind": "story", "ref": ref}, "reason_md": "تبلیغ بیرونی"},
        )
        assert r.status_code == 201, r.text
        r = await client.post(f"/api/v1/oversight/holds/{r.json()['ref']}/cancel", headers=owner)
        assert r.status_code == 200 and r.json()["state"] == "cancelled", r.text
    rings = (await client.get("/api/v1/stories", headers=owner)).json()
    assert live not in [i["ref"] for g in rings for i in g["items"]]
    archive = (
        await client.get("/api/v1/stories/archive", headers=owner, params={"company": co})
    ).json()
    assert old not in [s["ref"] for s in archive["items"]]
    await _end_test_runs(su, f"{co}-CEO", "HQ-OVR")


# ---------------------------------------------------------- §2.19, §4 stars --
async def test_rubric_weights_are_numbers_and_stars_are_whole_or_half(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    good = {
        "employee": f"{co}-TECH-MGR",
        "week": PAST_WEEK.isoformat(),
        "stars": 3.5,
        "criteria": {"results": 4},
        "reason_md": "تحویل خوب",
        "evidence": [{"kind": "work", "ref": "W-000001"}],
    }
    r = await client.post("/internal/v1/stars", headers={**ceo, **idem()}, json=good)
    assert r.status_code == 422 and "criteria" in r.json()["fields"]  # no rubric yet
    weights = {**RUBRIC, "criteria": [{**c} for c in RUBRIC["criteria"]]}
    weights["criteria"][0]["weight"] = 47.5
    weights["criteria"][1]["weight"] = 32.5
    r = await client.post("/internal/v1/stars/rubric", headers={**ceo, **idem()}, json=weights)
    assert r.status_code == 200, r.text
    served = (await client.get(f"/api/v1/stars/rubrics/{co}", headers=owner)).json()
    assert [c["weight"] for c in served["criteria"]] == [47.5, 32.5, 20]
    assert all(type(c["weight"]) in (int, float) for c in served["criteria"])
    stored = await su.fetchval(
        """SELECT jsonb_typeof(r.criteria -> 0 -> 'weight') FROM people.star_rubrics r
           JOIN core.companies c ON c.id = r.company_id WHERE c.code = $1""",
        co,
    )
    assert stored == "number"
    for stars in (3.7, 0.2):
        r = await client.post(
            "/internal/v1/stars", headers={**ceo, **idem()}, json={**good, "stars": stars}
        )
        assert r.status_code == 422 and "stars" in r.json()["fields"], r.text
    r = await client.post(
        "/internal/v1/stars",
        headers={**ceo, **idem()},
        json={**good, "criteria": {"results": 4.3}},
    )
    assert r.status_code == 422 and "criteria" in r.json()["fields"], r.text
    r = await client.post("/internal/v1/stars", headers={**ceo, **idem()}, json=good)
    assert r.status_code == 200 and r.json()["stars"] == 3.5, r.text
    assert S.half_step(Decimal("4.5")) and not S.half_step(Decimal("5.5"))
    await _end_test_runs(su, f"{co}-CEO")


# ------------------------------------------------------------- §4 errands --
async def test_a_cancelled_errand_withdraws_its_pending_card(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    r = await client.post(
        "/api/v1/errands",
        headers={**owner, **idem()},
        json={"brief_md": "یک اشتراک بخر", "title_fa": "خرید اشتراک"},
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    pa = await agent_headers("HQ-PA")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**pa, **idem()},
        json={
            "kind": "errand_action",
            "title": "خرید اشتراک ماهانه",
            "risk": "medium",
            "reversible": False,
            "payload": {
                "errand": ref,
                "action": "buy",
                "target": "example.com",
                "details_md": "اشتراک یک‌ماهه",
                "cost": "10 USD",
                "undo_md": "لغو تا ۷ روز",
            },
        },
    )
    assert r.status_code == 201, r.text
    card = r.json()["ref"]
    r = await client.post(f"/api/v1/errands/{ref}/cancel", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "cancelled", r.text
    d = await su.fetchrow(
        "SELECT status, decided_by_code FROM cartable.decisions WHERE ref = $1", card
    )
    assert (d["status"], d["decided_by_code"]) == ("withdrawn", "system")
    await _end_test_runs(su, "HQ-PA")


def test_the_score_bonus_is_small_and_bounded() -> None:
    assert scoring.with_welcome(7.0, True) == 7.2 and scoring.with_welcome(7.0, False) == 7.0
    assert scoring.combine({"owner_rating": 8.0, "owner_welcome": 0.2}) == 8.0
