"""Roles written on demand (prompt 13 §1.1, contract §22.5, agents/tools.md):

    role.draft   A1  a department manager writes a role the work needs
    role.decide  A2  a CEO approves a draft of its own company (delegated hiring)

The ceiling (tools, model, limits, at least three eval cases) is the api's,
by code (422 names each field); every text leaves redacted. The overseer
reviews a draft with skill.review and its RD- ref (tools.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T

DRAFT_REF = r"^RD-[0-9]{4,8}$"
ROLE = r"^[a-z][a-z0-9_]{1,40}$"


class LimitsIn(T.In):
    steps_per_run: int = Field(ge=1, le=50)
    tokens_per_step: int = Field(ge=1000, le=200_000)
    tokens_per_run: int = Field(ge=1000, le=2_000_000)


class EvalCaseIn(T.In):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
    input_md: str = Field(min_length=1, max_length=1500)
    rubric_md: str = Field(min_length=1, max_length=800)
    weight: float = Field(default=1.0, gt=0, le=10)


class RoleDraftIn(T.In):
    # The draft the work item names (the owner's request, or one sent back);
    # without it, the one this run's work item is for, else a new one.
    ref: str | None = Field(default=None, pattern=DRAFT_REF)
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    role: str = Field(pattern=ROLE)
    title_fa: str = Field(min_length=1, max_length=120)
    title_en: str = Field(min_length=1, max_length=120)
    why_md: str = Field(min_length=1, max_length=10000)
    compared: list[str] = Field(default_factory=list, max_length=30)
    charter_md: str = Field(min_length=1, max_length=20000)
    tools: list[str] = Field(min_length=1, max_length=80)
    model: str = Field(min_length=3, max_length=100)
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    limits: LimitsIn
    eval_cases: list[EvalCaseIn] = Field(default_factory=list, max_length=10)


class RoleDecideIn(T.In):
    ref: str = Field(pattern=DRAFT_REF)
    verdict: Literal["approve", "reject", "return"]
    note: str | None = Field(default=None, max_length=5000)


async def role_draft(api: T.Api, call: T.Call, a: RoleDraftIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request(
        "POST", "/internal/v1/roles/drafts", call.token, json=body, idem=call.idem("role.draft")
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "")
    return r


async def role_decide(api: T.Api, call: T.Call, a: RoleDecideIn) -> T.Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/roles/drafts/{a.ref}/decide",
        call.token,
        json={"verdict": a.verdict, "note": await T._text(a.note) if a.note else None},
        idem=call.idem("role.decide"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = a.ref
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "role.draft": (RoleDraftIn, role_draft),
    "role.decide": (RoleDecideIn, role_decide),
}
T.TOOLS.update(TOOLS)
