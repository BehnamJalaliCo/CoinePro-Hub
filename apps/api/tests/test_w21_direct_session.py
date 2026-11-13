"""⟨1.32⟩ The direct session, step three (contract §54): the holder of an owner's session is one
Claude Code session on the workshop with the hub's tools.

The owner, 2026-11-10: «مثل همین سشنی که من با تو صحبت میکنم». The holder's own run of an order
is handed over to a turn on the workshop (one brain, one thread, up to an hour); every hub tool
the session calls goes through the Tool Gateway as that holder, for the turn's own run; its
answer is the holder's word in the session. When the workshop cannot take it, the run is the
classic one: nothing waits.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import direct as DR
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p13a_media import mp4
from .test_p17_runners import take
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w14_workshop import run_ask, send_file, workshop

EMP_SQL = """SELECT e.id, e.code, e.kind, e.status, e.role, e.title_fa, e.company_id,
       c.code AS company, c.kind AS company_kind, c.name_fa AS company_name_fa,
       c.name_en AS company_name_en, d.code AS department
FROM core.employees e JOIN core.companies c ON c.id = e.company_id
LEFT JOIN core.departments d ON d.id = e.department_id WHERE e.code = $1"""


async def an_order(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, co: str, text: str | None = None
) -> dict[str, Any]:
    """An order of `co`, its holder and the holder's queued run of the order's own work."""
    out = await post_order(
        client, owner, text or f"برای {co} {words()} یک ریلز درباره‌ی اندیکاتور ATR بساز"
    )
    [route] = out["routes"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    emp = dict(await su.fetchrow(EMP_SQL, route["to"]))
    return {"ref": out["ref"], "holder": route["to"], "work_ref": route["work_ref"],
            "work_id": wid, "emp": emp}  # fmt: skip


async def queued_run(su: Any, o: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    """The holder's queued run of the order's work as the worker claims it (one is queued when
    there is none: a wake the hub made)."""
    row = await su.fetchrow(
        "SELECT * FROM agents.runs WHERE work_id = $1 AND state = 'queued' ORDER BY queued_at DESC",
        o["work_id"],
    )
    if row is None or (reason and not str(row["reason"]).startswith(reason.split(":")[0])):
        if row is not None:
            await su.execute(
                "UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now() "
                "WHERE id = $1",
                row["id"],
            )
        await su.fetchval(
            "SELECT work.wake_assignee($1, $2)", o["work_id"], reason or f"owner_reply:{o['ref']}"
        )
        row = await su.fetchrow(
            "SELECT * FROM agents.runs WHERE work_id = $1 AND state = 'queued'", o["work_id"]
        )
    assert row is not None
    await su.execute(
        "UPDATE agents.runs SET state = 'running', started_at = now() WHERE id = $1", row["id"]
    )
    return dict(row)


async def end_run(su: Any, run: dict[str, Any], note: str | None) -> None:
    """As Runner.execute ends a run it handed over (`done`, the note)."""
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now(), note = $2 WHERE id = $1",
        run["id"],
        note,
    )


async def result(
    client: httpx.AsyncClient, rn: dict[str, Any], job: str, answer: str,
    files: list[str] | None = None, exit_code: int = 0, usage: dict[str, Any] | None = None,
) -> None:  # fmt: skip
    r = await client.post(
        f"/api/v1/runners/jobs/{job}/result",
        json={"exit_code": exit_code, "summary_fa": "تمام شد." if exit_code == 0 else "خطا",
              "usage": usage,
              "data": {"session_id": "cs-direct-1", "result_fa": answer, "files": files or [],
                       "effort": "max", "tool_calls": 3}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text


def test_the_brief_says_who_it_is_once_and_only_what_is_new_after() -> None:
    w = {"ref": "W-000123", "title": "ریلز ATR"}
    emp = {"code": "PC-MED-MGR", "title_fa": "مدیر رسانه", "company": "PC",
           "company_name_fa": "پروچارت"}  # fmt: skip
    brief = {"order": "F-0014", "text": "یک ریلز بساز", "plan": [{"n": 1, "title": "متن", "state": "todo"}],
             "plan_next": 1, "owner_said": ["اول متن را بنویس", "شعار آخرش باشد"],
             "memory_md": "گوینده Charon است.", "direct_rule": "DIRECT: do it yourself."}  # fmt: skip

    class Charter:
        body = "You direct the company's media."

    tools = ["order.ask", "speech.make", "topic.claim"]
    first = DR.compose(w, emp, brief, charter=Charter(), tools=tools,
                       reason="owner_reply:F-0014", first=True,
                       inputs=[{"name": "logo.png", "mime": "image/png"}])  # fmt: skip
    assert "تو مدیر رسانه در پروچارت هستی" in first and "جلسه‌ی F-0014" in first
    assert "mcp__hq__" in first and "order_ask، speech_make، topic_claim" in first
    assert "skill_read" in first and "You direct the company's media." in first
    assert "گوینده Charon است." in first and "in/logo.png (image/png)" in first
    assert "DIRECT: do it yourself." in first and "یک ریلز بساز" in first
    assert first.rstrip().endswith("- شعار آخرش باشد")  # his last word is the last thing it reads
    assert "مدیر کل همین حالا در جلسه حرف زد" in first
    later = DR.compose(w, emp, brief, charter=Charter(), tools=tools, reason="nudge:F-0014",
                       first=False, inputs=[])  # fmt: skip
    assert "ادامه‌ی جلسه‌ی F-0014" in later and "«ادامه بده»" in later
    assert "راهنمای نقش تو" not in later and "mcp__hq__" not in later and len(later) < len(first)
    assert DR.mcp_name("kill_switch.engage") == "kill_switch_engage"
    assert DR.why_fa("child_delivered:W-1").startswith("کاری روی این جلسه")


async def test_the_holders_run_becomes_one_turn_with_the_hubs_tools(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    ref, holder = o["ref"], o["holder"]

    # 1. the worker claims the holder's run: it is handed over, no model is called here
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn "), note
    await end_run(su, run, note)
    job = await take(client, rn)
    a = job["args"]
    assert job["kind"] == "claude" and note.endswith(job["id"])
    assert a["direct"] is True and a["tools"] == "hub" and a["hands"] is True
    # ⟨2026-11-13⟩ the usage audit (P1): a session's talk thinks at xhigh, a flow's build at max
    assert a["model"] == "claude-opus-5-5" and a["effort"] == "xhigh" and a["sandbox"] == "auto"
    assert a["workspace"] == o["work_ref"] and a["order"] == ref and "resume" in a
    assert f"جلسه‌ی {ref}" in a["brief"] and "ابزارهای ستاد" in a["brief"]
    assert "order_ask" in a["brief"] and "workshop_run" not in a["brief"]
    # the turn has a run of its own (the gateway acts for a run), beside the classic one
    d = await su.fetchrow("SELECT * FROM agents.runs WHERE id = $1::uuid", a["run"])
    assert (d["trigger"], d["state"], d["reason"]) == ("direct", "running", f"direct:{ref}")
    assert d["work_id"] == o["work_id"] and (d["tool_calls_cap"], d["step_tool_calls_cap"]) == (
        500,
        50,
    )
    act = (await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)).json()
    working = act["working"]
    assert len(working) == 1 and "دارد روی فرمان تو کار میکند" in working[0]["doing_fa"]
    assert working[0]["who_fa"].startswith(o["emp"]["title_fa"])  # the holder, not «کارگاه هلدینگ»

    # 2. the session's tools: its role's own (the workshop is what it is), each with its input
    asked: list[dict[str, Any]] = []

    async def worker(hub_: Any, req: dict[str, Any], timeout_s: float = 150.0) -> Any:
        asked.append(req)
        if req["op"] == "catalog":
            return {"tools": [
                {"tool": t, "class": "A1", "description": f"does {t}",
                 "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}}}
                for t in req["tools"]
            ]}  # fmt: skip
        return {"outcome": "ok", "class": "A1", "code": None, "ref": ref,
                "result": {"done": req["tool"]}}  # fmt: skip

    monkeypatch.setattr(workflows_client, "direct_tool", worker)
    r = await client.get(f"/api/v1/runners/jobs/{job['id']}/tools", headers=rn["h"])
    assert r.status_code == 200, r.text
    tools = {t["name"]: t for t in r.json()["tools"]}
    assert {"order_ask", "order_progress", "topic_claim", "skill_list", "skill_read"} <= set(tools)
    assert "workshop_run" not in tools and "workshop_stop" not in tools
    assert tools["order_ask"]["description"].startswith("[A1] does order.ask")
    assert tools["order_ask"]["input_schema"]["properties"] == {"x": {"type": "string"}}
    assert asked[0]["op"] == "catalog" and "order.ask" in asked[0]["tools"]

    # 3. a call goes to the gateway as the holder, for the turn's own run
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/tools/call",
        headers=rn["h"],
        json={"name": "order_progress", "args": {"done": [1], "note_fa": "متن نوشته شد"}},
    )
    assert r.status_code == 200 and r.json()["outcome"] == "ok", r.text
    assert r.json()["result"] == {"done": "order.progress"}
    call = asked[-1]
    assert call == {"op": "call", "employee": holder, "run": a["run"], "step": 1, "index": 0,
                    "tool": "order.progress", "args": {"done": [1], "note_fa": "متن نوشته شد"}}  # fmt: skip
    # the steps follow the run's own count (the gateway's cap of a step is 50 calls)
    await su.execute("UPDATE agents.runs SET tool_calls = 120 WHERE id = $1::uuid", a["run"])
    await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                      json={"name": "order_ask", "args": {}})  # fmt: skip
    assert (asked[-1]["step"], asked[-1]["index"]) == (3, 20)
    # what is not its role's is not called at all; the workshop is not a tool of itself
    n = len(asked)
    for name in ("workshop_run", "kill_everything"):
        r = await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                              json={"name": name, "args": {}})  # fmt: skip
        assert r.status_code == 200 and r.json()["code"] == "unknown_tool", r.text
    assert len(asked) == n
    # roles are skills: the session reads a role's guide and does the work itself
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                          json={"name": "skill_list", "args": {}})  # fmt: skip
    roles = {s["role"] for s in r.json()["result"]["skills"]}
    assert {"scriptwriter", "motion_designer"} <= roles and "secretary" not in roles
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                          json={"name": "skill_read", "args": {"role": "scriptwriter"}})  # fmt: skip
    got = r.json()
    assert got["outcome"] == "ok" and len(got["result"]["guide_md"]) > 200, got
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                          json={"name": "skill_read", "args": {"role": "nobody"}})  # fmt: skip
    assert r.json()["outcome"] == "error" and r.json()["code"] == "not_found"
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'skill.read' AND actor_code = $1", holder
    ) == 1  # fmt: skip
    # another server's runner, and a job that is no direct turn, get nothing
    other = await new_company()
    from .test_p17_runners import pair

    stranger = await pair(client, hub, owner_session, other, "web-9")
    assert (await client.get(f"/api/v1/runners/jobs/{job['id']}/tools", headers=stranger["h"])
            ).status_code == 404  # fmt: skip

    # 4. his word while the turn works waits for it (one brain, one thread), said once
    r = await client.post(f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()},
                          json={"text": "شعار آخرش «با پروچارت همیشه با نمودار» باشد"})  # fmt: skip
    assert r.status_code == 200, r.text
    run2 = await queued_run(su, o)
    note2 = await DR.hand_over(hub, run2, o["emp"])
    assert note2 == DR.WAITING
    await end_run(su, run2, note2)
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    assert sum(1 for s in rep["steps"] if s["what_fa"] == DR.WAITS_FA) == 1
    assert (await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=rn["h"])
            ).status_code == 204  # nothing new started  # fmt: skip

    # 5. the turn ends: what it says is the holder's word in the session, its files an output
    # (the claim showed the holder working; the handed-over run's finish leaves it while the
    # turn is open, and the turn's end sets him at rest)
    await su.execute("UPDATE core.employees SET activity = 'working' WHERE code = $1", holder)
    r = await send_file(client, rn, job["id"], "reel.mp4", "video/mp4", mp4(2))
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    await result(
        client, rn, job["id"], "ریلز ATR آماده است؛ نگاهش کنید و اگر خوب بود «تأیید و انتشار» را بزنید.",
        files=[fid], usage={"input_tokens": 1200, "output_tokens": 800, "model": "claude-opus-5-5"},
    )  # fmt: skip
    # the runner's retry of the same result (its read timed out) is a replay: said once, booked once
    await result(
        client, rn, job["id"], "ریلز ATR آماده است؛ نگاهش کنید و اگر خوب بود «تأیید و انتشار» را بزنید.",
        files=[fid], usage={"input_tokens": 1200, "output_tokens": 800, "model": "claude-opus-5-5"},
    )  # fmt: skip
    d = await su.fetchrow("SELECT * FROM agents.runs WHERE id = $1::uuid", a["run"])
    assert (d["state"], d["input_tokens"], d["output_tokens"]) == ("done", 1200, 800)
    assert await su.fetchval("SELECT activity FROM core.employees WHERE code = $1", holder) == (
        "sleeping"
    )
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    last = [s for s in rep["steps"] if s["what_fa"].startswith("ریلز ATR آماده است")]
    assert len(last) == 1 and last[0]["who_fa"].startswith(o["emp"]["title_fa"])
    out = rep["outputs"][-1]
    made = await su.fetchrow(
        "SELECT title, produced_with, attachments FROM cartable.deliverables WHERE ref = $1",
        out["ref"],
    )
    pw = made["produced_with"]
    pw = json.loads(pw) if isinstance(pw, str) else pw
    # ⟨1.35⟩ §57.6 named by its file, never «خروجی جلسه: …»
    assert made["title"] == "reel" and pw["direct"] is True and "revision_of" not in pw
    assert (pw["effort"], pw["model"]) == ("max", "claude-opus-5-5")
    assert [str(x) for x in made["attachments"]] == [fid]
    # the order's work stays open (it is his session), and no classic run is woken to repeat it
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", o["work_id"]) in (
        "in_progress", "queued", "waiting",
    )  # fmt: skip
    runs = await su.fetch(
        "SELECT reason, state FROM agents.runs WHERE work_id = $1 AND state = 'queued'",
        o["work_id"],
    )
    # ... but the word of his that waited starts the next turn at once
    assert [x["reason"] for x in runs] == [f"owner_reply:{ref}"]
    run3 = await queued_run(su, o)
    note3 = await DR.hand_over(hub, run3, o["emp"])
    await end_run(su, run3, note3)
    nxt = await take(client, rn)
    assert nxt["args"]["direct"] is True and nxt["args"]["resume"] == "cs-direct-1"
    assert nxt["args"]["brief"].startswith(f"# ادامه‌ی جلسه‌ی {ref}")
    assert "شعار آخرش «با پروچارت همیشه با نمودار» باشد" in nxt["args"]["brief"]
    assert nxt["args"]["run"] != a["run"]
    # the Treasury saw the first turn's tokens, and the audit trail the turn itself
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'session.turn' AND target_ref = $1",
        o["work_ref"],
    ) >= 2  # fmt: skip
    # the talk-loop stop never counts a run that was handed over
    from hq_api.domain import order_report as OR

    async with hub.db.tx(await hub.companies.ids()) as tx:
        rep_row = await OR.ensure(tx, ref)
        works = await OR.tree(tx, OR.root_refs(await OR.load_order(tx, ref)))
        assert await OR.idle_runs(tx, dict(rep_row), works, rep_row["created_at"]) == 0


async def test_when_the_workshop_cannot_take_it_the_run_is_the_classic_one(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    # an older runner on the workshop: it could not give the session the hub's tools
    rn = await workshop(client, hub, owner_session, su, version="0.3.4")
    assert await DR.hand_over(hub, run, o["emp"]) is None
    # the right runner, but the switch of the deploy is off
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    on = hub.settings
    monkeypatch.setattr(hub, "settings", dataclasses.replace(on, direct_sessions=False))
    assert await DR.hand_over(hub, run, o["emp"]) is None
    monkeypatch.setattr(hub, "settings", on)
    # not the holder's run of the order's own work: a message, a child work, another employee
    assert await DR.hand_over(hub, {**run, "trigger": "message"}, o["emp"]) is None
    assert await DR.hand_over(hub, {**run, "work_id": None}, o["emp"]) is None
    other = dict(await su.fetchrow(EMP_SQL, f"{co}-CEO"))
    if other["code"] != o["holder"]:
        assert await DR.hand_over(hub, run, other) is None
    # a run that only tells of a failed turn stays the quick classic one (never a loop)
    assert await DR.hand_over(
        hub, {**run, "reason": f"workspace_failed:{o['work_ref']}"}, o["emp"]
    ) is None  # fmt: skip
    assert await su.fetchval(
        "SELECT count(*) FROM agents.runs WHERE trigger = 'direct' AND work_id = $1", o["work_id"]
    ) == 0  # fmt: skip
    assert (await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=rn["h"])
            ).status_code == 204  # fmt: skip

    # a classic turn of the workshop is live for this work (the holder's own `workshop.run`):
    # the word waits for it, and a classic job is no direct turn for the tool routes
    await end_run(su, run, None)  # the claimed run ended; the holder's next one is its own
    r = await run_ask(client, o["holder"], {"work": o["work_ref"], "brief": "یک کاور بساز"})
    assert r.status_code == 201, r.text
    classic = await take(client, rn)
    assert "direct" not in classic["args"] and "tools" not in classic["args"]
    assert await DR.hand_over(hub, run, o["emp"]) == DR.WAITING
    r = await client.get(f"/api/v1/runners/jobs/{classic['id']}/tools", headers=rn["h"])
    assert r.status_code == 422, r.text
    r = await client.post(f"/api/v1/runners/jobs/{classic['id']}/tools/call", headers=rn["h"],
                          json={"name": "order_ask", "args": {}})  # fmt: skip
    assert r.status_code == 422, r.text


async def test_a_turn_that_fails_or_is_stopped_ends_its_run_and_is_never_silent(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    job = await take(client, rn)
    await result(client, rn, job["id"], "", exit_code=1)
    d = await su.fetchrow("SELECT state, error_code FROM agents.runs WHERE id = $1::uuid",
                          job["args"]["run"])  # fmt: skip
    assert d["state"] == "failed"
    # the holder is told at once, by the quick classic run (it says why; a fix is a new turn)
    woken = await su.fetchrow(
        "SELECT reason FROM agents.runs WHERE work_id = $1 AND state = 'queued'", o["work_id"]
    )
    assert woken is not None and woken["reason"] == f"workspace_failed:{o['work_ref']}"
    # once the turn ended its tools are closed
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/tools/call", headers=rn["h"],
                          json={"name": "order_ask", "args": {}})  # fmt: skip
    assert r.status_code == 409, r.text

    # an empty answer with no file and no question is said, never left silent
    await su.execute(
        "UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now() "
        "WHERE work_id = $1 AND state = 'queued'",
        o["work_id"],
    )
    run = await queued_run(su, o, reason=f"nudge:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn "), note
    await end_run(su, run, note)
    job = await take(client, rn)
    assert "resume" in job["args"]
    await result(client, rn, job["id"], "")
    rep = (await client.get(f"/api/v1/orders/{o['ref']}/report", headers=owner)).json()
    assert rep["steps"][-1]["what_fa"] == DR.EMPTY_FA
    assert await su.fetchval(
        "SELECT count(*) FROM agents.runs WHERE trigger = 'direct' AND state = 'running' "
        "AND work_id = $1",
        o["work_id"],
    ) == 0  # fmt: skip


async def test_a_turn_the_owner_stops_ends_its_run_and_his_next_word_starts_a_turn(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ F-0018: the owner stopped a turn; its run stayed `running` (the runner's
    result of a cancelled job is refused, so after_job never ran) and each word he said after it
    only waited until the run's token expired."""
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    job = await take(client, rn)

    r = await client.post(f"/api/v1/work/{o['work_id']}/stop", headers={**owner, **idem()})
    assert r.status_code == 200 and r.json()["jobs_stopped"] == 1, r.text
    d = await su.fetchrow("SELECT state, error_code, note FROM agents.runs WHERE id = $1::uuid",
                          job["args"]["run"])  # fmt: skip
    assert (d["state"], d["error_code"]) == ("failed", "workspace_stopped")
    assert d["note"] == f"direct turn, job {job['id']}"
    # the runner's late result of the cancelled job changes nothing
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.", "data": {"result_fa": "x"}},
        headers=rn["h"],
    )
    assert r.status_code == 409, r.text

    # his next word is a new turn on the same workspace, not «the last turn is still working»
    await su.execute("UPDATE work.workspaces SET updated_at = now() - interval '1 minute' "
                     "WHERE work_id = $1", o["work_id"])  # fmt: skip
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn ") and note != DR.WAITING, note
    await end_run(su, run, note)
    nxt = await take(client, rn)
    assert nxt["id"] != job["id"] and nxt["args"]["direct"] is True

    # a turn the holder stops itself (workshop.stop) ends its run the same way
    from hq_api.domain import hands as HANDS
    from hq_api.domain import work as W

    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load(tx, o["work_id"], lock=True)
        out = await HANDS.stop_turn(tx, DR.principal(o["emp"]), w, "test")
    assert out["stopped"] is True
    assert await su.fetchval("SELECT state FROM agents.runs WHERE id = $1::uuid",
                             nxt["args"]["run"]) == "failed"  # fmt: skip


