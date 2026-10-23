"""The weekly review with the advisor (prompt 12 §3, contract §21.3, M15).

owner.reviews (WR-0001), one per week (its Saturday, the owner's time zone).
Settings: owner_settings.weekly_review {enabled, day: "sa", at: "10:00"}.

  - The agenda is code, built 30 minutes before the review's time, at most 12
    items in this order: the owner's waiting cards (oldest first), open risks
    with a high score (>= 15, §20.8), key results behind their pace (§20.5),
    open critical and high findings, budgets above 70%, revenue drops
    (§19.1), decisions whose 30/60/90-day outcome review is due (§20.6), the
    owner's open quick notes (§21.8).
  - The advisor writes a one-page brief in thread A (`meta.review: WR-…`): a
    work item for HQ-ADV of task class advisor_review, owner_zone "auto",
    capped at 100K tokens. It reads the open notes only here.
  - The owner goes item by item (done, deferred, a note; If-Match); what the
    owner does meanwhile (a seal, a rejection, an order) makes its own
    ordinary records. `finish` writes the minutes as a deliverable O-… by
    HQ-ADV, with the list of items and `duration_s`.
  - A review not done by the next Saturday is `skipped`: no urgent nag, only
    one line in the morning report.

The launch gate: the worker's tick (every 15 minutes) asks it first and does
nothing at all while the holding is locked: no review, no skip, no brief.
The owner zone's share: the brief waits (the next tick tries again) while
the zone's automatic runs have used OWNER_ZONE_DAILY_SHARE of the day.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model
from hq_common import owner_zone

SERVICE = Principal(kind="service", code="weekly-review", role="service")
REVIEW_TOKENS = 100_000
MAX_ITEMS = 12
BUILD_BEFORE = timedelta(minutes=30)
HIGH_RISK = 15
BUDGET_SHARE = 0.7
OKR_PACE = 0.7
OKR_MIN_ELAPSED = 0.25
DAYS = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
DEFAULT_SETTINGS: dict[str, Any] = {"enabled": True, "day": "sa", "at": "10:00"}
KINDS = ("decision", "risk", "okr", "finding", "budget", "revenue", "outcome_review", "note")
ItemKind = Literal[
    "decision", "risk", "okr", "finding", "budget", "revenue", "outcome_review", "note"
]
ItemStatus = Literal["open", "done", "deferred"]


# ------------------------------------------------------------------ shapes --
class ReviewItem(BaseModel):
    n: int
    kind: ItemKind
    ref: str
    company: str | None
    title_fa: str
    why_fa: str
    status: ItemStatus
    owner_note: str | None


class WeeklyReview(BaseModel):
    id: UUID
    ref: str
    week: date
    scheduled_at: datetime
    state: Literal["ready", "in_progress", "done", "skipped"]
    agenda: list[ReviewItem]
    brief_message_ref: str | None
    minutes_ref: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_s: int | None
    version: int


class ItemPatch(Model):
    status: ItemStatus
    owner_note: str | None = Field(default=None, max_length=2000)


def render(r: dict[str, Any]) -> WeeklyReview:
    return WeeklyReview(
        id=r["id"],
        ref=r["ref"],
        week=r["week"],
        scheduled_at=r["scheduled_at"],
        state=r["state"],
        agenda=[ReviewItem.model_validate(i) for i in r["agenda"] or []],
        brief_message_ref=r["brief_message_ref"],
        minutes_ref=r["minutes_ref"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        duration_s=r["duration_s"],
        version=r["version"],
    )


# --------------------------------------------------------------- settings --
async def settings(tx: Tx) -> tuple[dict[str, Any], ZoneInfo]:
    row = await tx.one("SELECT weekly_review, timezone FROM owner.settings WHERE id = 1")
    s = {**DEFAULT_SETTINGS, **(row["weekly_review"] or {})}
    try:
        zone = ZoneInfo(str(row["timezone"] or "Asia/Tehran"))
    except (KeyError, ValueError):
        zone = ZoneInfo("Asia/Tehran")
    return s, zone


def week_of(d: date) -> date:
    """The Saturday that starts d's week (the Persian week)."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def slot(s: dict[str, Any], zone: ZoneInfo, week: date) -> datetime:
    """The review's time in that week (the owner's day and hour)."""
    day = week + timedelta(days=(DAYS.get(str(s.get("day")), 5) - 5) % 7)
    hh, mm = (int(x) for x in str(s.get("at") or "10:00").split(":"))
    return datetime.combine(day, time(hh, mm), zone).astimezone(UTC)


