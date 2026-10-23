"""Small helpers shared by the archive modules."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal

SERVICE = Principal(kind="service", code="archive", role="service")
OWNER = Principal(kind="owner", code="owner", role="owner")
STATES = ("draft", "filed", "sealed", "superseded", "disposed")
LIVE = ("filed", "sealed", "superseded")  # records retention and reminders read


def J(v: Any, default: Any = None) -> Any:
    """A jsonb column as Python: decoded already (the driver's codec), or its
    text; a decoded JSON string ("permanent", "owner") stays what it is."""
    if v is None:
        return default
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def dumps(v: Any) -> str:
    def enc(o: Any) -> Any:
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, (UUID, Decimal)):
            return str(o)
        raise TypeError(type(o).__name__)

    return json.dumps(v, ensure_ascii=False, default=enc)


def invalid(fields: dict[str, str], detail: str | None = None) -> ApiError:
    return ApiError(422, "schema_invalid", detail, fields=fields)


async def holding(tx: Tx) -> dict[str, Any]:
    row = await tx.first(
        "SELECT id, code FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    if row is None:
        raise ApiError(409, "not_ready", "no holding yet")
    return row


async def company(tx: Tx, code: str) -> dict[str, Any]:
    row = await tx.first(
        "SELECT id, code, kind, name_fa FROM core.companies WHERE code = :c", c=code
    )
    if row is None:
        raise invalid({"scope": "unknown company"})
    return row


def wide_txf(hub: Any) -> Any:
    """A factory of transactions over every company, with the full clearance
    (the hub's own rule-only work and the owner's after-commit steps)."""

    class _Tx:
        async def __aenter__(self) -> Tx:
            self._cm = hub.db.tx(await hub.companies.ids())
            tx: Tx = await self._cm.__aenter__()
            await tx.exec("SELECT set_config('app.clearance', '{\"all\": true}', true)")
            return tx

        async def __aexit__(self, *exc: Any) -> Any:
            return await self._cm.__aexit__(*exc)

    return lambda: _Tx()


def actor_of(who: Principal) -> tuple[str, str]:
    kind = who.kind if who.kind in ("owner", "agent", "service") else "system"
    return kind, (who.code or "system")[:64]
