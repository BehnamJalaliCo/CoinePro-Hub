"""The deliverables cartable (contract §5.2): outputs, owner ratings 1..10
with history, and file downloads (tenant-checked)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.domain import org, scoring
from hq_api.errors import ApiError, responses
from hq_api.schemas import EmployeeRef, FileRef, Model, Page, employee_ref

router = APIRouter(tags=["deliverables"])
E = responses(401, 403, 404, 409, 422)
RERATE_DAYS = 7


class Rating(BaseModel):
    score: int
    comment: str | None
    rated_at: datetime
    history_count: int


class Deliverable(BaseModel):
    id: UUID
    ref: str
    company: str
    work_id: UUID
    work_ref: str
    producer: EmployeeRef
    title: str
    summary: str
    body: str | None
    attachments: list[FileRef]
    produced_with: dict[str, Any]
    usage: dict[str, Any]
    evidence: list[dict[str, Any]]
    rating: Rating | None
    created_at: datetime


class RatingIn(Model):
    score: int = Field(ge=1, le=10)
    comment: str | None = Field(default=None, max_length=5000)


DELIVERABLE_SQL = f"""
    SELECT dl.*, c.code AS company, w.ref AS work_ref, {org.ref_cols("p", "p_")},
           lr.score AS r_score, lr.comment AS r_comment, lr.rated_at AS r_rated_at,
           (SELECT count(*) FROM cartable.ratings x WHERE x.deliverable_id = dl.id) AS r_count,
           (SELECT min(rated_at) FROM cartable.ratings x WHERE x.deliverable_id = dl.id) AS r_first
    FROM cartable.deliverables dl
    JOIN core.companies c ON c.id = dl.company_id
    JOIN work.work w ON w.id = dl.work_id
    JOIN core.employees p ON p.id = dl.producer_id
    LEFT JOIN LATERAL (SELECT score, comment, rated_at FROM cartable.ratings r
                       WHERE r.deliverable_id = dl.id ORDER BY version_no DESC LIMIT 1) lr ON true
"""  # noqa: S608 - composed from module constants; values are bound


async def files_of(tx: Tx, ids: list[UUID]) -> dict[UUID, FileRef]:
    return await F.refs(tx, ids)


async def render(tx: Tx, rows: list[dict[str, Any]]) -> list[Deliverable]:
    files = await files_of(tx, [f for r in rows for f in r["attachments"] or []])
    out = []
    for r in rows:
        producer = employee_ref(r, "p_")
        assert producer is not None
        out.append(
            Deliverable(
                id=r["id"],
                ref=r["ref"],
                company=r["company"],
                work_id=r["work_id"],
                work_ref=r["work_ref"],
                producer=producer,
                title=r["title"],
                summary=r["summary"],
                body=r["body"],
                attachments=[files[f] for f in r["attachments"] or [] if f in files],
                produced_with=r["produced_with"],
                usage=r["usage"],
                evidence=r["evidence"],
                rating=Rating(
                    score=r["r_score"],
                    comment=r["r_comment"],
                    rated_at=r["r_rated_at"],
                    history_count=r["r_count"],
                )
                if r["r_score"] is not None
                else None,
                created_at=r["created_at"],
            )
        )
    return out


@router.get("/deliverables", response_model=Page[Deliverable], responses=E)
async def list_deliverables(
    company: list[str] | None = Query(default=None),
    producer: str | None = Query(default=None, max_length=40),
    unrated: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Deliverable]:
    """Newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            DELIVERABLE_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:producer AS text) IS NULL OR p.code = :producer)
                    AND (CAST(:unrated AS boolean) IS NULL OR (lr.score IS NULL) = :unrated)
                    AND (CAST(:q AS text) IS NULL OR dl.ref = :q
                         OR core.fa_normalize(dl.title || ' ' || dl.summary)
                            LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (dl.created_at, dl.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY dl.created_at DESC, dl.id DESC LIMIT :lim""",
            companies=company,
            producer=producer,
            unrated=unrated,
            q=q,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=await render(tx, items), next_cursor=nxt)


@router.get("/deliverables/{ref}", response_model=Deliverable, responses=E)
async def get_deliverable(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Deliverable:
    """One deliverable with its attachments, usage, model label and latest rating."""
    async with ctx.tx() as tx:
        return (
            await render(tx, [await tx.one(DELIVERABLE_SQL + " WHERE dl.ref = :ref", ref=ref)])
        )[0]


@router.post("/deliverables/{ref}/rating", response_model=Deliverable, responses=E)
async def rate_deliverable(
    ref: str, body: RatingIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Owner rating 1..10 (+ optional comment). Re-rating within 7 days of the
    first rating adds a new version; the history is kept. The producer's score
    is recomputed. A delivered work becomes done. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        dl = await tx.one(DELIVERABLE_SQL + " WHERE dl.ref = :ref", ref=ref)
        # Deliverables are append-only (no UPDATE right, so no FOR UPDATE):
        # serialise ratings of one deliverable with a transaction-level lock.
        await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))", id=str(dl["id"]))
        if dl["r_first"] is not None:
            open_ = await tx.scalar(
                "SELECT :first > now() - make_interval(days => :days)",
                first=dl["r_first"],
                days=RERATE_DAYS,
            )
            if not open_:
                raise ApiError(
                    409, "validation_failed", f"re-rating is possible for {RERATE_DAYS} days only"
                )
        version = await tx.scalar(
            "SELECT COALESCE(max(version_no), 0) + 1 FROM cartable.ratings WHERE deliverable_id = :d",
            d=dl["id"],
        )
        await tx.exec(
            """INSERT INTO cartable.ratings (company_id, deliverable_id, version_no, score, comment, rated_by_code)
               VALUES (:co, :d, :v, :s, :c, :by)""",
            co=dl["company_id"],
            d=dl["id"],
            v=version,
            s=body.score,
            c=body.comment,
            by=ctx.who.code,
        )
        await tx.exec(
            "UPDATE work.work SET status = 'done', closed_at = now() WHERE id = :w AND status = 'delivered'",
            w=dl["work_id"],
        )
        dept = await tx.scalar(
            "SELECT department_id FROM core.employees WHERE id = :p", p=dl["producer_id"]
        )
        if dept is not None:
            await scoring.recompute_department(tx, dept)
        await ctx.audit(
            tx,
            company_id=dl["company_id"],
            action="deliverable.rate",
            action_class="A1",
            target_kind="deliverable",
            target_ref=ref,
            summary=f"score {body.score} (v{version})",
        )
        await ctx.interaction(
            tx,
            company_id=dl["company_id"],
            kind="rating",
            action="deliverable.rate",
            target_kind="deliverable",
            target_ref=ref,
            data={
                "score": body.score,
                "comment": body.comment,
                "version": version,
                "producer": dl["p_code"],
            },
        )
        await ctx.emit(
            tx, dl["company"], "deliverable.rated", ref, {"score": body.score, "version": version}
        )
        await ctx.emit(tx, dl["company"], "employee.updated", dl["p_code"], {"change": "score"})
        result = (
            await render(tx, [await tx.one(DELIVERABLE_SQL + " WHERE dl.id = :id", id=dl["id"])])
        )[0]
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result
