"""Prompt 04.1 hardening (docs/server-prompts/PROMPT_04_1_HARDENING.md §1).

Each test was written first and failed on the prompt 04 code."""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import DBAPIError

from hq_api.app import create_app
from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import notify
from hq_api.errors import ApiError, sqlstate_of
from hq_api.hub import Hub
from hq_api.policy import Policy

from .conftest import (
    agent_headers,
    idem,
    random_code,
    running_run,
    service_headers,
    signed_put,
    step_up,
    superuser,
)


async def _work(client: httpx.AsyncClient, owner: dict[str, str], co: str) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/work", headers={**owner, **idem()}, json={"company": co, "title": "کار"}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


# ---------------------------------------------------------------- 1.1 -------
async def test_1_1_switch_and_freeze_release_follow_authority(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    scope = f"company:{co}"
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**h, **idem()},
        json={"scope": scope, "state": "engaged", "reason": "owner"},
    )
    assert r.status_code == 200
    r = await client.post(
        "/internal/v1/control/kill-switch",
        headers={**ceo, **idem()},
        json={"scope": scope, "state": "released", "reason": "ceo"},
    )
    assert r.status_code == 403, r.text  # the owner's switch is the owner's to release
    st = await step_up(hub, sid, "kill_switch.release", scope)
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**h, **st, **idem()},
        json={"scope": scope, "state": "released", "reason": "owner"},
    )
    assert r.status_code == 200
    # A switch an agent of the company engaged: its CEO may release it.
    for state in ("engaged", "released"):
        r = await client.post(
            "/internal/v1/control/kill-switch",
            headers={**ceo, **idem()},
            json={"scope": scope, "state": state, "reason": "ceo"},
        )
        assert r.status_code == 200, r.text

    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    await client.post(
        "/api/v1/control/deploy-freeze",
        headers=h,
        json={"company": co, "until": soon, "reason": "owner"},
    )
    r = await client.post(
        "/internal/v1/control/deploy-freeze",
        headers=ceo,
        json={"company": co, "until": soon, "reason": "ceo"},
    )
    assert r.status_code == 200
    # The CEO lifts its own freeze; the owner's stays.
    r = await client.post(
        "/internal/v1/control/deploy-freeze",
        headers=ceo,
        json={"company": co, "until": past, "reason": "ceo"},
    )
    assert r.status_code == 200
    freezes = [f for f in r.json()["deploy_freezes"] if f["company"] == co]
    assert [f["created_by"] for f in freezes] == ["owner"]
    r = await client.post(
        "/internal/v1/control/deploy-freeze",
        headers=ceo,
        json={"company": co, "until": past, "reason": "x"},
    )
    assert r.status_code == 403  # nothing of its own left to lift
    # The pipeline's freeze: the pipeline or the owner, never the CEO.
    await client.post(
        "/internal/v1/control/deploy-freeze",
        headers=service_headers(),
        json={"company": co, "until": soon, "reason": "deploy"},
    )
    assert (
        await client.post(
            "/internal/v1/control/deploy-freeze",
            headers=ceo,
            json={"company": co, "until": past, "reason": "x"},
        )
    ).status_code == 403
    r = await client.post(
        "/internal/v1/control/deploy-freeze",
        headers=service_headers(),
        json={"company": co, "until": past, "reason": "done"},
    )
    assert r.status_code == 200
    assert [f["created_by"] for f in r.json()["deploy_freezes"] if f["company"] == co] == ["owner"]
    r = await client.post(
        "/api/v1/control/deploy-freeze",
        headers=h,
        json={"company": co, "until": past, "reason": "done"},
    )
    assert r.status_code == 200 and r.json()["active"] is False


