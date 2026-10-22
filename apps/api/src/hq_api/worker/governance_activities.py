"""Temporal activities of prompt 11 §4-§10 (the governance half).

kpi_collect        every 15 minutes (hq-kpi-collect): the cards' query KPIs
                   by code (domain/gov_kpis.collect), stale marks, kpi.stale
governance_daily   daily (hq-governance-daily): outcome reviews that came due
                   (verdicts by code, outcome.due), the risk register's rules
                   (expired acceptances, review work for the risk's owner,
                   drafts from critical findings), the change calendar's sync
                   (freezes, the hub's backup windows, cancelled deploy cards),
                   okr cards that expired, and in a quarter's last Jalali month
                   one work item per CEO to draft the next quarter's OKR

Both ask hq_api.domain.gate first: while the holding is locked they do
nothing at all (no row, no work item, no model call, no outside call) and
answer {"skipped": true, "reason": "holding_locked"}. None of them calls a
model; the work items they make are the only thing that can wake an agent,
and only when the holding is not locked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from hq_api import audit
from hq_api.domain import gate
from hq_api.domain import gov_calendar as CAL
from hq_api.domain import gov_cards as CARDS
from hq_api.domain import gov_checks as _checks  # noqa: F401 - registers PR-006/090/112/113/116
from hq_api.domain import gov_common as G
from hq_api.domain import gov_kpis as K
from hq_api.domain import gov_outcomes as OUT
from hq_api.domain import gov_risks as RK
from hq_api.domain import work as W
from hq_api.hub import Hub

SYSTEM = audit.SYSTEM


class GovernanceActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.kpi_collect, self.governance_daily]

    @activity.defn(name="kpi_collect")
    async def kpi_collect(self) -> dict[str, Any]:
        async with self._tx() as tx:
            lock = await gate.holding_lock(tx)
            if lock is not None:
                return gate.skipped(lock)
            return await K.collect(tx)

    @activity.defn(name="governance_daily")
    async def governance_daily(self) -> dict[str, Any]:
        async with self._tx() as tx:
            lock = await gate.holding_lock(tx)
            if lock is not None:
                return gate.skipped(lock)
            now = datetime.now(UTC)
            return {
                "outcomes": await OUT.measure_due(tx, now),
                "risks": await RK.sweep(tx, now),
                "calendar": await CAL.sync(tx, now),
                "okr_cards": await CARDS.stale_okr_cards(tx),
                "okr_reminders": await okr_reminders(tx, now),
            }


async def okr_reminders(tx: Any, now: datetime) -> list[str]:
    """In a quarter's last Jalali month: one work item per company's CEO to
    draft the next quarter (okr.draft), once per quarter and company."""
    tz = await G.owner_tz(tx)
    today = G.today(tz, now)
    quarter = G.quarter_of(today)
    if G.quarter_bounds(quarter)[1].toordinal() - today.toordinal() > 31:
        return []
    nxt = G.next_quarter(quarter)
    made = []
    for co in await tx.all(
        """SELECT c.id, c.code, e.code AS ceo FROM core.companies c
           JOIN core.employees e ON e.company_id = c.id AND e.kind = 'ceo' AND e.status = 'active'
           WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code"""
    ):
        if await tx.scalar(
            """SELECT 1 FROM governance.objectives WHERE company_id = :co AND quarter = :q
                 AND status IN ('proposed', 'active')""",
            co=co["id"],
            q=nxt,
        ) or await tx.scalar(
            """SELECT 1 FROM work.work_events WHERE company_id = :co AND kind = 'okr_due'
                 AND data->>'quarter' = :q""",
            co=co["id"],
            q=nxt,
        ):
            continue
        w = await W.create(
            tx,
            SYSTEM,
            company_id=co["id"],
            company_code=co["code"],
            title=f"OKR فصل {nxt}"[:300],
            brief=(
                f"ماه آخر فصل {quarter} است. هدف‌ها و نتیجه‌های کلیدی فصل {nxt} شرکت را با okr.draft بنویس: "
                "هر نتیجه‌ی کلیدی یا به یک KPI کارت‌ها وصل است یا یک سنجه‌ی دستی با check-in. "
                "کارت okr برای مالک میرود و فقط با مُهر او فعال میشود."
            ),
            kind="one_off",
            priority="P2",
            assignee_code=co["ceo"],
        )
        await W.event(tx, w, "okr_due", SYSTEM, {"quarter": nxt})
        made.append(w["ref"])
    return made
