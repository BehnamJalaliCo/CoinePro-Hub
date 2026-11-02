"""Prompt 20.1 (contract §28.6 ⟨1.10.2⟩): what the holding spends. A
catalogue runs only on the owner's order, with a token cap per run; the
company's own Claude Code quota is named in the Token Treasury. Runners are
fakes; nothing leaves."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from hq_api.domain import catalogue as CAT
from hq_api.hub import Hub

from .test_p17_runners import pair, poll, take

pytestmark = pytest.mark.usefixtures("relay")

BROKEN = "this is not the section's JSON"


async def _end(
    client: httpx.AsyncClient, rn: dict[str, Any], job: dict[str, Any], tokens: int, text: str
) -> None:
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        headers=rn["h"],
        json={
            "exit_code": 0,
            "summary_fa": "ok",
            "usage": {"input_tokens": tokens // 10, "output_tokens": tokens // 10,
                      "cache_read_tokens": tokens - 2 * (tokens // 10), "model": "claude-x"},
            "data": {"result_fa": text},
        },
    )  # fmt: skip
    assert r.status_code == 200, r.text


async def test_a_catalogue_run_has_a_token_cap_and_a_second_try_only_within_it(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "cap-1")
    real = hub.settings
    hub.settings = replace(real, catalogue_run_tokens=1_200_000)
    try:
        r = await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    finally:
        hub.settings = real
    assert r.status_code == 202, r.text
    jobs = [await take(client, rn) for _ in CAT.SECTIONS]
    share = 1_200_000 // len(CAT.SECTIONS)
    for j in jobs:
        assert j["args"]["token_cap"] == share and j["args"]["max_turns"] == CAT.MAX_TURNS
    # a broken answer within the cap: asked once more, with the same share
    await _end(client, rn, jobs[0], 100_000, BROKEN)
    again = await take(client, rn)
    assert again["args"]["token_cap"] == share and "(دوباره)" in again["args"]["title"]
    # the run has spent what is left: a broken answer is not asked again
    await _end(client, rn, jobs[1], 1_000_000, BROKEN)
    r = await poll(client, rn)
    assert r.status_code == 204, r.text  # nothing queued: no second try
    row = await su.fetchrow(
        """SELECT meta FROM llm.calls WHERE task_class = 'server_claude'
             AND meta->>'server_job' = $1""",
        jobs[1]["id"],
    )
    meta = json.loads(row["meta"]) if isinstance(row["meta"], str) else row["meta"]
    assert meta["quota"] == "company_server" and meta["via"] == "catalogue"
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'cancelled' WHERE company_id = $1 AND state IN ('queued', 'running')",
        co["id"],
    )


def test_a_jobs_share_is_never_below_the_least_a_section_needs() -> None:
    assert CAT.job_cap(1_500_000, 6) == 250_000
    assert CAT.job_cap(100_000, 24) == CAT.MIN_JOB_TOKENS
    assert CAT.job_cap(1_000_000, 0) == 1_000_000


# ---------------------------------------------- §28.3 the watch, rule first --
@pytest.fixture
async def seeded(hub: Hub, owner_db: Any) -> None:
    from hq_api.domain import oversight as O
    from hq_common import charters

    holding = await hub.companies.holding()
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await O.seed_protocols(tx, holding.id, charters.load().root)


async def test_the_daily_security_sweep_reads_the_maps_by_rule_first(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    from hq_api.domain import oversight_checks as C

    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "sec-1")
    m = {
        "ports": [
            {"port": 443, "proto": "tcp", "bind": "0.0.0.0", "public": True},
            {"port": 5432, "proto": "tcp", "bind": "0.0.0.0", "public": True},
            {"port": 6379, "proto": "tcp", "bind": "127.0.0.1", "public": False},
        ],
        "disks": [{"mount": "/", "total_gb": 100.0, "used_gb": 85.0},
                  {"mount": "/data", "total_gb": 100.0, "used_gb": 20.0}],
    }  # fmt: skip
    await su.execute(
        "UPDATE infra.servers SET map = $2::jsonb WHERE id = $1::uuid",
        rn["server"]["id"],
        json.dumps(m),
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        found = [x for x in await C.security_signals(tx) if x.startswith(f"{co['code']}/")]
    assert found == [
        f"{co['code']}/sec-1: port 5432 bound publicly",
        f"{co['code']}/sec-1: disk / 85%",
    ]
    assert C.PRECHECKS["PR-140"] is not None and C.PRECHECKS["PR-141"] is not None
    await su.execute("UPDATE infra.servers SET map = NULL WHERE id = $1::uuid", rn["server"]["id"])


@pytest.mark.usefixtures("seeded")
async def test_without_anything_found_no_model_runs_and_with_it_the_model_starts_there(
    wk: dict[str, Any], su: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hq_api.domain import oversight_checks as C

    acts = wk["acts"].oversight
    await su.execute(
        "UPDATE oversight.protocol_runs SET work_id = NULL WHERE protocol_ref = 'PR-140'"
    )

    async def nothing(tx: Any) -> bool:
        return False

    monkeypatch.setitem(C.PRECHECKS, "PR-140", nothing)
    out = await acts.protocol_run("PR-140")
    assert out == {"protocol": "PR-140", "result": "pass", "why": "nothing_to_review"}

    async def something(tx: Any) -> bool:
        return True

    async def signals(tx: Any) -> list[str]:
        return ["TY/app-1: port 5432 bound publicly"]

    monkeypatch.setitem(C.PRECHECKS, "PR-140", something)
    monkeypatch.setattr(C, "security_signals", signals)
    out = await acts.protocol_run("PR-140")
    if out.get("deferred"):  # the day's model-backed runs were used by other tests
        return
    assert out.get("work"), out
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", out["work"])
    assert "port 5432 bound publicly" in brief


@pytest.mark.usefixtures("seeded")
async def test_the_code_review_of_every_repository_is_monthly(su: Any, owner_db: Any) -> None:
    from hq_api.domain import oversight as O

    cur = await su.fetchrow("SELECT * FROM oversight.current_protocols WHERE ref = 'PR-142'")
    assert cur["schedule"].startswith("FREQ=MONTHLY") and cur["calendar"] == "jalali"
    # a database seeded before 20.1 (the weekly seed version) gets a monthly one
    await su.execute(
        """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
               schedule, scope, evidence_md, severity, answerable, status, source, created_by_kind,
               created_by_code, calendar)
           SELECT company_id, ref, version + 1, 'بازبینی هفتگی کد هر مخزن', area, check_md, method,
                  'FREQ=WEEKLY;BYDAY=SA;BYHOUR=9;BYMINUTE=30', scope, evidence_md, severity, answerable,
                  status, 'seed', 'service', 'seed', 'gregorian'
           FROM oversight.current_protocols WHERE ref = 'PR-142'"""
    )
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        assert await O.monthly_code_review(tx) is True
        assert await O.monthly_code_review(tx) is False  # once
    cur = await su.fetchrow("SELECT * FROM oversight.current_protocols WHERE ref = 'PR-142'")
    assert cur["schedule"] == O.PR142_SCHEDULE and cur["title_fa"] == O.PR142_TITLE
