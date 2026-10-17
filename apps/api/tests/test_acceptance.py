"""Prompt 04 §11 acceptance, end to end with fake agents: the real API, the
real Temporal worker (in-process), Postgres, NATS, OPA and a software
passkey for every owner signature.

On a fresh database (make check, CI) the first hire is TY-GROWTH-01 and the
first resolution M-0001; on a reused one the next free numbers are expected.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.app import create_app
from hq_api.hub import Hub

from .conftest import agent_headers, body_bytes, idem
from .test_control_treasury_stream import serve
from .test_identity import bearer, enrolled
from .test_identity import step_up as passkey_step_up
from .test_worker import wait_for


@pytest.fixture
async def acc(hub: Hub, wk: dict[str, Any], relay: None) -> Any:
    """The API wired to the in-process worker's task queue."""
    h = replace(hub, settings=replace(hub.settings, task_queue=wk["tq"]), temporal=wk["client"])
    return create_app(h)


async def _collect(
    url: str,
    headers: dict[str, str],
    params: dict[str, Any],
    want: Callable[[list[dict[str, Any]]], bool],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async with (
        httpx.AsyncClient(base_url=url, timeout=60) as c,
        c.stream("GET", "/api/v1/stream", headers=headers, params=params) as r,
    ):
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                if want(events):
                    return events
    return events


async def test_acceptance_scenario(acc: Any, hub: Hub, wk: dict[str, Any], su: Any) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=acc), base_url="https://hq.test"
    ) as client:
        key = await enrolled(hub, client)  # the owner's software passkey
        owner = await bearer(client, key)

        async def sign(action: str, target: str) -> dict[str, str]:
            return {"X-Step-Up": await passkey_step_up(client, key, owner, action, target)}

        next_emp = await su.fetchval(
            """SELECT COALESCE(max(s.next_no), 1) FROM core.employee_code_seq s
               JOIN core.departments d ON d.id = s.department_id JOIN core.companies c ON c.id = s.company_id
               WHERE c.code = 'TY' AND d.code = 'GROWTH'"""
        )
        next_res = (
            await su.fetchval(
                "SELECT COALESCE(max(value), 0) FROM core.counters WHERE name = 'resolution'"
            )
        ) + 1

        # ---- 2. «خط کامل اول»: proposal -> cartable + 🟡 -> passkey approval -> hire -> M-…
        async with serve(acc) as url:
            watcher = asyncio.create_task(
                _collect(
                    url,
                    owner,
                    {"topics": "decisions,notifications", "company": "TY"},
                    lambda ev: (
                        {"decision.created", "notification.created"} <= {e["type"] for e in ev}
                    ),
                )
            )
            await asyncio.sleep(0.5)
            r = await client.post(
                "/internal/v1/decisions",
                headers={**await agent_headers("TY-GROWTH-MGR"), **idem()},
                json={
                    "kind": "hire",
                    "title": "استخدام کارشناس رشد",
                    "what": "یک کارشناس برای کمپین‌ها",
                    "why": "حجم کار",
                    "risk": "low",
                    "reversible": True,
                    "quota_estimate": {"tokens": 1500000, "usd": "30"},
                    "payload": {
                        "company": "TY",
                        "department": "GROWTH",
                        "title_fa": "کارشناس رشد",
                        "title_en": "Growth Specialist",
                        "reason": "کمپین‌های فصل",
                        "duties": ["تولید محتوا"],
                        "model": "claude-sonnet-5-5",
                        "effort": "high",
                        "permissions": ["A0", "A1"],
                    },
                },
            )
            assert r.status_code == 201, r.text
            ref = r.json()["ref"]
            seen = await asyncio.wait_for(watcher, 30)
        assert any(e["type"] == "decision.created" and e["ref"] == ref for e in seen)
        assert any(
            e["type"] == "notification.created" and e["data"].get("level") == "decision"
            for e in seen
        )
        assert ref in {
            d["ref"]
            for d in (
                await client.get("/api/v1/decisions", headers=owner, params={"company": "TY"})
            ).json()["items"]
        }

        r = await client.post(
            f"/api/v1/decisions/{ref}/approve", headers={**owner, **idem()}, json={"note": "تأیید"}
        )
        assert r.status_code == 403 and r.json()["code"] == "step_up_required"
        r = await client.post(
            f"/api/v1/decisions/{ref}/approve",
            headers={**owner, **await sign("decision.approve", ref), **idem()},
            json={"note": "تأیید"},
        )
        assert r.status_code == 200, r.text
        approved = r.json()
        assert (
            approved["resolution"] == f"M-{next_res:04d}"
            and approved["seal"]["method"] == "passkey_uv"
        )
        employee = f"TY-GROWTH-{next_emp:02d}"

        async def hired() -> bool:
            e = await client.get(f"/api/v1/employees/{employee}", headers=owner)
            return e.status_code == 200

        await wait_for(hired, 60)
        emp = (await client.get(f"/api/v1/employees/{employee}", headers=owner)).json()
        assert (
            emp["hired_by_decision"] == ref
            and emp["model"]["model"] == "claude-sonnet-5-5"
            and emp["model"]["effort"] == "high"
        )
        assert (
            await su.fetchval(
                "SELECT effort FROM llm.assignments WHERE scope_type = 'role' AND scope_ref = $1",
                f"TY:{employee}",
            )
            == "high"
        )
        thread = (await client.get("/api/v1/threads/TY-GROWTH-MGR/messages", headers=owner)).json()[
            "items"
        ]
        bodies = " ".join(m["body"] for m in thread[-3:])
        assert approved["resolution"] in bodies and employee in bodies
        verify = (await client.get("/api/v1/audit/verify", headers=owner)).json()
        assert verify["ok"] is True and verify["first_bad_seq"] is None

        # ---- 3. owner -> CEO -> manager -> employee (depth 2), depth 3 refused, delivery, rating 8
        r = await client.post(
            "/api/v1/work",
            headers={**owner, **idem()},
            json={
                "company": "TY",
                "title": "کمپین معرفی نسخه‌ی جدید",
                "priority": "P2",
                "budget": {"tokens": 300000},
            },
        )
        root = r.json()
        assert root["assignee"]["code"] == "TY-CEO"
        child = (
            await client.post(
                f"/internal/v1/work/{root['id']}/delegate",
                headers=await agent_headers("TY-CEO"),
                json={"to": "TY-GROWTH-MGR", "title": "طراحی کمپین"},
            )
        ).json()
        leaf = (
            await client.post(
                f"/internal/v1/work/{child['id']}/delegate",
                headers=await agent_headers("TY-GROWTH-MGR"),
                json={"to": employee, "title": "نوشتن متن‌ها"},
            )
        ).json()
        assert (child["depth"], leaf["depth"]) == (1, 2)
        r = await client.post(
            f"/internal/v1/work/{leaf['id']}/delegate",
            headers=await agent_headers("TY-GROWTH-MGR"),
            json={"to": employee, "title": "عمق سوم"},
        )
        assert r.status_code in (
            403,
            409,
        )  # refused (policy for the leaf's assignee, the database for depth 3)
        r = await client.post(
            f"/internal/v1/work/{leaf['id']}/deliver",
            headers={**await agent_headers(employee), **idem()},
            json={
                "title": "متن‌های کمپین",
                "summary": "سه متن",
                "body": "...",
                "produced_with": {
                    "connection": "claude-max",
                    "model": "claude-sonnet-5-5",
                    "effort": "high",
                },
            },
        )
        assert r.status_code == 200, r.text
        out = r.json()["deliverable"]
        r = await client.post(
            f"/api/v1/deliverables/{out}/rating", headers={**owner, **idem()}, json={"score": 8}
        )
        assert r.status_code == 200 and r.json()["rating"]["score"] == 8
        score = (await client.get(f"/api/v1/employees/{employee}", headers=owner)).json()["score"]
        assert score["owner_avg"] == 8.0 and score["value"] is not None

        # ---- 4. recurring work proposed by an agent, approved by TY's CEO within quota, first run
        budget = body_bytes(
            {
                "budgets": [
                    {
                        "company": "TY",
                        "scope_type": "company",
                        "scope_ref": "TY",
                        "period": "month",
                        "usd_limit": "500",
                    }
                ]
            }
        )
        r = await client.put(  # the passkey signs this exact body (step-up target = its SHA-256)
            "/api/v1/budgets",
            headers={
                **owner,
                **await sign("budgets.update", hashlib.sha256(budget).hexdigest()),
                "Content-Type": "application/json",
            },
            content=budget,
        )
        assert r.status_code == 200
        r = await client.post(
            "/internal/v1/work",
            headers={**await agent_headers("TY-GROWTH-MGR"), **idem()},
            json={
                "department": "GROWTH",
                "title": "گزارش هفتگی شبکه‌های اجتماعی",
                "kind": "recurring",
                "escrow": {
                    "allowed_action_classes": ["A0", "A1"],
                    "token_cap_per_run": 40000,
                    "usd_cap_per_month": "10",
                    "expires_at": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
                },
                "schedule": {"rrule": "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10", "timezone": "Asia/Tehran"},
            },
        )
        assert r.status_code == 201, r.text
        recurring, rec_ref = r.json()["work"], r.json()["decision"]
        r = await client.post(
            f"/internal/v1/decisions/{rec_ref}/approve",
            headers={**await agent_headers("TY-CEO"), **idem()},
            json={},
        )
        assert r.status_code == 200 and r.json()["decided_by"]["code"] == "TY-CEO"

        async def first_run() -> bool:
            n = await su.fetchval(
                "SELECT count(*) FROM work.work WHERE recurrence_of = $1 AND budget_tokens = 40000",
                recurring["id"],
            )
            return bool(n)

        await wait_for(first_run, 60)
        w = (await client.get(f"/api/v1/work/{recurring['id']}", headers=owner)).json()
        assert w["escrow"]["status"] == "active" and w["schedule"]["status"] == "active"

        # ---- 5. Khalvat: only 🔴 goes out; «در نبودت چه گذشت» counts right
        try:
            r = await client.put(
                "/api/v1/owner/presence", headers={**owner, **idem()}, json={"khalvat": True}
            )
            assert r.status_code == 200 and r.json()["khalvat"] is True
            yellow = await client.post(
                "/internal/v1/notifications",
                headers=await agent_headers("TY-CEO"),
                json={"level": "decision", "title_fa": "یک تصمیم کوچک"},
            )
            red = await client.post(
                "/internal/v1/notifications",
                headers=await agent_headers("TY-CEO"),
                json={"level": "urgent", "category": "service_down", "title_fa": "خرابی پرداخت"},
            )
            assert yellow.json()["state"] == "held" and red.json()["state"] == "delivered"
            unread = (
                await client.get(
                    "/api/v1/notifications",
                    headers=owner,
                    params={"company": "TY", "unread": "true"},
                )
            ).json()["items"]
            ids = {n["id"] for n in unread}
            assert red.json()["id"] in ids and yellow.json()["id"] not in ids
        finally:
            r = await client.put(
                "/api/v1/owner/presence", headers={**owner, **idem()}, json={"khalvat": False}
            )
        assert r.json()["khalvat"] is False
        away = (await client.get("/api/v1/owner/away-summary", headers=owner)).json()
        levels = away["notifications"]["by_level"]
        assert levels.get("urgent", 0) >= 1 and levels.get("decision", 0) >= 1
        ty = next(c for c in away["companies"] if c["company"] == "TY")
        assert ty["notifications_new"] >= 2

        # ---- 6. kill switch TY -> TY agent writes get 423 -> release with step-up
        r = await client.post(
            "/api/v1/control/kill-switch",
            headers={**owner, **idem()},
            json={"scope": "company:TY", "state": "engaged", "reason": "آزمون"},
        )
        assert r.status_code == 200
        try:
            r = await client.post(
                f"/internal/v1/work/{root['id']}/progress",
                headers=await agent_headers("TY-CEO"),
                json={"note": "x"},
            )
            assert r.status_code == 423 and r.json()["code"] == "company_locked"
        finally:
            r = await client.post(
                "/api/v1/control/kill-switch",
                headers={**owner, **await sign("kill_switch.release", "company:TY"), **idem()},
                json={"scope": "company:TY", "state": "released", "reason": "پایان آزمون"},
            )
            assert r.status_code == 200
        assert (
            await client.post(
                f"/internal/v1/work/{root['id']}/progress",
                headers=await agent_headers("TY-CEO"),
                json={"note": "ادامه"},
            )
        ).status_code == 200
        assert (await client.get("/api/v1/audit/verify", headers=owner)).json()["ok"] is True
