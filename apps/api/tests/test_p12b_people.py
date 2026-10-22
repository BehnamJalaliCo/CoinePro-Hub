"""Prompt 12 §5, §6, §12 (contract §21.5, §21.9): department ranks, the
monthly HR round and its evaluation cards, PR-082 on the Jalali calendar,
checked claims and the agent health board."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import claims as CL
from hq_api.domain import decisions as D
from hq_api.domain import hr, rankings
from hq_api.domain import oversight as O
from hq_api.domain import oversight_checks as C
from hq_api.domain import stars as S
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.jalali import to_jalali
from hq_api.worker.mgmt_activities import MgmtActivities
from hq_api.worker.oversight_activities import protocol_desired

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch

NOW = datetime(2031, 6, 1, tzinfo=UTC)
TEHRAN = ZoneInfo("Asia/Tehran")


def jalali_day(n: int, after: date) -> date:
    d = after
    while to_jalali(d)[2] != n:
        d += timedelta(days=1)
    return d


# --------------------------------------------------------------- ranking --
def test_the_department_formula_spreads_the_owner_weight_when_unrated() -> None:
    parts = {"people": 80.0, "delivery": 50.0, "efficiency": 60.0, "owner": None}
    assert rankings.department_score(parts) == pytest.approx(64.7)  # 55 / 0.85
    assert rankings.department_score({**parts, "owner": 90.0}) == pytest.approx(68.5)
    assert rankings.department_score(dict.fromkeys(parts)) is None
    assert rankings.people_part([(8.0, 7.0), (6.0, 1.0), (None, 7.0)]) == pytest.approx(77.5)
    assert rankings.people_part([(None, 3.0)]) is None
    assert rankings.rank([("a", 50.0), ("b", 70.0), ("c", 50.0)]) == {"b": 1, "a": 2, "c": 2}


async def _department(su: Any, company_id: Any, code: str) -> Any:
    return await su.fetchval(
        """INSERT INTO core.departments (company_id, code, name_fa, name_en, manager_title_fa, manager_title_en)
           VALUES ($1, $2, 'خالی', 'Empty', 'مدیر', 'Manager') RETURNING id""",
        company_id,
        code,
    )


async def test_ranks_with_fixed_data(hub: Hub, su: Any, new_company: Callable[..., Any]) -> None:
    a, b = await new_company(), await new_company()
    start = datetime(2031, 6, 7, tzinfo=UTC)  # a Saturday
    end = start + timedelta(days=7)
    empty = await _department(su, a["id"], "LAB")
    eff: dict[Any, float | None] = {}
    for co, score, on_time in ((a, 8.0, True), (b, 6.0, False)):
        emp = await su.fetchrow(
            "SELECT id, department_id FROM core.employees WHERE code = $1", f"{co['code']}-TECH-MGR"
        )
        await su.execute("UPDATE core.employees SET score = $2 WHERE id = $1", emp["id"], score)
        eff[emp["id"]] = 70.0
        w = await su.fetchval(
            """INSERT INTO work.work (company_id, department_id, kind, title, created_by_kind, created_by_code,
                   due_at, status, delivered_at)
               VALUES ($1, $2, 'one_off', 'due', 'owner', 'owner', $3, 'delivered', $4) RETURNING id""",
            co["id"],
            emp["department_id"],
            start + timedelta(days=2),
            start + timedelta(days=1 if on_time else 3),
        )
        dl = await su.fetchval(
            """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, evidence, created_at)
               VALUES ($1, $2, $3, 'out', '[{"kind": "link", "ref": "x"}]', $4) RETURNING id""",
            co["id"],
            w,
            emp["id"],
            start + timedelta(days=1),
        )
        await su.execute(
            """INSERT INTO cartable.ratings (company_id, deliverable_id, version_no, score, rated_by_code)
               VALUES ($1, $2, 1, 8, 'owner')""",
            co["id"],
            dl,
        )
    await su.execute(
        "UPDATE core.employees SET score = 6 WHERE code = $1", f"{a['code']}-GROWTH-MGR"
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = rankings.ranked(await rankings.figures(tx, start, end, eff, [a["id"], b["id"]]))
    tech = {r["company"]: r for r in rows if r["department"] == "TECH"}
    assert tech[a["code"]]["parts"] == {
        "people": 80.0,
        "delivery": 100.0,
        "efficiency": 70.0,
        "owner": 80.0,
    }
    assert tech[b["code"]]["parts"]["delivery"] == 0.0
    assert tech[a["code"]]["score"] == pytest.approx(84.0)  # 28 + 30 + 14 + 12
    assert tech[a["code"]]["rank_holding"] == 1 and tech[b["code"]]["rank_holding"] == 2
    assert all(r["department_id"] != empty for r in rows)  # no active employee: not ranked
    others = [r for r in rows if r["department"] == "GROWTH" and r["company"] == a["code"]]
    assert others and others[0]["parts"]["owner"] is None  # no rating: its weight is spread
    assert others[0]["score"] == pytest.approx(60.0)
    key = f"2031-{secrets.randbelow(10**6):06d}"[:7]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        written = await rankings.compute(tx, "month", key, start, end, eff, [a["id"], b["id"]])
        assert written and await rankings.compute(tx, "month", key, start, end, eff) == []


# -------------------------------------------------------------- HR flags --
def test_hr_flags_are_rules() -> None:
    later = NOW + timedelta(days=3)
    ended = NOW - timedelta(days=1)
    assert hr.flags(9.0, 8.6, 4.5, 0, None, NOW) == ["promote_candidate"]
    assert hr.flags(9.0, 8.6, 4.5, 1, None, NOW) == []  # an open high finding
    assert hr.flags(9.0, 8.6, 3.5, 0, None, NOW) == []
    assert hr.flags(6.0, 7.6, None, 0, None, NOW) == ["coach"]  # a drop of 1.6
    assert hr.flags(5.5, None, None, 0, None, NOW) == ["coach"]
    assert hr.flags(4.5, 4.9, None, 0, None, NOW) == ["demote_candidate"]
    assert hr.flags(3.0, 3.4, None, 0, None, NOW) == ["demote_candidate", "dismiss_candidate"]
    assert hr.flags(4.0, None, None, 0, ended, NOW) == ["dismiss_candidate", "probation_end"]
    assert hr.flags(7.0, 7.0, None, 0, ended, NOW) == ["probation_end"]
    assert hr.flags(7.0, 7.0, None, 0, later, NOW) == []
    assert hr.flags(None, None, None, 0, None, NOW) == []


async def _scores(su: Any, code: str, now_score: float, prev: float) -> None:
    emp = await su.fetchrow("SELECT id, company_id FROM core.employees WHERE code = $1", code)
    for month, value in ((date(2000, 1, 1), prev), (date(2000, 2, 1), now_score)):
        await su.execute(
            """INSERT INTO core.employee_scores (employee_id, company_id, month, value, components)
               VALUES ($1, $2, $3, $4, '{}') ON CONFLICT (employee_id, month) DO NOTHING""",
            emp["id"],
            emp["company_id"],
            month,
            value,
        )


async def _round(hub: Hub, su: Any, co: dict[str, Any], day: date) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        c = await tx.one("SELECT id, code, kind FROM core.companies WHERE id = :id", id=co["id"])
        out = await hr.open_round(tx, c, day, await S.owner_zone(tx))
    assert out is not None
    return dict(await su.fetchrow("SELECT * FROM people.hr_rounds WHERE ref = $1", out["ref"]))


async def test_the_round_flags_and_its_cards(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    star, weak, plain = f"{co['code']}-TECH-MGR", f"{co['code']}-SALES-MGR", f"{co['code']}-FIN-MGR"
    await _scores(su, star, 9.0, 8.8)
    await _scores(su, weak, 3.0, 3.2)
    await _scores(su, plain, 7.0, 7.0)
    day = jalali_day(1, date(2031, 7, 1) + timedelta(days=secrets.randbelow(3000)))
    r = await _round(hub, su, co, day)
    assert r["evaluator_code"] == f"{co['code']}-HR-MGR" and r["month"] == hr.month_key(day)
    flags = {e["code"]: e["flags"] for e in json.loads(r["employees"])}
    assert flags[weak] == ["demote_candidate", "dismiss_candidate"]
    assert flags[plain] == []
    assert await su.fetchval("SELECT title FROM work.work WHERE id = $1", r["work_id"])
    async with hub.db.tx(await hub.companies.ids()) as tx:
        c = await tx.one("SELECT id, code, kind FROM core.companies WHERE id = :id", id=co["id"])
        assert await hr.open_round(tx, c, day, await S.owner_zone(tx)) is None  # once a month
    hrm = await agent_headers(f"{co['code']}-HR-MGR")
    base = {"kind": "evaluation", "title": "ارزیابی", "risk": "low"}
    unflagged = {
        **base,
        "payload": {
            "employee": plain,
            "recommendation": "promote",
            "round": r["ref"],
            "change": {"title_fa": "ارشد"},
            "evidence": [{"kind": "link", "ref": "O-1"}],
        },
    }
    resp = await client.post("/internal/v1/decisions", headers={**hrm, **idem()}, json=unflagged)
    assert resp.status_code == 422 and "override_reason" in resp.text
    unflagged["payload"]["override_reason"] = "کار درخشان این ماه"
    resp = await client.post("/internal/v1/decisions", headers={**hrm, **idem()}, json=unflagged)
    assert resp.status_code == 201, resp.text
    assert resp.json()["payload"]["unflagged"] is True
    norounds = {**base, "payload": {"employee": weak, "recommendation": "demote", "evidence": []}}
    assert (
        await client.post("/internal/v1/decisions", headers={**hrm, **idem()}, json=norounds)
    ).status_code == 422
    # dismiss: the flagged one, with its open work handed to the plain one
    work = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, assignee_id, status)
           SELECT company_id, 'one_off', 'open', 'owner', 'owner', id, 'queued' FROM core.employees WHERE code = $1
           RETURNING id""",
        weak,
    )
    card = {
        **base,
        "payload": {
            "employee": weak,
            "recommendation": "dismiss",
            "round": r["ref"],
            "transfer_to": plain,
            "evidence": [{"kind": "metric", "ref": "score", "note": "3.0"}],
        },
    }
    resp = await client.post("/internal/v1/decisions", headers={**hrm, **idem()}, json=card)
    assert resp.status_code == 201, resp.text
    ref = resp.json()["ref"]
    assert ref in await su.fetchval("SELECT decisions FROM people.hr_rounds WHERE id = $1", r["id"])
    h = owner_session["headers"]
    nostep = await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={})
    assert nostep.status_code == 403 and nostep.json()["code"] == "step_up_required"
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    ok = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **idem(), **su_h}, json={}
    )
    assert ok.status_code == 200, ok.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await D.apply_effect(tx, ref, SYSTEM)
    assert (
        await su.fetchval("SELECT status FROM core.employees WHERE code = $1", weak) == "dismissed"
    )
    assignee = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1",
        work,
    )
    assert assignee == f"{co['code']}-CEO"  # a manager's open work goes up (§3.3), not lost


