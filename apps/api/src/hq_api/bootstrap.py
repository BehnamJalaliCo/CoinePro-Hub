"""`python -m hq_api.bootstrap <key>`: setup work from seed/bootstrap/<key>.yaml
(prompt 05 §9.2), as the service "bootstrap".

Each entry becomes one work item for the employee who holds the entry's role
(in every company of kind "company", or in the holding). Applying it again
adds only what is missing, so a company added later gets its items too.
The work wakes its assignee like any other work (a run is queued).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from hq_api.config import Settings
from hq_api.db import Database, Tx
from hq_api.domain import work as W
from hq_api.principal import Principal
from hq_common import logs

log = logging.getLogger("hq_api.bootstrap")
BOOTSTRAP_DIR = Path(__file__).resolve().parents[2] / "seed" / "bootstrap"
BOOTSTRAP = Principal(kind="service", code="bootstrap", role="service")


def load(key: str) -> dict[str, Any]:
    if not key.replace("_", "").isalnum():
        raise ValueError("bad bootstrap key")
    data: dict[str, Any] = yaml.safe_load((BOOTSTRAP_DIR / f"{key}.yaml").read_text("utf-8"))
    if data.get("key") != key:
        raise ValueError(f"{key}.yaml: key mismatch")
    return data


async def apply(tx: Tx, data: dict[str, Any]) -> dict[str, Any]:
    created: list[dict[str, str]] = []
    skipped = 0
    for item in data.get("items") or []:
        kinds = {"companies": "company", "holding": "holding"}[item["for"]]
        for co in await tx.all(
            "SELECT id, code FROM core.companies WHERE kind = :k ORDER BY code", k=kinds
        ):
            emp = await tx.first(
                """SELECT code FROM core.employees WHERE company_id = :co AND role = :role
                     AND status = 'active' ORDER BY created_at LIMIT 1""",
                co=co["id"],
                role=item["role"],
            )
            if emp is None:
                log.warning(
                    "bootstrap: nobody holds the role",
                    extra={"company": co["code"], "role": item["role"]},
                )
                continue
            tag = f"bootstrap:{data['key']}:{item['role']}"
            if await tx.scalar(
                """SELECT 1 FROM work.work w JOIN work.work_events e ON e.work_id = w.id
                   WHERE w.company_id = :co AND w.created_by_code = :by
                     AND e.kind = 'bootstrap' AND e.data->>'tag' = :tag""",
                co=co["id"],
                by=BOOTSTRAP.code,
                tag=tag,
            ):
                skipped += 1
                continue
            w = await W.create(
                tx,
                BOOTSTRAP,
                company_id=co["id"],
                company_code=co["code"],
                title=item["title"],
                brief=f"{item['brief'].strip()}\n\n(Reference: {data['reference']})",
                kind="one_off",
                priority=item.get("priority", "P3"),
                assignee_code=emp["code"],
                budget=W.BudgetIn(tokens=int(item["budget_tokens"])),
            )
            await W.event(
                tx,
                {"id": w["id"], "company_id": co["id"]},
                "bootstrap",
                BOOTSTRAP,
                {"tag": tag, "reference": data["reference"]},
            )
            created.append({"ref": w["ref"], "assignee": emp["code"]})
    return {"created": created, "skipped": skipped}


async def _main(key: str) -> dict[str, Any]:  # pragma: no cover - CLI
    s = Settings()
    db = Database.create(s, pool_size=1)
    try:
        async with db.raw() as tx:
            ids = [r["id"] for r in await tx.all("SELECT id FROM core.companies")]
        async with db.tx(ids) as tx:
            return await apply(tx, load(key))
    finally:
        await db.close()


def main() -> None:  # pragma: no cover - CLI
    s = Settings()
    logs.setup("bootstrap", s.log_level)
    out = asyncio.run(_main(sys.argv[1] if len(sys.argv) > 1 else "month1"))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
