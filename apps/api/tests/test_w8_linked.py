"""`linked.read` (A0), the owner, 2026-11-06: companies give each other data, like veins (contract
§35.6: a company reads another company's data by the same rule as a cross-company request).

- While the owner's `links_enforced` is off (the default): any active company reads any other
  active company (`via: open`); never the holding, a paused company or an unknown one.
- While it is on: only along an `on` link, either way; refused without one, or with an `off` one,
  in the same 403 as an unknown company.
- Always the caller's own company; a holding reader any company (404 for an unknown one).
- Each `what`: profile (names, departments with their mandate and manager, sites, connections with
  public handles only, servers by name, lines that are on, working groups), kpis (the latest
  values, none guessed), outputs (the last 20, short summaries, the producer's title; with `ref`
  one output's body, only that company's), catalogue (titles, summaries and counts, never the
  tables), connections (state and figures, never the settings or the secret; Instagram's
  accounts), links.
- No customer data or secret: a SALES output is never listed or read; text is masked.
- Each read is audited (A0) on the company that was read.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx

from hq_api.hub import Hub

from .conftest import agent_headers
from .test_w7_links import enforced, link  # noqa: F401 - the fixture

SECRET = "sk-ant-api03-" + "Q" * 40
EMAIL = "ali.rezaei@example.com"


async def read(
    client: httpx.AsyncClient, who: str, company: str, what: str, ref: str | None = None
) -> httpx.Response:
    params = {"company": company, "what": what, **({"ref": ref} if ref else {})}
    return await client.get(
        "/internal/v1/linked/read", headers=await agent_headers(who), params=params
    )


async def output(
    su: Any,
    company_id: Any,
    title: str,
    *,
    summary: str = "خلاصه",
    body: str = "متن کامل",
    department: str | None = None,
) -> str:
    """A deliverable of the company (its CEO's, or of a work in `department`)."""
    work = await su.fetchval(
        """INSERT INTO work.work (company_id, department_id, kind, title, created_by_kind,
               created_by_code)
           VALUES ($1, (SELECT id FROM core.departments WHERE company_id = $1 AND code = $2),
                   'one_off', 'w8 linked', 'owner', 'owner') RETURNING id""",
        company_id,
        department,
    )
    return str(
        await su.fetchval(
            """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary,
                   body, produced_with)
               SELECT $1, $2, e.id, $3, $4, $5, '{}' FROM core.employees e
               WHERE e.company_id = $1 AND e.kind = 'ceo' RETURNING ref""",
            company_id,
            work,
            title,
            summary,
            body,
        )
    )


# ------------------------------------------------------------- who may --
async def test_while_links_are_not_enforced_any_active_company_reads_any_other(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    assert await su.fetchval("SELECT links_enforced FROM owner.settings WHERE id = 1") is False
    a, b, paused = await new_company(), await new_company(), await new_company()
    holding = (await hub.companies.holding()).code
    # no link at all: a manager of A reads B's profile and its connections
    r = await read(client, f"{a['code']}-MEDIA-MGR", b["code"], "profile")
    assert r.status_code == 200, r.text
    assert (r.json()["via"], r.json()["profile"]["code"]) == ("open", b["code"])
    r = await read(client, f"{b['code']}-CEO", a["code"], "connections")
    assert r.status_code == 200 and r.json()["via"] == "open", r.text
    # never the holding, a paused company or one that is not there (the same 403)
    await su.execute("UPDATE core.companies SET status = 'paused' WHERE id = $1", paused["id"])
    hub.companies.invalidate()
    for code in (holding, paused["code"], "NOPEX"):
        r = await read(client, f"{a['code']}-CEO", code, "kpis")
        assert r.status_code == 403 and r.json()["code"] == "policy_denied", (code, r.text)
    # the audit says why it was allowed
    assert (
        await su.fetchval(
            """SELECT summary FROM audit.entries WHERE action = 'linked.read' AND company_id = $1
               ORDER BY seq DESC LIMIT 1""",
            b["id"],
        )
        == f"{a['code']} read profile of {b['code']} (open)"
    )


async def test_while_links_are_enforced_only_along_an_on_link_either_way(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    enforced: None,  # noqa: F811
) -> None:
    a, b, c = await new_company(), await new_company(), await new_company()
    holding = (await hub.companies.holding()).code
    made = await link(client, owner, a["code"], b["code"], "feeds", purpose_fa="آمار بده")
    # A reads B along the link, and B reads A (either way); a manager as much as a CEO
    r = await read(client, f"{a['code']}-GROWTH-MGR", b["code"], "links")
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["company"], got["what"], got["via"]) == (b["code"], "links", "link")
    assert got["name_fa"] == f"شرکت آزمایشی {b['code']}"
    assert got["links"] == [
        {
            "company": a["code"],
            "name_fa": f"شرکت آزمایشی {a['code']}",
            "kind": "feeds",
            "purpose_fa": "آمار بده",
            "outgoing": False,
        }
    ]
    r = await read(client, f"{b['code']}-CEO", a["code"], "kpis")
    assert r.status_code == 200 and r.json()["via"] == "link", r.text
    # no link: the same 403 as a company that is not there
    no_link = await read(client, f"{a['code']}-CEO", c["code"], "kpis")
    unknown = await read(client, f"{a['code']}-CEO", "NOPEX", "kpis")
    assert no_link.status_code == unknown.status_code == 403
    assert no_link.json()["code"] == unknown.json()["code"] == "policy_denied"
    # an `off` link is no link
    await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "off"})
    assert (await read(client, f"{a['code']}-CEO", b["code"], "kpis")).status_code == 403
    await client.patch(f"/api/v1/links/{made['id']}", headers=owner, json={"state": "on"})
    assert (await read(client, f"{a['code']}-CEO", b["code"], "kpis")).status_code == 200
    # its own company: always, without a link
    r = await read(client, f"{c['code']}-GROWTH-MGR", c["code"], "connections")
    assert r.status_code == 200 and r.json()["via"] == "own", r.text
    # the holding is never read along a link (it has none); the owner and services never
    r = await read(client, f"{a['code']}-CEO", holding, "outputs")
    assert r.status_code == 403
    r = await client.get(
        "/internal/v1/linked/read", headers=owner, params={"company": b["code"], "what": "kpis"}
    )
    assert r.status_code in (401, 403)
    # each read is audited (A0) on the company that was read; a refusal writes nothing
    rows = await su.fetch(
        """SELECT e.action_class, e.target_ref, e.summary, e.actor_code FROM audit.entries e
           WHERE e.action = 'linked.read' AND e.company_id = $1 ORDER BY e.seq""",
        b["id"],
    )
    assert [r["target_ref"] for r in rows] == [f"{b['code']}:links", f"{b['code']}:kpis"]
    assert {r["action_class"] for r in rows} == {"A0"}
    assert rows[0]["actor_code"] == f"{a['code']}-GROWTH-MGR"
    assert rows[0]["summary"] == f"{a['code']} read links of {b['code']} (link)"
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'linked.read' AND company_id = $1",
            c["id"],
        )
        == 1  # its own read only: the refused one wrote nothing
    )


