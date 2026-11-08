"""W11 H (2026-11-08). The owner, on the PC CTO's output (IG-Hub is not among Pro-Chart's servers;
the account names and the read command cannot be registered) and on the account living on IG-Hub:

H1  a company's technical role works on another company's server by the rule of linked.read
    (`via: linked`): links not enforced, an `on` link, or the company present in the session;
    `server.map` lists those servers; every job audited on both companies;
H2  `connection.set`: an agent registers a connection's non-secret settings (accounts, via IG-Hub,
    a read-only command, channels, a site); a secret-looking value and a command that is not
    read-only are refused; the order's session hears it;
H3  the capability brief says the account is on IG-Hub and who registers it; the owner never reads
    «Instagram is not connected» as his job.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import capabilities as CAP
from hq_api.domain import connections as CN
from hq_api.domain import links as LK
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p17_runners import pair
from .test_p21_routing_orders import all_tx, make_order, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued


async def set_connection(
    client: httpx.AsyncClient, code: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        "/internal/v1/connections/set", json=body, headers=await agent_headers(code)
    )


# ===================================================================== H2 + H3 ==
async def test_a_technical_role_registers_another_companys_instagram_and_secrets_are_refused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    ig, pc = await new_company(), await new_company()
    igc, pcc = ig["code"], pc["code"]
    body = {
        "company": pcc, "kind": "instagram", "accounts": ["@Pro.Chart", "prochart.edu"],
        "via": "ig_hub", "server": {"company": igc, "name": "IG-Hub"},
        "read_command": "cat /srv/ig/daily.json",
    }  # fmt: skip
    # IG's CTO (technical, links not enforced): PC's connection is within reach
    r = await set_connection(client, f"{igc}-TECH-MGR", body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["company"] == pcc and out["kind"] == "instagram" and out["state"] == "connected"
    assert out["config"]["accounts"] == ["Pro.Chart", "prochart.edu"]
    assert out["config"] == {**out["config"], "via": "ig_hub", "command": "cat /srv/ig/daily.json",
                             "server": {"company": igc, "name": "IG-Hub"}}  # fmt: skip
    assert out["secret"] == "missing"  # never set here
    rows = await su.fetch(
        """SELECT c.code, a.summary FROM audit.entries a JOIN core.companies c ON c.id = a.company_id
           WHERE a.action = 'connection.set' AND a.target_ref = $1 ORDER BY c.code""",
        f"{pcc}:instagram",
    )
    assert {r["code"] for r in rows} == {igc, pcc} and all("(linked)" in r["summary"] for r in rows)
    # PC's media director for its own company: the accounts only (the rest is kept)
    r = await set_connection(
        client, f"{pcc}-MEDIA-MGR", {"kind": "instagram", "accounts": ["@pro.chart"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["config"]["accounts"] == ["pro.chart"] and r.json()["config"]["command"]
    # a secret-looking value, anywhere: refused with the field named, nothing stored
    for bad in (
        {"kind": "instagram", "accounts": ["@x"], "handle": "sk-ant-api03-" + "Q" * 40},
        {"kind": "telegram", "channels": [{"chat": "@coinepro", "title_fa": "bot token 123456"}]},
        {"kind": "instagram", "read_command": "curl -H 'Authorization: Bearer abc' https://x"},
    ):
        r = await set_connection(client, f"{pcc}-MEDIA-MGR", bad)
        assert r.status_code == 422, (bad, r.text)
    assert "Q" * 40 not in json.dumps(
        await su.fetchval(
            "SELECT config::text FROM growth.connections WHERE company_id = $1 AND kind = 'instagram'",
            pc["id"],
        )
    )
    # a command that is not read-only: refused in one line
    r = await set_connection(
        client, f"{pcc}-MEDIA-MGR", {"kind": "instagram", "read_command": "rm -rf /srv/ig"}
    )
    assert r.status_code == 422 and r.json()["message_fa"] == CN.NOT_READ_ONLY_FA, r.text
    r = await set_connection(
        client, f"{pcc}-MEDIA-MGR", {"kind": "instagram", "read_command": "cat x > y"}
    )
    assert r.status_code == 422
    # a writer: never; a non-technical role of another company: never
    r = await set_connection(client, f"{pcc}-SALES-MGR", {"kind": "instagram", "accounts": ["@x"]})
    assert r.status_code == 403
    r = await set_connection(
        client, f"{igc}-MEDIA-MGR", {"company": pcc, "kind": "instagram", "accounts": ["@x"]}
    )
    assert r.status_code == 403
    # links enforced and no link: IG's CTO is out of reach; along an `on` link it is back
    await su.execute("UPDATE owner.settings SET links_enforced = true WHERE id = 1")
    try:
        r = await set_connection(
            client, f"{igc}-TECH-MGR", {"company": pcc, "kind": "instagram", "accounts": ["@pc.y"]}
        )
        assert r.status_code == 403, r.text
        holding = await hub.companies.holding()
        async with await all_tx(hub) as tx:
            await LK.create(
                tx, holding.id, LK.LinkIn(**{"from": pcc, "to": igc, "kind": "publishes"})
            )
        r = await set_connection(
            client, f"{igc}-TECH-MGR", {"company": pcc, "kind": "instagram", "accounts": ["@pc.y"]}
        )
        assert r.status_code == 200, r.text
    finally:
        await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")
    # telegram channels and a site, by the CEO
    r = await set_connection(client, f"{pcc}-CEO", {"kind": "telegram", "channels": [
        {"chat": "@coinepro_news", "title_fa": "اخبار", "role": "main"}, {"chat": "-100123456789"}]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert [c["chat"] for c in r.json()["config"]["channels"]] == [
        "@coinepro_news",
        "-100123456789",
    ]
    r = await set_connection(
        client, f"{pcc}-CEO", {"kind": "search_console", "site_url": "https://pro-chart.com/"}
    )
    assert r.status_code == 200 and r.json()["config"]["site_url"] == "https://pro-chart.com/"
    # the order's session hears it: the run belongs to an order's work (the media director holds a
    # reel order and may set the connection)
    out2 = await post_order(client, owner, f"برای {pcc} یک ریلز آموزشی بساز {words()}")
    ref = out2["ref"]
    route = next(x for x in out2["routes"] if x["company"] == pcc)
    holder = route["to"]
    assert holder == f"{pcc}-MEDIA-MGR"
    await refuse_queued(su, route["work_ref"])
    # a running run of the holder ON the order's work (the registry's token binds to it)
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE r.employee_id = e.id AND e.code = $1 AND r.state = 'running'""",
        holder,
    )
    await su.execute(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               started_at, token_expires_at)
           SELECT w.company_id, e.id, w.id, 'work', 'test', 'running', now(), now() + interval '1 hour'
           FROM work.work w, core.employees e WHERE w.ref = $1 AND e.code = $2""",
        route["work_ref"], holder,
    )  # fmt: skip
    headers = await agent_headers(holder)
    r = await client.post("/internal/v1/connections/set", headers=headers,
                          json={"kind": "instagram", "accounts": ["@pro.chart", "@pc.second"]})  # fmt: skip
    assert r.status_code == 200, r.text
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"].startswith("اتصال اینستاگرام"), rep["steps"][-1]
    assert "2 حساب" in rep["steps"][-1]["what_fa"]
    assert "2 حساب" in (rep["memory_md"] or "")


async def test_the_brief_says_the_account_lives_on_ig_hub_and_the_owner_never_reads_not_connected(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
           VALUES ($1, 'instagram', 'اینستاگرام (از راه IG-Hub)',
                   '{"via": "ig_hub", "accounts": [], "server": {"company": "IG", "name": "IG-Hub"}}'::jsonb,
                   'seed')""",
        company["id"],
    )
    hub_setting = CN.ig_hub()
    assert hub_setting == {"company": "IG", "server": "IG-Hub"}  # seed/channels.yaml, not code
    # the owner's line: the account exists; the technical team's step, never his
    need = CN.missing("instagram", {"via": "ig_hub", "accounts": []}, False)
    assert need == ["حساب روی IG-Hub است؛ تیم فنی آن را به هاب معرفی میکند"]
    assert CN.missing("instagram", {"accounts": []}, False) == [
        "نام حساب‌های اینستاگرام", "دستور فقط‌خواندنی خواندن عددها روی IG-Hub",
    ]  # fmt: skip
    # the capability brief (every run and talk persona): where the account is and who registers it
    async with await all_tx(hub) as tx:
        brief = await CAP.brief(tx, company["id"], n8n_up=False)
    ig = next(c for c in brief["your_company"]["connections"] if c["kind"] == "instagram")
    assert ig["state"] == "not_connected" and "IG-Hub" in ig["note"] and "company IG" in ig["note"]
    assert "connection.set" in ig["note"] and "server.map" in ig["note"]
    assert "IGHUB_PUBLISH_API.md" in ig["note"] and "NOT missing" in ig["note"]
    assert all(
        "note" not in c for c in brief["your_company"]["connections"] if c["kind"] != "instagram"
    )
    # the owner's blocker for a run that met the Instagram connection missing
    made = await make_order(hub, company, WORK_TEXT.format(co=company["code"], w=words()))
    ref, w = made["ref"], made["work"]
    await refuse_queued(su, w["ref"])
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               priority, started_at, finished_at)
           SELECT company_id, assignee_id, id, 'work', 'ig', 'done', 'P2', now(), now()
           FROM work.work WHERE id = $1 RETURNING id""",
        w["id"],
    )
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, summary_fa, actions)
           SELECT $1, company_id, 1, 'x', $2::jsonb FROM agents.runs WHERE id = $1""",
        rid,
        json.dumps([{"tool": "instagram", "outcome": "refused", "code": "channel_not_configured"}]),
    )
    rep = await report(client, owner, ref)
    [b] = [x for x in rep["blockers"] if x["kind"] == "connection_missing"]
    assert (
        b["title_fa"] == "حساب روی IG-Hub است؛ تیم فنی آن را به هاب معرفی میکند"
        and b["fix"] is None
    )
    assert "وصل نیست" not in b["title_fa"]


