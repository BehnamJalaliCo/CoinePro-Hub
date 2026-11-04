"""⟨1.13⟩ Prompt 22 part 3 (contract §31.7): an automation from one sentence.

POST /automations/compile        {sentence_fa, company?} -> {rule, preview_fa, refused_fa}: ONE
                                 router call (task class automation_compile), checked by code
POST /automations                {rule, sentence_fa, company?}: `proposed` (re-checked by code)
POST /automations/{ref}/seal     🔏 automation.seal (target = ref): from now it runs
POST /automations/{ref}/state    {state: on|off}
GET  /automations                the list, newest first
GET  /automations/{ref}          one, with its runs

Owner only. Running is code (the worker's tick and the event consumer), never a
model; an action outside the allow-list is refused here, at compile time."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import automations as AU
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model
from hq_api.security import stepup
from hq_common.redact import scrub

router = APIRouter(tags=["automations"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"


class CompileIn(Model):
    sentence_fa: str = Field(min_length=3, max_length=1000)
    company: str | None = Field(default=None, pattern=CODE)


class AutomationIn(Model):
    rule: dict[str, Any]
    sentence_fa: str = Field(min_length=3, max_length=1000)
    company: str | None = Field(default=None, pattern=CODE)


class AutomationStateIn(Model):
    state: Literal["on", "off"]


async def _known(ctx: Ctx) -> set[str]:
    return {c.code for c in await ctx.hub.companies.all() if c.kind != "holding"}


@router.post("/automations/compile", response_model=AU.Compiled, responses=E)
async def compile_automation(body: CompileIn, ctx: Ctx = Depends(owner_ctx)) -> AU.Compiled:
    """⟨1.13⟩ §31.7 one Persian sentence into a rule: ONE router call (task class
    `automation_compile`, a mid model, a strict JSON schema), then CODE decides
    what survives. `rule` has only allow-listed triggers (schedule, event,
    metric) and actions (work.create, line.run, line.pause, notify.owner,
    notify.lead, ad.pause, n8n.run); anything else is in `refused_fa` with a
    plain reason. `preview_fa` is written by code from the checked rule, so it
    says what will really run. Nothing is saved or run."""
    return await AU.compile_sentence(ctx.hub, body.sentence_fa, body.company)


@router.post("/automations", response_model=AU.Automation, status_code=201, responses=E)
async def add_automation(
    body: AutomationIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.13⟩ §31.7 save a rule as `proposed`: it is checked again by code (a rule
    the client made up is refused like the model's), its sentence and rule never
    change afterwards. Nothing runs before the seal. Requires `Idempotency-Key`."""
    known = await _known(ctx)
    if body.company is not None and body.company not in known:
        raise ApiError(404, "not_found")
    rule, why = AU.validate_rule(body.rule, body.company, known)
    if rule is None:
        raise ApiError(422, "validation_failed", fields={"rule": " ".join(why)}, message_fa=why[0])
    sentence = scrub(" ".join(body.sentence_fa.split()))
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        co = await ctx.hub.companies.by_code(body.company) if body.company else holding
        row = await tx.one(
            """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, n8n_workflow)
               VALUES (:co, :sc, :s, CAST(:r AS jsonb), :n8n) RETURNING *""",
            co=co.id,
            sc="company" if body.company else "holding",
            s=sentence,
            r=json.dumps(rule, ensure_ascii=False),
            n8n=AU.n8n_of(rule),
        )
        await ctx.audit(
            tx,
            company_id=co.id,
            action="automation.propose",
            action_class="A2",
            target_kind="automation",
            target_ref=row["ref"],
            summary="proposed",
        )
        result = AU.render(row, body.company)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.post("/automations/{ref}/seal", response_model=AU.Automation, responses=E)
