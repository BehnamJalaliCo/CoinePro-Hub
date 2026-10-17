"""Prompt 08 §1 (contract §18.0): the Chief Overseer and the personal
assistant, their threads N and P, and precedence."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from hq_common import charters

from .conftest import agent_headers, idem
from .test_agents import run, step

pytestmark = pytest.mark.usefixtures("relay")


async def test_the_overseer_and_the_assistant_are_seeded(su: Any) -> None:
    rows = {
        r["code"]: r
        for r in await su.fetch(
            """SELECT e.code, e.kind, e.role, d.code AS dept, t.code AS thread, t.kind AS thread_kind,
                      (SELECT b.code FROM core.employees b WHERE b.id = e.reports_to) AS boss
               FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
               LEFT JOIN msg.threads t ON t.employee_id = e.id AND t.kind IN ('overseer', 'assistant')
               WHERE e.code IN ('HQ-OVR', 'HQ-PA', 'HQ-OVS-MGR')"""
        )
    }
    ovr, pa = rows["HQ-OVR"], rows["HQ-PA"]
    assert (ovr["kind"], ovr["role"], ovr["dept"], ovr["thread"], ovr["thread_kind"]) == (
        "overseer", "overseer", "OVS", "N", "overseer",
    )  # fmt: skip
    assert (pa["kind"], pa["role"], pa["thread"], pa["thread_kind"]) == (
        "assistant", "assistant", "P", "assistant",
    )  # fmt: skip
    assert rows["HQ-OVS-MGR"]["boss"] == "HQ-OVR"  # QC under the overseer
    lib = charters.load()
    assert not [p for p in lib.problems if "overseer" in p or "assistant" in p]
    assert lib.roles["overseer"].kind == "overseer" and lib.roles["assistant"].kind == "assistant"


async def test_ranks_and_precedence(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Any
) -> None:
    co = (await new_company())["code"]
    r = await client.get("/api/v1/employees", headers=owner, params={"company": ["HQ", co], "limit": 200})
    assert r.status_code == 200, r.text
    items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
    ranks = {e["code"]: e["rank"] for e in items}
    assert ranks["HQ-OVR"] == ranks["HQ-ADV"] == 2
    assert ranks["HQ-OVS-MGR"] == ranks["HQ-AIOPS-MGR"] == ranks[f"{co}-CEO"] == 3
    assert ranks[f"{co}-TECH-MGR"] == 4 and ranks["HQ-PA"] == 5 and ranks["HQ-SYS"] is None
    meta = (await client.get("/api/v1/meta", headers=owner)).json()
    assert [p["rank"] for p in meta["precedence"]] == [1, 2, 3, 4, 5]
    assert meta["precedence"][1]["kinds"] == ["overseer", "advisor"]


@pytest.mark.parametrize(
    ("thread", "code", "role"), [("N", "HQ-OVR", "overseer"), ("P", "HQ-PA", "assistant")]
)
async def test_threads_n_and_p_are_the_owner_and_one_agent(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    thread: str,
    code: str,
    role: str,
) -> None:
    r = await client.post(
        f"/api/v1/threads/{thread}/messages", headers={**owner, **idem()}, json={"body": "سلام"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["message"]["ref"].startswith(f"{thread}-")
    queued = await su.fetchrow(
        """SELECT r.id, r.priority FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.code = $1 AND r.state = 'queued' ORDER BY r.queued_at DESC LIMIT 1""",
        code,
    )
    assert queued["priority"] == "P2"  # the owner's own agents answer first
    # Its own agent replies there; nobody else does (not the advisor, not QC).
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        code, step("پاسخ", ("message.thread", {"thread": thread, "body_md": "بله"}))
    )
    assert (await run(agents, queued["id"]))["state"] == "done"
    replies = await su.fetchval(
        """SELECT count(*) FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = $1 AND m.author_code = $2""",
        thread,
        code,
    )
    assert replies >= 1  # its message.thread (and the run's own reply)
    first = next(c for c in agents.fake.calls[since:] if c.actor_ref == code)
    lib = charters.load()
    assert lib.roles[role].body[:60] in (first.system or "")  # its own v2 charter
    run_row = await su.fetchrow(
        "SELECT charter_role, charter_version FROM agents.runs WHERE id = $1", queued["id"]
    )
    assert (run_row["charter_role"], run_row["charter_version"]) == (role, lib.roles[role].version)
    for other in ("HQ-ADV", "HQ-OVS-MGR"):
        r = await client.post(
            f"/internal/v1/threads/{thread}/messages",
            headers={**await agent_headers(other), **idem()},
            json={"body": "x"},
        )
        assert r.status_code == 403, (other, r.text)
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code IN ('HQ-ADV', 'HQ-OVS-MGR') AND r.state = 'running'
             AND r.reason = 'test'"""
    )
