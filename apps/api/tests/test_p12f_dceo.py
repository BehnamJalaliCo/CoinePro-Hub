"""Prompt 12 §13 (contract §21.10): the digital CEO, prediction only.

Sealed before the owner's decision and hidden until then; the service never
acts (OPA refuses service:dceo every write but its own rows); nothing after
the decision; the statistics with fixed data; principles versioned; the
model's daily cap (the rest keep the baseline); PR-121; the launch gate.
"""

from __future__ import annotations

import json
import random
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hq_api.domain import dceo as DC
from hq_api.domain import decisions as D
from hq_api.domain import oversight_checks as C
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.owner_tools_activities import OwnerToolsActivities

from .conftest import DCEO_TOKEN, agent_headers, idem
from .p10_fakes import FakeRouter
from .p10_support import holding_switch

ANSWER = json.dumps(
    {"verdict": "reject", "confidence": 0.8, "rationale_fa": "هزینه بالاست", "principles": []}
)


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


@pytest.fixture(autouse=True)
async def _settings_back(su: Any) -> AsyncIterator[None]:
    before = await su.fetchval("SELECT digital_ceo::text FROM owner.settings WHERE id = 1")
    yield
    await su.execute("UPDATE owner.settings SET digital_ceo = $1::jsonb WHERE id = 1", before)


async def card(client: httpx.AsyncClient, co: str, *, risk: str = "medium") -> str:
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={
            "kind": "proposal",
            "title": f"پیشنهاد {random.randint(1, 10**6)}",
            "risk": risk,
            "payload": {"options": ["a", "b"]},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["ref"])


