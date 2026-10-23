"""Temporal Schedules: the fixed jobs of the holding and one schedule per
active recurring work item, kept in line with the database.

Schedule ids:
    hq-maintenance            every 5 min   Maintenance (escalation, reconciliation, purge)
    hq-notification-digest    every 5 min   NotificationDigest
    hq-morning-report         daily, owner.settings.morning_report_at in the owner's zone
    hq-audit-verify           daily 02:30 (owner's zone)  AuditVerify
    hq-score-job              daily 03:00 (owner's zone)  ScoreJob
    hq-site-checks            every 5 min   SiteChecks (rule-based checks + the hub's snapshot)
    hq-ceo-daily              daily 07:30 (owner's zone)  CeoDaily, paused unless HQ_CEO_DAILY_REPORTS=on
    hq-stars-reminder         Friday 18:00 (owner's zone)  StarsReminder (prompt 08 §4)
    hq-stars-rollup           daily 08:00 (owner's zone)  StarsRollup: Saturday's week, a Jalali 1st's month
    hq-support-retention      daily 04:15 (owner's zone)  SupportRetention (prompt 10 §1.4; rule-only)
    hq-revenue-pull           daily 07:00 Asia/Tehran   RevenuePulls("scheduled") (prompt 10 §2.4)
    hq-revenue-retry          11:00 and 18:00 Asia/Tehran  RevenuePulls("retry")
    hq-rescue-follow-ups      hourly        RescueFollowUps (prompt 10 §3.4)
    hq-feedback-batch         daily 02:30 Asia/Tehran   FeedbackBatch (prompt 10 §8.1)
    hq-support-weekly         Saturday 08:30 Asia/Tehran  SupportWeekly (prompt 10 §8.3)
                              (each of these five asks the launch gate and skips while locked)
    hq-support-sweep          every SUPPORT_HANDOFF_DIGEST_MIN (30) min  SupportSweep (prompt 10
                              §4-§7: expiry, reminders, the handoff line, lifecycle, NPS);
                              its activity does nothing while the holding is locked
    hq-advisor-sweep          every 2 min   AdvisorSweep (prompt 12 §1: automatic memos,
                              proactive triggers; no memo and every trigger `deferred` while locked)
    hq-substitute-web         every minute  SubstituteWebJobs (prompt 12 §9.1; nothing while locked)
    hq-substitute-daily       daily 09:15 Asia/Tehran  SubstituteDaily (the Jalali 15th's value
                              ratio; the CLIs' model lists, not while locked)
    hq-waste-daily            daily 07:45 (owner's zone)  WasteDaily (prompt 12 §8)
    hq-cartable-reminders     every 15 min  CartableReminders (prompt 12 §11)
    hq-deploy-recheck         every 15 min  DeployRecheck (prompt 12 §7)
    hq-hr-rounds              daily 10:00 (owner's zone)  HrRounds: the 1st of a Jalali month
    hq-ceo-letters            hourly        CeoLetters: at the owner's day and hour
                              (prompt 12 part B: each asks the launch gate and does
                              nothing while the holding is locked)
    hq-media-sweep            every 5 min   MediaSweep (prompt 13 §2: the sealed series'
                              schedules, due publishing, the rule re-check; nothing
                              at all while the holding is locked)
    hq-legal-mail-poll        every 5 min   LegalMailPoll (prompt 13 §3.2: replies to the cases)
    hq-voice-bakeoff          daily 03:40 (owner's zone)  VoiceBakeoff (prompt 13 §4.2:
                              queue the missing samples; both do nothing while locked)
    recurring-<work ref>      the work's RRULE as a calendar spec in its zone,
                              end = min(UNTIL, escrow expiry); paused while the
                              company or the holding is locked
Each schedule carries a signature of its desired spec in `state.note`; a
schedule is updated only when the signature changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleCalendarSpec,
    ScheduleIntervalSpec,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
)
from temporalio.service import RPCError, RPCStatusCode

from hq_api.domain.recurrence import Rule

RECURRING_PREFIX = "recurring-"
MAINTENANCE = "hq-maintenance"
DIGEST = "hq-notification-digest"
MORNING = "hq-morning-report"
AUDIT = "hq-audit-verify"
SCORE = "hq-score-job"
SITE_CHECKS = "hq-site-checks"
CEO_DAILY = "hq-ceo-daily"
STARS_REMINDER = "hq-stars-reminder"
STARS_ROLLUP = "hq-stars-rollup"
SUPPORT_RETENTION = "hq-support-retention"
REVENUE_PULL = "hq-revenue-pull"
REVENUE_RETRY = "hq-revenue-retry"
RESCUE = "hq-rescue-follow-ups"
FEEDBACK_BATCH = "hq-feedback-batch"
SUPPORT_WEEKLY = "hq-support-weekly"
TEHRAN = "Asia/Tehran"  # the exchange's settlement times are real times, not the owner's view
SUPPORT_SWEEP = "hq-support-sweep"
WASTE_DAILY = "hq-waste-daily"
CARTABLE_REMINDERS = "hq-cartable-reminders"
DEPLOY_RECHECK = "hq-deploy-recheck"
HR_ROUNDS = "hq-hr-rounds"
CEO_LETTERS = "hq-ceo-letters"
P12B = (WASTE_DAILY, CARTABLE_REMINDERS, DEPLOY_RECHECK, HR_ROUNDS, CEO_LETTERS)
MEDIA_SWEEP = "hq-media-sweep"  # prompt 13 §2
LEGAL_MAIL_POLL = "hq-legal-mail-poll"
VOICE_BAKEOFF = "hq-voice-bakeoff"
P13B = (LEGAL_MAIL_POLL, VOICE_BAKEOFF)
FIXED = (
    SUPPORT_SWEEP,
    MAINTENANCE,
    DIGEST,
    MORNING,
    AUDIT,
    SCORE,
    SITE_CHECKS,
    CEO_DAILY,
    STARS_REMINDER,
    STARS_ROLLUP,
    SUPPORT_RETENTION,
    REVENUE_PULL,
    REVENUE_RETRY,
    RESCUE,
    FEEDBACK_BATCH,
    SUPPORT_WEEKLY,
    "hq-advisor-sweep",
    "hq-substitute-web",
    "hq-substitute-daily",
    *P12B,
    MEDIA_SWEEP,
    *P13B,
)


@dataclass(frozen=True)
class Desired:
    id: str
    workflow: str
    args: tuple[Any, ...]
    spec: ScheduleSpec
    catchup: timedelta
    execution_timeout: timedelta
    paused: bool = False

    def signature(self) -> str:
        raw = repr((self.workflow, self.args, self.spec, self.catchup, self.execution_timeout))
        return "hq:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _ranges(values: tuple[int, ...]) -> list[ScheduleRange]:
    return [ScheduleRange(start=v, end=v) for v in values]


def calendar_for(rule: Rule) -> ScheduleCalendarSpec:
    """The Rule as one calendar spec. Every supported rule restarts at local
    midnight, so the calendar matches recurrence.occurrences() exactly."""
    minute = _ranges(rule.by_minute)
    second = [ScheduleRange(start=0, end=0)]
    if rule.freq == "HOURLY":
        return ScheduleCalendarSpec(
            second=second, minute=minute, hour=[ScheduleRange(start=0, end=23, step=rule.interval)]
        )
    hour = _ranges(rule.by_hour)
    if rule.freq == "DAILY":
        return ScheduleCalendarSpec(second=second, minute=minute, hour=hour)
    if rule.freq == "WEEKLY":
        # Rule: 0 = Monday; Temporal: 0 = Sunday.
        days = tuple(sorted((d + 1) % 7 for d in rule.by_day))
        return ScheduleCalendarSpec(
            second=second, minute=minute, hour=hour, day_of_week=_ranges(days)
        )
    return ScheduleCalendarSpec(
        second=second, minute=minute, hour=hour, day_of_month=_ranges(rule.by_month_day)
    )


def recurring_spec(rule: Rule, tz: str, escrow_expires_at: datetime) -> ScheduleSpec:
    end = escrow_expires_at if rule.until is None else min(rule.until, escrow_expires_at)
    return ScheduleSpec(calendars=[calendar_for(rule)], time_zone_name=tz, end_at=end)


def daily_at(at: time, tz: str) -> ScheduleSpec:
    return ScheduleSpec(
        calendars=[
            ScheduleCalendarSpec(
                second=[ScheduleRange(start=0, end=0)],
                minute=[ScheduleRange(start=at.minute, end=at.minute)],
                hour=[ScheduleRange(start=at.hour, end=at.hour)],
            )
        ],
        time_zone_name=tz,
    )


def weekly_at(day_of_week: int, at: time, tz: str) -> ScheduleSpec:
    """Once a week (Temporal's day_of_week: 0 = Sunday, 5 = Friday)."""
    return ScheduleSpec(
        calendars=[
            ScheduleCalendarSpec(
                second=[ScheduleRange(start=0, end=0)],
                minute=[ScheduleRange(start=at.minute, end=at.minute)],
                hour=[ScheduleRange(start=at.hour, end=at.hour)],
                day_of_week=[ScheduleRange(start=day_of_week, end=day_of_week)],
            )
        ],
        time_zone_name=tz,
    )


def every(minutes: int) -> ScheduleSpec:
    return ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=minutes))])


