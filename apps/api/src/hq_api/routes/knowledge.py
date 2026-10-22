"""The four-layer knowledge base (prompt 11 §3, contract §20.3).

Owner (/api/v1):
  GET  /knowledge          ?layer&company&department&kind&status&q&include_expired (Page)
  GET  /knowledge/{ref} · /knowledge/{ref}/versions      K-… entries and KB-… support articles
  POST /knowledge · PUT /knowledge/{ref}                 the owner's entry or new version: approved by that act
  POST /knowledge/{ref}/retire
  A support article (KB-…) is read here, edited only at /support/kb: 405.
Agents (/internal/v1, behind the Tool Gateway):
  POST /knowledge                   knowledge.propose (A1)
  POST /knowledge/{ref}/review      knowledge.review  (A2: the overseer, AI safety)
  POST /knowledge/{ref}/approve     knowledge.approve (A2: the CEO, its own company)
  (knowledge.search kind `knowledge`: routes/agent_tools.py)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import knowledge as K
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model, Page

router = APIRouter(tags=["knowledge"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 405, 409, 422, 423)
REF = r"^(K-[0-9]{4,}|KB-[0-9]{4,6})$"
K_ONLY = r"^K-[0-9]{4,}$"


def _not_here(ref: str) -> None:
    if ref.startswith("KB-"):
        raise ApiError(
            405,
            "validation_failed",
            "a support article is edited and sealed at /support/kb only",
            headers={"Allow": "GET"},
        )


# ------------------------------------------------------------------ owner --
@router.get("/knowledge", response_model=Page[K.KnowledgeEntry], responses=E)
async def list_knowledge(
    layer: Literal["holding", "company", "department", "employee"] | None = None,
    company: str | None = Query(default=None, pattern=CODE),
    department: str | None = Query(default=None, pattern=K.DEPT),
    kind: Literal["principle", "policy", "fact", "faq", "playbook", "support"] | None = None,
    status: Literal["draft", "in_review", "approved", "expired", "retired"] | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=200),
    include_expired: bool = False,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[K.KnowledgeEntry]:
    """Every layer the owner may read (all): the entries, the support articles
    (kind support, read-only) and, for layer=employee, the employees' memory.
    Expired entries only with include_expired (or status=expired)."""
    after_t, after_id = pagination.time_id(cursor)
    hide_expired = not include_expired and status not in ("expired",)
    rows: list[dict[str, Any]] = []
    async with ctx.tx() as tx:
        pat = None
        if q:
            pat = (
                "%"
                + str(await tx.scalar("SELECT core.like_escape(core.fa_normalize(:q))", q=q))
                + "%"
            )
        if layer == "employee":
            mem = await tx.all(
                """SELECT m.id, m.note, m.run_id, m.created_at, e.code AS employee, c.code AS company,
                          d.code AS department
                   FROM core.employee_memory m JOIN core.employees e ON e.id = m.employee_id
                   JOIN core.companies c ON c.id = m.company_id LEFT JOIN core.departments d ON d.id = e.department_id
                   WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                     AND (CAST(:dept AS text) IS NULL OR d.code = :dept)
                     AND (CAST(:pat AS text) IS NULL OR core.fa_normalize(m.note) LIKE :pat)
                     AND (CAST(:after_t AS timestamptz) IS NULL OR m.created_at < CAST(:after_t AS timestamptz))
                   ORDER BY m.created_at DESC LIMIT :lim""",
                co=company,
                dept=department,
                pat=pat,
                after_t=after_t,
                lim=limit + 1,
            )
            items = [K.render_memory(r) for r in mem[:limit]]
            nxt = (
                pagination.encode([mem[limit - 1]["created_at"], items[-1].id])
                if len(mem) > limit
                else None
            )
            return Page(items=items, next_cursor=nxt)
        filters = """ AND (CAST(:layer AS text) IS NULL OR x.layer = :layer)
                      AND (CAST(:co AS text) IS NULL OR c.code = :co)
                      AND (CAST(:dept AS text) IS NULL OR x.department = :dept)
                      AND (CAST(:status AS text) IS NULL OR x.status = :status)
                      AND (NOT :hide OR x.status <> 'expired')
                      AND (CAST(:pat AS text) IS NULL OR x.search LIKE :pat)
                      AND (CAST(:after_t AS timestamptz) IS NULL
                           OR (x.updated_at, x.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))"""
        params: dict[str, Any] = {
            "layer": layer,
            "co": company,
            "dept": department,
            "status": status,
            "hide": hide_expired,
            "pat": pat,
            "after_t": after_t,
            "after_id": after_id,
            "lim": limit + 1,
        }
        if kind != "support":
            rows += await tx.all(
                """SELECT x.*, c.code AS company FROM knowledge.entries x JOIN core.companies c ON c.id = x.company_id
                   WHERE (CAST(:kind AS text) IS NULL OR x.kind = :kind)"""  # noqa: S608 - module constants
                + filters
                + " ORDER BY x.updated_at DESC, x.id DESC LIMIT :lim",
                kind=kind,
                **params,
            )
        if kind in (None, "support") and layer in (None, "company") and department is None:
            rows += await tx.all(
                """SELECT x.*, c.code AS company FROM knowledge.support_entries x
                   JOIN core.companies c ON c.id = x.company_id WHERE true"""  # noqa: S608 - module constants
                + filters
                + " ORDER BY x.updated_at DESC, x.id DESC LIMIT :lim",
                **params,
            )
    rows.sort(key=lambda r: (r["updated_at"], str(r["id"])), reverse=True)
    page = rows[:limit]
    nxt = (
        pagination.encode([page[-1]["updated_at"], page[-1]["id"]])
        if len(rows) > limit and page
        else None
    )
    return Page(items=[K.render(r) for r in page], next_cursor=nxt)


async def _one(ctx: Ctx, ref: str) -> dict[str, Any]:
    async with ctx.tx() as tx:
        return await (K.load_support(tx, ref) if ref.startswith("KB-") else K.load(tx, ref))


@router.get("/knowledge/{ref}", response_model=K.KnowledgeEntry, responses=E)
async def get_knowledge(
    ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> K.KnowledgeEntry:
    """The approved version (else the latest) of an entry or a support article."""
    return K.render(await _one(ctx, ref))


@router.get("/knowledge/{ref}/versions", response_model=list[K.KnowledgeEntry], responses=E)
async def knowledge_versions(
    ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> list[K.KnowledgeEntry]:
    """Every version of an entry or a support article, newest first."""
    async with ctx.tx() as tx:
        if ref.startswith("KB-"):
            rows = await tx.all(K.SUPPORT_SQL + " WHERE s.ref = :r ORDER BY s.version DESC", r=ref)
        else:
            rows = await tx.all(K.ENTRY_SQL + " WHERE e.ref = :r ORDER BY e.version DESC", r=ref)
    if not rows:
        raise ApiError(404, "not_found", f"no knowledge entry {ref}")
    return [K.render(r) for r in rows]


async def _owner_write(
    ctx: Ctx, request: Request, body: K.KnowledgeEntryIn, ref: str | None
) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        row = await K.create(tx, ctx.who, body, ref=ref)
        await ctx.audit(
            tx, company_id=row["company_id"], action="knowledge.write", action_class="A2", target_kind="knowledge",
            target_ref=f"{row['ref']}@{row['version']}", summary=f"{row['layer']} {row['kind']} approved by the owner",
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="knowledge.write", target_kind="knowledge",
            target_ref=f"{row['ref']}@{row['version']}",
        )  # fmt: skip
        out = K.render(row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post("/knowledge", response_model=K.KnowledgeEntry, status_code=201, responses=E)
async def create_knowledge(
    body: K.KnowledgeEntryIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner's entry: approved by that act (sources and an expiry within the
    kind's limit are required: 422)."""
    return await _owner_write(ctx, request, body, None)


