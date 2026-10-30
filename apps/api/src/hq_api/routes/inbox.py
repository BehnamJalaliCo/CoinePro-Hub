"""Inbox summary (contract §5.5): badge counts in one cheap round trip."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hq_api.context import Ctx, owner_ctx
from hq_api.errors import responses

router = APIRouter(tags=["inbox"])


class ByRisk(BaseModel):
    low: int
    medium: int
    high: int


class NotificationCounts(BaseModel):
    urgent: int
    decision: int
    report: int
    info: int
    learning: int


class InboxSummary(BaseModel):
    decisions_pending: int
    decisions_by_risk: ByRisk
    deliverables_unrated: int
    # ⟨1.7.3⟩ outputs the owner has not marked seen
    deliverables_unseen: int
    messages_unread: int
    notifications: NotificationCounts
    khalvat: bool


SUMMARY_SQL = """
SELECT
  -- ⟨1.4.3⟩ the owner's own cards only (approver null): a CEO's are its to decide (§18.11)
  (SELECT count(*) FROM cartable.decisions WHERE status = 'pending' AND approver_code IS NULL)
    AS decisions_pending,
  (SELECT count(*) FROM cartable.decisions
    WHERE status = 'pending' AND approver_code IS NULL AND risk = 'low') AS risk_low,
  (SELECT count(*) FROM cartable.decisions
    WHERE status = 'pending' AND approver_code IS NULL AND risk = 'medium') AS risk_medium,
  (SELECT count(*) FROM cartable.decisions
    WHERE status = 'pending' AND approver_code IS NULL AND risk = 'high') AS risk_high,
  (SELECT count(*) FROM cartable.deliverables d
    WHERE NOT EXISTS (SELECT 1 FROM cartable.ratings r WHERE r.deliverable_id = d.id))
    AS deliverables_unrated,
  (SELECT count(*) FROM cartable.deliverables WHERE seen_at IS NULL) AS deliverables_unseen,
  (SELECT COALESCE(sum(last_seq - owner_read_seq), 0) FROM msg.threads) AS messages_unread,
  n.urgent, n.decision, n.report, n.info, n.learning,
  (SELECT khalvat FROM owner.presence WHERE id = 1) AS khalvat
FROM (SELECT count(*) FILTER (WHERE level = 'urgent') AS urgent,
             count(*) FILTER (WHERE level = 'decision') AS decision,
             count(*) FILTER (WHERE level = 'report') AS report,
             count(*) FILTER (WHERE level = 'info') AS info,
             count(*) FILTER (WHERE level = 'learning') AS learning
      FROM notify.notifications WHERE read_at IS NULL AND delivered_in_app) AS n
"""


@router.get("/inbox/summary", response_model=InboxSummary, responses=responses(401))
async def get_inbox_summary(ctx: Ctx = Depends(owner_ctx)) -> InboxSummary:
    """Counts for the badges of the three inboxes and the notification levels."""
    async with ctx.tx() as tx:
        r = await tx.one(SUMMARY_SQL)
    return InboxSummary(
        decisions_pending=r["decisions_pending"],
        decisions_by_risk=ByRisk(low=r["risk_low"], medium=r["risk_medium"], high=r["risk_high"]),
        deliverables_unrated=r["deliverables_unrated"],
        deliverables_unseen=r["deliverables_unseen"],
        messages_unread=int(r["messages_unread"]),
        notifications=NotificationCounts(
            urgent=r["urgent"],
            decision=r["decision"],
            report=r["report"],
            info=r["info"],
            learning=r["learning"],
        ),
        khalvat=bool(r["khalvat"]),
    )
