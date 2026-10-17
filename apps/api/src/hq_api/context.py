"""Per-request context: who, which request, and the unit of work.

`ctx.tx()` opens one transaction scoped to what the principal may see
(owner and services: every company; an agent: its own company only).
Inside it, handlers write the change, `ctx.audit(...)` (always),
`ctx.interaction(...)` (owner actions) and `ctx.emit(...)` (events), so all
of them commit or roll back together.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, Request

from hq_api import audit, events, interactions
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.hub import Hub, get_hub
from hq_api.principal import Principal
from hq_api.security import deps


@dataclass
class Ctx:
    hub: Hub
    who: Principal
    request: Request

    @property
    def request_id(self) -> str:
        rid: str = getattr(self.request.state, "request_id", "") or str(uuid.uuid4())
        return rid

    async def scope(self) -> list[UUID]:
        if self.who.kind == "agent":
            assert self.who.company_id is not None
            return [self.who.company_id]
        return await self.hub.companies.ids()

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[Tx]:
        async with self.hub.db.tx(await self.scope()) as tx:
            yield tx

    async def audit(
        self,
        tx: Tx,
        *,
        company_id: UUID,
        action: str,
        action_class: str,
        target_kind: str,
        target_ref: str,
        summary: str = "",
        step_up: bool = False,
    ) -> None:
        await audit.record(
            tx,
            self.who,
            company_id=company_id,
            action=action,
            action_class=action_class,
            target_kind=target_kind,
            target_ref=target_ref,
            summary=summary,
            step_up=step_up,
            request_id=self.request_id,
            ip_hash=deps.ip_hash(self.request) if self.who.is_owner else None,
        )

    async def interaction(
        self,
        tx: Tx,
        *,
        company_id: UUID,
        kind: str,
        action: str,
        target_kind: str | None = None,
        target_ref: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        await interactions.record(
            tx,
            self.who,
            company_id=company_id,
            kind=kind,
            action=action,
            target_kind=target_kind,
            target_ref=target_ref,
            data=data,
            request_id=self.request_id,
        )

    async def emit(
        self,
        tx: Tx,
        company: str,
        type_: str,
        ref: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        await events.emit(tx, company, type_, ref, data)

    async def ensure_unlocked(self, tx: Tx, company_id: UUID) -> None:
        """Agents (and services acting for them) are refused while their company
        or the holding is locked; the owner is never locked out (contract §4, §9)."""
        if self.who.is_owner:
            return
        state = await tx.scalar("SELECT control.lock_state(:co)", co=company_id)
        if state is not None:
            raise ApiError(423, "company_locked", f"locked: {state}")


async def owner_ctx(
    request: Request, hub: Hub = Depends(get_hub), who: Principal = Depends(deps.owner)
) -> Ctx:
    return Ctx(hub=hub, who=who, request=request)


async def internal_ctx(
    request: Request, hub: Hub = Depends(get_hub), who: Principal = Depends(deps.internal)
) -> Ctx:
    return Ctx(hub=hub, who=who, request=request)
