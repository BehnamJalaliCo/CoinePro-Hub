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
    # prompt 10 §1.1: revenue and support; every table there is a tenant table
    "revenue",
    "support",
    "growth",
    "feedback",
    "intake",
    # prompt 12 part A: the advisor's memos and triggers, the substitute players
    "advisor",
    "substitutes",
    # prompt 12 part B: briefings and letters; checked claims
    "reports",
    "quality",
    # prompt 13, the media half: the media studio (people.role_drafts is in people)
    "media",
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
        """INSERT INTO knowledge.skill_versions (skill_id, company_id, version, body_md, name_fa,
               summary_fa, scope, text_sha256, source, precheck, created_by_kind, created_by_code)
           VALUES ($1, $2, 1, 'b', 'm', 's', '{}', repeat('0', 64), 'text', '{}', 'owner', 'owner')
           RETURNING id""",
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
           VALUES ($1, $2, '{"kind": "skill", "ref": "SK-999", "version": 1}', 'manual', $3,
                   'owner', 'owner')""",
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


# Prompt 12 part A: the holding's own configuration of the substitute players
# (one row per player and seat, the holding's company_id under forced RLS):
# no other company ever has a row there, so the check cannot fill them for B.
HOLDING_ONLY = {"substitutes.players", "substitutes.seats"}


async def _fill_p12a(su: Any, co: dict[str, Any]) -> None:
    """Prompt 12 part A (migration 0027): one row of company `co` in every
    table of advisor and substitutes but the holding-only two."""
    c = co["id"]
    d = await su.fetchrow(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code)
           VALUES ($1, 'proposal', 'A1', 'rls', 'owner', 'owner') RETURNING id, ref""",
        c,
    )
    await su.execute(
        """INSERT INTO advisor.memos (company_id, decision_id, decision_ref, decision_version, mode, trigger,
               created_by_kind, created_by_code) VALUES ($1, $2, $3, 1, 'standard', 'owner', 'owner', 'owner')""",
        c, d["id"], d["ref"],
    )  # fmt: skip
    await su.execute(
        """INSERT INTO advisor.triggers (company_id, key, kind, day, state)
           VALUES ($1, 'budget:' || $2 || ':rls-' || gen_random_uuid(), 'budget', current_date, 'deferred')""",
        c, co["code"],
    )  # fmt: skip
    call = await su.fetchval(
        """INSERT INTO substitutes.calls (company_id, player, seat, via, caller_kind, caller_code, day, month_key,
               state) VALUES ($1, 'gpt', 'content_draft', 'cli', 'owner', 'owner', current_date, '1405-08',
               'skipped') RETURNING id""",
        c,
    )
    await su.execute(
        """INSERT INTO substitutes.logins (company_id, player, connection_key, expires_at, call_id)
           VALUES ($1, 'gpt', 'chatgpt-plus', now(), $2)""",
        c, call,
    )  # fmt: skip
    await su.execute(
        """INSERT INTO substitutes.creatives (company_id, kind, brief_md, placement, aspect, player, model,
               requested_by_kind, requested_by_code)
           VALUES ($1, 'image', 'rls', 'banner', '16:9', 'gpt', 'gpt-5.5', 'owner', 'owner')""",
        c,
    )


