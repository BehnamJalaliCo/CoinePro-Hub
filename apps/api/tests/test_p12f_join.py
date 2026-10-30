"""Prompt 12 laid on prompt 11 (r12f): the migration chain, the decision kind
CHECK at the head, the one deploy payload (11's window and conflicts beside
12's diff), and the advisor's OKR trigger on 11's real key results."""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from hq_api.domain import advisor as A
from hq_api.domain import decisions as D
from hq_api.domain import gov_common as G
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p12b_cards import card, repo  # noqa: F401 - the bare repository fixture

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _revisions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for f in VERSIONS.glob("*.py"):
        tree = ast.parse(f.read_text())
        values = {
            t.id: n.value.value
            for n in tree.body
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        if "revision" in values:
            out[str(values["revision"])] = values.get("down_revision")
    return out


async def test_the_chain_runs_through_prompt_11_then_prompt_12(su: Any) -> None:
    rev = _revisions()
    assert rev["0026"] == "0025" and rev["0026_1"] == "0026"
    assert rev["0027"] == "0026_1" and rev["0027_1"] == "0027" and rev["0027_2"] == "0027_1"
    # ⟨1.6⟩ prompt 13 sits on prompt 12 final: 0027_2 -> 0028 -> 0028_1;
    # ⟨1.7⟩ prompt 14 on prompt 13: 0028_1 -> 0029 (the head)
    assert rev["0028"] == "0027_2" and rev["0028_1"] == "0028" and rev["0029"] == "0028_1"
    # ⟨1.7.2⟩ prompt 14.1: 0029 -> 0029_1 (the Gemini seats via web; no kind CHECK)
    assert rev["0029_1"] == "0029"
    # prompt 15: 0029_1 -> 0030 (deliverables seen, category, filed)
    assert rev["0030"] == "0029_1"
    heads = set(rev) - {d for d in rev.values() if d}
    assert rev["0031"] == "0030"  # 15.2: delete a company, the simple founding
    assert heads == {"0031"}
    assert await su.fetchval("SELECT version_num FROM alembic_version_api") == "0031"


async def test_the_kind_check_holds_every_kind_and_is_validated(su: Any) -> None:
    check = await su.fetchval(
        """SELECT pg_get_constraintdef(oid) FROM pg_constraint
           WHERE conname = 'decisions_kind_check' AND conrelid = 'cartable.decisions'::regclass"""
    )
    for kind in D.KINDS:
        assert f"'{kind}'" in check, kind
    assert await su.fetchval(
        """SELECT convalidated FROM pg_constraint
           WHERE conname = 'decisions_kind_check' AND conrelid = 'cartable.decisions'::regclass"""
    )


def test_one_deploy_payload_holds_both_prompts_fields() -> None:
    fields = set(D.DeployPayload.model_fields)
    assert {
        "head_sha",
        "window",
        "calendar_conflicts",
        "diff",
        "diff_unavailable",
        "second_review",
    } <= fields
    p = D.validate_payload(
        "deploy",
        {
            "repo": "acme/app",
            "pr_url": "https://github.com/acme/app/pull/3",
            "head_sha": "0a1b2c3d4e5f",
            "window": {"from": "2026-11-01T10:00:00Z", "to": "2026-11-01T12:00:00Z"},
        },
    )
    assert p["window"] and p["head_sha"] == "0a1b2c3d4e5f"


async def test_a_deploy_card_has_its_window_its_conflicts_and_its_diff(
    client: httpx.AsyncClient,
    repo: Any,  # noqa: F811 - the fixture imported above
) -> None:
    co, name = repo["co"], repo["name"]
    head = repo["repo"].change(11, "print('three')\n")
    body = card(name, 11, head)
    start = datetime.now(UTC) + timedelta(days=3)
    body["payload"]["window"] = {
        "from": start.isoformat(),
        "to": (start + timedelta(hours=1)).isoformat(),
    }
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co['code']}-TECH-MGR"), **idem()},
        json=body,
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["head_sha"] == head and p["diff"]["head_sha"] == head
    assert p["window"] is not None and isinstance(p["calendar_conflicts"], list)


async def test_the_okr_trigger_reads_prompt_11s_key_results(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    today = date.today()
    quarter = G.quarter_of(today)
    start, end = G.quarter_bounds(quarter)
    # The second half of the quarter, where the trigger looks.
    late = start + timedelta(days=int((end - start).days * 0.75))
    ob = await su.fetchval(
        """INSERT INTO governance.objectives (company_id, quarter, title_fa, owner_kind, owner_code, status,
               activated_at, created_by_kind, created_by_code)
           VALUES ($1, $2, 'رشد', 'agent', $3, 'active', now(), 'agent', $3) RETURNING id""",
        co["id"],
        quarter,
        f"{co['code']}-CEO",
    )
    kr = await su.fetchval(
        """INSERT INTO governance.key_results (company_id, objective_id, title_fa, metric_fa, start, target, current)
           VALUES ($1, $2, 'کاربر فعال', 'کاربر', 0, 100, 10) RETURNING ref""",
        co["id"],
        ob,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        fired = await A.detect(tx, late)
    mine = [t for t in fired if t["kind"] == "okr" and t["facts"]["key_result"] == kr]
    assert mine and mine[0]["facts"]["progress"] == 0.1 and mine[0]["facts"]["pace"] < 0.7
    assert mine[0]["company_id"] == co["id"]
    # In the first half it does not fire.
    early = start + timedelta(days=5)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert not [
            t for t in await A.detect(tx, early) if t.get("facts", {}).get("key_result") == kr
        ]
