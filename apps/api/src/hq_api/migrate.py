"""`python -m hq_api.migrate`: Alembic upgrade + seed, as the owner role hq.

Run by the one-shot compose job api-migrate after llm-migrate (which owns
core.companies and llm.*). Idempotent: safe on every `make up`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from hq_api.config import Settings
from hq_api.db import Database
from hq_api.seed import seed
from hq_common import logs

log = logging.getLogger("hq_api.migrate")
ROOT = Path(__file__).resolve().parents[2]


async def _seed(s: Settings) -> dict[str, object]:
    db = Database.create(s, pool_size=1)
    try:
        async with db.raw() as tx:
            return await seed(tx)
    finally:
        await db.close()


def main() -> None:
    s = Settings()
    logs.setup("api-migrate", s.log_level)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    log.info("alembic upgrade head done")
    result = asyncio.run(_seed(s))
    log.info("seed done", extra={"seed": result})


if __name__ == "__main__":
    main()
