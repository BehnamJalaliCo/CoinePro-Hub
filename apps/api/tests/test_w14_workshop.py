"""⟨2026-11-09⟩ The workshop: hands for any task (contract §43, docs/WORKSHOP_HANDS.md).

The owner: «اپ وسیله‌ی ارتباط است؛ سرور کامپیوتر است». Any working role of any company hands a task
with no tool of its own to Claude Code on the holding's workshop server (`workshop.run`); the
turn's `out/` files come back as attachments of an output of that work. The holding's runner is
simulated through the real runner routes (pairing, long-poll, files, result), as in
test_p17_runners; the policy is the real OPA.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from PIL import Image

from hq_api.domain import hands as HANDS
from hq_api.domain import workspace as WS
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p17_runners import RUNNER_HEADERS, pair, poll, take

API = "/api/v1"


async def workshop(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], su: Any, version: str = "0.3.2"
) -> dict[str, Any]:
    """The holding's workshop paired (any earlier one of the test database revoked first)."""
    holding = await hub.companies.holding()
    await su.execute(
        """UPDATE infra.servers SET state = 'revoked'
           WHERE company_id = $1 AND state IS DISTINCT FROM 'revoked'""",
        holding.id,
    )
    rn = await pair(client, hub, owner, {"code": holding.code, "id": holding.id}, "workshop")
    rn["h"] = {**rn["h"], "X-HQ-Runner-Version": version}
    r = await poll(client, rn)  # stores the version
    assert r.status_code in (200, 204), r.text
    return rn


async def run_ask(
    client: httpx.AsyncClient, who: str, body: dict[str, Any], key: str | None = None
) -> httpx.Response:
    return await client.post(
        "/internal/v1/workshop/runs",
        headers={**(await agent_headers(who)), "Idempotency-Key": key or str(uuid.uuid4())},
        json=body,
    )


def png(color: tuple[int, int, int] = (12, 80, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buf, format="PNG")
    return buf.getvalue()


async def send_file(
    client: httpx.AsyncClient, rn: dict[str, Any], job: str, name: str, ctype: str, data: bytes
) -> httpx.Response:
    return await client.post(
        f"{API}/runners/jobs/{job}/files",
        content=data,
        headers={**rn["h"], "Content-Type": ctype, "X-File-Name": name},
    )


async def refuse_queued(su: Any, work_id: str) -> None:
    """The work's queued runs end (no worker here): the next wake is a run of its own."""
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        uuid.UUID(work_id),
    )