async def _clean_slate(su: Any) -> None:
    await su.execute(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(),
               decided_by_kind = 'service', decided_by_code = 'test'
           WHERE status = 'pending' AND approver_code IS NULL"""
    )


async def test_a_prediction_is_sealed_before_the_decision_and_hidden_until_then(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    ref = await card(client, co)
    p = await su.fetchrow(
        "SELECT * FROM dceo.predictions WHERE decision_ref = $1 AND method = 'baseline'", ref
    )
    assert p is not None and p["actual"] is None and not p["seen_before"]
    sealed = json.loads(p["sealed"]) if isinstance(p["sealed"], str) else p["sealed"]
    assert DC.sealed_hash(sealed) == p["sealed_hash"] and sealed["decision"] == ref
    audit = await su.fetchval(
        "SELECT summary FROM audit.entries WHERE action = 'dceo.predict' AND target_ref = $1", ref
    )
    assert audit.startswith("baseline prediction sealed") and p["verdict"] not in audit
    got = (await client.get(f"/api/v1/decisions/{ref}", headers=owner)).json()
    assert got["digital_ceo_prediction"] is None
    listed = (await client.get("/api/v1/digital-ceo/predictions", headers=owner)).json()["items"]
    assert ref not in [x["decision"] for x in listed]
    # The owner decides: scored, and shown with {verdict, confidence, method, correct}.
    r = await client.post(
        f"/api/v1/decisions/{ref}/reject", headers={**owner, **idem()}, json={"reason": "نه"}
    )
    assert r.status_code == 200, r.text
    shown = r.json()["digital_ceo_prediction"]
    assert set(shown) == {"verdict", "confidence", "method", "correct"}
    assert shown["method"] == "baseline" and shown["correct"] == (shown["verdict"] == "reject")
    row = await su.fetchrow("SELECT * FROM dceo.predictions WHERE decision_ref = $1", ref)
    assert row["actual"] == "reject" and row["made_at"] < row["decided_at"]
    listed = (await client.get("/api/v1/digital-ceo/predictions", headers=owner)).json()["items"]
    assert ref in [x["decision"] for x in listed]
    assert next(x for x in listed if x["decision"] == ref)["kind"] == "proposal"


async def test_no_prediction_is_recorded_after_the_decision(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    ref = await card(client, co)
    await client.post(
        f"/api/v1/decisions/{ref}/return", headers={**owner, **idem()}, json={"note": "x"}
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        d = await D.load(tx, ref)
        assert (
            await DC.record(tx, d, method="model", verdict="approve", confidence=0.9, basis={})
            is None
        )
    assert not await su.fetchval(
        "SELECT count(*) FROM dceo.predictions WHERE decision_ref = $1 AND method = 'model'", ref
    )


async def test_service_dceo_is_refused_an_approval(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ref = await card(client, co)
    svc = {"Authorization": f"Bearer {DCEO_TOKEN}"}
    r = await client.post(
        f"/internal/v1/decisions/{ref}/approve", headers={**svc, **idem()}, json={}
    )
    assert r.status_code == 403, r.text
    v = await hub.policy.query(
        "internal",
        {"principal": DC.SERVICE.opa(), "op": "decision.approve", "target": {"company": co}},
    )
    assert not v.allow
    v = await hub.policy.query(
        "internal",
        {"principal": DC.SERVICE.opa(), "op": "notification.raise", "target": {"company": "HQ"}},
    )
    assert not v.allow
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", ref) == "pending"
    )


def test_the_statistics_with_fixed_data() -> None:
    def row(
        i: int, method: str, conf: float, correct: bool, kind: str = "proposal"
    ) -> dict[str, Any]:
        return {"decision_id": i, "decision_kind": kind, "method": method, "confidence": conf,
                "correct": correct, "decided_at": datetime(2026, 10, 1, tzinfo=UTC)}  # fmt: skip

    rows = [
        row(1, "baseline", 0.6, True),
        row(1, "model", 0.9, True),  # the primary of card 1
        row(2, "baseline", 0.6, False),
        row(3, "baseline", 0.7, True, "hire"),
        row(4, "baseline", 0.55, False, "hire"),
    ]
    s = DC.compute_stats(rows, "all")
    assert s.n == 4 and s.accuracy == 0.5
    assert s.baseline_accuracy == 0.5 and s.model_accuracy == 1.0
    # Brier over the primary predictions: (0.9-1)^2, (0.6-0)^2, (0.7-1)^2, (0.55-0)^2
    assert s.brier == round((0.01 + 0.36 + 0.09 + 0.3025) / 4, 4)
    assert s.by_kind["hire"].n == 2 and s.by_kind["hire"].accuracy == 0.5
    assert {b.bucket: (b.n, b.hit_rate) for b in s.calibration} == {
        "0.5-0.6": (1, 0.0),
        "0.6-0.7": (1, 0.0),
        "0.7-0.8": (1, 1.0),
        "0.9-1.0": (1, 1.0),
    }
    empty = DC.compute_stats([], "30d")
    assert empty.n == 0 and empty.accuracy is None and empty.brier is None
    assert DC.laplace({}) == ("approve", 0.333)
    assert DC.laplace({"approve": 1, "reject": 4}) == ("reject", round(5 / 8, 3))


async def test_an_edited_principle_is_a_new_version(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    r = await client.post(
        "/api/v1/digital-ceo/principles",
        headers=owner,
        json={
            "text_fa": "هزینه‌ی بی‌برگشت را با دقت بیشتری میسنجم.",
            "sources": [{"kind": "decision", "ref": "D-000001"}],
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "active" and p["version"] == 1 and p["edited_by_owner"]
    r = await client.put(
        f"/api/v1/digital-ceo/principles/{p['ref']}", headers=owner, json={"text_fa": "x"}
    )
    assert r.status_code == 428
    r = await client.put(
        f"/api/v1/digital-ceo/principles/{p['ref']}",
        headers={**owner, "If-Match": "1"},
        json={"text_fa": "هزینه‌ی بی‌برگشت را دو بار میسنجم.", "status": "active"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and r.json()["text_fa"].startswith("هزینه‌ی بی‌برگشت را دو")
    versions = (
        await client.get(f"/api/v1/digital-ceo/principles/{p['ref']}/versions", headers=owner)
    ).json()
    assert [v["version"] for v in versions] == [2, 1]
    # A proposed principle (the weekly run's) becomes active only by the owner.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        prop = await DC.add_principle(
            tx, DC.SERVICE, text_fa="کارت بی‌شاهد را برمیگردانم.", sources=[], status="proposed"
        )
    r = await client.post(f"/api/v1/digital-ceo/principles/{prop['ref']}/accept", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["version"] == 2
    ov = (await client.get("/api/v1/digital-ceo", headers=owner)).json()
    assert [s["window"] for s in ov["stats"]] == ["30d", "90d", "all"]
    assert ov["settings"]["reveal"] == "after" and isinstance(ov["hidden"], int)


async def test_the_daily_model_cap_holds_and_the_rest_keep_the_baseline(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    await _clean_slate(su)
    refs = [await card(client, co, risk="medium") for _ in range(3)]
    made = await su.fetchval(
        """SELECT count(*) FROM dceo.predictions p, owner.settings s WHERE s.id = 1 AND p.method = 'model'
             AND (p.made_at AT TIME ZONE s.timezone)::date = (now() AT TIME ZONE s.timezone)::date"""
    )
    await su.execute(
        "UPDATE owner.settings SET digital_ceo = digital_ceo || jsonb_build_object('max_model_per_day', $1::int) WHERE id = 1",
        int(made) + 2,
    )
    router = FakeRouter(ANSWER)
    async with holding_switch(su, "released"):
        out = await DC.sweep(hub, router, txf(hub))
    assert out["model"] == 2 and len(router.bodies) == 2, out
    assert {b["task_class"] for b in router.bodies} == {"dceo_predict"}
    assert all(
        b["meta"]["owner_zone"] == "auto" and b["model"] == DC.PREDICT_MODEL for b in router.bodies
    )
    rows = await su.fetch(
        "SELECT decision_ref, method FROM dceo.predictions WHERE decision_ref = ANY($1)", refs
    )
    by: dict[str, set[str]] = {}
    for r in rows:
        by.setdefault(r["decision_ref"], set()).add(r["method"])
    assert all("baseline" in m for m in by.values()) and len(by) == 3
    assert sum("model" in m for m in by.values()) == 2  # the third keeps its baseline only
    async with holding_switch(su, "released"):
        again = await DC.sweep(hub, router, txf(hub))
    assert again["model"] == 0 and again.get("model_reason") == "max_model_per_day"


async def test_the_digital_ceo_does_nothing_while_the_holding_is_locked(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    await card(client, co, risk="high")
    router = FakeRouter(ANSWER)
    acts = OwnerToolsActivities(hub, txf(hub), router=router)
    before = await su.fetchval("SELECT count(*) FROM dceo.predictions")
    async with holding_switch(su, "engaged"):
        assert await acts.dceo_sweep() == {"skipped": True, "reason": "holding_locked"}
        assert await acts.dceo_principles() == {"skipped": True, "reason": "holding_locked"}
    assert router.bodies == []
    assert await su.fetchval("SELECT count(*) FROM dceo.predictions") == before


async def test_reveal_before_shows_it_at_once_and_marks_it_seen(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await su.execute(
        'UPDATE owner.settings SET digital_ceo = digital_ceo || \'{"reveal": "before"}\' WHERE id = 1'
    )
    ref = await card(client, co)
    got = (await client.get(f"/api/v1/decisions/{ref}", headers=owner)).json()
    assert got["status"] == "pending" and got["digital_ceo_prediction"]["method"] == "baseline"
    assert (
        await su.fetchval("SELECT seen_before FROM dceo.predictions WHERE decision_ref = $1", ref)
        is True
    )
    ov = (await client.get("/api/v1/digital-ceo", headers=owner)).json()
    assert ov["settings"]["reveal"] == "before"


async def test_pr121_finds_a_prediction_made_after_the_decision(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    ref = await card(client, co)
    await client.post(f"/api/v1/decisions/{ref}/approve", headers={**owner, **idem()}, json={})
    holding = await su.fetchrow("SELECT id, code FROM core.companies WHERE kind = 'holding'")
    p = await su.fetchrow("SELECT * FROM dceo.predictions WHERE decision_ref = $1", ref)
    assert p["actual"] == "approve"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = C.CheckCtx(tx, holding["id"], holding["code"], {holding["code"]: holding["id"]},
                         datetime.now(UTC), {})  # fmt: skip
        ok = await C.CHECKS[DC.PR121](ctx)
    assert not [x for x in ok.problems if ref in x.key]
    # A forged one (its hash does not match) is a finding.
    d = await su.fetchrow("SELECT id, ref FROM cartable.decisions WHERE ref = $1", ref)
    await su.execute(
        """INSERT INTO dceo.predictions (company_id, decision_id, decision_ref, decision_kind, decision_title,
               decision_risk, proposer_kind, method, verdict, confidence, sealed, sealed_hash, made_at,
               actual, correct, decided_at, scored_at)
           VALUES ($1, $2, $3, 'proposal', 't', 'medium', 'agent', 'model', 'approve', 0.5, '{"x": 1}',
                   $4, now() - interval '2 hours', 'approve', true, now() - interval '1 hour', now())""",
        holding["id"], d["id"], d["ref"], "0" * 64,
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = C.CheckCtx(tx, holding["id"], holding["code"], {holding["code"]: holding["id"]},
                         datetime.now(UTC), {})  # fmt: skip
        bad = await C.CHECKS[DC.PR121](ctx)
    assert [x for x in bad.problems if x.key == f"dceo:{ref}:model"]
    # PR-121 is active (seeded paused; switched on with prompt 12).
    assert (
        await su.fetchval("SELECT status FROM oversight.current_protocols WHERE ref = 'PR-121'")
        == "active"
    )
