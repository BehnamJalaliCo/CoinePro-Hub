"""⟨2026-11-14⟩ The owner's two switches (migration 0067): no work the hub starts by itself
unless he wants it, and every n8n automation on the board, step by step."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import flows as FL

from .conftest import idem
from .test_agents import order, runs_of
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w26_flows import a_flow

pytestmark = pytest.mark.usefixtures("relay")


async def _work_by(su: Any, company: dict[str, Any], kind: str, code: str, **cols: Any) -> Any:
    ceo = await su.fetchval(
        "SELECT id FROM core.employees WHERE code = $1", f"{company['code']}-CEO"
    )
    return await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code,
               assignee_id, requested_by_work_id)
           VALUES ($1, 'one_off', 'برنامه‌ی امروز', $2, $3, $4, $5) RETURNING id""",
        company["id"], kind, code, ceo, cols.get("asked_by"),
    )  # fmt: skip


async def test_self_work_off_runs_only_what_the_owner_asked_for(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    r = await client.put(
        "/api/v1/control/self-work", headers=owner, json={"on": False, "reason": "owner in chat"}
    )
    assert r.status_code == 200 and r.json() == {"on": False}, r.text
    try:
        assert (await client.get("/api/v1/control/self-work", headers=owner)).json() == {
            "on": False
        }
        # a work the groups' schedule made by itself: refused before any model call, cancelled
        own = await _work_by(su, company, "service", "groups")
        (run,) = [x for x in await runs_of(su, f"{co}-CEO") if x["work_id"] == own]
        claim = await agents.runner.claim(str(run["id"]))
        assert (claim.state, claim.code) == ("final", "owner_only")
        w = await su.fetchrow("SELECT status, close_reason FROM work.work WHERE id = $1", own)
        assert w["status"] == "cancelled" and "owner" in w["close_reason"]
        assert await su.fetchval(
            "SELECT count(*) FROM llm.calls WHERE work_ref = (SELECT ref FROM work.work WHERE id = $1)",
            own,
        ) == 0  # fmt: skip
        # the owner's own order runs; so does what an employee opened for it
        mine = await order(client, owner, co)
        row = next(x for x in await runs_of(su, f"{co}-CEO") if str(x["work_id"]) == mine["id"])
        claim = await agents.runner.claim(str(row["id"]))
        assert claim.code != "owner_only", claim
        await su.execute(
            "UPDATE agents.runs SET state = 'done', finished_at = now(), started_at = now()"
            " WHERE id = $1 AND state = 'running'",
            row["id"],
        )
        asked = await _work_by(su, company, "agent", f"{co}-CEO", asked_by=uuid.UUID(mine["id"]))
        (run2,) = [x for x in await runs_of(su, f"{co}-CEO") if x["work_id"] == asked]
        claim = await agents.runner.claim(str(run2["id"]))
        assert claim.code != "owner_only", claim
        audit = await su.fetchval(
            "SELECT summary FROM audit.entries WHERE action = 'hub.self_work' ORDER BY seq DESC LIMIT 1"
        )
        assert audit.startswith("on -> off")
    finally:
        await client.put("/api/v1/control/self-work", headers=owner, json={"on": True})
    assert (await client.get("/api/v1/control/self-work", headers=owner)).json() == {"on": True}


async def test_an_n8n_flow_is_on_the_board_with_its_steps_and_its_switch(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pc = await new_company()
    key = f"t{uuid.uuid4().hex[:8]}"  # (the test DB keeps earlier runs' days)
    monkeypatch.setattr(FL, "FLOWS", {key: replace(a_flow(pc["code"]), key=key)})
    ref = f"N8:{key}"
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)
    r = await client.post(
        f"/api/v1/flows/{key}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    got = r.json()
    try:
        # the board: one item that opens the flow's page
        board = (await client.get("/api/v1/automations/board", headers=owner)).json()
        (item,) = [x for x in board["items"] if x["ref"] == ref]
        assert item["kind"] == "n8n" and item["state"] == "on" and item["switchable"]
        # (no workshop here: the day's turn may have failed already)
        assert item["opens"] == f"automation/{ref}"
        assert item["last"]["state"] in ("queued", "running", "failed")
        # the page: every step from n8n's call to the owner's notice
        r = await client.get(f"/api/v1/automations/{ref}", headers=owner)
        assert r.status_code == 200, r.text
        page = r.json()
        keys = [s["key"] for s in page["steps"]]
        assert keys[:2] == ["n8n", "order"] and keys[-1] == "report" and "render" in keys
        assert (
            page["state"] == "on"
            and page["playbook"] is None
            and page["last_run"]["ref"] == got["order"]
        )
        runs = (await client.get(f"/api/v1/automations/{ref}/runs", headers=owner)).json()
        assert [x["ref"] for x in runs["items"]] == [got["order"]]
        # the day, step by step: n8n and the order done, the rest still to come
        run = await client.get(f"/api/v1/line-runs/{got['order']}", headers=owner)
        assert run.status_code == 200, run.text
        steps = {s["key"]: s["state"] for s in run.json()["steps"]}
        assert steps["n8n"] == "done" and steps["order"] == "done"
        assert steps["publish"] == "pending" and run.json()["automation"] == ref
        # its other controls are the hub's Claude's
        r = await client.post(f"/api/v1/automations/{ref}/pause", headers=owner, json={})
        assert r.status_code == 409, r.text
        # the switch: off, n8n's next call makes nothing
        r = await client.post(
            f"/api/v1/automations/{ref}/state", headers=owner, json={"state": "off"}
        )
        assert r.status_code == 200 and r.json()["state"] == "off", r.text
        later = (day + timedelta(days=1)).isoformat()
        r = await client.post(
            f"/api/v1/flows/{key}/run", headers={**owner, **idem()}, json={"day": later}
        )
        assert r.status_code == 201 and r.json()["order"] == "" and r.json()["work"] is None, r.text
        assert not await su.fetchval(
            "SELECT count(*) FROM work.work WHERE run_meta -> 'flow' ->> 'day' = $1"
            " AND run_meta -> 'flow' ->> 'key' = $2",
            later,
            key,
        )
        audit = await client.get(f"/api/v1/automations/{ref}/audit", headers=owner)
        assert audit.status_code == 200 and audit.json(), audit.text
    finally:
        await su.execute("UPDATE owner.settings SET flows_off = '{}' WHERE id = 1")
