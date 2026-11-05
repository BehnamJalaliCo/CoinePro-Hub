"""Prompt 22 part 3 (contract §31.3-§31.5): the newsletter (Listmonk), SEO rank and
competitors, one campaign calendar. Listmonk, egress and SearXNG are fakes; nothing
leaves the test. The first half needs no database (parsers, rules, the Listmonk client);
the second half runs on the database (migration 0041) and the routes."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import pytest

from hq_api.domain import campaigns as CP
from hq_api.domain import connections as CN
from hq_api.domain import gov_calendar as GC
from hq_api.domain import newsletter as NL
from hq_api.domain import seo as SEO
from hq_api.hub import Hub

from .conftest import step_up
from .p10_fakes import holding_switch

TZ = "Asia/Tehran"


def _owner_today() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(TZ)).date().isoformat()


DAY = date(2026, 11, 4)
NOW = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)


# ------------------------------------------------------------ no database --
def test_serp_position_is_the_first_hit_of_each_named_site() -> None:
    results = [
        {"url": "https://other.com/a"},
        {"url": "https://www.rival.ir/x"},
        {"url": "https://blog.us.com/p"},
        {"url": "https://us.com/q"},
    ]
    got = SEO.serp_positions(results, {"us": "us.com", "rival": "rival.ir", "none": "zzz.com"})
    assert got == {"us": (3, "https://blog.us.com/p"), "rival": (2, "https://www.rival.ir/x")}
    assert not SEO.same_site(
        "https://notus.com/", "us.com"
    )  # a suffix of the name is not a subdomain


def test_search_console_rows_weighted_by_impressions() -> None:
    rows = [
        {"keys": ["q", "https://a/1"], "impressions": 300, "position": 4.0},
        {"keys": ["q", "https://a/2"], "impressions": 100, "position": 12.0},
        {"keys": ["q", "https://a/3"], "impressions": 0, "position": 1.0},
    ]
    assert SEO.weighted_position(rows) == (6.0, "https://a/1")
    assert SEO.weighted_position([]) is None


def test_sitemaps_urlset_index_and_fresh_pages() -> None:
    urlset = (
        "<urlset><url><loc>https://r.com/a</loc><lastmod>2026-11-04T01:00:00+00:00</lastmod></url>"
        "<url><loc>https://r.com/b</loc><lastmod>2026-10-01</lastmod></url>"
        "<url><loc><![CDATA[https://r.com/c]]></loc></url></urlset>"
    )
    assert SEO.parse_sitemap(urlset, DAY) == ([], 3, ["2026-11-04"])
    index = (
        "<sitemapindex>"
        + "".join(f"<sitemap><loc>https://r.com/s{i}.xml</loc></sitemap>" for i in range(5))
        + "</sitemapindex>"
    )
    kids, pages, fresh = SEO.parse_sitemap(index, DAY)
    assert len(kids) == SEO.MAX_CHILD_SITEMAPS and pages == 0 and fresh == []
    assert SEO.new_pages(120, 100.0, 3) == 20 and SEO.new_pages(120, None, 3) == 3
    assert SEO.new_pages(90, 100.0, 0) == 0  # a shrinking sitemap is not news


def test_jump_rules_follow_the_thresholds() -> None:
    assert SEO.jump_of("new_pages", None, 5, pages=5, pct=10)
    assert not SEO.jump_of("new_pages", None, 4, pages=5, pct=10)
    assert SEO.jump_of("subscribers", 1000, 1100, pages=5, pct=10)
    assert not SEO.jump_of("subscribers", 1000, 1099, pages=5, pct=10)
    assert not SEO.jump_of("subscribers", None, 5000, pages=5, pct=10)  # no yesterday: no jump
    assert not SEO.jump_of("views", 1, 99999, pages=5, pct=10)
    title, brief = SEO.jump_text("رقیب", "new_pages", 0, 7)
    assert "رقیب" in title and "7" in brief


def item(
    kind: str,
    at: datetime | None,
    day: date | None = None,
    platform: str | None = "instagram_reel",
    company: str = "AA",
    ref: str = "x",
    state: str = "planned",
) -> CP.CampaignCalendarItem:
    return CP.CampaignCalendarItem(
        day=day or (at or NOW).date(),
        at=at,
        company=company,
        kind=kind,  # type: ignore[arg-type]
        ref=ref,
        title_fa="پست",
        platform=platform,
        state=state,
    )


def test_conflicts_spacing_per_channel_and_holiday() -> None:
    a = item("line", NOW, ref="a")
    b = item("manual", NOW + timedelta(minutes=30), ref="b")
    far = item("line", NOW + timedelta(hours=5), ref="far")
    other_channel = item("line", NOW + timedelta(minutes=10), platform="telegram_post", ref="t")
    other_company = item("line", NOW + timedelta(minutes=10), company="BB", ref="o")
    cancelled = item("line", NOW + timedelta(minutes=5), ref="c", state="cancelled")
    camp = item("campaign", None, platform=None, ref="k")
    items = [a, b, far, other_channel, other_company, cancelled, camp]
    CP.mark_conflicts(items, 120, {NOW.date(): ["نوروز"]})
    assert a.conflict_fa and "کمتر از 120 دقیقه" in a.conflict_fa and b.conflict_fa
    assert far.conflict_fa and far.conflict_fa.startswith("روز تعطیل")  # the holiday still marks it
    assert other_channel.conflict_fa.startswith("روز تعطیل")  # type: ignore[union-attr]
    assert "کمتر" not in (other_company.conflict_fa or "") and "کمتر" not in (
        cancelled.conflict_fa or ""
    )
    assert camp.conflict_fa is None  # a campaign spans days; it is not a post
    spaced = [item("line", NOW), item("line", NOW + timedelta(hours=3))]
    CP.mark_conflicts(spaced, 120, {})
    assert all(i.conflict_fa is None for i in spaced)


def test_window_span_and_channel_validation() -> None:
    CP.check_window(DAY, DAY + timedelta(days=CP.MAX_SPAN_DAYS))
    with pytest.raises(Exception, match="validation_failed"):
        CP.check_window(DAY, DAY + timedelta(days=CP.MAX_SPAN_DAYS + 1))
    with pytest.raises(Exception, match="validation_failed"):
        CP.check_span(DAY, DAY - timedelta(days=1))
    assert CP.valid_channels(["instagram_reel", "instagram_reel", "newsletter"]) == [
        "instagram_reel",
        "newsletter",
    ]
    with pytest.raises(Exception, match="validation_failed"):
        CP.valid_channels(["Not A Platform"])


def test_the_size_limit_and_the_send_time() -> None:
    assert NL.needs_seal(501, 500) and not NL.needs_seal(500, 500)
    with pytest.raises(Exception, match="validation_failed"):
        NL.future_or_raise(datetime(2026, 11, 4, 5, 59, tzinfo=UTC), NOW)
    with pytest.raises(Exception, match="validation_failed"):
        NL.future_or_raise(datetime(2026, 11, 5, 5, 0), NOW)  # no zone
    assert NL.future_or_raise(NOW + timedelta(hours=2), NOW) == NOW + timedelta(hours=2)


def test_newsletter_figures_from_a_listmonk_campaign() -> None:
    figs = NL.figures_of(
        DAY, {"id": 7, "sent": 400, "views": 120, "clicks": 31, "bounces": 2}, {3: 812}
    )
    got = {(f.key, f.subject): f.value for f in figs}
    assert got == {
        ("sent", "c7"): 400,
        ("opens", "c7"): 120,
        ("clicks", "c7"): 31,
        ("bounces", "c7"): 2,
        ("subscribers", "l3"): 812,
    }
    assert NL.figures_of(DAY, {"id": 7, "views": None}, {}) == []  # nothing is guessed


class FakeListmonk:
    """Listmonk's REST API as far as the hub uses it (token auth, `{"data": ...}`)."""

    def __init__(self, subscribers: int = 10) -> None:
        self.lists: dict[int, dict[str, Any]] = {}
        self.campaigns: dict[int, dict[str, Any]] = {}
        self.subscribers = subscribers
        self.calls: list[tuple[str, str]] = []
        self.token_ok = True
        self.base = random.randint(1000, 10**8)  # the test database outlives a run

    def client(self) -> NL.Listmonk:
        return NL.Listmonk("http://listmonk:9000", "hq", "tok", httpx.MockTransport(self.handle))

    def handle(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        self.calls.append((method, path))
        if req.headers.get("Authorization") != "token hq:tok" or not self.token_ok:
            return httpx.Response(403, json={"message": "forbidden"})
        body = json.loads(req.content) if req.content else {}
        if path == "/api/lists" and method == "GET":
            rows = [{**x, "subscriber_count": self.subscribers} for x in self.lists.values()]
            return httpx.Response(200, json={"data": {"results": rows}})
        if path == "/api/lists" and method == "POST":
            lid = self.base + len(self.lists) + 1
            assert body["optin"] == "double"  # consent first
            self.lists[lid] = {"id": lid, "name": body["name"]}
            return httpx.Response(200, json={"data": self.lists[lid]})
        if path.startswith("/api/lists/"):
            lid = int(path.rsplit("/", 1)[1])
            return httpx.Response(
                200, json={"data": {**self.lists[lid], "subscriber_count": self.subscribers}}
            )
        if path == "/api/campaigns" and method == "POST":
            cid = self.base + len(self.campaigns) + 1
            self.campaigns[cid] = {
                "id": cid,
                "status": "draft",
                "sent": 0,
                "views": 0,
                "clicks": 0,
                "bounces": 0,
                **body,
                "lists": [{"id": i} for i in body["lists"]],
            }
            return httpx.Response(200, json={"data": self.campaigns[cid]})
        if path.endswith("/status"):
            cid = int(path.split("/")[3])
            if cid not in self.campaigns:
                return httpx.Response(404, json={"message": "unknown campaign"})
            assert self.campaigns[cid].get("send_at"), "scheduled needs a send time"
            self.campaigns[cid]["status"] = body["status"]
            return httpx.Response(200, json={"data": self.campaigns[cid]})
        if path.startswith("/api/campaigns/"):
            cid = int(path.rsplit("/", 1)[1])
            if cid not in self.campaigns:
                return httpx.Response(404, json={"message": "unknown campaign"})
            if method == "PUT":
                self.campaigns[cid].update({**body, "lists": [{"id": i} for i in body["lists"]]})
            return httpx.Response(200, json={"data": self.campaigns[cid]})
        return httpx.Response(404, json={"message": "no"})


async def test_the_listmonk_client_sends_its_token_and_maps_refusals() -> None:
    fake = FakeListmonk()
    lm = fake.client()
    made = await lm.create_list("AA · خبرنامه")
    assert made["id"] == fake.base + 1 and [x["id"] for x in await lm.lists()] == [made["id"]]
    fake.token_ok = False
    with pytest.raises(Exception, match="channel_not_configured"):
        await lm.lists()
    down = NL.Listmonk(
        "http://listmonk:9000",
        "hq",
        "tok",
        httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))),
    )
    with pytest.raises(Exception, match="channel_not_configured"):
        await down.lists()


