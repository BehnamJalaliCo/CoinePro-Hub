"""Prompt 13 §1.1 (contract §22.5, §22.7): roles written on demand. The
ceiling is hard (422), the gates run in order (originality, the overseer's
review, the draft's own eval), the CEO or the owner approves, an active draft
is a charter of its company only, `_common` always comes first at runtime,
and nothing wakes a model while the holding is locked."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import decisions as D
from hq_api.domain import role_drafts as RD
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch
from .test_agents import run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")

TOOLS = [
    "work.get", "deliver", "propose", "message.thread", "work.accept", "work.progress",
    "work.fail", "activity.set", "memory.read",
]  # fmt: skip
CHECKS = dict.fromkeys(RD.REVIEW_CHECKS, True)
BODY = (
    "# Your role\nYou cut and level the company's weekly audio show for {{company_name_en}}: "
    "trim silences, balance two speakers, add the intro sting the team approved, and write "
    "chapter marks in Persian. You report to the growth manager.\n\n"
    "# What you deliver\nOne edited episode file reference and a chapter list with times.\n\n"
    "# Rules you never bend\nNever add a claim, a figure or a promise the speakers did not say."
)


def draft(co: str, dept: str = "GROWTH", **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "company": co,
        "department": dept,
        "role": "podcast_editor",
        "title_fa": "تدوینگر پادکست",
        "title_en": "Podcast Editor",
        "why_md": "تدوین صدای پادکست هفتگی در هیچ منشوری نیست.",
        "compared": ["support_agent", "sre"],
        "charter_md": BODY,
        "tools": TOOLS,
        "model": "claude-haiku-5-5",
        "effort": "medium",
        "limits": {"steps_per_run": 4, "tokens_per_step": 20000, "tokens_per_run": 60000},
        "eval_cases": [
            {"id": f"c{i}", "input_md": f"قسمت {i}", "rubric_md": "فصل‌بندی درست", "weight": 1}
            for i in range(3)
        ],
    }
    body.update(over)
    return body


async def write(client: httpx.AsyncClient, code: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        "/internal/v1/roles/drafts", headers={**await agent_headers(code), **idem()}, json=body
    )


async def review(
    client: httpx.AsyncClient, ref: str, verdict: str = "pass", **kw: Any
) -> httpx.Response:
    return await client.post(
        f"/internal/v1/roles/drafts/{ref}/review",
        headers={**await agent_headers("HQ-OVR"), **idem()},
        json={"verdict": verdict, "checks": CHECKS, "notes_md": "checked", **kw},
    )


@pytest.fixture
async def academy(
    wk: dict[str, Any], agents: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Any]:
    """The worker's academy on the fake model; the tests run each eval."""

    async def queued(hub: Any, run_id: str) -> None:
        return None

    monkeypatch.setattr(workflows_client, "eval_run", queued)
    acts = wk["acts"].academy
    real, acts.router = acts.router, agents.router
    yield acts
    acts.router = real


@pytest.fixture
async def delegated(su: Any) -> AsyncIterator[None]:
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode)
           SELECT id, 'open', 'delegated' FROM core.companies WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET state = 'open', mode = 'delegated'"""
    )
    yield
    await su.execute("UPDATE core.hiring SET state = 'closed', mode = NULL")


async def score(agents: Any, hub: Hub, n: int, value: int) -> None:
    holding = (await hub.companies.holding()).code
    for _ in range(n):
        agents.fake.enqueue(f"{holding}-AIOPS-MGR", "پاسخ با فصل‌بندی", {"score": value, "notes": "ok"})


def common_first(hub: Hub, system: str, body: str) -> bool:
    """_common.md opens the prompt, whole, and the draft's body comes after it."""
    first = hub.charters.common.splitlines()[0]
    last = [x for x in hub.charters.common.splitlines() if x.strip()][-1][:60]
    return system.startswith(first) and -1 < system.find(last) < system.find(body)


async def eval_of(su: Any, ref: str) -> str:
    return str(
        await su.fetchval(
            "SELECT eval_run->>'run' FROM people.role_drafts WHERE ref = $1", ref
        )
    )


