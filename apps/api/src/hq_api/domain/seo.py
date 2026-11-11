"""SEO rank and competitors (contract §31.4 ⟨1.13⟩). Rule-based: no model reads a figure.

Keywords and competitors are data of a company (growth.keywords, growth.competitors).
Once a day, by code, through the egress service (nothing here opens a socket of its own):

  our position     Search Console (the company's `search_console` connection, the
                   last week's average for the exact query, weighted by impressions)
                   -> growth.rank_daily, source `search_console`
  a SERP check     the hub's SearXNG (egress POST /v1/search) for each keyword: the
                   first result of our site, and of each competitor's site, in the
                   page of results -> source `searxng`, APPROXIMATE (one engine mix,
                   no login, no location); competitors: serp_visible / serp_best
  competitors      the sitemap's pages and the new ones today (egress GET), a YouTube
                   channel's subscribers / views / videos (the company's own YouTube
                   key, if set), a public Telegram channel's members (the company's
                   bot token, if set) -> growth.competitor_daily
  a jump           new pages in a day or a follower move in percent, past the
                   settings' thresholds -> one work item for the company's growth
                   department (its manager, not the owner) and `competitor.jump`
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID

from pydantic import Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gate
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model

log = logging.getLogger("hq_api.seo")

SERVICE = Principal(kind="service", code="seo", role="service")
SITE = r"^[A-Za-z0-9.-]{3,253}$"
SC_DAYS = 8
SERP_N = 20
MAX_KEYWORDS_PER_DAY = 40
GROWTH_DEPARTMENT = "GROWTH"
APPROX_FA = "تقریبی (از جست‌وجوی خودِ هاب؛ جای دقیق گوگل نیست)"
FOLLOW_KEYS = ("subscribers", "members")  # a follower move is judged in percent
SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
MAX_CHILD_SITEMAPS = 3
# A sitemap whose URLs are this share (%) or more "modified today" is stamped wholesale.
STAMPED_PCT = 90
LOC = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)\s*(?:\]\]>)?\s*</loc>", re.I)
URL_BLOCK = re.compile(r"<url>(.*?)</url>", re.I | re.S)
LASTMOD = re.compile(r"<lastmod>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
INDEX = re.compile(r"<sitemapindex", re.I)


# ----------------------------------------------------------------- models --
class KeywordIn(Model):
    phrase: str = Field(min_length=1, max_length=200)
    site: str = Field(pattern=SITE)
    target_url: str | None = Field(default=None, max_length=2000)
    state: str = Field(default="on", pattern="^(on|paused)$")


class KeywordPut(Model):
    phrase: str | None = Field(default=None, min_length=1, max_length=200)
    site: str | None = Field(default=None, pattern=SITE)
    target_url: str | None = Field(default=None, max_length=2000)
    state: str | None = Field(default=None, pattern="^(on|paused)$")


class Keyword(Model):
    id: UUID
    company: str
    phrase: str
    site: str
    target_url: str | None
    state: str
    position: float | None = None  # the latest known (Search Console first)
    source: str | None = None
    day: date | None = None


class RankPoint(Model):
    keyword: UUID
    phrase: str
    day: date
    source: str
    position: float | None
    url: str | None
    approximate: bool
    note_fa: str | None = None


class CompetitorIn(Model):
    name_fa: str = Field(min_length=1, max_length=200)
    site: str | None = Field(default=None, pattern=SITE)
    instagram: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._]{1,64}$")
    youtube: str | None = Field(default=None, pattern=r"^UC[A-Za-z0-9_-]{20,24}$")
    telegram: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{4,64}$")
    state: str = Field(default="on", pattern="^(on|paused)$")


class CompetitorPut(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    site: str | None = Field(default=None, pattern=SITE)
    instagram: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._]{1,64}$")
    youtube: str | None = Field(default=None, pattern=r"^UC[A-Za-z0-9_-]{20,24}$")
    telegram: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{4,64}$")
    state: str | None = Field(default=None, pattern="^(on|paused)$")


class Competitor(Model):
    id: UUID
    company: str
    name_fa: str
    site: str | None
    instagram: str | None
    youtube: str | None
    telegram: str | None
    state: str


class CompetitorPoint(Model):
    competitor: UUID
    name_fa: str
    day: date
    key: str
    value: float
    source: str


# ----------------------------------------------------------- pure parsers --
def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def same_site(url: str, site: str) -> bool:
    """`url` is on `site` (or one of its subdomains)."""
    host, want = host_of(url), site.lower().removeprefix("www.")
    return bool(host) and (host == want or host.endswith("." + want))


def serp_positions(
    results: list[dict[str, Any]], sites: dict[str, str]
) -> dict[str, tuple[int, str]]:
    """The best (first) position of each named site in a page of results, 1-based.
    `sites` maps a name to its domain; a site absent from the page is absent here."""
    found: dict[str, tuple[int, str]] = {}
    for i, r in enumerate(results, start=1):
        url = str(r.get("url") or "")
        for name, site in sites.items():
            if name not in found and same_site(url, site):
                found[name] = (i, url)
    return found


def weighted_position(rows: list[dict[str, Any]]) -> tuple[float, str | None] | None:
    """Search Console rows (query, page) -> the average position weighted by
    impressions and the page with the most impressions. None without rows."""
    total, acc, best_url, best_imp = 0.0, 0.0, None, -1.0
    for row in rows:
        imp, pos = CN._num(row.get("impressions")), CN._num(row.get("position"))
        if imp is None or pos is None or imp <= 0:
            continue
        total += imp
        acc += imp * pos
        keys = row.get("keys") or []
        if imp > best_imp and len(keys) > 1:
            best_imp, best_url = imp, str(keys[1])
    if total <= 0:
        return None
    return round(acc / total, 1), best_url


def parse_sitemap(xml: str, today: date) -> tuple[list[str], int, list[str]]:
    """A sitemap body -> (children, pages, fresh days). An index gives its first child
    sitemaps and no pages; a urlset gives its URL count and the days of those modified
    yesterday or today. Regex only: the body is untrusted."""
    if INDEX.search(xml):
        return LOC.findall(xml)[:MAX_CHILD_SITEMAPS], 0, []
    blocks = URL_BLOCK.findall(xml)
    pages = len(blocks) or len(LOC.findall(xml))
    fresh = []
    cutoff = (today - timedelta(days=1)).isoformat()
    for b in blocks:
        m = LASTMOD.search(b)
        if m and m.group(1) >= cutoff:
            fresh.append(m.group(1))
    return [], pages, fresh


def new_pages(pages: int, previous: float | None, fresh: int) -> int:
    """New pages today: the growth of the sitemap since yesterday, or the pages
    marked modified since yesterday, whichever is larger. A sitemap that stamps
    (nearly) every URL with today's date (one built on each request, many CMS
    plugins) says nothing about new pages: only its growth counts then."""
    grown = max(0, pages - int(previous)) if previous is not None else 0
    if pages > 0 and fresh * 100 >= pages * STAMPED_PCT:
        return grown
    return max(grown, fresh)


def jump_of(key: str, before: float | None, after: float, *, pages: int, pct: int) -> bool:
    """Whether a day's figure is a competitor jump (settings' thresholds)."""
    if key == "new_pages":
        return after >= pages
    if key in FOLLOW_KEYS:
        return before is not None and before > 0 and (after - before) * 100 / before >= pct
    return False


def jump_text(name: str, key: str, before: float | None, after: float) -> tuple[str, str]:
    if key == "new_pages":
        title = f"رقیب «{name}» امروز {int(after)} صفحه‌ی تازه گذاشته است"
        brief = (
            f"Competitor {name} published {int(after)} new pages today (sitemap, public figures). "
            "Look at what they target, compare with our keywords and propose one reply to the growth "
            "lead's plan. Do not copy their text."
        )
    else:
        title = f"دنبال‌کننده‌های رقیب «{name}» به‌طور چشمگیر بالا رفته است"
        brief = (
            f"Competitor {name}: {key} moved from {int(before or 0)} to {int(after)} (public figure, "
            "read by code). Find what they did in the last days (public posts only) and propose "
            "one response."
        )
    return title, brief


# ------------------------------------------------------------------- CRUD --
def keyword_out(code: str, r: dict[str, Any]) -> Keyword:
    return Keyword(
        id=r["id"],
        company=code,
        phrase=r["phrase"],
        site=r["site"],
        target_url=r["target_url"],
        state=r["state"],
        position=_f(r.get("position")),
        source=r.get("source"),
        day=r.get("day"),
    )


def competitor_out(code: str, r: dict[str, Any]) -> Competitor:
    return Competitor(
        id=r["id"],
        company=code,
        name_fa=r["name_fa"],
        site=r["site"],
        instagram=r["instagram"],
        youtube=r["youtube"],
        telegram=r["telegram"],
        state=r["state"],
    )


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


async def keywords_of(tx: Tx, company: Any) -> list[Keyword]:
    rows = await tx.all(
        """SELECT k.*, l.position, l.source, l.day FROM growth.keywords k
           LEFT JOIN LATERAL (SELECT r.position, r.source, r.day FROM growth.rank_daily r
                              WHERE r.keyword_id = k.id AND r.position IS NOT NULL
                              ORDER BY r.day DESC, (r.source = 'search_console') DESC LIMIT 1) l ON true
           WHERE k.company_id = :co ORDER BY k.created_at""",
        co=company.id,
    )
    return [keyword_out(company.code, dict(r)) for r in rows]


async def ranks_of(tx: Tx, company: Any, days: int) -> list[RankPoint]:
    rows = await tx.all(
        """SELECT r.keyword_id, k.phrase, r.day, r.source, r.position, r.url
           FROM growth.rank_daily r JOIN growth.keywords k ON k.id = r.keyword_id
           WHERE r.company_id = :co AND r.day > current_date - CAST(:d AS int)
           ORDER BY r.day DESC, k.phrase, r.source""",
        co=company.id,
        d=days,
    )
    return [
        RankPoint(
            keyword=r["keyword_id"],
            phrase=r["phrase"],
            day=r["day"],
            source=r["source"],
            position=_f(r["position"]),
            url=r["url"],
            approximate=r["source"] == "searxng",
            note_fa=APPROX_FA if r["source"] == "searxng" else None,
        )
        for r in rows
    ]


async def competitor_points(tx: Tx, company: Any, days: int) -> list[CompetitorPoint]:
    rows = await tx.all(
        """SELECT d.competitor_id, c.name_fa, d.day, d.key, d.value, d.source
           FROM growth.competitor_daily d JOIN growth.competitors c ON c.id = d.competitor_id
           WHERE d.company_id = :co AND d.day > current_date - CAST(:d AS int)
           ORDER BY d.day DESC, c.name_fa, d.key""",
        co=company.id,
        d=days,
    )
    return [
        CompetitorPoint(
            competitor=r["competitor_id"],
            name_fa=r["name_fa"],
            day=r["day"],
            key=r["key"],
            value=float(r["value"]),
            source=r["source"],
        )
        for r in rows
    ]


# ------------------------------------------------------------- the readers --
@dataclass
class Day:
    """What one company's day read, to store."""

    ranks: list[tuple[UUID, str, float | None, str | None]]  # keyword, source, position, url
    figures: list[tuple[UUID, str, float, str]]  # competitor, key, value, source
    entries: list[dict[str, Any]]


