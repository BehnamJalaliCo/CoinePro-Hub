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


@pytest.fixture(autouse=True)
async def seeded(hub: Hub, owner_db: Any) -> None:
    holding = await hub.companies.holding()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await O.seed_protocols(tx, holding.id, charters.load().root)


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
    # Prompt 8's 52, plus the ones later prompts seeded paused (prompts 10-12).
    assert len(lib_file) >= 52 and {p["ref"] for p in lib_file} <= set(got)
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
    assert (run_row["result"], run_row["by_kind"]) == ("fail", "system")
    assert json.loads(run_row["per_company"])[co["code"]] == "fail"
    assert len(agents.fake.calls) == calls  # no model was asked by the check
    # The failure wakes the overseer once (prompt 08 §2.3), with only the
    # evidence the code collected, within the overseer's charter.
    if out.get("woken"):
        w = await su.fetchrow(
            "SELECT id, brief, budget_tokens FROM work.work WHERE ref = $1", out["woken"]
        )
        assert w["id"] == run_row["work_id"] and "PR-033" in w["brief"]
        assert "finding.update" in w["brief"] and 0 < w["budget_tokens"] <= 200_000
    else:
        assert out.get("why") in ("once_a_day", "daily_cap", "oversight_share"), out
    # Found again while still open: the same finding, not a second one, and no wake.
    again = await acts.protocol_run("PR-033")
    assert again["new"] == 0 and "woken" not in again
    assert (
        await su.fetchval("SELECT count(*) FROM oversight.findings WHERE company_id = $1", co["id"])
        == 1
    )
    # A clean code check passes; the append-only counts carry to the next run.
    first = await acts.protocol_run("PR-073")
    second = await acts.protocol_run("PR-073")
    assert first["result"] == second["result"] == "pass"
    assert "woken" not in first and "woken" not in second  # a pass never wakes the overseer
    assert set(C.CHECKS) >= {"PR-010", "PR-011", "PR-033", "PR-070", "PR-072", "PR-073"}


async def test_every_code_checker_runs(
    wk: dict[str, Any], su: Any, new_company: Callable[..., Any]
) -> None:
    """Each checker's SQL runs against the real schema (a broken one would fail
    its protocol in production): a result, never an exception."""
    co = await new_company()
    await su.execute(
        """INSERT INTO ops.hub_health (company_id, at, data)
           SELECT id, now(), '{"up": {"api": 0}, "disk_used_pct": 91, "certificate_days_left": 5}'
           FROM core.companies WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET data = EXCLUDED.data"""
    )
    acts = wk["acts"].oversight
    results = {}
    for ref in sorted(C.CHECKS):
        out = await acts.protocol_run(ref)
        assert out.get("result") in ("pass", "fail"), (ref, out)
        results[ref] = out["result"]
    assert (
        results["PR-062"] == "fail"
    )  # the hub snapshot above: a service down, disk 91%, cert 5 days
    assert co["code"]


