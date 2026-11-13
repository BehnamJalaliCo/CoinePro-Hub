"""⟨1.37⟩ Contract §59.7, §59.8 (prompt 38): a working group's daily flow, by itself.

The owner: «بحث دکمه نیست، باید اتوماتیک پشت صحنه انجام بشه … توسط n8n». A flow is an automation
of kind `flow`; its day is one `LineRun` of its line; n8n's tick starts each occurrence once (the
hub's own lines tick when n8n is silent); the owner's controls are taps; the budget stops a step
before it starts and tells him once; mode `ask` holds the post for his «نوبت تو» until his day
ends. Every adapter is faked here.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import flow_auto as FA
from hq_api.domain import playbooks as PB
from hq_api.hub import Hub
from hq_api.lines import adapters, engine
from hq_api.lines.base import REGISTRY, StepContext, StepOutput

from .conftest import idem, step_up
from .p10_fakes import holding_switch

API = "/api/v1"
TEHRAN = ZoneInfo("Asia/Tehran")
SEATS = [{"seat": "writer", "role": "scriptwriter", "title_fa": "نویسنده"}]
STEPS: list[dict[str, Any]] = [
    {"key": "topic", "title_fa": "موضوع روز", "seat": "writer", "kind": "topic",
     "helper": "model", "model": "sonnet", "output_fa": "یک موضوع تازه"},
    {"key": "script", "title_fa": "سناریو و متن", "seat": "writer", "kind": "gpt_text",
     "helper": "gpt", "inputs": ["topic"], "settings": {"prompt_fa": "یک سناریو بنویس"}},
    {"key": "package", "title_fa": "بسته", "seat": "writer", "kind": "package", "helper": "code",
     "inputs": ["script"]},
    {"key": "publish", "title_fa": "انتشار ریلز و استوری", "seat": "writer", "kind": "publish",
     "helper": "ighub"},
]  # fmt: skip


class Fake:
    def __init__(self, kind: str, fn: Callable[[StepContext], Any]) -> None:
        self.kind = kind
        self._fn = fn

    async def run(self, ctx: StepContext) -> StepOutput:
        out: StepOutput = await self._fn(ctx)
        return out


class Fakes:
    """topic, gpt_text, package and publish; `cost` is what each step spends (USD equivalent)."""

    def __init__(self) -> None:
        self.seen: dict[str, list[StepContext]] = defaultdict(list)
        self.cost: dict[str, Decimal] = {"topic": Decimal("0.2"), "script": Decimal("0.5")}

    def all(self) -> list[Any]:
        def step(kind: str) -> Fake:
            async def run(ctx: StepContext) -> StepOutput:
                self.seen[kind].append(ctx)
                key = ctx.step["key"]
                data: dict[str, Any] = {}
                if kind == "publish":
                    data = {"external_id": None if ctx.dry else f"ig-{ctx.run_ref}", "kind": "reel",
                            "url": None if ctx.dry else f"https://instagram.test/{ctx.run_ref}"}  # fmt: skip
                return StepOutput(
                    text=f"{key} {ctx.run_ref}", data=data, via="fake",
                    tokens=100, usd_equiv=self.cost.get(key, Decimal(0)),
                )  # fmt: skip

            return Fake(kind, run)

        return [step(k) for k in ("topic", "gpt_text", "package", "publish")]


@pytest.fixture
def fakes() -> Any:
    adapters.load()
    saved = dict(REGISTRY)
    f = Fakes()
    for a in f.all():
        REGISTRY[a.kind] = a
    yield f
    REGISTRY.clear()
    REGISTRY.update(saved)


@pytest.fixture
async def quiet_flows(su: Any) -> AsyncIterator[None]:
    """The test database outlives a run: the flows of earlier tests are off, so a tick here
    starts only this test's own."""
    await su.execute("UPDATE growth.automations SET state = 'off' WHERE kind = 'flow'")
    yield
    await su.execute("UPDATE growth.automations SET state = 'off' WHERE kind = 'flow'")


