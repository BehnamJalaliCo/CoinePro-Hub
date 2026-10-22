"""Company founding and server provisioning (prompt 09, contract §18.8).

Owner:   /foundings, /provisioning/plans (+ /seal 🔏 on the digest),
         /provisioning/runs/{id} (+ /live SSE, /resume), /infra/servers
Public:  POST /provisioning/callback, the new server's one report (its
         one-time token as Bearer; nothing else is public here)
Agents:  POST /internal/v1/provisioning/plans (server.plan)
Service: /internal/v1/provisioning/runs/* (the provisioner only)
There is no delete and no rebuild anywhere: the owner removes a server in
the Hetzner console.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field, model_validator

from hq_api import idempotency
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import founding as F
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import deps, stepup
from hq_common.tokens import bearer

log = logging.getLogger("hq_api.founding")
router = APIRouter(tags=["founding"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
POLL_S = 1.0
HEARTBEAT_S = 15.0
CALLBACK_MAX_BYTES = 256 * 1024


def _transport(ctx: Ctx) -> Any:
    return getattr(ctx.hub, "provisioner_transport", None)  # tests: a fake provisioner


async def _wake(ctx: Ctx) -> None:
    url = ctx.hub.settings.provisioner_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(
            base_url=url, timeout=5, transport=_transport(ctx), trust_env=False
        ) as c:
            await c.post("/v1/wake")
    except httpx.HTTPError:
        log.info("provisioner not woken (it polls anyway)")


# ----------------------------------------------------------------- inputs --
class Source(Model):
    kind: Literal["repo", "idea"]
    repo: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
    brief_md: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def _shape(self) -> Source:
        if self.kind == "repo" and not self.repo:
            raise ValueError("a repo source needs repo (owner/name)")
        if self.kind == "idea" and not self.brief_md.strip():
            raise ValueError("an idea needs brief_md")
        return self


class FoundingIn(Model):
    source: Source


class PlanIn(Model):
    """server.plan: a new plan, or a new version of one (`ref`)."""

    ref: str | None = Field(default=None, pattern=r"^PV-[0-9]{4,}$")
    founding: str | None = Field(default=None, pattern=r"^C-[0-9]{4,}$")
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    name: str = Field(min_length=1, max_length=63)
    type: str = Field(min_length=2, max_length=10)
    location: str = Field(min_length=2, max_length=10)
    private_network: bool = False
    firewall: list[F.FirewallRule] = Field(default_factory=list, max_length=50)
    software: list[str] = Field(min_length=1, max_length=20)
    work_user: str = Field(min_length=2, max_length=32)
    repo: str | None = Field(default=None, max_length=200)

    def fields(self) -> F.PlanFields:
        return F.PlanFields.model_validate(self.model_dump(exclude={"ref", "founding", "company"}))


class CallbackToken(Model):
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime


class StepIn(Model):
    key: str = Field(max_length=40)
    state: Literal["running", "done", "failed"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_tail: list[str] = Field(default_factory=list, max_length=50)


class ServerIn(Model):
    hetzner_id: int = Field(ge=1)
    name: str = Field(max_length=63)
    ipv4: str | None = Field(default=None, max_length=45)
    ipv6: str | None = Field(default=None, max_length=64)
    private_ip: str | None = Field(default=None, max_length=45)
    labels: dict[str, str] = Field(default_factory=dict)


class FinishIn(Model):
    state: Literal["done", "failed"]
    login: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class InfraServer(Model):
    hetzner_id: int
    company: str
    plan: str
    name: str
    ipv4: str | None
    ipv6: str | None
    private_ip: str | None
    labels: dict[str, str]
    created_at: datetime


class Inventory(Model):
    fetched_at: datetime | None
    ok: bool | None
    error: str | None = None
    servers: list[dict[str, Any]] = Field(default_factory=list)


class InfraServers(Model):
    items: list[InfraServer]
    # ⟨additive⟩ the latest listing of the Hetzner project (PR-063 reads it)
    inventory: Inventory


# -------------------------------------------------------------- foundings --
@router.get("/foundings", response_model=list[F.Founding], responses=E)
async def list_foundings(
    state: str | None = Query(default=None, max_length=20), ctx: Ctx = Depends(owner_ctx)
) -> list[F.Founding]:
    """Newest first."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            F.FOUNDING_SQL
            + " WHERE (CAST(:s AS text) IS NULL OR f.state = :s) ORDER BY f.created_at DESC LIMIT 200",
            s=state,
        )
        return [await F.render(tx, r) for r in rows]


