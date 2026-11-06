"""Prompt 21 part 1 (contract §29.1, §29.2, §29.6, §29.10, §29.14, §29.15):
routing by domain, every order answered, the delegation budget, automatic
hiring, employee state, and the management review's protocol changes."""

from __future__ import annotations

import importlib.util
import json
import random
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.agents.clients import ModelCall
from hq_api.agents.runner import RunCtx, Runner
from hq_api.domain import decisions as D
from hq_api.domain import hiring as HR
from hq_api.domain import humanize as HZ
from hq_api.domain import notify
from hq_api.domain import order_report as OR
from hq_api.domain import oversight as O
from hq_api.domain import routing as RT
from hq_api.domain import tech_summary as TS
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.principal import Principal

from .conftest import agent_headers, idem, running_run, step_up

OWNER = Principal(kind="owner", code="owner", role="owner")
SERVICE = Principal(kind="service", code="servers", role="service")
_SPEC = importlib.util.spec_from_file_location(
    "m0037",
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0037_routing_orders.py",
)
assert _SPEC is not None and _SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MIGRATION)


class Undo(Exception):
    """Rolls a test's transaction back on purpose."""


def clean(text: str | None) -> None:
    """Every owner-facing string passes humanize.check (contract §29.7)."""
    assert HZ.check(text) == [], (text, HZ.check(text))


async def all_tx(hub: Hub) -> Any:
    return hub.db.tx(await hub.companies.ids())


async def set_hiring(su: Any, state: str, mode: str | None) -> None:
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode)
           SELECT id, $1, $2 FROM core.companies WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET state = EXCLUDED.state, mode = EXCLUDED.mode""",
        state,
        mode,
    )


async def envelope(su: Any, company: dict[str, Any], tokens: int = 50_000_000) -> None:
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', $3)
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET token_limit = $3, enabled = true""",
        company["id"],
        company["code"],
        tokens,
    )


@pytest.fixture
async def auto_hiring(su: Any) -> AsyncIterator[None]:
    """Hiring open in mode auto (the owner's decision; migration 0037), closed after."""
    await set_hiring(su, "open", "auto")
    yield
    await set_hiring(su, "closed", None)


async def make_order(
    hub: Hub,
    company: dict[str, Any],
    text: str,
    *,
    department: str | None = None,
    budget: int | None = None,
    routed: bool = True,
) -> dict[str, Any]:
    """An order of the owner as the router leaves it: a root work (the CEO,
    or a department's manager) and its owner.orders row; then the receipt."""
    async with await all_tx(hub) as tx:
        w = await W.create(
            tx,
            OWNER,
            company_id=company["id"],
            company_code=company["code"],
            title=text[:80],
            brief=text,
            kind="one_off",
            priority="P2",
            department_code=department,
            budget=W.BudgetIn(tokens=budget) if budget else None,
        )
        holding = await hub.companies.holding()
        ref = await tx.scalar("SELECT 'F-' || lpad(nextval('owner.order_ref_seq')::text, 4, '0')")
        routes = [
            {"company": company["code"], "to": w["a_code"], "kind": "work", "work_ref": w["ref"]}
        ]
        await tx.exec(
            """INSERT INTO owner.orders (ref, company_id, text, source, routes, routed_by, summary_fa)
               VALUES (:ref, :co, :text, 'text', CAST(:routes AS jsonb), 'rules', :text)""",
            ref=ref,
            co=holding.id,
            text=text,
            routes=json.dumps(routes),
        )
        if routed:
            await OR.on_order_routed(tx, ref)
    return {"ref": ref, "work": w}


async def deliver(client: httpx.AsyncClient, who: str, work_id: Any, title: str) -> httpx.Response:
    return await client.post(
        f"/internal/v1/work/{work_id}/deliver",
        headers={**await agent_headers(who), **idem()},
        json={"title": title, "summary": "خلاصه", "body": "متن خروجی"},
    )


