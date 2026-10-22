"""The entry point's pieces: the api token cache and the run loop."""

from __future__ import annotations

import threading
import time
from typing import Any

from hq_provisioner import __main__ as main
from hq_provisioner.hub import HubError


class CountingVault:
    def __init__(self) -> None:
        self.n = 0

    def api_token(self) -> str:
        self.n += 1
        return f"svc-{self.n}"


def test_the_api_token_is_read_again_only_after_ten_minutes(monkeypatch: Any) -> None:
    v = CountingVault()
    cache = main.TokenCache(v)  # type: ignore[arg-type]
    assert cache() == cache() == "svc-1"
    monkeypatch.setattr(main, "API_TOKEN_TTL_S", 0.0)
    time.sleep(0.01)
    assert cache() == "svc-2"


def test_the_loop_survives_errors_and_wakes_on_demand() -> None:
    calls: list[str] = []

    class R:
        def tick(self) -> bool:
            calls.append("tick")
            if len(calls) == 1:
                raise HubError("api unreachable")
            if len(calls) == 2:
                raise RuntimeError("boom")
            return len(calls) == 3  # one run, then nothing

    wake = threading.Event()
    beat = {"loop": 0.0}
    threading.Thread(target=main.loop, args=(R(), wake, beat, 0.01), daemon=True).start()
    deadline = time.monotonic() + 5
    while len(calls) < 5 and time.monotonic() < deadline:
        wake.set()
        time.sleep(0.01)
    assert len(calls) >= 5 and beat["loop"] > 0
