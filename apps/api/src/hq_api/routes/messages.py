"""Messages and resolutions (contract §5.3, §5.4).

Threads: advisor `A`, a CEO `TY-CEO`, a manager `TY-TECH-MGR`, a department
group `TY-TECH`, an employee `TY-TECH-01`. Messages are immutable and
numbered per thread (A-0142). Search is Persian-safe (ی/ي, ک/ك, ZWNJ,
diacritics): Postgres FTS (`simple`) plus trigram substring match.
Message bodies never go to NATS or the audit log.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.errors import ApiError, responses
from hq_api.routes.deliverables import files_of
from hq_api.schemas import Actor, FileRef, Model, Page, actor

router = APIRouter(tags=["messages"])
E = responses(401, 403, 404, 409, 422)
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
THREAD = r"^(A|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"


class Thread(BaseModel):
    id: UUID
    code: str
    kind: str
    company: str | None
    title_fa: str
    participants: list[Actor]
    last_message_at: datetime | None
    last_ref: str | None
    unread: int


class ThreadCreate(Model):
    kind: Literal["employee"]
    employee: str = Field(pattern=EMP)


class Links(Model):
    decision: str | None = Field(default=None, max_length=20)
    work: str | None = Field(default=None, max_length=20)
    resolution: str | None = Field(default=None, max_length=20)
    corrects: str | None = Field(default=None, max_length=40)


class Message(BaseModel):
    id: UUID
    ref: str
    thread: str
    author: Actor
    body: str
    attachments: list[FileRef]
    links: dict[str, Any]
    kind: str
    created_at: datetime


class MessageIn(Model):
    body: str = Field(min_length=1, max_length=100000)
    links: Links | None = None


class ReadIn(Model):
    up_to_ref: str = Field(min_length=3, max_length=40)


class Resolution(BaseModel):
    id: UUID
    ref: str
    company: str | None
    title: str
    body: str
    source: dict[str, str | None]
    sealed_by: Actor
    sealed_at: datetime
    sent_to: list[str]
    follow_up_work_id: UUID | None


class ResolutionIn(Model):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=50000)
    source_message: str | None = Field(default=None, max_length=40)


class SearchHit(Message):
    rank: float


THREAD_SQL = """
    SELECT t.id, t.code, t.kind, t.title_fa, t.last_message_at, t.last_seq, t.owner_read_seq,
           c.code AS company, c.kind AS company_kind, e.code AS emp_code
    FROM msg.threads t
    JOIN core.companies c ON c.id = t.company_id
    LEFT JOIN core.employees e ON e.id = t.employee_id
"""

MESSAGE_SQL = """
    SELECT m.id, m.ref, t.code AS thread, m.author_kind, m.author_code, m.body, m.attachments, m.links,
           m.kind, m.created_at, m.seq
    FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
"""


def _thread(r: dict[str, Any]) -> Thread:
    parts = [Actor(kind="owner", code="owner", display_fa="مدیر کل")]
    if r["kind"] == "advisor":
        parts.append(Actor(kind="agent", code=r["emp_code"] or "HQ-ADV"))
    elif r["emp_code"]:
        parts.append(Actor(kind="agent", code=r["emp_code"]))
    last_ref = f"{r['code']}-{r['last_seq']:04d}" if r["last_seq"] else None
    return Thread(
        id=r["id"],
        code=r["code"],
        kind=r["kind"],
        company=r["company"],
        title_fa=r["title_fa"],
        participants=parts,
        last_message_at=r["last_message_at"],
        last_ref=last_ref,
        unread=r["last_seq"] - r["owner_read_seq"],
    )


async def render_messages(tx: Tx, rows: list[dict[str, Any]]) -> list[Message]:
    files = await files_of(tx, [f for r in rows for f in r["attachments"] or []])
    out = []
    for r in rows:
        author = actor(r["author_kind"], r["author_code"])
        assert author is not None
        out.append(
            Message(
                id=r["id"],
                ref=r["ref"],
                thread=r["thread"],
                author=author,
                body=r["body"],
                attachments=[files[f] for f in r["attachments"] or [] if f in files],
                links=r["links"],
                kind=r["kind"],
                created_at=r["created_at"],
            )
        )
    return out


@router.get("/threads", response_model=list[Thread], responses=E)
async def list_threads(
    kind: Literal["advisor", "ceo", "manager", "department", "employee"] | None = None,
    company: list[str] | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> list[Thread]:
    """The advisor first, then by latest activity."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            THREAD_SQL
            + """ WHERE (CAST(:kind AS text) IS NULL OR t.kind = :kind)
                    AND (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                  ORDER BY t.kind = 'advisor' DESC, t.last_message_at DESC NULLS LAST, t.code""",
            kind=kind,
            companies=company,
        )
    return [_thread(r) for r in rows]