async def report(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/orders/{ref}/report", headers=owner)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def owner_strings(rep: dict[str, Any]) -> list[str]:
    out = [s["what_fa"] for s in rep["steps"]] + [s["who_fa"] for s in rep["steps"]]
    for b in rep["blockers"]:
        out += [b["title_fa"], b["detail_fa"]] + ([b["fix"]["label_fa"]] if b["fix"] else [])
    out += [o["title_fa"] for o in rep["outputs"]]
    if rep["ack"]:
        out.append(rep["ack"]["plan_fa"])
    if rep["summary"]:
        out += list(rep["summary"].values())
    return out


async def end_runs(su: Any, code: str) -> None:
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = $1 AND r.state = 'running' AND r.reason = 'test'""",
        code,
    )


# ============================================================ §29.1 routing ==
def test_the_rules_name_a_domain_for_every_kind() -> None:
    assert (
        RT.finding_domain(protocol="PR-062", area="security", answerable="hub_platform_sre")
        == "infra"
    )
    assert (
        RT.finding_domain(protocol="PR-140", area="security", answerable="hub_platform_sre")
        == "security"
    )
    assert RT.finding_domain(protocol="PR-091", area="product", answerable="cto") == "tech"
    assert RT.finding_domain(protocol="PR-001", area="truth", answerable="manager") == "business"
    assert RT.finding_domain(kind="app_health") == "product"
    assert RT.finding_domain(kind="growth") == "business"
    assert RT.decision_domain("server_destructive") == "infra"
    assert RT.decision_domain("media_series") == "media"
    assert RT.decision_domain("hire") == "business"
    assert RT.notification_domain("backup") == "infra"
    assert RT.notification_domain("revenue_alert") == "revenue"
    assert RT.notification_domain("server_plan") == "business"  # founding is the owner's
    assert RT.notification_domain(None, category="service_down") == "infra"
    assert RT.critical_of(category="service_down") == "product_down"
    assert RT.critical_of(protocol="PR-030", severity="critical") == "data_leak"
    assert RT.critical_of(protocol="PR-030", severity="high") is None
    assert not RT.owner_visible("tech", None)
    assert RT.owner_visible("tech", "data_leak") and RT.owner_visible("media", None)
    assert RT.owner_visible("infra", None, owner_action=True)


async def test_the_sql_rules_of_the_data_move_match_the_code(su: Any) -> None:
    """Migration 0037's rules (SQL) and hq_api.domain.routing say the same."""
    from hq_common import charters

    protocols = O.protocol_file(charters.load().root)
    async with su.transaction():
        await su.execute(MIGRATION.RULES)
        for p in protocols:
            for kind in (None, "security", "code"):
                sql = await su.fetchval(
                    "SELECT pg_temp.finding_domain($1, $2, $3, $4)",
                    p["ref"], p["area"], p["answerable"], kind,
                )  # fmt: skip
                py = RT.finding_domain(
                    protocol=p["ref"], area=p["area"], answerable=p["answerable"], kind=kind
                )
                assert sql == py, (p["ref"], kind, sql, py)
        for kind in ("security", "app_health", "code", "growth", "holding", None):
            sql = await su.fetchval("SELECT pg_temp.finding_domain(NULL, NULL, NULL, $1)", kind)
            assert sql == RT.finding_domain(kind=kind), kind
        links = [*RT.LINK_DOMAIN, "media_item", "decision", "work", "deliverable", "server_x",
                 "deploy", "incident", "egress", "funnel", None]  # fmt: skip
        for link in links:
            for source in ("system", "backup", "llm-router", "archive-fixity"):
                sql = await su.fetchval("SELECT pg_temp.notification_domain($1, $2)", link, source)
                assert sql == RT.notification_domain(link, source), (link, source)


async def test_a_technical_finding_goes_to_the_cto_not_the_owner(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    async with await all_tx(hub) as tx:
        tech, _ = await O.raise_finding(
            tx, company_id=company["id"], company_code=co, severity="high",
            title_fa="پورت دیتابیس باز است", kind="security", by_code="HQ-OVR", by_kind="agent",
        )  # fmt: skip
        leak, _ = await O.raise_finding(
            tx, company_id=company["id"], company_code=co, severity="critical",
            title_fa="رمز در خروجی دیده شد", kind="security", critical_reason="data_leak",
        )  # fmt: skip
        biz, _ = await O.raise_finding(
            tx, company_id=company["id"], company_code=co, severity="high",
            title_fa="عدد خروجی منبع ندارد", kind="growth",
        )  # fmt: skip
    assert (tech["domain"], tech["owner_visible"], tech["routed_to"]) == (
        "security",
        False,
        f"{co}-TECH-MGR",
    )
    assert leak["owner_visible"] and leak["critical_reason"] == "data_leak"
    assert biz["domain"] == "business" and biz["owner_visible"] and biz["routed_to"] == f"{co}-CEO"
    mine = await client.get(f"/api/v1/oversight/findings?company={co}", headers=owner)
    refs = {f["ref"] for f in mine.json()["items"]}
    assert tech["ref"] not in refs and {leak["ref"], biz["ref"]} <= refs
    every = await client.get(
        f"/api/v1/oversight/findings?company={co}&scope=all&domain=tech|infra|security",
        headers=owner,
    )
    rows = {f["ref"]: f for f in every.json()["items"]}
    assert set(rows) == {tech["ref"], leak["ref"]}
    assert rows[tech["ref"]]["routed_to"] == f"{co}-TECH-MGR"
    assert set(rows[tech["ref"]]) >= {"domain", "owner_visible", "routed_to", "critical_reason"}
    # its notification (a high finding) is stored for the handler, never pushed or listed
    async with await all_tx(hub) as tx:
        # by kind and company too: the fresh-start tests (p16) restart the ref sequences, so a
        # new finding can carry the ref of an older one whose notification is still there
        n = await tx.one(
            """SELECT owner_visible, routed_to, state FROM notify.notifications
               WHERE link_kind = 'finding' AND link_ref = :r AND company_id = :co""",
            r=tech["ref"],
            co=company["id"],
        )
    assert not n["owner_visible"] and n["routed_to"] == f"{co}-TECH-MGR"
    listed = await client.get(f"/api/v1/notifications?company={co}", headers=owner)
    assert all(x["link"]["ref"] != tech["ref"] for x in listed.json()["items"] if x["link"])
    technical = await client.get(
        f"/api/v1/notifications?company={co}&scope=all&domain=security", headers=owner
    )
    assert any(x["link"] and x["link"]["ref"] == tech["ref"] for x in technical.json()["items"])
    bad = await client.get("/api/v1/notifications?scope=all&domain=nope", headers=owner)
    assert bad.status_code == 422


async def test_notifications_by_rule_and_written_for_the_owner(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    async with await all_tx(hub) as tx:
        backup = await notify.raise_notification(
            tx, company_id=company["id"], company_code=co, level="urgent",
            title_fa="پشتیبان دو ساعت است تازه نشده", link_kind="backup", link_ref="b1",
            source_code="backup",
        )  # fmt: skip
        down = await notify.raise_notification(
            tx, company_id=company["id"], company_code=co, level="urgent",
            title_fa="سایت از کار افتاده", category="service_down",
        )  # fmt: skip
        out = await notify.raise_notification(
            tx, company_id=company["id"], company_code=co, level="report",
            title_fa="خروجی تازه O-000123: کلیپ آماده شد", body_fa="کار W-000042 delivered شد",
            link_kind="deliverable", link_ref="O-000123",
        )  # fmt: skip
        row = await tx.one(
            "SELECT title_fa, body_fa, domain FROM notify.notifications WHERE id = :id",
            id=out["id"],
        )
    assert not backup["owner_visible"] and not backup["push_now"]  # urgent, but not the owner's
    assert down["owner_visible"] and down["critical_reason"] == "product_down"
    assert row["domain"] == "business"
    clean(row["title_fa"])
    clean(row["body_fa"])
    assert "O-000123" not in row["title_fa"]


async def test_the_data_move_hides_old_technical_items_once(
    su: Any, new_company: Callable[..., Any]
) -> None:
    """Migration 0037's data move on rows made the old way (owner_visible,
    no domain): technical ones go to their handler, one Audit row per kind;
    nothing is deleted (run again here in a transaction rolled back)."""
    company = await new_company()
    with pytest.raises(Undo):
        async with su.transaction():
            fid = await su.fetchval(
                """INSERT INTO oversight.findings (company_id, severity, title_fa, answerable_kind,
                       answerable_code, raised_by_kind, raised_by_code, due_at, kind)
                   VALUES ($1, 'high', 'old', 'owner', 'owner', 'system', 'oversight', now(),
                           'security')
                   RETURNING id""",
                company["id"],
            )
            nid = await su.fetchval(
                """INSERT INTO notify.notifications (company_id, level, title_fa, link_kind,
                       link_ref, state, source_kind, source_code)
                   VALUES ($1, 'urgent', 'old', 'backup', 'x', 'delivered', 'system', 'backup')
                   RETURNING id""",
                company["id"],
            )
            before = await su.fetchval(
                "SELECT count(*) FROM audit.entries WHERE action = 'routing.move'"
            )
            await su.execute(MIGRATION.RULES + MIGRATION.DATA_MOVE)
            f = await su.fetchrow(
                "SELECT domain, owner_visible, routed_to FROM oversight.findings WHERE id = $1",
                fid,
            )
            n = await su.fetchrow(
                "SELECT domain, owner_visible FROM notify.notifications WHERE id = $1", nid
            )
            assert (f["domain"], f["owner_visible"], f["routed_to"]) == (
                "security",
                False,
                f"{company['code']}-TECH-MGR",
            )
            assert (n["domain"], n["owner_visible"]) == ("infra", False)
            after = await su.fetchval(
                "SELECT count(*) FROM audit.entries WHERE action = 'routing.move'"
            )
            assert after >= before + 2
            mode = await su.fetchval(
                """SELECT h.state || ':' || h.mode FROM core.hiring h
                   JOIN core.companies c ON c.id = h.company_id WHERE c.kind = 'holding'"""
            )
            assert mode == "open:auto"
            raise Undo


# ============================================== §29.1 destructive cards ==
def _destructive(co: str, category: str) -> D.DecisionIn:
    return D.DecisionIn(
        kind="server_destructive",
        title="کار ویرانگر",
        what="`docker volume rm data`",
        why="test",
        risk="high",
        reversible=False,
        payload={
            "server": {"id": "srv-1", "name": "app"},
            "server_name": "app",
            "company": co,
            "category": category,
            "cmd": "docker volume rm data",
            "cmd_sha256": "0" * 64,
            "tool": "server.exec",
            "actor": {"kind": "agent", "code": f"{co}-TECH-MGR"},
            "job": str(uuid.uuid4()),
            "detected_by": "pattern",
        },
    )


async def test_a_destructive_card_is_the_ctos_unless_the_owner_keeps_it(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    async with await all_tx(hub) as tx:
        vol = await D.propose(
            tx, SERVICE, company_id=company["id"], company_code=co,
            body=_destructive(co, "volume_delete"), thread_code=None,
        )  # fmt: skip
        drop = await D.propose(
            tx, SERVICE, company_id=company["id"], company_code=co,
            body=_destructive(co, "db_drop"), thread_code=None,
        )  # fmt: skip
    assert (vol["approver_code"], vol["owner_visible"], vol["routed_to"], vol["domain"]) == (
        f"{co}-TECH-MGR",
        False,
        f"{co}-TECH-MGR",
        "infra",
    )
    assert drop["approver_code"] is None and drop["owner_visible"]
    item = await su.fetchrow(
        """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.title LIKE $1""",
        f"%{vol['ref']}%",
    )
    assert item["code"] == f"{co}-TECH-MGR"
    h = owner_session["headers"]
    mine = await client.get(f"/api/v1/decisions?company={co}", headers=h)
    assert [d["ref"] for d in mine.json()["items"]] == [drop["ref"]]
    every = await client.get(f"/api/v1/decisions?company={co}&scope=all&domain=infra", headers=h)
    assert {d["ref"] for d in every.json()["items"]} == {vol["ref"], drop["ref"]}
    # card.decide: the CEO may not, the CTO may
    r = await client.post(
        f"/internal/v1/cards/{vol['ref']}/decide",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"verdict": "approve"},
    )
    assert r.status_code == 403, r.text
    r = await client.post(
        f"/internal/v1/cards/{drop['ref']}/decide",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},
        json={"verdict": "approve"},
    )
    assert r.status_code == 403, r.text  # the owner keeps db_drop
    r = await client.post(
        f"/internal/v1/cards/{vol['ref']}/decide",
        headers={**await agent_headers(f"{co}-TECH-MGR"), **idem()},
        json={"verdict": "approve", "note": "پشتیبان تازه هست"},
    )
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    assert r.json()["decided_by"]["code"] == f"{co}-TECH-MGR"
    for code in (f"{co}-CEO", f"{co}-TECH-MGR"):
        await end_runs(su, code)
    # the owner changes the list (🔏 settings.destructive)
    sid = owner_session["session_id"]
    body = {"owner_categories": ["server_delete", "db_drop", "volume_delete"]}
    r = await client.put("/api/v1/owner/settings/destructive", headers=h, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    sh = await step_up(hub, sid, "settings.destructive", "db_drop,server_delete,volume_delete")
    r = await client.put("/api/v1/owner/settings/destructive", headers={**h, **sh}, json=body)
    assert r.status_code == 200 and r.json()["owner_categories"] == sorted(body["owner_categories"])
    async with await all_tx(hub) as tx:
        again = await D.propose(
            tx, SERVICE, company_id=company["id"], company_code=co,
            body=_destructive(co, "volume_delete"), thread_code=None,
        )  # fmt: skip
    assert again["approver_code"] is None
    await su.execute(
        "UPDATE owner.settings SET destructive_owner_categories = ARRAY['server_delete', 'db_drop']"
    )


# ===================================================== §29.2 the report ==
async def test_the_order_report_from_receipt_to_the_end(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, f"برای {co} گزارش فروش هفته را آماده کن")
    rep = await report(client, owner, o["ref"])
    assert rep["state"] == "received" and rep["ack"] is None
    assert rep["steps"][0]["what_fa"].startswith("دریافت شد؛ به مدیرعامل")
    assert rep["route"]["companies"] == [co]
    # the CEO's plan (order.ack), then a step (order.progress)
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/orders/{o['ref']}/ack",
        headers=ceo,
        json={"plan_fa": "گزارش را از عددهای فروش میسازم", "assigned": [f"{co}-SALES-MGR"]},
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["state"] == "planned"
        and r.json()["ack"]["assigned"][0]["code"] == f"{co}-SALES-MGR"
    )
    stranger = await agent_headers(f"{co}-HR-MGR")
    r = await client.post(
        f"/internal/v1/orders/{o['ref']}/progress", headers=stranger, json={"step_fa": "x"}
    )
    assert r.status_code == 403
    r = await client.post(
        f"/internal/v1/orders/{o['ref']}/progress", headers=ceo, json={"step_fa": "نیمی آماده شد"}
    )
    assert r.status_code == 200 and r.json()["steps"][-1]["what_fa"] == "نیمی آماده شد"
    # a partial output does not end it; the whole one does (progress 100)
    w = o["work"]
    assert (
        await deliver(client, f"{co}-CEO", w["id"], "خروجی ناقص: سقف اجرا رسید")
    ).status_code == 200
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) == "in_progress"
    assert (await report(client, owner, o["ref"]))["state"] == "in_progress"
    await client.post(
        f"/internal/v1/work/{w['id']}/progress", headers=ceo, json={"note": "تمام", "pct": 100}
    )
    assert (await deliver(client, f"{co}-CEO", w["id"], "گزارش فروش هفته")).status_code == 200
    rep = await report(client, owner, o["ref"])
    assert rep["state"] == "delivered" and rep["summary"] is not None
    assert [x["kind"] for x in rep["outputs"]] == ["partial", "final"]
    assert rep["summary"]["done_fa"].startswith("1 خروجی تحویل شد")
    for text in owner_strings(rep):
        clean(text)
    n = await su.fetchrow(
        """SELECT level, title_fa, body_fa, owner_visible, domain FROM notify.notifications
           WHERE link_kind = 'order' AND link_ref = $1""",
        o["ref"],
    )
    assert n["level"] == "report" and n["owner_visible"] and n["domain"] == "business"
    clean(n["title_fa"])
    clean(n["body_fa"])
    again = await report(client, owner, o["ref"])  # ended: one notification only
    assert again["state"] == "delivered"
    assert (
        await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_kind = 'order' AND link_ref = $1",
            o["ref"],
        )
        == 1
    )
    await end_runs(su, f"{co}-CEO")


