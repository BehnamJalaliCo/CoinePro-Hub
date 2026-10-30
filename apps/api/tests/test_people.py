"""Prompt 08 §4, §8, §9 (contract §18.4, §18.11, §18.12): stars and lessons,
hiring with the CEOs, stories."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator, Callable
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import decisions as D
from hq_api.domain import stars as S
from hq_api.principal import Principal
from hq_api.worker.jalali import to_jalali

from .conftest import agent_headers, idem, step_up

pytestmark = pytest.mark.usefixtures("relay")
SYSTEM = Principal(kind="service", code="system", role="system")
# A past Saturday of its own per run: the test database lives on between runs.
PAST_WEEK = date(2020, 1, 4) + timedelta(weeks=secrets.randbelow(150) * 2)
RUBRIC = {
    "criteria": [
        {"key": "results", "name_fa": "نتیجه", "weight": 50},
        {"key": "quality", "name_fa": "کیفیت", "weight": 30},
        {"key": "efficiency", "name_fa": "کارایی", "weight": 20},
    ],
    "rules_md": "شاهد لازم است.",
}


@pytest.fixture(autouse=True)
async def seeded(hub: Any, owner_db: Any) -> None:
    """The protocols (a hire's PR-098 review, PR-080): another file's
    migration round trip drops them for the rest of the session (8.1)."""
    from hq_api.domain import oversight
    from hq_common import charters

    holding = await hub.companies.holding()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await oversight.seed_protocols(tx, holding.id, charters.load().root)


async def _end_test_runs(su: Any, *codes: str) -> None:
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'running' AND r.reason = 'test'""",
        list(codes),
    )


# ------------------------------------------------------------ the formula --
def test_the_company_score_and_efficiency_with_fixed_data() -> None:
    parts = {"kpi": 80, "challenges": 70, "compliance": 90, "people": 60, "efficiency": 50}
    assert S.company_score(parts) == (72.0, 3.6)  # 28 + 14 + 13.5 + 9 + 7.5
    # A part without data is left out and the weights renormalised (0.65 left).
    assert S.company_score({**parts, "kpi": None}) == (67.7, 3.39)
    assert S.company_score(dict.fromkeys(parts)) == (None, None)
    # Company: 40% envelope + 30% waste + 30% cost per accepted output vs the median.
    assert (
        S.company_efficiency(
            used=900, envelope=1000, waste_share=0.1, cost_per_accepted=2, holding_median=1
        )
        == 82.0
    )  # 40 + 27 + 15
    assert (
        S.company_efficiency(
            used=1100, envelope=1000, waste_share=0.1, cost_per_accepted=2, holding_median=1
        )
        == 42.0
    )  # over the envelope: that part is 0
    # Employee: 50% tokens per accepted output + 25% failed runs + 25% estimate.
    assert (
        S.employee_efficiency(
            tokens_per_accepted=2000, dept_median=1000, failed_share=0.2, estimate_ratio=1.1
        )
        == 70.0
    )  # 25 + 20 + 25
    assert (
        S.estimate_part(1.25) == 100.0
        and S.estimate_part(1.5) == 66.7
        and S.estimate_part(2) == 0.0
    )
    assert S.inflated([5, 5, 5, 4]) and not S.inflated([5, 5, 4, 4]) and not S.inflated([5, 5])


