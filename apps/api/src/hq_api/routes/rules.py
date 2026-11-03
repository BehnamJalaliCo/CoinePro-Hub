"""The owner's rules (contract §29.3): «این دیگر تکرار نشود» from the app.

POST /rules makes a `proposed` standing order of the owner's words (the seal
is the existing 🔏 POST /oversight/orders/{ref}/seal); GET /rules lists them
with their counts; PUT /rules/{ref} is a new version (🔏); POST
/rules/{ref}/retire stops it from the next run."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import orders as O
from hq_api.domain import rules as R
from hq_api.errors import ApiError, responses
from hq_api.routes.orders import _hub_transcript
from hq_api.routes.oversight import seal_step_up
from hq_api.schemas import Model
from hq_common.redact import scrub

router = APIRouter(tags=["rules"])
E = responses(401, 403, 404, 409, 422)


class RuleIn(Model):
    text: str = Field(default="", max_length=10000)
    source: Literal["text", "voice"] = "text"
    file_id: UUID | None = None

    @model_validator(mode="after")
    def _text_or_audio(self) -> RuleIn:
        if not self.text.strip() and not (self.source == "voice" and self.file_id):
            raise ValueError("text, or a voice rule's audio (source voice, file_id)")
        return self


class RuleEdit(Model):
    text_md: str | None = Field(default=None, min_length=1, max_length=10000)
    applies_to: R.Applies | None = None

    @model_validator(mode="after")
    def _something(self) -> RuleEdit:
        if self.text_md is None and self.applies_to is None:
            raise ValueError("text_md or applies_to")
        return self


async def _written(ctx: Ctx, owner_text: str) -> str:
    """The precise rule: by rules; the light model only to make one clear
    imperative of a long text (when it is reachable)."""
    text_md = R.clean(owner_text)
    if R.needs_model(text_md):
        holding = await ctx.hub.companies.holding()
        better = R.model_text(
            await workflows_client.route_order(ctx.hub, R.model_request(text_md, holding.code))
        )
        if better:
            text_md = better
    return text_md


@router.post("/rules", response_model=R.Rule, status_code=201, responses=E)
async def add_rule(body: RuleIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.11⟩ §29.3 a rule of the owner (text or voice): a standing order
    `proposed`, its precise `text_md` written from the owner's words (kept as
    `owner_text`) and `applies_to` from them (a role, a company, the
    overseer, else all). Nothing applies before the seal (🔏 POST
    /oversight/orders/{ref}/seal). Requires `Idempotency-Key`."""
    raw = body.text if body.text.strip() else await _hub_transcript(ctx, body.file_id)  # type: ignore[arg-type]
    owner_text = scrub(" ".join(raw.split()))[:10000]
    text_md = await _written(ctx, owner_text)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if body.file_id and not await tx.scalar(
            "SELECT 1 FROM files.files WHERE id = :id", id=body.file_id
        ):
            raise ApiError(422, "validation_failed", fields={"file_id": "unknown file"})
        applies, codes = R.applies_of(owner_text, await O.directory(tx))
        holding = await ctx.hub.companies.holding()
        row = await tx.one(
            """INSERT INTO oversight.orders (company_id, text_md, source, file_id, applies_to,
                   applies_codes, owner_text, created_by_kind, created_by_code)
               VALUES (:co, :t, :s, :f, :a, CAST(:codes AS text[]), :owner, 'owner', 'owner')
               RETURNING *""",
            co=holding.id,
            t=text_md,
            s=body.source,
            f=body.file_id,
            a=applies,
            codes=codes,
            owner=owner_text,
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="oversight.order",
            action_class="A1",
            target_kind="order",
            target_ref=row["ref"],
            summary=f"proposed (a rule of the owner, applies to {applies}"
            + (f": {', '.join(codes)}" if codes else "")
            + ")",
        )
        result = await R.render(tx, row)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.get("/rules", response_model=list[R.Rule], responses=E)
async def list_rules(ctx: Ctx = Depends(owner_ctx)) -> list[R.Rule]:
    """⟨1.11⟩ §29.3 the owner's rules (every standing order), newest first,
    each with its counts: the runs it applied to since its seal, the
    violations found and how many were fixed."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM oversight.orders ORDER BY created_at DESC LIMIT 200")
        return [await R.render(tx, r) for r in rows]


@router.put("/rules/{ref}", response_model=R.Rule, responses=E)
async def edit_rule(
    ref: str, body: RuleEdit, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> R.Rule:
    """⟨1.11⟩ §29.3 a new version of a rule, 🔏 (`rule.seal` or
    `oversight.order`, target = ref): its text and/or whom it applies to;
    sealed from now (the 🔏 is its seal), the previous version kept in
    `history`, its first report 24 hours from now. 409 for a retired rule."""
    async with ctx.tx() as tx:
        o = await tx.one(
            "SELECT * FROM oversight.orders WHERE ref = :r FOR UPDATE", r=ref, not_found="not_found"
        )
        if o["status"] == "retired":
            raise ApiError(409, "validation_failed", f"{ref} is retired")
        su = await seal_step_up(tx, request, ctx.who, ref)
        applies, codes = (
            R.applies_in(body.applies_to)
            if body.applies_to is not None
            else (o["applies_to"], list(o["applies_codes"] or []))
        )
        if applies in ("roles", "companies") and not codes:
            raise ApiError(422, "validation_failed", fields={"applies_to": "name at least one"})
        if applies == "companies":
            known = {c.code for c in await ctx.hub.companies.all()}
            if any(c not in known for c in codes):
                raise ApiError(422, "validation_failed", fields={"applies_to": "unknown company"})
        before = {
            "version": o["version"],
            "text_md": o["text_md"],
            "applies_to": o["applies_to"],
            "applies_codes": list(o["applies_codes"] or []),
            "status": o["status"],
            "sealed_at": o["sealed_at"].isoformat() if o["sealed_at"] else None,
        }
        row = await tx.one(
            """UPDATE oversight.orders SET text_md = :t, applies_to = :a,
                   applies_codes = CAST(:codes AS text[]),
                   history = history || CAST(:h AS jsonb), status = 'sealed', sealed_at = now(),
                   sealed_step_up_id = :su, report_at = NULL, report = NULL, updated_at = now()
               WHERE id = :id RETURNING *""",
            t=scrub(body.text_md) if body.text_md is not None else o["text_md"],
            a=applies,
            codes=codes,
            h=json.dumps([before], ensure_ascii=False),
            su=su,
            id=o["id"],
        )
        await ctx.audit(
            tx,
            company_id=o["company_id"],
            action="oversight.order",
            action_class="A2",
            target_kind="order",
            target_ref=ref,
            summary=f"new version {row['version']} (sealed; applies to {applies})",
            step_up=True,
        )
        return await R.render(tx, row)


@router.post("/rules/{ref}/retire", response_model=R.Rule, responses=E)
async def retire_rule(ref: str, ctx: Ctx = Depends(owner_ctx)) -> R.Rule:
    """⟨1.11⟩ §29.3 the rule stops applying from the next run (no step-up)."""
    async with ctx.tx() as tx:
        o = await tx.one(
            "SELECT * FROM oversight.orders WHERE ref = :r FOR UPDATE", r=ref, not_found="not_found"
        )
        if o["status"] == "retired":
            return await R.render(tx, o)
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
            summary="retired",
        )
        return await R.render(tx, row)
