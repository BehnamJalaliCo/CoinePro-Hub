"""Prompt 05 §4-§9 with the FAKE model: the advisor's live answer and its
citations, rule-based site checks and incidents, hires bound to a charter,
memory and knowledge transfer, the owner's agent screens, the quota, the
morning report's rewrite, and a run end to end through Temporal."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.agents import checks
from hq_api.agents import protocol as P

from .conftest import idem, random_code, signed_put, step_up
from .test_agents import order, run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")


# ------------------------------------------------------------------ advisor --
async def test_advisor_answers_live_with_validated_citations(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    hub: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co, title="کار قابل استناد")
    q = hub.live.subscribe("A")
    r = await client.post(
        "/api/v1/threads/A/messages",
        headers={**owner, **idem()},
        json={"body": "وضعیت کارها چطور است؟"},
    )
    assert r.status_code == 201
    reply = r.json()["reply"]
    assert reply["state"] == "queued"
    run_row = await su.fetchrow(
        "SELECT * FROM agents.runs WHERE id = $1", uuid.UUID(reply["run_id"])
    )
    advisor = hub.charters.roles["advisor"]
    assert run_row["priority"] == advisor.priority and run_row["trigger"] == "message"
    answer = (
        f"خلاصه: کار {w['ref']} در صف است.\n\nشواهد: همان کار.\n"
        f'{P.CITATIONS_OPEN}[{{"kind": "work", "ref": "{w["ref"]}"}}, {{"kind": "decision", "ref": "D-999999"}}]{P.CITATIONS_CLOSE}'
    )
    agents.fake.enqueue(
        "HQ-ADV",
        step(
            "جستجو در سوابق",
            ("knowledge.search", {"q": "کار قابل استناد"}),
            ("company.state", {"company": co}),
        ),
        answer,
    )
    try:
        out = await run(agents, run_row["id"])
        assert out["state"] == "done", out
        seen: list[tuple[str, dict[str, Any]]] = []
        while not q.empty():
            seen.append(q.get_nowait())
    finally:
        hub.live.unsubscribe("A", q)
    types = [t for t, _ in seen]
    assert types[0] == "reply.started" and types[-1] == "reply.done"
    text = "".join(d["text"] for t, d in seen if t == "reply.delta")
    assert w["ref"] in text and P.CITATIONS_OPEN not in text  # the citations line never streams
    ref = seen[-1][1]["message_ref"]
    m = await su.fetchrow(
        "SELECT body, citations, meta, author_code FROM msg.messages WHERE ref = $1", ref
    )
    assert m["author_code"] == "HQ-ADV" and P.CITATIONS_OPEN not in m["body"]
    assert json.loads(m["citations"]) == [
        {"kind": "work", "ref": w["ref"]}
    ]  # the made-up one is dropped
    assert json.loads(m["meta"]) == {"citations_dropped": 1}
    # The owner's API shows them; the live SSE exists for the owner only.
    r = await client.get("/api/v1/threads/A/messages", headers=owner)
    last = r.json()["items"][-1]
    assert last["citations"] == [{"kind": "work", "ref": w["ref"]}] and last["meta"] == {
        "citations_dropped": 1
    }
    assert (await client.get("/api/v1/threads/A/live")).status_code == 401
    # The research step's tools ran with the advisor's holding scope (another company read).
    actions = json.loads(
        await su.fetchval(
            "SELECT actions FROM agents.steps WHERE run_id = $1 AND n = 1", run_row["id"]
        )
    )
    assert [a["outcome"] for a in actions] == ["ok", "ok"]


async def test_advisor_writes_nowhere_but_its_thread(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    w = await order(client, owner, co)
    r = await client.post(
        "/api/v1/threads/A/messages", headers={**owner, **idem()}, json={"body": "یک کار ساده"}
    )
    run_id = r.json()["reply"]["run_id"]
    agents.fake.enqueue(
        "HQ-ADV",
        step(
            "تلاش برای نوشتن",
            ("deliver", {"work_ref": w["ref"], "title_fa": "x", "body_md": "y"}),
            ("propose", {"kind": "proposal", "title_fa": "x"}),
            ("notify", {"level": "info", "title_fa": "x"}),
            ("work.delegate", {"ref": w["ref"], "to": f"{co}-TECH-MGR", "title_fa": "x"}),
            ("message.thread", {"thread": f"{co}-CEO", "body_md": "سلام"}),
            ("memory.write", {"note_md": "مالک پاسخ کوتاه میخواهد"}),
        ),
        "پاسخ کوتاه.",
    )
    assert (await run(agents, run_id))["state"] == "done"
    actions = json.loads(
        await su.fetchval(
            "SELECT actions FROM agents.steps WHERE run_id = $1 AND n = 1", uuid.UUID(run_id)
        )
    )
    assert [(a["tool"], a["outcome"], a.get("code")) for a in actions] == [
        ("deliver", "denied", "tool_not_in_charter"),
        ("propose", "denied", "tool_not_in_charter"),
        ("notify", "denied", "tool_not_in_charter"),
        ("work.delegate", "denied", "tool_not_in_charter"),
        ("message.thread", "error", "not_found"),  # another company's thread: not even visible
        ("memory.write", "ok", None),
    ]


async def test_review_with_advisor_gives_the_decision_card(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    from .conftest import agent_headers

    co = (await new_company())["code"]
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={
            "kind": "proposal",
            "title": "پیشنهاد رشد",
            "what": "کمپین",
            "why": "رشد",
            "payload": {"okr": "O1"},
        },
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    r = await client.post(
        f"/api/v1/decisions/{ref}/review-with-advisor", headers={**owner, **idem()}
    )
    assert r.status_code == 200, r.text
    row = await su.fetchrow(
        "SELECT r.id FROM agents.runs r JOIN msg.threads t ON t.id = r.thread_id WHERE t.code = 'A' AND r.state = 'queued' ORDER BY r.queued_at DESC LIMIT 1"
    )
    seen: list[str] = []

    def script(call: Any) -> Any:
        seen.append("".join(m.content for m in call.messages))
        return None

    agents.fake.script = script
    try:
        agents.fake.enqueue("HQ-ADV", step("کارت را خواندم"), f"این پیشنهاد {ref} را بررسی کردم.")
        assert (await run(agents, row["id"]))["state"] == "done"
    finally:
        agents.fake.script = None
    assert agents.fake.calls[-2].messages[0].content.count("# Decision card to review") == 1
    assert ref in agents.fake.calls[-2].messages[0].content


def test_propose_section_is_generated_from_the_api_models(hub: Any) -> None:
    from hq_api.domain import decisions as D

    lib = hub.charters
    co = P.propose_section(
        lib, lib.roles["cto"], D.PAYLOADS, {"company_code": "TY", "holding_code": "HQ"}
    )
    assert "kind `hire`: payload {company: string, department: string, role?: string" in co
    assert "`role` must be one of: sre (department TECH)" in co and "`company` is TY" in co
    assert "work_id: uuid" in co and "effort: low|medium|high|xhigh|max" in co
    holding = P.propose_section(
        lib, lib.roles["aiops_head"], D.PAYLOADS, {"company_code": "HQ", "holding_code": "HQ"}
    )
    assert (
        "hub_platform_sre (department AIOPS)" in holding and "sre (department TECH)" not in holding
    )
    assert P.propose_section(lib, lib.roles["advisor"], D.PAYLOADS, {}) == ""  # no propose tool
    system = P.system_prompt(
        lib,
        lib.roles["cto"],
        {"company_code": "TY", "holding_code": "HQ"},
        max_actions=8,
        payloads=D.PAYLOADS,
    )
    assert system.rstrip().endswith("One decision per hire.")


async def test_stream_filter_and_answer_parsing() -> None:
    f = P.StreamFilter()
    out = "".join(f.feed(c) for c in ["سلام ", "مدیر کل", "\n<cita", "tions>[{]"]) + f.flush()
    assert out == "سلام مدیر کل\n"
    body, cites = P.split_answer(
        'متن\n<citations>[{"kind": "work", "ref": "W-000001"}, {"kind": "x", "ref": "y"}, 5]</citations>'
    )
    assert body == "متن" and cites == [{"kind": "work", "ref": "W-000001"}]
    assert P.split_answer("بدون استناد") == ("بدون استناد", [])
    assert P.split_answer("x <citations>not json</citations>") == ("x", [])
    g = P.StreamFilter()
    assert g.feed("abc") == "" and g.flush() == "abc"
    with pytest.raises(P.BadOutput):
        P.parse_step({"summary_fa": 1}, None, 8)
    with pytest.raises(P.BadOutput):
        P.parse_step({"summary_fa": "x", "actions": [{"args": {}}], "done": True}, None, 8)
    s = P.parse_step(
        {"summary_fa": "x", "actions": [{"tool": "a", "args": 3}] * 12, "done": False}, None, 8
    )
    # Kept as the model wrote it: the Tool Gateway refuses non-object args
    # (invalid_args), so a malformed action is never run as an empty one.
    assert len(s.actions) == 8 and s.actions[0].args == 3
    assert P.trim("a\n\n\n\nb", 100) == "a\n\nb" and P.trim("x" * 20, 5).endswith("[cut]")


# -------------------------------------------------------------- site checks --
async def _site(su: Any, company_id: Any, url: str, **extra: Any) -> Any:
    return await su.fetchval(
        """INSERT INTO ops.sites (company_id, url, kind, method, expect, interval_s, canary)
           VALUES ($1, $2, 'web', $3, $4::jsonb, 60, $5) RETURNING id""",
        company_id,
        url,
        extra.get("method", "GET"),
        json.dumps(extra.get("expect", {"status": 200})),
        extra.get("canary", False),
    )


async def _round(hub: Any, su: Any, checker: checks.Checker, company_id: Any) -> dict[str, Any]:
    # Only this company's sites are due (others were checked "just now").
    await su.execute(
        "UPDATE ops.sites SET last_checked_at = now() WHERE company_id <> $1", company_id
    )
    await su.execute(
        "UPDATE ops.sites SET last_checked_at = NULL WHERE company_id = $1", company_id
    )
    return await checks.run_round(hub, checker)


async def test_site_checks_open_one_incident_and_close_it(
    su: Any, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    healthy = f"https://ok-{co.lower()}.example.test/"
    down = f"https://down-{co.lower()}.example.test/health"
    await _site(su, company["id"], healthy, expect={"status": 200, "contains": "ok"})
    down_id = await _site(su, company["id"], down)
    state = {"down": True}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "CoinePro-HQ-Monitor/1"
        if request.url.host.startswith("ok-"):
            if request.url.path == "/":
                return httpx.Response(302, headers={"location": "/home"})  # same host: followed
            return httpx.Response(200, text="all ok")
        return httpx.Response(503) if state["down"] else httpx.Response(200)

    checker = checks.Checker(transport=httpx.MockTransport(handler), tls=False, resolver=_public)
    hub = wk["hub"]
    for i in range(1, 6):
        r = await _round(hub, su, checker, company["id"])
        assert r["checked"] == 2 and r["failed"] == 1
        assert r["opened"] == (1 if i == 3 else 0)  # three in a row -> one incident, then no more
    inc = await su.fetchrow("SELECT * FROM ops.incidents WHERE site_id = $1", down_id)
    assert (
        inc["closed_at"] is None
        and inc["checks_failed"] == 5
        and inc["last_error"] == "unexpected_status"
    )
    work = await su.fetchrow("SELECT * FROM work.work WHERE id = $1", inc["work_id"])
    cto = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co}-TECH-MGR")
    assert (
        work["assignee_id"] == cto
        and work["kind"] == "event"
        and work["created_by_code"] == "site-checks"
    )
    assert work["budget_tokens"] == 60_000  # the responder's run stops at the incident's budget
    assert len(json.loads(work["evidence"])) == 4
    runs = await su.fetch("SELECT trigger FROM agents.runs WHERE work_id = $1", inc["work_id"])
    assert [r["trigger"] for r in runs] == [
        "alert"
    ]  # one run woke the CTO; the healthy site woke nobody
    assert (
        await su.fetchval(
            "SELECT count(*) FROM work.work WHERE company_id = $1 AND created_by_code = 'site-checks'",
            company["id"],
        )
        == 1
    )
    state["down"] = False
    r = await _round(hub, su, checker, company["id"])
    assert r["closed"] == 1
    assert await su.fetchval(
        "SELECT closed_at IS NOT NULL FROM ops.incidents WHERE id = $1", inc["id"]
    )
    checks_n = await su.fetchval("SELECT count(*) FROM ops.checks WHERE site_id = $1", down_id)
    assert checks_n == 6
    # Switched off while failing (the canary's way out): the next round closes its incident.
    state["down"] = True
    for _ in range(3):
        await _round(hub, su, checker, company["id"])
    again = await su.fetchrow(
        "SELECT * FROM ops.incidents WHERE site_id = $1 AND closed_at IS NULL", down_id
    )
    assert again is not None and again["id"] != inc["id"]
    await su.execute("UPDATE ops.sites SET enabled = false WHERE id = $1", down_id)
    r = await _round(hub, su, checker, company["id"])
    assert r["checked"] == 1 and r["closed"] == 1
    assert await su.fetchval(
        "SELECT closed_at IS NOT NULL FROM ops.incidents WHERE id = $1", again["id"]
    )
    why = await su.fetchval(
        "SELECT data->>'why' FROM work.work_events WHERE work_id = $1 AND kind = 'incident_closed'",
        again["work_id"],
    )
    assert why == "monitoring switched off"


async def test_checker_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/offsite":
            return httpx.Response(301, headers={"location": "https://elsewhere.test/"})
        if path == "/loop":
            return httpx.Response(302, headers={"location": "/loop"})
        if path == "/text":
            return httpx.Response(200, text="nothing here")
        if path == "/dns":
            raise httpx.ConnectError("[Errno -2] Name or service not known")
        if path == "/refused":
            raise httpx.ConnectError("connection refused")
        if path == "/slow":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, text="ok")

    c = checks.Checker(transport=httpx.MockTransport(handler), tls=False, resolver=_public)

    async def check(path: str, **expect: Any) -> checks.Result:
        return await c.check(
            {
                "url": f"https://site.test{path}",
                "method": "GET",
                "expect": expect or {"status": 200},
            }
        )

    assert (await check("/offsite")).error_code == "unexpected_status"
    off = await check("/offsite", status=301)
    assert off.ok and off.status == 301  # a redirect to another domain is reported, not followed
    assert (await check("/loop")).error_code == "too_many_redirects"
    assert (await check("/text", status=200, contains="ok")).error_code == "missing_text"
    assert (await check("/dns")).error_code == "dns_error"
    assert (await check("/refused")).error_code == "connect_error"
    assert (await check("/slow")).error_code == "timeout"
    head = await c.check(
        {
            "url": "https://site.test/x",
            "method": "HEAD",
            "expect": {"status": 200, "contains": "zzz"},
        }
    )
    assert head.ok  # contains is checked on GET only
    assert checks._cert_days_left("invalid.invalid") is None


async def _public(host: str) -> list[str]:
    """A resolver for the checker's tests: every test name is a public address."""
    return ["93.184.216.34"] if host.endswith(".test") else []  # a global address


