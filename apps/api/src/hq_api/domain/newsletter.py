"""Newsletter: the company's own channel (contract §31.3 ⟨1.13⟩).

Listmonk (AGPL-3.0, self-hosted, opt-in compose profile `newsletter`) keeps the
subscribers, their consent and the one-click unsubscribe. The hub keeps only
what it needs: which Listmonk list is which company's (growth.newsletter_lists)
and the campaigns it made (growth.newsletter_campaigns, the calendar's rows).

The hub calls Listmonk's REST API directly on the internal network
`hq-newsletter` (an own service of the hub, like OPA or the LLM router; no agent
reaches it, and no agent tool is built on it). The credential is an API user's
token in OpenBao (kv/hq/newsletter/api, keys `user` and `token`); it is read for
one call and never logged, returned or stored.

  lists       one list per company, made on first use (double opt-in)
  campaigns   made as a draft in Listmonk; a scheduled send is 🔏
              `newsletter.send` when the list is over the size limit (settings)
  daily read  opens, clicks, sent and bounces of each recent campaign, and each
              list's subscriber count, into growth.metrics_daily (kind
              `newsletter`); by code, no model

A/B subject: Listmonk has no native A/B test, so none is built here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.errors import ApiError

log = logging.getLogger("hq_api.newsletter")

CREDENTIAL_PATH = "hq/newsletter/api"
KIND = "newsletter"
SOURCE = "listmonk"
READ_DAYS = 30  # a campaign is read daily for a month after its send
TIMEOUT_S = 30.0
OFF_FA = "خبرنامه هنوز روشن نیست؛ پروفایل خبرنامه را روشن کنید (make newsletter-on)."
NO_CRED_FA = "کلید کاربر API لیست‌مانک هنوز در OpenBao گذاشته نشده است (make newsletter-secret)."
DOWN_FA = "لیست‌مانک پاسخ نداد؛ بعداً دوباره امتحان کنید."
Status = Literal["draft", "scheduled", "running", "finished", "paused", "cancelled"]
STATES: tuple[str, ...] = ("draft", "scheduled", "running", "finished", "paused", "cancelled")
# Listmonk's status words -> ours (Listmonk has no «paused by us»).
STATE_OF = {s: s for s in STATES}


class NewsletterList(BaseModel):
    id: UUID
    listmonk_id: int
    name: str
    subscribers: int | None = None


class CampaignOut(BaseModel):
    id: UUID
    company: str
    listmonk_id: int
    list_id: int
    subject: str
    state: str
    send_at: datetime | None
    list_size: int | None
    sent: int | None = None
    opens: int | None = None
    clicks: int | None = None
    bounces: int | None = None
    created_at: datetime


class NewsletterOut(BaseModel):
    company: str
    active: bool
    size_limit: int
    lists: list[NewsletterList]
    campaigns: list[CampaignOut]
    note_fa: str | None = None


class CampaignIn(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=200_000)
    content_type: Literal["richtext", "html", "markdown", "plain"] = "html"
    list_id: UUID | None = None


class ScheduleIn(BaseModel):
    at: AwareDatetime


# ---------------------------------------------------------------- client --
@dataclass
class Reply:
    status: int
    data: Any


class Listmonk:
    """A thin client of Listmonk's REST API (token auth). `transport` is for tests."""

    def __init__(
        self,
        base_url: str,
        user: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base = base_url.rstrip("/")
        self._auth = {"Authorization": f"token {user}:{token}"}
        self._transport = transport

    async def call(self, method: str, path: str, *, json_body: Any = None, **params: Any) -> Reply:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=TIMEOUT_S, trust_env=False
            ) as http:
                resp = await http.request(
                    method,
                    self.base + path,
                    headers=self._auth,
                    params={k: v for k, v in params.items() if v is not None},
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            log.warning("listmonk unreachable", extra={"error": type(exc).__name__})
            raise ApiError(503, "channel_not_configured", DOWN_FA, message_fa=DOWN_FA) from exc
        try:
            body = resp.json()
        except ValueError:
            body = None
        data = body.get("data") if isinstance(body, dict) else None
        if resp.status_code in (401, 403):
            raise ApiError(409, "channel_not_configured", message_fa=NO_CRED_FA)
        if resp.status_code >= 400:
            msg = str(body.get("message")) if isinstance(body, dict) else ""
            log.warning("listmonk refused", extra={"status": resp.status_code, "reason": msg[:200]})
            raise ApiError(
                422 if resp.status_code < 500 else 503,
                "validation_failed" if resp.status_code < 500 else "channel_not_configured",
                msg[:300] or None,
            )
        return Reply(resp.status_code, data)

    async def lists(self) -> list[dict[str, Any]]:
        r = await self.call("GET", "/api/lists", per_page="all", minimal="true")
        rows = (r.data or {}).get("results") if isinstance(r.data, dict) else None
        return [x for x in rows or [] if isinstance(x, dict)]

    async def list_one(self, list_id: int) -> dict[str, Any]:
        r = await self.call("GET", f"/api/lists/{list_id}")
        return r.data if isinstance(r.data, dict) else {}

    async def create_list(self, name: str) -> dict[str, Any]:
        body = {"name": name, "type": "private", "optin": "double", "tags": ["hq"]}
        r = await self.call("POST", "/api/lists", json_body=body)
        return r.data if isinstance(r.data, dict) else {}

    async def campaign(self, campaign_id: int) -> dict[str, Any]:
        r = await self.call("GET", f"/api/campaigns/{campaign_id}", no_body="true")
        return r.data if isinstance(r.data, dict) else {}

    async def create_campaign(self, body: dict[str, Any]) -> dict[str, Any]:
        r = await self.call("POST", "/api/campaigns", json_body=body)
        return r.data if isinstance(r.data, dict) else {}

    async def update_campaign(self, campaign_id: int, body: dict[str, Any]) -> dict[str, Any]:
        r = await self.call("PUT", f"/api/campaigns/{campaign_id}", json_body=body)
        return r.data if isinstance(r.data, dict) else {}

    async def set_status(self, campaign_id: int, status: str) -> dict[str, Any]:
        r = await self.call(
            "PUT", f"/api/campaigns/{campaign_id}/status", json_body={"status": status}
        )
        return r.data if isinstance(r.data, dict) else {}


OVERRIDE: Listmonk | None = None  # tests put a client over a fake Listmonk here


async def credentials(bao: Any) -> tuple[str, str] | None:
    if bao is None:
        return None
    from hq_common.openbao import OpenBaoError

    try:
        data = await bao.read_kv(CREDENTIAL_PATH)
    except OpenBaoError:
        return None
    user, token = (data or {}).get("user"), (data or {}).get("token")
    if isinstance(user, str) and user and isinstance(token, str) and token:
        return user, token
    return None


async def client_for(hub: Any) -> Listmonk:
    """The client, or 503 `channel_not_configured` with the Persian reason."""
    if OVERRIDE is not None:
        return OVERRIDE
    if not hub.settings.newsletter:
        raise ApiError(409, "channel_not_configured", OFF_FA, message_fa=OFF_FA)
    cred = await credentials(getattr(hub, "bao", None))
    if cred is None:
        raise ApiError(409, "channel_not_configured", NO_CRED_FA, message_fa=NO_CRED_FA)
    return Listmonk(hub.settings.newsletter_url, *cred)


def active(hub: Any) -> bool:
    return OVERRIDE is not None or bool(hub.settings.newsletter)


# --------------------------------------------------------------- the code --
def state_of(listmonk_status: Any) -> str:
    return STATE_OF.get(str(listmonk_status), "draft")


def needs_seal(list_size: int, limit: int) -> bool:
    """A scheduled send to a list over the size limit is the owner's to seal."""
    return list_size > limit


def future_or_raise(at: datetime, now: datetime | None = None) -> datetime:
    if at.tzinfo is None:
        raise ApiError(422, "validation_failed", fields={"at": "a time with a zone"})
    if at <= (now or datetime.now(UTC)) + timedelta(minutes=1):
        raise ApiError(422, "validation_failed", fields={"at": "in the future"})
    return at.astimezone(UTC)


async def lists_of(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        "SELECT id, listmonk_id, name FROM growth.newsletter_lists WHERE company_id = :co "
        "ORDER BY created_at",
        co=company_id,
    )


async def ensure_list(tx: Tx, lm: Listmonk, company: Any) -> dict[str, Any]:
    """The company's first list (made once, named by its code)."""
    found = await lists_of(tx, company.id)
    if found:
        return found[0]
    made = await lm.create_list(f"{company.code} · خبرنامه")
    lid = made.get("id")
    if not isinstance(lid, int):
        raise ApiError(503, "channel_not_configured", DOWN_FA, message_fa=DOWN_FA)
    row = await tx.one(
        """INSERT INTO growth.newsletter_lists (company_id, listmonk_id, name)
           VALUES (:co, :l, :n) RETURNING id, listmonk_id, name""",
        co=company.id,
        l=lid,
        n=str(made.get("name") or company.code)[:200],
    )
    return dict(row)


def _out(code: str, r: dict[str, Any], live: dict[str, Any] | None = None) -> CampaignOut:
    live = live or {}

    def n(key: str) -> int | None:
        v = live.get(key)
        return v if isinstance(v, int) else None

    return CampaignOut(
        id=r["id"],
        company=code,
        listmonk_id=r["listmonk_id"],
        list_id=r["list_id"],
        subject=r["subject"],
        state=r["state"],
        send_at=r["send_at"],
        list_size=r["list_size"],
        sent=n("sent"),
        opens=n("views"),
        clicks=n("clicks"),
        bounces=n("bounces"),
        created_at=r["created_at"],
    )


async def overview(hub: Any, tx: Tx, company: Any) -> NewsletterOut:
    """The company's lists with counts and its last campaigns. When Listmonk is
    off or unreachable the stored rows are still shown, with a Persian note."""
    note: str | None = None
    counts: dict[int, int] = {}
    if active(hub):
        try:
            lm = await client_for(hub)
            for item in await lm.lists():
                if isinstance(item.get("id"), int):
                    counts[item["id"]] = int(item.get("subscriber_count") or 0)
        except ApiError as exc:
            note = exc.message_fa or OFF_FA
    else:
        note = OFF_FA
    lists = [
        NewsletterList(
            id=r["id"],
            listmonk_id=r["listmonk_id"],
            name=r["name"],
            subscribers=counts.get(r["listmonk_id"]),
        )
        for r in await lists_of(tx, company.id)
    ]
    rows = await tx.all(
        "SELECT * FROM growth.newsletter_campaigns WHERE company_id = :co "
        "ORDER BY created_at DESC LIMIT 10",
        co=company.id,
    )
    return NewsletterOut(
        company=company.code,
        active=active(hub),
        size_limit=hub.settings.newsletter_size_limit,
        lists=lists,
        campaigns=[_out(company.code, dict(r)) for r in rows],
        note_fa=note,
    )


async def create_campaign(hub: Any, tx: Tx, company: Any, body: CampaignIn) -> CampaignOut:
    """A draft in Listmonk for one of the company's lists (its first when none is named)."""
    lm = await client_for(hub)
    if body.list_id is not None:
        lst = await tx.first(
            "SELECT id, listmonk_id, name FROM growth.newsletter_lists "
            "WHERE id = :id AND company_id = :co",
            id=body.list_id,
            co=company.id,
        )
        if lst is None:
            raise ApiError(422, "validation_failed", fields={"list_id": "a list of this company"})
    else:
        lst = await ensure_list(tx, lm, company)
    made = await lm.create_campaign(
        {
            "name": f"{company.code} · {body.subject}"[:200],
            "subject": body.subject,
            "lists": [lst["listmonk_id"]],
            "type": "regular",
            "content_type": body.content_type,
            "body": body.body,
            "messenger": "email",
            "tags": ["hq", company.code],
        }
    )
    cid = made.get("id")
    if not isinstance(cid, int):
        raise ApiError(503, "channel_not_configured", DOWN_FA, message_fa=DOWN_FA)
    row = await tx.one(
        """INSERT INTO growth.newsletter_campaigns (company_id, listmonk_id, list_id, subject, state)
           VALUES (:co, :c, :l, :s, 'draft') RETURNING *""",
        co=company.id,
        c=cid,
        l=lst["listmonk_id"],
        s=body.subject,
    )
    return _out(company.code, dict(row))


async def get_row(tx: Tx, campaign_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    sql = (
        "SELECT n.*, c.code AS company FROM growth.newsletter_campaigns n "
        "JOIN core.companies c ON c.id = n.company_id WHERE n.id = :id"
    )
    row = await tx.first(sql + " FOR UPDATE OF n" if lock else sql, id=campaign_id)
    if row is None:
        raise ApiError(404, "not_found")
    return dict(row)


async def detail(hub: Any, tx: Tx, campaign_id: UUID) -> CampaignOut:
    """The stored campaign with Listmonk's live figures when it answers."""
    r = await get_row(tx, campaign_id)
    live: dict[str, Any] = {}
    if active(hub):
        try:
            live = await (await client_for(hub)).campaign(r["listmonk_id"])
        except ApiError:
            live = {}
    return _out(r["company"], r, live)


async def list_size(lm: Listmonk, list_id: int) -> int:
    got = await lm.list_one(list_id)
    return int(got.get("subscriber_count") or 0)


async def schedule(lm: Listmonk, r: dict[str, Any], at: datetime) -> None:
    """Set the send time and move the campaign to `scheduled` (Listmonk sends it by itself)."""
    cur = await lm.campaign(r["listmonk_id"])
    if not cur:
        raise ApiError(404, "not_found")
    if str(cur.get("status")) not in ("draft", "scheduled"):
        raise ApiError(409, "version_conflict", "campaign is already sending or finished")
    body = {
        "name": cur.get("name"),
        "subject": cur.get("subject"),
        "lists": [x["id"] for x in cur.get("lists") or [] if isinstance(x, dict) and "id" in x],
        "type": cur.get("type") or "regular",
        "content_type": cur.get("content_type") or "html",
        "body": cur.get("body") or "",
        "messenger": cur.get("messenger") or "email",
        "template_id": cur.get("template_id"),
        "tags": cur.get("tags") or [],
        "send_at": at.isoformat(),
    }
    await lm.update_campaign(r["listmonk_id"], {k: v for k, v in body.items() if v is not None})
    await lm.set_status(r["listmonk_id"], "scheduled")


# ------------------------------------------------------------ daily read --
@dataclass
class Figure:
    day: date
    key: str
    value: float
    subject: str


def figures_of(day: date, campaign: dict[str, Any], list_counts: dict[int, int]) -> list[Figure]:
    """Pure: Listmonk's campaign object (and the lists' counts) -> the day's figures."""
    out: list[Figure] = []
    cid = campaign.get("id")
    if isinstance(cid, int):
        for src, key in (
            ("sent", "sent"),
            ("views", "opens"),
            ("clicks", "clicks"),
            ("bounces", "bounces"),
        ):
            v = campaign.get(src)
            if isinstance(v, int | float):
                out.append(Figure(day, key, float(v), f"c{cid}"))
    for lid, n in list_counts.items():
        out.append(Figure(day, "subscribers", float(n), f"l{lid}"))
    return out


async def read_daily(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The daily read, by code: each company's lists and its recent campaigns into
    growth.metrics_daily (kind `newsletter`). Nothing while the holding is locked
    or the profile is off."""
    from hq_api.domain import connections as CN
    from hq_api.domain.gov_common import owner_tz

    if not active(hub):
        return {"skipped": True, "reason": "newsletter_off"}
    now = now or datetime.now(UTC)
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        today = CN.owner_today(await owner_tz(tx), now)
        lists = await tx.all(
            "SELECT l.company_id, l.listmonk_id, c.code, control.lock_state(l.company_id) AS lock "
            "FROM growth.newsletter_lists l JOIN core.companies c ON c.id = l.company_id "
            "WHERE c.status = 'active'"
        )
        camps = await tx.all(
            "SELECT n.id, n.company_id, n.listmonk_id, c.code, control.lock_state(n.company_id) AS lock "
            "FROM growth.newsletter_campaigns n JOIN core.companies c ON c.id = n.company_id "
            "WHERE c.status = 'active' AND n.state IN ('scheduled', 'running', 'finished') "
            "AND coalesce(n.send_at, n.created_at) > :since",
            since=now - timedelta(days=READ_DAYS),
        )
    if not lists and not camps:
        return {"read": 0}
    try:
        lm = await client_for(hub)
        counts = {
            x["id"]: int(x.get("subscriber_count") or 0)
            for x in await lm.lists()
            if isinstance(x.get("id"), int)
        }
    except ApiError as exc:
        return {"skipped": True, "reason": "newsletter_unavailable", "note_fa": exc.message_fa}
    stored = 0
    async with hub.db.tx(ids) as tx:
        for lr in lists:
            if lr["lock"] is None and lr["listmonk_id"] in counts:
                figs = figures_of(today, {}, {lr["listmonk_id"]: counts[lr["listmonk_id"]]})
                stored += await CN.store(tx, lr["company_id"], KIND, _as_cn(figs))
    for cr in camps:
        if cr["lock"] is not None:
            continue
        try:
            live = await lm.campaign(cr["listmonk_id"])
        except ApiError:
            continue
        async with hub.db.tx(ids) as tx:
            stored += await CN.store(
                tx, cr["company_id"], KIND, _as_cn(figures_of(today, live, {}))
            )
            await tx.exec(
                "UPDATE growth.newsletter_campaigns SET state = :s, updated_at = now() WHERE id = :id",
                s=state_of(live.get("status")),
                id=cr["id"],
            )
    return {"read": stored}


def _as_cn(figs: list[Figure]) -> list[Any]:
    from hq_api.domain.connections import Figure as CF

    return [CF(f.day, f.key, f.value, f.subject, SOURCE) for f in figs]


async def announce(tx: Tx, company: str, campaign: CampaignOut) -> None:
    await events.emit(
        tx,
        company,
        "campaign.updated",
        str(campaign.id),
        {"kind": "newsletter", "state": campaign.state, "send_at": campaign.send_at},
    )
