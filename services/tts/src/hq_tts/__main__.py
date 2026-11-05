"""`python -m hq_tts`: one pass of the one-shot (claim, speak, send back)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from hq_tts.engine import Engine, Piper, installed
from hq_tts.job import Settings, api_token, run, run_talk


def engines(s: Settings) -> tuple[Engine, dict[str, Engine]]:
    """The default voice and every voice the image ships (prompt 13 §4)."""
    root = Path(s.voices_dir)
    shipped: dict[str, Engine] = {v: Piper(root, v, s.threads) for v in installed(root)}
    default = shipped.get(s.voice) or Piper(root, s.voice, s.threads)
    return default, shipped


async def serve(
    client: httpx.AsyncClient,
    default: Engine,
    s: Settings,
    pick: Callable[[str | None], Engine | None],
) -> dict[str, list[str]]:
    """Serving mode (prompt 23): for TTS_SERVE_S seconds answer the talk's queue, polling every
    TTS_SERVE_POLL_S, so the owner's voice chain reaches Piper in about a second.

    The other queues (the briefings, the bake-off samples, the narrations) are spoken in the
    talk's idle moments, one job at a time and TTS_MAX_JOBS a pass at most, so the talk always
    goes first (23.2: serving mode answered only the talk, and with TTS_SERVE_S set on the hub
    since 23.1 no briefing voice and no blind-test sample was made)."""
    done: list[str] = []
    failed: list[str] = []
    rest_left = max(0, s.max_jobs)  # jobs of the other queues this pass may still take
    deadline = time.monotonic() + s.serve_s
    while time.monotonic() < deadline:
        got = await run_talk(client, default, s.max_jobs, pick)
        done += got["done"]
        failed += got["failed"]
        if got["done"] or got["failed"]:
            continue
        if rest_left > 0:
            rest = await run(client, default, 1, pick)
            done += rest["done"]
            failed += rest["failed"]
            took = len(rest["done"]) + len(rest["failed"])
            # nothing waiting: not asked again this pass
            rest_left = rest_left - took if took else 0
            if took:
                continue
        await asyncio.sleep(max(0.2, s.serve_poll_s))
    return {"done": done, "failed": failed}


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    s = Settings()
    default, shipped = engines(s)
    token = await api_token(s)

    def pick(voice: str | None) -> Engine | None:
        return shipped.get(voice) if voice else None

    async with httpx.AsyncClient(
        base_url=s.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as client:
        del token
        if s.serve_s > 0:
            out = await serve(client, default, s, pick)
        else:
            out = await run(client, default, s.max_jobs, pick)
    print(json.dumps(out))  # refs only
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