@router.post("/threads", response_model=Thread, status_code=201, responses=E)
async def open_thread(body: ThreadCreate, ctx: Ctx = Depends(owner_ctx)) -> Thread:
    """Opens (or returns) the direct thread with an employee."""
    async with ctx.tx() as tx:
        emp = await tx.one(
            "SELECT id, code, title_fa, company_id, status FROM core.employees WHERE code = :c",
            c=body.employee,
        )
        await tx.exec(
            """INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
               VALUES (:code, 'employee', :co, :e, :t) ON CONFLICT (code) DO NOTHING""",
            code=emp["code"],
            co=emp["company_id"],
            e=emp["id"],
            t=emp["title_fa"],
        )
        await ctx.audit(
            tx,
            company_id=emp["company_id"],
            action="thread.open",
            action_class="A1",
            target_kind="thread",
            target_ref=emp["code"],
        )
        await ctx.interaction(
            tx,
            company_id=emp["company_id"],
            kind="message",
            action="thread.open",
            target_kind="thread",
            target_ref=emp["code"],
        )
        return _thread(await tx.one(THREAD_SQL + " WHERE t.code = :c", c=emp["code"]))


@router.get("/threads/{code}/messages", response_model=Page[Message], responses=E)
async def list_messages(
    code: str,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Message]:
    """Oldest -> newest from the cursor (no cursor: the latest page)."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        t = await tx.one("SELECT id, last_seq FROM msg.threads WHERE code = :c", c=code)
        start = after[0] if after else max(0, t["last_seq"] - limit)
        if not isinstance(start, int):
            raise ApiError(422, "validation_failed", fields={"cursor": "invalid"})
        rows = await tx.all(
            MESSAGE_SQL + " WHERE m.thread_id = :t AND m.seq > :s ORDER BY m.seq LIMIT :lim",
            t=t["id"],
            s=start,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("seq",))
        return Page(items=await render_messages(tx, items), next_cursor=nxt)


async def post_message(
    ctx: Ctx,
    tx: Tx,
    thread_code: str,
    body: str,
    links: dict[str, Any],
    attachments: list[UUID] | None = None,
) -> dict[str, Any]:
    t = await tx.one("SELECT id, company_id FROM msg.threads WHERE code = :c", c=thread_code)
    if links.get("corrects") and not await tx.scalar(
        "SELECT 1 FROM msg.messages WHERE ref = :r AND thread_id = :t",
        r=links["corrects"],
        t=t["id"],
    ):
        raise ApiError(
            422, "validation_failed", fields={"links.corrects": "a message of this thread"}
        )
    m = await tx.one(
        """SELECT id, ref, company_id
           FROM msg.post(:t, :ak, :ac, :body, CAST(:links AS jsonb), CAST(:att AS uuid[]), 'text')""",
        t=t["id"],
        ak=ctx.who.kind,
        ac=ctx.who.code,
        body=body,
        links=json.dumps(links),
        att=[str(a) for a in attachments or []],
    )
    co_code = await ctx.hub.companies.code_of(t["company_id"])
    await ctx.emit(
        tx,
        co_code,
        "message.created",
        m["ref"],
        {
            "thread": thread_code,
            "author": ctx.who.code,
            "links": {k: v for k, v in links.items() if v},
        },
    )
    await ctx.audit(
        tx,
        company_id=t["company_id"],
        action="message.post",
        action_class="A1",
        target_kind="message",
        target_ref=m["ref"],
        summary=f"thread {thread_code}",
    )
    return m


@router.post("/threads/{code}/messages", response_model=Message, status_code=201, responses=E)
async def send_message(
    code: str, body: MessageIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Messages are immutable: a correction is a new message with `links.corrects`.
    Requires `Idempotency-Key`."""
    links = body.links.model_dump(exclude_none=True) if body.links else {}
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        m = await post_message(ctx, tx, code, body.body, links)
        await ctx.interaction(
            tx,
            company_id=m["company_id"],
            kind="message",
            action="message.post",
            target_kind="message",
            target_ref=m["ref"],
            data={"thread": code, "chars": len(body.body), "links": links},
        )
        result = (
            await render_messages(tx, [await tx.one(MESSAGE_SQL + " WHERE m.id = :id", id=m["id"])])
        )[0]
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.post("/threads/{code}/read", response_model=Thread, responses=E)
async def mark_read(code: str, body: ReadIn, ctx: Ctx = Depends(owner_ctx)) -> Thread:
    async with ctx.tx() as tx:
        t = await tx.one("SELECT id FROM msg.threads WHERE code = :c", c=code)
        seq = await tx.scalar(
            "SELECT seq FROM msg.messages WHERE thread_id = :t AND ref = :r",
            t=t["id"],
            r=body.up_to_ref,
        )
        if seq is None:
            raise ApiError(404, "not_found", "no such message in this thread")
        await tx.exec(
            "UPDATE msg.threads SET owner_read_seq = greatest(owner_read_seq, :s) WHERE id = :t",
            t=t["id"],
            s=seq,
        )
        return _thread(await tx.one(THREAD_SQL + " WHERE t.id = :t", t=t["id"]))


