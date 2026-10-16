"""Seed loader: inserts the YAML seed rows that do not exist yet.

Never overwrites: once a row exists it belongs to the owner (later: the app).
Runs as the database owner from the migrate job.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncpg
import yaml

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def _load(name: str, seed_dir: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load((seed_dir / f"{name}.yaml").read_text())
    rows: list[dict[str, Any]] = data[name]
    return rows


async def seed(conn: asyncpg.Connection, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    added: dict[str, int] = {}
    async with conn.transaction():
        n = 0
        for c in _load("companies", seed_dir):
            status = await conn.execute(
                "INSERT INTO core.companies (code, name, kind) VALUES ($1, $2, $3)"
                " ON CONFLICT (code) DO NOTHING",
                c["code"],
                c["name"],
                c["kind"],
            )
            n += int(status.split()[-1])
        added["companies"] = n

        n = 0
        for t in _load("task_classes", seed_dir):
            status = await conn.execute(
                "INSERT INTO llm.task_classes (key, transferable, description) VALUES ($1, $2, $3)"
                " ON CONFLICT (key) DO NOTHING",
                t["key"],
                t["transferable"],
                t.get("description", ""),
            )
            n += int(status.split()[-1])
        added["task_classes"] = n

        n = 0
        for c in _load("connections", seed_dir):
            status = await conn.execute(
                """INSERT INTO llm.connections (key, kind, provider, display_name, status,
                       secret_ref, api_base, models, default_model, pricing, limits,
                       fallback_priority)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb, $11::jsonb, $12)
                   ON CONFLICT (key) DO NOTHING""",
                c["key"],
                c["kind"],
                c["provider"],
                c["display_name"],
                c.get("status", "disabled"),
                c.get("secret_ref"),
                c.get("api_base"),
                json.dumps(c.get("models", [])),
                c.get("default_model"),
                json.dumps(c.get("pricing", {})),
                json.dumps(c.get("limits", {})),
                c.get("fallback_priority"),
            )
            n += int(status.split()[-1])
        added["connections"] = n

        n = 0
        for a in _load("assignments", seed_dir):
            conn_id = None
            if a.get("connection"):
                conn_id = await conn.fetchval(
                    "SELECT id FROM llm.connections WHERE key = $1", a["connection"]
                )
                if conn_id is None:
                    msg = f"assignment references unknown connection {a['connection']}"
                    raise ValueError(msg)
            status = await conn.execute(
                """INSERT INTO llm.assignments
                       (scope_type, scope_ref, connection_id, model, effort, note)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (scope_type, scope_ref) DO NOTHING""",
                a["scope_type"],
                a["scope_ref"],
                conn_id,
                a.get("model"),
                a.get("effort"),
                a.get("note"),
            )
            n += int(status.split()[-1])
        added["assignments"] = n
    return added
