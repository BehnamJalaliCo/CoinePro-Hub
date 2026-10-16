"""Kill switch (contract §9): while the holding's or a company's switch is
engaged the router runs only P0. control.lock_state() belongs to apps/api's
schema; this router-only test database gets a stand-in with the same
signature, removed again at the end."""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from llm_router.service import RouterError

from .conftest import company_id
from .test_integration_ledger import req

STAND_IN = """
    CREATE SCHEMA control;
    CREATE TABLE control.test_locks (company_id uuid PRIMARY KEY, state text NOT NULL);
    CREATE FUNCTION control.lock_state(p uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        AS $$ SELECT state FROM control.test_locks WHERE company_id = p $$;
    GRANT USAGE ON SCHEMA control TO hq_llm_writer;
    GRANT EXECUTE ON FUNCTION control.lock_state(uuid) TO hq_llm_writer;
"""


async def test_only_p0_runs_while_locked(su: asyncpg.Connection, make_service: Any) -> None:
    ty = await company_id(su, "TY")
    svc = make_service()
    assert await svc.lock_state(ty) is None  # no control schema: nothing is locked
    await su.execute(STAND_IN)
    try:
        for state in ("holding", "company"):
            await su.execute(
                "INSERT INTO control.test_locks VALUES ($1, $2) "
                "ON CONFLICT (company_id) DO UPDATE SET state = EXCLUDED.state",
                ty,
                state,
            )
            svc = make_service()  # a fresh cache
            with pytest.raises(RouterError) as info:
                await svc.run(req(priority=3), "test", 100_000)
            assert (info.value.status_code, info.value.code) == (423, "company_locked")
            assert (await svc.run(req(priority=0), "test", 100_000)).status == "ok"
        await su.execute("UPDATE control.test_locks SET state = 'deploy_freeze'")
        svc = make_service()
        assert (await svc.run(req(priority=3), "test", 100_000)).status == "ok"  # a freeze does not stop thinking
    finally:
        await su.execute("DROP SCHEMA control CASCADE")
