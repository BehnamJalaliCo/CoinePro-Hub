"""`python -m hq_tts`: one pass of the one-shot (claim, speak, send back)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

from hq_tts.engine import Engine, Piper, installed
from hq_tts.job import Settings, api_token, run


def engines(s: Settings) -> tuple[Engine, dict[str, Engine]]:
    """The default voice and every voice the image ships (prompt 13 §4)."""
    root = Path(s.voices_dir)
    shipped: dict[str, Engine] = {v: Piper(root, v, s.threads) for v in installed(root)}
    default = shipped.get(s.voice) or Piper(root, s.voice, s.threads)
    return default, shipped


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    s = Settings()
    default, shipped = engines(s)
    token = await api_token(s)
    async with httpx.AsyncClient(
        base_url=s.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as client:
        del token
        out = await run(client, default, s.max_jobs, lambda v: shipped.get(v) if v else None)
    print(json.dumps(out))  # refs only
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
