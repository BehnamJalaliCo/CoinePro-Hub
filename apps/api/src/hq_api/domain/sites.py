"""Rule-based site checks (contract §16.4): the site list as data.

The list is seeded from seed/sites.yaml and edited by the owner afterwards
(PUT /api/v1/ops/sites). Nothing here knows a company or a URL.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from hq_api.db import Tx

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "sites.yaml"
DEFAULT_EXPECT = {"status": 200}


@lru_cache(maxsize=1)
def seeded() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("sites") or [])


async def seed(tx: Tx) -> int:
    """Adds missing (company, url) rows; canary rows follow the file's `enabled`."""
    added = 0
    for s in seeded():
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=s["company"])
        if co is None:
            continue  # a company this hub does not have (yet)
        row = await tx.first(
            """INSERT INTO ops.sites (company_id, url, kind, method, expect, interval_s, enabled, canary)
               VALUES (:co, :url, :kind, :method, CAST(:expect AS jsonb), :interval, :enabled, :canary)
               ON CONFLICT (company_id, url) DO NOTHING RETURNING id""",
            co=co,
            url=s["url"],
            kind=s.get("kind", "web"),
            method=s.get("method", "GET"),
            expect=json.dumps(s.get("expect") or DEFAULT_EXPECT),
            interval=int(s.get("interval_s", 300)),
            enabled=bool(s.get("enabled", True)),
            canary=bool(s.get("canary", False)),
        )
        added += row is not None
        if row is None and s.get("canary"):
            await tx.exec(
                """UPDATE ops.sites SET enabled = :enabled
                   WHERE company_id = :co AND url = :url AND canary AND enabled IS DISTINCT FROM :enabled""",
                co=co,
                url=s["url"],
                enabled=bool(s.get("enabled", True)),
            )
    return added
