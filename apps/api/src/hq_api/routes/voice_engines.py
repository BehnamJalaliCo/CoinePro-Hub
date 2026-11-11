"""⟨1.14⟩ Prompt 23 (contract §32.5–32.6, §32.9): the voice engines, the key in the chat with its
light, the live meter and the owner's cap. Owner only (OPA `hq.voice_engines`).

GET    /voice/engines                       every engine: the light, the price, the voices
GET    /voice/engines/{key}/voices          one engine's voices
GET    /voice/meter?period=today|month      the meter (the provider's tokens x the price table)
PUT    /voice/providers/{provider}/secret   🔏 voice.secret (target = provider): the key into OpenBao,
                                            202 {state: "checking"}; the check runs in the
                                            background and arrives as `voice.engine` on the stream
DELETE /voice/providers/{provider}/secret   🔏 voice.secret: the key is removed
POST   /voice/engines/{key}/check           the free metadata check now (502 with a plain reason
                                            when the provider refuses)
POST   /voice/sample                        a short sample (its cost on the meter)
PUT    /voice/engines/{key}/price           the owner's own price for an engine
TTS one-shot (service `tts`), the third queue beside the briefings and the bake-off:
POST   /internal/v1/voices/talk/claim       the next sentence for Piper (204: none, or locked)
POST   /internal/v1/voices/talk/{id}/done   its Ogg/Opus (raw body) ?duration_s
POST   /internal/v1/voices/talk/{id}/fail

The key is written once and never returned, logged or audited ("voice.secret set"); the api never
reads it back (the worker reads it per call, hq_api.voice.remote).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from hq_api import media
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.domain import gate
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup
from hq_api.voice import audio, catalog, jobs, store
from hq_api.voice.base import EngineFailed
from hq_api.voice.speaker import estimate_usd, speak_one

router = APIRouter(tags=["voice"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
E502 = {**E, 502: E[422]}
ENGINE_KEY = r"^[a-z0-9][a-z0-9._-]{1,60}$"
PROVIDER = r"^(google)$"  # the providers that take a key; `local` takes none
SECRET_SHAPE = re.compile(r"^[A-Za-z0-9._~-]{20,200}$")
MAX_SAMPLE_CHARS = 300
MAX_TALK_AUDIO = 4 * 1024 * 1024  # one sentence of Piper
PIPER_RECLAIM_S = 120
PIPER_ATTEMPTS = 3
CAP_HEADROOM = Decimal("0.002")  # about one more sentence: the light is amber a sentence early


# ------------------------------------------------------------------ models --
class VoicePriceNext(BaseModel):
    """A scheduled price: it applies from `from` (the day), by itself."""

    model_config = ConfigDict(populate_by_name=True)
    from_: date = Field(alias="from")
    text_in_per_m: float
    audio_out_per_m: float


class VoicePrice(BaseModel):
    text_in_per_m: float
    audio_out_per_m: float
    audio_tokens_per_s: int
    valid_until: date | None
    next: VoicePriceNext | None
    source_url: str
    as_of: date


class VoiceVoiceOut(BaseModel):
    name: str
    gender_fa: str
    trait_fa: str | None = None
    sample_file: str | None = None


class VoiceEngine(BaseModel):
    key: str
    title_fa: str
    provider: Literal["google", "local"]
    model: str
    languages: int
    rank_fa: str
    key_pattern: str | None
    state: Literal["missing", "checking", "ok", "failing", "capped"]
    reason_fa: str | None
    checked_at: datetime | None
    price: VoicePrice
    voices: list[VoiceVoiceOut]
    note_fa: str | None = None


class VoiceMeterEngine(BaseModel):
    engine: str
    usd: float
    seconds: float
    audio_tokens: int


class VoiceMeterPersona(BaseModel):
    persona: str
    usd: float
    seconds: float


class VoiceMeter(BaseModel):
    period: Literal["today", "month"]
    voice_usd: float
    cap_usd: float | None
    projected_usd: float
    by_engine: list[VoiceMeterEngine]
    by_persona: list[VoiceMeterPersona]
    talk_tokens: int
    talk_usd_equiv: float
    price_note_fa: str | None
    updated_at: datetime


class VoiceSecretIn(Model):
    secret: str = Field(min_length=8, max_length=300, repr=False)


class VoiceSecretState(BaseModel):
    provider: str
    state: Literal["missing", "checking"]


class VoicePriceNextIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: date = Field(alias="from")
    text_in_per_m: float = Field(ge=0, le=100_000)
    audio_out_per_m: float = Field(ge=0, le=100_000)


class VoicePriceIn(Model):
    """The owner's price for an engine, USD per one million tokens. `reset: true` goes back to the
    table's price."""

    reset: bool = False
    text_in_per_m: float | None = Field(default=None, ge=0, le=100_000)
    audio_out_per_m: float | None = Field(default=None, ge=0, le=100_000)
    audio_tokens_per_s: int | None = Field(default=None, ge=1, le=1000)
    valid_until: date | None = None
    next: VoicePriceNextIn | None = None


