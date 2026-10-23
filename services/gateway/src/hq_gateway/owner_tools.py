"""Prompt 12 §2's agent tool (agents/tools.md v1.5, contract §21.2):

    ask.answer  A1  the Hub Librarian's answer to the owner's «از هاب بپرس»,
                    only from the passages the search returned; every citation
                    names one of them ({kind, ref} for a record; {kind, repo,
                    path, lines} for a document or code). The api drops and
                    counts a citation outside them; an answer with no valid
                    citation fails.

The answer is redacted on the way, like every agent write.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hq_gateway import tools as T


class AskCitationIn(T.In):
    kind: Literal["resolution", "decision", "deliverable", "work", "message", "doc", "code"]
    ref: str | None = Field(default=None, max_length=60)
    repo: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=1000)
    lines: list[int] | None = Field(default=None, min_length=1, max_length=2)


class AskAnswerIn(T.In):
    ask: str = Field(pattern=r"^AK-[0-9]{4,9}$")
    answer_md: str = Field(min_length=1, max_length=6000)
    citations: list[AskCitationIn] = Field(default_factory=list, max_length=40)


async def ask_answer(api: T.Api, call: T.Call, a: AskAnswerIn) -> T.Result:
    body = a.model_dump(mode="json", exclude_none=True)
    body["answer_md"] = await T._text(a.answer_md)
    resp = await api.request(
        "POST",
        "/internal/v1/ask/answer",
        call.token,
        json=body,
        idem=call.idem(f"ask.answer:{a.ask}"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or a.ask)
        r.data = {
            "ref": r.data.get("ref"),
            "state": r.data.get("state"),
            "citations": len(r.data.get("citations") or []),
            "citations_dropped": r.data.get("citations_dropped"),
        }
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "ask.answer": (AskAnswerIn, ask_answer),
}
T.TOOLS.update(TOOLS)
