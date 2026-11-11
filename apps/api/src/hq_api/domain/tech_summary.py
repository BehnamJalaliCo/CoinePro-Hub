"""The weekly technical summary (contract §29.1, the owner's decision 3 of
2026-11-02): Saturday 09:00, the owner's time (Tehran), one rule-based
`report` deliverable of the holding's system employee (no model), a few lines
per company:

    open technical findings by severity and age, the week's incidents and
    their downtime, the sites' uptime, the week's spend by domain (§28.7),
    and the hires made (§29.10)

and one `report` notification for the technical team (the holding's technical
handler, §29.1), not the owner: the owner, 2026-11-06, «موارد فنی رو به من
ارجاع ندید». The findings it names are their handlers' to answer (the CTO and
SRE of each company, the hub's platform SRE for the holding). Once a week: an
ops.watch_runs row per week (a second run that week changes nothing).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import notify, routing, spend
from hq_api.domain import work as W
from hq_api.principal import Principal
from hq_api.worker.jalali import jalali_long

SYSTEM = Principal(kind="service", code="tech-summary", role="service")
SATURDAY = 5  # date.weekday(): Monday 0 .. Saturday 5
AT = time(9, 0)
SEVERITY_FA = {"critical": "بحرانی", "high": "جدی", "medium": "متوسط", "low": "کم", "info": "اطلاع"}


def week_of(now: datetime, tz: str) -> tuple[date, datetime, datetime] | None:
    """The Saturday that starts the owner's week, when it is Saturday 09:00 or
    later in the owner's zone (or any later day of that week: a missed
    Saturday is made up), with the past week's [start, end) in UTC."""
    z = ZoneInfo(tz)
    local = now.astimezone(z)
    saturday = local.date() - timedelta(days=(local.weekday() - SATURDAY) % 7)
    if local.date() == saturday and local.time() < AT:
        return None
    end = datetime.combine(saturday, AT, z).astimezone(UTC)
    return saturday, end - timedelta(days=7), end


async def _companies(tx: Tx) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT id, code, name_fa, kind FROM core.companies
           WHERE status = 'active' ORDER BY kind = 'holding', code"""
    )


async def lines_for(tx: Tx, c: dict[str, Any], start: datetime, end: datetime) -> list[str]:
    """A company's few lines (plain Persian, Latin digits)."""
    out: list[str] = []
    rows = await tx.all(
        """SELECT severity, count(*) AS n,
                  max(EXTRACT(EPOCH FROM (now() - opened_at)) / 86400)::int AS oldest
           FROM oversight.findings
           WHERE company_id = :co AND domain = ANY(:tech) AND status NOT IN ('verified', 'closed')
           GROUP BY severity""",
        co=c["id"],
        tech=list(routing.TECHNICAL),
    )
    if rows:
        by = {r["severity"]: r for r in rows}
        parts = [f"{int(by[s]['n'])} {SEVERITY_FA[s]}" for s in SEVERITY_FA if s in by]
        oldest = max(int(r["oldest"] or 0) for r in rows)
        out.append(f"یافته‌های فنی باز: {'، '.join(parts)}؛ قدیمی‌ترین {oldest} روزه")
    else:
        out.append("یافته‌ی فنی بازی نیست")
    inc = await tx.one(
        """SELECT count(*) AS n,
                  COALESCE(sum(EXTRACT(EPOCH FROM (LEAST(COALESCE(closed_at, :e), :e)
                                                   - GREATEST(opened_at, :s))) / 60), 0)::int AS mins
           FROM ops.incidents
           WHERE company_id = :co AND opened_at < :e AND COALESCE(closed_at, :e) >= :s""",
        co=c["id"],
        s=start,
        e=end,
    )
    if int(inc["n"]):
        out.append(f"حادثه‌ها: {int(inc['n'])}، روی هم {int(inc['mins'])} دقیقه از کار افتادگی")
    up = await tx.scalar(
        """SELECT round(count(*) FILTER (WHERE k.ok)::numeric / nullif(count(*), 0), 4)
           FROM ops.checks k JOIN ops.sites s ON s.id = k.site_id
           WHERE s.company_id = :co AND k.at >= :s AND k.at < :e""",
        co=c["id"],
        s=start,
        e=end,
    )
    if up is not None:
        out.append(f"در دسترس بودن سایت‌ها: {float(up) * 100:.1f}٪")
    rows = await spend.by_domain(tx, start, end, c["id"])
    if rows:
        top = "، ".join(f"{r['title_fa']} {r['share_pct']}٪" for r in rows[:3])
        out.append(f"مصرف هفته: {sum(r['tokens'] for r in rows):,} واحد ({top})")
    hires = await tx.all(
        """SELECT d.payload ->> 'title_fa' AS title FROM cartable.decisions d
           WHERE d.company_id = :co AND d.kind = 'hire' AND d.status = 'approved'
             AND d.decided_at >= :s AND d.decided_at < :e ORDER BY d.decided_at""",
        co=c["id"],
        s=start,
        e=end,
    )
    if hires:
        out.append(f"استخدام‌ها: {'، '.join(str(h['title']) for h in hires)}")
    from hq_api.domain import ads  # ⟨1.13⟩ §31.6: what a budget rule stopped this week

    out.extend(await ads.weekly_lines(tx, c["id"], start, end))
    return [HZ.humanize(x) for x in out]


