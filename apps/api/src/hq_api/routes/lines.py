"""⟨1.12⟩ Prompt 22 (contract §30.5, §31.1): production lines. Owner only,
but the signed n8n callback.

    GET  /line-templates                     the templates (seed/lines/*.yaml)
    GET  /line-templates/{key}
    GET  /companies/{code}/lines
    POST /companies/{code}/lines             {template, platform?, channel?, title_fa} -> a draft
    GET  /lines/{ref}
    PUT  /lines/{ref}                        a new version; 🔏 line.caps (<ref>) when a cap rises
    POST /lines/{ref}/state                  {state: on|paused}
    POST /lines/{ref}/mode                   {mode}; 🔏 line.auto (<ref>) for auto
    GET  /lines/{ref}/versions
    POST /lines/{ref}/revert                 {version, note_fa?} (a new version)
    POST /lines/{ref}/copy                   {company, title_fa?} -> a draft for another company
    GET  /lines/{ref}/insights               §31.1 the learning loop
    POST /lines/{ref}/runs                   {dry?, from_step?}
    POST /lines/{ref}/steps/{key}/test       {inputs?}: that step alone, nothing kept
    GET  /lines/{ref}/runs
    GET  /line-runs/{ref}
    POST /line-runs/{ref}/rerun              {from_step}
    POST /line-runs/{ref}/seal               {approve, note_fa?} (approving: 🔏 decision.approve
                                             on the card, A3)
    POST /line-runs/{ref}/cancel             {skip?}: ⟨1.37⟩ §59.8 `skip: true` «رد کردن این نوبت»
                                             (the run `skipped`, its ledger topic freed)
    GET  /calendar/lines?from&to&company
    GET  /library?company&kind,  POST /library,  PUT /library/{id},  DELETE /library/{id}
    GET  /tts/voices                         the speakers the tts adapter offers (a day's cache)
    POST /internal/v1/lines/callback         n8n's answer, HMAC-signed (X-HQ-Signature)

As built: `POST /library` takes JSON with `files` = ids of files already
uploaded with `POST /files` (the hub's hardened upload; the api has no
multipart parser), not a multipart body.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain.gov_common import owner_tz, zone
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.lines import adapters, engine, learning, signing, store
from hq_api.lines import templates as T
from hq_api.lines.base import REGISTRY
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["lines"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"
LN = r"^LN-[0-9]{4,}$"
RN = r"^RN-[0-9]{6,}$"
VOICES_TTL_S = 24 * 3600
_voices: dict[str, Any] = {"at": 0.0, "items": []}


# ------------------------------------------------------------------ bodies --
class ChannelIn(Model):
    kind: str = Field(default="", max_length=40, pattern=r"^([a-z][a-z0-9_]{1,40})?$")
    subject: str = Field(default="", max_length=200)


class LineIn(Model):
    template: str = Field(pattern=KEY)
    platform: str | None = Field(default=None, pattern=KEY)
    channel: ChannelIn = Field(default_factory=ChannelIn)
    title_fa: str = Field(min_length=1, max_length=200)


class LinePut(Model):
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    schedule: str | None = Field(default=None, max_length=500)
    clear_schedule: bool = False  # ⟨as built⟩ the schedule removed (null means "unchanged")
    steps: list[T.StepDef] | None = Field(default=None, min_length=1, max_length=40)
    caps: T.Caps | None = None
    library: list[UUID] | None = Field(default=None, max_length=50)
    channel: ChannelIn | None = None  # ⟨as built⟩ a copied line's own channel
    auto_after: int | None = Field(default=None, ge=1, le=100)
    note_fa: str | None = Field(default=None, max_length=500)


class StateIn(Model):
    state: Literal["on", "paused"]


class ModeIn(Model):
    mode: Literal["draft", "auto"]


class RevertIn(Model):
    version: int = Field(ge=1)
    note_fa: str | None = Field(default=None, max_length=500)


class CopyIn(Model):
    company: str = Field(pattern=CODE)
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)


class RunIn(Model):
    dry: bool = False
    from_step: str | None = Field(default=None, pattern=KEY)


class RerunIn(Model):
    from_step: str = Field(pattern=KEY)


class CancelIn(Model):
    """⟨1.37⟩ §59.8 `skip`: the run is `skipped` and its topic freed in the ledger (§47)."""

    skip: bool = False


class LineSealIn(Model):
    approve: bool
    note_fa: str | None = Field(default=None, max_length=1000)


class GivenOutput(Model):
    text: str | None = Field(default=None, max_length=100_000)
    file_id: str | None = Field(default=None, max_length=64)
    files: list[str] = Field(default_factory=list, max_length=20)
    data: dict[str, Any] = Field(default_factory=dict)


class StepTestIn(Model):
    inputs: dict[str, GivenOutput] | None = None


class StepTestOut(BaseModel):
    step: str
    kind: str
    state: Literal["done", "failed"]
    prompt: str | None
    missing: list[str]
    output: store.StepOutputOut | None
    via: str
    tokens: int
    usd_equiv: Decimal
    error_fa: str | None


class LineCalendarItem(BaseModel):
    line: str
    company: str
    platform: str
    at: datetime
    state: str  # "planned" (no run yet) or the run's state
    run: str | None


class CalendarDay(BaseModel):
    day: date
    items: list[LineCalendarItem]


class LineCalendar(BaseModel):
    days: list[CalendarDay]


class AssetIn(Model):
    company: str | None = Field(default=None, pattern=CODE)  # null: the holding's
    kind: Literal["cover_folder", "voice", "prompt", "pattern", "music", "brand"]
    title_fa: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    files: list[UUID] = Field(default_factory=list, max_length=100)


class AssetPut(Model):
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    files: list[UUID] | None = Field(default=None, max_length=100)


class TtsVoice(BaseModel):
    name: str
    title_fa: str
    gender: str | None = None
    sample_file: str | None = None


class CallbackIn(Model):
    """The run and step by name, or the n8n step's `token` ("<run>:<step>")."""

    run: str | None = Field(default=None, pattern=RN)
    step: str | None = Field(default=None, pattern=KEY)
    token: str | None = Field(default=None, pattern=r"^RN-[0-9]{6,}:[a-z][a-z0-9_]{1,40}$")
    ok: bool
    text: str | None = Field(default=None, max_length=200_000)
    file_id: str | None = Field(default=None, max_length=64)
    files: list[str] = Field(default_factory=list, max_length=50)
    data: dict[str, Any] = Field(default_factory=dict)
    error_fa: str | None = Field(default=None, max_length=1000)


