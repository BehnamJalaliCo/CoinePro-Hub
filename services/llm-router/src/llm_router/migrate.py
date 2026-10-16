"""`python -m llm_router.migrate`: Alembic upgrade, seed, partitions.

Run by the one-shot compose job llm-migrate as the database owner (role hq).
Idempotent: safe on every `make up`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

from hq_common import logs
from llm_router.seed import seed

log = logging.getLogger("llm_router.migrate")
ROOT = Path(__file__).resolve().parents[2]


async def _seed_and_partitions() -> None:
    conn = await asyncpg.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "hq"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    try:
        added = await seed(conn)
        created = await conn.fetchval("SELECT llm.ensure_calls_partitions(3)")
    finally:
        await conn.close()
    log.info("seed and partitions done", extra={"seed_added": added, "partitions_created": created})


def main() -> None:
    logs.setup("llm-migrate", os.environ.get("LOG_LEVEL", "info"))
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    log.info("alembic upgrade head done")
    asyncio.run(_seed_and_partitions())


if __name__ == "__main__":
    main()
