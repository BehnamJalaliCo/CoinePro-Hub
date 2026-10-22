"""The review of prompt 8 (prompt 08.1, contract §18.15): holds, the kill
switch, the oversight runs and their share, findings, paused protocols, the
daily cap of 0, and nothing of oversight running while the holding is locked."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from hq_api import workflows_client
from hq_api.domain import backups
from hq_api.domain import oversight as O
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.workshop import domain as WD
from hq_api.workshop.runtime import ApprovalAsk, FakeRuntime, RuntimeEvent
from hq_common import charters

from .conftest import agent_headers, idem, step_up
from .test_agents import order, runs_of
from .test_oversight import _hold, _proposal, protocol_body
from .test_worker import result_of, set_switch

pytestmark = pytest.mark.usefixtures("relay")
OVR = "HQ-OVR"
OWNER = Principal(kind="owner", code="owner", role="owner")


@pytest.fixture
def owner(owner_session: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = owner_session["headers"]
    return headers


@pytest.fixture(autouse=True)
async def seeded(hub: Hub, owner_db: Any) -> None:
    holding = await hub.companies.holding()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await O.seed_protocols(tx, holding.id, charters.load().root)


@pytest.fixture
async def done_runs(su: Any) -> Any:
    yield
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE state = 'running' AND reason = 'test'"
    )
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e
           WHERE e.id = r.employee_id AND e.code IN ('HQ-OVR', 'HQ-OVS-MGR') AND r.state = 'queued'"""
    )


async def _cancel(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.post(f"/api/v1/oversight/holds/{ref}/cancel", headers=owner, json={})
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def _release(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str
) -> dict[str, Any]:
    tok = await step_up(hub, owner_session["session_id"], "oversight.release", ref)
    r = await client.post(
        f"/api/v1/oversight/holds/{ref}/release",
        headers={**owner_session["headers"], **tok},
        json={},
    )
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def _budget_card(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], co: str
) -> dict[str, Any]:
    """An approved budget_change card whose effect is still due."""
    b = await _proposal(
        client, co, "budget_change",
        payload={"scope": {"scope_type": "company", "scope_ref": co}, "period": "month", "token_limit": 1234},
    )  # fmt: skip
    tok = await step_up(hub, owner_session["session_id"], "decision.approve", b["ref"])
    r = await client.post(
        f"/api/v1/decisions/{b['ref']}/approve",
        headers={**owner_session["headers"], **tok, **idem()},
        json={},
    )
    assert r.status_code == 200, r.text
    return b


# ------------------------------------------------------------- §1.1 cancel --
@pytest.mark.usefixtures("done_runs")
async def test_a_cancelled_hold_cancels_the_action_and_nothing_held_ever_runs(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    wk: dict[str, Any],
) -> None:
    co = (await new_company())["code"]
    # An approved card whose effect waits in the queue: held, then cancelled.
    b = await _budget_card(client, hub, owner_session, co)
    hb = (await _hold(client, "decision", b["ref"])).json()
    with pytest.raises(ApplicationError) as err:
        await wk["acts"].decision_apply_effect(b["ref"])
    assert err.value.type == "HoldingLocked"
    assert (await _cancel(client, owner, hb["ref"]))["state"] == "cancelled"
    out = await wk["acts"].decision_apply_effect(b["ref"])
    assert out["effect"] == "cancelled" and out["changed"] is False  # never applied
    row = await su.fetchrow(
        "SELECT effect_status, effect_applied_at FROM cartable.decisions WHERE ref = $1", b["ref"]
    )
    assert (row["effect_status"], row["effect_applied_at"]) == ("cancelled", None)
    assert not await su.fetchval(
        "SELECT 1 FROM llm.budgets WHERE scope_type = 'company' AND scope_ref = $1 AND token_limit = 1234",
        co,
    )
    # The lifecycle of that card ends without the effect.
    await workflows_client.decision_decided(wk["hub"], b["ref"])
    assert (await result_of(wk["client"], f"decision-{b['ref']}"))["effect"] == "cancelled"
    # A pending card: the owner's rejection, «لغو از hold».
    d = await _proposal(client, co)
    hd = (await _hold(client, "decision", d["ref"])).json()
    await _cancel(client, owner, hd["ref"])
    card = await su.fetchrow(
        "SELECT status, decided_by_kind, note FROM cartable.decisions WHERE ref = $1", d["ref"]
    )
    assert tuple(card) == ("rejected", "owner", O.CANCEL_NOTE)
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 409  # nothing to approve any more
    # A work item: cancelled with its children.
    w = await order(client, owner, co, title="کار نگه‌داشته")
    hw = (await _hold(client, "work", w["ref"])).json()
    await _cancel(client, owner, hw["ref"])
    assert (
        await su.fetchval("SELECT status FROM work.work WHERE ref = $1", w["ref"]) == "cancelled"
    )
    # Release and cancel are the owner's activity (watch mode ends on it).
    acts = await su.fetch(
        """SELECT action, target_ref FROM owner.interactions
           WHERE action = 'oversight.hold_cancel' AND target_ref = ANY($1)""",
        [b["ref"], d["ref"], w["ref"]],
    )
    assert {a["target_ref"] for a in acts} == {b["ref"], d["ref"], w["ref"]}