async def test_the_report_works_without_the_routers_call(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    o = await make_order(hub, company, "یک کار ساده", routed=False)
    rep = await report(client, owner, o["ref"])
    assert rep["steps"][0]["what_fa"].startswith("دریافت شد") and rep["state"] == "received"
    async with await all_tx(hub) as tx:
        fields = await OR.list_fields(tx, [o["ref"]])
    assert fields[o["ref"]]["state"] == "received"
    assert (await client.get("/api/v1/orders/F-99999/report", headers=owner)).status_code == 404


async def test_a_root_with_an_open_child_and_a_partial_stays_open(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    """Finding 3 of prompt 20: a plan delivered the parent at 40% and nobody followed it."""
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "کلیپ معرفی محصول")
    w = o["work"]
    ceo = await agent_headers(f"{co}-CEO")
    child = await client.post(
        f"/internal/v1/work/{w['id']}/delegate",
        headers=ceo,
        json={"to": f"{co}-TECH-MGR", "title": "بخش فنی"},
    )
    assert child.status_code == 201, child.text
    await client.post(
        f"/internal/v1/work/{w['id']}/progress", headers=ceo, json={"note": "طرح", "pct": 40}
    )
    r = await deliver(client, f"{co}-CEO", w["id"], "طرح کلیپ")
    assert r.status_code == 200 and r.json()["work"]["status"] == "waiting"  # a child is open
    await su.execute(
        "UPDATE work.work SET status = 'cancelled', closed_at = now() WHERE id = $1",
        uuid.UUID(child.json()["id"]),
    )
    r = await deliver(client, f"{co}-CEO", w["id"], "طرح دوم")
    assert r.json()["work"]["status"] == "in_progress"  # 40% is not done
    r = await deliver(client, f"{co}-CEO", w["id"], "خروجی ناقص: سقف اجرا رسید")
    assert r.json()["work"]["status"] == "in_progress"
    # a partial never closes any work, a child's either
    mgr = await agent_headers(f"{co}-TECH-MGR")
    c2 = await client.post(
        f"/internal/v1/work/{w['id']}/delegate",
        headers=ceo,
        json={"to": f"{co}-TECH-MGR", "title": "دوم"},
    )
    r = await deliver(client, f"{co}-TECH-MGR", c2.json()["id"], "خروجی ناقص: سقف اجرا رسید")
    assert r.json()["work"]["status"] == "in_progress"
    assert (await report(client, owner, o["ref"]))["state"] in ("in_progress", "waiting")
    del mgr
    for code in (f"{co}-CEO", f"{co}-TECH-MGR"):
        await end_runs(su, code)


async def test_the_timers_and_the_talk_loop(
    client: httpx.AsyncClient, hub: Hub, wk: dict[str, Any], owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "گزارش رقبا")
    ref, w = o["ref"], o["work"]
    s = hub.settings
    # 11 minutes without a plan: the CEO gets a small item, a no_progress blocker
    await su.execute(
        "UPDATE owner.orders SET created_at = now() - interval '11 minutes' WHERE ref = $1", ref
    )
    async with await all_tx(wk["hub"]) as tx:
        assert await OR.timers(tx, s, ref) == ["ack"]
        assert await OR.timers(tx, s, ref) == []  # once
        await OR.refresh(tx, ref)
    rep = await report(client, owner, ref)
    assert rep["state"] == "blocked" and [b["kind"] for b in rep["blockers"]] == ["no_progress"]
    nudge = await su.fetchrow(
        """SELECT e.code, w.status FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.title LIKE $1""",
        f"فرمان {ref}: %",
    )
    assert nudge["code"] == f"{co}-CEO" and nudge["status"] == "queued"
    # the plan closes the CEO's item
    ceo = await agent_headers(f"{co}-CEO")
    await client.post(f"/internal/v1/orders/{ref}/ack", headers=ceo, json={"plan_fa": "برنامه"})
    assert (
        await su.fetchval("SELECT status FROM work.work WHERE title LIKE $1", f"فرمان {ref}: %")
        == "cancelled"
    )
    # 3 hours without a step: the CEO must report; 7 hours: the owner hears why
    await su.execute(
        """UPDATE owner.order_reports SET acked_at = now() - interval '7 hours',
               last_step_at = now() - interval '7 hours' WHERE ref = $1""",
        ref,
    )
    await su.execute(
        "UPDATE owner.orders SET created_at = now() - interval '8 hours' WHERE ref = $1", ref
    )
    async with await all_tx(wk["hub"]) as tx:
        assert await OR.timers(tx, s, ref) == ["progress", "owner"]
    n = await su.fetchrow(
        """SELECT level, title_fa, body_fa, owner_visible, domain FROM notify.notifications
           WHERE link_kind = 'order' AND link_ref = $1""",
        ref,
    )
    assert (n["level"], n["owner_visible"], n["domain"]) == ("decision", True, "business")
    clean(n["title_fa"])
    clean(n["body_fa"])
    # talk without output: more than ORDER_TALK_LIMIT runs, no output -> stop
    emp = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", f"{co}-CEO")
    for _ in range(s.order_talk_limit + 1):
        await su.execute(
            """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                   started_at, finished_at)
               VALUES ($1, $2, $3, 'work', 'talk', 'done', now(), now())""",
            company["id"],
            emp,
            w["id"],
        )
    queued = await su.fetchval(
        "SELECT agents.queue_run($1, 'work', $2, NULL, 'next', 'P2')", emp, w["id"]
    )
    async with await all_tx(wk["hub"]) as tx:
        assert "talk_loop" in await OR.timers(tx, s, ref)
        assert await OR.stopped(tx, w["id"])
    row = await su.fetchrow("SELECT state, error_code FROM agents.runs WHERE id = $1", queued)
    assert (row["state"], row["error_code"]) == ("refused", "talk_loop")
    rep = await report(client, owner, ref)
    talk = [b for b in rep["blockers"] if b["kind"] == "talk_loop"]
    assert talk and talk[0]["detail_fa"].startswith("گیر کرد چون") and talk[0]["fix"] is None
    for text in owner_strings(rep):
        clean(text)
    await end_runs(su, f"{co}-CEO")


async def _blocked_run(
    su: Any,
    company: dict[str, Any],
    work_id: Any,
    code: str,
    *,
    tool: str = "propose",
    who: str = "CEO",
) -> None:
    """A finished run of the order's work whose step's tool answered `code`."""
    emp = await su.fetchval(
        "SELECT id FROM core.employees WHERE code = $1", f"{company['code']}-{who}"
    )
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               started_at, finished_at, error_code)
           VALUES ($1, $2, $3, 'work', 'blocked', 'done', now(), now(), $4) RETURNING id""",
        company["id"],
        emp,
        work_id,
        code if code in OR.BUDGET_CODES else None,
    )
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, summary_fa, actions)
           VALUES ($1, $2, 1, 's', $3::jsonb)""",
        rid,
        company["id"],
        json.dumps([{"tool": tool, "outcome": "error", "code": code}]),
    )


