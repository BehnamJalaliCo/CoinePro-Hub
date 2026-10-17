"""Organisation and work through the API (contract §3, §4)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import recurrence
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up


async def hire(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, Any], co: str, dept: str = "TECH"
) -> str:
    """Hire through the real path: proposal -> owner approval (step-up) -> effect.
    An agent's hire names an employee charter (prompt 05): TECH's SRE."""
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-{dept}-MGR"), **idem()},
        json={
            "kind": "hire",
            "title": "استخدام کارمند",
            "payload": {
                "company": co,
                "department": dept,
                "role": "sre",
                "title_fa": "کارشناس",
                "title_en": "Specialist",
                "reason": "need",
                "duties": ["x"],
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
        },
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    su = await step_up(hub, owner["session_id"], "decision.approve", ref)
    a = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**owner["headers"], **su, **idem()}, json={}
    )
    assert a.status_code == 200, a.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, ref, SYSTEM)
    return str(out["employee"])


async def test_companies_templates_and_versions(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    listed = (await client.get("/api/v1/companies", headers=h)).json()
    assert listed[0]["kind"] == "holding"
    assert {"code", "counts", "kill_switch", "version"} <= listed[0].keys()
    tpl = (await client.get("/api/v1/templates", headers=h)).json()
    assert {t["key"] for t in tpl} >= {"standard", "holding"}
    assert next(t for t in tpl if t["key"] == "standard")["departments"] == [
        "TECH",
        "GROWTH",
        "SALES",
        "PRODUCT",
        "FIN",
        "QUANT",
        "AIOPS",
        "HR",
    ]

    from .conftest import random_code

    code = random_code("N")
    body = {"code": code, "name_fa": "شرکت نو", "name_en": "New Co", "template": "standard"}
    r = await client.post("/api/v1/companies", headers=h, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su = await step_up(hub, owner_session["session_id"], "company.create", code)
    r = await client.post("/api/v1/companies", headers={**h, **su}, json=body)
    assert r.status_code == 201, r.text
    company = r.json()
    assert company["counts"]["employees_active"] == 9  # CEO + 8 managers, nobody numbered
    depts = (await client.get(f"/api/v1/companies/{code}/departments", headers=h)).json()
    assert len(depts) == 8 and all(d["manager"]["code"].endswith("-MGR") for d in depts)

    patch = {"name_en": "New Co Renamed"}
    assert (
        await client.patch(f"/api/v1/companies/{code}", headers=h, json=patch)
    ).status_code == 428
    r = await client.patch(f"/api/v1/companies/{code}", headers={**h, "If-Match": "99"}, json=patch)
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    r = await client.patch(
        f"/api/v1/companies/{code}", headers={**h, "If-Match": str(company["version"])}, json=patch
    )
    assert r.status_code == 200 and r.json()["name_en"] == "New Co Renamed"
    v = r.json()["version"]
    r = await client.patch(
        f"/api/v1/companies/{code}", headers={**h, "If-Match": str(v)}, json={"status": "archived"}
    )
    assert r.status_code == 403  # archiving needs step-up
    su = await step_up(hub, owner_session["session_id"], "company.archive", code)
    r = await client.patch(
        f"/api/v1/companies/{code}",
        headers={**h, **su, "If-Match": str(v)},
        json={"status": "archived"},
    )
    assert r.status_code == 200 and r.json()["status"] == "archived"

    d = depts[0]
    r = await client.patch(
        f"/api/v1/departments/{code}/{d['code']}",
        headers={**h, "If-Match": str(d["version"])},
        json={"name_en": "Tech & Platform"},
    )
    assert r.status_code == 200 and r.json()["name_en"] == "Tech & Platform"
    su = await step_up(hub, owner_session["session_id"], "department.create", code)
    r = await client.post(
        f"/api/v1/companies/{code}/departments",
        headers={**h, **su},
        json={
            "code": "LEGALX",
            "name_fa": "حقوقی",
            "name_en": "Legal",
            "manager_title_fa": "مدیر حقوقی",
            "manager_title_en": "Head of Legal",
        },
    )
    assert r.status_code == 201 and r.json()["manager"]["code"] == f"{code}-LEGALX-MGR"


async def test_employees_chart_pause_and_dismiss(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    emp_code = await hire(hub, client, owner_session, co)
    assert emp_code == f"{co}-TECH-01"
    e = (await client.get(f"/api/v1/employees/{emp_code}", headers=h)).json()
    assert e["model"] == {
        "connection": "claude-max",
        "model": "claude-sonnet-5-5",
        "effort": "high",
    }
    assert e["reports_to"]["code"] == f"{co}-TECH-MGR" and e["hired_by_decision"].startswith("D-")
    assert e["charter"] == {"role": "sre", "version": 1}
    page = (
        await client.get("/api/v1/employees", headers=h, params={"company": co, "limit": 3})
    ).json()
    assert len(page["items"]) == 3 and page["next_cursor"]
    rest = (
        await client.get(
            "/api/v1/employees", headers=h, params={"company": co, "cursor": page["next_cursor"]}
        )
    ).json()
    assert {x["code"] for x in page["items"]}.isdisjoint({x["code"] for x in rest["items"]})

    chart = (await client.get(f"/api/v1/org/{co}/chart", headers=h)).json()
    ceo = chart["roots"][0]
    assert ceo["kind"] == "ceo" and len(ceo["children"]) == 8
    tech = next(c for c in ceo["children"] if c["department"] == "TECH")
    assert [c["code"] for c in tech["children"]] == [emp_code]

    r = await client.patch(
        f"/api/v1/employees/{emp_code}",
        headers={**h, "If-Match": str(e["version"])},
        json={"display_name": "آرش"},
    )
    assert r.status_code == 200 and r.json()["display_name"] == "آرش"
    assert (await client.post(f"/api/v1/employees/{emp_code}/pause", headers=h)).json()[
        "status"
    ] == "paused"
    assert (await client.post(f"/api/v1/employees/{emp_code}/resume", headers=h)).json()[
        "status"
    ] == "active"

    body = {"reason": "test dismissal"}
    assert (
        await client.post(f"/api/v1/employees/{emp_code}/dismiss", headers=h, json=body)
    ).status_code == 403
    su = await step_up(hub, owner_session["session_id"], "employee.dismiss", emp_code)
    r = await client.post(f"/api/v1/employees/{emp_code}/dismiss", headers={**h, **su}, json=body)
    assert r.status_code == 200 and r.json()["knowledge_transfer_work"].startswith("W-")
    # The code is retired forever: the next hire in TECH gets 02, never 01.
    assert await hire(hub, client, owner_session, co) == f"{co}-TECH-02"


async def test_order_delegation_depth_budget_and_delivery(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    emp = await hire(hub, client, owner_session, co)
    order = {
        "company": co,
        "title": "کمپین رشد",
        "brief": "x",
        "priority": "P2",
        "budget": {"tokens": 100000, "usd": "5"},
    }
    assert (
        await client.post("/api/v1/work", headers=h, json=order)
    ).status_code == 422  # Idempotency-Key
    key = idem()
    r = await client.post("/api/v1/work", headers={**h, **key}, json=order)
    assert (
        r.status_code == 201
        and r.json()["assignee"]["code"] == f"{co}-CEO"
        and r.json()["depth"] == 0
    )
    root = r.json()
    replay = await client.post("/api/v1/work", headers={**h, **key}, json=order)
    assert replay.json()["id"] == root["id"] and replay.headers.get("idempotent-replay") == "true"
    other = await client.post(
        "/api/v1/work", headers={**h, **key}, json={**order, "title": "different"}
    )
    assert other.status_code == 409 and other.json()["code"] == "idempotency_conflict"

    # The hire is TECH's SRE (prompt 05: an agent's hire names a charter), so the chain runs in TECH.
    ceo, mgr = await agent_headers(f"{co}-CEO"), await agent_headers(f"{co}-TECH-MGR")
    assert (await client.post(f"/internal/v1/work/{root['id']}/accept", headers=ceo)).json()[
        "status"
    ] == "in_progress"
    r = await client.post(
        f"/internal/v1/work/{root['id']}/delegate",
        headers=ceo,
        json={"to": f"{co}-TECH-MGR", "title": "اجرای کمپین", "budget": {"tokens": 60000}},
    )
    assert r.status_code == 201, r.text
    child = r.json()
    assert child["depth"] == 1 and child["budget"]["tokens"] == 60000
    r = await client.post(
        f"/internal/v1/work/{child['id']}/delegate",
        headers=mgr,
        json={"to": emp, "title": "تولید محتوا", "budget": {"tokens": 70000}},
    )
    assert r.status_code == 409 and r.json()["code"] == "budget_exceeded"
    r = await client.post(
        f"/internal/v1/work/{child['id']}/delegate",
        headers=mgr,
        json={"to": emp, "title": "تولید محتوا"},
    )
    grand = r.json()
    assert r.status_code == 201 and grand["depth"] == 2 and grand["budget"]["tokens"] == 60000
    # A manager cannot delegate outside its department; nobody reaches depth 3.
    r = await client.post(
        f"/internal/v1/work/{child['id']}/delegate",
        headers=mgr,
        json={"to": f"{co}-GROWTH-MGR", "title": "x"},
    )
    assert r.status_code == 403 and r.json()["code"] == "policy_denied"
    r = await client.post(
        f"/internal/v1/work/{grand['id']}/delegate",
        headers=await agent_headers(emp),
        json={"to": emp, "title": "x"},
    )
    assert r.status_code == 403  # employees never delegate (policy) ...
    async with hub.db.tx(await hub.companies.ids()) as tx:  # ... and the database caps depth anyway
        from sqlalchemy.exc import DBAPIError

        from hq_api.errors import from_db_error

        with pytest.raises(DBAPIError) as info:
            await tx.exec(
                """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, parent_id)
                   SELECT company_id, 'one_off', 'depth 3', 'owner', 'owner', id FROM work.work WHERE id = :g""",
                g=grand["id"],
            )
        assert from_db_error(info.value).code == "delegation_depth_exceeded"

    detail = (await client.get(f"/api/v1/work/{grand['id']}", headers=h)).json()
    assert [s["depth"] for s in detail["chain"]] == [0, 1, 2]

    me = await agent_headers(emp)
    r = await client.post(
        f"/internal/v1/work/{grand['id']}/deliver",
        headers={**me, **idem()},
        json={
            "title": "پیش‌نویس محتوا",
            "summary": "s",
            "body": "متن",
            "produced_with": {
                "connection": "claude-max",
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
            "usage": {"input_tokens": 100, "output_tokens": 50, "equiv_cost_usd": "0.0012"},
        },
    )
    assert r.status_code == 200, r.text
    deliverable = r.json()["deliverable"]
    # Prompt 05: an agent's token belongs to a run, and a run's usage is booked by
    # the runtime from llm-router's ledger; the usage an agent reports is not counted.
    assert (
        r.json()["work"]["status"] == "delivered"
        and r.json()["work"]["budget"]["tokens_used"] == 0
    )

    r = await client.post(
        f"/api/v1/deliverables/{deliverable}/rating", headers={**h, **idem()}, json={"score": 8}
    )
    assert r.status_code == 200 and r.json()["rating"]["score"] == 8, r.text
    e = (await client.get(f"/api/v1/employees/{emp}", headers=h)).json()
    assert (
        e["score"]["owner_avg"] == 8.0
        and e["score"]["value"] is not None
        and e["score"]["rank_in_department"] == 1
    )
    assert e["recent_ratings"][0]["score"] == 8
    assert (await client.get(f"/api/v1/work/{grand['id']}", headers=h)).json()["status"] == "done"
    r = await client.post(
        f"/api/v1/deliverables/{deliverable}/rating",
        headers={**h, **idem()},
        json={"score": 9, "comment": "بهتر"},
    )
    assert r.json()["rating"]["history_count"] == 2

    # done needs evidence through the API too
    r = await client.post(
        "/api/v1/work",
        headers={**h, **idem()},
        json={"company": co, "department": "TECH", "title": "x"},
    )
    tech = r.json()
    assert tech["assignee"]["code"] == f"{co}-TECH-MGR" and tech["depth"] == 1
    assert (
        await client.post(f"/api/v1/work/{tech['id']}/complete", headers=h, json={"evidence": []})
    ).status_code == 422
    r = await client.post(
        f"/api/v1/work/{tech['id']}/complete",
        headers=h,
        json={"evidence": [{"kind": "link", "ref": "https://example.org/report"}]},
    )
    assert r.status_code == 200 and r.json()["status"] == "done"
    events = (await client.get(f"/api/v1/work/{tech['id']}/events", headers=h)).json()["items"]
    assert [e["kind"] for e in events] == ["created", "completed"]


async def test_cancel_cascade_patch_and_lists(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    root = (
        await client.post(
            "/api/v1/work", headers={**owner, **idem()}, json={"company": co, "title": "ریشه"}
        )
    ).json()
    child = (
        await client.post(
            f"/internal/v1/work/{root['id']}/delegate",
            headers=await agent_headers(f"{co}-CEO"),
            json={"to": f"{co}-SALES-MGR", "title": "فرزند"},
        )
    ).json()
    current = (await client.get(f"/api/v1/work/{root['id']}", headers=owner)).json()
    assert (
        current["status"] == "waiting" and current["version"] > root["version"]
    )  # delegation touched it
    r = await client.patch(
        f"/api/v1/work/{root['id']}",
        headers={**owner, "If-Match": str(current["version"])},
        json={"priority": "P1", "due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )
    assert r.status_code == 200 and r.json()["priority"] == "P1"
    listed = (
        await client.get("/api/v1/work", headers=owner, params={"company": co, "overdue": "true"})
    ).json()
    assert [w["ref"] for w in listed["items"]] == [root["ref"]] and listed["items"][0][
        "overdue"
    ] is True
    r = await client.post(
        f"/api/v1/work/{root['id']}/cancel", headers=owner, json={"reason": "تغییر برنامه"}
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await client.get(f"/api/v1/work/{child['id']}", headers=owner)).json()[
        "status"
    ] == "cancelled"
    assert (
        await client.post(
            f"/api/v1/work/{root['id']}/cancel", headers=owner, json={"reason": "again"}
        )
    ).status_code == 409


async def test_recurring_by_owner_and_planner(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    body = {
        "company": co,
        "department": "GROWTH",
        "title": "گزارش هفتگی سئو",
        "kind": "recurring",
        "escrow": {
            "allowed_action_classes": ["A0", "A1"],
            "token_cap_per_run": 20000,
            "usd_cap_per_month": "3",
            "expires_at": (datetime.now(UTC) + timedelta(days=60)).isoformat(),
        },
        "schedule": {"rrule": "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10", "timezone": "Asia/Tehran"},
    }
    r = await client.post("/api/v1/work", headers={**owner, **idem()}, json=body)
    assert r.status_code == 201, r.text
    w = r.json()
    assert w["escrow"]["status"] == "active" and w["schedule"]["status"] == "active"
    assert w["schedule"]["rrule"] == "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0"
    runs = (
        await client.get("/api/v1/work", headers=owner, params={"company": co, "kind": "one_off"})
    ).json()["items"]
    assert (
        len(runs) == 1 and runs[0]["budget"]["tokens"] == 20000
    )  # the first run, with the escrow's budget
    plan = (
        await client.get("/api/v1/planner", headers=owner, params={"scope": f"company:{co}"})
    ).json()
    assert plan["timezone"] and any(i["recurring"] for d in plan["days"] for i in d["items"])
    bad = {**body, "schedule": {"rrule": "FREQ=YEARLY", "timezone": "Asia/Tehran"}}
    r = await client.post("/api/v1/work", headers={**owner, **idem()}, json=bad)
    assert r.status_code == 422 and "schedule.rrule" in r.json()["fields"]


def test_recurrence_rules() -> None:
    rule = recurrence.parse("FREQ=DAILY")
    assert rule.rrule() == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
    start = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    occ = recurrence.occurrences(rule, "Asia/Tehran", start, start + timedelta(days=2))
    assert [o.isoformat() for o in occ] == [
        "2026-10-17T05:30:00+00:00",
        "2026-10-18T05:30:00+00:00",
    ]
    hourly = recurrence.parse("FREQ=HOURLY;INTERVAL=6;BYMINUTE=15")
    occ = recurrence.occurrences(hourly, "UTC", start, start + timedelta(days=1))
    assert [o.hour for o in occ] == [0, 6, 12, 18] and all(o.minute == 15 for o in occ)
    monthly = recurrence.parse("FREQ=MONTHLY;BYMONTHDAY=1,15;BYHOUR=8;UNTIL=20261201T000000Z")
    occ = recurrence.occurrences(monthly, "UTC", start, start + timedelta(days=90))
    assert [o.date().isoformat() for o in occ] == ["2026-11-01", "2026-11-15"]
    for bad in (
        "FREQ=HOURLY;INTERVAL=5",
        "FREQ=DAILY;COUNT=3",
        "FREQ=WEEKLY;BYDAY=1MO",
        "BYDAY=MO",
        "FREQ=DAILY;BYHOUR=25",
    ):
        with pytest.raises(ApiError) as info:
            recurrence.parse(bad)
        assert info.value.code == "validation_failed", bad
    assert recurrence.next_at(monthly, "UTC", datetime(2027, 1, 1, tzinfo=UTC)) is None
