"""`python -m hq_tts`: one pass of the one-shot (claim, speak, send back)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

from hq_tts.engine import Piper
from hq_tts.job import Settings, api_token, run

MEDIA_BASE = "/internal/v1/tts/media"  # prompt 13 §2: an item's narration (contract §22.3)


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    s = Settings()
    engine = Piper(Path(s.voices_dir), s.voice, s.threads)
    token = await api_token(s)
    async with httpx.AsyncClient(
        base_url=s.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as client:
        del token
        out = await run(client, engine, s.max_jobs)
        # ⟨1.6⟩ prompt 13: the media items' narrations, with the same engine
        out["media"] = await run(client, engine, s.max_jobs, base=MEDIA_BASE)
    print(json.dumps(out))  # refs only
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