async def a_work(client: httpx.AsyncClient, h: dict[str, str], co: str) -> dict[str, Any]:
    r = await client.post(
        f"{API}/work",
        headers={**h, **idem()},
        json={"company": co, "title": "موشن‌گرافی اندیکاتور ATR", "brief": "x", "priority": "P2"},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_any_role_hands_a_task_to_the_workshop_and_its_files_come_back(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    w = await a_work(client, h, co["code"])
    who = await su.fetchval(
        """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.id = $1""",
        uuid.UUID(w["id"]),
    )
    holding = await hub.companies.holding()
    await su.execute("UPDATE infra.servers SET state = 'revoked' WHERE company_id = $1", holding.id)

    # No workshop paired yet: said plainly, nothing made.
    r = await run_ask(client, who, {"brief": "یک موشن‌گرافی ۳۰ ثانیه‌ای بساز", "work": w["ref"]})
    assert r.status_code == 409 and r.json()["code"] == "workshop_unavailable", r.text
    assert "کارگاه" in r.json()["message_fa"]

    # The holding pairs its workshop (the owner seals it as any server); an old runner is not it.
    rn = await workshop(client, hub, owner_session, su, version="0.3.1")
    r = await run_ask(client, who, {"brief": "x", "work": w["ref"]})
    assert r.status_code == 409 and r.json()["code"] == "workshop_unavailable"
    rn = await workshop(client, hub, owner_session, su)
    assert rn["server"]["company"] == holding.code

    # A run without a work item names one; a work of someone else is refused.
    r = await run_ask(client, who, {"brief": "x"})
    assert r.status_code == 422 and "work" in r.json()["fields"], r.text
    other = await a_work(client, h, (await new_company())["code"])
    r = await run_ask(client, who, {"brief": "x", "work": other["ref"]})
    assert r.status_code == 403, r.text

    # The ask: a turn on the workshop for the agent's own work, in the work's folder.
    key = str(uuid.uuid4())
    ask = {"brief": "موشن‌گرافی ATR، ۱۰۸۰x۱۹۲۰، فونت IRANYekanX", "title": "ATR", "work": w["ref"]}
    r = await run_ask(client, who, ask, key)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["state"] == "starting" and out["turn"] == 1 and out["work_ref"] == w["ref"]
    assert out["server"] == "workshop" and out["path"] == f"~/hq-workspace/{w['ref']}"
    again = await run_ask(client, who, ask, key)  # the same key: the same answer
    assert again.status_code == 201 and again.json() == out
    job = await take(client, rn)
    assert job["id"] == out["job"] and job["kind"] == "claude"
    args = job["args"]
    assert args["hands"] is True and args["workspace"] == w["ref"]
    assert args["model"] == HANDS.MODEL and args["permission_mode"] == "acceptEdits"
    assert "Bash" in args["allowed_tools"] and "token_cap" not in args
    assert args["timeout_s"] == HANDS.SESSION_TIMEOUT_S < HANDS.TURN_TIMEOUT_S
    assert "out/" in args["brief"] and "IRANYekanX" in args["brief"] and w["ref"] in args["brief"]
    assert job["actor"]["code"] == who and job["timeout_s"] == HANDS.TURN_TIMEOUT_S
    # While it runs, another ask starts nothing new.
    r = await run_ask(client, who, {"brief": "یک چیز دیگر", "work": w["ref"]})
    assert r.status_code == 200 and r.json()["state"] == "working" and r.json()["job"] == job["id"]

    # The turn sends its out/ files while it runs: they belong to the work's company.
    r = await send_file(client, rn, job["id"], "cover.png", "image/png", png())
    assert r.status_code == 201, r.text
    cover = r.json()
    r = await send_file(client, rn, job["id"], "cover.png", "image/png", png())
    assert r.status_code == 201 and r.json()["id"] == cover["id"]  # the same bytes: the same file
    r = await send_file(
        client, rn, job["id"], "%D9%85%D8%AA%D9%86.md", "text/markdown", "# ATR\nمتن".encode()
    )
    assert r.status_code == 201, r.text
    notes = r.json()
    assert notes["name"] == "متن.md"
    r = await send_file(client, rn, job["id"], "x.sh", "application/x-sh", b"#!/bin/sh\n")
    assert r.status_code == 415, r.text
    row = await su.fetchrow(
        "SELECT company_id, created_by_kind, created_by_code, meta FROM files.files WHERE id = $1",
        uuid.UUID(cover["id"]),
    )
    assert row["company_id"] == co["id"] and row["created_by_kind"] == "agent"
    assert row["created_by_code"] == who and '"job"' in row["meta"]

    # The turn ends: its answer and its files are an output of the work, which stays open (the
    # order itself), and its holder gets a run to show the owner.
    bogus = str(uuid.uuid4())
    await refuse_queued(su, w["id"])
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={
            "exit_code": 0,
            "summary_fa": "نشست Claude روی سرور تمام شد. 2 فایل از out/ به ستاد رفت.",
            "usage": {"input_tokens": 1200, "output_tokens": 300, "model": HANDS.MODEL},
            "data": {
                "session_id": "cs-hands-1",
                "result_fa": "## ساخته شد\nکاور و متن آماده است.",
                "workspace": {"ref": w["ref"], "path": "/home/studio/hq-workspace/" + w["ref"]},
                "files": [cover["id"], notes["id"], bogus],
            },
        },
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    dl = await su.fetchrow(
        """SELECT ref, attachments, produced_with FROM cartable.deliverables
           WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1""",
        uuid.UUID(w["id"]),
    )
    assert dl is not None and sorted(str(a) for a in dl["attachments"]) == sorted(
        [cover["id"], notes["id"]]
    )  # the bogus id dropped
    assert '"workshop"' in dl["produced_with"]
    detail = (await client.get(f"{API}/work/{w['id']}", headers=h)).json()
    assert detail["status"] not in ("delivered", "done") and dl["ref"] in detail["deliverable_refs"]
    reason = await su.fetchval(
        "SELECT reason FROM agents.runs WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1",
        uuid.UUID(w["id"]),
    )
    assert reason == f"workshop_done:{w['ref']}"
    ws = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert ws["state"] == "idle" and ws["turns"] == 1
    async with hub.db.tx(await hub.companies.ids()) as tx:
        prog = await WS.progress(tx, [uuid.UUID(w["id"])])
    assert prog[0].where_fa == WS.WORKSHOP_FA
    # the owner opens and downloads it
    r = await client.get(f"{API}/files/{cover['id']}", headers=h)
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"

    # A fix is the next ask on the same work: the same session and folder, a resume.
    r = await run_ask(client, who, {"brief": "رنگ‌ها تیره‌تر", "work": w["ref"]})
    assert r.status_code == 201 and r.json()["turn"] == 2, r.text
    nxt = await take(client, rn)
    assert nxt["args"]["workspace"] == w["ref"] and nxt["args"]["hands"] is True
    assert nxt["args"]["resume"] == "cs-hands-1" and "رنگ‌ها تیره‌تر" in nxt["args"]["brief"]

    # Past its time the turn stops, and the holder is woken with the reason; never silent. What
    # it had left in out/ (sent by the runner at the time limit) comes as an unfinished output.
    r = await send_file(client, rn, nxt["id"], "half.png", "image/png", png((200, 40, 40)))
    assert r.status_code == 201, r.text
    half = r.json()
    await refuse_queued(su, w["id"])
    r = await client.post(
        f"{API}/runners/jobs/{nxt['id']}/result",
        json={
            "exit_code": 124,
            "summary_fa": "نشست Claude به سقف زمان رسید و متوقف شد. 1 فایل از out/ به ستاد رفت.",
            "data": {
                "workspace": {"ref": w["ref"], "path": "/home/studio/hq-workspace/" + w["ref"]},
                "files": [half["id"]],
                "sandbox": {"state": "on", "kind": "landlock"},
            },
        },
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    failed = await su.fetchrow(
        "SELECT state, result FROM infra.server_jobs WHERE id = $1", uuid.UUID(nxt["id"])
    )
    assert failed["state"] == "failed" and half["id"] in failed["result"]
    dl = await su.fetchrow(
        """SELECT title, attachments, produced_with FROM cartable.deliverables
           WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1""",
        uuid.UUID(w["id"]),
    )
    assert dl is not None and dl["title"].startswith("خروجی ناتمام کارگاه")
    assert [str(a) for a in dl["attachments"]] == [half["id"]]
    assert '"unfinished": true' in dl["produced_with"]
    ws = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert ws["state"] == "failed" and "سقف زمان" in ws["note_fa"]
    reason = await su.fetchval(
        "SELECT reason FROM agents.runs WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1",
        uuid.UUID(w["id"]),
    )
    assert reason == f"workspace_failed:{w['ref']}"
    note = await su.fetchval(
        """SELECT data->>'note_fa' FROM work.work_events WHERE work_id = $1
             AND kind = 'workspace_failed' ORDER BY at DESC LIMIT 1""",
        uuid.UUID(w["id"]),
    )
    assert note and "سقف زمان" in note
    # and the next ask starts a fresh session in the same folder
    r = await run_ask(client, who, {"brief": "دوباره، کوتاه‌تر", "work": w["ref"]})
    assert r.status_code == 201 and r.json()["turn"] == 3, r.text
    fresh = await take(client, rn)
    assert fresh["args"]["resume"] is None and fresh["args"]["workspace"] == w["ref"]
    assert fresh["session_ref"] != nxt["session_ref"]

    # Every call is on both companies' trails.
    trails = await su.fetch(
        "SELECT company_id FROM audit.entries WHERE action = 'workshop.run' AND target_ref = $1",
        w["ref"],
    )
    assert {t["company_id"] for t in trails} == {co["id"], holding.id}

    # Hands only: a company's agent cannot run a command on the workshop.
    r = await client.post(
        "/internal/v1/servers/jobs",
        headers={**(await agent_headers(who)), **idem()},
        json={"kind": "exec", "server": "workshop", "company": holding.code,
              "args": {"cmd": "id"}},
    )  # fmt: skip
    assert r.status_code == 403, r.text

    await su.execute("UPDATE infra.servers SET state = 'revoked' WHERE company_id = $1", holding.id)


async def test_a_turn_of_a_child_that_took_all_its_parents_budget_still_delivers(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """A working group's reel: a child delegated without a figure (it took all its capped
    parent had left) runs a workshop turn. The turn's tokens grow the child's budget and its
    parent's (the root first), and booking them never costs the turn's output (HQB01)."""
    from hq_api.domain import work as W

    co = await new_company()
    who = f"{co['code']}-TECH-MGR"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        parent = await W.create(
            tx, WS.SERVICE, company_id=co["id"], company_code=co["code"], title="برنامه‌ی محتوا",
            brief="x", kind="one_off", priority="P3", assignee_code=who,
            budget=W.BudgetIn(tokens=100_000),
        )  # fmt: skip
        child = await W.create(
            tx, WS.SERVICE, company_id=co["id"], company_code=co["code"], title="ریل ATR",
            brief="x", kind="one_off", priority="P3", assignee_code=who, parent=parent,
        )  # fmt: skip
    budgets = "SELECT budget_tokens FROM work.work WHERE id = $1"
    assert await su.fetchval(budgets, child["id"]) == 100_000  # all its parent had left
    rn = await workshop(client, hub, owner_session, su)
    r = await run_ask(client, who, {"brief": "یک ریل ۱۵ ثانیه‌ای بساز", "work": child["ref"]})
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    await refuse_queued(su, str(child["id"]))
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={
            "exit_code": 0,
            "summary_fa": "نشست Claude روی سرور تمام شد.",
            "usage": {"input_tokens": 40_000, "output_tokens": 9_000, "model": HANDS.MODEL},
            "data": {"session_id": "cs-hands-reel", "result_fa": "ریل آماده است."},
        },
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    used = await su.fetchval("SELECT tokens_used FROM work.work WHERE id = $1", child["id"])
    assert used > 0
    assert await su.fetchval(budgets, child["id"]) == 100_000 + used
    assert await su.fetchval(budgets, parent["id"]) == 100_000 + used
    assert await su.fetchval(
        "SELECT count(*) FROM cartable.deliverables WHERE work_id = $1", child["id"]
    ) == 1  # fmt: skip
    ws = await su.fetchrow("SELECT state FROM work.workspaces WHERE work_id = $1", child["id"])
    assert ws["state"] == "delivered"
    await refuse_queued(su, str(parent["id"]))
    await su.execute("UPDATE infra.servers SET state = 'revoked' WHERE company_id = $1",
                     (await hub.companies.holding()).id)  # fmt: skip


async def test_a_file_only_comes_from_a_workspace_turn_of_that_server(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "app-1")
    rn["h"] = {**rn["h"], **RUNNER_HEADERS, "X-HQ-Runner-Version": "0.3.2"}
    # an owner's map job is not a workspace turn
    r = await client.post(
        f"{API}/infra/servers/{rn['server']['id']}/map",
        headers={**owner_session["headers"], **idem()},
    )
    assert r.status_code in (200, 202), r.text
    job = await take(client, rn)
    r = await send_file(client, rn, job["id"], "x.png", "image/png", png())
    assert r.status_code == 422, r.text
    # an unknown job of another server
    r = await send_file(client, rn, str(uuid.uuid4()), "x.png", "image/png", png())
    assert r.status_code == 404, r.text


async def test_a_step_order_starts_only_its_next_task_and_the_holder_can_stop_the_turn(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """⟨2026-11-10⟩ the owner's recording of 2026-11-09 («با من»): the holder sent «ساخت ریلز» to
    the workshop two steps before the owner's script and voice, then answered «نمیتوانم بگویم آن
    سفارش متوقف شده است، چون این کار در دست من نیست». In a step-by-step order the workshop takes
    only the plan's next open task, the holder can stop its own turn, and a turn that runs is
    someone working (the session is not «گیر کرد» while the workshop builds)."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import servers as SV
    from hq_api.domain import session_activity as SA

    from .test_p21_secretary import post_order, words

    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="step"
    )
    ref = out["ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)

    # no plan yet: nothing to be out of order with
    r = await client.post(
        f"/api/v1/orders/{ref}/reply",
        headers={**owner, **idem()},
        json={"text": "۱ - متن گفتار آماده بشه\n۲ - صدا ساخته بشه\n۳ - ریلز ساخته بشه"},
    )
    assert r.status_code == 200, r.text

    # the reel is task 3: not before the script and the voice
    r = await run_ask(client, holder, {"work": work_ref, "brief": "ریلز بی‌صدا بساز"})
    assert r.status_code == 409 and r.json()["code"] == "not_next_step", r.text
    assert "1" in r.json()["fields"]["task"] and "متن گفتار" in r.json()["fields"]["task"]
    r = await run_ask(client, holder, {"work": work_ref, "brief": "ریلز بی‌صدا بساز", "task": 3})
    assert r.status_code == 409 and r.json()["code"] == "not_next_step", r.text
    assert await su.fetchval("SELECT count(*) FROM work.workspaces WHERE work_id = $1", wid) == 0
    r = await run_ask(
        client, holder, {"work": work_ref, "brief": "متن گفتار ۹۰ ثانیه‌ای بنویس", "task": 1}
    )
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    assert job["id"] == r.json()["job"]

    # while the turn runs, the session has someone working: the workshop (the holder's own run
    # ended when it handed the task over)
    await refuse_queued(su, str(wid))
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rep = await OR.ensure(tx, ref)
        works = await OR.tree(tx, OR.root_refs(await OR.load_order(tx, ref) or {}))
        pulse = await SA.read_pulse(tx, rep, works, minutes=0)
        act = await SA.activity(tx, rep, works, pulse=pulse)
        n = await SA.working_count(tx, ref)
    assert pulse.live and pulse.stuck_fa is None and pulse.doing_fa == SA.TURN_DOING_FA
    assert n >= 1 and any(w.who_fa == SA.WORKSHOP_WHO_FA for w in act.working), act.working

    # the holder stops the turn it started (its run's work; no ref needed with `work`)
    stop = await client.post(
        "/internal/v1/workshop/stop",
        headers=await agent_headers(holder),
        json={"work": work_ref, "reason": "مالک گفت اشتباه بود"},
    )
    assert stop.status_code == 200 and stop.json()["stopped"] is True, stop.text
    assert stop.json()["job"] == job["id"] and stop.json()["work_ref"] == work_ref
    st = await su.fetchrow(
        "SELECT state, error_code, summary_fa FROM infra.server_jobs WHERE id = $1",
        uuid.UUID(job["id"]),
    )
    assert st["state"] == "cancelled" and st["error_code"] == "workshop_stopped"
    assert "مالک گفت اشتباه بود" in st["summary_fa"]
    ws = await su.fetchrow("SELECT state FROM work.workspaces WHERE work_id = $1", wid)
    assert ws["state"] == "idle"
    r = await poll(client, rn)  # the runner is told to kill it
    assert r.status_code == 200 and job["id"] in r.json()["cancels"], r.text
    again = await client.post(
        "/internal/v1/workshop/stop", headers=await agent_headers(holder), json={"work": work_ref}
    )
    assert again.status_code == 200 and again.json()["stopped"] is False
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert not (await SA.live_turns(tx, [wid]))

    # the same task again starts a fresh session in the same folder
    r = await run_ask(
        client, holder, {"work": work_ref, "brief": "متن گفتار، این بار کوتاه‌تر", "task": 1}
    )
    assert r.status_code == 201 and r.json()["turn"] == 2, r.text
    nxt = await take(client, rn)
    assert nxt["args"]["hands"] is True and nxt["args"]["workspace"] == work_ref

    # past its hour with no word from the runner: the sweep fails it AND the turn ends as any
    # other (the workspace marked, the holder woken with the reason), never a silent stall
    await su.execute(
        "UPDATE infra.server_jobs SET dispatched_at = now() - interval '3 hours' WHERE id = $1",
        uuid.UUID(nxt["id"]),
    )
    await refuse_queued(su, str(wid))
    ended: list[uuid.UUID] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await SV.sweep(tx, ended=ended)
    assert uuid.UUID(nxt["id"]) in ended
    for jid in ended:
        await WS.after_job(hub, jid)
    ws = await su.fetchrow("SELECT state FROM work.workspaces WHERE work_id = $1", wid)
    assert ws["state"] == "failed"
    reason = await su.fetchval(
        "SELECT reason FROM agents.runs WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1", wid
    )
    assert reason == f"workspace_failed:{work_ref}"

    # the kill switch of the work's own company stops (and holds) its workshop turn
    r = await run_ask(client, holder, {"work": work_ref, "brief": "متن گفتار", "task": 1})
    assert r.status_code == 201, r.text
    held = r.json()["job"]
    from hq_api.domain import control
    from hq_api.principal import Principal

    async with hub.db.tx(await hub.companies.ids()) as tx:
        company = await control.resolve_scope(tx, f"company:{co}")
        await control.set_kill_switch(
            tx, Principal(kind="owner", code="owner", role="owner"), company, "engaged", "test"
        )
    st = await su.fetchrow(
        "SELECT state, error_code FROM infra.server_jobs WHERE id = $1", uuid.UUID(held)
    )
    assert (st["state"], st["error_code"]) == ("cancelled", "company_locked")
    r = await run_ask(client, holder, {"work": work_ref, "brief": "متن گفتار", "task": 1})
    assert r.status_code == 423, r.text
