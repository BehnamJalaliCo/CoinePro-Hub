"""Prompt 08 §3 and §5 (contract §18.2, §18.3): formal inquiries, the advisor
v2's tools, the personal assistant's errands and the owner's planner."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_common import charters

from .conftest import agent_headers, idem, step_up
from .test_agents import run, step

pytestmark = pytest.mark.usefixtures("relay")


async def _end_test_runs(su: Any, *codes: str) -> None:
    """agent_headers() leaves a running 'test' run per employee: ended here."""
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'running' AND r.reason = 'test'""",
        list(codes),
    )


async def _queued(su: Any, code: str, **where: Any) -> dict[str, Any]:
    extra = " AND r.work_id = $2" if "work_id" in where else ""
    args = [code, *where.values()]
    row = await su.fetchrow(
        """SELECT r.id, r.priority, r.trigger FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.code = $1 AND r.state = 'queued'"""
        + extra
        + " ORDER BY r.queued_at DESC LIMIT 1",
        *args,
    )
    assert row is not None, code
    return dict(row)


# --------------------------------------------------------------- inquiries --
async def test_the_advisors_inquiry_wakes_the_ceo_and_the_answer_lands_in_thread_a(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    ceo = f"{co}-CEO"
    r = await client.post(
        "/api/v1/threads/A/messages",
        headers={**owner, **idem()},
        json={"body": "فروش هفته‌ی گذشته‌ی این شرکت چقدر بود؟"},
    )
    adv_run = r.json()["reply"]["run_id"]
    agents.fake.enqueue(
        "HQ-ADV",
        step(
            "از مدیرعامل می‌پرسم",
            (
                "inquiry.ask",
                {"to": ceo, "question_md": "فروش هفته‌ی گذشته چقدر بود؟", "due_in_hours": 24},
            ),
        ),
        "پرسیدم؛ پاسخ با شاهد در همین رشته می‌آید.",
    )
    assert (await run(agents, adv_run))["state"] == "done"
    q = await su.fetchrow("SELECT * FROM oversight.inquiries WHERE to_code = $1", ceo)
    assert q["status"] == "open" and q["from_code"] == "HQ-ADV" and q["thread_code"] == "A"
    assert q["from_rank"] == 2 and q["ref"].startswith("Q-")
    # The CEO is woken above normal work, with the question in its work brief.
    woken = await _queued(su, ceo, work_id=q["work_id"])
    assert woken["priority"] == "P1" and woken["trigger"] == "work"
    since = len(agents.fake.calls)
    agents.fake.enqueue(
        ceo,
        step(
            "پاسخ دادم",
            (
                "inquiry.answer",
                {
                    "ref": q["ref"],
                    "answer_md": "فروش هفته‌ی گذشته ۱۲۰ میلیون تومان بود.",
                    "evidence": [{"kind": "metric", "ref": "sales.week", "note": "120M"}],
                },
            ),
        ),
    )
    assert (await run(agents, woken["id"]))["state"] == "done"
    first = next(c for c in agents.fake.calls[since:] if c.actor_ref == ceo)
    assert q["ref"] in first.messages[0].content and "inquiry.answer" in first.messages[0].content
    answered = await su.fetchrow("SELECT * FROM oversight.inquiries WHERE id = $1", q["id"])
    assert answered["status"] == "answered" and answered["answer_message_ref"].startswith("A-")
    m = await su.fetchrow(
        "SELECT * FROM msg.messages WHERE ref = $1", answered["answer_message_ref"]
    )
    assert m["author_code"] == ceo and json.loads(m["links"]) == {"inquiry": q["ref"]}
    assert "۱۲۰" in m["body"] and "metric:sales.week" in m["body"]  # the evidence is shown
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", q["work_id"]) == "done"
    assert await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.inquiry.answered' AND payload->>'ref' = $1",
        q["ref"],
    )
    # The owner sees it; the thread shows the link.
    listed = (await client.get("/api/v1/inquiries", headers=owner, params={"to": ceo})).json()
    assert (
        listed["items"][0]["status"] == "answered"
        and listed["items"][0]["from"]["code"] == "HQ-ADV"
    )
    thread = (await client.get("/api/v1/threads/A/messages", headers=owner)).json()
    assert any(x.get("links", {}).get("inquiry") == q["ref"] for x in thread["items"])