async def test_the_checker_never_reaches_a_private_network() -> None:
    """Prompt 5.1 §3: a monitored URL on a private or internal address, as
    written or as resolved, is refused before any request is made."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    async def resolver(host: str) -> list[str]:
        return {"inner.example.com": ["10.10.1.2"], "mixed.example.com": ["8.8.8.8", "::1"]}.get(
            host, ["8.8.8.8"]
        )

    c = checks.Checker(transport=httpx.MockTransport(handler), tls=False, resolver=resolver)
    for url in (
        "http://10.10.1.3/",
        "http://127.0.0.1:8000/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "http://172.30.0.5/",
        "http://192.168.1.1/",
        "http://100.64.0.1/",
        "http://postgres:5432/",
        "http://api:8000/",
        "https://printer.local/",
        "https://inner.example.com/",
        "https://mixed.example.com/",
    ):
        r = await c.check({"url": url, "method": "GET", "expect": {"status": 200}})
        assert (r.ok, r.error_code) == (False, "private_address"), url
    assert seen == []
    assert (await c.check({"url": "https://public.example.com/", "method": "GET", "expect": {}})).ok


async def test_the_holding_responder_and_hub_snapshot(
    su: Any, wk: dict[str, Any], hub: Any, tmp_path: Any
) -> None:
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        who = await checks.responder(hub, tx, holding.id, "holding")
    assert who is not None and who["code"] == f"{holding.code}-AIOPS-MGR"

    def prom(request: httpx.Request) -> httpx.Response:
        q = request.url.params["query"]
        if "hq_container_up" in q:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "result": [
                            {"metric": {"service": "caddy"}, "value": [0, "1"]},
                            {"metric": {"service": "loki"}, "value": [0, "0"]},
                        ]
                    }
                },
            )
        if "restarts" in q:
            return httpx.Response(
                200, json={"data": {"result": [{"metric": {"service": "loki"}, "value": [0, "2"]}]}}
            )
        return httpx.Response(
            200, json={"data": {"result": [{"metric": {}, "value": [0, "42.42"]}]}}
        )

    (tmp_path / "backup.json").write_text(
        json.dumps(
            {"at": datetime.now(UTC).isoformat(), "ok": True, "size_bytes": 608000, "stamp": "x"}
        )
    )
    from dataclasses import replace

    whub = wk["hub"]
    real = whub.settings
    whub.settings = replace(real, hub_status_dir=str(tmp_path))
    try:
        data = await checks.hub_snapshot(whub, transport=httpx.MockTransport(prom))
    finally:
        whub.settings = real
    assert data["services_up"] == "1/2" and data["restarts_24h"] == {"loki": 2}
    assert (
        data["disk_used_pct"] == 42.4
        and data["backup"]["ok"] is True
        and data["restore_test"] is None
    )
    assert data["backup"]["age_hours"] is not None and data["backup"]["age_hours"] < 1
    stored = await su.fetchval("SELECT data FROM ops.hub_health WHERE company_id = $1", holding.id)
    assert json.loads(stored)["services_up"] == "1/2"


# ------------------------------------------------------------- owner's side --
async def test_roles_runs_sites_incidents_and_quota_endpoints(
    client: httpx.AsyncClient,
    hub: Any,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    r = await client.get("/api/v1/roles", headers=h)
    roles = {x["role"]: x for x in r.json()}
    assert {"ceo", "cto", "sre", "advisor", "inspector", "aiops_head"} <= set(roles)
    advisor = hub.charters.roles["advisor"]
    assert roles["advisor"]["model"] == advisor.model
    assert roles["advisor"]["priority"] == advisor.priority
    company = await new_company()
    co = company["code"]
    r = await client.get(f"/api/v1/employees/{co}-TECH-MGR", headers=h)
    assert r.json()["charter"] == {"role": "cto", "version": hub.charters.roles["cto"].version}
    body = {
        "company": co,
        "sites": [
            {"url": f"https://a-{co.lower()}.test/", "expect": {"status": 200}},
            {"url": f"https://b-{co.lower()}.test/", "kind": "api", "method": "HEAD"},
        ],
    }
    r = await client.put("/api/v1/ops/sites", headers=h, json=body)
    assert r.status_code == 403  # 🔏
    r = await signed_put(client, hub, owner_session, "/api/v1/ops/sites", body, "sites.update")
    assert r.status_code == 200, r.text
    assert sorted(s["url"] for s in r.json() if s["enabled"]) == sorted(
        s["url"] for s in body["sites"]
    )
    body2 = {"company": co, "sites": [body["sites"][0]]}
    r = await signed_put(client, hub, owner_session, "/api/v1/ops/sites", body2, "sites.update")
    assert [s["enabled"] for s in sorted(r.json(), key=lambda s: s["url"])] == [
        True,
        False,
    ]  # off, not deleted
    bad = {
        "company": co,
        "sites": [{"url": f"https://a-{co.lower()}.test/", "expect": {"status": 999}}],
    }
    assert (
        await signed_put(client, hub, owner_session, "/api/v1/ops/sites", bad, "sites.update")
    ).status_code == 422
    for url in ("http://10.10.1.2/", "http://postgres:5432/", "https://x.internal/"):
        inner = {"company": co, "sites": [body["sites"][0], {"url": url}]}
        r = await signed_put(client, hub, owner_session, "/api/v1/ops/sites", inner, "sites.update")
        assert r.status_code == 422 and "sites.1.url" in r.json()["fields"], url
    dup = {"company": co, "sites": [body["sites"][0], body["sites"][0]]}
    assert (
        await signed_put(client, hub, owner_session, "/api/v1/ops/sites", dup, "sites.update")
    ).status_code == 422
    assert (await client.get(f"/api/v1/ops/sites?company={co}", headers=h)).status_code == 200
    r = await client.get(f"/api/v1/ops/incidents?company={co}&open=true", headers=h)
    assert r.status_code == 200 and r.json() == []
    r = await client.get("/api/v1/runs?limit=5", headers=h)
    assert r.status_code == 200 and "items" in r.json()
    # The quota as the Quota Controller left it.
    cid = await su.fetchval("SELECT id FROM llm.connections WHERE key = 'claude-max'")
    await su.execute(
        """INSERT INTO llm.quota_status (connection_id, status, window_kind, utilization, resets_at, source)
           VALUES ($1, 'warning', 'five_hour', 0.85, now() + interval '1 hour', 'sdk_rate_limit_event')
           ON CONFLICT (connection_id) DO UPDATE SET status = 'warning', resets_at = now() + interval '1 hour'""",
        cid,
    )
    q = (await client.get("/api/v1/treasury/quota", headers=h)).json()
    assert q["subscription"]["status"] == "warning" and q["throttle"]["paused_priorities"] == ["P4"]
    await su.execute(
        "UPDATE llm.quota_status SET resets_at = now() - interval '1 minute' WHERE connection_id = $1",
        cid,
    )
    q = (await client.get("/api/v1/treasury/quota", headers=h)).json()
    assert q["subscription"]["status"] == "ok" and q["throttle"]["paused_priorities"] == []
    await su.execute("DELETE FROM llm.quota_status WHERE connection_id = $1", cid)


async def test_live_stream_for_the_owner(app: Any, owner: dict[str, str], hub: Any) -> None:
    """The real SSE path, over TCP (ASGITransport buffers whole responses)."""
    import socket

    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    )
    serving = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)

        async def listen() -> list[str]:
            out: list[str] = []
            async with (
                httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as c,
                c.stream("GET", "/api/v1/threads/A/live", headers=owner, timeout=10) as resp,
            ):
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    out.append(line)
                    if line.startswith("data:") and "A-0001" in line:
                        return out
            return out

        task = asyncio.create_task(listen())
        for _ in range(100):
            if hub.live.listeners("A"):
                break
            await asyncio.sleep(0.05)
        hub.live.publish("A", "reply.delta", {"text": "سلام"})
        hub.live.publish("A", "reply.done", {"message_ref": "A-0001"})
        lines = await asyncio.wait_for(task, timeout=10)
        assert "event: reply.delta" in lines and any("سلام" in x for x in lines)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as c:
            assert (await c.get("/api/v1/threads/NOPE-X/live", headers=owner)).status_code == 404
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=10)
    assert hub.live.listeners("A") == 0  # the listener is gone with its connection


# ------------------------------------------------------------------- hiring --
@pytest.mark.usefixtures("hiring_open")  # agents propose hires (§18.11)
async def test_a_hire_runs_with_a_real_charter(
    client: httpx.AsyncClient,
    hub: Any,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from .conftest import agent_headers

    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    base = {
        "kind": "hire",
        "title": "استخدام SRE",
        "what": "پایش",
        "why": "نیاز",
        "payload": {
            "company": co,
            "department": "TECH",
            "title_fa": "SRE",
            "title_en": "SRE",
            "reason": "پایش",
            "model": "claude-haiku-5-5",
            "effort": "high",
        },
    }
    r = await client.post("/internal/v1/decisions", headers={**cto, **idem()}, json=base)
    assert (
        r.status_code == 422 and "payload.role" in r.json()["fields"]
    )  # an agent must name the charter
    for role, field in (
        ("nope", "payload.role"),
        ("cto", "payload.role"),
        ("ai_safety", "payload.role"),
    ):
        bad = json.loads(json.dumps(base))
        bad["payload"]["role"] = role
        r = await client.post("/internal/v1/decisions", headers={**cto, **idem()}, json=bad)
        assert r.status_code == 422 and field in r.json()["fields"], (role, r.text)
    wrong_dept = json.loads(json.dumps(base))
    wrong_dept["payload"].update(role="sre", department="GROWTH")
    r = await client.post("/internal/v1/decisions", headers={**cto, **idem()}, json=wrong_dept)
    assert r.status_code == 422 and "payload.department" in r.json()["fields"]
    good = json.loads(json.dumps(base))
    good["payload"]["role"] = "sre"
    r = await client.post("/internal/v1/decisions", headers={**cto, **idem()}, json=good)
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    h, sid = owner_session["headers"], owner_session["session_id"]
    st = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**h, **st, **idem()},
        json={"amendments": {"role": "manager"}},
    )
    assert r.status_code == 422  # the amended role is not an employee charter: not approved
    st = await step_up(hub, sid, "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **st, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    from hq_api.domain import decisions as D
    from hq_api.principal import Principal

    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, ref, Principal(kind="service", code="system", role="system"))
    emp = await su.fetchrow(
        "SELECT role, kind FROM core.employees WHERE code = $1", out["employee"]
    )
    assert (emp["role"], emp["kind"]) == ("sre", "employee")
    # The SRE now answers incidents of its company before the CTO.
    company_id = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        who = await checks.responder(hub, tx, company_id, "company")
    assert who["code"] == out["employee"]


async def test_memory_and_its_transfer_on_dismissal(
    client: httpx.AsyncClient,
    hub: Any,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from .conftest import agent_headers

    company = await new_company()
    co = company["code"]
    emp = f"{co}-TECH-01"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role,
               reports_to)
           SELECT c.id, d.id, $1, 'employee', 'SRE', 'SRE', 'sre',
                  (SELECT id FROM core.employees WHERE code = $3)
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'TECH'
           WHERE c.code = $2""",
        emp,
        co,
        f"{co}-TECH-MGR",
    )
    me = await agent_headers(emp)
    for note in ("درگاه پرداخت شب‌ها کند است", "پنجره‌ی نگهداری: جمعه‌ها"):
        r = await client.post(
            "/internal/v1/memory", headers=me, json={"note": note, "tags": ["ops"]}
        )
        assert r.status_code == 201, r.text
    r = await client.get("/internal/v1/memory", headers=me)
    assert r.json()[0]["note"] == "پنجره‌ی نگهداری: جمعه‌ها"  # latest first
    other = await agent_headers(f"{co}-TECH-MGR")
    assert (
        len((await client.get("/internal/v1/memory", headers=other)).json()) == 0
    )  # own memory only
    h, sid = owner_session["headers"], owner_session["session_id"]
    st = await step_up(hub, sid, "employee.dismiss", emp)
    r = await client.post(
        f"/api/v1/employees/{emp}/dismiss", headers={**h, **st, **idem()}, json={"reason": "پایان"}
    )
    assert r.status_code == 200, r.text
    moved = await su.fetch(
        """SELECT m.note, m.tags, s.code AS source FROM core.employee_memory m JOIN core.employees s
             ON s.id = m.source_employee_id JOIN core.employees e ON e.id = m.employee_id WHERE e.code = $1""",
        f"{co}-TECH-MGR",
    )
    assert len(moved) == 2 and all(m["source"] == emp and "transfer" in m["tags"] for m in moved)
    kt = await su.fetchval(
        "SELECT brief FROM work.work WHERE title = $1", f"Knowledge transfer from {emp}"
    )
    assert "2 memory note(s)" in kt


