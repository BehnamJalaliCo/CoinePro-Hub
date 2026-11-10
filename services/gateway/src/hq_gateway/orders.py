"""⟨1.16⟩ The owner's orders answered (contract §29.2, §34): the tools of whoever works on one.

    order.ack (A1)       {ref, plan_fa, assigned?: [code], due_at?, steps?: [str]}: the plan of
                         the order's holder («فهمیدم؛ برنامه: …»), within 10 minutes of the order;
                         ⟨1.17⟩ `steps` become the session's tasks (the owner sees them ticked)
    order.progress (A1)  {ref, step_fa, done?: [n]}: one real step, in plain Persian; ⟨1.17⟩
                         `done` ticks those task numbers
    automation.propose (A1)  ⟨2026-11-06⟩ {sentence_fa}: a CEO or a manager proposes one Persian
                         sentence as an automation of its company (the hub checks it; the owner
                         seals it; it may start an n8n workflow)
    order.ask (A1)       {ref, question_fa}: one short question to the owner (the owner's turn:
                         the order waits for the owner's word, which comes back to the same work);
                         ⟨1.17⟩ a second ask while the turn is open joins it

Every role has them (hq_common.charters.EVERY_ROLE_TOOLS); the api and the policy let only someone
who works on the order use them (`assigned`). Before prompt 25 the api and the policy had ack and
progress but no tool reached them: an order's holder could never answer it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StrictInt

from hq_gateway import tools as T

ORDER_REF = r"^F-[0-9]{4,}$"


class AckIn(T.In):
    ref: str = Field(pattern=ORDER_REF)
    plan_fa: str = Field(min_length=1, max_length=2000)
    assigned: list[str] = Field(default_factory=list, max_length=20)
    due_at: datetime | None = None
    steps: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=20
    )


class StepIn(T.In):
    ref: str = Field(pattern=ORDER_REF)
    step_fa: str = Field(min_length=1, max_length=1000)
    done: list[Annotated[StrictInt, Field(ge=1, le=500)]] = Field(
        default_factory=list, max_length=50
    )


class AskIn(T.In):
    ref: str = Field(pattern=ORDER_REF)
    question_fa: str = Field(min_length=2, max_length=1000)


def _view(r: T.Result, ref: str) -> T.Result:
    if r.outcome == "ok":
        r.ref = ref
        data = r.data if isinstance(r.data, dict) else {}
        r.data = {"order": ref, "state": data.get("state")}
    return r


async def order_ack(api: T.Api, call: T.Call, a: AckIn) -> T.Result:
    body = {
        "plan_fa": await T._text(a.plan_fa),
        "assigned": [c for c in a.assigned if c],
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "steps": await T._text([s for s in a.steps if s.strip()]),
    }
    resp = await api.request("POST", f"/internal/v1/orders/{a.ref}/ack", call.token, json=body)
    return _view(T.from_response(resp, None), a.ref)


async def order_progress(api: T.Api, call: T.Call, a: StepIn) -> T.Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/orders/{a.ref}/progress",
        call.token,
        json={"step_fa": await T._text(a.step_fa), "done": list(dict.fromkeys(a.done))},
    )
    return _view(T.from_response(resp, None), a.ref)


async def order_ask(api: T.Api, call: T.Call, a: AskIn) -> T.Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/orders/{a.ref}/ask",
        call.token,
        json={"question_fa": await T._text(a.question_fa)},
    )
    return _view(T.from_response(resp, None), a.ref)


class AutomationIn(T.In):
    sentence_fa: str = Field(min_length=3, max_length=1000)


async def automation_propose(api: T.Api, call: T.Call, a: AutomationIn) -> T.Result:
    resp = await api.request(
        "POST",
        "/internal/v1/automations/propose",
        call.token,
        json={"sentence_fa": await T._text(a.sentence_fa)},
        idem=call.idem("automation.propose"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "")
        on = r.data.get("state") == "on"
        r.data = {"automation": r.data.get("ref"), "state": r.data.get("state"),
                  "preview_fa": r.data.get("preview_fa")}  # fmt: skip
        # ⟨1.31⟩ §50 a routine the owner asked for in this session runs from now: no seal
        r.hint_fa = (
            "روال دائمی ساخته شد و از همین حالا سر وقتش اجرا میشود؛ مُهر نمیخواهد. در یک خط به "
            "مدیر کل بگو چه چیزی، کی، و اینکه با یک لمس خاموش میشود."
            if on
            else "پیشنهاد ثبت شد و منتظر مُهر مدیر کل است؛ تا آن وقت چیزی اجرا نمیشود."
        )
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "order.ack": (AckIn, order_ack),
    "order.progress": (StepIn, order_progress),
    "order.ask": (AskIn, order_ask),
    "automation.propose": (AutomationIn, automation_propose),
}
T.TOOLS.update(TOOLS)
