"""The Chief Overseer's tools (prompt 08 §2, agents/tools.md v2): findings,
protocol results, challenges, holds, the kill switch and the deploy freeze.

Each one is a thin call to the api's internal oversight routes, which decide
who may (OPA) and keep the records; outgoing text is redacted on the way.
Releasing a hold, a kill switch or a freeze has no tool: it is the owner's.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

CO = r"^[A-Z][A-Z0-9]{1,9}$"
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
Severity = Literal["info", "low", "medium", "high", "critical"]


class EvidenceIn(T.In):
    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=1000)


class FixIn(T.In):
    kind: Literal["work", "workshop", "decision"]
    ref: str | None = Field(default=None, max_length=40, pattern=r"^[A-Z]{1,4}-[0-9]{4,}$")
    summary_fa: str | None = Field(default=None, max_length=1000)


class FindingRaiseIn(T.In):
    company: str = Field(pattern=CO)
    protocol: str | None = Field(default=None, pattern=r"^PR-[0-9]{3,}$")
    severity: Severity
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(default="", max_length=20000)
    evidence: list[EvidenceIn] = Field(default_factory=list, max_length=20)
    answerable: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]{2,64}$")
    due_in_hours: int | None = Field(default=None, ge=1, le=720)
    # ⟨1.10⟩ §28.3 the watch's kind and the proposed fix (in words; and as a
    # work item, a Code Workshop session or a card, for the owner's seal)
    kind: Literal["security", "app_health", "code", "growth", "holding"] | None = None
    fix_md: str | None = Field(default=None, max_length=20000)
    fix: FixIn | None = None


class FindingUpdateIn(T.In):
    ref: str = Field(pattern=r"^FI-[0-9]{4,}$")
    status: Literal["acknowledged", "fixing", "fixed", "disputed", "verified", "closed"]
    note: str = Field(default="", max_length=5000)
    evidence: list[EvidenceIn] = Field(default_factory=list, max_length=20)


class OutcomeVerdictIn(T.In):
    ref: str = Field(pattern=r"^OR-[0-9]{4,}$")
    verdict: Literal["met", "partly", "missed", "unmeasurable"]
    note_md: str = Field(min_length=1, max_length=5000)


class ProtocolResultIn(T.In):
    protocol: str = Field(pattern=r"^PR-[0-9]{3,}$")
    result: Literal["pass", "fail", "partial"]
    findings: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=20000)
    # ⟨1.5⟩ prompt 11 §6.3: PR-006's verdicts on answered outcome reviews
    outcomes: list[OutcomeVerdictIn] = Field(default_factory=list, max_length=50)


class CriterionIn(T.In):
    name_fa: str = Field(min_length=1, max_length=200)
    weight: float = Field(ge=0, le=100)


class ChallengeIssueIn(T.In):
    company: str = Field(pattern=CO)
    period: Literal["week", "month"] = "week"
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=20000)
    criteria: list[CriterionIn] = Field(default_factory=list, max_length=10)
    due_at: datetime
    judge: str | None = Field(default=None, pattern=EMP)


class ChallengeSubmitIn(T.In):
    ref: str = Field(pattern=r"^CH-[0-9]{4,}$")
    work_ref: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")
    note: str = Field(default="", max_length=5000)


class ChallengeScoreIn(T.In):
    ref: str = Field(pattern=r"^CH-[0-9]{4,}$")
    score: int = Field(ge=0, le=100)
    notes: str = Field(default="", max_length=5000)


class HoldTargetIn(T.In):
    kind: Literal["decision", "session", "work", "employee", "tool", "story"]
    ref: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")


class HoldIn(T.In):
    target: HoldTargetIn
    reason_md: str = Field(min_length=1, max_length=5000)


class EngageIn(T.In):
    scope: str = Field(pattern=r"^company:[A-Z][A-Z0-9]{1,9}$")
    reason: str = Field(min_length=1, max_length=1000)


class FreezeIn(T.In):
    company: str = Field(pattern=CO)
    until: datetime
    reason: str = Field(min_length=1, max_length=1000)


def _compact(data: Any, keys: tuple[str, ...]) -> Any:
    return {k: data.get(k) for k in keys} if isinstance(data, dict) else data


async def _post(
    api: T.Api, call: T.Call, tool: str, path: str, body: dict[str, Any], keys: tuple[str, ...]
) -> T.Result:
    resp = await api.request(
        "POST", path, call.token, json=await T._text(body), idem=call.idem(tool)
    )
    r = T.from_response(resp)
    if r.outcome == "ok":
        r.data = _compact(r.data, keys)
    return r


FINDING = ("ref", "company", "severity", "status", "answerable", "due_at")


async def finding_raise(api: T.Api, call: T.Call, a: FindingRaiseIn) -> T.Result:
    return await _post(
        api,
        call,
        "finding.raise",
        "/internal/v1/oversight/findings",
        a.model_dump(mode="json", exclude_none=True),
        FINDING,
    )


async def finding_update(api: T.Api, call: T.Call, a: FindingUpdateIn) -> T.Result:
    body = a.model_dump(mode="json", exclude={"ref"})
    return await _post(
        api,
        call,
        "finding.update",
        f"/internal/v1/oversight/findings/{a.ref}/status",
        body,
        FINDING,
    )


async def protocol_result(api: T.Api, call: T.Call, a: ProtocolResultIn) -> T.Result:
    r = await _post(
        api, call, "protocol.result", "/internal/v1/oversight/protocol-runs/result",
        a.model_dump(mode="json"), ("protocol", "result", "findings", "finished_at"),
    )  # fmt: skip
    if r.outcome == "ok":
        r.ref = f"protocol:{a.protocol}"
    return r


CHALLENGE = ("ref", "company", "period", "status", "due_at", "score")


async def challenge_issue(api: T.Api, call: T.Call, a: ChallengeIssueIn) -> T.Result:
    return await _post(
        api,
        call,
        "challenge.issue",
        "/internal/v1/oversight/challenges",
        a.model_dump(mode="json", exclude_none=True),
        CHALLENGE,
    )


async def challenge_submit(api: T.Api, call: T.Call, a: ChallengeSubmitIn) -> T.Result:
    body = a.model_dump(mode="json", exclude={"ref"}, exclude_none=True)
    return await _post(
        api,
        call,
        "challenge.submit",
        f"/internal/v1/oversight/challenges/{a.ref}/submit",
        body,
        CHALLENGE,
    )


async def challenge_score(api: T.Api, call: T.Call, a: ChallengeScoreIn) -> T.Result:
    body = a.model_dump(mode="json", exclude={"ref"})
    return await _post(
        api,
        call,
        "challenge.score",
        f"/internal/v1/oversight/challenges/{a.ref}/score",
        body,
        CHALLENGE,
    )


async def hold(api: T.Api, call: T.Call, a: HoldIn) -> T.Result:
    return await _post(
        api,
        call,
        "hold",
        "/internal/v1/oversight/holds",
        a.model_dump(mode="json"),
        ("ref", "company", "state", "action"),
    )


CONTROL = ("holding", "companies")


async def kill_switch_engage(api: T.Api, call: T.Call, a: EngageIn) -> T.Result:
    r = await _post(
        api,
        call,
        "kill_switch.engage",
        "/internal/v1/oversight/kill-switch",
        a.model_dump(mode="json"),
        CONTROL,
    )
    if r.outcome == "ok":
        r.ref = a.scope
        r.data = {"engaged": a.scope}
    return r


async def deploy_freeze(api: T.Api, call: T.Call, a: FreezeIn) -> T.Result:
    r = await _post(
        api,
        call,
        "deploy.freeze",
        "/internal/v1/oversight/deploy-freeze",
        a.model_dump(mode="json"),
        CONTROL,
    )
    if r.outcome == "ok":
        r.ref = f"freeze:{a.company}"
        r.data = {"frozen": a.company, "until": a.until.isoformat()}
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "finding.raise": (FindingRaiseIn, finding_raise),
    "finding.update": (FindingUpdateIn, finding_update),
    "protocol.result": (ProtocolResultIn, protocol_result),
    "challenge.issue": (ChallengeIssueIn, challenge_issue),
    "challenge.submit": (ChallengeSubmitIn, challenge_submit),
    "challenge.score": (ChallengeScoreIn, challenge_score),
    "hold": (HoldIn, hold),
    "kill_switch.engage": (EngageIn, kill_switch_engage),
    "deploy.freeze": (FreezeIn, deploy_freeze),
}
T.TOOLS.update(TOOLS)