class VoiceSampleIn(Model):
    engine: str = Field(pattern=ENGINE_KEY)
    voice: str = Field(min_length=2, max_length=80)
    text: str | None = Field(default=None, max_length=MAX_SAMPLE_CHARS)


class VoiceSampleOut(BaseModel):
    engine: str
    voice: str
    text: str
    file_id: UUID
    seconds: float
    audio_tokens: int
    usd: float


class VoiceTalkJob(BaseModel):
    id: UUID
    ref: str
    voice: str
    script: str
    rate: float


class VoiceTalkFail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = Field(default="failed", max_length=300)


class VoiceTalkDone(BaseModel):
    job: UUID
    state: str
    file: UUID


# ----------------------------------------------------------------- helpers --
async def _policy(
    ctx: Ctx, op: str, target: dict[str, Any] | None = None, *, step_up: bool = False
) -> None:
    await ctx.hub.policy.require(
        "voice_engines",
        {
            "principal": ctx.who.opa(),
            "op": op,
            "target": target or {},
            "context": {"step_up": step_up},
        },
    )


def _engine_def(key: str) -> catalog.EngineDef:
    e = catalog.load().engine(key)
    if e is None:
        raise ApiError(404, "not_found", "no such voice engine", message_fa="این موتور صدا نیست.")
    return e


def _price_out(price: dict[str, Any], default_as_of: date) -> VoicePrice:
    nxt = price.get("next")
    return VoicePrice(
        text_in_per_m=float(price["text_in_per_m"]),
        audio_out_per_m=float(price["audio_out_per_m"]),
        audio_tokens_per_s=int(price.get("audio_tokens_per_s") or 0),
        valid_until=catalog.parse_day(price.get("valid_until")),
        next=VoicePriceNext(
            from_=catalog.parse_day(nxt["from"]),
            text_in_per_m=float(nxt["text_in_per_m"]),
            audio_out_per_m=float(nxt["audio_out_per_m"]),
        )
        if nxt
        else None,
        source_url=str(price.get("source_url") or "owner"),
        as_of=catalog.parse_day(price.get("as_of")) or default_as_of,
    )


def _light(
    e: catalog.EngineDef,
    row: dict[str, Any] | None,
    *,
    month: Decimal,
    cap: float | None,
    tts_on: bool,
    now: datetime,
) -> tuple[str, str | None, datetime | None]:
    """What the owner sees for an engine: the stored light, with what only time or the cap decide."""
    if e.provider == "local":
        if tts_on:
            return "ok", None, None
        return "missing", "صدای ساده‌ی روی هاب هنوز روشن نشده است.", None
    row = row or {}
    if not row.get("secret_set"):
        return "missing", "کلید صدا داده نشده است.", None
    state, reason, at = (
        str(row.get("state") or "missing"),
        row.get("reason_fa"),
        row.get("checked_at"),
    )
    if (
        cap is not None
        and month + CAP_HEADROOM >= Decimal(str(cap))
        and state in ("ok", "capped", "checking")
    ):
        return "capped", "سقف ماه صدا پر شد؛ صدا با صدای ساده ادامه دارد.", at
    if state == "capped":
        state, reason = "ok", None
    if (
        state == "checking"
        and (now - row["updated_at"]).total_seconds() > store.CHECKING_STALE_MIN * 60
    ):
        return "failing", "بررسی کلید به نتیجه نرسید؛ دوباره بسنج.", at
    return state, reason, at


