"""owner.interactions (contract §0 rule 5, §1.8): every owner action, the raw
material of the digital CEO. References and small fields only."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.principal import Principal


async def record(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    kind: str,
    action: str,
    target_kind: str | None = None,
    target_ref: str | None = None,
    data: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    if not who.is_owner:
        return
    await tx.exec(
        """INSERT INTO owner.interactions (company_id, kind, action, target_kind, target_ref, data,
               request_id)
           VALUES (:co, :kind, :action, :tk, :tr, CAST(:data AS jsonb), :rid)""",
        co=company_id,
        kind=kind,
        action=action,
        tk=target_kind,
        tr=target_ref,
        data=json.dumps(data or {}, default=str, ensure_ascii=False),
        rid=request_id,
    )
