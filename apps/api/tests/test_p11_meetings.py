"""Prompt 11 §1 (contract §20.1, §20.12): the meeting room, run by code. The
agenda and its speakers by rule, the budget estimate and its trim, turns that
do not fit, claims checked like citations, whispers for the owner only,
resolutions only by the owner's seal, standups that say nothing when nothing
changed, the war room and the postmortem, the meetings' daily share, the
owner's word and controls, and nothing at all while the holding is locked.
No real model: turns are driven by hand here and by the FAKE model in
test_a_meeting_runs_end_to_end_with_the_fake_model."""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import governance_checks as _gc  # noqa: F401 - registers PR-111, PR-114
from hq_api.domain import meeting_flow as MF
from hq_api.domain import meetings as MT
from hq_api.domain import oversight_checks as C
from hq_api.hub import Hub
from hq_api.security import agent_tokens

from .conftest import AGENT_KEY, agent_headers, idem
from .p10_support import holding_switch

pytestmark = pytest.mark.usefixtures("relay")
SOON = timedelta(hours=1)


def roomy(hub: Hub, **over: Any) -> Any:
    """Settings with room in the day (other tests' reservations never decide here)."""
    return dataclasses.replace(hub.settings, agent_daily_token_cap=10**9, **over)


async def ad_hoc(client: httpx.AsyncClient, owner: dict[str, str], **body: Any) -> dict[str, Any]:
    body.setdefault("starts_at", (datetime.now(UTC) + SOON).isoformat())
    r = await client.post("/api/v1/meetings", headers={**owner, **idem()}, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def start(hub: Hub, ref: str, s: Any = None) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        m = await MT.load(tx, ref, lock=True)
        await tx.exec("UPDATE meetings.meetings SET starts_at = now() WHERE id = :id", id=m["id"])
        return await MF.start(tx, await MT.load(tx, ref, lock=True), s or roomy(hub))


async def load(hub: Hub, ref: str) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await MT.load(tx, ref)


async def free(su: Any, code: str) -> None:
    """End the test's own other running run of an employee (one at a time each)."""
    await su.execute(
        """UPDATE agents.runs SET state = 'done', finished_at = now()
           WHERE state = 'running' AND trigger <> 'meeting'
             AND employee_id = (SELECT id FROM core.employees WHERE code = $1)""",
        code,
    )


async def take_turn(su: Any, hub: Hub, ref: str) -> tuple[dict[str, Any], dict[str, str]]:
    """The pending turn's run, running, and its agent token (what the runner does)."""
    m = await load(hub, ref)
    p = dict(m["pending"] or {})
    assert p, f"{ref} has no pending turn"
    await free(su, p["speaker"])
    await su.execute(
        """UPDATE agents.runs SET state = 'running', started_at = now(), token_expires_at = now() + interval '1 hour'
           WHERE id = $1 AND state = 'queued'""",
        m["pending_run_id"],
    )
    token = agent_tokens.mint(AGENT_KEY, p["speaker"], str(m["pending_run_id"]))
    return p, {"Authorization": f"Bearer {token}"}


async def end_turn(su: Any, hub: Hub, ref: str, tokens: int = 1000) -> dict[str, Any]:
    m = await load(hub, ref)
    await su.execute(
        "UPDATE agents.runs SET state = 'running', started_at = now() WHERE id = $1 AND state = 'queued'",
        m["pending_run_id"],
    )
    await su.execute(
        """UPDATE agents.runs SET state = 'done', finished_at = now(), input_tokens = $2 WHERE id = $1""",
        m["pending_run_id"],
        tokens,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await MF.turn_finished(tx, {"id": m["pending_run_id"]})
    return await load(hub, ref)


async def a_deliverable(
    client: httpx.AsyncClient, owner: dict[str, str], company: str, su: Any
) -> str:
    """An output of the company's CEO (what a claim may cite)."""
    w = await client.post(
        "/api/v1/work", headers={**owner, **idem()}, json={"company": company, "title": "گزارش"}
    )
    assert w.status_code == 201, w.text
    r = await client.post(
        f"/internal/v1/work/{w.json()['id']}/deliver",
        headers={**await agent_headers(f"{company}-CEO"), **idem()},
        json={"title": "گزارش هفته", "summary": "خلاصه"},
    )
    assert r.status_code == 200, r.text
    await free(su, f"{company}-CEO")
    return str(r.json()["deliverable"])


# ================================================================= agenda ==
async def test_the_board_agenda_and_speakers_follow_the_rule(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    a, b, quiet = await new_company(), await new_company(), await new_company()
    for co in (a, b):
        r = await client.post(
            "/internal/v1/decisions",
            headers={**await agent_headers(f"{co['code']}-CEO"), **idem()},
            json={"kind": "proposal", "title": f"رشد {co['code']}", "payload": {}},
        )
        assert r.status_code == 201, r.text
    t = await su.fetchrow("SELECT max_speakers FROM meetings.types WHERE key = 'board'")
    inspector = await su.fetchval(
        "SELECT e.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id "
        "WHERE c.kind = 'holding' AND e.role = 'inspector' AND e.status = 'active' ORDER BY e.created_at LIMIT 1"
    )

    holding = await su.fetchval("SELECT code FROM core.companies WHERE kind = 'holding'")

    async def check(m: dict[str, Any]) -> None:
        assert m["state"] == "prep" and m["company"] == holding
        report = m["items"][0]
        assert report["title_fa"] == "گزارش هفتگی شرکت‌ها" and report["speakers"] == []
        writers = {p["actor"]["code"] for p in m["participants"] if not p["speaker"]}
        speakers = {p["actor"]["code"] for p in m["participants"] if p["speaker"]}
        assert f"{quiet['code']}-CEO" in writers  # a company with nothing to discuss writes
        # Every company takes part: on its proposal's item, or in writing (oldest proposals first).
        assert {f"{a['code']}-CEO", f"{b['code']}-CEO"} <= writers | speakers
        assert len(m["items"]) <= MT.MAX_ITEMS
        for it in m["items"]:
            codes = [s["code"] for s in it["speakers"]]
            assert len(codes) <= t["max_speakers"], it
            if codes:
                assert codes[-1] == inspector  # the devil's advocate last
        mine = [it for it in m["items"] if it["sources"] and it["sources"][0]["kind"] == "decision"]
        assert mine, m["items"]

    m1 = await ad_hoc(client, owner, type="board")
    await check(m1)
    await new_company()  # one company more: still no item above the cap
    m2 = await ad_hoc(client, owner, type="board")
    await check(m2)
    assert (
        m2["budget"]["cap"] == 120000 and m2["budget"]["estimate"] <= m2["budget"]["cap"]
    ) or m2["trimmed_fa"]


async def test_an_estimate_over_the_budget_is_trimmed(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    for title in ("نخست", "دوم"):
        r = await client.post(
            "/internal/v1/decisions",
            headers={**await agent_headers(f"{co}-CEO"), **idem()},
            json={"kind": "proposal", "title": title, "payload": {}},
        )
        assert r.status_code == 201, r.text
    m = await ad_hoc(
        client, owner, type="company", company=co,
        items=[{"title_fa": "دستور مالک", "brief_md": "", "companies": [co]}],
    )  # fmt: skip
    assert len(m["items"]) == 4 and m["items"][0]["title_fa"] == "دستور مالک"
    r = await client.patch(
        f"/api/v1/meetings/{m['ref']}",
        headers={**owner, "If-Match": str(m["version"])},
        json={"budget_cap": 25000},
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert (
        after["budget"]["cap"] == 25000
        and after["trimmed_fa"]
        and "طبق قاعده" in after["trimmed_fa"]
    )
    # Raising it is not PATCH's (only control raise_budget, the owner's).
    r = await client.patch(
        f"/api/v1/meetings/{m['ref']}",
        headers={**owner, "If-Match": str(after["version"])},
        json={"budget_cap": 90000},
    )
    assert r.status_code == 422


async def test_only_the_owner_raises_a_budget(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    m = await ad_hoc(client, owner, type="company", company=co)
    for who in (await agent_headers(f"{co}-CEO"), await agent_headers("HQ-OVR")):
        r = await client.post(
            f"/api/v1/meetings/{m['ref']}/control",
            headers=who,
            json={"action": "raise_budget", "tokens": 10000},
        )
        assert r.status_code == 403
    assert (
        await client.post(
            f"/internal/v1/meetings/{m['ref']}/control", headers=await agent_headers(f"{co}-CEO"),
            json={"action": "raise_budget", "tokens": 10000},
        )
    ).status_code in (404, 405)  # fmt: skip
    r = await client.post(
        f"/api/v1/meetings/{m['ref']}/control",
        headers=owner,
        json={"action": "raise_budget", "tokens": 10000},
    )
    assert r.status_code == 200 and r.json()["budget"]["cap"] == 50000


# ================================================================== turns ==
async def test_turns_claims_drafts_and_the_owners_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co, other = (await new_company())["code"], (await new_company())["code"]
    mine, theirs = (
        await a_deliverable(client, owner, co, su),
        await a_deliverable(client, owner, other, su),
    )
    m = await ad_hoc(client, owner, type="company", company=co)
    started = await start(hub, m["ref"])
    assert (
        started["state"] == "live"
        and started["mode"] == "discussion"
        and started["reserved"] == 40000
    )
    p, h = await take_turn(su, hub, m["ref"])
    assert p["kind"] == "statement" and p["speaker"] == f"{co}-CEO" and p["n"] == 1
    # Another agent is not this turn.
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},
        json={"item": 1, "statement_md": "x"},
    )
    assert r.status_code == 403
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement",
        headers={**h, **idem()},
        json={
            "item": 1,
            "statement_md": "هفته‌ی خوبی بود.",
            "claims": [
                {"text_fa": "گزارش هفته منتشر شد", "source": {"kind": "deliverable", "ref": mine}},
                {"text_fa": "درآمد دو برابر شد"},
                {"text_fa": "رقیب ضعیف شد", "source": {"kind": "deliverable", "ref": theirs}},
                {"text_fa": "طبق متریک", "source": {"kind": "metric", "ref": "funnel.x"}},
            ],
            "draft_md": "انتشار نسخه‌ی تازه با canary ده درصد.",
        },
    )
    assert r.status_code == 201, r.text
    assert [c["status"] for c in r.json()["claims"]] == [
        "sourced",
        "unsourced",
        "unsourced",
        "unsourced",
    ]
    assert r.json()["draft"]
    # A second statement in the same turn is refused.
    again = await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement",
        headers={**h, **idem()},
        json={"item": 1, "statement_md": "y"},
    )
    assert again.status_code == 409
    after = await end_turn(su, hub, m["ref"], tokens=3000)
    assert after["used"] == 3000
    # The devil's challenge on the sourced claim.
    p, h = await take_turn(su, hub, m["ref"])
    assert p["kind"] == "challenge"
    claim = await su.fetchval(
        "SELECT id FROM meetings.claims WHERE status = 'sourced' AND meeting_id = $1", m["id"]
    )
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/challenge",
        headers={**h, **idem()},
        json={"item": 1, "statement_md": "این گزارش هنوز بازبینی نشده.", "claim": str(claim)},
    )
    assert r.status_code == 201, r.text
    await end_turn(su, hub, m["ref"])
    # The vote on the draft (the last round).
    p, h = await take_turn(su, hub, m["ref"])
    assert p["kind"] == "vote" and p["round"] == 2
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement",
        headers={**h, **idem()},
        json={
            "item": 1,
            "statement_md": "موافقم.",
            "stance": {"vote": "support", "reason_fa": "ریسک کم است"},
        },
    )
    assert r.status_code == 201, r.text
    after = await end_turn(su, hub, m["ref"])
    # Agenda done: closing, the secretary's summary turn.
    assert after["state"] == "closing"
    p, h = await take_turn(su, hub, m["ref"])
    assert p["kind"] == "minutes" and p["speaker"] == "HQ-SEC"
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/minutes",
        headers={**h, **idem()},
        json={"summary_md": "یک پیش‌نویس."},
    )
    assert r.status_code == 200, r.text
    ended = await end_turn(su, hub, m["ref"])
    assert (
        ended["state"] == "ended" and ended["minutes_ref"] and ended["summary_md"] == "یک پیش‌نویس."
    )
    body = await su.fetchval(
        "SELECT body FROM cartable.deliverables WHERE ref = $1", ended["minutes_ref"]
    )
    assert "درآمد دو برابر شد" not in body and "رقیب ضعیف شد" not in body
    assert "گزارش هفته منتشر شد" not in body  # challenged: out of the minutes too
    card_ref = await su.fetchval(
        "SELECT decision_ref FROM meetings.drafts WHERE meeting_id = $1", m["id"]
    )
    card = await su.fetchrow("SELECT * FROM cartable.decisions WHERE ref = $1", card_ref)
    assert (
        card["kind"] == "meeting_resolution"
        and card["status"] == "pending"
        and card["proposer_code"] == f"{co}-CEO"
    )
    payload = json.loads(card["payload"]) if isinstance(card["payload"], str) else card["payload"]
    assert payload["claims"] == [] and payload["votes"]["support"] == 1
    assert not await su.fetchval(
        "SELECT resolution_id FROM cartable.decisions WHERE ref = $1", card_ref
    )
    # Only the owner's seal makes the resolution and its follow-up work.
    r = await client.post(
        f"/api/v1/decisions/{card_ref}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["resolution"].startswith("M-")
    follow = await su.fetchval(
        "SELECT r.follow_up_work_id FROM cartable.resolutions r WHERE r.ref = $1",
        r.json()["resolution"],
    )
    assert follow
    # PR-114 sees nothing wrong with this meeting.
    holding = await hub.companies.holding()
    companies = {c.code: c.id for c in await hub.companies.all() if c.status == "active"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        checked = await C.CHECKS["PR-114"](
            C.CheckCtx(tx, holding.id, holding.code, companies, datetime.now(UTC), {})
        )
    assert not [x for x in checked.problems if x.key.startswith(f"meeting:{m['ref']}:")]


async def test_a_turn_that_does_not_fit_is_not_run(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    m = await ad_hoc(client, owner, type="company", company=co)
    await start(hub, m["ref"])
    await take_turn(su, hub, m["ref"])
    after = await end_turn(su, hub, m["ref"], tokens=36000)  # 40000 reserved: no 6000 turn fits
    assert after["state"] in ("closing", "ended") and after["end_reason"] == "budget"
    queued = await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE r.trigger = 'meeting' AND r.reason LIKE $1 AND e.code <> 'HQ-SEC'""",
        f"meeting:{m['ref']}:%",
    )
    assert queued == 1  # only the first turn ever ran


async def test_a_whisper_reaches_the_owner_only(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    m = await ad_hoc(client, owner, type="company", company=co)
    r = await client.patch(
        f"/api/v1/meetings/{m['ref']}", headers={**owner, "If-Match": str(m["version"])},
        json={"owner_presence": "live"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    await start(hub, m["ref"])
    await take_turn(su, hub, m["ref"])
    await end_turn(su, hub, m["ref"])
    p, _ = await take_turn(su, hub, m["ref"])
    if p["kind"] == "challenge":
        await end_turn(su, hub, m["ref"])
        p, _ = await take_turn(su, hub, m["ref"])
    assert p["kind"] == "whisper" and p["speaker"].endswith("-ADV")
    secret = f"نجوای {uuid.uuid4().hex[:6]}"
    _, h = await take_turn(su, hub, m["ref"])
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/whisper",
        headers={**h, **idem()},
        json={"item": 1, "text_md": secret},
    )
    assert r.status_code == 201, r.text
    # A turn's context (any speaker's: the code builds it the same way) has no whisper.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        cur = await MT.load(tx, m["ref"])
        speaker = await tx.one(
            "SELECT id, code, company_id FROM core.employees WHERE code = :c", c=f"{co}-CEO"
        )
        ctx = await MF.turn_context(tx, {"id": cur["pending_run_id"]}, speaker)
    assert ctx is not None and secret not in ctx["text"]
    await end_turn(su, hub, m["ref"])
    turns = (await client.get(f"/api/v1/meetings/{m['ref']}/turns", headers=owner)).json()
    assert [w["text_md"] for w in turns["whispers"]] == [secret]
    assert all(secret not in t["statement_md"] for t in turns["items"])
    event = await su.fetchval(
        "SELECT payload FROM core.outbox WHERE subject LIKE '%.meeting.whisper' AND payload::text LIKE $1",
        f"%{m['ref']}%",
    )
    assert event and secret not in str(event)


async def test_the_owners_word_jumps_in_once_per_key(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    m = await ad_hoc(client, owner, type="company", company=co)
    r = await client.post(
        f"/api/v1/meetings/{m['ref']}/speak", headers={**owner, **idem()}, json={"text": "زود"}
    )
    assert r.status_code == 409 and r.json()["code"] == "meeting_not_live"
    await start(hub, m["ref"])
    key = idem()
    first = await client.post(
        f"/api/v1/meetings/{m['ref']}/speak", headers={**owner, **key}, json={"text": "اول کیفیت."}
    )
    second = await client.post(
        f"/api/v1/meetings/{m['ref']}/speak", headers={**owner, **key}, json={"text": "اول کیفیت."}
    )
    assert (
        first.status_code == 201
        and second.status_code == 201
        and first.json()["id"] == second.json()["id"]
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM meetings.turns WHERE meeting_id = $1 AND kind = 'owner'", m["id"]
        )
        == 1
    )
    nope = await client.post(
        f"/api/v1/meetings/{m['ref']}/speak", headers=owner, json={"text": "بی کلید"}
    )
    assert nope.status_code == 422
    # The owner's word is in the next speaker's context.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        cur = await MT.load(tx, m["ref"])
        speaker = await tx.one(
            "SELECT id, code, company_id FROM core.employees WHERE code = :c",
            c=cur["pending"]["speaker"],
        )
        ctx = await MF.turn_context(tx, {"id": cur["pending_run_id"]}, speaker)
    assert ctx is not None and "اول کیفیت." in ctx["text"]


async def test_an_expired_source_refuses_the_turn(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    r = await client.post(
        "/api/v1/knowledge", headers=owner,
        json={"layer": "company", "company": co, "kind": "fact", "title_fa": "کهنه", "body_md": "x",
              "sources": [{"kind": "work", "ref": "W-000001"}], "valid_until": datetime.now(UTC).date().isoformat()},
    )  # fmt: skip
    ref = r.json()["ref"]
    await su.execute(
        "UPDATE knowledge.entries SET status = 'expired', expired_at = now() WHERE ref = $1", ref
    )
    m = await ad_hoc(client, owner, type="company", company=co)
    await start(hub, m["ref"])
    _, h = await take_turn(su, hub, m["ref"])
    r = await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement", headers={**h, **idem()},
        json={"item": 1, "statement_md": "x", "claims": [{"text_fa": "y", "source": {"kind": "knowledge", "ref": ref}}]},
    )  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "knowledge_expired"


# ============================================================ the day's share ==
async def test_the_daily_share_makes_the_next_meeting_written(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    today = datetime.now(UTC).date()
    already = int(
        await su.fetchval(
            "SELECT COALESCE(sum(reserved), 0) FROM meetings.meetings WHERE reserved_on = $1 AND type <> 'war_room'",
            today,
        )
    )
    cap = 10**9
    limit = already + 2 * 40000 + 20000  # room for two company meetings, not a third
    s = roomy(hub, meetings_daily_share=limit / cap)
    refs = []
    for _ in range(3):
        co = (await new_company())["code"]
        refs.append((await ad_hoc(client, owner, type="company", company=co))["ref"])
    modes = [(await start(hub, ref, s))["mode"] for ref in refs]
    assert modes[:2] == ["discussion", "discussion"] and modes[2] == "written"
    third = await load(hub, refs[2])
    assert third["reserved"] == 0 and third["state"] == "ended"
    note = await su.fetchval(
        "SELECT body_fa FROM notify.notifications WHERE link_ref = $1 ORDER BY created_at DESC LIMIT 1",
        refs[2],
    )
    assert note and "سهم روزانه" in note


async def test_company_meetings_spread_over_the_working_days(hub: Hub) -> None:
    fake = [{"id": uuid.uuid4(), "code": f"Z{i:02d}"} for i in range(7)]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        days = await MF._company_days(tx, fake, MF.WORKDAYS, "Asia/Tehran")
        again = await MF._company_days(tx, fake, MF.WORKDAYS, "Asia/Tehran")
    assert days == again  # fixed data, the same spread
    assert [days[c["code"]] for c in fake[:5]] == list(
        MF.WORKDAYS
    )  # code order, Saturday to Wednesday
    assert days["Z05"] == MF.WORKDAYS[0] and days["Z06"] == MF.WORKDAYS[1]  # then the lightest days


# ===================================================== standup, war room ==
async def test_a_standup_without_change_sends_nothing(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    calls = await su.fetchval("SELECT count(*) FROM llm.calls")
    after_nine = datetime.now(UTC).replace(hour=12, minute=0)  # 15:30 in Tehran
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await MF.standups(tx, after_nine, only=co["id"])
    rows = await su.fetch(
        "SELECT department, state, end_reason FROM meetings.meetings WHERE company_id = $1 AND type = 'standup'",
        co["id"],
    )
    assert rows and all(r["state"] == "cancelled" and r["end_reason"] == "no_change" for r in rows)
    assert not await su.fetchval(
        """SELECT 1 FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.company_id = $1 AND t.kind = 'department'""",
        co["id"],
    )
    assert await su.fetchval("SELECT count(*) FROM llm.calls") == calls
    r = await client.get(
        "/api/v1/meetings", params={"type": "standup", "company": co["code"]}, headers=owner
    )
    assert r.json()["items"] == []
    # A day with a change: the department's thread gets one line, by code (no model).
    w = await client.post(
        "/api/v1/work", headers={**owner, **idem()},
        json={"company": co["code"], "department": "GROWTH", "title": "کمپین تازه"},
    )  # fmt: skip
    assert w.status_code == 201, w.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await MF.standups(tx, after_nine + timedelta(days=1), only=co["id"]) == 1
    body = await su.fetchval(
        """SELECT m.body FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = $1 ORDER BY m.created_at DESC LIMIT 1""",
        f"{co['code']}-GROWTH",
    )
    assert body and w.json()["ref"] in body
    assert await su.fetchval("SELECT count(*) FROM llm.calls") == calls


async def test_a_sev1_opens_the_war_room_and_its_end_brings_a_postmortem(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    site = await su.fetchval(
        "INSERT INTO ops.sites (company_id, url, kind) VALUES ($1, $2, 'web') RETURNING id",
        co["id"], f"https://{co['code'].lower()}.example.test",
    )  # fmt: skip
    inc = await su.fetchrow(
        "INSERT INTO ops.incidents (company_id, site_id, severity, checks_failed) VALUES ($1, $2, 'sev1', 3) RETURNING id, ref",
        co["id"],
        site,
    )
    now = datetime.now(UTC)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await MF.war_rooms(tx, now, hub.settings)
    assert out["opened"] >= 1
    room = await su.fetchrow(
        "SELECT * FROM meetings.meetings WHERE type = 'war_room' AND incident_id = $1", inc["id"]
    )
    assert (
        room["state"] == "live"
        and room["budget_cap"] is None
        and room["incident_ref"] == inc["ref"]
    )
    parts = room["participants"]
    people = {p["actor"]["code"] for p in (json.loads(parts) if isinstance(parts, str) else parts)}
    assert f"{co['code']}-CEO" in people and f"{co['code']}-TECH-MGR" in people
    await su.execute("UPDATE ops.incidents SET closed_at = now() WHERE id = $1", inc["id"])
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await MF.war_rooms(tx, now, hub.settings)
        made = await MF.postmortems(tx, now)
    assert out["closed"] >= 1 and made >= 1
    assert (
        await su.fetchval("SELECT state FROM meetings.meetings WHERE id = $1", room["id"])
        == "ended"
    )
    pm = await su.fetchrow(
        "SELECT * FROM meetings.meetings WHERE type = 'postmortem' AND incident_id = $1", inc["id"]
    )
    local = pm["starts_at"].astimezone(ZoneInfo("Asia/Tehran"))
    assert (local.hour, local.minute) == (10, 0) and pm["budget_cap"] == 30000


# ================================================================ the lock ==
async def test_nothing_happens_while_the_holding_is_locked(
    client: httpx.AsyncClient, hub: Hub, wk: dict[str, Any], owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    m = await ad_hoc(client, owner, type="company", company=co["code"])
    await su.execute(
        "UPDATE meetings.meetings SET starts_at = now() - interval '1 minute' WHERE ref = $1",
        m["ref"],
    )
    site = await su.fetchval(
        "INSERT INTO ops.sites (company_id, url, kind) VALUES ($1, $2, 'web') RETURNING id",
        co["id"], f"https://lock-{co['code'].lower()}.example.test",
    )  # fmt: skip
    inc = await su.fetchval(
        "INSERT INTO ops.incidents (company_id, site_id, severity) VALUES ($1, $2, 'sev1') RETURNING id",
        co["id"],
        site,
    )
    runs = await su.fetchval("SELECT count(*) FROM agents.runs WHERE trigger = 'meeting'")
    calls = await su.fetchval("SELECT count(*) FROM llm.calls")
    async with holding_switch(su, "engaged"):
        out = await wk["acts"].meetings.meetings_tick()
        assert out == {"skipped": True, "reason": "holding_locked"}
        for step in MF.STEPS:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                assert (await MF.tick_step(tx, step, datetime.now(UTC), hub.settings))[
                    "skipped"
                ] is True
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await MF.war_room_for_alert(tx, co["id"], co["code"]) is None
            assert (await MF.advance(tx, await MT.load(tx, m["ref"], lock=True)))[
                "pending_run_id"
            ] is None
    assert (
        await su.fetchval("SELECT state FROM meetings.meetings WHERE ref = $1", m["ref"]) == "prep"
    )
    assert not await su.fetchval("SELECT 1 FROM meetings.meetings WHERE incident_id = $1", inc)
    assert await su.fetchval("SELECT count(*) FROM agents.runs WHERE trigger = 'meeting'") == runs
    assert await su.fetchval("SELECT count(*) FROM llm.calls") == calls
    await su.execute("UPDATE ops.incidents SET closed_at = now() WHERE id = $1", inc)


# ========================================================== PR-114, e2e ==
async def test_pr114_fails_a_meeting_over_its_budget_or_with_an_unsourced_claim_in_a_card(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    m = await ad_hoc(client, owner, type="company", company=co)
    await start(hub, m["ref"])
    _, h = await take_turn(su, hub, m["ref"])
    await client.post(
        f"/internal/v1/meetings/{m['ref']}/statement", headers={**h, **idem()},
        json={"item": 1, "statement_md": "x", "claims": [{"text_fa": "بی منبع"}], "draft_md": "پیش‌نویس"},
    )  # fmt: skip
    # One turn overshot the meeting's cap (the router stops the NEXT call).
    ended = await end_turn(su, hub, m["ref"], tokens=41000)
    assert ended["state"] == "ended" and ended["end_reason"] == "budget"
    own = await su.fetchval(
        "SELECT decision_ref FROM meetings.drafts WHERE meeting_id = $1", m["id"]
    )
    assert own  # the meeting's own card carries no unsourced claim (checked below)
    # A card that carries a claim the meeting never sourced (as if written around the code).
    card = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code,
               payload)
           SELECT id, 'meeting_resolution', 'A1', 'دور زدن', 'agent', $2,
                  jsonb_build_object('meeting', $3::text, 'item', 1, 'text_md', 'x', 'votes', '{}'::jsonb,
                                     'claims', '[{"text_fa": "بی منبع", "source": {"kind": "deliverable", "ref": "O-999999"}}]'::jsonb)
           FROM core.companies WHERE code = $1 RETURNING ref""",
        co,
        f"{co}-CEO",
        m["ref"],
    )
    holding = await hub.companies.holding()
    companies = {c.code: c.id for c in await hub.companies.all() if c.status == "active"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        checked = await C.CHECKS["PR-114"](
            C.CheckCtx(tx, holding.id, holding.code, companies, datetime.now(UTC), {})
        )
    keys = {x.key for x in checked.problems if x.key.startswith(f"meeting:{m['ref']}:")}
    assert f"meeting:{m['ref']}:budget" in keys and f"meeting:{m['ref']}:card:{card}" in keys
    assert f"meeting:{m['ref']}:card:{own}" not in keys


def step(summary: str, *actions: tuple[str, dict[str, Any]], done: bool = True) -> dict[str, Any]:
    return {
        "summary_fa": summary,
        "actions": [{"tool": t, "args": a} for t, a in actions],
        "done": done,
    }


async def test_a_meeting_runs_end_to_end_with_the_fake_model(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, agents: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    """Every turn is an agent run of trigger `meeting` through llm-router (the
    fake model) and the Tool Gateway; the secretary writes the summary."""
    co = (await new_company())["code"]
    report = await a_deliverable(client, owner, co, su)
    m = await ad_hoc(client, owner, type="company", company=co)
    await start(hub, m["ref"])
    devil = (await load(hub, m["ref"]))["settings"]
    agents.fake.enqueue(
        f"{co}-CEO",
        step("بیانیه", ("meeting.statement", {
            "meeting": m["ref"], "item": 1, "statement_md": "گزارش هفته آماده است.",
            "claims": [{"text_fa": "گزارش منتشر شد", "source": {"kind": "deliverable", "ref": report}}],
            "draft_md": "هفته‌ی بعد روی پشتیبانی تمرکز کنیم.",
        })),
        step("رأی", ("meeting.statement", {
            "meeting": m["ref"], "item": 1, "statement_md": "موافق.",
            "stance": {"vote": "support", "reason_fa": "اولویت درست است"},
        })),
    )  # fmt: skip
    seen: list[str] = []
    for _ in range(6):
        cur = await load(hub, m["ref"])
        if cur["state"] == "ended":
            break
        p = dict(cur["pending"] or {})
        seen.append(p["kind"])
        if p["kind"] == "challenge":
            agents.fake.enqueue(p["speaker"], step("چالش", ("meeting.challenge", {
                "meeting": m["ref"], "item": 1, "statement_md": "شاهد کافی است؟", "claims": []})))  # fmt: skip
        if p["kind"] == "minutes":
            agents.fake.enqueue(p["speaker"], step("خلاصه", ("meeting.minutes", {
                "meeting": m["ref"], "summary_md": "یک پیش‌نویس با یک رأی موافق."})))  # fmt: skip
        await free(su, p["speaker"])
        claim = await agents.runner.claim(str(cur["pending_run_id"]))
        assert claim.state == "running", (p, claim)
        out = await agents.runner.execute(str(cur["pending_run_id"]))
        assert out["state"] == "done", (p, out)
    assert seen == ["statement", "challenge", "vote", "minutes"], seen
    ended = await load(hub, m["ref"])
    assert ended["state"] == "ended" and ended["summary_md"] == "یک پیش‌نویس با یک رأی موافق."
    assert ended["used"] > 0 and ended["used"] <= ended["reserved"]
    metas = [
        json.loads(r["meta"]) if isinstance(r["meta"], str) else r["meta"]
        for r in await su.fetch(
            "SELECT meta FROM llm.calls WHERE meta ->> 'meeting' = $1", m["ref"]
        )
    ]
    assert len(metas) >= 4 and all(
        x["meeting_kind"] == "company" and int(x["meeting_cap"]) == 40000 for x in metas
    )
    assert all("charter_docs" in x and x["trigger"] == "meeting" for x in metas)
    assert devil.get("turn_cap_tokens") == 6000
    # A meeting tool outside a meeting turn is refused at the gateway's reserve.
    r = await client.post(
        "/internal/v1/runs/self/reserve", headers=await agent_headers(f"{co}-CEO"),
        json={"tool": "meeting.statement", "step": 1},
    )  # fmt: skip
    assert r.status_code == 403
