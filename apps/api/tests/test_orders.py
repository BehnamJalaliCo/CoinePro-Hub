"""Prompt 06 §5: the owner's voice orders (contract §17.4): rules first, then
the light model through the worker, then the advisor; each kind carried out."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.agents.clients import ModelCall
from hq_api.db import Database
from hq_api.domain import orders as O
from hq_api.hub import Hub
from hq_api.workshop.runtime import FakeRuntime

from .conftest import idem
from .test_workshop import grant, workspace


@pytest.fixture
def fake(hub: Hub) -> Any:
    rt = FakeRuntime()
    hub.workshop = rt
    yield rt
    hub.workshop = None


SECRET = "sk-ant-api03-" + "abcdefghijklmnopqrstuvwxyz012345"  # a key shape, not a real one


async def order(
    client: httpx.AsyncClient, owner: dict[str, str], text: str, **over: Any
) -> httpx.Response:
    return await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": text, "source": "voice", **over},
    )


async def work_row(su: Any, ref: str) -> Any:
    return await su.fetchrow(
        """SELECT w.depth, w.parent_id, w.created_by_kind, e.code AS assignee, w.brief, w.title
           FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1""",
        ref,
    )


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    async def refuse(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> None:
        calls.append(req)

    monkeypatch.setattr(workflows_client, "route_order", refuse)
    return calls


async def test_a_named_manager_is_reached_by_the_rules_alone(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, no_model: list[Any]
) -> None:
    r = await order(client, owner, "به مدیر فنی FX بگو گزارش امنیت سرور را تا فردا آماده کند")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["routed_by"] == "rules" and no_model == []  # no model was asked
    [route] = out["routes"]
    assert (route["company"], route["to"], route["kind"]) == ("FX", "FX-TECH-MGR", "work")
    w = await work_row(su, route["work_ref"])
    # The shortcut: straight to the manager, depth 1, a root work of the owner (depth 2 holds).
    assert w["assignee"] == "FX-TECH-MGR" and w["depth"] == 1 and w["parent_id"] is None
    assert w["created_by_kind"] == "owner" and out["ref"] in w["brief"]
    assert out["ref"].startswith("F-") and "FX-TECH-MGR" in out["summary_fa"]


async def test_an_ambiguous_order_goes_to_the_advisor(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    r = await order(client, owner, "یک کاری برای بهتر شدن اوضاع انجام بده")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["routed_by"] == "advisor"
    [route] = out["routes"]
    assert route["kind"] == "question" and route["to"] == "HQ-ADV"
    body = await su.fetchval(
        """SELECT m.body FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = 'A' AND m.ref = $1""",
        route["message_ref"],
    )
    assert "مسیرش روشن نبود" in body and out["ref"] in body


async def test_questions_go_to_the_advisor_and_meetings_to_the_ceo(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    r = await order(client, owner, "چرا فروش TY این هفته کم شد؟")
    [route] = r.json()["routes"]
    assert (route["company"], route["to"], route["kind"]) == ("TY", "HQ-ADV", "question")
    co = (await new_company())["code"]
    r = await order(client, owner, f"با مدیرعامل {co} جلسه بگذار درباره‌ی بودجه")
    [route] = r.json()["routes"]
    assert (route["kind"], route["to"]) == ("meeting", f"{co}-CEO")
    w = await work_row(su, route["work_ref"])
    assert w["title"].startswith("جلسه: ") and w["depth"] == 0 and w["parent_id"] is None


class FakeRouter:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.seen: list[dict[str, Any]] = []

    async def run(self, body: dict[str, Any], timeout_s: int) -> ModelCall:
        self.seen.append(body)
        return ModelCall(
            True, "ok", None, "call-1", O.MODEL, "low", "fake", self.answer, None, 120, 40
        )


async def test_the_light_model_routes_through_the_worker(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    fake_router = FakeRouter(
        {
            "routes": [
                {
                    "company": co,
                    "to": f"{co}-GROWTH-MGR",
                    "kind": "work",
                    "summary_fa": "کمپین تازه",
                },
                {"company": co, "to": "XX-HACK", "kind": "work", "summary_fa": "made up"},
                {"company": "NOPE", "to": "NOPE-CEO", "kind": "work", "summary_fa": "made up"},
            ]
        }
    )
    saved = (hub.temporal, hub.settings, wk["acts"].router)
    hub.temporal = wk["client"]
    hub.settings = dataclasses.replace(hub.settings, task_queue=wk["tq"])
    wk["acts"].router = fake_router
    try:
        r = await order(client, owner, f"یک کمپین برای مشتری‌های تازه بساز؛ کلیدش {SECRET} است")
    finally:
        hub.temporal, hub.settings, wk["acts"].router = saved
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["routed_by"] == "model"
    # Only what fits the directory survived.
    assert [(x["company"], x["to"], x["kind"]) for x in out["routes"]] == [
        (co, f"{co}-GROWTH-MGR", "work")
    ]
    [req] = fake_router.seen
    assert req["task_class"] == "order_routing" and req["priority"] == 1 and req["model"] == O.MODEL
    assert req["json_schema"] == O.ROUTES_SCHEMA
    # Masked before any model reads it; the agent's brief and the stored order too.
    assert SECRET not in json.dumps(req) and "[key]" in req["prompt"]
    w = await work_row(su, out["routes"][0]["work_ref"])
    assert SECRET not in w["brief"] and w["assignee"] == f"{co}-GROWTH-MGR"
    stored = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", out["ref"])
    assert SECRET not in stored


async def test_a_code_order_without_a_grant_asks_for_a_code_session(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    owner_db: Database,
) -> None:
    co = await new_company()
    ws = await workspace(owner_db, co)
    r = await order(client, owner, f"در ریپوی {co['code']} باگ صفحه‌ی ورود را درست کن")
    assert r.status_code == 201, r.text
    [route] = r.json()["routes"]
    assert (route["kind"], route["to"]) == ("code", ws) and route["decision_ref"]
    d = await su.fetchrow(
        "SELECT kind, status, action_class, proposer_kind, payload FROM cartable.decisions WHERE ref = $1",
        route["decision_ref"],
    )
    assert (d["kind"], d["status"], d["action_class"], d["proposer_kind"]) == (
        "code_session",
        "pending",
        "A1",
        "service",
    )
    payload = json.loads(d["payload"])
    assert payload["workspace"] == ws and "push_branch" in payload["actions"]


async def test_a_code_order_goes_into_the_workshop(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    owner_db: Database,
    fake: FakeRuntime,
) -> None:
    co = await new_company()
    ws = await workspace(owner_db, co)
    await grant(client, hub, owner_session, ws)
    # A live grant and no session yet: a new session under it.
    r = await order(client, owner, f"در ریپوی {co['code']} باگ صفحه‌ی ورود را درست کن")
    [route] = r.json()["routes"]
    assert route["kind"] == "code" and route["session_ref"] and not route.get("decision_ref")
    ref = route["session_ref"]
    assert fake.log_[ref][0]["kind"] == "start"
    # A running session of the workspace: the next code order goes into it.
    r = await order(client, owner, f"در ریپوی {co['code']} برای همین باگ تست هم بنویس")
    [route] = r.json()["routes"]
    assert route["session_ref"] == ref
    assert fake.log_[ref][-1]["kind"] == "message" and "تست" in fake.log_[ref][-1]["text"]


async def test_orders_are_kept_listed_streamed_and_replayable(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, no_model: list[Any]
) -> None:
    key = idem()
    body = {"text": "به مدیر مالی TY بگو گزارش ماهانه را بفرستد", "source": "text", "company": "TY"}
    first = await client.post("/api/v1/orders", headers={**owner, **key}, json=body)
    assert first.status_code == 201, first.text
    again = await client.post("/api/v1/orders", headers={**owner, **key}, json=body)
    assert again.json() == first.json() and again.headers.get("Idempotent-Replay") == "true"
    ref = first.json()["ref"]
    assert await su.fetchval("SELECT count(*) FROM work.work WHERE brief LIKE $1", f"%{ref}%") == 1
    listed = (await client.get("/api/v1/orders", headers=owner)).json()["items"]
    mine = next(o for o in listed if o["ref"] == ref)
    assert mine["text"] == body["text"] and mine["source"] == "text"
    assert mine["routes"][0]["to"] == "TY-FIN-MGR"
    holding = (await hub.companies.holding()).code
    env = await su.fetchrow(
        "SELECT subject, payload FROM core.outbox WHERE payload->>'ref' = $1 AND subject LIKE '%.order.routed'",
        ref,
    )
    assert env["subject"] == f"hq.core.{holding}.order.routed"
    assert json.loads(env["payload"])["data"]["routes"] == [
        {"company": "TY", "kind": "work", "to": "TY-FIN-MGR"}
    ]
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'order.route' AND target_ref = $1",
            ref,
        )
        == 1
    )
    r = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": "x", "file_id": "0195f1d2-7a3b-7c4d-8e5f-6a7b8c9d0e1f"},
    )
    assert r.status_code == 422


def test_the_rules_normalise_persian_text() -> None:
    assert O.normalise("مدیر فني  FX،") == "مدیر فنی fx"
    assert O.has(O.normalise("کوینه‌پرو اف‌ایکس"), "کوینه پرو اف ایکس")
    assert O.roles_named(O.normalise("به مدیر فنی بگو")) == ["TECH"]
    assert O.kind_of(O.normalise("وضعیت چطور است"), "وضعیت چطور است") == "question"
    assert O.kind_of(O.normalise("گزارش بده"), "گزارش بده?") == "question"
    assert O.kind_of(O.normalise("گزارش بده"), "گزارش بده") == "work"
    assert O.check_model("not json", {"companies": {}}) == []
