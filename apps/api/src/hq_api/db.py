"""Database access: SQLAlchemy 2 async engine (asyncpg), SQL-first.

The schema lives in the Alembic migrations (raw SQL: RLS, triggers,
policies). Queries are explicit SQL through `Tx`, a thin wrapper over one
AsyncConnection inside one transaction.

Every transaction starts with `SET LOCAL app.company_ids` (uuid[]), the RLS
contract shared with llm.*: the owner gets every company, an agent only its
own. Nothing is visible before that line runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from hq_api.config import Settings
from hq_api.errors import ApiError


def company_ids_literal(ids: Iterable[UUID | str]) -> str:
    return "{" + ",".join(str(i) for i in ids) + "}"


class Tx:
    """One connection in one transaction. Rows come back as plain dicts."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def all(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        result = await self.conn.execute(text(sql), params)
        return [dict(r) for r in result.mappings().all()]

    async def first(self, sql: str, **params: Any) -> dict[str, Any] | None:
        result = await self.conn.execute(text(sql), params)
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def one(self, sql: str, *, not_found: str = "not_found", **params: Any) -> dict[str, Any]:
        row = await self.first(sql, **params)
        if row is None:
            raise ApiError(404, not_found)
        return row

    async def scalar(self, sql: str, **params: Any) -> Any:
        result = await self.conn.execute(text(sql), params)
        return result.scalar()

    async def exec(self, sql: str, **params: Any) -> int:
        result = await self.conn.execute(text(sql), params)
        return int(result.rowcount)


class Database:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @classmethod
    def create(cls, s: Settings, *, pool_size: int | None = None) -> Database:
        url = URL.create(
            "postgresql+asyncpg",
            username=s.db_user,
            password=s.db_password,
            host=s.db_host,
            port=s.db_port,
            database=s.db_name,
        )
        engine = create_async_engine(
            url,
            pool_size=pool_size or s.db_pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=1800,
            # Parameters (message bodies, notes) never appear in an error text.
            hide_parameters=True,
            connect_args={"server_settings": {"application_name": s.db_user}},
        )
        return cls(engine)

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def tx(self, company_ids: Iterable[UUID | str]) -> AsyncIterator[Tx]:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.company_ids', :ids, true)"),
                {"ids": company_ids_literal(company_ids)},
            )
            yield Tx(conn)

    @asynccontextmanager
    async def raw(self) -> AsyncIterator[Tx]:
        """A transaction without any company scope (tables without RLS only)."""
        async with self.engine.begin() as conn:
            yield Tx(conn)

    async def ping(self) -> bool:
        async with self.engine.connect() as conn:
            return bool((await conn.execute(text("SELECT 1"))).scalar())


def as_mapping(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}
