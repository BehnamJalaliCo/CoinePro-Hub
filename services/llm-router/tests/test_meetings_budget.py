"""A meeting turn's limits in the router (prompt 11 §1.2, contract §20.1): the
meeting's own cap (the scope meeting:<ref>, from meta.meeting_cap, over every
company's calls of that meeting) and the meetings' daily share of the agents'
daily cap (MEETINGS_DAILY_SHARE; the war room is outside it). Real Postgres
and NATS (scripts/test-env.sh), like the oversight share's and the support
draft budget's tests; the ledger metadata the api's runner sends."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import asyncpg
import pytest
from pydantic import ValidationError

from llm_router.config import Settings
from llm_router.schemas import RunRequest
from llm_router.service import RouterError

from .conftest import FakeBackend, ok_result

BIG_DAY = 10_000_000  # a daily cap whose meetings' share never bites


def turn(company: str = "TY", **meta: Any) -> RunRequest:
    """One model call of a meeting turn: the TY CEO's, or the holding advisor's."""
    who = (
        {"actor_ref": "TY-CEO", "department": None, "role": "ceo"}
        if company == "TY"
        else {"actor_ref": "HQ-ADV", "department": None, "role": "advisor"}
    )
    return RunRequest(
        company_code=company,
        task_class="general",
        priority=2,
        prompt="statement",
        timeout_s=30,
        meta=meta or None,
        **who,
    )


async def refusal(su: asyncpg.Connection, call_id: str | None) -> tuple[str, str]:
    row = await su.fetchrow("SELECT status, error_class FROM llm.calls WHERE id = $1", call_id)
    assert row is not None
    return row["status"], row["error_class"]


# ------------------------------------------------------- the meeting's cap --
async def test_a_turn_over_the_meeting_cap_is_refused_and_counts_every_company(
    su: asyncpg.Connection, make_service: Any
) -> None:
    five_hundred = {"input_tokens": 300, "output_tokens": 50, "cache_read_tokens": 100,
                    "cache_write_tokens": 50}  # fmt: skip
    svc = make_service(subscription=FakeBackend(*(ok_result(**five_hundred) for _ in range(4))))
    svc.s = replace(svc.s, agent_daily_token_cap=BIG_DAY, meetings_daily_share=0.15)
    board = {"meeting": "MT-0001", "meeting_cap": 900, "meeting_kind": "board",
             "charter_docs": ["holding@3", "TY@1"]}  # fmt: skip

    assert (await svc.run(turn("HQ", **board), "t", 10_000)).status == "ok"  # 500, the holding's
    # Under the cap: TY's pre-check sees 500 < 900 (the holding's call counts); now 1000.
    assert (await svc.run(turn("TY", **board), "t", 10_000)).status == "ok"
    with pytest.raises(RouterError) as exc:
        await svc.run(turn("TY", **board), "t", 10_000)  # TY alone used 500; together 1000
    assert (exc.value.status_code, exc.value.code) == (429, "budget_exhausted")
    assert "meeting:MT-0001" in exc.value.message and "(1000/900)" in exc.value.message
    assert exc.value.retry_after is None  # only the owner raises a meeting's budget
    assert await refusal(su, exc.value.call_id) == ("rejected_budget", "meeting_budget")
    raw = await su.fetchval(
        "SELECT meta FROM llm.calls WHERE status = 'ok' ORDER BY started_at LIMIT 1"
    )
    meta = json.loads(raw) if isinstance(raw, str) else raw
    assert (meta["meeting"], meta["meeting_cap"], meta["charter_docs"]) == (
        "MT-0001", 900, ["holding@3", "TY@1"],
    )  # fmt: skip

    # Another meeting has its own cap; a cap sent as text is still a number.
    other = {**board, "meeting": "MT-0002", "meeting_cap": "900"}
    assert (await svc.run(turn("TY", **other), "t", 10_000)).status == "ok"
    # A cap of 0 or less (or no number at all) refuses at once, before any model call.
    for cap in (0, -5, "a lot"):
        with pytest.raises(RouterError) as exc:
            await svc.run(turn("TY", **{**board, "meeting": "MT-0003", "meeting_cap": cap}), "t",
                          10_000)  # fmt: skip
        assert exc.value.code == "budget_exhausted" and "(0/" in exc.value.message, cap
        assert await refusal(su, exc.value.call_id) == ("rejected_budget", "meeting_budget")


async def test_turns_of_an_older_week_do_not_count(
    su: asyncpg.Connection, make_service: Any
) -> None:
    svc = make_service(subscription=FakeBackend(ok_result(input_tokens=1000, output_tokens=0)))
    svc.s = replace(svc.s, agent_daily_token_cap=BIG_DAY)
    board = {"meeting": "MT-0004", "meeting_cap": 1000, "meeting_kind": "board"}
    await svc.run(turn("TY", **board), "t", 10_000)  # 1000 of 1000
    with pytest.raises(RouterError):
        await svc.run(turn("TY", **board), "t", 10_000)
    # The same ref's calls more than 7 days ago are outside the meeting's window.
    await su.execute(
        "UPDATE llm.calls SET started_at = started_at - interval '8 days'"
        " WHERE meta->>'meeting' = 'MT-0004'"
    )
    assert (await svc.run(turn("TY", **board), "t", 10_000)).status == "ok"


# ------------------------------------------------------ the meetings' share --
async def test_the_meetings_share_stops_a_board_turn_but_not_a_war_room(
    su: asyncpg.Connection, make_service: Any
) -> None:
    # 0.15 of a 1000-token day = 150 tokens for every meeting turn of the day.
    svc = make_service(
        subscription=FakeBackend(
            ok_result(input_tokens=4000, output_tokens=1000),  # the war room's: outside the share
            ok_result(input_tokens=100, output_tokens=20),
            ok_result(input_tokens=100, output_tokens=20),
        )
    )
    svc.s = replace(svc.s, agent_daily_token_cap=1000, meetings_daily_share=0.15)
    war = {"meeting": "MT-0010", "meeting_kind": "war_room"}  # no meeting cap
    assert (await svc.run(turn("TY", **war), "t", 10_000)).status == "ok"  # 5000, not counted
    assert (await svc.run(turn("TY", meeting="MT-0011", meeting_kind="board"), "t", 10_000)).status
    # Another company's meeting of the same day: the pre-check sees 120 < 150; now 240.
    company = {"meeting": "MT-0012", "meeting_kind": "company", "meeting_cap": 40_000}
    assert (await svc.run(turn("HQ", **company), "t", 10_000)).status == "ok"
    for args in ({"meeting": "MT-0011", "meeting_kind": "board"}, company):
        with pytest.raises(RouterError) as exc:
            await svc.run(turn("TY", **args), "t", 10_000)
        assert (exc.value.status_code, exc.value.code) == (429, "budget_exhausted")
        assert "meetings' share" in exc.value.message and "(240/150)" in exc.value.message
        assert exc.value.retry_after and 0 < exc.value.retry_after <= 86_400  # the next UTC day
        assert await refusal(su, exc.value.call_id) == ("rejected_budget", "meetings_share")
    # The war room goes on, and so does every call that is not a meeting turn.
    assert (await svc.run(turn("TY", **war), "t", 10_000)).status == "ok"
    assert (await svc.run(turn("TY"), "t", 10_000)).status == "ok"
    assert (await svc.run(turn("TY", meeting_kind="board"), "t", 10_000)).status == "ok"
    # A daily cap of 0 is nothing: no share either; the war room still runs.
    svc.s = replace(svc.s, agent_daily_token_cap=0)
    await su.execute("TRUNCATE llm.calls")
    with pytest.raises(RouterError) as exc:
        await svc.run(turn("TY", meeting="MT-0013", meeting_kind="strategy"), "t", 10_000)
    assert await refusal(su, exc.value.call_id) == ("rejected_budget", "meetings_share")
    assert (await svc.run(turn("TY", **war), "t", 10_000)).status == "ok"


async def test_no_meeting_meta_no_check(su: asyncpg.Connection, make_service: Any) -> None:
    svc = make_service()
    svc.s = replace(svc.s, agent_daily_token_cap=0, meetings_daily_share=0.0)
    # Neither limit applies to a call that names no meeting, whatever else its meta says.
    assert (await svc.run(turn("TY"), "t", 10_000)).status == "ok"
    plain = turn("TY", charter_docs=["holding@3"], meeting_cap=0, meeting_kind="board")
    assert (await svc.run(plain, "t", 10_000)).status == "ok"
    assert await su.fetchval("SELECT count(*) FROM llm.calls WHERE status <> 'ok'") == 0


# --------------------------------------------------------- meta and config --
def test_the_meeting_meta_keys() -> None:
    r = turn(meeting="MT-0001", meeting_cap=60_000, meeting_kind="board",
             charter_docs=["holding@3", "TY@1"])  # fmt: skip
    assert r.meta == {"meeting": "MT-0001", "meeting_cap": 60_000, "meeting_kind": "board",
                      "charter_docs": ["holding@3", "TY@1"]}  # fmt: skip
    for bad in (
        {"meeting_room": "MT-0001"},  # an unknown key is still refused
        {"meeting": ["MT-0001"]},  # a list only for the list keys
        {"charter_docs": ["x" * 33]},
        {"charter_docs": ["holding@3"] * 31},
        {"meeting_kind": "k" * 65},
    ):
        with pytest.raises(ValidationError):
            turn(**bad)


def test_the_meetings_share_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEETINGS_DAILY_SHARE", raising=False)
    assert Settings().meetings_daily_share == 0.15
    monkeypatch.setenv("MEETINGS_DAILY_SHARE", "")
    assert Settings().meetings_daily_share == 0.15
    monkeypatch.setenv("MEETINGS_DAILY_SHARE", "0.25")
    assert Settings().meetings_daily_share == 0.25
    for bad in ("1.2", "-0.1", "nan"):
        monkeypatch.setenv("MEETINGS_DAILY_SHARE", bad)
        with pytest.raises(ValueError, match="MEETINGS_DAILY_SHARE"):
            Settings()
