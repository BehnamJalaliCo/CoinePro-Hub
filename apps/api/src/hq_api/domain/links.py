"""Company links and the owner's canvas (contract §35.6), the owner, 2026-11-06: «شرکت ها به هم دیگه
ارتباط داشته باشند و همه به هاب و بتونم این ارتباط هارو شکل بدم».

A link is a directed line between two companies (`serves`, `publishes`, `feeds`, `sells`,
`supports`) with the owner's one-line purpose, `on` or `off` (nothing is deleted). Every company is
linked to the hub (the holding node) implicitly: no row is kept for that. The canvas is the nodes
(every active company and the holding, where the owner put them, one plain line of what each is
doing) and the links (with the works open along each).

Honoured: the secretary's preview suggests collaborators along `on` links that fit the order; with
`owner.settings.links_enforced` on, a cross-company request of an agent along an `on` link is
accepted (OPA `work_create_ok`); `company.state` lists a company's links.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import CODE, Model

LinkKind = Literal["serves", "publishes", "feeds", "sells", "supports"]
LinkState = Literal["on", "off"]
KINDS: tuple[str, ...] = ("serves", "publishes", "feeds", "sells", "supports")
KIND_FA = {
    "serves": "خدمت میدهد به",
    "publishes": "منتشر میکند برای",
    "feeds": "داده میدهد به",
    "sells": "میفروشد برای",
    "supports": "پشتیبانی میکند از",
}
# The kind that fits an order's output (the secretary's suggestion): content that goes out is
# publishing, a report is data, the rest serves. A sales or support department fits its own kind.
KIND_OF_OUTPUT = {
    "post": "publishes",
    "reel": "publishes",
    "story": "publishes",
    "article": "publishes",
    "report": "feeds",
}
KIND_OF_DEPARTMENT = {"SALES": "sells", "SUPPORT": "supports"}
SUGGESTED_MAX = 3
OPEN = ("queued", "in_progress", "waiting")
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class CanvasNode(BaseModel):
    code: str
    name_fa: str
    kind: Literal["holding", "company"]
    x: float | None = None
    y: float | None = None
    line_fa: str
    open_sessions: int


class CompanyLink(BaseModel):
    id: UUID
    from_: str = Field(serialization_alias="from", validation_alias="from")
    to: str
    kind: LinkKind
    purpose_fa: str
    state: LinkState
    open_works: int
    updated_at: datetime

    model_config = {"populate_by_name": True}


class Canvas(BaseModel):
    nodes: list[CanvasNode]
    links: list[CompanyLink]


class LinkIn(Model):
    from_: str = Field(alias="from", pattern=CODE)
    to: str = Field(pattern=CODE)
    kind: LinkKind
    purpose_fa: str = Field(default="", max_length=200)


class LinkPatch(Model):
    kind: LinkKind | None = None
    purpose_fa: str | None = Field(default=None, max_length=200)
    state: LinkState | None = None


class NodePlace(Model):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


def fa(n: int) -> str:
    return str(n).translate(_FA_DIGITS)


def line_of(open_works: int, open_sessions: int) -> str:
    """One plain Persian line of a company's state: what is open now."""
    if not open_works and not open_sessions:
        return "کار بازی ندارد"
    parts = []
    if open_works:
        parts.append(f"{fa(open_works)} کار باز")
    if open_sessions:
        parts.append(f"{fa(open_sessions)} فرمان تو در جریان")
    return "؛ ".join(parts)


# ----------------------------------------------------------------- reads --
_LINK_SQL = """SELECT l.id, f.code AS from_code, t.code AS to_code, l.from_company_id,
                      l.to_company_id, l.kind, l.purpose_fa, l.state, l.updated_at
               FROM core.company_links l
               JOIN core.companies f ON f.id = l.from_company_id
               JOIN core.companies t ON t.id = l.to_company_id"""


async def _open_between(tx: Tx) -> dict[frozenset[UUID], int]:
    """Open works that one company asked of the other (requested_by_work_id), by pair."""
    rows = await tx.all(
        """SELECT w.company_id AS a, r.company_id AS b, count(*) AS n
           FROM work.work w JOIN work.work r ON r.id = w.requested_by_work_id
           WHERE w.status = ANY(:open) AND w.company_id <> r.company_id
           GROUP BY 1, 2""",
        open=list(OPEN),
    )
    out: dict[frozenset[UUID], int] = {}
    for r in rows:
        k = frozenset((r["a"], r["b"]))
        out[k] = out.get(k, 0) + int(r["n"])
    return out