async def test_a_heavy_session_starts_afresh_from_its_memory_and_notes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ The owner: never millions of tokens re-read per word, never a model that
    forgot. A Claude session that carries more than ROTATE_TOKENS is ended between two turns,
    its memory caught up first; the next turn is a fresh session in the same folder whose brief
    sends it to NOTES.md, the memory and the session's state."""
    from hq_api.domain import session_memory as MEM

    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    job = await take(client, rn)
    assert "NOTES.md" in job["args"]["brief"]  # the rule is there from the first turn
    # a light turn: the next one resumes the same Claude session
    await result(client, rn, job["id"], "اولین نوبت تمام شد.",
                 usage={"cache_write_tokens": 90_000, "cache_read_tokens": 400_000})  # fmt: skip
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    second = await take(client, rn)
    assert second["args"].get("resume") and "ادامه‌ی جلسه" in second["args"]["brief"]
    sess = await su.fetchval("SELECT session_id FROM work.workspaces WHERE work_id = $1",
                             o["work_id"])  # fmt: skip

    # a heavy one: the next word starts afresh, after the memory caught up
    caught: list[str] = []

    async def catch_up(hub_: Any, call: Any, ref: str) -> int:
        caught.append(ref)
        return 1

    monkeypatch.setattr(MEM, "catch_up", catch_up)
    await result(client, rn, second["id"], "دومین نوبت تمام شد.",
                 usage={"cache_write_tokens": 200_000, "cache_read_tokens": 3_000_000})  # fmt: skip
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn "), note
    await end_run(su, run, note)
    third = await take(client, rn)
    assert caught == [o["ref"]]
    assert await su.fetchval("SELECT state FROM workshop.sessions WHERE id = $1", sess) == "done"
    assert not third["args"].get("resume")  # a fresh Claude session …
    assert third["args"]["workspace"] == o["work_ref"]  # … in the same folder
    brief = third["args"]["brief"]
    assert "ادامه‌ی همین جلسه در نشستی تازه" in brief and "## وضع جلسه" in brief
    assert await su.fetchval(
        "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'session_rotated'",
        o["work_id"],
    ) == 1  # fmt: skip
    # the fresh session carries little again: no second rotation on the next word
    await result(client, rn, third["id"], "ادامه دادم.", usage={"cache_write_tokens": 80_000})
    assert not await DR.rotate_if_heavy(hub, o["work_id"])


