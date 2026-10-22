"""The batch seal of low-risk cards (prompt 11 §10, contract §20.10, M7).

eligible     all of: kind in the matrix's `batch.kinds` (at most proposal,
             meeting_resolution, knowledge_entry; the owner only shortens it;
             OPA and the database both say so), action class A1, risk low,
             reversible, pending, the owner decides it, no hold, no
             amendments, quota_estimate.usd ≤ `batch.max_usd` (a card with a
             token estimate and no dollar figure is not eligible: its cost is
             unknown); at most `batch.max_items` cards
never        any A3, and every kind of the locked row `batch.never`
the seal     one step-up (`decision.batch`) on the SHA-256 of the canonical
             JSON of [{ref, version}] sorted by ref; all or nothing: one card
             that changed or is no longer eligible refuses the whole call
             (422 batch_not_eligible, fields.items [{ref, reason}]); each card
             gets its own resolution, audit row (batch B-0001) and interaction
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hq_api.db import Tx
from hq_api.domain import gov_authority as AU
from hq_api.domain import gov_common as G
from hq_api.domain import oversight
from hq_api.errors import ApiError
from hq_api.schemas import Actor, actor

ALLOWED = ("proposal", "meeting_resolution", "knowledge_entry")  # the most a batch may hold
NEVER = (
    "hire", "dismissal", "budget_change", "code_session", "server_plan", "deploy", "company_found",
    "tool_enable", "protocol", "errand_action", "evaluation", "charter_amendment", "authority_change",
    "risk_acceptance", "okr", "recurring_approval", "lesson_adoption", "message_template",
    "lifecycle_rule", "support_go_live", "a3_action",
)  # fmt: skip
REASONS = ("changed", "not_pending", "kind", "action_class", "risk", "irreversible", "amended",
           "over_max_usd", "over_max_items", "held")  # fmt: skip


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=r"^D-[0-9]{4,}$")
    version: int = Field(ge=1)


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BatchItem] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=5000)


class BatchQuota(BaseModel):
    tokens: int | None
    usd: Decimal | None


class Batchable(BaseModel):
    ref: str
    version: int
    kind: str
    company: str
    title: str
    quota_estimate: BatchQuota
    proposer: Actor
    risk: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


class BatchSealed(BaseModel):
    ref: str
    resolution: str | None


class BatchOut(BaseModel):
    batch: str
    items: list[BatchSealed]


def target(items: list[BatchItem]) -> str:
    """The step-up target: sha256 of the canonical [{ref, version}] sorted by ref."""
    return G.canonical_sha256(
        sorted(({"ref": i.ref, "version": i.version} for i in items), key=lambda x: x["ref"])
    )


async def limits(tx: Tx, hub: Any) -> tuple[set[str], Decimal, int]:
    """(kinds, max_usd, max_items) in force: the database row and OPA both."""
    kinds = {k for k in await AU.list_value(tx, "batch.kinds", list(ALLOWED)) if k in ALLOWED}
    if hub is not None:
        await AU.ensure(hub)
        for k in sorted(kinds):
            if not (await hub.policy.query("limits", {"rule": "batch.kinds", "kind": k})).allow:
                kinds.discard(k)
    max_usd = Decimal(str(await AU.limit_value(tx, "batch.max_usd", 2)))
    max_items = int(await AU.limit_value(tx, "batch.max_items", 20))
    return kinds, max_usd, max_items


async def reasons(tx: Tx, d: dict[str, Any], kinds: set[str], max_usd: Decimal) -> list[str]:
    out = []
    if d["status"] != "pending":
        out.append("not_pending")
    if d["kind"] not in kinds or d["kind"] in NEVER or d.get("approver_code"):
        out.append("kind")
    if d["action_class"] != "A1":
        out.append("action_class")
    if d["risk"] != "low":
        out.append("risk")
    if not d["reversible"]:
        out.append("irreversible")
    if d["amendments"]:
        out.append("amended")
    usd = d["quota_usd"]
    if (usd is not None and Decimal(usd) > max_usd) or (
        usd is None and (d["quota_tokens"] or 0) > 0
    ):
        out.append("over_max_usd")
    if await oversight.held(tx, "decision", d["ref"]):
        out.append("held")
    return out


async def batchable(tx: Tx, hub: Any, limit: int = 200) -> list[Batchable]:
    kinds, max_usd, _ = await limits(tx, hub)
    rows = await tx.all(
        """SELECT d.*, c.code AS company FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
           WHERE d.status = 'pending' AND d.kind = ANY(:k) AND d.action_class = 'A1' AND d.risk = 'low'
             AND d.reversible AND d.approver_code IS NULL AND d.amendments IS NULL
           ORDER BY d.created_at, d.id LIMIT :n""",
        k=sorted(kinds),
        n=limit,
    )
    out = []
    for d in rows:
        if await reasons(tx, dict(d), kinds, max_usd):
            continue
        who = actor(d["proposer_kind"], d["proposer_code"])
        assert who is not None
        out.append(
            Batchable(
                ref=d["ref"],
                version=d["version"],
                kind=d["kind"],
                company=d["company"],
                title=d["title"],
                quota_estimate=BatchQuota(tokens=d["quota_tokens"], usd=d["quota_usd"]),
                proposer=who,
                risk=d["risk"],
                created_at=d["created_at"],
                expires_at=d["expires_at"],
            )
        )
    return out


async def check(tx: Tx, hub: Any, items: list[BatchItem]) -> list[dict[str, Any]]:
    """The cards, locked, in ref order; 422 batch_not_eligible with every
    refusal when one of them may not be sealed in this batch."""
    if len({i.ref for i in items}) != len(items):
        raise ApiError(422, "validation_failed", fields={"items": "each card once"})
    kinds, max_usd, max_items = await limits(tx, hub)
    refused: list[dict[str, str]] = []
    ordered = sorted(items, key=lambda i: i.ref)
    if len(items) > max_items:
        refused += [{"ref": i.ref, "reason": "over_max_items"} for i in items[max_items:]]
    rows = []
    for i in ordered:
        await tx.exec("SELECT 1 FROM cartable.decisions WHERE ref = :r FOR UPDATE", r=i.ref)
        d = await tx.first(
            """SELECT d.*, c.code AS company, r.ref AS resolution FROM cartable.decisions d
               JOIN core.companies c ON c.id = d.company_id
               LEFT JOIN cartable.resolutions r ON r.id = d.resolution_id WHERE d.ref = :r""",
            r=i.ref,
        )
        if d is None:
            refused.append({"ref": i.ref, "reason": "not_pending"})
            continue
        d = dict(d)
        why = await reasons(tx, d, kinds, max_usd)
        if d["version"] != i.version:
            why.insert(0, "changed")
        refused += [{"ref": i.ref, "reason": w} for w in why]
        rows.append(d)
    if refused:
        raise ApiError(422, "batch_not_eligible", fields={"items": refused})
    return rows