def fixed(
    morning_at: time, tz: str, *, ceo_daily: bool = False, support_sweep_min: int = 30
) -> list[Desired]:
    return [
        Desired(
            SUPPORT_SWEEP,
            "SupportSweep",
            (),
            every(max(5, support_sweep_min)),
            timedelta(minutes=10),
            timedelta(minutes=10),
        ),
        Desired(
            SITE_CHECKS, "SiteChecks", (), every(5), timedelta(minutes=10), timedelta(minutes=4)
        ),
        Desired(
            CEO_DAILY,
            "CeoDaily",
            (),
            daily_at(time(7, 30), tz),
            timedelta(hours=2),
            timedelta(minutes=10),
            paused=not ceo_daily,
        ),
        Desired(
            MAINTENANCE, "Maintenance", (), every(5), timedelta(minutes=10), timedelta(minutes=10)
        ),
        Desired(
            DIGEST, "NotificationDigest", (), every(5), timedelta(minutes=10), timedelta(minutes=5)
        ),
        Desired(
            MORNING,
            "MorningReport",
            (),
            daily_at(morning_at, tz),
            timedelta(hours=6),
            timedelta(minutes=15),
        ),
        Desired(
            AUDIT,
            "AuditVerify",
            (),
            daily_at(time(2, 30), tz),
            timedelta(hours=12),
            timedelta(hours=1),
        ),
        Desired(
            SCORE, "ScoreJob", (), daily_at(time(3, 0), tz), timedelta(hours=12), timedelta(hours=1)
        ),
        Desired(
            STARS_REMINDER,
            "StarsReminder",
            (),
            weekly_at(5, time(18, 0), tz),
            timedelta(hours=6),
            timedelta(minutes=15),
        ),
        Desired(
            STARS_ROLLUP,
            "StarsRollup",
            (),
            daily_at(time(8, 0), tz),
            timedelta(hours=12),
            timedelta(minutes=45),
        ),
        Desired(
            SUPPORT_RETENTION,
            "SupportRetention",
            (),
            daily_at(time(4, 15), tz),
            timedelta(hours=12),
            timedelta(minutes=30),
        ),
        *revenue_fixed(),
        *management_fixed(),
        *p12b_fixed(tz),
        *studio_fixed(),
        *p13b_fixed(tz),
    ]