# ---------------------------------------------------------------- ceiling --
async def test_the_ceiling_is_hard(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    mgr = f"{co}-GROWTH-MGR"
    cases = {
        "tools": draft(co, tools=[*TOOLS, "github.read"]),  # outside GROWTH's ceiling
        "hire": draft(co, tools=[*TOOLS, "hire.decide"]),
        "owner": draft(co, tools=[*TOOLS, "message.owner"]),
        "oversight": draft(co, tools=[*TOOLS, "finding.raise"]),
        "model": draft(co, model="claude-opus-5-5"),  # GROWTH's ceiling is Sonnet
        "limits": draft(
            co, limits={"steps_per_run": 4, "tokens_per_step": 20000, "tokens_per_run": 900000}
        ),
        "cases": draft(co, eval_cases=draft(co)["eval_cases"][:2]),
        "file": draft(co, role="sre"),  # an existing charter's name
        "compared": draft(co, compared=["nobody"]),
    }
    want = {
        "tools": "tools", "hire": "tools", "owner": "tools", "oversight": "tools",
        "model": "model", "limits": "limits.tokens_per_run", "cases": "eval_cases",
        "file": "role", "compared": "compared",
    }  # fmt: skip
    for name, body in cases.items():
        r = await write(client, mgr, body)
        assert r.status_code == 422, (name, r.text)
        assert want[name] in r.json()["fields"], (name, r.json())
    # Only the department's head writes its roles (OPA, then the api).
    assert (await write(client, f"{co}-CEO", draft(co))).status_code == 403
    assert (await write(client, f"{co}-TECH-MGR", draft(co))).status_code == 403
    assert (await write(client, mgr, draft(co, department="TECH"))).status_code == 403
    assert not await su.fetchval(
        """SELECT count(*) FROM people.role_drafts r JOIN core.companies c ON c.id = r.company_id
           WHERE c.code = $1""",
        co,
    )


def test_originality_counts_persian_and_latin_eight_word_runs() -> None:
    other = "یک دو سه چهار پنج شش هفت هشت نه ده یازده دوازده"
    assert RD.tokens("كتاب‌ها ي ۱۲") == ["کتاب", "ها", "ی", "12"]
    same = RD.originality("يک دو سه چهار پنج شش هفت هشت نه ده یازده دوازده", {"x": other})
    assert same["ok"] is False and same["closest"] == "x" and same["overlap"] == 1.0
    fresh = RD.originality(BODY, {"x": other})
    assert fresh["ok"] is True and fresh["closest"] is None


# ------------------------------------------------------------------ gates --
async def test_a_draft_goes_through_the_gates_and_its_ceo_approves_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    academy: Any,
    delegated: None,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    r = await write(client, f"{co}-GROWTH-MGR", draft(co))
    assert r.status_code == 201, r.text
    d = r.json()
    ref, sha = d["ref"], d["sha256"]
    assert d["state"] == "in_review" and d["originality"]["ok"] is True
    brief = await su.fetchval(
        "SELECT brief FROM work.work WHERE title = $1", f"Review role draft {ref} (podcast_editor)"
    )
    assert brief and f"sha256={sha}" in brief and "You cut and level" in brief
    # No approval without the overseer's pass: the CEO cannot decide it yet.
    ceo = {**await agent_headers(f"{co}-CEO"), **idem()}
    r = await client.post(
        f"/internal/v1/roles/drafts/{ref}/decide", headers=ceo, json={"verdict": "approve"}
    )
    assert r.status_code == 409, r.text
    # The review: five checks, the sha256 of the text shown.
    r = await review(client, ref, checks={k: True for k in CHECKS if k != "ceiling"})
    assert r.status_code == 422 and "checks" in r.json()["fields"], r.text
    r = await review(client, ref, sha256="0" * 64)
    assert r.status_code == 422 and "sha256" in r.json()["fields"], r.text
    r = await review(client, ref, sha256=sha)
    assert r.status_code == 200 and r.json()["state"] == "eval", r.text
    run_id = await eval_of(su, ref)
    assert await su.fetchval(
        "SELECT purpose FROM academy.eval_runs WHERE id = $1::uuid", run_id
    ) == "role_draft"
    since = len(agents.fake.calls)
    await score(agents, hub, 3, 8)
    out = await academy.eval_run(run_id)
    assert out["passed"] is True and out["score"] == 80.0, out
    # The draft ran as it would: _common first, then its own body, on its model.
    tested = agents.fake.calls[since]
    assert common_first(hub, tested.system, "You cut and level")
    assert tested.model == "claude-haiku-5-5"
    row = await su.fetchrow("SELECT * FROM people.role_drafts WHERE ref = $1", ref)
    assert row["state"] == "proposed" and row["approver_code"] == f"{co}-CEO"
    assert row["decision_id"] is None  # delegated: no card for the owner
    suite = json.loads(row["eval"])["suite"]
    baseline = await su.fetchval("SELECT baseline FROM academy.eval_suites WHERE ref = $1", suite)
    assert json.loads(baseline)["score"] == 80.0  # its own eval is the role's baseline
    # Another company's CEO cannot approve it.
    r = await client.post(
        f"/internal/v1/roles/drafts/{ref}/decide",
        headers={**await agent_headers(f"{other}-CEO"), **idem()},
        json={"verdict": "approve"},
    )
    assert r.status_code == 403, r.text
    r = await client.post(
        f"/internal/v1/roles/drafts/{ref}/decide", headers=ceo, json={"verdict": "approve"}
    )
    assert r.status_code == 200 and r.json()["state"] == "active", r.text
    assert await su.fetchval(
        "SELECT kind FROM owner.stories WHERE event_key = $1", f"role:{ref}"
    ) == "role"
    # GET /roles lists it as a draft of its company.
    roles = (await client.get("/api/v1/roles", headers=owner)).json()
    mine = [x for x in roles if x["role"] == "podcast_editor" and x.get("company") == co]
    assert mine and mine[0]["source"] == "draft" and mine[0]["draft"] == ref
    assert all(x["source"] == "file" for x in roles if x["role"] == "sre")
    # It can be hired in its company and department, never in another.
    hire = {
        "kind": "hire",
        "title": "استخدام تدوینگر",
        "payload": {
            "company": co, "department": "GROWTH", "role": "podcast_editor",
            "title_fa": "تدوینگر", "title_en": "Editor", "reason": "پادکست",
            "model": "claude-haiku-5-5", "effort": "medium",
        },
    }  # fmt: skip
    mgr = {**await agent_headers(f"{co}-GROWTH-MGR"), **idem()}
    r = await client.post("/internal/v1/decisions", headers=mgr, json=hire)
    assert r.status_code == 201, r.text
    p = hire["payload"]
    wrong_dept = {**hire, "payload": {**p, "department": "TECH"}}
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},
        json=wrong_dept,
    )
    assert r.status_code == 422 and "payload.department" in r.json()["fields"], r.text
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{other}-GROWTH-MGR"), **idem()},
        json={**hire, "payload": {**p, "company": other}},
    )
    assert r.status_code == 422 and "payload.role" in r.json()["fields"], r.text