async def test_who_may_ask_and_answer_and_a_late_inquiry(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    a, b = (await new_company())["code"], (await new_company())["code"]
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/inquiries",
        headers={**ovr, **idem()},
        json={"to": f"{a}-TECH-MGR", "question_md": "چرا کار W-1 دیر شد؟", "due_in_hours": 2},
    )
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["from"]["code"] == "HQ-OVR" and q["thread_ref"] == "N" and q["company"] == a
    # A CEO asks inside its own company only; a manager does not ask; no code oracle.
    ceo = await agent_headers(f"{a}-CEO")
    inside = await client.post(
        "/internal/v1/inquiries",
        headers={**ceo, **idem()},
        json={"to": f"{a}-GROWTH-MGR", "question_md": "برنامه‌ی هفته؟", "due_in_hours": 24},
    )
    assert inside.status_code == 201, inside.text
    for headers, to in (
        (ceo, f"{b}-CEO"),
        (ceo, "ZZ-NOBODY"),
        (await agent_headers(f"{a}-GROWTH-MGR"), f"{a}-TECH-MGR"),
    ):
        r = await client.post(
            "/internal/v1/inquiries",
            headers={**headers, **idem()},
            json={"to": to, "question_md": "x", "due_in_hours": 1},
        )
        assert r.status_code == 403, (to, r.text)
    # Only the asked one answers; a rank-2 inquiry cannot be failed away.
    other = await client.post(
        f"/internal/v1/inquiries/{q['ref']}/answer",
        headers={**ceo, **idem()},
        json={"answer_md": "من جواب می‌دهم"},
    )
    assert other.status_code == 403
    mgr = await agent_headers(f"{a}-TECH-MGR")
    work_id = await su.fetchval("SELECT work_id FROM oversight.inquiries WHERE ref = $1", q["ref"])
    failed = await client.post(
        f"/internal/v1/work/{work_id}/fail",
        headers=mgr,
        json={"reason": "وقت ندارم", "decline": True},
    )
    assert failed.status_code == 409 and q["ref"] in failed.text
    # Past its due time: late, the owner told once.
    await su.execute(
        "UPDATE oversight.inquiries SET due_at = now() - interval '1 minute' WHERE ref = $1",
        q["ref"],
    )
    out = await wk["acts"].inquiries_late()
    assert out["late"] >= 1
    assert (await wk["acts"].inquiries_late())["late"] == 0  # once
    row = await su.fetchrow(
        "SELECT status, late_at FROM oversight.inquiries WHERE ref = $1", q["ref"]
    )
    assert row["status"] == "late" and row["late_at"] is not None
    n = await su.fetchrow(
        "SELECT level, title_fa FROM notify.notifications WHERE link_kind = 'inquiry' AND link_ref = $1",
        q["ref"],
    )
    assert n["level"] == "decision" and q["ref"] in n["title_fa"]
    # A late one can still be answered, into the overseer's thread N.
    ok = await client.post(
        f"/internal/v1/inquiries/{q['ref']}/answer",
        headers={**mgr, **idem()},
        json={"answer_md": "به‌خاطر کمبود منبع.", "evidence": [{"kind": "link", "ref": "W-000001"}]},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "answered" and ok.json()["answer_message_ref"].startswith("N-")
    await _end_test_runs(su, "HQ-OVR", f"{a}-CEO", f"{a}-GROWTH-MGR", f"{a}-TECH-MGR")


def test_the_advisor_v2_has_its_read_tools() -> None:
    lib = charters.load()
    adv = set(lib.allowed("advisor"))
    for tool in ("files.read", "github.read", "workshop.read", "backups.status", "web.search",
                 "web.read", "web.browse", "http.request", "mcp.call", "inquiry.ask"):  # fmt: skip
        assert tool in adv, tool
    assert not [p for p in lib.problems if p.startswith("advisor:")]
    from hq_common.tool_status import GATEWAY_TOOLS

    # Every one of them is a live gateway tool, but prompt 10's reads: §12 builds
    # revenue.read and funnel.read in the gateway and then drops this exception.
    assert adv - {"done", "revenue.read", "funnel.read"} <= set(GATEWAY_TOOLS)


async def test_the_advisor_reads_a_workshop_session_and_still_answers(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, agents: Any
) -> None:
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "وضعیت پشتیبان‌ها؟"}
    )
    run_id = r.json()["reply"]["run_id"]
    agents.fake.enqueue(
        "HQ-ADV",
        step("می‌خوانم", ("backups.status", {}), ("workshop.read", {"session_ref": "S-9999"})),
        "پشتیبان‌ها را خواندم.",
    )
    out = await run(agents, run_id)
    assert out["state"] == "done", out
    steps = await su.fetch("SELECT actions FROM agents.steps WHERE run_id = $1 ORDER BY n", run_id)
    text = json.dumps([s["actions"] for s in steps], default=str)
    assert "backups.status" in text and "workshop.read" in text
    assert "unknown_tool" not in text  # both are real tools now (a missing session: 403)


