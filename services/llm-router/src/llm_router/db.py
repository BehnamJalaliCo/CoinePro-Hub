"""asyncpg pool with company-scoped transactions for row-level security.

Every transaction that touches llm.calls/usage/budgets/transcripts sets
app.company_ids (SET LOCAL) to the companies it may see; RLS does the rest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

import asyncpg

from llm_router.config import Settings


def company_ids_literal(ids: Iterable[str]) -> str:
    """uuid[] literal for app.company_ids, e.g. '{a,b}'."""
    return "{" + ",".join(sorted({str(i) for i in ids})) + "}"


class Database:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def connect(cls, s: Settings, *, min_size: int = 1, max_size: int = 10) -> Database:
        pool = await asyncpg.create_pool(
            host=s.db_host,
            port=s.db_port,
            database=s.db_name,
            user=s.db_user,
            password=s.db_password,
            min_size=min_size,
            max_size=max_size,
            command_timeout=15,
        )
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def scoped(self, company_ids: Iterable[str]) -> AsyncIterator[asyncpg.Connection]:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT set_config('app.company_ids', $1, true)", company_ids_literal(company_ids)
            )
            yield conn

    async def ping(self) -> bool:
        async with self.pool.acquire() as conn:
            return bool(await conn.fetchval("SELECT true"))
