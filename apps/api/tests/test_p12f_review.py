"""Prompt 12 §3 (contract §21.3): the weekly review with the advisor on
prompt 11's records: the agenda by code (order, at most 12), the advisor's
brief in thread A, the owner's items (If-Match), the minutes as a deliverable
by HQ-ADV, a review not done by the next week skipped, and the launch gate."""

from __future__ import annotations

import json
import random
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import reviews as RV
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.owner_tools_activities import OwnerToolsActivities

from .conftest import agent_headers, idem
from .p10_support import holding_switch
from .test_p12a_advisor import advisor_run


@pytest.fixture(autouse=True)
async def _end_advisor_runs(su: Any) -> AsyncIterator[None]:
    yield
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'running'
             AND r.reason = 'test' AND e.code = 'HQ-ADV'"""
    )
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'queued' AND e.code = 'HQ-ADV'"""
    )


def a_week() -> date:
    """A Saturday of its own (the test database outlives a run)."""
    d = date(2040, 1, 7) + timedelta(weeks=random.randint(0, 2000))
    assert d.weekday() == 5
    return d


async def review_row(su: Any, week: date, items: list[dict[str, Any]], state: str = "ready") -> str:
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    ref: str = await su.fetchval(
        """INSERT INTO owner.reviews (company_id, week, scheduled_at, agenda, state)
           VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING ref""",
        holding,
        week,
        datetime(week.year, week.month, week.day, 6, 30, tzinfo=UTC),
        json.dumps(items, ensure_ascii=False),
        state,
    )
    return ref


def item(n: int, kind: str, ref: str) -> dict[str, Any]:
    return {"n": n, "kind": kind, "ref": ref, "company": "HQ", "title_fa": f"مورد {n}",
            "why_fa": "دلیل", "status": "open", "owner_note": None}  # fmt: skip


def test_the_agenda_keeps_the_order_and_twelve_items() -> None:
    parts = {
        "note": [{"ref": "NT-0001"}],
        "risk": [{"ref": f"RK-000{i}"} for i in range(1, 4)],
        "decision": [{"ref": f"D-00000{i}"} for i in range(1, 6)],
        "budget": [{"ref": "company:TY"}],
        "okr": [{"ref": "KR-0001"}],
        "finding": [{"ref": "FI-0001"}, {"ref": "FI-0002"}],
        "revenue": [{"ref": "revenue:TY"}],
        "outcome_review": [{"ref": "OR-0001"}],
    }
    out = RV.assemble(parts)
    assert len(out) == 12 and [i["n"] for i in out] == list(range(1, 13))
    assert [i["kind"] for i in out] == (
        ["decision"] * 5 + ["risk"] * 3 + ["okr"] + ["finding"] * 2 + ["budget"]
    )
    assert out[0]["ref"] == "D-000001" and out[5]["ref"] == "RK-0001"
    short = RV.assemble({"note": [{"ref": "NT-0002"}], "outcome_review": [{"ref": "OR-0002"}]})
    assert [i["kind"] for i in short] == ["outcome_review", "note"]
    assert RV.week_of(date(2026, 10, 23)) == date(2026, 10, 17)  # a Friday -> its Saturday
    assert RV.week_of(date(2026, 10, 24)) == date(2026, 10, 24)


