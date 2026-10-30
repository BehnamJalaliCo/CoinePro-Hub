"""The decision cartable (contract §5.1)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import dceo, gov_authority
from hq_api.domain import decisions as D
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["decisions"])
E = responses(401, 403, 404, 409, 422)


class Approve(Model):
    note: str | None = Field(default=None, max_length=5000)
    amendments: dict[str, Any] | None = None


class Reject(Model):
    reason: str | None = Field(default=None, max_length=5000)
    reason_code: Literal["cost", "risk", "timing", "quality", "other"] | None = None


class Return(Model):
    note: str = Field(min_length=1, max_length=5000)


class Ask(Model):
    question: str | None = Field(default=None, max_length=10000)


class Posted(BaseModel):
    thread: str
    message_ref: str


def needs_step_up(d: dict[str, Any]) -> bool:
    return d["action_class"] == "A3" or d["kind"] in D.STEP_UP_KINDS


@router.get("/decisions", response_model=Page[D.Decision], responses=E)
async def list_decisions(
    status: Literal[
        "pending", "approved", "rejected", "returned", "expired", "withdrawn"
    ] = "pending",
    company: list[str] | None = Query(default=None),
    kind: Literal[
        "hire",
        "dismissal",
        "recurring_approval",
        "deploy",
        "a3_action",
        "proposal",
        "budget_change",
        "evaluation",
        "code_session",
        "errand_action",
        "lesson_adoption",
        "protocol",
        "tool_enable",
        "company_found",
        "server_plan",
        # ⟨1.5⟩ prompt 10 and 11
        "message_template",
        "lifecycle_rule",
        "support_go_live",
        "meeting_resolution",
        "charter_amendment",
        "knowledge_entry",
        "okr",
        "risk_acceptance",
        "authority_change",
        # ⟨1.6⟩ prompt 13
        "media_series",
        "media_publish",
        "role_new",
        "email_send",
        "archive_schema",
        "archive_disposal",
        "server_destructive",
    ]
    | None = None,
    risk: Literal["low", "medium", "high"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    approver: Literal["owner", "all"] = "owner",
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[D.Decision]:
    """Default `status=pending`, oldest first. ⟨1.4.3⟩ by default only the cards
    the owner decides (`approver` null); `?approver=all` adds the CEOs' (§18.11)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            D.DECISION_SQL
            + """ WHERE d.status = :status
                    AND (:approver = 'all' OR d.approver_code IS NULL)
                    AND (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:kind AS text) IS NULL OR d.kind = :kind)
                    AND (CAST(:risk AS text) IS NULL OR d.risk = :risk)
                    AND (CAST(:q AS text) IS NULL OR d.ref = :q
                         OR core.fa_normalize(d.title) LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (d.created_at, d.id) > (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY d.created_at, d.id LIMIT :lim""",
            status=status,
            approver=approver,
            companies=company,
            kind=kind,
            risk=risk,
            q=q,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        out = [D.render(r) for r in items]
        await dceo.reveal(tx, out)  # ⟨1.5⟩ only with reveal "before" (prompt 12 §13)
    return Page(items=out, next_cursor=nxt)


@router.get("/decisions/{ref}", response_model=D.Decision, responses=E)
async def get_decision(ref: str, ctx: Ctx = Depends(owner_ctx)) -> D.Decision:
    """One decision card: what, why, quota, risk, reversibility, payload and its seal."""
    async with ctx.tx() as tx:
        out = D.render(await D.load(tx, ref))
        await dceo.reveal(tx, [out])
        return out