async def search(
    hub: Any, company: str, q: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One SearXNG query through egress: (results, egress log entries). Raises
    CN.ReadError with a Persian reason when egress or SearXNG does not answer."""
    import httpx

    url = hub.settings.support_egress_url.rstrip("/") + "/v1/search"
    payload = {
        "ctx": {"company": company, "actor": "seo-read", "cls": "A0"},
        "q": q[:500],
        "lang": "fa",
        "n": SERP_N,
    }
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
            resp = await http.post(url, json=payload)
        out = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CN.ReadError("راه بیرون هاب پاسخ نداد؛ فردا دوباره خوانده میشود.") from exc
    if not isinstance(out, dict):
        raise CN.ReadError("جست‌وجوی هاب پاسخ نداد؛ فردا دوباره خوانده میشود.")
    entries = [e for e in out.get("entries") or [] if isinstance(e, dict)]
    raw = out.get("data")
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if out.get("outcome") != "ok":
        return [], entries
    return [r for r in data.get("results") or [] if isinstance(r, dict)], entries


SEARCH: Any = None  # tests put a fake `search(hub, company, q)` here


async def read_company(
    hub: Any,
    ctx: CN.ReadCtx,
    kws: list[dict[str, Any]],
    comps: list[dict[str, Any]],
    previous: dict[tuple[UUID, str], float],
) -> Day:
    """One company's reads. A reader that fails leaves its figures out (the next
    day reads again); nothing is estimated."""
    day = Day([], [], [])
    sc_token = None
    sc_site = str((ctx.config or {}).get("site_url") or "")
    if sc_site and ctx.secret:
        try:
            sc_token = await CN.google_token(ctx, CN.SC_SCOPE)
        except CN.ReadError as exc:
            log.info("search console unavailable for %s: %s", ctx.company, exc.reason_fa)
    sites = {f"c:{c['id']}": c["site"] for c in comps if c["site"]}
    for kw in kws[:MAX_KEYWORDS_PER_DAY]:
        if sc_token:
            try:
                got = await _sc_position(ctx, sc_site, sc_token, kw["phrase"])
                if got:
                    day.ranks.append((kw["id"], "search_console", got[0], got[1]))
            except CN.ReadError as exc:
                log.info("search console read failed: %s", exc.reason_fa)
        try:
            results, entries = await (SEARCH or search)(hub, ctx.company, kw["phrase"])
        except CN.ReadError:
            continue
        day.entries.extend(entries)
        if not results:
            continue
        found = serp_positions(results, {"us": kw["site"], **sites})
        pos, url = found.get("us", (None, None))
        day.ranks.append((kw["id"], "searxng", float(pos) if pos else None, url))
        for name, (p, _) in found.items():
            if name != "us":
                cid = UUID(name[2:])
                day.figures.append((cid, "serp_visible", 1.0, "searxng"))
                day.figures.append((cid, "serp_best", float(p), "searxng"))
    day.figures = _fold_serp(day.figures)
    for c in comps:
        day.figures.extend(await _competitor(ctx, c, previous))
    return day


def _fold_serp(figs: list[tuple[UUID, str, float, str]]) -> list[tuple[UUID, str, float, str]]:
    """Per competitor: in how many of our keywords' pages it showed (sum) and its best position (min)."""
    seen: dict[tuple[UUID, str], float] = {}
    for cid, key, v, _ in figs:
        if key == "serp_visible":
            seen[(cid, key)] = seen.get((cid, key), 0.0) + v
        else:
            seen[(cid, key)] = min(seen.get((cid, key), v), v)
    return [(cid, key, v, "searxng") for (cid, key), v in seen.items()]


