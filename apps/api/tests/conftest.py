"""Fixtures: real Postgres, NATS, Temporal and OPA from services/scripts/test-env.sh
(HQ_TEST_TARGET=api). Migrations (llm-router, then apps/api) and the seed run
once per session as the owner role hq; the API connects as hq_api, exactly as
in production, so RLS is always in force.

Append-only tables cannot be truncated, so tests never reset the database:
each test that needs isolation creates its own company (`new_company`).
"""

from __future__ import annotations

import os
import secrets
import string
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from hq_api.app import create_app
from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database
from hq_api.domain import templates
from hq_api.events import Bus
from hq_api.hub import Hub
from hq_api.live import LiveHub
from hq_api.policy import Policy
from hq_api.secrets import Secrets
from hq_api.security import agent_tokens
from hq_api.storage import LocalStorage
from hq_api.worker.activities import Activities
from hq_api.worker.workflows import WORKFLOWS
from hq_common import charters
from hq_common.tokens import digest

API_DIR = Path(__file__).resolve().parents[1]
ROUTER_DIR = Path("/w/llm-router")
HOST = os.environ.get("TEST_DB_HOST", "postgres")
ORIGIN = "https://hq.test"
SERVICE_TOKEN = "test-service-token-" + "0" * 40
PROVISIONER_TOKEN = "test-provisioner-token-" + "1" * 40  # the provisioner service (prompt 09)
AGENT_KEY = bytes.fromhex("11" * 32)
ROUTER_TOKEN = "test-router-token-" + "1" * 40
GATEWAY_TOKEN = "test-gateway-token-" + "2" * 40
PSEUDONYM_KEY = bytes.fromhex("33" * 32)  # kv/support/pseudonym in tests (prompt 10 §1.2)
WORKER_API_TOKEN = "test-worker-api-token-" + "4" * 40  # the connector's caller (prompt 10 §2.2)
SUBSTITUTES_TOKEN = "test-substitutes-token-" + "5" * 40  # the runner's dispatcher (prompt 12 §9.1)
TTS_TOKEN = "test-tts-token-" + "5" * 40  # the TTS one-shot (prompt 12 §4)
MEDIA_TOKEN = "test-media-token-" + "6" * 40  # the render one-shot (prompt 13 §2)

if "TEST_DB_HOST" not in os.environ:
    pytest.skip("needs services/scripts/test-env.sh (HQ_TEST_TARGET=api)", allow_module_level=True)


def _run(module: str, cwd: Path, user: str, password_var: str, extra_path: str) -> None:
    env = {
        **os.environ,
        "DB_HOST": HOST,
        "DB_USER": user,
        "DB_PASSWORD": os.environ[password_var],
        "PYTHONPATH": f"/w/hq-common/src:{extra_path}",
        "LOG_LEVEL": "warning",
    }
    proc = subprocess.run(
        [sys.executable, "-m", module], cwd=cwd, env=env, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{module} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    _run("llm_router.migrate", ROUTER_DIR, "hq", "HQ_DB_PASSWORD", "/w/llm-router/src")
    _run("hq_api.migrate", API_DIR, "hq", "HQ_DB_PASSWORD", "/api/src")


def settings(**over: Any) -> Settings:
    base: dict[str, Any] = {
        "db_host": HOST,
        "db_user": "hq_api",
        "db_password": os.environ["HQ_API_DB_PASSWORD"],
        "db_pool_size": 4,
        "nats_url": os.environ.get("TEST_NATS_URL", "nats://nats:4222"),
        "nats_password": os.environ.get("NATS_PASSWORD", ""),
        "temporal_address": os.environ.get("TEST_TEMPORAL_ADDRESS", "temporal:7233"),
        "opa_url": os.environ.get("TEST_OPA_URL", "http://opa:8181"),
        "public_origin": ORIGIN,
        "rp_id": "hq.test",
        "files_root": "/tmp/hq-files-test",
        "oversight_schedules": False,  # the protocols' schedules exist, paused
        "rate_per_principal": 100_000,
        "auth_rate_per_ip": 100_000,
    }
    base.update(over)
    return Settings(**base)


def make_secrets() -> Secrets:
    return Secrets(
        agent_token_key=AGENT_KEY,
        service_tokens={
            "test-service": digest(SERVICE_TOKEN),
            "provisioner": digest(PROVISIONER_TOKEN),
            "worker": digest(WORKER_API_TOKEN),
            "substitutes": digest(SUBSTITUTES_TOKEN),
            "tts": digest(TTS_TOKEN),
            "media": digest(MEDIA_TOKEN),
        },
        llm_router_token=ROUTER_TOKEN,
        gateway_token=GATEWAY_TOKEN,
        support_pseudonym_key=PSEUDONYM_KEY,
        worker_api_token=WORKER_API_TOKEN,
    )


@pytest.fixture(scope="session")
async def hub() -> AsyncIterator[Hub]:
    s = settings()
    db = Database.create(s)
    bus = Bus(s)
    await bus.connect()
    h = Hub(
        settings=s,
        db=db,
        companies=Companies(db, ttl_s=0),
        secrets=make_secrets(),
        policy=Policy(s.opa_url),
        storage=LocalStorage(s.files_root),
        bus=bus,
        charters=charters.load(),
        live=LiveHub(),
    )
    yield h
    await h.policy.aclose()
    await bus.close()
    await db.close()


@pytest.fixture(scope="session")
async def app(hub: Hub) -> Any:
    return create_app(hub)


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as c:
        yield c


async def superuser() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=HOST, user="postgres", database="hq", password=os.environ["POSTGRES_PASSWORD"]
    )


