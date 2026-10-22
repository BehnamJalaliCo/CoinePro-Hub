"""The Chief Overseer (contract §18.1): the owner's view and seals, and the
internal API behind the overseer's tools (agents/tools.md v2).

Owner: summary, protocols (🔏 body hash to add or version), runs, findings
(verify/close/dispute), challenges, standing orders (🔏 seal), holds (🔏
release; cancel), watch, compliance.
Agents (Tool Gateway): finding.raise / finding.update, protocol.result,
challenge.issue / submit / score, hold, kill_switch.engage, deploy.freeze.
Releasing a kill switch, a freeze or a hold has no agent path at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import control
from hq_api.domain import oversight as O
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model, Page
from hq_api.security import stepup
from hq_api.workshop import service as workshop_service
from hq_common.redact import scrub, scrub_async

router = APIRouter(tags=["oversight"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
EI = responses(401, 403, 404, 409, 422, 423, 429)
CO = r"^[A-Z][A-Z0-9]{1,9}$"


class ProtocolRun(BaseModel):
    id: UUID
    protocol: str
    version: int
    method: str
    started_at: datetime
    finished_at: datetime | None
    result: str
    by: str
    findings: int
    per_company: dict[str, str]
    notes: str


class Summary(BaseModel):
    watch: O.WatchReport
    compliance: list[O.Compliance]
    findings_open: dict[str, int]
    holds_waiting: int
    challenges_week: dict[str, int]
    protocols: dict[str, int]


class FindingStatusIn(Model):
    status: Literal["verified", "closed", "disputed"]
    note: str = Field(default="", max_length=5000)
    evidence: list[O.Evidence] = Field(default_factory=list, max_length=20)


class OrderIn(Model):
    text_md: str = Field(min_length=1, max_length=10000)
    source: Literal["voice", "text"] = "text"
    file_id: UUID | None = None
    applies_to: Literal["overseer", "all"] = "overseer"


class NoteIn(Model):
    note: str | None = Field(default=None, max_length=2000)


class WatchIn(Model):
    on: bool


def _run(r: dict[str, Any]) -> ProtocolRun:
    return ProtocolRun(
        id=r["id"],
        protocol=r["protocol_ref"],
        version=r["version"],
        method=r["method"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        result=r["result"],
        by=r["by_code"],
        findings=r["findings"],
        per_company=dict(r["per_company"] or {}),
        notes=r["notes"],
    )


async def _tz(tx: Tx) -> str:
    return str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran")


# ------------------------------------------------------------------ owner --
@router.get("/oversight/summary", response_model=Summary, responses=E)
async def summary(ctx: Ctx = Depends(owner_ctx)) -> Summary:
    """Compliance per company, open findings by severity, holds waiting, this
    week's challenges, watch mode."""
    async with ctx.tx() as tx:
        tz = await _tz(tx)
        ids = [
            c.id
            for c in await ctx.hub.companies.all()
            if c.kind != "holding" and c.status == "active"
        ]
        sev = await tx.all(
            "SELECT severity, count(*) AS n FROM oversight.findings"
            " WHERE status NOT IN ('verified', 'closed') GROUP BY severity"
        )
        week = O.week_key(datetime.now(UTC), tz)
        ch = await tx.all(
            "SELECT status, count(*) AS n FROM oversight.challenges WHERE period = 'week' AND period_key = :k"
            " GROUP BY status",
            k=week,
        )
        holds = await tx.scalar("SELECT count(*) FROM oversight.holds WHERE state = 'held'")
        active = await tx.scalar(
            "SELECT count(*) FROM oversight.current_protocols WHERE status = 'active'"
        )
        failed = await tx.scalar(
            "SELECT count(*) FROM oversight.protocol_runs WHERE result = 'fail' AND started_at >= :s",
            s=O.day_start(datetime.now(UTC), tz),
        )
        return Summary(
            watch=await O.watch_report(tx),
            compliance=await O.compliance_of(tx, ids),
            findings_open=dict.fromkeys(O.SEVERITIES, 0)
            | {r["severity"]: int(r["n"]) for r in sev},
            holds_waiting=int(holds or 0),
            challenges_week=dict.fromkeys(
                ("issued", "accepted", "submitted", "scored", "missed"), 0
            )
            | {r["status"]: int(r["n"]) for r in ch},
            protocols={"active": int(active or 0), "failed_today": int(failed or 0)},
        )


