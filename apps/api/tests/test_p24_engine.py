"""Prompt 24 (contract §33.7, §33.10): agents in parallel and the company workspace.

The parts are split through the real internal route (the policy is the real OPA); a runner on 0.3.0
is simulated through the real runner routes (pairing, long-poll, result), as in test_p17_runners.
A run's hand-over to the server is called the way the agents' runner calls it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import split as SP
from hq_api.domain import workspace as WS
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p17_runners import pair, poll, take

API = "/api/v1"


def part(title: str, role: str, brief: str = "بررسی کامل و گزارش با شواهد") -> SP.SplitPartIn:
    return SP.SplitPartIn(title_fa=title, role=role, brief=brief)


# ------------------------------------------------------------------ units --
def test_the_parallel_limits_are_data() -> None:
    conf = SP.settings()
    assert conf["max"] == SP.parallel_max() == 3 and conf["min"] == 2
    assert conf["workspace"] == {"runner_min": "0.3.0", "keep_days": 30, "turn_timeout_s": 3600}


@pytest.mark.parametrize(
    ("parts", "dependent"),
    [
        ([part("سرعت سایت", "TECH"), part("محتوای سئو", "GROWTH")], None),
        ([part("سرعت سایت", "TECH"), part("محتوا", "GROWTH", "از خروجی بخش ۱ استفاده کن")], 2),
        ([part("a speed check", "TECH"), part("b", "GROWTH", "use the result of part 1")], 2),
        ([part("سرعت سایت", "TECH", "بعد از بخش اول"), part("محتوا", "GROWTH")], 1),
        (
            [
                part("گزارش رقبای بازار", "TECH"),
                part("x", "GROWTH", "گزارش رقبای بازار را خلاصه کن"),
            ],
            2,
        ),
        ([part("سرعت", "TECH"), part("محتوا", "GROWTH", "با بخش‌های دیگر هماهنگ کن")], 2),
        ([part("یکی", "TECH"), part("یکی", "GROWTH")], 1),
    ],
)
def test_parts_that_use_each_other_are_refused(
    parts: list[SP.SplitPartIn], dependent: int | None
) -> None:
    got = SP.dependency(parts)
    assert (got[0] if got else None) == dependent


def test_version_and_the_brief() -> None:
    assert WS.version_ok("0.3.0", "0.3.0") and WS.version_ok("0.10.1", "0.3.0")
    assert not WS.version_ok("0.2.9", "0.3.0") and not WS.version_ok(None, "0.3.0")
    w = {"ref": "W-000123", "title": "رفع خطا", "brief": "تست‌ها را درست کن", "progress_note": None}
    first = WS.compose(w, {"trigger": "work", "reason": "work:W-000123"}, True, None)
    assert "~/hq-workspace/W-000123" in first and "تست‌ها را درست کن" in first
    again = WS.compose(w, {"trigger": "work", "reason": "resume:W-000123"}, False, None)
    assert "ادامه" in again and "resume:W-000123" in again


# -------------------------------------------------------------- the split --
async def root_work(
    client: httpx.AsyncClient, h: dict[str, str], co: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        f"{API}/work",
        headers={**h, **idem()},
        json={"company": co, "title": "بررسی کامل سایت", "brief": "x", "priority": "P2", **extra},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def split(
    client: httpx.AsyncClient, wid: str, who: str, parts: list[dict[str, str]]
) -> httpx.Response:
    return await client.post(
        f"/internal/v1/work/{wid}/split",
        headers={**(await agent_headers(who)), **idem()},
        json={"parts": parts},
    )


async def test_a_ceo_splits_into_parallel_parts_and_merges_once(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    root = await root_work(client, h, co, budget={"tokens": 400000})
    ceo = f"{co}-CEO"
    parts = [
        {"title_fa": "سرعت و پایداری سایت", "role": "TECH", "brief": "سرعت صفحه‌ها را بسنج"},
        {"title_fa": "سئو و محتوای سایت", "role": "GROWTH", "brief": "صفحه‌های مهم را بررسی کن"},
    ]
    # Refusals first: not the assignee, too many parts, parts that depend, a part a CEO may not
    # hand to an employee, one part only.
    r = await split(client, root["id"], f"{co}-TECH-MGR", parts)
    assert r.status_code == 403 and r.json()["code"] == "policy_denied", r.text
    four = [*parts, {**parts[0], "title_fa": "سه", "role": "SALES"}]
    four.append({**parts[0], "title_fa": "چهار", "role": "FIN"})
    r = await split(client, root["id"], ceo, four)
    assert r.status_code == 422 and "parts" in r.json()["fields"], r.text
    dep = [parts[0], {**parts[1], "brief": "از نتیجه‌ی بخش ۱ استفاده کن"}]
    r = await split(client, root["id"], ceo, dep)
    assert r.status_code == 422 and "parts.1" in r.json()["fields"], r.text
    assert "وابسته" in r.json()["message_fa"]
    emp = await su.fetchval(
        "SELECT code FROM core.employees WHERE code LIKE $1 AND kind = 'employee' LIMIT 1",
        f"{co}-%",
    )
    if emp:
        r = await split(client, root["id"], ceo, [parts[0], {**parts[1], "role": emp}])
        assert r.status_code == 403, r.text
    r = await split(client, root["id"], ceo, [parts[0]])
    assert r.status_code == 422, r.text
    assert not await su.fetchval(
        "SELECT count(*) FROM work.work WHERE parent_id = $1", uuid.UUID(root["id"])
    )

    # The split: two child works, each with its own run and an equal share of the budget.
    r = await split(client, root["id"], ceo, parts)
    assert r.status_code == 201, r.text
    view = r.json()
    assert view["state"] == "running" and view["proposed_by"] == ceo
    assert [p["assignee"] for p in view["parts"]] == [f"{co}-TECH-MGR", f"{co}-GROWTH-MGR"]
    assert all(p["state"] == "working" for p in view["parts"])
    each = int(400000 * 0.75) // 2
    assert all(p["budget_tokens"] == each for p in view["parts"])
    kids = await su.fetch(
        "SELECT id, ref, depth FROM work.work WHERE parent_id = $1 ORDER BY ref",
        uuid.UUID(root["id"]),
    )
    assert len(kids) == 2 and all(k["depth"] == 1 for k in kids)
    queued = await su.fetchval(
        "SELECT count(*) FROM agents.runs WHERE work_id = ANY($1::uuid[]) AND state = 'queued'",
        [k["id"] for k in kids],
    )
    assert queued == 2
    parent = (await client.get(f"{API}/work/{root['id']}", headers=h)).json()
    assert parent["status"] == "waiting"
    assert (
        await su.fetchval(
            "SELECT count(*) FROM core.outbox WHERE subject = $1 AND payload->>'ref' = $2",
            f"hq.core.{co}.work.split",
            root["ref"],
        )
        == 1
    )
    r = await split(client, root["id"], ceo, parts)
    assert r.status_code == 409  # one open split per work

    # The first part delivers: the parent's assignee is NOT woken for it alone.
    tech = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(
        f"/internal/v1/work/{kids[0]['id']}/deliver",
        headers={**tech, **idem()},
        json={"title": "گزارش سرعت", "summary": "LCP دو ثانیه", "body": "جزئیات سرعت"},
    )
    assert r.status_code in (200, 201), r.text
    woken = await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE r.work_id = $1 AND e.code = $2 AND r.reason LIKE 'child_delivered:%'""",
        uuid.UUID(root["id"]),
        ceo,
    )
    assert woken == 0
    got = (await client.get(f"{API}/work/{root['id']}/split", headers=h)).json()
    assert [p["state"] for p in got["parts"]] == ["delivered", "working"]
    assert got["parts"][0]["output_ref"] and got["state"] == "running"

    # The second part fails: every part has ended -> ONE merge run, the failure shown.
    growth = await agent_headers(f"{co}-GROWTH-MGR")
    r = await client.post(
        f"/internal/v1/work/{kids[1]['id']}/fail",
        headers={**growth, **idem()},
        json={"reason": "دسترسی به Search Console نبود"},
    )
    assert r.status_code == 200, r.text
    got = (await client.get(f"{API}/work/{root['id']}/split", headers=h)).json()
    assert got["state"] == "running"  # the api never queues a run: the worker's sweep does
    # (the CEO's first run of the order ran long ago: only the merge may be queued now)
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        uuid.UUID(root["id"]),
    )
    whub = wk["hub"]
    async with whub.db.tx(await whub.companies.ids()) as tx:
        assert await SP.sweep(tx) >= 1
    merge = await su.fetch(
        """SELECT r.reason, r.state FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE r.work_id = $1 AND e.code = $2 AND r.reason LIKE 'split_merge:%'""",
        uuid.UUID(root["id"]),
        ceo,
    )
    assert [m["reason"] for m in merge] == [f"split_merge:{root['ref']}"]
    got = (await client.get(f"{API}/work/{root['id']}/split", headers=h)).json()
    assert got["state"] == "merging" and [p["state"] for p in got["parts"]] == [
        "delivered",
        "failed",
    ]
    assert got["parts"][1]["failed_fa"]
    async with whub.db.tx(await whub.companies.ids()) as tx:
        brief = await SP.merge_brief(tx, uuid.UUID(root["id"]))
        assert brief is not None and "ONE merged deliverable" in brief["instruction"]
        assert brief["parts"][0]["output"]["title"] == "گزارش سرعت"
        assert brief["parts"][1]["state"] == "failed" and brief["parts"][1]["failed"]
        await SP.sweep(tx)  # nothing new: the merge was queued once
    assert (
        await su.fetchval(
            "SELECT count(*) FROM agents.runs WHERE work_id = $1 AND reason LIKE 'split_merge:%'",
            uuid.UUID(root["id"]),
        )
        == 1
    )

    # The merge delivers: the split is done.
    ceo_h = await agent_headers(ceo)
    r = await client.post(
        f"/internal/v1/work/{root['id']}/deliver",
        headers={**ceo_h, **idem()},
        json={"title": "گزارش یکپارچه", "summary": "s", "body": "سرعت خوب؛ سئو ناتمام ماند"},
    )
    assert r.status_code in (200, 201), r.text
    got = (await client.get(f"{API}/work/{root['id']}/split", headers=h)).json()
    assert got["state"] == "done"
    r = await client.get(f"{API}/work/{kids[0]['id']}/split", headers=h)
    assert r.status_code == 404


