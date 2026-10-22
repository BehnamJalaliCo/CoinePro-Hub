"""The support desk's agent tools (agents/tools.md v1.5, contract §19.10;
prompt 10 §12). None of them sends free text to a customer: support.draft is
only a draft, and the api's code decides (auto-send policy, queue, block).

    kb.search        A0  the company's approved articles (the support lead also
                         sees proposed ones); another company's base is refused
    kb.propose       A1  an article proposal or a new version (the owner approves
                         it with step-up); never a referral code or a link
    support.draft    A2  the support agent's draft for one conversation
    support.handoff  A2  hand a conversation to the owner (holding reply goes out)
    support.mystery  A2  the overseer only (PR-043): a mystery customer on the
                         mystery channel; `conversation` instead reads its transcript
Registered with the gateway's tools on import (gateway.py).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from hq_gateway import tools as T

KB_REF = r"^KB-[0-9]{4,6}$"
CITE = r"^KB-[0-9]{4,6}@[0-9]{1,6}$"
CONV = r"^SC-[0-9]{6,}$"
Kind = Literal["faq", "policy", "procedure", "referral", "official_link", "safety"]


class KbSearchIn(T.In):
    q: str = Field(min_length=2, max_length=200)
    company: str | None = Field(default=None, pattern=T.CODE)
    kind: Kind | None = None


class VariableIn(T.In):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    source: Literal["customer", "policy"] = "customer"


class KbProposeIn(T.In):
    company: str = Field(pattern=T.CODE)
    kind: Kind
    question_fa: str = Field(min_length=1, max_length=1000)
    answer_md: str = Field(min_length=1, max_length=8000)
    variables: list[VariableIn] = Field(default_factory=list, max_length=20)
    source_ref: str = Field(min_length=1, max_length=200)
    ref: str | None = Field(default=None, pattern=KB_REF)


class DraftIn(T.In):
    conversation: str = Field(pattern=CONV)
    body_md: str = Field(min_length=1, max_length=4000)
    kb_refs: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def _refs(self) -> DraftIn:
        import re

        bad = [r for r in self.kb_refs if not re.fullmatch(CITE, r)]
        if bad:
            raise ValueError("kb_refs are KB-…@version")
        return self


class HandoffIn(T.In):
    conversation: str = Field(pattern=CONV)
    reason: Literal["no_kb", "low_confidence", "asked_for_human", "complaint", "security"]
    note_fa: str = Field(default="", max_length=1000)


class MysteryIn(T.In):
    company: str = Field(pattern=T.CODE)
    question_fa: str | None = Field(default=None, min_length=1, max_length=2000)
    conversation: str | None = Field(default=None, pattern=CONV)

    @model_validator(mode="after")
    def _one(self) -> MysteryIn:
        if (self.question_fa is None) == (self.conversation is None):
            raise ValueError("either question_fa or conversation")
        return self


async def kb_search(api: T.Api, call: T.Call, a: KbSearchIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "GET",
            "/internal/v1/support/kb",
            call.token,
            params={"q": a.q, "company": a.company, "kind": a.kind},
        ),
        None,
    )
    if r.outcome == "ok" and isinstance(r.data, list):
        r.data = {"articles": r.data, "count": len(r.data)}
    return r


async def kb_propose(api: T.Api, call: T.Call, a: KbProposeIn) -> T.Result:
    body: dict[str, Any] = a.model_dump(mode="json", exclude_none=True)
    body["question_fa"] = await T._text(a.question_fa)
    body["answer_md"] = await T._text(a.answer_md)
    r = T.from_response(
        await api.request(
            "POST", "/internal/v1/support/kb", call.token, json=body, idem=call.idem("kb.propose")
        )
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"{r.data.get('ref')}@{r.data.get('version')}"
        r.data = {k: r.data.get(k) for k in ("ref", "version", "kind", "status", "expires_at")}
    return r


async def support_draft(api: T.Api, call: T.Call, a: DraftIn) -> T.Result:
    # The draft leaves exactly as written (the api masks and guards it); only
    # a secret-looking string is scrubbed, as for every text an agent writes.
    r = T.from_response(
        await api.request(
            "POST",
            f"/internal/v1/support/conversations/{a.conversation}/draft",
            call.token,
            json={
                "body_md": await T._text(a.body_md),
                "kb_refs": a.kb_refs,
                "confidence": a.confidence,
            },
            idem=call.idem(f"support.draft:{a.conversation}"),
        ),
        None,
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = a.conversation
        msg = r.data.get("message") or {}
        r.data = {
            "decision": r.data.get("decision"),
            "problems": r.data.get("problems") or [],
            "blocked_reasons": msg.get("blocked_reasons") or [],
            "checks": msg.get("checks"),
        }
    return r


async def support_handoff(api: T.Api, call: T.Call, a: HandoffIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "POST",
            f"/internal/v1/support/conversations/{a.conversation}/handoff",
            call.token,
            json={"reason": a.reason, "note_fa": await T._text(a.note_fa)},
            idem=call.idem(f"support.handoff:{a.conversation}"),
        )
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {"conversation": r.data.get("ref"), "state": r.data.get("state")}
    return r


async def support_mystery(api: T.Api, call: T.Call, a: MysteryIn) -> T.Result:
    body: dict[str, Any] = {"company": a.company}
    if a.question_fa is not None:
        body["question_fa"] = await T._text(a.question_fa)
    if a.conversation is not None:
        body["conversation"] = a.conversation
    return T.from_response(
        await api.request(
            "POST",
            "/internal/v1/support/mystery",
            call.token,
            json=body,
            idem=call.idem(f"support.mystery:{a.company}"),
        ),
        "conversation",
    )


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "kb.search": (KbSearchIn, kb_search),
    "kb.propose": (KbProposeIn, kb_propose),
    "support.draft": (DraftIn, support_draft),
    "support.handoff": (HandoffIn, support_handoff),
    "support.mystery": (MysteryIn, support_mystery),
}

# Registered with the gateway's tools (tools.py itself knows nothing of these).
T.TOOLS.update(TOOLS)
