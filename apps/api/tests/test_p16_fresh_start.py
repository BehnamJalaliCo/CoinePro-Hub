"""Prompt 16: the fresh start. The script runs as the superuser inside a
transaction the test rolls back, so the shared test database keeps its rows
(and a dry run on the hub writes nothing either): what ran is gone, what the
hub is made of stays, a kept row pointing at wiped data or a table in no list
stops it, and the audit chain starts again from its genesis."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import asyncpg
import httpx
import pytest

from hq_api import fresh_start as FS
from hq_api.audit import GENESIS
from hq_api.hub import Hub

from .conftest import idem, superuser
from .test_org_work import hire

SNAP = "568e02bc"


async def _count(conn: asyncpg.Connection, table: str) -> int:
    return int(await conn.fetchval(f"SELECT count(*) FROM {table}"))


async def _ran(client: httpx.AsyncClient, owner: dict[str, str], co: str) -> None:
    r = await client.post(
        "/api/v1/work", headers={**owner, **idem()}, json={"company": co, "title": "کار"}
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/threads/N/messages", headers={**owner, **idem()}, json={"body": "سلام"}
    )
    assert r.status_code == 201, r.text


def test_every_list_is_disjoint_and_the_arguments_are_checked() -> None:
    lists = FS.WIPE + FS.KEEP + FS.ASK
    assert len(lists) == len(set(lists))
    assert not set(FS.REF_RESET) & set(FS.REF_KEEP)
    with pytest.raises(ValueError):
        FS.body("not-a-snapshot", 1, "a" * 64)
    with pytest.raises(ValueError):
        FS.body(SNAP, 1, "short")
    assert FS.script(SNAP, 3, "b" * 64).startswith("\\set ON_ERROR_STOP on\nBEGIN;")


@pytest.mark.usefixtures("hiring_open")
async def test_what_ran_goes_what_the_hub_is_made_of_stays(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await _ran(client, owner, co)
    # an employee hired by a card (the card is wiped, the employee stays)
    hired = await hire(hub, client, owner_session, co)
    conn = await superuser()
    try:
        kept = {t: await _count(conn, t) for t in ("core.companies", "core.employees",
                                                   "core.departments", "msg.threads",
                                                   "oversight.protocols", "auth.passkeys",
                                                   "archive.classes")}  # fmt: skip
        protocols = await conn.fetch(
            "SELECT ref, version, status FROM oversight.protocols ORDER BY 1, 2"
        )
        head = await conn.fetchrow("SELECT last_seq, last_hash FROM audit.chain_head")
        before_ref = await conn.fetchval("SELECT last_value FROM work.work_ref_seq")
        assert await _count(conn, "work.work") > 0 and await _count(conn, "msg.messages") > 0
        tx = conn.transaction()
        await tx.start()
        try:
            await conn.execute(FS.body(SNAP, head["last_seq"], head["last_hash"]))
            for t in FS.WIPE:
                if t != "audit.entries":
                    assert await _count(conn, t) == 0, t
            for t, n in kept.items():
                assert await _count(conn, t) == n, t
            assert (
                await conn.fetch(
                    "SELECT ref, version, status FROM oversight.protocols ORDER BY 1, 2"
                )
                == protocols
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM msg.threads WHERE last_seq <> 0 OR owner_read_seq <> 0"
                )
                == 0
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM core.employees WHERE activity_at IS NOT NULL OR score IS NOT NULL"
                )
                == 0
            )
            assert await conn.fetchval(
                "SELECT hired_by_decision_id IS NULL FROM core.employees WHERE code = $1", hired
            )
            # refs start again; a kept kind's numbering does not
            assert await conn.fetchval("SELECT nextval('work.work_ref_seq')") == 1
            # the new chain: one row, this fresh start, and it verifies
            e = await conn.fetchrow("SELECT * FROM audit.entries")
            assert e["seq"] == 1 and e["prev_hash"] == GENESIS and e["action"] == "hub.fresh_start"
            assert e["target_ref"] == f"snapshot:{SNAP}" and FS.DECISION in e["summary"]
            assert f"previous chain seq {head['last_seq']}" in e["summary"]
            assert (await conn.fetchrow("SELECT ok, checked FROM audit.verify_chain()"))[0] is True
            assert tuple(
                await conn.fetchrow("SELECT last_seq, last_hash FROM audit.chain_head")
            ) == (
                1,
                e["hash"],
            )
            assert await _count(conn, "fresh_start_blobs") >= 0
        finally:
            await tx.rollback()
        # rolled back: every row and every number as it was (a dry run writes nothing)
        assert await _count(conn, "work.work") > 0
        assert (await conn.fetchrow("SELECT last_seq, last_hash FROM audit.chain_head")) == head
        assert await conn.fetchval("SELECT last_value FROM work.work_ref_seq") == before_ref
    finally:
        await conn.close()


async def test_a_table_in_no_list_or_a_kept_row_pointing_at_wiped_data_stops_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = (await new_company())["code"]
    await _ran(client, owner, co)
    conn = await superuser()
    try:
        head = await conn.fetchrow("SELECT last_seq, last_hash FROM audit.chain_head")
        for listed, error in ((False, "tables in no list: archive.fs_probe"),
                              (True, r"kept rows point at wiped data: fs_probe_w_fkey \(1 rows\)")):  # fmt: skip
            if listed:
                monkeypatch.setattr(FS, "KEEP", (*FS.KEEP, "archive.fs_probe"))
            tx = conn.transaction()
            await tx.start()
            try:
                await conn.execute(
                    """CREATE TABLE archive.fs_probe (w uuid REFERENCES work.work (id));
                       INSERT INTO archive.fs_probe SELECT id FROM work.work LIMIT 1"""
                )
                with pytest.raises(asyncpg.RaiseError, match=error):
                    await conn.execute(FS.body(SNAP, head["last_seq"], head["last_hash"]))
            finally:
                await tx.rollback()
        assert await _count(conn, "work.work") > 0
    finally:
        await conn.close()
