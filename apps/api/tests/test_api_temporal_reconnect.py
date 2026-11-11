"""Audit 2026-11-11: the API retries Temporal when it was down at start,
instead of running without workflows for the life of the process."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from hq_api import __main__ as entry
from hq_api import workflows_client


async def test_temporal_down_at_start_is_retried_until_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object()
    calls: list[str] = []

    async def flaky_connect(address: str, namespace: str) -> Any:
        calls.append(address)
        if len(calls) < 3:
            raise ConnectionError("temporal restarting")
        return client

    monkeypatch.setattr(workflows_client, "connect", flaky_connect)
    hub = cast(
        Any,
        SimpleNamespace(
            settings=SimpleNamespace(temporal_address="temporal:7233", temporal_namespace="hq"),
            temporal=None,
        ),
    )
    # The first attempt (in build) fails: the API starts without Temporal.
    assert await entry.connect_temporal(hub) is False
    assert hub.temporal is None

    monkeypatch.setattr(entry, "TEMPORAL_RETRY_FIRST_S", 0.01)
    await asyncio.wait_for(entry.temporal_reconnect(hub), 5)
    assert hub.temporal is client
    assert len(calls) == 3


async def test_a_hung_connect_times_out_and_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(address: str, namespace: str) -> Any:
        await asyncio.Event().wait()

    monkeypatch.setattr(workflows_client, "connect", hang)
    monkeypatch.setattr(entry, "TEMPORAL_CONNECT_TIMEOUT_S", 0.05)
    hub = cast(
        Any,
        SimpleNamespace(
            settings=SimpleNamespace(temporal_address="temporal:7233", temporal_namespace="hq"),
            temporal=None,
        ),
    )
    assert await entry.connect_temporal(hub) is False
    assert hub.temporal is None
