"""The owner: Khalvat (presence), «در نبودت چه گذشت», settings, and the
record of their own interactions (contract §6, §1.8)."""

from __future__ import annotations

import ipaddress
import logging
import re
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import hiring, notify
from hq_api.errors import ApiError, responses
from hq_api.routes.notifications import if_match, time_cursor
from hq_api.security import stepup
from hq_common import provisioning

log = logging.getLogger("hq_api.routes.owner")
router = APIRouter(tags=["owner"])

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Presence(BaseModel):
    khalvat: bool
    since: datetime
    until: datetime | None


class PresenceIn(BaseModel):
    khalvat: bool
    until: datetime | None = None


class TopDecision(BaseModel):
    ref: str
    title: str
    kind: str
    risk: str
    status: str
    company: str
    created_at: datetime


class TopDeliverable(BaseModel):
    ref: str
    title: str
    company: str
    created_at: datetime


class TopThread(BaseModel):
    thread: str
    company: str
    new_messages: int
    last_at: datetime


class TopNotification(BaseModel):
    id: UUID
    level: str
    title_fa: str
    company: str
    created_at: datetime
    link_kind: str | None
    link_ref: str | None


class DecisionsBox(BaseModel):
    new: int
    pending: int
    top: list[TopDecision]


class DeliverablesBox(BaseModel):
    new: int
    unrated: int
    top: list[TopDeliverable]


class MessagesBox(BaseModel):
    new: int
    unread: int
    top_threads: list[TopThread]


class NotificationsBox(BaseModel):
    by_level: dict[str, int]
    held: int
    top: list[TopNotification]


class CompanyAway(BaseModel):
    company: str
    decisions_new: int
    deliverables_new: int
    messages_new: int
    notifications_new: int


class AwaySummary(BaseModel):
    since: datetime
    until: datetime
    decisions: DecisionsBox
    deliverables: DeliverablesBox
    messages: MessagesBox
    notifications: NotificationsBox
    companies: list[CompanyAway]


class OwnerSettings(BaseModel):
    timezone: str
    morning_report_at: str
    digest_minutes: int
    ceo_daily_attention: int
    learning_daily_cap: int
    calendars: list[Literal["jalali", "gregorian"]]
    # ⟨1.4⟩ hours without the owner before the Chief Overseer keeps watch (§18.1)
    watch_after_hours: int = 6
    # ⟨1.4⟩ prompt 09: the owner's addresses SSH may come from on a new server
    # (a server plan never opens SSH to the whole internet)
    provision_ssh_sources: list[str] = Field(default_factory=list)
    version: int


