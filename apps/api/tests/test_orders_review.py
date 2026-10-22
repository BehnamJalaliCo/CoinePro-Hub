"""Review of prompt 6 (06.1 §2-§3), voice orders: a role named outright beats a
question word, an order's work is due on a day (so the planner has it), and a
code route the model found opens a session only when a rule agrees."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.db import Database
from hq_api.domain import orders as O
from hq_api.hub import Hub
from hq_api.workshop.runtime import FakeRuntime

from .test_orders import FakeRouter, fake, no_model, order, work_row  # noqa: F401 - fixtures
from .test_workshop import grant, workspace


def test_a_title_beats_a_question_word() -> None:
    assert O.roles_addressed(O.normalise("به مدیر فنی FX بگو چطور")) == ["TECH"]
    assert O.roles_addressed(O.normalise("چرا فروش TY کم شد")) == []  # a topic, not a person
    assert O.is_title("CTO") and O.is_title("مدیرعامل") and not O.is_title("فروش")


async def test_a_named_role_receives_a_question_shaped_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    r = await order(client, owner, "به مدیر فنی FX بگو چطور سرور را امن‌تر کنیم؟")
    assert r.status_code == 201, r.text
    out = r.json()
    [route] = out["routes"]
    assert (route["company"], route["to"], route["kind"]) == ("FX", "FX-TECH-MGR", "work")
    assert out["routed_by"] == "rules" and no_model == []
    # A question about a topic still goes to the advisor.
    r = await order(client, owner, "چرا فروش TY این هفته کم شد؟")
    [route] = r.json()["routes"]
    assert (route["to"], route["kind"]) == ("HQ-ADV", "question")


async def _due(su: Any, ref: str) -> datetime:
    value: datetime = await su.fetchval("SELECT due_at FROM work.work WHERE ref = $1", ref)
    return value


async def test_an_orders_work_is_due_and_in_the_planner(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    tz = ZoneInfo(
        await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    )
    today = datetime.now(tz).date()
    cases = [
        ("به مدیر مالی TY بگو گزارش ماهانه را تا فردا بفرستد", 1),
        ("به مدیر مالی TY بگو گزارش هزینه‌ها را پس فردا بفرستد", 2),
        ("به مدیر مالی TY بگو صورت حساب‌ها را مرتب کند", 3),  # no day said: the default
    ]
    for text, days in cases:
        r = await order(client, owner, text)
        assert r.status_code == 201, r.text
        [route] = r.json()["routes"]
        due = (await _due(su, route["work_ref"])).astimezone(tz)
        assert due.date() == today + timedelta(days=days) and (due.hour, due.minute) == (23, 59)
        planner = await client.get(
            "/api/v1/planner",
            headers=owner,
            params={"from": str(today), "to": str(today + timedelta(days=days))},
        )
        assert planner.status_code == 200, planner.text
        refs = [i["ref"] for d in planner.json()["days"] for i in d["items"]]
        assert route["work_ref"] in refs, text


async def test_a_model_found_code_route_waits_for_a_rule_or_the_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
    owner_db: Database,
    fake: FakeRuntime,  # noqa: F811
) -> None:
    co = await new_company()
    ws = await workspace(owner_db, co)
    await grant(client, hub, owner_session, ws, driver=None)
    saved = (hub.temporal, hub.settings, wk["acts"].router)
    hub.temporal = wk["client"]
    hub.settings = dataclasses.replace(hub.settings, task_queue=wk["tq"])
    wk["acts"].router = FakeRouter(
        {"routes": [{"company": co["code"], "to": ws, "kind": "code", "summary_fa": "کار کد"}]}
    )
    try:
        # No code word: the model alone said "code"; no session opens by itself.
        r = await order(client, owner, "صفحه‌ی ورود مشتری‌ها کند شده، رسیدگی کنید")
        assert r.status_code == 201, r.text
        out = r.json()
        [route] = out["routes"]
        assert out["routed_by"] == "model" and route["kind"] == "code"
        assert not route.get("session_ref") and route["decision_ref"] and route["note_fa"]
        opened = await su.fetchval(
            """SELECT count(*) FROM workshop.sessions s
               JOIN workshop.workspaces w ON w.id = s.workspace_id WHERE w.code = $1""",
            ws,
        )
        assert opened == 0
        kind = await su.fetchval(
            "SELECT kind FROM cartable.decisions WHERE ref = $1", route["decision_ref"]
        )
        assert kind == "code_session"
        # A code word the rules know (the company is still the model's): it goes on.
        r = await order(client, owner, "یک باگ در صفحه‌ی ورود مشتری‌ها هست، درستش کنید")
        [route] = r.json()["routes"]
        assert r.json()["routed_by"] == "model" and route["session_ref"]
        assert fake.log_[route["session_ref"]][0]["kind"] == "start"
    finally:
        hub.temporal, hub.settings, wk["acts"].router = saved


@pytest.mark.parametrize(
    ("text", "days"),
    [("همین امروز", 0), ("تا فردا", 1), ("پس فردا", 2), ("هفته بعد", 7), ("هر وقت شد", 3)],
)
def test_due_words(text: str, days: int) -> None:
    assert O.due_days(text) == days
