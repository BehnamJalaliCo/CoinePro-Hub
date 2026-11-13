"""⟨1.37⟩ Contract §59.9-§59.10 (prompt 38): the automations board, the owner's day, the calendar
and an automation's audit (owner); n8n's 21:30 summary (`/internal/v1/flows/summary`, signed).

GET  /automations/board?company=&kind=      everything that runs by itself, the road's health
                                            and today's figures
GET  /automations/today?day=                the owner's day: each flow, and one line for all
GET  /automations/calendar?from=&to=&company=   each flow's runs and planned days
GET  /automations/{ref}/audit?limit=50      every change of one automation, from the audit log
POST /internal/v1/flows/summary {day?}      n8n (HMAC, kv/hq/n8n): ONE notification of the day
                                            and `automation.summary` on the stream

Included before `routes/automations.py`, so `/automations/board`, `/automations/today` and
`/automations/calendar` are matched before `/automations/{ref}`. The switch of every kind is
`POST /automations/{ref}/state` (routes/automations.py → domain/automation_board.switch)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import automation_board as AB
from hq_api.domain import flow_shapes as FS
from hq_api.domain.gov_common import owner_tz, today
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.lines import signing
from hq_api.routes.lines import n8n_secret
from hq_api.schemas import Model

router = APIRouter(tags=["automations"])
internal_router = APIRouter(tags=["flows"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
CALENDAR_DEFAULT = timedelta(days=14)


@router.get("/automations/board", response_model=FS.AutomationBoard, responses=E)
async def automation_board(
    company: str | None = Query(default=None, pattern=CODE),
    kind: FS.BoardKind | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> FS.AutomationBoard:
    """⟨1.37⟩ §59.10 one list for everything that runs by itself: flows, routines, the standing
    word on publishing (`SP:<group>:<company>`), production lines that are no flow's, the rules of
    a sentence and the archive's rules; each with when it runs, its last run, the next and today's
    cost, and where the app opens it. `health`: n8n, IG-Hub, each company's publish path, the
    helpers' browser, AI Studio and the workshop, read by code (a note says who handles what is
    not ok; never the owner's technical step). `today`: runs, what went out, cost."""
    async with ctx.tx() as tx:
        return await AB.board(tx, ctx.hub, company, kind)


@router.get("/automations/today", response_model=FS.DaySummary, responses=E)
async def automations_today(
    day: date | None = Query(default=None), ctx: Ctx = Depends(owner_ctx)
) -> FS.DaySummary:
    """⟨1.37⟩ §59.9 the owner's day (his zone; `day` left out: today): each flow's runs, what went
    out with its links, the comments, DMs and clicks read from IG-Hub (null: not read, never
    guessed), the cost; `line_fa` says it in one line («امروز: ریلز «…» منتشر شد، ۱۲ کامنت …», or
    «امروز چیزی منتشر نشد: …» with why)."""
    async with ctx.tx() as tx:
        return await AB.day_summary(tx, day)


@router.get("/automations/calendar", response_model=FS.AutoCalendar, responses=E)
async def automations_calendar(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> FS.AutoCalendar:
    """⟨1.37⟩ §59.10 each flow's days from `from` to `to` (both in, the owner's days; left out:
    today and the next 14 days; at most 62): its runs with their states and topics, and its
    planned occurrences ahead (`skipped` where the owner skipped one). `422` for a range that is
    backwards or too long."""
    async with ctx.tx() as tx:
        start = from_ or today(await owner_tz(tx))
        AB.check_day(start, "from")
        return await AB.calendar(tx, start, to or start + CALENDAR_DEFAULT, company)


@router.get("/automations/{ref}/audit", response_model=list[FS.AuditLine], responses=E)
async def automation_audit(
    ref: str = Path(pattern=AB.REF),
    limit: int = Query(default=50, ge=1, le=200),
    ctx: Ctx = Depends(owner_ctx),
) -> list[FS.AuditLine]:
    """⟨1.37⟩ §59.10 every change of one automation (a flow or rule `AT-…`, a line `LN-…`, an
    archive rule `AU-…`, a standing word `SP:<group>:<company>`), newest first, from the audit
    log: who, what, and «from → to» in plain words."""
    async with ctx.tx() as tx:
        return await AB.audit_of(tx, ctx.hub, ref, limit)


class SummaryIn(Model):
    day: date | None = None


class SummaryOut(FS.DaySummary):
    notified: bool


@internal_router.post("/flows/summary", response_model=SummaryOut, responses=E)
async def flows_summary(request: Request, hub: Hub = Depends(get_hub)) -> Any:
    """⟨1.37⟩ §59.9 n8n's 21:30 call (`hq-flows`), signed like a line's callback: the day's
    summary as ONE notification for the owner (Persian only) and `automation.summary {day,
    line_fa}` on the stream (topic `automations`). Once a day: a second call answers the same
    summary with `notified: false`. `401` unsigned."""
    raw = await request.body()
    if not signing.verify(await n8n_secret(hub), raw, request.headers.get(signing.HEADER)):
        raise ApiError(401, "unauthenticated", "bad signature")
    try:
        body = SummaryIn.model_validate_json(raw or b"{}")
    except ValueError as exc:
        raise ApiError(422, "validation_failed", "not a summary body") from exc
    summary, sent = await AB.send_summary(hub, body.day)
    return SummaryOut(**summary.model_dump(), notified=sent)
