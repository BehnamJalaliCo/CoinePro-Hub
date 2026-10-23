"""Prompt 14.1 §2.2, contract ⟨1.7.2⟩: Google ended the Gemini CLI's sign-in
for individuals. Every Gemini seat runs via the signed-in web profile; the CLI
player's "unavailable" answer is recorded with its reason; the app points the
owner to `make gemini-web-login`; code_review stays with GPT (Codex); and
migration 0029_1 moves only the seats the owner has not changed by hand."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from hq_api.domain import substitutes as S

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "0029_1_gemini_web.py"


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0029_1", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_gemini_seat_runs_via_web_and_code_review_stays_with_gpt() -> None:
    assert all(s["via"] == "web" for s in S.DEFAULT_SEATS["gemini"])
    assert S.DEFAULT_PLAYERS["gemini"]["capabilities"]["text"] == "web"
    gpt_review = next(s for s in S.DEFAULT_SEATS["gpt"] if s["seat"] == "code_review")
    gem_review = next(s for s in S.DEFAULT_SEATS["gemini"] if s["seat"] == "code_review")
    assert gpt_review["enabled"] is True and gpt_review["via"] == "cli"
    assert gem_review["enabled"] is False
    assert S._make("gemini") == "gemini-web-login"


def test_the_runners_unavailable_answer_is_accepted() -> None:
    d = S.DoneIn(ok=False, error="unavailable", status_reason="Gemini CLI ... discontinued")
    assert d.error == "unavailable"


async def test_the_seeded_gemini_seats_are_web_after_migrate(su: Any) -> None:
    rows = await su.fetch("SELECT seat, via FROM substitutes.seats WHERE player = 'gemini'")
    assert rows and all(r["via"] == "web" for r in rows)
    text = await su.fetchval(
        "SELECT capabilities ->> 'text' FROM substitutes.players WHERE player = 'gemini'"
    )
    assert text == "web"


@pytest.mark.parametrize("owner_changed", [False, True])
async def test_0029_1_moves_only_seats_the_owner_left_alone(su: Any, owner_changed: bool) -> None:
    m = _migration()
    tr = su.transaction()
    await tr.start()
    try:
        await su.execute(
            "UPDATE substitutes.seats SET via = 'cli' WHERE player = 'gemini' AND seat = 'long_read'"
        )
        if await su.fetchval(  # the audit is append-only: an earlier edit decides
            """SELECT 1 FROM audit.entries
               WHERE action = 'substitute.seats' AND target_ref = 'gemini'"""
        ):
            pytest.skip("an earlier test edited Gemini's seats in this database")
        if owner_changed:
            co = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
            await su.execute(
                """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id,
                       action, action_class, target_kind, target_ref, step_up, summary)
                   VALUES ('owner', 'owner', 'owner', $1, 'substitute.seats', 'A2', 'substitute',
                           'gemini', true, 'the owner set the seats')""",
                co,
            )
        await su.execute(m.UPGRADE)
        via = await su.fetchval(
            "SELECT via FROM substitutes.seats WHERE player = 'gemini' AND seat = 'long_read'"
        )
        assert via == ("cli" if owner_changed else "web")
        moved = await su.fetchval(
            """SELECT count(*) FROM audit.entries
               WHERE action = 'substitute.seats' AND target_ref = 'gemini:long_read'"""
        )
        assert moved == (0 if owner_changed else 1)
    finally:
        await tr.rollback()