def test_every_meta_key_the_hub_sends_is_one_the_router_takes() -> None:
    """⟨2026-11-13⟩ A meta key llm-router does not allow fails the whole call (422): the session
    memory sent `order` and never folded. The keys the api's model calls send, against the
    router's own allow-list (services/llm-router/src/llm_router/schemas.py)."""
    import ast
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "hq_api"
    tail = "llm-router/src/llm_router/schemas.py"
    here = Path(__file__).resolve()
    roots = [*(parent / "services" for parent in here.parents), Path("/w")]
    found = [r / tail for r in roots if (r / tail).exists()]
    if not found:
        pytest.skip("the router's source is not mounted here")
    block = found[0].read_text().split("META_KEYS = frozenset(")[1].split("})")[0]
    allowed = set(re.findall(r'^\s+"([a-z_]+)",', block, re.M))
    sent: set[str] = set()
    for f in root.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value: v for k, v in zip(node.keys, node.values, strict=True)
                    if isinstance(k, ast.Constant)}  # fmt: skip
            meta = keys.get("meta")
            if "task_class" in keys and isinstance(meta, ast.Dict):  # a router call's body
                sent |= {str(x.value) for x in meta.keys if isinstance(x, ast.Constant)}
    assert sent and sent <= allowed, sorted(sent - allowed)


