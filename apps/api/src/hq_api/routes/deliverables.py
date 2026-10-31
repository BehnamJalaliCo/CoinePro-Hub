"""The deliverables cartable (contract §5.2): outputs, owner ratings 1..10
with history, and file downloads (tenant-checked). ⟨1.7.3⟩ seen and filed:
the owner marks outputs seen (one or many) and files one in the archive.
⟨1.10⟩ §28.1: several filed at once, or deleted for good by the owner alone
(🔏; their ratings and files go with them, an Audit row stays, and archive
records they were filed into stay)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from hq_api import events, idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.domain import org, scoring, stories
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError, responses
from hq_api.schemas import EmployeeRef, FileRef, Model, Page, employee_ref
from hq_api.security import stepup

router = APIRouter(tags=["deliverables"])
log = logging.getLogger("hq_api.deliverables")
E = responses(401, 403, 404, 409, 422)
RERATE_DAYS = 7
REF = re.compile(r"^O-[0-9]{4,}$")


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
    # ⟨1.7.3⟩ report: the hub's own reporting (<CODE>-SYS); work: an agent's output
    category: Literal["report", "work"]
    seen_at: datetime | None
    filed_as: str | None


class SeenIn(Model):
    refs: list[str] = Field(min_length=1, max_length=500)
    seen: bool


class SeenOut(BaseModel):
    updated: int


class FiledOut(BaseModel):
    record: str


class RefsIn(Model):
    refs: list[str] = Field(min_length=1, max_length=200)

    @field_validator("refs")
    @classmethod
    def _refs(cls, v: list[str]) -> list[str]:
        bad = [r for r in v if not REF.fullmatch(r)]
        if bad:
            raise ValueError(f"not a deliverable ref: {bad[0][:20]}")
        return sorted(set(v))


class FiledRecord(BaseModel):
    ref: str
    record: str


class FiledMany(BaseModel):
    records: list[FiledRecord]


class DeletedOut(BaseModel):
    deleted: int


def delete_target(refs: list[str]) -> str:
    """The 🔏 target of `deliverables.delete`: SHA-256 (hex) of the sorted,
    distinct refs as a compact JSON array (`["O-000001","O-000002"]`)."""
    raw = json.dumps(sorted(set(refs)), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


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
                category=r["category"],
                seen_at=r["seen_at"],
                filed_as=r["filed_as"],
            )
        )
    return out


@router.get("/deliverables", response_model=Page[Deliverable], responses=E)
async def list_deliverables(
    company: list[str] | None = Query(default=None),
    producer: str | None = Query(default=None, max_length=40),
    unrated: bool | None = None,
    seen: bool | None = None,
    category: Literal["report", "work"] | None = None,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    q: str | None = Query(default=None, max_length=100),
    work: str | None = Query(
        default=None,
        pattern=r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|W-[0-9]{4,})$",
    ),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Deliverable]:
    """Newest first. ⟨1.7.3⟩ `seen`, `category`, and `from`/`to` (days in the
    owner's zone, both included). ⟨1.7.4⟩ `work`: one work's deliverables (its
    id or its ref)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        tz = await owner_tz(tx)
        work_id = None
        if work is not None:
            work_id = await tx.scalar(
                "SELECT id FROM work.work WHERE ref = :w OR id::text = lower(:w)", w=work
            )
            if work_id is None:  # no such work: nothing of it
                return Page(items=[], next_cursor=None)
        rows = await tx.all(
            DELIVERABLE_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:producer AS text) IS NULL OR p.code = :producer)
                    AND (CAST(:unrated AS boolean) IS NULL OR (lr.score IS NULL) = :unrated)
                    AND (CAST(:seen AS boolean) IS NULL OR (dl.seen_at IS NOT NULL) = :seen)
                    AND (CAST(:category AS text) IS NULL OR dl.category = :category)
                    AND (CAST(:from_day AS date) IS NULL
                         OR dl.created_at >= (CAST(:from_day AS date)::timestamp AT TIME ZONE :tz))
                    AND (CAST(:to_day AS date) IS NULL
                         OR dl.created_at < (CAST(:to_day AS date)::timestamp AT TIME ZONE :tz))
                    AND (CAST(:q AS text) IS NULL OR dl.ref = :q
                         OR core.fa_normalize(dl.title || ' ' || dl.summary)
                            LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                    AND (CAST(:work_id AS uuid) IS NULL OR dl.work_id = :work_id)
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (dl.created_at, dl.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY dl.created_at DESC, dl.id DESC LIMIT :lim""",
            companies=company,
            work_id=work_id,
            producer=producer,
            unrated=unrated,
            seen=seen,
            category=category,
            from_day=from_,
            to_day=(to + timedelta(days=1)) if to else None,
            tz=tz,
            q=q,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=await render(tx, items), next_cursor=nxt)


# ⟨1.7.3⟩ registered before /deliverables/{ref}, which would otherwise take the
# path (and answer 405 to a POST).
@router.post("/deliverables/seen", response_model=SeenOut, responses=E)
async def mark_seen(body: SeenIn, ctx: Ctx = Depends(owner_ctx)) -> SeenOut:
    """Owner: mark one or many deliverables seen (`seen: true`) or new again;
    idempotent (a deliverable already in that state is not counted)."""
    refs = sorted(set(body.refs))
    async with ctx.tx() as tx:
        rows = await tx.all(
            """UPDATE cartable.deliverables
                  SET seen_at = CASE WHEN :seen THEN now() ELSE NULL END
                WHERE ref = ANY(:refs) AND (seen_at IS NOT NULL) <> :seen
            RETURNING ref, company_id""",
            refs=refs,
            seen=body.seen,
        )
        if rows:
            holding = await ctx.hub.companies.holding()
            await ctx.audit(
                tx,
                company_id=holding.id,
                action="deliverable.seen" if body.seen else "deliverable.unseen",
                action_class="A1",
                target_kind="deliverable",
                target_ref=rows[0]["ref"] if len(rows) == 1 else f"{len(rows)} deliverables",
                summary=", ".join(r["ref"] for r in rows[:20]),
            )
    return SeenOut(updated=len(rows))


@router.post("/deliverables/file", response_model=FiledMany, responses=E)
async def file_many(body: RefsIn, ctx: Ctx = Depends(owner_ctx)) -> FiledMany:
    """⟨1.10⟩ §28.1 Owner: file several deliverables in the archive, each one
    as `/{ref}/file` does (idempotent per ref: a filed one answers its record)."""
    async with ctx.tx() as tx:
        rows = await tx.all(DELIVERABLE_SQL + " WHERE dl.ref = ANY(:refs)", refs=body.refs)
    missing = sorted(set(body.refs) - {r["ref"] for r in rows})
    if missing:
        raise ApiError(404, "not_found", f"no such deliverable: {', '.join(missing[:5])}")
    out = []
    for dl in sorted(rows, key=lambda r: r["ref"]):
        out.append(FiledRecord(ref=dl["ref"], record=await _file_one(ctx, dict(dl))))
    return FiledMany(records=out)


@router.delete("/deliverables", response_model=DeletedOut, responses=E)
async def delete_many(body: RefsIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> DeletedOut:
    """⟨1.10⟩ §28.1 Owner only, 🔏 `deliverables.delete` on the SHA-256 of the
    sorted refs (`delete_target`): the deliverables, their ratings, the files
    only they carried, the overseer's claims about them and a weekly letter
    made of one are removed from the database and the storage. An Audit row
    per deliverable stays ({ref, title, company, deleted_by, at}); archive
    records they were filed into stay. -> {deleted: n}."""
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "deliverables.delete", delete_target(body.refs))
        rows = await tx.all(
            """SELECT dl.id, dl.ref, dl.title, dl.company_id, c.code AS company
               FROM cartable.deliverables dl JOIN core.companies c ON c.id = dl.company_id
               WHERE dl.ref = ANY(:refs)""",
            refs=body.refs,
        )
        if not rows:
            return DeletedOut(deleted=0)
        out = await tx.scalar(
            "SELECT cartable.owner_delete_deliverables(CAST(:ids AS uuid[]))",
            ids=[str(r["id"]) for r in rows],
        )
        at = datetime.now().astimezone().isoformat()
        for r in rows:
            await ctx.audit(
                tx,
                company_id=r["company_id"],
                action="deliverable.delete",
                action_class="A3",
                target_kind="deliverable",
                target_ref=r["ref"],
                summary=json.dumps(
                    {
                        "ref": r["ref"],
                        "title": r["title"][:200],
                        "company": r["company"],
                        "deleted_by": ctx.who.code,
                        "at": at,
                    },
                    ensure_ascii=False,
                )[:1000],
                step_up=True,
            )
            await events.emit(tx, r["company"], "deliverable.deleted", r["ref"], {})
        keys = [str(k) for k in (out or {}).get("storage_keys") or []]
        gone = [
            k
            for k in keys
            if not await tx.scalar("SELECT 1 FROM files.files WHERE storage_key = :k", k=k)
        ]
    for k in gone:  # the blobs no row uses any more, after the commit
        try:
            await ctx.hub.storage.destroy(k)
        except (OSError, ValueError):
            log.warning("deliverable delete: a blob was not removed", extra={"key": k[:12]})
    return DeletedOut(deleted=len(rows))


async def _file_one(ctx: Ctx, dl: dict[str, Any]) -> str:
    from hq_api.archive import deliverables as AD

    record = await AD.file(ctx.hub, ctx.tx, ctx.who, dl)
    if record != dl["filed_as"]:
        async with ctx.tx() as tx:
            await ctx.audit(
                tx,
                company_id=dl["company_id"],
                action="deliverable.file",
                action_class="A1",
                target_kind="deliverable",
                target_ref=dl["ref"],
                summary=record,
            )
    return record


@router.post("/deliverables/{ref}/file", response_model=FiledOut, responses=E)
async def file_deliverable(ref: str, ctx: Ctx = Depends(owner_ctx)) -> FiledOut:
    """Owner: file the deliverable in the archive (§23): a draft of class
    `report` with the body as a PDF and a link `about` the deliverable. A
    second call answers the same record."""
    async with ctx.tx() as tx:
        dl = await tx.one(DELIVERABLE_SQL + " WHERE dl.ref = :ref", ref=ref)
    return FiledOut(record=await _file_one(ctx, dict(dl)))


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
        if body.score >= 9:  # ⟨1.4.3⟩ a 9 or a 10 is the company's story (§18.12), once
            await stories.system(
                tx,
                company_id=dl["company_id"],
                company_code=dl["company"],
                kind="deliverable",
                title_fa=f"خروجی {body.score} از ۱۰: {dl['title']}",
                body_fa=f"{dl['p_code']} · {dl['work_ref']}",
                figures=[{"label_fa": "امتیاز مالک", "value": str(body.score)}],
                links={"deliverable": ref, "employee": dl["p_code"], "work": dl["work_ref"]},
                event_key=f"deliverable:{ref}",
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
