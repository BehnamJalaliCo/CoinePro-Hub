"""⟨1.11⟩ Prompt 21 part 3 (contract §29.11-§29.13): the working groups' tools.

    group.plan (A1)        {group?, company?, items?: [{seat, title_fa, series?, why_fa?}],
                           note_fa?, suggestion?: {title_fa, why_fa, impact_fa, cost_fa,
                           impact, cost}}: the content lead's plan of the day and,
                           optionally, one suggestion for the owner's home. The
                           content lead (media_director) or the CEO of the company.
    experiment.write (A1)  {group?, company?, week?, hypothesis_fa?, metric?, target?,
                           baseline?, result?, kept?, note_fa?}: the week's experiment
                           of the company, and its close with the figure. The content
                           analyst or the content lead.
    connection.read (A0)   {company?, kind?, days?}: the company's connections (the ten
                           kinds), their state and daily figures (never a secret:
                           only set/missing). Any agent for its own company; the
                           holding's readers for any.

Text leaves redacted (no personal data, no secret, no internal ref).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

CODE = r"^[A-Z][A-Z0-9]{1,9}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"
Kind = Literal[
    "search_console", "ga4", "instagram", "telegram", "youtube", "x", "pagespeed", "trends",
    "bing", "play_console",
]  # fmt: skip


class PlanItemIn(T.In):
    seat: str = Field(pattern=KEY)
    title_fa: str = Field(min_length=1, max_length=300)
    series: str | None = Field(default=None, max_length=40)
    why_fa: str | None = Field(default=None, max_length=1000)


class SuggestionIn(T.In):
    title_fa: str = Field(min_length=3, max_length=300)
    why_fa: str = Field(default="", max_length=1000)
    impact_fa: str = Field(default="", max_length=300)
    cost_fa: str = Field(default="", max_length=300)
    impact: int = Field(default=3, ge=1, le=5)
    cost: int = Field(default=2, ge=1, le=5)


class GroupPlanIn(T.In):
    group: str = Field(default="content", pattern=KEY)
    company: str | None = Field(default=None, pattern=CODE)
    items: list[PlanItemIn] = Field(default_factory=list, max_length=10)
    note_fa: str | None = Field(default=None, max_length=2000)
    suggestion: SuggestionIn | None = None


class ExperimentIn(T.In):
    group: str = Field(default="content", pattern=KEY)
    company: str | None = Field(default=None, pattern=CODE)
    week: date | None = None
    hypothesis_fa: str | None = Field(default=None, min_length=3, max_length=1000)
    metric: str | None = Field(default=None, pattern=KEY)
    target: float | None = None
    baseline: float | None = None
    result: float | None = None
    kept: bool | None = None
    note_fa: str | None = Field(default=None, max_length=1000)


class ConnectionReadIn(T.In):
    company: str | None = Field(default=None, pattern=CODE)
    kind: Kind | None = None
    days: int = Field(default=7, ge=1, le=60)


async def group_plan(api: T.Api, call: T.Call, a: GroupPlanIn) -> T.Result:
    body: dict[str, Any] = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request(
        "POST", "/internal/v1/groups/plan", call.token, json=body, idem=call.idem("group.plan")
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"group:{r.data.get('group')}:{r.data.get('company')}"
    return r


async def experiment_write(api: T.Api, call: T.Call, a: ExperimentIn) -> T.Result:
    body: dict[str, Any] = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request(
        "POST",
        "/internal/v1/experiments",
        call.token,
        json=body,
        idem=call.idem("experiment.write"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"experiment:{r.data.get('id')}"
    return r


async def connection_read(api: T.Api, call: T.Call, a: ConnectionReadIn) -> T.Result:
    params = {k: v for k, v in a.model_dump(mode="json").items() if v is not None}
    return T.from_response(
        await api.request("GET", "/internal/v1/connections", call.token, params=params), None
    )


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "group.plan": (GroupPlanIn, group_plan),
    "experiment.write": (ExperimentIn, experiment_write),
    "connection.read": (ConnectionReadIn, connection_read),
}
T.TOOLS.update(TOOLS)