# ----------------------------------------------------------- morning report --
async def test_morning_report_rewrite_keeps_the_numbers(
    su: Any, wk: dict[str, Any], agents: Any
) -> None:
    from hq_api.worker import report
    from hq_api.worker.activities import Activities

    assert report.same_numbers(
        "کار W-000123 و ۳ تصمیم و $2.94", "سه تصمیم، کار W-000123، مبلغ $2.94"
    )
    assert not report.same_numbers("۳ تصمیم", "۴ تصمیم")
    holding = await wk["hub"].companies.holding()
    acts = Activities(
        wk["hub"], None, router=agents.router, gateway=agents.gateway, live=agents.live
    )
    today_title = await su.fetchval("SELECT 1")
    assert today_title
    await su.execute(
        "UPDATE work.work SET title = title || ' (old)' WHERE company_id = $1 AND title LIKE 'Morning report %'",
        holding.id,
    )
    agents.fake.enqueue(f"{holding.code}-SYS", "گزارش خوش‌خوان امروز: همه چیز آرام است.")
    out = await acts.morning_report()
    assert out["created"] is True and out["rewritten"]
    pdl = await su.fetchrow(
        "SELECT title, produced_with FROM cartable.deliverables WHERE ref = $1", out["rewritten"]
    )
    assert (
        pdl["title"].endswith("(متن خوش‌خوان)")
        and json.loads(pdl["produced_with"])["model"] == "claude-sonnet-5-5"
    )
    await su.execute(
        "UPDATE work.work SET title = title || ' (old)' WHERE company_id = $1 AND title LIKE 'Morning report %' AND title NOT LIKE '%(old)'",
        holding.id,
    )
    agents.fake.enqueue(
        f"{holding.code}-SYS", "امروز 999999 کار تازه داریم."
    )  # a number the report never had
    out = await acts.morning_report()
    assert out["created"] is True and out["rewritten"] is None
    noti = await su.fetchval(
        "SELECT link_ref FROM notify.notifications WHERE link_ref = $1", out["deliverable"]
    )
    assert noti == out["deliverable"]