async def test_a_manager_splits_inside_its_department_only(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    hiring_open: None,
    su: Any,
) -> None:
    from .test_org_work import hire

    h = owner_session["headers"]
    co = (await new_company())["code"]
    first = await hire(hub, client, owner_session, co)
    await hire(hub, client, owner_session, co)
    w = await root_work(client, h, co, department="TECH")
    assert w["assignee"]["code"] == f"{co}-TECH-MGR"
    parts = [  # one by its code, one by its charter role (the least busy holder)
        {"title_fa": "پایش سرویس‌ها", "role": first, "brief": "هشدارها را مرور کن"},
        {"title_fa": "بازبینی پشتیبان‌ها", "role": "sre", "brief": "آخرین پشتیبان را بسنج"},
    ]
    r = await split(client, w["id"], f"{co}-TECH-MGR", parts)
    assert r.status_code == 201, r.text
    got = r.json()["parts"]
    assert got[0]["assignee"] == first and got[1]["assignee"] not in (None, first)
    assert got[0]["budget_tokens"] is None  # no budget: none to share
    r = await split(client, w["id"], f"{co}-TECH-MGR", [parts[0], {**parts[1], "role": "nobody_x"}])
    assert r.status_code in (409, 422)
    other = [parts[0], {**parts[1], "title_fa": "دیگر", "role": "GROWTH"}]
    w2 = await root_work(client, h, co, department="TECH")
    r = await split(client, w2["id"], f"{co}-TECH-MGR", other)
    assert r.status_code == 403, r.text  # a manager hands work to its own department only


