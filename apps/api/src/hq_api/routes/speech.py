"""`speech.make` (A1): a voice from Google AI Studio for the media roles (domain/speech_make.py).

    POST /internal/v1/speech/make          {text_fa, voice?, style?}: a job (202 `running`, its
                                           `job`), or the final answer when no worker runs
    GET  /internal/v1/speech/make/{job}    the job's answer: running | done (the audio's file
                                           id) | failed (a code and a plain Persian hint)

Allowed (OPA hq.internal, media.rego): the media director, the voice producer, the video
director, the motion designer and the scriptwriter, for their own company. The text leaves the
hub (to the owner's Google account): personal or secret data is refused, never sent. While AI
Studio's last answer was its login page (within SIGNED_OUT_HOLD) a new job is refused at once,
naming the owner's step (`make aistudio-web-login`).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hq_api import idempotency
from hq_api.context import Ctx, internal_ctx
from hq_api.domain import egress as G
from hq_api.domain import speech_make as SM
from hq_api.errors import ApiError, responses
from hq_api.lines.adapters import tts
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_common.redact import scrub

internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 503)
NS = uuid.UUID("2f6c7a4e-1d3b-4c58-9e0a-5b7d8c9e1f20")  # job ids from the idempotency key


class SpeechIn(Model):
    text_fa: str = Field(min_length=1, max_length=tts.MAX_CHARS)
    voice: str = Field(default=tts.DEFAULT_VOICE, pattern=r"^[A-Za-z]{2,30}$")
    style: str = Field(default="", max_length=500)


class SpeechMakeAnswer(BaseModel):
    """`running`: ask again with `job`; `done`: `file_id` is the audio (the company's file);
    `failed`: `code` (signed_out, channel_not_configured, company_locked, timeout, recipe_failed,
    invalid_args, failed) and `hint_fa`."""

    job: str
    state: Literal["running", "done", "failed"]
    # ⟨2026-11-13⟩ which one spoke: Gemini's API first, AI Studio's web page after
    engine: Literal["aistudio", "gemini_api"] = "aistudio"
    file_id: str | None = None
    mime: str | None = None
    bytes: int | None = None
    voice: str | None = None
    style: str | None = None
    # ⟨1.31⟩ §48 true: the voice and the style are the company's own narrator (set once by the
    # owner), whatever was asked for
    narrator: bool = False
    code: str | None = None
    hint_fa: str | None = None


def _speech_agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


def _leaves_clean(*texts: str) -> bool:
    """Nothing personal or secret goes to Google, not even hidden in an encoding."""
    for text in texts:
        if scrub(text) != text:
            return False
        if any(scrub(h) != h for h in G._hidden(G.decoded(text))):
            return False
    return True


@internal_router.post("/speech/make", response_model=SpeechMakeAnswer, status_code=202, responses=E)
async def speech_make(body: SpeechIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """speech.make: `text_fa` spoken by one of AI Studio's prebuilt voices (`voice`, default Kore)
    with an optional `style` note, as an audio file of the agent's company. Answers `running` with
    the job (ask again with GET .../{job}), or the final answer when no worker runs. Refusals: a
    voice AI Studio does not have (422), personal or secret data (403), signed out (503
    channel_not_configured, naming `make aistudio-web-login`). Requires `Idempotency-Key`."""
    _speech_agent(ctx)
    who = ctx.who
    assert who.company is not None
    assert who.company_id is not None
    await allow(ctx, "speech.make", {"company": who.company, "charter": who.charter})
    # ⟨1.31⟩ §48 the narrator of the company the content is for (the run's work's company), set
    # once: its voice and style are used whatever the model asked for
    from hq_api.domain import files as F
    from hq_api.domain import narrator as NR

    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        _, fixed = await NR.for_work(tx, who)
        # ⟨2026-11-13⟩ the session the voice is made for: its next turn finds the file in `in/`
        order_id = await F.order_of_run(tx, who.run_id)
    voice, style = body.voice, body.style.strip()
    if fixed is not None:
        voice, style = str(fixed["voice"]), str(fixed["style_fa"] or "")
    if not tts.known_voice(voice):
        names = "، ".join(v[0] for v in tts.DOCUMENTED[:6])
        raise ApiError(
            422,
            "validation_failed",
            fields={"voice": "not one of AI Studio's prebuilt voices"},
            message_fa=f"صدای «{voice}» در ای‌آی استودیو نیست؛ یکی از صداهای آماده مثل {names}.",
        )
    if not _leaves_clean(body.text_fa, style):
        raise ApiError(
            403,
            "policy_denied",
            "the text may not leave the hub: personal_or_secret_data",
            message_fa="متن اطلاعات شخصی یا محرمانه دارد و به بیرون نمی‌رود؛ آن را بردار.",
        )
    key = idempotency.read_key(request, required=True)
    job = str(uuid.uuid5(NS, f"{who.code}:{key}"))
    payload: dict[str, Any] = {
        "job": job,
        "company_id": str(who.company_id),
        "company": who.company,
        "by": who.code,
        "text": body.text_fa.strip(),
        "voice": voice,
        "style": style,
        "narrator": fixed is not None,
        **({"order_id": str(order_id)} if order_id else {}),
    }
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, who, required=True)
        if idem and idem.replay:
            return idem.replay
        # ⟨2026-11-13⟩ a signed-out web page holds a job back only when the API cannot speak
        if await SM.held_back(tx) and not await SM.api_ready(ctx.hub, tx):
            raise ApiError(
                503, "channel_not_configured", "aistudio signed out", message_fa=SM.SIGNED_OUT_FA
            )
        await ctx.audit(
            tx,
            company_id=who.company_id,
            action="speech.make",
            action_class="A1",
            target_kind="speech",
            target_ref=job,
            summary=f"speech {voice}{' (the narrator)' if fixed is not None else ''}, "
            f"{len(payload['text'])} chars",
        )
        client = getattr(ctx.hub, "temporal", None)
        if client is not None:
            await _start(ctx, client, payload)
            out = SpeechMakeAnswer(
                job=job, state="running", voice=voice, style=style,
                narrator=fixed is not None, hint_fa=SM.RUNNING_FA,
            )  # fmt: skip
            if idem:
                await idem.store(tx, 202, out.model_dump(mode="json"))
            return out
    # no worker (tests, a bare api): the job runs here and its answer is final
    done = SpeechMakeAnswer.model_validate(await SM.make(ctx.hub, payload))
    if idem:
        async with ctx.hub.db.tx([who.company_id]) as tx:
            await idem.store(tx, 202, done.model_dump(mode="json"))
    return done


async def _start(ctx: Ctx, client: Any, payload: dict[str, Any]) -> None:
    from temporalio.common import WorkflowIDConflictPolicy

    try:
        await client.start_workflow(
            SM.WORKFLOW,
            payload,
            id=SM.workflow_id(payload["company"], payload["job"]),
            task_queue=ctx.hub.settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            execution_timeout=timedelta(minutes=30),
        )
    except Exception as exc:  # a client error of any kind: nothing was started
        raise ApiError(
            503,
            "channel_not_configured",
            "the speech job could not start",
            message_fa="کارگر هاب در دسترس نیست؛ کمی بعد دوباره امتحان کن.",
        ) from exc


@internal_router.get("/speech/make/{job}", response_model=SpeechMakeAnswer, responses=E)
async def speech_job(job: uuid.UUID, ctx: Ctx = Depends(internal_ctx)) -> SpeechMakeAnswer:
    """The job's answer: `running` (ask again later), `done` with the audio's file id, or `failed`
    with a code and a plain Persian hint. Only a job of the agent's own company is found."""
    _speech_agent(ctx)
    who = ctx.who
    assert who.company is not None
    await allow(ctx, "speech.make", {"company": who.company, "charter": who.charter})
    client = getattr(ctx.hub, "temporal", None)
    gone = ApiError(404, "not_found", "no such speech job", message_fa="چنین کار صدایی نیست.")
    if client is None:
        raise gone  # without a worker every job answered at once
    handle = client.get_workflow_handle(SM.workflow_id(who.company, str(job)))
    try:
        desc = await handle.describe()
    except Exception as exc:  # not found: another company's job, or one never started
        raise gone from exc
    status = getattr(desc.status, "name", str(desc.status))
    if status == "RUNNING":
        return SpeechMakeAnswer(job=str(job), state="running", hint_fa=SM.RUNNING_FA)
    if status == "COMPLETED":
        return SpeechMakeAnswer.model_validate(await handle.result())
    return SpeechMakeAnswer(
        job=str(job),
        state="failed",
        code="failed",
        hint_fa="ساخت صدا ناتمام ماند؛ یک بار دیگر speech.make را صدا بزن.",
    )