class CallbackOut(BaseModel):
    run: str
    step: str
    state: str


# ----------------------------------------------------------------- helpers --
async def _policy(ctx: Ctx, op: str, target: dict[str, Any], *, step_up: bool = False) -> None:
    await ctx.hub.policy.require(
        "lines",
        {"principal": ctx.who.opa(), "op": op, "target": target, "context": {"step_up": step_up}},
    )


async def _line(ctx: Ctx, tx: Any, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await store.load(tx, ref, lock=lock)


async def _out(tx: Any, row: dict[str, Any]) -> store.Line:
    return await store.render(tx, row, await owner_tz(tx))


async def _changed(
    ctx: Ctx, tx: Any, row: dict[str, Any], action: str, summary: str, *, step_up: bool = False,
    data: dict[str, Any] | None = None,
) -> None:  # fmt: skip
    await ctx.audit(
        tx,
        company_id=row["company_id"],
        action=action,
        action_class="A2",
        target_kind="line",
        target_ref=row["ref"],
        summary=summary[:500],
        step_up=step_up,
    )
    await ctx.interaction(
        tx,
        company_id=row["company_id"],
        kind="setting",
        action=action,
        target_kind="line",
        target_ref=row["ref"],
        data=data or {},
    )
    await ctx.emit(
        tx, row["company"], "line.updated", row["ref"], {"version": row["version"], **(data or {})}
    )


# --------------------------------------------------------------- templates --
@router.get("/line-templates", response_model=list[T.LineTemplate], responses=E)
async def list_line_templates(ctx: Ctx = Depends(owner_ctx)) -> list[T.LineTemplate]:
    """§30.1 every line template (seed/lines/*.yaml): its steps, defaults and
    what it makes. A file that does not hold together is left out."""
    return sorted(T.load().values(), key=lambda t: t.key)


@router.get("/line-templates/{key}", response_model=T.LineTemplate, responses=E)
async def get_line_template(key: str, ctx: Ctx = Depends(owner_ctx)) -> T.LineTemplate:
    """One line template with its steps and their starting prompts."""
    return T.get(key)


# ------------------------------------------------------------------- lines --
@router.get("/companies/{code}/lines", response_model=list[store.Line], responses=E)
async def list_company_lines(code: str, ctx: Ctx = Depends(owner_ctx)) -> list[store.Line]:
    """Every production line of the company, oldest first, with its next
    scheduled run and its latest run."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        tz = await owner_tz(tx)
        return [await store.render(tx, r, tz) for r in await store.of_company(tx, company.id)]


@router.post("/companies/{code}/lines", response_model=store.Line, status_code=201, responses=E)
async def create_company_line(
    code: str, body: LineIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new line from a template, as a `draft`: nothing runs on its own and
    its publish waits for the owner's seal until it is made automatic."""
    company = await ctx.hub.companies.by_code(code)
    template = T.get(body.template)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await _policy(ctx, "line.create", {"company": code, "template": body.template})
        row = await store.insert_line(
            tx,
            ctx.who,
            company_id=company.id,
            template=template,
            platform=body.platform or template.platform,
            channel=body.channel.model_dump(),
            title_fa=body.title_fa.strip(),
        )
        await _changed(
            ctx, tx, row, "line.create", f"from template {template.key}", data={"new": True}
        )
        out = await _out(tx, row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/lines/{ref}", response_model=store.Line, responses=E)
async def get_line(ref: str, ctx: Ctx = Depends(owner_ctx)) -> store.Line:
    """One line: its steps as this line sets them, caps, schedule, state,
    mode and good runs (`offer_auto`: the app offers «خودکار کن»)."""
    async with ctx.tx() as tx:
        return await _out(tx, await _line(ctx, tx, ref))


@router.put("/lines/{ref}", response_model=store.Line, responses=E)
async def update_line(
    ref: str, body: LinePut, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> store.Line:
    """A new version of the line (the previous one kept). A higher cap needs
    🔏 `line.caps` on the line's ref; `clear_schedule` removes the schedule."""
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref, lock=True)
        change: dict[str, Any] = {}
        if body.title_fa is not None:
            change["title_fa"] = body.title_fa.strip()
        if body.clear_schedule:
            change["schedule"] = None
        elif body.schedule is not None:
            change["schedule"] = body.schedule.strip() or None
        if body.steps is not None:
            change["steps"] = [s.model_dump() for s in body.steps]
        if body.caps is not None:
            change["caps"] = body.caps.model_dump()
        if body.library is not None:
            change["library"] = [str(x) for x in body.library]
        if body.channel is not None:
            change["channel"] = body.channel.model_dump()
        if body.auto_after is not None:
            change["auto_after"] = body.auto_after
        rise = "caps" in change and store.caps_rise(row["caps"], change["caps"])
        if rise:
            await stepup.consume(tx, request, ctx.who, "line.caps", ref)
        await _policy(ctx, "line.update", {"line": ref, "caps_rise": rise}, step_up=rise)
        out = await store.update(tx, ctx.who, row, change, body.note_fa)
        if out["version"] != row["version"]:
            await _changed(
                ctx, tx, out, "line.update", f"version {out['version']}: " + ", ".join(sorted(change)),
                step_up=rise, data={"fields": sorted(change)},
            )  # fmt: skip
        return await _out(tx, out)


@router.post("/lines/{ref}/state", response_model=store.Line, responses=E)
async def set_line_state(ref: str, body: StateIn, ctx: Ctx = Depends(owner_ctx)) -> store.Line:
    """`on`: its schedule makes runs (with HQ_LINES on); `paused`: it makes
    none (runs already started go on)."""
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref, lock=True)
        await _policy(ctx, "line.state", {"line": ref, "state": body.state})
        if row["state"] != body.state:
            row = await store.set_state(tx, row, body.state)
            await _changed(ctx, tx, row, "line.state", body.state, data={"state": body.state})
        return await _out(tx, row)


@router.post("/lines/{ref}/mode", response_model=store.Line, responses=E)
async def set_line_mode(
    ref: str, body: ModeIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> store.Line:
    """`auto` publishes without the owner's seal (🔏 `line.auto` on the ref);
    `draft` brings the seal back."""
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref, lock=True)
        su = body.mode == "auto" and row["mode"] != "auto"
        if su:
            await stepup.consume(tx, request, ctx.who, "line.auto", ref)
        await _policy(ctx, "line.mode", {"line": ref, "mode": body.mode}, step_up=su)
        if row["mode"] != body.mode:
            row = await store.set_mode(tx, row, body.mode)
            await _changed(
                ctx, tx, row, "line.mode", body.mode, step_up=su, data={"mode": body.mode}
            )
        return await _out(tx, row)


@router.get("/lines/{ref}/versions", response_model=list[store.LineVersion], responses=E)
async def list_line_versions(ref: str, ctx: Ctx = Depends(owner_ctx)) -> list[store.LineVersion]:
    """Every version of the line, newest first, each with the whole line."""
    async with ctx.tx() as tx:
        return await store.versions(tx, await _line(ctx, tx, ref))


@router.post("/lines/{ref}/revert", response_model=store.Line, responses=E)
async def revert_line(
    ref: str, body: RevertIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> store.Line:
    """A new version with an old version's body (🔏 `line.caps` when it
    raises a cap)."""
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref, lock=True)
        if body.version >= row["version"]:
            raise ApiError(422, "validation_failed", fields={"version": "an earlier version"})
        old = await store.version_body(tx, row["id"], body.version)
        change = {
            k: old[k] for k in store.BODY_KEYS if k in old and k not in ("template", "platform")
        }
        rise = store.caps_rise(row["caps"], change.get("caps") or row["caps"])
        if rise:
            await stepup.consume(tx, request, ctx.who, "line.caps", ref)
        await _policy(ctx, "line.update", {"line": ref, "caps_rise": rise}, step_up=rise)
        out = await store.update(
            tx, ctx.who, row, change, body.note_fa or f"برگشت به نسخه‌ی {body.version}"
        )
        await _changed(
            ctx, tx, out, "line.revert", f"version {body.version} -> {out['version']}",
            step_up=rise, data={"version": body.version},
        )  # fmt: skip
        return await _out(tx, out)


@router.post("/lines/{ref}/copy", response_model=store.Line, status_code=201, responses=E)
async def copy_line(ref: str, body: CopyIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The line as a `draft` of another company (§30.7): its steps, prompts,
    caps and schedule; the holding's library kept, the other company's left
    out; its channel's subject empty (the new company's own is set after)."""
    company = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        row = await _line(ctx, tx, ref)
        await _policy(ctx, "line.create", {"company": body.company, "copy_of": ref})
        src = store.body_of(row)
        keep = [
            str(a["id"])
            for a in await store.assets_of(tx, src["library"])
            if a["company_kind"] == "holding"
        ]
        out = await store.insert_line(
            tx,
            ctx.who,
            company_id=company.id,
            template=T.get(row["template"]) if row["template"] in T.load() else _stub(row),
            platform=row["platform"],
            channel={"kind": (row["channel"] or {}).get("kind", ""), "subject": ""},
            title_fa=(body.title_fa or row["title_fa"]).strip(),
            copied_from=ref,
            body={**src, "library": keep},
        )
        await _changed(ctx, tx, out, "line.create", f"copy of {ref}", data={"copy_of": ref})
        res = await _out(tx, out)
        if idem:
            await idem.store(tx, 201, res.model_dump(mode="json"))
    return res


def _stub(row: dict[str, Any]) -> T.LineTemplate:
    """A line whose template file is gone still copies (its own body)."""
    return T.LineTemplate.model_validate(
        {
            "key": row["template"],
            "title_fa": row["title_fa"],
            "platform": row["platform"],
            "version": row["template_version"],
            "steps": row["steps"],
        }
    )


@router.get("/lines/{ref}/insights", response_model=store.Insights, responses=E)
async def get_line_insights(ref: str, ctx: Ctx = Depends(owner_ctx)) -> store.Insights:
    """§31.1 what the line's published runs taught (code, no model): ranked by
    its template's metric, the best hour, length, voice and pattern, the top
    hooks and plain Persian lessons."""
    async with ctx.tx() as tx:
        return await learning.get(tx, await _line(ctx, tx, ref))


# -------------------------------------------------------------------- runs --
async def _run_out(tx: Any, ref: str, storage: Any | None = None) -> store.LineRunOut:
    return await store.render_run(tx, await store.load_run(tx, ref), storage)


@router.post("/lines/{ref}/runs", response_model=store.LineRunOut, status_code=201, responses=E)
async def start_line_run(
    ref: str, body: RunIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A run now (`dry`: every step but publish and deliver leaves nothing:
    «آزمایش کامل»). `from_step`: the steps before it reuse the latest run's
    outputs. A lock or the line's daily cap answers a `skipped` run."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        row = await _line(ctx, tx, ref)
        await _policy(ctx, "line.run", {"line": ref, "dry": body.dry})
        run = await engine.start_run(
            tx, row, trigger="owner", who=ctx.who, dry=body.dry, from_step=body.from_step
        )
        await _changed(
            ctx, tx, row, "line.run", f"{run['ref']} {run['state']}" + (" dry" if body.dry else ""),
            data={"run": run["ref"], "dry": body.dry},
        )  # fmt: skip
        out = await _run_out(tx, run["ref"])
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    if out.state == "queued":
        await engine.kick(ctx.hub, out.ref)
    return out


@router.post(
    "/lines/{ref}/steps/{key}/test", response_model=StepTestOut, responses={**E, 503: E[422]}
)
async def run_line_step_test(
    ref: str, key: str, body: StepTestIn, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """That step alone, now (publish and deliver dry), with the given inputs
    or the latest run's; nothing is kept beyond this answer."""
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref)
        engine.step_def(await store.version_body(tx, row["id"], row["version"]), key)
        await _policy(ctx, "line.test", {"line": ref, "step": key})
    given = {k: v.model_dump() for k, v in (body.inputs or {}).items()}
    client = getattr(ctx.hub, "temporal", None)
    if client is None:  # tests, or an api without the worker: inline
        return await engine.test_step(ctx.hub, ref, key, given)
    try:
        return await client.execute_workflow(
            "LineStepTest",
            args=[ref, key, given],
            id=f"line-step-test-{ref}-{uuid.uuid4().hex[:10]}",
            task_queue=ctx.hub.settings.task_queue,
            execution_timeout=timedelta(seconds=360),
        )
    except Exception as exc:
        raise ApiError(503, "channel_not_configured", "the step could not run now") from exc


