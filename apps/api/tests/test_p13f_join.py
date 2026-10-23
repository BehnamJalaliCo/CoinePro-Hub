"""Prompt 13 laid on prompt 12 final (r13f: prompt 11, prompt 12 parts A and B,
§2, §3 and §13), and prompt 14 on it (r14f): one validating head (0029 since
prompt 14; 0028_1 was it on 13) whose kind CHECKs hold every kind of 11 to 14,
a down-and-up run that keeps a card of each later kind and finds the seeds
(the archive's open layer among them) again after the deploy's re-seed, the
system prompt in the contract's order (_common, the sealed charter, the role,
the department identity, the skills) and the templates' departments beside
prompt 11's, 12's and 14's system roles."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.domain import charter as CH
from hq_api.domain import decisions as D
from hq_api.hub import Hub
from hq_common.tool_status import GATEWAY_TOOLS

from .conftest import API_DIR, _run
from .test_hiring import _alembic, reseeded  # noqa: F401 - the round trip and its re-seed

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
# The kinds the revisions after 0025 add: prompt 11's six and three, prompt 13's
# four, prompt 14's two (0029).
LATER_KINDS = (
    "meeting_resolution",
    "charter_amendment",
    "knowledge_entry",
    "okr",
    "risk_acceptance",
    "authority_change",
    "media_series",
    "media_publish",
    "role_new",
    "email_send",
    "archive_schema",
    "archive_disposal",
)
HEAD = "0029_1"  # 14.1 sits on 0029 (which still validates the kind CHECKs)


def test_only_the_head_validates_the_kind_checks() -> None:
    """0026_1, 0027_2 and 0028_1 validated the CHECK while each was the head
    (0028_1 no longer does; production ran it once and is not touched); on 14
    the head is 0029 and every earlier re-add stays NOT VALID."""
    validating = {
        f.name
        for f in VERSIONS.glob("*.py")
        if re.search(r"VALIDATE CONSTRAINT (decisions|threads)_kind_check", f.read_text())
    }
    assert validating == {"0029_archive.py"}


async def _check(su: Any, table: str, name: str) -> tuple[str, bool]:
    row = await su.fetchrow(
        """SELECT pg_get_constraintdef(oid) AS def, convalidated FROM pg_constraint
           WHERE conname = $1 AND conrelid = $2::regclass""",
        name,
        table,
    )
    return str(row["def"]), bool(row["convalidated"])


async def test_the_head_holds_every_kind_of_11_to_14_validated(su: Any) -> None:
    check, valid = await _check(su, "cartable.decisions", "decisions_kind_check")
    assert valid
    for kind in (*D.KINDS, *LATER_KINDS):
        assert f"'{kind}'" in check, kind
    threads, valid = await _check(su, "msg.threads", "threads_kind_check")
    assert valid and "'legal'" in threads


@pytest.mark.usefixtures("reseeded")
async def test_a_round_trip_keeps_a_card_of_every_later_kind(su: Any) -> None:
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    tag = uuid.uuid4().hex[:8]
    for kind in LATER_KINDS:
        await su.execute(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
                   proposer_code)
               VALUES ($1, $2, $3, $4, 'owner', 'owner')""",
            holding,
            kind,
            D.ACTION_CLASS[kind],
            f"r13f {tag} {kind}",
        )
    before = await su.fetchval("SELECT count(*) FROM cartable.decisions")

    _alembic("downgrade", "0009")
    _alembic("upgrade", "head")

    assert await su.fetchval("SELECT version_num FROM alembic_version_api") == HEAD
    kinds = {
        r["kind"]
        for r in await su.fetch(
            "SELECT kind FROM cartable.decisions WHERE title LIKE $1", f"r13f {tag} %"
        )
    }
    assert kinds == set(LATER_KINDS)
    assert await su.fetchval("SELECT count(*) FROM cartable.decisions") == before
    _, valid = await _check(su, "cartable.decisions", "decisions_kind_check")
    assert valid
    _, valid = await _check(su, "msg.threads", "threads_kind_check")
    assert valid
    legal = await su.fetchval(
        """SELECT t.kind FROM msg.threads t JOIN core.companies c ON c.id = t.company_id
           WHERE c.kind = 'holding' AND t.code = 'L'"""
    )
    assert legal == "legal"
    # The round trip recreated the archive empty; the deploy's seed (the api's
    # migrate, as the `reseeded` fixture runs it after every round trip) brings
    # its open layer back, and the archivist is seated again.
    assert await su.fetchval("SELECT count(*) FROM archive.levels") == 0
    _run("hq_api.migrate", API_DIR, "hq", "HQ_DB_PASSWORD", "/api/src")
    levels = {r["key"] for r in await su.fetch("SELECT key FROM archive.levels")}
    assert {"public", "internal", "confidential", "secret"} <= levels
    assert await su.fetchval("SELECT count(*) FROM archive.classes") >= 11
    arc = await su.fetchval(
        "SELECT kind FROM core.employees WHERE code = 'HQ-ARC' AND status = 'active'"
    )
    assert arc == "system"