@pytest.fixture
async def su() -> AsyncIterator[asyncpg.Connection]:
    conn = await superuser()
    yield conn
    await conn.close()


def random_code(prefix: str = "T") -> str:
    return prefix + "".join(secrets.choice(string.ascii_uppercase) for _ in range(5))


@pytest.fixture(scope="session")
async def owner_db() -> AsyncIterator[Database]:
    """The database as the owner role hq (via the superuser), for test setup only."""
    db = Database.create(
        settings(db_user="postgres", db_password=os.environ["POSTGRES_PASSWORD"]), pool_size=2
    )
    yield db
    await db.close()


@pytest.fixture
def new_company(hub: Hub, owner_db: Database) -> Callable[..., Any]:
    """Create a fresh company from a template (as the owner role hq)."""

    async def make(template: str = "standard", code: str | None = None) -> dict[str, Any]:
        given = code is not None
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            # The test database outlives a run: a random code may already exist.
            while code is None or (
                not given
                and await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=code)
            ):
                code = random_code()
            row = await tx.one(
                """INSERT INTO core.companies (code, name, kind, name_fa, name_en, color_index, template)
                   VALUES (:code, :name, 'company', :nfa, :name, NULL, :tpl) RETURNING id, code""",
                code=code,
                name=f"Test {code}",
                nfa=f"شرکت آزمایشی {code}",
                tpl=template,
            )
            await templates.apply(tx, row["id"], code, template)
        hub.companies.invalidate()
        return {"id": row["id"], "code": code}

    return make


async def owner_token(hub: Hub, client_kind: str = "android") -> tuple[str, uuid.UUID]:
    """A real owner session row for a test passkey (identity tests do the full flow)."""
    from hq_api.security import sessions

    async with hub.db.raw() as tx:
        pk = await tx.scalar(
            """INSERT INTO auth.passkeys (credential_id, public_key, name)
               VALUES (:cid, :pub, 'test device') RETURNING id""",
            cid=secrets.token_bytes(16),
            pub=b"test-key",
        )
        token, row = await sessions.create(
            tx, hub.settings, passkey_id=pk, client=client_kind, device_name="pytest", ip_hash=None
        )
    return token, row["id"]


@pytest.fixture
async def owner(hub: Hub) -> dict[str, str]:
    token, _ = await owner_token(hub)
    return {"Authorization": f"Bearer {token}"}


_POOL: asyncpg.Pool | None = None


async def _su_pool() -> asyncpg.Pool:
    """A small superuser pool for test setup (the session shares one event loop)."""
    global _POOL
    if _POOL is None:
        _POOL = await asyncpg.create_pool(
            host=HOST,
            user="postgres",
            database="hq",
            password=os.environ["POSTGRES_PASSWORD"],
            min_size=1,
            max_size=4,
        )
    return _POOL


async def running_run(code: str) -> str:
    """The employee's running run (the registry allows one at a time), started
    for the test if there is none. An unknown code gets a run id nobody has."""
    pool = await _su_pool()
    async with pool.acquire() as c:
        rid = await c.fetchval(
            """SELECT r.id FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
               WHERE e.code = $1 AND r.state = 'running' AND r.token_expires_at > now()""",
            code,
        )
        if rid is None:
            rid = await c.fetchval(
                """INSERT INTO agents.runs (company_id, employee_id, trigger, reason, state, started_at,
                       token_expires_at)
                   SELECT company_id, id, 'work', 'test', 'running', now(), now() + interval '1 hour'
                   FROM core.employees WHERE code = $1
                   ON CONFLICT DO NOTHING RETURNING id""",
                code,
            )
    return str(rid or uuid.uuid4())