# ------------------------------------------------- §1.3 workshop session --
@pytest.mark.usefixtures("done_runs")
async def test_a_hold_interrupts_a_running_session_and_a_release_lets_it_go_on(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    owner_db: Any,
    su: Any,
) -> None:
    from .test_workshop import grant, open_session, workspace

    rt = FakeRuntime()
    hub.workshop = rt
    try:
        co = await new_company()
        ws = await workspace(owner_db, co)
        g = await grant(client, hub, owner_session, ws)
        r = await open_session(client, owner, g["ref"])
        assert r.status_code == 201, r.text
        ref = r.json()["ref"]
        s = await su.fetchrow("SELECT id, state, external_id FROM workshop.sessions WHERE ref = $1", ref)
        assert s["external_id"] and s["state"] in WD.ACTIVE
        h = (await _hold(client, "session", ref)).json()
        s2 = await su.fetchrow("SELECT state, held, last_seq FROM workshop.sessions WHERE ref = $1", ref)
        assert (s2["state"], s2["held"]) == ("idle", "hold")
        assert rt.log_[ref][-1]["kind"] == "stop"  # interrupted at once on its runtime
        # Whatever the runtime still reports is not taken: no step, no push.
        push = RuntimeEvent(
            "approval_request", "push", {"action": "push_branch"}, state="waiting_approval",
            approval=ApprovalAsk(f"late-{ref}", "push_branch", "git push"), usd=None,
        )  # fmt: skip
        async with hub.db.tx(await hub.companies.ids()) as tx:
            out = await WD.ingest(
                tx, s["id"], [RuntimeEvent("command", "git push", {"cmd": "git push"}), push]
            )
        assert out["interrupt"] is True
        s3 = await su.fetchrow("SELECT state, last_seq FROM workshop.sessions WHERE ref = $1", ref)
        assert (s3["state"], s3["last_seq"]) == ("idle", s2["last_seq"])
        assert not await su.fetchval(
            "SELECT 1 FROM workshop.approvals WHERE external_id = $1", f"late-{ref}"
        )
        r = await client.post(
            f"/api/v1/workshop/sessions/{ref}/messages",
            headers={**owner, **idem()},
            json={"body": "ادامه بده"},
        )
        assert r.status_code == 423 and r.json()["code"] == "held"
        # The owner releases: it goes on (takes messages again).
        assert (await _release(client, hub, owner_session, h["ref"]))["state"] == "released"
        assert await su.fetchval("SELECT held FROM workshop.sessions WHERE ref = $1", ref) is None
        r = await client.post(
            f"/api/v1/workshop/sessions/{ref}/messages",
            headers={**owner, **idem()},
            json={"body": "ادامه بده"},
        )
        assert r.status_code == 201, r.text
        assert any(e["kind"] == "message" for e in rt.log_[ref])
        # Another session, held then cancelled: stopped for good.
        r = await open_session(client, owner, g["ref"], title="دومی")
        ref2 = r.json()["ref"]
        h2 = (await _hold(client, "session", ref2)).json()
        await _cancel(client, owner, h2["ref"])
        row = await su.fetchrow(
            "SELECT state, error_code FROM workshop.sessions WHERE ref = $1", ref2
        )
        assert tuple(row) == ("stopped", "hold_cancelled")
    finally:
        hub.workshop = None