async def _fill_p12b(su: Any, co: dict[str, Any]) -> None:
    """Prompt 12 part B (migration 0027_1): one row of company `co` in each new
    table (reports, quality; people.department_ranks/hr_rounds; owner.notes,
    owner.decision_reminders; llm.waste_daily)."""
    c = co["id"]
    emp = await su.fetchrow(
        "SELECT id, department_id FROM core.employees WHERE company_id = $1 AND kind = 'manager' LIMIT 1",
        c,
    )
    work = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
           VALUES ($1, 'one_off', 'p12b', 'owner', 'owner') RETURNING id""",
        c,
    )
    dl = await su.fetchrow(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title)
           VALUES ($1, $2, $3, 'p12b') RETURNING id, ref""",
        c,
        work,
        emp["id"],
    )
    await su.execute(
        """INSERT INTO reports.briefings (company_id, kind, period_from, period_to, deliverable_id,
               deliverable_ref, text_md, audio_state)
           VALUES ($1, 'ceo_letter', current_date, current_date, $2, $3, 't', 'off')""",
        c,
        dl["id"],
        dl["ref"],
    )
    await su.execute(
        """INSERT INTO reports.ceo_letters (company_id, week, ceo_code, facts)
           VALUES ($1, current_date - ((extract(isodow FROM current_date)::int + 1) % 7), 'X-CEO', '{}')""",
        c,
    )
    await su.execute(
        """INSERT INTO people.department_ranks (company_id, period, key, department_id, department, score,
               parts, employees, rank_company)
           SELECT $1, 'week', '2000-01-01', id, code, 50, '{}', 1, 1 FROM core.departments
           WHERE company_id = $1 LIMIT 1""",
        c,
    )
    await su.execute(
        """INSERT INTO people.hr_rounds (company_id, month, evaluator_kind, evaluator_code, due_at, employees)
           VALUES ($1, '1405-08', 'agent', 'X-HR-MGR', now(), '[]')""",
        c,
    )
    await su.execute(
        """INSERT INTO llm.waste_daily (company_id, scope, day, total_tokens, total_usd, waste_tokens, waste_usd,
               share, items)
           VALUES ($1, 'company', current_date, 0, 0, 0, 0, 0, '[]')""",
        c,
    )
    await su.execute(
        "INSERT INTO owner.notes (company_id, text_md, source) VALUES ($1, 'n', 'text')", c
    )
    d = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code)
           VALUES ($1, 'proposal', 'A1', 'p12b', 'agent', 'x') RETURNING id""",
        c,
    )
    await su.execute(
        "INSERT INTO owner.decision_reminders (company_id, decision_id, kind) VALUES ($1, $2, 'age_24h')",
        c,
        d,
    )
    await su.execute(
        """INSERT INTO quality.claims (company_id, deliverable_id, deliverable_ref, claim_md, verdict,
               checked_by_kind, checked_by_code)
           VALUES ($1, $2, $3, 'c', 'confirmed', 'agent', 'HQ-OVR')""",
        c,
        dl["id"],
        dl["ref"],
    )


async def _fill_p10(su: Any, co: dict[str, Any]) -> None:
    """Prompt 10 §1.1: one row of company `co` in every table of revenue,
    support, growth, feedback and intake (migration 0025)."""
    c = co["id"]
    sub = "c" * 64
    acc = await su.fetchval(
        """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
               created_by_kind, created_by_code)
           VALUES ($1, 'lbank', 'lbank-affiliate-v2', 'lbank-aff', 'افیلیت', 'owner', 'owner')
           RETURNING id""",
        c,
    )
    await su.execute(
        "INSERT INTO revenue.days (company_id, account_id, day, complete) VALUES ($1, $2, current_date, true)",
        c,
        acc,
    )
    await su.execute(
        "INSERT INTO revenue.invitees (company_id, account_id, subject) VALUES ($1, $2, $3)",
        c,
        acc,
        sub,
    )
    await su.execute(
        """INSERT INTO revenue.pulls (company_id, account_id, kind, from_day, to_day, requested_by_kind,
               requested_by_code) VALUES ($1, $2, 'manual', current_date, current_date, 'owner', 'owner')""",
        c,
        acc,
    )
    await su.execute(
        """INSERT INTO revenue.alerts (company_id, account_id, kind, incident_key, note_fa)
           VALUES ($1, $2, 'drop', 'drop:test', 'افت')""",
        c,
        acc,
    )
    await su.execute("INSERT INTO support.settings (company_id) VALUES ($1)", c)
    await su.execute(
        "INSERT INTO support.channels (company_id, kind) VALUES ($1, 'telegram_bot')", c
    )
    cust = await su.fetchval(
        """INSERT INTO support.customers (company_id, channel, external_id, subject)
           VALUES ($1, 'telegram_bot', '42', $2) RETURNING id""",
        c,
        sub,
    )
    conv = await su.fetchrow(
        """INSERT INTO support.conversations (company_id, channel, customer_id)
           VALUES ($1, 'telegram_bot', $2) RETURNING id, ref""",
        c,
        cust,
    )
    msg = await su.fetchval(
        """INSERT INTO support.messages (company_id, conversation_id, direction, author, body, status)
           VALUES ($1, $2, 'in', 'customer', 'سلام', 'sent') RETURNING id""",
        c,
        conv["id"],
    )
    await su.execute(
        """INSERT INTO support.kb_articles (company_id, kind, question_fa, answer_md, sha256,
               proposed_by_kind, proposed_by_code)
           VALUES ($1, 'faq', 'سؤال', 'جواب', $2, 'owner', 'owner')""",
        c,
        "d" * 64,
    )
    file_id = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code, kind)
           VALUES ($1, 'h.json', 'application/pdf', 10, repeat('e', 64), $2, 'owner', 'owner',
                   'document') RETURNING id""",
        c,
        f"p10/{c}",
    )
    await su.execute(
        "INSERT INTO support.history_imports (company_id, file_id) VALUES ($1, $2)", c, file_id
    )
    await su.execute(
        """INSERT INTO support.shadow_runs (company_id, suite_ref, suite_version, requested_by_kind,
               requested_by_code) VALUES ($1, 'support-shadow-X', 1, 'owner', 'owner')""",
        c,
    )
    case = await su.fetchval(
        """INSERT INTO growth.rescue_cases (company_id, source, conversation_id, exchange, subject)
           VALUES ($1, 'support', $2, 'lbank', $3) RETURNING id""",
        c,
        conv["id"],
        sub,
    )
    await su.execute(
        """INSERT INTO growth.rescue_steps (case_id, company_id, kind, result_fa, by_kind, by_code)
           VALUES ($1, $2, 'check', 'دعوت‌شده نیست', 'service', 'worker')""",
        case,
        c,
    )
    await su.execute(
        """INSERT INTO growth.referral_checks (company_id, exchange, subject, ok, invitee, by_kind, by_code)
           VALUES ($1, 'lbank', $2, true, false, 'agent', 'X-SALES-01')""",
        c,
        sub,
    )
    await su.execute(
        """INSERT INTO growth.templates (company_id, purpose, body_fa, sha256, proposed_by_kind,
               proposed_by_code) VALUES ($1, 'safety', 'پشتیبانی Coine', $2, 'owner', 'owner')""",
        c,
        "f" * 64,
    )
    rule = await su.fetchval(
        """INSERT INTO growth.rules (company_id, kind, template_ref, template_version, channel,
               proposed_by_kind, proposed_by_code)
           VALUES ($1, 'csat', 'TM-0001', 1, 'telegram_bot', 'owner', 'owner') RETURNING id""",
        c,
    )
    await su.execute(
        """INSERT INTO growth.sends (company_id, rule_id, template, subject, channel, dedupe_key, status)
           VALUES ($1, $2, 'TM-0001@1', $3, 'telegram_bot', 'csat:test', 'skipped')""",
        c,
        rule,
        sub,
    )
    await su.execute(
        "INSERT INTO growth.opt_outs (company_id, subject, source) VALUES ($1, $2, 'message')",
        c,
        sub,
    )
    wave = await su.fetchval(
        """INSERT INTO growth.nps_waves (company_id, ref, quarter, opens_at, closes_at)
           VALUES ($1, $2, '2026Q4', now(), now() + interval '14 days') RETURNING id""",
        c,
        f"NP-2026Q4-{co['code']}",
    )
    nps = await su.fetchval(
        """INSERT INTO growth.nps_responses (wave_id, company_id, subject, score)
           VALUES ($1, $2, $3, 9) RETURNING id""",
        wave,
        c,
        sub,
    )
    await su.execute(
        """INSERT INTO growth.funnel_days (company_id, day, stage, count, source)
           VALUES ($1, current_date, 'referral_verified', 3, 'affiliate')""",
        c,
    )
    await su.execute(
        """INSERT INTO growth.leaks (company_id, stage, period, period_start, rate, median_rate, note_fa)
           VALUES ($1, 'min_balance', 'week', current_date, 0.1, 0.3, 'نشتی')""",
        c,
    )
    item = await su.fetchval(
        """INSERT INTO feedback.items (company_id, kind, area, title_fa) VALUES ($1, 'bug', 'app', 'خطا')
           RETURNING id""",
        c,
    )
    await su.execute(
        """INSERT INTO feedback.signals (company_id, item_id, source_ref, message_id, quote, tagged_by)
           VALUES ($1, $2, $3, $4, 'خطا', 'rule')""",
        c,
        item,
        conv["ref"],
        msg,
    )
    await su.execute(
        """INSERT INTO feedback.signals (company_id, source_ref, nps_response_id)
           VALUES ($1, $2, $3)""",
        c,
        f"NP-2026Q4-{co['code']}",
        nps,
    )
    await su.execute(
        """INSERT INTO feedback.keywords (company_id, pattern, kind, area, created_by_kind, created_by_code)
           VALUES ($1, 'خطا', 'bug', 'app', 'owner', 'owner')""",
        c,
    )
    src = await su.fetchval(
        "INSERT INTO intake.sources (company_id, kind) VALUES ($1, 'product') RETURNING id", c
    )
    await su.execute(
        "INSERT INTO intake.nonces (company_id, source_id, nonce) VALUES ($1, $2, 'n-1')", c, src
    )
    await su.execute(
        """INSERT INTO intake.events (company_id, source_id, kind, event_id, subject)
           VALUES ($1, $2, 'signup', 'e-1', $3)""",
        c,
        src,
        sub,
    )
    await su.execute(
        """INSERT INTO intake.rejections (company_id, source_id, kind, reason)
           VALUES ($1, $2, 'product', 'bad_signature')""",
        c,
        src,
    )