async def test_blockers_and_their_fixes(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    o = await make_order(
        hub, company, "یک کلیپ برای اینستاگرام", department="MEDIA", budget=200_000
    )
    ref, w = o["ref"], o["work"]
    await set_hiring(su, "closed", None)
    await _blocked_run(su, company, w["id"], "hiring_closed")
    await _blocked_run(su, company, w["id"], "channel_not_configured", tool="web.browse")
    await _blocked_run(su, company, w["id"], "budget")
    await su.execute("UPDATE work.work SET player = 'gemini' WHERE id = $1", w["id"])
    gemini = await su.fetchval("SELECT status FROM substitutes.players WHERE player = 'gemini'")
    await su.execute("UPDATE substitutes.players SET status = 'off' WHERE player = 'gemini'")
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**h, **idem()},
        json={"scope": f"company:{co}", "state": "engaged", "reason": "آزمون"},
    )
    assert r.status_code == 200, r.text
    rep = await report(client, h, ref)
    kinds = {b["kind"]: b for b in rep["blockers"]}
    assert rep["state"] == "blocked"
    assert set(kinds) >= {"hiring_closed", "connection_missing", "budget", "player_down", "locked",
                          "no_employee"}  # fmt: skip
    assert kinds["no_employee"]["fix"] == {
        "action": "hire",
        "label_fa": "استخدام کن",
        "target": f"{co}:motion_designer",
    }
    assert kinds["locked"]["fix"]["target"] == f"company:{co}"
    assert kinds["budget"]["fix"]["target"] == w["ref"]
    for text in owner_strings(rep):
        clean(text)

    async def fix(body: dict[str, Any], extra: dict[str, str] | None = None) -> httpx.Response:
        return await client.post(
            f"/api/v1/orders/{ref}/fix", headers={**h, **(extra or {})}, json=body
        )

    # the lock: its own step-up
    assert (await fix({"action": "lock.open"})).json()["code"] == "step_up_required"
    sh = await step_up(hub, sid, "kill_switch.release", f"company:{co}")
    assert (await fix({"action": "lock.open"}, sh)).status_code == 200
    # hiring: 🔏 hiring.start -> auto; then the empty seat is filled by code
    sh = await step_up(hub, sid, "hiring.start", "holding")
    r = await fix({"action": "hiring.open"}, sh)
    assert r.status_code == 200, r.text
    # the apps sign a fix by its own name and target: that seal opens it too, once
    sh = await step_up(hub, sid, "hiring.open", "holding")
    r = await fix({"action": "hiring.open", "target": "holding"}, sh)
    assert r.status_code in (200, 409), r.text  # no blocker left is 409, never a step-up error
    assert r.json().get("code") not in ("step_up_required", "step_up_invalid"), r.text
    assert await su.fetchval("SELECT core.hiring_mode()") == "auto"
    r = await fix({"action": "hire", "target": f"{co}:motion_designer"})
    assert r.status_code == 200, r.text
    assert (
        await su.fetchval(
            "SELECT count(*) FROM core.employees WHERE company_id = $1 AND role = 'motion_designer'",
            company["id"],
        )
        == 1
    )
    # budget: +X on the work (it goes on); the player: back to auto
    r = await fix({"action": "budget.add", "target": w["ref"], "tokens": 100_000})
    assert r.status_code == 200, r.text
    assert (
        await su.fetchval("SELECT budget_tokens FROM work.work WHERE id = $1", w["id"]) == 300_000
    )
    r = await fix({"action": "player.auto", "target": w["ref"]})
    assert r.status_code == 200
    assert await su.fetchval("SELECT player FROM work.work WHERE id = $1", w["id"]) == "auto"
    r = await fix({"action": "connection.guide"})
    assert r.status_code == 200
    kinds = {b["kind"] for b in r.json()["blockers"]}
    assert not kinds & {"locked", "hiring_closed", "no_employee", "player_down"}, kinds
    assert (await fix({"action": "series.seal", "target": "SR-9999"})).status_code == 409
    await su.execute(
        "UPDATE substitutes.players SET status = $1 WHERE player = 'gemini'", gemini or "off"
    )
    await set_hiring(su, "closed", None)