# ------------------------------------------------------------ the workspace --
async def paired_on(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], co: dict[str, Any],
    version: str,
) -> dict[str, Any]:  # fmt: skip
    rn = await pair(client, hub, owner_session, co, "app-1")
    rn["h"] = {**rn["h"], "X-HQ-Runner-Version": version}
    r = await poll(client, rn)  # the poll stores the version
    assert r.status_code in (200, 204), r.text
    return rn


async def queued_run(su: Any, work_id: str, reason: str = "work") -> dict[str, Any]:
    row = await su.fetchrow(
        """SELECT r.id, r.work_id, r.trigger, r.reason, e.code FROM agents.runs r
           JOIN core.employees e ON e.id = r.employee_id
           WHERE r.work_id = $1 ORDER BY r.created_at DESC LIMIT 1""",
        uuid.UUID(work_id),
    )
    assert row is not None
    return {"id": row["id"], "work_id": row["work_id"], "trigger": row["trigger"],
            "reason": reason if reason != "work" else row["reason"], "code": row["code"]}  # fmt: skip


async def test_an_on_server_work_runs_in_its_workspace_until_delivered(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    rn = await paired_on(client, hub, owner_session, co, "0.3.0")
    w = await root_work(client, h, co["code"], mode="on_server")
    assert w["mode"] == "on_server"
    run = await queued_run(su, w["id"])

    # The run hands its turn to the server's Claude: a `claude` job in the work's own folder.
    note = await WS.hand_over(hub, run, {"code": run["code"]})
    assert note and "turn 1" in note
    job = await take(client, rn)
    assert job["kind"] == "claude" and job["args"]["workspace"] == w["ref"]
    assert job["args"]["resume"] is None and w["title"] in job["args"]["brief"]
    assert job["actor"]["code"] == run["code"]
    # A turn still running: another run of the work starts nothing new.
    again = await WS.hand_over(hub, run, {"code": run["code"]})
    assert again and "still" in again
    r = await poll(client, rn)
    assert r.status_code == 204 or r.json().get("job") is None

    rep = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert rep["state"] == "starting" and rep["turns"] == 1 and rep["session_id"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        prog = await WS.progress(tx, [uuid.UUID(w["id"])])
    assert prog[0].state == "working" and prog[0].path == f"~/hq-workspace/{w['ref']}"
    assert prog[0].where_fa == f"شرکت آزمایشی {co['code']}"  # the company's name, not a host

    # The turn ends with an answer: it is the work's deliverable.
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={
            "exit_code": 0,
            "summary_fa": "تمام شد",
            "usage": {"input_tokens": 900, "output_tokens": 100, "model": "claude-code"},
            "data": {"session_id": "cs-ws-1", "result_fa": "## خروجی\nتست‌ها درست شد (commit abc123)",
                     "workspace": {"ref": w["ref"], "path": "/home/u/hq-workspace/" + w["ref"]}},
        },
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    detail = (await client.get(f"{API}/work/{w['id']}", headers=h)).json()
    assert detail["status"] == "delivered" and detail["deliverable_refs"]
    assert detail["budget"]["tokens_used"] >= 1000
    ws = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert ws["state"] == "delivered"
    body = await su.fetchval(
        "SELECT body FROM cartable.deliverables WHERE ref = $1", detail["deliverable_refs"][0]
    )
    assert "commit abc123" in body

    # A later run (a resume) is the next turn of the same session, in the same folder.
    await su.execute(
        "UPDATE work.work SET status = 'in_progress' WHERE id = $1", uuid.UUID(w["id"])
    )
    note = await WS.hand_over(hub, {**run, "reason": f"resume:{w['ref']}"}, {"code": run["code"]})
    assert note and "turn 2" in note
    nxt = await take(client, rn)
    assert nxt["args"]["workspace"] == w["ref"] and nxt["args"]["resume"] == "cs-ws-1"
    assert "ادامه" in nxt["args"]["brief"]

    # The owner stops it: the turn is cancelled on the runner; nothing more runs for it.
    r = await client.post(f"{API}/work/{w['id']}/stop", headers={**h, **idem()})
    assert r.status_code == 200, r.text
    assert r.json() == {"work_ref": w["ref"], "workspace": "stopped", "jobs_stopped": 1}
    r = await poll(client, rn)
    assert nxt["id"] in r.json()["cancels"]
    assert "stopped" in (await WS.hand_over(hub, run, {"code": run["code"]}) or "")
    r = await client.post(f"{API}/work/{w['id']}/stop", headers={**h, **idem()})
    assert r.json()["jobs_stopped"] == 0  # idempotent
    detail = (await client.get(f"{API}/work/{w['id']}", headers=h)).json()
    assert detail["status"] not in ("cancelled", "failed", "done")  # the work stays open

    # The work closes: the runner is told once, and removes the folder 30 days later.
    r = await client.post(
        f"{API}/work/{w['id']}/cancel", headers={**h, **idem()}, json={"reason": "تمام"}
    )
    assert r.status_code == 200, r.text
    r = await poll(client, rn)
    assert r.status_code == 200 and [c["workspace"] for c in r.json()["closed"]] == [w["ref"]]
    r = await poll(client, rn)
    assert r.status_code == 204 or not r.json().get("closed")
    ws = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert (ws["remove_after"] - ws["closed_at"]).days == 30 and ws["close_sent_at"]
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'workspace.close' AND target_ref = $1",
            w["ref"],
        )
        == 1
    )


