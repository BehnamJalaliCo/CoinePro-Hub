"""The API shapes of a session (contract §35.2), kept apart from the logic so that the order
report (domain.order_report) can carry them without a circular import."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Badge = Literal["your_turn", "ready", "stuck", "moving", "closed"]


class Holder(BaseModel):
    code: str
    title_fa: str
    company: str
    company_fa: str


class Participant(BaseModel):
    key: str
    kind: Literal["holder", "person", "player"]
    title_fa: str
    company: str | None = None


class SessionTask(BaseModel):
    id: UUID
    n: int
    title_fa: str
    state: Literal["todo", "doing", "done", "dropped"]
    by: Literal["owner", "agent"]
    who_fa: str | None = None
    work_ref: str | None = None


class TaskCount(BaseModel):
    done: int
    total: int


class Brief(BaseModel):
    done_fa: str
    now_fa: str
    need_fa: str


class SessionState(BaseModel):
    state: Literal["open", "closed"]
    badge: Badge
    reason_fa: str
    closed_at: datetime | None = None
    hidden: bool = False
    # ⟨1.22⟩ §40.3 the playbook this session was opened from (PB-…), or null
    source: str | None = None
    # ⟨1.36⟩ §58.2 a closed session: the playbook it left in the library (PB-…) and the one line
    # «کارگروه این جلسه در کتابخانه ماند»; null while open or when it left none
    playbook_kept: str | None = None
    playbook_kept_fa: str | None = None


class SessionCard(BaseModel):
    ref: str
    conversation_ref: str | None
    title_fa: str
    holder: Holder | None
    badge: Badge
    reason_fa: str
    brief: Brief
    pace: Literal["auto", "step"]
    participants: list[Participant] = Field(default_factory=list)
    tasks: TaskCount
    opened_at: datetime
    last_at: datetime
    closed_at: datetime | None = None
    hidden: bool = False
    # ⟨1.22⟩ §40.3 the playbook this session was opened from (PB-…), or null
    source: str | None = None
    # ⟨1.36⟩ §58.2 as SessionState's
    playbook_kept: str | None = None
    playbook_kept_fa: str | None = None
