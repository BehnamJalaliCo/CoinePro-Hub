"""Prompt 20.1 (contract §28.6 ⟨1.10.2⟩): GPT's text goes through ChatGPT's web
chat (the owner, 2026-11-02), never Codex; Codex keeps only code review, off
until the owner asks; GPT is ready once its web profile is signed in; a
Codex limit never stops the web chat. Plus the Token Treasury's fixes:
treasury.usage takes what a role writes, and each company has its own daily
cap. The players, the CLI and the model are fakes; nothing leaves."""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, substitutes_headers
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import bench, per_day
from .test_p18_players import order, work_run

pytestmark = pytest.mark.usefixtures("relay")

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "0036_cost_gpt_web.py"
TEXT_SEATS = ("advisor_second_opinion", "overseer_cross_check", "assistant_errand")


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0036", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gpts_text_is_the_web_and_codex_keeps_only_code_review_off() -> None:
    gpt = S.DEFAULT_PLAYERS["gpt"]
    assert gpt["capabilities"]["text"] == "web" and gpt["web"] == "chatgpt-web"
    seats = {s["seat"]: s for s in S.DEFAULT_SEATS["gpt"]}
    assert all(seats[x]["via"] == "web" for x in TEXT_SEATS)
    assert seats["code_review"]["via"] == "cli" and seats["code_review"]["enabled"] is False
    assert [s for s in S.DEFAULT_SEATS["gpt"] if s["via"] == "cli"] == [seats["code_review"]]


async def test_the_seeded_gpt_is_on_the_web_after_migrate(su: Any) -> None:
    rows = {r["seat"]: r for r in await su.fetch(
        "SELECT seat, via, enabled FROM substitutes.seats WHERE player = 'gpt'")}  # fmt: skip
    assert all(rows[x]["via"] == "web" for x in TEXT_SEATS)
    assert rows["code_review"]["via"] == "cli"
    text = await su.fetchval(
        "SELECT capabilities ->> 'text' FROM substitutes.players WHERE player = 'gpt'"
    )
    assert text == "web"


@pytest.mark.parametrize("owner_changed", [False, True])
async def test_0036_moves_only_seats_the_owner_left_alone(su: Any, owner_changed: bool) -> None:
    m = _migration()
    tr = su.transaction()
    await tr.start()
    try:
        await su.execute(
            """UPDATE substitutes.seats SET via = 'cli' WHERE player = 'gpt'
                 AND seat = ANY($1::text[])""",
            list(TEXT_SEATS),
        )
        await su.execute(
            """UPDATE substitutes.players SET capabilities = jsonb_set(capabilities, '{text}', '"cli"'),
                   web_state = 'signed_in', status = 'off' WHERE player = 'gpt'"""
        )
        if await su.fetchval(
            "SELECT 1 FROM audit.entries WHERE action = 'substitute.seats' AND target_ref = 'gpt'"
        ):
            pytest.skip("an earlier test edited GPT's seats in this database")
        if owner_changed:
            co = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
            await su.execute(
                """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id,
                       action, action_class, target_kind, target_ref, step_up, summary)
                   VALUES ('owner', 'owner', 'owner', $1, 'substitute.seats', 'A2', 'substitute',
                           'gpt', true, 'the owner set the seats')""",
                co,
            )
        # the column exists already (the test database is migrated): only the data part
        await su.execute(m.UPGRADE.split("WITH moved AS", 1)[1].join(["WITH moved AS", ""]))
        vias = {r["seat"]: r["via"] for r in await su.fetch(
            "SELECT seat, via FROM substitutes.seats WHERE player = 'gpt'")}  # fmt: skip
        want = "cli" if owner_changed else "web"
        assert all(vias[x] == want for x in TEXT_SEATS)
        p = await su.fetchrow(
            "SELECT capabilities ->> 'text' AS t, status FROM substitutes.players WHERE player = 'gpt'"
        )
        assert (p["t"], p["status"]) == ("web", "ready")  # signed in on the web: ready at once
    finally:
        await tr.rollback()