async def test_a_judgement_protocol_is_the_overseers_work_within_the_daily_cap(
    wk: dict[str, Any], su: Any
) -> None:
    from dataclasses import replace

    from hq_api.principal import Principal

    hub = wk["hub"]
    real = hub.settings
    acts = wk["acts"].oversight
    holding = await hub.companies.holding()
    owner = Principal(kind="owner", code="owner", role="owner")
    async with hub.db.tx(await hub.companies.ids()) as tx:  # fresh protocols: no run yet today
        llm = await O.new_version(
            tx, owner, holding.id, protocol_body(method="llm"), ref=None, source="owner"
        )
        qc = await O.new_version(
            tx, owner, holding.id, protocol_body(method="sample"), ref=None, source="owner"
        )
        capped = await O.new_version(
            tx, owner, holding.id, protocol_body(method="mystery"), ref=None, source="owner"
        )
    try:
        hub.settings = replace(real, oversight_model_runs_per_day=10_000)
        out = await acts.protocol_run(llm["ref"])
        assert out.get("work") and out["assignee"] == OVR, out
        w = await su.fetchrow("SELECT budget_tokens FROM work.work WHERE ref = $1", out["work"])
        assert w["budget_tokens"] == real.oversight_run_tokens
        assert (await acts.protocol_run(qc["ref"]))["assignee"] == "HQ-OVS-MGR"  # sampling: QC
        again = await acts.protocol_run(llm["ref"])  # an hourly one would be the same
        assert again["skipped"] == "once_a_day"
        # No CEO approved a hire for review (or another test already ran it today).
        # PR-098: nothing to review, already handed today, or a CEO's hire to review.
        pr98 = await acts.protocol_run("PR-098")
        assert pr98.get("why") == "nothing_to_review" or pr98.get("skipped") == "once_a_day" or (
            pr98.get("work") and pr98.get("assignee") == OVR
        ), pr98
        hub.settings = replace(real, oversight_model_runs_per_day=0)
        # Over the count cap: deferred to the next day, never `skipped` (8.1 §2.2).
        assert await acts.protocol_run(capped["ref"]) == {
            "protocol": capped["ref"],
            "deferred": "daily_cap",
        }
    finally:
        hub.settings = real
        await su.execute(
            """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
               FROM core.employees e
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
    # A cancel cancels the action itself (8.1 §1.1): the effect never runs.
    assert (await wk["acts"].decision_apply_effect(b["ref"]))["effect"] == "cancelled"


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


# ------------------------------------------- paused protocols (v1.4.4) --
async def test_paused_protocols_have_no_schedule_run_or_finding_and_do_not_count(
    wk: dict[str, Any], su: Any, hub: Hub, new_company: Callable[..., Any]
) -> None:
    from temporalio.service import RPCError

    from hq_api.principal import Principal
    from hq_api.worker import oversight_activities as OA
    from hq_api.worker import schedules

    lib_file = O.protocol_file(charters.load().root)
    paused = {p["ref"] for p in lib_file if p["status"] == "paused"}
    assert {"PR-043", "PR-053", "PR-082", "PR-090"} <= paused
    rows = await su.fetch(
        "SELECT ref, status FROM oversight.current_protocols WHERE ref = ANY($1)", list(paused)
    )
    assert {r["ref"]: r["status"] for r in rows} == dict.fromkeys(paused, "paused")
    acts = wk["acts"].oversight
    client = wk["client"]
    # A schedule left from before (an active version) is removed; none is made.
    stale = OA.protocol_desired("PR-043", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "Asia/Tehran", True)
    await schedules.upsert(client, stale, wk["tq"])
    out = await acts.reconcile(client, wk["tq"], "Asia/Tehran")
    assert f"{OA.PROTOCOL_PREFIX}PR-043" in out["deleted"]
    assert not {f"{OA.PROTOCOL_PREFIX}{ref}" for ref in paused} & set(out["protocols"])
    assert f"{OA.PROTOCOL_PREFIX}PR-033" in out["protocols"]  # an active one has its schedule
    for ref in paused:
        with pytest.raises(RPCError):
            await client.get_schedule_handle(f"{OA.PROTOCOL_PREFIX}{ref}").describe()
    # Run by hand: nothing (no run row, no finding).
    for ref in sorted(paused):
        assert await acts.protocol_run(ref) == {"protocol": ref, "skipped": "paused"}
    assert not await su.fetchval(
        "SELECT count(*) FROM oversight.protocol_runs WHERE protocol_ref = ANY($1)", list(paused)
    )
    assert not await su.fetchval(
        """SELECT count(*) FROM oversight.findings f JOIN oversight.protocols p ON p.id = f.protocol_id
           WHERE p.ref = ANY($1)""",
        list(paused),
    )
    # A protocol paused after it ran: its runs leave the compliance score.
    co = await new_company()
    holding = await hub.companies.holding()
    owner = Principal(kind="owner", code="owner", role="owner")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await O.new_version(
            tx, owner, holding.id, protocol_body(area="product"), ref=None, source="owner"
        )
        r = await O.start_run(tx, p)
        await O.finish_run(tx, r["id"], "fail", per_company={co["code"]: "fail"})
        assert (await O.compute_compliance(tx, co["id"]))["by_area"] == {"product": 0.0}
        await O.new_version(
            tx,
            owner,
            holding.id,
            protocol_body(area="product", status="paused"),
            ref=p["ref"],
            source="owner",
        )
        c = await O.compute_compliance(tx, co["id"])
        assert c["by_area"] == {} and c["protocols"] == {"passed": 0, "failed": 0}
        assert c["score"] == 100.0


# --------------------------------------- the oversight share (§2.3) --
async def test_with_the_share_spent_a_high_protocol_is_deferred_and_a_critical_one_runs(
    wk: dict[str, Any], su: Any, agents: Any
) -> None:
    from dataclasses import replace

    from hq_api.principal import Principal

    hub = wk["hub"]
    real = hub.settings
    acts = wk["acts"].oversight
    holding = await hub.companies.holding()
    owner = Principal(kind="owner", code="owner", role="owner")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        high, medium, critical = [
            await O.new_version(
                tx,
                owner,
                holding.id,
                protocol_body(method="llm", severity=sev),
                ref=None,
                source="owner",
            )
            for sev in ("high", "medium", "critical")
        ]
    # The overseer and QC spent more than 0.2 of today's 1M cap.
    spend = await su.fetchval(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
               status, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, meta)
           VALUES (gen_random_uuid(), now(), $1, 'HQ-OVR', 'general', 2, 'hq-agents', 'ok',
                   150000, 1000, 100000, 0, '{"run_id": "x", "charter": "overseer@2"}')
           RETURNING id""",
        holding.id,
    )
    try:
        hub.settings = replace(
            real,
            oversight_model_runs_per_day=10_000,
            agent_daily_token_cap=1_000_000,
            oversight_daily_share=0.2,
            oversight_run_tokens=900_000,  # above the charter: the charter wins
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await O.oversight_tokens_today(tx) >= 251_000
            assert await O.share_spent(tx, 1_000_000, 0.2)
            assert await O.share_spent(tx, 0, 0.2)  # a cap of 0 is nothing (8.1)
        assert await acts.protocol_run(high["ref"]) == {
            "protocol": high["ref"],
            "deferred": "oversight_share",
        }
        assert (await acts.protocol_run(medium["ref"]))["deferred"] == "oversight_share"
        rows = await su.fetch(
            "SELECT result, work_id, finished_at FROM oversight.protocol_runs WHERE protocol_ref = ANY($1)",
            [high["ref"], medium["ref"]],
        )
        assert [(r["result"], r["work_id"]) for r in rows] == [("deferred", None)] * 2
        assert all(r["finished_at"] for r in rows)
        # A critical protocol still goes to the overseer, within its charter (200K).
        out = await acts.protocol_run(critical["ref"])
        assert out.get("work") and out["assignee"] == OVR, out
        w = await su.fetchrow("SELECT id, budget_tokens FROM work.work WHERE ref = $1", out["work"])
        assert (
            w["budget_tokens"] == 200_000 == charters.load().get("overseer").limits.tokens_per_run
        )
        # Deferred is no failure: compliance counts only pass, fail and partial.
        assert not await su.fetchval(
            """SELECT count(*) FROM oversight.protocol_runs
               WHERE protocol_ref = ANY($1) AND result IN ('pass', 'fail', 'partial')""",
            [high["ref"], medium["ref"]],
        )
        # The overseer's run of the critical protocol: capped at 200K, and the
        # router learns the protocol and its severity (it lets critical go on).
        await su.execute("DELETE FROM llm.calls WHERE id = $1", spend)
        run_id = await su.fetchval(
            "SELECT id FROM agents.runs WHERE work_id = $1 AND state = 'queued'", w["id"]
        )
        agents.fake.enqueue(OVR, step("بررسی شد"))
        await run(agents, run_id)
        cap = await su.fetchval("SELECT token_cap FROM agents.runs WHERE id = $1", run_id)
        assert cap == 200_000
        meta = await su.fetchval(
            "SELECT meta FROM llm.calls WHERE meta ->> 'run_id' = $1 ORDER BY started_at LIMIT 1",
            str(run_id),
        )
        meta = json.loads(meta) if isinstance(meta, str) else meta
        assert (meta["protocol"], meta["severity"]) == (critical["ref"], "critical")
        # The next day (UTC) the deferred runs go first, the most severe first.
        await su.execute(
            """UPDATE oversight.protocol_runs SET started_at = now() - interval '1 day',
                   finished_at = now() - interval '1 day' WHERE protocol_ref = ANY($1)""",
            [high["ref"], medium["ref"]],
        )
        tick = await acts.oversight_tick()
        resumed = [r for r in tick["resumed"] if r["protocol"] in (high["ref"], medium["ref"])]
        assert [r["protocol"] for r in resumed] == [high["ref"], medium["ref"]]
        assert all(r.get("work") for r in resumed), resumed
        assert not [
            r for r in (await acts.oversight_tick())["resumed"] if r["protocol"] == high["ref"]
        ]
    finally:
        hub.settings = real
        await su.execute("DELETE FROM llm.calls WHERE id = $1", spend)
        await su.execute(
            """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
               FROM core.employees e
               WHERE e.id = r.employee_id AND e.code IN ('HQ-OVR', 'HQ-OVS-MGR') AND r.state = 'queued'"""
        )


async def test_a_code_check_that_cannot_decide_wakes_the_overseer_with_its_evidence(
    wk: dict[str, Any], su: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from hq_api.principal import Principal

    hub = wk["hub"]
    real = hub.settings
    acts = wk["acts"].oversight
    holding = await hub.companies.holding()
    owner = Principal(kind="owner", code="owner", role="owner")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await O.new_version(
            tx, owner, holding.id, protocol_body(method="reconcile"), ref=None, source="owner"
        )

    async def undecided(ctx: C.CheckCtx) -> C.Checked:
        item = C.Problem(
            holding.id, holding.code, "دو عدد ناهمخوان", "", "k1", [{"kind": "query", "ref": "Q-1"}]
        )
        return C.Checked([], {holding.code: holding.id}, unclear=[item])

    monkeypatch.setitem(C.CHECKS, p["ref"], undecided)
    try:
        hub.settings = replace(real, oversight_model_runs_per_day=10_000)
        out = await acts.protocol_run(p["ref"])
        assert out["result"] == "pending" and out["unclear"] == 1 and out["woken"], out
        row = await su.fetchrow(
            """SELECT r.result, r.by_kind, w.brief, w.budget_tokens FROM oversight.protocol_runs r
               JOIN work.work w ON w.id = r.work_id WHERE r.protocol_ref = $1""",
            p["ref"],
        )
        assert (row["result"], row["by_kind"]) == ("pending", "agent")  # the overseer finishes it
        assert "query:Q-1" in row["brief"] and "protocol.result" in row["brief"]
        assert row["budget_tokens"] <= 200_000
    finally:
        hub.settings = real
        await su.execute(
            """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
               FROM core.employees e
               WHERE e.id = r.employee_id AND e.code IN ('HQ-OVR', 'HQ-OVS-MGR') AND r.state = 'queued'"""
        )


def test_the_overseer_and_the_advisor_are_capped_by_their_charters() -> None:
    from hq_api.agents.runner import RunCtx

    lib = charters.load()
    for role in ("overseer", "advisor"):
        charter = lib.get(role)
        assert charter is not None and charter.limits.tokens_per_run == 200_000
        for recorded in (None, 0, 150_000, 600_000, 10**9):
            rc = RunCtx(run={"token_cap": recorded}, emp={}, charter=charter, token="t")
            assert rc.token_cap == min(recorded or 200_000, 200_000)
        assert O.run_tokens(lib, role, 900_000) == 200_000
        assert O.run_tokens(lib, role, 60_000) == 60_000
    assert O.run_tokens(None, "overseer", 900_000) == 900_000  # no library: the setting
