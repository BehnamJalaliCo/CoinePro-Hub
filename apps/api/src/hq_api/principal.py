"""Who is calling (contract §2): the owner, an agent (one employee in one
company, minted per run by the agent runtime) or an internal service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

Kind = Literal["owner", "agent", "service"]


@dataclass(frozen=True)
class Principal:
    kind: Kind
    code: str  # "owner" | employee code (TY-CEO) | service name
    role: str  # owner | ceo | manager | employee | advisor | inspector | system | service
    company: str | None = None
    company_id: UUID | None = None
    department: str | None = None
    department_id: UUID | None = None
    employee_id: UUID | None = None
    status: str | None = None
    session_id: UUID | None = None
    via_cookie: bool = False
    run_id: str | None = None
    charter: str | None = None  # agents/roles/<charter>.md (agents only)
    # "holding": a holding-level role whose charter reads every company
    # (oversight, AI operations, the advisor); else "company".
    scope: str = "company"

    @property
    def is_owner(self) -> bool:
        return self.kind == "owner"

    @property
    def is_agent(self) -> bool:
        return self.kind == "agent"

    def actor(self) -> dict[str, str]:
        return {"kind": self.kind, "code": self.code}

    def opa(self) -> dict[str, Any]:
        """The principal as OPA expects it (infra/opa/README.md)."""
        return {
            "kind": self.kind,
            "code": self.code,
            "role": self.role,
            "company": self.company,
            "department": self.department,
            "status": self.status,
            "scope": self.scope,
        }


OWNER_CODE = "owner"