# ============================================ §29.6 the delegation budget ==
async def test_a_request_is_raised_to_its_roles_floor(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    r = await client.post(
        "/internal/v1/work",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"department": "TECH", "title": "بررسی", "brief": "x", "budget": {"tokens": 60_000}},
    )
    assert r.status_code == 201, r.text
    budget = r.json()["work"]["budget"]["tokens"]
    async with await all_tx(hub) as tx:
        floor = await W.budget_floor(tx, hub.charters, "cto")
    assert floor >= 150_000 and budget == floor  # 3 x 50 000 of the CTO's charter, at least
    await end_runs(su, f"{co}-CEO")


async def test_a_cache_read_counts_a_tenth_on_the_run_and_the_work(
    hub: Hub, wk: dict[str, Any], su: Any, new_company: Callable[..., Any]
) -> None:
    assert W.effective_tokens(1000, 200, 10_000, 500) == 2700
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "کار با حافظه‌ی نهان", budget=500_000)
    rid = await running_run(f"{co}-CEO")
    runner = Runner(wk["hub"], router=None, gateway=None)  # type: ignore[arg-type]
    charter = hub.charters.get("ceo")
    rc = RunCtx(run={"id": uuid.UUID(rid), "work_id": o["work"]["id"], "token_cap": 160_000},
                emp={"code": f"{co}-CEO"}, charter=charter, token="")  # fmt: skip
    call = ModelCall(ok=True, status="ok", code=None, call_id=None, model="m", effort=None,
                     connection=None, structured=None, text=None, input_tokens=1000,
                     output_tokens=200, cache_read_tokens=10_000, cache_write_tokens=500)  # fmt: skip
    await runner._book(rc, call)
    assert rc.used_tokens == 2700 and rc.last_cache_read == 10_000
    assert (
        await su.fetchval("SELECT tokens_used FROM work.work WHERE id = $1", o["work"]["id"])
        == 2700
    )
    assert (
        await su.fetchval("SELECT cache_read_tokens FROM agents.runs WHERE id = $1", uuid.UUID(rid))
        == 10_000
    )
    await end_runs(su, f"{co}-CEO")