# ------------------------------------------------------- §1.2 kill switch --
@pytest.mark.usefixtures("done_runs")
async def test_the_overseer_takes_over_a_switch_a_ceo_engaged_first(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ceo = await agent_headers(f"{co['code']}-CEO")
    scope = f"company:{co['code']}"
    r = await client.post(
        "/internal/v1/control/kill-switch",
        headers={**ceo, **idem()},
        json={"scope": scope, "state": "engaged", "reason": "خودم"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/internal/v1/oversight/kill-switch",
        headers={**await agent_headers(OVR), **idem()},
        json={"scope": scope, "reason": "ناظر کل: توقف"},
    )
    assert r.status_code == 200, r.text
    by = await su.fetchval(
        "SELECT changed_by_code FROM control.kill_switches WHERE company_id = $1", co["id"]
    )
    assert by == OVR  # the overseer's switch now
    r = await client.post(
        "/internal/v1/control/kill-switch",
        headers={**ceo, **idem()},
        json={"scope": scope, "state": "released", "reason": "آزاد"},
    )
    assert r.status_code == 403
    assert (
        await su.fetchval("SELECT state FROM control.kill_switches WHERE company_id = $1", co["id"])
        == "engaged"
    )
    # The overseer never releases either; the CEO engaging again changes nothing.
    r = await client.post(
        "/internal/v1/control/kill-switch",
        headers={**ceo, **idem()},
        json={"scope": scope, "state": "engaged", "reason": "دوباره"},
    )
    assert r.status_code == 200
    assert (
        await su.fetchval(
            "SELECT changed_by_code FROM control.kill_switches WHERE company_id = $1", co["id"]
        )
        == OVR
    )
    await su.execute(
        "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", co["id"]
    )


# --------------------------------------------------------- §2.2 the runs --
@pytest.mark.usefixtures("done_runs")
async def test_the_count_cap_never_stops_a_critical_protocol_and_nothing_is_skipped(
    wk: dict[str, Any], su: Any
) -> None:
    hub = wk["hub"]
    real = hub.settings
    acts = wk["acts"].oversight
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        medium, critical = [
            await O.new_version(
                tx, OWNER, holding.id, protocol_body(method="llm", severity=sev), ref=None,
                source="owner",
            )
            for sev in ("medium", "critical")
        ]  # fmt: skip
    try:
        hub.settings = replace(real, oversight_model_runs_per_day=0)
        assert await acts.protocol_run(medium["ref"]) == {
            "protocol": medium["ref"],
            "deferred": "daily_cap",
        }
        out = await acts.protocol_run(critical["ref"])
        assert out.get("work") and out["assignee"] == OVR, out
    finally:
        hub.settings = real
    results = await su.fetch(
        "SELECT protocol_ref, result FROM oversight.protocol_runs WHERE protocol_ref = ANY($1)",
        [medium["ref"], critical["ref"]],
    )
    assert {(r["protocol_ref"], r["result"]) for r in results} == {
        (medium["ref"], "deferred"),
        (critical["ref"], "pending"),
    }
    with pytest.raises(Exception, match="check"):  # `skipped` is no result any more
        await su.execute(
            "UPDATE oversight.protocol_runs SET result = 'skipped' WHERE protocol_ref = $1",
            medium["ref"],
        )
    # No protocol's last run is `skipped` (contract §18.15).
    assert not await su.fetchval("SELECT 1 FROM oversight.protocol_runs WHERE result = 'skipped'")


# ----------------------------------------------------------- §2.3 watch --
@pytest.mark.usefixtures("done_runs")
async def test_watch_mode_holds_a_ceos_card_and_not_again_what_the_owner_released(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await su.execute("UPDATE owner.presence SET khalvat = true WHERE id = 1")
    holding = await hub.companies.holding()
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', 50000000)
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET token_limit = 50000000""",
        co["id"],
        co["code"],
    )
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode) VALUES ($1, 'open', 'delegated')
           ON CONFLICT (company_id) DO UPDATE SET state = 'open', mode = 'delegated'""",
        holding.id,
    )
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await O.evaluate_watch(tx, holding.id, holding.code)
            assert await O.watch_on(tx)
        # A hire card the CEO decides: held as well.
        r = await client.post(
            "/internal/v1/decisions",
            headers={**await agent_headers(f"{co['code']}-TECH-MGR"), **idem()},
            json={
                "kind": "hire",
                "title": "استخدام SRE",
                "payload": {
                    "company": co["code"], "department": "TECH", "role": "sre",
                    "title_fa": "کارشناس پایداری", "title_en": "SRE", "reason": "پایش",
                    "model": "claude-haiku-5-5", "effort": "low",
                    "quota_estimate_month": {"tokens": 1_500_000},
                },
            },
        )  # fmt: skip
        assert r.status_code == 201, r.text
        card = r.json()
        assert card["approver"] and card["approver"]["code"] == f"{co['code']}-CEO"
        h = await su.fetchrow(
            "SELECT ref, watch FROM oversight.holds WHERE target_kind = 'decision' AND target_ref = $1"
            " AND state = 'held'",
            card["ref"],
        )
        assert h and h["watch"] is True
        # The owner releases it: the next sweep of the same watch leaves it alone.
        await _release(client, hub, owner_session, h["ref"])
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await O.hold_pending_cards(tx)
        assert not await su.fetchval(
            "SELECT 1 FROM oversight.holds WHERE target_kind = 'decision' AND target_ref = $1"
            " AND state = 'held'",
            card["ref"],
        )
        assert await su.fetchval(
            "SELECT 1 FROM owner.interactions WHERE action = 'oversight.hold_release' AND target_ref = $1",
            card["ref"],
        )
    finally:
        await su.execute("UPDATE owner.presence SET khalvat = false WHERE id = 1")
        await su.execute("UPDATE core.hiring SET state = 'closed', mode = NULL")
        async with hub.db.tx(await hub.companies.ids()) as tx:
            w = await O.open_watch(tx)
            if w is not None:
                await O.end_watch(tx, w, holding.code)


# ------------------------------------------------- §2.4 no hot loop --
@pytest.mark.usefixtures("done_runs")
async def _switch(su: Any, company_id: Any, state: str) -> None:
    await su.execute(
        """INSERT INTO control.kill_switches (company_id, state, reason) VALUES ($1, $2, 'test')
           ON CONFLICT (company_id) DO UPDATE SET state = $2, reason = 'test'""",
        company_id,
        state,
    )


async def test_an_effect_held_or_under_a_company_switch_waits_without_spinning(
    su: Any,
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    wk: dict[str, Any],
) -> None:
    co = await new_company()
    # Held: the workflow sleeps between attempts (lock_poll_s = 1 in tests).
    b = await _budget_card(client, hub, owner_session, co["code"])
    hb = (await _hold(client, "decision", b["ref"])).json()
    await workflows_client.decision_decided(wk["hub"], b["ref"])
    await asyncio.sleep(3)
    handle = wk["client"].get_workflow_handle(f"decision-{b['ref']}")
    attempts = len(
        [
            e
            async for e in handle.fetch_history_events()
            if e.HasField("activity_task_scheduled_event_attributes")
            and e.activity_task_scheduled_event_attributes.activity_type.name
            == "decision_apply_effect"
        ]
    )
    assert 1 <= attempts <= 6, attempts  # a hot loop makes hundreds
    await _release(client, hub, owner_session, hb["ref"])
    assert (await result_of(wk["client"], f"decision-{b['ref']}"))["result"] == "applied"
    # Under the company's own switch: the same wait, then the effect.
    b2 = await _budget_card(client, hub, owner_session, co["code"])
    await _switch(su, co["id"], "engaged")
    try:
        await workflows_client.decision_decided(wk["hub"], b2["ref"])
        await asyncio.sleep(3)
        assert (
            await su.fetchval(
                "SELECT effect_status FROM cartable.decisions WHERE ref = $1", b2["ref"]
            )
            == "pending"
        )
        handle = wk["client"].get_workflow_handle(f"decision-{b2['ref']}")
        n = len([e async for e in handle.fetch_history_events()])
        assert n < 150, n  # a hot loop makes thousands of events
    finally:
        await _switch(su, co["id"], "released")
    assert (await result_of(wk["client"], f"decision-{b2['ref']}"))["result"] == "applied"


# ---------------------------------------------- §2.5 compliance passes --
@pytest.mark.usefixtures("done_runs")
async def test_a_model_protocols_result_records_pass_for_every_company_it_covered(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    good, bad = await new_company(), await new_company()
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await O.new_version(
            tx, OWNER, holding.id, protocol_body(method="llm"), ref=None, source="owner"
        )
    ovr = await agent_headers(OVR)
    r = await client.post(
        "/internal/v1/oversight/findings",
        headers={**ovr, **idem()},
        json={"company": bad["code"], "protocol": p["ref"], "severity": "low", "title_fa": "کمبود"},
    )
    assert r.status_code == 201, r.text
    fi = r.json()["ref"]
    r = await client.post(
        "/internal/v1/oversight/protocol-runs/result",
        headers=ovr,
        json={"protocol": p["ref"], "result": "fail", "findings": [fi]},
    )
    assert r.status_code == 200, r.text
    per = r.json()["per_company"]
    assert per[bad["code"]] == "fail" and per[good["code"]] == "pass"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        c = await O.compute_compliance(tx, good["id"])
        assert c["protocols"]["passed"] >= 1
    # A finding of another protocol, not raised by this agent: refused.
    other = await su.fetchval(
        "SELECT ref FROM oversight.findings WHERE raised_by_kind = 'system' LIMIT 1"
    )
    if other:
        r = await client.post(
            "/internal/v1/oversight/protocol-runs/result",
            headers=ovr,
            json={"protocol": p["ref"], "result": "fail", "findings": [other]},
        )
        assert r.status_code == 422


# --------------------------------------------------- §2.6 who answers --
@pytest.mark.usefixtures("done_runs")
async def test_only_the_answerable_or_its_chain_moves_a_finding(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ovr = await agent_headers(OVR)
    r = await client.post(
        "/internal/v1/oversight/findings",
        headers={**ovr, **idem()},
        json={"company": co, "severity": "medium", "title_fa": "تست بی‌شاهد", "answerable": f"{co}-TECH-MGR"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    path = f"/internal/v1/oversight/findings/{ref}/status"
    other = await agent_headers(f"{co}-GROWTH-MGR")  # same company, not its chain
    r = await client.post(path, headers=other, json={"status": "acknowledged"})
    assert r.status_code == 403
    r = await client.post(path, headers=ovr, json={"status": "fixing"})
    assert r.status_code == 403  # the overseer does not answer for the company
    r = await client.post(
        path, headers=await agent_headers(f"{co}-CEO"), json={"status": "acknowledged"}
    )
    assert r.status_code == 200, r.text  # the top of the chain
    # Verified only after a `fixed` that carried evidence: its own evidence never counts.
    r = await client.post(
        path,
        headers=ovr,
        json={"status": "verified", "evidence": [{"kind": "link", "ref": "O-1"}]},
    )
    assert r.status_code == 422
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(
        path,
        headers=mgr,
        json={"status": "fixed", "evidence": [{"kind": "link", "ref": "O-2"}]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(path, headers=ovr, json={"status": "verified"})
    assert r.status_code == 200 and r.json()["status"] == "verified"


# ------------------------------------------------ §2.7 paused everywhere --
@pytest.mark.usefixtures("done_runs")
async def test_a_paused_protocol_is_refused_on_every_path(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await O.new_version(
            tx, OWNER, holding.id, protocol_body(method="llm", status="paused"), ref=None,
            source="owner",
        )  # fmt: skip
    ovr = await agent_headers(OVR)
    r = await client.post(
        "/internal/v1/oversight/findings",
        headers={**ovr, **idem()},
        json={"company": co, "protocol": p["ref"], "severity": "low", "title_fa": "x"},
    )
    assert r.status_code == 409, r.text
    r = await client.post(
        "/internal/v1/oversight/protocol-runs/result",
        headers=ovr,
        json={"protocol": p["ref"], "result": "pass"},
    )
    assert r.status_code == 409
    assert not await su.fetchval(
        "SELECT 1 FROM oversight.protocol_runs WHERE protocol_ref = $1", p["ref"]
    )
    # PR-070 (the backup hook) raises nothing while PR-070 is paused.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        pr70 = await O.load_protocol(tx, "PR-070")
        keep = {k: pr70[k] for k in O.ProtocolIn.model_fields}
        await O.new_version(
            tx, OWNER, holding.id, {**keep, "status": "paused"}, ref="PR-070", source="owner"
        )
    try:
        before = await su.fetchval(
            "SELECT count(*) FROM oversight.findings WHERE dedupe_key = 'PR-070:backup-hourly'"
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await backups.oversight_finding(tx, "stale", {"last_ok_at": None})
        after = await su.fetchval(
            "SELECT count(*) FROM oversight.findings WHERE dedupe_key = 'PR-070:backup-hourly'"
        )
        assert after == before
    finally:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await O.new_version(
                tx, OWNER, holding.id, {**keep, "status": "active"}, ref="PR-070", source="owner"
            )


# ------------------------------------------------------ daily cap of 0 --
async def test_a_daily_token_cap_of_zero_means_nothing_runs(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await order(client, owner, co)
    row = (await runs_of(su, f"{co}-CEO"))[-1]
    real = agents.runner.s
    agents.runner.s = replace(real, agent_daily_token_cap=0)
    try:
        c = await agents.runner.claim(str(row["id"]))
        assert (c.state, c.code) == ("final", "daily_cap")  # not "no cap"
        assert await agents.runner._daily_cap_reached()
    finally:
        agents.runner.s = real
    assert await su.fetchval("SELECT state FROM agents.runs WHERE id = $1", row["id"]) == "refused"
    async with agents.runner.hub.db.tx(await agents.runner.hub.companies.ids()) as tx:
        assert await O.share_spent(tx, 0, 0.2)  # no share of nothing either


# ------------------------------------- nothing while the holding is locked --
@pytest.mark.usefixtures("done_runs")
async def test_oversight_runs_nothing_on_its_own_while_the_holding_is_locked(
    wk: dict[str, Any], su: Any
) -> None:
    hub = wk["hub"]
    real = hub.settings
    acts = wk["acts"].oversight
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        llm, critical = [
            await O.new_version(
                tx, OWNER, holding.id, protocol_body(method="llm", severity=sev), ref=None,
                source="owner",
            )
            for sev in ("high", "critical")
        ]  # fmt: skip
        # Yesterday's deferred run, due first today.
        r = await O.start_run(tx, llm)
        await O.finish_run(tx, r["id"], "deferred", notes="test")
    await su.execute(
        "UPDATE oversight.protocol_runs SET started_at = now() - interval '1 day' WHERE id = $1",
        r["id"],
    )
    works_before = await su.fetchval(
        """SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code IN ('HQ-OVR', 'HQ-OVS-MGR')"""
    )
    runs_before = await su.fetchval("SELECT count(*) FROM oversight.protocol_runs")
    calls_before = await su.fetchval("SELECT count(*) FROM llm.calls")
    await set_switch(hub, holding.id, "engaged")
    try:
        hub.settings = replace(real, oversight_model_runs_per_day=10_000)
        for ref in (llm["ref"], critical["ref"], "PR-033", "PR-070"):
            assert await acts.protocol_run(ref) == {"protocol": ref, "skipped": "holding_locked"}
        tick = await acts.oversight_tick()
        assert tick["resumed"] == []  # the deferred run waits for the lock to lift
        week = await acts.oversight_weekly()
        assert week["work"] is None and week.get("skipped") == "holding_locked"
        assert await su.fetchval("SELECT count(*) FROM oversight.protocol_runs") == runs_before
        assert (
            await su.fetchval(
                """SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
                   WHERE e.code IN ('HQ-OVR', 'HQ-OVS-MGR')"""
            )
            == works_before
        )
        assert await su.fetchval("SELECT count(*) FROM llm.calls") == calls_before  # no model
    finally:
        hub.settings = real
        await set_switch(hub, holding.id, "released")
    # Once lifted, the deferred run goes first.
    assert any(x["protocol"] == llm["ref"] for x in (await acts.oversight_tick())["resumed"])
