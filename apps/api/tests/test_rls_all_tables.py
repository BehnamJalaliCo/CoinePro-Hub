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
    "egress",
    "oversight",
    "people",
    "knowledge",
    "academy",
    "provisioning",
    "infra",
    "tools",  # 7.1 §2.12: tools.mcp_calls is a tenant table
    "org",  # 9.1: org.company_brands
)
# The tools schema's tables without a company (holding configuration, read by
# the api only): every other table there must carry company_id under RLS.
COMPANYLESS_TOOLS = {"accounts", "mcp_servers"}


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
                "quota_estimate_month": {"tokens": 1500000},
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
    # Prompt 9.1: a brand version of the company.
    await su.execute(
        """INSERT INTO org.company_brands (company_id, version, part, source, created_by_kind,
               created_by_code)
           VALUES ($1, 1, 'mark', '{"kind": "upload"}', 'owner', 'owner')""",
        co["id"],
    )
    # Prompt 09: a founding, its plan, a run and its event, a server, a listing
    # (the holding's in production; any company's here, to prove the isolation).
    founding = await su.fetchval(
        """INSERT INTO core.foundings (company_id, source, created_by_kind, created_by_code)
           VALUES ($1, '{"kind": "idea", "brief_md": "b"}', 'owner', 'owner') RETURNING id""",
        co["id"],
    )
    plan = await su.fetchval(
        """INSERT INTO provisioning.plans (company_id, company_code, founding_id, name, type, location,
               work_user, digest, created_by_kind, created_by_code)
           VALUES ($1, $2, $3, 'x-1', 'cpx22', 'fsn1', 'ops', repeat('a', 64), 'agent', 'x') RETURNING id""",
        co["id"],
        co["code"],
        founding,
    )
    prun = await su.fetchval(
        """INSERT INTO provisioning.runs (plan_id, company_id, sealed_digest)
           VALUES ($1, $2, repeat('a', 64)) RETURNING id""",
        plan,
        co["id"],
    )
    await su.execute(
        """INSERT INTO provisioning.run_events (run_id, company_id, seq, key, state)
           VALUES ($1, $2, 1, 'ssh-key', 'running')""",
        prun,
        co["id"],
    )
    await su.execute(
        """INSERT INTO infra.servers (company_id, plan_id, run_id, hetzner_id, name)
           VALUES ($1, $2, $3, $4, 'x-1')""",
        co["id"],
        plan,
        prun,
        abs(hash(co["code"])) % 1_000_000_000 + 1,
    )
    await su.execute("INSERT INTO infra.inventory (company_id, ok) VALUES ($1, true)", co["id"])
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
    # Prompt 08 §3, §5: an inquiry to the CEO, an errand and a planner item
    # (the holding's in production; any company's here, to prove the isolation).
    ceo_id = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co['code']}-CEO")
    await su.execute(
        """INSERT INTO oversight.inquiries (company_id, from_kind, from_code, to_employee_id, to_code,
               question_md, due_at, thread_code)
           VALUES ($1, 'agent', 'HQ-ADV', $2, $3, 'q', now() + interval '1 day', 'A')""",
        co["id"],
        ceo_id,
        f"{co['code']}-CEO",
    )
    errand = await su.fetchval(
        """INSERT INTO owner.errands (company_id, title_fa, brief_md, source)
           VALUES ($1, 't', 'b', 'text') RETURNING id""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO owner.planner_items (company_id, title_fa, at, errand_id, created_by_kind,
               created_by_code)
           VALUES ($1, 't', now(), $2, 'agent', 'HQ-PA')""",
        co["id"],
        errand,
    )
    # Prompt 08 §4, §9: a rubric, a star, a roll-up, a lesson and its adoption, a story.
    await su.execute(
        """INSERT INTO people.star_rubrics (company_id, version, criteria, by_kind, by_code)
           VALUES ($1, 1, '[{"key": "efficiency", "weight": 100}]', 'agent', $2)""",
        co["id"],
        f"{co['code']}-CEO",
    )
    await su.execute(
        """INSERT INTO people.stars (company_id, employee_id, week, stars, counted, by_kind, by_code)
           SELECT $1, id, DATE '2026-10-10', 4, true, 'agent', $2 FROM core.employees WHERE code = $3""",
        co["id"],
        f"{co['code']}-CEO",
        f"{co['code']}-TECH-MGR",
    )
    await su.execute(
        """INSERT INTO people.star_rollups (company_id, period, key, starts_on, ends_on, data)
           VALUES ($1, 'week', $2, DATE '2026-10-10', DATE '2026-10-17', '{}')""",
        co["id"],
        f"2026-{abs(hash(co['code'])) % 12 + 1:02d}-{abs(hash(co['id'])) % 28 + 1:02d}",
    )
    lesson = await su.fetchrow(
        """INSERT INTO knowledge.lessons (company_id, period, title_fa, body_md, by_kind, by_code)
           VALUES ($1, 'week:2026-10-10', 'درس', 'متن', 'agent', 'HQ-OVR') RETURNING id, ref""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO knowledge.lesson_adoptions (lesson_id, lesson_ref, company_id)
           VALUES ($1, $2, $3)""",
        lesson["id"],
        lesson["ref"],
        co["id"],
    )
    await su.execute(
        """INSERT INTO owner.stories (company_id, kind, author_kind, author_code, title_fa)
           VALUES ($1, 'post', 'agent', $2, 'استوری')""",
        co["id"],
        f"{co['code']}-CEO",
    )
    # Prompt 08 §2: the overseer's records about this company.
    prot = await su.fetchrow("SELECT id, ref FROM oversight.protocols ORDER BY ref LIMIT 1")
    if prot is None:  # a migration round-trip test ran before: one protocol row is enough
        prot = await su.fetchrow(
            """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
                   schedule, scope, severity, answerable, status, source, created_by_kind, created_by_code)
               SELECT id, 'PR-001', 1, 't', 'truth', 'c', 'rule', 'FREQ=DAILY', 'company', 'low', 'ceo',
                      'active', 'seed', 'service', 'seed' FROM core.companies WHERE kind = 'holding'
               RETURNING id, ref"""
        )
    run = await su.fetchval(
        """INSERT INTO oversight.protocol_runs (company_id, protocol_id, protocol_ref, version, method, by_kind,
               by_code) VALUES ($1, $2, $3, 1, 'rule', 'system', 'test') RETURNING id""",
        co["id"],
        prot["id"],
        prot["ref"],
    )
    finding = await su.fetchval(
        """INSERT INTO oversight.findings (company_id, run_id, severity, title_fa, answerable_kind,
               answerable_code, raised_by_kind, raised_by_code, due_at)
           VALUES ($1, $2, 'low', 'f', 'owner', 'owner', 'system', 'test', now()) RETURNING id""",
        co["id"],
        run,
    )
    await su.execute(
        """INSERT INTO oversight.finding_history (finding_id, company_id, by_kind, by_code, status)
           VALUES ($1, $2, 'system', 'test', 'open')""",
        finding,
        co["id"],
    )
    await su.execute(
        """INSERT INTO oversight.challenges (company_id, period, period_key, title_fa, due_at, judge_kind,
               judge_code, issued_by_code)
           VALUES ($1, 'week', current_date, 'c', now() + interval '1 day', 'agent', 'HQ-OVR', 'HQ-OVR')""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO oversight.orders (company_id, text_md, source, applies_to, created_by_kind,
               created_by_code) VALUES ($1, 'o', 'text', 'overseer', 'owner', 'owner')""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO oversight.holds (company_id, target_kind, target_ref, reason_md, held_by_kind,
               held_by_code) VALUES ($1, 'employee', $2, 'r', 'agent', 'HQ-OVR')""",
        co["id"],
        f"{co['code']}-RLS-HOLD",
    )
    await su.execute(
        "INSERT INTO oversight.compliance (company_id, day, score) VALUES ($1, current_date, 90)",
        co["id"],
    )
    await su.execute(
        """INSERT INTO oversight.watch (company_id, reason, since, until)
           VALUES ($1, 'owner', now() - interval '1 hour', now())""",
        co["id"],
    )
    # Prompt 07: one request of an agent's web tool.
    await su.execute(
        """INSERT INTO egress.log (company_id, actor, tool, class, method, host)
           VALUES ($1, $2, 'web.read', 'A0', 'GET', 'example.com')""",
        co["id"],
        f"{co['code']}-CEO",
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
    # Prompt 08 §6-§7: the skill library and the academy (the holding's in
    # production; any company's here, to prove the isolation).
    n = int(co["code"].encode().hex(), 16) % 900000 + 100000
    skill = await su.fetchval(
        """INSERT INTO knowledge.skills (company_id, ref, name_fa, summary_fa, scope, source,
               created_by_kind, created_by_code)
           VALUES ($1, $2, 'm', 's', '{}', 'text', 'owner', 'owner') RETURNING id""",
        co["id"],
        f"SK-{n}",
    )
    sv = await su.fetchval(
        """INSERT INTO knowledge.skill_versions (skill_id, company_id, version, body_md, source,
               precheck, created_by_kind, created_by_code)
           VALUES ($1, $2, 1, 'b', 'text', '{}', 'owner', 'owner') RETURNING id""",
        skill,
        co["id"],
    )
    role = f"r{n}"
    await su.execute(
        "INSERT INTO academy.curricula (company_id, role, version, modules) VALUES ($1, $2, 1, '[]')",
        co["id"],
        role,
    )
    await su.execute(
        """INSERT INTO academy.eval_suites (company_id, ref, role, title_fa, cases)
           VALUES ($1, $2, $3, 't', '[]')""",
        co["id"],
        f"EV-{n}",
        role,
    )
    teaching = await su.fetchval(
        """INSERT INTO academy.teachings (company_id, target, source, text_md, created_by_kind,
               created_by_code)
           VALUES ($1, '{}', 'text', 't', 'owner', 'owner') RETURNING id""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO academy.eval_runs (company_id, suite_ref, subject, purpose, skill_version_id,
               requested_by_kind, requested_by_code)
           VALUES ($1, $2, '{}', 'manual', $3, 'owner', 'owner')""",
        co["id"],
        f"EV-{n}",
        sv,
    )
    await su.execute(
        """INSERT INTO academy.addenda (company_id, role, version, text_md, teaching_id)
           VALUES ($1, $2, 1, 'a', $3)""",
        co["id"],
        role,
        teaching,
    )
    # Prompt 07 §3 (7.1 §2.12): one resolved MCP call of the company.
    await su.execute(
        """INSERT INTO tools.mcp_calls (company_id, run_id, actor_code, server_key, tool, class,
               outcome, args_sha256)
           VALUES ($1, $2, $3, 'crm', 'lookup', 'A0', 'resolved', $4)""",
        co["id"],
        run,
        f"{co['code']}-CEO",
        "a" * 64,
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
    assert "tools.mcp_calls" in {f"{r['s']}.{r['t']}" for r in tables}
    companyless = await su.fetch(
        """SELECT x.table_name AS t FROM information_schema.tables x
           WHERE x.table_schema = 'tools' AND x.table_type = 'BASE TABLE'
             AND NOT EXISTS (SELECT 1 FROM information_schema.columns c
                             WHERE c.table_schema = x.table_schema AND c.table_name = x.table_name
                               AND c.column_name = 'company_id')"""
    )
    assert {r["t"] for r in companyless} == COMPANYLESS_TOOLS
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
