"""The watch's periodic duties (contract §28.2-§28.3 ⟨1.10⟩, prompt 19),
run by the worker's Maintenance every 5 minutes; each one once per its
period (ops.watch_runs, a unique key):

  catalogue         weekly per company with a paired server: its catalogue
                    is refreshed; the difference goes to its CEO and the owner
  growth_memo       weekly per company: the advisor's three highest-value
                    moves from the catalogue, revenue, funnel and support data
  holding_proposal  monthly: the digital CEO's «پیشنهاد هلدینگ»

The weeks are the owner's (Saturday first, the owner's time zone). The
overseer's own watch (the daily security sweep, the daily app health, the
weekly code review per repository) are protocols PR-140..PR-142 of
agents/protocols/oversight.yaml, run like every other protocol. Nothing
while the holding is locked.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from hq_api.db import Tx
from hq_api.domain import catalogue as CAT
from hq_api.domain import gate
from hq_api.principal import Principal
from hq_common import owner_zone

SERVICE = Principal(kind="service", code="watch", role="service")
GROWTH_TOKENS = 120_000

GROWTH_BRIEF = """The weekly growth memo for {company} (contract §28.3, your duty). From its catalogue
(company.state, its latest catalogue deliverable {catalogue}), its revenue (revenue.read), funnel
(funnel.read), support and the last week's work, find the THREE highest-value moves for the company,
each with: what to do, why now (the evidence, cited), the expected impact (a figure with its arithmetic)
and the first step. Post ONE message in your thread with the owner (message.thread, thread "A") titled
«یادداشت رشد {company}»; nothing else, then finish (done). No move without evidence; say plainly what
data was missing."""


def owner_week(now: datetime, tz: str) -> str:
    """The owner's week (Saturday first) as its Saturday's date."""
    local = now.astimezone(ZoneInfo(tz)).date()
    saturday = local - timedelta(days=(local.weekday() - 5) % 7)
    return saturday.isoformat()


def owner_month(now: datetime, tz: str) -> str:
    return now.astimezone(ZoneInfo(tz)).strftime("%Y-%m")


async def _once(tx: Tx, company_id: Any, key: str, kind: str, **refs: Any) -> bool:
    """Claims a duty for its period: True the first time only."""
    row = await tx.first(
        """INSERT INTO ops.watch_runs (company_id, key, kind, work_id, catalogue_id, note)
           VALUES (:co, :key, :kind, :w, :cat, :note) ON CONFLICT (key) DO NOTHING RETURNING id""",
        co=company_id,
        key=key[:140],
        kind=kind,
        w=refs.get("work_id"),
        cat=refs.get("catalogue_id"),
        note=refs.get("note"),
    )
    return row is not None


async def _owner_tz(tx: Tx) -> str:
    from hq_api.domain.gov_common import owner_tz

    return await owner_tz(tx)


async def sweep(hub: Any, router: Any = None, now: datetime | None = None) -> dict[str, Any]:
    from hq_api.domain import advisor, dceo
    from hq_api.domain import work as W

    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"catalogues": 0, "growth_memos": 0, "proposal": None, "stale": 0}
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        out["stale"] = await CAT.sweep(tx, hub, now)
        tz = await _owner_tz(tx)
        week, month = owner_week(now, tz), owner_month(now, tz)
        companies = await tx.all(
            """SELECT c.id, c.code FROM core.companies c
               WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code"""
        )
        adv = await tx.scalar(
            """SELECT e.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id
               WHERE c.kind = 'holding' AND e.kind = 'advisor' AND e.status = 'active' LIMIT 1"""
        )
        spent = await advisor.zone_spent(tx, hub)
        holding = await hub.companies.holding()
        for co in companies:
            company = await hub.companies.by_code(co["code"])
            has_server = await tx.scalar(
                """SELECT 1 FROM infra.servers WHERE company_id = :co AND origin = 'attached'
                     AND state IN ('online', 'offline')""",
                co=co["id"],
            )
            if has_server and await _once(
                tx, co["id"], f"catalogue:{co['code']}:{week}", "catalogue"
            ):
                c, fresh = await CAT.start(tx, hub, company, by_kind="service", by_code="watch")
                if fresh and c["state"] == "running":
                    out["catalogues"] += 1
            if (
                adv
                and not spent
                and await _once(tx, co["id"], f"growth_memo:{co['code']}:{week}", "growth_memo")
            ):
                last = await CAT.latest(tx, co["id"])
                w = await W.create(
                    tx,
                    SERVICE,
                    company_id=holding.id,
                    company_code=holding.code,
                    title=f"یادداشت رشد هفته‌ی {co['code']}",
                    brief=GROWTH_BRIEF.format(
                        company=co["code"],
                        catalogue=(last or {}).get("deliverable_ref") or "(none yet)",
                    ),
                    kind="one_off",
                    priority="P3",
                    assignee_code=adv,
                    budget=W.BudgetIn(tokens=GROWTH_TOKENS),
                )
                await tx.exec(
                    "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
                    id=w["id"],
                    m=json.dumps(
                        {
                            "task_class": "advisor_proactive",
                            "owner_zone": owner_zone.AUTO,
                            "watch": "growth_memo",
                        }
                    ),
                )
                out["growth_memos"] += 1
        proposal_due = await _once(tx, holding.id, f"holding_proposal:{month}", "holding_proposal")
    if proposal_due:
        out["proposal"] = await dceo.holding_proposal(hub, router, lambda: hub.db.tx(ids), month)
    return out


def week_of(day: date) -> str:  # for tests: the Saturday of a date
    return (day - timedelta(days=(day.weekday() - 5) % 7)).isoformat()
