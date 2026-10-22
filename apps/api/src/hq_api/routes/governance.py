"""Governance, prompt 11 §4-§10 (contract §20.4-§20.10, §20.12).

Owner (/api/v1):
    GET /cards (?company, default the holding)        the three cards
    GET /scorecards (?q&cursor&limit)                  one row per company
    GET · PUT /kpis/{company} (PUT: If-Match)          definitions and targets
    GET /kpis/{company}/{key}/values (?from&to)
    GET /okr (?company&quarter&status) · /okr/{ref}
    GET /outcomes (?company&verdict&due&decision) · /outcomes/accuracy
    GET /authority · PUT /authority 🔏 authority.update (the body's SHA-256)
    GET /risks (?company&status&category&min_score) · /risks/matrix · /risks/{ref}
    POST /risks · PATCH /risks/{ref} (If-Match)
    GET /calendar (?company&from&to&kind) · POST /calendar · PATCH /calendar/{ref} (If-Match)
    GET /decisions/batchable · POST /decisions/batch/approve 🔏 decision.batch
Agents (/internal/v1/governance/...): kpi.record, okr.draft, okr.checkin,
    outcome.note, risk.raise, risk.update, calendar.read, calendar.add,
    authority.read, governance.read (hq.internal, governance.rego)

This router is registered before the decisions router: /decisions/batchable
and /decisions/batch/approve are not decision refs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import gov_authority as AU
from hq_api.domain import gov_batch as B
from hq_api.domain import gov_calendar as CAL
from hq_api.domain import gov_common as G
from hq_api.domain import gov_kpis as K
from hq_api.domain import gov_okr as OKR
from hq_api.domain import gov_outcomes as OUT
from hq_api.domain import gov_risks as RK
from hq_api.errors import ApiError, responses
from hq_api.http import if_match
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Page
from hq_api.security import stepup

router = APIRouter(tags=["governance"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 428)
IE = responses(401, 403, 404, 409, 422, 423)
KR_OR_KEY = r"^[a-z][a-z0-9_.]{1,60}$"


async def _company(ctx: Ctx, code: str | None) -> Any:
    if code is None:
        return await ctx.hub.companies.holding()
    return await ctx.hub.companies.by_code(code)


# ================================================================= cards ==
@router.get("/cards", response_model=list[K.Card], responses=E)
async def get_cards(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[K.Card]:
    """The three cards (stability, growth, safety_cost) of a company, or of the
    holding (its own KPIs plus every company's, aggregated). Every value has
    its time and source; an old one is `stale`; no source is `no_source`, never zero."""
    co = await _company(ctx, company)
    async with ctx.tx() as tx:
        return await K.cards(tx, co)


@router.get("/scorecards", response_model=Page[K.ScoreRow], responses=E)
async def get_scorecards(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[K.ScoreRow]:
    """The live scorecard: one row per operating company with its `scorecard`
    KPIs (value, time, source, target, 30-day trend, state); by code, paged."""
    after = pagination.decode(cursor, 1)
    needle = (q or "").strip().lower()
    companies = [
        c
        for c in await ctx.hub.companies.all()
        if c.kind != "holding"
        and c.status == "active"
        and (after is None or c.code > str(after[0]))
        and (
            not needle
            or needle in c.code.lower()
            or needle in (c.name_fa or "")
            or needle in (c.name_en or "").lower()
        )
    ]
    page, nxt = companies[:limit], None
    if len(companies) > limit:
        nxt = pagination.encode([page[-1].code])
    async with ctx.tx() as tx:
        return Page(items=await K.scorecards(tx, page), next_cursor=nxt)


@router.get("/kpis/{company}", response_model=K.KpiSet, responses=E)
async def get_kpis(company: str, ctx: Ctx = Depends(owner_ctx)) -> K.KpiSet:
    """The company's KPI definitions and targets with the set's version (If-Match)."""
    co = await ctx.hub.companies.by_code(company)
    async with ctx.tx() as tx:
        return await K.kpi_set(tx, co)


@router.put("/kpis/{company}", response_model=K.KpiSet, responses=E)
async def put_kpis(
    company: str, body: K.KpiSetIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> K.KpiSet:
    """Targets, scorecard, status and freshness of KPIs (and a new KPI of the
    registry or manual). `If-Match: <version>`; a query outside the registry is 422."""
    expected = if_match(request)
    co = await ctx.hub.companies.by_code(company)
    async with ctx.tx() as tx:
        changed = await K.put_set(tx, ctx.who, co, body, expected)
        if changed:
            await ctx.audit(tx, company_id=co.id, action="kpi.update", action_class="A2", target_kind="kpis",
                            target_ref=co.code, summary=", ".join(changed)[:500])  # fmt: skip
            await ctx.interaction(tx, company_id=co.id, kind="setting", action="kpi.update", target_kind="kpis",
                                  target_ref=co.code, data={"keys": changed})  # fmt: skip
        return await K.kpi_set(tx, co)


@router.get("/kpis/{company}/{key}/values", response_model=Page[K.KpiValue], responses=E)
async def get_kpi_values(
    company: str,
    key: str,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[K.KpiValue]:
    """The KPI's series (default: the last 30 days; at most 2000 values)."""
    co = await ctx.hub.companies.by_code(company)
    end = to or datetime.now(UTC)
    start = from_ or end - timedelta(days=30)
    async with ctx.tx() as tx:
        return Page(items=await K.values(tx, co.id, key, start, end))


# =================================================================== OKR ==
@router.get("/okr", response_model=Page[OKR.Objective], responses=E)
async def list_okr(
    company: str | None = Query(default=None, pattern=CODE),
    quarter: str | None = Query(default=None, pattern=G.QUARTER),
    status: Literal["draft", "proposed", "active", "closed"] | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[OKR.Objective]:
    after_t, after_id = pagination.time_id(cursor)
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            OKR.OBJECTIVE_SQL
            + """ WHERE (CAST(:co AS uuid) IS NULL OR o.company_id = :co)
                    AND (CAST(:q AS text) IS NULL OR o.quarter = :q)
                    AND (CAST(:st AS text) IS NULL OR o.status = :st)
                    AND (CAST(:at AS timestamptz) IS NULL
                         OR (o.created_at, o.id) > (CAST(:at AS timestamptz), CAST(:aid AS uuid)))
                  ORDER BY o.created_at, o.id LIMIT :n""",
            co=co,
            q=quarter,
            st=status,
            at=after_t,
            aid=after_id,
            n=limit + 1,
        )
        items, nxt = pagination.page([dict(r) for r in rows], limit, ("created_at", "id"))
        return Page(
            items=[await OKR.render(tx, r, with_checkins=False) for r in items], next_cursor=nxt
        )


@router.get("/okr/{ref}", response_model=OKR.Objective, responses=E)
async def get_okr(ref: str, ctx: Ctx = Depends(owner_ctx)) -> OKR.Objective:
    """An objective with its key results, their progress and check-ins."""
    async with ctx.tx() as tx:
        return await OKR.render(
            tx, dict(await tx.one(OKR.OBJECTIVE_SQL + " WHERE o.ref = :r", r=ref))
        )


# ============================================================== outcomes ==
@router.get("/outcomes", response_model=Page[OUT.OutcomeReview], responses=E)
async def list_outcomes(
    company: str | None = Query(default=None, pattern=CODE),
    verdict: Literal["pending", "met", "partly", "missed", "unmeasurable"] | None = None,
    due: bool | None = None,
    decision: str | None = Query(default=None, pattern=r"^D-[0-9]{4,}$"),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[OUT.OutcomeReview]:
    """The outcome reviews (`?due=true`: due now or overdue), by due date."""
    after_t, after_id = pagination.time_id(cursor)
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        rows = await OUT.listing(
            tx, company_id=co, verdict=verdict, due=due, decision=decision, limit=limit,
            after=(after_t, after_id) if after_t and after_id else None,
        )  # fmt: skip
    items, nxt = pagination.page(rows, limit, ("due_at", "id"))
    return Page(items=[OUT.render(r) for r in items], next_cursor=nxt)


@router.get("/outcomes/accuracy", response_model=list[OUT.Accuracy], responses=E)
async def outcomes_accuracy(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[OUT.Accuracy]:
    """Prediction accuracy of every proposer: (met + partly / 2) / decided."""
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        return await OUT.accuracy(tx, co)


# ============================================================= authority ==
@router.get("/authority", response_model=AU.Matrix, responses=E)
async def get_authority(ctx: Ctx = Depends(owner_ctx)) -> AU.Matrix:
    """The whole authority matrix, locked rows included."""
    async with ctx.tx() as tx:
        return await AU.matrix(tx)


@router.put("/authority", response_model=AU.Matrix, responses=E)
async def put_authority(body: AU.MatrixIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `authority.update` on the SHA-256 of the exact body. Unlocked rows
    only, inside their bounds (422 otherwise); each row's `version` must match
    (409). `actor: "owner"` takes a row back. OPA enforces it at once."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        su = await stepup.consume(
            tx, request, ctx.who, "authority.update", await stepup.body_target(request)
        )
        done = await AU.apply(tx, ctx.who, body.rules)
        for c in done:
            await ctx.audit(tx, company_id=holding.id, action="authority.update", action_class="A2",
                            target_kind="authority", target_ref=c["key"], summary=f"v{c['version']}",
                            step_up=True)  # fmt: skip
        await ctx.interaction(tx, company_id=holding.id, kind="setting", action="authority.update",
                              target_kind="authority", target_ref="matrix",
                              data={"changes": done, "step_up": str(su)})  # fmt: skip
        out = await AU.matrix(tx)
    await AU.ensure(ctx.hub, force=True)
    return out


# ================================================================= risks ==
@router.get("/risks/matrix", response_model=RK.RiskMatrix, responses=E)
async def risks_matrix(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> RK.RiskMatrix:
    """5 × 5 counts of open risks, [likelihood − 1][impact − 1]."""
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        return RK.RiskMatrix(company=company, counts=await RK.matrix(tx, co))


@router.get("/risks", response_model=Page[RK.Risk], responses=E)
async def list_risks(
    company: str | None = Query(default=None, pattern=CODE),
    status: Literal["open", "mitigating", "accepted", "closed"] | None = None,
    category: RK.Category | None = None,
    min_score: int | None = Query(default=None, ge=1, le=25),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[RK.Risk]:
    """Highest score first."""
    after = pagination.decode(cursor, 2)
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            RK.SQL
            + """ WHERE (CAST(:co AS uuid) IS NULL OR r.company_id = :co)
                    AND (CAST(:st AS text) IS NULL OR r.status = :st)
                    AND (CAST(:cat AS text) IS NULL OR r.category = :cat)
                    AND (CAST(:ms AS int) IS NULL OR r.score >= :ms)
                    AND (CAST(:a_s AS int) IS NULL OR (r.score, r.ref) < (CAST(:a_s AS int), CAST(:a_r AS text)))
                  ORDER BY r.score DESC, r.ref DESC LIMIT :n""",
            co=co,
            st=status,
            cat=category,
            ms=min_score,
            a_s=int(after[0]) if after else None,
            a_r=str(after[1]) if after else None,
            n=limit + 1,
        )
        items, nxt = pagination.page([dict(r) for r in rows], limit, ("score", "ref"))
        return Page(items=[await RK.render(tx, r, history=False) for r in items], next_cursor=nxt)


@router.get("/risks/{ref}", response_model=RK.Risk, responses=E)
async def get_risk(ref: str, ctx: Ctx = Depends(owner_ctx)) -> RK.Risk:
    async with ctx.tx() as tx:
        return await RK.render(tx, await RK.load(tx, ref))


@router.post("/risks", response_model=RK.Risk, status_code=201, responses=E)
async def create_risk(body: RK.RiskIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner's risk. Requires `Idempotency-Key`."""
    co = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await RK.create(tx, ctx.who, co.id, co.code, body, origin="owner")
        assert r is not None
        await ctx.audit(tx, company_id=co.id, action="risk.create", action_class="A1", target_kind="risk",
                        target_ref=r["ref"], summary=f"score {r['score']}")  # fmt: skip
        await ctx.interaction(tx, company_id=co.id, kind="edit", action="risk.create", target_kind="risk",
                              target_ref=r["ref"])  # fmt: skip
        out = await RK.render(tx, r)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.patch("/risks/{ref}", response_model=RK.Risk, responses=E)
async def patch_risk(
    ref: str, body: RK.RiskPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> RK.Risk:
    """`If-Match: <version>`. Acceptance only through a sealed risk_acceptance card."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        r = await RK.load(tx, ref, lock=True)
        changes = body.model_dump(exclude_unset=True, exclude={"note"})
        fresh = await RK.update(tx, ctx.who, r, changes, expected_version=expected, note=body.note)
        await ctx.audit(tx, company_id=r["company_id"], action="risk.update", action_class="A2",
                        target_kind="risk", target_ref=ref, summary=", ".join(sorted(changes))[:500])  # fmt: skip
        await ctx.interaction(tx, company_id=r["company_id"], kind="edit", action="risk.update",
                              target_kind="risk", target_ref=ref, data={"fields": sorted(changes)})  # fmt: skip
        return await RK.render(tx, fresh)


# ============================================================== calendar ==
def _window(from_: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
    start = from_ or datetime.now(UTC) - timedelta(days=7)
    end = to or start + timedelta(days=42)
    if end <= start or end - start > timedelta(days=400):
        raise ApiError(422, "validation_failed", fields={"to": "after from, at most 400 days"})
    return start, end


@router.get("/calendar", response_model=CAL.Calendar, responses=E)
async def get_calendar(
    company: str | None = Query(default=None, pattern=CODE),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    kind: CAL.Kind | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> CAL.Calendar:
    """Events (a company's and the holding-wide ones) and their conflicts."""
    start, end = _window(from_, to)
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        return await CAL.listing(tx, company_id=co, start=start, end=end, kind=kind)


@router.post("/calendar", response_model=CAL.CalendarEvent, status_code=201, responses=E)
async def add_event(body: CAL.EventIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner's event (any kind but `deploy`: a deploy comes from its card).
    Without `company` it is the holding's. Requires `Idempotency-Key`."""
    co = await _company(ctx, body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        e = await CAL.add(tx, ctx.who, co.id, co.code, body)
        await ctx.audit(tx, company_id=co.id, action="calendar.add", action_class="A2", target_kind="calendar",
                        target_ref=e["ref"], summary=f"{e['kind']} {e['starts_at'].isoformat()}")  # fmt: skip
        await ctx.interaction(tx, company_id=co.id, kind="edit", action="calendar.add", target_kind="calendar",
                              target_ref=e["ref"])  # fmt: skip
        out = CAL.render(e)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.patch("/calendar/{ref}", response_model=CAL.CalendarEvent, responses=E)
async def patch_event(
    ref: str, body: CAL.EventPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> CAL.CalendarEvent:
    """`If-Match: <version>`: title, times, status, risk."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        e = await CAL.patch(tx, ctx.who, ref, body, expected)
        await ctx.audit(tx, company_id=e["company_id"], action="calendar.update", action_class="A2",
                        target_kind="calendar", target_ref=ref,
                        summary=", ".join(sorted(body.model_dump(exclude_unset=True)))[:500])  # fmt: skip
        await ctx.interaction(tx, company_id=e["company_id"], kind="edit", action="calendar.update",
                              target_kind="calendar", target_ref=ref)  # fmt: skip
        return CAL.render(e)


# ============================================================ batch seal ==
@router.get("/decisions/batchable", response_model=Page[B.Batchable], responses=E)
async def batchable(ctx: Ctx = Depends(owner_ctx)) -> Page[B.Batchable]:
    """The pending cards that may be sealed together (title, cost, proposer)."""
    async with ctx.tx() as tx:
        return Page(items=await B.batchable(tx, ctx.hub))


@router.post("/decisions/batch/approve", response_model=B.BatchOut, responses=E)
async def batch_approve(body: B.BatchIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `decision.batch` on the SHA-256 of the canonical JSON of the items
    ([{ref, version}] sorted by ref). All or nothing: one card that changed or
    is not eligible is `422 batch_not_eligible` (fields.items [{ref, reason}])
    and nothing is sealed. Each card gets its own resolution, audit row and
    interaction. Requires `Idempotency-Key`."""
    holding = await ctx.hub.companies.holding()
    sealed: list[B.Sealed] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        su = await stepup.consume(tx, request, ctx.who, "decision.batch", B.target(body.items))
        cards = await B.check(tx, ctx.hub, body.items)
        batch = await tx.scalar(
            """INSERT INTO governance.batches (company_id, items, target_sha256, step_up_id, note)
               VALUES (:co, CAST(:items AS jsonb), :t, :su, :n) RETURNING ref""",
            co=holding.id,
            items=G.canonical_json([i.model_dump() for i in body.items]),
            t=B.target(body.items),
            su=su,
            n=body.note,
        )
        for d in cards:
            await ctx.hub.policy.require("decisions", D.opa_input(ctx.who, d, quota_ok=False))
            out = await D.decide(tx, ctx.who, d, "approved", note=body.note, step_up_id=su,
                                 charters=ctx.hub.charters, hub=ctx.hub)  # fmt: skip
            await ctx.audit(
                tx,
                company_id=d["company_id"],
                action="decision.approve",
                action_class=d["action_class"],
                target_kind="decision",
                target_ref=d["ref"],
                summary=f"{d['kind']} -> approved ({out['resolution']}) batch: {batch}",
                step_up=True,
            )
            await ctx.interaction(
                tx, company_id=d["company_id"], kind="decision", action="decision.approve", target_kind="decision",
                target_ref=d["ref"],
                data={"kind": d["kind"], "verdict": "approved", "batch": batch, "risk": d["risk"],
                      "proposer": d["proposer_code"], "note": body.note},
            )  # fmt: skip
            sealed.append(B.Sealed(ref=d["ref"], resolution=out["resolution"]))
        await ctx.audit(tx, company_id=holding.id, action="decision.batch", action_class="A1", target_kind="batch",
                        target_ref=batch, summary=f"{len(sealed)} card(s)", step_up=True)  # fmt: skip
        result = B.BatchOut(batch=batch, items=sealed)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    for s in sealed:
        await workflows_client.decision_decided(ctx.hub, s.ref)
    return result


# ============================================================= the agents ==
def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None or ctx.who.company is None:
        raise ApiError(403, "policy_denied", "agents only")


async def _target(ctx: Ctx, op: str, code: str | None, **extra: Any) -> Any:
    """The company of an agent's call, looked up only after the policy allowed
    it (a missing and a forbidden company both answer 403)."""
    wanted = code or ctx.who.company
    await allow(ctx, op, {"company": wanted, **extra})
    co = await ctx.hub.companies.find(str(wanted))
    if co is None:
        raise ApiError(403, "policy_denied", f"{op}: not permitted")
    return co


@asynccontextmanager
async def _scoped(
    ctx: Ctx, *, read_only: bool = False, extra: list[UUID] | None = None
) -> AsyncIterator[Tx]:
    """The agent's company (and the holding: its holiday and hub windows), or
    every company for a holding-scope role."""
    holding = await ctx.hub.companies.holding()
    if ctx.who.scope == "holding":
        scope = await ctx.hub.companies.ids()
    else:
        assert ctx.who.company_id is not None
        scope = list(dict.fromkeys([ctx.who.company_id, holding.id, *(extra or [])]))
    async with ctx.hub.db.tx(scope) as tx:
        if read_only:
            await tx.exec("SET TRANSACTION READ ONLY")
        yield tx


@internal_router.post("/governance/kpis/record", responses=IE)
async def kpi_record(body: K.RecordIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """kpi.record (A2): a manual KPI's value, with its source (CEO or a manager)."""
    _agent(ctx)
    co = await _target(ctx, "kpi.record", body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await K.record(tx, ctx.who, co.id, body)
        await ctx.audit(tx, company_id=co.id, action="kpi.record", action_class="A2", target_kind="kpi",
                        target_ref=f"{co.code}:{body.key}", summary=f"{body.value} ({body.source.kind})")  # fmt: skip
        if idem:
            await idem.store(tx, 200, out)
    return out


@internal_router.post("/governance/okr/draft", responses=IE)
async def okr_draft(body: OKR.DraftIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """okr.draft (A1, the CEO): the next quarter's OKR as one `okr` card."""
    _agent(ctx)
    co = await _target(ctx, "okr.draft", body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        r = await OKR.draft(tx, ctx.who, co.id, co.code, body, charters=ctx.hub.charters)
        await ctx.audit(
            tx,
            company_id=co.id,
            action="okr.draft",
            action_class="A1",
            target_kind="decision",
            target_ref=r["decision"]["ref"],
            summary=f"{body.quarter}: {', '.join(r['objectives'])}",
        )
        out = {
            "decision": r["decision"]["ref"],
            "objectives": r["objectives"],
            "quarter": body.quarter,
        }
        if idem:
            await idem.store(tx, 201, out)
    await workflows_client.decision_created(ctx.hub, out["decision"])
    return out


@internal_router.post("/governance/okr/checkin", responses=IE)
async def okr_checkin(
    body: OKR.CheckinIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """okr.checkin (A2): a key result of the agent's own company."""
    _agent(ctx)
    co = await _target(ctx, "okr.checkin", None)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await OKR.checkin(tx, ctx.who, co.id, body)
        await ctx.audit(tx, company_id=co.id, action="okr.checkin", action_class="A2", target_kind="key_result",
                        target_ref=body.key_result, summary=f"confidence {body.confidence}")  # fmt: skip
        if idem:
            await idem.store(tx, 200, out)
    return out


@internal_router.post("/governance/outcomes/note", responses=IE)
async def outcome_note(body: OUT.NoteIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """outcome.note (A1): the proposer's note on a due outcome review."""
    _agent(ctx)
    async with ctx.tx() as tx:  # the agent's own company: another's review is never found
        r = await tx.first(OUT.SQL + " WHERE r.ref = :ref", ref=body.ref)
    await _target(ctx, "outcome.note", None, proposer=r["proposer_code"] if r else None)
    if r is None:
        raise ApiError(403, "policy_denied", "outcome.note: not permitted")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await OUT.note(tx, ctx.who, body)
        await ctx.audit(tx, company_id=r["company_id"], action="outcome.note", action_class="A1",
                        target_kind="outcome_review", target_ref=body.ref, summary=r["decision_ref"])  # fmt: skip
        if idem:
            await idem.store(tx, 200, out)
    return out


@internal_router.post("/governance/risks", status_code=201, responses=IE)
async def risk_raise(body: RK.RiskIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """risk.raise (A1): own company; an oversight (holding-scope) role any company."""
    _agent(ctx)
    co = await _target(ctx, "risk.raise", body.company)
    async with _scoped(ctx, extra=[co.id]) as tx:
        await ctx.ensure_unlocked(tx, co.id)
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        r = await RK.create(
            tx, ctx.who, co.id, co.code, body.model_copy(update={"review_at": None}), origin="agent"
        )
        assert r is not None
        await ctx.audit(tx, company_id=co.id, action="risk.raise", action_class="A1", target_kind="risk",
                        target_ref=r["ref"], summary=f"score {r['score']}")  # fmt: skip
        out = {"ref": r["ref"], "score": r["score"], "status": r["status"], "owner": r["owner_code"],
               "review_at": r["review_at"].isoformat(), "version": r["version"]}  # fmt: skip
        if idem:
            await idem.store(tx, 201, out)
    return out


@internal_router.post("/governance/risks/update", responses=IE)
async def risk_update(body: RK.UpdateIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """risk.update (A2): the risk's owner, or the keeper (QC); only the keeper closes it."""
    _agent(ctx)
    async with _scoped(ctx, read_only=True) as tx:
        r = await tx.first(RK.SQL + " WHERE r.ref = :ref", ref=body.ref)
    await _target(ctx, "risk.update", r["company"] if r else ctx.who.company,
                  owner=r["owner_code"] if r else None)  # fmt: skip
    if r is None:
        raise ApiError(403, "policy_denied", "risk.update: not permitted")
    async with _scoped(ctx, extra=[r["company_id"]]) as tx:
        await ctx.ensure_unlocked(tx, r["company_id"])
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        row = await RK.load(tx, body.ref, lock=True)
        changes = body.model_dump(exclude_unset=True, exclude={"ref", "version", "note"})
        fresh = await RK.update(
            tx, ctx.who, row, changes, expected_version=body.version, note=body.note
        )
        await ctx.audit(tx, company_id=r["company_id"], action="risk.update", action_class="A2", target_kind="risk",
                        target_ref=body.ref, summary=", ".join(sorted(changes))[:500])  # fmt: skip
        out = {"ref": fresh["ref"], "score": fresh["score"], "status": fresh["status"],
               "review_at": fresh["review_at"].isoformat(), "version": fresh["version"]}  # fmt: skip
        if idem:
            await idem.store(tx, 200, out)
    return out


@internal_router.get("/governance/calendar", response_model=CAL.Calendar, responses=IE)
async def calendar_read(
    company: str | None = Query(default=None, pattern=CODE),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    kind: CAL.Kind | None = None,
    ctx: Ctx = Depends(internal_ctx),
) -> CAL.Calendar:
    """calendar.read (A0): own company (with the holding-wide events); a
    holding-scope role any company."""
    _agent(ctx)
    co = await _target(ctx, "calendar.read", company)
    start, end = _window(from_, to)
    async with _scoped(ctx, read_only=True) as tx:
        return await CAL.listing(tx, company_id=co.id, start=start, end=end, kind=kind)


@internal_router.post("/governance/calendar", status_code=201, responses=IE)
async def calendar_add(
    body: CAL.EventIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """calendar.add (A2): a campaign, event or maintenance (the calendar never decides)."""
    _agent(ctx)
    co = await _target(ctx, "calendar.add", body.company)
    async with _scoped(ctx, extra=[co.id]) as tx:
        await ctx.ensure_unlocked(tx, co.id)
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        e = await CAL.add(tx, ctx.who, co.id, co.code, body)
        conflicts = await CAL.clashes_with(tx, e)
        await ctx.audit(tx, company_id=co.id, action="calendar.add", action_class="A2", target_kind="calendar",
                        target_ref=e["ref"], summary=f"{e['kind']} {e['starts_at'].isoformat()}")  # fmt: skip
        out = {"ref": e["ref"], "kind": e["kind"], "conflicts": [c.model_dump() for c in conflicts]}
        if idem:
            await idem.store(tx, 201, out)
    return out


@internal_router.get("/governance/authority", response_model=list[AU.AuthorityRule], responses=IE)
async def authority_read(ctx: Ctx = Depends(internal_ctx)) -> list[AU.AuthorityRule]:
    """authority.read (A0): the rows that apply to the agent's company."""
    _agent(ctx)
    await _target(ctx, "authority.read", None)
    async with ctx.tx() as tx:
        return await AU.for_agent(tx, ctx.who)


@internal_router.get("/governance/read", responses=IE)
async def governance_read(
    what: Literal["cards", "okr", "risks", "charter", "outcomes"],
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """governance.read (A0): the company's cards, OKRs, open risks, sealed
    charter and outcome reviews; own company, a holding-scope role any."""
    _agent(ctx)
    co = await _target(ctx, "governance.read", company)
    async with _scoped(ctx, read_only=True) as tx:
        if what == "cards":
            return [c.model_dump(mode="json") for c in await K.cards(tx, co, seed=False)]
        if what == "okr":
            rows = await tx.all(
                OKR.OBJECTIVE_SQL
                + " WHERE o.company_id = :co AND o.status IN ('proposed', 'active')"
                " ORDER BY o.quarter, o.ref LIMIT 20",
                co=co.id,
            )
            return [
                (await OKR.render(tx, dict(r), with_checkins=False)).model_dump(mode="json")
                for r in rows
            ]
        if what == "risks":
            rows = await tx.all(
                RK.SQL
                + " WHERE r.company_id = :co AND r.status <> 'closed' ORDER BY r.score DESC LIMIT 50",
                co=co.id,
            )
            return [
                (await RK.render(tx, dict(r), history=False)).model_dump(mode="json") for r in rows
            ]
        if what == "outcomes":
            rows = await tx.all(
                OUT.SQL
                + " WHERE r.company_id = :co AND r.status <> 'verified' ORDER BY r.due_at LIMIT 50",
                co=co.id,
            )
            return [OUT.render(dict(r)).model_dump(mode="json") for r in rows]
        return await sealed_charter(tx, co.code)


async def sealed_charter(tx: Tx, code: str) -> dict[str, Any]:
    """The sealed charter of the holding and the company's addendum, when the
    charter (prompt 11 §2, the other half) is in this database."""
    cols = set(
        await tx.scalar(
            """SELECT coalesce(array_agg(column_name::text), '{}') FROM information_schema.columns
               WHERE table_schema = 'governance' AND table_name = 'charters'"""
        )
        or []
    )
    if not {"scope", "version", "status", "body_md", "red_lines"} <= cols:
        return {"state": "no_source"}
    rows = await tx.all(
        """SELECT DISTINCT ON (scope) scope, version, body_md, red_lines FROM governance.charters
           WHERE status = 'sealed' AND scope IN ('holding', :c) ORDER BY scope, version DESC""",
        c=code,
    )
    return {"state": "ok", "charters": [dict(r) for r in rows]}
