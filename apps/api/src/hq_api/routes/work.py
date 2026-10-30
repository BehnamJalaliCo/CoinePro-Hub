"""Work and the planner (contract §4). The planner is a view over work."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import org, recurrence, recurring
from hq_api.domain import players as PL
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.schemas import (
    DEPT_CODE,
    EMPLOYEE_CODE,
    EmployeeRef,
    Evidence,
    Model,
    Page,
    employee_ref,
)

router = APIRouter(tags=["work"])
E = responses(401, 403, 404, 409, 422)

Priority = Literal["P0", "P1", "P2", "P3", "P4"]
# ⟨1.7.4⟩ `owner`, or an agent's employee code
CREATED_BY = r"^(owner|[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?)$"
Status = Literal["queued", "in_progress", "waiting", "delivered", "done", "cancelled", "failed"]


class WorkCreate(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str | None = Field(default=None, pattern=DEPT_CODE)
    assignee: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
    )
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(default="", max_length=50000)
    kind: Literal["one_off", "recurring", "event", "project"] = "one_off"
    priority: Priority = "P3"
    due_at: datetime | None = None
    budget: W.BudgetIn | None = None
    escrow: W.EscrowIn | None = None
    schedule: W.ScheduleIn | None = None
    # ⟨1.5⟩ prompt 11 §5.3: the key result this work serves
    key_result: str | None = Field(default=None, pattern=r"^KR-[0-9]{4,}$")
    # ⟨1.9⟩ contract §27.1-§27.2: who plays it, and alone or as a council;
    # `media`: a council that makes images or video (each player its own)
    player: Literal["auto", "claude", "gpt", "gemini", "deepseek"] = "auto"
    mode: Literal["single", "council"] = "single"
    media: Literal["image", "video"] | None = None


class WorkPatch(Model):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    brief: str | None = Field(default=None, max_length=50000)
    priority: Priority | None = None
    due_at: datetime | None = None
    # ⟨1.9⟩ §27.1: a new player starts afresh (no wait, no fallback); a
    # council started on an open order runs from then on
    player: Literal["auto", "claude", "gpt", "gemini", "deepseek"] | None = None
    mode: Literal["single", "council"] | None = None


class Reason(Model):
    reason: str = Field(min_length=1, max_length=2000)


class Complete(Model):
    evidence: list[Evidence] = Field(min_length=1, max_length=50)


class ChainStep(BaseModel):
    id: UUID
    ref: str
    depth: int
    status: str
    assignee: EmployeeRef | None
    created_at: datetime
    tokens_used: int
    usd_used: float


class ChildWork(ChainStep):
    """⟨1.7.4⟩ prompt 15.1: a sub-work as the owner's order tracker shows it,
    with its own sub-works (two levels below the work at most)."""

    title: str
    updated_at: datetime
    # the latest /progress report, 0..1, or null (none yet)
    progress: float | None
    deliverable_refs: list[str]
    children: list[ChildWork] = Field(default_factory=list)


ChildWork.model_rebuild()


class WorkDetail(W.Work):
    chain: list[ChainStep]
    children: list[ChildWork]


class TreeEvent(BaseModel):
    """⟨1.7.4⟩ one event of a work's tree: a work event (`work.<kind>`) or an
    agent run's step (`run.step`, its summary and tool metadata only, §16)."""

    id: str
    at: datetime
    kind: str
    work_id: UUID
    work_ref: str
    depth: int
    actor_kind: str
    actor_code: str
    data: dict[str, Any]


class WorkEvent(BaseModel):
    id: int
    at: datetime
    kind: str
    actor_kind: str
    actor_code: str
    data: dict[str, Any]


