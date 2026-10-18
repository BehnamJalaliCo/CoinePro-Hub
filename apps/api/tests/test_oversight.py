"""Prompt 08 §2 (contract §18.1): the Chief Overseer — protocols, findings,
holds, watch mode, standing orders, challenges and compliance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from hq_api.domain import oversight as O
from hq_api.domain import oversight_checks as C
from hq_api.hub import Hub
from hq_common import charters

from .conftest import agent_headers, body_bytes, idem, step_up
from .test_agents import run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")
OVR = "HQ-OVR"


@pytest.fixture
def owner(owner_session: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = owner_session["headers"]
    return headers


@pytest.fixture
async def done_runs(su: Any) -> AsyncIterator[None]:
    """agent_headers() leaves a running test run per employee: end them."""
    yield
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE state = 'running' AND reason = 'test'"
    )


async def _post_signed(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    method: str,
    path: str,
    body: Any,
    action: str,
) -> httpx.Response:
    content = body_bytes(body)
    su = await step_up(
        hub, owner_session["session_id"], action, hashlib.sha256(content).hexdigest()
    )
    return await client.request(
        method,
        path,
        content=content,
        headers={**owner_session["headers"], **su, **idem(), "Content-Type": "application/json"},
    )


def protocol_body(**over: Any) -> dict[str, Any]:
    return {
        "title_fa": "هر قرارداد امضا شده بایگانی شده است",
        "area": "data",
        "check_md": "Every signed contract of the week is in the archive with its signature.",
        "method": "rule",
        "schedule": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0",
        "scope": "company",
        "evidence_md": "contract refs",
        "severity": "medium",
        "answerable": "ceo",
        **over,
    }


# -------------------------------------------------------------- protocols --
async def test_the_protocols_are_seeded_and_only_the_owner_seals_new_versions(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
) -> None:
    lib_file = O.protocol_file(charters.load().root)
    r = await client.get("/api/v1/oversight/protocols", headers=owner)
    assert r.status_code == 200, r.text
    got = {p["ref"]: p for p in r.json()}
    assert len(lib_file) == 52 and {p["ref"] for p in lib_file} <= set(got)
    assert len({p["area"] for p in lib_file}) == 11 and {"PR-099", "PR-100"} <= set(got)
    assert got["PR-070"]["method"] == "rule" and got["PR-001"]["version"] >= 1
    # Without the step-up: refused; with it bound to the exact body: a new protocol.
    plain = await client.post(
        "/api/v1/oversight/protocols", headers={**owner, **idem()}, json=protocol_body()
    )
    assert plain.status_code == 403 and plain.json()["code"] == "step_up_required"
    r = await _post_signed(
        client,
        hub,
        owner_session,
        "POST",
        "/api/v1/oversight/protocols",
        protocol_body(),
        "oversight.protocol",
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["ref"].startswith("PR-") and new["version"] == 1 and new["sealed_at"]
    # A pause is a new version; the old one stays (append-only).
    paused = protocol_body(status="paused", title_fa=new["title_fa"])
    r = await _post_signed(
        client,
        hub,
        owner_session,
        "PUT",
        f"/api/v1/oversight/protocols/{new['ref']}",
        paused,
        "oversight.protocol",
    )
    assert r.status_code == 200 and (r.json()["version"], r.json()["status"]) == (2, "paused")
    assert (
        await su.fetchval("SELECT count(*) FROM oversight.protocols WHERE ref = $1", new["ref"])
        == 2
    )
    bad = protocol_body(schedule="FREQ=YEARLY")
    r = await _post_signed(
        client, hub, owner_session, "POST", "/api/v1/oversight/protocols", bad, "oversight.protocol"
    )
    assert r.status_code == 422


# ------------------------------------------------------------- rule runs --
async def test_a_rule_protocol_runs_by_code_and_raises_one_finding(
    wk: dict[str, Any], su: Any, agents: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    calls = len(agents.fake.calls)
    await su.execute(
        """INSERT INTO egress.log (company_id, actor, run_id, tool, class, method, host, blocked_reason)
           VALUES ($1, $2, gen_random_uuid(), 'web.read', 'A0', 'GET', '10.10.1.1', 'private_address')""",
        co["id"],
        f"{co['code']}-CEO",
    )
    acts = wk["acts"].oversight
    out = await acts.protocol_run("PR-033")
    assert out["result"] == "fail" and out["new"] >= 1, out
    f = await su.fetchrow(
        """SELECT f.ref, f.severity, f.status, f.answerable_code, p.ref AS protocol FROM oversight.findings f
           JOIN oversight.protocols p ON p.id = f.protocol_id WHERE f.company_id = $1""",
        co["id"],
    )
    assert (f["severity"], f["status"], f["protocol"]) == ("critical", "open", "PR-033")
    assert f["answerable_code"]  # someone of the company (or the owner) answers
    run_row = await su.fetchrow(
        "SELECT result, by_kind, work_id, per_company FROM oversight.protocol_runs WHERE protocol_ref = 'PR-033'"
        " ORDER BY started_at DESC LIMIT 1"
    )
    assert (run_row["result"], run_row["by_kind"], run_row["work_id"]) == ("fail", "system", None)
    assert json.loads(run_row["per_company"])[co["code"]] == "fail"
    assert len(agents.fake.calls) == calls  # no model was asked
    # Found again while still open: the same finding, not a second one.
    again = await acts.protocol_run("PR-033")
    assert again["new"] == 0
    assert (
        await su.fetchval("SELECT count(*) FROM oversight.findings WHERE company_id = $1", co["id"])
        == 1
    )
    # A clean code check passes; the append-only counts carry to the next run.
    first = await acts.protocol_run("PR-073")
    second = await acts.protocol_run("PR-073")
    assert first["result"] == second["result"] == "pass"
    assert set(C.CHECKS) >= {"PR-010", "PR-011", "PR-033", "PR-070", "PR-072", "PR-073"}


async def test_a_judgement_protocol_is_the_overseers_work_within_the_daily_cap(
    wk: dict[str, Any], su: Any
) -> None:
    hub = wk["hub"]
    real = hub.settings
    from dataclasses import replace

    acts = wk["acts"].oversight
    try:
        hub.settings = replace(real, oversight_model_runs_per_day=10_000)
        out = await acts.protocol_run("PR-005")  # method llm
        assert out.get("work") and out["assignee"] == OVR, out
        w = await su.fetchrow(
            "SELECT budget_tokens, assignee_id FROM work.work WHERE ref = $1", out["work"]
        )
        assert w["budget_tokens"] == real.oversight_run_tokens
        qc = await acts.protocol_run("PR-001")  # method sample: QC
        assert qc["assignee"] == "HQ-OVS-MGR"
        hub.settings = replace(real, oversight_model_runs_per_day=0)
        capped = await acts.protocol_run("PR-004")
        assert capped == {"protocol": "PR-004", "skipped": "daily_cap"}
    finally:
        hub.settings = real
        await su.execute(
            """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now() FROM core.employees e
               WHERE e.id = r.employee_id AND e.code IN ('HQ-OVR', 'HQ-OVS-MGR') AND r.state = 'queued'"""
        )


# ------------------------------------------------------------------ holds --
async def _proposal(
    client: httpx.AsyncClient, co: str, kind: str = "proposal", **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"kind": kind, "title": "یک پیشنهاد آزمایشی", "why": "برای آزمون", **extra},
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def _hold(client: httpx.AsyncClient, kind: str, ref: str, who: str = OVR) -> httpx.Response:
    return await client.post(
        "/internal/v1/oversight/holds",
        headers={**await agent_headers(who), **idem()},
        json={"target": {"kind": kind, "ref": ref}, "reason_md": "شاهد کافی ندارد"},
    )


@pytest.mark.usefixtures("done_runs")
async def test_a_hold_stops_the_card_and_only_the_owner_releases_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    wk: dict[str, Any],
) -> None:
    co = (await new_company())["code"]
    d = await _proposal(client, co)
    r = await _hold(client, "decision", d["ref"])
    assert r.status_code == 201, r.text
    h = r.json()
    assert h["state"] == "held" and h["held_by"]["code"] == OVR and h["action"]["ref"] == d["ref"]
    assert (await _hold(client, "decision", d["ref"])).json()["ref"] == h["ref"]  # one open hold
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 423 and r.json()["code"] == "held"
    # The overseer cannot approve the card nor release its own hold.
    ovr = await agent_headers(OVR)
    r = await client.post(
        f"/internal/v1/decisions/{d['ref']}/approve", headers={**ovr, **idem()}, json={}
    )
    assert r.status_code == 403
    r = await client.post(
        f"/api/v1/oversight/holds/{h['ref']}/release", headers={**ovr, **idem()}, json={}
    )
    assert r.status_code in (401, 403)
    # The owner: release needs the step-up bound to the hold's ref.
    r = await client.post(f"/api/v1/oversight/holds/{h['ref']}/release", headers=owner, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_tok = await step_up(hub, owner_session["session_id"], "oversight.release", h["ref"])
    r = await client.post(
        f"/api/v1/oversight/holds/{h['ref']}/release",
        headers={**owner, **su_tok},
        json={"note": "دیدم"},
    )
    assert r.status_code == 200 and r.json()["state"] == "released"
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    # An approved card whose effect is still due waits while held.
    b = await _proposal(
        client, co, "budget_change",
        payload={"scope": {"scope_type": "company", "scope_ref": co}, "period": "month", "token_limit": 1000},
    )  # fmt: skip
    su_tok = await step_up(hub, owner_session["session_id"], "decision.approve", b["ref"])
    r = await client.post(
        f"/api/v1/decisions/{b['ref']}/approve", headers={**owner, **su_tok, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    hb = (await _hold(client, "decision", b["ref"])).json()
    with pytest.raises(ApplicationError) as err:
        await wk["acts"].decision_apply_effect(b["ref"])
    assert err.value.type == "HoldingLocked"
    r = await client.post(f"/api/v1/oversight/holds/{hb['ref']}/cancel", headers=owner, json={})
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert (await wk["acts"].decision_apply_effect(b["ref"]))["effect"] == "applied"


@pytest.mark.usefixtures("done_runs")
async def test_a_held_agent_only_reads_and_a_held_tool_never_runs(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    from .test_agents import order

    co = (await new_company())["code"]
    mgr = f"{co}-TECH-MGR"
    assert (await _hold(client, "employee", mgr)).status_code == 201
    assert (await _hold(client, "tool", f"{mgr}:knowledge.search")).status_code == 201
    await order(client, owner, co, department="TECH")
    row = (await runs_of(su, mgr))[-1]
    agents.fake.enqueue(
        mgr,
        step(
            "کار با نگه‌داشت",
            ("company.state", {}),
            ("knowledge.search", {"q": "گزارش"}),
            ("message.owner", {"body_md": "سلام"}),
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    actions = json.loads(
        await su.fetchval("SELECT actions FROM agents.steps WHERE run_id = $1", row["id"])
    )
    got = [(a["tool"], a["outcome"], a.get("code")) for a in actions]
    assert got[0][:2] == ("company.state", "ok")  # reading goes on
    assert got[1] == ("knowledge.search", "denied", "held")  # the held tool, even a read
    assert got[2] == ("message.owner", "denied", "held")


@pytest.mark.usefixtures("done_runs")
async def test_a_held_workshop_session_takes_no_message(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    owner_db: Any,
) -> None:
    from hq_api.workshop.runtime import FakeRuntime

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
        assert (await _hold(client, "session", ref)).status_code == 201
        r = await client.post(
            f"/api/v1/workshop/sessions/{ref}/messages",
            headers={**owner, **idem()},
            json={"body": "ادامه بده"},
        )
        assert r.status_code == 423 and r.json()["code"] == "held"
    finally:
        hub.workshop = None


# ------------------------------------------------------------------ watch --
@pytest.mark.usefixtures("done_runs")
async def test_in_watch_mode_a_high_risk_card_is_held(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    wk: dict[str, Any],
) -> None:
    co = (await new_company())["code"]
    r = await client.post("/api/v1/oversight/watch", headers=owner, json={"on": True})
    assert r.status_code == 200 and r.json()["on"] is True
    try:
        risky = await _proposal(client, co, risk="high")
        calm = await _proposal(client, co, risk="low")
        held = await su.fetchrow(
            "SELECT ref, state, watch, held_by_code FROM oversight.holds"
            " WHERE target_kind = 'decision' AND target_ref = $1",
            risky["ref"],
        )
        assert held and (held["state"], held["watch"], held["held_by_code"]) == ("held", True, OVR)
        assert not await su.fetchval(
            "SELECT 1 FROM oversight.holds WHERE target_kind = 'decision' AND target_ref = $1",
            calm["ref"],
        )
        await wk["acts"].oversight.protocol_run("PR-097")  # refreshes "while you were away"
        rep = (await client.get("/api/v1/oversight/watch", headers=owner)).json()
        assert rep["on"] is True and held["ref"] in rep["held"] and rep["report_at"]

    finally:
        r = await client.post("/api/v1/oversight/watch", headers=owner, json={"on": False})
        assert r.json()["on"] is False


async def test_watch_follows_khalvat_and_the_owners_absence(wk: dict[str, Any], su: Any) -> None:
    hub = wk["hub"]
    holding = await hub.companies.holding()
    await su.execute("UPDATE owner.presence SET khalvat = true WHERE id = 1")
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert (await O.evaluate_watch(tx, holding.id, holding.code)).get(
                "started"
            ) == "khalvat"
    finally:
        await su.execute("UPDATE owner.presence SET khalvat = false WHERE id = 1")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        now = datetime.now(UTC)
        out = await O.evaluate_watch(tx, holding.id, holding.code, now)
        assert out == {"on": False, "ended": "khalvat"}  # the owner is around
        far = now + timedelta(hours=7)  # past watch_after_hours (6) without the owner
        assert (await O.evaluate_watch(tx, holding.id, holding.code, far)).get("on") is True
        w = await O.open_watch(tx)
        assert w is not None
        await O.end_watch(tx, w, holding.code)


# -------------------------------------------------------- standing orders --
@pytest.mark.usefixtures("done_runs")
async def test_a_standing_order_applies_only_once_sealed(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    agents: Any,
) -> None:
    text = "هر یافته‌ی بحرانی را همان روز با مدیرعامل همان شرکت در میان بگذار"
    r = await client.post(
        "/api/v1/oversight/orders",
        headers={**owner, **idem()},
        json={"text_md": text, "source": "voice"},
    )
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    ref = r.json()["ref"]

    async def overseer_system() -> str:
        await client.post(
            "/api/v1/threads/N/messages", headers={**owner, **idem()}, json={"body": "گزارش؟"}
        )
        row = (await runs_of(su, OVR))[-1]
        since = len(agents.fake.calls)
        agents.fake.enqueue(OVR, step("دیدم"))
        await run(agents, row["id"])
        return next(c for c in agents.fake.calls[since:] if c.actor_ref == OVR).system or ""

    assert text not in await overseer_system()
    plain = await client.post(f"/api/v1/oversight/orders/{ref}/seal", headers=owner)
    assert plain.status_code == 403
    su_tok = await step_up(hub, owner_session["session_id"], "oversight.order", ref)
    r = await client.post(f"/api/v1/oversight/orders/{ref}/seal", headers={**owner, **su_tok})
    assert r.status_code == 200 and r.json()["status"] == "sealed"
    system = await overseer_system()
    assert text in system and ref in system
    await client.post(f"/api/v1/oversight/orders/{ref}/retire", headers=owner)


# --------------------------------------------------------------- findings --
@pytest.mark.usefixtures("done_runs")
async def test_a_finding_is_verified_only_with_evidence_of_the_fix(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ovr = await agent_headers(OVR)
    r = await client.post(
        "/internal/v1/oversight/findings",
        headers={**ovr, **idem()},
        json={"company": co, "severity": "high", "title_fa": "عدد بی‌منبع در گزارش", "answerable": "ceo",
              "evidence": [{"kind": "deliverable", "ref": "O-000001", "note": "no source"}]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["answerable"]["code"] == f"{co}-CEO" and f["status"] == "open"
    ref = f["ref"]
    # Verified without any evidence of a fix: refused (overseer and owner alike).
    r = await client.post(
        f"/internal/v1/oversight/findings/{ref}/status", headers=ovr, json={"status": "verified"}
    )
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/oversight/findings/{ref}/status", headers=owner, json={"status": "verified"}
    )
    assert r.status_code == 422
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/oversight/findings/{ref}/status", headers=ceo, json={"status": "verified"}
    )
    assert r.status_code == 403  # the answerable never verifies its own finding
    r = await client.post(
        f"/internal/v1/oversight/findings/{ref}/status", headers=ceo, json={"status": "fixed"}
    )
    assert r.status_code == 422  # fixed needs the evidence
    r = await client.post(
        f"/internal/v1/oversight/findings/{ref}/status",
        headers=ceo,
        json={
            "status": "fixed",
            "note": "منبع اضافه شد",
            "evidence": [{"kind": "link", "ref": "O-000002"}],
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "fixed"
    r = await client.post(
        f"/internal/v1/oversight/findings/{ref}/status", headers=ovr, json={"status": "verified"}
    )
    assert r.status_code == 200 and r.json()["status"] == "verified"
    got = (await client.get(f"/api/v1/oversight/findings/{ref}", headers=owner)).json()
    assert [h["status"] for h in got["history"]] == ["open", "fixed", "verified"]
    page = (
        await client.get("/api/v1/oversight/findings", headers=owner, params={"company": co})
    ).json()
    assert [x["ref"] for x in page["items"]] == [ref]


# ---------------------------------------------- challenges and compliance --
@pytest.mark.usefixtures("done_runs")
async def test_challenges_and_compliance(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    wk: dict[str, Any],
    su: Any,
) -> None:
    co = (await new_company())["code"]
    ovr = await agent_headers(OVR)
    due = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    r = await client.post(
        "/internal/v1/oversight/challenges",
        headers={**ovr, **idem()},
        json={
            "company": co,
            "title_fa": "کاهش هزینه‌ی هر خروجی",
            "criteria": [{"name_fa": "هزینه", "weight": 60}],
            "due_at": due,
        },
    )
    assert r.status_code == 201, r.text
    ch = r.json()["ref"]
    other = (await new_company())["code"]
    r = await client.post(
        f"/internal/v1/oversight/challenges/{ch}/submit",
        headers=await agent_headers(f"{other}-CEO"),
        json={"note": "x"},
    )
    assert r.status_code == 403
    r = await client.post(
        f"/internal/v1/oversight/challenges/{ch}/submit",
        headers=await agent_headers(f"{co}-CEO"),
        json={"note": "تحویل"},
    )
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    r = await client.post(
        f"/internal/v1/oversight/challenges/{ch}/score", headers=ovr, json={"score": 80}
    )
    assert r.status_code == 200 and r.json()["score"] == 80
    # Compliance: open findings weigh on it, per area from the protocol runs.
    await wk["acts"].oversight.oversight_tick()
    comp = {
        c["company"]: c
        for c in (await client.get("/api/v1/oversight/compliance", headers=owner)).json()
    }
    assert 0 <= comp[co]["score"] <= 100 and set(comp[co]["findings_open"]) == {
        "critical",
        "high",
        "medium",
        "low",
    }
    s = (await client.get("/api/v1/oversight/summary", headers=owner)).json()
    assert s["challenges_week"]["scored"] >= 1 and s["protocols"]["active"] >= 50
    assert (
        await su.fetchval(
            "SELECT count(*) FROM oversight.compliance WHERE day = current_date OR day = current_date - 1"
        )
        >= 1
    )


async def test_compliance_formula_with_fixed_data(
    su: Any, hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await O.load_protocol(tx, "PR-012")  # area authority
        run_a = await O.start_run(tx, p)
        await O.finish_run(tx, run_a["id"], "pass", per_company={co["code"]: "pass"})
        run_b = await O.start_run(tx, p)
        await O.finish_run(tx, run_b["id"], "fail", per_company={co["code"]: "fail"})
        c = await O.compute_compliance(tx, co["id"])
        assert c["by_area"] == {"authority": 50.0} and c["score"] == 50.0
        await O.raise_finding(
            tx,
            company_id=co["id"],
            company_code=co["code"],
            severity="high",
            title_fa="t",
            dedupe_key="x",
        )
        assert (await O.compute_compliance(tx, co["id"]))[
            "score"
        ] == 40.0  # minus 10 for an open high
