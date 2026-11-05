"""Handoff 2026-11-05, bug 2: the stream's heartbeat is by the clock.

A busy bus whose events this client does not take (another company's, another topic's) kept `next_msg` answering, so
the old loop wrote nothing and the app's 50 s read timeout cut the stream (`SocketTimeoutException` on `GET /stream`).
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any

from hq_api.routes import stream


class _Sub:
    """A bus that answers at once, forever, with an event of another company."""

    def __init__(self) -> None:
        self.seq = 0

    async def next_msg(self, timeout: float) -> Any:  # noqa: ASYNC109 - the nats-py signature
        await asyncio.sleep(0.005)
        self.seq += 1
        env = {
            "id": str(self.seq),
            "type": "work.created",
            "company": "OTHER",
            "at": "2026-11-05T00:00:00Z",
        }
        return SimpleNamespace(
            data=json.dumps(env).encode(),
            metadata=SimpleNamespace(sequence=SimpleNamespace(stream=self.seq)),
        )

    async def unsubscribe(self) -> None:
        return None


def _ctx() -> Any:
    sub = _Sub()

    async def subscribe(*_a: Any, **_k: Any) -> _Sub:
        return sub

    bus = SimpleNamespace(connected=True, js=SimpleNamespace(subscribe=subscribe))
    return SimpleNamespace(hub=SimpleNamespace(bus=bus))


async def test_a_busy_bus_of_other_events_still_gets_a_heartbeat(monkeypatch: Any) -> None:
    monkeypatch.setattr(stream, "HEARTBEAT_S", 0.2)
    gen = stream.bridge(_ctx(), {"work"}, {"MINE"}, False, None)
    first = await gen.__anext__()
    assert first.startswith(b": topics")
    t0 = time.monotonic()
    second = await asyncio.wait_for(gen.__anext__(), timeout=2)
    assert second == b": heartbeat\n\n"
    assert time.monotonic() - t0 < 1.0
    await gen.aclose()


async def test_a_matching_event_goes_out_and_resets_the_clock(monkeypatch: Any) -> None:
    monkeypatch.setattr(stream, "HEARTBEAT_S", 0.2)
    gen = stream.bridge(_ctx(), {"work"}, {"OTHER"}, False, None)
    await gen.__anext__()
    out = await asyncio.wait_for(gen.__anext__(), timeout=2)
    assert out.startswith(b"id: ") and b"event: work.created" in out
    await gen.aclose()
