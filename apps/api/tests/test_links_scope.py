"""Prompt 5.1 §1.1: another company's decision card never reaches an agent's
prompt. A message's links must resolve in the thread's company (or what the
author may read), and the run context reads only inside the charter's scope."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from .conftest import agent_headers, idem
from .test_agents import run, step

pytestmark = pytest.mark.usefixtures("relay")


async def _decision(client: httpx.AsyncClient, co: str, mark: str) -> str:
    """A pending card of `co`, proposed by its CEO, with recognisable text."""
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={
            "kind": "proposal",
            "title": f"TITLE-{mark}",
            "what": f"WHAT-{mark}",
            "why": f"WHY-{mark}",
            "payload": {"okr": f"OKR-{mark}"},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["ref"])


async def _insert_message(su: Any, thread: str, links: dict[str, str]) -> None:
    """A message written straight into the database (bypassing the API's check)."""
    await su.execute(
        """INSERT INTO msg.messages (thread_id, company_id, seq, ref, author_kind, author_code, body,
               attachments, links, kind, citations, meta)
           SELECT t.id, '00000000-0000-0000-0000-000000000000', 0, '', 'owner', 'owner', 'به این کارت نگاه کن',
                  '{}', $2::jsonb, 'text', '[]', '{}'
           FROM msg.threads t WHERE t.code = $1""",
        thread,
        json.dumps(links),
    )


def _prompts(agents: Any, actor: str, since: int) -> str:
    return "\n".join(
        (c.system or "") + "".join(m.content for m in c.messages)
        for c in agents.fake.calls[since:]
        if c.actor_ref == actor
    )


async def test_agent_cannot_link_another_companys_decision(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    ty = (await new_company())["code"]
    fx = (await new_company())["code"]
    d_fx = await _decision(client, fx, uuid.uuid4().hex[:8])
    d_ty = await _decision(client, ty, uuid.uuid4().hex[:8])
    ceo = await agent_headers(f"{ty}-CEO")
    path = f"/internal/v1/threads/{ty}-CEO/messages"
    for links in ({"decision": d_fx}, {"decision": "D-999999"}, {"work": "W-999999"}):
        r = await client.post(
            path, headers={**ceo, **idem()}, json={"body": "این را ببین", "links": links}
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "validation_failed" and "links" in r.json()["fields"]
    r = await client.post(
        path, headers={**ceo, **idem()}, json={"body": "این را ببین", "links": {"decision": d_ty}}
    )
    assert r.status_code == 201, r.text
    # The owner's side checks existence too (the owner reads every company).
    r = await client.post(
        f"/api/v1/threads/{ty}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "کارت", "links": {"resolution": "M-999999"}},
    )
    assert r.status_code == 422 and "links" in r.json()["fields"]
    r = await client.post(
        f"/api/v1/threads/{ty}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "کارت", "links": {"decision": d_fx}},
    )
    assert r.status_code == 201, r.text


async def test_run_context_never_carries_another_companys_card(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    ty = (await new_company())["code"]
    fx = (await new_company())["code"]
    mark = uuid.uuid4().hex[:8]
    d_fx = await _decision(client, fx, mark)
    r = await client.post(
        f"/api/v1/threads/{ty}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "گزارش کوتاه بده"},
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["reply"]["run_id"]
    await _insert_message(su, f"{ty}-CEO", {"decision": d_fx})
    since = len(agents.fake.calls)
    agents.fake.enqueue(f"{ty}-CEO", step("پاسخ", ("message.owner", {"body_md": "باشد"})))
    assert (await run(agents, run_id))["state"] == "done"
    seen = _prompts(agents, f"{ty}-CEO", since)
    assert "به این کارت نگاه کن" in seen  # the message itself is there
    for leak in (d_fx, f"WHAT-{mark}", f"WHY-{mark}", f"TITLE-{mark}", f"OKR-{mark}"):
        assert leak not in seen, leak


async def test_holding_charter_sees_any_companys_card(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    fx = (await new_company())["code"]
    mark = uuid.uuid4().hex[:8]
    d_fx = await _decision(client, fx, mark)
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "نظرت؟"}
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["reply"]["run_id"]
    await _insert_message(su, "A", {"decision": d_fx})
    since = len(agents.fake.calls)
    agents.fake.enqueue("HQ-ADV", step("بررسی کارت"), "نظر کوتاه درباره‌ی کارت.")
    assert (await run(agents, run_id))["state"] == "done"
    seen = _prompts(agents, "HQ-ADV", since)
    assert d_fx in seen and f"WHAT-{mark}" in seen and f"OKR-{mark}" in seen
