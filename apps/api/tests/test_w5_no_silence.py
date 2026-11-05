"""Handoff 2026-11-05: the owner's bugs «به مدیرعامل پیام میدم خبری نمیشه»، «کارگروه فرستادم برای استخدام هیچ خبری
نشد»، «گفتگو از هیچ چیز خبر نداشت».

- A talk run (§32) opens beside the employee's own running run, and the employee's runs start beside an open talk
  (0045); a talk run its turn never closed is failed once its token expired.
- An owner's message still unanswered after a few minutes tells the owner why, once.
- A working group's seat automatic hiring could not fill keeps the reason, and the owner hears it once a day.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import groups as GR
from hq_api.domain import no_silence as NS
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .conftest import idem


async def _ceo(su: Any, code: str) -> Any:
    return await su.fetchrow(
        """SELECT e.id, e.company_id FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE c.code = $1 AND e.kind = 'ceo' AND e.status = 'active'""",
        code,
    )


async def test_talk_runs_never_make_an_employee_busy_and_expire(
    su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await _ceo(su, co)
    # the CEO at work: a running run of its own
    work = await su.fetchval(
        "SELECT agents.queue_run($1, 'schedule', NULL, NULL, 'w5 test', NULL)", ceo["id"]
    )
    await su.execute(
        "UPDATE agents.runs SET state = 'running', started_at = now() WHERE id = $1", work
    )
    # two talks beside it (before 0045 the first came back NULL: every read refused)
    a = await su.fetchval("SELECT talk.open_run($1, 'talk a', 3, 1000, 600)", ceo["id"])
    b = await su.fetchval("SELECT talk.open_run($1, 'talk b', 3, 1000, 600)", ceo["id"])
    assert a is not None and b is not None and a != b
    # and the work finishes, then another run starts while the talks are open
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE id = $1", work
    )
    nxt = await su.fetchval(
        "SELECT agents.queue_run($1, 'schedule', NULL, NULL, 'w5 test 2', NULL)", ceo["id"]
    )
    await su.execute(
        "UPDATE agents.runs SET state = 'running', started_at = now() WHERE id = $1", nxt
    )
    # a talk its worker never closed: failed once its token expired, and only then
    assert await su.fetchval("SELECT talk.reap_runs($1)", ceo["id"]) == 0
    await su.execute(
        "UPDATE agents.runs SET token_expires_at = now() - interval '1 minute' WHERE id = $1", a
    )
    assert await su.fetchval("SELECT talk.reap_runs(NULL)") >= 1
    rows = {
        r["id"]: r
        for r in await su.fetch(
            "SELECT id, state, error_code FROM agents.runs WHERE id = ANY($1::uuid[])", [a, b, nxt]
        )
    }
    assert (rows[a]["state"], rows[a]["error_code"]) == ("failed", "talk_expired")
    assert rows[b]["state"] == "running" and rows[nxt]["state"] == "running"
    await su.execute(
        """UPDATE agents.runs SET state = 'done', finished_at = now()
           WHERE id = ANY($1::uuid[]) AND state = 'running'""",
        [b, nxt],
    )


async def test_an_unanswered_owner_message_tells_why_once(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = (await new_company())["code"]
    thread = f"{co}-CEO"
    r = await client.post(
        f"/api/v1/threads/{thread}/messages",
        headers={**owner, **idem()},
        json={"body": "گزارش این هفته را بفرست"},
    )
    assert r.status_code == 201
    monkeypatch.setattr(NS, "QUIET", timedelta(0))
    # the run was refused by a kill switch: the owner hears why
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'locked', finished_at = now()
           WHERE thread_id = (SELECT id FROM msg.threads WHERE code = $1) AND state = 'queued'""",
        thread,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await NS.sweep_unanswered(tx, limit=500) >= 1
    rows = await su.fetch(
        """SELECT title_fa, body_fa, owner_visible FROM notify.notifications
           WHERE link_kind = 'thread' AND link_ref = $1""",
        thread,
    )
    assert len(rows) == 1 and rows[0]["owner_visible"]
    assert "کلید توقف" in rows[0]["body_fa"]
    # once per message
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await NS.sweep_unanswered(tx, limit=500)
    assert (
        await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_kind = 'thread' AND link_ref = $1",
            thread,
        )
        == 1
    )


async def test_a_seat_without_an_envelope_says_why_and_tells_the_owner(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    async def refuse(*_: Any) -> None:
        raise ApiError(422, "envelope_required", "no envelope")

    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await GR._auto_fill(tx, refuse, co["id"], "publisher", "ناشر")
        assert out == (None, "envelope_required")
        w = NS.hire_why("envelope_required")
        assert "پاکت" in w["why_fa"] and w["fix_fa"]
        assert await NS.tell_seat_blocked(
            tx, co["id"], co["code"], "content", "تولید محتوا", "ناشر", "envelope_required"
        )
        # once a day for the same seat and reason
        assert not await NS.tell_seat_blocked(
            tx, co["id"], co["code"], "content", "تولید محتوا", "ناشر", "envelope_required"
        )
    n = await su.fetchrow(
        """SELECT title_fa, body_fa, owner_visible FROM notify.notifications
           WHERE company_id = $1 AND link_kind = 'group' AND link_ref = 'content'""",
        co["id"],
    )
    assert n is not None and n["owner_visible"] and "پاکت" in n["body_fa"]