async def _engines(ctx: Ctx, tx: Any, only: str | None = None) -> list[VoiceEngine]:
    cat = catalog.load()
    holding = await ctx.hub.companies.holding()
    clk = await store.clock(tx)
    cfg = await store.voice_settings(tx)
    st = await store.states(tx, holding.id)
    month = await store.month_usd(tx, clk.month_start)
    out: list[VoiceEngine] = []
    for e in cat.engines.values():
        if only and e.key != only:
            continue
        row = st.get(e.key)
        price, source = catalog.effective_price(e, await store.override_of(tx, e.key))
        state, reason, at = _light(
            e,
            row,
            month=month,
            cap=cfg["month_cap_usd"],
            tts_on=bool(getattr(ctx.hub.settings, "tts", False)),
            now=clk.now,
        )
        provider = cat.providers[e.provider]
        out.append(
            VoiceEngine(
                key=e.key,
                title_fa=e.title_fa,
                provider=e.provider,
                model=e.model,
                languages=e.languages,
                rank_fa=e.rank_fa,
                key_pattern=provider.key_pattern,
                state=state,
                reason_fa=reason,
                checked_at=at,
                price=_price_out(price, clk.day),
                voices=[VoiceVoiceOut(**v, sample_file=None) for v in cat.voices_of(e.key)],
                note_fa=e.note_fa if source == "table" else "قیمت را خود مالک گذاشته است.",
            )
        )
    return out


# ------------------------------------------------------------------ reads --
@router.get("/voice/engines", response_model=list[VoiceEngine], responses=E)
async def list_voice_engines(ctx: Ctx = Depends(owner_ctx)) -> list[VoiceEngine]:
    """Every engine of the chain's registry: its light (green ok, yellow checking, red
    missing/failing with the reason and the fix, amber capped), its price in force with the next
    one, and its voices. `key_pattern` is the provider's key shape the app keeps out of the
    composer."""
    await _policy(ctx, "voice.read")
    async with ctx.tx() as tx:
        return await _engines(ctx, tx)


@router.get("/voice/engines/{key}/voices", response_model=list[VoiceVoiceOut], responses=E)
async def list_voice_engine_voices(
    key: str = Path(pattern=ENGINE_KEY), ctx: Ctx = Depends(owner_ctx)
) -> list[VoiceVoiceOut]:
    """The engine's voices (Gemini's prebuilt names with their gender, or Piper's shipped ones)."""
    await _policy(ctx, "voice.read", {"engine": key})
    _engine_def(key)
    return [VoiceVoiceOut(**v, sample_file=None) for v in catalog.load().voices_of(key)]


@router.get("/voice/meter", response_model=VoiceMeter, responses=E)
async def get_voice_meter(
    period: Literal["today", "month"] = Query(default="today"), ctx: Ctx = Depends(owner_ctx)
) -> VoiceMeter:
    """What the voice cost: Google's own token counts x the price table (Google's bill, with
    tax and currency, can differ slightly), by engine and by persona, with the month's projection
    and the model tokens of the talk."""
    await _policy(ctx, "voice.read", {"period": period})
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        return VoiceMeter.model_validate(await store.meter(tx, period, holding.id))