async def test_a_voice_the_session_made_reaches_its_next_turn_in_the_in_folder(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ F-0018: the raw voice speech.make made never reached the session's folder (only
    the owner's files did), so its check, a sentence made again and the video's sound waited. A
    file that names the session (meta order_id) goes into `in/` with the next turn."""
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    job = await take(client, rn)
    await result(client, rn, job["id"], "نوبت اول.")
    order_id = await su.fetchval(
        "SELECT order_id FROM owner.order_reports WHERE ref = $1", o["ref"]
    )
    fid = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code, kind, meta)
           VALUES ($1, 'speech-abc.ogg', 'audio/ogg', 10, repeat('a', 64), gen_random_uuid()::text, 'agent', $2,
                   'audio', jsonb_build_object('order_id', $3::text, 'made_by', 'speech.make'))
           RETURNING id""",
        o["emp"]["company_id"], o["holder"], str(order_id),
    )  # fmt: skip
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    nxt = await take(client, rn)
    names = {i["file_id"]: i["name"] for i in nxt["args"].get("inputs") or []}
    assert str(fid) in names and names[str(fid)].endswith(".ogg")
    assert "in/" in nxt["args"]["brief"]


async def test_the_same_content_is_not_delivered_twice(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """⟨2026-11-13⟩ F-0018: one video came three times under three names (the card's name is §57.6's)."""
    from hq_api.domain import workspace as WSX

    co = await new_company()

    async def a_file(name: str, sha: str) -> str:
        return str(await su.fetchval(
            """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
                   created_by_kind, created_by_code, kind)
               VALUES ($1, $2, 'video/mp4', 1, $3, gen_random_uuid()::text, 'agent', 'x', 'video')
               RETURNING id""",
            co["id"], name, sha * 64,
        ))  # fmt: skip

    v1, v2, cover = await a_file("ویدیو-۱۵-ثانیه.mp4", "a"), await a_file("پیش_نمایش.mp4", "a"), \
        await a_file("کاور-ویدیوی-اول.jpg", "b")  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        # the same content twice in one turn: once
        w = await su.fetchval(
            """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
               VALUES ($1, 'one_off', 'کار', 'service', 'test') RETURNING id""",
            co["id"],
        )
        # a video in the set: a publish package, kept whole (F-0018: the cover was lost)
        assert await WSX.fresh_files(tx, w, [v1, v2, cover]) == [v1, v2, cover]
    # once a card of the work holds it, it is not delivered again
    emp = await su.fetchval("SELECT id FROM core.employees WHERE company_id = $1 LIMIT 1", co["id"])
    await su.execute(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary,
               attachments, produced_with, usage, evidence, category)
           VALUES ($1, $2, $3, 't', 's', ARRAY[$4::uuid], '{}', '{}', '[]', 'report')""",
        co["id"], w, emp, v1,
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await WSX.fresh_files(tx, w, [v2, cover]) == [v2, cover]  # a video: a package
        # a set without a video drops what an earlier card holds
        cap = str(await su.fetchval(
            """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
                   created_by_kind, created_by_code, kind)
               VALUES ($1, 'caption.txt', 'text/plain', 1, $2, gen_random_uuid()::text, 'agent',
                       'x', 'document') RETURNING id""",
            co["id"], "c" * 64,
        ))  # fmt: skip
        cover2 = str(await su.fetchval(
            """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
                   created_by_kind, created_by_code, kind)
               VALUES ($1, 'cover-2.jpg', 'image/jpeg', 1, $2, gen_random_uuid()::text, 'agent',
                       'x', 'image') RETURNING id""",
            co["id"], "a" * 64,
        ))  # fmt: skip
        assert await WSX.fresh_files(tx, w, [cover2, cap]) == [cap]


async def test_a_turn_without_a_question_is_followed_at_once_while_the_plan_is_open(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ F-0018 sat idle 13 minutes after a turn that ended «فعلاً کاری با شما نیست»:
    the next turn now starts at once while the plan has open tasks, at most CONTINUE_MAX times
    since the owner's last word; a turn that asked him waits for him."""
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    r = await client.post(
        f"/internal/v1/orders/{o['ref']}/ack",
        headers=await agent_headers(o["holder"]),
        json={"plan_fa": "دو قدم", "steps": ["صدا", "ویدیو"]},
    )
    assert r.status_code == 200, r.text
    # the agent's own token holds a run of its own: ended, as its run would end
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() "
        "WHERE employee_id = $1 AND state = 'running'",
        o["emp"]["id"],
    )
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    await end_run(su, run, note)
    job = await take(client, rn)
    await result(
        client, rn, job["id"], "صدا را ساختم؛ نوبت بعد کنترلش میکنم. فعلاً کاری با شما نیست."
    )
    nxt = await su.fetchrow(
        "SELECT reason FROM agents.runs WHERE work_id = $1 AND state = 'queued'", o["work_id"]
    )
    assert nxt is not None and nxt["reason"] == f"{DR.CONTINUE_REASON}{o['ref']}"
    assert "قدم بعد برنامه" in DR.why_fa(nxt["reason"])
    # capped: once CONTINUE_MAX turns went on by themselves since his last word, none more
    async with hub.db.tx(await hub.companies.ids()) as tx:
        from hq_api.domain import work as W

        rep = await tx.first("SELECT * FROM owner.order_reports WHERE ref = :r", r=o["ref"])
        w = await W.load(tx, o["work_id"])
        went = await tx.scalar(
            "SELECT count(*) FROM agents.runs WHERE work_id = :w AND reason = :r",
            w=o["work_id"], r=f"{DR.CONTINUE_REASON}{o['ref']}",
        )  # fmt: skip
        assert went == 1
        monkeypatch.setattr(DR, "CONTINUE_MAX", 1)
        assert await DR.go_on(tx, dict(rep), w, o["ref"]) is False