async def _sc_position(
    ctx: CN.ReadCtx, site: str, token: str, phrase: str
) -> tuple[float, str | None] | None:
    body = {
        "startDate": (ctx.today - timedelta(days=SC_DAYS)).isoformat(),
        "endDate": (ctx.today - timedelta(days=1)).isoformat(),
        "dimensions": ["query", "page"],
        "dimensionFilterGroups": [
            {"filters": [{"dimension": "query", "operator": "equals", "expression": phrase}]}
        ],
        "rowLimit": 25,
    }
    ans = await ctx.call(
        "POST",
        CN.SC_QUERY.format(site=quote(site, safe="")),
        json_body=body,
        account=CN.bearer(token),
    )
    data = ans.json()
    if ans.status != 200 or not isinstance(data, dict):
        raise CN.ReadError(CN._http_reason(ans.status, "Search Console"))
    return weighted_position([r for r in data.get("rows") or [] if isinstance(r, dict)])


async def _competitor(
    ctx: CN.ReadCtx, c: dict[str, Any], previous: dict[tuple[UUID, str], float]
) -> list[tuple[UUID, str, float, str]]:
    out: list[tuple[UUID, str, float, str]] = []
    cid = c["id"]
    if c["site"]:
        try:
            pages, fresh = await _sitemap(ctx, c["site"])
            if pages:
                out.append((cid, "pages", float(pages), "sitemap"))
                out.append(
                    (
                        cid,
                        "new_pages",
                        float(new_pages(pages, previous.get((cid, "pages")), fresh)),
                        "sitemap",
                    )
                )
        except CN.ReadError as exc:
            log.info("competitor sitemap failed: %s", exc.reason_fa)
    if c["youtube"]:
        key = await CN.read_secret(ctx.hub.bao, ctx.company, "youtube")
        if key:
            try:
                out.extend(
                    (cid, k, v, "youtube") for k, v in await _youtube(ctx, c["youtube"], key)
                )
            except CN.ReadError as exc:
                log.info("competitor youtube failed: %s", exc.reason_fa)
    if c["telegram"]:
        token = await CN.read_secret(ctx.hub.bao, ctx.company, "telegram")
        if token:
            try:
                n = await _telegram(ctx, c["telegram"], token)
                if n is not None:
                    out.append((cid, "members", float(n), "telegram"))
            except CN.ReadError as exc:
                log.info("competitor telegram failed: %s", exc.reason_fa)
    return out


