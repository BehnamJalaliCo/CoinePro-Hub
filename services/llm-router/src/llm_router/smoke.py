"""`python -m llm_router.smoke < token`: one small real call, end to end.

Run inside the llm-router container (make llm-smoke). Prints the API
response (usage, cost), the ledger row and the call.finished NATS event.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import asyncpg
import httpx
import nats

from llm_router.config import Settings
from llm_router.db import company_ids_literal

REQUEST = {
    "company_code": "HQ",
    "actor_ref": "owner",
    "work_ref": "prompt-03-smoke",
    "task_class": "general",
    "priority": "P2",
    "model": "claude-haiku-5-5",
    "effort": "low",
    "prompt": "Just write OK",
    "timeout_s": 120,
}


async def main() -> int:
    token = sys.stdin.read().strip()
    s = Settings()
    nc = await nats.connect(s.nats_url, user=s.nats_user, password=s.nats_password)
    events: list[tuple[str, dict[str, Any]]] = []

    async def on_event(msg: Any) -> None:
        events.append((msg.subject, json.loads(msg.data)))

    await nc.subscribe("hq.llm.HQ.call.*", cb=on_event)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{s.listen_port}", timeout=180) as c:
        r = await c.post("/v1/run", json=REQUEST, headers={"Authorization": f"Bearer {token}"})
    body = r.json()
    for _ in range(50):
        if any(subj.endswith(".finished") for subj, _ in events):
            break
        await asyncio.sleep(0.1)
    await nc.drain()

    conn = await asyncpg.connect(
        host=s.db_host, user=s.db_user, password=s.db_password, database=s.db_name
    )
    try:
        async with conn.transaction():
            hq = await conn.fetchval("SELECT id::text FROM core.companies WHERE code = 'HQ'")
            await conn.execute(
                "SELECT set_config('app.company_ids', $1, true)", company_ids_literal([hq])
            )
            row = await conn.fetchrow(
                """SELECT c.id, c.status, c.model, c.effort, c.input_tokens, c.output_tokens,
                          c.cache_read_tokens, c.cache_write_tokens, c.thinking_tokens,
                          c.cost_usd, c.equiv_cost_usd, c.latency_ms, c.error_class,
                          cn.key AS connection
                   FROM llm.calls c JOIN llm.connections cn ON cn.id = c.connection_id
                   WHERE c.id = $1::uuid""",
                body.get("call_id"),
            )
    finally:
        await conn.close()
    print(
        json.dumps(
            {
                "http_status": r.status_code,
                "response": body,
                "ledger_row": dict(row) if row else None,
                "nats_events": [
                    {"subject": subj, "call_id": e.get("call_id"), "status": e.get("status")}
                    for subj, e in events
                ],
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )
    return 0 if r.status_code == 200 and row and row["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
