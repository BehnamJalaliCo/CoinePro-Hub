"""Temporal activities of the Chief Overseer (prompt 08 §2).

protocol_run      one scheduled run of a protocol: a checker in code when one
                  exists (rule, reconcile), else work for the overseer or QC,
                  within the daily cap of model-backed runs
oversight_tick    every 5 minutes (Maintenance): watch mode on/off and its
                  report, missed challenges, today's compliance
oversight_weekly  Saturday morning: one work item for the overseer to issue
                  this week's challenge to every company that has none
reconcile()       the protocols seeded from agents/ and one Temporal schedule
                  per active protocol (called from reconcile_schedules)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from temporalio import activity
from temporalio.client import Client, ScheduleCalendarSpec, ScheduleRange, ScheduleSpec

from hq_api import audit
from hq_api.domain import oversight as O
from hq_api.domain import oversight_checks as C
from hq_api.domain import recurrence
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.worker import schedules

log = logging.getLogger("hq_api.worker.oversight")
SYSTEM = audit.SYSTEM
PROTOCOL_PREFIX = "protocol-"
WEEKLY = "hq-oversight-weekly"


def protocol_desired(ref: str, rrule: str, tz: str, paused: bool) -> schedules.Desired:
    spec = ScheduleSpec(
        calendars=[schedules.calendar_for(recurrence.parse(rrule))], time_zone_name=tz
    )
    return schedules.Desired(
        f"{PROTOCOL_PREFIX}{ref}",
        "ProtocolRun",
        (ref,),
        spec,
        timedelta(minutes=30),
        timedelta(minutes=10),
        paused,
    )


def weekly_desired(tz: str) -> schedules.Desired:
    spec = ScheduleSpec(
        calendars=[
            ScheduleCalendarSpec(
                second=[ScheduleRange(start=0, end=0)],
                minute=[ScheduleRange(start=0, end=0)],
                hour=[ScheduleRange(start=7, end=7)],
                day_of_week=[ScheduleRange(start=6, end=6)],  # Saturday (0 = Sunday)
            )
        ],
        time_zone_name=tz,
    )
    return schedules.Desired(
        WEEKLY, "OversightWeekly", (), spec, timedelta(hours=12), timedelta(minutes=10)
    )


class OversightActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.protocol_run, self.oversight_tick, self.oversight_weekly]

    # ----------------------------------------------------------- schedules --
    async def reconcile(self, client: Client, task_queue: str, tz: str) -> dict[str, Any]:
        holding = await self.hub.companies.holding()
        async with self._tx() as tx:
            seeded = await O.seed_protocols(tx, holding.id, self.hub.charters.root)
            rows = await tx.all("SELECT ref, schedule, status FROM oversight.current_protocols")
        out: dict[str, Any] = {"seeded": seeded, "protocols": {}, "deleted": []}
        wanted = {WEEKLY}
        out["weekly"] = await schedules.upsert(client, weekly_desired(tz), task_queue)
        for r in rows:
            paused = r["status"] != "active" or not self.hub.settings.oversight_schedules
            d = protocol_desired(r["ref"], r["schedule"], tz, paused)
            out["protocols"][d.id] = await schedules.upsert(client, d, task_queue)
            wanted.add(d.id)
        async for s in await client.list_schedules():
            if (
                s.id.startswith(PROTOCOL_PREFIX)
                and s.id not in wanted
                and await schedules.delete(client, s.id)
            ):
                out["deleted"].append(s.id)
        return out

    # ------------------------------------------------------------- the run --
    @activity.defn(name="protocol_run")
    async def protocol_run(self, ref: str) -> dict[str, Any]:
        holding = await self.hub.companies.holding()
        s = self.hub.settings
        async with self._tx() as tx:
            try:
                p = await O.load_protocol(tx, ref)
            except ApiError:
                return {"protocol": ref, "skipped": "unknown"}
            if p["status"] != "active":
                return {"protocol": ref, "skipped": p["status"]}
            run = await O.start_run(tx, p)
            checker = C.CHECKS.get(ref) if p["method"] in O.CODE_METHODS else None
            if checker is not None:
                return await self._by_code(tx, p, run, checker, holding)
            tz = str(
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            if await O.model_runs_today(tx, tz) >= s.oversight_model_runs_per_day:
                await O.finish_run(
                    tx,
                    run["id"],
                    "skipped",
                    notes="daily cap of model-backed protocol runs reached",
                )
                return {"protocol": ref, "skipped": "daily_cap"}
            assignee = f"{holding.code}-{O.QC if p['method'] in O.QC_METHODS else O.OVERSEER}"
            active = await tx.scalar(
                "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active'", c=assignee
            )
            if not active:
                assignee = f"{holding.code}-{O.OVERSEER}"
                if not await tx.scalar(
                    "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active'", c=assignee
                ):
                    await O.finish_run(tx, run["id"], "skipped", notes="no overseer to run it")
                    return {"protocol": ref, "skipped": "no_overseer"}
            w = await W.create(
                tx,
                SYSTEM,
                company_id=holding.id,
                company_code=holding.code,
                title=f"Protocol {ref}: {p['title_fa']}"[:300],
                brief=self._brief(p),
                kind="event",
                priority="P2",
                assignee_code=assignee,
                budget=W.BudgetIn(tokens=s.oversight_run_tokens),
            )
            await tx.exec(
                "UPDATE oversight.protocol_runs SET work_id = :w, by_kind = 'agent', by_code = :a WHERE id = :id",
                w=w["id"],
                a=assignee,
                id=run["id"],
            )
            return {"protocol": ref, "work": w["ref"], "assignee": assignee}

    @staticmethod
    def _brief(p: dict[str, Any]) -> str:
        return (
            f"Scheduled run of oversight protocol {p['ref']} v{p['version']} "
            f"({p['area']}, {p['method']}, scope {p['scope']}, severity {p['severity']}, "
            f"answerable: {p['answerable']}).\n\nCheck:\n{p['check_md']}\n\nEvidence to keep:\n"
            f"{p['evidence_md']}\n\nRaise one `finding.raise` per real problem (with evidence and "
            f"the protocol {p['ref']}), then report with `protocol.result` "
            f'{{"protocol": "{p["ref"]}", "result": "pass|fail|partial", "findings": [FI-...], "notes": "..."}}. '
            "Read only what you need; stop within this work's budget."
        )

    async def _by_code(
        self, tx: Any, p: dict[str, Any], run: dict[str, Any], checker: C.Checker, holding: Any
    ) -> dict[str, Any]:
        companies = {c.code: c.id for c in await self.hub.companies.all() if c.status == "active"}
        prev = await tx.scalar(
            """SELECT notes FROM oversight.protocol_runs WHERE protocol_ref = :r AND result <> 'pending'
                 AND id <> :id ORDER BY started_at DESC LIMIT 1""",
            r=p["ref"],
            id=run["id"],
        )
        try:
            previous = dict(json.loads(prev).get("data") or {}) if prev else {}
        except (ValueError, AttributeError):
            previous = {}
        ctx = C.CheckCtx(tx, holding.id, holding.code, companies, datetime.now(UTC), previous)
        checked = await checker(ctx)
        raised = 0
        failed: set[str] = set()
        for pr in checked.problems:
            _, created = await O.raise_finding(
                tx,
                company_id=pr.company_id,
                company_code=pr.company,
                severity=p["severity"],
                title_fa=pr.title_fa,
                body_md=pr.body_md,
                evidence=pr.evidence,
                protocol=p,
                run_id=run["id"],
                by_kind="system",
                by_code=p["ref"],
                dedupe_key=f"{p['ref']}:{pr.key}",
            )
            raised += int(created)
            failed.add(pr.company)
        per_company = {c: ("fail" if c in failed else "pass") for c in checked.companies}
        per_company |= dict.fromkeys(failed, "fail")
        result = "fail" if checked.problems else "pass"
        summary = checked.notes or f"{len(checked.problems)} problem(s), {raised} new finding(s)"
        notes = json.dumps(
            {"summary": summary, "data": checked.data}, ensure_ascii=False, default=str
        )
        await O.finish_run(
            tx,
            run["id"],
            result,
            findings=len(checked.problems),
            per_company=per_company,
            notes=notes,
        )
        return {
            "protocol": p["ref"],
            "result": result,
            "findings": len(checked.problems),
            "new": raised,
        }

    # ------------------------------------------------------------- the tick --
    @activity.defn(name="oversight_tick")
    async def oversight_tick(self) -> dict[str, Any]:
        holding = await self.hub.companies.holding()
        async with self._tx() as tx:
            watch = await O.evaluate_watch(tx, holding.id, holding.code)
            if watch.get("on"):
                await O.hold_pending_cards(tx)
            missed = await O.sweep_missed(tx)
            tz = str(
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            today = datetime.now(UTC).astimezone(ZoneInfo(tz)).date()
            stored = 0
            for c in await self.hub.companies.all():
                if c.kind != "holding" and c.status == "active":
                    await O.store_compliance(tx, c.id, today)
                    stored += 1
        return {"watch": watch, "missed": missed, "compliance": stored}

    # ----------------------------------------------------------- the week --
    @activity.defn(name="oversight_weekly")
    async def oversight_weekly(self) -> dict[str, Any]:
        """At least one challenge per company per week (Saturday): one work item
        for the overseer naming the companies still without one."""
        holding = await self.hub.companies.holding()
        async with self._tx() as tx:
            tz = str(
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            key = O.week_key(datetime.now(UTC), tz)
            missing = []
            for c in await self.hub.companies.all():
                if c.kind == "holding" or c.status != "active":
                    continue
                if not await tx.scalar(
                    "SELECT 1 FROM oversight.challenges WHERE company_id = :co AND period = 'week' AND period_key = :k",
                    co=c.id,
                    k=key,
                ):
                    missing.append(c.code)
            overseer = f"{holding.code}-{O.OVERSEER}"
            if not missing or not await tx.scalar(
                "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active'", c=overseer
            ):
                return {"week": key.isoformat(), "missing": missing, "work": None}
            title = f"Weekly challenges {key.isoformat()}"
            if await tx.scalar(
                "SELECT 1 FROM work.work WHERE company_id = :co AND title = :t",
                co=holding.id,
                t=title,
            ):
                return {"week": key.isoformat(), "missing": missing, "work": "exists"}
            w = await W.create(
                tx,
                SYSTEM,
                company_id=holding.id,
                company_code=holding.code,
                title=title,
                brief=(
                    "Issue this week's challenge to each of these companies with `challenge.issue` "
                    f"(period week, due within the week, clear criteria with weights): {', '.join(missing)}. "
                    "Make each one a real stretch for that company's goals; one call per company."
                ),
                kind="event",
                priority="P3",
                assignee_code=overseer,
                budget=W.BudgetIn(tokens=self.hub.settings.oversight_run_tokens),
            )
        return {"week": key.isoformat(), "missing": missing, "work": w["ref"]}