async def _sitemap(ctx: CN.ReadCtx, site: str) -> tuple[int, int]:
    """(pages, fresh pages) of a competitor's sitemap, an index's first children included."""
    for path in SITEMAP_PATHS:
        try:
            ans = await ctx.call("GET", f"https://{site}{path}")
        except CN.ReadError:
            continue
        if ans.status != 200 or "<loc" not in ans.body.lower():
            continue
        children, pages, fresh = parse_sitemap(ans.body, ctx.today)
        n_fresh = len(fresh)
        for child in children:
            if not same_site(child, site):
                continue  # a sitemap of another host is not read
            try:
                sub = await ctx.call("GET", child)
            except CN.ReadError:
                continue
            _, p, f = parse_sitemap(sub.body, ctx.today)
            pages, n_fresh = pages + p, n_fresh + len(f)
        return pages, n_fresh
    raise CN.ReadError("نقشه‌ی سایت رقیب خوانده نشد.")


async def _youtube(ctx: CN.ReadCtx, channel: str, key: str) -> list[tuple[str, float]]:
    q = urlencode({"part": "statistics", "id": channel})
    ans = await ctx.call("GET", f"{CN.YT}?{q}", account=CN.api_key(key))
    data = ans.json()
    if ans.status != 200 or not isinstance(data, dict):
        raise CN.ReadError(CN._http_reason(ans.status, "یوتیوب"))
    items = data.get("items") or []
    st = (items[0].get("statistics") or {}) if items and isinstance(items[0], dict) else {}
    out = []
    for src, name in (
        ("subscriberCount", "subscribers"),
        ("viewCount", "views"),
        ("videoCount", "videos"),
    ):
        v = CN._num(st.get(src))
        if v is not None:
            out.append((name, v))
    return out