def _link(r: dict[str, Any], between: dict[frozenset[UUID], int]) -> CompanyLink:
    return CompanyLink(
        id=r["id"],
        from_=r["from_code"],
        to=r["to_code"],
        kind=r["kind"],
        purpose_fa=r["purpose_fa"],
        state=r["state"],
        open_works=between.get(frozenset((r["from_company_id"], r["to_company_id"])), 0),
        updated_at=r["updated_at"],
    )


async def canvas(tx: Tx) -> Canvas:
    """Every active company and the holding as nodes, every link (on and off) between them."""
    companies = await tx.all(
        """SELECT c.id, c.code, c.kind, c.name_fa, c.name_en, n.x, n.y
           FROM core.companies c LEFT JOIN owner.canvas_nodes n ON n.company_id = c.id
           WHERE c.status = 'active' OR c.kind = 'holding'
           ORDER BY c.kind = 'holding' DESC, c.code"""
    )
    works = {
        r["company_id"]: int(r["n"])
        for r in await tx.all(
            """SELECT company_id, count(*) AS n FROM work.work
               WHERE status = ANY(:open) AND kind <> 'recurring' AND parent_id IS NULL
               GROUP BY company_id""",
            open=list(OPEN),
        )
    }
    # An open session as live.SESSIONS_SQL counts it: not closed by the owner
    # (closed_at is the only end of an order since 0052) and not hidden.
    sessions = {
        r["company_id"]: int(r["n"])
        for r in await tx.all(
            """SELECT w.company_id, count(DISTINCT o.id) AS n
               FROM owner.order_reports o JOIN work.work w ON w.ref = ANY(o.work_refs)
               WHERE o.closed_at IS NULL AND o.hidden_at IS NULL GROUP BY w.company_id"""
        )
    }
    nodes = [
        CanvasNode(
            code=c["code"],
            name_fa=c["name_fa"] or c["name_en"] or c["code"],
            kind="holding" if c["kind"] == "holding" else "company",
            x=float(c["x"]) if c["x"] is not None else None,
            y=float(c["y"]) if c["y"] is not None else None,
            line_fa=line_of(works.get(c["id"], 0), sessions.get(c["id"], 0)),
            open_sessions=sessions.get(c["id"], 0),
        )
        for c in companies
    ]
    between = await _open_between(tx)
    rows = await tx.all(_LINK_SQL + " ORDER BY l.created_at, l.id")
    return Canvas(nodes=nodes, links=[_link(r, between) for r in rows])


async def get(tx: Tx, link_id: UUID) -> CompanyLink:
    r = await tx.one(_LINK_SQL + " WHERE l.id = :id", id=link_id, not_found="not_found")
    return _link(r, await _open_between(tx))


async def linked(tx: Tx, a: UUID, b: UUID) -> bool:
    """Whether the two companies have an `on` link (either direction)."""
    return bool(await tx.scalar("SELECT core.company_linked(:a, :b)", a=a, b=b))


async def links_of(tx: Tx, company: UUID) -> list[dict[str, Any]]:
    """A company's `on` links as the other end sees them: {company, name_fa, kind, purpose_fa,
    outgoing}."""
    rows = await tx.all("SELECT * FROM core.company_links_of(:c)", c=company)
    return [
        {
            "company": r["other_code"],
            "name_fa": r["other_name_fa"],
            "kind": r["kind"],
            "purpose_fa": r["purpose_fa"],
            "outgoing": r["outgoing"],
        }
        for r in rows
    ]


async def enforced(tx: Tx) -> bool:
    return bool(await tx.scalar("SELECT links_enforced FROM owner.settings WHERE id = 1"))


# ---------------------------------------------------------------- writes --
async def _company(tx: Tx, code: str) -> dict[str, Any]:
    r = await tx.first("SELECT id, code, kind, status FROM core.companies WHERE code = :c", c=code)
    if r is None or (r["status"] != "active" and r["kind"] != "holding"):
        raise ApiError(
            422,
            "validation_failed",
            fields={"company": f"unknown: {code}"},
            message_fa=f"شرکتی با کد {code} نیست.",
        )
    return r