# ---------------------------------------------------------------- 1.2 -------
async def test_1_2_score_history_is_append_only(
    hub: Hub, new_company: Callable[..., Any], owner_db: Any
) -> None:
    co = await new_company()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        emp = await tx.scalar(
            "SELECT id FROM core.employees WHERE company_id = :co AND kind = 'ceo'", co=co["id"]
        )
        await tx.exec(
            """INSERT INTO core.employee_scores (employee_id, company_id, month, value) VALUES
               (:e, :co, date_trunc('month', now() - interval '2 months')::date, 5),
               (:e, :co, date_trunc('month', now())::date, 6)""",
            e=emp,
            co=co["id"],
        )
    cases = [
        (
            "UPDATE core.employee_scores SET value = 9 WHERE employee_id = :e AND month < date_trunc('month', now())",
            "HQA01",
        ),
        (
            "UPDATE core.employee_scores SET month = date_trunc('month', now() - interval '5 months')::date WHERE employee_id = :e",
            None,
        ),
        ("UPDATE core.employee_scores SET company_id = company_id WHERE employee_id = :e", None),
        ("DELETE FROM core.employee_scores WHERE employee_id = :e", None),
    ]
    for sql, state in cases:
        async with hub.db.tx([co["id"]]) as tx:
            with pytest.raises(DBAPIError) as info:
                await tx.exec(sql, e=emp)
            assert sqlstate_of(info.value) in (
                (state,) if state else ("HQA01", "HQI01", "42501")
            ), sql
    async with hub.db.tx([co["id"]]) as tx:  # the current month's score columns may move
        assert (
            await tx.exec(
                "UPDATE core.employee_scores SET value = 7, computed_at = now() WHERE employee_id = :e AND month = date_trunc('month', now())::date",
                e=emp,
            )
            == 1
        )
    conn = await superuser()
    try:
        with pytest.raises(Exception) as info:
            await conn.execute("TRUNCATE core.employee_scores CASCADE")
        assert getattr(info.value, "sqlstate", None) == "HQA01"
        with pytest.raises(Exception) as info:
            await conn.execute("DELETE FROM core.employee_scores WHERE employee_id = $1", emp)
        assert getattr(info.value, "sqlstate", None) == "HQA01"
    finally:
        await conn.close()


# ---------------------------------------------------------------- 1.4 -------
async def test_1_4_nobody_approves_their_own_proposal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    await signed_put(
        client,
        hub,
        owner_session,
        "/api/v1/budgets",
        {
            "budgets": [
                {
                    "company": co,
                    "scope_type": "company",
                    "scope_ref": co,
                    "period": "month",
                    "usd_limit": "100",
                }
            ]
        },
        "budgets.update",
    )
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/work",
        headers={**ceo, **idem()},
        json={
            "department": "GROWTH",
            "title": "rec",
            "kind": "recurring",
            "escrow": {
                "token_cap_per_run": 1000,
                "usd_cap_per_month": "5",
                "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
            "schedule": {"rrule": "FREQ=DAILY", "timezone": "UTC"},
        },
    )
    assert r.status_code == 201, r.text
    ref = r.json()["decision"]
    r = await client.post(
        f"/internal/v1/decisions/{ref}/approve", headers={**ceo, **idem()}, json={}
    )
    assert r.status_code == 403 and "own_proposal" in r.json()["detail"], r.text
    r = await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={})
    assert r.status_code == 200  # it goes to the owner


# ---------------------------------------------------------------- 1.5 -------
async def test_1_5_agents_raise_urgent_only_for_incidents(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/notifications", headers=ceo, json={"level": "urgent", "title_fa": "فوری نیست"}
    )
    assert r.status_code == 201 and r.json()["level"] == "decision"  # downgraded
    r = await client.post(
        "/internal/v1/notifications",
        headers=ceo,
        json={"level": "urgent", "category": "service_down", "title_fa": "سرویس پایین است"},
    )
    assert r.status_code == 201 and r.json()["level"] == "urgent"
    levels = []
    for _ in range(notify.AGENT_URGENT_PER_HOUR + 1):
        r = await client.post(
            "/internal/v1/notifications",
            headers=ceo,
            json={"level": "urgent", "category": "security", "title_fa": "امنیت"},
        )
        levels.append(r.json()["level"])
    assert (
        levels[-1] == "decision" and levels.count("urgent") == notify.AGENT_URGENT_PER_HOUR - 1
    )  # rate cap
    await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": f"company:{co}", "state": "engaged", "reason": "x"},
    )
    r = await client.post(
        "/internal/v1/notifications", headers=ceo, json={"level": "info", "title_fa": "اطلاع"}
    )
    assert r.status_code in (403, 423)  # a locked company raises only urgent incidents
    r = await client.post(
        "/internal/v1/notifications",
        headers=service_headers(),
        json={"company": co, "level": "info", "title_fa": "سرویس"},
    )
    assert r.status_code == 201  # services are not limited


