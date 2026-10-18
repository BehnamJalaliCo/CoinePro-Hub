"""Seed from files (prompt 04 §2): company extensions and templates.

Idempotent and conservative: fields are filled only where empty; rows are
only added, never overwritten (edits made later in the app survive).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hq_api.db import Tx
from hq_api.domain import sites, templates
from hq_api.workshop import domain as workshop

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


async def seed(tx: Tx) -> dict[str, Any]:
    data = yaml.safe_load((SEED_DIR / "companies.yaml").read_text(encoding="utf-8"))
    filled = 0
    for c in data.get("companies") or []:
        filled += await tx.exec(
            """UPDATE core.companies
               SET name_fa = COALESCE(name_fa, :nfa),
                   name_en = COALESCE(name_en, :nen),
                   color_index = COALESCE(color_index, :ci),
                   template = COALESCE(template, :tpl)
               WHERE code = :code
                 AND (name_fa IS NULL OR color_index IS NULL OR template IS NULL)""",
            code=c["code"],
            nfa=c.get("name_fa"),
            nen=c.get("name_en"),
            ci=c.get("color_index"),
            tpl=c.get("template"),
        )
    # Every company gets its template applied (only what is missing is added).
    added: dict[str, int] = {"departments": 0, "employees": 0, "threads": 0, "roles": 0}
    for co in await tx.all("SELECT id, code, kind, template FROM core.companies ORDER BY code"):
        key = co["template"] or ("holding" if co["kind"] == "holding" else "standard")
        for k, v in (await templates.apply(tx, co["id"], co["code"], key)).items():
            added[k] += v
        # The charter of each leadership position follows its template (no
        # API edits it); hired employees keep the role their decision gave.
        for code, role in templates.leadership_roles(co["code"], key).items():
            added["roles"] += await tx.exec(
                """UPDATE core.employees SET role = :role
                   WHERE code = :code AND company_id = :co AND role IS DISTINCT FROM :role""",
                code=code,
                co=co["id"],
                role=role,
            )
    added["sites"] = await sites.seed(tx)
    added["workspaces"] = await workshop.seed(tx)
    return {"companies_filled": filled, **added}
