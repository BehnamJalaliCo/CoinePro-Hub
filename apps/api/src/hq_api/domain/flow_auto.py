"""⟨1.37⟩ Contract §59.4, §59.7, §59.8 (prompt 38): a working group's daily flow, by itself.

The owner (2026-11-13): «بحث دکمه نیست، باید اتوماتیک پشت صحنه انجام بشه … توسط n8n», and «باید
از اولین و تا آخرین لحظه اتوماسیون بشه».

Built on what runs, not beside it:
- a flow is an automation of kind `flow` (growth.automations): its playbook and version, its
  line, its schedule (a fixed hour on some days, or the account's best hour of §49), its account,
  story, mode (`auto`: nobody taps; `ask`: the owner's «نوبت تو» before the post) and budget;
- its day is one `LineRun` of its line (§30): the line is the playbook version's steps for that
  company, platform and account (`lines.lines.template = flow`, `template_version` = the playbook
  version it was built from; rebuilt when the member moves to another version);
- the clock is n8n's signed tick each minute (`/internal/v1/flows/tick`); the hub's own lines tick
  runs the same when no tick came for ten minutes (`growth.flow_clock`);
- a run starts `lead` before its publish time (the playbook's mean run time over the last 30
  days, 90 minutes until there is one), once per occurrence and per day: `lines.runs.occurrence_at`
  is the publish time the run works towards (null: publish at once, a run-now after the day ran);
- the engine (lines/engine.py) asks this module, before each step of a flow's run, for the stops
  of §59.7 (a paused member, a retired version), the budget, and the owner's mode.

Nothing here is a second scheduler, a second publish path or a second rule engine: the publish
step is §45's standing publish, which reads its time from the run.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel, ValidationError

from hq_api import events, idempotency
from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.domain import playbooks as PB
from hq_api.domain.gov_common import owner_tz, zone
from hq_api.errors import ApiError
from hq_api.lines import engine, store
from hq_api.lines.base import KINDS
from hq_api.principal import Principal

log = logging.getLogger("hq_api.flow_auto")

SERVICE = Principal(kind="service", code="flows", role="service")
WORKFLOW = "hq-flows"
PLATFORM = "instagram_reel"
LEAD_MIN = 90  # §59.7 a run starts this long before its hour until the playbook has its mean
LEAD_RANGE = (10, 600)
NO_TICK = timedelta(minutes=10)  # no tick of n8n this long: the hub runs what is due itself
LATE = timedelta(minutes=30)  # a publish time this far past still starts (it goes out at once)
UPCOMING_DAYS = 14
STATS_DAYS = 30
DEFAULT_AT = "09:30"
DAYS_A_MONTH = 30
DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
WEEK_FA = ("SA", "SU", "MO", "TU", "WE", "TH", "FR")
DAY_FA = {"SA": "شنبه", "SU": "یکشنبه", "MO": "دوشنبه", "TU": "سه‌شنبه", "WE": "چهارشنبه",
          "TH": "پنجشنبه", "FR": "جمعه"}  # fmt: skip
HELPER_FA = {"gpt": "با ChatGPT", "gemini": "با جمینای", "aistudio": "با ای‌آی استودیو",
             "workshop": "در کارگاه", "code": "با کد", "ighub": "با IG-Hub", "model": "با مدل"}  # fmt: skip
TIMEOUTS = {"workshop": 3600, "tts": 900, "voice_check": 600, "gpt_text": 900, "cover": 900,
            "publish": 1800, "topic": 600, "inspire": 600, "package": 300, "report": 300}  # fmt: skip
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

NOT_FOUND_FA = "این اتوماسیون پیدا نشد."
TAKEN_FA = "این شرکت همین کارگروه را دارد"
NO_VERSION_FA = "این کارگروه هنوز نسخه‌ی مُهرشده ندارد؛ اول آن را مُهر کن."
RETIRED_VERSION_FA = "این نسخه بازنشسته شده است؛ نسخه‌ی دیگری را انتخاب کن."
NO_STEPS_FA = "این نسخه هنوز قدمی ندارد؛ روند روزانه از قدم‌ها ساخته میشود."
AT_NEEDED_FA = "برای ساعت ثابت، ساعت انتشار را بنویس (مثل ۰۹:۳۰)."
PICK_ACCOUNT_FA = "این حساب از حساب‌های ثبت‌شده‌ی این شرکت نیست."
NOT_AN_OCCURRENCE_FA = "این زمان یکی از نوبت‌های این اتوماسیون نیست."
UNTIL_PAST_FA = "زمان پایان توقف باید در آینده باشد."
NOT_APPROVED_FA = "تأیید نشد؛ منتشر نشد."
ASK_FA = (
    "نوبت تو: بسته‌ی امروز آماده است (ویدیو و کپشن). «انتشار» یا «این بار نه»؛ "
    "اگر تا آخر امروز جوابی نیاید، این نوبت منتشر نمیشود."
)
OWNER_SKIP_FA = "این نوبت را مالک رد کرده بود؛ اجرا نشد."
SKIPPED_FA = "مالک این نوبت را رد کرد؛ موضوعش آزاد شد."
PAUSED_MEMBER_FA = "عضویت این شرکت در کارگروه متوقف است؛ این نوبت اجرا نشد."
RETIRED_FA = "نسخه‌ی این کارگروه بازنشسته شده است؛ این نوبت اجرا نشد."
BUDGET_DAY_FA = "به سقف بودجه‌ی امروز رسید (${x} از ${y})"
BUDGET_RUN_FA = "به سقف بودجه‌ی این اجرا رسید (${x} از ${y})"
BUDGET_REACHED_FA = "سقف بودجه‌ی امروز پر است (${x} از ${y})؛ اول سقف را بالا ببر."
CHOICES = [{"id": "raise", "label_fa": "سقف را بالا ببر"},
           {"id": "skip", "label_fa": "این نوبت رد شود"}]  # fmt: skip

AUTO_SQL = """
    SELECT a.*, c.code AS company, coalesce(c.name_fa, c.code) AS company_fa
    FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
"""


class PlaybookUsed(BaseModel):
    """§59.4 `201` of the form: the playbook (§40), its new member and the member's flow."""

    playbook: PB.Playbook
    member: PB.PlaybookMember | None = None
    automation: FS.FlowAutomation


# ------------------------------------------------------------------- reading --
def fa(v: Any) -> str:
    return str(v).translate(FA_DIGITS)


