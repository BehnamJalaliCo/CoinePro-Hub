"""Response and request models shared across areas (contract §3–§5)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CODE = r"^[A-Z][A-Z0-9]{1,9}$"
DEPT_CODE = r"^[A-Z][A-Z0-9]{1,11}$"
EMPLOYEE_CODE = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class Actor(BaseModel):
    kind: Literal["owner", "agent", "service", "system"]
    code: str
    display_fa: str | None = None


class EmployeeRef(BaseModel):
    code: str
    title_fa: str
    kind: str
    company: str
    department: str | None = None


class Evidence(Model):
    kind: Literal["deliverable", "link", "metric", "log"]
    ref: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class Budget(BaseModel):
    tokens: int | None
    usd: Decimal | None
    tokens_used: int
    usd_used: Decimal


class Escrow(BaseModel):
    allowed_action_classes: list[str]
    token_cap_per_run: int
    usd_cap_per_month: Decimal
    expires_at: datetime
    status: str
    approved_by: Actor | None
    decision: str | None


class Schedule(BaseModel):
    rrule: str
    timezone: str
    next_at: datetime | None
    status: str


class ModelChoice(BaseModel):
    connection: str | None
    model: str | None
    effort: str | None


class Score(BaseModel):
    value: float | None
    owner_avg: float | None
    rank_in_department: int | None
    trend: list[float | None]


class FileVariants(BaseModel):
    thumb: UUID | None = None
    poster: UUID | None = None


class FileRef(BaseModel):
    """A stored file (contract §17.1, ⟨1.3⟩ adds kind … transcript)."""

    id: UUID
    name: str
    mime: str
    size: int
    sha256: str
    kind: Literal["image", "video", "audio", "document"] = "document"
    status: Literal["processing", "ready", "failed"] = "ready"
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    variants: FileVariants = Field(default_factory=FileVariants)
    transcript: str | None = None


class Deleted(BaseModel):
    ok: bool = True


def actor(kind: str | None, code: str | None) -> Actor | None:
    if not kind or not code:
        return None
    display = (
        "مدیر کل" if kind == "owner" else ("سامانه" if kind in ("system", "service") else None)
    )
    return Actor.model_validate({"kind": kind, "code": code, "display_fa": display})


def employee_ref(row: dict[str, Any] | None, prefix: str = "") -> EmployeeRef | None:
    """EmployeeRef from a row with columns <prefix>code, <prefix>title_fa, ..."""
    if row is None or not row.get(f"{prefix}code"):
        return None
    return EmployeeRef(
        code=row[f"{prefix}code"],
        title_fa=row[f"{prefix}title_fa"],
        kind=row[f"{prefix}kind"],
        company=row[f"{prefix}company"],
        department=row.get(f"{prefix}department"),
    )
