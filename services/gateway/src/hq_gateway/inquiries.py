"""Prompt 08 §3 and §5 tools (agents/tools.md v2, contract §18.2, §18.3):
formal inquiries, the personal assistant's errands and the owner's planner,
and workshop.read (the advisor v2 reads every company's sessions).

    inquiry.ask     A1  the overseer, the advisor (anyone); a CEO (own company)
    inquiry.answer  A1  the asked one; the answer goes to the asker's thread
    errand.step     A2  the assistant: one step of an errand's trail
    errand.finish   A2  the assistant: the errand's result (posted in thread P)
    planner.add     A2  the assistant: a dated item in the owner's planner
    workshop.read   A0  one Code Workshop session and its events
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

INQUIRY_REF = r"^Q-[0-9]{4,}$"
ERRAND_REF = r"^E-[0-9]{4,}$"
SESSION_REF = r"^S-[0-9]{4,}$"


class InquiryAskIn(T.In):
    to: str = Field(pattern=T.EMP)
    question_md: str = Field(min_length=1, max_length=20000)
    due_in_hours: int = Field(ge=1, le=24 * 14, strict=True)


class InquiryAnswerIn(T.In):
    ref: str = Field(pattern=INQUIRY_REF)
    answer_md: str = Field(min_length=1, max_length=50000)
    evidence: list[T.EvidenceIn] = Field(default_factory=list, max_length=50)


class ErrandStepIn(T.In):
    ref: str = Field(pattern=ERRAND_REF)
    kind: Literal["search", "read", "browse", "request", "draft", "note", "proposal"]
    summary_fa: str = Field(min_length=1, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)


class ErrandFinishIn(T.In):
    ref: str = Field(pattern=ERRAND_REF)
    result_md: str = Field(min_length=1, max_length=50000)
    file_ids: list[str] = Field(default_factory=list, max_length=20)


class PlannerAddIn(T.In):
    title_fa: str = Field(min_length=1, max_length=200)
    at: datetime
    note: str | None = Field(default=None, max_length=2000)
    errand: str | None = Field(default=None, pattern=ERRAND_REF)


class WorkshopReadIn(T.In):
    session_ref: str = Field(pattern=SESSION_REF)
    after: int = Field(default=0, ge=0, strict=True)


async def inquiry_ask(api: T.Api, call: T.Call, a: InquiryAskIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "POST",
            "/internal/v1/inquiries",
            call.token,
            json={
                "to": a.to,
                "question_md": await T._text(a.question_md),
                "due_in_hours": a.due_in_hours,
            },
            idem=call.idem(f"inquiry.ask:{a.to}"),
        )
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {
            "inquiry": r.ref,
            "to": a.to,
            "due_at": r.data.get("due_at"),
            "work": r.data.get("work_ref"),
        }
    return r


async def inquiry_answer(api: T.Api, call: T.Call, a: InquiryAnswerIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "POST",
            f"/internal/v1/inquiries/{a.ref}/answer",
            call.token,
            json={
                "answer_md": await T._text(a.answer_md),
                "evidence": [await T._text(e.model_dump(exclude_none=True)) for e in a.evidence],
            },
            idem=call.idem(f"inquiry.answer:{a.ref}"),
        )
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {
            "inquiry": r.ref,
            "status": r.data.get("status"),
            "message": r.data.get("answer_message_ref"),
            "thread": r.data.get("thread_ref"),
        }
    return r


def _errand(r: T.Result) -> T.Result:
    if r.outcome == "ok" and isinstance(r.data, dict):
        steps = r.data.get("steps") or []
        r.data = {
            "errand": r.ref,
            "status": r.data.get("status"),
            "steps": len(steps),
            "decision": r.data.get("decision_ref"),
        }
    return r


async def errand_step(api: T.Api, call: T.Call, a: ErrandStepIn) -> T.Result:
    return _errand(
        T.from_response(
            await api.request(
                "POST",
                f"/internal/v1/errands/{a.ref}/steps",
                call.token,
                json={
                    "kind": a.kind,
                    "summary_fa": await T._text(a.summary_fa),
                    "data": await T._text(a.data),
                },
                idem=call.idem(f"errand.step:{a.ref}"),
            )
        )
    )


async def errand_finish(api: T.Api, call: T.Call, a: ErrandFinishIn) -> T.Result:
    return _errand(
        T.from_response(
            await api.request(
                "POST",
                f"/internal/v1/errands/{a.ref}/finish",
                call.token,
                json={"result_md": await T._text(a.result_md), "file_ids": a.file_ids},
                idem=call.idem(f"errand.finish:{a.ref}"),
            )
        )
    )


async def planner_add(api: T.Api, call: T.Call, a: PlannerAddIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "POST",
            "/internal/v1/planner",
            call.token,
            json={
                "title_fa": await T._text(a.title_fa),
                "at": a.at.isoformat(),
                "note": await T._text(a.note) if a.note else None,
                "errand": a.errand,
            },
            idem=call.idem("planner.add"),
        )
    )
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {"planner_item": r.ref, "at": r.data.get("at")}
    return r


async def workshop_read(api: T.Api, call: T.Call, a: WorkshopReadIn) -> T.Result:
    r = T.from_response(
        await api.request(
            "GET",
            f"/internal/v1/workshop/sessions/{a.session_ref}",
            call.token,
            params={"after": a.after},
        ),
        None,
    )
    if r.outcome == "ok":
        r.ref = f"workshop:{a.session_ref}"
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "inquiry.ask": (InquiryAskIn, inquiry_ask),
    "inquiry.answer": (InquiryAnswerIn, inquiry_answer),
    "errand.step": (ErrandStepIn, errand_step),
    "errand.finish": (ErrandFinishIn, errand_finish),
    "planner.add": (PlannerAddIn, planner_add),
    "workshop.read": (WorkshopReadIn, workshop_read),
}

# Registered with the gateway's tools (like the internet tools, web.py).
T.TOOLS.update(TOOLS)
