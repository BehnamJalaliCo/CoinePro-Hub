"""Ad budgets that stop by themselves (contract §31.6 ⟨1.13⟩).

`google_ads` and `meta_ads` are connection kinds (§29.12): their config is
non-secret (account ids), their secret lives in OpenBao
(kv/hq/growth/<company>/<kind>, key `secret`) and is never printed. Rule first,
model last: nothing here calls a model.

- The daily read (the connections' own tick, by code, through egress) puts each
  campaign's day into growth.ad_daily (spend, clicks, conversions, revenue, ROAS)
  and the campaigns' state into growth.ad_campaigns; the account's totals go to
  growth.metrics_daily (`ad_spend`, `ad_clicks`, `ad_conversions`, `ad_revenue`,
  `ad_roas`) so an automation can watch them. Revenue is the platform's reported
  conversion value; for the campaigns the owner names in the config
  (`hub_revenue_campaigns`) it is the hub's own revenue of the day (§19, the
  revenue radar's commission, times `usdt_rate`), shared among those campaigns
  by their spend so the day is counted once. A ROAS floor on such a campaign is
  judged only over days the radar has settled.
- The owner's rules (growth.ad_rules) are judged by code after each read: a
  daily cap on a campaign's spend, and a ROAS floor over a window once a minimum
  was spent. A tripped rule PAUSES the campaign through the platform's API
  (status only, reversible), writes the Audit, makes a work item for the
  company's growth lead and stays in the owner's weekly summary. Code here sends
  no other kind of change: a budget is never raised, never touched.
- Raising a cap (a looser rule) is 🔏 `ads.cap`; resuming a campaign is 🔏
  `ads.resume`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import quote, urlencode
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gate
from hq_api.principal import Principal
from hq_api.schemas import Model

log = logging.getLogger("hq_api.ads")

PLATFORMS = ("google_ads", "meta_ads")
Platform = Literal["google_ads", "meta_ads"]
SERVICE = Principal(kind="service", code="ads", role="service")
GOOGLE_ADS_VERSION = "v21"
META_VERSION = "v21.0"
GOOGLE_ADS_SITE = "googleads.googleapis.com"
META_SITE = "facebook.com"
READ_DAYS = 7  # what a daily read looks back over (the platforms revise late figures)
KEEP_DAYS = 120
RETRY_AFTER = timedelta(minutes=30)  # a pause that failed is tried again after this
GRACE = timedelta(hours=24)  # a campaign the owner resumed is not judged again at once
STALE_DAYS = 2  # figures older than this are not judged
JUDGE_DAYS = 90 + STALE_DAYS + 1  # the longest window a rule may have (window_days <= 90)
META_CONVERSIONS = (
    "purchase",
    "omni_purchase",
    "offsite_conversion.fb_pixel_purchase",
    "lead",
    "offsite_conversion.fb_pixel_lead",
    "complete_registration",
    "offsite_conversion.fb_pixel_complete_registration",
)
ACTION_FA = {"pause": "متوقف شود", "notify": "فقط خبر بدهد"}
REASON_FA = {"daily_cap": "سقف هزینه‌ی روزانه", "min_roas": "حداقل بازده تبلیغ"}


# ------------------------------------------------------------------ shapes --
class AdRuleIn(Model):
    platform: Platform
    scope: str = Field(
        default="account", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"
    )
    daily_cap: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    window_days: int = Field(default=7, ge=1, le=90)
    min_roas: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=4)
    min_spend_before_judging: Decimal = Field(
        default=Decimal(0), ge=0, max_digits=18, decimal_places=4
    )
    action: Literal["pause", "notify"] = "pause"
    state: Literal["on", "off"] = "on"
    note_fa: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _something_to_judge(self) -> AdRuleIn:
        if self.daily_cap is None and self.min_roas is None:
            raise ValueError("a daily_cap or a min_roas")
        return self


class AdRuleEdit(Model):
    scope: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"
    )
    daily_cap: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    window_days: int | None = Field(default=None, ge=1, le=90)
    min_roas: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=4)
    min_spend_before_judging: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    action: Literal["pause", "notify"] | None = None
    state: Literal["on", "off"] | None = None
    note_fa: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _no_null_where_the_rule_needs_a_value(self) -> AdRuleEdit:
        # Left out means unchanged; an explicit null is only for the cap, the floor
        # and the note (the rest are NOT NULL in growth.ad_rules).
        nulls = sorted(
            k
            for k in ("scope", "window_days", "min_spend_before_judging", "action", "state")
            if k in self.model_fields_set and getattr(self, k) is None
        )
        if nulls:
            raise ValueError(f"may not be null: {', '.join(nulls)}")
        return self


class AdRule(BaseModel):
    id: str
    company: str
    platform: Platform
    scope: str
    daily_cap: float | None
    window_days: int
    min_roas: float | None
    min_spend_before_judging: float
    action: Literal["pause", "notify"]
    state: Literal["on", "off"]
    note_fa: str | None
    summary_fa: str
    created_at: datetime
    updated_at: datetime


class AdDay(BaseModel):
    day: date
    spend: float
    clicks: int
    conversions: float
    revenue: float
    roas: float | None


class AdTotals(BaseModel):
    spend: float
    clicks: int
    conversions: float
    revenue: float
    roas: float | None


class AdCampaign(BaseModel):
    platform: Platform
    campaign_id: str
    name: str
    status: Literal["active", "paused", "removed"]
    paused_by: Literal["rule", "owner", "platform"] | None
    paused_at: datetime | None
    paused_reason_fa: str | None
    totals: AdTotals
    days: list[AdDay]


class AdAccount(BaseModel):
    platform: Platform
    label_fa: str
    state: Literal["not_connected", "connected", "error"]
    secret: Literal["set", "missing"]
    missing_fa: list[str]
    last_read_at: datetime | None
    last_error_fa: str | None


class AdTrip(BaseModel):
    day: date
    platform: Platform
    campaign_id: str
    reason: str
    action: str
    outcome: Literal["paused", "notified", "failed"]
    detail_fa: str
    at: datetime


class Ads(BaseModel):
    company: str
    accounts: list[AdAccount]
    campaigns: list[AdCampaign]
    trips: list[AdTrip]


# ------------------------------------------------------------- the rules --
def roas_of(revenue: Any, spend: Any) -> float | None:
    s = float(spend or 0)
    return round(float(revenue or 0) / s, 4) if s > 0 else None


def num(v: Any) -> str:
    """A figure for a Persian sentence (Latin digits, no trailing zeros)."""
    f = float(v)
    return f"{f:.2f}".rstrip("0").rstrip(".") if f != int(f) else str(int(f))


@dataclass(frozen=True)
class Trip:
    reason: Literal["daily_cap", "min_roas"]
    day: date
    detail_fa: str


def judge(rule: dict[str, Any], days: list[dict[str, Any]], today: date) -> Trip | None:
    """One rule over one campaign's days (code, no model): the latest day's
    spend over the daily cap, or the ROAS of the window under the floor once the
    window spent the minimum. Figures older than STALE_DAYS are not judged."""
    rows = sorted((d for d in days if d["day"] <= today), key=lambda d: d["day"])
    if not rows:
        return None
    last = rows[-1]
    if (today - last["day"]).days > STALE_DAYS:
        return None
    cap = rule.get("daily_cap")
    if cap is not None and float(last["spend"]) > float(cap):
        return Trip(
            "daily_cap",
            last["day"],
            f"هزینه‌ی روز {last['day']} به {num(last['spend'])} رسید و از سقف روزانه‌ی {num(cap)} گذشت.",
        )
    floor = rule.get("min_roas")
    # A day whose revenue is not known yet (None: the hub's own revenue before
    # the radar settled the day) is left out; the window ends at the last day
    # that has one, so unsettled spend never reads as revenue 0.
    known = [d for d in rows if d["revenue"] is not None]
    end = known[-1]["day"] if known else None
    if floor is not None and end is not None and (today - end).days <= STALE_DAYS:
        start = end - timedelta(days=int(rule["window_days"]) - 1)
        win = [d for d in known if d["day"] >= start]
        spend = sum(float(d["spend"]) for d in win)
        revenue = sum(float(d["revenue"]) for d in win)
        if spend > 0 and spend >= float(rule.get("min_spend_before_judging") or 0):
            r = revenue / spend
            if r < float(floor):
                return Trip(
                    "min_roas",
                    end,
                    f"بازده تبلیغ در {int(rule['window_days'])} روز تا {end} برابر {num(r)} بود، "
                    f"کمتر از حداقل {num(floor)}؛ هزینه‌ی این مدت {num(spend)}.",
                )
    return None


def loosens(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """The new rule lets more money through than the old one (a higher cap, a
    lower ROAS floor, a larger minimum before judging, a longer window that
    dilutes the figure, only telling instead of pausing, the rule switched off,
    a cap or a floor taken away, the guard moved off a campaign): 🔏 `ads.cap`.
    Tightening needs none."""

    def up(a: Any, b: Any) -> bool:  # b is looser than a, for a cap-like number
        if a is None:
            return False
        return b is None or float(b) > float(a)

    def down(a: Any, b: Any) -> bool:  # b is looser than a, for a floor-like number
        if a is None:
            return False
        return b is None or float(b) < float(a)

    return (
        up(old["daily_cap"], new["daily_cap"])
        or down(old["min_roas"], new["min_roas"])
        or float(new["min_spend_before_judging"]) > float(old["min_spend_before_judging"])
        or int(new["window_days"]) > int(old["window_days"])
        or (old["action"] == "pause" and new["action"] == "notify")
        or (old["state"] == "on" and new["state"] == "off")
        # fewer campaigns covered, or the guarded campaign is no longer guarded
        or (old["scope"] != new["scope"] and new["scope"] != "account")
    )


def summary_fa(r: dict[str, Any]) -> str:
    parts = []
    if r["daily_cap"] is not None:
        parts.append(f"سقف هزینه‌ی روزانه {num(r['daily_cap'])}")
    if r["min_roas"] is not None:
        parts.append(
            f"حداقل بازده {num(r['min_roas'])} در {int(r['window_days'])} روز "
            f"(پس از خرج دست‌کم {num(r['min_spend_before_judging'])})"
        )
    where = "همه‌ی کمپین‌ها" if r["scope"] == "account" else f"کمپین {r['scope']}"
    return f"{where}: {'، '.join(parts)}؛ اگر رد شد {ACTION_FA[r['action']]}."


def render_rule(r: dict[str, Any], company: str) -> AdRule:
    def f(v: Any) -> float | None:
        return None if v is None else float(v)

    return AdRule(
        id=str(r["id"]),
        company=company,
        platform=r["platform"],
        scope=r["scope"],
        daily_cap=f(r["daily_cap"]),
        window_days=r["window_days"],
        min_roas=f(r["min_roas"]),
        min_spend_before_judging=float(r["min_spend_before_judging"]),
        action=r["action"],
        state=r["state"],
        note_fa=r["note_fa"],
        summary_fa=summary_fa(r),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


# ------------------------------------------------------------ the platforms --
@dataclass
class DayRow:
    campaign_id: str
    day: date
    spend: float
    clicks: int
    conversions: float
    revenue: float


@dataclass
class CampaignInfo:
    campaign_id: str
    name: str
    status: str  # active | paused | removed


def _digits(v: Any) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def google_secret(secret: str | None) -> dict[str, str]:
    """The four values of the secret text (JSON): clientId, clientSecret,
    refreshToken, developerToken (the snake_case spellings are accepted too)."""
    try:
        data = json.loads(secret or "")
    except ValueError:
        data = None
    out: dict[str, str] = {}
    for camel, snake in (
        ("clientId", "client_id"), ("clientSecret", "client_secret"),
        ("refreshToken", "refresh_token"), ("developerToken", "developer_token"),
    ):  # fmt: skip
        v = data.get(camel) or data.get(snake) if isinstance(data, dict) else None
        if not str(v or "").strip():
            raise CN.ReadError(
                "رمز اتصال تبلیغات گوگل کامل نیست؛ چهار مقدار لازم را طبق راهنما "
                "به‌صورت یک متن JSON بگذار."
            )
        out[snake] = str(v).strip()
    return out


async def google_session(ctx: CN.ReadCtx) -> tuple[dict[str, Any], dict[str, str], str]:
    """(the bearer account, the request headers, the customer id): the refresh
    token is exchanged for an access token at Google, through egress."""
    sec = google_secret(ctx.secret)
    cid = _digits(ctx.config.get("customer_id"))
    form = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": sec["client_id"],
            "client_secret": sec["client_secret"],
            "refresh_token": sec["refresh_token"],
        }
    )
    ans = await ctx.call(
        "POST",
        CN.TOKEN_URI,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=form,
    )
    data = ans.json()
    token = data.get("access_token") if isinstance(data, dict) else None
    if ans.status != 200 or not isinstance(token, str) or not token:
        raise CN.ReadError(CN._http_reason(401 if ans.status in (400, 401) else ans.status, "گوگل"))
    headers = {"developer-token": sec["developer_token"]}
    if login := _digits(ctx.config.get("login_customer_id")):
        headers["login-customer-id"] = login
    acct = {
        "key": "growth-google-ads",
        "site": GOOGLE_ADS_SITE,
        "secret": token,
        "inject": {"kind": "bearer"},
    }
    return acct, headers, cid


def _gaql_status(s: Any) -> str:
    return {"ENABLED": "active", "PAUSED": "paused", "REMOVED": "removed"}.get(str(s), "active")


def _stream_results(data: Any) -> list[dict[str, Any]]:
    """searchStream answers a list of batches, each with `results`."""
    batches = data if isinstance(data, list) else [data]
    out: list[dict[str, Any]] = []
    for b in batches:
        if isinstance(b, dict):
            out += [r for r in b.get("results") or [] if isinstance(r, dict)]
    return out


async def read_google_ads(ctx: CN.ReadCtx) -> tuple[list[DayRow], list[CampaignInfo]]:
    acct, headers, cid = await google_session(ctx)
    url = f"https://{GOOGLE_ADS_SITE}/{GOOGLE_ADS_VERSION}/customers/{cid}/googleAds:searchStream"
    since = ctx.today - timedelta(days=READ_DAYS - 1)
    daily_q = (
        "SELECT campaign.id, campaign.name, campaign.status, segments.date, metrics.cost_micros, "  # noqa: S608 - GAQL with our own dates, not SQL
        "metrics.clicks, metrics.conversions, metrics.conversions_value FROM campaign "
        f"WHERE segments.date BETWEEN '{since.isoformat()}' AND '{ctx.today.isoformat()}' "
        "AND campaign.status != 'REMOVED'"
    )
    ans = await ctx.call("POST", url, json_body={"query": daily_q}, headers=headers, account=acct)
    data = ans.json()
    if ans.status != 200 or data is None:
        raise CN.ReadError(CN._http_reason(ans.status, "Google Ads"))
    rows: list[DayRow] = []
    for r in _stream_results(data):
        c, m = r.get("campaign") or {}, r.get("metrics") or {}
        try:
            day = date.fromisoformat(str((r.get("segments") or {}).get("date")))
        except ValueError:
            continue
        rows.append(
            DayRow(
                str(c.get("id")),
                day,
                round((CN._num(m.get("costMicros")) or 0) / 1_000_000, 4),
                int(CN._num(m.get("clicks")) or 0),
                CN._num(m.get("conversions")) or 0.0,
                CN._num(m.get("conversionsValue")) or 0.0,
            )
        )
    state_q = (
        "SELECT campaign.id, campaign.name, campaign.status FROM campaign "
        "WHERE campaign.status != 'REMOVED'"
    )
    ans = await ctx.call("POST", url, json_body={"query": state_q}, headers=headers, account=acct)
    data = ans.json()
    if ans.status != 200 or data is None:
        raise CN.ReadError(CN._http_reason(ans.status, "Google Ads"))
    camps = [
        CampaignInfo(str(c.get("id")), str(c.get("name") or ""), _gaql_status(c.get("status")))
        for c in (r.get("campaign") or {} for r in _stream_results(data))
        if c.get("id")
    ]
    return rows, camps


def meta_account(secret: str | None) -> dict[str, Any]:
    if not secret:
        raise CN.ReadError("توکن Meta Ads گذاشته نشده است؛ طبق راهنما توکن را در اپ بگذار.")
    return {
        "key": "growth-meta-ads",
        "site": META_SITE,
        "secret": secret,
        "inject": {"kind": "bearer"},
    }


def _meta_status(s: Any) -> str:
    s = str(s or "").upper()
    if s in ("DELETED", "ARCHIVED"):
        return "removed"
    return "paused" if s in ("PAUSED", "CAMPAIGN_PAUSED") else "active"


def _sum_actions(items: Any, wanted: set[str]) -> float:
    total = 0.0
    for a in items or []:
        if isinstance(a, dict) and str(a.get("action_type")) in wanted:
            total += CN._num(a.get("value")) or 0.0
    return total


async def _meta_pages(ctx: CN.ReadCtx, url: str, acct: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(10):  # ten pages at most
        ans = await ctx.call("GET", url, account=acct)
        data = ans.json()
        if ans.status != 200 or not isinstance(data, dict):
            raise CN.ReadError(CN._http_reason(ans.status, "Meta Ads"))
        out += [r for r in data.get("data") or [] if isinstance(r, dict)]
        nxt = ((data.get("paging") or {}).get("next")) or ""
        if not str(nxt).startswith("https://graph.facebook.com/"):
            break
        url = str(nxt)
    return out


async def read_meta_ads(ctx: CN.ReadCtx) -> tuple[list[DayRow], list[CampaignInfo]]:
    acct = meta_account(ctx.secret)
    aid = _digits(ctx.config.get("account_id"))
    base = f"https://graph.facebook.com/{META_VERSION}/act_{aid}"
    since = ctx.today - timedelta(days=READ_DAYS - 1)
    q = urlencode(
        {
            "level": "campaign",
            "time_increment": 1,
            "time_range": json.dumps({"since": since.isoformat(), "until": ctx.today.isoformat()}),
            "fields": "campaign_id,campaign_name,spend,clicks,actions,action_values,date_start",
            "limit": 500,
        }
    )
    wanted = set(ctx.config.get("conversion_actions") or META_CONVERSIONS)
    rows: list[DayRow] = []
    for r in await _meta_pages(ctx, f"{base}/insights?{q}", acct):
        try:
            day = date.fromisoformat(str(r.get("date_start")))
        except ValueError:
            continue
        rows.append(
            DayRow(
                str(r.get("campaign_id")),
                day,
                CN._num(r.get("spend")) or 0.0,
                int(CN._num(r.get("clicks")) or 0),
                _sum_actions(r.get("actions"), wanted),
                _sum_actions(r.get("action_values"), wanted),
            )
        )
    q = urlencode({"fields": "id,name,effective_status", "limit": 200})
    camps = [
        CampaignInfo(
            str(c["id"]), str(c.get("name") or ""), _meta_status(c.get("effective_status"))
        )
        for c in await _meta_pages(ctx, f"{base}/campaigns?{q}", acct)
        if c.get("id")
    ]
    return rows, camps


async def set_status(ctx: CN.ReadCtx, campaign_id: str, *, paused: bool) -> None:
    """The one change code ever sends to an ad platform: a campaign's status
    (PAUSED or back to ENABLED/ACTIVE). Never a budget, a bid or a target."""
    cid_ok = campaign_id.isdigit()
    if not cid_ok:
        raise CN.ReadError("شناسه‌ی کمپین درست نیست.")
    if ctx.kind == "google_ads":
        acct, headers, cust = await google_session(ctx)
        url = f"https://{GOOGLE_ADS_SITE}/{GOOGLE_ADS_VERSION}/customers/{cust}/campaigns:mutate"
        body = {
            "operations": [
                {
                    "updateMask": "status",
                    "update": {
                        "resourceName": f"customers/{cust}/campaigns/{campaign_id}",
                        "status": "PAUSED" if paused else "ENABLED",
                    },
                }
            ]
        }
        ans = await ctx.call("POST", url, json_body=body, headers=headers, account=acct)
        if ans.status != 200:
            raise CN.ReadError(CN._http_reason(ans.status, "Google Ads"))
        return
    acct = meta_account(ctx.secret)
    url = f"https://graph.facebook.com/{META_VERSION}/{quote(campaign_id, safe='')}"
    form = urlencode({"status": "PAUSED" if paused else "ACTIVE"})
    ans = await ctx.call(
        "POST",
        url,
        body=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        account=acct,
    )
    data = ans.json()
    if ans.status != 200 or not (isinstance(data, dict) and data.get("success") is True):
        raise CN.ReadError(CN._http_reason(ans.status if ans.status != 200 else 502, "Meta Ads"))


# ------------------------------------------------------------- the daily read --
HubKey = tuple[str, str, date]  # (platform, campaign_id, day)
HubConfs = dict[str, tuple[set[str], float]]  # platform -> (hub campaigns, usdt_rate)


def hub_conf(config: dict[str, Any]) -> tuple[set[str], float]:
    """A connection's hub campaigns (`hub_revenue_campaigns`) and its `usdt_rate`
    (the ad account's currency per USDT; 1 when unset or not a positive number)."""
    rate = CN._num(config.get("usdt_rate"))
    return (
        {str(c) for c in config.get("hub_revenue_campaigns") or []},
        rate if rate is not None and rate > 0 else 1.0,
    )


async def hub_confs(
    tx: Tx, company_id: UUID, own: tuple[str, dict[str, Any]] | None = None
) -> HubConfs:
    """The company's ad connections that name hub campaigns (`own` is the config
    of the connection being read, in place of the stored one)."""
    rows = await tx.all(
        "SELECT kind, config FROM growth.connections WHERE company_id = :co AND kind = ANY(:k)",
        co=company_id,
        k=list(PLATFORMS),
    )
    confs = {str(r["kind"]): hub_conf(dict(r["config"] or {})) for r in rows}
    if own is not None:
        confs[own[0]] = hub_conf(own[1])
    return {k: v for k, v in confs.items() if v[0]}


async def hub_spend(
    tx: Tx, company_id: UUID, confs: HubConfs, since: date, skip: str | None = None
) -> dict[HubKey, float]:
    """The stored spend of every hub campaign from `since` on (`skip`: a platform
    whose rows the caller has in hand)."""
    out: dict[HubKey, float] = {}
    for kind, (camps, _rate) in confs.items():
        if kind == skip:
            continue
        for r in await tx.all(
            """SELECT campaign_id, day, spend FROM growth.ad_daily WHERE company_id = :co
                 AND platform = :p AND campaign_id = ANY(:c) AND day >= :since""",
            co=company_id,
            p=kind,
            c=sorted(camps),
            since=since,
        ):
            out[(kind, str(r["campaign_id"]), r["day"])] = float(r["spend"])
    return out


async def hub_credit(
    tx: Tx, company_id: UUID, confs: HubConfs, spend: dict[HubKey, float]
) -> dict[HubKey, tuple[float, bool]]:
    """The hub's own revenue of each day (§19, the revenue radar's commission),
    credited once: shared among the hub campaigns of that day, on both ad
    connections, by their spend in USDT (equally when none spent), each share in
    its account's currency. The flag says the radar has settled the day (its
    rows are there and complete); until then the figure is partial or nothing
    (LBank settles a day at 00:00 UTC+8 and the radar pulls it the next morning)."""
    days = sorted({k[2] for k in spend})
    if not days:
        return {}
    radar = {
        r["day"]: (float(r["usdt"] or 0), bool(r["settled"]))
        for r in await tx.all(
            """SELECT day, sum(commission_usdt) AS usdt, bool_and(complete) AS settled
               FROM revenue.days WHERE company_id = :co AND day = ANY(:d) GROUP BY day""",
            co=company_id,
            d=days,
        )
    }
    usdt_spend = {k: s / confs[k[0]][1] for k, s in spend.items()}
    total: dict[date, float] = {}
    count: dict[date, int] = {}
    for k, v in usdt_spend.items():
        total[k[2]] = total.get(k[2], 0.0) + v
        count[k[2]] = count.get(k[2], 0) + 1
    out: dict[HubKey, tuple[float, bool]] = {}
    for k, v in usdt_spend.items():
        usdt, settled = radar.get(k[2], (0.0, False))
        share = v / total[k[2]] if total[k[2]] > 0 else 1 / count[k[2]]
        out[k] = (round(usdt * share * confs[k[0]][1], 4), settled)
    return out


async def store_read(
    ctx: CN.ReadCtx, rows: list[DayRow], camps: list[CampaignInfo]
) -> list[CN.Figure]:
    """growth.ad_daily and growth.ad_campaigns from one read; the account's
    totals back as the figures of growth.metrics_daily."""
    hub_camps = hub_conf(ctx.config)[0]
    async with ctx.tx_factory() as tx:
        mine: dict[HubKey, float] = {
            (ctx.kind, r.campaign_id, r.day): r.spend for r in rows if r.campaign_id in hub_camps
        }
        if mine:
            confs = await hub_confs(tx, ctx.company_id, (ctx.kind, ctx.config))
            days = {k[2] for k in mine}
            stored = await hub_spend(tx, ctx.company_id, confs, min(days), skip=ctx.kind)
            others = {k: v for k, v in stored.items() if k[2] in days}
            credit = await hub_credit(tx, ctx.company_id, confs, mine | others)
            for r in rows:
                if (got := credit.get((ctx.kind, r.campaign_id, r.day))) is not None:
                    r.revenue = got[0]
            for (kind, cid, day), (revenue, _settled) in credit.items():
                if kind == ctx.kind:
                    continue
                # the other connection's hub campaigns: their share of the same days
                await tx.exec(
                    """UPDATE growth.ad_daily SET revenue = :r, roas = :roas, at = now()
                       WHERE company_id = :co AND platform = :p AND campaign_id = :c AND day = :d""",
                    co=ctx.company_id,
                    p=kind,
                    c=cid,
                    d=day,
                    r=revenue,
                    roas=roas_of(revenue, others[(kind, cid, day)]),
                )
        for r in rows:
            await tx.exec(
                """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend, clicks,
                       conversions, revenue, roas)
                   VALUES (:co, :p, :c, :d, :s, :k, :v, :r, :roas)
                   ON CONFLICT (company_id, platform, campaign_id, day) DO UPDATE SET
                       spend = EXCLUDED.spend, clicks = EXCLUDED.clicks,
                       conversions = EXCLUDED.conversions, revenue = EXCLUDED.revenue,
                       roas = EXCLUDED.roas, at = now()""",
                co=ctx.company_id,
                p=ctx.kind,
                c=r.campaign_id,
                d=r.day,
                s=r.spend,
                k=r.clicks,
                v=r.conversions,
                r=r.revenue,
                roas=roas_of(r.revenue, r.spend),
            )
        seen = {c.campaign_id for c in camps} | {r.campaign_id for r in rows}
        names = {c.campaign_id: c for c in camps}
        for cid in sorted(seen):
            info = names.get(cid)
            status = info.status if info else "active"
            await tx.exec(
                """INSERT INTO growth.ad_campaigns (company_id, platform, campaign_id, name, status,
                       paused_by, paused_at)
                   VALUES (:co, :p, :c, :n, :st, CASE WHEN :st = 'paused' THEN 'platform' END,
                           CASE WHEN :st = 'paused' THEN now() END)
                   ON CONFLICT (company_id, platform, campaign_id) DO UPDATE SET
                       name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name
                                   ELSE growth.ad_campaigns.name END,
                       status = EXCLUDED.status,
                       paused_by = CASE WHEN EXCLUDED.status = 'active' THEN NULL
                                        WHEN growth.ad_campaigns.status = 'paused'
                                             THEN growth.ad_campaigns.paused_by
                                        WHEN EXCLUDED.status = 'paused' THEN 'platform'
                                        ELSE growth.ad_campaigns.paused_by END,
                       paused_at = CASE WHEN EXCLUDED.status = 'active' THEN NULL
                                        WHEN growth.ad_campaigns.status = 'paused'
                                             THEN growth.ad_campaigns.paused_at
                                        WHEN EXCLUDED.status = 'paused' THEN now()
                                        ELSE growth.ad_campaigns.paused_at END,
                       paused_reason_fa = CASE WHEN EXCLUDED.status = 'active' THEN NULL
                                               ELSE growth.ad_campaigns.paused_reason_fa END,
                       seen_at = now(), updated_at = now()""",
                co=ctx.company_id,
                p=ctx.kind,
                c=cid,
                n=(info.name if info else "")[:300],
                st=status,
            )
        await tx.exec(
            "DELETE FROM growth.ad_daily WHERE company_id = :co AND day < :d",
            co=ctx.company_id,
            d=ctx.today - timedelta(days=KEEP_DAYS),
        )
    by_day: dict[date, list[DayRow]] = {}
    for r in rows:
        by_day.setdefault(r.day, []).append(r)
    figures: list[CN.Figure] = []
    subject = _digits(ctx.config.get("customer_id") or ctx.config.get("account_id"))
    for day, items in sorted(by_day.items()):
        spend = sum(i.spend for i in items)
        revenue = sum(i.revenue for i in items)
        figures += [
            CN.Figure(day, "ad_spend", round(spend, 4), subject, ctx.kind),
            CN.Figure(day, "ad_clicks", float(sum(i.clicks for i in items)), subject, ctx.kind),
            CN.Figure(
                day,
                "ad_conversions",
                round(sum(i.conversions for i in items), 4),
                subject,
                ctx.kind,
            ),
            CN.Figure(day, "ad_revenue", round(revenue, 4), subject, ctx.kind),
        ]
        if (ratio := roas_of(revenue, spend)) is not None:
            figures.append(CN.Figure(day, "ad_roas", ratio, subject, ctx.kind))
    return figures


async def read_ads(ctx: CN.ReadCtx) -> list[CN.Figure]:
    """The connection reader of both platforms (registered in CN.READERS)."""
    read = read_google_ads if ctx.kind == "google_ads" else read_meta_ads
    rows, camps = await read(ctx)
    return await store_read(ctx, rows, camps)


# ---------------------------------------------------------------- the tick --
async def _api_ctx(hub: Any, company_id: UUID, code: str, kind: str, today: date) -> CN.ReadCtx:
    ids = await hub.companies.ids()

    def factory() -> Any:
        return hub.db.tx(ids)

    async with factory() as tx:
        row = await tx.first(
            "SELECT config FROM growth.connections WHERE company_id = :co AND kind = :k",
            co=company_id,
            k=kind,
        )
    secret = await CN.read_secret(getattr(hub, "bao", None), code, kind)
    if row is None or not secret:
        raise CN.ReadError("اتصال تبلیغ کامل نیست؛ رمز یا شناسه‌ی حساب را در اپ بگذار.")
    return CN.ReadCtx(
        hub=hub,
        tx_factory=factory,
        company_id=company_id,
        company=code,
        kind=kind,
        config=dict(row["config"] or {}),
        secret=secret,
        today=today,
        http=CN.http_for(hub, "A2"),
    )


async def _record_egress(hub: Any, company_id: UUID, ctx: CN.ReadCtx) -> None:
    if not ctx.entries:
        return
    from hq_api.domain import egress as G

    async with hub.db.tx(await hub.companies.ids()) as tx:
        await G.record(tx, company_id=company_id, actor=CN.ACTOR, run_id=None, entries=ctx.entries)


async def growth_lead(tx: Tx, company_id: UUID) -> str | None:
    """The company's growth lead: its content lead, else its CEO."""
    from hq_api.domain import groups

    held = await groups.seat_holders(tx, company_id, ["media_director", "ceo"])
    return held.get("media_director") or held.get("ceo")


async def tell_lead(
    tx: Tx, company: dict[str, Any], title_fa: str, brief_fa: str, ref: str
) -> UUID | None:
    """A work item for the company's growth lead (best effort: a refused item
    never stops the pause that already happened)."""
    from hq_api.domain import work as W
    from hq_api.errors import ApiError

    try:
        async with tx.conn.begin_nested():
            w = await W.create(
                tx,
                SERVICE,
                company_id=company["id"],
                company_code=company["code"],
                title=title_fa[:300],
                brief=brief_fa[:5000],
                kind="one_off",
                priority="P2",
                assignee_code=await growth_lead(tx, company["id"]),
            )
        return UUID(str(w["id"]))
    except ApiError as exc:
        log.warning("ad trip work refused", extra={"code": exc.code, "ref": ref})
        return None


async def evaluate_due(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """After the reads: every rule that is on, over its campaigns. Each trip
    once per rule, campaign and day; a pause that failed is retried after 30
    minutes. Nothing while the holding or the company is locked."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"checked": 0, "tripped": 0, "paused": 0, "notified": 0, "failed": 0}
    ids = await hub.companies.ids()
    plans: list[tuple[dict[str, Any], dict[str, Any], Trip, bool]] = []
    hubs: dict[UUID, tuple[HubConfs, dict[HubKey, tuple[float, bool]]]] = {}
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        today = CN.owner_today(await owner_tz(tx), now)
        since = today - timedelta(days=JUDGE_DAYS)
        rules = await tx.all(
            """SELECT r.*, c.code AS company_code, c.name_fa AS company_name FROM growth.ad_rules r
               JOIN core.companies c ON c.id = r.company_id
               WHERE r.state = 'on' AND c.status = 'active' ORDER BY c.code, r.created_at"""
        )
        for rule in rules:
            if await gate.automation_lock(tx, rule["company_id"]) is not None:
                continue
            camps = await tx.all(
                """SELECT * FROM growth.ad_campaigns WHERE company_id = :co AND platform = :p
                     AND status = 'active' AND (:scope = 'account' OR campaign_id = :scope)
                     AND (resumed_at IS NULL OR resumed_at < :grace) ORDER BY campaign_id""",
                co=rule["company_id"],
                p=rule["platform"],
                scope=rule["scope"],
                grace=now - GRACE,
            )
            co = rule["company_id"]
            if co not in hubs:
                confs = await hub_confs(tx, co)
                spent = await hub_spend(tx, co, confs, since)
                hubs[co] = (confs, await hub_credit(tx, co, confs, spent))
            confs, credit = hubs[co]
            hub_camps = confs.get(rule["platform"], (set(), 1.0))[0]
            for camp in camps:
                out["checked"] += 1
                days = await tx.all(
                    """SELECT day, spend, revenue FROM growth.ad_daily
                       WHERE company_id = :co AND platform = :p AND campaign_id = :c AND day > :since
                       ORDER BY day""",
                    co=co,
                    p=rule["platform"],
                    c=camp["campaign_id"],
                    # the window may end up to STALE_DAYS early (hub revenue not settled yet)
                    since=today - timedelta(days=int(rule["window_days"]) + STALE_DAYS + 1),
                )
                if camp["campaign_id"] in hub_camps:
                    # the hub's own revenue as the radar has it now (the stored
                    # figure was taken at the read, often before the day settled);
                    # None until the day is settled
                    for d in days:
                        got = credit.get((rule["platform"], camp["campaign_id"], d["day"]))
                        d["revenue"] = got[0] if got is not None and got[1] else None
                trip = judge(rule, days, today)
                if trip is None:
                    continue
                before = await tx.first(
                    """SELECT outcome, at FROM growth.ad_trips
                       WHERE rule_id = :r AND campaign_id = :c AND day = :d""",
                    r=rule["id"],
                    c=camp["campaign_id"],
                    d=trip.day,
                )
                if before is not None and (
                    before["outcome"] != "failed" or before["at"] > now - RETRY_AFTER
                ):
                    continue
                plans.append((rule, camp, trip, before is not None))
    for rule, camp, trip, retry in plans:
        out["tripped"] += 1
        acted = await _act(hub, rule, camp, trip, today, retry)
        out[acted] += 1
    return out


async def _act(
    hub: Any, rule: dict[str, Any], camp: dict[str, Any], trip: Trip, today: date, retry: bool
) -> str:
    """One trip: pause through the platform's API (or only tell), then the
    record: the trip, the campaign, the Audit, the event, the lead's work item."""
    outcome, why = "notified", ""
    egress_ctx: CN.ReadCtx | None = None
    if rule["action"] == "pause":
        try:
            egress_ctx = await _api_ctx(
                hub, rule["company_id"], rule["company_code"], rule["platform"], today
            )
            await set_status(egress_ctx, camp["campaign_id"], paused=True)
            outcome = "paused"
        except CN.ReadError as exc:
            outcome, why = "failed", exc.reason_fa
        except Exception:
            log.warning("ad pause failed", extra={"platform": rule["platform"]}, exc_info=True)
            outcome, why = "failed", "درخواست توقف کمپین به پلتفرم نرسید."
    if egress_ctx is not None:
        await _record_egress(hub, rule["company_id"], egress_ctx)
    name = camp["name"] or camp["campaign_id"]
    label = {"paused": "متوقف شد", "notified": "فقط خبر داده شد", "failed": "توقفش انجام نشد"}[
        outcome
    ]
    detail = f"کمپین «{name}» {label}. {trip.detail_fa}" + (f" دلیل: {why}" if why else "")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        company = {"id": rule["company_id"], "code": rule["company_code"]}
        work_id = None
        if not retry or outcome != "failed":
            work_id = await tell_lead(
                tx,
                company,
                f"تبلیغ {label}: {name}",
                f"{detail}\nقاعده: {summary_fa(rule)}\n"
                + (
                    "برای ادامه‌ی کمپین باید مدیر کل در اپ آن را روشن کند."
                    if outcome == "paused"
                    else ""
                ),
                str(rule["id"]),
            )
        await tx.exec(
            """INSERT INTO growth.ad_trips (company_id, rule_id, platform, campaign_id, day, reason,
                   action, outcome, detail_fa, work_id)
               VALUES (:co, :r, :p, :c, :d, :why, :a, :o, :det, :w)
               ON CONFLICT (rule_id, campaign_id, day) DO UPDATE SET
                   outcome = EXCLUDED.outcome, detail_fa = EXCLUDED.detail_fa,
                   work_id = COALESCE(EXCLUDED.work_id, growth.ad_trips.work_id)""",
            co=rule["company_id"],
            r=rule["id"],
            p=rule["platform"],
            c=camp["campaign_id"],
            d=trip.day,
            why=trip.reason,
            a=rule["action"],
            o=outcome,
            det=detail[:500],
            w=work_id,
        )
        if outcome == "paused":
            await tx.exec(
                """UPDATE growth.ad_campaigns SET status = 'paused', paused_by = 'rule',
                       paused_rule_id = :r, paused_at = now(), paused_reason_fa = :why, updated_at = now()
                   WHERE id = :id""",
                id=camp["id"],
                r=rule["id"],
                why=trip.detail_fa[:500],
            )
        await audit.record(
            tx,
            SERVICE,
            company_id=rule["company_id"],
            action="ads.trip",
            action_class="A2" if outcome == "paused" else "A1",
            target_kind="ad_campaign",
            target_ref=f"{rule['platform']}:{camp['campaign_id']}",
            summary=f"{trip.reason}: {outcome}",
        )
        if outcome == "paused":
            await events.emit(
                tx,
                rule["company_code"],
                "ad.paused",
                camp["campaign_id"],
                {
                    "platform": rule["platform"],
                    "campaign": camp["campaign_id"],
                    "reason": trip.reason,
                    "rule": str(rule["id"]),
                },
            )
    return outcome


# ---------------------------------------------------------------- the routes --
def _f(v: Any) -> float:
    return float(v or 0)


async def overview(tx: Tx, company: Any, days: int = 30) -> Ads:
    """Accounts, campaigns (their last 30 days) and the last trips."""
    conns = await CN.rows_of(tx, company.id)
    accounts = []
    for kind in PLATFORMS:
        cn = CN.render(company.code, kind, conns.get(kind), [])
        accounts.append(
            AdAccount(
                platform=kind,
                label_fa=cn.label_fa,
                state=cn.state,
                secret=cn.secret,
                missing_fa=cn.missing_fa,
                last_read_at=cn.last_read_at,
                last_error_fa=cn.last_error_fa,
            )
        )
    camps = await tx.all(
        """SELECT * FROM growth.ad_campaigns WHERE company_id = :co ORDER BY platform, campaign_id""",
        co=company.id,
    )
    rows = await tx.all(
        """SELECT platform, campaign_id, day, spend, clicks, conversions, revenue, roas
           FROM growth.ad_daily WHERE company_id = :co AND day > current_date - CAST(:n AS int)
           ORDER BY day""",
        co=company.id,
        n=days,
    )
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault((r["platform"], r["campaign_id"]), []).append(r)
    out: list[AdCampaign] = []
    for c in camps:
        mine = by.get((c["platform"], c["campaign_id"]), [])
        spend, revenue = sum(_f(r["spend"]) for r in mine), sum(_f(r["revenue"]) for r in mine)
        out.append(
            AdCampaign(
                platform=c["platform"],
                campaign_id=c["campaign_id"],
                name=c["name"],
                status=c["status"],
                paused_by=c["paused_by"],
                paused_at=c["paused_at"],
                paused_reason_fa=c["paused_reason_fa"],
                totals=AdTotals(
                    spend=round(spend, 4),
                    clicks=sum(int(r["clicks"]) for r in mine),
                    conversions=round(sum(_f(r["conversions"]) for r in mine), 4),
                    revenue=round(revenue, 4),
                    roas=roas_of(revenue, spend),
                ),
                days=[
                    AdDay(
                        day=r["day"],
                        spend=_f(r["spend"]),
                        clicks=int(r["clicks"]),
                        conversions=_f(r["conversions"]),
                        revenue=_f(r["revenue"]),
                        roas=None if r["roas"] is None else float(r["roas"]),
                    )
                    for r in mine
                ],
            )
        )
    trips = await tx.all(
        "SELECT * FROM growth.ad_trips WHERE company_id = :co ORDER BY at DESC LIMIT 30",
        co=company.id,
    )
    return Ads(
        company=company.code,
        accounts=accounts,
        campaigns=out,
        trips=[AdTrip(**{k: t[k] for k in AdTrip.model_fields}) for t in trips],
    )


async def weekly_lines(tx: Tx, company_id: UUID, start: datetime, end: datetime) -> list[str]:
    """The lines of the owner's weekly summary about a company's ads: what a
    rule stopped, and what it only told (plain Persian)."""
    rows = await tx.all(
        """SELECT t.outcome, t.detail_fa FROM growth.ad_trips t
           WHERE t.company_id = :co AND t.at >= :s AND t.at < :e ORDER BY t.at""",
        co=company_id,
        s=start,
        e=end,
    )
    if not rows:
        return []
    paused = sum(1 for r in rows if r["outcome"] == "paused")
    failed = sum(1 for r in rows if r["outcome"] == "failed")
    line = f"تبلیغ‌ها: {paused} کمپین به‌خاطر قاعده‌ی بودجه خودکار متوقف شد"
    if failed:
        line += f"، {failed} توقف انجام نشد و پیگیری میشود"
    return [line + ".", *[str(r["detail_fa"])[:160] for r in rows[:3]]]


async def resume(
    hub: Any, company_id: UUID, code: str, platform: str, campaign_id: str, today: date
) -> None:
    """The campaign on again at the platform (the owner's 🔏 ads.resume was
    consumed by the route). Raises CN.ReadError with the plain reason."""
    ctx = await _api_ctx(hub, company_id, code, platform, today)
    try:
        await set_status(ctx, campaign_id, paused=False)
    finally:
        await _record_egress(hub, company_id, ctx)
