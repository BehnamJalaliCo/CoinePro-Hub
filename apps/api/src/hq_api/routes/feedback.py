"""The feedback inbox (prompt 10 §8, contract §19.7).

Owner (/api/v1):  GET /feedback (?company&kind&state&cursor, most frequent first),
                  PATCH /feedback/{ref} (state, work_ref; If-Match)
Agents (/internal/v1): POST /feedback/tag  feedback.tag (A2: the support lead, the
                  PRODUCT manager) files a conversation (SC-…) or an NPS wave (NP-…)
Tables: feedback.items, signals, keywords (migration 0025). Quotes are
hq_common.customer_mask.quote(): no handle, no UID, no secret.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from hq_api import pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import feedback as FB
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model, Page

router = APIRouter(tags=["feedback"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 428)
KIND = Literal["bug", "feature", "confusion", "complaint", "praise"]
STATE = Literal["new", "triaged", "in_backlog", "done", "wont_do"]
SOURCE = r"^(SC-[0-9]{6,}|NP-[0-9]{4}Q[1-4]-[A-Z][A-Z0-9]{1,9})$"


class FeedbackItem(Model):
    id: str
    ref: str
    company: str
    kind: KIND
    area: str
    title_fa: str
    count: int
    first_seen: datetime
    last_seen: datetime
    quotes: list[str]
    sources: list[str]
    state: STATE
    work_ref: str | None = None
    version: int


class FeedbackPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: STATE | None = None
    work_ref: str | None = Field(default=None, max_length=40, pattern=r"^[A-Z][A-Z0-9-]{1,39}$")


@router.get("/feedback", response_model=Page[FeedbackItem], responses=E)
async def list_feedback(
    company: str | None = Query(default=None, pattern=CODE),
    kind: KIND | None = None,
    state: STATE | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Most frequent first (count, then the latest)."""
    after = pagination.decode(cursor, 3)
    co = None
    if company:
        try:
            co = (await ctx.hub.companies.by_code(company)).id
        except ApiError as exc:
            raise ApiError(404, "not_found", "no such company") from exc
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT i.*, c.code AS company FROM feedback.items i JOIN core.companies c ON c.id = i.company_id
               WHERE i.merged_into IS NULL
                 AND (CAST(:co AS uuid) IS NULL OR i.company_id = CAST(:co AS uuid))
                 AND (CAST(:k AS text) IS NULL OR i.kind = :k)
                 AND (CAST(:st AS text) IS NULL OR i.state = :st)
                 AND (CAST(:ac AS int) IS NULL
                      OR (i.count, i.last_seen, i.id) < (CAST(:ac AS int), CAST(:al AS timestamptz), CAST(:ai AS uuid)))
               ORDER BY i.count DESC, i.last_seen DESC, i.id DESC LIMIT :n""",
            co=str(co) if co else None,
            k=kind,
            st=state,
            ac=int(after[0]) if after else None,
            al=datetime.fromisoformat(str(after[1])) if after else None,
            ai=str(after[2]) if after else None,
            n=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("count", "last_seen", "id"))
    return Page[FeedbackItem](
        items=[FeedbackItem.model_validate(FB.item_out(r, r["company"])) for r in items],
        next_cursor=nxt,
    )


@router.patch("/feedback/{ref}", response_model=FeedbackItem, responses=E)
async def patch_feedback(
    ref: str, body: FeedbackPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The item's state and its backlog reference (`If-Match`: its version)."""
    expected = if_match(request)
    if body.state is None and body.work_ref is None:
        raise ApiError(422, "validation_failed", fields={"body": "state or work_ref"})
    async with ctx.tx() as tx:
        r = await tx.one(
            """SELECT i.*, c.code AS company FROM feedback.items i JOIN core.companies c ON c.id = i.company_id
               WHERE i.ref = :r FOR UPDATE OF i""",
            r=ref,
        )
        check_version(r["version"], expected)
        row = await tx.one(
            """UPDATE feedback.items SET state = COALESCE(:st, state), work_ref = COALESCE(:wr, work_ref),
                   updated_at = now() WHERE id = :id RETURNING *""",
            id=r["id"],
            st=body.state,
            wr=body.work_ref,
        )
        await ctx.audit(
            tx,
            company_id=r["company_id"],
            action="feedback.update",
            action_class="A1",
            target_kind="feedback_item",
            target_ref=ref,
            summary=f"state {r['state']} -> {row['state']}"
            + (f", work {body.work_ref}" if body.work_ref else ""),
        )
        await ctx.emit(tx, r["company"], "feedback.item", ref, {"state": row["state"]})
    return FeedbackItem.model_validate(FB.item_out(row, r["company"]))


class FeedbackTagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ref: str = Field(pattern=SOURCE)
    kind: KIND
    area: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=300)


@internal_router.post("/feedback/tag", responses=E)
async def feedback_tag(body: FeedbackTagIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """feedback.tag (A2): files a source of the agent's own company."""
    if not ctx.who.is_agent or ctx.who.company_id is None or ctx.who.company is None:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "feedback.tag", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        out = await FB.tag(
            tx,
            ctx.hub,
            company_id=ctx.who.company_id,
            company=ctx.who.company,
            source_ref=body.source_ref,
            kind=body.kind,
            area=body.area,
            title_fa=FB.quote(body.title_fa) or body.title_fa,
        )
        item = out.get("item")
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,
            action="feedback.tag",
            action_class="A2",
            target_kind="feedback_item" if item else "feedback_signal",
            target_ref=item["ref"] if item else body.source_ref,
            summary=f"{body.source_ref} -> {body.kind}/{body.area}",
        )
    if item is None:
        return {"ref": None, "mystery": True}
    return {"ref": item["ref"], "count": item["count"], "kind": item["kind"], "area": item["area"],
            "created": bool(out.get("created"))}  # fmt: skip
