"""Rules enforced by the database itself (prompt 04 §2), checked as hq_api."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from hq_api.db import Tx
from hq_api.errors import from_db_error, sqlstate_of
from hq_api.hub import Hub

from .conftest import superuser

SCHEMAS = (
    "core",
    "work",
    "cartable",
    "msg",
    "notify",
    "auth",
    "owner",
    "audit",
    "control",
    "files",
    "workshop",
    "backup",
    "egress",
    "oversight",
    "people",
    "knowledge",
    "academy",
    "provisioning",
    "infra",
)


async def _employee(tx: Tx, company_id: Any, code_suffix: str) -> Any:
    return await tx.scalar(
        "SELECT id FROM core.employees WHERE company_id = :co AND code LIKE :pat",
        co=company_id,
        pat=f"%-{code_suffix}",
    )


async def _work(tx: Tx, company_id: Any, **kw: Any) -> dict[str, Any]:
    cols = {
        "company_id": company_id,
        "kind": "one_off",
        "title": "t",
        "created_by_kind": "owner",
        "created_by_code": "owner",
        **kw,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    return await tx.one(f"INSERT INTO work.work ({names}) VALUES ({values}) RETURNING *", **cols)


async def _expect(state: str, coro: Any) -> None:
    with pytest.raises(DBAPIError) as info:
        await coro
    assert sqlstate_of(info.value) == state, info.value


async def test_every_tenant_table_has_forced_rls(su: Any) -> None:
    rows = await su.fetch(
        """SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           JOIN information_schema.columns col
             ON col.table_schema = n.nspname AND col.table_name = c.relname AND col.column_name = 'company_id'
           WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY($1::text[])""",
        list(SCHEMAS),
    )
    assert len(rows) >= 18
    for r in rows:
        assert r["relrowsecurity"] and r["relforcerowsecurity"], f"{r['nspname']}.{r['relname']}"


async def test_cross_company_rows_are_invisible_and_unwritable(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    a, b = await new_company(), await new_company()
    async with hub.db.tx([a["id"], b["id"]]) as tx:
        await _work(tx, a["id"], title="for A")
        await _work(tx, b["id"], title="for B")
    async with hub.db.tx([a["id"]]) as tx:
        seen = await tx.all(
            "SELECT company_id FROM work.work WHERE company_id IN (:a, :b)", a=a["id"], b=b["id"]
        )
        assert seen and {r["company_id"] for r in seen} == {a["id"]}
        assert (
            await tx.scalar("SELECT count(*) FROM core.employees WHERE company_id = :b", b=b["id"])
            == 0
        )
        assert (
            await tx.scalar("SELECT count(*) FROM msg.threads WHERE company_id = :b", b=b["id"])
            == 0
        )
    async with hub.db.tx([a["id"]]) as tx:
        await _expect("42501", _work(tx, b["id"], title="smuggled"))
    async with hub.db.tx([]) as tx:  # no scope: nothing at all
        assert await tx.scalar("SELECT count(*) FROM work.work") == 0


async def test_delegation_depth_is_capped_at_two(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        root = await _work(tx, co["id"])
        child = await _work(tx, co["id"], parent_id=root["id"])
        grandchild = await _work(tx, co["id"], parent_id=child["id"])
        assert (root["depth"], child["depth"], grandchild["depth"]) == (0, 1, 2)
        assert grandchild["root_id"] == root["id"]
    async with hub.db.tx([co["id"]]) as tx:
        with pytest.raises(DBAPIError) as info:
            await _work(tx, co["id"], parent_id=grandchild["id"])
        assert from_db_error(info.value).code == "delegation_depth_exceeded"
    async with hub.db.tx([co["id"]]) as tx:  # a shortcut root may start at depth 1
        shortcut = await _work(tx, co["id"], depth=1)
        assert (await _work(tx, co["id"], parent_id=shortcut["id"]))["depth"] == 2


async def test_child_budget_never_exceeds_what_remains(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        root = await _work(tx, co["id"], budget_tokens=1000, budget_usd=10)
        c1 = await _work(tx, co["id"], parent_id=root["id"], budget_tokens=600, budget_usd=4)
        c2 = await _work(tx, co["id"], parent_id=root["id"])  # inherits what remains
        assert (c2["budget_tokens"], float(c2["budget_usd"])) == (400, 6.0)
        assert c1["budget_tokens"] == 600
    async with hub.db.tx([co["id"]]) as tx:
        await _expect("HQB01", _work(tx, co["id"], parent_id=root["id"], budget_tokens=1))
    async with hub.db.tx([co["id"]]) as tx:
        # the parent cannot shrink below what its children hold
        await _expect(
            "HQB01",
            tx.exec("UPDATE work.work SET budget_tokens = 500 WHERE id = :id", id=root["id"]),
        )
    async with hub.db.tx([co["id"]]) as tx:
        # a child cannot grow beyond its parent
        await _expect(
            "HQB01", tx.exec("UPDATE work.work SET budget_tokens = 700 WHERE id = :id", id=c1["id"])
        )


async def test_done_needs_evidence(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        w = await _work(tx, co["id"])
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "HQE01", tx.exec("UPDATE work.work SET status = 'done' WHERE id = :id", id=w["id"])
        )
    async with hub.db.tx([co["id"]]) as tx:
        await tx.exec(
            """UPDATE work.work SET status = 'done', evidence = '[{"kind": "link", "ref": "https://x"}]'
               WHERE id = :id""",
            id=w["id"],
        )
        assert await tx.scalar("SELECT status FROM work.work WHERE id = :id", id=w["id"]) == "done"
    async with hub.db.tx([co["id"]]) as tx:  # closed stays closed
        await _expect(
            "HQV01", tx.exec("UPDATE work.work SET status = 'queued' WHERE id = :id", id=w["id"])
        )


async def test_codes_and_refs_are_immutable(
    hub: Hub, new_company: Callable[..., Any], owner_db: Any
) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        w = await _work(tx, co["id"])
        assert w["ref"].startswith("W-")
    # Layer 1: the application roles have no UPDATE right on code/ref columns.
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "42501", tx.exec("UPDATE work.work SET ref = 'W-999999' WHERE id = :id", id=w["id"])
        )
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "42501",
            tx.exec("UPDATE core.employees SET code = 'X-Y' WHERE company_id = :co", co=co["id"]),
        )
    # Layer 2: even the owner role hq is stopped by the trigger.
    for stmt in (
        "UPDATE work.work SET ref = 'W-999999' WHERE id = :id",
        "UPDATE core.companies SET code = 'ZZZZ' WHERE id = :co",
        "UPDATE core.employees SET code = 'X-Y' WHERE company_id = :co",
    ):
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            await _expect("HQI01", tx.exec(stmt, id=w["id"], co=co["id"]))


async def test_employee_codes_move_forward_and_are_never_reused(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        dept = await tx.scalar(
            "SELECT id FROM core.departments WHERE company_id = :co AND code = 'GROWTH'",
            co=co["id"],
        )
        first = await tx.scalar("SELECT core.issue_employee_code(:co, :d)", co=co["id"], d=dept)
        second = await tx.scalar("SELECT core.issue_employee_code(:co, :d)", co=co["id"], d=dept)
        assert (first, second) == (f"{co['code']}-GROWTH-01", f"{co['code']}-GROWTH-02")
        emp = await tx.scalar(
            """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en)
               VALUES (:co, :d, :code, 'employee', 'کارمند', 'Employee') RETURNING id""",
            co=co["id"],
            d=dept,
            code=first,
        )
        await tx.exec(
            "UPDATE core.employees SET status = 'dismissed', dismissed_at = now() WHERE id = :id",
            id=emp,
        )
        third = await tx.scalar("SELECT core.issue_employee_code(:co, :d)", co=co["id"], d=dept)
        assert third == f"{co['code']}-GROWTH-03"
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "HQA01",
            tx.exec(
                "UPDATE core.employee_code_seq SET next_no = 1 WHERE company_id = :co", co=co["id"]
            ),
        )
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "HQV01", tx.exec("UPDATE core.employees SET status = 'active' WHERE id = :id", id=emp)
        )
    async with hub.db.tx([co["id"]]) as tx:
        await _expect(
            "23505",
            tx.exec(
                """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en)
                   VALUES (:co, :d, :code, 'employee', 'x', 'x')""",
                co=co["id"],
                d=dept,
                code=first,
            ),
        )


async def test_append_only_tables_reject_update_and_delete_for_everyone(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    thread = f"{co['code']}-CEO"
    async with hub.db.tx([co["id"]]) as tx:
        tid = await tx.scalar("SELECT id FROM msg.threads WHERE code = :c", c=thread)
        msg = await tx.one(
            "SELECT * FROM msg.post(:t, 'owner', 'owner', 'سلام', NULL, NULL, 'text')", t=tid
        )
        assert msg["ref"] == f"{thread}-0001"
        await tx.exec(
            """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                   action_class, target_kind, target_ref)
               VALUES ('owner', 'owner', 'owner', :co, 'test.append', 'A0', 'test', 'x')""",
            co=co["id"],
        )
    conn = await superuser()
    try:
        for table, where in (
            ("msg.messages", f"id = '{msg['id']}'"),
            ("audit.entries", f"company_id = '{co['id']}'"),
        ):
            for stmt in (
                f"UPDATE {table} SET created_at = now() WHERE {where}"
                if table == "msg.messages"
                else f"UPDATE {table} SET summary = 'x' WHERE {where}",
                f"DELETE FROM {table} WHERE {where}",
                f"TRUNCATE {table} CASCADE",
            ):
                with pytest.raises(Exception) as info:
                    await conn.execute(stmt)
                assert getattr(info.value, "sqlstate", None) == "HQA01", stmt
        for table in (
            "cartable.resolutions",
            "cartable.ratings",
            "cartable.deliverables",
            "owner.interactions",
            "work.work_events",
            "files.files",
        ):
            # TRUNCATE fires the statement trigger even on an empty table.
            with pytest.raises(Exception) as info:
                await conn.execute(f"TRUNCATE {table} CASCADE")
            assert getattr(info.value, "sqlstate", None) == "HQA01", table
    finally:
        await conn.close()


async def test_audit_chain_detects_tampering(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        for i in range(3):
            await tx.exec(
                """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                       action_class, target_kind, target_ref, summary)
                   VALUES ('owner', 'owner', 'owner', :co, 'test.chain', 'A0', 'test', :ref, 'ok')""",
                co=co["id"],
                ref=f"r{i}",
            )
        ok = await tx.one("SELECT * FROM audit.verify_chain()")
        assert ok["ok"] is True and ok["first_bad_seq"] is None
        victim = await tx.scalar(
            "SELECT seq FROM audit.entries WHERE company_id = :co AND target_ref = 'r1'",
            co=co["id"],
        )
    conn = await superuser()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL session_replication_role = replica")  # bypass the trigger
            await conn.execute("UPDATE audit.entries SET summary = 'forged' WHERE seq = $1", victim)
            bad = await conn.fetchrow("SELECT * FROM audit.verify_chain()")
            assert bad["ok"] is False and bad["first_bad_seq"] == victim
            raise _Rollback
    except _Rollback:
        pass
    finally:
        await conn.close()
    async with hub.db.tx([co["id"]]) as tx:
        assert (await tx.one("SELECT * FROM audit.verify_chain()"))["ok"] is True


class _Rollback(Exception):
    pass


async def test_resolution_refs_are_gapless(hub: Hub) -> None:
    async with hub.db.tx([]) as tx:
        a = await tx.scalar("SELECT cartable.next_resolution_ref()")
    try:
        async with hub.db.tx([]) as tx:
            await tx.scalar("SELECT cartable.next_resolution_ref()")
            raise _Rollback
    except _Rollback:
        pass
    async with hub.db.tx([]) as tx:
        b = await tx.scalar("SELECT cartable.next_resolution_ref()")
    assert int(b[2:]) == int(a[2:]) + 1


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("كيك", "کیک"),
        ("می‌روم", "می روم"),  # ZWNJ becomes a space (v2)
        ("أحمد إمام آمد", "احمد امام امد"),
        ("مدرسة مؤسسه", "مدرسه موسسه"),
        ("سَلام", "سلام"),
        ("۱۲۳ و ١٢٣", "123 و 123"),
        ("  Hello   World ", "hello world"),
    ],
)
async def test_persian_normalisation(hub: Hub, raw: str, normal: str) -> None:
    async with hub.db.tx([]) as tx:
        assert await tx.scalar("SELECT core.fa_normalize(:t)", t=raw) == normal


async def test_lock_state_sees_the_holding_switch(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        assert await tx.scalar("SELECT control.lock_state(:co)", co=co["id"]) is None
        await tx.exec(
            "UPDATE control.kill_switches SET state = 'engaged', reason = 't' WHERE company_id = :co",
            co=co["id"],
        )
        assert await tx.scalar("SELECT control.lock_state(:co)", co=co["id"]) == "company"
        await tx.exec(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = :co",
            co=co["id"],
        )
    assert uuid.UUID(str(co["id"]))