async def seal_automation(
    ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> AU.Automation:
    """⟨1.13⟩ §31.7 the owner's seal, 🔏 `automation.seal` (target = the ref): the
    automation is `on` from now. Only what happens after the seal counts (a
    schedule's earlier times and an event's earlier occurrences never run).
    409 when it is not `proposed`."""
    async with ctx.tx() as tx:
        a = await AU.row_of(tx, ref, lock=True)
        if a["state"] != "proposed":
            raise ApiError(409, "validation_failed", f"{ref} is {a['state']}")
        known = await _known(ctx)
        if (
            AU.validate_rule(
                a["rule"], a["company_code"] if a["scope"] == "company" else None, known
            )[0]
            is None
        ):
            raise ApiError(409, "validation_failed", "the rule is no longer allowed")
        su = await stepup.consume(tx, request, ctx.who, "automation.seal", ref)
        row = await tx.one(
            """UPDATE growth.automations SET state = 'on', sealed_at = now(), sealed_step_up_id = :su,
                   event_cursor = :cur, failures_in_row = 0, updated_at = now()
               WHERE id = :id RETURNING *""",
            su=su,
            cur=await AU.max_outbox(tx),
            id=a["id"],
        )
        await ctx.audit(
            tx,
            company_id=a["company_id"],
            action="automation.seal",
            action_class="A2",
            target_kind="automation",
            target_ref=ref,
            summary="sealed",
            step_up=True,
        )
        return AU.render(row, a["company_code"])


@router.post("/automations/{ref}/state", response_model=AU.Automation, responses=E)
async def set_automation_state(
    ref: str, body: AutomationStateIn, ctx: Ctx = Depends(owner_ctx)
) -> AU.Automation:
    """⟨1.13⟩ §31.7 switch a sealed automation on or off (no step-up: the seal
    already covers exactly what runs). Switching it on again clears its failure
    count. 409 while it is still `proposed`."""
    async with ctx.tx() as tx:
        a = await AU.row_of(tx, ref, lock=True)
        if a["state"] == "proposed":
            raise ApiError(409, "validation_failed", f"{ref} is not sealed yet")
        row = await tx.one(
            """UPDATE growth.automations SET state = :st, failures_in_row = 0,
                   last_error_fa = CASE WHEN :st = 'on' THEN NULL ELSE last_error_fa END,
                   off_reason = CASE WHEN :st = 'off' THEN 'owner' ELSE NULL END,
                   event_cursor = CASE WHEN :st = 'on' AND state = 'off' THEN :cur ELSE event_cursor END,
                   updated_at = now() WHERE id = :id RETURNING *""",
            st=body.state,
            cur=await AU.max_outbox(tx),
            id=a["id"],
        )
        await ctx.audit(
            tx,
            company_id=a["company_id"],
            action="automation.state",
            action_class="A2",
            target_kind="automation",
            target_ref=ref,
            summary=body.state,
        )
        return AU.render(row, a["company_code"])


@router.get("/automations", response_model=list[AU.Automation], responses=E)
async def list_automations(
    state: Literal["proposed", "on", "off"] | None = Query(default=None),
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> list[AU.Automation]:
    """⟨1.13⟩ §31.7 the automations, newest first (filter by `state` or
    `company`), each with its plain-Persian preview."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT a.*, c.code AS company_code FROM growth.automations a
               JOIN core.companies c ON c.id = a.company_id
               WHERE (CAST(:st AS text) IS NULL OR a.state = :st)
                 AND (CAST(:co AS text) IS NULL OR (a.scope = 'company' AND c.code = :co))
               ORDER BY a.created_at DESC LIMIT 200""",
            st=state,
            co=company,
        )
    return [AU.render(r, r["company_code"]) for r in rows]


@router.get("/automations/{ref}", response_model=AU.AutomationDetail, responses=E)
async def get_automation(ref: str, ctx: Ctx = Depends(owner_ctx)) -> AU.AutomationDetail:
    """⟨1.13⟩ §31.7 one automation with its last 50 runs (what fired it, each
    action's result in plain Persian)."""
    async with ctx.tx() as tx:
        a = await AU.row_of(tx, ref)
        runs = await tx.all(
            "SELECT * FROM growth.automation_runs WHERE automation_id = :a ORDER BY at DESC LIMIT 50",
            a=a["id"],
        )
    return AU.AutomationDetail(
        **AU.render(a, a["company_code"]).model_dump(), run_log=[AU.render_run(r) for r in runs]
    )
