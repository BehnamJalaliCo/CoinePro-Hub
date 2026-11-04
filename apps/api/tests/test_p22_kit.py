"""Prompt 22 (contract §31.2): a ready company with one order, the company kit.

Kits are data (seed/kits) and name no company; the preview writes nothing; a
company is made only behind the step-up 🔏 company.create on the body's hash,
with its team, group memberships, KPIs, connections (`not_connected`) and its
lines as drafts through the lines engine's create_line (faked here: it is on
another branch); the secretary routes «یک شرکت تازه …» to a kit card in the
order report (no work item, nothing created before the seal)."""

from __future__ import annotations

import hashlib
import re
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from hq_api import workflows_client
from hq_api.domain import dispatch as D
from hq_api.domain import groups as GR
from hq_api.domain import humanize
from hq_api.domain import kits as K
from hq_api.hub import Hub

from .conftest import body_bytes, idem, random_code, step_up

API = Path(__file__).resolve().parents[1]
ORDER = "یک شرکت تازه برای تولید محتوای دانش مالی بساز"


class FakeLines:
    """hq_api.lines.store as the lines engine will expose it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_line(self, tx: Any, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        return {"ref": f"LN-{len(self.calls):04d}", "state": "draft"}


@pytest.fixture
def fake_lines(monkeypatch: pytest.MonkeyPatch) -> FakeLines:
    fake = FakeLines()
    mod = types.ModuleType("hq_api.lines.store")
    mod.create_line = fake.create_line  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hq_api.lines.store", mod)
    return fake


@pytest.fixture
def no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "hq_api.lines.store", None)


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    async def refuse(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> None:
        calls.append(req)

    monkeypatch.setattr(workflows_client, "route_order", refuse)
    return calls


@pytest.fixture
async def groups(hub: Hub) -> None:
    """The content group, loaded from its file (as the start does)."""
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await GR.seed(tx, holding.id)


def body_of(kit: str = "content_brand", **extra: Any) -> dict[str, Any]:
    code = random_code("K")
    return {"kit": kit, "code": code, "name_fa": "شرکت آزمایشی", "name_en": f"Kit {code}", **extra}


async def count_companies(su: Any) -> int:
    return int(await su.fetchval("SELECT count(*) FROM core.companies"))


async def post_sealed(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    body: dict[str, Any],
    *,
    target: str | None = None,
) -> httpx.Response:
    raw = body_bytes(body)
    su = await step_up(
        hub,
        owner_session["session_id"],
        "company.create",
        target or hashlib.sha256(raw).hexdigest(),
    )
    return await client.post(
        "/api/v1/companies/from-kit",
        content=raw,
        headers={**owner_session["headers"], **su, "Content-Type": "application/json"},
    )


# -------------------------------------------------------------- the files --
def test_the_kit_files_validate_and_say_what_the_owner_asked() -> None:
    files = K.load_files()
    assert {"content_brand", "saas_product"} <= set(files)
    brand, saas = files["content_brand"], files["saas_product"]
    assert {x["platform"] for x in brand["lines"]} == {
        "instagram_reel", "instagram_story", "youtube_short", "telegram_post",
    }  # fmt: skip
    assert brand["groups"] == ["content"] and brand["team_template"] == "standard"
    assert brand["connections"] == ["instagram", "telegram", "youtube", "search_console", "ga4"]
    assert {x["platform"] for x in saas["lines"]} == {"site_article", "telegram_post"}
    assert saas["connections"] == ["search_console", "ga4", "telegram"]
    assert "funnel.signups_7d" in saas["kpis"]
    assert any(isinstance(k, dict) and "revenue" in k["key"] for k in saas["kpis"])
    for key in files:
        s = K.describe(key)
        assert s.team.positions > 1 and s.team.departments and s.todo_fa
        for text in [s.purpose_fa, *s.todo_fa]:
            assert humanize.check(text) == [], text


def test_no_kit_names_a_company_and_nothing_counts_companies() -> None:
    channels = yaml.safe_load((API / "seed" / "channels.yaml").read_text(encoding="utf-8"))
    rules = yaml.safe_load((API / "seed" / "order_rules.yaml").read_text(encoding="utf-8"))
    codes = {str(c["company"]) for c in channels["channels"]} | set(rules["companies"])
    assert codes  # the real codes of the seed files
    for path in (API / "seed" / "kits").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        for code in codes:
            assert not re.search(rf"\b{code}\b", text), f"{path.name} names {code}"
    for path in (
        API / "src/hq_api/domain/kits.py",
        API / "src/hq_api/routes/kits.py",
        *(API / "seed" / "kits").glob("*.yaml"),
    ):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?:\b[0-9]+|سه|three)\s+(?:companies|شرکت)\b", text), path.name
        assert not re.search(r"len\(.*compan", text), path.name


def test_a_broken_kit_is_refused_with_its_reason(tmp_path: Path) -> None:
    good = (API / "seed" / "kits" / "content_brand.yaml").read_text(encoding="utf-8")
    cases = {
        "team_template: standard": "team_template: nowhere",
        "groups: [content]": "groups: [no_such_group]",
        "platform: instagram_reel": "platform: tiktok_dance",
        "  - users.active": "  - not.a.standard.kpi",
        "connections: [instagram,": "connections: [fax,",
    }
    for old, new in cases.items():
        assert old in good, old
        (tmp_path / "content_brand.yaml").write_text(good.replace(old, new, 1), encoding="utf-8")
        with pytest.raises(ValueError, match="kit content_brand"):
            K.load_files(tmp_path)
    (tmp_path / "content_brand.yaml").write_text(
        good.replace("key: content_brand", "key: other", 1), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="must equal the file name"):
        K.load_files(tmp_path)


# ----------------------------------------------------------------- reads --
async def test_the_kits_are_listed_and_one_is_read(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    r = await client.get("/api/v1/kits", headers=owner)
    assert r.status_code == 200, r.text
    assert {"content_brand", "saas_product"} <= {k["key"] for k in r.json()}
    r = await client.get("/api/v1/kits/content_brand", headers=owner)
    kit = r.json()
    assert [g["key"] for g in kit["groups"]] == ["content"]
    assert next(x["platform"] for x in kit["lines"]) == "instagram_reel"
    assert {c["kind"] for c in kit["connections"]} >= {"instagram", "ga4"}
    assert any(k["key"] == "content.followers" and k["manual"] for k in kit["kpis"])
    assert (await client.get("/api/v1/kits/nope", headers=owner)).status_code == 404
    assert (await client.get("/api/v1/kits")).status_code in (401, 403)


async def test_the_preview_writes_nothing(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, fake_lines: FakeLines
) -> None:
    body = body_of()
    before = await count_companies(su)
    r = await client.post("/api/v1/companies/from-kit/preview", headers=owner, json=body)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["nothing_written"] is True and p["code_free"] is True and p["problems"] == []
    assert p["kit"]["key"] == "content_brand" and len(p["kit"]["lines"]) == 4
    assert await count_companies(su) == before and fake_lines.calls == []
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", body["code"])
    taken = await client.post(
        "/api/v1/companies/from-kit/preview", headers=owner, json={**body, "code": "HQ"}
    )
    assert taken.json()["code_free"] is False and taken.json()["problems"]
    bad = await client.post(
        "/api/v1/companies/from-kit/preview", headers=owner, json={**body, "kit": "nope"}
    )
    assert bad.status_code == 404


# ---------------------------------------------------------------- the seal --
async def test_without_the_seal_nothing_is_made(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    fake_lines: FakeLines,
    groups: None,
) -> None:
    body = body_of()
    before = await count_companies(su)
    r = await client.post("/api/v1/companies/from-kit", headers=owner_session["headers"], json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    # a seal for another body (or another action) does not open it
    r = await post_sealed(client, hub, owner_session, body, target=body["code"])
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    assert await count_companies(su) == before and fake_lines.calls == []


async def test_the_company_is_made_with_everything_the_kit_says(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    fake_lines: FakeLines,
    groups: None,
) -> None:
    body = body_of(color_index=None)
    r = await post_sealed(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    out = r.json()
    code = body["code"]
    assert out["company"]["code"] == code and out["company"]["template"] == "standard"
    assert out["company"]["counts"]["employees_active"] > 1  # the CEO and the managers
    assert out["team"]["departments"] > 0 and out["team"]["employees"] > 1
    # the team: the template's departments and positions, all of them asleep until work
    co = await su.fetchrow("SELECT id FROM core.companies WHERE code = $1", code)
    assert await su.fetchval(
        "SELECT count(*) FROM core.departments WHERE company_id = $1", co["id"]
    )
    assert await su.fetchval(
        "SELECT 1 FROM core.employees WHERE company_id = $1 AND code = $2", co["id"], f"{code}-CEO"
    )
    # the group memberships
    assert out["groups"] == ["content"] and out["groups_pending"] == []
    assert (
        await su.fetchval(
            """SELECT m.state FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           WHERE m.company_id = $1 AND g.key = 'content'""",
            co["id"],
        )
        == "on"
    )
    # the KPIs: the standard set plus the kit's own
    kpis = {
        r["key"]: r
        for r in await su.fetch(
            "SELECT key, card, source FROM governance.kpis WHERE company_id = $1", co["id"]
        )
    }
    assert {"users.active", "content.followers", "content.views_7d", "health.uptime_24h"} <= set(
        kpis
    )
    assert kpis["content.followers"]["card"] == "growth"
    assert out["kpis"] == len(kpis)
    # the connections, all not_connected
    conns = {
        r["kind"]: r["state"]
        for r in await su.fetch(
            "SELECT kind, state FROM growth.connections WHERE company_id = $1", co["id"]
        )
    }
    assert conns == dict.fromkeys(
        ["instagram", "telegram", "youtube", "search_console", "ga4"], "not_connected"
    )
    assert out["connections"] == 5
    # the lines, as drafts, through the engine's create_line
    assert [c["platform"] for c in fake_lines.calls] == [
        "instagram_reel", "instagram_story", "youtube_short", "telegram_post",
    ]  # fmt: skip
    assert all(
        c["company_id"] == co["id"] and c["by"] == "kit" and c["channel"] is None
        and c["template_key"] == c["platform"]
        for c in fake_lines.calls
    )  # fmt: skip
    assert [x["ref"] for x in out["lines"]] == ["LN-0001", "LN-0002", "LN-0003", "LN-0004"]
    assert out["lines_pending"] == []
    # what the owner still has to connect, in plain Persian
    todo = " ".join(out["todo_fa"])
    assert "Google Analytics" in todo and "یوتیوب" in todo and "پیش‌نویس" in todo
    for line in out["todo_fa"]:
        assert humanize.check(line) == [], line
    # no server is made here; the audit row says it was sealed
    assert not await su.fetchval("SELECT 1 FROM infra.servers WHERE company_id = $1", co["id"])
    audit = await su.fetchrow(
        "SELECT action, step_up FROM audit.entries WHERE company_id = $1 ORDER BY at DESC LIMIT 1",
        co["id"],
    )
    assert audit["action"] == "company.create_from_kit" and audit["step_up"] is True
    # the same code again: refused, the seal was spent on the first
    again = await post_sealed(client, hub, owner_session, body)
    assert again.status_code == 409


async def test_the_saas_kit_and_a_missing_engine(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_engine: None,
    groups: None,
) -> None:
    body = body_of("saas_product")
    r = await post_sealed(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["lines"] == []  # the lines engine is not on this hub (yet): not a failure
    assert [x["platform"] for x in out["lines_pending"]] == ["site_article", "telegram_post"]
    assert all(x["why_fa"] and humanize.check(x["why_fa"]) == [] for x in out["lines_pending"])
    co = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", body["code"])
    keys = {
        r["key"]
        for r in await su.fetch("SELECT key FROM governance.kpis WHERE company_id = $1", co)
    }
    assert {"funnel.signups_7d", "product.revenue_month_usd", "site.organic_clicks_7d"} <= keys
    kinds = {
        r["kind"]
        for r in await su.fetch("SELECT kind FROM growth.connections WHERE company_id = $1", co)
    }
    assert kinds == {"search_console", "ga4", "telegram"}


async def test_one_refused_line_does_not_undo_the_company(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    groups: None,
) -> None:
    async def create_line(tx: Any, **kw: Any) -> dict[str, Any]:
        if kw["platform"] == "youtube_short":
            raise RuntimeError("template missing")
        return {"ref": "LN-9999"}

    mod = types.ModuleType("hq_api.lines.store")
    mod.create_line = create_line  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hq_api.lines.store", mod)
    body = body_of()
    r = await post_sealed(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert [x["platform"] for x in out["lines_pending"]] == ["youtube_short"]
    assert len(out["lines"]) == 3 and out["company"]["code"] == body["code"]


async def test_only_the_owner_may_make_a_company_from_a_kit(hub: Hub) -> None:
    agent = {"kind": "agent", "code": "X-CEO", "role": "ceo", "company": "X"}
    ask = {"op": "company.from_kit", "target": {"kit": "content_brand"}}
    assert not (await hub.policy.query("kits", {"principal": agent, **ask})).allow
    service = {"kind": "service", "code": "groups", "role": "service"}
    assert not (await hub.policy.query("kits", {"principal": service, **ask})).allow
    owner = {"kind": "owner", "code": "owner", "role": "owner"}
    assert (await hub.policy.query("kits", {"principal": owner, **ask})).allow


# ------------------------------------------------------------ the secretary --
async def test_the_secretary_drafts_a_kit_and_no_work_item(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],
    fake_lines: FakeLines,
    groups: None,
) -> None:
    owner = owner_session["headers"]
    r = await client.post("/api/v1/orders/preview", headers=owner, json={"text": ORDER})
    assert r.status_code == 200, r.text
    route = r.json()
    assert route["kind"] == "kit" and route["kit"] == "content_brand"
    assert route["kit_name_fa"] == "تولید محتوای دانش مالی"
    assert route["preview_fa"].startswith("→") and "مُهر" in route["preview_fa"]
    assert humanize.check(route["preview_fa"]) == [] and humanize.check(route["why_fa"]) == []
    assert no_model == []  # the rules alone
    works = await su.fetchval("SELECT count(*) FROM work.work")
    companies = await count_companies(su)

    r = await client.post(
        "/api/v1/orders", headers={**owner, **idem()}, json={"text": ORDER, "source": "text"}
    )
    assert r.status_code == 201, r.text
    placed = r.json()
    assert placed["routed_by"] == "rules" and [x["kind"] for x in placed["routes"]] == ["kit"]
    assert placed["routes"][0].get("work_ref") is None and placed["route"]["kit"] == "content_brand"
    assert await su.fetchval("SELECT count(*) FROM work.work") == works  # no work item
    assert await count_companies(su) == companies  # nothing created before the seal
    ref = placed["ref"]

    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    assert rep["state"] == "waiting" and rep["steps"][0]["what_fa"].startswith("دریافت شد")
    assert rep["kit"]["kit"] == "content_brand" and rep["kit"]["sealed"] is False
    assert rep["kit"]["name_fa"] == "تولید محتوای دانش مالی"
    assert len(rep["kit"]["summary"]["lines"]) == 4
    blocker = rep["blockers"][0]
    assert blocker["kind"] == "kit_unsealed" and blocker["fix"] == {
        "action": "kit.create", "label_fa": "شرکت را بساز", "target": "content_brand",
    }  # fmt: skip
    assert humanize.check(blocker["title_fa"]) == []

    # a kit order of another kit does not seal this one
    other = body_of("saas_product", order=ref)
    r = await post_sealed(client, hub, owner_session, other)
    assert r.status_code == 409, r.text

    # the owner seals it: the company exists, the order is delivered
    body = body_of(order=ref)
    r = await post_sealed(client, hub, owner_session, body)
    assert r.status_code == 201, r.text
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    assert rep["state"] == "delivered" and rep["blockers"] == [] and rep["kit"]["sealed"] is True
    assert body["code"] in rep["summary"]["done_fa"]
    assert not await su.fetchval("SELECT 1 FROM work.work WHERE title LIKE '%' || $1 || '%'", ref)
    # sealed once: the same order cannot seal a second company
    again = await post_sealed(client, hub, owner_session, body_of(order=ref))
    assert again.status_code == 409


async def test_other_orders_are_not_taken_for_a_kit(no_model: list[Any]) -> None:
    from hq_api.domain import orders as O

    def kit(text: str) -> Any:
        return D.kit_of(text, O.normalise(text))

    assert kit("یک شرکت تازه برای محصول اپ موبایل بساز")[0] == "saas_product"
    assert kit("شرکت جدید برای کانال تلگرام و اینستاگرام")[0] == "content_brand"
    assert kit("یک شرکت جدید بساز")[1] is None  # no name said: the owner types it on the card
    assert kit("شرکت جدید «نگار» را بساز")[1] == "نگار"
    assert kit("۳ ریلز برای شرکت بساز") is None
    assert kit("گزارش فروش این هفته را بده") is None
    d = D.by_rules("چرا شرکت جدید ما ثبت نام ندارد", {"companies": {}}, None)
    assert d.kind != "kit"  # a question is a question