# ----------------------------------------------------------- through Temporal --
async def test_a_run_end_to_end_through_temporal(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    wk: dict[str, Any],
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    from temporalio.worker import Worker

    from hq_api.agents.dispatch import Dispatcher
    from hq_api.worker.activities import Activities
    from hq_api.worker.workflows import WORKFLOWS

    tq = f"agents-test-{uuid.uuid4().hex[:6]}"
    acts = Activities(
        wk["hub"], wk["client"], router=agents.router, gateway=agents.gateway, live=agents.live
    )
    co = (await new_company())["code"]
    await su.execute(
        "UPDATE agents.runs SET dispatched_at = now() WHERE state = 'queued' AND dispatched_at IS NULL"
    )
    w = await order(client, owner, co, title="از راه تمپورال")
    agents.fake.enqueue(
        f"{co}-CEO",
        step(
            "تحویل", ("deliver", {"work_ref": w["ref"], "title_fa": "تحویل", "body_md": "انجام شد"})
        ),
    )
    async with Worker(wk["client"], task_queue=tq, workflows=WORKFLOWS, activities=acts.all()):
        d = Dispatcher(wk["hub"], wk["client"], tq)
        assert await d.once() == 1
        assert await d.once() == 0  # dispatched once
        row = (await runs_of(su, f"{co}-CEO"))[-1]
        handle = wk["client"].get_workflow_handle(f"agent-run-{row['id']}")
        result = await asyncio.wait_for(handle.result(), timeout=60)
    assert result["state"] == "done", result
    assert (
        await su.fetchval("SELECT status FROM work.work WHERE id = $1", uuid.UUID(w["id"]))
        == "delivered"
    )


async def test_quota_alert_reaches_the_stream_and_the_owner(
    hub: Any, su: Any, wk: dict[str, Any]
) -> None:
    from types import SimpleNamespace

    from hq_api.worker.bridge import Bridge

    bridge = Bridge(wk["hub"])
    marker = datetime.now(UTC).isoformat()
    payload = {
        "type": "quota",
        "connection": "claude-max",
        "status": "warning",
        "previous": "ok",
        "window": "five_hour",
        "utilization": "0.8500",
        "resets_at": None,
        "source": "sdk_rate_limit_event",
        "paused_priorities": ["P4"],
        "at": marker,
    }
    msg = SimpleNamespace(
        data=json.dumps(payload).encode(),
        subject="hq.alerts.quota",
        metadata=SimpleNamespace(
            sequence=SimpleNamespace(stream=10**6 + random_code().__hash__() % 1000)
        ),
    )
    await bridge.handle("HQ_ALERTS", msg)
    row = await su.fetchrow(
        "SELECT level, title_fa FROM notify.notifications WHERE link_ref = $1",
        f"quota:warning:{marker}"[:100],
    )
    assert row["level"] == "report" and "هشدار" in row["title_fa"] and "P4" in row["title_fa"]
    await bridge.handle("HQ_ALERTS", msg)  # redelivered: told once
    assert (
        await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_ref = $1",
            f"quota:warning:{marker}"[:100],
        )
        == 1
    )


