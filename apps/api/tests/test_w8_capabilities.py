"""The owner, 2026-11-06: a media director said «ابزارهای من به ChatGPT، Gemini یا DeepSeek اتصالی
ندارند» and «نمیدونه n8n کجاست». Every run and every talk now reads what the holding gives (live),
every working role may ask the outside players (the policy names the seats, a cover included), and a
CEO or a manager proposes an automation in one sentence that the owner seals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import capabilities as CAP
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p22_ops import DAILY_REPORT, route_answer, routes


async def test_the_capability_brief_names_every_helper_and_how(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(tx, co["id"], n8n_up=False)
    players = {p["player"]: p for p in b["outside_players"]}
    assert {"gpt", "gemini", "deepseek"} <= set(players)
    assert players["gpt"]["name"] == "ChatGPT" and "creative" in players["gpt"]["seats"]
    assert {"outside_model", "cover_image_video", "automation", "hire", "delegate", "owner"} <= set(
        b["how"]
    )
    assert "substitute.call" in b["how"]["cover_image_video"]
    assert "automation.propose" in b["how"]["automation"]
    assert b["automations"]["n8n"] == "not set up"
    assert set(b["your_company"]) >= {
        "connections",
        "links",
        "working_groups",
        "production_lines_on",
    }


async def test_a_manager_proposes_an_automation_and_the_owner_is_told(
    client: httpx.AsyncClient,
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = (await new_company())["code"]
    route_answer(monkeypatch, routes(DAILY_REPORT))
    r = await client.post(
        "/internal/v1/automations/propose",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"sentence_fa": "هر روز ساعت ۹ گزارش صبح را برایم بفرست"},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["state"] == "proposed" and a["company"] == co
    n = await su.fetchrow(
        """SELECT owner_visible, level FROM notify.notifications
           WHERE link_kind = 'automation' AND link_ref = $1""",
        a["ref"],
    )
    assert n is not None and n["owner_visible"] and n["level"] == "decision"
    # nothing runs before the owner's seal
    assert (
        await su.fetchval("SELECT state FROM growth.automations WHERE ref = $1", a["ref"])
        == "proposed"
    )
