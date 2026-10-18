"""HTTP API of stt. Callers: the worker only (network hq-stt, no published port).

POST /v1/transcribe   raw audio body (Content-Type audio/*, at most STT_MAX_BYTES,
                      counted while it is read; at most STT_MAX_DURATION_S long)
                      -> {text_raw, text, language, duration_s, confidence,
                          segments, engine, timing}
GET  /health          {ok, engine, model, loaded} without loading the model
GET  /metrics         Prometheus

One transcription runs at a time (CPU); at most STT_MAX_WAITING wait, the rest
get 503 busy. Errors are {code, detail}: 413 too_large / too_long, 415
unsupported_media_type, 422 undecodable, 503 busy. No audio or text is logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from hq_stt import engine as E
from hq_stt.config import Settings

log = logging.getLogger("hq_stt")
REAP_EVERY_S = 15.0


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "stt_requests", "Transcription requests by outcome", ["outcome"], registry=self.registry
        )
        self.seconds = Histogram(
            "stt_transcribe_seconds",
            "Wall time of a transcription (decode + model)",
            buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160, 320),
            registry=self.registry,
        )
        self.audio = Counter(
            "stt_audio_seconds", "Seconds of audio transcribed", registry=self.registry
        )
        self.loaded = Gauge(
            "stt_model_loaded", "1 while the model is in memory", registry=self.registry
        )
        self.load_seconds = Histogram(
            "stt_model_load_seconds",
            "Time to load the model",
            buckets=(1, 2, 5, 10, 20, 40),
            registry=self.registry,
        )


@dataclass
class State:
    s: Settings
    engine: E.Engine
    metrics: Metrics = field(default_factory=Metrics)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiting: int = 0
    last_used: float = field(default_factory=time.monotonic)


def problem(status: int, code: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status)


async def read_body(request: Request, limit: int) -> bytes | None:
    """The body, or None as soon as it is larger than `limit` (never read whole)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def reaper(state: State) -> None:
    """Frees the model after STT_IDLE_UNLOAD_S without a request."""
    while True:
        await asyncio.sleep(min(REAP_EVERY_S, max(state.s.idle_unload_s / 4, 0.05)))
        idle = time.monotonic() - state.last_used
        if state.engine.loaded and not state.lock.locked() and idle >= state.s.idle_unload_s:
            async with state.lock:
                if await asyncio.to_thread(state.engine.unload):
                    state.metrics.loaded.set(0)


def build_app(state: State) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(reaper(state))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="stt", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, object]:
        e = state.engine
        return {"ok": True, "engine": e.name, "model": e.model, "loaded": e.loaded}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(state.metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/transcribe", response_model=None)
    async def transcribe(request: Request) -> JSONResponse:
        m = state.metrics
        ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ctype.startswith(("audio/", "video/")):
            m.requests.labels("unsupported").inc()
            return problem(415, "unsupported_media_type", "audio/* only")
        data = await read_body(request, state.s.max_bytes)
        if data is None:
            m.requests.labels("too_large").inc()
            return problem(413, "too_large", f"at most {state.s.max_bytes} bytes")
        if state.waiting >= state.s.max_waiting:
            m.requests.labels("busy").inc()
            return problem(503, "busy", "too many transcriptions waiting")
        state.waiting += 1
        try:
            await state.lock.acquire()
        finally:
            state.waiting -= 1
        try:
            was_loaded = state.engine.loaded
            started = time.monotonic()
            try:
                t = await asyncio.to_thread(state.engine.transcribe, data)
            except E.TooLong as exc:
                m.requests.labels("too_long").inc()
                return problem(413, "too_long", str(exc))
            except E.Undecodable as exc:
                m.requests.labels("undecodable").inc()
                return problem(422, "undecodable", str(exc))
            finally:
                state.last_used = time.monotonic()
            m.seconds.observe(time.monotonic() - started)
        finally:
            state.lock.release()
        m.requests.labels("ok").inc()
        m.audio.inc(t.duration_s)
        m.loaded.set(1 if state.engine.loaded else 0)
        if not was_loaded and state.engine.loaded:
            m.load_seconds.observe(t.load_s)
        e = state.engine
        log.info(
            "transcribed",
            extra={"duration_s": t.duration_s, "seconds": t.transcribe_s, "load_s": t.load_s},
        )
        return JSONResponse(
            {
                "text_raw": t.text_raw,
                "text": t.text,
                "language": state.s.language,
                "duration_s": t.duration_s,
                "confidence": t.confidence,
                "segments": [
                    {"start_s": x.start_s, "end_s": x.end_s, "text": x.text} for x in t.segments
                ],
                "engine": {"name": e.name, "model": e.model, "version": e.version},
                "timing": {"load_s": t.load_s, "transcribe_s": t.transcribe_s},
            }
        )

    return app


def create_app(s: Settings | None = None) -> FastAPI:
    settings = s or Settings()
    eng = E.build(settings)
    if isinstance(eng, E.WhisperEngine):
        # Refuses to serve a model whose bytes are not the pinned ones.
        eng.verify()
    return build_app(State(settings, eng))
