"""The charter and its addenda (prompt 11 §2, contract §20.2).

Owner (/api/v1):
  GET  /charter                                   the holding charter and every addendum, with versions
  GET  /charter/{scope}/versions · /versions/{v}
  GET  /charter/{scope}/versions/{v}/diff?against=  unified diff on the server
  PUT  /charter/{scope}                           a new `proposed` version {body_md, red_lines}
  POST /charter/{scope}/versions/{v}/seal         🔏 charter.seal, target = body_sha256 (recomputed)
Agents never write a charter: there is no tool for it, and an agent's
attempt on /internal/v1 is refused (403) and audited. They propose an
amendment with `propose` kind charter_amendment instead.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request

from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import charter as CH
from hq_api.errors import ApiError, responses
from hq_api.security import stepup

router = APIRouter(tags=["charter"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
ScopeP = Path(pattern=CH.SCOPE_RE)


async def _company_of(ctx: Ctx, scope: str) -> Any:
    if scope == CH.HOLDING:
        return await ctx.hub.companies.holding()
    co = await ctx.hub.companies.find(scope)
    if co is None or co.kind == "holding":
        raise ApiError(404, "not_found", f"no company {scope}")
    return co


@router.get("/charter", response_model=list[CH.CharterScope], responses=E)
async def list_charters(ctx: Ctx = Depends(owner_ctx)) -> list[CH.CharterScope]:
    """The holding charter first, then each company's addendum (sealed and
    proposed versions, and the version list)."""
    holding = await ctx.hub.companies.holding()
    root = str(ctx.hub.charters.root) if ctx.hub.charters is not None else "/app/agents"
    async with ctx.tx() as tx:
        await CH.seed(tx, holding.id, root)  # v1 proposed, once (the api's start does it too)
        rows = await tx.all(CH.SQL + " ORDER BY scope = 'holding' DESC, scope, version DESC")
    scopes: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        scopes.setdefault(r["scope"], []).append(r)
    return [CH.summary(s, v) for s, v in scopes.items()]


@router.get("/charter/{scope}/versions", response_model=list[CH.CharterVersion], responses=E)
async def charter_versions(
    scope: str = ScopeP, ctx: Ctx = Depends(owner_ctx)
) -> list[CH.CharterVersion]:
    """Every version of a scope, newest first."""
    async with ctx.tx() as tx:
        return [CH.render(r) for r in await CH.versions(tx, scope)]


@router.get("/charter/{scope}/versions/{version}", response_model=CH.CharterVersion, responses=E)
async def charter_version(
    version: int = Path(ge=1), scope: str = ScopeP, ctx: Ctx = Depends(owner_ctx)
) -> CH.CharterVersion:
    """One version of a scope, with its body_sha256 (the seal's target)."""
    async with ctx.tx() as tx:
        return CH.render(await CH.load(tx, scope, version))


@router.get("/charter/{scope}/versions/{version}/diff", response_model=CH.CharterDiff, responses=E)
async def charter_diff(
    against: int = Query(ge=1),
    version: int = Path(ge=1),
    scope: str = ScopeP,
    ctx: Ctx = Depends(owner_ctx),
) -> CH.CharterDiff:
    """`against` -> `version`, line by line (difflib, unified), the red lines too."""
    async with ctx.tx() as tx:
        a = await CH.load(tx, scope, version)
        b = await CH.load(tx, scope, against)
    return CH.diff(scope, a, b)


@router.put("/charter/{scope}", response_model=CH.CharterVersion, status_code=201, responses=E)
async def propose_charter(
    body: CH.CharterIn, scope: str = ScopeP, ctx: Ctx = Depends(owner_ctx)
) -> CH.CharterVersion:
    """The owner's new version, `proposed`: nothing in force changes until the
    seal (holding ≤ 6000 characters, an addendum ≤ 3000: 422 beyond)."""
    co = await _company_of(ctx, scope)
    async with ctx.tx() as tx:
        row = await CH.propose_version(
            tx,
            ctx.who,
            scope=scope,
            company_id=co.id,
            body_md=body.body_md,
            red_lines=body.red_lines,
        )
        await ctx.audit(
            tx, company_id=co.id, action="charter.propose", action_class="A2", target_kind="charter",
            target_ref=f"{scope}@{row['version']}", summary=f"sha256 {row['body_sha256'][:12]}",
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=co.id, kind="edit", action="charter.propose", target_kind="charter",
            target_ref=f"{scope}@{row['version']}",
        )  # fmt: skip
    return CH.render(row)


@router.post(
    "/charter/{scope}/versions/{version}/seal", response_model=CH.CharterVersion, responses=E
)
async def seal_charter(
    request: Request, version: int = Path(ge=1), scope: str = ScopeP, ctx: Ctx = Depends(owner_ctx)
) -> CH.CharterVersion:
    """🔏 `charter.seal`, target = the version's `body_sha256`, which the server
    recomputes from the stored body and red lines (a token for another body,
    or for the same body with other red lines, is refused: 403 step_up_invalid).
    The sealed version before it is superseded."""
    co = await _company_of(ctx, scope)
    async with ctx.tx() as tx:
        row = await CH.load(tx, scope, version, lock=True)
        target = CH.body_sha256(row["body_md"], list(row["red_lines"] or []))
        step_up_id = await stepup.consume(tx, request, ctx.who, "charter.seal", target)
        sealed = await CH.seal(tx, ctx.who, row, company_code=co.code, step_up_id=step_up_id)
        await ctx.audit(
            tx, company_id=co.id, action="charter.seal", action_class="A2", target_kind="charter",
            target_ref=f"{scope}@{version}", summary=f"sha256 {target[:12]}", step_up=True,
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=co.id, kind="decision", action="charter.seal", target_kind="charter",
            target_ref=f"{scope}@{version}",
        )  # fmt: skip
    return CH.render(sealed)


@internal_router.put("/charter/{scope}", status_code=403, responses=E)
async def agent_charter_write(scope: str = ScopeP, ctx: Ctx = Depends(internal_ctx)) -> None:
    """Agents read the charter, never write it (contract §20.2): refused and
    audited, whoever asks. An amendment is a `charter_amendment` card."""
    await _refuse(ctx, scope)


@internal_router.post("/charter/{scope}/versions/{version}/seal", status_code=403, responses=E)
async def agent_charter_seal(
    version: int = Path(ge=1), scope: str = ScopeP, ctx: Ctx = Depends(internal_ctx)
) -> None:
    """Only the owner seals (🔏 on /api/v1): an agent's seal is refused and audited."""
    await _refuse(ctx, scope)


async def _refuse(ctx: Ctx, scope: str) -> None:
    if ctx.who.company_id is not None:
        async with ctx.hub.db.tx([ctx.who.company_id]) as tx:
            await ctx.audit(
                tx, company_id=ctx.who.company_id, action="charter.write_denied", action_class="A2",
                target_kind="charter", target_ref=scope, summary=f"{ctx.who.kind}:{ctx.who.code}",
            )  # fmt: skip
    raise ApiError(403, "policy_denied", "no agent writes the charter; propose a charter_amendment")