async def build(tx: Tx, start: datetime, end: datetime) -> tuple[str, str]:
    """(summary, body) of the week."""
    sections: list[str] = []
    for c in await _companies(tx):
        name = c["name_fa"] or c["code"]
        sections.append(
            f"### {name}\n" + "\n".join(f"- {x}" for x in await lines_for(tx, c, start, end))
        )
    total = await spend.by_domain(tx, start, end)
    body = "\n\n".join(
        [
            "خلاصه‌ی فنی هفته (قاعده‌محور، بدون مدل). رسیدگی با مدیر فنی هر شرکت و "
            "SRE پلتفرم هلدینگ است؛ این فقط برای آگاهی توست.",
            *sections,
            "### کل هلدینگ\n" + "\n".join(spend.lines(total)),
        ]
    )
    open_tech = await tx.scalar(
        """SELECT count(*) FROM oversight.findings
           WHERE domain = ANY(:tech) AND status NOT IN ('verified', 'closed')""",
        tech=list(routing.TECHNICAL),
    )
    summary = (
        f"{int(open_tech or 0)} یافته‌ی فنی باز؛ مصرف هفته {sum(r['tokens'] for r in total):,} واحد"
    )
    return HZ.humanize(summary), body


async def run(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """Make the week's summary once (Saturday 09:00, owner's time, or later
    that week). Returns {created, week?, deliverable?}."""
    now = now or datetime.now(UTC)
    tz = str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran")
    week = week_of(now, tz)
    if week is None:
        return {"created": False, "reason": "not yet"}
    saturday, start, end = week
    key = f"tech_summary:{saturday.isoformat()}"
    holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=key)
    if await tx.scalar("SELECT 1 FROM ops.watch_runs WHERE key = :k", k=key):
        return {"created": False, "reason": "already this week", "week": saturday.isoformat()}
    summary, body = await build(tx, start, end)
    title = f"خلاصه‌ی فنی هفته · {jalali_long(saturday)}"
    sys = f"{holding['code']}-SYS"
    w = await W.create(
        tx,
        SYSTEM,
        company_id=holding["id"],
        company_code=holding["code"],
        title=title,
        brief="Rule-based weekly technical summary (no model, contract §29.1).",
        kind="event",
        priority="P3",
        assignee_code=sys,
    )
    sys_id = await tx.scalar("SELECT id FROM core.employees WHERE code = :c", c=sys)
    dl = await tx.one(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
               produced_with)
           VALUES (:co, :w, :p, :title, :summary, :body, CAST(:pw AS jsonb)) RETURNING id, ref""",
        co=holding["id"],
        w=w["id"],
        p=sys_id,
        title=title,
        summary=summary,
        body=body,
        pw='{"label_fa": "قاعده‌محور، بدون مدل", "provider": "rules"}',
    )
    await W.set_status(tx, w, "done", delivered_at=now, closed_at=now)
    await W.event(tx, w, "delivered", SYSTEM, {"deliverable": dl["ref"]})
    await tx.exec(
        """INSERT INTO ops.watch_runs (company_id, key, kind, work_id, note)
           VALUES (:co, :k, 'tech_summary', :w, :n)""",
        co=holding["id"],
        k=key,
        w=w["id"],
        n=f"deliverable {dl['ref']}",
    )
    await events.emit(
        tx, holding["code"], "deliverable.created", dl["ref"], {"work": w["ref"], "producer": sys}
    )
    # the technical team's (§29.1): it reaches the owner only as a critical item would
    n = await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="report",
        title_fa=title,
        body_fa=summary,
        link_kind="deliverable",
        link_ref=dl["ref"],
        source_kind="service",
        source_code="tech-summary",
        domain="tech",
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=holding["id"],
        action="report.tech_summary",
        action_class="A1",
        target_kind="deliverable",
        target_ref=dl["ref"],
        summary=f"weekly technical summary of {saturday.isoformat()}",
    )
    return {
        "created": True,
        "week": saturday.isoformat(),
        "deliverable": dl["ref"],
        "notification": n["id"],
    }
