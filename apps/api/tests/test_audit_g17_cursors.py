"""Audit 2026-11-11 (g17): list cursors of the owner's routes.

A forged or mismatched cursor is a 422, never a 500; the employee-memory layer
of /knowledge pages through notes stamped at the same moment without losing any."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import pagination


@pytest.mark.parametrize(
    ("path", "values"),
    [
        ("/api/v1/feedback", ["x", "y", "z"]),
        ("/api/v1/feedback", [3, "2026-11-11T00:00:00+00:00", "not-a-uuid"]),
        ("/api/v1/feedback", [None, None, None]),
        ("/api/v1/risks", ["abc", "R-1"]),
        ("/api/v1/risks", ["2026-11-11T00:00:00+00:00", "00000000-0000-0000-0000-000000000001"]),
    ],
)
async def test_a_bad_cursor_is_422(
    client: httpx.AsyncClient, owner: dict[str, str], path: str, values: list[Any]
) -> None:
    r = await client.get(path, headers=owner, params={"cursor": pagination.encode(values)})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "validation_failed"


async def test_employee_memory_pages_keep_notes_stamped_alike(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    ceo = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co['code']}-CEO")
    # one statement, one transaction: every note has the same created_at
    await su.execute(
        """INSERT INTO core.employee_memory (company_id, employee_id, note)
           SELECT $1, $2, 'یادداشت ' || g FROM generate_series(1, 5) g""",
        co["id"],
        ceo,
    )
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {"layer": "employee", "company": co["code"], "limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = await client.get("/api/v1/knowledge", headers=owner, params=params)
        assert r.status_code == 200, r.text
        seen += [i["id"] for i in r.json()["items"]]
        cursor = r.json()["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 5