def test_charter_problems_are_reported(tmp_path: Any) -> None:
    from hq_common import charters

    (tmp_path / "roles").mkdir()
    (tmp_path / "tools.md").write_text(
        "| `work.get` | A0 | `{ref}` | one item |\n| `x.y` | A4 | `{}` | never |\n"
        "| `web.browse` | A0/A2 | `{steps}` | browse |\n| `mcp.call` | per tool | `{server}` | mcp |\n"
        "| `pay.now` | A2/A3 | `{}` | pays |\n| `odd.one` | A0/B9 | `{}` | ? |\n"
    )
    (tmp_path / "roles" / "_common.md").write_text(
        "---\nrole: _common\nversion: 2\n---\nسلام {{employee_code}} {{unknown}}"
    )
    (tmp_path / "roles" / "aa.md").write_text(
        "---\nrole: aa\ntitle_fa: الف\ntitle_en: A\nkind: employee\nscope: company\nmodel: m\neffort: high\n"
        "priority: P3\ntools: [work.get, nope, x.y, web.browse, mcp.call, pay.now, odd.one]\nlimits: {steps_per_run: 2, tokens_per_step: 10, tokens_per_run: 20}\n"
        "version: 3\n---\nبدنه"
    )
    (tmp_path / "roles" / "b.md").write_text("no frontmatter")
    (tmp_path / "roles" / "c.md").write_text(
        "---\nrole: wrong\ntitle_fa: x\ntitle_en: x\nkind: employee\nmodel: m\neffort: high\npriority: P3\nlimits: {steps_per_run: 1, tokens_per_step: 1, tokens_per_run: 1}\nversion: 1\n---\n"
    )
    lib = charters.load(tmp_path)
    assert set(lib.roles) == {"aa"}
    assert lib.roles["aa"].tools == ("work.get", "web.browse", "mcp.call")
    browse, mcp = lib.tools["web.browse"], lib.tools["mcp.call"]
    assert (browse.cls, browse.classes, browse.per_tool) == ("A2", ("A0", "A2"), False)
    assert (mcp.cls, mcp.per_tool) == ("A2", True)
    assert any("pay.now" in p and "A3" in p for p in lib.problems)  # the highest class decides
    assert "odd.one" not in lib.tools  # an unknown class: not a tool
    assert any("nope" in p for p in lib.problems) and any("A4" in p for p in lib.problems)
    assert any("b.md" in p for p in lib.problems) and any("c.md" in p for p in lib.problems)
    assert lib.system_prompt("aa", {"employee_code": "TY-X-01"}).startswith("سلام TY-X-01 ")
    assert lib.common_version == 2 and lib.roles["aa"].ref == "aa@3"
    empty = charters.load(tmp_path / "missing")
    assert empty.roles == {} and len(empty.problems) == 2
    assert timedelta  # imported for symmetry with other tests