class PlannerItem(BaseModel):
    ref: str
    title: str
    company: str
    status: str
    priority: str
    at: datetime
    assignee: str | None
    recurring: bool
    # ⟨1.4⟩ "reminder": a dated item of the owner's own (the assistant's
    # planner.add, contract §18.3), PL-…; it never wakes or escalates anyone.
    # ⟨1.5⟩ "meeting": a meeting MT-… (prompt 11 §1.10), its state as status;
    # "calendar": a change-calendar event CE-… (§9.4), its kind in calendar_kind.
    kind: Literal["work", "reminder", "meeting", "calendar"] = "work"
    note: str | None = None
    # ⟨1.5⟩ prompt 11: the work's key result (§5.3); a calendar event's kind (§9.4)
    key_result: str | None = None
    calendar_kind: str | None = None


class PlannerDay(BaseModel):
    date: date
    items: list[PlannerItem]


class Planner(BaseModel):
    scope: str
    timezone: str
    days: list[PlannerDay]


async def _detail(tx: Any, w: dict[str, Any]) -> WorkDetail:
    steps_sql = f"""
        SELECT w.id, w.ref, w.depth, w.status, w.created_at, w.tokens_used, w.usd_used,
               {org.ref_cols("a", "a_")}
        FROM work.work w LEFT JOIN core.employees a ON a.id = w.assignee_id
    """  # noqa: S608 - composed from module constants; values are bound
    chain = await tx.all(
        f"""WITH RECURSIVE up AS (
                SELECT id, parent_id, 0 AS n FROM work.work WHERE id = :id
                UNION ALL SELECT p.id, p.parent_id, up.n + 1 FROM work.work p JOIN up ON p.id = up.parent_id)
            {steps_sql} JOIN up ON up.id = w.id ORDER BY up.n DESC""",  # noqa: S608 - composed from module constants; values are bound
        id=w["id"],
    )
    # ⟨1.7.4⟩ the sub-works two levels down, each with its progress and
    # deliverables (one query; the tree is built here)
    below = await tx.all(
        f"""WITH RECURSIVE down AS (
                SELECT id, 1 AS lvl FROM work.work WHERE parent_id = :id
                UNION ALL SELECT c.id, down.lvl + 1 FROM work.work c JOIN down ON c.parent_id = down.id
                WHERE down.lvl < 2)
            SELECT w.id, w.ref, w.depth, w.status, w.created_at, w.tokens_used, w.usd_used,
                   w.title, w.updated_at, w.progress_pct, w.parent_id,
                   ARRAY(SELECT dl.ref FROM cartable.deliverables dl WHERE dl.work_id = w.id
                         ORDER BY dl.created_at) AS deliverable_refs,
                   {org.ref_cols("a", "a_")}
            FROM work.work w JOIN down ON down.id = w.id
            LEFT JOIN core.employees a ON a.id = w.assignee_id
            ORDER BY w.created_at, w.id""",  # noqa: S608 - composed from module constants; values are bound
        id=w["id"],
    )

    def step(r: dict[str, Any]) -> ChainStep:
        return ChainStep(
            id=r["id"],
            ref=r["ref"],
            depth=r["depth"],
            status=r["status"],
            assignee=employee_ref(r, "a_"),
            created_at=r["created_at"],
            tokens_used=r["tokens_used"],
            usd_used=float(r["usd_used"]),
        )

    def child(r: dict[str, Any]) -> ChildWork:
        pct = r["progress_pct"]
        return ChildWork(
            **step(r).model_dump(),
            title=r["title"],
            updated_at=r["updated_at"],
            progress=None if pct is None else max(0.0, min(1.0, pct / 100)),
            deliverable_refs=list(r["deliverable_refs"] or []),
            children=[child(x) for x in below if x["parent_id"] == r["id"]],
        )

    return WorkDetail(
        **W.render(w).model_dump(),
        chain=[step(r) for r in chain],
        children=[child(r) for r in below if r["parent_id"] == w["id"]],
    )