class OwnerSettingsIn(BaseModel):
    """Fields left out keep their current value."""

    timezone: str | None = Field(default=None, max_length=64)
    morning_report_at: str | None = None
    digest_minutes: int | None = Field(default=None, ge=5, le=720)
    ceo_daily_attention: int | None = Field(default=None, ge=0, le=100)
    learning_daily_cap: int | None = Field(default=None, ge=0, le=20)
    calendars: list[Literal["jalali", "gregorian"]] | None = Field(
        default=None, min_length=1, max_length=2
    )
    watch_after_hours: int | None = Field(default=None, ge=1, le=72)
    provision_ssh_sources: list[str] | None = Field(default=None, max_length=20)

    @field_validator("provision_ssh_sources")
    @classmethod
    def _cidrs(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        out = []
        for s in v:
            try:
                net = ipaddress.ip_network(s.strip(), strict=True)
            except ValueError as exc:
                raise ValueError(f"{s[:50]!r} is not a CIDR") from exc
            if net.prefixlen == 0:
                raise ValueError("not the whole internet: name your own addresses")
            out.append(str(net))
        # Review 9.2 §2.1: nor the whole internet in pieces (0.0.0.0/1 + 128.0.0.0/1).
        if provisioning.covers_everything([ipaddress.ip_network(s) for s in out]):
            raise ValueError("not the whole internet: name your own addresses")
        return list(dict.fromkeys(out))

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown time zone") from exc
        return v

    @field_validator("morning_report_at")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v is not None and not _HHMM.match(v):
            raise ValueError("HH:MM, 24-hour")
        return v


class Target(BaseModel):
    kind: str | None
    ref: str | None


class Interaction(BaseModel):
    id: UUID
    at: datetime
    company: str
    kind: str
    action: str
    target: Target
    data: dict[str, Any]


class InteractionPage(BaseModel):
    items: list[Interaction]
    next_cursor: str | None


async def _presence(tx: Any) -> dict[str, Any]:
    row: dict[str, Any] = await tx.one(
        """SELECT khalvat, since, until, last_khalvat_start, last_khalvat_end, version
           FROM owner.presence WHERE id = 1"""
    )
    return row


@router.get("/owner/presence", response_model=Presence, responses=responses(401))
async def get_presence(ctx: Ctx = Depends(owner_ctx)) -> Presence:
    """Khalvat state: on/off, since when and until when."""
    async with ctx.tx() as tx:
        p = await _presence(tx)
    return Presence(khalvat=p["khalvat"], since=p["since"], until=p["until"])


@router.put("/owner/presence", response_model=Presence, responses=responses(401, 422))
async def put_presence(body: PresenceIn, ctx: Ctx = Depends(owner_ctx)) -> Presence:
    """Khalvat on: only urgent items reach the owner and every CEO sees
    "owner in Khalvat - urgent only". Off: held items are released and
    `/owner/away-summary` tells what happened meanwhile."""
    if body.until is not None and (not body.khalvat or body.until <= datetime.now(UTC)):
        raise ApiError(
            422, "validation_failed", fields={"until": "only with khalvat on, in the future"}
        )
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        before = await _presence(tx)
        changed = before["khalvat"] != body.khalvat
        if body.khalvat:
            row = await tx.one(
                """UPDATE owner.presence
                   SET khalvat = true, until = :until,
                       since = CASE WHEN khalvat THEN since ELSE now() END,
                       last_khalvat_start = CASE WHEN khalvat THEN last_khalvat_start ELSE now() END
                   WHERE id = 1 RETURNING khalvat, since, until""",
                until=body.until,
            )
        else:
            row = await tx.one(
                """UPDATE owner.presence
                   SET khalvat = false, until = NULL,
                       since = CASE WHEN khalvat THEN now() ELSE since END,
                       last_khalvat_end = CASE WHEN khalvat THEN now() ELSE last_khalvat_end END
                   WHERE id = 1 RETURNING khalvat, since, until"""
            )
        if changed:
            data = {"khalvat": body.khalvat, "until": body.until, "since": row["since"]}
            for c in await ctx.hub.companies.all():
                await ctx.emit(tx, c.code, "presence.changed", "owner", data)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="presence.khalvat_on" if body.khalvat else "presence.khalvat_off",
            action_class="A1",
            target_kind="presence",
            target_ref="owner",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="presence",
            action="presence.khalvat_on" if body.khalvat else "presence.khalvat_off",
            target_kind="presence",
            target_ref="owner",
            data={"until": body.until},
        )
    if changed and not body.khalvat:
        try:
            await notify.flush_digest(ctx.hub)
        except Exception:  # noqa: BLE001 - the worker's next digest pass retries
            log.warning("release after khalvat failed; the digest workflow will retry")
    return Presence(khalvat=row["khalvat"], since=row["since"], until=row["until"])


@router.get("/owner/away-summary", response_model=AwaySummary, responses=responses(401))
async def get_away_summary(
    ctx: Ctx = Depends(owner_ctx), since: datetime | None = None
) -> AwaySummary:
    """«در نبودت چه گذشت»: counts and the top items per box and per company since
    `since` (default: the start of the last Khalvat). Deterministic, no model."""
    async with ctx.tx() as tx:
        if since is None:
            p = await _presence(tx)
            since = p["last_khalvat_start"] or datetime.now(UTC) - timedelta(hours=24)
        result = await notify.away_summary(tx, since)
    return AwaySummary.model_validate(result)