async def create(tx: Tx, holding: UUID, body: LinkIn) -> UUID:
    if body.from_ == body.to:
        raise ApiError(
            422,
            "validation_failed",
            fields={"to": "a company cannot be linked to itself"},
            message_fa="یک شرکت را نمیشود به خودش وصل کرد.",
        )
    a, b = await _company(tx, body.from_), await _company(tx, body.to)
    if a["kind"] == "holding" or b["kind"] == "holding":
        raise ApiError(
            422,
            "validation_failed",
            fields={"from": "the hub is linked to every company already"},
            message_fa="هاب از پیش به همه‌ی شرکت‌ها وصل است؛ پیوند تازه نمیخواهد.",
        )
    taken = await tx.first(
        """SELECT id, state FROM core.company_links
           WHERE from_company_id = :a AND to_company_id = :b AND kind = :k""",
        a=a["id"],
        b=b["id"],
        k=body.kind,
    )
    if taken is not None:
        raise ApiError(
            409,
            "version_conflict",
            "the link exists",
            message_fa="این پیوند از پیش هست"
            + ("؛ خاموش است، روشنش کن." if taken["state"] == "off" else "."),
        )
    return UUID(
        str(
            await tx.scalar(
                """INSERT INTO core.company_links (company_id, from_company_id, to_company_id, kind,
                       purpose_fa) VALUES (:h, :a, :b, :k, :p) RETURNING id""",
                h=holding,
                a=a["id"],
                b=b["id"],
                k=body.kind,
                p=" ".join(body.purpose_fa.split()),
            )
        )
    )


async def update(tx: Tx, link_id: UUID, body: LinkPatch) -> None:
    cur = await tx.one(
        "SELECT * FROM core.company_links WHERE id = :id FOR UPDATE",
        id=link_id,
        not_found="not_found",
    )
    kind = body.kind or cur["kind"]
    if kind != cur["kind"] and await tx.scalar(
        """SELECT 1 FROM core.company_links
           WHERE from_company_id = :a AND to_company_id = :b AND kind = :k""",
        a=cur["from_company_id"],
        b=cur["to_company_id"],
        k=kind,
    ):
        raise ApiError(
            409, "version_conflict", "the link exists", message_fa="پیوندی با این نوع از پیش هست."
        )
    await tx.exec(
        """UPDATE core.company_links SET kind = :k, purpose_fa = :p, state = :s WHERE id = :id""",
        id=link_id,
        k=kind,
        p=" ".join(body.purpose_fa.split()) if body.purpose_fa is not None else cur["purpose_fa"],
        s=body.state or cur["state"],
    )


async def place(tx: Tx, code: str, x: float, y: float) -> None:
    c = await tx.first("SELECT id FROM core.companies WHERE code = :c", c=code)
    if c is None:
        raise ApiError(404, "not_found", "company not found", message_fa="چنین شرکتی در بوم نیست.")
    await tx.exec(
        """INSERT INTO owner.canvas_nodes (company_id, x, y) VALUES (:c, :x, :y)
           ON CONFLICT (company_id) DO UPDATE SET x = EXCLUDED.x, y = EXCLUDED.y,
                                                  updated_at = now()""",
        c=c["id"],
        x=Decimal(str(round(x, 6))),
        y=Decimal(str(round(y, 6))),
    )


# ------------------------------------------------------------ suggestions --
def kind_for(output_kind: str, department: str | None) -> str:
    """The kind of link that fits an order (§35.6): content that goes out is `publishes`, a report
    `feeds`, a sales or support department `sells` or `supports`, otherwise `serves`."""
    if department in KIND_OF_DEPARTMENT:
        return KIND_OF_DEPARTMENT[department]
    return KIND_OF_OUTPUT.get(output_kind, "serves")


async def suggest(tx: Tx, company: str, output_kind: str, department: str | None) -> list[str]:
    """Codes of the companies on the other end of an `on` link of `company` that fits the order
    (at most SUGGESTED_MAX, by code). Only a suggestion: the owner's route stays decisive."""
    kind = kind_for(output_kind, department)
    rows = await tx.all(
        """SELECT o.code FROM core.company_links l
           JOIN core.companies me ON me.code = :c
           JOIN core.companies o ON o.id = CASE WHEN l.from_company_id = me.id
                                                THEN l.to_company_id ELSE l.from_company_id END
           WHERE l.state = 'on' AND l.kind = :k AND me.id IN (l.from_company_id, l.to_company_id)
             AND o.status = 'active' AND o.kind <> 'holding'
           GROUP BY o.code ORDER BY o.code LIMIT :n""",
        c=company,
        k=kind,
        n=SUGGESTED_MAX,
    )
    return [r["code"] for r in rows]
