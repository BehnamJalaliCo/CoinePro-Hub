"""Audit rows (contract §8): one per mutation, in the same transaction.

The chain (seq, prev_hash, hash) is computed by the database trigger. Only
references and a short summary are written, never a body or a secret.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.principal import Principal

SYSTEM = Principal(kind="service", code="system", role="system")


async def record(
    tx: Tx,
    actor: Principal,
    *,
    company_id: UUID,
    action: str,
    action_class: str,
    target_kind: str,
    target_ref: str,
    summary: str = "",
    step_up: bool = False,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> None:
    actor_kind = "system" if actor is SYSTEM else actor.kind
    await tx.exec(
        """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
               action_class, target_kind, target_ref, request_id, ip_hash, step_up, summary)
           VALUES (:ak, :ac, :pk, :co, :action, :cls, :tk, :tr, :rid, :ip, :su, :summary)""",
        ak=actor_kind,
        ac=actor.code,
        pk=actor_kind,
        co=company_id,
        action=action,
        cls=action_class,
        tk=target_kind,
        tr=target_ref[:200],
        rid=request_id,
        ip=ip_hash,
        su=step_up,
        summary=summary[:500],
    )


async def verify(tx: Tx, *, anchor_file: str | Path | None = None) -> dict[str, Any]:
    """The chain recomputed in Postgres, then compared with the last anchor
    kept outside it (a rewrite of every row *and* the head is caught there)."""
    row = dict(await tx.one("SELECT ok, checked, first_bad_seq FROM audit.verify_chain()"))
    row["anchor"] = "none"
    anchor = last_anchor(anchor_file)
    if anchor is not None:
        h = await tx.scalar("SELECT hash FROM audit.entries WHERE seq = :s", s=anchor["seq"])
        if h == anchor["hash"]:
            row["anchor"] = "ok"
        else:
            row.update(ok=False, anchor="mismatch")
            first = row["first_bad_seq"]
            row["first_bad_seq"] = anchor["seq"] if first is None else min(first, anchor["seq"])
    return row


def last_anchor(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    data = json.loads(lines[-1])
    return {"seq": int(data["seq"]), "hash": str(data["hash"])}


async def write_anchor(tx: Tx, path: str | Path) -> dict[str, Any]:
    """Append the chain head (seq, hash) to an append-only file outside
    Postgres (the backup set). Called by the nightly AuditVerify."""
    head = await tx.one(
        "SELECT last_seq AS seq, last_hash AS hash, now() AS at FROM audit.chain_head WHERE id = 1"
    )
    line = json.dumps({"seq": head["seq"], "hash": head["hash"], "at": head["at"].isoformat()})
    await asyncio.to_thread(_append, Path(path), line)
    return {"seq": head["seq"], "hash": head["hash"]}


def _append(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
