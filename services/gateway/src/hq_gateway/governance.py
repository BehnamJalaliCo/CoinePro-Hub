"""Prompt 11's governance tools of §4-§10 (agents/tools.md v1.5, contract
§20.11), each a call of the internal API with the run's own agent token.

    kpi.record       A2  a manual KPI's value, with its source (CEO or a manager)
    okr.draft        A1  the CEO's next-quarter OKR: one `okr` card for the owner
    okr.checkin      A2  a key result's check-in (every 14 days)
    outcome.note     A1  the proposer's note on a 30/60/90-day outcome review
    risk.raise       A1  a risk for the register
    risk.update      A2  the risk's owner or the keeper (QC); closing is the keeper's
    calendar.read    A0  the change calendar and its conflicts
    calendar.add     A2  a planned campaign, event or maintenance (the calendar never decides)
    authority.read   A0  the authority-matrix rows of the role's company
    governance.read  A0  the company's cards, OKRs, risks, outcome reviews, sealed charter

There is no tool that writes the charter or the authority matrix; nothing
here sends anything outside the hub.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from hq_gateway import tools as T

KEY = r"^[a-z][a-z0-9_.]{1,60}$"
QUARTER = r"^1[3-9][0-9]{2}-Q[1-4]$"


class SourceIn(T.In):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    ref: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=1000)


class KpiRecordIn(T.In):
    company: str = Field(pattern=T.CODE)
    key: str = Field(pattern=KEY)
    value: float = Field(allow_inf_nan=False)
    at: datetime
    source: SourceIn


class KeyResultIn(T.In):
    title_fa: str = Field(min_length=1, max_length=300)
    kpi: str | None = Field(default=None, pattern=KEY)
    metric_fa: str | None = Field(default=None, min_length=1, max_length=300)
    start: float = Field(allow_inf_nan=False)
    target: float = Field(allow_inf_nan=False)
    weight: float = Field(default=1, gt=0, le=100)


class ObjectiveIn(T.In):
    title_fa: str = Field(min_length=1, max_length=300)
    why_md: str = Field(default="", max_length=5000)
    key_results: list[KeyResultIn] = Field(min_length=1, max_length=5)


class OkrDraftIn(T.In):
    company: str = Field(pattern=T.CODE)
    quarter: str = Field(pattern=QUARTER)
    objectives: list[ObjectiveIn] = Field(min_length=1, max_length=5)


class OkrCheckinIn(T.In):
    key_result: str = Field(pattern=r"^KR-[0-9]{4,}$")
    confidence: float = Field(ge=0, le=1)
    note_md: str = Field(min_length=1, max_length=5000)
    evidence: list[SourceIn] = Field(default_factory=list, max_length=20)
    current: float | None = Field(default=None, allow_inf_nan=False)


class MeasuredIn(T.In):
    value: float = Field(allow_inf_nan=False)
    at: datetime
    source_ref: SourceIn


class OutcomeNoteIn(T.In):
    ref: str = Field(pattern=r"^OR-[0-9]{4,}$")
    note_md: str = Field(min_length=1, max_length=5000)
    measured: MeasuredIn | None = None


class LinksIn(T.In):
    finding: str | None = Field(default=None, pattern=r"^FI-[0-9]{4,}$")
    incident: str | None = Field(default=None, pattern=r"^I-[0-9]{4,}$")
    decision: str | None = Field(default=None, pattern=r"^D-[0-9]{4,}$")
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")


Category = Literal["product", "security", "data", "money", "people", "vendor", "ops", "reputation"]


class RiskRaiseIn(T.In):
    company: str = Field(pattern=T.CODE)
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(default="", max_length=20000)
    category: Category
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    links: LinksIn | None = None


class RiskUpdateIn(T.In):
    ref: str = Field(pattern=r"^RK-[0-9]{4,}$")
    version: int = Field(ge=1)
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation_md: str | None = Field(default=None, max_length=20000)
    status: Literal["open", "mitigating", "closed"] | None = None
    note: str = Field(min_length=1, max_length=2000)


class CalendarReadIn(T.In):
    company: str | None = Field(default=None, pattern=T.CODE)
    from_: datetime = Field(alias="from")
    to: datetime
    kind: (
        Literal["deploy", "campaign", "event", "maintenance", "meeting", "freeze", "holiday"] | None
    ) = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CalendarSourceIn(T.In):
    decision: str | None = Field(default=None, pattern=r"^D-[0-9]{4,}$")
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")
    meeting: str | None = Field(default=None, pattern=r"^MT-[0-9]{4,}$")
    order: str | None = Field(default=None, max_length=40)


class CalendarAddIn(T.In):
    company: str = Field(pattern=T.CODE)
    kind: Literal["campaign", "event", "maintenance"]
    title_fa: str = Field(min_length=1, max_length=300)
    starts_at: datetime
    ends_at: datetime
    source: CalendarSourceIn = Field(default_factory=CalendarSourceIn)
    risk: Literal["low", "medium", "high"] = "low"


class GovernanceReadIn(T.In):
    what: Literal["cards", "okr", "risks", "charter", "outcomes"]
    company: str | None = Field(default=None, pattern=T.CODE)


async def _post(
    api: T.Api, call: T.Call, tool: str, path: str, body: dict[str, object]
) -> T.Result:
    resp = await api.request(
        "POST", path, call.token, json=await T._text(body), idem=call.idem(tool)
    )
    return T.from_response(resp)


async def kpi_record(api: T.Api, call: T.Call, a: KpiRecordIn) -> T.Result:
    r = await _post(
        api, call, "kpi.record", "/internal/v1/governance/kpis/record", a.model_dump(mode="json")
    )
    if r.outcome == "ok":
        r.ref = f"kpi:{a.company}:{a.key}"
    return r


async def okr_draft(api: T.Api, call: T.Call, a: OkrDraftIn) -> T.Result:
    r = await _post(api, call, "okr.draft", "/internal/v1/governance/okr/draft",
                    a.model_dump(mode="json", exclude_none=True))  # fmt: skip
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = r.data.get("decision")
    return r


async def okr_checkin(api: T.Api, call: T.Call, a: OkrCheckinIn) -> T.Result:
    r = await _post(api, call, "okr.checkin", "/internal/v1/governance/okr/checkin",
                    a.model_dump(mode="json", exclude_none=True))  # fmt: skip
    if r.outcome == "ok":
        r.ref = a.key_result
    return r


async def outcome_note(api: T.Api, call: T.Call, a: OutcomeNoteIn) -> T.Result:
    r = await _post(api, call, "outcome.note", "/internal/v1/governance/outcomes/note",
                    a.model_dump(mode="json", exclude_none=True))  # fmt: skip
    if r.outcome == "ok":
        r.ref = a.ref
    return r


async def risk_raise(api: T.Api, call: T.Call, a: RiskRaiseIn) -> T.Result:
    return await _post(api, call, "risk.raise", "/internal/v1/governance/risks",
                       a.model_dump(mode="json", exclude_none=True))  # fmt: skip


async def risk_update(api: T.Api, call: T.Call, a: RiskUpdateIn) -> T.Result:
    return await _post(api, call, "risk.update", "/internal/v1/governance/risks/update",
                       a.model_dump(mode="json", exclude_none=True))  # fmt: skip


async def calendar_read(api: T.Api, call: T.Call, a: CalendarReadIn) -> T.Result:
    params = {
        "company": a.company,
        "from": a.from_.isoformat(),
        "to": a.to.isoformat(),
        "kind": a.kind,
    }
    resp = await api.request("GET", "/internal/v1/governance/calendar", call.token, params=params)
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = f"calendar:{a.company or call.gate.get('company')}"
    return r


async def calendar_add(api: T.Api, call: T.Call, a: CalendarAddIn) -> T.Result:
    return await _post(api, call, "calendar.add", "/internal/v1/governance/calendar",
                       a.model_dump(mode="json", exclude_none=True))  # fmt: skip


async def authority_read(api: T.Api, call: T.Call, a: T.Empty) -> T.Result:
    resp = await api.request("GET", "/internal/v1/governance/authority", call.token)
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = "authority"
    return r


async def governance_read(api: T.Api, call: T.Call, a: GovernanceReadIn) -> T.Result:
    resp = await api.request(
        "GET",
        "/internal/v1/governance/read",
        call.token,
        params={"what": a.what, "company": a.company},
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = f"governance:{a.what}:{a.company or call.gate.get('company')}"
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "kpi.record": (KpiRecordIn, kpi_record),
    "okr.draft": (OkrDraftIn, okr_draft),
    "okr.checkin": (OkrCheckinIn, okr_checkin),
    "outcome.note": (OutcomeNoteIn, outcome_note),
    "risk.raise": (RiskRaiseIn, risk_raise),
    "risk.update": (RiskUpdateIn, risk_update),
    "calendar.read": (CalendarReadIn, calendar_read),
    "calendar.add": (CalendarAddIn, calendar_add),
    "authority.read": (T.Empty, authority_read),
    "governance.read": (GovernanceReadIn, governance_read),
}
T.TOOLS.update(TOOLS)