@pytest.fixture
async def hiring_open() -> AsyncIterator[None]:
    """Hiring open to agents (contract §18.11) for a test whose agents propose
    hires; closed again afterwards, as it is by default."""
    pool = await _su_pool()
    async with pool.acquire() as c:
        await c.execute(
            """INSERT INTO core.hiring (company_id, state, mode)
               SELECT id, 'open', 'proposals' FROM core.companies WHERE kind = 'holding'
               ON CONFLICT (company_id) DO UPDATE SET state = 'open', mode = 'proposals'"""
        )
    yield
    async with pool.acquire() as c:
        await c.execute("UPDATE core.hiring SET state = 'closed', mode = NULL")


async def agent_headers(code: str) -> dict[str, str]:
    """An agent token for `code`, bound to a running run in the registry."""
    run = await running_run(code)
    return {"Authorization": f"Bearer {agent_tokens.mint(AGENT_KEY, code, run)}"}


def service_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def provisioner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PROVISIONER_TOKEN}"}


def worker_headers() -> dict[str, str]:
    """The worker's own api service token (prompt 10 §2.2: the connector's caller)."""
    return {"Authorization": f"Bearer {WORKER_API_TOKEN}"}


def substitutes_headers() -> dict[str, str]:
    """The substitutes runner's host dispatcher (prompt 12 §9.1)."""
    return {"Authorization": f"Bearer {SUBSTITUTES_TOKEN}"}


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def step_up(hub: Hub, session_id: uuid.UUID, action: str, target: str) -> dict[str, str]:
    """A verified step-up token for (session, action, target), as the passkey flow
    would issue it (the full WebAuthn flow is covered by test_identity.py)."""
    token = secrets.token_urlsafe(32)
    async with hub.db.raw() as tx:
        await tx.exec(
            """INSERT INTO auth.step_ups (session_id, action, target, challenge, challenge_expires_at,
                   token_sha256, verified_at, expires_at)
               VALUES (:s, :a, :t, :c, now() + interval '5 minutes', :h, now(),
                       now() + interval '120 seconds')""",
            s=session_id,
            a=action,
            t=target,
            c=secrets.token_bytes(32),
            h=digest(token),
        )
    return {"X-Step-Up": token}


@pytest.fixture
async def owner_session(hub: Hub) -> dict[str, Any]:
    """Headers plus the session id (for step-up tokens)."""
    token, sid = await owner_token(hub)
    return {"headers": {"Authorization": f"Bearer {token}"}, "session_id": sid}


@pytest.fixture(scope="session")
async def relay(hub: Hub) -> AsyncIterator[None]:
    """The outbox relay (as in the api process), so events reach NATS."""
    import asyncio
    import contextlib

    from hq_api.events import OutboxRelay

    task = asyncio.create_task(OutboxRelay(hub.settings, hub.db, hub.bus).run())  # type: ignore[arg-type]
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.fixture(scope="session")
async def wk(hub: Hub) -> AsyncIterator[dict[str, Any]]:
    s = settings(
        db_user="hq_worker",
        db_password=os.environ["HQ_WORKER_DB_PASSWORD"],
        task_queue=f"hq-core-test-{uuid.uuid4().hex[:8]}",
    )
    db = Database.create(s, pool_size=4)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    whub = Hub(
        settings=s,
        db=db,
        companies=Companies(db, ttl_s=0),
        secrets=make_secrets(),
        policy=hub.policy,
        storage=hub.storage,
        bus=hub.bus,
        temporal=client,
        charters=hub.charters,
    )
    acts = Activities(whub, client, lock_poll_s=1, escalation_gap_s=0)
    async with Worker(client, task_queue=s.task_queue, workflows=WORKFLOWS, activities=acts.all()):
        yield {"hub": whub, "client": client, "acts": acts, "tq": s.task_queue}
    await db.close()


def body_bytes(body: Any) -> bytes:
    import json as _json

    return _json.dumps(body, ensure_ascii=False).encode()


async def signed_put(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    path: str,
    body: Any,
    action: str,
) -> httpx.Response:
    """PUT whose step-up is bound to the SHA-256 of the exact body (contract §10 v1.1)."""
    import hashlib

    content = body_bytes(body)
    su = await step_up(
        hub, owner_session["session_id"], action, hashlib.sha256(content).hexdigest()
    )
    return await client.put(
        path,
        content=content,
        headers={**owner_session["headers"], **su, "Content-Type": "application/json"},
    )


@pytest.fixture(scope="session")
async def agents(app: Any, wk: dict[str, Any]) -> AsyncIterator[Any]:
    """llm-router (fake model) + Tool Gateway + api in process; the runner on the worker's hub."""
    from .agents_env import build

    env = await build(app, wk["hub"], HOST, ROUTER_TOKEN, GATEWAY_TOKEN)
    yield env
    await env.close()
