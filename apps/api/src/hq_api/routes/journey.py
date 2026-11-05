"""⟨1.15⟩ Prompt 24 (contract §33.8-§33.9): the company journey, personas and the message test.
Owner only (OPA hq.journey).

    GET    /companies/{code}/journey            the stages, where the company is, the one line
    GET    /journeys                            every company, and all reached stages on one timeline
    GET    /companies/{code}/personas
    POST   /companies/{code}/personas           {name_fa, ...}: a persona (`source: kb_suggested` keeps
                                                one the suggestion proposed)
    PATCH  /personas/{id}                       edit (version +1)
    DELETE /personas/{id}                       archive (nothing is deleted)
    POST   /companies/{code}/personas/suggest   ONE mid-model call from the company's knowledge; saves nothing
    POST   /companies/{code}/personas/test      {text}: ONE call for all personas, checked by code

A stage is reached by code from rows; the model only writes the one line `next_fa` when a stage
changes, and the persona answers. The owner's explicit suggest or test that the model cannot answer
is a 502 with a plain Persian reason."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import journey as J
from hq_api.domain import personas as P
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model

router = APIRouter(tags=["journey"])
E = responses(401, 403, 404, 409, 422)
E502 = {**E, 502: E[422]}


class PersonaIn(Model):
    name_fa: str = Field(min_length=1, max_length=100)
    summary_fa: str = Field(min_length=1, max_length=1000)
    pains_fa: list[str] = Field(default_factory=list, max_length=8)
    objections_fa: list[str] = Field(default_factory=list, max_length=8)
    channel_fa: str = Field(default="", max_length=200)
    source: Literal["owner", "kb_suggested"] = "owner"


class PersonaPatch(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=100)
    summary_fa: str | None = Field(default=None, min_length=1, max_length=1000)
    pains_fa: list[str] | None = Field(default=None, max_length=8)
    objections_fa: list[str] | None = Field(default=None, max_length=8)
    channel_fa: str | None = Field(default=None, max_length=200)


class PersonaTestIn(Model):
    text: str = Field(min_length=1, max_length=P.MAX_TEXT)


async def _policy(ctx: Ctx, op: str, company: str | None) -> None:
    await ctx.hub.policy.require(
        "journey", {"principal": ctx.who.opa(), "op": op, "target": {"company": company}}
    )


async def _company(ctx: Ctx, code: str) -> Any:
    c = await ctx.hub.companies.by_code(code)
    if c.kind == "holding":
        raise J.not_found(code)  # the holding has no journey and no personas
    return c


# ----------------------------------------------------------------- journey --
@router.get("/companies/{code}/journey", response_model=J.Journey, responses=E)
async def get_journey(code: str, ctx: Ctx = Depends(owner_ctx)) -> J.Journey:
    """⟨1.15⟩ §33.8 the company's stages (data: the default list, or its kit's), each reached by
    code from existing rows with its evidence; `current` is the latest reached; `next_fa` is one line
    written by a mid model only when a stage changed (a plain line made by code when it is down).
    A source another part has not built yet leaves its stage unreached, never an error."""
    await _policy(ctx, "journey.read", code)
    return await J.refresh_company(ctx.hub, await _company(ctx, code))


@router.get("/journeys", response_model=J.JourneyBoard, responses=E)
async def get_journeys(ctx: Ctx = Depends(owner_ctx)) -> J.JourneyBoard:
    """⟨1.15⟩ §33.8 every company's journey, and every reached stage of every company on one
    timeline, newest first."""
    await _policy(ctx, "journey.read", None)
    return await J.board(ctx.hub)


# ---------------------------------------------------------------- personas --
@router.get("/companies/{code}/personas", response_model=list[P.PersonaRecord], responses=E)
async def list_personas(code: str, ctx: Ctx = Depends(owner_ctx)) -> list[P.PersonaRecord]:
    """⟨1.15⟩ §33.9 the company's personas, oldest first (archived ones are not listed)."""
    await _policy(ctx, "persona.read", code)
    company = await _company(ctx, code)
    async with ctx.tx() as tx:
        rows = await P.active(tx, company.id)
    return [P.record(r, company.code) for r in rows]


@router.post(
    "/companies/{code}/personas", response_model=P.PersonaRecord, status_code=201, responses=E
)
async def add_persona(code: str, body: PersonaIn, ctx: Ctx = Depends(owner_ctx)) -> P.PersonaRecord:
    """⟨1.15⟩ §33.9 a persona the owner wrote, or (`source: kb_suggested`) one of the suggestion
    he decided to keep. At most 8 per company."""
    await _policy(ctx, "persona.write", code)
    company = await _company(ctx, code)
    async with ctx.tx() as tx:
        row = await P.create(
            tx,
            company.id,
            name_fa=body.name_fa,
            summary_fa=body.summary_fa,
            pains_fa=body.pains_fa,
            objections_fa=body.objections_fa,
            channel_fa=body.channel_fa,
            source=body.source,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="persona.create",
            action_class="A1",
            target_kind="persona",
            target_ref=str(row["id"]),
            summary=f"persona {body.source}",
        )
    return P.record(row, company.code)


