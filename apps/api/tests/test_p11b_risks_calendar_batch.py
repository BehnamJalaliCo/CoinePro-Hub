"""Prompt 11 §8, §9, §10 and §12 (contract §20.8-§20.10): the risk register
(PR-112), the change calendar (PR-113), the batch seal of low-risk cards, and
the protocols that went active (PR-090, PR-112, PR-113, PR-116), which do
nothing while the holding is locked."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import gov_calendar as CAL
from hq_api.domain import oversight_checks as OC
from hq_api.hub import Hub
from hq_api.worker.oversight_activities import OversightActivities

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch
from .p11b_helpers import (
    ceo,
    governance_seeded,  # noqa: F401 - the seed before each test (autouse)
    propose,
    txf,
)


async def _check(hub: Hub, ref: str) -> OC.Checked:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
        companies = {
            r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")
        }
        ctx = OC.CheckCtx(tx, holding["id"], holding["code"], companies, datetime.now(UTC), {})
        return await OC.CHECKS[ref](ctx)


async def _raise(
    client: httpx.AsyncClient, headers: dict[str, str], co: str, **kw: Any
) -> httpx.Response:
    body = {"company": co, "title_fa": "وابستگی به یک صرافی", "body_md": "اگر API قطع شود",
            "category": "vendor", "likelihood": 4, "impact": 5, **kw}  # fmt: skip
    return await client.post(
        "/internal/v1/governance/risks", headers={**headers, **idem()}, json=body
    )


# ------------------------------------------------------------------- §8 --
async def test_a_20_risk_without_mitigation_after_its_date_is_a_finding(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    r = await _raise(client, await ceo(co), co["code"])
    assert r.status_code == 201, r.text
    rk = r.json()
    assert rk["score"] == 20 and rk["owner"] == f"{co['code']}-CEO"
    review_at = datetime.fromisoformat(rk["review_at"])
    assert review_at <= datetime.now(UTC) + timedelta(days=14, minutes=1)  # 15+: two weeks at most
    assert not [p for p in (await _check(hub, "PR-112")).problems if p.key == f"risk:{rk['ref']}"]
    await su.execute(
        "UPDATE governance.risks SET review_at = now() - interval '1 day' WHERE ref = $1", rk["ref"]
    )
    problems = [p for p in (await _check(hub, "PR-112")).problems if p.key == f"risk:{rk['ref']}"]
    assert len(problems) == 1 and "راه کاهش" in problems[0].title_fa
    # The daily rule first gives its owner a review work item (once).
    from hq_api.domain import gov_risks as RK

    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await RK.sweep(tx)
        again = await RK.sweep(tx)
    assert rk["ref"] in out["review_work"] and rk["ref"] not in again["review_work"]
    r = await client.get("/api/v1/risks/matrix", headers=owner, params={"company": co["code"]})
    assert r.json()["counts"][3][4] == 1


async def test_an_acceptance_needs_the_owners_step_up(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rk = (await _raise(client, await ceo(co), co["code"])).json()
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await ceo(co), **idem()},
        json={
            "kind": "risk_acceptance",
            "title": "پذیرش ریسک",
            "payload": {"risk": rk["ref"], "until": until},
        },
    )
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["payload"]["score"] == 20
    too_long = (datetime.now(UTC) + timedelta(days=120)).isoformat()
    bad = await client.post(
        "/internal/v1/decisions",
        headers={**await ceo(co), **idem()},
        json={
            "kind": "risk_acceptance",
            "title": "x",
            "payload": {"risk": rk["ref"], "until": too_long},
        },
    )
    assert bad.status_code == 422
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
    risk = (await client.get(f"/api/v1/risks/{rk['ref']}", headers=h)).json()
    assert risk["status"] == "accepted" and risk["accepted"]["decision"] == card["ref"]


async def test_the_owner_of_a_risk_cannot_close_it_and_the_keeper_can(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    mgr = await agent_headers(f"{co['code']}-GROWTH-MGR")
    rk = (await _raise(client, mgr, co["code"], likelihood=2, impact=2)).json()
    assert rk["owner"] == f"{co['code']}-GROWTH-MGR"
    upd = {"ref": rk["ref"], "version": rk["version"], "status": "closed", "note": "حل شد"}
    r = await client.post(
        "/internal/v1/governance/risks/update", headers={**mgr, **idem()}, json=upd
    )
    assert r.status_code == 403
    r = await client.post(
        "/internal/v1/governance/risks/update",
        headers={**mgr, **idem()},
        json={**upd, "status": "mitigating", "mitigation_md": "صرافی دوم"},
    )
    assert r.status_code == 200, r.text
    keeper = await agent_headers("HQ-OVS-MGR")
    r = await client.post(
        "/internal/v1/governance/risks/update",
        headers={**keeper, **idem()},
        json={**upd, "version": r.json()["version"]},
    )
    assert r.status_code == 200 and r.json()["status"] == "closed", r.text
    risk = (await client.get(f"/api/v1/risks/{rk['ref']}", headers=owner)).json()
    assert [h["by"]["code"] for h in risk["history"]][-1] == "HQ-OVS-MGR"


async def test_the_fx_ceo_does_not_see_or_touch_a_ty_risk(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    ty, fx = await new_company(), await new_company()
    rk = (await _raise(client, await ceo(ty), ty["code"])).json()
    r = await client.get(
        "/internal/v1/governance/read",
        headers=await ceo(fx),
        params={"what": "risks", "company": ty["code"]},
    )
    assert r.status_code == 403
    r = await client.post(
        "/internal/v1/governance/risks/update",
        headers={**await ceo(fx), **idem()},
        json={"ref": rk["ref"], "version": 1, "impact": 1, "note": "x"},
    )
    assert r.status_code == 403
    assert (await _raise(client, await ceo(fx), ty["code"])).status_code == 403
    own = await client.get(
        "/internal/v1/governance/read", headers=await ceo(ty), params={"what": "risks"}
    )
    assert [x["ref"] for x in own.json()] == [rk["ref"]]


# ------------------------------------------------------------------- §9 --
def _deploy(
    window: tuple[datetime, datetime] | None, head_sha: str | None = "a1b2c3d4e5f6"
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repo": "coinepro/app",
        "pr_url": "https://github.com/coinepro/app/pull/7",
    }
    if head_sha:
        payload["head_sha"] = head_sha
    if window:
        payload["window"] = {"from": window[0].isoformat(), "to": window[1].isoformat()}
    return {"kind": "deploy", "title": "انتشار نسخه‌ی ۲", "payload": payload, "risk": "medium"}


async def test_a_deploy_in_a_freeze_conflicts_high_and_head_sha_is_required(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    start = datetime.now(UTC) + timedelta(days=3)
    r = await client.post(
        "/api/v1/calendar", headers={**owner, **idem()},
        json={"company": co["code"], "kind": "freeze", "title_fa": "فریز پایان فصل",
              "starts_at": start.isoformat(), "ends_at": (start + timedelta(days=1)).isoformat(), "risk": "high"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    freeze = r.json()["ref"]
    mgr = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()},
                          json=_deploy((start + timedelta(hours=2), start + timedelta(hours=3)), head_sha=None))  # fmt: skip
    assert r.status_code == 422 and "payload.head_sha" in r.json()["fields"]
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()},
                          json=_deploy((start + timedelta(hours=2), start + timedelta(hours=3))))  # fmt: skip
    assert r.status_code == 201, r.text
    card = r.json()
    (c,) = [x for x in card["payload"]["calendar_conflicts"] if x["rule"] == "deploy_in_freeze"]
    assert (c["severity"], c["b"]) == ("high", freeze)
    assert "تداخل تقویم (high)" in card["risk_note"]
    events = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1 AND payload->'data'->>'rule' = 'deploy_in_freeze'",
        f"hq.core.{co['code']}.calendar.conflict",
    )
    assert events == 1
    cal = await client.get(
        "/api/v1/calendar", headers=owner,
        params={"company": co["code"], "from": start.isoformat(), "to": (start + timedelta(days=2)).isoformat()},
    )  # fmt: skip
    dep = next(e for e in cal.json()["events"] if e["kind"] == "deploy")
    assert dep["source"] == {"decision": card["ref"]}
    assert any(x["a"] == dep["ref"] and x["b"] == freeze for x in cal.json()["conflicts"])
    # The card is not approved: its window comes off the calendar.
    await client.post(
        f"/api/v1/decisions/{card['ref']}/reject", headers={**owner, **idem()}, json={}
    )
    assert (
        await su.fetchval(
            "SELECT status FROM governance.calendar_events WHERE ref = $1", dep["ref"]
        )
        == "cancelled"
    )


async def test_a_campaign_at_the_same_time_is_seen_and_another_companys_is_refused(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co, other = await new_company(), await new_company()
    start = datetime.now(UTC) + timedelta(days=5)
    body = {"company": co["code"], "kind": "campaign", "title_fa": "کمپین یلدا",
            "starts_at": start.isoformat(), "ends_at": (start + timedelta(days=2)).isoformat()}  # fmt: skip
    r = await client.post(
        "/internal/v1/governance/calendar", headers={**await ceo(co), **idem()}, json=body
    )
    assert r.status_code == 201, r.text
    campaign = r.json()["ref"]
    r = await client.post(
        "/internal/v1/governance/calendar", headers={**await ceo(other), **idem()}, json=body
    )
    assert r.status_code == 403
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    assert (await client.post("/internal/v1/governance/calendar", headers={**tech, **idem()},
                              json=body)).status_code == 403  # fmt: skip
    r = await client.post("/internal/v1/decisions", headers={**await ceo(co), **idem()},
                          json=_deploy((start + timedelta(hours=5), start + timedelta(hours=6))))  # fmt: skip
    conflicts = r.json()["payload"]["calendar_conflicts"]
    assert {(c["rule"], c["severity"], c["b"]) for c in conflicts} >= {
        ("deploy_during_campaign", "high", campaign)
    }
    read = await client.get(
        "/internal/v1/governance/calendar", headers=await ceo(co),
        params={"from": start.isoformat(), "to": (start + timedelta(days=3)).isoformat()},
    )  # fmt: skip
    assert read.status_code == 200
    assert {e["ref"] for e in read.json()["events"]} >= {campaign}
    assert any(c["rule"] == "deploy_during_campaign" for c in read.json()["conflicts"])


async def test_the_holidays_are_seeded_and_a_deploy_on_one_is_medium(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub
) -> None:
    r = await client.get(
        "/api/v1/calendar", headers=owner,
        params={"kind": "holiday", "from": "2027-03-19T00:00:00Z", "to": "2027-03-25T00:00:00Z"},
    )  # fmt: skip
    days = {e["starts_at"][:10]: e for e in r.json()["events"]}
    nowruz = [e for e in days.values() if "نوروز" in e["title_fa"]]
    assert len(nowruz) == 4 and all(e["company"] is None for e in nowruz)
    hol = nowruz[0]
    dep = {"id": "x", "ref": "CE-TEST", "kind": "deploy", "status": "planned", "company_id": "c", "company_kind": "company",
           "starts_at": datetime.fromisoformat(hol["starts_at"]) + timedelta(hours=8),
           "ends_at": datetime.fromisoformat(hol["starts_at"]) + timedelta(hours=9), "repo": None}  # fmt: skip
    other = {"id": "h", "ref": hol["ref"], "kind": "holiday", "status": "planned", "company_id": "hq",
             "company_kind": "holding", "starts_at": datetime.fromisoformat(hol["starts_at"]),
             "ends_at": datetime.fromisoformat(hol["ends_at"]), "title_fa": hol["title_fa"]}  # fmt: skip
    cs = CAL.conflicts_of(dep, [other], [], "Asia/Tehran")
    assert [(c.rule, c.severity) for c in cs] == [("holiday", "medium")]
    friday = CAL.conflicts_of({**dep, "starts_at": datetime(2026, 10, 30, 8, tzinfo=UTC),
                               "ends_at": datetime(2026, 10, 30, 9, tzinfo=UTC)}, [], ["fri"], "Asia/Tehran")  # fmt: skip
    assert [(c.rule, c.a, c.b) for c in friday] == [("blackout_day", "CE-TEST", "CE-TEST")]


async def test_pr_113_finds_a_deploy_outside_the_calendar(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    r = await client.post(
        "/internal/v1/decisions", headers={**await ceo(co), **idem()}, json=_deploy(None)
    )
    ref = r.json()["ref"]
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    r = await client.post(f"/api/v1/decisions/{ref}/approve",
                          headers={**owner_session["headers"], **su_h, **idem()}, json={})  # fmt: skip
    assert r.status_code == 200, r.text
    keys = {p.key for p in (await _check(hub, "PR-113")).problems if p.company == co["code"]}
    assert f"deploy:{ref}:outside" in keys


# ------------------------------------------------------------------ §10 --
async def _batch(
    client: httpx.AsyncClient, hub: Hub, sess: dict[str, Any], items: list[dict[str, Any]],
    signed: list[dict[str, Any]] | None = None,
) -> httpx.Response:  # fmt: skip
    canon = json.dumps(sorted(signed if signed is not None else items, key=lambda x: x["ref"]),
                       sort_keys=True, separators=(",", ":"))  # fmt: skip
    su_h = await step_up(
        hub, sess["session_id"], "decision.batch", hashlib.sha256(canon.encode()).hexdigest()
    )
    return await client.post(
        "/api/v1/decisions/batch/approve",
        headers={**sess["headers"], **su_h, **idem()},
        json={"items": items, "note": "یکجا"},
    )


def _items(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"ref": c["ref"], "version": c["version"]} for c in cards]


@pytest.mark.usefixtures("hiring_open")
async def test_a_batch_with_a_hire_is_422_and_nothing_is_sealed(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    from .test_people import _hire

    co = await new_company()
    cards = [await propose(client, co, f"پیشنهاد {i}") for i in range(2)]
    listed = await client.get("/api/v1/decisions/batchable", headers=owner_session["headers"])
    assert {c["ref"] for c in cards} <= {x["ref"] for x in listed.json()["items"]}
    mgr = await agent_headers(f"{co['code']}-TECH-MGR")
    hire = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co["code"])
    )
    assert hire.status_code == 201, hire.text
    r = await _batch(client, hub, owner_session, _items([*cards, hire.json()]))
    assert (r.status_code, r.json()["code"]) == (422, "batch_not_eligible")
    assert {"ref": hire.json()["ref"], "reason": "kind"} in r.json()["fields"]["items"]
    for c in [*cards, hire.json()]:
        assert (
            await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", c["ref"])
            == "pending"
        )


async def test_a_card_that_changed_after_the_step_up_refuses_the_batch(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    cards = [await propose(client, co, f"پیشنهاد {i}") for i in range(2)]
    await su.execute(
        "UPDATE cartable.decisions SET reminded_at = now() WHERE ref = $1", cards[0]["ref"]
    )
    r = await _batch(client, hub, owner_session, _items(cards))
    assert (r.status_code, r.json()["code"]) == (422, "batch_not_eligible")
    assert r.json()["fields"]["items"] == [{"ref": cards[0]["ref"], "reason": "changed"}]
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", cards[1]["ref"])
        == "pending"
    )


async def test_a_token_for_one_card_less_or_more_is_refused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    cards = [await propose(client, co, f"پیشنهاد {i}") for i in range(3)]
    items = _items(cards)
    r = await _batch(client, hub, owner_session, items, signed=items[:2])
    assert (r.status_code, r.json()["code"]) == (403, "step_up_invalid")
    extra = {"ref": "D-999999", "version": 1}
    r = await _batch(client, hub, owner_session, items, signed=[*items, extra])
    assert (r.status_code, r.json()["code"]) == (403, "step_up_invalid")


async def test_the_twenty_first_card_is_422(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    cards = [await propose(client, co, f"پیشنهاد {i}") for i in range(21)]
    r = await _batch(client, hub, owner_session, _items(cards))
    assert (r.status_code, r.json()["code"]) == (422, "batch_not_eligible")
    assert {"ref": cards[20]["ref"], "reason": "over_max_items"} in r.json()["fields"]["items"]


async def test_each_card_of_a_batch_has_its_resolution_audit_and_interaction(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    cards = [await propose(client, co, f"پیشنهاد {i}") for i in range(3)]
    risky = await propose(client, co, "پرهزینه", quota_estimate={"usd": "5"})
    r = await _batch(client, hub, owner_session, _items([*cards, risky]))
    assert {"ref": risky["ref"], "reason": "over_max_usd"} in r.json()["fields"]["items"]
    r = await _batch(client, hub, owner_session, _items(cards))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["batch"].startswith("B-") and len({i["resolution"] for i in out["items"]}) == 3
    for c in cards:
        d = (
            await client.get(f"/api/v1/decisions/{c['ref']}", headers=owner_session["headers"])
        ).json()
        assert d["status"] == "approved" and d["resolution"] and d["seal"]
        audit = await su.fetchval(
            "SELECT summary FROM audit.entries WHERE action = 'decision.approve' AND target_ref = $1",
            c["ref"],
        )
        assert f"batch: {out['batch']}" in audit
        assert (
            await su.fetchval(
                """SELECT count(*) FROM owner.interactions WHERE target_ref = $1 AND data->>'batch' = $2""",
                c["ref"],
                out["batch"],
            )
            == 1
        )


# ------------------------------------------------------------------ §12 --
async def test_the_activated_protocols_are_active_and_scheduled(
    hub: Hub, su: Any, wk: dict[str, Any]
) -> None:
    rows = await su.fetch(
        "SELECT ref, status FROM oversight.current_protocols WHERE ref = ANY($1)",
        ["PR-006", "PR-090", "PR-112", "PR-113", "PR-116"],
    )
    assert {r["ref"]: r["status"] for r in rows} == dict.fromkeys(
        ("PR-006", "PR-090", "PR-112", "PR-113", "PR-116"), "active"
    )
    audit = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'protocol.activate' AND target_ref = 'PR-090'"
    )
    assert audit >= 1
    ov = OversightActivities(wk["hub"], txf(wk["hub"]))
    out = await ov.reconcile(wk["client"], wk["tq"], "Asia/Tehran")
    for ref in ("PR-090", "PR-112", "PR-113", "PR-116"):
        assert f"protocol-{ref}" in out["protocols"]
        desc = await wk["client"].get_schedule_handle(f"protocol-{ref}").describe()
        assert desc.schedule.action.workflow == "ProtocolRun"  # type: ignore[attr-defined]


async def test_a_protocol_runs_nothing_while_the_holding_is_locked(hub: Hub, su: Any) -> None:
    ov = OversightActivities(hub, txf(hub))
    runs = await su.fetchval(
        "SELECT count(*) FROM oversight.protocol_runs WHERE protocol_ref = 'PR-090'"
    )
    async with holding_switch(su, "engaged"):
        for ref in ("PR-090", "PR-112", "PR-113", "PR-116", "PR-006"):
            assert await ov.protocol_run(ref) == {"protocol": ref, "skipped": "holding_locked"}
    after = await su.fetchval(
        "SELECT count(*) FROM oversight.protocol_runs WHERE protocol_ref = 'PR-090'"
    )
    assert after == runs