async def test_a_failed_turn_and_an_old_runner_keep_the_work_on_the_hub(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    old = await new_company()
    await paired_on(client, hub, owner_session, old, "0.2.2")
    w = await root_work(client, h, old["code"], mode="on_server")
    run = await queued_run(su, w["id"])
    assert await WS.hand_over(hub, run, {"code": run["code"]}) is None  # runner 0.2.x: the hub
    assert (
        await su.fetchval(
            "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'workspace_unavailable'",
            uuid.UUID(w["id"]),
        )
        == 1
    )
    single = await root_work(client, h, old["code"])
    assert (
        await WS.hand_over(hub, await queued_run(su, single["id"]), {"code": run["code"]}) is None
    )

    co = await new_company()
    rn = await paired_on(client, hub, owner_session, co, "0.3.1")
    w = await root_work(client, h, co["code"], mode="on_server")
    run = await queued_run(su, w["id"])
    assert await WS.hand_over(hub, run, {"code": run["code"]})
    job = await take(client, rn)
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={
            "exit_code": 1,
            "summary_fa": "Claude Code روی سرور پیدا نشد",
            "error": "runner_error",
        },
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    ws = await su.fetchrow("SELECT * FROM work.workspaces WHERE work_id = $1", uuid.UUID(w["id"]))
    assert ws["state"] == "failed" and ws["note_fa"]
    fallback = await su.fetchval(
        "SELECT data->>'why' FROM work.work_events WHERE work_id = $1 AND kind = 'resume'",
        uuid.UUID(w["id"]),
    )
    assert fallback == f"workspace_failed:{w['ref']}"  # the worker wakes its assignee on the hub
    assert await WS.hand_over(hub, run, {"code": run["code"]}) is None  # from now on, the hub


async def test_the_order_report_shows_the_parts_and_the_workspace(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    from .test_p21_routing_orders import make_order, report

    h = owner_session["headers"]
    co = await new_company()
    order = await make_order(hub, co, "سایت را از نظر سرعت و سئو بررسی کن")
    root = order["work"]
    parts = [
        {"title_fa": "سرعت سایت", "role": "TECH", "brief": "سرعت صفحه‌ها را بسنج"},
        {"title_fa": "سئوی سایت", "role": "GROWTH", "brief": "صفحه‌های مهم را بسنج"},
    ]
    r = await split(client, str(root["id"]), f"{co['code']}-CEO", parts)
    assert r.status_code == 201, r.text
    rep = await report(client, h, order["ref"])
    assert len(rep["parts"]) == 1 and rep["parts"][0]["work_ref"] == root["ref"]
    assert [p["title_fa"] for p in rep["parts"][0]["parts"]] == ["سرعت سایت", "سئوی سایت"]
    assert rep["workspaces"] == []

    rn = await paired_on(client, hub, owner_session, co, "0.3.0")
    order2 = await make_order(hub, co, "خطای ورود را روی سرور درست کن")
    w = order2["work"]
    await su.execute("UPDATE work.work SET mode = 'on_server' WHERE id = $1", w["id"])
    run = await queued_run(su, str(w["id"]))
    assert await WS.hand_over(hub, run, {"code": run["code"]})
    await take(client, rn)
    rep = await report(client, h, order2["ref"])
    ws = rep["workspaces"][0]
    assert ws["work_ref"] == w["ref"] and ws["state"] == "working" and ws["turns"] == 1
    assert ws["path"] == f"~/hq-workspace/{w['ref']}" and ws["server"] == "app-1"
    assert rep["parts"] == []
