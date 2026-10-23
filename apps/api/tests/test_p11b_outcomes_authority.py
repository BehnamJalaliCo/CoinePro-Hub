"""Prompt 11 §6 and §7 (contract §20.6, §20.7): decision outcome reviews at
30/60/90 days (PR-006) and the authority matrix (data for OPA, locked
invariants that no data can break)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import gov_authority as AU
from hq_api.domain import gov_outcomes as OUT
from hq_api.domain import lifecycle
from hq_api.domain import oversight_checks as OC
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .conftest import agent_headers, body_bytes, idem, step_up
from .p10_support import (
    article,
    fake_telegram,
    holding_switch,
    inbound,
    make_live,
    process,
    seal_basics,
)
from .p11b_helpers import (
    ceo,
    governance_seeded,  # noqa: F401 - the seed before each test (autouse)
    manual_kpi,
    propose,
    record,
)
from .test_p10_desk import MIN_A, MIN_Q
from .test_p10_kb_lifecycle import _sealed_rule


# ------------------------------------------------------------------- §6 --
async def test_a_proposal_without_expected_warns_for_seven_days_then_is_422(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    d = await propose(client, co)
    assert d["warnings"] == ["expected_missing"] and d["expected"] is None
    other = await client.post(
        "/internal/v1/decisions",
        headers={**await ceo(co), **idem()},
        json={"kind": "budget_change", "title": "بودجه", "payload": {
            "scope": {"scope_type": "company", "scope_ref": co["code"]}, "period": "month", "token_limit": 10}},
    )  # fmt: skip
    assert other.status_code == 201 and other.json()["warnings"] == []  # only a proposal is asked
    since = await su.fetchval("SELECT at FROM governance.rollout WHERE key = 'p11.governance'")
    async with hub.db.tx([co["id"]]) as tx:
        assert await OUT.check_expected(
            tx, "proposal", co["id"], None, now=since + timedelta(days=6)
        ) == ["expected_missing"]
        with pytest.raises(ApiError) as exc:
            await OUT.check_expected(tx, "proposal", co["id"], None, now=since + timedelta(days=8))
        assert (exc.value.status, exc.value.code) == (422, "validation_failed")
    # A card made before stays as it was: `expected` and `warnings` never change.
    with pytest.raises(Exception, match=r"immutable"):
        await su.execute("UPDATE cartable.decisions SET warnings = '{}' WHERE ref = $1", d["ref"])
    # A KPI the company does not have is refused.
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await ceo(co), **idem()},
        json={"kind": "proposal", "title": "x", "payload": {},
              "expected": {"metric_fa": "x", "kpi": "no.such_kpi", "baseline": 1, "target": 2, "by_days": 30}},
    )  # fmt: skip
    assert r.status_code == 422 and "expected.kpi" in r.json()["fields"]


async def _sealed_with(
    client: httpx.AsyncClient, owner: dict[str, str], co: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    d = await propose(client, co, "پیشنهاد با قول", expected=expected)
    assert d["warnings"] == [] and d["expected"]["by_days"] == expected["by_days"]
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    return d


async def test_a_sealed_decision_has_reviews_at_30_60_90_and_a_met_kpi_is_met(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    key = await manual_kpi(client, owner, co)
    d = await _sealed_with(
        client,
        owner,
        co,
        {"metric_fa": "کاربر فعال", "kpi": key, "baseline": 100, "target": 200, "by_days": 90},
    )
    r = await client.get("/api/v1/outcomes", headers=owner, params={"decision": d["ref"]})
    rows = r.json()["items"]
    assert [(x["day"], x["verdict"], x["status"]) for x in rows] == [
        (30, "pending", "due"), (60, "pending", "due"), (90, "pending", "due")
    ]  # fmt: skip
    assert rows[0]["proposer"]["code"] == f"{co['code']}-CEO"
    await record(client, co, key, 210)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await OUT.measure_due(tx, datetime.now(UTC) + timedelta(days=31))
    assert rows[0]["ref"] in out["decided"] and rows[1]["ref"] not in out["decided"]
    r = await client.get("/api/v1/outcomes", headers=owner, params={"decision": d["ref"]})
    first = r.json()["items"][0]
    assert (first["verdict"], first["status"], first["measured"]["value"]) == (
        "met",
        "verified",
        210.0,
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM core.outbox WHERE subject = $1 AND payload->>'ref' = $2",
            f"hq.core.{co['code']}.outcome.due",
            first["ref"],
        )
        == 1
    )
    assert OUT.verdict_of(100, 200, 160) == "partly" and OUT.verdict_of(100, 200, 120) == "missed"
    assert OUT.verdict_of(50, 20, 30) == "partly" and OUT.verdict_of(50, 20, 19) == "met"


@pytest.fixture
async def due_now(su: Any) -> AsyncIterator[Callable[[str], Any]]:
    """Moves a review's due day into the past (the immutable column, by the
    superuser with triggers off for one statement)."""

    async def move(decision: str) -> None:
        await su.execute("SET session_replication_role = replica")
        try:
            await su.execute(
                "UPDATE governance.outcome_reviews SET due_at = now() - interval '1 day' WHERE decision_ref = $1",
                decision,
            )
        finally:
            await su.execute("SET session_replication_role = origin")

    yield move


async def test_without_a_kpi_the_review_waits_for_the_note_and_the_overseer(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any,
    due_now: Callable[[str], Any],
) -> None:  # fmt: skip
    co = await new_company()
    d = await _sealed_with(
        client, owner, co, {"metric_fa": "رضایت شریک‌ها", "baseline": 0, "target": 1, "by_days": 30}
    )
    await due_now(d["ref"])
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await OUT.measure_due(tx)
    ref = await su.fetchval(
        "SELECT ref FROM governance.outcome_reviews WHERE decision_ref = $1", d["ref"]
    )
    assert ref in out["waiting_for_note"]
    row = await su.fetchrow(
        "SELECT verdict, status FROM governance.outcome_reviews WHERE ref = $1", ref
    )
    assert (row["verdict"], row["status"]) == ("unmeasurable", "due")
    # Only the proposer notes it.
    other = await agent_headers(f"{co['code']}-GROWTH-MGR")
    r = await client.post("/internal/v1/governance/outcomes/note", headers={**other, **idem()},
                          json={"ref": ref, "note_md": "نه"})  # fmt: skip
    assert r.status_code == 403
    r = await client.post(
        "/internal/v1/governance/outcomes/note",
        headers={**await ceo(co), **idem()},
        json={"ref": ref, "note_md": "دو شریک تازه قرارداد بستند.",
              "measured": {"value": 1, "at": datetime.now(UTC).isoformat(),
                           "source_ref": {"kind": "link", "ref": "W-000001"}}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
        companies = {
            r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")
        }
        ctx = OC.CheckCtx(tx, holding["id"], holding["code"], companies, datetime.now(UTC), {})
        checked = await OC.CHECKS["PR-006"](ctx)
    assert f"outcome-verdict:{ref}" in {p.key for p in checked.unclear}
    # The overseer's verdict (protocol.result outcomes, PR-006 only).
    ovr = await agent_headers("HQ-OVR")
    body = {"protocol": "PR-006", "result": "pass", "notes": "x",
            "outcomes": [{"ref": ref, "verdict": "met", "note_md": "شاهد کافی است."}]}  # fmt: skip
    r = await client.post("/internal/v1/oversight/protocol-runs/result", headers=ovr, json=body)
    assert r.status_code == 200, r.text
    row = await su.fetchrow(
        "SELECT verdict, status, decided_by_code FROM governance.outcome_reviews WHERE ref = $1",
        ref,
    )
    assert (row["verdict"], row["status"], row["decided_by_code"]) == ("met", "verified", "HQ-OVR")
    r = await client.post("/internal/v1/oversight/protocol-runs/result", headers=ovr,
                          json={**body, "protocol": "PR-010"})  # fmt: skip
    assert r.status_code in (409, 422)


async def test_prediction_accuracy_with_fixed_data(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    d = await propose(client, co)
    for day, verdict in ((30, "met"), (60, "partly"), (90, "missed")):
        await su.execute(
            """INSERT INTO governance.outcome_reviews (company_id, decision_id, decision_ref, day, due_at,
                   expected, verdict, proposer_kind, proposer_code, status, decided_at)
               SELECT company_id, id, ref, $2, now(), '{}', $3, 'agent', proposer_code, 'verified', now()
               FROM cartable.decisions WHERE ref = $1""",
            d["ref"],
            day,
            verdict,
        )
    r = await client.get("/api/v1/outcomes/accuracy", headers=owner, params={"company": co["code"]})
    (row,) = r.json()
    assert (row["met"], row["partly"], row["missed"], row["accuracy"]) == (1, 1, 1, 0.5)


# ------------------------------------------------------------------- §7 --
async def _put(
    client: httpx.AsyncClient, hub: Hub, sess: dict[str, Any], body: Any
) -> httpx.Response:
    content = body_bytes(body)
    su_h = await step_up(
        hub, sess["session_id"], "authority.update", hashlib.sha256(content).hexdigest()
    )
    return await client.put(
        "/api/v1/authority", content=content,
        headers={**sess["headers"], **su_h, "Content-Type": "application/json"},
    )  # fmt: skip


def _row(matrix: dict[str, Any], key: str) -> dict[str, Any]:
    return next(r for r in matrix["rules"] if r["key"] == key)


@pytest.fixture
async def restore_matrix(hub: Hub, owner_db: Any) -> AsyncIterator[None]:
    """Every unlocked row back to its seed after the test (the seed keeps
    the owner's values, so this test writes them back itself)."""
    yield
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        for r in AU.load_seed():
            await tx.exec(
                "UPDATE governance.authority SET actor = :a, lim = CAST(:l AS jsonb) WHERE key = :k",
                a=r["actor"], l=json.dumps(r["lim"]) if r["lim"] is not None else None, k=r["key"],
            )  # fmt: skip
        await tx.exec("UPDATE owner.settings SET ceo_daily_attention = 6 WHERE id = 1")
    await AU.ensure(hub, force=True)


@pytest.mark.usefixtures("restore_matrix")
async def test_a_locked_row_or_a_number_outside_its_bounds_is_422(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any]
) -> None:
    m = (await client.get("/api/v1/authority", headers=owner_session["headers"])).json()
    locked = _row(m, "a3.owner_only")
    assert locked["locked"] and locked["class"] == "A3"
    r = await _put(client, hub, owner_session,
                   {"rules": [{"key": "a3.owner_only", "actor": "ceo", "limit": None, "version": locked["version"]}]})  # fmt: skip
    assert r.status_code == 422 and "locked" in r.json()["fields"]["a3.owner_only"]
    hire = _row(m, "hire.per_day")
    r = await _put(client, hub, owner_session,
                   {"rules": [{"key": "hire.per_day", "limit": {"count_day": 1000}, "version": hire["version"]}]})  # fmt: skip
    assert r.status_code == 422 and "outside bounds" in r.json()["fields"]["hire.per_day.count_day"]
    # Without the step-up, nothing.
    r = await client.put("/api/v1/authority", headers=owner_session["headers"],
                         json={"rules": [{"key": "hire.per_day", "limit": {"count_day": 3}, "version": 1}]})  # fmt: skip
    assert r.status_code == 403
    kinds = _row(m, "batch.kinds")
    r = await _put(client, hub, owner_session, {"rules": [
        {"key": "batch.kinds", "limit": {"kinds": ["proposal", "deploy"]}, "version": kinds["version"]}]})  # fmt: skip
    assert r.status_code == 422  # the allowed list only ever gets shorter