async def a_playbook(
    hub: Hub, owner_db: Any, steps: list[dict[str, Any]] | None = None, *, sealed: bool = True
) -> str:
    """A sealed playbook (its group made as the seal makes it) with version 1 holding `steps`."""
    holding = await hub.companies.holding()
    d = {"seats": SEATS, "routines": [], "kpis": [], "connections": ["instagram"], "rules_fa": []}
    body = {**d, "title_fa": "ریلز روزانه", "purpose_fa": "یک ریلز هر روز", "platform": "instagram",
            "steps": STEPS if steps is None else steps, "package": [], "lessons": []}  # fmt: skip
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        row = await tx.one(
            """INSERT INTO owner.playbooks (company_id, title_fa, purpose_fa, state, platform,
                   definition, source, sealed_at)
               VALUES (:co, 'ریلز روزانه', 'یک ریلز هر روز', :st, 'instagram',
                       CAST(:d AS jsonb), CAST('{}' AS jsonb), CASE WHEN :st = 'sealed' THEN now() END)
               RETURNING *""",
            co=holding.id,
            st="sealed" if sealed else "draft",
            d=PB.definition_json(d),
        )
        if sealed:
            grow = await PB._group_row(tx, holding.id, dict(row))
            await tx.exec(
                "UPDATE owner.playbooks SET group_id = :g WHERE id = :id",
                g=grow["id"],
                id=row["id"],
            )
        await tx.exec(
            """INSERT INTO owner.playbook_versions (company_id, playbook_id, version, state, body,
                   sealed_at)
               VALUES (:co, :p, 1, :st, CAST(:b AS jsonb), CASE WHEN :st = 'sealed' THEN now() END)""",
            co=holding.id,
            p=row["id"],
            st="sealed" if sealed else "draft",
            b=json.dumps(body, ensure_ascii=False),
        )
    return str(row["ref"])


def form(co: str, **over: Any) -> dict[str, Any]:
    return {
        "company": co, "accounts": ["@pro.chart"],
        "time": {"mode": "fixed", "at": "09:30", "story": True},
        "budget": {"per_run_usd": 5, "per_day_usd": 8}, "mode": "auto", **over,
    }  # fmt: skip


