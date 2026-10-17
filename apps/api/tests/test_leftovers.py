"""Prompt 05 §1: what the review of 04.1 left (docs/server-prompts/PROMPT_05_AGENTS.md).

Each test was written first and failed on the 04.1 code."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.hub import Hub

from .conftest import agent_headers, idem, service_headers, step_up, superuser
from .soft_authenticator import SoftAuthenticator, b64url, unb64url
from .test_identity import BASE, enrolled, login

KS = "/internal/v1/control/kill-switch"
FREEZE = "/internal/v1/control/deploy-freeze"


# ---------------------------------------------------------------- 1.1 -------
async def test_owner_reengaging_an_agent_switch_takes_it_over(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    scope = f"company:{co}"
    r = await client.post(
        KS, headers={**ceo, **idem()}, json={"scope": scope, "state": "engaged", "reason": "ceo"}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": scope, "state": "engaged", "reason": "owner keeps it"},
    )
    assert r.status_code == 200
    mine = next(s for s in r.json()["companies"] if s["company"] == co)
    assert mine["state"] == "engaged" and mine["changed_by"] == "owner"
    r = await client.post(
        KS, headers={**ceo, **idem()}, json={"scope": scope, "state": "released", "reason": "ceo"}
    )
    assert r.status_code == 403, r.text  # the owner's now: owner + step-up only


async def test_agent_release_reads_the_switch_under_a_row_lock(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    ceo = await agent_headers(f"{co}-CEO")
    scope = f"company:{co}"
    r = await client.post(
        KS, headers={**ceo, **idem()}, json={"scope": scope, "state": "engaged", "reason": "ceo"}
    )
    assert r.status_code == 200
    su = await superuser()
    tr = su.transaction()
    await tr.start()
    try:
        # Someone else holds the row (as the owner's engage would): the agent's
        # release must wait for it instead of judging a stale owner.
        await su.execute(
            "SELECT 1 FROM control.kill_switches WHERE company_id = $1 FOR UPDATE", company["id"]
        )
        release = asyncio.create_task(
            client.post(
                KS,
                headers={**ceo, **idem()},
                json={"scope": scope, "state": "released", "reason": "ceo"},
            )
        )
        await asyncio.sleep(1.0)
        assert not release.done()
        await su.execute(
            """UPDATE control.kill_switches SET changed_by_kind = 'owner', changed_by_code = 'owner'
               WHERE company_id = $1""",
            company["id"],
        )
    finally:
        await tr.commit()
        await su.close()
    r = await release
    assert r.status_code == 403, r.text  # judged on the owner's takeover, not the stale row


# ---------------------------------------------------------------- 1.2 -------
async def test_forged_assertion_never_flags_or_alarms(
    hub: Hub, client: httpx.AsyncClient, su: Any
) -> None:
    auth = await enrolled(hub, client)
    assert (await login(client, auth)).status_code == 200
    counts = """SELECT (SELECT count(*) FROM auth.passkeys WHERE flagged_at IS NOT NULL),
                       (SELECT count(*) FROM audit.entries WHERE action = 'auth.passkey_clone_suspected'),
                       (SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_kind = 'device')"""
    before = tuple(await su.fetchrow(counts))
    opts = (await client.post(f"{BASE}/passkey/login/options")).json()
    cred = auth.sign(opts, bump=False)  # a stale counter ...
    sig = bytearray(unb64url(cred["response"]["signature"]))
    sig[-1] ^= 0xFF  # ... on a signature the passkey never made
    cred["response"]["signature"] = b64url(bytes(sig))
    r = await client.post(f"{BASE}/passkey/login/verify", json={"credential": cred})
    assert r.status_code == 401
    assert tuple(await su.fetchrow(counts)) == before
    # A genuine stale counter (a real clone) is still caught.
    r = await login(client, auth, bump=False)
    assert r.status_code == 401
    assert tuple(await su.fetchrow(counts)) == tuple(n + 1 for n in before)


async def test_registration_requires_a_discoverable_passkey(
    client: httpx.AsyncClient, hub: Hub
) -> None:
    from .test_identity import enrolment_token

    opts = await client.post(
        f"{BASE}/passkey/register/options", json={"enrolment_token": await enrolment_token(hub)}
    )
    assert opts.status_code == 200
    sel = opts.json()["authenticatorSelection"]
    assert sel["residentKey"] == "required" and sel["userVerification"] == "required"
    login_opts = (await client.post(f"{BASE}/passkey/login/options")).json()
    assert login_opts.get("allowCredentials", []) == []
    assert SoftAuthenticator  # the software authenticator answers discoverable requests


# ---------------------------------------------------------------- 1.8 -------
async def test_releasing_again_is_idempotent(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    ceo = await agent_headers(f"{co}-CEO")
    body = {"scope": f"company:{co}", "state": "released", "reason": "nothing to release"}
    for _ in range(2):
        r = await client.post(KS, headers={**ceo, **idem()}, json=body)
        assert r.status_code == 200, r.text
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    for who in (ceo, service_headers()):
        r = await client.post(
            FREEZE, headers=who, json={"company": co, "until": past, "reason": "lift nothing"}
        )
        assert r.status_code == 200, r.text
    other = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(FREEZE, headers=other, json={"company": co, "until": past, "reason": "x"})
    assert r.status_code == 403  # a no-op still needs the authority to freeze


async def test_a_service_lifts_only_its_own_freeze(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    await su.execute(  # a freeze set by another pipeline
        """INSERT INTO control.deploy_freezes (company_id, until, reason, created_by_kind, created_by_code)
           SELECT id, now() + interval '1 hour', 'other pipeline', 'service', 'other-pipeline'
           FROM core.companies WHERE code = $1""",
        co,
    )
    r = await client.post(
        FREEZE, headers=service_headers(), json={"company": co, "until": past, "reason": "x"}
    )
    assert r.status_code == 403, r.text
    r = await client.post(
        FREEZE, headers=service_headers(), json={"company": co, "until": soon, "reason": "mine"}
    )
    assert r.status_code == 200
    r = await client.post(
        FREEZE, headers=service_headers(), json={"company": co, "until": past, "reason": "done"}
    )
    assert r.status_code == 200
    assert [f["created_by"] for f in r.json()["deploy_freezes"] if f["company"] == co] == [
        "other-pipeline"
    ]


async def test_locked_company_gets_423_from_the_action_gate(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    mgr = await agent_headers(f"{co}-GROWTH-MGR")
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": f"company:{co}", "state": "engaged", "reason": "stop"},
    )
    assert r.status_code == 200
    r = await client.post(
        "/internal/v1/notifications",
        headers=mgr,
        json={"level": "info", "title_fa": "اطلاع"},
    )
    assert r.status_code == 403  # hq.internal: a locked company raises only incidents
    r = await client.post(
        "/internal/v1/notifications",
        headers=mgr,
        json={"level": "urgent", "category": "service_down", "title_fa": "سرویس از کار افتاد"},
    )
    assert r.status_code == 201, r.text  # the incident still gets through
    r = await client.post(
        "/internal/v1/decisions",
        headers={**mgr, **idem()},
        json={"kind": "a3_action", "title": "x", "payload": {"action": "restart", "target": "x"}},
    )
    assert r.status_code == 423 and r.json()["code"] == "company_locked", r.text


# ---------------------------------------------------------------- 1.7 -------
async def test_urgent_quota_holds_under_concurrency(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    # Four 🔴 this hour already: exactly one more may go out as 🔴.
    await su.execute(
        """INSERT INTO notify.notifications (company_id, level, title_fa, source_kind, source_code)
           SELECT $1, 'urgent', 'x', 'agent', $2 FROM generate_series(1, 4)""",
        company["id"],
        f"{co}-CEO",
    )
    senders = [f"{co}-CEO", f"{co}-TECH-MGR", f"{co}-SALES-MGR", f"{co}-HR-MGR"]
    heads = [await agent_headers(code) for code in senders]
    results = await asyncio.gather(
        *(
            client.post(
                "/internal/v1/notifications",
                headers=h,
                json={"level": "urgent", "category": "service_down", "title_fa": "قطعی"},
            )
            for h in heads
        )
    )
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert sorted(r.json()["level"] for r in results) == ["decision"] * 3 + ["urgent"]
    n = await su.fetchval(
        """SELECT count(*) FROM notify.notifications WHERE company_id = $1 AND level = 'urgent'
             AND source_kind = 'agent'""",
        company["id"],
    )
    assert n == 5


# ---------------------------------------------------------------- 1.8 -------
async def test_two_new_companies_never_share_a_colour(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    from .conftest import random_code

    used = await su.fetchval("SELECT count(*) FROM core.companies WHERE color_index IS NOT NULL")
    codes = [random_code("C"), random_code("C")]
    bodies = [
        {"code": c, "name_fa": f"شرکت {c}", "name_en": f"Company {c}", "template": "standard"}
        for c in codes
    ]
    heads = [
        {
            **owner_session["headers"],
            **await step_up(hub, owner_session["session_id"], "company.create", c),
        }
        for c in codes
    ]
    results = await asyncio.gather(
        *(
            client.post("/api/v1/companies", headers=h, json=b)
            for h, b in zip(heads, bodies, strict=True)
        )
    )
    assert [r.status_code for r in results] == [201, 201], [r.text for r in results]
    slots = [r.json()["color_index"] for r in results]
    if used <= 6:
        assert None not in slots and len(set(slots)) == 2
    else:
        assert len({s for s in slots if s is not None}) == len([s for s in slots if s is not None])


# --------------------------------------------------------------- 1.10 -------
async def test_spending_stops_when_the_work_budget_is_used_up(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    r = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co, "title": "بودجه‌دار", "budget": {"tokens": 1000}},
    )
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    # The step that crosses the line is recorded truthfully ...
    await su.execute("UPDATE work.work SET tokens_used = 1200 WHERE id = $1", wid)
    # ... and nothing more is spent after it.
    import asyncpg

    try:
        await su.execute("UPDATE work.work SET tokens_used = 1300 WHERE id = $1", wid)
        raised = None
    except asyncpg.PostgresError as exc:
        raised = exc.sqlstate
    assert raised == "HQB01"
    try:
        await su.execute("UPDATE work.work SET tokens_used = 10 WHERE id = $1", wid)
        raised = None
    except asyncpg.PostgresError as exc:
        raised = exc.sqlstate
    assert raised == "HQV01"  # spending never goes down


async def test_web_step_up_rotates_the_session_cookie(hub: Hub, client: httpx.AsyncClient) -> None:
    from .test_identity import WEB

    auth = await enrolled(hub, client)
    r = await login(client, auth, headers=WEB)
    assert r.status_code == 200
    before = client.cookies.get("hq_session", path="/api")
    opts = await client.post(
        f"{BASE}/step-up/options",
        json={"action": "passkey.register", "target": "self"},
        headers=WEB,
    )
    assert opts.status_code == 200, opts.text
    r = await client.post(
        f"{BASE}/step-up/verify", json={"credential": auth.sign(opts.json())}, headers=WEB
    )
    assert r.status_code == 200, r.text
    after = client.cookies.get("hq_session", path="/api")
    assert before and after and before != after
    assert (await client.get(f"{BASE}/session")).status_code == 200  # the new cookie works
    client.cookies.set("hq_session", before, domain="hq.test", path="/api")
    assert (await client.get(f"{BASE}/session")).status_code == 401  # the old one is worthless
    client.cookies.clear()


# ---------------------------------------------------------------- 1.4 -------
async def test_reanchor_after_a_restore(hub: Hub, su: Any, tmp_path: Any) -> None:
    import json

    from hq_api import audit, reanchor

    anchors = tmp_path / "audit-chain.jsonl"
    # The file remembers a head the restored database never reached.
    lost = {"seq": 10**9, "hash": "a" * 64, "at": "2026-10-17T00:00:00Z"}
    anchors.write_text(json.dumps(lost) + "\n", encoding="utf-8")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert (await audit.verify(tx, anchor_file=anchors))["anchor"] == "mismatch"
    before = await su.fetchval("SELECT count(*) FROM audit.entries WHERE action = 'audit.reanchor'")
    r = await reanchor.reanchor(hub.db, str(anchors), "restore of backup 20261017T000000Z (test)")
    assert r["ok"] is True
    async with hub.db.tx(await hub.companies.ids()) as tx:
        v = await audit.verify(tx, anchor_file=anchors)
    assert v["ok"] is True and v["anchor"] == "ok"
    lines = anchors.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == lost  # nothing is removed from the file
    new = json.loads(lines[-1])
    assert new["reanchor"] is True and new["previous"] == {"seq": lost["seq"], "hash": lost["hash"]}
    after = await su.fetchval("SELECT count(*) FROM audit.entries WHERE action = 'audit.reanchor'")
    assert after == before + 1
    row = await su.fetchrow(
        "SELECT action_class, summary FROM audit.entries WHERE action = 'audit.reanchor' ORDER BY seq DESC LIMIT 1"
    )
    assert row["action_class"] == "A3" and "restore of backup" in row["summary"]