@router.get("/oversight/protocols", response_model=list[O.Protocol], responses=E)
async def list_protocols(
    area: str | None = Query(default=None, pattern=r"^[a-z]{3,10}$"),
    status: Literal["active", "paused", "draft"] | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[O.Protocol]:
    """The protocols in force (newest version each), `?area&status`, with their last run."""
    async with ctx.tx() as tx:
        return await O.protocols(tx, area=area, status=status)


async def _seal_protocol(
    ctx: Ctx, request: Request, body: O.ProtocolIn, ref: str | None, status_code: int
) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        su = await stepup.consume(
            tx, request, ctx.who, "oversight.protocol", await stepup.body_target(request)
        )
        holding = await ctx.hub.companies.holding()
        p = await O.new_version(
            tx, ctx.who, holding.id, body.model_dump(), ref=ref, source="owner", step_up_id=su
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="oversight.protocol",
            action_class="A2",
            target_kind="protocol",
            target_ref=f"{p['ref']}@{p['version']}",
            summary=p["status"],
            step_up=True,
        )
        result = O.render_protocol(p)
        if idem:
            await idem.store(tx, status_code, result.model_dump(mode="json"))
    await _reconcile(ctx)
    return result


async def _reconcile(ctx: Ctx) -> None:
    """The schedules follow the protocols (the worker reconciles them)."""
    from hq_api import workflows_client

    try:
        await workflows_client.reconcile(ctx.hub)
    except Exception:  # noqa: BLE001 - Maintenance reconciles every 5 minutes anyway
        return


@router.post("/oversight/protocols", response_model=O.Protocol, status_code=201, responses=E)
async def add_protocol(body: O.ProtocolIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`oversight.protocol`, target = SHA-256 of the exact body): a new
    protocol, sealed now. Agents propose one through a `protocol` decision.
    Requires `Idempotency-Key`."""
    return await _seal_protocol(ctx, request, body, None, 201)


@router.put("/oversight/protocols/{ref}", response_model=O.Protocol, responses=E)
async def version_protocol(
    ref: str, body: O.ProtocolIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 (`oversight.protocol`, body hash): an edit, a pause (status paused)
    or a resume is a new version. Requires `Idempotency-Key`."""
    return await _seal_protocol(ctx, request, body, ref, 200)


@router.get("/oversight/protocols/{ref}/runs", response_model=list[ProtocolRun], responses=E)
async def protocol_runs(
    ref: str, limit: int = Query(default=50, ge=1, le=200), ctx: Ctx = Depends(owner_ctx)
) -> list[ProtocolRun]:
    """The runs of one protocol, newest first: result, findings, by code or by the overseer."""
    async with ctx.tx() as tx:
        await O.load_protocol(tx, ref)
        rows = await tx.all(
            "SELECT * FROM oversight.protocol_runs WHERE protocol_ref = :r ORDER BY started_at DESC LIMIT :l",
            r=ref,
            l=limit,
        )
        return [_run(r) for r in rows]


@router.get("/oversight/findings", response_model=Page[O.Finding], responses=E)
async def list_findings(
    company: str | None = Query(default=None, pattern=CO),
    status: str | None = Query(default=None, pattern=r"^[a-z]{4,12}$"),
    severity: Literal["info", "low", "medium", "high", "critical"] | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[O.Finding]:
    """Findings, newest first, `?company&status&severity` (cursor page)."""
    at, fid = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            O.FINDING_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                  AND (CAST(:st AS text) IS NULL OR f.status = :st)
                  AND (CAST(:sev AS text) IS NULL OR f.severity = :sev)
                  AND (CAST(:at AS timestamptz) IS NULL
                       OR (f.opened_at, f.id) < (CAST(:at AS timestamptz), CAST(:id AS uuid)))
                ORDER BY f.opened_at DESC, f.id DESC LIMIT :lim""",
            co=company,
            st=status,
            sev=severity,
            at=at,
            id=fid,
            lim=limit + 1,
        )
        items, nxt = pagination.page(
            [{**r, "at": r["opened_at"]} for r in rows], limit, ("at", "id")
        )
        return Page(items=[O.render_finding(r) for r in items], next_cursor=nxt)


@router.get("/oversight/findings/{ref}", response_model=O.Finding, responses=E)
async def get_finding(ref: str, ctx: Ctx = Depends(owner_ctx)) -> O.Finding:
    """One finding with its history (who moved it, when, with what evidence)."""
    async with ctx.tx() as tx:
        f = await O.load_finding(tx, ref)
        return O.render_finding(f, await O.history_of(tx, f["id"]))


@router.post("/oversight/findings/{ref}/status", response_model=O.Finding, responses=E)
async def finding_status(
    ref: str, body: FindingStatusIn, ctx: Ctx = Depends(owner_ctx)
) -> O.Finding:
    """The owner verifies (only with evidence of the fix), closes or disputes."""
    async with ctx.tx() as tx:
        f = await O.update_finding(
            tx, ctx.who, ref, body.status, body.note, [e.model_dump() for e in body.evidence]
        )
        await ctx.audit(
            tx,
            company_id=f["company_id"],
            action="oversight.finding",
            action_class="A2",
            target_kind="finding",
            target_ref=ref,
            summary=body.status,
        )
        return O.render_finding(f, await O.history_of(tx, f["id"]))


@router.get("/oversight/challenges", response_model=Page[O.Challenge], responses=E)
async def list_challenges(
    company: str | None = Query(default=None, pattern=CO),
    period: Literal["week", "month"] | None = None,
    status: Literal["issued", "accepted", "submitted", "scored", "missed"] | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[O.Challenge]:
    """The overseer's challenges, newest first, `?company&period&status` (cursor page)."""
    at, cid = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            O.CHALLENGE_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                  AND (CAST(:p AS text) IS NULL OR ch.period = :p)
                  AND (CAST(:st AS text) IS NULL OR ch.status = :st)
                  AND (CAST(:at AS timestamptz) IS NULL
                       OR (ch.created_at, ch.id) < (CAST(:at AS timestamptz), CAST(:id AS uuid)))
                ORDER BY ch.created_at DESC, ch.id DESC LIMIT :lim""",
            co=company,
            p=period,
            st=status,
            at=at,
            id=cid,
            lim=limit + 1,
        )
        items, nxt = pagination.page(
            [{**r, "at": r["created_at"]} for r in rows], limit, ("at", "id")
        )
        return Page(items=[O.render_challenge(r) for r in items], next_cursor=nxt)


@router.get("/oversight/orders", response_model=list[O.StandingOrder], responses=E)
async def list_standing_orders(ctx: Ctx = Depends(owner_ctx)) -> list[O.StandingOrder]:
    """The owner's standing orders (proposed, sealed, retired)."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM oversight.orders ORDER BY created_at DESC LIMIT 200")
        return [O.render_order(r) for r in rows]


@router.post("/oversight/orders", response_model=O.StandingOrder, status_code=201, responses=E)
async def add_standing_order(body: OrderIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner's standing order (text or a voice transcript), `proposed`
    until sealed; nothing applies before the seal. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        row = await tx.one(
            """INSERT INTO oversight.orders (company_id, text_md, source, file_id, applies_to,
                   created_by_kind, created_by_code)
               VALUES (:co, :t, :s, :f, :a, 'owner', 'owner') RETURNING *""",
            co=holding.id,
            t=body.text_md,
            s=body.source,
            f=body.file_id,
            a=body.applies_to,
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="oversight.order",
            action_class="A1",
            target_kind="order",
            target_ref=row["ref"],
            summary="proposed",
        )
        result = O.render_order(row)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


async def _order_state(
    ctx: Ctx, request: Request, ref: str, state: Literal["sealed", "retired"]
) -> O.StandingOrder:
    async with ctx.tx() as tx:
        o = await tx.one(
            "SELECT * FROM oversight.orders WHERE ref = :r FOR UPDATE", r=ref, not_found="not_found"
        )
        if state == "sealed":
            if o["status"] != "proposed":
                raise ApiError(409, "validation_failed", f"{ref} is {o['status']}")
            su = await stepup.consume(tx, request, ctx.who, "oversight.order", ref)
            row = await tx.one(
                """UPDATE oversight.orders SET status = 'sealed', sealed_at = now(), sealed_step_up_id = :su,
                       updated_at = now() WHERE id = :id RETURNING *""",
                id=o["id"],
                su=su,
            )
        else:
            if o["status"] == "retired":
                return O.render_order(o)
            row = await tx.one(
                """UPDATE oversight.orders SET status = 'retired', retired_at = now(), updated_at = now()
                   WHERE id = :id RETURNING *""",
                id=o["id"],
            )
        await ctx.audit(
            tx,
            company_id=o["company_id"],
            action="oversight.order",
            action_class="A2",
            target_kind="order",
            target_ref=ref,
            summary=state,
            step_up=state == "sealed",
        )
        return O.render_order(row)


@router.post("/oversight/orders/{ref}/seal", response_model=O.StandingOrder, responses=E)
async def seal_standing_order(
    ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> O.StandingOrder:
    """🔏 (`oversight.order`, target = ref): from now in the overseer's system
    prompt (applies_to overseer) or every role's (all)."""
    return await _order_state(ctx, request, ref, "sealed")


@router.post("/oversight/orders/{ref}/retire", response_model=O.StandingOrder, responses=E)
async def retire_standing_order(
    ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> O.StandingOrder:
    """The order stops applying from the next run (no step-up)."""
    return await _order_state(ctx, request, ref, "retired")


@router.get("/oversight/holds", response_model=list[O.Hold], responses=E)
async def list_holds(
    state: Literal["held", "released", "cancelled"] | None = None, ctx: Ctx = Depends(owner_ctx)
) -> list[O.Hold]:
    """Holds, newest first, `?state=held` for the ones waiting for the owner."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            O.HOLD_SQL
            + " WHERE (CAST(:s AS text) IS NULL OR h.state = :s) ORDER BY h.held_at DESC LIMIT 200",
            s=state,
        )
        return [O.render_hold(r) for r in rows]


async def _decide_hold(
    ctx: Ctx, request: Request, ref: str, state: Literal["released", "cancelled"], note: str | None
) -> O.Hold:
    async with ctx.tx() as tx:
        su = (
            await stepup.consume(tx, request, ctx.who, "oversight.release", ref)
            if state == "released"
            else None
        )
        h = await O.decide_hold(tx, ctx.who, ref, state, note, su)
        await ctx.audit(
            tx,
            company_id=h["company_id"],
            action=f"oversight.hold_{'release' if state == 'released' else 'cancel'}",
            action_class="A2",
            target_kind=h["target_kind"],
            target_ref=h["target_ref"],
            summary=ref
            + "".join(f" {k}={v}" for k, v in (h.get("cancelled") or {}).items())[:200],
            step_up=su is not None,
        )
    # After the commit: the runtime follows the record (a released session goes
    # on or starts; a cancelled one stops), and a rejected card's lifecycle ends.
    if h["target_kind"] == "session" and h.get("session") is not None:
        if state == "released":
            await workshop_service.overseer_released(ctx.hub, h["session"])
        else:
            await workshop_service.stopped(ctx.hub, [h["session"]])
    if (h.get("cancelled") or {}).get("decision") == "rejected":
        from hq_api import workflows_client

        await workflows_client.decision_decided(ctx.hub, h["target_ref"])
    return O.render_hold(h)


@router.post("/oversight/holds/{ref}/release", response_model=O.Hold, responses=E)
async def release_hold(
    ref: str, request: Request, body: NoteIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> O.Hold:
    """🔏 (`oversight.release`, target = ref): the held action may go on (a
    held decision can now be decided; its effect runs; a held workshop session
    goes on, or starts if it never had)."""
    return await _decide_hold(ctx, request, ref, "released", body.note if body else None)


@router.post("/oversight/holds/{ref}/cancel", response_model=O.Hold, responses=E)
async def cancel_hold(
    ref: str, request: Request, body: NoteIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> O.Hold:
    """No step-up: the held action itself is cancelled (contract §18.15) and
    never runs: a pending card is rejected (by the owner, «لغو از hold»), a
    queued effect is cancelled, a workshop session is stopped, a work item is
    cancelled. Like release, only the owner can."""
    return await _decide_hold(ctx, request, ref, "cancelled", body.note if body else None)


@router.get("/oversight/watch", response_model=O.WatchReport, responses=E)
async def get_watch(ctx: Ctx = Depends(owner_ctx)) -> O.WatchReport:
    """The current watch report, or the last one ("while you were away")."""
    async with ctx.tx() as tx:
        return await O.watch_report(tx)


@router.post("/oversight/watch", response_model=O.WatchReport, responses=E)
async def set_watch(body: WatchIn, ctx: Ctx = Depends(owner_ctx)) -> O.WatchReport:
    """⟨additive⟩ The owner puts the overseer on watch (or ends it) by hand."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        w = await O.open_watch(tx)
        if body.on and w is None:
            await O.start_watch(tx, holding.id, holding.code, "owner")
        elif not body.on and w is not None:
            await O.end_watch(tx, w, holding.code)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="oversight.watch",
            action_class="A2",
            target_kind="watch",
            target_ref="on" if body.on else "off",
        )
        return await O.watch_report(tx)


@router.get("/oversight/compliance", response_model=list[O.Compliance], responses=E)
async def compliance(ctx: Ctx = Depends(owner_ctx)) -> list[O.Compliance]:
    """Compliance per operating company (0..100, by area, open findings, trend)."""
    async with ctx.tx() as tx:
        ids = [
            c.id
            for c in await ctx.hub.companies.all()
            if c.kind != "holding" and c.status == "active"
        ]
        return await O.compliance_of(tx, ids)


# --------------------------------------------------------------- internal --
@asynccontextmanager
async def _tx_with(ctx: Ctx, company_id: UUID) -> AsyncIterator[Tx]:
    """A write transaction over the agent's own company and the target's (the
    overseer acts on every company; RLS still scopes it to these two)."""
    assert ctx.who.company_id is not None
    async with ctx.hub.db.tx(list({ctx.who.company_id, company_id})) as tx:
        yield tx


def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


class FindingRaiseIn(Model):
    company: str = Field(pattern=CO)
    protocol: str | None = Field(default=None, pattern=r"^PR-[0-9]{3,}$")
    severity: Literal["info", "low", "medium", "high", "critical"]
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(default="", max_length=20000)
    evidence: list[O.Evidence] = Field(default_factory=list, max_length=20)
    answerable: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]{2,64}$")
    due_in_hours: int | None = Field(default=None, ge=1, le=24 * 30)


class FindingUpdateIn(Model):
    status: Literal["acknowledged", "fixing", "fixed", "disputed", "verified", "closed"]
    note: str = Field(default="", max_length=5000)
    evidence: list[O.Evidence] = Field(default_factory=list, max_length=20)


class ProtocolResultIn(Model):
    protocol: str = Field(pattern=r"^PR-[0-9]{3,}$")
    result: Literal["pass", "fail", "partial"]
    findings: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=20000)


class ChallengeIn(Model):
    company: str = Field(pattern=CO)
    period: Literal["week", "month"] = "week"
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=20000)
    criteria: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    due_at: datetime
    judge: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$")


class SubmitIn(Model):
    work_ref: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")
    note: str = Field(default="", max_length=5000)


class ScoreIn(Model):
    score: int = Field(ge=0, le=100)
    notes: str = Field(default="", max_length=5000)


class HoldTarget(Model):
    kind: Literal["decision", "session", "work", "employee", "tool", "story"]
    ref: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")


class HoldIn(Model):
    target: HoldTarget
    reason_md: str = Field(min_length=1, max_length=5000)


class EngageIn(Model):
    scope: str = Field(pattern=r"^company:[A-Z][A-Z0-9]{1,9}$")
    reason: str = Field(min_length=1, max_length=1000)


class FreezeIn(Model):
    company: str = Field(pattern=CO)
    until: datetime
    reason: str = Field(min_length=1, max_length=1000)


@internal_router.post(
    "/oversight/findings", response_model=O.Finding, status_code=201, responses=EI
)
async def raise_finding(
    body: FindingRaiseIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """finding.raise: the overseer, QC and the oversight specialists, on any company."""
    _agent(ctx)
    await allow(
        ctx, "oversight.finding_raise", {"company": body.company, "severity": body.severity}
    )
    company = await ctx.hub.companies.by_code(body.company)
    async with _tx_with(ctx, company.id) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        protocol = await O.load_protocol(tx, body.protocol) if body.protocol else None
        f, _ = await O.raise_finding(
            tx,
            company_id=company.id,
            company_code=company.code,
            severity=body.severity,
            title_fa=scrub(body.title_fa),
            body_md=await scrub_async(body.body_md),
            evidence=[e.model_dump() for e in body.evidence],
            protocol=protocol,
            answerable=body.answerable,
            due_in_hours=body.due_in_hours,
            by_kind="agent",
            by_code=ctx.who.code,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="oversight.finding_raise",
            action_class="A1",
            target_kind="finding",
            target_ref=f["ref"],
            summary=body.severity,
        )
        result = O.render_finding(f)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@internal_router.post("/oversight/findings/{ref}/status", response_model=O.Finding, responses=EI)
async def update_finding(
    ref: str, body: FindingUpdateIn, ctx: Ctx = Depends(internal_ctx)
) -> O.Finding:
    """finding.update: the answerable moves it; the overseer verifies (with
    evidence of the fix) and closes."""
    _agent(ctx)
    holding = await ctx.hub.companies.holding()
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as probe:
        row = await probe.first(
            "SELECT c.code FROM oversight.findings f JOIN core.companies c ON c.id = f.company_id WHERE f.ref = :r",
            r=ref,
        )
    target = str(row["code"] if row else ctx.who.company)
    await allow(ctx, "oversight.finding_update", {"company": target, "status": body.status})
    if row is None:
        raise ApiError(403, "policy_denied", "not this agent's finding")
    company = await ctx.hub.companies.by_code(target)
    async with _tx_with(ctx, company.id if company else holding.id) as tx:
        f = await O.update_finding(
            tx,
            ctx.who,
            ref,
            body.status,
            await scrub_async(body.note),
            [e.model_dump() for e in body.evidence],
        )
        await ctx.audit(
            tx,
            company_id=f["company_id"],
            action="oversight.finding_update",
            action_class="A2",
            target_kind="finding",
            target_ref=ref,
            summary=body.status,
        )
        return O.render_finding(f)


@internal_router.post("/oversight/protocol-runs/result", response_model=ProtocolRun, responses=EI)
async def protocol_result(body: ProtocolResultIn, ctx: Ctx = Depends(internal_ctx)) -> ProtocolRun:
    """protocol.result: the overseer's (or QC's) result of the protocol run
    handed to it; the findings it raised are linked by ref. A protocol that is
    not active takes no result (409). Every company the protocol covers gets
    its pass or fail (compliance counts both, contract §18.15)."""
    _agent(ctx)
    await allow(ctx, "oversight.protocol_result", {"protocol": body.protocol})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        protocol = await O.load_protocol(tx, body.protocol)
        O.require_active(protocol)
        run = await tx.first(
            """SELECT r.id FROM oversight.protocol_runs r LEFT JOIN work.work w ON w.id = r.work_id
               LEFT JOIN core.employees e ON e.id = w.assignee_id
               WHERE r.protocol_ref = :p AND r.result = 'pending' AND (e.code = :me OR r.work_id IS NULL)
               ORDER BY r.started_at DESC LIMIT 1 FOR UPDATE OF r""",
            p=body.protocol,
            me=ctx.who.code,
        )
        if run is None:
            run = await O.start_run(tx, protocol, by_kind="agent", by_code=ctx.who.code)
        mine: list[str] = []
        if body.findings:
            # Only findings of this protocol, or raised by this agent (§4).
            rows = await tx.all(
                """SELECT f.ref, c.code FROM oversight.findings f
                   JOIN core.companies c ON c.id = f.company_id
                   WHERE f.ref = ANY(:r)
                     AND (f.protocol_id IN (SELECT id FROM oversight.protocols WHERE ref = :p)
                          OR (f.raised_by_kind = 'agent' AND f.raised_by_code = :me))""",
                r=body.findings,
                p=body.protocol,
                me=ctx.who.code,
            )
            unknown = sorted(set(body.findings) - {r["ref"] for r in rows})
            if unknown:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={"findings": f"not of {body.protocol} nor yours: {', '.join(unknown)[:200]}"},
                )
            mine = [r["code"] for r in rows]
            await tx.exec(
                "UPDATE oversight.findings SET updated_at = now() WHERE ref = ANY(:r)",
                r=body.findings,
            )
        covered = await _covered(ctx, protocol)
        per_company = O.per_company_result(body.result, covered, mine)
        done = await O.finish_run(
            tx,
            run["id"],
            body.result,
            findings=len(body.findings),
            per_company=per_company,
            notes=await scrub_async(body.notes),
            by=("agent", ctx.who.code),
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,  # type: ignore[arg-type]
            action="oversight.protocol_result",
            action_class="A2",
            target_kind="protocol",
            target_ref=body.protocol,
            summary=body.result,
        )
        return _run(done)


async def _covered(ctx: Ctx, protocol: dict[str, Any]) -> list[str]:
    """The companies a protocol's run looks at: the holding for a holding
    protocol, every active operating company otherwise."""
    companies = await ctx.hub.companies.all()
    if protocol["scope"] == "holding":
        return [c.code for c in companies if c.kind == "holding"]
    return [c.code for c in companies if c.kind != "holding" and c.status == "active"]


@internal_router.post(
    "/oversight/challenges", response_model=O.Challenge, status_code=201, responses=EI
)
async def issue_challenge(
    body: ChallengeIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """challenge.issue (the overseer): a challenge to one company."""
    _agent(ctx)
    await allow(ctx, "oversight.challenge_issue", {"company": body.company})
    company = await ctx.hub.companies.by_code(body.company)
    async with _tx_with(ctx, company.id) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        ch = await O.issue_challenge(
            tx,
            ctx.who,
            company_id=company.id,
            company_code=company.code,
            period=body.period,
            title_fa=scrub(body.title_fa),
            brief_md=await scrub_async(body.brief_md),
            criteria=body.criteria,
            due_at=body.due_at,
            judge=body.judge,
            tz=await _tz(tx),
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="oversight.challenge_issue",
            action_class="A2",
            target_kind="challenge",
            target_ref=ch["ref"],
        )
        result = O.render_challenge(ch)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@internal_router.post(
    "/oversight/challenges/{ref}/submit", response_model=O.Challenge, responses=EI
)
async def submit_challenge(
    ref: str, body: SubmitIn, ctx: Ctx = Depends(internal_ctx)
) -> O.Challenge:
    """challenge.submit (the company's CEO)."""
    _agent(ctx)
    await allow(ctx, "oversight.challenge_submit", {"company": ctx.who.company})
    async with ctx.tx() as tx:
        work_id = None
        if body.work_ref:
            work_id = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=body.work_ref)
            if work_id is None:
                raise ApiError(
                    422, "validation_failed", fields={"work_ref": "unknown in this company"}
                )
        ch = await O.submit_challenge(tx, ctx.who, ref, work_id, await scrub_async(body.note))
        await ctx.audit(
            tx,
            company_id=ch["company_id"],
            action="oversight.challenge_submit",
            action_class="A1",
            target_kind="challenge",
            target_ref=ref,
        )
        return O.render_challenge(ch)


@internal_router.post("/oversight/challenges/{ref}/score", response_model=O.Challenge, responses=EI)
async def score_challenge(ref: str, body: ScoreIn, ctx: Ctx = Depends(internal_ctx)) -> O.Challenge:
    """challenge.score (the judge: the overseer or QC)."""
    _agent(ctx)
    await allow(ctx, "oversight.challenge_score", {"challenge": ref})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        ch = await O.score_challenge(tx, ctx.who, ref, body.score, await scrub_async(body.notes))
        await ctx.audit(
            tx,
            company_id=ch["company_id"],
            action="oversight.challenge_score",
            action_class="A2",
            target_kind="challenge",
            target_ref=ref,
            summary=str(body.score),
        )
        return O.render_challenge(ch)


@internal_router.post("/oversight/holds", response_model=O.Hold, status_code=201, responses=EI)
async def place_hold(body: HoldIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """hold: the overseer, QC and the security analyst stop an action until
    the owner decides. Only the owner releases (no agent route exists)."""
    _agent(ctx)
    await allow(ctx, "oversight.hold", {"kind": body.target.kind})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        h, _ = await O.place_hold(
            tx,
            kind=body.target.kind,
            ref=body.target.ref,
            reason_md=await scrub_async(body.reason_md),
            by_kind="agent",
            by_code=ctx.who.code,
        )
        await ctx.audit(
            tx,
            company_id=h["company_id"],
            action="oversight.hold",
            action_class="A2",
            target_kind=body.target.kind,
            target_ref=body.target.ref,
            summary=h["ref"],
        )
        result = O.render_hold(h)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    if body.target.kind == "session":
        # Interrupted at once on its runtime (contract §18.15).
        await workshop_service.overseer_held(ctx.hub, h.get("session"))
    return result


@internal_router.post("/oversight/kill-switch", response_model=control.ControlState, responses=EI)
async def engage_kill_switch(
    body: EngageIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """kill_switch.engage: the overseer, any company; a CEO, its own. Engage
    only: releasing is the owner's (public API, 🔏)."""
    _agent(ctx)
    company_code = body.scope.split(":", 1)[1]
    company = await ctx.hub.companies.by_code(company_code)
    async with _tx_with(ctx, company.id) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        target = await control.resolve_scope(tx, body.scope)
        current = await control.current_switch(tx, target["id"], lock=True)
        await allow(
            ctx, "kill_switch.set", {"scope": body.scope, "state": "engaged", "current": current}
        )
        changed = await control.set_kill_switch(
            tx, ctx.who, target, "engaged", await scrub_async(body.reason)
        )
        await ctx.audit(
            tx,
            company_id=target["id"],
            action="kill_switch.engage",
            action_class="A2",
            target_kind="kill_switch",
            target_ref=body.scope,
            summary=("changed" if changed else "unchanged") + f" by {ctx.who.code}",
        )
        result = await control.state(tx)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workshop_service.paused(ctx.hub)
    return result


@internal_router.post("/oversight/deploy-freeze", response_model=control.ControlState, responses=EI)
async def freeze_deploys(body: FreezeIn, ctx: Ctx = Depends(internal_ctx)) -> control.ControlState:
    """deploy.freeze (the overseer): any company, until a future time. Lifting
    a freeze the overseer set is the owner's (public API)."""
    _agent(ctx)
    if body.until <= datetime.now(UTC):
        raise ApiError(
            422, "validation_failed", fields={"until": "in the future (lifting is the owner's)"}
        )
    await allow(ctx, "deploy_freeze.set", {"company": body.company, "lift": False, "freeze": None})
    company = await ctx.hub.companies.by_code(body.company)
    async with _tx_with(ctx, company.id) as tx:
        target = await control.resolve_scope(tx, f"company:{body.company}")
        await control.add_deploy_freeze(
            tx, ctx.who, target, body.until, await scrub_async(body.reason)
        )
        await ctx.audit(
            tx,
            company_id=target["id"],
            action="deploy_freeze.set",
            action_class="A2",
            target_kind="company",
            target_ref=body.company,
            summary=f"active by {ctx.who.code}",
        )
        result = await control.state(tx)
    await workshop_service.paused(ctx.hub)
    return result
