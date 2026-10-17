"""Company registry cache (core.companies has no RLS: codes and names are
not tenant data). Companies are data: nothing here knows any code."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hq_api.db import Database
from hq_api.errors import ApiError


@dataclass(frozen=True)
class Company:
    id: UUID
    code: str
    kind: str
    status: str
    name_fa: str | None
    name_en: str | None
    color_index: int | None
    template: str | None
    version: int
    created_at: datetime


class Companies:
    def __init__(self, db: Database, ttl_s: float = 5.0) -> None:
        self._db = db
        self._ttl = ttl_s
        self._rows: list[Company] = []
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        self._loaded_at = 0.0

    async def all(self) -> list[Company]:
        if not self._rows or time.monotonic() - self._loaded_at > self._ttl:
            async with self._db.raw() as tx:
                rows = await tx.all(
                    """SELECT id, code, kind, status, name_fa, name_en, color_index, template,
                              version, created_at
                       FROM core.companies
                       ORDER BY kind = 'holding' DESC, code"""
                )
            self._rows = [Company(**r) for r in rows]
            self._loaded_at = time.monotonic()
        return self._rows

    async def ids(self) -> list[UUID]:
        return [c.id for c in await self.all()]

    async def find(self, code: str) -> Company | None:
        for c in await self.all():
            if c.code == code:
                return c
        self.invalidate()  # a company created a moment ago by another process
        for c in await self.all():
            if c.code == code:
                return c
        return None

    async def by_code(self, code: str) -> Company:
        c = await self.find(code)
        if c is None:
            raise ApiError(404, "not_found", f"company {code} not found")
        return c

    async def by_id(self, company_id: UUID) -> Company:
        for c in await self.all():
            if c.id == company_id:
                return c
        self.invalidate()
        for c in await self.all():
            if c.id == company_id:
                return c
        raise ApiError(404, "not_found", "company not found")

    async def holding(self) -> Company:
        for c in await self.all():
            if c.kind == "holding":
                return c
        raise ApiError(500, "internal_error", "no holding company")

    async def code_of(self, company_id: UUID) -> str:
        return (await self.by_id(company_id)).code