async def test_a_promotion_that_breaks_the_envelope_is_refused_and_changes_nothing(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    star = f"{co['code']}-TECH-MGR"
    await _scores(su, star, 9.0, 8.8)
    await su.execute("""UPDATE core.employees SET score_owner_avg = 9 WHERE code = $1""", star)
    await su.execute(
        """INSERT INTO people.stars (company_id, employee_id, week, stars, counted, by_kind, by_code, reason_md)
           SELECT company_id, id, $2, 5, true, 'agent', 'x', 'r' FROM core.employees WHERE code = $1""",
        star,
        date(2000, 1, 1),
    )
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', 1000)""",
        co["id"],
        co["code"],
    )
    day = jalali_day(1, date(2032, 1, 1) + timedelta(days=secrets.randbelow(3000)))
    r = await _round(hub, su, co, day)
    hrm = await agent_headers(f"{co['code']}-HR-MGR")
    card = {
        "kind": "evaluation",
        "title": "ارتقا",
        "payload": {
            "employee": star,
            "recommendation": "promote",
            "round": r["ref"],
            "override_reason": "ستاره",
            "change": {"title_fa": "مدیر ارشد", "quota_estimate_month": {"tokens": 5000}},
            "evidence": [{"kind": "metric", "ref": "score"}],
        },
    }
    resp = await client.post("/internal/v1/decisions", headers={**hrm, **idem()}, json=card)
    assert resp.status_code == 201, resp.text
    ref = resp.json()["ref"]
    h = owner_session["headers"]
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    no = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **idem(), **su_h}, json={}
    )
    assert no.status_code == 409 and no.json()["code"] == "envelope_exceeded"
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", ref) == "pending"
    )
    assert (
        await su.fetchval("SELECT title_fa FROM core.employees WHERE code = $1", star)
        != "مدیر ارشد"
    )


