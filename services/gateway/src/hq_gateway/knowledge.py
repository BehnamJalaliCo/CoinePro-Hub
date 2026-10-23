"""The four-layer knowledge base's agent tools (agents/tools.md v1.5
"Governance", contract §20.3; prompt 11 §3, §11). Reading is `knowledge.search`
(tools.py, kind `knowledge`); these are the writes of the approval cycle
draft -> in_review -> review -> approved.

    knowledge.propose  A1  an entry or a new version (`ref`): at least one source
                           and an expiry within the kind's limit (the api: 422)
    knowledge.review   A2  the overseer's or AI Safety's review, all four checks
    knowledge.approve  A2  a CEO approves an entry of its own company after a
                           passing review (an authority-matrix row the owner may
                           take back); holding entries are the owner's cards

The employee layer is the employee's memory (memory.write) and support articles
are kb.propose's (prompt 10): neither is proposed here. Who may is the api's
(OPA, RLS); every text an agent writes leaves redacted, and every write carries
its Idempotency-Key. Registered with the gateway's tools on import (gateway.py).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt

from hq_gateway import tools as T
from hq_gateway.meetings import CODE, KREF, SourceIn, sources_out


class ProposeIn(T.In):
    layer: Literal["holding", "company", "department"]
    company: str | None = Field(default=None, pattern=CODE)
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    kind: Literal["principle", "policy", "fact", "faq", "playbook"]
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=20000)
    sources: list[SourceIn] = Field(min_length=1, max_length=20)
    valid_until: date
    ref: str | None = Field(default=None, pattern=KREF)


class ChecksIn(T.In):
    """The review's four checks (injection, secrets, conflicts with the charter
    and the standing orders, extra authority): each one a real boolean."""

    injection: StrictBool
    secrets: StrictBool
    conflicts: StrictBool
    policy: StrictBool


class ReviewIn(T.In):
    ref: str = Field(pattern=KREF)
    version: StrictInt = Field(ge=1, le=100000)
    verdict: Literal["pass", "changes", "reject"]
    checks: ChecksIn
    notes_md: str = Field(default="", max_length=4000)


class ApproveIn(T.In):
    ref: str = Field(pattern=KREF)
    version: StrictInt = Field(ge=1, le=100000)


async def knowledge_propose(api: T.Api, call: T.Call, a: ProposeIn) -> T.Result:
    body: dict[str, Any] = {
        "layer": a.layer,
        "kind": a.kind,
        "title_fa": await T._text(a.title_fa),
        "body_md": await T._text(a.body_md),
        "sources": await sources_out(a.sources),
        "valid_until": a.valid_until.isoformat(),
    }
    for key in ("company", "department", "ref"):
        value = getattr(a, key)
        if value is not None:
            body[key] = value
    resp = await api.request(
        "POST", "/internal/v1/knowledge", call.token, json=body,
        idem=call.idem("knowledge.propose"),
    )  # fmt: skip
    return T.from_response(resp)


async def knowledge_review(api: T.Api, call: T.Call, a: ReviewIn) -> T.Result:
    body: dict[str, Any] = {
        "version": a.version,
        "verdict": a.verdict,
        "checks": a.checks.model_dump(),
        "notes_md": await T._text(a.notes_md),
    }
    resp = await api.request(
        "POST", f"/internal/v1/knowledge/{a.ref}/review", call.token, json=body,
        idem=call.idem("knowledge.review"),
    )  # fmt: skip
    return T.from_response(resp)


async def knowledge_approve(api: T.Api, call: T.Call, a: ApproveIn) -> T.Result:
    resp = await api.request(
        "POST", f"/internal/v1/knowledge/{a.ref}/approve", call.token,
        json={"version": a.version}, idem=call.idem("knowledge.approve"),
    )  # fmt: skip
    return T.from_response(resp)


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "knowledge.propose": (ProposeIn, knowledge_propose),
    "knowledge.review": (ReviewIn, knowledge_review),
    "knowledge.approve": (ApproveIn, knowledge_approve),
}

# Registered with the gateway's tools (tools.py itself knows nothing of these).
T.TOOLS.update(TOOLS)
