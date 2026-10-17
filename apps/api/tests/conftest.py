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
from hq_api.policy import Policy
from hq_api.secrets import Secrets
from hq_api.security import agent_tokens
from hq_api.storage import LocalStorage
from hq_api.worker.activities import Activities
from hq_api.worker.workflows import WORKFLOWS
from hq_common.tokens import digest

API_DIR = Path(__file__).resolve().parents[1]
ROUTER_DIR = Path("/w/llm-router")
HOST = os.environ.get("TEST_DB_HOST", "postgres")
ORIGIN = "https://hq.test"
SERVICE_TOKEN = "test-service-token-" + "0" * 40
AGENT_KEY = bytes.fromhex("11" * 32)

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
        "rate_per_principal": 100_000,
        "auth_rate_per_ip": 100_000,
    }
    base.update(over)
    return Settings(**base)


def make_secrets() -> Secrets:
    return Secrets(
        agent_token_key=AGENT_KEY, service_tokens={"test-service": digest(SERVICE_TOKEN)}
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
        code = code or random_code()
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
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


def agent_headers(code: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {agent_tokens.mint(AGENT_KEY, code, str(uuid.uuid4()))}"}


def service_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SERVICE_TOKEN}"}


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