ADVISOR_SWEEP = "hq-advisor-sweep"
SUBSTITUTE_WEB = "hq-substitute-web"
SUBSTITUTE_DAILY = "hq-substitute-daily"


def management_fixed() -> list[Desired]:
    """Prompt 12 part A (contract §21.1, §21.13): they gate themselves."""
    return [
        Desired(
            ADVISOR_SWEEP, "AdvisorSweep", (), every(2), timedelta(minutes=5), timedelta(minutes=6)
        ),
        Desired(
            SUBSTITUTE_WEB,
            "SubstituteWebJobs",
            (),
            every(1),
            timedelta(minutes=2),
            timedelta(minutes=16),
        ),
        Desired(
            SUBSTITUTE_DAILY,
            "SubstituteDaily",
            (),
            daily_at(time(9, 15), TEHRAN),
            timedelta(hours=6),
            timedelta(minutes=10),
        ),
    ]


def p12b_fixed(tz: str) -> list[Desired]:
    """Prompt 12 part B: each activity asks the launch gate first."""
    hourly = ScheduleSpec(
        calendars=[
            ScheduleCalendarSpec(
                second=[ScheduleRange(start=0, end=0)],
                minute=[ScheduleRange(start=0, end=0)],
                hour=[ScheduleRange(start=0, end=23)],
            )
        ],
        time_zone_name=tz,
    )
    return [
        Desired(
            WASTE_DAILY,
            "WasteDaily",
            (),
            daily_at(time(7, 45), tz),
            timedelta(hours=12),
            timedelta(minutes=30),
        ),
        Desired(
            CARTABLE_REMINDERS,
            "CartableReminders",
            (),
            every(15),
            timedelta(minutes=10),
            timedelta(minutes=10),
        ),
        Desired(
            DEPLOY_RECHECK,
            "DeployRecheck",
            (),
            every(15),
            timedelta(minutes=10),
            timedelta(minutes=15),
        ),
        Desired(
            HR_ROUNDS,
            "HrRounds",
            (),
            daily_at(time(10, 0), tz),
            timedelta(hours=12),
            timedelta(minutes=30),
        ),
        Desired(
            CEO_LETTERS, "CeoLetters", (), hourly, timedelta(minutes=50), timedelta(minutes=15)
        ),
    ]


