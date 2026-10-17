"""Fixtures for integration tests: real Postgres + NATS from scripts/test-env.sh.

The schema is migrated once per session as the owner (role hq); every test
starts from empty ledger tables. The router connects as llm_router, exactly
as in production, so row-level security is always in force.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import nats
import pytest

from llm_router.backends.base import OK, BackendCall, BackendResult, Delta
from llm_router.config import Settings
from llm_router.db import Database
from llm_router.events import Events
from llm_router.metrics import Metrics
from llm_router.pricing import Usage
from llm_router.registry import Registry
from llm_router.scheduler import PriorityScheduler
from llm_router.service import RouterService

ROUTER_DIR = Path(__file__).resolve().parents[1]
HOST = os.environ.get("TEST_DB_HOST", "postgres")
NATS_URL = os.environ.get("TEST_NATS_URL", "nats://nats:4222")
needs_db = pytest.mark.skipif("TEST_DB_HOST" not in os.environ, reason="needs scripts/test-env.sh")


def _env(user: str, password_var: str) -> dict[str, str]:
    return {**os.environ, "DB_HOST": HOST, "DB_USER": user, "DB_PASSWORD": os.environ[password_var]}


@pytest.fixture(scope="session")
def migrated() -> None:
    if "TEST_DB_HOST" not in os.environ:
        pytest.skip("needs scripts/test-env.sh")
    subprocess.run(
        [sys.executable, "-m", "llm_router.migrate"],
        cwd=ROUTER_DIR,
        check=True,
        env=_env("hq", "HQ_DB_PASSWORD"),
        capture_output=True,
    )


async def superuser() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=HOST, user="postgres", database="hq", password=os.environ["POSTGRES_PASSWORD"]
    )


@pytest.fixture
async def su(migrated: None) -> AsyncIterator[asyncpg.Connection]:
    conn = await superuser()
    await conn.execute(
        """TRUNCATE llm.calls, llm.usage, llm.budgets, llm.transcripts, llm.quota_status;
           DELETE FROM llm.assignments WHERE note IS DISTINCT FROM 'Default for the whole holding'
               AND note IS DISTINCT FROM 'General advisor (§1.1)';
           UPDATE llm.connections SET status = CASE key WHEN 'claude-max' THEN 'enabled' ELSE 'disabled' END,
               status_reason = NULL, quota_reset_at = NULL, api_base = NULL;"""
    )
    yield conn
    await conn.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        db_host=HOST,
        db_user="llm_router",
        db_password=os.environ.get("LLM_ROUTER_DB_PASSWORD", ""),
        nats_url=NATS_URL,
        nats_password=os.environ.get("NATS_PASSWORD", ""),
        max_concurrency=3,
        reserved_high=1,
        p4_max_waiting=1,
        registry_ttl_s=0,
        anomaly_min_calls=30,
    )


@pytest.fixture
async def db(settings: Settings, su: asyncpg.Connection) -> AsyncIterator[Database]:
    database = await Database.connect(settings, max_size=4)
    yield database
    await database.close()


@pytest.fixture
async def bus(settings: Settings) -> AsyncIterator[Events]:
    events = Events(settings.nats_url, settings.nats_user, settings.nats_password)
    await events.connect()
    yield events
    await events.close()


class Captured:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def subjects(self) -> list[str]:
        return [s for s, _ in self.messages]

    def raw(self) -> str:
        return json.dumps(self.messages)


@pytest.fixture
async def captured(settings: Settings) -> AsyncIterator[Captured]:
    cap = Captured()
    nc = await nats.connect(
        settings.nats_url, user=settings.nats_user, password=settings.nats_password
    )

    async def handler(msg: Any) -> None:
        cap.messages.append((msg.subject, json.loads(msg.data)))

    await nc.subscribe("hq.>", cb=handler)
    yield cap
    await nc.drain()


class FakeBackend:
    """Scripted backend: pops the next result; streams it word by word."""

    def __init__(self, *results: BackendResult, delay: float = 0.0) -> None:
        self.results = list(results)
        self.calls: list[BackendCall] = []
        self.delay = delay

    def _next(self) -> BackendResult:
        return self.results.pop(0) if self.results else ok_result()

    async def run(self, call: BackendCall) -> BackendResult:
        self.calls.append(call)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._next()

    async def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]:
        self.calls.append(call)
        result = self._next()
        for word in (result.text or "").split(" "):
            yield Delta(word + " ")
        yield result


def ok_result(text: str = "OK", model: str = "claude-sonnet-5-5", **usage: int) -> BackendResult:
    u = {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 0, "cache_write_tokens": 0}
    u.update(usage)
    return BackendResult(
        OK,
        text=text,
        model=model,
        usage=Usage(**u),
        sdk_cost_usd=Decimal("0.000400"),
        stop_reason="end_turn",
        effort_applied=True,
    )


@pytest.fixture
def make_service(settings: Settings, db: Database, bus: Events) -> Iterator[Any]:
    def build(
        subscription: Any = None, api: Any = None, capacity: int = 3, now: Any = None, **kw: Any
    ) -> RouterService:
        return RouterService(
            settings,
            db,
            Registry(db, 0),
            bus,
            Metrics(),
            PriorityScheduler(capacity, 1, kw.get("p4_max_waiting", 1), 8, 7),
            {"claude_subscription": subscription or FakeBackend(), "api": api or FakeBackend()},
            now=now or (lambda: datetime.now(UTC)),
        )

    yield build


async def company_id(su: asyncpg.Connection, code: str) -> str:
    return str(await su.fetchval("SELECT id FROM core.companies WHERE code = $1", code))
