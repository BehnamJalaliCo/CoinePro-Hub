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
