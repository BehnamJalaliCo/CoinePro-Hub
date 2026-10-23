"""The oversight protocols of prompt 11 §4-§10, checked by CODE (prompt 11
§12; agents/protocols/oversight.yaml), and their activation.

  PR-006  outcome reviews (reconcile, daily 13:00): due reviews with a KPI get
          their verdict by code; an `unmeasurable` one without the proposer's
          note a week after its due day is a finding; an answered one is
          undecided (the overseer gives the verdict through protocol.result's
          `outcomes`, woken with this evidence only)
  PR-090  the cards' KPIs (rule, daily 09:50): a KPI whose value is older than
          its freshness is a finding (a KPI with no source is not: it shows
          «منبع وصل نیست», never zero)
  PR-112  risks reviewed on time (rule, Saturday 09:30): an overdue review
          whose owner's work is a day old and not done (or whose owner is the
          owner); a 15+ risk with neither a mitigation nor an unexpired
          acceptance
  PR-113  the change calendar (rule, daily 21:00): a deploy card approved in
          the last day without a calendar window, or with a `high` conflict
  PR-116  OKR check-ins (rule, Saturday 09:45): a key result without a
          check-in for 14 days; the next quarter's OKR not proposed 30 days
          before it starts

PR-090, PR-112, PR-113 and PR-116 are seeded paused from the file and made
active by migration 0026_1 (an existing database) or activate() (the seed of
a fresh one), each with an audit row; a protocol the owner has touched keeps
the owner's version. Like every protocol run, nothing runs while the holding
is locked (worker/oversight_activities.protocol_run).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import gov_calendar as CAL
from hq_api.domain import gov_common as G
from hq_api.domain import gov_kpis as K
from hq_api.domain import gov_okr as OKR
from hq_api.domain import gov_outcomes as OUT
from hq_api.domain import gov_risks as RK
from hq_api.domain import oversight_checks as C

ACTIVATED = ("PR-090", "PR-112", "PR-113", "PR-116")
NEXT_QUARTER_LEAD = timedelta(days=30)


def _code(ctx: C.CheckCtx, company_id: Any) -> str:
    return next((c for c, i in ctx.companies.items() if i == company_id), "?")


@C.check("PR-006")
async def outcomes_reviewed(ctx: C.CheckCtx) -> C.Checked:
    measured = await OUT.measure_due(ctx.tx, ctx.now)
    problems, unclear = [], []
    for r in await ctx.tx.all(
        OUT.SQL + " WHERE r.status = 'due' AND r.verdict = 'unmeasurable' AND r.due_at < :t",
        t=ctx.now - OUT.NOTE_WITHIN,
    ):
        problems.append(
            C.Problem(
                r["company_id"], r["company"],
                f"بازبینی نتیجه‌ی {r['decision_ref']} (روز {r['day']}) یادداشت پیشنهاددهنده ندارد",
                f"{r['ref']}: due {r['due_at'].isoformat()}, no KPI value; {r['proposer_code']} writes outcome.note.",
                f"outcome:{r['ref']}",
                [{"kind": "log", "ref": r["ref"], "note": f"decision {r['decision_ref']}"}],
            )
        )  # fmt: skip
    for r in await ctx.tx.all(OUT.SQL + " WHERE r.status = 'answered' ORDER BY r.due_at LIMIT 20"):
        unclear.append(
            C.Problem(
                r["company_id"], r["company"],
                f"حکم بازبینی {r['ref']} ({r['decision_ref']}، روز {r['day']})",
                f"expected {r['expected']}; measured {r['measured']}; note: {(r['proposer_note_md'] or '')[:500]}. "
                f"Give the verdict with protocol.result outcomes [{{ref: {r['ref']}, verdict, note_md}}].",
                f"outcome-verdict:{r['ref']}",
                [{"kind": "log", "ref": r["ref"], "note": "answered"}],
            )
        )  # fmt: skip
    return C.Checked(problems, ctx.companies, notes=f"decided by code: {len(measured['decided'])}",
                     data=measured, unclear=unclear)  # fmt: skip


@C.check("PR-090")
async def kpis_fresh(ctx: C.CheckCtx) -> C.Checked:
    have = await K.available(ctx.tx)
    problems = []
    for k in await ctx.tx.all(
        """SELECT k.*, c.code AS company FROM governance.kpis k JOIN core.companies c ON c.id = k.company_id
           WHERE k.status = 'active' AND c.status = 'active' ORDER BY c.code, k.key"""
    ):
        if K.state_of(dict(k), ctx.now, have) != "stale":
            continue
        problems.append(
            C.Problem(
                k["company_id"], k["company"],
                f"KPI «{k['name_fa']}» قدیمی است",
                f"{k['key']}: last value at {k['last_at'].isoformat()}, freshness {k['freshness_hours']} h.",
                f"kpi:{k['key']}",
                [{"kind": "metric", "ref": f"kpi:{k['company']}:{k['key']}", "note": str(k["last_value"])}],
            )
        )  # fmt: skip
    return C.Checked(problems, ctx.companies)


@C.check("PR-112")
async def risks_reviewed(ctx: C.CheckCtx) -> C.Checked:
    problems = []
    for r in await RK.overdue(ctx.tx, ctx.now):
        no_way = (
            r["score"] >= 15
            and not (r["mitigation_md"] or "").strip()
            and r["status"] != "accepted"
        )
        problems.append(
            C.Problem(
                r["company_id"], r["company"],
                f"ریسک {r['ref']} (امتیاز {r['score']}) "
                + ("بدون راه کاهش یا پذیرش مالک" if no_way else "به‌موقع بازبینی نشده"),
                f"{r['ref']}: review_at {r['review_at'].isoformat()}, status {r['status']}, owner {r['owner_code']}.",
                f"risk:{r['ref']}",
                [{"kind": "log", "ref": r["ref"], "note": f"score {r['score']}"}],
            )
        )  # fmt: skip
    return C.Checked(problems, ctx.companies)


@C.check("PR-113")
async def calendar_kept(ctx: C.CheckCtx) -> C.Checked:
    problems = []
    for d in await CAL.deploys_outside(ctx.tx, ctx.now - timedelta(days=1)):
        if d["event"] is None:
            problems.append(
                C.Problem(d["company_id"], d["company"], f"انتشار {d['ref']} بیرون از تقویم تغییرات",
                          f"{d['ref']} was approved without a calendar window.", f"deploy:{d['ref']}:outside",
                          [{"kind": "link", "ref": d["ref"]}])
            )  # fmt: skip
        for c in d["high"]:
            problems.append(
                C.Problem(d["company_id"], d["company"], f"انتشار {d['ref']} با تداخل بالا: {c.note_fa}"[:300],
                          f"{d['ref']} ({c.a}) went ahead with a high conflict ({c.rule}, {c.b}).",
                          f"deploy:{d['ref']}:{c.rule}:{c.b}", [{"kind": "link", "ref": d["ref"]},
                                                                {"kind": "log", "ref": c.b}])
            )  # fmt: skip
    return C.Checked(problems, ctx.companies)


@C.check("PR-116")
async def okr_checked_in(ctx: C.CheckCtx) -> C.Checked:
    problems = []
    for kr in await OKR.checkins_due(ctx.tx, ctx.now):
        problems.append(
            C.Problem(
                kr["company_id"], kr["company"], f"نتیجه‌ی کلیدی {kr['ref']} ۱۴ روز check-in ندارد",
                f"{kr['ref']} ({kr['objective']}): last check-in or activation {kr['since'].isoformat()}.",
                f"okr:{kr['ref']}", [{"kind": "log", "ref": kr["ref"]}],
            )
        )  # fmt: skip
    tz = await G.owner_tz(ctx.tx)
    nxt = G.next_quarter(G.quarter_of(G.today(tz, ctx.now)))
    start = G.local_midnight(G.quarter_bounds(nxt)[0], tz)
    if start - ctx.now <= NEXT_QUARTER_LEAD:
        for code, cid in C._ops(ctx).items():
            if not await ctx.tx.scalar(
                """SELECT 1 FROM governance.objectives WHERE company_id = :co AND quarter = :q
                     AND status IN ('proposed', 'active')""",
                co=cid,
                q=nxt,
            ):
                problems.append(
                    C.Problem(cid, code, f"OKR فصل {nxt} هنوز پیشنهاد نشده",
                              f"{nxt} starts {start.date()}; no proposed or active objective.", f"okr-next:{nxt}")
                )  # fmt: skip
    return C.Checked(problems, ctx.companies)


async def activate(tx: Tx) -> list[str]:
    """Prompt 11 §4.7, §12.2: PR-090, PR-112, PR-113, PR-116 from paused to
    active where only their seeded versions exist (the seed of a fresh
    database; migration 0026_1 does the same on an existing one)."""
    done = []
    for ref in ACTIVATED:
        p = await tx.first(
            "SELECT * FROM oversight.protocols WHERE ref = :r ORDER BY version DESC LIMIT 1", r=ref
        )
        if (
            p is None
            or p["status"] != "paused"
            or await tx.scalar(
                "SELECT 1 FROM oversight.protocols WHERE ref = :r AND source <> 'seed'", r=ref
            )
        ):
            continue
        await tx.exec(
            """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
                   schedule, scope, evidence_md, severity, answerable, status, source, created_by_kind,
                   created_by_code)
               SELECT company_id, ref, version + 1, title_fa, area, check_md, method, schedule, scope,
                      evidence_md, severity, answerable, 'active', 'seed', 'service', 'seed-prompt-11'
               FROM oversight.protocols WHERE id = :id""",
            id=p["id"],
        )
        await audit.record(
            tx, audit.SYSTEM, company_id=p["company_id"], action="protocol.activate", action_class="A1",
            target_kind="protocol", target_ref=ref, summary=f"prompt 11: paused -> active (v{p['version'] + 1})",
        )  # fmt: skip
        done.append(ref)
    return done


def now() -> datetime:
    return datetime.now(UTC)
