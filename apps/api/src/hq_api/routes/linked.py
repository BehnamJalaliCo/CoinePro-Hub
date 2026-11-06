"""`linked.read` (A0): another company's data (domain/linked.py, contract §35.6).

    GET /internal/v1/linked/read ?company&what&ref    profile | kpis | outputs (ref: one output's
                                                     body) | catalogue | connections | links

Allowed (OPA hq.internal, linked.rego), the same rule as a cross-company request: while the owner's
`links_enforced` is off any active company reads any other active company; while it is on only
along an `on` link between the two (either way). Always its own company; any company for a holding
reader; never the holding's data along the way. The facts (the company's kind and state, the link,
the setting) are looked up here before the policy, with domain/links.py's own `enforced()` and
`linked()`, never taken from the caller. The read runs in an all-companies READ ONLY transaction
once allowed; each read is audited (A0) on the company that was read.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from hq_api.context import Ctx, internal_ctx
from hq_api.domain import linked as LD
from hq_api.domain import links as LK
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import CODE

internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 422)


async def _facts(ctx: Ctx, target: Any) -> dict[str, Any]:
    """What the policy decides on: the company read (its kind, whether it is active), whether the
    caller's company and it share an `on` link, whether the owner enforces links; and `via`, why a
    read would be allowed (own, link, open, holding; none)."""
    who = ctx.who
    own = who.company_id
    assert own is not None  # agents only (checked by the caller)
    kind = target.kind if target is not None else None
    active = target is not None and target.status == "active"
    async with ctx.hub.db.tx([own]) as tx:  # the caller's own scope; both reads are the holding's
        enforced = await LK.enforced(tx)
        linked = (
            target is not None
            and kind != "holding"
            and target.id != own
            and await LK.linked(tx, own, target.id)
        )
    if target is not None and target.id == own:
        via = "own"
    elif linked and active:
        via = "link"
    elif who.scope == "holding":
        via = "holding"
    elif not enforced and kind == "company" and active:
        via = "open"
    else:
        via = "none"
    return {
        "company_kind": kind,
        "company_active": active,
        "linked": linked,
        "links_enforced": enforced,
        "via": via,
    }


@internal_router.get("/linked/read", response_model=LD.LinkedRead, responses=E)
async def linked_read(
    company: str = Query(pattern=CODE),
    what: LD.What = Query(),
    ref: str | None = Query(default=None, pattern=LD.REF),
    ctx: Ctx = Depends(internal_ctx),
) -> LD.LinkedRead:
    """linked.read: another company's profile (who it is, its departments, sites, connections and
    their public handles, servers by name, production lines, working groups), KPIs, latest outputs
    (or one output's body with `ref`), deep catalogue in short, connections' figures (Instagram:
    the accounts IG-Hub reads) or links. Any active company while the owner does not enforce links,
    else along an `on` link; its own company; any company for a holding reader. Never customer
    data or a secret. Audited (A0)."""
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    if ref is not None and what != "outputs":
        raise ApiError(
            422,
            "validation_failed",
            fields={"ref": "only with what=outputs"},
            message_fa="شماره‌ی خروجی فقط با what=outputs معنا دارد.",
        )
    target = await ctx.hub.companies.find(company)
    facts = await _facts(ctx, target)
    via = facts.pop("via")
    await allow(
        ctx, "linked.read", {"company": company, "what": what, "charter": who.charter, **facts}
    )
    if target is None:  # a holding reader asked for a company that is not there
        raise ApiError(
            404,
            "not_found",
            f"company {company} not found",
            message_fa=f"شرکتی با کد {company} نیست.",
        )
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        out = await LD.read(tx, target, what, ref, via)
    if out is None:
        raise ApiError(
            404,
            "not_found",
            f"no output {ref} of {company}",
            message_fa=f"خروجی {ref} از آنِ {company} نیست یا خواندنی نیست.",
        )
    async with ctx.hub.db.tx([target.id]) as tx:
        await ctx.audit(
            tx,
            company_id=target.id,
            action="linked.read",
            action_class="A0",
            target_kind="company",
            target_ref=f"{company}:{what}" + (f":{ref}" if ref else ""),
            summary=f"{who.company} read {what} of {company} ({via})",
        )
    return out
