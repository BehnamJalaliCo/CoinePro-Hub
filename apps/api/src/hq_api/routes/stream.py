"""Live stream (contract §7): Server-Sent Events bridged from JetStream
stream HQ_CORE (`hq.core.<company>.<type>`).

- `id:` is the JetStream sequence, so `Last-Event-ID` resumes without loss
  (within the 30-day retention).
- Filters: `topics` (work, decisions, deliverables, messages, notifications,
  activity, llm, control, runs) and `company` (repeatable). `company=*` is
  the holding view for 40+ companies: only counters, never full payloads,
  but for `activity.changed` and ⟨1.24⟩ §42.1 the live events of HOLDING_FULL.
- ⟨1.4.2⟩ Unknown topics are ignored, not refused (a client may name topics a
  newer server adds); the first comment lists the topics served
  (`: topics work,decisions,...`). Only a malformed `topics` is 422.
- ⟨1.7.5⟩ `topics` up to 1000 characters, and `topics=all` for every topic
  (one connection for an app that follows them all).
- Heartbeat comment every 15 s. Events carry metadata only.
"""

from __future__ import annotations

import contextlib
import json
import time
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


# ⟨1.24⟩ §42.1: the small, text-free events the holding's live views draw from pass in full
HOLDING_FULL = frozenset(
    {
        "activity.changed",
        "server.state",
        "network.link",
        "holding.flow",
        "employee.state",
        "llm.tick",
        "session.updated",
        "session.activity",
        "control.changed",
        "links.updated",
    }
)


def holding_view(env: dict[str, Any]) -> dict[str, Any]:
    """company=*: counters only, except the live events of HOLDING_FULL."""
    if env.get("type") in HOLDING_FULL:
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
    served = ",".join(t for t in events.TOPICS if t in topics)
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
        yield f": topics{' ' + served if served else ''}\nretry: 3000\n\n".encode()
        # The heartbeat is by the clock, not only on an idle bus (handoff 2026-11-05, bug 2): a busy bus whose events
        # this client does not take (another company's, another topic's, or a replay from a far `Last-Event-ID`) used to
        # keep `next_msg` answering, so nothing was written for minutes and the app's 50 s read timeout cut the stream.
        sent = time.monotonic()
        while True:
            wait = max(0.1, HEARTBEAT_S - (time.monotonic() - sent))
            try:
                msg = await sub.next_msg(timeout=wait)
            except TimeoutError:
                msg = None
            out: bytes | None = None
            if msg is not None:
                try:
                    env = json.loads(msg.data)
                except ValueError:
                    env = None
                if env is not None and matches(env, topics, companies):
                    out = sse(
                        int(msg.metadata.sequence.stream), holding_view(env) if summary else env
                    )
            if out is None and time.monotonic() - sent >= HEARTBEAT_S:
                out = b": heartbeat\n\n"
            if out is not None:
                sent = time.monotonic()
                yield out
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
        default="work,decisions,deliverables,messages,notifications,activity,llm,control,runs",
        pattern=r"^[a-z][a-z_]*(,[a-z][a-z_]*)*$",
        max_length=1000,
    ),
    company: list[str] | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> StreamingResponse:
    """Live events (SSE). `Last-Event-ID` resumes after that JetStream sequence.
    Unknown topics are ignored; the first comment names the topics served."""
    names = {t for t in topics.split(",") if t}
    wanted = set(events.TOPICS) if "all" in names else names & events.TOPICS.keys()
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
