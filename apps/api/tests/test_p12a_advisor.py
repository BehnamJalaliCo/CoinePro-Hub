"""Prompt 12 §1 (contract §21.1): the premium advisor's decision memos, the
devil's advocate and proactive notes; and the launch gate (nothing wakes the
advisor while the holding's kill switch is engaged)."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.agents.runner import RunCtx, Runner
from hq_api.domain import advisor as A
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .p10_fakes import holding_switch


async def _card(client: httpx.AsyncClient, co: str, *, risk: str = "high", kind: str = "proposal") -> str:
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={
            "kind": kind,
            "title": f"پیشنهاد آزمایشی {random.randint(1, 10**6)}",
            "risk": risk,
            "payload": {"okr": "O1", "options": ["a", "b"]},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["ref"])


async def _clean_slate(su: Any) -> None:
    """The test database outlives a run: older pending owner cards would take
    today's automatic memos first, so they are withdrawn (test env only)."""
    await su.execute(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(),
               decided_by_kind = 'service', decided_by_code = 'test'
           WHERE status = 'pending' AND approver_code IS NULL"""
    )


async def _cap(su: Any, extra: int) -> int:
    """owner_settings.advisor.auto_memo.max_per_day = today's automatic memos + extra."""
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1")
    made = await su.fetchval(
        """SELECT count(*) FROM advisor.memos WHERE trigger = 'auto'
           AND (created_at AT TIME ZONE $1)::date = (now() AT TIME ZONE $1)::date""",
        tz,
    )
    await su.execute(
        """UPDATE owner.settings SET advisor = jsonb_set(advisor, '{auto_memo}',
               jsonb_build_object('enabled', true, 'max_per_day', $1::int)) WHERE id = 1""",
        int(made) + extra,
    )
    return int(made)


async def advisor_run(su: Any, trigger: str, *, thread_id: Any = None, work_id: Any = None) -> str:
    """HQ-ADV's running run with this trigger (a run's trigger, thread and
    work are immutable: the one running now is ended and a new one started)."""
    emp = await su.fetchrow("SELECT id, company_id FROM core.employees WHERE code = 'HQ-ADV'")
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE employee_id = $1 AND state = 'running'",
        emp["id"],
    )
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, trigger, reason, state, started_at, token_expires_at,
               thread_id, work_id)
           VALUES ($1, $2, $3, 'test', 'running', now(), now() + interval '1 hour', $4, $5) RETURNING id""",
        emp["company_id"], emp["id"], trigger, thread_id, work_id,
    )  # fmt: skip
    return str(rid)


def _memo_body(ref: str, version: int, **over: Any) -> dict[str, Any]:
    body = {
        "decision": ref,
        "decision_version": version,
        "mode": "standard",
        "summary_fa": "خلاصه‌ی یادداشت",
        "recommendation": "approve",
        "confidence": 0.7,
        "options": [{"title_fa": "تأیید", "pros_md": "سریع", "cons_md": "هزینه"}],
        "against_md": "قوی‌ترین استدلال مخالف: هزینه‌ی برگشت‌ناپذیر.",
        "risks": [{"title_fa": "هزینه", "likelihood": "medium", "impact": "high", "mitigation_fa": "سقف"}],
        "questions": ["هزینه‌ی دقیق چقدر است؟"],
        "citations": [{"kind": "decision", "ref": ref}],
    }
    body.update(over)
    return body


async def test_a_high_risk_card_gets_an_automatic_memo_and_the_fourth_of_the_day_does_not(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    await _clean_slate(su)
    await _cap(su, 3)
    async with holding_switch(su, "released"):
        refs = [await _card(client, co) for _ in range(4)]
        low = await _card(client, co, risk="low")
        out = await A.sweep(hub)
    made = out["auto_memos"]["memos"]
    assert len(made) == 3, out
    rows = await su.fetch(
        """SELECT m.ref, m.decision_ref, m.trigger, m.state, w.run_meta, w.budget_tokens, e.code AS who
           FROM advisor.memos m JOIN work.work w ON w.id = m.work_id
           JOIN core.employees e ON e.id = w.assignee_id WHERE m.ref = ANY($1::text[])""",
        made,
    )
    assert sorted(r["decision_ref"] for r in rows) == sorted(refs[:3])
    for r in rows:
        meta = json.loads(r["run_meta"]) if isinstance(r["run_meta"], str) else r["run_meta"]
        assert (r["trigger"], r["state"], r["budget_tokens"], r["who"]) == ("auto", "writing", 80000, "HQ-ADV")
        assert meta["task_class"] == "advisor_memo" and meta["owner_zone"] == "auto"
    # The 4th card of the day and a low-risk card get none; the cap is not carried over.
    for ref in (refs[3], low):
        assert (await client.get(f"/api/v1/decisions/{ref}/memo", headers=owner)).status_code == 404
    again = await A.sweep(hub)
    assert again["auto_memos"]["made"] == 0
    # The advisor writes it: against_md is always filled (empty -> 422).
    adv = await agent_headers("HQ-ADV")
    first = refs[0]
    d = (await client.get(f"/api/v1/decisions/{first}", headers=owner)).json()
    bad = await client.post(
        "/internal/v1/advisor/memos", headers={**adv, **idem()}, json=_memo_body(first, d["version"], against_md=" ")
    )
    assert bad.status_code == 422, bad.text
    ok = await client.post(
        "/internal/v1/advisor/memos", headers={**adv, **idem()}, json=_memo_body(first, d["version"])
    )
    assert ok.status_code == 200, ok.text
    memo = (await client.get(f"/api/v1/decisions/{first}/memo", headers=owner)).json()
    assert memo["state"] == "ready" and memo["trigger"] == "auto" and memo["against_md"].strip()
    assert memo["recommendation"] == "approve" and memo["questions"]
    card = (await client.get(f"/api/v1/decisions/{first}", headers=owner)).json()
    assert [m["ref"] for m in card["memos"]] == [memo["ref"]]
    # Its work item is done, with the memo as evidence.
    w = await su.fetchrow("SELECT status FROM work.work w JOIN advisor.memos m ON m.work_id = w.id WHERE m.ref = $1", memo["ref"])
    assert w["status"] == "done"


async def test_the_same_mode_and_version_is_the_same_memo(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    async with holding_switch(su, "released"):
        ref = await _card(client, co, risk="low")
        a = await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={"mode": "standard"})
        b = await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={"mode": "standard"})
        devil = await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={"mode": "devil"})
    assert a.status_code == b.status_code == devil.status_code == 202, a.text
    assert a.json()["ref"] == b.json()["ref"] != devil.json()["ref"]
    assert a.json()["trigger"] == "owner" and devil.json()["mode"] == "devil"
    meta = await su.fetchval(
        "SELECT w.run_meta FROM work.work w JOIN advisor.memos m ON m.work_id = w.id WHERE m.ref = $1",
        devil.json()["ref"],
    )
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta == {"task_class": "advisor_memo", "owner_zone": "direct", "memo": devil.json()["ref"], "mode": "devil"}
    listed = (await client.get(f"/api/v1/advisor/memos?decision={ref}", headers=owner)).json()
    assert {m["mode"] for m in listed["items"]} == {"standard", "devil"}
    assert (await client.get(f"/api/v1/decisions/{ref}/memo?mode=devil", headers=owner)).json()["ref"] == devil.json()["ref"]


async def test_a_changed_card_makes_its_memo_stale(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    async with holding_switch(su, "released"):
        ref = await _card(client, co, risk="low")
        memo = (await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={})).json()
    v1 = memo["decision_version"]
    # A reminder (bookkeeping) does not change the card; a new decider does.
    await su.execute("UPDATE cartable.decisions SET reminded_at = now() WHERE ref = $1", ref)
    assert await su.fetchval("SELECT state FROM advisor.memos WHERE ref = $1", memo["ref"]) == "writing"
    await su.execute(
        "UPDATE cartable.decisions SET expires_at = now() + interval '3 days' WHERE ref = $1", ref
    )
    assert await su.fetchval("SELECT state FROM advisor.memos WHERE ref = $1", memo["ref"]) == "stale"
    adv = await agent_headers("HQ-ADV")
    r = await client.post("/internal/v1/advisor/memos", headers={**adv, **idem()}, json=_memo_body(ref, v1))
    assert r.status_code == 409 and r.json()["code"] == "version_conflict", r.text
    # The new version gets a memo of its own.
    async with holding_switch(su, "released"):
        new = (await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={})).json()
    assert new["ref"] != memo["ref"] and new["decision_version"] > v1 and new["state"] == "writing"


async def test_memo_write_on_a_decided_card_is_409_and_an_invented_citation_is_dropped(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    h = owner_session["headers"]
    async with holding_switch(su, "released"):
        ref = await _card(client, co, risk="low")
        other = await _card(client, co, risk="low")
    adv = await agent_headers("HQ-ADV")
    d = (await client.get(f"/api/v1/decisions/{ref}", headers=h)).json()
    cites = [{"kind": "decision", "ref": ref}, {"kind": "decision", "ref": "D-999999999"},
             {"kind": "message", "ref": "A-99999999"}]  # fmt: skip
    r = await client.post(
        "/internal/v1/advisor/memos", headers={**adv, **idem()}, json=_memo_body(ref, d["version"], citations=cites)
    )
    assert r.status_code == 200, r.text
    assert r.json()["citations"] == [{"kind": "decision", "ref": ref}] and r.json()["citations_dropped"] == 2
    o = (await client.get(f"/api/v1/decisions/{other}", headers=h)).json()
    rej = await client.post(f"/api/v1/decisions/{other}/reject", headers={**h, **idem()}, json={"reason_code": "cost"})
    assert rej.status_code == 200, rej.text
    late = await client.post(
        "/internal/v1/advisor/memos", headers={**adv, **idem()}, json=_memo_body(other, o["version"])
    )
    assert late.status_code == 409 and late.json()["code"] == "decision_not_pending", late.text
    owner_late = await client.post(f"/api/v1/decisions/{other}/memo", headers=h, json={})
    assert owner_late.status_code == 409 and owner_late.json()["code"] == "decision_not_pending"
    # Only the advisor writes memos.
    ceo = await client.post(
        "/internal/v1/advisor/memos", headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json=_memo_body(ref, d["version"], mode="devil"),
    )  # fmt: skip
    assert ceo.status_code == 403


async def test_devil_mode_is_the_advisors_thread_only_and_its_reply_says_so(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages", headers={**owner, **idem()}, json={"body": "نقد کن", "mode": "devil"}
    )
    assert r.status_code == 422, r.text
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "مخالف‌خوانی کن", "mode": "devil"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["message"]["meta"] == {"mode": "devil"}
    # The advisor's run answering it: the runner adds the instruction for this
    # run only, and the reply carries meta.mode.
    thread = await su.fetchval("SELECT id FROM msg.threads WHERE code = 'A'")
    run = await advisor_run(su, "message", thread_id=thread)
    row = dict(await su.fetchrow("SELECT * FROM agents.runs WHERE id = $1::uuid", run))
    runner = Runner(hub, router=None, gateway=None)  # type: ignore[arg-type]
    charter = hub.charters.get("advisor")
    rc = RunCtx(run=row, emp={"code": "HQ-ADV"}, charter=charter, token="t")
    assert await runner._devil(rc)
    rc_ceo = RunCtx(run=row, emp={"code": f"{co}-CEO"}, charter=hub.charters.get("ceo"), token="t")
    assert not await runner._devil(rc_ceo)
    reply = await client.post(
        "/internal/v1/threads/A/messages", headers={**await agent_headers("HQ-ADV"), **idem()},
        json={"body": "چرا نه: ..."},
    )  # fmt: skip
    assert reply.status_code == 201, reply.text
    assert reply.json()["meta"].get("mode") == "devil"
    await advisor_run(su, "work")


async def test_a_trigger_fires_once_a_day_and_its_note_is_a_report_never_urgent(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    cid = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
    # Three of the owner's cards waiting more than 72 hours (inserted as such).
    for i in range(3):
        await su.execute(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code,
                   created_at) VALUES ($1, 'proposal', 'A1', $2, 'agent', $3, now() - interval '4 days')""",
            cid, f"منتظر {i}", f"{co}-CEO",
        )  # fmt: skip
    # A day of its own (the test database outlives a run).
    now = datetime(2031, 1, 1, 9, tzinfo=UTC) + timedelta(days=random.randint(0, 3000))
    async with holding_switch(su, "released"):
        first = await A.fire_triggers_tx(hub, now)
        second = await A.fire_triggers_tx(hub, now)
    day = A.owner_day("Asia/Tehran", now).isoformat()
    t = await su.fetchrow("SELECT * FROM advisor.triggers WHERE key = $1", f"waiting_decisions:{day}")
    assert t is not None and t["state"] == "sent" and first["sent"] >= 1
    assert second["sent"] == 0 and second["seen"] >= 1  # the same key never wakes the advisor again
    meta = await su.fetchval("SELECT run_meta FROM work.work WHERE id = $1", t["work_id"])
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta["task_class"] == "advisor_proactive" and meta["owner_zone"] == "auto"
    # The advisor's run on it writes one message in A: meta.proactive, one report.
    await advisor_run(su, "work", work_id=t["work_id"])
    m = await client.post(
        "/internal/v1/threads/A/messages", headers={**await agent_headers("HQ-ADV"), **idem()},
        json={"body": "سه کارت بیش از ۷۲ ساعت منتظرند."},
    )  # fmt: skip
    assert m.status_code == 201, m.text
    assert m.json()["meta"]["proactive"] == {"kind": "waiting_decisions", "key": f"waiting_decisions:{day}"}
    t2 = await su.fetchrow("SELECT message_ref FROM advisor.triggers WHERE id = $1", t["id"])
    assert t2["message_ref"] == m.json()["ref"]
    notes = await su.fetch("SELECT level FROM notify.notifications WHERE link_kind = 'message' AND link_ref = $1", m.json()["ref"])
    assert [n["level"] for n in notes] == ["report"]
    await advisor_run(su, "work")
    listed = (await client.get("/api/v1/advisor/triggers?kind=waiting_decisions", headers=owner)).json()
    assert any(x["key"] == f"waiting_decisions:{day}" and x["message_ref"] == m.json()["ref"] for x in listed)
    # Over proactive_per_day the rest are `capped`.
    await su.execute("UPDATE owner.settings SET advisor = jsonb_set(advisor, '{proactive_per_day}', '0') WHERE id = 1")
    try:
        later = now + timedelta(days=1)
        async with holding_switch(su, "released"):
            capped = await A.fire_triggers_tx(hub, later)
        assert capped["capped"] >= 1 and capped["sent"] == 0
    finally:
        await su.execute("UPDATE owner.settings SET advisor = jsonb_set(advisor, '{proactive_per_day}', '3') WHERE id = 1")
    await su.execute(
        "UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now() WHERE company_id = $1 AND status = 'pending'",
        cid,
    )