@pytest.mark.usefixtures("hiring_open")  # agents propose hires (§18.11)
async def test_month1_bootstrap_is_data_and_applies_once(
    su: Any, hub: Any, new_company: Callable[..., Any]
) -> None:
    from hq_api import bootstrap

    data = bootstrap.load("month1")
    assert {i["role"] for i in data["items"]} == {"cto", "inspector", "aiops_head"}
    company = await new_company()
    one = {**data, "items": [i for i in data["items"] if i["for"] == "companies"]}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        first = await bootstrap.apply(tx, one)
    mine = [c for c in first["created"] if c["assignee"] == f"{company['code']}-TECH-MGR"]
    assert len(mine) == 1  # every company of kind "company", including one added today
    w = await su.fetchrow("SELECT * FROM work.work WHERE ref = $1", mine[0]["ref"])
    assert (w["created_by_kind"], w["created_by_code"], w["budget_tokens"]) == (
        "service",
        "bootstrap",
        60000,
    )
    assert "§6.4" in w["brief"]
    assert (
        await su.fetchval("SELECT trigger FROM agents.runs WHERE work_id = $1", w["id"]) == "work"
    )  # it wakes the CTO like any other work
    async with hub.db.tx(await hub.companies.ids()) as tx:
        again = await bootstrap.apply(tx, one)
    assert again["created"] == [] and again["skipped"] >= len(first["created"])
    with pytest.raises(ValueError):
        bootstrap.load("../etc")


async def test_the_checker_checks_where_a_connection_really_went() -> None:
    """Review of 5.1: a name resolved once for the check and again for the
    connection (DNS rebinding) is caught on the connected socket itself,
    before the request is sent; NAT64 and IPv4-in-IPv6 are not public."""
    from hq_api.domain import sites as site_seed

    for private in ("64:ff9b::a0a:102", "64:ff9b:1::1", "::ffff:10.10.1.2", "2002:a0a:102::1"):
        assert site_seed.not_public(private), private
    assert not site_seed.not_public("2606:4700:4700::1111")
    got: list[bytes] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        got.append(await reader.read(100))
        writer.write(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        c = checks.Checker(tls=False, resolver=_public)
        async with httpx.AsyncClient(timeout=5) as http:
            with pytest.raises(checks.PrivateAddress):
                await c._fetch(http, "GET", f"http://127.0.0.1:{port}/", "127.0.0.1")
        await asyncio.sleep(0.1)
        assert got in ([], [b""])  # connected, refused, not a byte of the request sent
    finally:
        server.close()
        await server.wait_closed()
    assert checks._cert_days_left("127.0.0.1") is None
