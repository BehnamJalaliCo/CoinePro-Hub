"""Who sees what in the archive (contract §23.4, §23.12; prompt 14 red line 3).

Every transaction that reads the archive sets `app.clearance` (SET LOCAL,
set_config(..., true)) before its first query; the database's policies
(archive.can_see) decide from it, so a record above the reader's clearance
is never in any answer, count or snippet, whatever the query. Without it
nothing is visible.

    {"all": true}                                   the owner, the hub's own jobs
    {"code": <employee>, "grants": {<company uuid>|"*": rank}, "meta": rank}
                                                    an agent: its role's grants

An agent's subject is `employee:<code>` if the owner set one, else
`role:<charter>`, else the default `role:*` (every role `internal` in its own
company). Grant scopes: `own` (the agent's company), `holding`, `all`, or a
company code. Content grants are capped at the level marked `agents_max`
(seeded on `confidential`); the metadata level (the archivist's, for what
it files) is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from hq_api.archive.common import J
from hq_api.db import Tx
from hq_api.principal import Principal

ALL = {"all": True}
DEFAULT_SUBJECT = "role:*"


@dataclass(frozen=True)
class Clearance:
    everything: bool
    code: str | None = None
    grants: dict[str, int] = field(default_factory=dict)  # company uuid | "*" -> rank
    meta: int | None = None
    agent: bool = False

    def setting(self) -> dict[str, Any]:
        if self.everything:
            return dict(ALL)
        out: dict[str, Any] = {"code": self.code, "grants": self.grants}
        if self.meta is not None:
            out["meta"] = self.meta
        return out

    def rank_in(self, company_id: UUID | str) -> int:
        if self.everything:
            return 1 << 30
        return self.grants.get(str(company_id), self.grants.get("*", -1))

    def sees(self, rank: int, company_id: UUID | str) -> bool:
        return rank <= self.rank_in(company_id)

    def files_at(self, rank: int, company_id: UUID | str) -> bool:
        """May this reader file (and so see the metadata of) a record of this rank?"""
        return self.sees(rank, company_id) or (self.meta is not None and rank <= self.meta)


EVERYTHING = Clearance(everything=True)


async def apply(tx: Tx, c: Clearance) -> Clearance:
    await tx.exec(
        "SELECT set_config('app.clearance', :c, true)", c=json.dumps(c.setting(), sort_keys=True)
    )
    return c


async def full(tx: Tx) -> Clearance:
    """The owner and the hub's own rule-only jobs."""
    return await apply(tx, EVERYTHING)


async def ranks(tx: Tx) -> dict[str, int]:
    rows = await tx.all("SELECT key, rank FROM archive.levels")
    return {r["key"]: int(r["rank"]) for r in rows}


async def agents_max(tx: Tx) -> int:
    rank = await tx.scalar("SELECT rank FROM archive.levels WHERE agents_max")
    return int(rank) if rank is not None else 20


async def subject_row(tx: Tx, who: Principal) -> dict[str, Any] | None:
    for subject in (f"employee:{who.code}", f"role:{who.charter}", DEFAULT_SUBJECT):
        row = await tx.first(
            "SELECT * FROM archive.clearance WHERE subject = :s AND status = 'active'", s=subject
        )
        if row is not None:
            return row
    return None


async def of_agent(tx: Tx, who: Principal) -> Clearance:
    """The clearance of an agent principal, read under the holding's scope
    (the caller's transaction must reach the holding's configuration rows)."""
    row = await subject_row(tx, who)
    level_rank = await ranks(tx)
    cap = await agents_max(tx)
    grants: dict[str, int] = {}
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    for g in J(row["grants"], []) if row else []:
        rank = level_rank.get(str(g.get("level")))
        if rank is None:
            continue
        scope = str(g.get("scope") or "own")
        if scope == "own":
            target = str(who.company_id) if who.company_id else None
        elif scope == "holding":
            target = str(holding) if holding else None
        elif scope == "all":
            target = "*"
        else:
            cid = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=scope)
            target = str(cid) if cid else None
        if target is None:
            continue
        grants[target] = max(grants.get(target, -1), min(rank, cap))
    meta = None
    if row and row.get("metadata_level"):
        meta = level_rank.get(str(row["metadata_level"]))
    return Clearance(everything=False, code=who.code, grants=grants, meta=meta, agent=True)


async def for_ask(tx: Tx, who: Principal) -> Clearance:
    """⟨1.7⟩ «از هاب بپرس» (contract §21.2, §23.9): records within the asker's
    clearance. The passages go to the Hub Librarian, a model, so the owner's
    own clearance is capped at the level marked `agents_max` here: a record
    above it (`secret`: encrypted, a passkey to view) never reaches a model or
    an ask's stored passages. An agent's clearance is capped already."""
    if who.is_agent:
        return await of_agent(tx, who)
    return Clearance(everything=False, grants={"*": await agents_max(tx)})


async def for_principal(tx: Tx, who: Principal) -> Clearance:
    if who.is_agent:
        return await apply(tx, await of_agent(tx, who))
    return await full(tx)