async def test_a_holding_reader_reads_any_company(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    a = await new_company()
    holding = (await hub.companies.holding()).code
    r = await read(client, "HQ-ADV", a["code"], "outputs")
    assert r.status_code == 200, r.text
    assert r.json()["via"] == "holding" and r.json()["outputs"] == []
    assert r.json()["note_fa"] == "این شرکت هنوز خروجی‌ای ندارد."
    r = await read(client, "HQ-ADV", "NOPEX", "kpis")
    assert r.status_code == 404 and r.json()["message_fa"], r.text
    r = await read(client, "HQ-ADV", holding, "links")
    assert r.status_code == 200 and r.json()["via"] == "own"
    # the advisor's test run ends here, so a later test can claim a real advisor run
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = 'HQ-ADV' AND r.state = 'running'
             AND r.reason = 'test'"""
    )


async def test_a_ref_goes_only_with_outputs_and_the_input_is_checked(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    a = await new_company()
    ceo = f"{a['code']}-CEO"
    r = await read(client, ceo, a["code"], "kpis", ref="O-000001")
    assert r.status_code == 422 and r.json()["message_fa"], r.text
    for params in (
        {"company": a["code"], "what": "secrets"},
        {"company": "bad code", "what": "kpis"},
        {"company": a["code"], "what": "outputs", "ref": "W-000001"},
        {"what": "kpis"},
    ):
        r = await client.get(
            "/internal/v1/linked/read", headers=await agent_headers(ceo), params=params
        )
        assert r.status_code == 422, (params, r.text)


# ------------------------------------------------------------ each what --
async def test_kpis_carry_their_latest_values_and_none_is_guessed(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = await new_company(), await new_company()
    await link(client, owner, a["code"], b["code"], "serves")
    await su.execute(
        """INSERT INTO governance.kpis (company_id, key, card, name_fa, unit, direction, source,
               freshness_hours, origin, last_value, last_at, target)
           VALUES ($1, 'growth.followers', 'growth', 'فالوور', 'نفر', 'up', '{"kind": "manual"}',
                   24, 'owner', 1520, now(), 2000),
                  ($1, 'growth.empty', 'growth', 'بی‌مقدار', '', 'up', '{"kind": "manual"}',
                   24, 'owner', NULL, NULL, NULL)""",
        b["id"],
    )
    r = await read(client, f"{a['code']}-CEO", b["code"], "kpis")
    assert r.status_code == 200, r.text
    got = {k["key"]: k for k in r.json()["kpis"]}
    assert got["growth.followers"]["value"] == 1520 and got["growth.followers"]["state"] == "ok"
    assert got["growth.followers"]["target"] == 2000 and got["growth.followers"]["unit"] == "نفر"
    assert got["growth.empty"]["value"] is None and got["growth.empty"]["state"] == "no_source"
    assert r.json()["note_fa"] is None
    assert set(got["growth.followers"]) == {
        "key", "name_fa", "card", "unit", "direction", "value", "at", "target", "target_max",
        "state",
    }  # fmt: skip


async def test_outputs_are_the_last_twenty_and_one_body_only_of_that_company(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = await new_company(), await new_company()
    await link(client, owner, b["code"], a["code"], "publishes")
    long = "گزارش " * 200
    first = await output(
        su, b["id"], "گزارش هفته", summary=long, body=f"بدنه با {SECRET} و {EMAIL}"
    )
    hidden = await output(su, b["id"], "پاسخ به کاربر", summary=EMAIL, department="SALES")
    growth = await output(su, b["id"], "برنامه‌ی رشد", department="GROWTH")
    for i in range(20):
        await output(su, b["id"], f"خروجی {i}")
    mine = await output(su, a["id"], "خروجی خودم")
    ceo = f"{a['code']}-CEO"
    r = await read(client, ceo, b["code"], "outputs")
    assert r.status_code == 200, r.text
    rows = r.json()["outputs"]
    assert len(rows) == 20 and [x["title"] for x in rows[:2]] == ["خروجی 19", "خروجی 18"]
    refs = {x["ref"] for x in rows}
    assert hidden not in refs and first not in refs  # the oldest fell off; SALES never listed
    assert set(rows[0]) == {"ref", "title", "summary", "producer", "at"}
    assert rows[0]["producer"] and rows[0]["producer"] != f"{b['code']}-CEO"  # a title, not a code
    # an older one is still read by its ref, its summary short, its body masked
    r = await read(client, ceo, b["code"], "outputs", ref=first)
    assert r.status_code == 200, r.text
    one = r.json()["output"]
    assert one["ref"] == first and len(one["summary"]) <= 400 and one["summary"].endswith("…")
    assert SECRET not in one["body"] and EMAIL not in one["body"] and one["truncated"] is False
    assert r.json()["outputs"] is None
    r = await read(client, ceo, b["code"], "outputs", ref=growth)
    assert r.status_code == 200 and r.json()["output"]["title"] == "برنامه‌ی رشد"
    # a SALES output, another company's ref, an unknown ref: not found
    for ref in (hidden, mine, "O-999999999"):
        r = await read(client, ceo, b["code"], "outputs", ref=ref)
        assert r.status_code == 404 and r.json()["message_fa"], (ref, r.text)
    # a long body comes in part, and says so
    big = await output(su, b["id"], "بلند", body="الف" * 20_000)
    r = await read(client, ceo, b["code"], "outputs", ref=big)
    assert len(r.json()["output"]["body"]) == 12_000 and r.json()["output"]["truncated"] is True
    audited = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'linked.read' AND target_ref = $1",
        f"{b['code']}:outputs:{first}",
    )
    assert audited == 1


async def test_the_catalogue_in_short_never_its_tables(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = await new_company(), await new_company()
    await link(client, owner, a["code"], b["code"], "supports")
    ceo = f"{a['code']}-CEO"
    r = await read(client, ceo, b["code"], "catalogue")
    assert r.status_code == 200 and r.json()["catalogue"] is None
    assert r.json()["note_fa"] == "برای این شرکت هنوز فهرست کاملی ساخته نشده است."
    sections = [
        {
            "key": "products",
            "title_fa": "محصولات و سرویس‌ها",
            "summary_fa": "سه سرویس اصلی و یک سایت. " * 40,
            "tables": [{"title_fa": "کانتینرها", "columns": ["نام"], "rows": [["db-secret-x"]]}],
            "notes_fa": ["یادداشت"],
            "count": 3,
        },
        {"key": "data", "title_fa": "داده‌ها", "summary_fa": None, "tables": [], "notes_fa": [],
         "count": None},
    ]  # fmt: skip
    await su.execute(
        """INSERT INTO infra.catalogues (company_id, state, sections, deliverable_ref,
               started_by_kind, started_by_code, created_at)
           VALUES ($1, 'done', $2::jsonb, 'O-000123', 'owner', 'owner', now() - interval '1 day'),
                  ($1, 'running', '[]', NULL, 'owner', 'owner', now())""",
        b["id"],
        json.dumps(sections, ensure_ascii=False),
    )
    r = await read(client, ceo, b["code"], "catalogue")
    assert r.status_code == 200, r.text
    cat = r.json()["catalogue"]
    assert cat["state"] == "done" and cat["deliverable"] == "O-000123"  # the finished one first
    assert [s["key"] for s in cat["sections"]] == ["products", "data"]
    assert cat["sections"][0]["count"] == 3 and len(cat["sections"][0]["summary_fa"]) <= 400
    assert set(cat["sections"][0]) == {"key", "title_fa", "summary_fa", "count"}
    assert "db-secret-x" not in r.text and "tables" not in r.text


async def test_connections_are_state_and_figures_never_settings_or_secrets(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    a, b = await new_company(), await new_company()
    await link(client, owner, a["code"], b["code"], "feeds")
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set)
           VALUES ($1, 'search_console', 'سرچ کنسول', $2::jsonb, true)""",
        b["id"],
        json.dumps({"site_url": "https://example.ir/", "note": SECRET}),
    )
    for account, value in (("coinepro_signals", 900), ("@CoinePro.FX", 1200)):
        await su.execute(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES ($1, 'instagram', current_date, 'followers', $2, $3, 'test')""",
            b["id"],
            account.lstrip("@").lower(),
            value,
        )
    today = date.today()
    for days_ago, value in ((0, 30), (13, 20), (20, 99)):
        await su.execute(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES ($1, 'search_console', $2, 'clicks', '', $3, 'test')""",
            b["id"],
            today - timedelta(days=days_ago),
            value,
        )
    r = await read(client, f"{a['code']}-GROWTH-MGR", b["code"], "connections")
    assert r.status_code == 200, r.text
    got = {c["kind"]: c for c in r.json()["connections"]}
    sc = got["search_console"]
    assert sc["state"] == "connected" and set(sc) == {
        "kind", "label_fa", "state", "last_read_at", "daily", "accounts",
    }  # fmt: skip
    assert sorted(d["value"] for d in sc["daily"]) == [20, 30]  # 14 days, not 20
    assert sc["accounts"] is None  # Instagram's only
    assert all(
        c["state"] == "not_connected"
        for k, c in got.items()
        if k not in ("search_console", "instagram")
    )
    assert SECRET not in r.text and "example.ir" not in r.text and "secret" not in r.text
    assert r.json()["note_fa"] is None
    # Instagram: the accounts IG-Hub reads for the company, as its figures name them
    ig = got["instagram"]
    assert ig["accounts"] == ["coinepro.fx", "coinepro_signals"], ig
    assert {d["subject"] for d in ig["daily"]} == {"coinepro.fx", "coinepro_signals"}