# ------------------------------------------------------------------ stars --
async def test_rubrics_stars_and_the_overseers_audit(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    low = {
        **RUBRIC,
        "criteria": [
            {**c, "weight": w} for c, w in zip(RUBRIC["criteria"], (60, 30, 10), strict=True)
        ],
    }
    r = await client.post("/internal/v1/stars/rubric", headers={**ceo, **idem()}, json=low)
    assert r.status_code == 422 and "efficiency" in r.json()["fields"]["criteria"]
    for version in (1, 2):
        r = await client.post("/internal/v1/stars/rubric", headers={**ceo, **idem()}, json=RUBRIC)
        assert r.status_code == 200 and r.json()["version"] == version, r.text
    assert (await client.get(f"/api/v1/stars/rubrics/{co}", headers=owner)).json()["version"] == 2
    week = PAST_WEEK.isoformat()
    good = {
        "employee": f"{co}-TECH-MGR",
        "week": week,
        "stars": 4.5,
        "criteria": {"results": 5, "efficiency": 4},
        "reason_md": "تحویل به‌موقع با هزینه‌ی کم",
        "evidence": [{"kind": "work", "ref": "W-000001"}],
    }
    r = await client.post("/internal/v1/stars", headers={**ceo, **idem()}, json=good)
    assert r.status_code == 200 and r.json()["counted"], r.text
    bare = {**good, "employee": f"{co}-GROWTH-MGR", "evidence": []}
    r = await client.post("/internal/v1/stars", headers={**ceo, **idem()}, json=bare)
    assert r.status_code == 200 and r.json()["counted"] is False  # no evidence: kept, not counted
    r = await client.post(
        "/internal/v1/stars",
        headers={**ceo, **idem()},
        json={**good, "employee": f"{other}-TECH-MGR"},
    )
    assert r.status_code == 403  # another company's employee
    r = await client.post(
        "/internal/v1/stars", headers={**ceo, **idem()}, json={**good, "criteria": {"luck": 5}}
    )
    assert r.status_code == 422  # not in the rubric
    star_id = (
        await client.get("/api/v1/stars", headers=owner, params={"employee": f"{co}-TECH-MGR"})
    ).json()["items"][0]["id"]
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        f"/internal/v1/stars/{star_id}/audit",
        headers={**ovr, **idem()},
        json={"counted": False, "note": "شاهد به کار دیگری مربوط است"},
    )
    assert r.status_code == 200 and r.json()["counted"] is False and r.json()["overseer_note"]
    r = await client.post(
        f"/internal/v1/stars/{star_id}/audit",
        headers={**ceo, **idem()},
        json={"counted": True, "note": "x"},
    )
    assert r.status_code == 403  # only the overseer audits
    await _end_test_runs(su, f"{co}-CEO", "HQ-OVR")


async def test_the_weekly_rollup_flags_inflation_and_tells_the_best_company(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    week = PAST_WEEK + timedelta(days=7)
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    for emp in ("TECH-MGR", "GROWTH-MGR", "SALES-MGR", "PRODUCT-MGR"):
        code = f"{co}-{emp}"
        r = await client.post(
            "/internal/v1/stars",
            headers={**ceo, **idem()},
            json={
                "employee": code,
                "week": week.isoformat(),
                "stars": 5,
                "reason_md": "عالی",
                "evidence": [{"kind": "metric", "ref": "uptime 99.9"}],
            },
        )
        assert r.status_code == 200, r.text
    counted = await su.fetchval(
        """SELECT count(*) FROM people.stars s JOIN core.companies c ON c.id = s.company_id
           WHERE c.code = $1 AND s.week = $2 AND s.counted""",
        co,
        week,
    )
    assert counted >= 3
    out = await wk["acts"].people.stars_rollup((week + timedelta(days=7)).isoformat())
    assert out["week"]["key"] == week.isoformat() and out["week"]["created"]
    again = await wk["acts"].people.stars_rollup((week + timedelta(days=7)).isoformat())
    assert again["week"]["created"] is False  # once per period
    r = await client.get(
        "/api/v1/stars/rollup", headers=owner, params={"period": "week", "key": week.isoformat()}
    )
    assert r.status_code == 200, r.text
    roll = r.json()
    mine = next(c for c in roll["companies"] if c["company"] == co)
    assert mine["parts"]["people"] == 100.0 and mine["parts"]["kpi"] is None
    assert mine["parts"]["challenges"] is None and mine["score"] is not None
    assert {e["company"] for e in roll["employees"]} >= {co}
    # More than 70% fives: the overseer's finding of PR-080 (the merge wired the hook).
    flagged = await su.fetchval(
        """SELECT count(*) FROM oversight.findings f JOIN core.companies c ON c.id = f.company_id
           WHERE c.code = $1 AND f.dedupe_key = 'PR-080:stars-inflation'
             AND f.status NOT IN ('verified', 'closed')""",
        co,
    )
    assert flagged == 1
    best = roll["best_company"]
    story = await su.fetchrow(
        "SELECT kind, links FROM owner.stories WHERE event_key = $1",
        f"stars:week:{week.isoformat()}",
    )
    assert best and story["kind"] == "stars"
    # A rolled-up week takes no more stars.
    r = await client.post(
        "/internal/v1/stars",
        headers={**ceo, **idem()},
        json={"employee": f"{co}-TECH-MGR", "week": week.isoformat(), "stars": 3},
    )
    assert r.status_code == 409
    await _end_test_runs(su, f"{co}-CEO")


async def test_the_jalali_month_rolls_up_on_its_first_day(wk: dict[str, Any], su: Any) -> None:
    day = date(2026, 6, 1)
    while to_jalali(day)[2] != 1:
        day += timedelta(days=1)
    out = await wk["acts"].people.stars_rollup(day.isoformat())
    key = S.jalali_key(day - timedelta(days=1))
    assert out["month"]["key"] == key
    row = await su.fetchrow(
        "SELECT starts_on, ends_on FROM people.star_rollups WHERE period = 'month' AND key = $1",
        key,
    )
    assert row["ends_on"] == day and to_jalali(row["starts_on"])[2] == 1


async def test_a_lesson_goes_to_the_other_ceos_for_adoption(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    hub: Any,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    src = (await new_company())["code"]
    other = (await new_company())["code"]
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/lessons",
        headers={**ovr, **idem()},
        json={
            "source_company": src,
            "period": f"week:{PAST_WEEK.isoformat()}",
            "title_fa": "بازبینی دوطرفه پیش از تحویل",
            "body_md": "هر خروجی را یک همکار پیش از تحویل میخواند.",
            "evidence": [{"kind": "deliverable", "ref": "O-000001"}],
        },
    )
    assert r.status_code == 201, r.text
    lesson = r.json()
    adoption = {a["company"]: a for a in lesson["adoption"]}
    assert src not in adoption and adoption[other]["status"] == "proposed"
    assert adoption[other]["work_ref"]
    ceo_work = await su.fetchval(
        """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.ref = $1""",
        adoption[other]["work_ref"],
    )
    assert ceo_work == f"{other}-CEO"
    ceo = await agent_headers(f"{other}-CEO")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={
            "kind": "lesson_adoption",
            "title": f"به‌کارگیری {lesson['ref']}",
            "payload": {"lesson": lesson["ref"], "adopt": True, "plan_md": "از هفته‌ی بعد"},
        },
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    seal = await step_up(hub, owner_session["session_id"], "decision.approve", ref)  # 8.1 §2.16
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await D.apply_effect(tx, ref, SYSTEM)
    lessons = (await client.get("/api/v1/lessons", headers=h, params={"company": src})).json()
    got = next(a for a in lessons["items"][0]["adoption"] if a["company"] == other)
    assert (got["status"], got["decision_ref"]) == ("adopted", ref)
    # A lesson not offered (or already decided) cannot be proposed again.
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={"kind": "lesson_adoption", "title": "x", "payload": {"lesson": lesson["ref"]}},
    )
    assert r.status_code == 422
    r = await client.post(
        "/internal/v1/lessons",
        headers={**ceo, **idem()},
        json={"source_company": src, "period": "week:2026-09-05", "title_fa": "x", "body_md": "y"},
    )
    assert r.status_code == 403  # a CEO writes no lessons
    await _end_test_runs(su, "HQ-OVR", f"{other}-CEO")