# --------------------------------------------------------------- the key --
@router.put(
    "/voice/providers/{provider}/secret",
    status_code=202,
    response_model=VoiceSecretState,
    responses={**E, 503: E[422]},
)
async def put_voice_secret(
    body: VoiceSecretIn,
    request: Request,
    provider: str = Path(pattern=PROVIDER),
    ctx: Ctx = Depends(owner_ctx),
) -> VoiceSecretState:
    """🔏 `voice.secret` (target = the provider). Write-only: the key goes to OpenBao
    (kv/hq/voice/<provider>) and is never returned, logged or audited ("voice.secret set"). Then
    the check starts in the background (the free metadata call for each model, then one spoken
    word whose cost is on the meter) and its result arrives as `voice.engine` on the stream."""
    secret = body.secret.strip()
    if not SECRET_SHAPE.match(secret):
        raise ApiError(
            422,
            "validation_failed",
            fields={"secret": "not a key"},
            message_fa="این شبیه کلید نیست؛ کلید را کامل و بدون فاصله بچسبان.",
        )
    holding = await ctx.hub.companies.holding()
    bao = ctx.hub.bao
    path = catalog.load().providers[provider].kv_path
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "voice.secret", provider)
        await _policy(ctx, "voice.secret", {"provider": provider}, step_up=True)
        if bao is None or path is None:
            raise ApiError(503, "channel_not_configured", "the secret store is not available")
        await bao.write_kv(path, {"secret": secret})
        await store.ensure_rows(tx, holding.id)
        await store.set_secret(tx, provider, True)
        for e in catalog.load().engines_of(provider):
            await store.emit_engine(tx, holding.code, e.key, "checking", None)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="voice.secret",
            action_class="A2",
            target_kind="voice_provider",
            target_ref=provider,
            summary="voice.secret set",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="voice.secret",
            target_kind="voice_provider",
            target_ref=provider,
        )
    del secret
    await jobs.start_check(ctx.hub, provider, speech=True)
    return VoiceSecretState(provider=provider, state="checking")


@router.delete(
    "/voice/providers/{provider}/secret",
    response_model=VoiceSecretState,
    responses={**E, 503: E[422]},
)
async def delete_voice_secret(
    request: Request,
    provider: str = Path(pattern=PROVIDER),
    ctx: Ctx = Depends(owner_ctx),
) -> VoiceSecretState:
    """🔏 `voice.secret`: the key is removed (the stored value is emptied; the api's policy on the
    secret store is write-only), every engine of the provider is `missing` and the chain moves on
    to the next engine."""
    holding = await ctx.hub.companies.holding()
    bao = ctx.hub.bao
    path = catalog.load().providers[provider].kv_path
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "voice.secret", provider)
        await _policy(ctx, "voice.secret", {"provider": provider}, step_up=True)
        if bao is None or path is None:
            raise ApiError(503, "channel_not_configured", "the secret store is not available")
        await bao.write_kv(path, {"secret": ""})
        await store.ensure_rows(tx, holding.id)
        await store.set_secret(tx, provider, False)
        for e in catalog.load().engines_of(provider):
            await store.emit_engine(tx, holding.code, e.key, "missing", "کلید صدا داده نشده است.")
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="voice.secret",
            action_class="A2",
            target_kind="voice_provider",
            target_ref=provider,
            summary="voice.secret removed",
            step_up=True,
        )
    return VoiceSecretState(provider=provider, state="missing")


# ------------------------------------------------------------ check, sample --
async def _usable(ctx: Ctx, tx: Any, e: catalog.EngineDef) -> None:
    """The engine can be called now: a key is set (a paid engine) and the cap is not reached."""
    if e.provider == "local":
        if not getattr(ctx.hub.settings, "tts", False):
            raise ApiError(
                409, "validation_failed", "piper is off",
                message_fa="صدای ساده‌ی روی هاب هنوز روشن نشده است.",
            )  # fmt: skip
        return
    holding = await ctx.hub.companies.holding()
    st = await store.states(tx, holding.id)
    if not st[e.key]["secret_set"]:
        raise ApiError(
            409, "validation_failed", "no key",
            message_fa="کلید صدا داده نشده است؛ با دکمه‌ی کلید آن را بده.",
        )  # fmt: skip