async def test_the_agenda_is_built_by_code_and_the_advisor_writes_the_brief(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    await su.execute(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(),
               decided_by_kind = 'service', decided_by_code = 'test'
           WHERE status = 'pending' AND approver_code IS NULL"""
    )
    old = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code,
               created_at) VALUES ($1, 'proposal', 'A1', 'کارت قدیمی', 'agent', $2, now() - interval '5 days')
           RETURNING ref""",
        co["id"],
        f"{co['code']}-CEO",
    )
    new = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code)
           VALUES ($1, 'proposal', 'A1', 'کارت تازه', 'agent', $2) RETURNING ref""",
        co["id"],
        f"{co['code']}-CEO",
    )
    risk = await su.fetchval(
        """INSERT INTO governance.risks (company_id, title_fa, category, likelihood, impact, owner_kind, owner_code,
               review_at, origin, created_by_kind, created_by_code)
           VALUES ($1, 'ریسک بزرگ', 'ops', 5, 5, 'agent', $2, now() + interval '7 days', 'agent', 'agent', $2)
           RETURNING ref""",
        co["id"],
        f"{co['code']}-CEO",
    )
    week = a_week()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        s, zone = await RV.settings(tx)
    now = RV.slot({**s, "enabled": True}, zone, week) - timedelta(minutes=20)
    async with holding_switch(su, "released"):
        early = await RV.tick_tx(hub, now - timedelta(hours=1))
        out = await RV.tick_tx(hub, now)
    assert early["made"] is None
    row = await su.fetchrow("SELECT * FROM owner.reviews WHERE week = $1", week)
    assert out["made"] == row["ref"] and row["state"] == "ready"
    agenda = json.loads(row["agenda"]) if isinstance(row["agenda"], str) else row["agenda"]
    kinds = [i["kind"] for i in agenda]
    assert len(agenda) <= 12 and agenda[0]["ref"] == old and agenda[1]["ref"] == new
    assert kinds == sorted(kinds, key=RV.KINDS.index)  # the order of §21.3
    risks = [i["ref"] for i in agenda if i["kind"] == "risk"]
    assert kinds[2] == "risk" and (risk in risks or len(risks) >= 10)
    # The advisor's work: advisor_review, the owner zone's automatic share, 100K.
    meta = await su.fetchval("SELECT run_meta FROM work.work WHERE id = $1", row["brief_work_id"])
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta == {"task_class": "advisor_review", "owner_zone": "auto", "review": row["ref"]}
    assert (
        await su.fetchval("SELECT budget_tokens FROM work.work WHERE id = $1", row["brief_work_id"])
        == RV.REVIEW_TOKENS
    )
    # Its run writes one message in A, which carries meta.review.
    await advisor_run(su, "work", work_id=row["brief_work_id"])
    m = await client.post(
        "/internal/v1/threads/A/messages", headers={**await agent_headers("HQ-ADV"), **idem()},
        json={"body": f"خلاصه‌ی مرور {row['ref']}: ابتدا {old} را ببینید."},
    )  # fmt: skip
    assert m.status_code == 201, m.text
    assert m.json()["meta"]["review"] == row["ref"]
    assert (
        await su.fetchval("SELECT brief_message_ref FROM owner.reviews WHERE id = $1", row["id"])
        == m.json()["ref"]
    )
    async with holding_switch(su, "released"):
        again = await RV.tick_tx(hub, now + timedelta(minutes=15))
    assert again.get("made") is None and again.get("brief") is None  # once a week, one brief


async def test_items_need_if_match_and_finish_writes_the_minutes(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    ref = await review_row(
        su, a_week(), [item(1, "decision", "D-000123"), item(2, "note", "NT-0042")]
    )
    r = await client.patch(
        f"/api/v1/reviews/weekly/{ref}/items/1", headers=owner, json={"status": "done"}
    )
    assert r.status_code == 428, r.text
    r = await client.post(f"/api/v1/reviews/weekly/{ref}/start", headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "in_progress"
    v = r.json()["version"]
    r = await client.patch(
        f"/api/v1/reviews/weekly/{ref}/items/1",
        headers={**owner, "If-Match": str(v)},
        json={"status": "done", "owner_note": "تأیید شد"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agenda"][0]["status"] == "done" and r.json()["version"] == v + 1
    stale = await client.patch(
        f"/api/v1/reviews/weekly/{ref}/items/2",
        headers={**owner, "If-Match": str(v)},
        json={"status": "deferred"},
    )
    assert stale.status_code == 409
    r = await client.patch(
        f"/api/v1/reviews/weekly/{ref}/items/2",
        headers={**owner, "If-Match": str(v + 1)},
        json={"status": "deferred"},
    )
    assert r.status_code == 200
    r = await client.post(f"/api/v1/reviews/weekly/{ref}/finish", headers=owner)
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["state"] == "done" and done["minutes_ref"].startswith("O-")
    assert done["duration_s"] is not None and done["duration_s"] >= 0
    dl = await su.fetchrow(
        """SELECT d.body, d.produced_with, e.code FROM cartable.deliverables d
           JOIN core.employees e ON e.id = d.producer_id WHERE d.ref = $1""",
        done["minutes_ref"],
    )
    assert dl["code"] == "HQ-ADV"
    assert "D-000123" in dl["body"] and "NT-0042" in dl["body"] and "تأیید شد" in dl["body"]
    pw = (
        json.loads(dl["produced_with"])
        if isinstance(dl["produced_with"], str)
        else dl["produced_with"]
    )
    assert pw["review"] == ref and pw["duration_s"] == done["duration_s"]


async def test_last_weeks_review_is_skipped_with_one_morning_line(hub: Hub, su: Any) -> None:
    week = a_week()
    ref = await review_row(su, week, [item(1, "note", "NT-0001")])
    later = datetime(week.year, week.month, week.day, 9, tzinfo=UTC) + timedelta(days=7)
    async with holding_switch(su, "released"):
        out = await RV.tick_tx(hub, later)
    assert ref in out["skipped"]
    assert await su.fetchval("SELECT state FROM owner.reviews WHERE ref = $1", ref) == "skipped"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        line = await RV.morning_line(tx, datetime.now(UTC))
    assert line is not None and "مرور هفتگی" in line
    assert not await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_ref = $1", ref
    )  # no urgent nag, no notification at all


async def test_the_weekly_review_does_nothing_while_the_holding_is_locked(
    hub: Hub, su: Any
) -> None:
    week = a_week()
    old = await review_row(su, week, [item(1, "note", "NT-0001")])
    later = datetime(week.year, week.month, week.day, 6, 10, tzinfo=UTC) + timedelta(days=7)
    reviews_before = await su.fetchval("SELECT count(*) FROM owner.reviews")
    work_before = await su.fetchval("SELECT count(*) FROM work.work")
    async with holding_switch(su, "engaged"):
        out = await RV.tick_tx(hub, later)
        act = await OwnerToolsActivities(hub, lambda: _ScopedTx(hub)).weekly_review()
    assert out == {"skipped": True, "reason": "holding_locked"} == act
    assert await su.fetchval("SELECT state FROM owner.reviews WHERE ref = $1", old) == "ready"
    assert await su.fetchval("SELECT count(*) FROM owner.reviews") == reviews_before
    assert await su.fetchval("SELECT count(*) FROM work.work") == work_before


async def test_the_current_review_is_404_until_one_exists(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    open_now = await su.fetchval(
        "SELECT count(*) FROM owner.reviews WHERE state IN ('ready', 'in_progress')"
    )
    r = await client.get("/api/v1/reviews/weekly/current", headers=owner)
    assert r.status_code in (200, 404)
    if not open_now:
        assert r.status_code == 404
    listed = await client.get("/api/v1/reviews/weekly", headers=owner)
    assert listed.status_code == 200 and isinstance(listed.json()["items"], list)