# ---------------------------------------------------------------- 1.6 -------
async def test_1_6_budget_change_scope_is_typed_and_inside_the_company(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")

    def body(scope: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "budget_change",
            "title": "بودجه",
            "payload": {"scope": scope, "period": "month", "usd_limit": "10"},
        }

    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json=body({"scope_type": "galaxy", "scope_ref": co}),
    )
    assert r.status_code == 422
    for scope in (
        {"scope_type": "company", "scope_ref": "PC"},
        {"scope_type": "department", "scope_ref": "PC-TECH"},
        {"scope_type": "role", "scope_ref": "PC:TY-CEO"},
        {"scope_type": "holding", "scope_ref": "HQ"},
    ):
        r = await client.post("/internal/v1/decisions", headers={**ceo, **idem()}, json=body(scope))
        assert r.status_code == 403, (scope, r.text)
    for scope in (
        {"scope_type": "company", "scope_ref": co},
        {"scope_type": "department", "scope_ref": f"{co}-TECH"},
    ):
        r = await client.post("/internal/v1/decisions", headers={**ceo, **idem()}, json=body(scope))
        assert r.status_code == 201, r.text


# ---------------------------------------------------------------- 1.7 -------
async def test_1_7_owner_amendments_are_applied(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-GROWTH-MGR"), **idem()},
        json={
            "kind": "hire",
            "title": "hire",
            "payload": {
                "company": co,
                "department": "GROWTH",
                "title_fa": "کارشناس",
                "title_en": "Specialist",
                "reason": "r",
                "model": "claude-sonnet-5-5",
                "effort": "medium",
            },
        },
    )
    ref = r.json()["ref"]
    st = await step_up(hub, sid, "decision.approve", ref)
    bad = await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**h, **st, **idem()},
        json={"amendments": {"effort": "galactic"}},
    )
    assert bad.status_code == 422
    st = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**h, **st, **idem()},
        json={"amendments": {"model": "claude-opus-5-5", "effort": "max"}},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["payload"]["model"] == "claude-sonnet-5-5" and d["amendments"] == {
        "model": "claude-opus-5-5",
        "effort": "max",
    }
    async with hub.db.tx(await hub.companies.ids()) as tx:
        emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
        row = await tx.one(
            "SELECT model, effort FROM llm.assignments WHERE scope_type = 'role' AND scope_ref = :r",
            r=f"{co}:{emp}",
        )
    assert (row["model"], row["effort"]) == ("claude-opus-5-5", "max")


# ---------------------------------------------------------------- 1.8 -------
async def test_1_8_action_classes_gate_every_agent_write(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    from hq_api.routes import internal
    from hq_api.security.deps import agent_principal

    co = (await new_company())["code"]
    mgr = await agent_principal(hub, f"{co}-GROWTH-MGR", run=await running_run(f"{co}-GROWTH-MGR"))
    ceo = await agent_principal(hub, f"{co}-CEO", run=await running_run(f"{co}-CEO"))
    with pytest.raises(ApiError) as info:
        await internal.action_gate(hub, mgr, "data.delete", "A4", escrow_classes=["A0", "A1", "A2"])
    assert info.value.code == "policy_denied" and "a4_forbidden_for_ai" in (info.value.detail or "")
    with pytest.raises(ApiError) as info:
        await internal.action_gate(hub, mgr, "kill_switch.set", "A2", escrow_classes=[])
    assert "a2_needs_role_or_escrow" in (info.value.detail or "")
    await internal.action_gate(
        hub, mgr, "work.delegate", "A2", escrow_classes=[]
    )  # granted by role
    await internal.action_gate(hub, ceo, "kill_switch.set", "A2", escrow_classes=[])
    await internal.action_gate(
        hub, mgr, "report.publish", "A2", escrow_classes=["A0", "A1", "A2"]
    )  # by escrow
    with pytest.raises(ApiError):
        await internal.action_gate(
            hub, ceo, "price.change", "A3", escrow_classes=["A0", "A1", "A2"]
        )
    assert set(internal.OP_CLASS.values()) <= {"A0", "A1", "A2"}


# ---------------------------------------------------------------- 1.9 -------
async def test_1_9_agent_scope_is_never_widened(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    assert "rescope" not in inspect.getsource(notify) and "set_config" not in inspect.getsource(
        notify
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM pg_proc WHERE proname = 'agent_notification_counts'"
        )
        == 1
    )
    a, b = (await new_company())["code"], (await new_company())["code"]
    ceo = await agent_headers(f"{a}-CEO")
    answers = []
    for to in (f"{b}-TECH-MGR", f"{b}-NOPE-77"):
        r = await client.post(
            "/internal/v1/work",
            headers={**ceo, **idem()},
            json={"company": b, "to": to, "title": "x"},
        )
        answers.append((r.status_code, r.json()["code"], r.json().get("detail")))
    assert answers[0] == answers[1] and answers[0][0] == 403, answers
    w = await _work(client, owner, a)
    answers = []
    for to in (f"{b}-TECH-MGR", f"{b}-NOPE-77"):
        r = await client.post(
            f"/internal/v1/work/{w['id']}/delegate", headers=ceo, json={"to": to, "title": "x"}
        )
        answers.append((r.status_code, r.json()["code"], r.json().get("detail")))
    assert answers[0] == answers[1] and answers[0][0] == 403, answers
    await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": f"company:{b}", "state": "engaged", "reason": "x"},
    )
    r = await client.post(
        "/internal/v1/work", headers={**ceo, **idem()}, json={"company": b, "title": "x"}
    )
    assert r.status_code == 423  # the destination company is locked too


