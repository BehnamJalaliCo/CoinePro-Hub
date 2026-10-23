"""Prompt 12 part A's tools (agents/tools.md v1.5, contract §21.1, §21.13).

    memo.write       A1  the advisor's decision memo on a pending card: the
                         answer first, the options, `against_md` (the strongest
                         case against, never empty), the risks, the questions
                         and a citation for every fact (checked by the api; an
                         invented one is dropped and counted)
    substitute.call  A0  one bounded question to a substitute player (ChatGPT,
                         Gemini, DeepSeek on the owner's subscriptions) at a seat
                         the role may use; masked input only; the answer is
                         labelled with its source and is never evidence

Agent-written text goes through the gateway's redaction like every write.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T

Seat = Literal[
    "advisor_second_opinion",
    "code_review",
    "overseer_cross_check",
    "assistant_errand",
    "content_draft",
    "long_read",
    "quick_search",
    "third_opinion",
    "creative",
]


class MemoOption(T.In):
    title_fa: str = Field(min_length=1, max_length=300)
    pros_md: str = Field(default="", max_length=4000)
    cons_md: str = Field(default="", max_length=4000)


class MemoRisk(T.In):
    title_fa: str = Field(min_length=1, max_length=300)
    likelihood: Literal["low", "medium", "high"]
    impact: Literal["low", "medium", "high"]
    mitigation_fa: str = Field(default="", max_length=2000)


class MemoCitation(T.In):
    kind: Literal["decision", "resolution", "deliverable", "work", "message", "audit"]
    ref: str = Field(min_length=1, max_length=40)


class MemoWriteIn(T.In):
    decision: str = Field(pattern=r"^D-[0-9]{4,9}$")
    decision_version: int = Field(ge=1)
    mode: Literal["standard", "devil"] = "standard"
    summary_fa: str = Field(min_length=1, max_length=4000)
    recommendation: Literal["approve", "reject", "return", "ask"]
    confidence: float = Field(ge=0, le=1)
    options: list[MemoOption] = Field(default_factory=list, max_length=8)
    against_md: str = Field(min_length=1, max_length=20000)
    risks: list[MemoRisk] = Field(default_factory=list, max_length=20)
    questions: list[str] = Field(default_factory=list, max_length=20)
    citations: list[MemoCitation] = Field(default_factory=list, max_length=50)


class Overlay(T.In):
    title_fa: str = Field(min_length=1, max_length=80)
    body_fa: str | None = Field(default=None, max_length=200)
    cta_fa: str | None = Field(default=None, max_length=60)
    mark: bool = True


class SubstituteCallIn(T.In):
    seat: Seat
    player: Literal["gpt", "gemini", "deepseek"] | None = None
    input_md: str = Field(min_length=1, max_length=200_000)
    file_ids: list[str] = Field(default_factory=list, max_length=10)
    repo: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    kind: Literal["text", "image", "video"] = "text"
    placement: (
        Literal[
            "telegram_post",
            "telegram_story",
            "instagram_post",
            "instagram_story",
            "banner",
            "other",
        ]
        | None
    ) = None
    overlay: Overlay | None = None
    duration_s: int | None = Field(default=None, ge=1, le=10)


async def memo_write(api: T.Api, call: T.Call, a: MemoWriteIn) -> T.Result:
    body = a.model_dump(mode="json")
    body["summary_fa"] = await T._text(a.summary_fa)
    body["against_md"] = await T._text(a.against_md)
    body["questions"] = [await T._text(q) for q in a.questions]
    for opt in body["options"]:
        opt["pros_md"] = await T._text(opt["pros_md"])
        opt["cons_md"] = await T._text(opt["cons_md"])
    for risk in body["risks"]:
        risk["mitigation_fa"] = await T._text(risk["mitigation_fa"])
    resp = await api.request(
        "POST", "/internal/v1/advisor/memos", call.token, json=body, idem=call.idem("memo.write")
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "")
        r.data = {
            "ref": r.data.get("ref"),
            "state": r.data.get("state"),
            "citations_dropped": r.data.get("citations_dropped"),
        }
    return r


async def substitute_call(api: T.Api, call: T.Call, a: SubstituteCallIn) -> T.Result:
    body = a.model_dump(mode="json", exclude_none=True)
    body["input_md"] = await T._text(a.input_md)
    resp = await api.request("POST", "/internal/v1/substitutes/call", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("creative") or r.data.get("call") or f"substitute:{a.seat}")
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "memo.write": (MemoWriteIn, memo_write),
    "substitute.call": (SubstituteCallIn, substitute_call),
}
T.TOOLS.update(TOOLS)