async def test_a_gpt_work_goes_to_the_web_queue_never_to_codex(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, web=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = await order(client, owner, co, player="gpt")
        run = await work_run(su, w["id"])
        c = await agents.runner.claim(str(run["id"]))
        assert (c.state, c.final, c.code) == ("final", "done", "player_call")
        call = await su.fetchrow(
            """SELECT via, state, seat FROM substitutes.calls
               WHERE purpose_kind = 'work' AND purpose_ref = $1""",
            w["ref"],
        )
        assert (call["via"], call["state"], call["seat"]) == ("web", "queued", "assistant_errand")
        # nothing for the host's CLI dispatcher (Codex): the job waits for the web path
        r = await client.post("/internal/v1/substitutes/jobs/claim", headers=substitutes_headers())
        assert r.status_code == 200 and r.json().get("job") is None, r.text
        await su.execute(
            """UPDATE substitutes.calls SET state = 'skipped', state_reason = 'test', finished_at = now()
               WHERE purpose_ref = $1 AND state = 'queued'""",
            w["ref"],
        )


def test_a_codex_limit_never_stops_gpts_web_chat() -> None:
    now = datetime.now(UTC)
    p = {"status": "limited", "limited_until": now + timedelta(hours=2), "runner": "codex_cli",
         "web_state": "signed_in", "web_error_until": None, "web_last_failure": None,
         "login_state": "signed_in"}  # fmt: skip
    web = {"enabled": True, "via": "web"}
    cli = {"enabled": True, "via": "cli"}
    assert S._skip_reason(p, web, now) is None
    assert S._skip_reason(p, cli, now) == "limited"
    # its web chat's own limit is a hold on the web path
    held = {**p, "status": "ready", "web_error_until": now + timedelta(hours=1),
            "web_last_failure": "limited"}  # fmt: skip
    assert S._skip_reason(held, web, now) == "limited"
    # a web-only player's limit still stops its web
    gem = {**p, "runner": None}
    assert S._skip_reason(gem, web, now) == "limited"
    assert S.text_via({"capabilities": {"text": "web"}}) == "web"
    assert S.text_via({"capabilities": '{"text": "cli"}'}) == "cli"


async def test_gpt_is_ready_once_its_web_profile_is_signed_in(
    client: httpx.AsyncClient, su: Any
) -> None:
    before = await su.fetchrow(
        "SELECT login_state, web_state, status FROM substitutes.players WHERE player = 'gpt'"
    )
    try:
        await su.execute(
            """UPDATE substitutes.players SET status = 'off', login_state = 'signed_out',
                   web_state = 'signed_out' WHERE player = 'gpt'"""
        )
        r = await client.post("/internal/v1/substitutes/signed-in", headers=substitutes_headers(),
                              json={"player": "gpt", "via": "web"})  # fmt: skip
        assert r.status_code == 200, r.text
        row = await su.fetchrow(
            "SELECT status, login_state FROM substitutes.players WHERE player = 'gpt'"
        )
        assert (row["status"], row["login_state"]) == ("ready", "signed_out")
    finally:
        await su.execute(
            "UPDATE substitutes.players SET login_state = $1, web_state = $2, status = $3 WHERE player = 'gpt'",
            before["login_state"],
            before["web_state"],
            before["status"],
        )


# ------------------------------------------------- §28.6 the Token Treasury --
async def test_treasury_usage_takes_what_a_manager_writes(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    mgr = await agent_headers(f"{co['code']}-TECH-MGR")
    for params in ({"period": "week"}, {"scope": co["code"], "period": "day"},
                   {"department": "TECH"}, {"role": "manager", "period": "week"}):  # fmt: skip
        r = await client.get("/internal/v1/treasury/usage", headers=mgr, params=params)
        assert r.status_code == 200, (params, r.text)
        body = r.json()
        assert body["scope"] == co["code"] and isinstance(body["by_domain"], list)
        assert "by_department" in body
    r = await client.get("/internal/v1/treasury/usage", headers=mgr, params={"period": "year"})
    assert r.status_code == 422


async def test_a_company_stops_at_its_own_daily_cap(
    hub: Hub, su: Any, agents: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    cid = co["id"] if isinstance(co["id"], uuid.UUID) else uuid.UUID(str(co["id"]))
    runner = agents.runner
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await runner._company_cap_reached(tx, cid) is False
    await su.execute("UPDATE core.companies SET daily_token_cap = 0 WHERE id = $1", cid)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await runner._company_cap_reached(tx, cid) is False  # 0: only the hub's cap
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
               input_tokens, output_tokens, status, meta)
           VALUES (gen_random_uuid(), now(), $1, 'X-CEO', 'general', 3, 'agent_runner', 900, 200,
                   'ok', jsonb_build_object('run_id', gen_random_uuid()::text))""",
        cid,
    )
    await su.execute("UPDATE core.companies SET daily_token_cap = 1000 WHERE id = $1", cid)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await runner._company_cap_reached(tx, cid) is True
    await su.execute("UPDATE core.companies SET daily_token_cap = NULL WHERE id = $1", cid)