async def test_in_a_direct_session_a_word_with_a_question_mark_reaches_the_holder(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ F-0018: the owner's «این ویدیو نهاییه؟ … هر کلمه … موشنگرافی بشه» was read as a
    question: no step, nobody woken. With the workshop holding direct turns, it is his word."""
    from hq_api.domain import order_turns as OT

    co = (await new_company())["code"]
    await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    await su.execute(
        "UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now() "
        "WHERE work_id = $1 AND state IN ('queued', 'running')",
        o["work_id"],
    )
    words_ = "این ویدیو نهاییه؟ قراره هر جمله موشنگرافی بشه."
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await OT.owner_word(tx, o["ref"], words_, work_mode=True)
    assert out["replied"] is True and out["woken"] == [o["work_ref"]]
    rep = (await client.get(f"/api/v1/orders/{o['ref']}/report", headers=owner)).json()
    assert any(s["who_fa"] == "مدیر کل" and "موشنگرافی" in s["what_fa"] for s in rep["steps"])


def test_a_later_turn_carries_only_what_moves() -> None:
    """⟨2026-11-13 usage audit⟩ F-0018's later briefs re-sent the whole state (27 tasks, 24 done;
    one output title 20 times) and the 9000-character cut fell before `waiting_on`. A later turn
    of the same Claude session gets the open tasks and what moves; the first one the whole state,
    its outputs once each."""
    w = {"ref": "W-000123", "title": "ریلز ATR"}
    emp = {"code": "PC-MED-MGR", "title_fa": "مدیر رسانه", "company": "PC",
           "company_name_fa": "پروچارت"}  # fmt: skip
    plan = [
        {"n": n, "title": f"قدم {n}", "state": "done" if n < 25 else "todo"} for n in range(1, 28)
    ]
    brief = {"order": "F-0018", "text": "ریلز روزانه", "plan": plan, "plan_next": 25,
             "outputs": ["خروجی جلسه: نوت‌برداری"] * 20, "files": ["font.zip", "3934.mp4"],
             "playbooks": [{"ref": "PB-1"}], "related_sessions": [{"ref": "F-0017"}],
             "steps": ["مدیر کل: شروع کن"], "waiting_on": [{"kind": "work", "ref": "W-000415"}],
             "owner_said": ["شروع کن"]}  # fmt: skip

    class Charter:
        body = "You direct the company's media."

    first = DR.compose(w, emp, brief, charter=Charter(), tools=["order.ask"],
                       reason="owner_reply:F-0018", first=True, inputs=[])  # fmt: skip
    assert first.count("خروجی جلسه: نوت‌برداری") == 1 and "font.zip" in first
    assert '"n": 1,' in first and "W-000415" in first
    later = DR.compose(w, emp, brief, charter=Charter(), tools=["order.ask"],
                       reason="owner_reply:F-0018", first=False, inputs=[])  # fmt: skip
    for gone in ("خروجی جلسه", "font.zip", "PB-1", "F-0017", '"n": 1,'):
        assert gone not in later, gone
    state = DR.state_of(brief, first=False)
    assert [t["n"] for t in state["plan"]] == [25, 26, 27] and state["plan_done"] == 24
    assert state["waiting_on"] and state["steps"] and state["plan_next"] == 25
    assert len(later) < len(first) // 2
    assert "ToolSearch" in first and "۶ هزار" in first  # the step and notebook rules


async def test_a_session_whose_account_is_full_starts_afresh_on_the_other_one(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13 usage audit⟩ A prompt cache is one account's: on F-0018 the move to the second
    account rewrote 717K and 678K tokens of two sessions at the write price. A session carrying
    more than ROTATE_ON_SWITCH_TOKENS whose account is full while the other has room starts
    afresh. And a resumed session's turn is booked at what it added to the CLI's running total."""
    import uuid

    from hq_api.domain import session_memory as MEM

    from .test_w13_second_account import _quota

    keys = ["claude-max", "claude-max-2"]
    before = await su.fetch("SELECT key, status FROM llm.connections WHERE key = ANY($1)", keys)
    saved = await su.fetch(
        """SELECT q.* FROM llm.quota_status q JOIN llm.connections c ON c.id = q.connection_id
           WHERE c.key = ANY($1)""",
        keys,
    )
    clear = """DELETE FROM llm.quota_status
               WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))"""
    on_main = """UPDATE infra.server_jobs
                 SET usage = usage || '{"account": "claude-max"}'::jsonb WHERE id = $1"""
    caught: list[str] = []

    async def catch_up(hub_: Any, call: Any, ref: str) -> int:
        caught.append(ref)
        return 1

    monkeypatch.setattr(MEM, "catch_up", catch_up)
    cli = f"cs-{uuid.uuid4()}"
    try:
        await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = ANY($1)", keys)
        await su.execute(clear, keys)
        co = (await new_company())["code"]
        rn = await workshop(client, hub, owner_session, su, version="0.3.5")
        o = await an_order(client, owner, su, co)
        run = await queued_run(su, o)
        note = await DR.hand_over(hub, run, o["emp"])
        await end_run(su, run, note)
        job = await take(client, rn)
        await result(client, rn, job["id"], "اولین نوبت تمام شد.",
                     usage={"cache_write_tokens": 40_000, "session_id": cli, "cost_usd": 1.5,
                            "model": "claude-opus-5-5"})  # fmt: skip
        await su.execute(on_main, uuid.UUID(job["id"]))
        # the main account full, the second one with room: a light session still goes on
        await _quota(su, "claude-max", "limited", "1", "1 day")
        assert not await DR.rotate_if_heavy(hub, o["work_id"])
        await su.execute(clear, keys)
        run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
        note = await DR.hand_over(hub, run, o["emp"])
        await end_run(su, run, note)
        second = await take(client, rn)
        assert second["args"].get("resume")
        await result(client, rn, second["id"], "دومین نوبت تمام شد.",
                     usage={"cache_write_tokens": 50_000, "session_id": cli, "cost_usd": 4.0,
                            "model": "claude-opus-5-5"})  # fmt: skip
        await su.execute(on_main, uuid.UUID(second["id"]))
        booked = await su.fetchval(
            "SELECT equiv_cost_usd FROM llm.calls WHERE meta ->> 'server_job' = $1", second["id"]
        )
        assert float(booked) == pytest.approx(2.5)  # 4.0 is the session's running total
        # 90K carried, its account has room: it goes on
        assert not await DR.rotate_if_heavy(hub, o["work_id"])
        # its account is full and the other has room: a fresh session on the other account
        await _quota(su, "claude-max", "limited", "1", "1 day")
        assert await DR.rotate_if_heavy(hub, o["work_id"])
        assert caught == [o["ref"]]
    finally:
        await su.execute(clear, keys)
        for r in saved:
            cols = list(r.keys())
            await su.execute(
                f"INSERT INTO llm.quota_status ({', '.join(cols)}) VALUES "
                f"({', '.join(f'${i + 1}' for i in range(len(cols)))})",
                *[r[c] for c in cols],
            )
        for r in before:
            await su.execute(
                "UPDATE llm.connections SET status = $2 WHERE key = $1", r["key"], r["status"]
            )