@router.get("/search/messages", response_model=Page[SearchHit], responses=E)
async def search_messages(
    q: str = Query(min_length=1, max_length=200),
    thread: str | None = Query(default=None, pattern=THREAD),
    company: list[str] | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[SearchHit]:
    """Full-text and substring search over every thread the caller may read."""
    after = pagination.decode(cursor, 1)
    offset = int(after[0]) if after else 0
    async with ctx.tx() as tx:
        rows = await tx.all(
            MESSAGE_SQL
            + """ JOIN core.companies c ON c.id = m.company_id,
                    LATERAL (SELECT core.fa_normalize(:q) AS nq) n
                  WHERE (m.search @@ plainto_tsquery('simple', n.nq)
                         OR core.fa_normalize(m.body) LIKE '%' || n.nq || '%')
                    AND (CAST(:thread AS text) IS NULL OR t.code = :thread)
                    AND (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:from_ AS timestamptz) IS NULL OR m.created_at >= :from_)
                    AND (CAST(:to_ AS timestamptz) IS NULL OR m.created_at < :to_)
                  ORDER BY ts_rank(m.search, plainto_tsquery('simple', n.nq)) DESC, m.created_at DESC
                  OFFSET :off LIMIT :lim""",
            q=q,
            thread=thread,
            companies=company,
            from_=from_,
            to_=to,
            off=offset,
            lim=limit + 1,
        )
        msgs = await render_messages(tx, rows[:limit])
    hits = [SearchHit(**m.model_dump(), rank=1.0 / (i + 1 + offset)) for i, m in enumerate(msgs)]
    nxt = pagination.encode([offset + limit]) if len(rows) > limit else None
    return Page(items=hits, next_cursor=nxt)


# ------------------------------------------------------------- resolutions --
RESOLUTION_SQL = """
    SELECT r.*, c.code AS company, c.kind AS company_kind, d.ref AS decision_ref, m.ref AS message_ref
    FROM cartable.resolutions r
    JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN cartable.decisions d ON d.id = r.source_decision_id
    LEFT JOIN msg.messages m ON m.id = r.source_message_id
"""


def _resolution(r: dict[str, Any]) -> Resolution:
    sealed = actor(r["sealed_by_kind"], r["sealed_by_code"])
    assert sealed is not None
    return Resolution(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        title=r["title"],
        body=r["body"],
        source={"decision": r["decision_ref"], "message": r["message_ref"]},
        sealed_by=sealed,
        sealed_at=r["sealed_at"],
        sent_to=list(r["sent_to"]),
        follow_up_work_id=r["follow_up_work_id"],
    )


@router.get("/resolutions", response_model=Page[Resolution], responses=E)
async def list_resolutions(
    company: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Resolution]:
    """Newest first (M-0001 is the first resolution of the holding)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            RESOLUTION_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:q AS text) IS NULL OR r.ref = :q
                         OR core.fa_normalize(r.title || ' ' || r.body) LIKE '%' || core.fa_normalize(:q) || '%')
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (r.sealed_at, r.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY r.sealed_at DESC, r.id DESC LIMIT :lim""",
            companies=company,
            q=q,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("sealed_at", "id"))
    return Page(items=[_resolution(r) for r in items], next_cursor=nxt)


@router.get("/resolutions/{ref}", response_model=Resolution, responses=E)
async def get_resolution(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Resolution:
    async with ctx.tx() as tx:
        return _resolution(await tx.one(RESOLUTION_SQL + " WHERE r.ref = :ref", ref=ref))


@router.post("/resolutions", response_model=Resolution, status_code=201, responses=E)
async def record_resolution(
    body: ResolutionIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner records a resolution from a conversation (§1.1). It belongs to
    the message's company (or the holding) and is sent to the thread's agent."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=False)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        company_id, msg_id, sent_to, thread_code = holding.id, None, [], None
        if body.source_message:
            m = await tx.one(
                """SELECT m.id, m.company_id, t.code AS thread, e.code AS emp
                   FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
                   LEFT JOIN core.employees e ON e.id = t.employee_id WHERE m.ref = :r""",
                r=body.source_message,
            )
            company_id, msg_id, thread_code = m["company_id"], m["id"], m["thread"]
            sent_to = [m["emp"]] if m["emp"] else []
        res = await D.record_resolution(
            tx,
            ctx.who,
            company_id=company_id,
            title=body.title,
            body=body.body,
            message_id=msg_id,
            sent_to=sent_to,
        )
        await D.post_system_message(
            tx, thread_code, f"مصوبه‌ی {res['ref']} ثبت شد: {body.title}", {"resolution": res["ref"]}
        )
        await ctx.audit(
            tx,
            company_id=company_id,
            action="resolution.record",
            action_class="A2",
            target_kind="resolution",
            target_ref=res["ref"],
            summary=f"from {body.source_message or 'owner'}",
        )
        await ctx.interaction(
            tx,
            company_id=company_id,
            kind="decision",
            action="resolution.record",
            target_kind="resolution",
            target_ref=res["ref"],
            data={"title": body.title, "source_message": body.source_message},
        )
        result = _resolution(await tx.one(RESOLUTION_SQL + " WHERE r.id = :id", id=res["id"]))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result