@router.post("/foundings", response_model=F.Founding, status_code=201, responses=E)
async def create_founding(body: FoundingIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Opens the read-only audit of the repository (a workshop session under an
    automatic read-only grant once a runtime exists; else github.read and
    reading, no execution), or for an idea the proposal straight away.
    Requires `Idempotency-Key`."""
    from hq_api.workshop import service as workshop

    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        f = await F.create(
            tx,
            ctx.who,
            body.source.model_dump(exclude_none=True),
            runtime_on=workshop.meta_runtime(ctx.hub) is not None
            or getattr(ctx.hub, "workshop", None) is not None,
        )
        out = await F.render(tx, f)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/foundings/{ref}", response_model=F.Founding, responses=E)
async def get_founding(ref: str, ctx: Ctx = Depends(owner_ctx)) -> F.Founding:
    """One founding with its audit, proposal, card and server plan."""
    async with ctx.tx() as tx:
        return await F.render(tx, await F.load(tx, ref))


@router.post("/foundings/{ref}/cancel", response_model=F.Founding, responses=E)
async def cancel_founding(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Before it is active; a company already made stays (paused), never
    deleted. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        f = await F.cancel(tx, ctx.who, await F.load(tx, ref, lock=True))
        out = await F.render(tx, f)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


class ActivateIn(Model):
    """⟨1.4.6⟩ `skip_brand`: activate a company whose brand is not sealed yet."""

    skip_brand: bool = False


@router.post("/foundings/{ref}/activate", response_model=F.Founding, responses=E)
async def activate_founding(
    ref: str, request: Request, body: ActivateIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 step-up `founding.activate`, target = the ref: after the owner logged
    in on the new server, the company goes live and its CEO starts. ⟨1.4.6⟩
    Without an active brand: `409 not_ready` with `missing: ["brand"]`,
    unless the body says `{skip_brand: true}`."""
    skip = bool(body and body.skip_brand)
    async with ctx.tx() as tx:
        f = await F.load(tx, ref, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "founding.activate", ref)
        out = await F.render(tx, await F.activate(tx, ctx.who, f, step_up_id=su, skip_brand=skip))
    ctx.hub.companies.invalidate()
    return out


# ------------------------------------------------------------------ plans --
@router.get("/provisioning/plans", response_model=list[F.ServerPlan], responses=E)
async def list_plans(
    state: str | None = Query(default=None, max_length=20),
    company: str | None = Query(default=None, max_length=10),
    ctx: Ctx = Depends(owner_ctx),
) -> list[F.ServerPlan]:
    """Server plans, newest first."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            F.PLAN_SQL
            + """ WHERE (CAST(:s AS text) IS NULL OR p.state = :s)
                    AND (CAST(:c AS text) IS NULL OR p.company_code = :c)
                  ORDER BY p.created_at DESC LIMIT 200""",
            s=state,
            c=company,
        )
    return [F.render_plan(r) for r in rows]


@router.get("/provisioning/plans/{ref}", response_model=F.ServerPlan, responses=E)
async def get_plan(ref: str, ctx: Ctx = Depends(owner_ctx)) -> F.ServerPlan:
    """The plan with its digest (the step-up target of its seal) and what
    stops a seal. A proposed plan without a price gets one first, if the
    provisioner is on (the digest then changes, before the owner sees it)."""
    async with ctx.tx() as tx:
        row = await F.load_plan(tx, ref)
        if (
            row["state"] == "proposed"
            and row["monthly_eur"] is None
            and ctx.hub.settings.provisioner_url
        ):
            price = await F.price_of(
                ctx.hub.settings.provisioner_url, row["type"], row["location"], _transport(ctx)
            )
            if price[0] is not None:
                row = await F.save_plan(
                    tx,
                    ctx.who,
                    F.PlanFields.model_validate({k: row[k] for k in F.PlanFields.model_fields}),
                    company_id=row["company_id"],
                    company_code=row["company_code"],
                    founding_id=row["founding_id"],
                    ref=ref,
                    price=price,
                )
        return F.render_plan(row)


@router.post("/provisioning/plans/{ref}/seal", response_model=F.ServerPlan, responses=E)
async def seal_plan(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 step-up `provision.seal`, target = the plan's `digest` (recomputed
    here: a plan changed after the owner saw it cannot be sealed with that
    step-up). The A3 seal that spends money; the provisioner builds it."""
    async with ctx.tx() as tx:
        row = await F.load_plan(tx, ref, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "provision.seal", row["digest"])
        out = F.render_plan(await F.seal(tx, ctx.who, row, step_up_id=su))
    await _wake(ctx)
    return out


# ------------------------------------------------------------------- runs --
@router.get("/provisioning/runs/{id}", response_model=F.ProvisionRun, responses=E)
async def get_provision_run(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> F.ProvisionRun:
    """A build of a sealed plan: its steps (with a short log each), the server and the login."""
    async with ctx.tx() as tx:
        return F.render_run(await F.load_run(tx, id))


@router.post("/provisioning/runs/{id}/resume", response_model=F.ProvisionRun, responses=E)
async def resume_provision_run(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨additive⟩ A failed run continues from its first step not done (the
    same sealed plan; nothing is made twice). Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        run = await F.load_run(tx, id, lock=True)
        await F.resume(tx, ctx.who, run)
        out = F.render_run(await F.load_run(tx, id))
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    await _wake(ctx)
    return out


def _sse(r: dict[str, Any]) -> str:
    data = {"seq": r["seq"], "at": r["at"].isoformat(), "key": r["key"], "state": r["state"],
            "log_tail": r["log_tail"]}  # fmt: skip
    return (
        f"id: {r['seq']}\nevent: provision.step\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


@router.get("/provisioning/runs/{id}/live", responses=E)
async def run_live(
    id: UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """SSE of the run's step events (`id:` = seq); resumes after
    `Last-Event-ID`; ends when the run is done or failed."""
    try:
        after = max(0, int(last_event_id or 0))
    except ValueError:
        after = 0
    async with ctx.tx() as tx:
        await F.load_run(tx, id)
    hub, scope = ctx.hub, await ctx.scope()

    async def stream() -> AsyncIterator[str]:
        seq, idle = after, 0.0
        yield ": live\n\n"
        while True:
            if await request.is_disconnected():
                return
            async with hub.db.tx(scope) as tx:
                rows = await tx.all(
                    "SELECT * FROM provisioning.run_events WHERE run_id = :r AND seq > :a ORDER BY seq LIMIT 200",
                    r=id,
                    a=seq,
                )
                state = await tx.scalar("SELECT state FROM provisioning.runs WHERE id = :r", r=id)
            for r in rows:
                seq = r["seq"]
                yield _sse(r)
            if not rows and state in ("done", "failed"):
                return
            if rows:
                idle = 0.0
                continue
            await asyncio.sleep(POLL_S)
            idle += POLL_S
            if idle >= HEARTBEAT_S:
                idle = 0.0
                yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ infra --
@router.get("/infra/servers", response_model=InfraServers, responses=E)
async def infra_servers(ctx: Ctx = Depends(owner_ctx)) -> InfraServers:
    """Read-only: the servers the provisioner made, and the latest listing of
    the Hetzner project (refreshed here while the provisioner is on). There is
    no delete: the owner removes a server in the Hetzner console."""
    async with ctx.tx() as tx:
        await F.refresh_inventory(tx, ctx.hub.settings.provisioner_url, _transport(ctx))
        rows = await tx.all(
            """SELECT s.*, p.ref AS plan_ref, p.company_code FROM infra.servers s
               JOIN provisioning.plans p ON p.id = s.plan_id ORDER BY s.created_at DESC LIMIT 500"""
        )
        inv = await tx.first("SELECT * FROM infra.inventory ORDER BY fetched_at DESC LIMIT 1")
    return InfraServers(
        items=[
            InfraServer(
                hetzner_id=r["hetzner_id"],
                company=r["company_code"],
                plan=r["plan_ref"],
                name=r["name"],
                ipv4=r["ipv4"],
                ipv6=r["ipv6"],
                private_ip=r["private_ip"],
                labels=r["labels"] or {},
                created_at=r["created_at"],
            )
            for r in rows
        ],
        inventory=Inventory(
            fetched_at=inv["fetched_at"] if inv else None,
            ok=inv["ok"] if inv else None,
            error=inv["error"] if inv else None,
            servers=list(inv["servers"] or []) if inv else [],
        ),
    )


# -------------------------------------------------------------- callback --
@router.post("/provisioning/callback", status_code=204, responses=responses(401, 413))
async def provisioning_callback(request: Request) -> Response:
    """Public, the new server's single report (cloud-init's last step), with
    its one-time token as `Authorization: Bearer` (never in the URL: it would
    be in the access log). Valid 60 minutes, once; anything else is 401."""
    hub = request.app.state.hub
    hub.limiter.check(f"provision-callback:{deps.ip_hash(request)}", 30)
    token = bearer(request.headers.get("authorization"))
    raw = await request.body()
    if len(raw) > CALLBACK_MAX_BYTES:
        raise ApiError(413, "validation_failed", "report too large")
    if not token or len(token) > 200:
        raise ApiError(401, "unauthenticated")
    try:
        body = json.loads(raw or b"{}")
    except ValueError as exc:
        raise ApiError(401, "unauthenticated") from exc
    if not isinstance(body, dict):
        raise ApiError(401, "unauthenticated")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if not await F.callback(tx, token, body):
            raise ApiError(401, "unauthenticated")
    return Response(status_code=204)


# ------------------------------------------------------- agents: server.plan --
@internal_router.post(
    "/provisioning/plans", response_model=F.ServerPlan, status_code=201, responses=E
)
async def agent_server_plan(
    body: PlanIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """server.plan (A1; a CTO for its company, the platform SRE for any and for
    a founding): a plan with its cost; the owner seals it, the provisioner (code,
    not an agent) builds it. A founding's plan waits for the company to exist."""
    await allow(ctx, "provisioning.plan", {"company": body.company, "founding": body.founding})
    hub = ctx.hub
    async with hub.db.tx(await hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        founding_id = None
        if body.founding:
            f = await F.load(tx, body.founding)
            if f["state"] not in ("auditing", "proposed", "sealed"):
                raise ApiError(
                    409, "validation_failed", fields={"founding": f"{f['ref']} is {f['state']}"}
                )
            if f["code"] and f["code"] != body.company:
                raise ApiError(
                    422, "validation_failed", fields={"company": f"the founding is {f['code']}"}
                )
            company_id = f["new_company_id"] or f["company_id"]
            founding_id = f["id"]
        else:
            co = await tx.first(
                "SELECT id FROM core.companies WHERE code = :c AND kind = 'company'", c=body.company
            )
            if co is None:
                raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
            company_id = co["id"]
        price = await F.price_of(
            hub.settings.provisioner_url, body.type, body.location, _transport(ctx)
        )
        row = await F.save_plan(
            tx,
            ctx.who,
            body.fields(),
            company_id=company_id,
            company_code=body.company,
            founding_id=founding_id,
            ref=body.ref,
            price=price,
        )
        out = F.render_plan(row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


# --------------------------------------------------- service: the provisioner --
async def _provisioner(ctx: Ctx) -> None:
    await allow(ctx, "provisioning.run", {})


@internal_router.get("/provisioning/runs/next", responses=responses(401, 403))
async def runs_next(ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The next run of a SEALED plan (204: none). A plan whose digest is not
    its seal any more is never handed out: its seal is voided instead."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        run = await F.next_run(tx)
    if run is None:
        return Response(status_code=204)
    return {"run": run}


@internal_router.get("/provisioning/runs/{id}", responses=responses(401, 403, 404))
async def runs_get(id: UUID, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The run's state and the new server's report (`cloud_init`), once it came."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        r = await F.load_run(tx, id)
    ci = r["cloud_init"]
    return {
        "id": str(r["id"]),
        "state": r["state"],
        "cloud_init": (
            {k: ci.get(k) for k in ("received_at", "results", "deploy_key", "failed")}
            if ci
            else None
        ),
    }


@internal_router.post("/provisioning/runs/{id}/callback", status_code=204, responses=E)
async def runs_callback(
    id: UUID, body: CallbackToken, ctx: Ctx = Depends(internal_ctx)
) -> Response:
    """The one-time token's sha256 (the plaintext only goes into the new
    server's user data); valid at most 60 minutes."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        run = await F.load_run(tx, id, lock=True)
        if run["state"] != "running":
            raise ApiError(409, "validation_failed", f"the run is {run['state']}")
        await F.record_callback_token(tx, run, body.token_sha256, body.expires_at)
    return Response(status_code=204)


@internal_router.post("/provisioning/runs/{id}/steps", status_code=204, responses=E)
async def runs_step(id: UUID, body: StepIn, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """One step's state and log tail (masked); the owner follows them live."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        run = await F.load_run(tx, id, lock=True)
        await F.record_step(tx, run, body.model_dump(mode="json"))
    return Response(status_code=204)


@internal_router.post("/provisioning/runs/{id}/server", status_code=204, responses=E)
async def runs_server(id: UUID, body: ServerIn, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The server the run made (only a labelled one of ours is recorded)."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        run = await F.load_run(tx, id, lock=True)
        await F.record_server(tx, run, body.model_dump(mode="json"))
    return Response(status_code=204)


@internal_router.post("/provisioning/runs/{id}/finish", status_code=204, responses=E)
async def runs_finish(id: UUID, body: FinishIn, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """Done (the login) or failed (the step): the owner is told either way."""
    await _provisioner(ctx)
    async with ctx.tx() as tx:
        run = await F.load_run(tx, id, lock=True)
        if run["state"] != "running":
            raise ApiError(409, "validation_failed", f"the run is {run['state']}")
        await F.finish(tx, run, body.model_dump(mode="json"))
    return Response(status_code=204)