async def _telegram(ctx: CN.ReadCtx, handle: str, token: str) -> int | None:
    acct = {
        "key": "growth-telegram",
        "site": "api.telegram.org",
        "secret": token,
        "inject": {"kind": "header", "name": "X-Hub-Unused"},
    }
    url = f"https://api.telegram.org/bot{token}/getChatMemberCount?" + urlencode(
        {"chat_id": "@" + handle}
    )
    ans = await ctx.call("GET", url, account=acct)
    data = ans.json()
    n = data.get("result") if isinstance(data, dict) and data.get("ok") else None
    return n if isinstance(n, int) else None


# --------------------------------------------------------------- the run --
async def store(tx: Tx, company_id: UUID, today: date, day: Day) -> None:
    for kid, source, pos, url in day.ranks:
        await tx.exec(
            """INSERT INTO growth.rank_daily (company_id, keyword_id, day, source, position, url)
               VALUES (:co, :k, :d, :s, :p, :u)
               ON CONFLICT (keyword_id, day, source)
               DO UPDATE SET position = EXCLUDED.position, url = EXCLUDED.url, at = now()""",
            co=company_id,
            k=kid,
            d=today,
            s=source,
            p=pos,
            u=url,
        )
    for cid, key, value, source in day.figures:
        await tx.exec(
            """INSERT INTO growth.competitor_daily (company_id, competitor_id, day, key, value, source)
               VALUES (:co, :c, :d, :k, :v, :s)
               ON CONFLICT (competitor_id, day, key)
               DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source, at = now()""",
            co=company_id,
            c=cid,
            d=today,
            k=key,
            v=value,
            s=source,
        )


async def raise_jump(
    hub: Any,
    tx: Tx,
    company: dict[str, Any],
    comp: dict[str, Any],
    today: date,
    key: str,
    before: float | None,
    after: float,
) -> str | None:
    """One work item for the growth department's manager, once per competitor, day and key."""
    from hq_api.domain import work as W

    jid = await tx.scalar(
        """INSERT INTO growth.competitor_jumps (company_id, competitor_id, day, key, before_value, after_value)
           VALUES (:co, :c, :d, :k, :b, :a) ON CONFLICT (competitor_id, day, key) DO NOTHING
           RETURNING id""",
        co=company["id"],
        c=comp["id"],
        d=today,
        k=key,
        b=before or 0,
        a=after,
    )
    if jid is None:
        return None
    title, brief = jump_text(comp["name_fa"], key, before, after)
    work: dict[str, Any] | None = None
    for dept in (GROWTH_DEPARTMENT, None):  # no such department: the CEO takes it
        try:
            async with tx.conn.begin_nested():
                work = await W.create(
                    tx,
                    SERVICE,
                    company_id=company["id"],
                    company_code=company["code"],
                    title=title,
                    brief=brief,
                    kind="one_off",
                    priority="P3",
                    department_code=dept,
                    budget=W.BudgetIn(tokens=60_000),
                )
            break
        except ApiError as exc:
            log.warning("competitor jump work refused", extra={"code": exc.code, "dept": dept})
    ref = work["ref"] if work else None
    if work:
        await tx.exec(
            "UPDATE growth.competitor_jumps SET work_id = :w WHERE id = :id", w=work["id"], id=jid
        )
    await events.emit(
        tx,
        company["code"],
        "competitor.jump",
        ref,
        {"competitor": str(comp["id"]), "name_fa": comp["name_fa"], "key": key, "value": after},
    )
    return str(ref) if ref else None


