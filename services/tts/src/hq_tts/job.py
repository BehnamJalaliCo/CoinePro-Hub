"""One pass of the TTS one-shot: claim -> speak -> send back, until the api
has nothing more (204) or TTS_MAX_JOBS jobs of a queue are done.

Two queues, one engine (prompt 13 §4.1: one voice registry for everything):
  /internal/v1/tts/claim          the briefings' spoken scripts (prompt 12 §4)
  /internal/v1/voices/jobs/claim  the bake-off samples and the media items'
                                  narration (prompt 13 §4), each with its
                                  measurement (real-time factor, this
                                  synthesis' own peak memory)
Each job names its voice; a voice this image does not ship fails the job
("voice not installed"), never another voice in its place (a briefing,
written before the choice, keeps the image's default).

The api answers 204 while the holding is locked, so nothing is generated
then. The api token comes from OpenBao (AppRole of service `tts`, kv
tts/config); it is never printed or written.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from hq_tts.engine import Engine, EngineError

log = logging.getLogger("hq_tts")


@dataclass(frozen=True)
class Settings:
    api_url: str = field(
        default_factory=lambda: os.environ.get("HQ_API_INTERNAL_URL", "http://api:8000")
    )
    openbao_addr: str = field(
        default_factory=lambda: os.environ.get("OPENBAO_ADDR", "http://openbao:8200")
    )
    approle_file: str = field(
        default_factory=lambda: os.environ.get(
            "OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json"
        )
    )
    token_path: str = field(default_factory=lambda: os.environ.get("TTS_TOKEN_PATH", "tts/config"))
    voices_dir: str = field(default_factory=lambda: os.environ.get("TTS_VOICES_DIR", "/voices"))
    voice: str = field(default_factory=lambda: os.environ.get("TTS_VOICE", "fa_IR-amir-medium"))
    max_jobs: int = field(default_factory=lambda: int(os.environ.get("TTS_MAX_JOBS", "3")))
    threads: int = field(default_factory=lambda: int(os.environ.get("TTS_THREADS", "1")))


async def api_token(s: Settings) -> str:
    from hq_common.openbao import OpenBaoClient

    bao = OpenBaoClient(s.openbao_addr, s.approle_file)
    data: dict[str, Any] = await bao.read_kv(s.token_path)
    token = data.get("api_token")
    if not token:
        raise RuntimeError("no api_token at the tts path in OpenBao")
    return str(token)


# A job's voice -> its engine; None (or a voice not shipped) -> the default
# for a briefing, a failed job for a voice job.
Engines = Callable[[str | None], Engine | None]


async def _queue(
    client: httpx.AsyncClient,
    claim: str,
    base: str,
    engine_of: Callable[[dict[str, Any]], Engine | None],
    max_jobs: int,
    measured: bool,
) -> tuple[list[str], list[str]]:
    done: list[str] = []
    failed: list[str] = []
    for _ in range(max(1, max_jobs)):
        r = await client.post(claim)
        if r.status_code == 204:
            break
        r.raise_for_status()
        job = r.json()
        script = str(job.get("script") or "").strip()
        try:
            if not script:
                raise EngineError("empty script")
            engine = engine_of(job)
            if engine is None:
                raise EngineError("voice not installed")
            with tempfile.TemporaryDirectory(prefix="tts-") as tmp:
                spoken = engine.speak(script, Path(tmp))
        except EngineError as exc:
            log.warning("tts failed for %s", job.get("ref"))
            await client.post(f"{base}/{job['id']}/fail", json={"error": str(exc)[:300]})
            failed.append(str(job.get("ref")))
            continue
        params: dict[str, Any] = {"duration_s": spoken.duration_s}
        if measured:
            params |= {"synth_s": spoken.synth_s, "peak_mb": spoken.peak_rss_mb}
        up = await client.post(
            f"{base}/{job['id']}/done",
            params=params,
            content=spoken.ogg,
            headers={"Content-Type": "audio/ogg"},
        )
        up.raise_for_status()
        log.info(
            "spoken",
            extra={
                "ref": job.get("ref"),
                "seconds": spoken.duration_s,
                "rtf": round(spoken.rtf, 3),
            },
        )
        done.append(str(job.get("ref")))
    return done, failed


async def run(
    client: httpx.AsyncClient, engine: Engine, max_jobs: int, engines: Engines | None = None
) -> dict[str, Any]:
    """`client` carries the api's base URL and the bearer token; `engines`
    gives each job's voice its engine (default: `engine` for every job)."""
    pick: Engines = engines or (lambda _voice: engine)

    def briefing(job: dict[str, Any]) -> Engine | None:
        return pick(job.get("voice")) or engine

    def voice_job(job: dict[str, Any]) -> Engine | None:
        return pick(job.get("voice")) if job.get("voice") else None

    done, failed = await _queue(
        client, "/internal/v1/tts/claim", "/internal/v1/tts", briefing, max_jobs, False
    )
    more, lost = await _queue(
        client,
        "/internal/v1/voices/jobs/claim",
        "/internal/v1/voices/jobs",
        voice_job,
        max_jobs,
        True,
    )
    return {"done": done + more, "failed": failed + lost}