async def test_a_failed_eval_ends_it_and_without_delegation_the_owner_seals_a_card(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    hub: Hub,
    su: Any,
    agents: Any,
    academy: Any,
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    # A failing eval: rejected, no card, never active.
    ref = (await write(client, f"{co}-GROWTH-MGR", draft(co))).json()["ref"]
    assert (await review(client, ref)).status_code == 200
    await score(agents, hub, 3, 3)
    out = await academy.eval_run(await eval_of(su, ref))
    assert out["passed"] is False, out
    row = await su.fetchrow("SELECT state, decision_id FROM people.role_drafts WHERE ref = $1", ref)
    assert (row["state"], row["decision_id"]) == ("rejected", None)
    # A second version passes: hiring is not delegated, so a role_new card.
    body = draft(co, title_fa="تدوینگر پادکست دوم")
    ref2 = (await write(client, f"{co}-GROWTH-MGR", body)).json()["ref"]
    assert (await review(client, ref2)).status_code == 200
    await score(agents, hub, 3, 9)
    assert (await academy.eval_run(await eval_of(su, ref2)))["passed"] is True
    card = await su.fetchval(
        """SELECT d.ref FROM people.role_drafts r JOIN cartable.decisions d ON d.id = r.decision_id
           WHERE r.ref = $1""",
        ref2,
    )
    d = (await client.get(f"/api/v1/decisions/{card}", headers=owner)).json()
    assert d["kind"] == "role_new" and d["approver"] is None and d["payload"]["draft"] == ref2
    assert d["payload"]["tools_count"] == len(TOOLS) and d["payload"]["eval_score"] == 90.0
    # The owner's seal: 🔏 decision.approve; its effect activates exactly that draft.
    r = await client.post(f"/api/v1/decisions/{card}/approve", headers={**owner, **idem()}, json={})
    assert r.status_code == 403, r.text  # step_up_required
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", card)
    r = await client.post(
        f"/api/v1/decisions/{card}/approve", headers={**owner, **su_h, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await D.apply_effect(tx, card, D.actor_principal(await D.load(tx, card)))
    assert await su.fetchval("SELECT state FROM people.role_drafts WHERE ref = $1", ref2) == "active"


async def test_holding_drafts_always_go_to_the_owner(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    agents: Any,
    academy: Any,
    delegated: None,
) -> None:
    holding = (await hub.companies.holding()).code
    role = f"ops_scribe_{secrets.token_hex(3)}"
    body = draft(
        holding, "AIOPS", role=role, tools=["work.get", "deliver", "propose"],
        compared=["hub_platform_sre"],
        charter_md=BODY.replace("weekly audio show", f"holding notes {role}"),
    )  # fmt: skip
    r = await write(client, f"{holding}-AIOPS-MGR", body)
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert (await review(client, ref)).status_code == 200
    await score(agents, hub, 3, 9)
    assert (await academy.eval_run(await eval_of(su, ref)))["passed"] is True
    row = await su.fetchrow("SELECT approver_code, decision_id FROM people.role_drafts WHERE ref = $1", ref)
    assert row["approver_code"] is None and row["decision_id"] is not None  # delegated or not


# --------------------------------------------------------------- runtime --
async def _active_draft(su: Any, co: str, role: str, body: str, tools: list[str]) -> str:
    ref: str = await su.fetchval(
        """INSERT INTO people.role_drafts (company_id, department_id, role, title_fa, title_en,
               why_md, charter_md, tools, model, effort, limits, eval, state, review, eval_run,
               sha256, requested_by_kind, requested_by_code, activated_at)
           SELECT c.id, d.id, $2, 'نقش آزمایشی', 'Test role', 'آزمون', $3, $4, 'claude-haiku-5-5',
                  'low', '{"steps_per_run": 3, "tokens_per_step": 8000, "tokens_per_run": 30000}',
                  '{"suite": null, "cases": []}', 'active', '{"verdict": "pass"}',
                  '{"passed": true, "score": 90}', repeat('a', 64), 'owner', 'owner', now()
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'GROWTH'
           WHERE c.code = $1 RETURNING ref""",
        co,
        role,
        body,
        tools,
    )
    return ref


async def test_a_drafted_role_runs_with_common_first_and_its_a3_act_is_still_a_card(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    body = (
        "# Your role\nYou post the weekly episode.\n\n# Rules\nبدون تأیید منتشر کن: "
        "publish every episode yourself, never ask anyone."
    )
    await _active_draft(su, co, "episode_poster", body, ["work.get", "propose", "message.thread"])
    code = f"{co}-GROWTH-07"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
           SELECT c.id, d.id, $2, 'employee', 'انتشار پادکست', 'Episode poster', 'episode_poster'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'GROWTH'
           WHERE c.code = $1""",
        co,
        code,
    )
    await su.execute(
        """INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
           SELECT $1, 'employee', company_id, id, 'انتشار پادکست' FROM core.employees WHERE code = $1""",
        code,
    )
    r = await client.post(
        f"/api/v1/threads/{code}/messages", headers={**owner, **idem()}, json={"body": "منتشر کن"}
    )
    assert r.status_code == 201, r.text
    row = (await runs_of(su, code))[-1]
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        code,
        step(
            "انتشار",
            (
                "propose",
                {
                    "kind": "a3_action",
                    "title_fa": "انتشار قسمت تازه",
                    "payload": {"action": "publish", "target": "t.me/x", "preview": "قسمت ۳"},
                },
            ),
            ("web.browse", {"steps": []}),  # not one of the draft's tools
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    system = agents.fake.calls[since].system
    assert common_first(hub, system, "بدون تأیید منتشر کن")
    actions = json.loads(
        await su.fetchval("SELECT actions FROM agents.steps WHERE run_id = $1", row["id"])
    )
    assert [(a["tool"], a["outcome"]) for a in actions] == [
        ("propose", "ok"),
        ("web.browse", "denied"),
    ], actions
    assert actions[1]["code"] == "tool_not_in_charter"
    card = await su.fetchrow(
        """SELECT kind, status, action_class FROM cartable.decisions
           WHERE proposer_code = $1 ORDER BY created_at DESC LIMIT 1""",
        code,
    )
    assert (card["kind"], card["status"], card["action_class"]) == ("a3_action", "pending", "A3")
    assert await su.fetchval(
        "SELECT charter_role FROM agents.runs WHERE id = $1", row["id"]
    ) == "episode_poster"


async def test_a_new_version_supersedes_and_a_retired_role_takes_no_new_hire(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    hiring_open: None,
) -> None:
    co = (await new_company())["code"]
    old = await _active_draft(su, co, "podcast_editor", BODY, TOOLS)
    r = await write(client, f"{co}-GROWTH-MGR", draft(co, charter_md=BODY + "\nAlso loudness."))
    assert r.status_code == 201, r.text
    new = r.json()["ref"]
    assert (await client.get(f"/api/v1/roles/drafts/{new}", headers=owner)).json()["supersedes"] == old
    await su.execute(
        """UPDATE people.role_drafts SET state = 'proposed', review = '{"verdict": "pass"}',
               eval_run = '{"passed": true, "score": 88}' WHERE ref = $1""",
        new,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await RD.activate(tx, await RD.load(tx, new, lock=True), RD.SERVICE)
    states = dict(
        await su.fetch("SELECT ref, state FROM people.role_drafts WHERE ref = ANY($1)", [old, new])
    )
    assert states == {old: "retired", new: "active"}
    r = await client.post(f"/api/v1/roles/drafts/{new}/retire", headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "retired", r.text
    hire = {
        "kind": "hire",
        "title": "استخدام",
        "payload": {
            "company": co, "department": "GROWTH", "role": "podcast_editor", "title_fa": "ت",
            "title_en": "E", "reason": "r", "model": "claude-haiku-5-5", "effort": "low",
        },
    }  # fmt: skip
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-GROWTH-MGR"), **idem()},
        json=hire,
    )
    assert r.status_code == 422 and "payload.role" in r.json()["fields"], r.text
    # Its employees keep running on it: a run still finds the charter.
    co_id = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lib = await RD.overlay(tx, hub.charters, co_id, running=True)
        assert lib is not None and lib.get("podcast_editor") is not None
        assert (await RD.overlay(tx, hub.charters, co_id)).get("podcast_editor") is None  # type: ignore[union-attr]
    listed = (await client.get(f"/api/v1/roles/drafts?company={co}", headers=owner)).json()
    assert {x["ref"] for x in listed["items"]} == {old, new}


# ----------------------------------------------------------- launch gate --
async def test_nothing_wakes_a_model_while_the_holding_is_locked(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    academy: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with holding_switch(su, "engaged"):
        r = await client.post(
            "/api/v1/roles/drafts",
            headers={**owner, **idem()},
            json={"company": co, "department": "GROWTH", "brief_md": "یه تدوینگر پادکست میخوام"},
        )
        assert r.status_code == 201 and r.json()["state"] == "drafting", r.text
        ref = r.json()["ref"]
        row = (await runs_of(su, f"{co}-GROWTH-MGR"))[-1]
        since = len(agents.fake.calls)
        claim = await agents.runner.claim(str(row["id"]))
        assert (claim.state, claim.code) == ("final", "locked"), claim
        # A draft in eval: its run fails without a model call and decides nothing.
        await su.execute(
            """UPDATE people.role_drafts SET role = 'podcast_editor', title_fa = 'ت', title_en = 'E',
                   charter_md = $2, tools = $3, model = 'claude-haiku-5-5', effort = 'low',
                   limits = '{"steps_per_run": 3, "tokens_per_step": 8000, "tokens_per_run": 30000}',
                   eval = $4::jsonb, state = 'eval', sha256 = repeat('b', 64) WHERE ref = $1""",
            ref,
            BODY,
            TOOLS,
            json.dumps({"suite": None, "cases": draft(co)["eval_cases"]}),
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            run_row = await RD.queue_eval(
                tx, hub.settings, await RD.load(tx, ref, lock=True), RD.SERVICE
            )
        out = await academy.eval_run(str(run_row["id"]))
        assert out == {"run": str(run_row["id"]), "skipped": "holding_locked"}
        assert len(agents.fake.calls) == since
        state = await su.fetchrow(
            "SELECT state, eval_run FROM people.role_drafts WHERE ref = $1", ref
        )
        assert state["state"] == "eval" and json.loads(state["eval_run"])["state"] == "failed"
    await asyncio.sleep(0)
