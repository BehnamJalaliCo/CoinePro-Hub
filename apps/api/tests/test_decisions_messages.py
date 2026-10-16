"""Decision cartable, messages, search and resolutions (contract §5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up


def hire_body(co: str, **over: Any) -> dict[str, Any]:
    payload = {
        "company": co,
        "department": "GROWTH",
        "title_fa": "کارشناس سئو",
        "title_en": "SEO Specialist",
        "reason": "رشد ارگانیک",
        "duties": ["seo"],
        "model": "claude-sonnet-5-5",
        "effort": "high",
        "permissions": ["A0", "A1"],
        "quota_estimate_month": {"tokens": 2000000, "usd": "40"},
    }
    payload.update(over)
    return {
        "kind": "hire",
        "title": "استخدام کارشناس سئو",
        "what": "یک کارشناس",
        "why": "ترافیک",
        "risk": "low",
        "reversible": True,
        "payload": payload,
    }


async def test_hire_proposal_approval_and_effect(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    mgr = agent_headers(f"{co}-GROWTH-MGR")
    bad = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=hire_body(co, model="gpt-9")
    )
    assert bad.status_code == 422 and "payload.model" in bad.json()["fields"]
    other = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=hire_body("PC")
    )
    assert other.status_code == 422  # a manager hires only for its own company
    r = await client.post("/internal/v1/decisions", headers={**mgr, **idem()}, json=hire_body(co))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ref"].startswith("D-") and d["status"] == "pending" and d["action_class"] == "A2"
    assert d["thread"] == f"{co}-GROWTH-MGR" and d["proposer"] == {
        "kind": "agent",
        "code": f"{co}-GROWTH-MGR",
        "display_fa": None,
    }

    notes = (
        await client.get(
            "/api/v1/notifications", headers=h, params={"level": "decision", "company": co}
        )
    ).json()
    assert any(n["link"]["ref"] == d["ref"] for n in notes["items"])
    pending = (await client.get("/api/v1/decisions", headers=h, params={"company": co})).json()[
        "items"
    ]
    assert [x["ref"] for x in pending] == [d["ref"]]

    ref = d["ref"]
    r = await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, sid, "decision.approve", "D-999999")
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **wrong, **idem()}, json={}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    su = await step_up(hub, sid, "decision.approve", ref)
    key = idem()
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **su, **key}, json={"note": "موافقم"}
    )
    assert r.status_code == 200, r.text
    ok = r.json()
    assert (
        ok["status"] == "approved"
        and ok["resolution"].startswith("M-")
        and ok["seal"]["method"] == "passkey_uv"
    )
    assert ok["effect_status"] == "pending"
    again = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **su, **key}, json={"note": "موافقم"}
    )
    assert (
        again.status_code == 200 and again.json()["resolution"] == ok["resolution"]
    )  # idempotent replay
    r = await client.post(f"/api/v1/decisions/{ref}/reject", headers={**h, **idem()}, json={})
    assert r.status_code == 409 and r.json()["code"] == "decision_not_pending"

    msgs = (await client.get(f"/api/v1/threads/{co}-GROWTH-MGR/messages", headers=h)).json()[
        "items"
    ]
    assert msgs[-1]["kind"] == "system" and ok["resolution"] in msgs[-1]["body"]
    res = (await client.get(f"/api/v1/resolutions/{ok['resolution']}", headers=h)).json()
    assert res["source"]["decision"] == ref and res["sent_to"] == [f"{co}-GROWTH-MGR"]

    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, ref, SYSTEM)
        assert (await D.apply_effect(tx, ref, SYSTEM))["changed"] is False  # idempotent
    assert out["employee"] == f"{co}-GROWTH-01"
    emp = (await client.get(f"/api/v1/employees/{out['employee']}", headers=h)).json()
    assert emp["model"]["model"] == "claude-sonnet-5-5" and emp["model"]["effort"] == "high"
    threads = {
        t["code"]
        for t in (await client.get("/api/v1/threads", headers=h, params={"company": co})).json()
    }
    assert out["employee"] in threads


async def test_reject_return_ask_and_advisor(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = agent_headers(f"{co}-CEO")

    async def propose() -> str:
        r = await client.post(
            "/internal/v1/decisions",
            headers={**ceo, **idem()},
            json={
                "kind": "proposal",
                "title": "پیشنهاد رشد",
                "payload": {"okr": "O1", "options": ["a", "b"]},
            },
        )
        assert r.status_code == 201, r.text
        return str(r.json()["ref"])

    a, b = await propose(), await propose()
    r = await client.post(
        f"/api/v1/decisions/{a}/reject", headers={**owner, **idem()}, json={"reason_code": "cost"}
    )
    assert (
        r.json()["status"] == "rejected"
        and r.json()["reason_code"] == "cost"
        and r.json()["resolution"] is None
    )
    assert (
        await client.post(f"/api/v1/decisions/{b}/return", headers={**owner, **idem()}, json={})
    ).status_code == 422
    r = await client.post(
        f"/api/v1/decisions/{b}/return", headers={**owner, **idem()}, json={"note": "عدد بیاور"}
    )
    assert r.json()["status"] == "returned" and r.json()["note"] == "عدد بیاور"
    c = await propose()
    r = await client.post(
        f"/api/v1/decisions/{c}/ask", headers={**owner, **idem()}, json={"question": "هزینه؟"}
    )
    assert r.status_code == 200 and r.json()["thread"] == f"{co}-CEO"
    r = await client.post(f"/api/v1/decisions/{c}/review-with-advisor", headers={**owner, **idem()})
    assert r.json()["thread"] == "A" and r.json()["message_ref"].startswith("A-")
    # proposal approval (A1) needs no step-up and creates a follow-up work for the CEO
    r = await client.post(f"/api/v1/decisions/{c}/approve", headers={**owner, **idem()}, json={})
    assert r.status_code == 200 and r.json()["effect_status"] == "none"
    res = (await client.get(f"/api/v1/resolutions/{r.json()['resolution']}", headers=owner)).json()
    assert res["follow_up_work_id"] is not None


async def test_ceo_approves_recurring_work_within_quota(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    """Acceptance 4 (API level): an agent proposes recurring work; the company's
    CEO may approve it only inside the company's monthly budget."""
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = (await new_company())["code"]
    body = {
        "department": "GROWTH",
        "title": "پایش هفتگی رقبا",
        "kind": "recurring",
        "escrow": {
            "allowed_action_classes": ["A0", "A1"],
            "token_cap_per_run": 30000,
            "usd_cap_per_month": "20",
            "expires_at": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        },
        "schedule": {"rrule": "FREQ=WEEKLY;BYDAY=SU;BYHOUR=9", "timezone": "Asia/Tehran"},
    }
    r = await client.post(
        "/internal/v1/work", headers={**agent_headers(f"{co}-GROWTH-MGR"), **idem()}, json=body
    )
    assert r.status_code == 201, r.text
    created = r.json()
    ref = created["decision"]
    assert created["work"]["escrow"]["status"] == "pending" and ref.startswith("D-")

    ceo = agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/decisions/{ref}/approve", headers={**ceo, **idem()}, json={}
    )
    assert r.status_code == 403 and "outside_quota" in r.json()["detail"]  # no company budget yet
    su = await step_up(hub, sid, "budgets.update", "*")
    r = await client.put(
        "/api/v1/budgets",
        headers={**h, **su},
        json={
            "budgets": [
                {
                    "company": co,
                    "scope_type": "company",
                    "scope_ref": co,
                    "period": "month",
                    "usd_limit": "100",
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    other_ceo = agent_headers("PC-CEO")
    r = await client.post(
        f"/internal/v1/decisions/{ref}/approve", headers={**other_ceo, **idem()}, json={}
    )
    assert r.status_code in (403, 404)  # another company's CEO never sees or decides it
    r = await client.post(
        f"/internal/v1/decisions/{ref}/approve", headers={**ceo, **idem()}, json={"note": "ok"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["decided_by"]["code"] == f"{co}-CEO" and r.json()["seal"] is None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, ref, SYSTEM)
    assert out["first_run"] and out["first_run"].startswith("W-")
    w = (await client.get(f"/api/v1/work/{created['work']['id']}", headers=h)).json()
    assert w["escrow"]["status"] == "active" and w["escrow"]["approved_by"]["code"] == f"{co}-CEO"
    assert w["schedule"]["status"] == "active"
    # a deploy stays owner-only whatever the CEO thinks
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={
            "kind": "deploy",
            "title": "deploy v2",
            "payload": {"repo": "TradeYar", "pr_url": "https://github.com/x/y/pull/1"},
        },
    )
    dep = r.json()["ref"]
    r = await client.post(
        f"/internal/v1/decisions/{dep}/approve", headers={**ceo, **idem()}, json={}
    )
    assert r.status_code == 403 and r.json()["code"] == "policy_denied"


async def test_messages_search_read_and_resolutions(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    thread = f"{co}-CEO"
    body = {"body": "گزارش فروش كیك و يادداشت‌های مهم"}  # Arabic kaf/yeh, ZWNJ
    assert (
        await client.post(f"/api/v1/threads/{thread}/messages", headers=owner, json=body)
    ).status_code == 422
    r = await client.post(
        f"/api/v1/threads/{thread}/messages", headers={**owner, **idem()}, json=body
    )
    assert r.status_code == 201 and r.json()["ref"] == f"{thread}-0001"
    first = r.json()
    r = await client.post(
        f"/internal/v1/threads/{thread}/messages",
        headers={**agent_headers(thread), **idem()},
        json={"body": "پاسخ مدیرعامل"},
    )
    assert r.status_code == 201 and r.json()["author"]["code"] == thread
    threads = {
        t["code"]: t
        for t in (await client.get("/api/v1/threads", headers=owner, params={"company": co})).json()
    }
    assert threads[thread]["unread"] == 1  # the CEO's reply; the owner's own messages count as read
    r = await client.post(
        f"/internal/v1/threads/{co}-TECH-MGR/messages",
        headers={**agent_headers(f"{co}-GROWTH-MGR"), **idem()},
        json={"body": "x"},
    )
    assert r.status_code == 403  # not its thread
    corr = await client.post(
        f"/api/v1/threads/{thread}/messages",
        headers={**owner, **idem()},
        json={"body": "اصلاحیه", "links": {"corrects": first["ref"]}},
    )
    assert corr.json()["links"]["corrects"] == first["ref"]

    page = (await client.get(f"/api/v1/threads/{thread}/messages", headers=owner)).json()
    assert [m["ref"] for m in page["items"]] == [f"{thread}-000{i}" for i in (1, 2, 3)]
    r = await client.post(
        f"/api/v1/threads/{thread}/read", headers=owner, json={"up_to_ref": f"{thread}-0003"}
    )
    assert r.json()["unread"] == 0  # (replying already marked the thread read)

    for q in ("کیک", "يادداشتهای", "يادداشت‌های مهم", "فروش"):  # Persian-safe in both directions
        hits = (
            await client.get(
                "/api/v1/search/messages", headers=owner, params={"q": q, "company": co}
            )
        ).json()
        assert first["ref"] in {h["ref"] for h in hits["items"]}, q

    r = await client.post(
        "/api/v1/resolutions",
        headers={**owner, **idem()},
        json={"title": "تصمیم در گفت‌وگو", "body": "متن", "source_message": first["ref"]},
    )
    assert (
        r.status_code == 201
        and r.json()["source"]["message"] == first["ref"]
        and r.json()["company"] == co
    )
    listed = (
        await client.get("/api/v1/resolutions", headers=owner, params={"company": co})
    ).json()["items"]
    assert listed[0]["ref"] == r.json()["ref"]