# ---------------------------------------------------------------- 1.10 ------
async def test_1_10_integrity_lives_in_the_database(
    hub: Hub, new_company: Callable[..., Any], owner_db: Any, su: Any
) -> None:
    a, b = await new_company(), await new_company()
    ids: dict[str, Any] = {}
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        for k, co in (("a", a), ("b", b)):
            ids[f"emp_{k}"] = await tx.scalar(
                "SELECT id FROM core.employees WHERE company_id = :c AND kind = 'ceo'", c=co["id"]
            )
            ids[f"thread_{k}"] = await tx.scalar(
                "SELECT id FROM msg.threads WHERE company_id = :c AND kind = 'ceo'", c=co["id"]
            )
            ids[f"work_{k}"] = await tx.scalar(
                """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
                   VALUES (:c, 'one_off', 't', 'owner', 'owner') RETURNING id""",
                c=co["id"],
            )
    cross = [
        "INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, assignee_id) VALUES (:a, 'one_off', 't', 'owner', 'owner', :emp_b)",
        "INSERT INTO work.work_events (work_id, company_id, kind, actor_kind, actor_code) VALUES (:work_b, :a, 'xx', 'owner', 'owner')",
        "INSERT INTO work.escrows (company_id, work_id, token_cap_per_run, usd_cap_per_month, expires_at) VALUES (:a, :work_b, 1, 1, now() + interval '1 day')",
        "INSERT INTO work.schedules (company_id, work_id, rrule) VALUES (:a, :work_b, 'FREQ=DAILY')",
        "INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title) VALUES (:a, :work_b, :emp_a, 't')",
        "INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title) VALUES (:a, :work_a, :emp_b, 't')",
        "INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code, work_id) VALUES (:a, 'proposal', 'A1', 't', 'owner', 'owner', :work_b)",
    ]
    for sql in cross:
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            with pytest.raises(DBAPIError) as info:
                await tx.exec(sql, a=a["id"], b=b["id"], **ids)
            assert sqlstate_of(info.value) == "23503", sql
    # messages: number, ref and company always come from the thread
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        m = await tx.one(
            """INSERT INTO msg.messages (thread_id, company_id, seq, ref, author_kind, author_code, body)
               VALUES (:t, :b, 999, 'FORGED-9', 'owner', 'owner', 'x') RETURNING company_id, seq, ref""",
            t=ids["thread_a"],
            b=b["id"],
        )
    assert m["company_id"] == a["id"] and m["ref"] != "FORGED-9" and m["seq"] < 999
    # a decided decision is sealed
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        dec = await tx.scalar(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code)
               VALUES (:a, 'proposal', 'A1', 't', 'agent', 'X-CEO') RETURNING id""",
            a=a["id"],
        )
        await tx.exec(
            """UPDATE cartable.decisions SET status = 'approved', decided_at = now(), decided_by_kind = 'owner',
                         decided_by_code = 'owner', note = 'first' WHERE id = :d""",
            d=dec,
        )
    for sql in (
        "UPDATE cartable.decisions SET note = 'second' WHERE id = :d",
        "UPDATE cartable.decisions SET amendments = '{}' WHERE id = :d",
        "UPDATE cartable.decisions SET decided_at = now() WHERE id = :d",
    ):
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            with pytest.raises(DBAPIError) as info:
                await tx.exec(sql, d=dec)
            assert sqlstate_of(info.value) in ("HQI01", "HQS01"), sql
    # llm.assignments: never written directly by the api role
    async with hub.db.tx(await hub.companies.ids()) as tx:
        with pytest.raises(DBAPIError) as info:
            await tx.exec(
                "INSERT INTO llm.assignments (scope_type, scope_ref, effort) VALUES ('company', :c, 'low')",
                c=a["code"],
            )
        assert sqlstate_of(info.value) == "42501"
    async with hub.db.tx(
        [a["id"]]
    ) as tx:  # through the scoped function, only inside the caller's companies
        with pytest.raises(DBAPIError):
            await tx.exec(
                "SELECT llm.put_assignment('company', :c, NULL, NULL, 'low', NULL)", c=b["code"]
            )
    async with hub.db.tx([a["id"]]) as tx:
        await tx.exec(
            "SELECT llm.put_assignment('company', :c, NULL, NULL, 'low', NULL)", c=a["code"]
        )
    # audit.at is the database clock, whatever the client sends
    async with hub.db.tx([a["id"]]) as tx:
        await tx.exec(
            """INSERT INTO audit.entries (at, actor_kind, actor_code, principal_kind, company_id, action, action_class,
                   target_kind, target_ref) VALUES ('2000-01-01', 'owner', 'owner', 'owner', :a, 'test.clock', 'A0', 'test', 'x')""",
            a=a["id"],
        )
        at = await tx.scalar(
            "SELECT at FROM audit.entries WHERE action = 'test.clock' AND company_id = :a",
            a=a["id"],
        )
    assert at > datetime.now(UTC) - timedelta(minutes=5)


# ---------------------------------------------------------------- 1.11 ------
async def test_1_11_anchor_catches_a_rewritten_chain(hub: Hub, tmp_path: Any) -> None:
    from hq_api import audit

    path = tmp_path / "audit-chain.jsonl"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        head = await audit.write_anchor(tx, path)
        ok = await audit.verify(tx, anchor_file=path)
    assert ok["ok"] is True and json.loads(path.read_text().splitlines()[-1])["seq"] == head["seq"]
    # The whole chain rewritten together with its head looks consistent in
    # Postgres, but no longer matches the anchor kept outside it.
    with path.open("a") as fh:
        fh.write(
            json.dumps({"seq": head["seq"], "hash": "0" * 64, "at": "2026-10-17T00:00:00Z"}) + "\n"
        )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        bad = await audit.verify(tx, anchor_file=path)
    assert (
        bad["ok"] is False and bad["first_bad_seq"] == head["seq"] and bad["anchor"] == "mismatch"
    )


# ---------------------------------------------------------------- 1.13 ------
async def test_1_13_colour_slots(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    cos = {c["code"]: c for c in (await client.get("/api/v1/companies", headers=owner)).json()}
    assert (cos["PC"]["color_index"], cos["FX"]["color_index"], cos["TY"]["color_index"]) == (
        1,
        2,
        3,
    )
    assert cos["HQ"]["color_index"] is None
    r = await client.patch(
        "/api/v1/companies/TY",
        headers={**owner, "If-Match": str(cos["TY"]["version"])},
        json={"color_index": 9},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- 1.14 ------
async def test_1_14_error_codes(
    hub: Hub,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    dead = replace(hub, policy=Policy("http://127.0.0.1:9", timeout=0.5))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(dead)), base_url="https://hq.test"
    ) as c:
        r = await c.post(
            "/internal/v1/decisions",
            headers={**await agent_headers(f"{co}-CEO"), **idem()},
            json={"kind": "proposal", "title": "x", "payload": {}},
        )
    await dead.policy.aclose()
    assert (r.status_code, r.json()["code"]) == (503, "policy_unavailable")
    r = await client.patch(f"/api/v1/companies/{co}", headers=h, json={"name_en": "x"})
    assert (r.status_code, r.json()["code"]) == (428, "precondition_required")
    conn = (await client.get("/api/v1/connections", headers=h)).json()[1]
    st = await step_up(hub, owner_session["session_id"], "connection.update", conn["id"])
    r = await client.patch(
        f"/api/v1/connections/{conn['id']}", headers={**h, **st}, json={"display_name": "x"}
    )
    assert (r.status_code, r.json()["code"]) == (428, "precondition_required")
    assert "version" in conn
    spec = client._transport.app.openapi()  # type: ignore[attr-defined]
    assert "428" in spec["paths"]["/api/v1/connections/{id}"]["patch"]["responses"]
    assert random_code() and uuid.uuid4()
