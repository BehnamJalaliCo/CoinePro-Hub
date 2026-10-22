"""Stars, lessons, stories and the CEOs' hire decisions (agents/tools.md v2;
contract §18.4, §18.11, §18.12; prompt 08 §4, §8, §9).

    star.rubric   A2  CEO: the company's star rubric (an efficiency criterion >= 15%)
    star.give     A2  CEO: one employee's weekly stars (no evidence: not counted)
    star.audit    A2  overseer: a star counted or not, with the reason
    lesson.write  A1  overseer, AI Ops head: a lesson from the best company
    story.post    A1  CEOs and holding heads: a story (3 a day per company)
    hire.decide   A2  CEO: a hire card it is the approver of (delegated hiring)

The api decides who may (OPA hq.internal, people.rego); every text leaves
redacted. Registered with the gateway's tools on import (gateway.py).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator

from hq_gateway import tools as T

DECISION_REF = r"^D-[0-9]{6,}$"
PERIOD = r"^(week|month):[0-9]{4}-[0-9]{2}(-[0-9]{2})?$"


class CriterionIn(T.In):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    name_fa: str = Field(min_length=1, max_length=100)
    weight: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    description_md: str = Field(default="", max_length=2000)


class RubricIn(T.In):
    criteria: list[CriterionIn] = Field(min_length=1, max_length=12)
    rules_md: str = Field(default="", max_length=10000)


class StarEvidenceIn(T.In):
    kind: str = Field(min_length=1, max_length=20)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=500)


def _half_step(v: Decimal) -> Decimal:
    # Whole or half stars, 0 to 5 (contract §18.15): 3.7 is refused here, by field.
    if not (0 <= v <= 5) or (v * 2) != (v * 2).to_integral_value():
        raise ValueError("whole or half stars: 0, 0.5, … 5")
    return v


class StarGiveIn(T.In):
    employee: str = Field(pattern=T.EMP)
    week: date
    stars: Decimal = Field(ge=0, le=5, max_digits=2, decimal_places=1)
    criteria: dict[str, Decimal] = Field(default_factory=dict, max_length=12)
    reason_md: str = Field(default="", max_length=4000)
    evidence: list[StarEvidenceIn] = Field(default_factory=list, max_length=20)

    @field_validator("stars")
    @classmethod
    def _stars(cls, v: Decimal) -> Decimal:
        return _half_step(v)

    @field_validator("criteria")
    @classmethod
    def _criteria(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        for value in v.values():
            _half_step(value)
        return v


class StarAuditIn(T.In):
    star_id: str = Field(pattern=T.UUID_RE)
    counted: bool
    note: str = Field(min_length=1, max_length=2000)


class LessonIn(T.In):
    source_company: str = Field(pattern=T.CODE)
    period: str = Field(pattern=PERIOD)
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=20000)
    evidence: list[StarEvidenceIn] = Field(default_factory=list, max_length=20)


class FigureIn(T.In):
    label_fa: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=16)


class StoryLinksIn(T.In):
    employee: str | None = Field(default=None, pattern=T.EMP)
    deliverable: str | None = Field(default=None, pattern=r"^O-[0-9]{6,}$")
    decision: str | None = Field(default=None, pattern=DECISION_REF)
    work: str | None = Field(default=None, pattern=T.WORK_REF)
    period: str | None = Field(default=None, pattern=PERIOD)
    metric: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")  # a KPI by name


class StoryIn(T.In):
    kind: Literal["post", "milestone"]
    title_fa: str = Field(min_length=1, max_length=60)
    body_fa: str = Field(default="", max_length=280)
    figures: list[FigureIn] = Field(default_factory=list, max_length=3)
    file_id: str | None = Field(default=None, pattern=T.UUID_RE)
    links: StoryLinksIn = Field(default_factory=StoryLinksIn)


class HireDecideIn(T.In):
    ref: str = Field(pattern=DECISION_REF)
    verdict: Literal["approve", "reject", "return"]
    note: str | None = Field(default=None, max_length=5000)


async def _post(call: T.Call, api: T.Api, tool: str, path: str, body: dict[str, Any]) -> T.Result:
    resp = await api.request("POST", path, call.token, json=body, idem=call.idem(tool))
    return T.from_response(resp, None)


async def star_rubric(api: T.Api, call: T.Call, a: RubricIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json"))
    r = await _post(call, api, "star.rubric", "/internal/v1/stars/rubric", body)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"rubric:{r.data.get('company')}@{r.data.get('version')}"
    return r


async def star_give(api: T.Api, call: T.Call, a: StarGiveIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json"))
    r = await _post(call, api, "star.give", "/internal/v1/stars", body)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"star:{r.data.get('id')}"
        r.data = {k: r.data.get(k) for k in ("id", "employee", "week", "stars", "counted")}
    return r


async def star_audit(api: T.Api, call: T.Call, a: StarAuditIn) -> T.Result:
    r = await _post(
        call,
        api,
        "star.audit",
        f"/internal/v1/stars/{a.star_id}/audit",
        {"counted": a.counted, "note": await T._text(a.note)},
    )
    if r.outcome == "ok":
        r.ref = f"star:{a.star_id}"
    return r


async def lesson_write(api: T.Api, call: T.Call, a: LessonIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json"))
    r = await _post(call, api, "lesson.write", "/internal/v1/lessons", body)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "") or None
    return r


async def story_post(api: T.Api, call: T.Call, a: StoryIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True))
    r = await _post(call, api, "story.post", "/internal/v1/stories", body)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "") or None
        r.data = {k: r.data.get(k) for k in ("ref", "kind", "title_fa", "expires_at")}
    return r


async def hire_decide(api: T.Api, call: T.Call, a: HireDecideIn) -> T.Result:
    r = await _post(
        call,
        api,
        "hire.decide",
        f"/internal/v1/hires/{a.ref}/decide",
        {"verdict": a.verdict, "note": await T._text(a.note) if a.note else None},
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = a.ref
        r.data = {k: r.data.get(k) for k in ("ref", "status", "resolution")}
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "star.rubric": (RubricIn, star_rubric),
    "star.give": (StarGiveIn, star_give),
    "star.audit": (StarAuditIn, star_audit),
    "lesson.write": (LessonIn, lesson_write),
    "story.post": (StoryIn, story_post),
    "hire.decide": (HireDecideIn, hire_decide),
}

# Registered with the gateway's tools (tools.py itself knows nothing of these).
T.TOOLS.update(TOOLS)