@pytest.mark.usefixtures("restore_matrix")
async def test_after_the_hire_cap_changes_opa_enforces_it_at_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    m = (await client.get("/api/v1/authority", headers=owner_session["headers"])).json()
    hire = _row(m, "hire.per_day")
    assert (await hub.policy.query("limits", {"rule": "hire.per_day", "count": 1})).allow
    r = await _put(client, hub, owner_session,
                   {"rules": [{"key": "hire.per_day", "limit": {"count_day": 1}, "version": hire["version"]}]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert _row(r.json(), "hire.per_day")["limit"] == {"count_day": 1}
    assert not (await hub.policy.query("limits", {"rule": "hire.per_day", "count": 1})).allow
    assert (await hub.policy.query("limits", {"rule": "hire.per_day", "count": 0})).allow
    assert await hub.policy.value("limits/version") == r.json()["digest"]
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        assert not await AU.within(hub, tx, "hire.per_day", 1, 5)
        assert await AU.within(hub, tx, "hire.per_day", 0, 5)
    # Taking a row back for the owner: the CEO no longer approves recurring work.
    rec = _row(m, "decision.recurring_approval.ceo")
    r = await _put(client, hub, owner_session, {"rules": [
        {"key": "decision.recurring_approval.ceo", "actor": "owner", "limit": None, "version": rec["version"]}]})  # fmt: skip
    assert r.status_code == 200, r.text
    verdict = await hub.policy.query("decisions", {
        "principal": {"kind": "agent", "code": f"{co['code']}-CEO", "role": "ceo", "company": co["code"]},
        "decision": {"kind": "recurring_approval", "company": co["code"], "action_class": "A2",
                     "payload": {}, "proposer": {"kind": "agent", "code": f"{co['code']}-GROWTH-MGR"}},
        "context": {"within_quota": True}})  # fmt: skip
    assert not verdict.allow and "owner_only" in verdict.reasons


@pytest.mark.usefixtures("restore_matrix")
async def test_tampered_data_gives_no_agent_a3(hub: Hub) -> None:
    tampered = {"version": "forged", "rules": {
        "a3.owner_only": {"actor": "ceo", "locked": False, "class": "A0", "limit": None},
        "a4.never": {"actor": "agent", "locked": False, "class": "A0", "limit": None},
        "hire.per_day": {"actor": "ceo", "locked": False, "class": "A2", "limit": {"count_day": 100000}}}}  # fmt: skip
    assert await hub.policy.put_authority(tampered)
    ceo_p = {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY"}
    for cls in ("A3", "A4"):
        v = await hub.policy.query("actions", {"principal": ceo_p, "action": {"class": cls, "name": "deploy",
                                                                             "company": "TY"},
                                               "context": {"company_locked": False}})  # fmt: skip
        assert not v.allow
    v = await hub.policy.query("decisions", {"principal": ceo_p, "decision": {
        "kind": "deploy", "company": "TY", "action_class": "A3", "payload": {},
        "proposer": {"kind": "agent", "code": "TY-TECH-MGR"}}, "context": {}})  # fmt: skip
    assert not v.allow and "owner_only" in v.reasons
    # A forged number stays inside the file's bounds (20 hires a day at most).
    assert not (await hub.policy.query("limits", {"rule": "hire.per_day", "count": 20})).allow
    # The api sees the other digest and pushes its own rows again.
    assert await hub.policy.value("limits/version") == "forged"
    AU._SYNC["at"] = 0.0
    await AU.ensure(hub)
    async with hub.db.raw() as tx:
        assert await hub.policy.value("limits/version") == AU.opa_doc(await AU.rows(tx))["version"]


async def test_an_agent_never_writes_the_matrix(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    r = await client.put(
        "/api/v1/authority", headers=await ceo(co),
        json={"rules": [{"key": "hire.per_day", "limit": {"count_day": 20}, "version": 1}]},
    )  # fmt: skip
    assert r.status_code == 403
    r = await client.get("/internal/v1/governance/authority", headers=await ceo(co))
    assert r.status_code == 200
    rows = {x["key"]: x for x in r.json()}
    assert "hire.per_day" in rows and "batch.max_usd" not in rows  # only its company's rows
    assert rows["a3.ceo_content_calendar"]["locked"]


@pytest.mark.usefixtures("restore_matrix")
async def test_an_authority_change_card_is_sealed_with_step_up_and_applied(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    body = {"kind": "authority_change", "title": "سقف استوری", "payload": {
        "changes": [{"key": "story.per_day", "to": {"limit": {"count_day": 2}}}]}}  # fmt: skip
    r = await client.post("/internal/v1/decisions", headers={**await ceo(co), **idem()}, json=body)
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["payload"]["changes"][0]["from"] == {"actor": "ceo", "limit": {"count_day": 3}}
    bad = {**body, "payload": {"changes": [{"key": "a4.never", "to": {"actor": "ceo"}}]}}
    r = await client.post("/internal/v1/decisions", headers={**await ceo(co), **idem()}, json=bad)
    assert r.status_code == 422
    h = owner_session["headers"]
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/approve", headers={**h, **idem()}, json={}
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", card["ref"])
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/approve", headers={**h, **su_h, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    m = (await client.get("/api/v1/authority", headers=h)).json()
    assert _row(m, "story.per_day")["limit"] == {"count_day": 2}
    assert await hub.policy.value("limits/version") == m["digest"]


@pytest.mark.usefixtures("restore_matrix")
async def test_sealed_sends_stay_allowed_and_an_unsealed_template_stops_its_rule(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    """The locked A3 invariant reads the seals, not the matrix: a sealed
    lifecycle rule and a live channel's automatic answer still go out after
    the matrix changed; a rule whose template got a new version does not."""
    m = (await client.get("/api/v1/authority", headers=owner_session["headers"])).json()
    story = _row(m, "story.per_day")
    r = await _put(client, hub, owner_session,
                   {"rules": [{"key": "story.per_day", "limit": {"count_day": 1}, "version": story["version"]}]})  # fmt: skip
    assert r.status_code == 200
    co = await new_company()
    await seal_basics(hub, co["id"])
    await article(hub, co["id"], MIN_Q, MIN_A, variants=["حداقل موجودی وی آی پی"])
    await make_live(su, co["id"])
    rule = await _sealed_rule(hub, co["id"], "csat")
    tehran = ZoneInfo("Asia/Tehran")
    morning = datetime.combine(
        datetime.now(tehran).date(), datetime.min.time(), tehran
    ) + timedelta(hours=10)
    async with holding_switch(su, "released"), fake_telegram() as tg:
        msg = await inbound(hub, co["id"], "حداقل موجودی برای VIP چقدر است")
        out = await process(hub, co["id"], msg["message"]["id"])
        assert out.result == "verbatim" and out.queued  # the live channel answers by itself
        async with hub.db.tx([co["id"]]) as tx:
            sent = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="p11b:csat",
                conversation_id=msg["conversation"]["id"], now=morning,
            )  # fmt: skip
        assert sent["status"] == "queued" and sent["message_id"]
        async with hub.db.tx([co["id"]]) as tx:
            await lifecycle.propose_template(
                tx, company_id=co["id"], purpose="csat", body_fa="نسخه‌ی تازه از ۱ تا ۵؟",
                variables=[], by_kind="owner", by_code="owner", ref=rule["template_ref"],
            )  # fmt: skip
            again = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="p11b:csat:2",
                conversation_id=msg["conversation"]["id"], now=morning,
            )  # fmt: skip
        assert again["status"] == "skipped" and not again.get("message_id")
    assert tg is not None


def test_the_bounds_of_the_files_agree() -> None:
    """The seed's bounds and the policy's (hq.limits clamps with the latter)."""
    from pathlib import Path

    data = json.loads(Path("/opa/policy/data.json").read_text(encoding="utf-8"))["hq"]["config"]
    seed = {r["key"]: r for r in AU.load_seed()}
    for key, b in data["authority_bounds"].items():
        r = seed[key]
        assert r["lim"] == {b["field"]: b["default"]}, key
        assert r["bounds"] == {"min": b["min"], "max": b["max"]}, key
    for key, lst in data["authority_lists"].items():
        r = seed[key]
        assert r["lim"] == {lst["field"]: lst["default"]}, key
        assert r["bounds"] == {"allowed": lst["allowed"]}, key
    assert set(data["never_batch"]) == set(seed["batch.never"]["lim"]["kinds"])
    numeric = {k for k, r in seed.items() if r["lim"] and not r["locked"] and AU._number_key(r)}
    assert numeric == set(data["authority_bounds"])


async def test_the_api_pushes_the_matrix_at_its_start(hub: Hub) -> None:
    assert await hub.policy.put_authority({"version": "stale", "rules": {}})
    assert await AU.push_at_start(hub, attempts=1, wait_s=0)
    async with hub.db.raw() as tx:
        assert await hub.policy.value("limits/version") == AU.opa_doc(await AU.rows(tx))["version"]
