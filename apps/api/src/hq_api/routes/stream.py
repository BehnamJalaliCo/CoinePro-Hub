"""Live stream (contract §7): Server-Sent Events bridged from JetStream
stream HQ_CORE (`hq.core.<company>.<type>`).

- `id:` is the JetStream sequence, so `Last-Event-ID` resumes without loss
  (within the 30-day retention).
- Filters: `topics` (work, decisions, deliverables, messages, notifications,
  activity, llm, control) and `company` (repeatable). `company=*` is the
  holding view for 40+ companies: only counters and `activity.changed`,
  never full payloads.
- Heartbeat comment every 15 s. Events carry metadata only.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from nats.js.api import ConsumerConfig, DeliverPolicy

from hq_api import events
from hq_api.context import Ctx, owner_ctx
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["stream"])
HEARTBEAT_S = 15.0


def matches(env: dict[str, Any], topics: set[str], companies: set[str] | None) -> bool:
    if companies is not None and env.get("company") not in companies:
        return False
    type_ = str(env.get("type", ""))
    return any(type_.startswith(prefix) for t in topics for prefix in events.TOPICS[t])


def holding_view(env: dict[str, Any]) -> dict[str, Any]:
    """company=*: counters only, except live activity."""
    if env.get("type") == "activity.changed":
        return env
    return {
        "id": env.get("id"),
        "type": env.get("type"),
        "at": env.get("at"),
        "company": env.get("company"),
    }


def sse(seq: int, env: dict[str, Any]) -> bytes:
    return (
        f"id: {seq}\nevent: {env['type']}\ndata: {json.dumps(env, ensure_ascii=False)}\n\n".encode()
    )


async def bridge(
    ctx: Ctx, topics: set[str], companies: set[str] | None, summary: bool, last_id: int | None
) -> AsyncIterator[bytes]:
    bus = ctx.hub.bus
    if bus is None or not bus.connected:
        raise ApiError(503, "internal_error", "the event bus is not available")
    if last_id is not None:
        cfg = ConsumerConfig(
            deliver_policy=DeliverPolicy.BY_START_SEQUENCE, opt_start_seq=last_id + 1
        )
    else:
        cfg = ConsumerConfig(deliver_policy=DeliverPolicy.NEW)
    sub = await bus.js.subscribe(
        events.SUBJECTS, stream=events.STREAM, ordered_consumer=True, config=cfg
    )
    try:
        yield b"retry: 3000\n\n"
        while True:
            try:
                msg = await sub.next_msg(timeout=HEARTBEAT_S)
            except TimeoutError:
                yield b": heartbeat\n\n"
                continue
            try:
                env = json.loads(msg.data)
            except ValueError:
                continue
            if not matches(env, topics, companies):
                continue
            yield sse(int(msg.metadata.sequence.stream), holding_view(env) if summary else env)
    finally:
        with contextlib.suppress(Exception):
            await sub.unsubscribe()


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={
        **responses(401, 422, 503),
        200: {"content": {"text/event-stream": {}}, "description": "SSE"},
    },
)
async def stream(
    request: Request,
    topics: str = Query(
        default="work,decisions,deliverables,messages,notifications,activity,llm,control",
        pattern=r"^[a-z]+(,[a-z]+)*$",
        max_length=200,
    ),
    company: list[str] | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> StreamingResponse:
    """Live events (SSE). `Last-Event-ID` resumes after that JetStream sequence."""
    wanted = {t for t in topics.split(",") if t}
    unknown = wanted - events.TOPICS.keys()
    if unknown:
        raise ApiError(
            422, "validation_failed", fields={"topics": f"unknown: {', '.join(sorted(unknown))}"}
        )
    summary = company == ["*"]
    companies: set[str] | None = None
    if company and not summary:
        for code in company:
            await ctx.hub.companies.by_code(code)  # 404 for unknown codes (tenant check)
        companies = set(company)
    raw = request.headers.get("last-event-id")
    last_id = int(raw) if raw and raw.isdigit() else None
    gen = bridge(ctx, wanted, companies, summary, last_id)
    first = await gen.__anext__()  # fail before the 200 if the bus is down

    async def body() -> AsyncIterator[bytes]:
        yield first
        async for chunk in gen:
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