async def test_work_budget_by_the_ceo_inside_the_envelope(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    o = await make_order(hub, company, "کار کم‌بودجه", budget=100_000)
    w = o["work"]
    await su.execute("UPDATE work.work SET status = 'waiting' WHERE id = $1", w["id"])
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/work/{w['ref']}/budget",
        headers={**ceo, **idem()},
        json={"add_tokens": 50_000},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["budget_tokens"], r.json()["status"]) == (150_000, "in_progress")
    mgr = await agent_headers(f"{co}-TECH-MGR")
    r = await client.post(
        f"/internal/v1/work/{w['ref']}/budget", headers={**mgr, **idem()}, json={"add_tokens": 1}
    )
    assert r.status_code == 403
    await envelope(su, company, 10)  # a month envelope already spent
    r = await client.post(
        f"/internal/v1/work/{w['ref']}/budget",
        headers={**ceo, **idem()},
        json={"add_tokens": 50_000},
    )
    assert r.status_code == 409 and r.json()["code"] == "envelope_exceeded"
    for code in (f"{co}-CEO", f"{co}-TECH-MGR"):
        await end_runs(su, code)


# ============================================== §29.10 automatic hiring ==
def _hire(co: str, estimate: int) -> dict[str, Any]:
    return {
        "kind": "hire",
        "title": "استخدام طراح",
        "payload": {
            "company": co, "department": "MEDIA", "role": "visual_designer",
            "title_fa": "طراح تصویر", "title_en": "Visual designer", "reason": "پست روزانه",
            "model": "claude-sonnet-5-5", "effort": "medium",
            "quota_estimate_month": {"tokens": estimate},
        },
    }  # fmt: skip


