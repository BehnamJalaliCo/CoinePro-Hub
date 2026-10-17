"""RLS between companies for EVERY new table (prompt 04 §10): a session scoped
to company A sees no row of company B, whatever the table."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import scoring
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up

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
    "agents",
    "ops",
    "workshop",
    "backup",
)


async def _fill(client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], co: str) -> None:
    """Rows of company `co` in (nearly) every table, through the real API."""
    h = owner["headers"]
    mgr, ceo = await agent_headers(f"{co}-TECH-MGR"), await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**mgr, **idem()},
        json={
            "kind": "hire",
            "title": "hire",
            "payload": {
                "company": co,
                "department": "TECH",
                "role": "sre",
                "title_fa": "کارشناس",
                "title_en": "Specialist",
                "reason": "r",
                "model": "claude-sonnet-5-5",
                "effort": "medium",
            },
        },
    )
    ref = r.json()["ref"]
    su = await step_up(hub, owner["session_id"], "decision.approve", ref)
    await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **su, **idem()}, json={})
    async with hub.db.tx(await hub.companies.ids()) as tx:
        emp = (await D.apply_effect(tx, ref, SYSTEM))["employee"]
    root = (
        await client.post(
            "/api/v1/work",
            headers={**h, **idem()},
            json={
                "company": co,
                "title": "t",
                "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
    ).json()
    child = (
        await client.post(
            f"/internal/v1/work/{root['id']}/delegate",
            headers=ceo,
            json={"to": f"{co}-TECH-MGR", "title": "c"},
        )
    ).json()
    leaf = (
        await client.post(
            f"/internal/v1/work/{child['id']}/delegate", headers=mgr, json={"to": emp, "title": "l"}
        )
    ).json()
    file = (
        await client.post(
            "/internal/v1/files",
            params={"name": "a.txt"},
            headers={**await agent_headers(emp), "Content-Type": "text/plain"},
            content=b"hello",
        )
    ).json()
    out = (
        await client.post(
            f"/internal/v1/work/{leaf['id']}/deliver",
            headers={**await agent_headers(emp), **idem()},
            json={"title": "o", "attachments": [file["id"]]},
        )
    ).json()["deliverable"]
    await client.post(
        f"/api/v1/deliverables/{out}/rating", headers={**h, **idem()}, json={"score": 7}
    )
    await client.post(
        f"/api/v1/threads/{co}-CEO/messages", headers={**h, **idem()}, json={"body": "سلام"}
    )
    await client.post(
        "/internal/v1/notifications", headers=ceo, json={"level": "info", "title_fa": "اطلاع"}
    )
    await client.post(
        "/api/v1/control/deploy-freeze",
        headers=h,
        json={
            "company": co,
            "until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "reason": "x",
        },
    )
    await client.post(
        "/api/v1/work",
        headers={**h, **idem()},
        json={
            "company": co,
            "department": "GROWTH",
            "title": "rec",
            "kind": "recurring",
            "escrow": {
                "token_cap_per_run": 1000,
                "usd_cap_per_month": "1",
                "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
            "schedule": {"rrule": "FREQ=DAILY", "timezone": "UTC"},
        },
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        dept = await tx.scalar("SELECT department_id FROM core.employees WHERE code = :c", c=emp)
        await scoring.recompute_department(tx, dept)


async def _fill_agents(su: Any, co: dict[str, Any]) -> None:
    """Prompt 05's tables: rows of `co` the runtime and the checker would write
    (superuser, test setup only)."""
    # Prompt 07: the backup's status, runs, snapshots and restore tests (the
    # holding's in production; any company's here, to prove the isolation).
    await su.execute(
        "INSERT INTO backup.status (company_id) VALUES ($1) ON CONFLICT DO NOTHING", co["id"]
    )
    await su.execute(
        "INSERT INTO backup.runs (company_id, at, ok) VALUES ($1, now(), true)", co["id"]
    )
    await su.execute(
        """INSERT INTO backup.snapshots (company_id, destination, snapshot_id, time)
           VALUES ($1, 'local', 'abcdef0123456789', now())""",
        co["id"],
    )
    await su.execute(
        "INSERT INTO backup.restore_tests (company_id, at, ok) VALUES ($1, now(), true)", co["id"]
    )
    # Prompt 06: the processing state of an upload.
    await su.execute(
        """INSERT INTO files.processing (file_id, company_id)
           SELECT id, company_id FROM files.files WHERE company_id = $1 LIMIT 1""",
        co["id"],
    )
    emp = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co['code']}-CEO")
    run = await su.fetchval(
        "SELECT id FROM agents.runs WHERE company_id = $1 ORDER BY queued_at LIMIT 1", co["id"]
    )
    assert run is not None  # the owner's message woke the CEO
    await su.execute(
        "INSERT INTO agents.steps (run_id, company_id, n) VALUES ($1, $2, 1)", run, co["id"]
    )
    # core.hiring (prompt 5.1) holds the holding's row only; a row of `co` here just
    # proves the policy (core.hiring_state() reads the holding's).
    await su.execute(
        "INSERT INTO core.hiring (company_id) VALUES ($1) ON CONFLICT DO NOTHING", co["id"]
    )
    await su.execute(
        "INSERT INTO core.employee_memory (company_id, employee_id, note) VALUES ($1, $2, 'n')",
        co["id"],
        emp,
    )
    site = await su.fetchval(
        "INSERT INTO ops.sites (company_id, url) VALUES ($1, $2) RETURNING id",
        co["id"],
        f"https://{co['code'].lower()}.example.test/",
    )
    await su.execute(
        "INSERT INTO ops.checks (site_id, company_id, ok) VALUES ($1, $2, false)", site, co["id"]
    )
    await su.execute(
        "INSERT INTO ops.incidents (company_id, site_id) VALUES ($1, $2)", co["id"], site
    )
    await su.execute("INSERT INTO ops.hub_health (company_id, data) VALUES ($1, '{}')", co["id"])
    # Prompt 06: the Code Workshop and the owner's orders.
    ws = await su.fetchval(
        """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
           VALUES ($1, $2, 'o/r', 'main', 'w', '{}') RETURNING id""",
        co["id"],
        f"{co['code']}-RLS",
    )
    grant = await su.fetchval(
        """INSERT INTO workshop.grants (company_id, workspace_id, actions, budget_usd, expires_at,
               granted_by_kind, granted_by_code)
           VALUES ($1, $2, '{read}', 1, now() + interval '1 day', 'owner', 'owner') RETURNING id""",
        co["id"],
        ws,
    )
    session = await su.fetchval(
        """INSERT INTO workshop.sessions (company_id, workspace_id, grant_id, title, writes,
               opened_by_kind, opened_by_code, driver_kind, driver_code, runtime, model, effort,
               last_seq)
           VALUES ($1, $2, $3, 't', false, 'owner', 'owner', 'owner', 'owner', 'fake', 'm', 'low', 1)
           RETURNING id""",
        co["id"],
        ws,
        grant,
    )
    await su.execute(
        """INSERT INTO workshop.events (session_id, company_id, seq, type, actor_kind, actor_code)
           VALUES ($1, $2, 1, 'state', 'system', 'workshop')""",
        session,
        co["id"],
    )
    await su.execute(
        "INSERT INTO workshop.approvals (session_id, company_id, action) VALUES ($1, $2, 'command')",
        session,
        co["id"],
    )
    await su.execute(
        "INSERT INTO owner.orders (company_id, text, source) VALUES ($1, 'o', 'text')", co["id"]
    )


@pytest.mark.usefixtures("hiring_open")  # agents propose hires (§18.11)
async def test_no_table_leaks_between_companies(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    a, b = await new_company(), await new_company()
    await _fill(client, hub, owner_session, b["code"])
    await _fill_agents(su, b)
    tables = await su.fetch(
        """SELECT c.table_schema AS s, c.table_name AS t FROM information_schema.columns c
           JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name
           WHERE c.column_name = 'company_id' AND x.table_type = 'BASE TABLE' AND c.table_schema = ANY($1::text[])
             AND NOT EXISTS (  -- partitions are reached through their parent only
                 SELECT 1 FROM pg_inherits i JOIN pg_class k ON k.oid = i.inhrelid
                 JOIN pg_namespace n ON n.oid = k.relnamespace
                 WHERE n.nspname = c.table_schema AND k.relname = c.table_name)
           ORDER BY 1, 2""",
        list(SCHEMAS),
    )
    assert len(tables) >= 18
    populated = []
    for row in tables:
        name = f"{row['s']}.{row['t']}"
        in_b = await su.fetchval(f"SELECT count(*) FROM {name} WHERE company_id = $1", b["id"])
        if in_b:
            populated.append(name)
        async with hub.db.tx([a["id"]]) as tx:
            seen = await tx.scalar(f"SELECT count(*) FROM {name} WHERE company_id = :b", b=b["id"])
        assert seen == 0, f"{name}: {seen} row(s) of another company visible"
        async with hub.db.tx([b["id"]]) as tx:
            assert (
                await tx.scalar(f"SELECT count(*) FROM {name} WHERE company_id = :b", b=b["id"])
                == in_b
            ), name
    # Nearly every tenant table really held rows of B during the check.
    assert len(populated) >= len(tables) - 2, sorted(
        {f"{r['s']}.{r['t']}" for r in tables} - set(populated)
    )


async def test_every_tenant_policy_evaluates_the_scope_once_per_query(su: Any) -> None:
    """Prompt 5.1 §3: migration 0009 put every tenant policy in the InitPlan
    form, `company_id = ANY ((SELECT <schema>.allowed_company_ids())::uuid[])`;
    a later migration that writes the old per-row form again fails here."""
    rows = await su.fetch(
        """SELECT n.nspname || '.' || c.relname || ':' || pol.polname AS name,
                  pg_get_expr(pol.polqual, pol.polrelid) AS qual,
                  pg_get_expr(pol.polwithcheck, pol.polrelid) AS chk
           FROM pg_policy pol JOIN pg_class c ON c.oid = pol.polrelid
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = ANY($1::text[]) OR n.nspname = 'llm'""",
        list(SCHEMAS),
    )
    tenant = [r for r in rows if "allowed_company_ids" in f"{r['qual']} {r['chk']}"]
    assert len(tenant) >= 40
    hoisted = re.compile(r"\( SELECT (core|llm)\.allowed_company_ids\(\) AS allowed_company_ids\)")
    per_row = re.compile(r"ANY \((core|llm)\.allowed_company_ids\(\)\)")
    for r in tenant:
        for expr in (r["qual"], r["chk"]):
            if expr and "allowed_company_ids" in expr:
                assert hoisted.search(expr) and not per_row.search(expr), (r["name"], expr)
