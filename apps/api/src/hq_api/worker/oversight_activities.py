"""Temporal activities of the Chief Overseer (prompt 08 §2).

protocol_run      one scheduled run of a protocol: a checker in code when one
                  exists (rule, reconcile), else work for the overseer or QC,
                  within the oversight share of the token cap (prompt 08 §2.3:
                  once it is spent only `critical` protocols go on, the rest
                  are `deferred`) and the count cap of model-backed runs (never
                  for a `critical` one; the rest `deferred`); a code check
                  wakes the overseer only for a failure or what it could not
                  decide, with the evidence it collected. Nothing at all while
                  the holding is locked (no run row, no work, no model).
oversight_tick    every 5 minutes (Maintenance): yesterday's deferred runs
                  first (not while the holding is locked), watch mode on/off
                  and its report, missed challenges, today's compliance (rule
                  only: no model, no outside call)
oversight_weekly  Saturday morning: one work item for the overseer to issue
                  this week's challenge to every company that has none (none
                  while the holding is locked)
reconcile()       the protocols seeded from agents/ and one Temporal schedule
                  per ACTIVE protocol (a paused one has none; called from
                  reconcile_schedules)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from temporalio import activity
from temporalio.client import Client, ScheduleCalendarSpec, ScheduleRange, ScheduleSpec

from hq_api import audit
from hq_api.domain import gov_checks as _gov  # registers PR-006/090/112/113/116 (prompt 11)
from hq_api.domain import governance_checks as _p11
from hq_api.domain import oversight as O
from hq_api.domain import oversight_checks as C
from hq_api.domain import oversight_support as OS  # registers PR-043/101/102/103 (prompt 10)
from hq_api.domain import recurrence
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.worker import schedules
from hq_common import oversight_share

log = logging.getLogger("hq_api.worker.oversight")
SYSTEM = audit.SYSTEM
PROTOCOL_PREFIX = "protocol-"
WEEKLY = "hq-oversight-weekly"


def protocol_desired(
    ref: str, rrule: str, tz: str, paused: bool, calendar: str = "gregorian"
) -> schedules.Desired:
    rule = recurrence.parse(rrule)
    if calendar == "jalali":
        # ⟨1.5⟩ BYMONTHDAY is a Jalali day (contract §21.12): the schedule fires
        # daily at the hour and protocol_run ends at once on every other day.
        spec = schedules.daily_at(
            time(rule.by_hour[0] if rule.by_hour else 0, rule.by_minute[0]), tz
        )
    else:
        spec = ScheduleSpec(calendars=[schedules.calendar_for(rule)], time_zone_name=tz)
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
            # prompt 11's own, once (as the api's seed): PR-111/114/115 and PR-090/112/113/116
            await _p11.switch_on(tx, holding.id)
            await _gov.activate(tx)
            rows = await tx.all(
                "SELECT ref, schedule, status, calendar FROM oversight.current_protocols"
            )
        out: dict[str, Any] = {"seeded": seeded, "protocols": {}, "deleted": []}
        wanted = {WEEKLY}
        out["weekly"] = await schedules.upsert(client, weekly_desired(tz), task_queue)
        for r in rows:
            if r["status"] != "active":
                continue  # paused or draft (contract §18.1 v1.4.4): no schedule at all
            paused = not self.hub.settings.oversight_schedules
            d = protocol_desired(r["ref"], r["schedule"], tz, paused, r["calendar"])
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
    async def holding_locked(self, tx: Any, holding: Any) -> bool:
        """The holding kill switch (or any lock on the holding): oversight runs
        nothing on its own (no run, no work, no model call) until it is lifted."""
        return await tx.scalar("SELECT control.lock_state(:co)", co=holding.id) is not None

    @activity.defn(name="protocol_run")
    async def protocol_run(self, ref: str) -> dict[str, Any]:
        holding = await self.hub.companies.holding()
        async with self._tx() as tx:
            if await self.holding_locked(tx, holding):
                return {"protocol": ref, "skipped": "holding_locked"}
            try:
                p = await O.load_protocol(tx, ref)
            except ApiError:
                return {"protocol": ref, "skipped": "unknown"}
            if p["status"] != "active":
                return {"protocol": ref, "skipped": p["status"]}
            tz = str(
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            if not O.jalali_due(p, datetime.now(ZoneInfo(tz)).date()):
                # ⟨1.5⟩ a Jalali protocol off its day: no run row, no model (§21.12)
                return {"protocol": ref, "skipped": "not_its_jalali_day"}
            checker = C.CHECKS.get(ref) if p["method"] in O.CODE_METHODS else None
            if checker is None and await tx.scalar(
                """SELECT 1 FROM oversight.protocol_runs WHERE protocol_ref = :r AND work_id IS NOT NULL
                     AND started_at >= :s LIMIT 1""",
                r=ref,
                s=O.day_start(datetime.now(UTC), tz),
            ):
                # An hourly judgement protocol goes to a model at most once a
                # day: today's run stands, no new run is recorded.
                return {"protocol": ref, "skipped": "once_a_day"}
            run = await O.start_run(tx, p)
            held = await OS.GATES[ref](tx) if ref in OS.GATES else None
            if held is not None:  # ⟨1.5⟩ PR-043: locked -> skipped, no live channel -> deferred
                await O.finish_run(tx, run["id"], held[0], notes=held[1])
                return {"protocol": ref, held[0]: held[1]}
            if checker is not None:
                return await self._by_code(tx, p, run, checker, holding)
            precheck = C.PRECHECKS.get(ref)
            if precheck is not None and not await precheck(tx):
                await O.finish_run(tx, run["id"], "pass", notes="nothing to review")
                return {"protocol": ref, "result": "pass", "why": "nothing_to_review"}
            if await self._defer(tx, p, run):
                return {"protocol": ref, "deferred": "oversight_share"}
            if await self._over_count(tx, p, run, tz):
                return {"protocol": ref, "deferred": "daily_cap"}
            prefer = O.QC if p["method"] in O.QC_METHODS else O.OVERSEER
            handed = await self._hand(tx, p, run, holding, prefer, self._brief(p))
            if handed is None:
                await O.finish_run(tx, run["id"], "deferred", notes="no overseer to run it")
                return {"protocol": ref, "deferred": "no_overseer"}
            return {"protocol": ref, "work": handed[0], "assignee": handed[1]}

    async def _over_count(self, tx: Any, p: dict[str, Any], run: dict[str, Any], tz: str) -> bool:
        """The count cap of model-backed runs (HQ_OVERSIGHT_MODEL_RUNS_PER_DAY),
        counted under a lock: a run beyond it is `deferred` to the next day,
        except a `critical` protocol, which it never stops (contract §18.15)."""
        count = await O.model_runs_today(tx, tz)  # takes the lock first
        if (
            p["severity"] == oversight_share.CRITICAL
            or count < self.hub.settings.oversight_model_runs_per_day
        ):
            return False
        await O.finish_run(
            tx, run["id"], "deferred", notes="daily cap of model-backed protocol runs reached"
        )
        return True

    async def _defer(self, tx: Any, p: dict[str, Any], run: dict[str, Any]) -> bool:
        """The oversight share is spent and the protocol is not critical: the
        run is `deferred` (no failure; the next day it goes first)."""
        s = self.hub.settings
        if p["severity"] == oversight_share.CRITICAL or not await O.share_spent(
            tx, s.agent_daily_token_cap, s.oversight_daily_share
        ):
            return False
        await O.finish_run(
            tx, run["id"], "deferred", notes="the oversight share of today's token cap is spent"
        )
        return True

    async def _hand(
        self,
        tx: Any,
        p: dict[str, Any],
        run: dict[str, Any],
        holding: Any,
        prefer: str,
        brief: str,
        *,
        link: bool = True,
    ) -> tuple[str, str] | None:
        """Work for the overseer (or QC) on this run, its budget within the
        assignee's charter (prompt 08 §2.3: never above tokens_per_run)."""
        emp = None
        for code in dict.fromkeys((prefer, O.OVERSEER)):
            emp = await tx.first(
                "SELECT code, role FROM core.employees WHERE code = :c AND status = 'active'",
                c=f"{holding.code}-{code}",
            )
            if emp is not None:
                break
        if emp is None:
            return None
        w = await W.create(
            tx,
            SYSTEM,
            company_id=holding.id,
            company_code=holding.code,
            title=f"Protocol {p['ref']}: {p['title_fa']}"[:300],
            brief=brief,
            kind="event",
            priority="P2",
            assignee_code=emp["code"],
            budget=W.BudgetIn(
                tokens=O.run_tokens(
                    self.hub.charters, emp["role"], self.hub.settings.oversight_run_tokens
                )
            ),
        )
        if link:
            await tx.exec(
                "UPDATE oversight.protocol_runs SET work_id = :w, by_kind = 'agent', by_code = :a WHERE id = :id",
                w=w["id"],
                a=emp["code"],
                id=run["id"],
            )
        else:
            await tx.exec(
                "UPDATE oversight.protocol_runs SET work_id = :w WHERE id = :id",
                w=w["id"],
                id=run["id"],
            )
        return w["ref"], emp["code"]

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

    @staticmethod
    def _evidence_brief(
        p: dict[str, Any], checked: C.Checked, new: list[C.Problem], *, pending: bool
    ) -> str:
        """The overseer's brief after a code check: only what the code found
        (prompt 08 §2.3: pre-collected evidence, never the whole records)."""

        def item(pr: C.Problem) -> str:
            ev = "; ".join(f"{e.get('kind')}:{e.get('ref')}" for e in pr.evidence[:10])
            return f"- {pr.company}: {pr.title_fa} [{pr.key}]" + (f" ({ev})" if ev else "")

        parts = [
            f"Oversight protocol {p['ref']} v{p['version']} ({p['area']}, {p['method']}, severity "
            f"{p['severity']}) was checked by code.",
        ]
        if new:
            parts += [
                "It failed; these findings are raised already (FI- refs on the protocol). Word each "
                "one for its answerable role with `finding.update` notes or add what the code "
                "could not see; the run's result is recorded, so do not report it again:",
                *(item(pr) for pr in new[:20]),
            ]
        if checked.unclear:
            report = (
                f' and report with `protocol.result` {{"protocol": "{p["ref"]}", '
                '"result": "pass|fail|partial", "findings": [FI-...], "notes": "..."}'
                if pending
                else ""
            )
            parts += [
                f"The code could not decide these; judge them, raise a finding per real problem{report}:",
                *(item(pr) for pr in checked.unclear[:20]),
            ]
        parts.append(
            "Evidence is above; read more only to confirm a point. Stop within this work's budget."
        )
        return "\n".join(parts)

    async def _wake(
        self,
        tx: Any,
        p: dict[str, Any],
        run: dict[str, Any],
        holding: Any,
        checked: C.Checked,
        new: list[C.Problem],
        *,
        pending: bool,
    ) -> dict[str, Any]:
        """A failure or an unclear result of a code check wakes the overseer
        once a day per protocol, within the oversight share (critical: always);
        a run still pending (undecided by code) becomes the overseer's to finish."""
        if not new and not checked.unclear:
            return {}  # passed (or nothing new): the overseer sleeps
        s = self.hub.settings
        tz = str(
            await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
        )
        if await tx.scalar(
            """SELECT 1 FROM oversight.protocol_runs WHERE protocol_ref = :r AND work_id IS NOT NULL
                 AND started_at >= :s LIMIT 1""",
            r=p["ref"],
            s=O.day_start(datetime.now(UTC), tz),
        ):
            return {"woken": None, "why": "once_a_day"}
        if p["severity"] != oversight_share.CRITICAL and await O.share_spent(
            tx, s.agent_daily_token_cap, s.oversight_daily_share
        ):
            return {"woken": None, "why": "oversight_share"}
        if (
            await O.model_runs_today(tx, tz) >= s.oversight_model_runs_per_day
            and p["severity"] != oversight_share.CRITICAL
        ):
            return {"woken": None, "why": "daily_cap"}
        handed = await self._hand(
            tx,
            p,
            run,
            holding,
            O.OVERSEER,
            self._evidence_brief(p, checked, new, pending=pending),
            link=pending,
        )
        return {"woken": handed[0] if handed else None}

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
        new: list[C.Problem] = []
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
            if created:
                new.append(pr)
        per_company = {c: ("fail" if c in failed else "pass") for c in checked.companies}
        per_company |= dict.fromkeys(failed, "fail")
        result = "fail" if checked.problems else "pass"
        summary = checked.notes or f"{len(checked.problems)} problem(s), {raised} new finding(s)"
        notes = json.dumps(
            {"summary": summary, "data": checked.data}, ensure_ascii=False, default=str
        )
        if checked.unclear and not checked.problems:
            # Undecided by code: the overseer's judgement finishes the run (or
            # the run is deferred when the share is spent).
            if await self._defer(tx, p, run):
                return {"protocol": p["ref"], "deferred": "oversight_share"}
            woke = await self._wake(tx, p, run, holding, checked, new, pending=True)
            if woke.get("woken"):
                return {
                    "protocol": p["ref"],
                    "result": "pending",
                    "unclear": len(checked.unclear),
                    **woke,
                }
            result = "partial"
            summary += (
                f"; {len(checked.unclear)} undecided, the overseer not woken "
                f"({woke.get('why') or 'no overseer'})"
            )
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
        woke = (
            await self._wake(tx, p, run, holding, checked, new, pending=False)
            if checked.problems
            else {}
        )
        return {
            "protocol": p["ref"],
            "result": result,
            "findings": len(checked.problems),
            "new": raised,
            **woke,
        }

    # ------------------------------------------------------------- the tick --
    @activity.defn(name="oversight_tick")
    async def oversight_tick(self) -> dict[str, Any]:
        holding = await self.hub.companies.holding()
        async with self._tx() as tx:
            # While the holding is locked no deferred run is resumed (the rest
            # of the tick is rule-only bookkeeping: no model, no outside call).
            due = [] if await self.holding_locked(tx, holding) else await O.deferred_due(tx)
        resumed = [await self.protocol_run(ref) for ref in due]  # first in the new day's queue
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
        return {"watch": watch, "missed": missed, "compliance": stored, "resumed": resumed}

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
            if await self.holding_locked(tx, holding):
                return {
                    "week": key.isoformat(),
                    "missing": [],
                    "work": None,
                    "skipped": "holding_locked",
                }
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
                budget=W.BudgetIn(
                    tokens=O.run_tokens(
                        self.hub.charters, "overseer", self.hub.settings.oversight_run_tokens
                    )
                ),
            )
        return {"week": key.isoformat(), "missing": missing, "work": w["ref"]}