@router.post("/voice/engines/{key}/check", response_model=VoiceEngine, responses=E502)
async def check_voice_engine(
    key: str = Path(pattern=ENGINE_KEY), ctx: Ctx = Depends(owner_ctx)
) -> VoiceEngine:
    """The free metadata check now (`models.get`, no speech). The light is updated and sent on
    the stream; when the provider refuses, 502 with the plain Persian reason (the fix is in it)."""
    await _policy(ctx, "voice.check", {"engine": key})
    e = _engine_def(key)
    async with ctx.tx() as tx:
        await _usable(ctx, tx, e)
    state, reason = await jobs.check_engine(ctx.hub, key, speech=False)
    async with ctx.tx() as tx:
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="voice.check",
            action_class="A0",
            target_kind="voice_engine",
            target_ref=key,
            summary=state,
        )
        view = (await _engines(ctx, tx, key))[0]
    if state != "ok":
        raise ApiError(
            502,
            "channel_not_configured",
            "the provider refused",
            message_fa=reason or "گوگل جواب درست نداد.",
        )
    return view


@router.post("/voice/sample", response_model=VoiceSampleOut, responses=E502)
async def voice_sample(body: VoiceSampleIn, ctx: Ctx = Depends(owner_ctx)) -> VoiceSampleOut:
    """A short sample of one engine's voice so the owner can choose by ear. Its cost goes on the
    meter like any sentence; a provider's refusal is 502 with the plain reason."""
    await _policy(ctx, "voice.sample", {"engine": body.engine})
    cat = catalog.load()
    e = _engine_def(body.engine)
    if body.voice not in {v["name"] for v in cat.voices_of(e.key)}:
        raise ApiError(
            422, "validation_failed", fields={"voice": "not a voice of this engine"},
            message_fa="این صدا برای این موتور نیست.",
        )  # fmt: skip
    text = (body.text or cat.sample_text_fa).strip()
    for p in cat.providers.values():
        if p.key_pattern and re.search(p.key_pattern, text):
            raise ApiError(
                422, "validation_failed", fields={"text": "a key"},
                message_fa="کلید را با دکمه‌ی کلید بده، نه در متن.",
            )  # fmt: skip
    if not text:
        raise ApiError(422, "validation_failed", fields={"text": "empty"})
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        await _usable(ctx, tx, e)
        if e.provider != "local":
            clk = await store.clock(tx)
            cfg = await store.voice_settings(tx)
            price = await store.price_for(tx, e.key, clk.day)
            month = await store.month_usd(tx, clk.month_start)
            if cfg["month_cap_usd"] is not None and month + estimate_usd(price, text) > Decimal(
                str(cfg["month_cap_usd"])
            ):
                raise ApiError(
                    409, "validation_failed", "cap reached",
                    message_fa="سقف ماه صدا پر شده؛ نمونه‌ی این موتور ساخته نمیشود.",
                )  # fmt: skip
    try:
        spoke = await speak_one(
            ctx.hub, e.key, text, body.voice, 1.0, kind="sample", persona="",
            conversation_ref=None, turn_id=None, seq=None, name=f"sample-{e.key}-{body.voice}",
        )  # fmt: skip
    except EngineFailed as exc:
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
            if await store.set_state(tx, e.key, exc.state, exc.reason_fa):
                await store.emit_engine(tx, holding.code, e.key, exc.state, exc.reason_fa)
        raise ApiError(
            502, "channel_not_configured", "the provider refused", message_fa=exc.reason_fa
        ) from exc
    async with ctx.tx() as tx:
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="voice.sample",
            action_class="A1",
            target_kind="voice_engine",
            target_ref=e.key,
            summary=f"{body.voice}, {len(text)} chars",
        )
    out = spoke.out
    return VoiceSampleOut(
        engine=e.key,
        voice=body.voice,
        text=text,
        file_id=UUID(out.file_id),
        seconds=out.seconds,
        audio_tokens=out.audio_tokens,
        usd=float(round(out.usd, 8)),
    )