async def test_hr_rounds_do_nothing_while_the_holding_is_locked(hub: Hub, su: Any) -> None:
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    day = jalali_day(1, date(2033, 1, 1))
    async with holding_switch(su, "engaged"):
        out = await acts.hr_rounds(day.isoformat())
    assert out == {"skipped": True, "reason": "holding_locked"}
    async with holding_switch(su, "released"):
        quiet = await acts.hr_rounds((day + timedelta(days=1)).isoformat())
    assert quiet["opened"] == []  # only on the 1st of the Jalali month


# -------------------------------------------------------------- PR-082 --
async def test_pr082_is_active_on_the_third_of_the_jalali_month(hub: Hub, su: Any) -> None:
    p = await su.fetchrow("SELECT * FROM oversight.current_protocols WHERE ref = 'PR-082'")
    assert p["status"] == "active" and p["calendar"] == "jalali" and "BYMONTHDAY=3" in p["schedule"]
    assert p["check_md"] == O.PR082_CHECK and p["version"] >= 2
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'oversight.protocol_activate' AND target_ref LIKE 'PR-082@%'"
        )
        >= 1
    )
    third, fourth = jalali_day(3, date(2031, 1, 1)), jalali_day(4, date(2031, 1, 1))
    assert O.jalali_due(dict(p), third) and not O.jalali_due(dict(p), fourth)
    assert O.jalali_due({"calendar": "gregorian", "schedule": p["schedule"]}, fourth)
    d = protocol_desired("PR-082", p["schedule"], "Asia/Tehran", False, "jalali")
    cal = d.spec.calendars[0]
    days = cal.day_of_month[0] if cal.day_of_month else None
    assert days is None or (days.start, days.end) == (1, 31)  # every day; the run checks it
    assert cal.hour[0].start == 10 and not cal.day_of_week[1:]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await O.activate_pr082(tx) is False  # already active: no second version