# ----------------------------------------------------------------- errands --
def _fake_egress(seen: list[dict[str, Any]]) -> Any:
    sys.path[:0] = ["/w/gateway/src"]
    from hq_gateway.web import Egress

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"path": request.url.path, **body})
        entry = {"tool": "web.search", "method": "GET", "host": "searxng", "kind": "search",
                 "status": 200, "bytes_in": 900, "bytes_out": 60, "ms": 30, "class": "A0"}  # fmt: skip
        data = {
            "source": "web",
            "results": [
                {
                    "title": "پرواز تهران-استانبول",
                    "url": "https://example.com/flights",
                    "snippet": "از ۲۴ میلیون",
                    "date": None,
                }
            ],
        }
        return httpx.Response(
            200, json={"outcome": "ok", "code": None, "data": data, "entries": [entry]}
        )

    return Egress("http://egress.test", 5, transport=httpx.MockTransport(handle))


async def test_an_errand_runs_search_and_summary_to_the_end(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, agents: Any
) -> None:
    seen: list[dict[str, Any]] = []
    real = agents.core.api.egress
    agents.core.api.egress = _fake_egress(seen)
    try:
        r = await client.post(
            "/api/v1/threads/P/messages",
            headers={**owner, **idem()},
            json={"body": "ارزان‌ترین پرواز تهران به استانبول برای جمعه را پیدا کن"},
        )
        assert r.status_code == 201, r.text
        ref = r.json()["message"]["links"]["errand"]
        e = await su.fetchrow("SELECT * FROM owner.errands WHERE ref = $1", ref)
        assert e["status"] == "queued" and e["message_ref"] == r.json()["message"]["ref"]
        run_id = r.json()["reply"]["run_id"]
        since = len(agents.fake.calls)
        agents.fake.enqueue(
            "HQ-PA",
            step(
                "جستجو کردم",
                ("web.search", {"q": "Tehran Istanbul flight Friday"}),
                ("errand.step", {"ref": ref, "kind": "search", "summary_fa": "سه پرواز پیدا شد"}),
                done=False,
            ),
            step(
                "نتیجه",
                (
                    "errand.finish",
                    {"ref": ref, "result_md": "ارزان‌ترین: ۲۴ میلیون تومان، ساعت ۸ صبح."},
                ),
            ),
        )
        assert (await run(agents, run_id))["state"] == "done"
    finally:
        agents.core.api.egress = real
    first = next(c for c in agents.fake.calls[since:] if c.actor_ref == "HQ-PA")
    assert "# Errand" in first.messages[0].content and ref in first.messages[0].content
    assert seen and seen[0]["path"] == "/v1/search"
    done = (await client.get(f"/api/v1/errands/{ref}", headers=owner)).json()
    assert done["status"] == "done" and [s["kind"] for s in done["steps"]] == ["search"]
    assert "۲۴" in done["result_md"] and done["usage"]["input_tokens"] > 0  # from the ledger
    result = await su.fetchrow(
        """SELECT m.author_code, m.links FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = 'P' AND m.links->>'errand' = $1 AND m.author_kind = 'agent'""",
        ref,
    )
    assert result["author_code"] == "HQ-PA"
    assert await su.fetchval(
        "SELECT count(*) FROM egress.log WHERE actor = 'HQ-PA' AND tool = 'web.search'"
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.errand.updated' AND payload->>'ref' = $1",
            ref,
        )
        >= 2
    )
    # A follow-up message continues the same errand; a finished one cannot be continued.
    again = await client.post(
        "/api/v1/threads/P/messages",
        headers={**owner, **idem()},
        json={"body": "ادامه بده", "links": {"errand": ref}},
    )
    assert again.status_code == 422


