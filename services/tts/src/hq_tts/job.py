"""One pass of the TTS one-shot: claim -> speak -> send back, until the api
has nothing more (204) or TTS_MAX_JOBS briefings are done.

The api answers 204 while the holding is locked, so nothing is generated
then. The api token comes from OpenBao (AppRole of service `tts`, kv
tts/config); it is never printed or written.
"""

from __future__ import annotations

import logging
import os
import tempfile
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


async def run(
    client: httpx.AsyncClient, engine: Engine, max_jobs: int, base: str = "/internal/v1/tts"
) -> dict[str, Any]:
    """`client` carries the api's base URL and the bearer token."""
    done: list[str] = []
    failed: list[str] = []
    for _ in range(max(1, max_jobs)):
        r = await client.post(f"{base}/claim")
        if r.status_code == 204:
            break
        r.raise_for_status()
        job = r.json()
        script = str(job.get("script") or "").strip()
        try:
            if not script:
                raise EngineError("empty script")
            with tempfile.TemporaryDirectory(prefix="tts-") as tmp:
                spoken = engine.speak(script, Path(tmp))
        except EngineError as exc:
            log.warning("tts failed for %s", job.get("ref"))
            await client.post(f"{base}/{job['id']}/fail", json={"error": str(exc)[:300]})
            failed.append(str(job.get("ref")))
            continue
        up = await client.post(
            f"{base}/{job['id']}/done",
            params={"duration_s": spoken.duration_s},
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
    return {"done": done, "failed": failed}
