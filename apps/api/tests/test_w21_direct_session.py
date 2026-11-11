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

from .conftest import idem
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
    assert a["model"] == "claude-opus-5-5" and a["effort"] == "max" and a["sandbox"] == "auto"
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
    assert len(working) == 1 and "دارد روی فرمان شما کار میکند" in working[0]["doing_fa"]
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
    assert made["title"].startswith("خروجی جلسه: ") and pw["direct"] is True
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