async def test_a_ceos_hire_in_the_envelope_is_approved_by_code(
    client: httpx.AsyncClient, hub: Hub, su: Any, auto_hiring: None, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    await envelope(su, company, 10_000_000)
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        "/internal/v1/decisions", headers={**ceo, **idem()}, json=_hire(co, 4_000_000)
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "approved" and d["decided_by"]["kind"] == "service"
    emp = await su.fetchrow(
        "SELECT code, status FROM core.employees WHERE hired_by_decision_id = $1",
        uuid.UUID(d["id"]),
    )
    assert emp["status"] == "active"
    assert (
        await su.fetchval("SELECT kind FROM owner.stories WHERE event_key = $1", f"hire:{d['ref']}")
        == "hire"
    )
    assert not await su.fetchval(  # no card and no line for the owner
        "SELECT count(*) FROM notify.notifications WHERE link_ref IN ($1, $2)",
        d["ref"],
        emp["code"],
    )
    # over the envelope: refused, nothing made
    r = await client.post(
        "/internal/v1/decisions", headers={**ceo, **idem()}, json=_hire(co, 9_000_000)
    )
    assert r.status_code == 409 and r.json()["code"] == "envelope_exceeded", r.text
    # a manager's hire is its CEO's card (as delegated)
    mgr = await agent_headers(f"{co}-MEDIA-MGR")
    r = await client.post(
        "/internal/v1/decisions", headers={**mgr, **idem()}, json=_hire(co, 1_000_000)
    )
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert r.json()["approver"]["code"] == f"{co}-CEO" and not r.json()["owner_visible"]
    for code in (f"{co}-CEO", f"{co}-MEDIA-MGR"):
        await end_runs(su, code)


async def test_a_working_groups_seat_is_filled_by_code(
    hub: Hub, su: Any, auto_hiring: None, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    await envelope(su, company, 20_000_000)
    async with await all_tx(hub) as tx:
        out = await HR.auto_fill(
            tx, company["id"], "publisher", "مسئول انتشار", charters=hub.charters
        )
        again = await HR.auto_fill(tx, company["id"], "publisher", charters=hub.charters)
    assert out["hired"] and again == {"employee": out["employee"], "decision": None, "hired": False}
    row = await su.fetchrow(
        "SELECT title_fa, role FROM core.employees WHERE code = $1", out["employee"]
    )
    assert (row["title_fa"], row["role"]) == ("مسئول انتشار", "publisher")
    small = await new_company()
    await envelope(su, small, 1_000)
    with pytest.raises(Exception) as exc:
        async with await all_tx(hub) as tx:
            await HR.auto_fill(tx, small["id"], "publisher", charters=hub.charters)
    assert (
        "envelope_exceeded" in str(exc.value.args)
        or getattr(exc.value, "code", "") == "envelope_exceeded"
    )
    await set_hiring(su, "closed", None)
    with pytest.raises(Exception) as exc:
        async with await all_tx(hub) as tx:
            await HR.auto_fill(tx, company["id"], "content_analyst", charters=hub.charters)
    assert getattr(exc.value, "code", "") == "hiring_closed"


# ================================================ §29.14 employee state ==
async def test_each_employee_has_a_state(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    company = await new_company()
    co = company["code"]
    await running_run(f"{co}-CEO")  # a run in flight: thinking
    o = await make_order(hub, company, "کار مالی", department="FIN", budget=100_000)
    await su.execute("UPDATE work.work SET status = 'waiting' WHERE id = $1", o["work"]["id"])
    o2 = await make_order(hub, company, "کار فروش", department="SALES", budget=100_000)
    await _blocked_run(su, company, o2["work"]["id"], "budget", who="SALES-MGR")
    r = await client.get(f"/api/v1/companies/{co}/employees", headers=owner)
    assert r.status_code == 200, r.text
    by = {e["code"]: e for e in r.json()}
    assert by[f"{co}-CEO"]["state"] == "thinking"
    assert by[f"{co}-FIN-MGR"]["state"] == "waiting"
    sales = by[f"{co}-SALES-MGR"]
    assert sales["state"] == "stuck" and sales["stuck"]["fix"]["action"] == "budget.add"
    clean(sales["stuck"]["reason_fa"])
    assert by[f"{co}-HR-MGR"]["state"] == "idle" and by[f"{co}-HR-MGR"]["stuck"] is None
    one = await client.get(f"/api/v1/employees/{co}-FIN-MGR", headers=owner)
    assert one.json()["state"] == "waiting"
    await end_runs(su, f"{co}-CEO")


# ================================== management review §5.1: the protocols ==
async def test_the_management_reviews_protocol_changes(hub: Hub, owner_db: Any) -> None:
    from hq_common import charters

    holding = await hub.companies.holding()
    with pytest.raises(Undo):
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            await O.seed_protocols(tx, holding.id, charters.load().root)
            assert await O.management_review(tx) == []  # idempotent
            cur = {
                r["ref"]: r
                for r in await tx.all(
                    "SELECT ref, status, schedule, source FROM oversight.current_protocols"
                    " WHERE ref = ANY(:r)",
                    r=list(O.REVIEW_21),
                )
            }
            for ref in ("PR-005", "PR-081", "PR-098", "PR-041"):
                assert cur[ref]["status"] == "paused", ref
            for ref in ("PR-001", "PR-004", "PR-100"):
                assert cur[ref]["schedule"].startswith("FREQ=WEEKLY"), ref
            assert cur["PR-095"]["schedule"].startswith("FREQ=DAILY")
            assert await tx.first(
                "SELECT 1 FROM oversight.current_protocols WHERE ref = 'PR-040' AND status = 'active'"
            )
            # an owner's own version is never touched
            p = await O.load_protocol(tx, "PR-005")
            fields = {k: p[k] for k in O.ProtocolIn.model_fields}
            await O.new_version(
                tx, OWNER, holding.id, {**fields, "status": "active"}, ref="PR-005", source="owner"
            )
            assert await O.management_review(tx) == []
            assert (await O.load_protocol(tx, "PR-005"))["status"] == "active"
            raise Undo


# ================================================= the weekly tech summary ==
def test_the_week_starts_saturday_nine_in_the_owners_zone() -> None:
    tz = "Asia/Tehran"
    sat_early = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)  # 08:30 Tehran, Saturday
    assert TS.week_of(sat_early, tz) is None
    sat = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # 09:30 Tehran
    week = TS.week_of(sat, tz)
    assert week is not None and week[0].isoformat() == "2026-11-07"
    assert week[2] - week[1] == timedelta(days=7)
    sunday = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)  # a missed Saturday is made up
    assert TS.week_of(sunday, tz)[0].isoformat() == "2026-11-07"  # type: ignore[index]


async def test_the_weekly_technical_summary_once(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    async with await all_tx(hub) as tx:
        await O.raise_finding(
            tx, company_id=company["id"], company_code=company["code"], severity="medium",
            title_fa="گواهی سایت ۱۵ روز دیگر تمام میشود", kind="security",
        )  # fmt: skip
    # a Saturday 10:30 Tehran of a week no other run took (the test database outlives a run)
    now = datetime(2100, 1, 2, 7, 0, tzinfo=UTC) + timedelta(weeks=random.randrange(1, 40_000))
    async with await all_tx(hub) as tx:
        out = await TS.run(tx, now)
        again = await TS.run(tx, now)
    assert out["created"] and not again["created"]
    dl = await su.fetchrow(
        "SELECT title, summary, body FROM cartable.deliverables WHERE ref = $1", out["deliverable"]
    )
    assert "یافته‌های فنی باز" in dl["body"]
    for line in dl["body"].splitlines():
        if line.startswith("- "):
            clean(line)
    clean(dl["summary"])
    n = await su.fetchrow(
        "SELECT level, owner_visible, routed_to FROM notify.notifications WHERE link_ref = $1",
        out["deliverable"],
    )
    # the technical team's, not the owner's (the owner, 2026-11-06)
    assert n["level"] == "report" and not n["owner_visible"] and n["routed_to"]