async def _decide(
    ctx: Ctx,
    request: Request,
    ref: str,
    verdict: Literal["approved", "rejected", "returned"],
    *,
    note: str | None,
    reason_code: str | None = None,
    amendments: dict[str, Any] | None = None,
) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        d = await D.load(tx, ref, lock=True)
        if d["status"] != "pending":
            raise ApiError(409, "decision_not_pending", f"{ref} is {d['status']}")
        if verdict == "approved" and d["kind"] == "server_plan":
            # ⟨1.4⟩ its seal is bound to the plan's digest (contract §18.8)
            raise ApiError(
                409,
                "validation_failed",
                f"seal it at /provisioning/plans/{d['payload'].get('plan')}/seal (its digest)",
            )
        if verdict == "approved" and d["kind"] == "media_series":
            # ⟨1.6.1⟩ sealed on the series page, on its digest (contract §22.7)
            raise ApiError(
                409,
                "validation_failed",
                f"seal it at /media/series/{d['payload'].get('series')}/seal (its digest)",
            )
        final = D.amended(d["kind"], d["payload"], amendments)  # 422 when amended badly
        if verdict == "approved" and d["kind"] == "hire":
            # The new employee needs a real charter, else approving is refused.
            company = await ctx.hub.companies.by_id(d["company_id"])
            lib = await D.company_charters(tx, ctx.hub.charters, d["company_id"])
            D.check_hire_role(final, company.kind, lib, required=True)
        step_up_id = None
        target = ref
        if verdict == "approved" and d["kind"] == "email_send":
            # ⟨1.6⟩ bound to the exact message (contract §22.6): the seal's
            # target is its digest; a changed email or no mailbox -> 409
            from hq_api.domain import legal

            if amendments:
                raise ApiError(
                    422, "validation_failed", fields={"amendments": "this card is sealed as it is"}
                )
            await legal.check_seal(tx, ctx.hub, d)
            target = str((d["payload"] or {}).get("digest") or "")
        action = "decision.approve"
        if d["kind"] == "server_destructive":
            # ⟨1.8⟩ contract §26.3: 🔏 server.destructive on <CODE>:<server>,
            # sealed as it is (exactly the command it shows)
            if amendments:
                raise ApiError(
                    422, "validation_failed", fields={"amendments": "this card is sealed as it is"}
                )
            p = d["payload"] or {}
            action, target = "server.destructive", f"{p.get('company')}:{p.get('server_name')}"
        if verdict == "approved" and needs_step_up(d):
            step_up_id = await stepup.consume(tx, request, ctx.who, action, target)
        await ctx.hub.policy.require("decisions", D.opa_input(ctx.who, d, quota_ok=False))
        out = await D.decide(
            tx,
            ctx.who,
            d,
            verdict,
            note=note,
            reason_code=reason_code,
            amendments=amendments,
            step_up_id=step_up_id,
            charters=ctx.hub.charters,
            hub=ctx.hub,
        )
        action = {
            "approved": "decision.approve",
            "rejected": "decision.reject",
            "returned": "decision.return",
        }[verdict]
        await ctx.audit(
            tx,
            company_id=d["company_id"],
            action=action,
            action_class=d["action_class"],
            target_kind="decision",
            target_ref=ref,
            summary=f"{d['kind']} -> {verdict}"
            + (f" ({out['resolution']})" if out["resolution"] else ""),
            step_up=step_up_id is not None,
        )
        await ctx.interaction(
            tx,
            company_id=d["company_id"],
            kind="decision",
            action=action,
            target_kind="decision",
            target_ref=ref,
            data={
                "kind": d["kind"],
                "verdict": verdict,
                "note": note,
                "reason_code": reason_code,
                "risk": d["risk"],
                "proposer": d["proposer_code"],
                "amended": bool(amendments),
            },
        )
        result = D.render(out)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workflows_client.decision_decided(ctx.hub, ref)
    if verdict == "approved" and d["kind"] == "authority_change":
        await gov_authority.ensure(ctx.hub, force=True)  # ⟨1.5⟩ OPA enforces it at once
    if verdict == "approved" and result.kind == "archive_disposal":
        # ⟨1.7⟩ the sealed disposal committed: the destroyed files' bytes go now
        from hq_api.archive import retention as RT
        from hq_api.archive.common import wide_txf

        await RT.destroy_queued(ctx.hub, wide_txf(ctx.hub))
    return result


@router.post("/decisions/{ref}/approve", response_model=D.Decision, responses=E)
async def approve_decision(
    ref: str, body: Approve, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 for A3, `hire`, `dismissal`, `budget_change`, `code_session` and
    `tool_enable` (step-up action `decision.approve`, target = the ref; a
    `tool_enable` card whose server changed since is superseded: 409
    decision_not_pending). Creates the resolution (M-…), tells
    the proposer, and hands the effect to the worker. Requires `Idempotency-Key`.
    ⟨1.5⟩ A deploy card whose PR branch moved since is set aside first (409)."""
    from hq_api.domain import deploy_diff

    await deploy_diff.before_seal(ctx.hub, ref)
    return await _decide(ctx, request, ref, "approved", note=body.note, amendments=body.amendments)


@router.post("/decisions/{ref}/reject", response_model=D.Decision, responses=E)
async def reject_decision(
    ref: str, body: Reject, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Requires `Idempotency-Key`."""
    return await _decide(
        ctx, request, ref, "rejected", note=body.reason, reason_code=body.reason_code
    )


@router.post("/decisions/{ref}/return", response_model=D.Decision, responses=E)
async def return_decision(
    ref: str, body: Return, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """«برگشت با یادداشت»: back to the proposer with a required note. Requires `Idempotency-Key`."""
    return await _decide(ctx, request, ref, "returned", note=body.note)


async def _post_owner(
    ctx: Ctx, request: Request, ref: str, thread_code: str | None, body: str
) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        d = await D.load(tx, ref)
        code = thread_code or d["thread_code"]
        if not code:
            raise ApiError(422, "validation_failed", "this decision has no proposer thread")
        t = await tx.one("SELECT id, company_id FROM msg.threads WHERE code = :c", c=code)
        m = await tx.one(
            "SELECT ref FROM msg.post(:t, 'owner', 'owner', :body, CAST(:links AS jsonb), NULL, 'text')",
            t=t["id"],
            body=body,
            links='{"decision": "' + ref + '"}',
        )
        co_code = await ctx.hub.companies.code_of(t["company_id"])
        await ctx.emit(
            tx,
            co_code,
            "message.created",
            m["ref"],
            {"thread": code, "author": "owner", "decision": ref},
        )
        await ctx.audit(
            tx,
            company_id=t["company_id"],
            action="message.post",
            action_class="A1",
            target_kind="message",
            target_ref=m["ref"],
            summary=f"about {ref}",
        )
        await ctx.interaction(
            tx,
            company_id=t["company_id"],
            kind="message",
            action="message.post",
            target_kind="message",
            target_ref=m["ref"],
            data={"decision": ref, "thread": code},
        )
        result = Posted(thread=code, message_ref=m["ref"])
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@router.post("/decisions/{ref}/ask", response_model=Posted, responses=E)
async def ask_about_decision(
    ref: str, body: Ask, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """«توی چت بپرس»: a linked message in the proposer's thread. Requires `Idempotency-Key`."""
    text = body.question or f"درباره‌ی تصمیم {ref} سؤال دارم؛ توضیح بیشتری بده."
    return await _post_owner(ctx, request, ref, None, text)


@router.post("/decisions/{ref}/review-with-advisor", response_model=Posted, responses=E)
async def review_with_advisor(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """«با مشاور بررسی کن»: posts the decision into the advisor's thread (A). Requires `Idempotency-Key`."""
    return await _post_owner(ctx, request, ref, "A", f"تصمیم {ref} را با هم بررسی کنیم.")
