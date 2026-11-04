"""The adapters of the voice engines (contract §32.5): one interface (voice/base.py `Engine`),
one file per provider, and a registry from an engine key of seed/voice/engines.yaml to its adapter.

A new engine of an existing provider is a block in the seed file; a new provider is one adapter
file here plus a line in `ADAPTERS`. Tests swap an adapter in with `OVERRIDE`.
"""

from __future__ import annotations

from collections.abc import Callable

from hq_api.voice import catalog
from hq_api.voice.base import Engine
from hq_api.voice.engines._ctx import FILE_NAME
from hq_api.voice.engines.gemini import GeminiEngine
from hq_api.voice.engines.piper import PiperEngine

# provider -> how to build the adapter of one engine of it
ADAPTERS: dict[str, Callable[[catalog.EngineDef], Engine]] = {
    "google": lambda e: GeminiEngine(e.key, e.model),
    "local": lambda e: PiperEngine(e.key),
}
OVERRIDE: dict[str, Engine] = {}  # tests: engine key -> a fake adapter

__all__ = ["ADAPTERS", "FILE_NAME", "OVERRIDE", "engine_for"]


def engine_for(key: str) -> Engine:
    if key in OVERRIDE:
        return OVERRIDE[key]
    e = catalog.load().engines[key]
    return ADAPTERS[e.provider](e)