def money(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def minute(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(second=0, microsecond=0)


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        AUTO_SQL + " WHERE a.ref = :r AND a.kind = 'flow'" + (" FOR UPDATE OF a" if lock else ""),
        r=ref,
    )
    if row is None:
        raise ApiError(404, "not_found", "unknown flow automation", message_fa=NOT_FOUND_FA)
    return dict(row)


async def kind_of(tx: Tx, ref: str) -> str | None:
    kind: str | None = await tx.scalar("SELECT kind FROM growth.automations WHERE ref = :r", r=ref)
    return kind


async def row_for_run(tx: Tx, run: dict[str, Any]) -> dict[str, Any] | None:
    """The engine's question: the flow a run's line is under (`run.automation`, store.RUN_SQL)."""
    row = await tx.first(AUTO_SQL + " WHERE a.ref = :r AND a.kind = 'flow'", r=run["automation"])
    return dict(row) if row is not None else None


def schedule_of(row: dict[str, Any]) -> FS.FlowSchedule:
    return FS.FlowSchedule.model_validate(_j(row["schedule"]) or {})


def budget_of(row: dict[str, Any]) -> FS.FlowBudget:
    raw = dict(_j(row["budget"]) or {})
    raw.pop("spent_today_usd", None)
    return FS.FlowBudget.model_validate(raw)


def skips_of(row: dict[str, Any]) -> set[datetime]:
    out = set()
    for v in _j(row.get("skips")) or []:
        try:
            out.add(minute(datetime.fromisoformat(str(v))))
        except ValueError:
            continue
    return out


def gate_mode(flow: dict[str, Any] | None) -> str:
    """The line mode the engine's gates read for a flow: `ask` holds the publish (as a draft)."""
    return "draft" if flow is not None and flow["mode"] == "ask" else "auto"


# ------------------------------------------------------------------- the clock --
def hm(at: str) -> tuple[int, int]:
    h, m = at.split(":")
    return int(h), int(m)


def when_fa(sch: FS.FlowSchedule, at: str, best: bool) -> str:
    days = (
        "هر روز"
        if not sch.days or len(set(sch.days)) == len(WEEK_FA)
        else "، ".join(DAY_FA[d] for d in WEEK_FA if d in set(sch.days))
    )
    if sch.mode == "fixed":
        return f"{days} ساعت {fa(at)}"
    if best:
        return f"{days} در پربازدیدترین ساعت حساب (حالا {fa(at)})"
    return f"{days} در پربازدیدترین ساعت حساب؛ تا داده‌ی کافی برسد ساعت {fa(at)}"


async def hour_of(
    tx: Tx, row: dict[str, Any], sch: FS.FlowSchedule, tz: str, now: datetime | None = None
) -> tuple[str, bool]:
    """The publish hour («HH:MM», the owner's zone) and whether it is the account's best (§49);
    with too little data yet, the schedule's own hour (flows.slot_of's idea), else DEFAULT_AT."""
    if sch.mode == "fixed":
        return sch.at or DEFAULT_AT, False
    from hq_api.domain import best_hour as BH

    got = await BH.best(tx, row["company_id"], row.get("account"), tz, now)
    if got.enough and got.hour:
        return str(got.hour), True
    return sch.at or DEFAULT_AT, False


def times(sch: FS.FlowSchedule, at: str, tz: str, start: datetime, end: datetime) -> list[datetime]:
    """The publish times in [start, end) (UTC), on the schedule's days, at `at` in `tz`."""
    z = zone(tz)
    h, m = hm(at)
    wanted = {DAY_CODES[d] for d in sch.days} if sch.days else None
    out: list[datetime] = []
    d = start.astimezone(z).date()
    last = end.astimezone(z).date()
    while d <= last:
        if wanted is None or d.weekday() in wanted:
            t = datetime.combine(d, time(h, m), z).astimezone(UTC)
            if start <= t < end:
                out.append(t)
        d += timedelta(days=1)
    return out


async def occurrences(
    tx: Tx, row: dict[str, Any], start: datetime, end: datetime, tz: str
) -> list[datetime]:
    sch = schedule_of(row)
    at, _ = await hour_of(tx, row, sch, tz)
    return times(sch, at, tz, start, end)


def day_bounds(tz: str, at: datetime) -> tuple[datetime, datetime]:
    """The owner's day of `at` as [start, end) in UTC."""
    z = zone(tz)
    d = at.astimezone(z).date()
    start = datetime.combine(d, time(0, 0), z)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def stats(tx: Tx, playbook: str) -> dict[str, Any]:
    """The playbook's flow runs over the last 30 days, every member: mean minutes and cost."""
    row = await tx.first(
        """SELECT count(*) AS runs,
                  avg(EXTRACT(EPOCH FROM (r.ended_at - r.started_at)) / 60)
                      FILTER (WHERE r.state = 'done' AND NOT r.dry
                              AND r.started_at IS NOT NULL) AS minutes,
                  avg(r.usd_equiv) FILTER (WHERE r.state = 'done' AND NOT r.dry) AS cost
           FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
           JOIN growth.automations a ON a.line = l.ref AND a.kind = 'flow'
           WHERE a.playbook = :p AND r.at >= now() - make_interval(days => :d)""",
        p=playbook,
        d=STATS_DAYS,
    )
    row = row or {}
    return {
        "runs": int(row.get("runs") or 0),
        "minutes": float(row["minutes"]) if row.get("minutes") is not None else None,
        "cost": float(row["cost"]) if row.get("cost") is not None else None,
    }


async def lead(tx: Tx, playbook: str) -> timedelta:
    got = (await stats(tx, playbook))["minutes"]
    minutes = LEAD_MIN if got is None else min(max(int(got) + 10, LEAD_RANGE[0]), LEAD_RANGE[1])
    return timedelta(minutes=minutes)


async def ran_that_day(tx: Tx, line_id: UUID, at: datetime, tz: str) -> bool:
    """A run of the line already holds that day's occurrence (one a day, whatever the hour)."""
    d0, d1 = day_bounds(tz, at)
    return bool(
        await tx.scalar(
            """SELECT 1 FROM lines.runs WHERE line_id = :l AND occurrence_at >= :a
                 AND occurrence_at < :b LIMIT 1""",
            l=line_id,
            a=d0,
            b=d1,
        )
    )


# --------------------------------------------------------------- the version --
async def version_row(tx: Tx, playbook: str, version: int) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT v.* FROM owner.playbook_versions v JOIN owner.playbooks p ON p.id = v.playbook_id
           WHERE p.ref = :p AND v.version = :v""",
        p=playbook,
        v=version,
    )
    return dict(row) if row is not None else None


async def chosen_version(tx: Tx, pb: dict[str, Any], version: int | None) -> dict[str, Any]:
    """The form's version (sealed, not retired), else the newest sealed: 409 when none."""
    if version is not None:
        row = await version_row(tx, str(pb["ref"]), version)
        if row is None:
            raise ApiError(404, "not_found", "no such version", message_fa="این نسخه پیدا نشد.")
        if row["state"] == "retired":
            raise ApiError(409, "validation_failed", "retired", message_fa=RETIRED_VERSION_FA)
        if row["state"] != "sealed":
            raise ApiError(409, "validation_failed", "a draft", message_fa=NO_VERSION_FA)
        return row
    row = await tx.first(
        """SELECT * FROM owner.playbook_versions WHERE playbook_id = :p AND state = 'sealed'
           ORDER BY version DESC LIMIT 1""",
        p=pb["id"],
    )
    if row is None:
        raise ApiError(409, "validation_failed", "no sealed version", message_fa=NO_VERSION_FA)
    return dict(row)


def flow_steps(body: dict[str, Any]) -> list[FS.FlowStep]:
    out = []
    for raw in _j(body.get("steps")) or []:
        try:
            out.append(FS.FlowStep.model_validate(raw))
        except ValidationError:
            continue
    return out


def line_steps(body: dict[str, Any]) -> list[dict[str, Any]]:
    """§59.2 the version's FlowSteps as the engine's StepDefs. A step's own words (its seat, the
    helper, model and effort, its rules, what it takes and leaves) are kept in its settings, where
    the adapters read them; `gate: ask` is the owner's gate; `settings.prompt_fa` is its prompt."""
    body = _j(body) or {}
    seats = {str(s.get("seat")): str(s.get("title_fa") or "") for s in body.get("seats") or []}
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(_j(body.get("steps")) or []):
        try:
            st = FS.FlowStep.model_validate(raw)
        except ValidationError as exc:
            raise ApiError(
                422, "validation_failed", fields={f"steps.{i}": str(exc.errors()[0]["msg"])[:200]},
                message_fa="یکی از قدم‌های این نسخه درست نیست.",
            ) from exc  # fmt: skip
        if st.kind not in KINDS:
            raise ApiError(
                422, "validation_failed", fields={f"steps.{i}.kind": "a step kind the hub runs"},
                message_fa=f"قدم «{st.title_fa}» از نوعی است که هاب اجرا نمیکند.",
            )  # fmt: skip
        settings = dict(st.settings)
        prompt = settings.pop("prompt_fa", None)
        own = {
            "seat": st.seat, "seat_fa": seats.get(st.seat), "helper": st.helper, "model": st.model,
            "effort": st.effort, "rules_fa": st.rules_fa, "input_fa": st.input_fa,
            "output_fa": st.output_fa,
        }  # fmt: skip
        for k, v in own.items():
            if v not in (None, "", []):
                settings.setdefault(k, v)
        out.append(
            {
                "key": st.key,
                "kind": st.kind,
                "title_fa": st.title_fa,
                "prompt_fa": prompt[:20_000] if isinstance(prompt, str) else None,
                "settings": settings,
                "inputs": st.inputs,
                "gate": "owner" if st.gate == "ask" else "auto",
                "optional": st.optional,
                "enabled": True,
                "max_attempts": st.max_attempts,
                "timeout_s": st.timeout_s or TIMEOUTS.get(st.kind, 900),
            }
        )
    if not out:
        raise ApiError(422, "validation_failed", fields={"steps": "none"}, message_fa=NO_STEPS_FA)
    return out


async def member_of(tx: Tx, row: dict[str, Any]) -> dict[str, Any] | None:
    m = await tx.first("SELECT * FROM growth.memberships WHERE automation = :a", a=row["ref"])
    return dict(m) if m is not None else None


async def sync_version(tx: Tx, row: dict[str, Any]) -> dict[str, Any]:
    """The flow's line, rebuilt first when its member moved to another version (§59.1 «استفاده
    از این نسخه»): the line's `template_version` is the playbook version it was built from."""
    line = await store.load(tx, row["line"], lock=True)
    m = await member_of(tx, row)
    want = int(m["version"]) if m and m.get("version") else int(row["playbook_version"])
    if int(line["template_version"]) == want:
        return line
    v = await version_row(tx, str(row["playbook"]), want)
    if v is None or v["state"] == "draft":
        return line
    line = await store.update(
        tx, SERVICE, line, {"steps": line_steps(v["body"]), "template_version": want},
        f"نسخه‌ی {want} کارگروه",
    )  # fmt: skip
    await tx.exec(
        "UPDATE growth.automations SET playbook_version = :v, updated_at = now() WHERE id = :id",
        v=want,
        id=row["id"],
    )
    return line


# ------------------------------------------------------------------- rendering --
async def run_ref(tx: Tx, r: dict[str, Any], *, results: bool = False) -> FS.FlowRunRef:
    topic = await tx.scalar(
        """SELECT title_fa FROM growth.topics WHERE run_id = :r AND kind = 'topic'
           ORDER BY (state = 'said') DESC, created_at DESC LIMIT 1""",
        r=r["id"],
    )
    res = (await store.results_of(tx, [r["id"]])).get(str(r["id"])) if results else None
    return FS.FlowRunRef(
        ref=r["ref"], at=r["occurrence_at"] or r["at"], state=r["state"], topic_fa=topic,
        note_fa=r["note_fa"] or "", cost_usd=round(float(r["usd_equiv"]), 4), results=res,
    )  # fmt: skip


async def spent_today(tx: Tx, row: dict[str, Any], tz: str, now: datetime | None = None) -> float:
    d0, d1 = day_bounds(tz, now or datetime.now(UTC))
    v = await tx.scalar(
        """SELECT COALESCE(sum(r.usd_equiv), 0) FROM lines.runs r JOIN lines.lines l
               ON l.id = r.line_id
           WHERE l.ref = :line AND r.at >= :a AND r.at < :b""",
        line=row["line"],
        a=d0,
        b=d1,
    )
    return round(float(v or 0), 4)


async def last_tick(tx: Tx) -> datetime | None:
    at: datetime | None = await tx.scalar(
        """SELECT f.last_tick_at FROM growth.flow_clock f JOIN core.companies c
               ON c.id = f.company_id WHERE c.kind = 'holding' LIMIT 1"""
    )
    return at


async def render(tx: Tx, row: dict[str, Any], now: datetime | None = None) -> FS.FlowAutomation:
    """§59.7 `GET /automations/{ref}` of a flow."""
    now = now or datetime.now(UTC)
    tz = await owner_tz(tx)
    sch = schedule_of(row)
    at, best = await hour_of(tx, row, sch, tz, now)
    sch = sch.model_copy(update={"when_fa": when_fa(sch, at, best)})
    line = await store.load(tx, row["line"])
    m = await member_of(tx, row)
    version = int(m["version"]) if m and m.get("version") else int(row["playbook_version"])
    vrow = await version_row(tx, str(row["playbook"]), version)
    upcoming_at = times(sch, at, tz, now, now + timedelta(days=UPCOMING_DAYS))
    runs = await tx.all(
        """SELECT id, occurrence_at FROM lines.runs WHERE line_id = :l AND occurrence_at >= :s""",
        l=line["id"],
        s=now - timedelta(days=1),
    )
    run_on: dict[date, UUID] = {}
    z = zone(tz)
    for r in runs:
        run_on[r["occurrence_at"].astimezone(z).date()] = r["id"]
    topics = {}
    if run_on:
        topics = {
            t["run_id"]: t["title_fa"]
            for t in await tx.all(
                """SELECT run_id, title_fa FROM growth.topics
                   WHERE run_id = ANY(CAST(:ids AS uuid[])) AND kind = 'topic' AND state = 'said'""",
                ids=[str(i) for i in run_on.values()],
            )
        }
    skips = skips_of(row)
    upcoming = [
        FS.FlowOccurrence(
            at=a, topic_fa=topics.get(run_on.get(a.astimezone(z).date())), skip=minute(a) in skips
        )
        for a in upcoming_at
    ]
    nxt = None
    if row["state"] == "on":
        nxt = upcoming[0] if upcoming else None
    elif row["state"] == "paused" and row["paused_until"] is not None:
        nxt = next((o for o in upcoming if o.at >= row["paused_until"]), None)
    last = await tx.first(
        "SELECT * FROM lines.runs WHERE line_id = :l ORDER BY at DESC, ref DESC LIMIT 1",
        l=line["id"],
    )
    d0, d1 = day_bounds(tz, now)
    today = await tx.first(
        """SELECT count(*) AS n, COALESCE(sum(usd_equiv), 0) AS usd FROM lines.runs
           WHERE line_id = :l AND at >= :a AND at < :b""",
        l=line["id"],
        a=d0,
        b=d1,
    )
    playbook_fa = await tx.scalar(
        "SELECT title_fa FROM owner.playbooks WHERE ref = :p", p=row["playbook"]
    )
    budget = budget_of(row).model_copy(
        update={"spent_today_usd": round(float(today["usd"] if today else 0), 4)}
    )
    return FS.FlowAutomation(
        ref=row["ref"],
        company=row["company"],
        company_fa=row["company_fa"] or row["company"],
        playbook=str(row["playbook"]),
        playbook_fa=playbook_fa or "",
        version=version,
        line=str(row["line"]),
        title_fa=row.get("title_fa") or row["sentence_fa"],
        state=row["state"],
        paused_until=row["paused_until"],
        schedule=sch,
        account=row["account"],
        story=bool(row["story"]) if row["story"] is not None else True,
        mode=row["mode"] or "auto",
        budget=budget,
        replies=FS.ReplyPolicy.model_validate(_j(row["replies"]) or {}),
        steps=flow_steps(_j(vrow["body"]) if vrow else {}),
        next=nxt,
        upcoming=upcoming,
        last_run=await run_ref(tx, last, results=True) if last is not None else None,
        today=FS.FlowToday(
            runs=int(today["n"] if today else 0),
            cost_usd=round(float(today["usd"] if today else 0), 4),
        ),
        n8n=FS.FlowN8n(workflow=WORKFLOW, last_tick_at=await last_tick(tx)),
        created_at=row["created_at"],
        by_fa="مالک",
    )


async def runs(tx: Tx, row: dict[str, Any], limit: int, before: str | None) -> FS.FlowRuns:
    """§59.8 `GET /automations/{ref}/runs`: newest first, each with its results."""
    from hq_api import pagination

    c0, c1 = pagination.time_id(before)
    rows = await tx.all(
        """SELECT r.* FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
           WHERE l.ref = :line
             AND (CAST(:c0 AS timestamptz) IS NULL
                  OR (r.at, r.id) < (CAST(:c0 AS timestamptz), CAST(:c1 AS uuid)))
           ORDER BY r.at DESC, r.id DESC LIMIT :n""",
        line=row["line"],
        c0=c0,
        c1=c1,
        n=limit + 1,
    )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return FS.FlowRuns(items=[await run_ref(tx, r, results=True) for r in items], next_cursor=nxt)


# ---------------------------------------------------------------- the engine's --
async def stop_why(
    tx: Tx, flow: dict[str, Any], run: dict[str, Any], body: dict[str, Any]
) -> str | None:
    """§59.7 what stops a flow's run before its next step (besides the kill switch and a freeze,
    which the engine's own stop_reason reads): a paused member, a retired version, and the owner's
    «این نوبت رد شود» on the run's budget notice."""
    m = await member_of(tx, flow)
    if m is not None and m["state"] == "paused":
        return PAUSED_MEMBER_FA
    version = int(body.get("template_version") or flow["playbook_version"])
    state = await tx.scalar(
        """SELECT v.state FROM owner.playbook_versions v JOIN owner.playbooks p ON p.id = v.playbook_id
           WHERE p.ref = :p AND v.version = :v""",
        p=flow["playbook"],
        v=version,
    )
    if state == "retired":
        return RETIRED_FA
    if run["state"] == "waiting" and await tx.scalar(
        """SELECT 1 FROM notify.notifications
           WHERE link_kind = 'line_run' AND link_ref = :r AND answer = 'skip' LIMIT 1""",
        r=run["ref"],
    ):
        return SKIPPED_FA
    return None


async def budget_hold(tx: Tx, flow: dict[str, Any], run: dict[str, Any]) -> bool:
    """§59.7 before each step: the run's and the day's spend against the flow's caps. Spent: the
    run waits (`waiting`, its note says so) and the owner gets ONE decision notice; under the caps
    again (he raised one): the run goes on."""
    b = budget_of(flow)
    tz = await owner_tz(tx)
    spent = round(float(run["usd_equiv"]), 4)
    day = await spent_today(tx, flow, tz)
    note = None
    if spent >= b.per_run_usd:
        note = BUDGET_RUN_FA.format(x=money(spent), y=money(b.per_run_usd))
    elif day >= b.per_day_usd:
        note = BUDGET_DAY_FA.format(x=money(day), y=money(b.per_day_usd))
    if note is None:
        if run["state"] == "waiting":
            await tx.exec(
                "UPDATE lines.runs SET note_fa = NULL, updated_at = now() WHERE id = :id",
                id=run["id"],
            )
        return False
    if run["state"] == "waiting":
        return True  # already told
    await tx.exec(
        """UPDATE lines.runs SET state = 'waiting', note_fa = :n, updated_at = now(),
               started_at = coalesce(started_at, now()) WHERE id = :id""",
        n=note,
        id=run["id"],
    )
    from hq_api.domain import notify

    title = flow.get("title_fa") or flow["sentence_fa"]
    await notify.raise_notification(
        tx,
        company_id=flow["company_id"],
        company_code=flow["company"],
        level="decision",
        title_fa=f"«{title or flow['ref']}»: {note}"[:300],
        body_fa=(
            f"اجرای {run['ref']} پیش از قدم بعد ایستاد. «سقف را بالا ببر» یا «این نوبت رد شود»."
        ),
        link_kind="line_run",
        link_ref=run["ref"],
        source_kind="system",
        source_code="flows",
        choices=CHOICES,
        domain="business",
        owner_action=True,
    )
    await engine._emit(tx, run, note_fa=note, state="waiting")
    return True


async def ask_expired(tx: Tx, run: dict[str, Any], w: dict[str, Any]) -> bool:
    """§59.7 mode `ask`: a run that waits for the owner's tap past the end of his day."""
    if w["gate"] != "owner":
        return False
    tz = await owner_tz(tx)
    since = run["occurrence_at"] or w["started_at"] or run["at"]
    _, end = day_bounds(tz, since)
    return datetime.now(UTC) >= end


def step_context(flow: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """`ctx.step["_flow"]`: what a flow's step (above all `publish`) reads of its run: the publish
    time (`publish_at`, null: at once), the account, the story, the mode and the automation."""
    occ = run.get("occurrence_at")
    return {
        "automation": flow["ref"],
        "playbook": flow["playbook"],
        "version": flow["playbook_version"],
        "publish_at": occ.isoformat() if occ is not None else None,
        "account": flow["account"],
        "story": bool(flow["story"]) if flow["story"] is not None else True,
        "mode": flow["mode"] or "auto",
        "replies": _j(flow["replies"]) or {},
    }


# ------------------------------------------------------------------ the tick --
async def _clock(tx: Tx, holding_id: UUID, now: datetime, source: str) -> bool:
    """n8n's tick stamps the clock; the fallback runs only when no tick came for NO_TICK."""
    if source == "n8n":
        await tx.exec(
            """INSERT INTO growth.flow_clock (company_id, last_tick_at, ticks, updated_at)
               VALUES (:co, :t, 1, now())
               ON CONFLICT (company_id) DO UPDATE SET last_tick_at = EXCLUDED.last_tick_at,
                   ticks = growth.flow_clock.ticks + 1, updated_at = now()""",
            co=holding_id,
            t=now,
        )
        return True
    last = await tx.scalar(
        "SELECT last_tick_at FROM growth.flow_clock WHERE company_id = :co", co=holding_id
    )
    if last is not None and now - last < NO_TICK:
        return False
    await tx.exec(
        """INSERT INTO growth.flow_clock (company_id, last_fallback_at, updated_at)
           VALUES (:co, :t, now())
           ON CONFLICT (company_id) DO UPDATE SET last_fallback_at = EXCLUDED.last_fallback_at,
               updated_at = now()""",
        co=holding_id,
        t=now,
    )
    return True


async def _changed(tx: Tx, row: dict[str, Any], state: str) -> None:
    await events.emit(
        tx, row["company"], "automation.changed", row["ref"], {"ref": row["ref"], "state": state}
    )


async def start(
    tx: Tx, row: dict[str, Any], occ: datetime | None, *, trigger: str, who: Principal
) -> dict[str, Any]:
    """One run of the flow for the publish time `occ` (null: at once); an occurrence the owner
    skipped is a `skipped` run, so its day is accounted for."""
    line = await sync_version(tx, row)
    skip = occ is not None and minute(occ) in skips_of(row)
    return await engine.start_run(
        tx, line, trigger=trigger, who=who, occurrence_at=occ,
        skip_fa=OWNER_SKIP_FA if skip else None,
    )  # fmt: skip


async def due(hub: Any, now: datetime | None = None, *, source: str = "n8n") -> dict[str, Any]:
    """Every flow `on` whose occurrence is due: its publish time minus the playbook's lead has
    come, and no run holds that day yet. `source`: n8n's signed tick, or the hub's own lines
    tick (`fallback`: only when no tick came for NO_TICK)."""
    now = now or datetime.now(UTC)
    holding = await hub.companies.holding()
    made: list[str] = []
    out: dict[str, Any] = {"source": source, "made": 0, "skipped": 0, "runs": made}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if not await _clock(tx, holding.id, now, source):
            return {**out, "idle": "n8n ticks"}
        tz = await owner_tz(tx)
        rows = await tx.all(
            AUTO_SQL
            + """ WHERE a.kind = 'flow' AND a.state IN ('on', 'paused') AND c.status = 'active'
                  ORDER BY a.created_at FOR UPDATE OF a SKIP LOCKED"""
        )
        for r in rows:
            row = dict(r)
            if row["state"] == "paused":
                if row["paused_until"] is None or row["paused_until"] > now:
                    continue
                await tx.exec(
                    """UPDATE growth.automations SET state = 'on', paused_until = NULL,
                           updated_at = now() WHERE id = :id""",
                    id=row["id"],
                )
                row["state"] = "on"
                await _changed(tx, row, "on")
            ahead = await lead(tx, str(row["playbook"]))
            line_id = await tx.scalar("SELECT id FROM lines.lines WHERE ref = :r", r=row["line"])
            for occ in await occurrences(
                tx, row, now - LATE, now + ahead + timedelta(seconds=1), tz
            ):
                if occ - ahead > now or await ran_that_day(tx, line_id, occ, tz):
                    continue
                run = await start(
                    tx, row, occ, trigger="n8n" if source == "n8n" else "schedule", who=SERVICE
                )
                if run["state"] == "skipped":
                    out["skipped"] += 1
                else:
                    made.append(run["ref"])
    for ref in made:
        await engine.kick(hub, ref)
    out["made"] = len(made)
    return out


async def fallback(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The hub's own clock (its lines tick): what n8n would have started, when n8n is silent."""
    try:
        out = await due(hub, now, source="fallback")
        if out.get("made") or out.get("skipped"):
            log.warning("n8n is silent: the hub started the flows due", extra={"runs": out["runs"]})
        return out
    except Exception as exc:  # noqa: BLE001 - the lines tick goes on
        log.warning("the flows' fallback failed", extra={"error": type(exc).__name__})
        return {"source": "fallback", "error": type(exc).__name__}


# -------------------------------------------------------------- the use form --
def _account(form_accounts: list[str], registered: list[str]) -> str | None:
    wanted = next((a.strip().lstrip("@") for a in form_accounts if a.strip().lstrip("@")), None)
    if wanted is None and len(registered) == 1:
        wanted = registered[0]
    if wanted is not None and registered and wanted not in registered:
        raise ApiError(
            422, "validation_failed",
            fields={"accounts": "one of: " + ", ".join("@" + a for a in registered[:20])},
            message_fa=PICK_ACCOUNT_FA,
        )  # fmt: skip
    return wanted


def _schedule(src: FS.UseTime | FS.FlowSchedule) -> FS.FlowSchedule:
    """The form's time (or a PATCH's schedule) as the flow keeps it: a fixed hour needs `at`."""
    if src.mode == "fixed" and not src.at:
        raise ApiError(
            422, "validation_failed", fields={"time.at": "HH:MM"}, message_fa=AT_NEEDED_FA
        )
    days = sorted(set(src.days), key=WEEK_FA.index) if src.days else None
    return FS.FlowSchedule(mode=src.mode, at=src.at, days=days)


async def _warnings(
    tx: Tx, hub: Any, company: Any, grow: dict[str, Any], steps: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[FS.UseWarning]:  # fmt: skip
    """§59.4 what the preview warns of; `by_hub`: the hub settles it itself (never the owner's
    step): the company's publish path, a seat to hire, AI Studio signed out while the API works."""
    from hq_api.domain import groups as GR
    from hq_api.domain import speech_make as SM

    out: list[FS.UseWarning] = []
    if not route.get("ready"):
        out.append(FS.UseWarning(
            key="publish_path", by_hub=True,
            text_fa="مسیر انتشار اینستاگرام این شرکت هنوز کامل نیست؛ هاب خودش آن را از تیم فنی میخواهد.",
        ))  # fmt: skip
    g = GR.render(grow)
    roles = sorted({s.role for s in g.seats})
    held = await GR.seat_holders(tx, company.id, roles)
    empty = [s for s in g.seats if not s.optional and s.role not in held]
    if empty:
        names = "، ".join(s.title_fa for s in empty[:4])
        out.append(FS.UseWarning(
            key="seats", by_hub=True,
            text_fa=f"{fa(len(empty))} جایگاه خالی است ({names})؛ هاب در پاکت ماه این شرکت استخدام میکند.",
        ))  # fmt: skip
    if any(s["kind"] == "tts" for s in steps):
        signed = (await SM.speech_state(tx))["aistudio"]
        api = await SM.api_ready(hub, tx)
        if signed == "signed_out" and api:
            out.append(FS.UseWarning(
                key="aistudio", by_hub=True,
                text_fa="صفحه‌ی ای‌آی استودیو بیرون افتاده؛ صدا با API جمینای ساخته میشود.",
            ))  # fmt: skip
        elif signed == "signed_out":
            out.append(FS.UseWarning(
                key="voice", by_hub=False,
                text_fa="کلید صدای جمینای داده نشده و ای‌آی استودیو هم بیرون است؛ صدا ساخته نمیشود.",
            ))  # fmt: skip
    return out


def _lines_fa(
    steps: list[dict[str, Any]], sch: FS.FlowSchedule, when: str, ahead: timedelta,
    account: str | None, story: bool, mode: str, budget: FS.UseBudget,
) -> list[str]:  # fmt: skip
    """§59.4 each day in order, in plain Persian."""
    out = [f"شروع: {fa(int(ahead.total_seconds() // 60))} دقیقه پیش از ساعت انتشار ({when})"]
    for i, s in enumerate(steps, 1):
        st = s["settings"]
        how = HELPER_FA.get(str(st.get("helper") or ""), "")
        line = f"{fa(i)}. {s['title_fa']}" + (f" {how}" if how else "")
        if st.get("output_fa"):
            line += f": {st['output_fa']}"
        out.append(line)
    where = f"روی @{account}" if account else "روی حساب این شرکت"
    out.append(f"انتشار {where}" + ("، با استوری" if story else "") + f"، {when}")
    out.append("بی‌پرسش منتشر میشود" if mode == "auto" else "پیش از انتشار از تو میپرسد («نوبت تو»)")
    out.append(
        f"سقف هزینه: {fa(money(budget.per_run_usd))} دلار هر اجرا، "
        f"{fa(money(budget.per_day_usd))} دلار هر روز"
    )
    return out


async def _brand_asset(tx: Tx, company: Any, brand: FS.UseBrand) -> str:
    """The form's brand as a `brand` asset of the line's library (null kept the company's own)."""
    files: list[str] = []
    if brand.logo_file:
        try:
            files = [str(UUID(brand.logo_file))]
        except ValueError as exc:
            raise ApiError(
                422, "validation_failed", fields={"brand.logo_file": "a file id"}
            ) from exc
        await store.check_files(tx, [UUID(f) for f in files])
    aid = await tx.scalar(
        """INSERT INTO lines.assets (company_id, kind, title_fa, config, files)
           VALUES (:co, 'brand', :t, CAST(:c AS jsonb), CAST(:f AS uuid[])) RETURNING id""",
        co=company.id,
        t=f"برند {company.name_fa or company.code}"[:200],
        c=store.dumps(brand.model_dump()),
        f=files,
    )
    return str(aid)


async def use(
    ctx: Any, request: Request, ref: str, form: FS.UseForm
) -> PlaybookUsed | FS.UsePreview | Any:
    """§59.4 «در شرکت دیگر به کار ببر»: `dry` the preview; else the membership (its version
    pinned), its seats, the line, the standing word and the flow automation, in one transaction."""
    from hq_api.domain import narrator as NR
    from hq_api.domain import session_publish as SPB
    from hq_api.domain import site_links as SL

    company = await ctx.hub.companies.find(form.company)
    if company is None or company.kind == "holding":
        raise ApiError(404, "not_found", "unknown company", message_fa="این شرکت را نمیشناسم.")
    async with ctx.tx() as tx:
        idem = None
        if not form.dry:
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay
        pb = await PB.row_of(tx, ref, lock=not form.dry)
        if pb["state"] == "retired":
            raise ApiError(409, "validation_failed", "retired",
                           message_fa="این کارگروه بازنشسته شده است.")  # fmt: skip
        v = await chosen_version(tx, pb, form.version)
        if pb.get("group_id") is None:
            raise ApiError(409, "validation_failed", "no group", message_fa=NO_VERSION_FA)
        grow = dict(await tx.one("SELECT * FROM growth.groups WHERE id = :g", g=pb["group_id"]))
        taken = await tx.scalar(
            """SELECT 1 FROM growth.automations
               WHERE kind = 'flow' AND playbook = :p AND company_id = :co LIMIT 1""",
            p=ref,
            co=company.id,
        ) or await tx.scalar(
            """SELECT 1 FROM growth.memberships
               WHERE group_id = :g AND company_id = :co AND automation IS NOT NULL""",
            g=grow["id"],
            co=company.id,
        )
        if taken:
            raise ApiError(409, "validation_failed", "already a member", message_fa=TAKEN_FA)
        body = _j(v["body"]) or {}
        steps = line_steps(body)
        sch = _schedule(form.time)
        route = await SPB._route(tx, company.id)
        account = _account(form.accounts, list(route["accounts"]))
        tz = await owner_tz(tx)
        now = datetime.now(UTC)
        fake = {"company_id": company.id, "account": account}
        at, best = await hour_of(tx, fake, sch, tz, now)
        when = when_fa(sch, at, best)
        ahead = await lead(tx, ref)
        if form.dry:
            first = times(sch, at, tz, now + ahead, now + timedelta(days=UPCOMING_DAYS))
            return FS.UsePreview(
                lines_fa=_lines_fa(
                    steps, sch, when, ahead, account, form.time.story, form.mode, form.budget
                ),
                first_at=first[0] if first else None,
                cost_estimate_usd=(await stats(tx, ref))["cost"],
                warnings=await _warnings(tx, ctx.hub, company, grow, steps, route),
            )
        await ctx.hub.policy.require(
            "lines",
            {"principal": ctx.who.opa(), "op": "flow.use",
             "target": {"playbook": ref, "company": company.code}, "context": {"step_up": False}},
        )  # fmt: skip
        if grow["state"] != "on":
            await tx.exec(
                "UPDATE growth.groups SET state = 'on', updated_at = now() WHERE id = :id",
                id=grow["id"],
            )
            grow["state"] = "on"
        await PB.join(tx, grow, company)
        await SPB.set_rule(
            tx, grow["id"], company.id, mode=form.mode, account=account, story=form.time.story,
            at=sch.at, best=sch.mode == "best",
        )  # fmt: skip
        library = [await _brand_asset(tx, company, form.brand)] if form.brand is not None else []
        title = str(body.get("title_fa") or pb["title_fa"])[:200]
        line = await store.insert_flow_line(
            tx, ctx.who, company_id=company.id, platform=PLATFORM,
            channel={"kind": "instagram", "subject": f"@{account}" if account else ""},
            title_fa=title, version=int(v["version"]), steps=steps, library=library,
        )  # fmt: skip
        if form.links is not None:
            await SL.save_links(tx, company.id, company.code, form.links, "مالک")
        if form.replies is not None:
            replies = await SL.fill_policy(tx, company.code, form.replies)
        else:
            replies = FS.ReplyPolicy.model_validate(body.get("replies") or {})
        if form.narrator is not None:
            await NR.put(
                tx, company.id, voice=form.narrator.voice, style_fa=form.narrator.style_fa,
                by=ctx.who,
            )  # fmt: skip
        auto = await tx.one(
            """INSERT INTO growth.automations (company_id, scope, sentence_fa, title_fa, rule, state,
                   sealed_at, kind, playbook, playbook_version, line, schedule, budget, replies,
                   mode, account, story)
               VALUES (:co, 'company', :s, :s, CAST('{}' AS jsonb), 'on', now(), 'flow', :p, :v,
                       :l, CAST(:sch AS jsonb), CAST(:b AS jsonb), CAST(:rep AS jsonb), :mode,
                       :acc, :story)
               RETURNING ref""",
            co=company.id,
            s=title,
            p=ref,
            v=int(v["version"]),
            l=line["ref"],
            sch=store.dumps(sch.model_dump(exclude={"when_fa"})),
            b=store.dumps(form.budget.model_dump()),
            rep=store.dumps(replies.model_dump()),
            mode=form.mode,
            acc=account,
            story=form.time.story,
        )
        await tx.exec(
            """UPDATE growth.memberships SET version = :v, automation = :a, updated_at = now()
               WHERE group_id = :g AND company_id = :co""",
            v=int(v["version"]),
            a=auto["ref"],
            g=grow["id"],
            co=company.id,
        )
        await ctx.audit(
            tx, company_id=company.id, action="playbook.use", action_class="A3",
            target_kind="playbook", target_ref=ref,
            summary=f"{company.code} v{v['version']}: {auto['ref']} on {line['ref']}, "
            f"{sch.mode} {sch.at or ''} {form.mode}, ${form.budget.per_run_usd}/run "
            f"${form.budget.per_day_usd}/day"[:500],
        )  # fmt: skip
        row = await load(tx, auto["ref"])
        await _changed(tx, row, "on")
        pbout = await PB.render(tx, await PB.row_of(tx, ref))
        result = PlaybookUsed(
            playbook=pbout,
            member=next((x for x in pbout.members if x.company == company.code), None),
            automation=await render(tx, row),
        )
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# ---------------------------------------------------------------- the controls --
async def _audit(
    ctx: Any, tx: Tx, row: dict[str, Any], verb: str, before: Any, after: Any, *,
    step_up: bool = False,
) -> None:  # fmt: skip
    """`automation.<verb>` with what it was and what it is now (§59.7)."""
    b = json.dumps(before, ensure_ascii=False, default=str)
    a = json.dumps(after, ensure_ascii=False, default=str)
    await ctx.audit(
        tx, company_id=row["company_id"], action=f"automation.{verb}", action_class="A2",
        target_kind="automation", target_ref=row["ref"], summary=f"{b} -> {a}"[:500],
        step_up=step_up,
    )  # fmt: skip


async def _policy(ctx: Any, op: str, target: dict[str, Any], *, step_up: bool = False) -> None:
    await ctx.hub.policy.require(
        "lines",
        {"principal": ctx.who.opa(), "op": op, "target": target, "context": {"step_up": step_up}},
    )


async def set_state(ctx: Any, tx: Tx, ref: str, state: str) -> FS.FlowAutomation:
    """`POST /automations/{ref}/state` of a flow: on (a pause ends too) or off."""
    row = await load(tx, ref, lock=True)
    await _policy(ctx, "flow.state", {"automation": ref, "state": state})
    before = {"state": row["state"], "paused_until": row["paused_until"]}
    await tx.exec(
        """UPDATE growth.automations SET state = :s, paused_until = NULL, updated_at = now()
           WHERE id = :id""",
        s=state,
        id=row["id"],
    )
    await _audit(ctx, tx, row, "state", before, {"state": state})
    row = await load(tx, ref)
    await _changed(tx, row, state)
    return await render(tx, row)


async def run_now(ctx: Any, tx: Tx, ref: str) -> FS.FlowRunRef:
    """`POST /automations/{ref}/run-now`: a run now. When today's occurrence has no run yet it
    is that run (it publishes at its hour); else an extra one, not the day's (it publishes at
    once). 409 `budget_reached` past the day's cap."""
    row = await load(tx, ref, lock=True)
    await _policy(ctx, "flow.run", {"automation": ref})
    tz = await owner_tz(tx)
    now = datetime.now(UTC)
    b = budget_of(row)
    day = await spent_today(tx, row, tz, now)
    if day >= b.per_day_usd:
        raise ApiError(
            409, "budget_reached", f"{day} of {b.per_day_usd}",
            message_fa=BUDGET_REACHED_FA.format(x=money(day), y=money(b.per_day_usd)),
        )  # fmt: skip
    line_id = await tx.scalar("SELECT id FROM lines.lines WHERE ref = :r", r=row["line"])
    _, end = day_bounds(tz, now)
    occ = None
    for a in await occurrences(tx, row, now, end, tz):
        if minute(a) not in skips_of(row) and not await ran_that_day(tx, line_id, a, tz):
            occ = a
            break
    run = await start(tx, row, occ, trigger="owner", who=ctx.who)
    await _audit(
        ctx, tx, row, "run_now", None,
        {"run": run["ref"], "publish_at": occ.isoformat() if occ else "now"},
    )  # fmt: skip
    return await run_ref(tx, run)


async def pause(ctx: Any, tx: Tx, ref: str, until: datetime | None) -> FS.FlowAutomation:
    """`POST /automations/{ref}/pause {until?}`: paused till `until` (the tick turns it on
    again), or till the owner's `state on`."""
    row = await load(tx, ref, lock=True)
    if until is not None and until.tzinfo is None:
        raise ApiError(422, "validation_failed", fields={"until": "a time with its zone"})
    if until is not None and until <= datetime.now(UTC):
        raise ApiError(422, "validation_failed", fields={"until": "in the future"},
                       message_fa=UNTIL_PAST_FA)  # fmt: skip
    await _policy(ctx, "flow.pause", {"automation": ref})
    before = {"state": row["state"], "paused_until": row["paused_until"]}
    await tx.exec(
        """UPDATE growth.automations SET state = 'paused', paused_until = :u, updated_at = now()
           WHERE id = :id""",
        u=until,
        id=row["id"],
    )
    await _audit(ctx, tx, row, "pause", before, {"state": "paused", "paused_until": until})
    row = await load(tx, ref)
    await _changed(tx, row, "paused")
    return await render(tx, row)


async def skip(ctx: Any, tx: Tx, ref: str, at: datetime | None, on: bool) -> FS.FlowAutomation:
    """`POST /automations/{ref}/skip {at?, skip}`: the next occurrence (or the one at `at`) is
    skipped (`skip: false` undoes it). A skipped occurrence makes a `skipped` run at its time."""
    row = await load(tx, ref, lock=True)
    tz = await owner_tz(tx)
    now = datetime.now(UTC)
    ahead = await occurrences(tx, row, now - LATE, now + timedelta(days=UPCOMING_DAYS), tz)
    if at is None:
        line_id = await tx.scalar("SELECT id FROM lines.lines WHERE ref = :r", r=row["line"])
        target = None
        for a in ahead:
            if a >= now and not await ran_that_day(tx, line_id, a, tz):
                target = a
                break
        if target is None:
            raise ApiError(422, "validation_failed", fields={"at": "no occurrence ahead"},
                           message_fa=NOT_AN_OCCURRENCE_FA)  # fmt: skip
    else:
        if at.tzinfo is None:
            raise ApiError(422, "validation_failed", fields={"at": "a time with its zone"})
        target = next((a for a in ahead if abs((a - at).total_seconds()) < 60), None)
        if target is None and minute(at) not in skips_of(row):
            raise ApiError(422, "validation_failed", fields={"at": "an occurrence of this flow"},
                           message_fa=NOT_AN_OCCURRENCE_FA)  # fmt: skip
        target = target or minute(at)
    await _policy(ctx, "flow.skip", {"automation": ref, "skip": on})
    keep = {s for s in skips_of(row) if s >= now - timedelta(days=1)}
    before = sorted(x.isoformat() for x in keep)
    if on:
        keep.add(minute(target))
    else:
        keep.discard(minute(target))
    after = sorted(x.isoformat() for x in keep)
    await tx.exec(
        "UPDATE growth.automations SET skips = CAST(:s AS jsonb), updated_at = now() WHERE id = :id",
        s=json.dumps(after),
        id=row["id"],
    )
    await _audit(ctx, tx, row, "skip", {"skips": before}, {"skips": after})
    row = await load(tx, ref)
    await _changed(tx, row, row["state"])
    return await render(tx, row)


async def month_limit_usd(tx: Tx, company_id: UUID) -> float | None:
    """§18.11 the company's month envelope in USD (its `llm.budgets` month row), if set."""
    v = await tx.scalar(
        """SELECT b.usd_limit FROM llm.budgets b JOIN core.companies c ON c.id = b.company_id
           WHERE b.company_id = :co AND b.scope_type = 'company' AND b.scope_ref = c.code
             AND b.period = 'month' AND b.enabled""",
        co=company_id,
    )
    return float(v) if v is not None else None


def budget_target(ref: str, per_day: float) -> str:
    """🔏 `automation.budget`'s target: `<ref>:<per_day_usd>` (e.g. `AT-0012:12.5`)."""
    return f"{ref}:{money(per_day)}"


async def patch(
    ctx: Any, tx: Tx, request: Request, ref: str, body: FS.FlowPatch
) -> tuple[FS.FlowAutomation, bool]:
    """`PATCH /automations/{ref}`: a tap; raising a cap past the company's month envelope
    (the day's cap × 30 over its USD month budget, or no such budget) is 🔏 `automation.budget`.
    Returns the flow and whether its budget changed (waiting runs look again)."""
    from hq_api.domain import session_publish as SPB
    from hq_api.security import stepup

    row = await load(tx, ref, lock=True)
    sets: dict[str, Any] = {}
    before: dict[str, Any] = {}
    if body.schedule is not None:
        sch = _schedule(body.schedule)
        sets["schedule"] = store.dumps(sch.model_dump(exclude={"when_fa"}))
        before["schedule"] = _j(row["schedule"])
    if body.account is not None:
        route = await SPB._route(tx, row["company_id"])
        sets["account"] = _account([body.account], list(route["accounts"]))
        before["account"] = row["account"]
    if body.story is not None:
        sets["story"] = body.story
        before["story"] = row["story"]
    if body.mode is not None:
        sets["mode"] = body.mode
        before["mode"] = row["mode"]
    rise, su, over = False, False, False
    if body.budget is not None:
        old = budget_of(row)
        new = FS.FlowBudget(per_run_usd=body.budget.per_run_usd,
                            per_day_usd=body.budget.per_day_usd)  # fmt: skip
        rise = new.per_day_usd > old.per_day_usd or new.per_run_usd > old.per_run_usd
        if rise:
            limit = await month_limit_usd(tx, row["company_id"])
            over = limit is None or new.per_day_usd * DAYS_A_MONTH > limit
            if over:
                await stepup.consume(
                    tx, request, ctx.who, "automation.budget", budget_target(ref, new.per_day_usd)
                )
                su = True
        sets["budget"] = store.dumps(new.model_dump(exclude={"spent_today_usd"}))
        before["budget"] = old.model_dump(exclude={"spent_today_usd"})
    await _policy(
        ctx, "flow.update", {"automation": ref, "budget_rise": rise, "over_envelope": over},
        step_up=su,
    )  # fmt: skip
    if body.title_fa is not None:  # the flow's own title (its sentence_fa never changes)
        sets["title_fa"] = " ".join(body.title_fa.split())
        before["title_fa"] = row.get("title_fa") or row["sentence_fa"]
    for col, val in sets.items():
        cast = "CAST(:v AS jsonb)" if col in ("schedule", "budget") else ":v"
        await tx.exec(
            f"UPDATE growth.automations SET {col} = {cast}, updated_at = now() WHERE id = :id",  # noqa: S608 - a known column
            v=val,
            id=row["id"],
        )
    after_row = await load(tx, ref)
    if {"schedule", "account", "story", "mode"} & set(sets):
        # §45 the member's standing word follows the flow (the publish step reads it)
        m = await member_of(tx, after_row)
        if m is not None:
            s2 = schedule_of(after_row)
            await SPB.set_rule(
                tx, m["group_id"], row["company_id"], mode=after_row["mode"] or "auto",
                account=after_row["account"], story=bool(after_row["story"]), at=s2.at,
                best=s2.mode == "best",
            )  # fmt: skip
    after = {k: _j(after_row[k]) if k in ("schedule", "budget") else after_row[k] for k in before}
    await _audit(ctx, tx, row, "update", before, after, step_up=su)
    await _changed(tx, after_row, after_row["state"])
    return await render(tx, after_row), "budget" in sets


async def waiting_runs(tx: Tx, row: dict[str, Any]) -> list[str]:
    return [
        r["ref"]
        for r in await tx.all(
            """SELECT r.ref FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
               WHERE l.ref = :line AND r.state = 'waiting'""",
            line=row["line"],
        )
    ]
