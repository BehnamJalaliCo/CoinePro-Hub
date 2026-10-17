"""Prompt 5.1 §2.8 and §3: the stream carries the runs topic, and an unknown
topic is ignored (contract §7, v1.4.1 and v1.4.2)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import events

from .test_agents import order, run, runs_of, step
from .test_control_treasury_stream import _events, serve

pytestmark = pytest.mark.usefixtures("relay")


async def _first_comment(url: str, headers: dict[str, str], topics: str) -> str:
    async with (
        httpx.AsyncClient(base_url=url, timeout=10) as c,
        c.stream("GET", "/api/v1/stream", headers=headers, params={"topics": topics}) as resp,
    ):
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith(":"):
                return line
    raise AssertionError("no comment")


async def test_unknown_topics_are_ignored_and_named(
    app: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    async with serve(app) as url:
        assert await _first_comment(url, owner, "work,oversight") == ": topics work"
        newer = "files,workshop,orders,runs,oversight"
        served = ",".join(t for t in events.TOPICS if t in newer.split(","))
        assert await _first_comment(url, owner, newer) == f": topics {served}"
        assert await _first_comment(url, owner, "gossip") == ": topics"  # nothing served
    for bad in ("Work!", "work,,x", "a" * 201):
        r = await client.get("/api/v1/stream", headers=owner, params={"topics": bad})
        assert r.status_code == 422, bad


async def test_a_run_is_seen_on_the_runs_topic(
    app: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with serve(app) as url:
        listener = asyncio.create_task(_events(url, owner, {"topics": "runs", "company": co}, 3))
        await asyncio.sleep(0.5)
        w = await order(client, owner, co)
        (ceo,) = await runs_of(su, f"{co}-CEO")
        agents.fake.enqueue(f"{co}-CEO", step("خواندن کار", ("work.get", {"ref": w["ref"]})))
        assert (await run(agents, ceo["id"]))["state"] == "done"
        got = await asyncio.wait_for(listener, 20)
    assert [e["event"] for e in got] == ["run.started", "run.step", "run.finished"]
    assert {e["data"]["ref"] for e in got} == {str(ceo["id"])}
    assert got[1]["data"]["data"]["actions"] == ["work.get"]