# ------------------------------------------------------------- the database --
class FakeBao:
    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data

    async def read_kv(self, path: str) -> dict[str, Any]:
        from hq_common.openbao import SecretNotFound

        if path not in self.data:
            raise SecretNotFound(path)
        return self.data[path]


@pytest.fixture
def newsletter(hub: Hub) -> Any:
    fake = FakeListmonk()
    NL.OVERRIDE = fake.client()
    yield fake
    NL.OVERRIDE = None


async def test_the_newsletter_is_off_without_the_profile_or_its_credential(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    c = (await new_company())["code"]
    r = await client.get(f"/api/v1/companies/{c}/newsletter", headers=h)
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["lists"] == []
    assert r.json()["note_fa"]
    made = await client.post(
        f"/api/v1/companies/{c}/newsletter/campaigns",
        headers=h,
        json={"subject": "سلام", "body": "<p>x</p>"},
    )
    assert made.status_code == 409 and made.json()["code"] == "channel_not_configured"
    object.__setattr__(hub.settings, "newsletter", True)
    try:
        hub.bao = FakeBao({})
        again = await client.post(
            f"/api/v1/companies/{c}/newsletter/campaigns",
            headers=h,
            json={"subject": "سلام", "body": "<p>x</p>"},
        )
        assert again.status_code == 409 and "OpenBao" in again.json()["message_fa"]
        assert await NL.credentials(
            FakeBao({NL.CREDENTIAL_PATH: {"user": "hq", "token": "t"}})
        ) == ("hq", "t")
    finally:
        object.__setattr__(hub.settings, "newsletter", False)
        hub.bao = None


async def test_a_campaign_is_a_draft_and_a_big_list_needs_the_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    newsletter: FakeListmonk,
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = await new_company()
    c = co["code"]
    made = await client.post(
        f"/api/v1/companies/{c}/newsletter/campaigns",
        headers=h,
        json={"subject": "تخفیف پاییزی", "body": "<p>سلام</p>"},
    )
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    assert made.json()["state"] == "draft" and made.json()["list_id"] == newsletter.base + 1
    lists = (await client.get(f"/api/v1/companies/{c}/newsletter", headers=h)).json()
    assert len(lists["lists"]) == 1 and lists["lists"][0]["subscribers"] == 10
    assert (
        lists["campaigns"][0]["id"] == cid
        and lists["size_limit"] == hub.settings.newsletter_size_limit
    )
    # a second campaign reuses the company's list
    await client.post(
        f"/api/v1/companies/{c}/newsletter/campaigns",
        headers=h,
        json={"subject": "دوم", "body": "x"},
    )
    assert len(newsletter.lists) == 1
    at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    past = await client.post(
        f"/api/v1/newsletter/campaigns/{cid}/schedule",
        headers=h,
        json={"at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )
    assert past.status_code == 422
    # a small list: no seal
    small = await client.post(
        f"/api/v1/newsletter/campaigns/{cid}/schedule", headers=h, json={"at": at}
    )
    assert small.status_code == 200, small.text
    assert small.json()["state"] == "scheduled" and small.json()["list_size"] == 10
    assert (
        newsletter.campaigns[newsletter.base + 1]["status"] == "scheduled"
        and newsletter.campaigns[newsletter.base + 1]["send_at"]
    )
    # a big list: refused without the seal, sent with it
    newsletter.subscribers = hub.settings.newsletter_size_limit + 1
    second = (await client.get(f"/api/v1/companies/{c}/newsletter", headers=h)).json()["campaigns"][
        0
    ]["id"]
    no_su = await client.post(
        f"/api/v1/newsletter/campaigns/{second}/schedule", headers=h, json={"at": at}
    )
    assert no_su.status_code == 403 and no_su.json()["code"] == "step_up_required"
    assert newsletter.campaigns[newsletter.base + 2]["status"] == "draft"
    su_h = await step_up(hub, sid, "newsletter.send", second)
    ok = await client.post(
        f"/api/v1/newsletter/campaigns/{second}/schedule", headers={**h, **su_h}, json={"at": at}
    )
    assert (
        ok.status_code == 200 and ok.json()["list_size"] == hub.settings.newsletter_size_limit + 1
    )
    row = await su.fetchrow(
        "SELECT state FROM growth.newsletter_campaigns WHERE id = $1", UUID(second)
    )
    assert row["state"] == "scheduled"
    one = await client.get(f"/api/v1/newsletter/campaigns/{cid}", headers=h)
    assert one.status_code == 200 and one.json()["sent"] == 0
    audit = await su.fetch(
        "SELECT step_up FROM audit.entries WHERE action = 'newsletter.send' AND target_ref = $1",
        second,
    )
    assert audit and audit[0]["step_up"] is True


async def test_the_daily_newsletter_read_writes_metrics_and_follows_the_state(
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    newsletter: FakeListmonk,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    made = await client.post(
        f"/api/v1/companies/{co['code']}/newsletter/campaigns",
        headers=h,
        json={"subject": "s", "body": "b"},
    )
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    sched = await client.post(
        f"/api/v1/newsletter/campaigns/{cid}/schedule",
        headers=h,
        json={"at": (datetime.now(UTC) + timedelta(hours=3)).isoformat()},
    )
    assert sched.status_code == 200, sched.text
    newsletter.campaigns[newsletter.base + 1].update(
        status="finished", sent=10, views=6, clicks=2, bounces=0
    )
    async with holding_switch(su, "released"):
        out = await NL.read_daily(hub)
    assert out["read"] >= 5, out
    rows = await su.fetch(
        "SELECT key, subject, value FROM growth.metrics_daily WHERE company_id = $1 AND kind = 'newsletter'",
        co["id"],
    )
    assert {(r["key"], r["subject"]): float(r["value"]) for r in rows} == {
        ("subscribers", f"l{newsletter.base + 1}"): 10.0,
        ("sent", f"c{newsletter.base + 1}"): 10.0,
        ("opens", f"c{newsletter.base + 1}"): 6.0,
        ("clicks", f"c{newsletter.base + 1}"): 2.0,
        ("bounces", f"c{newsletter.base + 1}"): 0.0,
    }
    state = await su.fetchval(
        "SELECT state FROM growth.newsletter_campaigns WHERE id = $1", UUID(cid)
    )
    assert state == "finished"
    async with holding_switch(su, "engaged"):
        assert (await NL.read_daily(hub)).get(
            "skipped"
        ) is True  # nothing while the holding is locked


class FakeEgress:
    """Egress for the SEO reads: POST /v1/http by host (Google, sitemaps, YouTube, Telegram)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sitemap_pages = 12

    async def request(self, method: str, url: str, *, company: str, **kw: Any) -> CN.Answer:
        self.calls.append({"method": method, "url": url, "company": company, **kw})
        host = urlsplit(url).hostname or ""
        entry = {
            "tool": "http.request",
            "kind": "request",
            "class": "A0",
            "method": method,
            "host": host,
            "status": 200,
            "bytes_in": 10,
            "bytes_out": 0,
            "ms": 5,
        }
        if host == "rival.example":
            urls = "".join(
                # modified today in the owner's zone (a fixed date went stale on 2026-11-06)
                f"<url><loc>https://rival.example/p{i}</loc><lastmod>{_owner_today()}</lastmod></url>"
                for i in range(self.sitemap_pages)
            )
            return CN.Answer("ok", 200, f"<urlset>{urls}</urlset>", None, [entry])
        if host == "www.googleapis.com" and "/youtube/" in url:
            st = {"subscriberCount": "2000", "viewCount": "9", "videoCount": "3"}
            return CN.Answer("ok", 200, json.dumps({"items": [{"statistics": st}]}), None, [entry])
        if host == "api.telegram.org":
            return CN.Answer("ok", 200, json.dumps({"ok": True, "result": 1500}), None, [entry])
        return CN.Answer("error", None, "", "fetch_failed", [entry])


async def test_seo_crud_daily_read_ranks_and_a_competitor_jump(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    c = co["code"]
    kw = await client.post(
        f"/api/v1/companies/{c}/keywords",
        headers=h,
        json={"phrase": "ساخت سایت", "site": "Us.example"},
    )
    assert kw.status_code == 201 and kw.json()["site"] == "us.example"
    dup = await client.post(
        f"/api/v1/companies/{c}/keywords",
        headers=h,
        json={"phrase": "ساخت سایت", "site": "us.example"},
    )
    assert dup.status_code == 409
    bad = await client.post(
        f"/api/v1/companies/{c}/keywords", headers=h, json={"phrase": "x", "site": "not a host"}
    )
    assert bad.status_code == 422
    kid = kw.json()["id"]
    comp = await client.post(
        f"/api/v1/companies/{c}/competitors",
        headers=h,
        json={
            "name_fa": "رقیب",
            "site": "rival.example",
            "youtube": "UC" + "a" * 22,
            "telegram": "rival_ch",
        },
    )
    assert comp.status_code == 201, comp.text
    comp_id = comp.json()["id"]
    paused = await client.put(
        f"/api/v1/companies/{c}/keywords/{kid}", headers=h, json={"state": "paused"}
    )
    assert paused.json()["state"] == "paused"
    await client.put(f"/api/v1/companies/{c}/keywords/{kid}", headers=h, json={"state": "on"})
    assert (
        await client.put(f"/api/v1/companies/{c}/keywords/{kid}", headers=h, json={})
    ).status_code == 422

    # yesterday: the competitor's sitemap had 3 pages and 1000 telegram members
    await su.execute(
        "INSERT INTO growth.competitor_daily (company_id, competitor_id, day, key, value, source) "
        "VALUES ($1, $2, current_date - 1, 'pages', 3, 'sitemap'), ($1, $2, current_date - 1, 'members', 1000, 'telegram')",
        co["id"],
        UUID(comp_id),
    )
    egress = FakeEgress()
    CN.OVERRIDE = egress

    serps: list[str] = []

    async def serp(
        _hub: Any, company: str, q: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if company != c:  # companies of earlier runs (the test database outlives a run)
            return [], []
        assert q == "ساخت سایت"
        serps.append(q)
        return (
            [
                {"url": "https://other.com/1"},
                {"url": "https://rival.example/x"},
                {"url": "https://us.example/p"},
            ],
            [
                {
                    "tool": "web.search",
                    "kind": "search",
                    "class": "A0",
                    "method": "GET",
                    "host": "searxng",
                    "status": 200,
                    "bytes_in": 1,
                    "bytes_out": 0,
                    "ms": 3,
                }
            ],
        )

    SEO.SEARCH = serp
    hub.bao = FakeBao(
        {
            f"hq/growth/{c}/youtube": {"secret": "AIza" + "k" * 35},
            f"hq/growth/{c}/telegram": {"secret": "123456:" + "T" * 35},
        }
    )
    try:
        async with holding_switch(su, "released"):
            out = await SEO.read_daily(hub)
            again = await SEO.read_daily(hub)
    finally:
        CN.OVERRIDE = None
        SEO.SEARCH = None
        hub.bao = None
    assert out["companies"] >= 1 and out["jumps"] >= 2, out
    assert again["companies"] >= 0 and serps == ["ساخت سایت"]  # once a day each
    ranks = (await client.get(f"/api/v1/companies/{c}/ranks?days=3", headers=h)).json()
    assert [(r["source"], r["position"], r["approximate"]) for r in ranks] == [
        ("searxng", 3.0, True)
    ]
    assert ranks[0]["note_fa"] and ranks[0]["url"] == "https://us.example/p"
    daily = (await client.get(f"/api/v1/companies/{c}/competitors/daily?days=3", headers=h)).json()
    latest = max(d["day"] for d in daily)  # today in the owner's zone
    got = {(d["key"], d["source"]): d["value"] for d in daily if d["day"] == latest}
    assert got[("serp_best", "searxng")] == 2.0 and got[("serp_visible", "searxng")] == 1.0
    assert got[("new_pages", "sitemap")] == 12.0 and got[("subscribers", "youtube")] == 2000.0
    assert got[("members", "telegram")] == 1500.0
    # the jump became work for the growth department, never a card for the owner; once only
    jumps = await su.fetch(
        "SELECT key, work_id FROM growth.competitor_jumps WHERE company_id = $1 ORDER BY key",
        co["id"],
    )
    assert [j["key"] for j in jumps] == ["members", "new_pages"] and all(
        j["work_id"] for j in jumps
    )
    work = await su.fetchrow(
        "SELECT w.title, e.department_id FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1",
        jumps[1]["work_id"],
    )
    assert "رقیب" in work["title"]
    dept = await su.fetchval(
        "SELECT code FROM core.departments WHERE id = $1", work["department_id"]
    )
    assert dept == "GROWTH"
    # every call left through egress as this company and is in its log
    assert {x["company"] for x in egress.calls} == {c}
    assert (
        await su.fetchval(
            "SELECT count(*) FROM egress.log WHERE company_id = $1 AND actor = 'seo-read'", co["id"]
        )
        >= 4
    )
    stream = await su.fetch(
        "SELECT payload->>'type' AS t FROM core.outbox WHERE subject LIKE $1", f"hq.core.{c}.%"
    )
    assert {"rank.daily", "competitor.jump"} <= {s["t"] for s in stream}
    # delete: the keyword and its ranks go; the competitor and its figures go
    assert (
        await client.delete(f"/api/v1/companies/{c}/keywords/{kid}", headers=h)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/companies/{c}/competitors/{comp_id}", headers=h)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/companies/{c}/competitors/{comp_id}", headers=h)
    ).status_code == 404
    assert (
        await su.fetchval("SELECT count(*) FROM growth.rank_daily WHERE company_id = $1", co["id"])
        == 0
    )


async def test_search_console_position_is_read_per_keyword(
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
) -> None:
    from .test_p21_connections import FakeBao as SCBao
    from .test_p21_connections import service_account

    h = owner_session["headers"]
    co = await new_company()
    c = co["code"]
    sa, _ = service_account()
    await client.post(
        f"/api/v1/companies/{c}/keywords", headers=h, json={"phrase": "کلمه", "site": "us.example"}
    )
    await su.execute(
        "INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set) VALUES ($1, 'search_console', 'ا', $2::jsonb, true)",
        co["id"],
        json.dumps({"site_url": "sc-domain:us.example"}),
    )

    class SC:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, *, company: str, **kw: Any) -> CN.Answer:
            host = urlsplit(url).hostname
            if host == "oauth2.googleapis.com":
                return CN.Answer(
                    "ok", 200, json.dumps({"access_token": "ya29." + "A" * 40}), None, []
                )
            if company == c:
                self.calls.append(kw)
            rows = [{"keys": ["کلمه", "https://us.example/a"], "impressions": 50, "position": 7.0}]
            return CN.Answer("ok", 200, json.dumps({"rows": rows}), None, [])

    async def nothing(*_a: Any) -> tuple[list[Any], list[Any]]:
        return [], []

    sc = SC()
    CN.OVERRIDE, SEO.SEARCH = sc, nothing
    hub.bao = SCBao({f"hq/growth/{c}/search_console": sa})
    try:
        async with holding_switch(su, "released"):
            await SEO.read_daily(hub)
    finally:
        CN.OVERRIDE, SEO.SEARCH, hub.bao = None, None, None
    ranks = (await client.get(f"/api/v1/companies/{c}/ranks", headers=h)).json()
    assert [(r["source"], r["position"], r["approximate"], r["note_fa"]) for r in ranks] == [
        ("search_console", 7.0, False, None)
    ]
    f = sc.calls[0]["json_body"]
    assert (
        f["dimensions"] == ["query", "page"]
        and f["dimensionFilterGroups"][0]["filters"][0]["expression"] == "کلمه"
    )
    listed = (await client.get(f"/api/v1/companies/{c}/keywords", headers=h)).json()
    assert listed[0]["position"] == 7.0 and listed[0]["source"] == "search_console"


async def test_the_campaign_calendar_merges_every_source_and_marks_conflicts(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    newsletter: FakeListmonk,
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    c = co["code"]
    camp = await client.post(
        "/api/v1/campaigns",
        headers=h,
        json={
            "company": c,
            "title_fa": "پاییز",
            "goal_fa": "فروش",
            "starts": "2027-03-19",
            "ends": "2027-03-25",
            "channels": ["instagram_reel", "newsletter"],
            "budget": 5000,
        },
    )
    assert camp.status_code == 201, camp.text
    assert (
        camp.json()["channels"] == ["instagram_reel", "newsletter"]
        and camp.json()["budget"] == 5000
    )
    assert (
        await client.post(
            "/api/v1/campaigns",
            headers=h,
            json={"company": c, "title_fa": "x", "starts": "2027-03-05", "ends": "2027-03-01"},
        )
    ).status_code == 422
    hol = min(
        d for d in GC.load_holidays() if d >= date.today() + timedelta(days=2)
    )  # a real holiday, ahead
    at1 = datetime.combine(hol, datetime.min.time(), UTC) + timedelta(hours=9)
    m1 = await client.post(
        "/api/v1/campaign-calendar/items",
        headers=h,
        json={
            "company": c,
            "day": hol.isoformat(),
            "at": at1.isoformat(),
            "title_fa": "ریلز",
            "platform": "instagram_reel",
        },
    )
    m2 = await client.post(
        "/api/v1/campaign-calendar/items",
        headers=h,
        json={
            "company": c,
            "day": hol.isoformat(),
            "at": (at1 + timedelta(minutes=45)).isoformat(),
            "title_fa": "ریلز دوم",
            "platform": "instagram_reel",
        },
    )
    assert m1.status_code == 201 and m2.status_code == 201
    nl = (
        await client.post(
            f"/api/v1/companies/{c}/newsletter/campaigns",
            headers=h,
            json={"subject": "خبرنامه", "body": "b"},
        )
    ).json()["id"]
    send = at1 + timedelta(days=2)
    if send > datetime.now(UTC):
        await client.post(
            f"/api/v1/newsletter/campaigns/{nl}/schedule", headers=h, json={"at": send.isoformat()}
        )
    cal = await client.get(
        "/api/v1/campaign-calendar",
        headers=h,
        params={
            "from": (hol - timedelta(days=1)).isoformat(),
            "to": (hol + timedelta(days=3)).isoformat(),
            "company": c,
        },
    )
    assert cal.status_code == 200, cal.text
    body = cal.json()
    assert "from" in body and body["holidays"]
    by_ref = {i["ref"]: i for i in body["items"]}
    first, second = by_ref[m1.json()["ref"]], by_ref[m2.json()["ref"]]
    assert (
        first["kind"] == "manual"
        and "کمتر از" in first["conflict_fa"]
        and "روز تعطیل" in first["conflict_fa"]
    )
    assert second["conflict_fa"]
    kinds = {i["kind"] for i in body["items"]}
    assert "manual" in kinds and ({"newsletter"} <= kinds or send <= datetime.now(UTC))
    wide = await client.get(
        "/api/v1/campaign-calendar",
        headers=h,
        params={"from": "2027-03-01", "to": "2027-03-31", "company": c},
    )
    assert [i["kind"] for i in wide.json()["items"]] == ["campaign"] and wide.json()["items"][0][
        "day"
    ] == "2027-03-19"
    too_long = await client.get(
        "/api/v1/campaign-calendar", headers=h, params={"from": "2027-01-01", "to": "2027-12-31"}
    )
    assert too_long.status_code == 422
    # the change calendar of §20 is untouched
    assert (
        await client.get(
            "/api/v1/calendar", headers=h, params={"from": "2027-03-01", "to": "2027-03-31"}
        )
    ).status_code == 200
    # update, delete
    cid = camp.json()["id"]
    upd = await client.put(
        f"/api/v1/campaigns/{cid}", headers=h, json={"state": "running", "ends": "2027-03-30"}
    )
    assert (
        upd.status_code == 200
        and upd.json()["state"] == "running"
        and upd.json()["ends"] == "2027-03-30"
    )
    assert (
        await client.put(f"/api/v1/campaigns/{cid}", headers=h, json={"ends": "2027-03-01"})
    ).status_code == 422
    assert [
        x["id"] for x in (await client.get(f"/api/v1/campaigns?company={c}", headers=h)).json()
    ] == [cid]
    assert (await client.delete(f"/api/v1/campaigns/{cid}", headers=h)).status_code == 204
    assert (await client.get(f"/api/v1/campaigns/{cid}", headers=h)).status_code == 404
    item_id = m1.json()["ref"]
    assert (
        await client.put(
            f"/api/v1/campaign-calendar/items/{item_id}", headers=h, json={"state": "done"}
        )
    ).json()["state"] == "done"
    assert (
        await client.delete(f"/api/v1/campaign-calendar/items/{item_id}", headers=h)
    ).status_code == 204
    types = {
        r["t"]
        for r in await su.fetch(
            "SELECT payload->>'type' AS t FROM core.outbox WHERE subject LIKE $1", f"hq.core.{c}.%"
        )
    }
    assert "campaign.updated" in types


async def test_the_calendar_works_alone_without_the_engines_or_the_ads_tables(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """The lines and ads sources are optional: with their tables missing they give nothing."""
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await CP._optional(tx, "growth.campaigns")
        assert not await CP._optional(tx, "growth.no_such_table")
        cal = await CP.build(
            tx, DAY, DAY + timedelta(days=2), 120, TZ, await hub.companies.by_code(co["code"])
        )
    assert cal.items == []


async def test_the_calendar_shows_the_lines_runs_and_marks_them_with_a_manual_post(
    client: httpx.AsyncClient,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    """The engine's runs (§30, migration 0040) join the calendar through its own store."""
    h = owner_session["headers"]
    co = await new_company()
    c = co["code"]
    at = datetime.now(UTC) + timedelta(hours=1)
    line = await su.fetchval(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa, caps, steps)
           VALUES ($1, 'cal_line', 1, 'telegram_post', 'کانال خبر', '{}', '[]') RETURNING id""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, at)
           VALUES ($1, $2, 1, 'owner', 'queued', $3), ($1, $2, 1, 'owner', 'cancelled', $3)""",
        co["id"],
        line,
        at,
    )
    manual = await client.post(
        "/api/v1/campaign-calendar/items",
        headers=h,
        json={
            "company": c,
            "day": at.date().isoformat(),
            "at": (at + timedelta(minutes=20)).isoformat(),
            "title_fa": "پست دستی",
            "platform": "telegram_post",
        },
    )
    assert manual.status_code == 201
    cal = await client.get(
        "/api/v1/campaign-calendar",
        headers=h,
        params={
            "from": (at - timedelta(days=1)).date().isoformat(),
            "to": (at + timedelta(days=1)).date().isoformat(),
            "company": c,
        },
    )
    assert cal.status_code == 200, cal.text
    items = cal.json()["items"]
    lines = [i for i in items if i["kind"] == "line"]
    assert len(lines) == 1 and lines[0]["title_fa"] == "کانال خبر" and lines[0]["state"] == "queued"
    assert (
        lines[0]["platform"] == "telegram_post" and lines[0]["company"] == c
    )  # the cancelled run is left out
    posts = [i for i in items if i["platform"] == "telegram_post"]
    assert len(posts) == 2 and all("کمتر از" in (i["conflict_fa"] or "") for i in posts)


async def test_only_the_owner_reaches_the_growth_routes(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    for path in (
        f"/api/v1/companies/{co['code']}/newsletter",
        f"/api/v1/companies/{co['code']}/keywords",
        f"/api/v1/companies/{co['code']}/ranks",
        f"/api/v1/companies/{co['code']}/competitors",
        f"/api/v1/companies/{co['code']}/competitors/daily",
        "/api/v1/campaigns",
        "/api/v1/campaign-calendar?from=2027-01-01&to=2027-01-02",
    ):
        assert (await client.get(path)).status_code == 401, path


async def test_another_companys_rows_are_invisible_by_rls(
    su: Any, new_company: Callable[..., Any], hub: Hub
) -> None:
    a, b = await new_company(), await new_company()
    await su.execute(
        "INSERT INTO growth.keywords (company_id, phrase, site) VALUES ($1, 'k', 'a.example')",
        a["id"],
    )
    async with hub.db.tx([b["id"]]) as tx:
        assert await tx.scalar("SELECT count(*) FROM growth.keywords") == 0
    async with hub.db.tx([a["id"]]) as tx:
        assert await tx.scalar("SELECT count(*) FROM growth.keywords") >= 1


def test_the_newsletter_line_template_is_valid_data() -> None:
    """seed/lines/newsletter.yaml: the §30.1 shape, step kinds the engine knows, inputs that exist."""
    from pathlib import Path

    import yaml

    from hq_api.lines import templates as line_templates
    from hq_api.lines.base import KINDS

    path = Path(__file__).resolve().parents[1] / "seed" / "lines" / "newsletter.yaml"
    text = path.read_text(encoding="utf-8")
    t = yaml.safe_load(text)
    assert line_templates.validate(t).key == "newsletter"  # the engine's own validation
    assert "newsletter" in line_templates.load() and line_templates.refused() == ()
    assert t["key"] == "newsletter" and t["platform"] == "newsletter" and t["version"] >= 1
    assert t["title_fa"] and t["outputs_fa"] and t["defaults"]["insights"]["metric"] == "opens"
    keys = [s["key"] for s in t["steps"]]
    assert len(keys) == len(set(keys))
    for i, s in enumerate(t["steps"]):
        assert s["kind"] in KINDS, s["key"]
        assert set(s["inputs"]) <= set(keys[:i]), s["key"]  # inputs are earlier steps
        assert s["gate"] in ("auto", "owner", "ceo") and 1 <= s["max_attempts"] <= 3
        assert s["title_fa"] and s["timeout_s"] > 0
    assert t["steps"][-1]["kind"] == "publish"
    assert "CoinePro" not in text  # a template names no company