def studio_fixed() -> list[Desired]:
    """Prompt 13 §2: the media sweep gates itself (hq_api.domain.gate)."""
    return [
        Desired(
            MEDIA_SWEEP, "MediaSweep", (), every(5), timedelta(minutes=10), timedelta(minutes=25)
        )
    ]


def p13b_fixed(tz: str) -> list[Desired]:
    """Prompt 13, legal and voice: each activity asks the launch gate first."""
    return [
        Desired(
            LEGAL_MAIL_POLL,
            "LegalMailPoll",
            (),
            every(5),
            timedelta(minutes=5),
            timedelta(minutes=5),
        ),
        Desired(
            VOICE_BAKEOFF,
            "VoiceBakeoff",
            (),
            daily_at(time(3, 40), tz),
            timedelta(hours=12),
            timedelta(minutes=5),
        ),
    ]


def revenue_fixed() -> list[Desired]:
    """Prompt 10 §2-§8: they gate themselves (hq_api.domain.gate)."""
    retry = ScheduleSpec(
        calendars=[
            ScheduleCalendarSpec(
                second=[ScheduleRange(start=0, end=0)],
                minute=[ScheduleRange(start=0, end=0)],
                hour=_ranges((11, 18)),
            )
        ],
        time_zone_name=TEHRAN,
    )
    return [
        Desired(
            REVENUE_PULL,
            "RevenuePulls",
            ("scheduled",),
            daily_at(time(7, 0), TEHRAN),
            timedelta(hours=4),
            timedelta(hours=4),
        ),
        Desired(
            REVENUE_RETRY, "RevenuePulls", ("retry",), retry, timedelta(hours=3), timedelta(hours=4)
        ),
        Desired(
            RESCUE, "RescueFollowUps", (), every(60), timedelta(minutes=30), timedelta(minutes=10)
        ),
        Desired(
            FEEDBACK_BATCH,
            "FeedbackBatch",
            (),
            daily_at(time(2, 30), TEHRAN),
            timedelta(hours=6),
            timedelta(minutes=30),
        ),
        Desired(
            SUPPORT_WEEKLY,
            "SupportWeekly",
            (),
            weekly_at(6, time(8, 30), TEHRAN),
            timedelta(hours=12),
            timedelta(minutes=15),
        ),
    ]


def recurring(ref: str, work_id: str, spec: ScheduleSpec, paused: bool) -> Desired:
    return Desired(
        f"{RECURRING_PREFIX}{ref}",
        "RecurringRun",
        (work_id,),
        spec,
        timedelta(hours=1),
        timedelta(minutes=10),
        paused,
    )


def build(d: Desired, task_queue: str) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            d.workflow,
            args=list(d.args),
            id=f"{d.id}-run",
            task_queue=task_queue,
            execution_timeout=d.execution_timeout,
        ),
        spec=d.spec,
        policy=SchedulePolicy(catchup_window=d.catchup),
        state=ScheduleState(note=d.signature(), paused=d.paused),
    )


async def upsert(client: Client, d: Desired, task_queue: str) -> str:
    """create | update | pause | unpause | unchanged."""
    handle = client.get_schedule_handle(d.id)
    try:
        desc = await handle.describe()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        await client.create_schedule(d.id, build(d, task_queue))
        return "created"
    result = "unchanged"
    if desc.schedule.state.note != d.signature():
        await handle.update(lambda _: ScheduleUpdate(schedule=build(d, task_queue)))
        desc = await handle.describe()
        result = "updated"
    if desc.schedule.state.paused != d.paused:
        if d.paused:
            await handle.pause(note=d.signature())
            result = "paused" if result == "unchanged" else result
        else:
            await handle.unpause(note=d.signature())
            result = "unpaused" if result == "unchanged" else result
    return result


async def delete(client: Client, schedule_id: str) -> bool:
    try:
        await client.get_schedule_handle(schedule_id).delete()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    return True


async def existing_recurring(client: Client) -> set[str]:
    """Recurring schedule ids Temporal knows (eventually consistent listing)."""
    ids: set[str] = set()
    async for s in await client.list_schedules():
        if s.id.startswith(RECURRING_PREFIX):
            ids.add(s.id)
    return ids