@router.get("/work", response_model=Page[W.Work], responses=E)
async def list_work(
    company: list[str] | None = Query(default=None),
    department: str | None = Query(default=None, pattern=DEPT_CODE),
    assignee: str | None = Query(default=None, pattern=EMPLOYEE_CODE),
    status: list[Status] | None = Query(default=None),
    kind: Literal["one_off", "recurring", "event", "project"] | None = None,
    priority: Priority | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    parent: UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    overdue: bool | None = None,
    created_by: str | None = Query(default=None, pattern=CREATED_BY),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[W.Work]:
    """Newest first. ⟨1.7.4⟩ `created_by=owner` (the owner's orders) or an
    agent's code."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            W.WORK_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:dept AS text) IS NULL OR d.code = :dept)
                    AND (CAST(:assignee AS text) IS NULL OR a.code = :assignee)
                    AND (CAST(:statuses AS text[]) IS NULL OR w.status = ANY(:statuses))
                    AND (CAST(:kind AS text) IS NULL OR w.kind = :kind)
                    AND (CAST(:prio AS text) IS NULL OR w.priority = :prio)
                    AND (CAST(:due_from AS timestamptz) IS NULL OR w.due_at >= :due_from)
                    AND (CAST(:due_to AS timestamptz) IS NULL OR w.due_at < :due_to)
                    AND (CAST(:parent AS uuid) IS NULL OR w.parent_id = :parent)
                    AND (CAST(:q AS text) IS NULL OR w.ref = :q
                         OR core.fa_normalize(w.title) LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                    AND (CAST(:overdue AS boolean) IS NULL
                         OR (w.due_at < now() AND w.status IN ('queued', 'in_progress', 'waiting')) = :overdue)
                    AND (CAST(:created_by AS text) IS NULL
                         OR (CAST(:created_by AS text) = 'owner' AND w.created_by_kind = 'owner')
                         OR (w.created_by_kind <> 'owner' AND w.created_by_code = :created_by))
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (w.created_at, w.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY w.created_at DESC, w.id DESC LIMIT :lim""",
            companies=company,
            dept=department,
            assignee=assignee,
            statuses=status,
            kind=kind,
            prio=priority,
            due_from=due_from,
            due_to=due_to,
            parent=parent,
            q=q,
            overdue=overdue,
            created_by=created_by,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[W.render(r) for r in items], next_cursor=nxt)