# ------------------------------------------------------------------ price --
def _price_object(body: VoicePriceIn, today: date) -> dict[str, Any]:
    if body.text_in_per_m is None or body.audio_out_per_m is None:
        raise ApiError(
            422, "validation_failed",
            fields={"text_in_per_m": "required", "audio_out_per_m": "required"},
            message_fa="قیمت متن و قیمت صدا هر دو لازم است.",
        )  # fmt: skip
    if body.next is not None and body.next.from_ <= today:
        raise ApiError(
            422, "validation_failed", fields={"next": "from must be in the future"},
            message_fa="روز قیمت بعدی باید در آینده باشد.",
        )  # fmt: skip
    if body.valid_until is not None and body.next is None:
        raise ApiError(
            422, "validation_failed", fields={"next": "valid_until needs a next price"},
            message_fa="برای «تا چه روزی» قیمت بعدی را هم بنویس.",
        )  # fmt: skip

    def money(x: float) -> str:
        try:
            return str(Decimal(str(x)).quantize(Decimal("0.0001")).normalize())
        except InvalidOperation as exc:  # pragma: no cover - the model bounds the number
            raise ApiError(422, "validation_failed") from exc

    return {
        "text_in_per_m": money(body.text_in_per_m),
        "audio_out_per_m": money(body.audio_out_per_m),
        "audio_tokens_per_s": body.audio_tokens_per_s or 25,
        "valid_until": body.valid_until.isoformat() if body.valid_until else None,
        "next": {
            "from": body.next.from_.isoformat(),
            "text_in_per_m": money(body.next.text_in_per_m),
            "audio_out_per_m": money(body.next.audio_out_per_m),
        }
        if body.next
        else None,
        "source_url": "owner",
        "as_of": today.isoformat(),
    }


@router.put("/voice/engines/{key}/price", response_model=VoiceEngine, responses=E)
async def put_voice_price(
    body: VoicePriceIn, key: str = Path(pattern=ENGINE_KEY), ctx: Ctx = Depends(owner_ctx)
) -> VoiceEngine:
    """The owner's own price for an engine (USD per one million tokens), replacing the table's
    until `reset: true`. Rows already made keep the price they were charged at; a scheduled
    `next` price applies by itself on its day and the app warns 14 days before it."""
    await _policy(ctx, "voice.price", {"engine": key})
    e = _engine_def(key)
    holding = await ctx.hub.companies.holding()
    if e.provider == "local":
        raise ApiError(
            422, "validation_failed", fields={"engine": "free"},
            message_fa="صدای ساده رایگان است و قیمت ندارد.",
        )  # fmt: skip
    async with ctx.tx() as tx:
        clk = await store.clock(tx)
        await store.ensure_rows(tx, holding.id)
        await store.set_override(tx, key, None if body.reset else _price_object(body, clk.day))
        await store.emit_meter(tx, holding.code)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="voice.price",
            action_class="A1",
            target_kind="voice_engine",
            target_ref=key,
            summary="price reset" if body.reset else "price set",
        )
        return (await _engines(ctx, tx, key))[0]


# ---------------------------------------------------- Piper's queue (tts) --
async def _tts(ctx: Ctx, op: str) -> None:
    if ctx.who.kind != "service" or ctx.who.code != "tts":
        raise ApiError(403, "policy_denied", "the tts service only")
    await allow(ctx, op, {})