async def test_nothing_wakes_the_advisor_or_a_substitute_while_the_holding_is_locked(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    await _clean_slate(su)
    await _cap(su, 3)
    async with holding_switch(su, "released"):
        ref = await _card(client, co)
    cid = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
    for i in range(3):  # a trigger the rules fire (three cards waiting > 72 h)
        await su.execute(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code,
                   created_at) VALUES ($1, 'proposal', 'A1', $2, 'agent', $3, now() - interval '4 days')""",
            cid, f"منتظر {i}", f"{co}-CEO",
        )  # fmt: skip
    runs_before = await su.fetchval("SELECT count(*) FROM agents.runs")
    async with holding_switch(su, "engaged"):
        when = datetime(2036, 3, 3, 9, tzinfo=UTC) + timedelta(days=random.randint(0, 3000))
        out = await A.sweep(hub, when)
        assert out["auto_memos"]["skipped"] is True and out["auto_memos"]["reason"] == "holding_locked"
        assert out["triggers"]["sent"] == 0
        r = await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={})
        assert r.status_code == 423, r.text
        async with hub.db.tx(await hub.companies.ids()) as tx:
            holding = await hub.companies.holding()
            call = await S.seat_call(tx, hub, A.SERVICE, seat="advisor_second_opinion", input_md="x",
                                     company_id=holding.id)  # fmt: skip
            claimed = await S.claim(tx)
        assert (call["state"], call["state_reason"]) == ("skipped", "holding_locked")
        assert claimed == {"job": None, "skipped": "holding_locked"}
    assert await su.fetchval("SELECT count(*) FROM advisor.memos m JOIN cartable.decisions d ON d.id = m.decision_id WHERE d.ref = $1", ref) == 0
    states = await su.fetch(
        "SELECT state, state_reason FROM advisor.triggers WHERE day = $1", A.owner_day("Asia/Tehran", when)
    )
    assert states and all(s["state"] == "deferred" and s["state_reason"] == "holding_locked" for s in states)
    states = [s for s in states if s["state"] == "sent"]
    assert states == []
    # No run was queued for the advisor by any of it.
    assert await su.fetchval("SELECT count(*) FROM agents.runs") == runs_before