async def test_the_profile_says_who_a_company_is_and_what_it_has_never_a_secret(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from hq_api.domain import linked as LD

    a, b = await new_company(), await new_company()
    await su.execute(
        """INSERT INTO ops.sites (company_id, url) VALUES ($1, 'https://example-fx.ir/'),
                  ($1, 'https://user:pw@example-fx.ir/admin')""",
        b["id"],
    )
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set)
           VALUES ($1, 'instagram', 'اینستاگرام', $2::jsonb, false),
                  ($1, 'telegram', 'تلگرام', $3::jsonb, true)""",
        b["id"],
        json.dumps({
            "via": "ig_hub", "accounts": ["@CoinePro.FX", "bad account!"],
            "server": {"company": "IG", "name": "IG-Hub"},
            "command": f"ig-read --token {SECRET}",
        }),
        json.dumps({"channels": [
            {"role": "signal", "title_fa": "کانال سیگنال", "chat": "@coinepro_signal"},
            {"role": "news", "title_fa": "کانال خصوصی", "chat": "-1001234567890"},
        ], "bot_token": SECRET}),
    )  # fmt: skip
    await su.execute(
        """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
           VALUES ($1, 'instagram', current_date, 'followers', 'coinepro.fx', 1200, 'test'),
                  ($1, 'instagram', current_date, 'followers', 'coinepro.edu', 300, 'test')""",
        b["id"],
    )
    await su.execute(
        """INSERT INTO infra.servers (company_id, origin, name, state, hostname, ipv4)
           VALUES ($1, 'attached', 'fx-main', 'online', 'fx-main.internal', '203.0.113.7'),
                  ($1, 'attached', 'fx-old', 'revoked', NULL, NULL)""",
        b["id"],
    )
    await su.execute(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa,
               caps, steps, state)
           VALUES ($1, 'cal_line', 1, 'telegram_post', 'خبر روز', '{}', '[]', 'on'),
                  ($1, 'cal_line', 1, 'telegram_post', 'پیش‌نویس', '{}', '[]', 'draft')""",
        b["id"],
    )
    await su.execute(
        """INSERT INTO growth.memberships (company_id, group_id)
           SELECT $1, id FROM growth.groups WHERE key = 'content'""",
        b["id"],
    )
    r = await read(client, f"{a['code']}-MEDIA-MGR", b["code"], "profile")
    assert r.status_code == 200, r.text
    prof = r.json()["profile"]
    assert (prof["code"], prof["kind"], prof["status"]) == (b["code"], "company", "active")
    assert prof["name_fa"] == f"شرکت آزمایشی {b['code']}" and prof["name_en"] == f"Test {b['code']}"
    depts = {d["code"]: d for d in prof["departments"]}
    assert {"TECH", "GROWTH", "SALES", "MEDIA"} <= set(depts)
    assert depts["MEDIA"]["manager"] == f"{b['code']}-MEDIA-MGR"
    assert depts["SALES"]["mandate"] and len(depts["SALES"]["mandate"]) <= 300
    assert depts["SALES"]["name_en"] == "Sales and Support"
    assert prof["sites"] == ["https://example-fx.ir/"]  # an address with credentials never
    conns = {c["kind"]: c for c in prof["connections"]}
    ig = conns["instagram"]
    assert ig["handles"] == {
        "accounts": ["coinepro.fx"],
        "via": {"server": "IG-Hub", "company": "IG"},
    }
    assert ig["accounts_seen"] == ["coinepro.edu", "coinepro.fx"] and ig["state"] == "connected"
    tg = conns["telegram"]
    assert tg["handles"] == {
        "channels": [
            {"chat": "@coinepro_signal", "title_fa": "کانال سیگنال", "role": "signal"},
            {"chat": None, "title_fa": "کانال خصوصی", "role": "news"},
        ]
    }
    assert tg["accounts_seen"] == []
    assert prof["servers"] == [{"name": "fx-main"}]
    assert [ln["title_fa"] for ln in prof["lines"]] == ["خبر روز"]
    assert prof["lines"][0]["ref"].startswith("LN-")
    assert [g["key"] for g in prof["groups"]] == ["content"] and prof["groups"][0]["state"] == "on"
    for leak in (SECRET, "203.0.113.7", "fx-main.internal", "ig-read", "-1001234567890", "pw@"):
        assert leak not in r.text, leak
    # the same profile for the capability brief, as a plain dict
    async with hub.db.tx(await hub.companies.ids()) as tx:
        plain = await LD.profile(tx, b["id"])
    assert plain == prof