# ----------------------------------------------------------------- hiring --
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


async def _envelope(su: Any, company: dict[str, Any], tokens: int = 50_000_000) -> None:
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', $3)
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET token_limit = $3, enabled = true""",
        company["id"],
        company["code"],
        tokens,
    )


def _hire(co: str, estimate: int = 1_500_000, n: int = 0) -> dict[str, Any]:
    return {
        "kind": "hire",
        "title": f"استخدام SRE {n}",
        "payload": {
            "company": co,
            "department": "TECH",
            "role": "sre",
            "title_fa": f"کارشناس پایداری {n}",
            "title_en": "SRE",
            "reason": "پایش شبانه‌روزی سایت‌ها",
            "model": "claude-haiku-5-5",
            "effort": "low",
            "quota_estimate_month": {"tokens": estimate},
        },
    }


async def test_a_ceo_hires_inside_the_envelope(
    client: httpx.AsyncClient,
    hub: Any,
    su: Any,
    delegated: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = delegated["headers"]
    company = await new_company()
    co = company["code"]
    await _envelope(su, company)
    fx = (await new_company())["code"]
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co))
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["approver"] == {"kind": "agent", "code": f"{co}-CEO", "display_fa": None}
    decide_work = await su.fetchval(
        """SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = $1 AND w.title LIKE $2""",
        f"{co}-CEO",
        f"%{card['ref']}%",
    )
    assert decide_work == 1
    # The owner's cartable and inbox show only the owner's cards.
    mine = (await client.get("/api/v1/decisions", headers=h, params={"company": co})).json()
    assert card["ref"] not in [d["ref"] for d in mine["items"]]
    every = (
        await client.get("/api/v1/decisions", headers=h, params={"company": co, "approver": "all"})
    ).json()
    assert card["ref"] in [d["ref"] for d in every["items"]]
    pending = (await client.get("/api/v1/inbox/summary", headers=h)).json()["decisions_pending"]
    owners = await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE status = 'pending' AND approver_code IS NULL"
    )
    assert pending == owners
    # Another company's CEO cannot decide it.
    r = await client.post(
        f"/internal/v1/hires/{card['ref']}/decide",
        headers={**await agent_headers(f"{fx}-CEO"), **idem()},
        json={"verdict": "approve"},
    )
    assert r.status_code == 403
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/hires/{card['ref']}/decide",
        headers={**ceo, **idem()},
        json={"verdict": "approve", "note": "در پاکت جا میشود"},
    )
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, card["ref"], SYSTEM)
    emp = out["employee"]
    row = await su.fetchrow(
        "SELECT status, probation_until - now() AS left FROM core.employees WHERE code = $1", emp
    )
    assert row["status"] == "active" and timedelta(days=6) < row["left"] <= timedelta(days=7)
    story = await su.fetchrow(
        "SELECT kind, figures, links FROM owner.stories WHERE event_key = $1", f"hire:{card['ref']}"
    )
    assert story["kind"] == "hire" and json.loads(story["links"])["employee"] == emp
    assert [f["label_fa"] for f in json.loads(story["figures"])] == ["نقش", "مدل", "برآورد ماهانه"]
    note = await su.fetchrow(
        "SELECT level FROM notify.notifications WHERE link_kind = 'employee' AND link_ref = $1", emp
    )
    assert note["level"] == "report"  # the digest, never an urgent push
    review = await su.fetchrow(
        """SELECT e.code, w.due_at - now() AS due FROM work.work w
           JOIN core.employees e ON e.id = w.assignee_id WHERE w.title LIKE $1""",
        f"%{emp}%PR-098%",
    )
    assert review["code"] == "HQ-OVR" and review["due"] <= timedelta(hours=24)
    # An estimate that does not fit the envelope: 409, no employee.
    await _envelope(su, company, 2_000_000)  # 1.5M committed + 0.9M > 2M
    r = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, 900_000, 1)
    )
    big = r.json()["ref"]
    before = await su.fetchval(
        "SELECT count(*) FROM core.employees WHERE company_id = $1", company["id"]
    )
    r = await client.post(
        f"/internal/v1/hires/{big}/decide", headers={**ceo, **idem()}, json={"verdict": "approve"}
    )
    assert (r.status_code, r.json()["code"]) == (409, "envelope_exceeded")
    after = await su.fetchval(
        "SELECT count(*) FROM core.employees WHERE company_id = $1", company["id"]
    )
    assert after == before
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", big) == "pending"
    )
    await _end_test_runs(su, f"{co}-TECH-MGR", f"{co}-CEO", f"{fx}-CEO")


async def test_holding_cards_stay_with_the_owner_and_five_a_day(
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
    aiops = await agent_headers("HQ-AIOPS-MGR")
    body = _hire("HQ")
    body["payload"].update(department="AIOPS", role="hub_platform_sre", title_fa="SRE هاب")
    r = await client.post("/internal/v1/decisions", headers={**aiops, **idem()}, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["approver"] is None  # the holding has no CEO: the owner decides
    # Five approved hires today in a company: the sixth is refused (a loop guard).
    for n in range(5):
        await su.execute(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
                   proposer_code, status, decided_at, payload)
               VALUES ($1, 'hire', 'A2', $2, 'agent', $3, 'approved', now(), '{}')""",
            company["id"],
            f"seed {n}",
            f"{co}-TECH-MGR",
        )
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, n=6))
    ref = r.json()["ref"]
    r = await client.post(
        f"/internal/v1/hires/{ref}/decide",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"verdict": "approve"},
    )
    assert (r.status_code, r.json()["code"]) == (429, "rate_limited")
    # The owner may decide a CEO's card first; the same checks apply to it.
    st = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **st, **idem()}, json={}
    )
    assert (r.status_code, r.json()["code"]) == (429, "rate_limited")
    r = await client.post(
        f"/api/v1/decisions/{ref}/reject", headers={**h, **idem()}, json={"reason": "بعداً"}
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    await _end_test_runs(su, "HQ-AIOPS-MGR", f"{co}-TECH-MGR", f"{co}-CEO")


# ---------------------------------------------------------------- stories --
async def test_stories_limits_masking_rings_and_welcome(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    phone = "0912" + "345" + "6789"
    post = {"kind": "post", "title_fa": "رکورد تازه", "body_fa": f"با ما تماس بگیرید {phone}"}
    r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=post)
    assert r.status_code == 201, r.text
    first = r.json()
    assert phone not in first["body_fa"]  # redacted like every agent output
    for bad, field in (
        ({**post, "body_fa": "ببینید https://example.com"}, "body_fa"),
        ({"kind": "milestone", "title_fa": "هدف رسید"}, "links"),
    ):
        r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=bad)
        assert r.status_code == 422 and field in r.json()["fields"], r.text
    other_file = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code, kind)
           SELECT id, 'x.png', 'image/png', 10, repeat('a', 64), 'k/' || $1, 'owner', 'owner', 'image'
           FROM core.companies WHERE code = $1 RETURNING id""",
        other,
    )
    r = await client.post(
        "/internal/v1/stories", headers={**ceo, **idem()}, json={**post, "file_id": str(other_file)}
    )
    assert r.status_code == 403  # an image of another company
    milestone = {
        "kind": "milestone",
        "title_fa": "۱۰۰۰ کاربر",
        "figures": [{"label_fa": "کاربر", "value": "1000"}],
        "links": {"metric": "users"},  # 8.1 §2.17: a metric with its figure
    }
    for body in (post, milestone):
        r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=body)
        assert r.status_code == 201, r.text
    r = await client.post("/internal/v1/stories", headers={**ceo, **idem()}, json=post)
    assert (r.status_code, r.json()["code"]) == (429, "story_limit")  # the fourth of the day
    rings = (await client.get("/api/v1/stories", headers=owner)).json()
    ring = next(g for g in rings if g["company"] == co)
    assert ring["unseen"] == 3 and ring["items"][0]["ref"] == first["ref"]
    unseen = [g["unseen"] > 0 for g in rings]
    assert unseen == sorted(unseen, reverse=True)  # rings with unseen stories come first
    r = await client.post(
        "/api/v1/stories/seen", headers=owner, json={"refs": [s["ref"] for s in ring["items"]]}
    )
    assert r.json() == {"seen": 3}
    ring = next(
        g for g in (await client.get("/api/v1/stories", headers=owner)).json() if g["company"] == co
    )
    assert ring["unseen"] == 0
    r = await client.post(f"/api/v1/stories/{first['ref']}/welcome", headers=owner)
    assert r.status_code == 422  # only a hire story
    # After 24 h a story leaves the rings for the archive (a story of yesterday).
    old = await su.fetchval(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa,
               created_at, expires_at)
           SELECT id, 'post', 'agent', $2, 'دیروز', now() - interval '25 hours', now() - interval '1 hour'
           FROM core.companies WHERE code = $1 RETURNING ref""",
        co,
        f"{co}-CEO",
    )
    ring = next(
        g for g in (await client.get("/api/v1/stories", headers=owner)).json() if g["company"] == co
    )
    assert old not in [s["ref"] for s in ring["items"]] and len(ring["items"]) == 3
    archive = (
        await client.get("/api/v1/stories/archive", headers=owner, params={"company": co})
    ).json()
    assert [s["ref"] for s in archive["items"]] == [old]
    await _end_test_runs(su, f"{co}-CEO")