async def _fill_p13a_roles(su: Any, co: dict[str, Any]) -> None:
    """Prompt 13 §1.1 (migration 0028): a role draft of company `co`."""
    await su.execute(
        """INSERT INTO people.role_drafts (company_id, department_id, brief_md, requested_by_kind,
               requested_by_code)
           SELECT $1, id, 'یه تدوینگر پادکست', 'owner', 'owner' FROM core.departments
           WHERE company_id = $1 AND code = 'GROWTH'""",
        co["id"],
    )


async def _fill_p13a_media(su: Any, co: dict[str, Any]) -> None:
    """Prompt 13 §2 (migration 0028): one row of company `co` in every table of media."""
    c = co["id"]
    series = await su.fetchval(
        """INSERT INTO media.series (company_id, title_fa, kind, targets, schedule, format, checks,
               max_per_day, digest, proposed_by_kind, proposed_by_code)
           VALUES ($1, 'ریلز', 'reel', '[]', 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0', '{}', '{brand}', 2,
                   repeat('a', 64), 'owner', 'owner') RETURNING id""",
        c,
    )
    item = await su.fetchval(
        """INSERT INTO media.items (company_id, series_id, kind, title_fa, state, created_by_kind,
               created_by_code) VALUES ($1, $2, 'reel', 'آیتم', 'composing', 'owner', 'owner') RETURNING id""",
        c,
        series,
    )
    comp = await su.fetchval(
        """INSERT INTO media.compositions (company_id, item_id, n, format, sha256, source, by_kind, by_code)
           VALUES ($1, $2, 1, 'html', repeat('b', 64), '<html lang="fa" dir="rtl"></html>', 'agent', 'X')
           RETURNING id""",
        c,
        item,
    )
    await su.execute(
        """INSERT INTO media.render_jobs (company_id, item_id, composition_id, purpose, spec, requested_by)
           VALUES ($1, $2, $3, 'preview', '{}', 'X')""",
        c,
        item,
        comp,
    )
    await su.execute(
        """INSERT INTO media.publish_log (company_id, item_id, action, channel, placement, account, via,
               outcome, by_kind, by_code)
           VALUES ($1, $2, 'publish', 'telegram', 'telegram_post', 'telegram-x', 'api', 'error', 'service', 'media')""",
        c,
        item,
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
    await _fill_p10(su, b)
    await _fill_p12a(su, b)
    await _fill_p12b(su, b)
    await _fill_p13a_roles(su, b)
    await _fill_p13a_media(su, b)
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
    # Prompt 10 §1.1: no company-less table in the five new schemas.
    p10_tables = await su.fetch(
        """SELECT x.table_schema || '.' || x.table_name AS t FROM information_schema.tables x
           WHERE x.table_schema = ANY($1::text[]) AND x.table_type = 'BASE TABLE'""",
        ["revenue", "support", "growth", "feedback", "intake"],
    )
    assert len(p10_tables) >= 31
    assert {r["t"] for r in p10_tables} <= {f"{r['s']}.{r['t']}" for r in tables}
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
    assert len(populated) >= len(tables) - 2 - len(HOLDING_ONLY), sorted(
        {f"{r['s']}.{r['t']}" for r in tables} - set(populated)
    )
    # The holding-only tables hold the holding's rows and nobody else's.
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    for name in sorted(HOLDING_ONLY):
        others = await su.fetchval(f"SELECT count(*) FROM {name} WHERE company_id <> $1", holding)
        assert others == 0, name


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
