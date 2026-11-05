"""The voice layer's entry for the talk engine (contract §32.5–32.6): `speak` walks the chain.

The chain is the persona's engine, then `owner.settings.voice.chain`, Piper always last. Before
each sentence the owner's month cap is checked (an estimate of this sentence added to the month so
far); an engine that is capped, has no key, is known to be failing, or fails on this very
sentence hands the sentence to the next one and `fell_back_fa` says so in one plain line. Every
sentence writes one usage row with the provider's own token counts and the price in force at that
moment, stores the audio as a file of the conversation (Ogg/Opus), and moves the meter on the
stream. `VoiceUnavailable` is raised only when every engine failed, Piper included.

Tests of the talk engine set OVERRIDE to a fake Speaker.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from hq_api.domain import notify
from hq_api.voice import audio, catalog, store
from hq_api.voice.base import (
    EngineAudio,
    EngineFailed,
    Speaker,
    SpeakRequest,
    SpeechOut,
    VoiceUnavailable,
)
from hq_api.voice.engines import FILE_NAME, engine_for

log = logging.getLogger("hq_api.voice")

OVERRIDE: Speaker | None = None

CHARS_PER_SECOND = 12.0  # Persian speech, for the cap's estimate of a sentence not made yet
CHARS_PER_TEXT_TOKEN = 3.0
RETRY_FAILING_AFTER = timedelta(minutes=2)  # a failing engine is tried again after this
DEFAULT_VOICE = {"زن": "Kore", "مرد": "Charon"}
UNAVAILABLE_FA = "صدا الان در دسترس نیست؛ جواب را بخوانید."


# ------------------------------------------------------------------ voices --
def voice_for(engine: str, wanted: str) -> str:
    """The persona's voice on this engine; on another engine of the chain, a voice of the same
    gender (the engines' voice names differ)."""
    cat = catalog.load()
    names = [v["name"] for v in cat.voices_of(engine)]
    if wanted in names:
        return wanted
    gender = next(
        (v["gender_fa"] for v in (*cat.gemini_voices, *cat.piper_voices) if v["name"] == wanted),
        None,
    )
    preferred = DEFAULT_VOICE.get(gender or "")
    if preferred in names:
        return str(preferred)
    same = [v["name"] for v in cat.voices_of(engine) if v["gender_fa"] == gender]
    return (same or names)[0]


def short_fa(engine: str) -> str:
    if engine == catalog.LOCAL:
        return "صدای ساده"
    return catalog.load().engines[engine].title_fa.split("·")[0].strip()


def estimate_usd(price: catalog.InForce, text: str) -> Decimal:
    seconds = max(1.0, len(text) / CHARS_PER_SECOND)
    return price.usd(
        int(len(text) / CHARS_PER_TEXT_TOKEN) + 1, int(seconds * price.audio_tokens_per_s) + 1
    )


# --------------------------------------------------------------- one call --
@dataclass(frozen=True)
class Spoke:
    out: SpeechOut
    usd: Decimal


async def _file_of(hub: Any, got: EngineAudio, rate: float, name: str) -> tuple[str, float]:
    """(file id, seconds): an adapter returns a stored file's id, or raw 24 kHz PCM to store."""
    if isinstance(got.pcm_or_file, str):
        return got.pcm_or_file, got.seconds
    blob, mime, seconds = await audio.encode(bytes(got.pcm_or_file), rate)
    holding = await hub.companies.holding()
    ext = "ogg" if mime == audio.OGG else "wav"
    fid = await audio.store(hub, holding.id, blob, name=f"{name}.{ext}", mime=mime, seconds=seconds)
    return str(fid), seconds


async def speak_one(
    hub: Any,
    engine: str,
    text: str,
    voice: str,
    rate: float,
    *,
    kind: str,
    persona: str,
    conversation_ref: str | None,
    turn_id: str | None,
    seq: int | None,
    name: str,
) -> Spoke:
    """One sentence on one engine: the audio as a file and its usage row. Raises EngineFailed."""
    eng = engine_for(engine)
    token = FILE_NAME.set(name)
    try:
        got = await eng.speak(hub, text, voice_for(engine, voice), rate)
    except EngineFailed:
        raise
    except Exception as exc:  # an adapter must not take a turn down
        log.warning("voice engine crashed", extra={"engine": engine, "error": type(exc).__name__})
        raise EngineFailed("صدا الان جواب نداد.", state="failing", code="engine_crashed") from exc
    finally:
        FILE_NAME.reset(token)
    file_id, seconds = await _file_of(hub, got, rate, name)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        clk = await store.clock(tx)
        price = await store.price_for(tx, engine, clk.day)
        usd = await store.add_usage(
            tx,
            holding.id,
            engine=engine,
            kind=kind,
            persona=persona,
            conversation_ref=conversation_ref,
            turn_id=turn_id,
            seq=seq,
            chars=len(text),
            text_tokens=got.text_tokens,
            audio_tokens=got.audio_tokens,
            seconds=seconds,
            price=price,
        )
        row = await tx.first(
            "SELECT state, reason_fa FROM talk.engine_state WHERE engine = :e", e=engine
        )
        if row is not None and row["state"] != "ok":
            await store.set_state(tx, engine, "ok", None)
            await store.emit_engine(tx, holding.code, engine, "ok", None)
        await store.emit_meter(tx, holding.code)
        warn = await _maybe_warn(tx, holding, clk)
    if warn is not None and warn.get("push_now"):
        await notify.deliver_pending(hub, [warn["id"]])
    out = SpeechOut(
        file_id=file_id,
        seconds=round(seconds, 3),
        engine=engine,
        audio_tokens=got.audio_tokens,
        text_tokens=got.text_tokens,
        usd=usd,
    )
    return Spoke(out, usd)


async def _maybe_warn(tx: Any, holding: Any, clk: store.Clock) -> dict[str, Any] | None:
    """One notification when the month reaches `warn_at` of the owner's cap (once per month and
    cap value: raising the cap makes a new warning possible)."""
    cfg = await store.voice_settings(tx)
    cap = cfg["month_cap_usd"]
    if not cap:
        return None
    month = await store.month_usd(tx, clk.month_start)
    if month < Decimal(str(cap)) * Decimal(str(cfg["warn_at"])):
        return None
    ref = f"{clk.day:%Y-%m}:{cap:g}"
    if await tx.scalar(
        "SELECT 1 FROM notify.notifications WHERE link_kind = 'voice_cap' AND link_ref = :r", r=ref
    ):
        return None
    left = max(Decimal(0), Decimal(str(cap)) - month)
    return await notify.raise_notification(
        tx,
        company_id=holding.id,
        company_code=holding.code,
        level="info",
        title_fa=f"هزینه‌ی صدا به {int(cfg['warn_at'] * 100)} درصد سقف ماه رسید",
        body_fa=(
            f"این ماه {month:.2f} دلار از سقف {cap:g} دلار خرج شده؛ {left:.2f} دلار مانده. "
            "بعد از سقف، صدا با گویای ساده‌ی روی هاب ادامه میدهد."
        ),
        link_kind="voice_cap",
        link_ref=ref,
        source_kind="service",
        source_code="voice",
        owner_action=True,
    )


# --------------------------------------------------------------- the chain --
def _fell_back(first: str, spoke: str, why: list[tuple[str, str]]) -> str | None:
    if first == spoke or not why:
        return None
    reason = next((r for e, r in why if e == first), why[0][1])
    return f"{reason}؛ با {short_fa(spoke)} ادامه میدهم."


def _stale(row: dict[str, Any] | None, now: Any) -> bool:
    return (
        row is None
        or row.get("checked_at") is None
        or now - row["checked_at"] > RETRY_FAILING_AFTER
    )


async def speak(hub: Any, req: SpeakRequest) -> SpeechOut:
    if OVERRIDE is not None:
        return await OVERRIDE(hub, req)
    cat = catalog.load()
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        cfg = await store.voice_settings(tx)
        st = await store.states(tx, holding.id)
        clk = await store.clock(tx)
        month = await store.month_usd(tx, clk.month_start)
    chain = store.chain_for(req.choice.engine, cfg["chain"], local=cfg["local"])
    if not chain:  # the persona's voice is the local one, and it is off: the answer stays text
        raise VoiceUnavailable(UNAVAILABLE_FA)
    cap = Decimal(str(cfg["month_cap_usd"])) if cfg["month_cap_usd"] is not None else None
    why: list[tuple[str, str]] = []
    for key in chain:
        eng = cat.engines[key]
        row = st.get(key)
        paid = eng.provider != "local"
        if paid:
            if not (row and row["secret_set"]):
                why.append((key, "کلید صدا داده نشده است"))
                continue
            price = await _price(hub, key, clk.day)
            if cap is not None and month + estimate_usd(price, req.text) > cap:
                await _set(hub, holding, key, "capped", "سقف ماه صدا پر شد.")
                why.append((key, "سقف ماه پر شد"))
                continue
            if row["state"] == "capped":  # the owner raised the cap (or a new month began)
                await _set(hub, holding, key, "ok", None)
            elif row["state"] in ("failing", "missing") and not _stale(row, clk.now):
                why.append((key, row["reason_fa"] or "صدا جواب نمیداد"))
                continue
        try:
            spoke = await speak_one(
                hub,
                key,
                req.text,
                req.choice.voice,
                req.choice.rate,
                kind="speech",
                persona=req.persona,
                conversation_ref=req.conversation_ref,
                turn_id=req.turn_id,
                seq=req.seq,
                name=f"{req.conversation_ref}-{req.turn_id}-{req.seq}",
            )
        except EngineFailed as exc:
            await _set(hub, holding, key, exc.state, exc.reason_fa)
            why.append((key, exc.reason_fa.rstrip(".")))
            await _recheck_soon(hub, eng.provider)
            continue
        out = spoke.out
        return SpeechOut(
            file_id=out.file_id,
            seconds=out.seconds,
            engine=out.engine,
            audio_tokens=out.audio_tokens,
            text_tokens=out.text_tokens,
            usd=out.usd,
            fell_back_fa=_fell_back(chain[0], key, why),
        )
    raise VoiceUnavailable(UNAVAILABLE_FA)


async def _price(hub: Any, engine: str, day: Any) -> catalog.InForce:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await store.price_for(tx, engine, day)


async def _set(hub: Any, holding: Any, engine: str, state: str, reason: str | None) -> None:
    """Move an engine's light and tell the stream when it changed."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await store.set_state(tx, engine, state, reason):
            await store.emit_engine(tx, holding.code, engine, state, reason)


_rechecks: dict[str, float] = {}


async def _recheck_soon(hub: Any, provider: str) -> None:
    """After a failure the provider's key is looked at again by the metadata call (free); at most
    once a minute. Best effort: the engine is also tried again by itself after a while."""
    from hq_api.voice import jobs

    loop = asyncio.get_running_loop()
    if loop.time() - _rechecks.get(provider, -1e9) < 60:
        return
    _rechecks[provider] = loop.time()
    try:
        await jobs.start_check(hub, provider, speech=False)
    except Exception as exc:  # noqa: BLE001 - never a reason to fail a sentence
        log.info("voice recheck not started", extra={"error": type(exc).__name__})


__all__ = ["OVERRIDE", "Spoke", "speak", "speak_one", "voice_for"]