async def test_the_prompt_reads_common_charter_role_identity_then_skills(
    agents: Any,
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
) -> None:
    """Contract §20.2: the sealed charter (or the four red lines until one is
    sealed) after _common and before the role; §22.1: the department's
    identity after the role, before the skills."""
    from .test_agents import order, run, runs_of, step

    co = (await new_company())["code"]
    w = await order(client, owner, co, title="یک برنامه‌ی انتشار پیشنهاد بده", brief="رسانه")
    await su.execute(
        """UPDATE work.work SET assignee_id = (SELECT id FROM core.employees WHERE code = $1)
           WHERE id = $2""",
        f"{co}-MEDIA-MGR",
        uuid.UUID(w["id"]),
    )
    queued = [r for r in await runs_of(su, f"{co}-MEDIA-MGR") if r["state"] == "queued"]
    assert queued
    agents.fake.enqueue(f"{co}-MEDIA-MGR", step("دیدم.", ("activity.set", {"state": "working"})))
    calls = len(agents.fake.calls)
    out = await run(agents, queued[-1]["id"])
    assert out["state"] in ("done", "failed"), out
    system = next(c.system for c in agents.fake.calls[calls:] if c.actor_ref == f"{co}-MEDIA-MGR")
    assert system is not None and system.startswith("# Who you are")
    sealed = "# اساسنامه‌ی هلدینگ"
    charter_at = system.index(sealed) if sealed in system else system.index(CH.FALLBACK_TITLE)
    role_at = system.index("# Your role")
    identity_at = system.index("# Your department: Media and Design (MEDIA)")
    assert 0 < charter_at < role_at < identity_at
    if "# Skills" in system:
        assert identity_at < system.index("# Skills")
    doc = await su.fetchval("SELECT identity_doc FROM agents.runs WHERE id = $1", queued[-1]["id"])
    assert doc and doc.startswith(f"{co}-MEDIA@")


async def test_the_templates_hold_13s_departments_beside_11s_12s_and_14s_system_roles(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    tpl = {t["key"]: t for t in (await client.get("/api/v1/templates", headers=owner)).json()}
    std = {d["code"]: d for d in tpl["standard"]["blueprint"]}
    hold = {d["code"]: d for d in tpl["holding"]["blueprint"]}
    assert std["MEDIA"]["sort"] == 25 and std["MEDIA"]["head_role"] == "media_director"
    assert {"OVS", "AIOPS", "LEGAL"} <= set(hold)
    # Every department's tool ceiling is live on this hub: prompt 11's
    # governance tools (kpi.record, risk.raise, governance.read …) among them.
    for code, d in {**std, **{f"HQ:{k}": v for k, v in hold.items()}}.items():
        ceiling = set((d.get("mandate") or {}).get("tool_ceiling") or [])
        assert ceiling <= set(GATEWAY_TOOLS), (code, sorted(ceiling - set(GATEWAY_TOOLS)))
    rows = {
        r["suffix"]: dict(r)
        for r in await su.fetch(
            """SELECT substr(e.code, length(c.code) + 2) AS suffix, e.kind, e.role, d.code AS dept
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id
               LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE c.kind = 'holding'"""
        )
    }
    assert (rows["SEC"]["kind"], rows["SEC"]["role"], rows["SEC"]["dept"]) == (
        "system",
        "secretary",
        "AIOPS",
    )
    assert (rows["LIB"]["kind"], rows["LIB"]["role"]) == ("system", "librarian")
    # ⟨1.7⟩ prompt 14: the archivist, a system role of the holding without a department
    assert (rows["ARC"]["kind"], rows["ARC"]["role"], rows["ARC"]["dept"]) == (
        "system",
        "archivist",
        None,
    )
    assert (rows["LGL"]["kind"], rows["LGL"]["role"], rows["LGL"]["dept"]) == (
        "employee",
        "legal_counsel",
        "LEGAL",
    )