@internal_router.post(
    "/voices/talk/claim",
    response_model=VoiceTalkJob,
    responses={**E, 204: {"description": "nothing to say, or the holding is locked"}},
)
async def voice_talk_claim(ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The next sentence of the talk for Piper; 204 when there is none and always while the
    holding is locked (nothing is spoken then)."""
    await _tts(ctx, "voices.claim")
    async with ctx.tx() as tx:
        if await gate.holding_lock(tx) is not None:
            return Response(status_code=204)
        row = await tx.first(
            """SELECT id, voice, script, rate, attempts FROM talk.voice_jobs
               WHERE (state = 'queued'
                      OR (state = 'claimed' AND claimed_at < now() - make_interval(secs => :s)))
               ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""",
            s=PIPER_RECLAIM_S,
        )
        if row is None:
            return Response(status_code=204)
        if int(row["attempts"]) >= PIPER_ATTEMPTS:
            await tx.exec(
                """UPDATE talk.voice_jobs SET state = 'failed', error = 'too many attempts',
                       updated_at = now() WHERE id = :id""",
                id=row["id"],
            )
            return Response(status_code=204)
        await tx.exec(
            """UPDATE talk.voice_jobs SET state = 'claimed', claimed_at = now(),
                   attempts = attempts + 1, updated_at = now() WHERE id = :id""",
            id=row["id"],
        )
    return VoiceTalkJob(
        id=row["id"], ref=f"talk/{str(row['id'])[:8]}", voice=row["voice"], script=row["script"],
        rate=float(row["rate"]),
    )  # fmt: skip


@internal_router.post(
    "/voices/talk/{id}/done",
    response_model=VoiceTalkDone,
    responses=E,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def voice_talk_done(
    id: UUID,
    request: Request,
    duration_s: float | None = Query(default=None, ge=0, le=600),
    ctx: Ctx = Depends(internal_ctx),
) -> VoiceTalkDone:
    """The sentence's Ogg/Opus (raw body, ≤ 4 MB), stored as a file of the holding at the
    persona's speed (Piper has no speed of its own)."""
    await _tts(ctx, "voices.done")
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime != "audio/ogg":
        raise ApiError(415, "validation_failed", fields={"Content-Type": "audio/ogg"})
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_TALK_AUDIO:
            raise ApiError(413, "validation_failed", "audio too large")
    checked = media.check_type("audio/ogg", bytes(data[:64]))
    if isinstance(checked, str):
        raise ApiError(422, "validation_failed", fields={"body": f"not an Ogg stream ({checked})"})
    async with ctx.tx() as tx:
        job = await tx.first(
            "SELECT id, company_id, state, rate FROM talk.voice_jobs WHERE id = :id FOR UPDATE",
            id=id,
        )
        if job is None:
            raise ApiError(404, "not_found", "no such job")
        if job["state"] not in ("claimed", "queued"):
            raise ApiError(409, "validation_failed", f"the job is {job['state']}")
    rate = float(job["rate"])
    try:
        blob = await audio.ogg_with_tempo(bytes(data), rate)
    except audio.EncodeFailed:
        blob = bytes(data)  # the speech at its own speed is better than none
        rate = 1.0
    seconds = (duration_s or 0.0) / (rate if rate > 0 else 1.0)
    key, sha = await ctx.hub.storage.put(blob)
    async with ctx.tx() as tx:
        fid = await F.insert(
            tx, company_id=job["company_id"], name=f"talk-{str(id)[:8]}.ogg", mime="audio/ogg",
            size=len(blob), sha256=sha, storage_key=key, kind="audio", by_kind="service",
            by_code="tts", duration_s=round(seconds, 3) or None,
        )  # fmt: skip
        changed = await tx.exec(
            """UPDATE talk.voice_jobs SET state = 'done', file_id = :f, seconds = :s, error = NULL,
                   updated_at = now() WHERE id = :id AND state IN ('claimed', 'queued')""",
            f=fid,
            s=round(seconds, 3),
            id=id,
        )
        if not changed:
            raise ApiError(409, "validation_failed", "the job is no longer waiting")
    return VoiceTalkDone(job=id, state="done", file=fid)


@internal_router.post(
    "/voices/talk/{id}/fail", status_code=204, response_class=Response, responses=E
)
async def voice_talk_fail(
    id: UUID, body: VoiceTalkFail, ctx: Ctx = Depends(internal_ctx)
) -> Response:
    """Piper could not make it; after three tries the sentence is `failed` (the turn goes on)."""
    await _tts(ctx, "voices.done")
    clean = re.sub(r"[^A-Za-z0-9 _.:-]", "", body.error)[:300] or "failed"
    async with ctx.tx() as tx:
        await tx.exec(
            """UPDATE talk.voice_jobs SET
                   state = CASE WHEN attempts >= :n THEN 'failed' ELSE 'queued' END,
                   error = :e, claimed_at = NULL, updated_at = now()
               WHERE id = :id AND state IN ('claimed', 'queued')""",
            n=PIPER_ATTEMPTS,
            e=clean,
            id=id,
        )
    return Response(status_code=204)
