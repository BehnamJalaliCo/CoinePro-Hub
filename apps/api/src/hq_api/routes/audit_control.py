"""Audit (contract §8) and control (§9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import audit, idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import control
from hq_api.errors import responses
from hq_api.schemas import Actor, Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["audit and control"])
E = responses(401, 403, 404, 409, 422)


class AuditEntry(BaseModel):
    seq: int
    at: datetime
    actor: Actor
    principal_kind: str
    company: str
    action: str
    action_class: str
    target: dict[str, str]
    request_id: str | None
    ip_hash: str | None
    step_up: bool
    summary: str
    prev_hash: str
    hash: str


class Verify(BaseModel):
    ok: bool
    checked: int
    first_bad_seq: int | None
    verified_at: datetime


class KillSwitchIn(Model):
    scope: str = Field(pattern=r"^(holding|company:[A-Z][A-Z0-9]{1,9})$")
    state: Literal["engaged", "released"]
    reason: str = Field(min_length=1, max_length=1000)


class FreezeIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    until: datetime
    reason: str = Field(min_length=1, max_length=1000)


class FreezeOut(BaseModel):
    company: str
    active: bool
    until: datetime


@router.get("/audit", response_model=Page[AuditEntry], responses=E)
async def list_audit(
    company: list[str] | None = Query(default=None),
    actor: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    action_class: Literal["A0", "A1", "A2", "A3", "A4"] | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[AuditEntry]:
    """Newest first. Only references and short summaries, never bodies or secrets."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT a.*, c.code AS company FROM audit.entries a JOIN core.companies c ON c.id = a.company_id
               WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                 AND (CAST(:actor AS text) IS NULL OR a.actor_code = :actor)
                 AND (CAST(:action AS text) IS NULL OR a.action = :action)
                 AND (CAST(:cls AS text) IS NULL OR a.action_class = :cls)
                 AND (CAST(:from_ AS timestamptz) IS NULL OR a.at >= :from_)
                 AND (CAST(:to_ AS timestamptz) IS NULL OR a.at < :to_)
                 AND (CAST(:after AS bigint) IS NULL OR a.seq < :after)
               ORDER BY a.seq DESC LIMIT :lim""",
            companies=company,
            actor=actor,
            action=action,
            cls=action_class,
            from_=from_,
            to_=to,
            after=after[0] if after else None,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("seq",))
    return Page(
        items=[
            AuditEntry(
                seq=r["seq"],
                at=r["at"],
                actor=Actor(kind=r["actor_kind"], code=r["actor_code"]),
                principal_kind=r["principal_kind"],
                company=r["company"],
                action=r["action"],
                action_class=r["action_class"],
                target={"kind": r["target_kind"], "ref": r["target_ref"]},
                request_id=r["request_id"],
                ip_hash=r["ip_hash"],
                step_up=r["step_up"],
                summary=r["summary"],
                prev_hash=r["prev_hash"],
                hash=r["hash"],
            )
            for r in items
        ],
        next_cursor=nxt,
    )


@router.get("/audit/verify", response_model=Verify, responses=E)
async def verify_audit(ctx: Ctx = Depends(owner_ctx)) -> Verify:
    """Recomputes the whole hash chain (every company)."""
    async with ctx.tx() as tx:
        r = await audit.verify(tx)
        at = await tx.scalar("SELECT now()")
    return Verify(
        ok=r["ok"], checked=r["checked"], first_bad_seq=r["first_bad_seq"], verified_at=at
    )


@router.get("/control/state", response_model=control.ControlState, responses=E)
async def control_state(ctx: Ctx = Depends(owner_ctx)) -> control.ControlState:
    """Kill switches and deploy freezes of the holding and every company."""
    async with ctx.tx() as tx:
        return await control.state(tx)


@router.post("/control/kill-switch", response_model=control.ControlState, responses=E)
async def set_kill_switch(
    body: KillSwitchIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Engage needs no step-up (speed matters); release is 🔏 (`kill_switch.release`,
    target = the scope). Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        company = await control.resolve_scope(tx, body.scope)
        step = False
        if body.state == "released":
            await stepup.consume(tx, request, ctx.who, "kill_switch.release", body.scope)
            step = True
        changed = await control.set_kill_switch(tx, ctx.who, company, body.state, body.reason)
        await ctx.audit(
            tx,
            company_id=company["id"],
            action=f"kill_switch.{'engage' if body.state == 'engaged' else 'release'}",
            action_class="A2",
            target_kind="kill_switch",
            target_ref=body.scope,
            summary=("changed" if changed else "unchanged") + f": {body.state}",
            step_up=step,
        )
        await ctx.interaction(
            tx,
            company_id=company["id"],
            kind="control",
            action="kill_switch.set",
            target_kind="kill_switch",
            target_ref=body.scope,
            data={"state": body.state, "reason": body.reason},
        )
        result = await control.state(tx)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@router.post("/control/deploy-freeze", response_model=FreezeOut, responses=E)
async def set_deploy_freeze(body: FreezeIn, ctx: Ctx = Depends(owner_ctx)) -> FreezeOut:
    """Freezes agent write actions of one company until `until` (§1.5 #5);
    a past `until` lifts the freeze."""
    async with ctx.tx() as tx:
        company = await control.resolve_scope(tx, f"company:{body.company}")
        r = await control.set_deploy_freeze(tx, ctx.who, company, body.until, body.reason)
        await ctx.audit(
            tx,
            company_id=company["id"],
            action="deploy_freeze.set",
            action_class="A2",
            target_kind="company",
            target_ref=body.company,
            summary="active" if r["active"] else "lifted",
        )
        await ctx.interaction(
            tx,
            company_id=company["id"],
            kind="control",
            action="deploy_freeze.set",
            target_kind="company",
            target_ref=body.company,
            data={"until": body.until.isoformat(), "reason": body.reason},
        )
    return FreezeOut(company=body.company, active=r["active"], until=body.until)