async def a_flow(
    client: httpx.AsyncClient, hub: Hub, owner_db: Any, owner: dict[str, str],
    new_company: Callable[..., Any], **over: Any,
) -> dict[str, Any]:  # fmt: skip
    """A company runs a sealed playbook's flow (the use form): the 201's automation."""
    pref = await a_playbook(hub, owner_db)
    co = await new_company()
    r = await client.post(
        f"{API}/playbooks/{pref}/use", json=form(co["code"], **over), headers={**owner, **idem()}
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return {**out["automation"], "_company": co, "_playbook": pref}


def tehran(day_offset: int, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    d = datetime.now(TEHRAN).date() + timedelta(days=day_offset)
    return datetime.combine(d, time(h, m), TEHRAN).astimezone(UTC)


async def runs_of(su: Any, line: str) -> list[Any]:
    return list(
        await su.fetch(
            """SELECT r.* FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
               WHERE l.ref = $1 ORDER BY r.at, r.ref""",
            line,
        )
    )


# ------------------------------------------------------------------ units --
def test_the_publish_times_follow_the_days_and_the_hour() -> None:
    from hq_api.domain import flow_shapes as FS

    start = datetime(2026, 11, 14, 0, 0, tzinfo=TEHRAN).astimezone(UTC)  # a Saturday
    every = FA.times(FS.FlowSchedule(mode="fixed", at="09:30"), "09:30", "Asia/Tehran",
                     start, start + timedelta(days=7))  # fmt: skip
    assert len(every) == 7 and all(t.astimezone(TEHRAN).strftime("%H:%M") == "09:30" for t in every)
    some = FA.times(FS.FlowSchedule(mode="fixed", at="19:00", days=["SA", "MO"]), "19:00",
                    "Asia/Tehran", start, start + timedelta(days=7))  # fmt: skip
    assert [t.astimezone(TEHRAN).strftime("%a") for t in some] == ["Sat", "Mon"]
    sch = FS.FlowSchedule(mode="best", at="18:00")
    assert "پربازدیدترین" in FA.when_fa(sch, "18:00", False) and "۱۸:۰۰" in FA.when_fa(
        sch, "18:00", False
    )


def test_a_flow_step_keeps_its_own_words_in_its_settings() -> None:
    steps = FA.line_steps({"seats": SEATS, "steps": STEPS})
    script = next(s for s in steps if s["key"] == "script")
    assert script["prompt_fa"] == "یک سناریو بنویس" and "prompt_fa" not in script["settings"]
    assert script["settings"]["helper"] == "gpt" and script["settings"]["seat_fa"] == "نویسنده"
    assert script["timeout_s"] == FA.TIMEOUTS["gpt_text"] and script["gate"] == "auto"
    asked = FA.line_steps({"steps": [{**STEPS[0], "gate": "ask"}]})
    assert asked[0]["gate"] == "owner"


# ---------------------------------------------------------------- the tick --
async def test_the_tick_starts_each_occurrence_once_and_the_hub_steps_in_without_n8n(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company)
    publish = tehran(1, "09:30")
    async with holding_switch(su, "released"):
        early = await FA.due(hub, publish - timedelta(hours=3))
        assert flow["line"] not in str(early) and not await runs_of(su, flow["line"])
        first = await FA.due(hub, publish - timedelta(minutes=80))
        again = await FA.due(hub, publish - timedelta(minutes=79))
    runs = await runs_of(su, flow["line"])
    assert len(runs) == 1 and runs[0]["ref"] in first["runs"] and not again["runs"]
    assert runs[0]["trigger"] == "n8n" and runs[0]["occurrence_at"] == publish
    clock = await su.fetchrow(
        """SELECT f.* FROM growth.flow_clock f JOIN core.companies c ON c.id = f.company_id
           WHERE c.kind = 'holding'"""
    )
    assert clock["last_tick_at"] == publish - timedelta(minutes=79)
    # the run: each step knows its publish time; the timeline names the flow
    async with holding_switch(su, "released"):
        assert (await engine.drive(hub, runs[0]["ref"]))["state"] == "done"
    assert fakes.seen["publish"][-1].step["_flow"]["publish_at"] == publish.isoformat()
    assert fakes.seen["publish"][-1].step["_flow"]["automation"] == flow["ref"]
    run = (await client.get(f"{API}/line-runs/{runs[0]['ref']}", headers=owner)).json()
    assert run["automation"] == flow["ref"] and run["playbook"] == flow["_playbook"]
    assert run["version"] == 1 and run["cost"]["usd"] == pytest.approx(0.7)
    assert run["published"][0]["permalink"].startswith("https://instagram.test/")
    script = next(s for s in run["steps"] if s["key"] == "script")
    assert script["helper"] == "gpt" and script["seat_fa"] == "نویسنده"
    assert script["cost_usd"] == pytest.approx(0.5)
    # n8n silent: the hub's own tick runs the next day's; while n8n ticks it stays idle. The lead
    # is now the playbook's mean run (a fast fake run: its 10 minutes' margin)
    next_day = publish + timedelta(days=1)
    await su.execute(
        """UPDATE growth.flow_clock f SET last_tick_at = $1 FROM core.companies c
           WHERE c.id = f.company_id AND c.kind = 'holding'""",
        next_day - timedelta(minutes=12),
    )
    async with holding_switch(su, "released"):
        idle = await FA.fallback(hub, next_day - timedelta(minutes=8))
        assert idle.get("idle") and not idle["runs"]
        ran = await FA.fallback(hub, next_day - timedelta(minutes=1))
    later = await runs_of(su, flow["line"])
    assert len(later) == 2 and later[1]["ref"] in ran["runs"], ran
    assert later[1]["trigger"] == "schedule" and later[1]["occurrence_at"] == next_day
    assert await su.fetchval(
        """SELECT f.last_fallback_at FROM growth.flow_clock f JOIN core.companies c
               ON c.id = f.company_id WHERE c.kind = 'holding'"""
    ) == next_day - timedelta(minutes=1)


async def test_run_now_pause_and_skip_are_the_owners_taps(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company,
                        time={"mode": "fixed", "at": "23:59", "story": False})  # fmt: skip
    ref = flow["ref"]
    async with holding_switch(su, "released"):
        r = await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        assert r.status_code == 201, r.text
        first = r.json()
        r = await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        assert r.status_code == 201, r.text
    runs = await runs_of(su, flow["line"])
    assert [x["ref"] for x in runs] == [first["ref"], r.json()["ref"]]
    assert all(x["trigger"] == "owner" for x in runs)
    if datetime.now(TEHRAN).strftime("%H:%M") < "23:58":  # today's occurrence was still ahead
        assert runs[0]["occurrence_at"] == tehran(0, "23:59")
    assert runs[1]["occurrence_at"] is None  # the day already ran: an extra, out at once
    audit = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'automation.run_now' AND target_ref = $1",
        ref,
    )
    assert audit == 2
    # pause till a time, then the tick turns it on again
    until = datetime.now(UTC) + timedelta(hours=2)
    r = await client.post(f"{API}/automations/{ref}/pause", json={"until": until.isoformat()},
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "paused" and r.json()["paused_until"] is not None
    bad = await client.post(
        f"{API}/automations/{ref}/pause",
        json={"until": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        headers={**owner, **idem()},
    )
    assert bad.status_code == 422
    async with holding_switch(su, "released"):
        await FA.due(hub, until + timedelta(minutes=1))
    got = (await client.get(f"{API}/automations/{ref}", headers=owner)).json()
    assert got["state"] == "on" and got["paused_until"] is None
    # skip the next occurrence not started yet: its day is a skipped run; undoing brings it back
    r = await client.post(f"{API}/automations/{ref}/skip", json={"skip": True},
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 200, r.text
    skipped = [o for o in r.json()["upcoming"] if o["skip"]]
    assert len(skipped) == 1
    nxt = skipped[0]["at"]
    assert datetime.fromisoformat(nxt) > datetime.now(UTC)
    r = await client.post(f"{API}/automations/{ref}/skip", json={"at": nxt, "skip": False},
                          headers={**owner, **idem()})  # fmt: skip
    assert not any(o["skip"] for o in r.json()["upcoming"])
    r = await client.post(f"{API}/automations/{ref}/skip", json={"at": nxt, "skip": True},
                          headers={**owner, **idem()})  # fmt: skip
    at = datetime.fromisoformat(nxt)
    async with holding_switch(su, "released"):
        out = await FA.due(hub, at - timedelta(minutes=30))
    assert out["skipped"] >= 1
    last = (await runs_of(su, flow["line"]))[-1]
    assert last["state"] == "skipped" and last["note_fa"] == FA.OWNER_SKIP_FA
    # the switch: off, then on
    r = await client.post(f"{API}/automations/{ref}/state", json={"state": "off"}, headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "off" and r.json()["next"] is None
    r = await client.post(f"{API}/automations/{ref}/state", json={"state": "on"}, headers=owner)
    assert r.json()["state"] == "on" and r.json()["kind"] == "flow"
    verbs = {
        x["action"]
        for x in await su.fetch("SELECT action FROM audit.entries WHERE target_ref = $1", ref)
    }
    assert {"automation.pause", "automation.skip", "automation.state"} <= verbs


async def test_the_budget_stops_a_step_and_tells_the_owner_once(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company,
                        budget={"per_run_usd": 5, "per_day_usd": 0.6})  # fmt: skip
    ref = flow["ref"]
    async with holding_switch(su, "released"):
        r = await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        run = r.json()["ref"]
        assert (await engine.drive(hub, run))["state"] == "waiting"
        assert (await engine.drive(hub, run))["state"] == "waiting"  # looked again: still told once
    row = await su.fetchrow("SELECT * FROM lines.runs WHERE ref = $1", run)
    assert row["state"] == "waiting" and "به سقف بودجه‌ی امروز رسید" in row["note_fa"]
    assert "0.7" in row["note_fa"] and "0.6" in row["note_fa"]
    steps = {s["key"]: s["state"] for s in await su.fetch(
        "SELECT key, state FROM lines.step_runs WHERE run_id = $1", row["id"])}  # fmt: skip
    assert steps["package"] == "pending" and steps["script"] == "done"
    notes = await su.fetch(
        "SELECT * FROM notify.notifications WHERE link_kind = 'line_run' AND link_ref = $1", run
    )
    assert len(notes) == 1 and notes[0]["level"] == "decision"
    # a run-now past the day's cap
    r = await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
    assert r.status_code == 409 and r.json()["code"] == "budget_reached"
    assert "سقف بودجه" in r.json()["message_fa"]
    # raising the cap: no month envelope in USD, so 🔏 automation.budget on <ref>:<per_day>
    body = {"budget": {"per_run_usd": 5, "per_day_usd": 10}}
    r = await client.patch(f"{API}/automations/{ref}", json=body, headers=owner)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_h = await step_up(hub, owner_session["session_id"], "automation.budget", f"{ref}:10")
    r = await client.patch(f"{API}/automations/{ref}", json=body, headers={**owner, **su_h})
    assert r.status_code == 200, r.text
    assert r.json()["budget"]["per_day_usd"] == 10
    async with holding_switch(su, "released"):
        assert (await engine.drive(hub, run))["state"] == "done"
    # inside the company's USD month envelope a raise is a tap; lowering always is
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit, usd_limit)
           VALUES ($1, 'company', $2, 'month', 50000000, 1000)
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET usd_limit = 1000, enabled = true""",
        flow["_company"]["id"], flow["_company"]["code"],
    )  # fmt: skip
    r = await client.patch(f"{API}/automations/{ref}",
                           json={"budget": {"per_run_usd": 6, "per_day_usd": 20}}, headers=owner)  # fmt: skip
    assert r.status_code == 200, r.text
    r = await client.patch(f"{API}/automations/{ref}",
                           json={"budget": {"per_run_usd": 1, "per_day_usd": 2}}, headers=owner)  # fmt: skip
    assert r.status_code == 200 and r.json()["budget"]["per_day_usd"] == 2
    audit = await su.fetchrow(
        """SELECT * FROM audit.entries WHERE action = 'automation.update' AND target_ref = $1
           ORDER BY at DESC LIMIT 1""",
        ref,
    )
    assert "20" in audit["summary"] and "->" in audit["summary"]


async def test_mode_ask_waits_for_the_owner_till_his_day_ends(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company, mode="ask")
    ref = flow["ref"]
    async with holding_switch(su, "released"):
        r = await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        run = r.json()["ref"]
        assert (await engine.drive(hub, run))["state"] == "waiting"
    got = (await client.get(f"{API}/line-runs/{run}", headers=owner)).json()
    publish = next(s for s in got["steps"] if s["key"] == "publish")
    assert publish["state"] == "waiting" and publish["gate"] == "owner" and got["decision"]
    why = await su.fetchval("SELECT why FROM cartable.decisions WHERE ref = $1", got["decision"])
    assert why == FA.ASK_FA
    assert not fakes.seen["publish"]
    # his day ended untapped: skipped, never published, the card withdrawn
    await su.execute(
        "UPDATE lines.runs SET occurrence_at = now() - interval '2 days' WHERE ref = $1", run
    )
    async with holding_switch(su, "released"):
        assert (await engine.advance(hub, run))["state"] == "skipped"
    row = await su.fetchrow("SELECT state, note_fa FROM lines.runs WHERE ref = $1", run)
    assert row["state"] == "skipped" and row["note_fa"] == FA.NOT_APPROVED_FA
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", got["decision"])
        == "withdrawn"
    )
    assert not fakes.seen["publish"]


async def test_a_paused_member_and_a_skip_of_the_run_stop_it(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company)
    ref = flow["ref"]
    async with holding_switch(su, "released"):
        a = (
            await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        ).json()
        b = (
            await client.post(f"{API}/automations/{ref}/run-now", headers={**owner, **idem()})
        ).json()
    # «رد کردن این نوبت»: skipped, its ledger topic freed
    run_id = await su.fetchval("SELECT id FROM lines.runs WHERE ref = $1", a["ref"])
    co = flow["_company"]
    await su.execute(
        """INSERT INTO growth.topics (company_id, kind, title_fa, norm, run_id, source, by_code)
           VALUES ($1, 'topic', $2, $3, $4, 'claim', 'test')""",
        co["id"], f"سه سطح طلا {uuid.uuid4().hex[:6]}", uuid.uuid4().hex, run_id,
    )  # fmt: skip
    got = (await client.get(f"{API}/line-runs/{a['ref']}", headers=owner)).json()
    assert got["topic_fa"].startswith("سه سطح طلا")
    r = await client.post(f"{API}/line-runs/{a['ref']}/cancel", json={"skip": True}, headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "skipped"
    assert await su.fetchval("SELECT state FROM growth.topics WHERE run_id = $1", run_id) == "freed"
    # a paused member stops the next run before its next step
    await su.execute("UPDATE growth.memberships SET state = 'paused' WHERE automation = $1", ref)
    async with holding_switch(su, "released"):
        assert (await engine.advance(hub, b["ref"]))["state"] == "skipped"
    note = await su.fetchval("SELECT note_fa FROM lines.runs WHERE ref = $1", b["ref"])
    assert note == FA.PAUSED_MEMBER_FA


async def test_get_automation_answers_a_flows_shape(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any, fakes: Fakes, quiet_flows: None,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    flow = await a_flow(client, hub, owner_db, owner, new_company,
                        time={"mode": "best", "at": "18:00", "days": ["MO", "SA"], "story": True})  # fmt: skip
    r = await client.get(f"{API}/automations/{flow['ref']}", headers=owner)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["kind"] == "flow" and f["state"] == "on" and f["version"] == 1
    assert f["company"] == flow["_company"]["code"] and f["playbook"] == flow["_playbook"]
    assert f["schedule"]["mode"] == "best" and f["schedule"]["days"] == ["SA", "MO"]
    assert "پربازدیدترین" in f["schedule"]["when_fa"]
    assert [s["key"] for s in f["steps"]] == [s["key"] for s in STEPS]
    assert 3 <= len(f["upcoming"]) <= 5 and f["next"]["at"] == f["upcoming"][0]["at"]
    assert all(datetime.fromisoformat(o["at"]).astimezone(TEHRAN).strftime("%H:%M") == "18:00"
               for o in f["upcoming"])  # fmt: skip
    assert f["budget"] == {"per_run_usd": 5.0, "per_day_usd": 8.0, "spent_today_usd": 0.0}
    assert f["n8n"]["workflow"] == "hq-flows" and f["account"] == "pro.chart"
    assert f["today"] == {"runs": 0, "cost_usd": 0.0} and f["last_run"] is None
    runs = (await client.get(f"{API}/automations/{flow['ref']}/runs", headers=owner)).json()
    assert runs == {"items": [], "next_cursor": None}
    # the rules' list and the rule engine leave a flow alone
    listed = (await client.get(f"{API}/automations", headers=owner)).json()
    assert flow["ref"] not in {a["ref"] for a in listed}
    from hq_api.domain import automations as AU

    await AU.tick(hub)
    # PATCH: the hour, the mode and the title; the standing word follows
    r = await client.patch(
        f"{API}/automations/{flow['ref']}",
        json={"schedule": {"mode": "fixed", "at": "20:15"}, "mode": "ask", "title_fa": "ریلز شب"},
        headers=owner,
    )
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["schedule"]["at"] == "20:15" and f["mode"] == "ask" and f["title_fa"] == "ریلز شب"
    word = await su.fetchval("SELECT publish FROM growth.memberships WHERE automation = $1",
                             flow["ref"])  # fmt: skip
    assert '"ask"' in word
    r = await client.patch(f"{API}/automations/{flow['ref']}",
                           json={"schedule": {"mode": "fixed"}}, headers=owner)  # fmt: skip
    assert r.status_code == 422