async def test_pr082_does_nothing_off_its_day_or_while_the_holding_is_locked(
    hub: Hub, su: Any
) -> None:
    from hq_api.worker.oversight_activities import OversightActivities

    acts = OversightActivities(hub, lambda: _ScopedTx(hub))
    before = await su.fetchval(
        "SELECT count(*) FROM oversight.protocol_runs WHERE protocol_ref = 'PR-082'"
    )
    async with holding_switch(su, "engaged"):
        assert (await acts.protocol_run("PR-082"))["skipped"] == "holding_locked"
    today = datetime.now(TEHRAN).date()
    if to_jalali(today)[2] != 3:
        async with holding_switch(su, "released"):
            assert (await acts.protocol_run("PR-082"))["skipped"] == "not_its_jalali_day"
    after = await su.fetchval(
        "SELECT count(*) FROM oversight.protocol_runs WHERE protocol_ref = 'PR-082'"
    )
    assert after == before  # no run row either way


def test_the_seed_ignores_an_unknown_key_with_a_warning(tmp_path: Any, caplog: Any) -> None:
    (tmp_path / "protocols").mkdir()
    (tmp_path / "protocols" / "oversight.yaml").write_text(
        "protocols:\n  - ref: PR-999\n    area: people\n    method: rule\n"
        "    schedule: 'FREQ=MONTHLY;BYMONTHDAY=3;BYHOUR=10;BYMINUTE=0'\n    scope: company\n"
        "    severity: low\n    answerable: manager\n    calendar: jalali\n    future_key: 1\n"
        "    title_fa: t\n    check: c\n",
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        rows = O.protocol_file(tmp_path)
    assert rows[0]["calendar"] == "jalali" and "future_key" in caplog.text


async def test_the_pr082_checker_reads_the_rounds(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    holding = await hub.companies.holding()
    day = jalali_day(3, date(2034, 1, 1) + timedelta(days=secrets.randbelow(2000)))
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = C.CheckCtx(
            tx,
            holding.id,
            holding.code,
            {co["code"]: co["id"]},
            datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            {},
        )
        out = await C.CHECKS["PR-082"](ctx)
    assert [p.key for p in out.problems] == [f"hr:{hr.month_key(day)}:none"]


# ---------------------------------------------------------------- claims --
async def _fact_checker(su: Any) -> str:
    code = "HQ-OVS-FC"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
           SELECT c.id, d.id, $1, 'employee', 'راستی‌آزما', 'Fact-checker', 'fact_checker'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'OVS'
           WHERE c.kind = 'holding' ON CONFLICT (code) DO NOTHING""",
        code,
    )
    return code


async def _deliverable_of(su: Any, code: str) -> str:
    emp = await su.fetchrow("SELECT id, company_id FROM core.employees WHERE code = $1", code)
    w = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
           VALUES ($1, 'one_off', 't', 'owner', 'owner') RETURNING id""",
        emp["company_id"],
    )
    return str(
        await su.fetchval(
            """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title)
               VALUES ($1, $2, $3, 'گزارش') RETURNING ref""",
            emp["company_id"],
            w,
            emp["id"],
        )
    )


def test_health_flags_are_rules() -> None:
    assert CL.health_flags(10, 3, 2, 5, 1) == (["truth", "reliability", "loops"], 0.2, 0.3)
    assert CL.health_flags(10, 2, 1, 4, 4) == ([], 1.0, 0.2)  # under 5 checked: no truth flag
    assert CL.health_flags(0, 0, 0, 0, 0) == ([], None, 0.0)


async def test_claims_are_recorded_by_checkers_and_feed_the_board_and_hr(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    author = f"{co['code']}-GROWTH-MGR"
    fc = await agent_headers(await _fact_checker(su))
    dls = [await _deliverable_of(su, author) for _ in range(5)]
    for i, dl in enumerate(dls):
        verdict = "refuted" if i == 0 else "confirmed"
        body = {
            "deliverable": dl,
            "claim_md": f"ادعای {i}: ۲۰٪ رشد",
            "verdict": verdict,
            "evidence": [{"kind": "metric", "ref": "growth.users", "note": "۱۲٪"}]
            if i == 0
            else [],
        }
        r = await client.post("/internal/v1/claims", headers={**fc, **idem()}, json=body)
        assert r.status_code == 201, r.text
    bare = {"deliverable": dls[1], "claim_md": "x", "verdict": "refuted", "evidence": []}
    assert (
        await client.post("/internal/v1/claims", headers={**fc, **idem()}, json=bare)
    ).status_code == 422
    staff = await agent_headers(f"{co['code']}-TECH-MGR")
    denied = await client.post(
        "/internal/v1/claims", headers={**staff, **idem()}, json={**bare, "verdict": "confirmed"}
    )
    assert denied.status_code == 403 and denied.json()["code"] == "policy_denied"
    page = await client.get(f"/api/v1/claims?employee={author}&verdict=refuted", headers=owner)
    assert page.status_code == 200 and len(page.json()["items"]) == 1
    assert page.json()["items"][0]["checked_by"]["code"] == "HQ-OVS-FC"
    board = await client.get(f"/api/v1/runs/health?company={co['code']}&period=7d", headers=owner)
    row = next(x for x in board.json()["items"] if x["employee"] == author)
    assert row["claims_checked"] == 5 and row["refuted"] == 1 and row["flags"] == ["truth"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        facts = await hr.facts(
            tx,
            co["id"],
            datetime.now(UTC) - timedelta(days=1),
            datetime.now(UTC) + timedelta(days=1),
        )
    assert next(e for e in facts if e["code"] == author)["refuted_claims"] == 1
