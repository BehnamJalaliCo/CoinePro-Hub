"""⟨1.31⟩ §48 A company's narrator, set once (domain/narrator.py).

GET  /companies/{code}/narrator        the company's narrator (or that it has none), AI Studio's
                                       voices, and whether the hub is signed in there
PUT  /companies/{code}/narrator        {voice, style_fa?}: the owner sets it (a tap)
POST /internal/v1/narrator             narrator.set (A1): an agent that works on the owner's own
                                       order sets it for that work's company, as he asked there
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import hands as HANDS
from hq_api.domain import narrator as NR
from hq_api.domain import order_report as OR
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model

router = APIRouter(tags=["media"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"


class NarratorIn(Model):
    voice: str = Field(pattern=r"^[A-Za-z]{2,30}$")
    style_fa: str | None = Field(default=None, max_length=NR.STYLE_MAX)


class NarratorSetIn(NarratorIn):
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{6,}$")


@router.get("/companies/{code}/narrator", response_model=NR.Narrator, responses=E)
async def get_narrator(code: str, ctx: Ctx = Depends(owner_ctx)) -> NR.Narrator:
    """⟨1.31⟩ §48 The company's narrator: the voice and the style every `speech.make` for its
    content uses (`set: false`: none yet, a model still chooses). `voices`: AI Studio's prebuilt
    speakers; `aistudio`: whether the hub's browser is signed in to it."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await NR.render(tx, company)


@router.put("/companies/{code}/narrator", response_model=NR.Narrator, responses=E)
async def put_narrator(code: str, body: NarratorIn, ctx: Ctx = Depends(owner_ctx)) -> NR.Narrator:
    """⟨1.31⟩ §48 The owner sets the company's narrator once: from now every voice made for
    this company's content is this voice in this style, whatever a model asks for. `422` for a
    voice AI Studio does not have. A tap, no step-up."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        row = await NR.put(tx, company.id, voice=body.voice, style_fa=body.style_fa, by=ctx.who)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="narrator.set",
            action_class="A2",
            target_kind="company",
            target_ref=code,
            summary=f"the narrator: {row['voice']}" + (" with a style" if row["style_fa"] else ""),
        )
        return await NR.render(tx, company)


@internal_router.post("/narrator", response_model=NR.Narrator, responses=E)
async def agent_narrator(body: NarratorSetIn, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """⟨1.31⟩ narrator.set (A1): the agent that works on the owner's own order sets the narrator
    of that work's company, as he asked in the session («گوینده را … بگذار»). Only for a work of
    an open order (its run's work, or `work`, assigned to the caller): `403` otherwise. The
    company's own page changes it later."""
    who = ctx.who
    if not who.is_agent or who.company_id is None or who.role == "system":
        raise ApiError(403, "policy_denied", "a working role only")
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        w = await HANDS.the_work(tx, who, body.work)
        order = await OR.order_of_work(tx, w["id"])
    await allow(ctx, "narrator.set", {"company": who.company, "assigned": order is not None})
    async with ctx.hub.db.tx(wide) as tx:
        company = await ctx.hub.companies.by_id(w["company_id"])
        cur = await NR.of(tx, company.id)
        if cur is not None and cur["by_kind"] == "owner":
            # ⟨2026-11-13⟩ the owner's own choice stays (F-0018: the holder set it back from its
            # old notes a minute after the owner chose); only the owner changes it
            style = f" ({cur['style_fa']})" if cur.get("style_fa") else " (بی حالت)"
            raise ApiError(
                409,
                "validation_failed",
                fields={"voice": "the owner set this company's narrator himself"},
                message_fa=f"گوینده‌ی این شرکت را مدیر کل خودش گذاشته است: {cur['voice']}{style}. "
                "همان میماند و ساخت صدا خودش همان را میگیرد؛ عوض کردنش فقط با خود مدیر کل است.",
            )
        row = await NR.put(tx, company.id, voice=body.voice, style_fa=body.style_fa, by=who)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="narrator.set",
            action_class="A1",
            target_kind="company",
            target_ref=company.code,
            summary=f"the narrator: {row['voice']}, set by {who.code} in {order}",
        )
        return await NR.render(tx, company, full=False)
