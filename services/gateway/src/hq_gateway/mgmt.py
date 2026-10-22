"""Management tools, part B (prompt 12 §12, agents/tools.md v1.5):
`claim.verdict`, the fact check of one claim in a deliverable (A2: the fact
checker, the overseer and QC; the api's policy decides who). The claim and
the evidence notes are redacted on the way; `refuted` needs evidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T


class ClaimEvidenceIn(T.In):
    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=1000)


class ClaimVerdictIn(T.In):
    deliverable: str = Field(pattern=r"^O-[0-9]+$")
    claim_md: str = Field(min_length=1, max_length=2000)
    verdict: Literal["confirmed", "refuted", "unverifiable"]
    evidence: list[ClaimEvidenceIn] = Field(default_factory=list, max_length=20)
    protocol: str | None = Field(default=None, pattern=r"^PR-[0-9]{3,}$")


async def claim_verdict(api: T.Api, call: T.Call, a: ClaimVerdictIn) -> T.Result:
    if a.verdict == "refuted" and not a.evidence:
        return T.Result(
            "error",
            code="validation_failed",
            fields={"evidence": "a refuted claim needs evidence"},
            hint_fa="ادعای رد شده بدون شاهد ثبت نمیشود.",
        )
    body = await T._text(a.model_dump(mode="json", exclude_none=True))
    resp = await api.request(
        "POST",
        "/internal/v1/claims",
        call.token,
        json=body,
        idem=call.idem(f"claim.verdict:{a.deliverable}"),
    )
    r = T.from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {k: r.data.get(k) for k in ("ref", "deliverable", "employee", "verdict", "at")}
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "claim.verdict": (ClaimVerdictIn, claim_verdict),
}
T.TOOLS.update(TOOLS)
