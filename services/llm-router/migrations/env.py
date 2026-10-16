"""Alembic environment: async engine on asyncpg, settings from the environment.

Runs as the database owner (role hq). Migrations are raw SQL: RLS, policies,
partitioning and grants are clearer in SQL than in ORM metadata.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import create_async_engine


def _url() -> URL:
    return URL.create(
        "postgresql+asyncpg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "postgres"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "hq"),
    )


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table=context.config.get_main_option("version_table") or "alembic_version",
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
        await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported")
asyncio.run(_main())