@router.put("/knowledge/{ref}", response_model=K.KnowledgeEntry, status_code=201, responses=E)
async def update_knowledge(
    body: K.KnowledgeEntryIn,
    request: Request,
    ref: str = Path(pattern=REF),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """A new version of an entry, approved by the owner's act (the version
    before it retires). A support article: 405 (edit it at /support/kb)."""
    _not_here(ref)
    return await _owner_write(ctx, request, body, ref)


@router.post("/knowledge/{ref}/retire", response_model=K.KnowledgeEntry, responses=E)
async def retire_knowledge(
    ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> K.KnowledgeEntry:
    """The owner retires an entry (every version); a support article: 405."""
    _not_here(ref)
    async with ctx.tx() as tx:
        row = await K.retire(tx, ctx.who, ref)
        await ctx.audit(
            tx, company_id=row["company_id"], action="knowledge.retire", action_class="A2", target_kind="knowledge",
            target_ref=ref,
        )  # fmt: skip
    return K.render(row)


# ----------------------------------------------------------------- agents --
class KnowledgeProposeIn(Model):
    layer: Literal["holding", "company", "department"]
    company: str | None = Field(default=None, pattern=CODE)
    department: str | None = Field(default=None, pattern=K.DEPT)
    kind: Literal["principle", "policy", "fact", "faq", "playbook"]
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=20000)
    sources: list[K.KnowledgeSource] = Field(min_length=1, max_length=20)
    valid_until: date
    ref: str | None = Field(default=None, pattern=K_ONLY)


class KnowledgeReviewIn(Model):
    version: int = Field(ge=1)
    verdict: Literal["pass", "changes", "reject"]
    checks: K.KnowledgeChecks
    notes_md: str = Field(default="", max_length=4000)


class KnowledgeApproveIn(Model):
    version: int = Field(ge=1)


def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


def _root(ctx: Ctx) -> str:
    lib = ctx.hub.charters
    return str(lib.root) if lib is not None else "/app/agents"


@internal_router.post("/knowledge", response_model=K.KnowledgeEntry, status_code=201, responses=E)
async def agent_propose_knowledge(
    body: KnowledgeProposeIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """knowledge.propose: an entry (or a new version of `ref`) of the agent's
    own company (a holding entry: the holding's roles), to review."""
    _agent(ctx)
    company = body.company or ctx.who.company
    await allow(
        ctx,
        "knowledge.propose",
        {"company": company, "layer": body.layer, "charter": ctx.who.charter},
    )
    entry = K.KnowledgeEntryIn(
        layer=body.layer, company=company or "", department=body.department, kind=body.kind,
        title_fa=body.title_fa, body_md=body.body_md, sources=body.sources, valid_until=body.valid_until,
    )  # fmt: skip
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        row = await K.create(tx, ctx.who, entry, ref=body.ref)
        await ctx.audit(
            tx, company_id=row["company_id"], action="knowledge.propose", action_class="A1",
            target_kind="knowledge", target_ref=f"{row['ref']}@{row['version']}",
            summary=f"{row['layer']} {row['kind']}",
        )  # fmt: skip
        out = K.render(row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


async def _visible(ctx: Ctx, tx: Any, ref: str, version: int) -> dict[str, Any]:
    """The entry under the agent's own RLS: another company's is a 403, the
    same as one that does not exist (prompt 11 §3: no leak)."""
    try:
        return await K.load(tx, ref, version, lock=True)
    except ApiError as exc:
        raise ApiError(403, "policy_denied", "not a knowledge entry you may act on") from exc


@internal_router.post("/knowledge/{ref}/review", response_model=K.KnowledgeEntry, responses=E)
async def agent_review_knowledge(
    body: KnowledgeReviewIn,
    request: Request,
    ref: str = Path(pattern=K_ONLY),
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """knowledge.review (the overseer, AI safety; any company): code's checks
    first (injection, secrets, a rule red line); a failed one is `reject`."""
    _agent(ctx)
    await allow(ctx, "knowledge.review", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        await _visible(ctx, tx, ref, body.version)
        row = await K.review(
            tx, ctx.who, ref, body.version, verdict=body.verdict, checks=body.checks.model_dump(),
            notes_md=body.notes_md, root=_root(ctx),
        )  # fmt: skip
        await ctx.audit(
            tx, company_id=row["company_id"], action="knowledge.review", action_class="A2", target_kind="knowledge",
            target_ref=f"{ref}@{body.version}", summary=str((row.get("review") or {}).get("verdict")),
        )  # fmt: skip
        out = K.render(row)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@internal_router.post("/knowledge/{ref}/approve", response_model=K.KnowledgeEntry, responses=E)
async def agent_approve_knowledge(
    body: KnowledgeApproveIn,
    request: Request,
    ref: str = Path(pattern=K_ONLY),
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """knowledge.approve: a CEO, a company or department entry of its own
    company after a passing review (an authority-matrix row the owner may
    take back: then OPA refuses)."""
    _agent(ctx)
    async with ctx.tx() as tx:
        entry = await _visible(ctx, tx, ref, body.version)
    await allow(ctx, "knowledge.approve", {"company": entry["company"], "layer": entry["layer"]})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        row = await K.approve(tx, ctx.who, ref, body.version)
        await ctx.audit(
            tx, company_id=row["company_id"], action="knowledge.approve", action_class="A2", target_kind="knowledge",
            target_ref=f"{ref}@{body.version}",
        )  # fmt: skip
        out = K.render(row)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out