def _settings_out(row: dict[str, Any]) -> OwnerSettings:
    t: time = row["morning_report_at"]
    return OwnerSettings(
        timezone=row["timezone"],
        morning_report_at=t.strftime("%H:%M"),
        digest_minutes=row["digest_minutes"],
        ceo_daily_attention=row["ceo_daily_attention"],
        learning_daily_cap=row["learning_daily_cap"],
        calendars=row["calendars"],
        watch_after_hours=row["watch_after_hours"],
        provision_ssh_sources=list(row["provision_ssh_sources"] or []),
        version=row["version"],
    )


SETTINGS_COLS = (
    "timezone, morning_report_at, digest_minutes, ceo_daily_attention, learning_daily_cap, "
    "calendars, watch_after_hours, provision_ssh_sources, version"
)


@router.get("/owner/settings", response_model=OwnerSettings, responses=responses(401))
async def get_owner_settings(response: Response, ctx: Ctx = Depends(owner_ctx)) -> OwnerSettings:
    """Time zone, morning report time, digest window, CEO attention quota, learning cap, calendars."""
    async with ctx.tx() as tx:
        row = await tx.one(f"SELECT {SETTINGS_COLS} FROM owner.settings WHERE id = 1")  # noqa: S608 - constant column list
    response.headers["ETag"] = f'"{row["version"]}"'
    return _settings_out(row)


@router.put(
    "/owner/settings", response_model=OwnerSettings, responses=responses(401, 409, 422, 428)
)
async def put_owner_settings(
    body: OwnerSettingsIn, request: Request, response: Response, ctx: Ctx = Depends(owner_ctx)
) -> OwnerSettings:
    """Updates the owner's settings (partial body). Requires `If-Match: <version>`."""
    version = if_match(request)
    holding = await ctx.hub.companies.holding()
    changes = body.model_dump(exclude_none=True)
    async with ctx.tx() as tx:
        row = await tx.first(
            f"""UPDATE owner.settings SET
                   timezone = COALESCE(:tz, timezone),
                   morning_report_at = COALESCE(CAST(:mra AS time), morning_report_at),
                   digest_minutes = COALESCE(:dm, digest_minutes),
                   ceo_daily_attention = COALESCE(:cda, ceo_daily_attention),
                   learning_daily_cap = COALESCE(:ldc, learning_daily_cap),
                   calendars = COALESCE(CAST(:cal AS text[]), calendars),
                   watch_after_hours = COALESCE(:wah, watch_after_hours),
                   provision_ssh_sources = COALESCE(CAST(:pss AS text[]), provision_ssh_sources)
               WHERE id = 1 AND version = :v RETURNING {SETTINGS_COLS}""",  # noqa: S608 - constant column list, values are bound
            tz=body.timezone,
            mra=time.fromisoformat(body.morning_report_at) if body.morning_report_at else None,
            dm=body.digest_minutes,
            cda=body.ceo_daily_attention,
            ldc=body.learning_daily_cap,
            cal=list(dict.fromkeys(body.calendars)) if body.calendars else None,
            wah=body.watch_after_hours,
            pss=body.provision_ssh_sources,
            v=version,
        )
        if row is None:
            raise ApiError(409, "version_conflict")
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="owner.settings",
            action_class="A1",
            target_kind="settings",
            target_ref="owner",
            summary=", ".join(sorted(changes)),
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="owner.settings",
            target_kind="settings",
            target_ref="owner",
            data=changes,
        )
    response.headers["ETag"] = f'"{row["version"]}"'
    return _settings_out(row)


