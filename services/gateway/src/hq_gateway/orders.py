"""⟨1.16⟩ The owner's orders answered (contract §29.2, §34): the tools of whoever works on one.

    order.ack (A1)       {ref, plan_fa, assigned?: [code], due_at?}: the plan of the order's holder
                         («فهمیدم؛ برنامه: …»), within 10 minutes of the order
    order.progress (A1)  {ref, step_fa}: one real step, in plain Persian
    order.ask (A1)       {ref, question_fa}: one short question to the owner (the owner's turn:
                         the order waits for the owner's word, which comes back to the same work)

Every role has them (hq_common.charters.EVERY_ROLE_TOOLS); the api and the policy let only someone
who works on the order use them (`assigned`). Before prompt 25 the api and the policy had ack and
progress but no tool reached them: an order's holder could never answer it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from hq_gateway import tools as T

ORDER_REF = r"^F-[0-9]{4,}$"


class AckIn(T.In):
    ref: str = Field(pattern=ORDER_REF)
    plan_fa: str = Field(min_length=1, max_length=2000)
    assigned: list[str] = Field(default_factory=list, max_length=20)
    due_at: datetime | None = None


class StepIn(T.In):
    ref: str = Field(pattern=ORDER_REF)
    step_fa: str = Field(min_length=1, max_length=1000)


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
    }
    resp = await api.request("POST", f"/internal/v1/orders/{a.ref}/ack", call.token, json=body)
    return _view(T.from_response(resp, None), a.ref)


async def order_progress(api: T.Api, call: T.Call, a: StepIn) -> T.Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/orders/{a.ref}/progress",
        call.token,
        json={"step_fa": await T._text(a.step_fa)},
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


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "order.ack": (AckIn, order_ack),
    "order.progress": (StepIn, order_progress),
    "order.ask": (AskIn, order_ask),
}
T.TOOLS.update(TOOLS)