async def read_daily(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The daily read of every company that has keywords or competitors on, once a
    day each (rank rows are keyed by day). Nothing while the holding or the company
    is locked (these are outside calls)."""
    from hq_api.domain import egress as G
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        today = CN.owner_today(await owner_tz(tx), now)
        cos = await tx.all(
            """SELECT c.id, c.code, control.lock_state(c.id) AS lock FROM core.companies c
               WHERE c.status = 'active' AND (
                 EXISTS (SELECT 1 FROM growth.keywords k WHERE k.company_id = c.id AND k.state = 'on')
                 OR EXISTS (SELECT 1 FROM growth.competitors x WHERE x.company_id = c.id AND x.state = 'on'))
               ORDER BY c.code"""
        )
    out = {"companies": 0, "ranks": 0, "figures": 0, "jumps": 0}
    for co in cos:
        if co["lock"] is not None:
            continue
        async with hub.db.tx(ids) as tx:
            done = await tx.scalar(
                "SELECT EXISTS (SELECT 1 FROM growth.rank_daily WHERE company_id = :c AND day = :d) "
                "OR EXISTS (SELECT 1 FROM growth.competitor_daily WHERE company_id = :c AND day = :d)",
                c=co["id"],
                d=today,
            )
            if done:
                continue
            kws = [
                dict(r)
                for r in await tx.all(
                    "SELECT * FROM growth.keywords WHERE company_id = :c AND state = 'on' ORDER BY created_at",
                    c=co["id"],
                )
            ]
            comps = [
                dict(r)
                for r in await tx.all(
                    "SELECT * FROM growth.competitors WHERE company_id = :c AND state = 'on' ORDER BY created_at",
                    c=co["id"],
                )
            ]
            conn = await tx.first(
                "SELECT config FROM growth.connections WHERE company_id = :c AND kind = 'search_console'",
                c=co["id"],
            )
            prev = {
                (r["competitor_id"], r["key"]): float(r["value"])
                for r in await tx.all(
                    "SELECT DISTINCT ON (competitor_id, key) competitor_id, key, value FROM growth.competitor_daily "
                    "WHERE company_id = :c AND day < :d ORDER BY competitor_id, key, day DESC",
                    c=co["id"],
                    d=today,
                )
            }
        secret = await CN.read_secret(getattr(hub, "bao", None), co["code"], "search_console")
        ctx = CN.ReadCtx(
            hub=hub,
            tx_factory=lambda: hub.db.tx(ids),
            company_id=co["id"],
            company=co["code"],
            kind="search_console",
            config=dict((conn or {}).get("config") or {}),
            secret=secret,
            today=today,
            http=CN.http_for(hub),
        )
        day = await read_company(hub, ctx, kws, comps, prev)
        day.entries.extend(ctx.entries)
        async with hub.db.tx(ids) as tx:
            if day.entries:
                await G.record(
                    tx, company_id=co["id"], actor="seo-read", run_id=None, entries=day.entries
                )
            await store(tx, co["id"], today, day)
            by_id = {c["id"]: c for c in comps}
            s = hub.settings
            for cid, key, value, _ in day.figures:
                if jump_of(
                    key,
                    prev.get((cid, key)),
                    value,
                    pages=s.competitor_jump_pages,
                    pct=s.competitor_jump_pct,
                ):
                    out["jumps"] += (
                        1
                        if await raise_jump(
                            hub, tx, dict(co), by_id[cid], today, key, prev.get((cid, key)), value
                        )
                        else 0
                    )
            await events.emit(
                tx,
                co["code"],
                "rank.daily",
                None,
                {"day": today.isoformat(), "ranks": len(day.ranks), "figures": len(day.figures)},
            )
        out["companies"] += 1
        out["ranks"] += len(day.ranks)
        out["figures"] += len(day.figures)
    return out