async def test_a_purchase_becomes_a_decision_and_nothing_happens_without_the_seal(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    su: Any,
    hub: Any,
    agents: Any,
) -> None:
    h = owner_session["headers"]
    r = await client.post(
        "/api/v1/errands",
        headers={**h, **idem()},
        json={"brief_md": "بلیط پرواز جمعه را بخر", "title_fa": "خرید بلیط"},
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert r.json()["message_ref"].startswith("P-") and r.json()["title_fa"] == "خرید بلیط"
    run_id = await su.fetchval(
        """SELECT r.id FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.code = 'HQ-PA' AND r.state = 'queued' ORDER BY r.queued_at DESC LIMIT 1"""
    )
    agents.fake.enqueue(
        "HQ-PA",
        step(
            "خرید را تا آخرین کلیک آماده کردم",
            (
                "propose",
                {
                    "kind": "errand_action",
                    "title_fa": "خرید بلیط تهران-استانبول",
                    "what_md": "پرداخت ۲۴ میلیون تومان در example.com",
                    "why_md": "ارزان‌ترین پرواز جمعه",
                    "risk": "medium",
                    "reversible": False,
                    "payload": {
                        "errand": ref,
                        "action": "buy",
                        "target": "example.com",
                        "details_md": "بلیط اکونومی، جمعه ساعت ۸",
                        "cost": "24,000,000 تومان",
                        "undo_md": "لغو تا ۲۴ ساعت با ۱۰٪ جریمه",
                    },
                },
            ),
        ),
    )
    assert (await run(agents, run_id))["state"] == "done"
    d = await su.fetchrow(
        "SELECT * FROM cartable.decisions WHERE kind = 'errand_action' AND payload->>'errand' = $1",
        ref,
    )
    assert d["status"] == "pending" and d["action_class"] == "A3" and d["proposer_code"] == "HQ-PA"
    e = (await client.get(f"/api/v1/errands/{ref}", headers=h)).json()
    assert e["status"] == "waiting_owner" and e["decision_ref"] == d["ref"]
    # Nothing goes on while it waits: no finish, no approval without the seal.
    pa = await agent_headers("HQ-PA")
    r = await client.post(
        f"/internal/v1/errands/{ref}/finish", headers={**pa, **idem()}, json={"result_md": "خریدم"}
    )
    assert r.status_code == 409
    r = await client.post(f"/api/v1/decisions/{d['ref']}/approve", headers={**h, **idem()}, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    assert (await client.get(f"/api/v1/errands/{ref}", headers=h)).json()[
        "status"
    ] == "waiting_owner"
    # With the seal: the errand goes on, and the assistant gets the follow-up
    # work; the commitment itself is still the owner's last step (no tool makes it).
    seal = await step_up(hub, owner_session["session_id"], "decision.approve", d["ref"])
    r = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**h, **seal, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    e = (await client.get(f"/api/v1/errands/{ref}", headers=h)).json()
    assert e["status"] == "working" and e["steps"][-1]["data"]["verdict"] == "approved"
    follow = await su.fetchval(
        """SELECT count(*) FROM work.work w JOIN core.employees a ON a.id = w.assignee_id
           WHERE a.code = 'HQ-PA' AND w.brief LIKE $1""",
        f"%{d['ref']}%",
    )
    assert follow == 1
    cancelled = await client.post(f"/api/v1/errands/{ref}/cancel", headers=h)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    await _end_test_runs(su, "HQ-PA")
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND e.code = 'HQ-PA' AND r.state = 'queued'"""
    )


async def test_a_reminder_appears_in_the_owners_planner(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    pa = await agent_headers("HQ-PA")
    at = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    r = await client.post(
        "/internal/v1/planner",
        headers={**pa, **idem()},
        json={"title_fa": "تمدید گذرنامه", "at": at.isoformat(), "note": "مدارک را همراه ببر"},
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert ref.startswith("PL-")
    plan = (await client.get("/api/v1/planner", headers=owner, params={"scope": "owner"})).json()
    items = [i for d in plan["days"] for i in d["items"] if i["ref"] == ref]
    assert (
        len(items) == 1
        and items[0]["kind"] == "reminder"
        and items[0]["note"] == "مدارک را همراه ببر"
    )
    # Only the assistant writes the owner's planner.
    ceo = await agent_headers("HQ-ADV")
    r = await client.post(
        "/internal/v1/planner",
        headers={**ceo, **idem()},
        json={"title_fa": "x", "at": at.isoformat()},
    )
    assert r.status_code == 403
    await _end_test_runs(su, "HQ-PA", "HQ-ADV")