# ----------------------------------------------------------------- agenda --
def _item(kind: str, ref: str, company: str | None, title: str, why: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "ref": ref,
        "company": company,
        "title_fa": title[:300],
        "why_fa": why[:300],
        "status": "open",
        "owner_note": None,
    }


def _hours(at: datetime, now: datetime) -> str:
    h = max(0, int((now - at).total_seconds() // 3600))
    return f"{h // 24} روز" if h >= 48 else f"{h} ساعت"


async def _decisions(tx: Tx, now: datetime) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT d.ref, c.code, d.title, d.risk, d.created_at FROM cartable.decisions d
           JOIN core.companies c ON c.id = d.company_id
           WHERE d.status = 'pending' AND d.approver_code IS NULL
           ORDER BY d.created_at, d.ref LIMIT :n""",
        n=MAX_ITEMS,
    )
    return [
        _item("decision", r["ref"], r["code"], r["title"],
              f"منتظر تصمیم از {_hours(r['created_at'], now)} پیش · ریسک {r['risk']}")
        for r in rows
    ]  # fmt: skip


async def _risks(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT r.ref, c.code, r.title_fa, r.score FROM governance.risks r
           JOIN core.companies c ON c.id = r.company_id
           WHERE r.status IN ('open', 'mitigating') AND r.score >= :s
           ORDER BY r.score DESC, r.ref LIMIT :n""",
        s=HIGH_RISK,
        n=MAX_ITEMS,
    )
    return [
        _item("risk", r["ref"], r["code"], r["title_fa"], f"امتیاز ریسک {r['score']} از ۲۵")
        for r in rows
    ]


async def _okrs(tx: Tx, today: date) -> list[dict[str, Any]]:
    from hq_api.domain import advisor

    rows = await tx.all(
        """SELECT kr.ref, c.code, kr.title_fa, o.quarter, kr.start, kr.target,
                  CASE WHEN kr.kpi_key IS NOT NULL
                       THEN (SELECT k.last_value FROM governance.kpis k
                              WHERE k.company_id = kr.company_id AND k.key = kr.kpi_key)
                       ELSE kr.current END AS current
           FROM governance.key_results kr
           JOIN governance.objectives o ON o.id = kr.objective_id
           JOIN core.companies c ON c.id = kr.company_id
           WHERE o.status = 'active' ORDER BY kr.ref"""
    )
    out = []
    for r in rows:
        span = advisor.quarter_span(str(r["quarter"]))
        if span is None:
            continue
        start, end = span
        elapsed = (today - start).days / ((end - start).days or 1)
        if elapsed < OKR_MIN_ELAPSED or elapsed > 1:
            continue
        progress = advisor.okr_progress(
            float(r["start"]),
            float(r["target"]),
            None if r["current"] is None else float(r["current"]),
        )
        pace = progress / elapsed
        if pace < OKR_PACE:
            out.append(
                _item("okr", r["ref"], r["code"], r["title_fa"],
                      f"پیشرفت {round(progress * 100)}٪ در {round(elapsed * 100)}٪ فصل (سرعت {round(pace * 100)}٪)")
            )  # fmt: skip
    return out


async def _findings(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT f.ref, c.code, f.title_fa, f.severity, f.opened_at FROM oversight.findings f
           JOIN core.companies c ON c.id = f.company_id
           WHERE f.severity IN ('critical', 'high') AND f.status NOT IN ('fixed', 'verified', 'closed')
           ORDER BY f.severity = 'critical' DESC, f.opened_at, f.ref LIMIT :n""",
        n=MAX_ITEMS,
    )
    return [
        _item("finding", r["ref"], r["code"], r["title_fa"], f"یافته‌ی {r['severity']} باز")
        for r in rows
    ]


async def _budgets(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT b.scope_type, b.scope_ref, c.code, b.token_limit, b.usd_limit, u.tokens, u.usd
           FROM llm.budgets b
           JOIN core.companies c ON c.id = b.company_id
           JOIN llm.usage u ON u.scope_type = b.scope_type AND u.scope_ref = b.scope_ref
                           AND u.period = b.period
                           AND u.period_start = CASE WHEN b.period = 'month'
                                   THEN date_trunc('month', now() AT TIME ZONE 'UTC')::date
                                   ELSE (now() AT TIME ZONE 'UTC')::date END
           WHERE b.enabled AND b.period = 'month'
             AND ((b.token_limit IS NOT NULL AND b.token_limit > 0 AND u.tokens >= :s * b.token_limit)
                  OR (b.usd_limit IS NOT NULL AND b.usd_limit > 0 AND u.usd >= :s * b.usd_limit))
           ORDER BY c.code, b.scope_type, b.scope_ref LIMIT :n""",
        s=BUDGET_SHARE,
        n=MAX_ITEMS,
    )
    out = []
    for r in rows:
        pct = max(
            (r["tokens"] / r["token_limit"]) if r["token_limit"] else 0,
            float(r["usd"] / r["usd_limit"]) if r["usd_limit"] else 0,
        )
        out.append(
            _item("budget", f"{r['scope_type']}:{r['scope_ref']}"[:40], r["code"],
                  f"بودجه‌ی ماه {r['scope_type']} {r['scope_ref']}", f"{round(pct * 100)}٪ مصرف شده")
        )  # fmt: skip
    return out


async def _revenue(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT DISTINCT ON (a.company_id) a.company_id, c.code, a.day FROM revenue.alerts a
           JOIN core.companies c ON c.id = a.company_id
           WHERE a.kind = 'drop' AND a.created_at >= now() - interval '7 days'
           ORDER BY a.company_id, a.created_at DESC"""
    )
    return [
        _item("revenue", f"revenue:{r['code']}", r["code"], f"افت درآمد {r['code']}",
              f"کمیسیون روز {r['day'].isoformat() if r['day'] else '?'} زیر ۶۰٪ میانه‌ی ۲۸ روزه")
        for r in rows
    ]  # fmt: skip


async def _outcomes(tx: Tx, now: datetime) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT r.ref, r.decision_ref, r.day, c.code, d.title FROM governance.outcome_reviews r
           JOIN core.companies c ON c.id = r.company_id
           JOIN cartable.decisions d ON d.id = r.decision_id
           WHERE r.status = 'due' AND r.due_at <= :now
           ORDER BY r.due_at, r.ref LIMIT :n""",
        now=now,
        n=MAX_ITEMS,
    )
    return [
        _item("outcome_review", r["ref"], r["code"], r["title"],
              f"بازبینی {r['day']} روزه‌ی {r['decision_ref']} رسیده")
        for r in rows
    ]  # fmt: skip


async def _notes(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT n.ref, n.text_md, n.created_at FROM owner.notes n
           WHERE n.status = 'open' ORDER BY n.created_at, n.ref LIMIT :n""",
        n=MAX_ITEMS,
    )
    return [
        _item("note", r["ref"], None, " ".join(str(r["text_md"]).split())[:120], "یادداشت سریع باز")
        for r in rows
    ]


def assemble(parts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The agenda from each kind's items: the kinds in the order of §21.3
    (each kind's own order kept), at most 12, numbered from 1."""
    items: list[dict[str, Any]] = []
    for kind in KINDS:
        for it in parts.get(kind) or []:
            if len(items) >= MAX_ITEMS:
                break
            items.append({**it, "kind": kind})
    return [{**it, "n": i + 1} for i, it in enumerate(items)]


async def agenda(tx: Tx, now: datetime, today: date) -> list[dict[str, Any]]:
    """At most 12 items, in the order of §21.3 (code, no model)."""
    return assemble(
        {
            "decision": await _decisions(tx, now),
            "risk": await _risks(tx),
            "okr": await _okrs(tx, today),
            "finding": await _findings(tx),
            "budget": await _budgets(tx),
            "revenue": await _revenue(tx),
            "outcome_review": await _outcomes(tx, now),
            "note": await _notes(tx),
        }
    )


# ------------------------------------------------------------- the worker --
async def _advisor(tx: Tx) -> str | None:
    from hq_api.domain import advisor

    return await advisor._advisor_code(tx)


async def _open_notes(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        "SELECT ref, text_md, tags FROM owner.notes WHERE status = 'open' ORDER BY created_at LIMIT 30"
    )
    return [
        {"ref": r["ref"], "text": str(r["text_md"])[:1500], "tags": list(r["tags"] or [])}
        for r in rows
    ]


async def brief(tx: Tx, hub: Any, review: dict[str, Any]) -> str | None:
    """The advisor's work for the one-page brief, unless the owner zone is
    spent (the next tick tries again) or no advisor is seated."""
    from hq_api.domain import advisor

    if review["brief_work_id"] is not None or review["state"] not in ("ready", "in_progress"):
        return None
    if await advisor.zone_spent(tx, hub):
        return None
    code = await _advisor(tx)
    if code is None:
        return None
    holding = await hub.companies.holding()
    from hq_common.redact import scrub

    notes = [{**n, "text": scrub(n["text"])} for n in await _open_notes(tx)]
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding.id,
        company_code=holding.code,
        title=f"مرور هفتگی {review['ref']}: خلاصه‌ی یک‌صفحه‌ای"[:300],
        brief=(
            f"The weekly review {review['ref']} (week of {review['week'].isoformat()}) starts at "
            f"{review['scheduled_at'].isoformat()}. Write ONE message in your thread with the owner "
            '(message.thread, thread "A"): a one-page brief of what matters this week and your '
            "recommendation for each agenda item, every claim cited. The agenda is code; do not "
            "reorder it. Then finish (done).\n\nAgenda (JSON):\n"
            + json.dumps(review["agenda"], ensure_ascii=False, default=str)[:20000]
            + "\n\nThe owner's open quick notes (masked; read them only for this review):\n"
            + json.dumps(notes, ensure_ascii=False)[:20000]
        ),
        kind="one_off",
        priority="P2",
        assignee_code=code,
        budget=W.BudgetIn(tokens=REVIEW_TOKENS),
    )
    await tx.exec(
        "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
        id=w["id"],
        m=json.dumps(
            {"task_class": "advisor_review", "owner_zone": owner_zone.AUTO, "review": review["ref"]}
        ),
    )
    await tx.exec(
        "UPDATE owner.reviews SET brief_work_id = :w WHERE id = :id", w=w["id"], id=review["id"]
    )
    return str(w["ref"])


async def tick(tx: Tx, hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """Every 15 minutes: skip what was not done by its next week, build this
    week's agenda 30 minutes before its time, ask the advisor for the brief.
    Nothing at all while the holding is locked."""
    lock = await gate.automation_lock(tx)
    if lock is not None:
        return gate.skipped(lock)
    now = now or datetime.now(UTC)
    s, zone = await settings(tx)
    today = now.astimezone(zone).date()
    week = week_of(today)
    holding = await hub.companies.holding()
    skipped = []
    for r in await tx.all(
        """UPDATE owner.reviews SET state = 'skipped', skipped_at = :now
           WHERE week < :w AND state IN ('ready', 'in_progress') RETURNING ref""",
        now=now,
        w=week,
    ):
        skipped.append(r["ref"])
        await audit.record(
            tx, SERVICE, company_id=holding.id, action="review.skipped", action_class="A0",
            target_kind="review", target_ref=r["ref"], summary="not done by the next week",
        )  # fmt: skip
        await events.emit(tx, holding.code, "review.updated", r["ref"], {"state": "skipped"})
    out: dict[str, Any] = {"skipped": skipped}
    if not s.get("enabled", True):
        return {**out, "made": None, "reason": "off"}
    at = slot(s, zone, week)
    row = await tx.first("SELECT * FROM owner.reviews WHERE week = :w FOR UPDATE", w=week)
    if row is None:
        if now < at - BUILD_BEFORE or now > at + timedelta(days=7):
            return {**out, "made": None, "next_at": at.isoformat()}
        items = await agenda(tx, now, today)
        row = await tx.one(
            """INSERT INTO owner.reviews (company_id, week, scheduled_at, agenda)
               VALUES (:co, :w, :at, CAST(:a AS jsonb)) RETURNING *""",
            co=holding.id,
            w=week,
            at=at,
            a=json.dumps(items, ensure_ascii=False, default=str),
        )
        await audit.record(
            tx, SERVICE, company_id=holding.id, action="review.ready", action_class="A0",
            target_kind="review", target_ref=row["ref"], summary=f"{len(items)} items",
        )  # fmt: skip
        await events.emit(tx, holding.code, "review.updated", row["ref"], {"state": "ready"})
        out["made"] = row["ref"]
    out["brief"] = await brief(tx, hub, row)
    return out


async def tick_tx(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await tick(tx, hub, now)


# ------------------------------------------------------------- the owner --
REVIEW_SQL = "SELECT r.* FROM owner.reviews r"


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(REVIEW_SQL + " WHERE r.ref = :r" + (" FOR UPDATE" if lock else ""), r=ref)
    if row is None:
        raise ApiError(404, "not_found", "no such weekly review")
    return row


async def current(tx: Tx) -> dict[str, Any] | None:
    """This week's review, else the newest one still open."""
    _, zone = await settings(tx)
    week = week_of(datetime.now(UTC).astimezone(zone).date())
    row: dict[str, Any] | None = await tx.first(REVIEW_SQL + " WHERE r.week = :w", w=week)
    if row is None:
        row = await tx.first(
            REVIEW_SQL + " WHERE r.state IN ('ready', 'in_progress') ORDER BY r.week DESC LIMIT 1"
        )
    return row


async def start(tx: Tx, who: Principal, ref: str) -> dict[str, Any]:
    r = await load(tx, ref, lock=True)
    if r["state"] == "in_progress":
        return r
    if r["state"] != "ready":
        raise ApiError(409, "version_conflict", f"{ref} is {r['state']}")
    row = await tx.one(
        """UPDATE owner.reviews SET state = 'in_progress', started_at = now()
           WHERE id = :id RETURNING *""",
        id=r["id"],
    )
    await _changed(tx, who, row, "review.start", "in_progress")
    return row


async def patch_item(
    tx: Tx, who: Principal, ref: str, n: int, body: ItemPatch, expected: int
) -> dict[str, Any]:
    from hq_api.http import check_version

    r = await load(tx, ref, lock=True)
    check_version(int(r["version"]), expected)
    if r["state"] not in ("ready", "in_progress"):
        raise ApiError(409, "version_conflict", f"{ref} is {r['state']}")
    items = list(r["agenda"] or [])
    idx = next((i for i, it in enumerate(items) if int(it["n"]) == n), None)
    if idx is None:
        raise ApiError(404, "not_found", f"no item {n}")
    note = body.owner_note if body.owner_note is not None else items[idx].get("owner_note")
    items[idx] = {**items[idx], "status": body.status, "owner_note": note}
    row = await tx.one(
        """UPDATE owner.reviews SET agenda = CAST(:a AS jsonb),
               state = CASE WHEN state = 'ready' THEN 'in_progress' ELSE state END,
               started_at = COALESCE(started_at, now())
           WHERE id = :id RETURNING *""",
        a=json.dumps(items, ensure_ascii=False, default=str),
        id=r["id"],
    )
    await _changed(tx, who, row, "review.item", "in_progress", summary=f"{n}: {body.status}")
    return row


def minutes_md(r: dict[str, Any], duration_s: int) -> str:
    status_fa = {"done": "انجام شد", "deferred": "به بعد", "open": "باز ماند"}
    lines = [
        f"# صورت‌جلسه‌ی مرور هفتگی {r['ref']}",
        "",
        f"- هفته‌ی {r['week'].isoformat()} · مدت {duration_s // 60} دقیقه و {duration_s % 60} ثانیه",
        f"- خلاصه‌ی مشاور: {r['brief_message_ref'] or '—'}",
        "",
        "## موارد",
    ]
    for it in r["agenda"] or []:
        lines.append(
            f"{it['n']}. [{it['kind']}] {it['ref']}"
            + (f" ({it['company']})" if it.get("company") else "")
            + f": {it['title_fa']} — {status_fa.get(it['status'], it['status'])}"
        )
        if it.get("owner_note"):
            lines.append(f"   - یادداشت مالک: {it['owner_note']}")
    return "\n".join(lines)


async def finish(tx: Tx, hub: Any, who: Principal, ref: str) -> dict[str, Any]:
    r = await load(tx, ref, lock=True)
    if r["state"] == "done":
        return r
    if r["state"] not in ("ready", "in_progress"):
        raise ApiError(409, "version_conflict", f"{ref} is {r['state']}")
    holding = await hub.companies.holding()
    adv = await tx.first(
        """SELECT e.id, e.code FROM msg.threads t JOIN core.employees e ON e.id = t.employee_id
           WHERE t.code = 'A'"""
    )
    if adv is None:
        raise ApiError(409, "not_ready", "the advisor is not seated")
    now = datetime.now(UTC)
    started = r["started_at"] or now
    duration = max(0, int((now - started).total_seconds()))
    items = list(r["agenda"] or [])
    done = sum(1 for i in items if i["status"] == "done")
    deferred = sum(1 for i in items if i["status"] == "deferred")
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding.id,
        company_code=holding.code,
        title=f"صورت‌جلسه‌ی مرور هفتگی {r['ref']}"[:300],
        brief="The weekly review's minutes (code: the agenda, the owner's statuses and notes).",
        kind="event",
        priority="P3",
        assignee_code=adv["code"],
    )
    dl = await tx.one(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
               produced_with)
           VALUES (:co, :w, :p, :title, :summary, :body, CAST(:pw AS jsonb)) RETURNING id, ref""",
        co=holding.id,
        w=w["id"],
        p=adv["id"],
        title=f"صورت‌جلسه‌ی مرور هفتگی {r['ref']}",
        summary=f"{len(items)} مورد: {done} انجام شد، {deferred} به بعد، {len(items) - done - deferred} باز",
        body=minutes_md(r, duration),
        pw=json.dumps(
            {"label_fa": "صورت‌جلسه‌ی مرور هفتگی، قاعده‌محور", "provider": "rules",
             "review": r["ref"], "duration_s": duration}, ensure_ascii=False,
        ),
    )  # fmt: skip
    await W.set_status(tx, w, "done", delivered_at=now, closed_at=now)
    await W.event(tx, w, "delivered", SERVICE, {"deliverable": dl["ref"]})
    await events.emit(
        tx,
        holding.code,
        "deliverable.created",
        dl["ref"],
        {"work": w["ref"], "producer": adv["code"]},
    )
    row = await tx.one(
        """UPDATE owner.reviews SET state = 'done', started_at = :st, finished_at = :now,
               duration_s = :d, minutes_deliverable_id = :dl, minutes_ref = :ref
           WHERE id = :id RETURNING *""",
        st=started,
        now=now,
        d=duration,
        dl=dl["id"],
        ref=dl["ref"],
        id=r["id"],
    )
    await _changed(tx, who, row, "review.finish", "done", summary=f"{dl['ref']}, {duration}s")
    return row


async def _changed(
    tx: Tx, who: Principal, row: dict[str, Any], action: str, state: str, summary: str = ""
) -> None:
    await audit.record(
        tx, who, company_id=row["company_id"], action=action, action_class="A1",
        target_kind="review", target_ref=row["ref"], summary=summary or state,
    )  # fmt: skip
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=row["company_id"])
    await events.emit(tx, str(code), "review.updated", row["ref"], {"state": row["state"]})


# ---------------------------------------------------- the advisor's brief --
async def brief_of_run(tx: Tx, work_id: UUID) -> str | None:
    ref: str | None = await tx.scalar(
        "SELECT ref FROM owner.reviews WHERE brief_work_id = :w", w=work_id
    )
    return ref


async def brief_posted(tx: Tx, who: Principal, message: dict[str, Any], ref: str) -> None:
    """The advisor's brief is in thread A: the review keeps its message."""
    row = await tx.first("SELECT * FROM owner.reviews WHERE ref = :r FOR UPDATE", r=ref)
    if row is None or row["brief_message_ref"] is not None:
        return
    row = await tx.one(
        "UPDATE owner.reviews SET brief_message_ref = :m WHERE id = :id RETURNING *",
        m=message["ref"],
        id=row["id"],
    )
    await _changed(tx, who, row, "review.brief", row["state"], summary=message["ref"])
    if row["brief_work_id"] is not None:
        from hq_api.domain import advisor

        await advisor._close_work(
            tx, row["brief_work_id"], message["ref"], who, "weekly brief written"
        )


async def morning_line(tx: Tx, now: datetime) -> str | None:
    """One line in the morning report for a review skipped in the last week."""
    r = await tx.first(
        """SELECT ref, week FROM owner.reviews WHERE state = 'skipped' AND skipped_at >= :since
           ORDER BY skipped_at DESC LIMIT 1""",
        since=now - timedelta(days=7),
    )
    if r is None:
        return None
    return f"- **مرور هفتگی:** {r['ref']} (هفته‌ی {r['week'].isoformat()}) انجام نشد و کنار رفت"