async def _persona(ctx: Ctx, tx: Any, pid: UUID) -> tuple[dict[str, Any], Any]:
    row = await tx.first(
        "SELECT * FROM growth.personas WHERE id = :id AND archived_at IS NULL", id=pid
    )
    if row is None:
        raise ApiError(404, "not_found", "persona")
    return row, await ctx.hub.companies.by_id(row["company_id"])


@router.patch("/personas/{pid}", response_model=P.PersonaRecord, responses=E)
async def edit_persona(
    pid: UUID, body: PersonaPatch, ctx: Ctx = Depends(owner_ctx)
) -> P.PersonaRecord:
    """⟨1.15⟩ §33.9 edit a persona; `version` goes up by one and a kept suggestion becomes the
    owner's own (`source: owner`)."""
    async with ctx.tx() as tx:
        row, company = await _persona(ctx, tx, pid)
        await _policy(ctx, "persona.write", company.code)
        fields = body.model_dump(exclude_unset=True, exclude_none=True)
        if not fields:
            raise ApiError(422, "validation_failed", fields={"body": "nothing to change"})
        new = {
            "name_fa": P.clean(fields.get("name_fa", row["name_fa"]), 100),
            "summary_fa": P.clean(fields.get("summary_fa", row["summary_fa"]), 1000),
            "channel_fa": P.clean(fields.get("channel_fa", row["channel_fa"]), 200),
            "pains": fields.get("pains_fa"),
            "objections": fields.get("objections_fa"),
        }
        updated = await tx.first(
            """UPDATE growth.personas SET name_fa = :n, summary_fa = :s, channel_fa = :c,
                      pains_fa = COALESCE(CAST(:p AS jsonb), pains_fa),
                      objections_fa = COALESCE(CAST(:o AS jsonb), objections_fa),
                      source = 'owner', updated_at = now()
               WHERE id = :id RETURNING *""",
            id=pid,
            n=new["name_fa"],
            s=new["summary_fa"],
            c=new["channel_fa"],
            p=None
            if new["pains"] is None
            else json.dumps(P.clean_list(new["pains"], 300), ensure_ascii=False),
            o=None
            if new["objections"] is None
            else json.dumps(P.clean_list(new["objections"], 300), ensure_ascii=False),
        )
        assert updated is not None
        await ctx.audit(
            tx,
            company_id=updated["company_id"],
            action="persona.update",
            action_class="A1",
            target_kind="persona",
            target_ref=str(pid),
            summary=f"version {updated['version']}",
        )
    return P.record(updated, company.code)


@router.delete("/personas/{pid}", status_code=204, responses=E)
async def archive_persona(pid: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """⟨1.15⟩ §33.9 archive a persona (it leaves the list and the tests; the row stays)."""
    async with ctx.tx() as tx:
        row, company = await _persona(ctx, tx, pid)
        await _policy(ctx, "persona.write", company.code)
        await tx.exec(
            "UPDATE growth.personas SET archived_at = now(), updated_at = now() WHERE id = :id",
            id=pid,
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="persona.archive",
            action_class="A1",
            target_kind="persona",
            target_ref=str(pid),
            summary="archived",
        )
    return Response(status_code=204)


@router.post(
    "/companies/{code}/personas/suggest", response_model=P.PersonaSuggestion, responses=E502
)
async def suggest_personas(code: str, ctx: Ctx = Depends(owner_ctx)) -> P.PersonaSuggestion:
    """⟨1.15⟩ §33.9 up to four personas proposed from the company's approved knowledge by ONE
    mid-model call (task class `persona_test`). Nothing is saved: the owner keeps one by posting it
    to the personas with `source: kb_suggested`. 422 when the company has no knowledge yet; 502 when
    the model cannot answer."""
    await _policy(ctx, "persona.suggest", code)
    return await P.suggest(ctx.hub, await _company(ctx, code))


@router.post("/companies/{code}/personas/test", response_model=P.PersonaTest, responses=E502)
async def run_persona_test(
    code: str, body: PersonaTestIn, ctx: Ctx = Depends(owner_ctx)
) -> P.PersonaTest:
    """⟨1.15⟩ §33.9 a message tested against every persona of the company in ONE model call (task
    class `persona_test`, a strict schema, checked by code): a score 0..100, whether the persona
    would act, its objection and a fix. `average` and `lowest` are computed by code. 422 with no
    personas; 502 when the model cannot answer."""
    await _policy(ctx, "persona.test", code)
    company = await _company(ctx, code)
    test, _ = await P.run_test(ctx.hub, company, body.text)
    async with ctx.tx() as tx:
        await ctx.audit(
            tx,
            company_id=company.id,
            action="persona.test",
            action_class="A0",
            target_kind="persona_test",
            target_ref=str(test.id),
            summary=f"average {test.average}, lowest {test.lowest}",
        )
    return test