@router.get("/owner/interactions", response_model=InteractionPage, responses=responses(401, 422))
async def list_owner_interactions(
    ctx: Ctx = Depends(owner_ctx),
    kind: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
) -> InteractionPage:
    """What the system records about the owner (§1.8): always visible to them."""
    c0, c1 = time_cursor(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT i.id, i.at, c.code AS company, i.kind, i.action, i.target_kind, i.target_ref,
                      i.data
               FROM owner.interactions i JOIN core.companies c ON c.id = i.company_id
               WHERE (CAST(:kind AS text) IS NULL OR i.kind = CAST(:kind AS text))
                 AND (CAST(:c0 AS timestamptz) IS NULL
                      OR (i.at, i.id) < (CAST(:c0 AS timestamptz), CAST(:c1 AS uuid)))
               ORDER BY i.at DESC, i.id DESC LIMIT :lim""",
            kind=kind,
            c0=c0,
            c1=c1,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return InteractionPage(
        items=[
            Interaction(
                id=r["id"],
                at=r["at"],
                company=r["company"],
                kind=r["kind"],
                action=r["action"],
                target=Target(kind=r["target_kind"], ref=r["target_ref"]),
                data=r["data"],
            )
            for r in items
        ],
        next_cursor=nxt,
    )


# ------------------------------------------------------------------ hiring --
class HiringStart(BaseModel):
    mode: hiring.Mode


class HiringStarted(hiring.Hiring):
    work: list[str] = Field(default_factory=list, description="work items created (proposals)")


@router.get("/owner/hiring", response_model=hiring.Hiring, responses=responses(401))
async def get_hiring(ctx: Ctx = Depends(owner_ctx)) -> hiring.Hiring:
    """Hiring starts with the owner (contract §18.11): `closed` by default; the
    hire cards the system withdrew are listed in `withdrawn`."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        return await hiring.load(tx, holding.id)


@router.post(
    "/owner/hiring/start",
    response_model=HiringStarted,
    responses=responses(401, 403, 409, 422),
)
async def start_hiring(body: HiringStart, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`hiring.start`, target `holding`). `proposals`: hiring opens to agents,
    the owner decides every card, and each CEO (and each holding head with a
    hiring duty) gets one work item "propose your first month's team" (a second
    start adds none). `delegated`: each CEO hires inside its company's monthly
    envelope and decides the company's hire cards; every active operating
    company needs an envelope (`/budgets`, company, month) or `422
    envelope_required` names the ones without, before any step-up is consumed.
    Honours `Idempotency-Key` (a retry after a lost answer gets the same
    answer, not a spent step-up)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await hiring.require_envelopes(tx, body.mode)
        await stepup.consume(tx, request, ctx.who, "hiring.start", "holding")
        out = await hiring.start(
            tx,
            ctx.who,
            holding_id=holding.id,
            holding_code=holding.code,
            mode=body.mode,
            charters=ctx.hub.charters,
        )
        work = [w["ref"] for w in out["work"]]
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="hiring.start",
            action_class="A2",
            target_kind="hiring",
            target_ref=holding.code,
            summary=f"mode {body.mode}; {len(work)} work items",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="hiring.start",
            target_kind="hiring",
            target_ref=holding.code,
            data={"mode": body.mode, "work": work},
        )
        state = await hiring.load(tx, holding.id)
        result = HiringStarted(**state.model_dump(), work=work)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@router.post("/owner/hiring/close", response_model=hiring.Hiring, responses=responses(401))
async def close_hiring(ctx: Ctx = Depends(owner_ctx)) -> hiring.Hiring:
    """No step-up (closing is always safe): hiring closes to agents and every
    pending hire card is withdrawn (never deleted; listed in `withdrawn`)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        refs = await hiring.close(tx, ctx.who, holding_id=holding.id, holding_code=holding.code)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="hiring.close",
            action_class="A1",
            target_kind="hiring",
            target_ref=holding.code,
            summary=f"{len(refs)} pending hire cards withdrawn",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="hiring.close",
            target_kind="hiring",
            target_ref=holding.code,
            data={"withdrawn": refs},
        )
        state = await hiring.load(tx, holding.id)
    for ref in refs:  # each card's DecisionLifecycle sees it is no longer pending and ends
        await workflows_client.decision_decided(ctx.hub, ref)
    return state
