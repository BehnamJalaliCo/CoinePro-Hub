"""Prompt 19.3 (contract §28.5): the owner deletes notifications for good,
by ids (read or not) or every read one up to the newest shown; other
devices hear it on the stream."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from .conftest import agent_headers

pytestmark = pytest.mark.usefixtures("relay")


async def _notes(su: Any, n: int, *, read: bool, at: datetime) -> list[str]:
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    out = []
    for i in range(n):
        out.append(
            str(
                await su.fetchval(
                    """INSERT INTO notify.notifications (company_id, level, title_fa, source_kind,
                           source_code, delivered_in_app, read_at, created_at)
                       VALUES ($1, 'info', $2, 'system', 'test', true, $3, $4) RETURNING id""",
                    holding,
                    f"اعلان آزمایشی {i}",
                    at if read else None,
                    at - timedelta(seconds=i),
                )
            )
        )
    return out


async def _delete(client: httpx.AsyncClient, h: dict[str, str], body: Any) -> httpx.Response:
    return await client.request("DELETE", "/api/v1/notifications", headers=h, json=body)


async def test_the_owner_deletes_chosen_notifications_for_good(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    now = datetime.now(UTC)
    unread = await _notes(su, 2, read=False, at=now)
    read = await _notes(su, 1, read=True, at=now)
    r = await _delete(client, owner, {"ids": [unread[0], read[0], unread[0]]})
    assert r.status_code == 200 and r.json() == {"deleted": 2}, r.text
    left = await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE id = ANY($1::uuid[])", unread + read
    )
    assert left == 1  # gone from the database, not hidden
    ev = await su.fetchval(
        "SELECT payload FROM core.outbox WHERE subject LIKE '%.notification.deleted' ORDER BY id DESC LIMIT 1"
    )
    data = (json.loads(ev) if isinstance(ev, str) else ev)["data"]
    assert sorted(data["ids"]) == sorted([unread[0], read[0]]) and data["count"] == 2
    audit = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'notification.delete' AND summary = '2 deleted'"
    )
    assert audit >= 1


async def test_every_read_one_up_to_the_newest_shown(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    shown = datetime.now(UTC) - timedelta(minutes=10)
    old_read = await _notes(su, 3, read=True, at=shown - timedelta(minutes=5))
    old_unread = await _notes(su, 1, read=False, at=shown - timedelta(minutes=5))
    newer_read = await _notes(su, 1, read=True, at=shown + timedelta(minutes=5))
    r = await _delete(client, owner, {"all_read": True, "before": shown.isoformat()})
    assert r.status_code == 200 and r.json()["deleted"] >= 3
    ids = old_read + old_unread + newer_read
    rows = await su.fetch(
        "SELECT id::text FROM notify.notifications WHERE id = ANY($1::uuid[])", ids
    )
    assert {x["id"] for x in rows} == set(old_unread + newer_read)  # unread and newer stay


async def test_the_request_must_say_what_and_only_the_owner_may(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Any
) -> None:
    for bad in ({}, {"all_read": True}, {"ids": []}, {"ids": [], "all_read": True},
                {"ids": ["00000000-0000-4000-8000-000000000001"], "all_read": True}):  # fmt: skip
        r = await _delete(client, owner, bad)
        assert r.status_code == 422, (bad, r.text)
    ids = await _notes(su, 1, read=True, at=datetime.now(UTC))
    co = (await new_company())["code"]
    for h in ({}, await agent_headers(f"{co}-CEO")):
        r = await _delete(client, h, {"ids": ids})
        assert r.status_code in (401, 403)
    assert (
        await su.fetchval("SELECT count(*) FROM notify.notifications WHERE id = $1::uuid", ids[0])
        == 1
    )
