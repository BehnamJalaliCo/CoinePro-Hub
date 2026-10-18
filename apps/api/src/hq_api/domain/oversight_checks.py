"""The oversight protocols checked by CODE (prompt 08 §2.3: "first rule,
then AI"): each checker reads the records and returns its problems; the
protocol run turns them into findings (one open finding per problem key).

A rule or reconcile protocol without a checker here is not guessed at: it
becomes the overseer's work like the judgement methods (sample, llm, ...),
within the daily cap of model-backed runs.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_common.redact import scrub

# Append-only tables whose row counts never go down (PR-073).
APPEND_ONLY = (
    "audit.entries",
    "msg.messages",
    "cartable.resolutions",
    "cartable.deliverables",
    "work.work_events",
    "oversight.finding_history",
    "oversight.protocols",
)
# Egress refusals that mean an attempt at the hub's own or private networks (PR-033).
PRIVATE_REASONS = (
    "private_address", "loopback", "link_local", "metadata", "cgnat", "reserved_address",
    "hub_internal", "internal_name",
)  # fmt: skip


@dataclass
class Problem:
    company_id: UUID
    company: str
    title_fa: str
    body_md: str
    key: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Checked:
    """A checker's answer: its problems, and the companies it looked at (a
    company looked at without a problem passed)."""

    problems: list[Problem]
    companies: dict[str, UUID]
    notes: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckCtx:
    tx: Tx
    holding_id: UUID
    holding: str
    companies: dict[str, UUID]  # every active company (holding included)
    now: datetime
    previous: dict[str, Any]  # the last run's data (PR-073)


Checker = Callable[[CheckCtx], Awaitable[Checked]]
CHECKS: dict[str, Checker] = {}


def check(ref: str) -> Callable[[Checker], Checker]:
    def register(fn: Checker) -> Checker:
        CHECKS[ref] = fn
        return fn

    return register


def _ops(ctx: CheckCtx) -> dict[str, UUID]:
    """The operating companies (not the holding)."""
    return {c: i for c, i in ctx.companies.items() if i != ctx.holding_id}


async def _by_company(ctx: CheckCtx, sql: str, **params: Any) -> list[dict[str, Any]]:
    rows = await ctx.tx.all(sql, **params)
    return [dict(r) for r in rows]


def _code_of(ctx: CheckCtx, company_id: UUID) -> str:
    for code, cid in ctx.companies.items():
        if cid == company_id:
            return code
    return "?"


# --------------------------------------------------------------- authority --
@check("PR-010")
async def a3_never_ran_without_a_seal(ctx: CheckCtx) -> Checked:
    """An agent's tool call of class A3 or A4 that succeeded: never allowed."""
    rows = await _by_company(
        ctx,
        """SELECT company_id, actor_code, target_ref, count(*) AS n, max(seq) AS seq
           FROM audit.entries WHERE action = 'tool.call' AND action_class IN ('A3', 'A4')
             AND summary LIKE 'ok%' AND at > now() - interval '1 day'
           GROUP BY company_id, actor_code, target_ref""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"اقدام {r['target_ref']} بدون مُهر اجرا شد ({r['actor_code']})",
            f"{r['n']} tool call(s) of class A3/A4 succeeded without a sealed decision.",
            f"a3:{r['actor_code']}:{r['target_ref']}",
            [{"kind": "log", "ref": f"audit:{r['seq']}", "note": "tool.call ok"}],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


@check("PR-011")
async def no_a4_attempts(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT company_id, actor_code, count(*) AS n, max(seq) AS seq FROM audit.entries
           WHERE action = 'tool.call' AND (action_class = 'A4' OR summary LIKE '%a4_forbidden_for_ai%')
             AND at > now() - interval '1 day'
           GROUP BY company_id, actor_code""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"تلاش برای اقدام ممنوع A4 از {r['actor_code']}",
            f"{r['n']} attempt(s) at an A4 action in the last day (refused).",
            f"a4:{r['actor_code']}",
            [{"kind": "log", "ref": f"audit:{r['seq']}", "note": "A4 refused"}],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


@check("PR-012")
async def delegation_depth_and_budget(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT w.company_id, w.ref, w.depth, w.budget_tokens, p.ref AS parent,
                  p.budget_tokens AS parent_budget, p.tokens_used AS parent_used
           FROM work.work w LEFT JOIN work.work p ON p.id = w.parent_id
           WHERE w.created_at > now() - interval '1 day'
             AND (w.depth > 2 OR (p.id IS NOT NULL AND w.budget_tokens IS NOT NULL
                  AND p.budget_tokens IS NOT NULL AND w.budget_tokens > p.budget_tokens))""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"ارجاع {r['ref']} از مرز عمق یا بودجه گذشت",
            f"depth {r['depth']}; budget {r['budget_tokens']} vs parent {r['parent']} "
            f"{r['parent_budget']} (used {r['parent_used']}).",
            f"delegation:{r['ref']}",
            [{"kind": "link", "ref": r["ref"], "note": "delegation"}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx) | {ctx.holding: ctx.holding_id})


@check("PR-014")
async def locks_hold(ctx: CheckCtx) -> Checked:
    """While a company's kill switch is engaged, no agent's write tool call of
    that company succeeded after the switch changed."""
    rows = await _by_company(
        ctx,
        """SELECT a.company_id, count(*) AS n, max(a.seq) AS seq
           FROM control.kill_switches k JOIN audit.entries a ON a.company_id = k.company_id
           WHERE k.state = 'engaged' AND a.action = 'tool.call' AND a.action_class IN ('A1', 'A2')
             AND a.summary LIKE 'ok%' AND a.at > k.changed_at
           GROUP BY a.company_id""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            "اقدام نوشتنی با کلید توقف روشن موفق شد",
            f"{r['n']} write tool call(s) succeeded while the kill switch is engaged.",
            "lock-bypass",
            [{"kind": "log", "ref": f"audit:{r['seq']}", "note": "write while locked"}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


@check("PR-015")
async def workshop_branches(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT company_id, ref, branch FROM workshop.sessions
           WHERE branch IS NOT NULL AND branch NOT LIKE 'hq/%' AND updated_at > now() - interval '1 day'""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"جلسه‌ی کارگاه {r['ref']} بیرون از شاخه‌ی hq/ نوشت",
            f"branch {r['branch']!r} is not an hq/<session> branch.",
            f"branch:{r['ref']}",
            [{"kind": "link", "ref": r["ref"], "note": r["branch"]}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


# ------------------------------------------------------------------- money --
@check("PR-024")
async def workshop_spend(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT s.company_id, s.ref, s.usd, g.budget_usd, s.state FROM workshop.sessions s
           JOIN workshop.grants g ON g.id = s.grant_id
           WHERE s.usd > g.budget_usd AND s.updated_at > now() - interval '1 day'""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"خرج جلسه‌ی {r['ref']} از سقف مجوز گذشت",
            f"${r['usd']} spent against a cap of ${r['budget_usd']} (state {r['state']}).",
            f"spend:{r['ref']}",
            [{"kind": "metric", "ref": f"{r['ref']}.usd", "note": str(r["usd"])}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


@check("PR-099")
async def envelopes_hold(ctx: CheckCtx) -> Checked:
    from hq_api.domain import hiring

    problems = []
    for e in await hiring.envelopes(ctx.tx):
        cid = ctx.companies.get(e.company)
        if cid is None or not e.tokens_month:
            continue
        if e.used_month > e.tokens_month or e.committed_month > e.tokens_month:
            problems.append(
                Problem(
                    cid,
                    e.company,
                    "پاکت ماهانه‌ی توکن رعایت نشد",
                    f"used {e.used_month:,}, committed {e.committed_month:,}, envelope {e.tokens_month:,}.",
                    "envelope",
                    [
                        {
                            "kind": "metric",
                            "ref": f"{e.company}.envelope",
                            "note": f"{e.used_month}/{e.tokens_month}",
                        }
                    ],
                )
            )
    return Checked(problems, _ops(ctx))


# -------------------------------------------------------------- delivery --
@check("PR-022")
async def no_retry_loops(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT r.company_id, w.ref, count(*) AS n FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE r.queued_at > now() - interval '1 day' AND r.state IN ('failed', 'done')
             AND r.reason <> 'test'
           GROUP BY r.company_id, w.ref HAVING count(*) >= 5""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"حلقه‌ی تکرار روی {r['ref']}",
            f"{r['n']} runs on the same work item in a day.",
            f"loop:{r['ref']}",
            [{"kind": "link", "ref": r["ref"], "note": f"{r['n']} runs"}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


@check("PR-050")
async def overdue_climbs_the_ladder(ctx: CheckCtx) -> Checked:
    """Work more than an hour past due that never started up the escalation
    ladder (the Maintenance step escalates on time; this catches a stall)."""
    rows = await _by_company(
        ctx,
        """SELECT company_id, array_agg(ref ORDER BY ref) AS refs FROM work.work
           WHERE due_at < now() - interval '1 hour' AND escalation_level = 0
             AND status IN ('queued', 'in_progress', 'waiting')
           GROUP BY company_id""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            "کار عقب‌افتاده بدون پله‌ی پیگیری",
            "Overdue, not escalated: " + ", ".join(r["refs"][:30]),
            "overdue:" + ",".join(r["refs"][:5]),
            [{"kind": "link", "ref": ref, "note": "overdue"} for ref in r["refs"][:10]],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


# Model-backed protocols that need something to look at first (else skipped).
Precheck = Callable[[Tx], Awaitable[bool]]
PRECHECKS: dict[str, Precheck] = {}


async def _hires_to_review(tx: Tx) -> bool:
    """PR-098: a hire a CEO (not the owner) approved in the last 24 hours."""
    return bool(
        await tx.scalar(
            """SELECT 1 FROM cartable.decisions WHERE kind = 'hire' AND status = 'approved'
                 AND decided_by_kind = 'agent' AND decided_at > now() - interval '24 hours' LIMIT 1"""
        )
    )


PRECHECKS["PR-098"] = _hires_to_review


@check("PR-052")
async def findings_on_time(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT company_id, array_agg(ref ORDER BY ref) AS refs FROM oversight.findings
           WHERE status IN ('open', 'acknowledged', 'fixing') AND due_at < now()
             AND raised_by_code <> 'PR-052'
           GROUP BY company_id""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            "یافته‌های دیرکرده",
            "Past due: " + ", ".join(r["refs"][:30]),
            "late-findings",
            [{"kind": "link", "ref": ref, "note": "past due"} for ref in r["refs"][:10]],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


@check("PR-054")
async def challenges_delivered(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT company_id, ref FROM oversight.challenges
           WHERE status = 'missed' AND due_at > now() - interval '8 days'""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"چالش {r['ref']} به‌موقع تحویل نشد",
            "The challenge passed its due time without a submission.",
            f"missed:{r['ref']}",
            [{"kind": "link", "ref": r["ref"], "note": "missed"}],
        )
        for r in rows
    ]
    return Checked(problems, _ops(ctx))


@check("PR-051")
async def inquiries_on_time(ctx: CheckCtx) -> Checked:
    if not await ctx.tx.scalar("SELECT to_regclass('oversight.inquiries') IS NOT NULL"):
        return Checked([], {}, notes="inquiries are not built yet")
    rows = await _by_company(
        ctx,
        """SELECT company_id, array_agg(ref ORDER BY ref) AS refs FROM oversight.inquiries
           WHERE status IN ('open', 'late') AND due_at < now() GROUP BY company_id""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            "پرسش‌های رسمی بی‌جواب از موعد گذشته",
            "Late: " + ", ".join(r["refs"][:30]),
            "late-inquiries",
            [{"kind": "link", "ref": ref, "note": "late"} for ref in r["refs"][:10]],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


# ---------------------------------------------------------------- security --
@check("PR-030")
async def no_secrets_in_outputs(ctx: CheckCtx) -> Checked:
    """Secret patterns in what agents wrote in the last day (messages,
    deliverables): only WHERE, never the value."""
    rows = await _by_company(
        ctx,
        """SELECT company_id, ref, body FROM msg.messages
             WHERE author_kind = 'agent' AND created_at > now() - interval '1 day'
           UNION ALL
           SELECT company_id, ref, coalesce(body, '') || ' ' || coalesce(summary, '') FROM cartable.deliverables
             WHERE created_at > now() - interval '1 day'
           LIMIT 2000""",
    )
    hits: dict[UUID, list[str]] = {}
    for r in rows:
        text = str(r["body"] or "")
        if text and scrub(text) != text:
            hits.setdefault(r["company_id"], []).append(r["ref"])
    problems = [
        Problem(
            cid,
            _code_of(ctx, cid),
            "الگوی رمز یا داده‌ی حساس در خروجی ایجنت",
            "Found in: " + ", ".join(refs[:30]) + " (values never shown).",
            "secret:" + ",".join(sorted(refs)[:5]),
            [{"kind": "link", "ref": ref, "note": "pattern"} for ref in refs[:10]],
        )
        for cid, refs in hits.items()
    ]
    return Checked(problems, ctx.companies)


@check("PR-033")
async def no_private_egress(ctx: CheckCtx) -> Checked:
    if not await ctx.tx.scalar("SELECT to_regclass('egress.log') IS NOT NULL"):
        return Checked([], {}, notes="no egress log")
    rows = await _by_company(
        ctx,
        """SELECT company_id, actor, run_id, host, blocked_reason, count(*) AS n FROM egress.log
           WHERE (blocked_reason = ANY(:r) OR blocked_reason LIKE 'embedded_%')
             AND at > now() - interval '1 hour'
           GROUP BY company_id, actor, run_id, host, blocked_reason""",
        r=list(PRIVATE_REASONS),
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"تلاش برای رسیدن به شبکه‌ی خصوصی از {r['actor']}",
            f"{r['n']} request(s) to {r['host']} refused ({r['blocked_reason']}); run {r['run_id']}.",
            f"egress:{r['actor']}:{r['host']}",
            [{"kind": "log", "ref": f"run:{r['run_id']}", "note": r["blocked_reason"]}],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


# -------------------------------------------------------------- operations --
@check("PR-060")
async def sites_healthy(ctx: CheckCtx) -> Checked:
    rows = await _by_company(
        ctx,
        """SELECT s.company_id, s.url, c.tls_days_left, s.consecutive_failures,
                  EXISTS (SELECT 1 FROM ops.incidents i WHERE i.site_id = s.id AND i.closed_at IS NULL) AS incident
           FROM ops.sites s
           LEFT JOIN LATERAL (SELECT tls_days_left FROM ops.checks k WHERE k.site_id = s.id
                              ORDER BY k.at DESC LIMIT 1) c ON true
           WHERE s.enabled AND NOT s.canary
             AND ((c.tls_days_left IS NOT NULL AND c.tls_days_left < 14) OR s.consecutive_failures >= 3)""",
    )
    problems = []
    for r in rows:
        if r["consecutive_failures"] >= 3 and r["incident"] and (r["tls_days_left"] or 99) >= 14:
            continue  # failing, but with an open incident: being handled
        why = (
            f"TLS {r['tls_days_left']} days left"
            if r["tls_days_left"] is not None and r["tls_days_left"] < 14
            else f"{r['consecutive_failures']} failed checks, no open incident"
        )
        problems.append(
            Problem(
                r["company_id"],
                _code_of(ctx, r["company_id"]),
                f"سلامت سایت: {r['url']}",
                why,
                f"site:{r['url']}",
                [{"kind": "metric", "ref": r["url"], "note": why}],
            )
        )
    return Checked(problems, _ops(ctx))


@check("PR-062")
async def hub_healthy(ctx: CheckCtx) -> Checked:
    row = await ctx.tx.first(
        "SELECT at, data FROM ops.hub_health WHERE company_id = :co", co=ctx.holding_id
    )
    problems = []
    if row is not None:
        d = dict(row["data"] or {})
        why = []
        down = [s for s, v in (d.get("up") or {}).items() if float(v) < 1]
        if down:
            why.append("down: " + ", ".join(sorted(down)[:10]))
        if float(d.get("disk_used_pct") or 0) > 85:
            why.append(f"disk {d['disk_used_pct']}%")
        if float(d.get("memory_used_pct") or 0) > 90:
            why.append(f"memory {d['memory_used_pct']}%")
        cert = d.get("certificate_days_left")
        if isinstance(cert, int | float) and cert < 14:
            why.append(f"certificate {cert} days")
        if why:
            problems.append(
                Problem(
                    ctx.holding_id,
                    ctx.holding,
                    "سلامت خود هاب",
                    "; ".join(why),
                    "hub:" + ",".join(why)[:150],
                    [{"kind": "metric", "ref": "health.hub", "note": "; ".join(why)}],
                )
            )
    return Checked(problems, {ctx.holding: ctx.holding_id})


@check("PR-070")
async def hourly_backup_fresh(ctx: CheckCtx) -> Checked:
    row = await ctx.tx.first(
        "SELECT at, hourly FROM backup.status WHERE company_id = :co", co=ctx.holding_id
    )
    hourly = dict((row or {}).get("hourly") or {})
    last = hourly.get("last_ok_at")
    why = []
    if not last:
        why.append("no successful hourly backup yet")
    else:
        at = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if ctx.now - at.astimezone(UTC) > _hours(2):
            why.append(f"last good hourly backup {last}")
    lag = (hourly.get("wal") or {}).get("lag_s") if isinstance(hourly.get("wal"), dict) else None
    if isinstance(lag, int | float) and lag > 300:
        why.append(f"WAL lag {int(lag)} s")
    problems = []
    if why:
        problems.append(
            Problem(
                ctx.holding_id,
                ctx.holding,
                "backup ساعتی سالم یا تازه نیست",
                "; ".join(why),
                "backup-hourly",
                [{"kind": "metric", "ref": "backups.status", "note": "; ".join(why)}],
            )
        )
    return Checked(problems, {ctx.holding: ctx.holding_id})


@check("PR-071")
async def restore_test_passed(ctx: CheckCtx) -> Checked:
    row = await ctx.tx.first(
        "SELECT at, ok, snapshot FROM backup.restore_tests WHERE company_id = :co ORDER BY at DESC LIMIT 1",
        co=ctx.holding_id,
    )
    problems = []
    if row is not None and not row["ok"]:
        problems.append(
            Problem(
                ctx.holding_id,
                ctx.holding,
                "تست بازیابی هفتگی قبول نشد",
                f"restore test of {row['at'].isoformat()} failed (snapshot {row['snapshot']}).",
                f"restore:{row['at'].date()}",
                [{"kind": "log", "ref": f"restore_test:{row['at'].isoformat()}", "note": "failed"}],
            )
        )
    return Checked(problems, {ctx.holding: ctx.holding_id})


@check("PR-072")
async def audit_chain_verifies(ctx: CheckCtx) -> Checked:
    row = await ctx.tx.one("SELECT ok, checked, first_bad_seq FROM audit.verify_chain()")
    problems = []
    if not row["ok"]:
        problems.append(
            Problem(
                ctx.holding_id,
                ctx.holding,
                "زنجیره‌ی Audit سالم نیست",
                f"chain breaks at seq {row['first_bad_seq']} ({row['checked']} rows checked).",
                "audit-chain",
                [{"kind": "log", "ref": f"audit:{row['first_bad_seq']}", "note": "chain break"}],
            )
        )
    return Checked(problems, {ctx.holding: ctx.holding_id}, data={"checked": row["checked"]})


@check("PR-073")
async def nothing_deleted(ctx: CheckCtx) -> Checked:
    counts: dict[str, int] = {}
    for table in APPEND_ONLY:
        if await ctx.tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table):
            counts[table] = int(await ctx.tx.scalar(f"SELECT count(*) FROM {table}"))  # noqa: S608 - fixed list
    before = dict(ctx.previous.get("counts") or {})
    shrunk = {t: (before[t], n) for t, n in counts.items() if t in before and n < int(before[t])}
    problems = []
    if shrunk:
        problems.append(
            Problem(
                ctx.holding_id,
                ctx.holding,
                "ردیف از جدول append-only کم شد",
                "; ".join(f"{t}: {a} -> {b}" for t, (a, b) in shrunk.items()),
                "deleted:" + ",".join(sorted(shrunk)),
                [
                    {"kind": "metric", "ref": t, "note": f"{a} -> {b}"}
                    for t, (a, b) in shrunk.items()
                ],
            )
        )
    return Checked(problems, {ctx.holding: ctx.holding_id}, data={"counts": counts})


@check("PR-097")
async def watch_report_current(ctx: CheckCtx) -> Checked:
    from hq_api.domain import oversight as O

    w = await O.open_watch(ctx.tx)
    if w is None:
        return Checked([], {ctx.holding: ctx.holding_id}, notes="watch mode is off")
    await O.refresh_report(ctx.tx, ctx.holding)
    return Checked([], {ctx.holding: ctx.holding_id}, notes="watch report refreshed")


# -------------------------------------------- other forks' records (guarded) --
@check("PR-034")
async def skills_reviewed(ctx: CheckCtx) -> Checked:
    if not await ctx.tx.scalar("SELECT to_regclass('knowledge.skills') IS NOT NULL"):
        return Checked([], {}, notes="skills are not built yet")
    rows = await _by_company(
        ctx,
        """SELECT company_id, ref FROM knowledge.skills
           WHERE status = 'active' AND coalesce(review->>'verdict', '') <> 'pass'""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            f"مهارت {r['ref']} بی‌بازبینی فعال است",
            "An active skill without a passing review.",
            f"skill:{r['ref']}",
            [{"kind": "link", "ref": r["ref"], "note": "no pass"}],
        )
        for r in rows
    ]
    return Checked(problems, ctx.companies)


@check("PR-080")
async def stars_are_honest(ctx: CheckCtx) -> Checked:
    if not await ctx.tx.scalar("SELECT to_regclass('people.stars') IS NOT NULL"):
        return Checked([], {}, notes="stars are not built yet")
    rows = await _by_company(
        ctx,
        """SELECT company_id, count(*) AS n, count(*) FILTER (WHERE stars = 5) AS fives
           FROM people.stars WHERE created_at > now() - interval '7 days' AND counted
           GROUP BY company_id""",
    )
    problems = [
        Problem(
            r["company_id"],
            _code_of(ctx, r["company_id"]),
            "تورم ستاره‌ها",
            f"{r['fives']} of {r['n']} counted stars this week are fives (> 70%).",
            "stars-inflation",
            [{"kind": "metric", "ref": "stars.fives", "note": f"{r['fives']}/{r['n']}"}],
        )
        for r in rows
        if r["n"] >= 3 and r["fives"] / r["n"] > 0.7
    ]
    return Checked(problems, _ops(ctx))


def _hours(n: int) -> Any:
    from datetime import timedelta

    return timedelta(hours=n)


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