@router.get("/lines/{ref}/runs", response_model=Page[store.LineRunOut], responses=E)
async def list_line_runs(
    ref: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[store.LineRunOut]:
    """The line's runs, newest first, each step by step with its output."""
    c0, c1 = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        row = await _line(ctx, tx, ref)
        rows = await tx.all(
            """SELECT r.ref, r.at, r.id FROM lines.runs r WHERE r.line_id = :line
                 AND (CAST(:c0 AS timestamptz) IS NULL
                      OR (r.at, r.id) < (CAST(:c0 AS timestamptz), CAST(:c1 AS uuid)))
               ORDER BY r.at DESC, r.id DESC LIMIT :n""",
            line=row["id"],
            c0=c0,
            c1=c1,
            n=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("at", "id"))
        return Page(items=[await _run_out(tx, r["ref"]) for r in items], next_cursor=nxt)


@router.get("/line-runs/{ref}", response_model=store.LineRunOut, responses=E)
async def get_line_run(ref: str, ctx: Ctx = Depends(owner_ctx)) -> store.LineRunOut:
    """One run, step by step: each output (text, files, data), the tool that
    answered, tokens, the reason of a failure, the card it waits on. ⟨1.37⟩
    §59.8 a flow's run also names its automation, playbook and version, the
    day's topic, its results and minutes; each step its seat, helper, model,
    effort, cost and files (a `.txt` or `.md` with its first 4000 letters)."""
    async with ctx.tx() as tx:
        return await _run_out(tx, ref, ctx.hub.storage)


@router.post(
    "/line-runs/{ref}/rerun", response_model=store.LineRunOut, status_code=201, responses=E
)
async def rerun_line_run(
    ref: str, body: RerunIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new run from one step: the steps before it reuse this run's outputs
    (the line's current version runs the rest)."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        src = await store.load_run(tx, ref)
        row = await store.by_id(tx, src["line_id"])
        await _policy(ctx, "line.run", {"line": row["ref"], "rerun_of": ref})
        run = await engine.start_run(
            tx,
            row,
            trigger="owner",
            who=ctx.who,
            dry=src["dry"],
            from_step=body.from_step,
            source=src,
        )
        await _changed(
            ctx, tx, row, "line.run", f"{run['ref']} rerun of {ref} from {body.from_step}",
            data={"run": run["ref"], "rerun_of": ref},
        )  # fmt: skip
        out = await _run_out(tx, run["ref"])
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    if out.state == "queued":
        await engine.kick(ctx.hub, out.ref)
    return out


@router.post("/line-runs/{ref}/seal", response_model=store.LineRunOut, responses=E)
async def seal_line_run(
    ref: str, body: LineSealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> store.LineRunOut:
    """The owner's seal on the step the run waits at (its `line_publish`
    card, A3): approving needs 🔏 `decision.approve` on the card's ref and
    lets the run go on; rejecting ends it with the note."""
    from hq_api.domain import decisions as D

    async with ctx.tx() as tx:
        run = await store.load_run(tx, ref)
        if run["state"] != "waiting" or not run["decision_ref"]:
            raise ApiError(409, "validation_failed", f"{ref} waits for no seal")
        d = await D.load(tx, run["decision_ref"], lock=True)
        if d["status"] != "pending":
            raise ApiError(409, "decision_not_pending", f"{d['ref']} is {d['status']}")
        su = None
        if body.approve:
            su = await stepup.consume(tx, request, ctx.who, "decision.approve", d["ref"])
        await ctx.hub.policy.require("decisions", D.opa_input(ctx.who, d, quota_ok=False))
        verdict: Literal["approved", "rejected"] = "approved" if body.approve else "rejected"
        await D.decide(tx, ctx.who, d, verdict, note=body.note_fa, step_up_id=su, hub=ctx.hub)
        await ctx.audit(
            tx,
            company_id=d["company_id"],
            action="decision.approve" if body.approve else "decision.reject",
            action_class="A3",
            target_kind="decision",
            target_ref=d["ref"],
            summary=f"line_publish {ref} -> {verdict}",
            step_up=su is not None,
        )
        await ctx.interaction(
            tx,
            company_id=d["company_id"],
            kind="decision",
            action="line_run.seal",
            target_kind="line_run",
            target_ref=ref,
            data={"verdict": verdict, "note": body.note_fa, "decision": d["ref"]},
        )
        out = await _run_out(tx, ref)
    await engine.wake(ctx.hub, ref)
    return out


@router.post("/line-runs/{ref}/cancel", response_model=store.LineRunOut, responses=E)
async def cancel_line_run(
    ref: str, body: CancelIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> store.LineRunOut:
    """Stops the run before its next step (its open card withdrawn). ⟨1.37⟩
    `skip: true` («رد کردن این نوبت»): the run ends `skipped` and the topic it
    claimed in the ledger is free for another day."""
    skip = body is not None and body.skip
    async with ctx.tx() as tx:
        run = await store.load_run(tx, ref, lock=True)
        await _policy(ctx, "line.cancel", {"run": ref})
        await engine.cancel(tx, run, skip=skip)
        await ctx.audit(
            tx, company_id=run["company_id"], action="line_run.cancel", action_class="A2",
            target_kind="line_run", target_ref=ref,
            summary="skipped by the owner, topic freed" if skip else "cancelled by the owner",
        )  # fmt: skip
        out = await _run_out(tx, ref)
    await engine.wake(ctx.hub, ref)
    return out


# ---------------------------------------------------------------- calendar --
@router.get("/calendar/lines", response_model=LineCalendar, responses=E)
async def line_calendar(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> LineCalendar:
    """Each day's planned runs of every `on` line (by its schedule, the
    owner's zone) and the runs already made; at most 62 days."""
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        tz = await owner_tz(tx)
        today = datetime.now(UTC).astimezone(zone(tz)).date()
        start_day = from_ or today
        end_day = to or start_day + timedelta(days=7)
        if end_day < start_day or (end_day - start_day).days > 62:
            raise ApiError(422, "validation_failed", fields={"to": "from + 0..62 days"})
        z = zone(tz)
        start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=z).astimezone(UTC)
        end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=z).astimezone(
            UTC
        ) + timedelta(days=1)
        days = await store.calendar(tx, start, end, tz, co)
    return LineCalendar.model_validate({"days": days})


# ----------------------------------------------------------------- library --
@router.get("/library", response_model=list[store.Asset], responses=E)
async def list_library(
    company: str | None = Query(default=None, pattern=CODE),
    kind: Literal["cover_folder", "voice", "prompt", "pattern", "music", "brand"] | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[store.Asset]:
    """The library: with `company`, its own assets and the holding's (what
    its lines may use); without, every asset."""
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            store.ASSET_SQL
            + """ WHERE a.state = 'active' AND (CAST(:kind AS text) IS NULL OR a.kind = :kind)
                    AND (CAST(:co AS uuid) IS NULL OR a.company_id = :co OR c.kind = 'holding')
                  ORDER BY a.created_at""",
            kind=kind,
            co=co,
        )
        return [store.render_asset(r) for r in rows]


@router.post("/library", response_model=store.Asset, status_code=201, responses=E)
async def create_library_asset(
    body: AssetIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A library asset (a cover folder, a voice, a prompt, a pattern, music, a
    brand); `company` null: the holding's, for every company. `files`: ids
    from `POST /files`."""
    company = (
        await ctx.hub.companies.by_code(body.company)
        if body.company
        else await ctx.hub.companies.holding()
    )
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await _policy(ctx, "library.write", {"company": body.company, "kind": body.kind})
        await store.check_files(tx, body.files)
        aid = await tx.scalar(
            """INSERT INTO lines.assets (company_id, kind, title_fa, config, files)
               VALUES (:co, :kind, :title, CAST(:config AS jsonb), CAST(:files AS uuid[]))
               RETURNING id""",
            co=company.id,
            kind=body.kind,
            title=body.title_fa.strip(),
            config=store.dumps(body.config),
            files=[str(f) for f in body.files],
        )
        await ctx.audit(
            tx, company_id=company.id, action="library.create", action_class="A2",
            target_kind="asset", target_ref=str(aid), summary=f"{body.kind}: {body.title_fa[:200]}",
        )  # fmt: skip
        await ctx.emit(tx, company.code, "line.updated", None, {"library": str(aid)})
        out = store.render_asset(await store.load_asset(tx, aid))
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.put("/library/{id}", response_model=store.Asset, responses=E)
async def update_library_asset(
    id: UUID, body: AssetPut, ctx: Ctx = Depends(owner_ctx)
) -> store.Asset:
    """A library asset's title, config or files changed (its version + 1)."""
    async with ctx.tx() as tx:
        cur = await store.load_asset(tx, id, lock=True)
        await _policy(ctx, "library.write", {"company": cur["company"], "kind": cur["kind"]})
        if body.files is not None:
            await store.check_files(tx, body.files)
        await tx.exec(
            """UPDATE lines.assets SET title_fa = coalesce(:title, title_fa),
                   config = coalesce(CAST(:config AS jsonb), config),
                   files = coalesce(CAST(:files AS uuid[]), files), version = version + 1,
                   updated_at = now() WHERE id = :id""",
            id=id,
            title=body.title_fa.strip() if body.title_fa else None,
            config=store.dumps(body.config) if body.config is not None else None,
            files=[str(f) for f in body.files] if body.files is not None else None,
        )
        await ctx.audit(
            tx, company_id=cur["company_id"], action="library.update", action_class="A2",
            target_kind="asset", target_ref=str(id), summary=cur["kind"],
        )  # fmt: skip
        return store.render_asset(await store.load_asset(tx, id))


@router.delete("/library/{id}", status_code=204, response_class=Response, responses=E)
async def delete_library_asset(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """The asset leaves the library (kept in the database, never shown again;
    a line that names it no longer gets it)."""
    async with ctx.tx() as tx:
        cur = await store.load_asset(tx, id, lock=True)
        await _policy(ctx, "library.write", {"company": cur["company"], "kind": cur["kind"]})
        await tx.exec(
            "UPDATE lines.assets SET state = 'deleted', updated_at = now() WHERE id = :id", id=id
        )
        await ctx.audit(
            tx, company_id=cur["company_id"], action="library.delete", action_class="A2",
            target_kind="asset", target_ref=str(id), summary=cur["kind"],
        )  # fmt: skip
    return Response(status_code=204)


@router.get("/tts/voices", response_model=list[TtsVoice], responses=E)
async def list_tts_voices(ctx: Ctx = Depends(owner_ctx)) -> list[TtsVoice]:
    """The speakers the tts step can use (as AI Studio offers them), cached a
    day; empty until the tts adapter can read them."""
    if _voices["items"] and time.monotonic() - float(_voices["at"]) < VOICES_TTL_S:
        return list(_voices["items"])
    adapters.load()
    read = getattr(REGISTRY.get("tts"), "voices", None)
    if read is None:
        return []
    try:
        got = [TtsVoice.model_validate(v) for v in await read(ctx.hub)]
    except Exception:  # noqa: BLE001 - the list is a convenience; the step says why it fails
        return list(_voices["items"])
    _voices.update(at=time.monotonic(), items=got)
    return got


# ---------------------------------------------------------------- internal --
CALLBACK_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": CallbackIn.model_json_schema(),
                "example": {
                    "token": "RN-000001:flow", "ok": True, "text": "متن آماده",
                    "file_id": None, "files": [], "data": {"rows": 12}, "error_fa": None,
                },
            }
        },
    }
}  # fmt: skip


async def n8n_secret(hub: Hub) -> str:
    """kv/hq/n8n (loaded with the secrets; read again when it was not there)."""
    secret = str(getattr(hub.secrets, "n8n_secret", "") or "")
    if secret or hub.bao is None:
        return secret
    from hq_common.openbao import OpenBaoError

    try:
        data = await hub.bao.read_kv("hq/n8n")
    except OpenBaoError:
        return ""
    return str((data or {}).get("secret") or "")


@internal_router.post(
    "/lines/callback",
    response_model=CallbackOut,
    responses={**E, 400: E[422]},
    openapi_extra=CALLBACK_BODY,
)
async def line_callback(request: Request, hub: Hub = Depends(get_hub)) -> CallbackOut:
    """n8n's answer to a waiting `n8n` step (contract §30.4), signed with
    HMAC-SHA256 in `X-HQ-Signature: t=<unix>,v1=<hex>` over `<t>.<raw body>`
    (5 minutes at most). A bad or missing signature: 401, nothing read."""
    raw = await request.body()
    if not signing.verify(await n8n_secret(hub), raw, request.headers.get(signing.HEADER)):
        raise ApiError(401, "unauthenticated", "bad signature")
    try:
        body = CallbackIn.model_validate_json(raw)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", "not a callback body") from exc
    data = body.model_dump()
    if body.token:
        data["run"], data["step"] = body.token.split(":", 1)
    if not data["run"] or not data["step"]:
        raise ApiError(422, "validation_failed", fields={"token": "the run and step, or a token"})
    out = await engine.on_callback(hub, data)
    return CallbackOut(**out)