# ===================================================================== H1 ==
async def test_a_technical_role_works_on_another_companys_server_by_the_linked_rule(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    ig, pc = await new_company(), await new_company()
    igc, pcc = ig["code"], pc["code"]
    await pair(client, hub, owner_session, ig, "IG-Hub")
    await pair(client, hub, owner_session, pc, "pc-web")
    cto = await agent_headers(f"{pcc}-TECH-MGR")
    # server.map without a server: PC's CTO sees IG-Hub too (links not enforced)
    r = await client.get("/internal/v1/servers", headers=cto)
    assert r.status_code == 200, r.text
    listed = {(s["company"], s["name"]) for s in r.json()}
    assert {(pcc, "pc-web"), (igc, "IG-Hub")} <= listed
    # a read job on IG-Hub by PC's CTO: via linked, audited on both companies
    r = await client.post(
        "/internal/v1/servers/jobs", headers={**cto, **idem()},
        json={"kind": "read", "server": "IG-Hub", "company": igc, "args": {"path": "/etc/hostname"}, "wait_s": 0},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    job = r.json()["job"]
    row = await su.fetchrow(
        "SELECT actor_code, on_behalf_code FROM infra.server_jobs WHERE id = $1", job["id"]
    )
    assert row["actor_code"] == f"{pcc}-TECH-MGR" and row["on_behalf_code"] is None
    trails = await su.fetch(
        """SELECT c.code FROM audit.entries a JOIN core.companies c ON c.id = a.company_id
           WHERE a.action = 'server.read' AND a.summary LIKE $1""",
        f"%via linked, job {job['id']}%",
    )
    assert {t["code"] for t in trails} == {igc, pcc}
    # the CTO reads its own job back
    r = await client.get(f"/internal/v1/servers/jobs/{job['id']}", headers=cto)
    assert r.status_code == 200
    # a destructive command still waits for the owner's seal, as on its own server
    r = await client.post(
        "/internal/v1/servers/jobs", headers={**cto, **idem()},
        json={"kind": "exec", "server": "IG-Hub", "company": igc, "args": {"cmd": "dropdb prod"}, "wait_s": 0},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["job"]["state"] == "awaiting_seal", r.text
    # the media director (not technical) still needs an accepted request
    r = await client.post(
        "/internal/v1/servers/jobs", headers={**(await agent_headers(f"{pcc}-MEDIA-MGR")), **idem()},
        json={"kind": "read", "server": "IG-Hub", "company": igc, "args": {"path": "/etc/hostname"}, "wait_s": 0},
    )  # fmt: skip
    assert r.status_code == 403 and "other_company" in r.text
    # links enforced: out of reach without an `on` link; back along one
    await su.execute("UPDATE owner.settings SET links_enforced = true WHERE id = 1")
    try:
        r = await client.get("/internal/v1/servers", headers=cto)
        assert (igc, "IG-Hub") not in {(s["company"], s["name"]) for s in r.json()}
        r = await client.post(
            "/internal/v1/servers/jobs", headers={**cto, **idem()},
            json={"kind": "read", "server": "IG-Hub", "company": igc, "args": {"path": "/etc/hostname"}, "wait_s": 0},
        )  # fmt: skip
        assert r.status_code == 403 and "other_company" in r.text
        holding = await hub.companies.holding()
        async with await all_tx(hub) as tx:
            await LK.create(
                tx, holding.id, LK.LinkIn(**{"from": pcc, "to": igc, "kind": "publishes"})
            )
        r = await client.get("/internal/v1/servers", headers=cto)
        assert (igc, "IG-Hub") in {(s["company"], s["name"]) for s in r.json()}
        r = await client.post(
            "/internal/v1/servers/jobs", headers={**cto, **idem()},
            json={"kind": "read", "server": "IG-Hub", "company": igc, "args": {"path": "/etc/hostname"}, "wait_s": 0},
        )  # fmt: skip
        assert r.status_code == 201, r.text
    finally:
        await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")
    # the capability brief tells the technical role its reach; others their own servers only
    lib = hub.charters
    assert lib is not None
    cto_c, media_c = lib.get("cto"), lib.get("media_director")
    assert cto_c is not None and media_c is not None
    async with await all_tx(hub) as tx:
        b = await CAP.brief(
            tx, pc["id"], n8n_up=False, role="cto", tools=cto_c.tools, scope="company"
        )
        m = await CAP.brief(tx, pc["id"], n8n_up=False, role="media_director", tools=media_c.tools,
                            scope="company")  # fmt: skip
    assert (
        f"{igc} · IG-Hub" in b["technical"]["servers"]
        and "every company" in b["technical"]["reach"]
    )
    assert b["technical"]["servers"][0] == f"{pcc} · pc-web"  # its own first
    assert (
        f"{igc} · IG-Hub" not in m["technical"]["servers"]
        and "your company" in m["technical"]["reach"]
    )