async def test_a_hire_story_is_welcomed(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    from hq_api.domain import stories

    ref = await su.fetchval(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa, links, event_key)
           VALUES ($1, 'hire', 'service', 'system', 'استخدام', $2::jsonb, $3) RETURNING ref""",
        company["id"],
        json.dumps({"employee": f"{co}-TECH-MGR"}),
        f"hire:test-{co}",
    )
    r = await client.post(f"/api/v1/stories/{ref}/welcome", headers=owner)
    assert r.status_code == 200 and r.json()["welcomed"] and r.json()["seen"], r.text
    told = await su.fetchval(
        """SELECT count(*) FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = $1 AND m.body LIKE '%خوشامد%'""",
        f"{co}-CEO",
    )
    assert told == 1
    assert stories.short(1_600_000) == "1.6M" and stories.short(820_000) == "820K"


async def test_a_held_story_waits_for_the_owner(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """A story the overseer holds (hold kind `story`) leaves the rings until the
    owner releases it (prompt 08 merge: oversight x stories)."""
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/stories",
        headers={**ceo, **idem()},
        json={"kind": "post", "title_fa": "خبر", "body_fa": "متن"},
    )
    ref = r.json()["ref"]

    async def shown() -> bool:
        rings = (await client.get("/api/v1/stories", headers=owner)).json()
        return any(i["ref"] == ref for ring in rings for i in ring["items"])

    assert await shown()
    await su.execute(
        """INSERT INTO oversight.holds (company_id, target_kind, target_ref, reason_md, held_by_kind,
               held_by_code)
           SELECT id, 'story', $2, 'r', 'agent', 'HQ-OVR' FROM core.companies WHERE code = $1""",
        co,
        ref,
    )
    assert not await shown()
    await su.execute(
        """UPDATE oversight.holds SET state = 'released', decided_by_kind = 'owner',
               decided_by_code = 'owner', decided_at = now()
           WHERE target_ref = $1""",
        ref,
    )
    assert await shown()
