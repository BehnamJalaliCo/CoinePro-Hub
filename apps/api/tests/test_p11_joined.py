"""Prompt 11 where its two halves meet (r11i): a meeting (§1) is an event of
the change calendar (§9.2) and the planner shows it once; the authority
matrix (§7) decides the CEOs' knowledge approval (§3.4) in OPA, in the shape
the api pushes, and by the database row as well."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import meeting_flow as MF
from hq_api.hub import Hub
from hq_api.principal import Principal

from .conftest import agent_headers, idem
from .p11b_helpers import governance_seeded  # noqa: F401 - the seed before each test (autouse)
from .test_p11_charter_knowledge import entry
from .test_p11_meetings import ad_hoc, roomy
from .test_p11b_outcomes_authority import _put, _row, restore_matrix  # noqa: F401 - a fixture

pytestmark = pytest.mark.usefixtures("relay")
CHECKS = {"injection": True, "secrets": True, "conflicts": True, "policy": True}


async def test_a_meeting_is_on_the_change_calendar_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    m = await ad_hoc(client, owner, type="company", company=co["code"])
    rows = await su.fetch(
        """SELECT e.kind, e.status, e.source, e.starts_at, e.ends_at, c.code AS company
           FROM governance.calendar_events e JOIN core.companies c ON c.id = e.company_id
           WHERE e.auto_key = $1""",
        f"meeting:{m['ref']}",
    )
    assert len(rows) == 1
    ev = rows[0]
    assert (ev["kind"], ev["status"], ev["company"]) == ("meeting", "planned", co["code"])
    assert json.loads(ev["source"]) == {"meeting": m["ref"]}
    assert ev["ends_at"] - ev["starts_at"] == timedelta(hours=1)
    cal = await client.get(
        "/api/v1/calendar", headers=owner, params={"company": co["code"], "kind": "meeting"}
    )
    assert cal.status_code == 200, cal.text
    mine = [e for e in cal.json()["events"] if e["source"] == {"meeting": m["ref"]}]
    assert (
        len(mine) == 1 and mine[0]["company"] == co["code"]
    )  # (the holding's board is listed too)
    # The planner: the meeting once (its own row), never its calendar event too.
    plan = await client.get(
        "/api/v1/planner",
        headers=owner,
        params={"scope": f"company:{co['code']}", "to": (ev["starts_at"].date() + timedelta(days=1)).isoformat()},
    )  # fmt: skip
    assert plan.status_code == 200, plan.text
    items = [i for d in plan.json()["days"] for i in d["items"]]
    assert [i["kind"] for i in items if i["ref"] == m["ref"]] == ["meeting"]
    assert not [i for i in items if i["kind"] == "calendar" and i["calendar_kind"] == "meeting"]
    # A meeting that was never started (missed) leaves the calendar.
    long_ago = await su.fetchval(
        "UPDATE meetings.meetings SET starts_at = now() - interval '30 days' WHERE ref = $1 RETURNING starts_at",
        m["ref"],
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await MF.start_due(tx, long_ago + timedelta(hours=7), roomy(hub))
    assert (
        await su.fetchval("SELECT state FROM meetings.meetings WHERE ref = $1", m["ref"])
        == "cancelled"
    )
    assert (
        await su.fetchval(
            "SELECT status FROM governance.calendar_events WHERE auto_key = $1",
            f"meeting:{m['ref']}",
        )
        == "cancelled"
    )


@pytest.mark.usefixtures("restore_matrix")
async def test_the_owner_takes_the_ceos_knowledge_approval_back(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    ty = await new_company()
    mgr = await agent_headers(f"{ty['code']}-GROWTH-MGR")
    r = await client.post(
        "/internal/v1/knowledge", headers={**mgr, **idem()}, json=entry(ty["code"])
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    r = await client.post(
        f"/internal/v1/knowledge/{ref}/review", headers={**await agent_headers("HQ-OVR"), **idem()},
        json={"version": 1, "verdict": "pass", "checks": CHECKS, "notes_md": ""},
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["review"]["verdict"] == "pass", r.text
    ceo_p = Principal(
        kind="agent", code=f"{ty['code']}-CEO", role="ceo", company=ty["code"], status="active"
    )
    ask = {
        "principal": ceo_p.opa(),
        "op": "knowledge.approve",
        "target": {"company": ty["code"], "layer": "company"},
    }
    assert (await hub.policy.query("internal", ask)).allow  # the default: the CEO approves (§0.7)
    m = (await client.get("/api/v1/authority", headers=owner_session["headers"])).json()
    row = _row(m, "knowledge.approve.company")
    assert (row["actor"], row["locked"]) == ("ceo", False)
    r = await _put(client, hub, owner_session, {"rules": [
        {"key": "knowledge.approve.company", "actor": "owner", "limit": None, "version": row["version"]}]})  # fmt: skip
    assert r.status_code == 200, r.text
    # OPA reads the row in the shape the api pushes ({version, rules: {key: row}}).
    pushed = await hub.policy.value("authority")
    assert pushed["rules"]["knowledge.approve.company"]["actor"] == "owner"
    assert not (await hub.policy.query("internal", ask)).allow
    ceo_h = await agent_headers(f"{ty['code']}-CEO")
    r = await client.post(
        f"/internal/v1/knowledge/{ref}/approve", headers={**ceo_h, **idem()}, json={"version": 1}
    )
    assert r.status_code == 403, r.text
    # OPA's copy lost (a restart): the database row still refuses.
    assert await hub.policy.put_authority({"version": "lost", "rules": {}})
    r = await client.post(
        f"/internal/v1/knowledge/{ref}/approve", headers={**ceo_h, **idem()}, json={"version": 1}
    )
    assert r.status_code == 403, r.text
    # Given back to the CEOs: approved.
    m = (await client.get("/api/v1/authority", headers=owner_session["headers"])).json()
    row = _row(m, "knowledge.approve.company")
    r = await _put(client, hub, owner_session, {"rules": [
        {"key": "knowledge.approve.company", "actor": "ceo", "limit": None, "version": row["version"]}]})  # fmt: skip
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/internal/v1/knowledge/{ref}/approve", headers={**ceo_h, **idem()}, json={"version": 1}
    )
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