@router.get("/work/{id}", response_model=WorkDetail, responses=E)
async def get_work(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> WorkDetail:
    """Includes `chain`: the delegation path with time, assignee and usage of each step."""
    async with ctx.tx() as tx:
        return await _detail(tx, await W.load(tx, id))


@router.get("/work/{id}/events", response_model=Page[WorkEvent], responses=E)
async def work_events(
    id: UUID,
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[WorkEvent]:
    """Timeline, oldest first."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        await W.load(tx, id)
        rows = await tx.all(
            """SELECT id, at, kind, actor_kind, actor_code, data FROM work.work_events
               WHERE work_id = :w AND (CAST(:after AS bigint) IS NULL OR id > :after)
               ORDER BY id LIMIT :lim""",
            w=id,
            after=after[0] if after else None,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("id",))
    return Page(items=[WorkEvent(**r) for r in items], next_cursor=nxt)


@router.get("/work/{id}/tree-events", response_model=Page[TreeEvent], responses=E)
async def work_tree_events(
    id: UUID,
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[TreeEvent]:
    """⟨1.7.4⟩ The events of the work and of its sub-works (two levels down),
    oldest first: work events, and the steps of their agent runs as summaries
    and tool metadata only (§16), never a prompt, an output or a payload."""
    after = pagination.decode(cursor, 2)
    after_t = datetime.fromisoformat(str(after[0])) if after else None
    after_k = str(after[1]) if after else None
    async with ctx.tx() as tx:
        await W.load(tx, id)
        rows = await tx.all(
            """WITH RECURSIVE tree AS (
                   SELECT id, 0 AS lvl FROM work.work WHERE id = :id
                   UNION ALL SELECT c.id, tree.lvl + 1 FROM work.work c JOIN tree ON c.parent_id = tree.id
                   WHERE tree.lvl < 2),
               ev AS (
                   SELECT 'e' || lpad(e.id::text, 19, '0') AS key, e.at, 'work.' || e.kind AS kind,
                          w.id AS work_id, w.ref AS work_ref, w.depth, e.actor_kind, e.actor_code,
                          e.data
                   FROM work.work_events e JOIN tree ON tree.id = e.work_id
                   JOIN work.work w ON w.id = e.work_id
                   UNION ALL
                   SELECT 's' || lpad(s.id::text, 19, '0'), s.at, 'run.step', w.id, w.ref, w.depth,
                          'agent', coalesce(emp.code, ''),
                          jsonb_build_object(
                              'run_id', r.id, 'n', s.n, 'summary_fa', s.summary_fa,
                              'actions', coalesce((
                                  SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                                      'tool', a->'tool', 'class', a->'class',
                                      'outcome', a->'outcome', 'ref', a->'ref')))
                                  FROM jsonb_array_elements(s.actions) a), '[]'::jsonb))
                   FROM agents.steps s JOIN agents.runs r ON r.id = s.run_id
                   JOIN tree ON tree.id = r.work_id
                   JOIN work.work w ON w.id = r.work_id
                   LEFT JOIN core.employees emp ON emp.id = r.employee_id)
               SELECT * FROM ev
               WHERE CAST(:after_t AS timestamptz) IS NULL
                  OR (at, key) > (CAST(:after_t AS timestamptz), CAST(:after_k AS text))
               ORDER BY at, key LIMIT :lim""",
            id=id,
            after_t=after_t,
            after_k=after_k,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("at", "key"))
    return Page(
        items=[
            TreeEvent(
                id=r["key"],
                at=r["at"],
                kind=r["kind"],
                work_id=r["work_id"],
                work_ref=r["work_ref"],
                depth=r["depth"],
                actor_kind=r["actor_kind"],
                actor_code=r["actor_code"],
                data=dict(r["data"] or {}),
            )
            for r in items
        ],
        next_cursor=nxt,
    )


@router.post("/work", response_model=W.Work, status_code=201, responses=E)
async def create_work(body: WorkCreate, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner's order. Without `assignee` it goes to the CEO, or straight to
    the department's manager when `department` is given (the shortcut, depth 1).
    Recurring work needs `escrow` and `schedule`; the owner's is active at once.
    Requires `Idempotency-Key`."""
    co = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        w = await W.create(
            tx,
            ctx.who,
            company_id=co.id,
            company_code=co.code,
            title=body.title,
            brief=body.brief,
            kind=body.kind,
            priority=body.priority,
            department_code=body.department,
            assignee_code=body.assignee,
            due_at=body.due_at,
            budget=body.budget,
            escrow=body.escrow,
            schedule=body.schedule,
            key_result=body.key_result,
            player=body.player,
            mode=body.mode,
            media=body.media,
        )
        if body.mode == "council":  # ⟨1.9⟩ §27.2: every ready player, then Claude's synthesis
            await PL.start_council(tx, ctx.hub, w)
            w = await W.load(tx, w["id"])
        if body.kind == "recurring":
            await recurring.activate(tx, w, ctx.who)
            w = await W.load(tx, w["id"])
        await ctx.audit(
            tx,
            company_id=co.id,
            action="work.create",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"{body.kind} {body.priority} to {w['a_code']}"
            + (f"; player {body.player}" if body.player != "auto" else "")
            + (f"; {body.mode}" if body.mode != "single" else ""),
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="order",
            action="work.create",
            target_kind="work",
            target_ref=w["ref"],
            data={
                "kind": body.kind,
                "priority": body.priority,
                "assignee": w["a_code"],
                "title": body.title,
            },
        )
        result = W.render(w)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.patch(
    "/work/{id}", response_model=W.Work, responses=responses(401, 403, 404, 409, 422, 428)
)
async def update_work(
    id: UUID, body: WorkPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> W.Work:
    """`title, brief, priority, due_at`. Requires `If-Match: <version>`."""
    expected = if_match(request)
    fields = body.model_dump(exclude_unset=True)
    async with ctx.tx() as tx:
        w = await W.load(tx, id, lock=True)
        check_version(w["version"], expected)
        if w["status"] in W.CLOSED:
            raise ApiError(409, "validation_failed", "the work is closed")
        fields = {k: v for k, v in fields.items() if v is not None or k in ("due_at",)}
        if fields:
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            await tx.exec(f"UPDATE work.work SET {sets} WHERE id = :id", id=id, **fields)  # noqa: S608
        if "player" in fields and fields["player"] != w["player"]:
            await tx.exec(
                """UPDATE work.work SET player_wait_since = NULL, player_tried_at = NULL,
                       player_fallback_at = NULL WHERE id = :id""",
                id=id,
            )
        if fields.get("mode") == "council" and w["mode"] != "council" and w["parent_id"] is None:
            await PL.start_council(tx, ctx.hub, await W.load(tx, id))
        await W.event(tx, w, "updated", ctx.who, {"fields": sorted(fields)})
        await ctx.audit(
            tx,
            company_id=w["company_id"],
            action="work.update",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary="fields: " + ",".join(sorted(fields)),
        )
        await ctx.interaction(
            tx,
            company_id=w["company_id"],
            kind="edit",
            action="work.update",
            target_kind="work",
            target_ref=w["ref"],
            data={"fields": sorted(fields)},
        )
        await ctx.emit(tx, w["company"], "work.updated", w["ref"], {"fields": sorted(fields)})
        return W.render(await W.load(tx, id))


@router.get("/work/{id}/council", response_model=PL.Council, responses=E)
async def work_council(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> PL.Council:
    """⟨1.9⟩ contract §27.2: the council of an order: each member (Claude and
    every substitute player: its state, run, deliverable or creative, or why
    it was skipped), the synthesis and the council's state. 404 for a work
    that runs alone."""
    async with ctx.tx() as tx:
        c = await PL.council_of(tx, id)
        if c is None:
            raise ApiError(404, "not_found", "this work has no council")
        await PL.refresh(tx, ctx.hub, c)
        c = await PL.council_of(tx, id)
        assert c is not None
        return PL.render(c)


@router.post("/work/{id}/cancel", response_model=W.Work, responses=E)
async def cancel_work(id: UUID, body: Reason, ctx: Ctx = Depends(owner_ctx)) -> W.Work:
    """Cancels the work and every open item under it."""
    async with ctx.tx() as tx:
        w = await W.load(tx, id, lock=True)
        if w["status"] in W.CLOSED:
            raise ApiError(409, "validation_failed", f"the work is already {w['status']}")
        rows = await tx.all(
            """WITH RECURSIVE down AS (
                   SELECT id FROM work.work WHERE id = :id
                   UNION ALL SELECT c.id FROM work.work c JOIN down ON c.parent_id = down.id)
               UPDATE work.work SET status = 'cancelled', close_reason = :r, closed_at = now()
               WHERE id IN (SELECT id FROM down) AND status NOT IN ('done', 'cancelled', 'failed')
               RETURNING ref""",
            id=id,
            r=body.reason,
        )
        await tx.exec("UPDATE work.schedules SET status = 'ended' WHERE work_id = :id", id=id)
        await W.event(
            tx, w, "cancelled", ctx.who, {"reason": body.reason, "cascade": len(rows) - 1}
        )
        await ctx.audit(
            tx,
            company_id=w["company_id"],
            action="work.cancel",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"cancelled with {len(rows) - 1} open children",
        )
        await ctx.interaction(
            tx,
            company_id=w["company_id"],
            kind="order",
            action="work.cancel",
            target_kind="work",
            target_ref=w["ref"],
            data={"reason": body.reason},
        )
        for r in rows:
            await ctx.emit(tx, w["company"], "work.updated", r["ref"], {"status": "cancelled"})
        return W.render(await W.load(tx, id))


@router.post("/work/{id}/complete", response_model=W.Work, responses=E)
async def complete_work(id: UUID, body: Complete, ctx: Ctx = Depends(owner_ctx)) -> W.Work:
    """The owner closes the work with evidence (a tick needs evidence, §1.9)."""
    async with ctx.tx() as tx:
        w = await W.load(tx, id, lock=True)
        if w["status"] in W.CLOSED:
            raise ApiError(409, "validation_failed", f"the work is already {w['status']}")
        await tx.exec(
            """UPDATE work.work SET evidence = evidence || CAST(:ev AS jsonb), status = 'done', closed_at = now()
               WHERE id = :id""",
            id=id,
            ev=W.evidence_json(body.evidence),
        )
        await W.event(tx, w, "completed", ctx.who, {"evidence": len(body.evidence)})
        await ctx.audit(
            tx,
            company_id=w["company_id"],
            action="work.complete",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"closed with {len(body.evidence)} evidence item(s)",
        )
        await ctx.interaction(
            tx,
            company_id=w["company_id"],
            kind="order",
            action="work.complete",
            target_kind="work",
            target_ref=w["ref"],
        )
        await ctx.emit(tx, w["company"], "work.completed", w["ref"], {"by": "owner"})
        return W.render(await W.load(tx, id))


@router.get("/planner", response_model=Planner, responses=E)
async def planner(
    scope: str = Query(
        default="owner",
        pattern=r"^(owner|company:[A-Z][A-Z0-9]{1,9}|department:[A-Z][A-Z0-9]{1,9}-[A-Z][A-Z0-9]{1,11})$",
    ),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Planner:
    """Days with work due and recurring occurrences, in the owner's time zone.
    A view over work, not separate data (§1.9). At most 62 days."""
    async with ctx.tx() as tx:
        tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
        z = recurrence.zone(tz)
        today = datetime.now(z).date()
        start_d = from_ or today
        end_d = to or (start_d + timedelta(days=7))
        if end_d < start_d or (end_d - start_d).days > 62:
            raise ApiError(422, "validation_failed", fields={"to": "range must be 0..62 days"})
        start = datetime.combine(start_d, time.min, z).astimezone(UTC)
        end = datetime.combine(end_d + timedelta(days=1), time.min, z).astimezone(UTC)
        company_code = dept_code = None
        if scope.startswith("company:"):
            company_code = scope.split(":", 1)[1]
        elif scope.startswith("department:"):
            company_code, dept_code = scope.split(":", 1)[1].split("-", 1)
        filters = """ AND (CAST(:co AS text) IS NULL OR c.code = :co)
                      AND (CAST(:dept AS text) IS NULL OR d.code = :dept)"""
        due = await tx.all(
            W.WORK_SQL
            + " WHERE w.due_at >= :s AND w.due_at < :e AND w.kind <> 'recurring'"
            + filters
            + " ORDER BY w.due_at",
            s=start,
            e=end,
            co=company_code,
            dept=dept_code,
        )
        templates = await tx.all(
            W.WORK_SQL + " WHERE w.kind = 'recurring' AND sc.status = 'active'" + filters,
            co=company_code,
            dept=dept_code,
        )
        reminders = await tx.all(
            """SELECT p.ref, p.title_fa, p.at, p.note, c.code AS company FROM owner.planner_items p
               JOIN core.companies c ON c.id = p.company_id
               WHERE p.at >= :s AND p.at < :e ORDER BY p.at LIMIT 500""",
            s=start,
            e=end,
        )
        # ⟨1.5⟩ the meetings (prompt 11 §1.10): the planner stays a view over data
        meetings = await tx.all(
            """SELECT m.ref, m.title_fa, m.starts_at, m.state, m.type, m.department, c.code AS company
               FROM meetings.meetings m JOIN core.companies c ON c.id = m.company_id
               WHERE m.starts_at >= :s AND m.starts_at < :e AND m.state <> 'cancelled' AND m.type <> 'standup'
                 AND (CAST(:co AS text) IS NULL OR c.code = :co)
                 AND (CAST(:dept AS text) IS NULL OR m.department = :dept)
               ORDER BY m.starts_at LIMIT 500""",
            s=start,
            e=end,
            co=company_code,
            dept=dept_code,
        )
        # ⟨1.5⟩ prompt 11 §9.4: the change calendar's events (the planner stays a view;
        # a meeting's own event is left out, the meeting above is its row)
        calendar = await tx.all(
            """SELECT e.ref, e.title_fa, e.starts_at, e.kind, e.status, c.code AS company
               FROM governance.calendar_events e JOIN core.companies c ON c.id = e.company_id
               WHERE e.starts_at >= :s AND e.starts_at < :e AND e.status <> 'cancelled'
                 AND e.kind <> 'meeting'
                 AND (CAST(:co AS text) IS NULL OR c.code = :co OR c.kind = 'holding')
               ORDER BY e.starts_at LIMIT 500""",
            s=start,
            e=end,
            co=company_code,
        )
    items: list[PlannerItem] = [
        PlannerItem(
            ref=r["ref"],
            title=r["title"],
            company=r["company"],
            status=r["status"],
            priority=r["priority"],
            at=r["due_at"],
            assignee=r["a_code"],
            recurring=r["recurrence_of"] is not None,
            key_result=r.get("key_result_ref"),
        )
        for r in due
    ]
    for t in templates:
        rule = recurrence.parse(t["sc_rrule"])
        for at in recurrence.occurrences(rule, t["sc_timezone"], start, end, limit=200):
            if t["es_expires_at"] and at > t["es_expires_at"]:
                break
            items.append(
                PlannerItem(
                    ref=t["ref"],
                    title=t["title"],
                    company=t["company"],
                    status="scheduled",
                    priority=t["priority"],
                    at=at,
                    assignee=t["a_code"],
                    recurring=True,
                )
            )
    if scope == "owner":
        for r in reminders:
            items.append(
                PlannerItem(
                    ref=r["ref"],
                    title=r["title_fa"],
                    company=r["company"],
                    status="reminder",
                    priority="P3",
                    at=r["at"],
                    assignee=None,
                    recurring=False,
                    kind="reminder",
                    note=r["note"],
                )
            )
    for m in meetings:
        items.append(
            PlannerItem(
                ref=m["ref"],
                title=m["title_fa"],
                company=m["company"],
                status=m["state"],
                priority="P0" if m["type"] == "war_room" else "P2",
                at=m["starts_at"],
                assignee=None,
                recurring=m["type"] in ("board", "company", "strategy"),
                kind="meeting",
                note=m["type"],
            )
        )
    if dept_code is None:
        for r in calendar:
            items.append(
                PlannerItem(
                    ref=r["ref"],
                    title=r["title_fa"],
                    company=r["company"],
                    status=r["status"],
                    priority="P3",
                    at=r["starts_at"],
                    assignee=None,
                    recurring=False,
                    kind="calendar",
                    calendar_kind=r["kind"],
                )
            )
    days: dict[date, list[PlannerItem]] = {}
    for it in sorted(items, key=lambda i: i.at):
        days.setdefault(it.at.astimezone(z).date(), []).append(it)
    return Planner(
        scope=scope,
        timezone=tz,
        days=[PlannerDay(date=d, items=days[d]) for d in sorted(days)],
    )
