"""The oversight protocols of prompt 11 §1-§3 (§12; agents/protocols/oversight.yaml).

All six of prompt 11 are seeded from the file as it is, `paused`; this half
switches its three on (a new version, status active, with an audit row) the
first time the api seeds after the deploy, never again (an owner's pause
later stays):

  PR-111  knowledge fresh and sourced (rule, daily, by code): every approved
          entry has a source and an expiry; no deliverable of the last day
          cites an expired entry; review work exists 14 days before expiry
  PR-114  meetings kept their rules (rule, daily, by code): the budget, the
          rounds and the speakers per item; no unsourced or challenged claim
          in the minutes or a resolution card; a resolution only from a card
          the owner sealed
  PR-115  the charter's red lines (sample, daily): the overseer reviews the
          day's rule matches (findings raised by charter.scan_internal) and
          samples more; a judgement method, so it is the overseer's work
          (gated by the holding lock like every protocol run)
Registered on import (worker/oversight_activities.py imports this module).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import oversight_checks as C

SWITCHED_ON = ("PR-111", "PR-114", "PR-115")


async def switch_on(tx: Tx, holding_id: UUID, refs: tuple[str, ...] = SWITCHED_ON) -> list[str]:
    """Version 2, active, of each protocol whose only version is the seed's
    paused one: the feature it checks exists now (prompt 11 §12.2)."""
    done = []
    for ref in refs:
        rows = await tx.all(
            "SELECT * FROM oversight.protocols WHERE ref = :r ORDER BY version", r=ref
        )
        if len(rows) != 1 or rows[0]["status"] != "paused" or rows[0]["source"] != "seed":
            continue
        p = rows[0]
        await tx.exec(
            """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method, schedule,
                   scope, evidence_md, severity, answerable, status, source, created_by_kind, created_by_code)
               VALUES (:co, :ref, 2, :title_fa, :area, :check_md, :method, :schedule, :scope, :evidence_md,
                       :severity, :answerable, 'active', 'seed', 'service', 'prompt-11')""",
            co=holding_id,
            ref=ref,
            title_fa=p["title_fa"],
            area=p["area"],
            check_md=p["check_md"],
            method=p["method"],
            schedule=p["schedule"],
            scope=p["scope"],
            evidence_md=p["evidence_md"],
            severity=p["severity"],
            answerable=p["answerable"],
        )
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=holding_id,
            action="protocol.activate",
            action_class="A1",
            target_kind="protocol",
            target_ref=f"{ref}@2",
            summary="prompt 11: the feature it checks exists",
        )
        done.append(ref)
    return done


@C.check("PR-111")
async def knowledge_fresh_and_sourced(ctx: C.CheckCtx) -> C.Checked:
    problems: list[C.Problem] = []
    rows = await ctx.tx.all(
        """SELECT e.ref, e.version, e.company_id, e.valid_until, e.review_work_ref,
                  jsonb_array_length(e.sources) AS n
           FROM knowledge.entries e
           WHERE e.status = 'approved'
             AND (jsonb_array_length(e.sources) = 0
                  OR (e.valid_until <= CAST(now() AS date) + 14 AND e.review_work_ref IS NULL))
           LIMIT 500"""
    )
    for r in rows:
        why = "no source" if not r["n"] else "no review work 14 days before its expiry"
        problems.append(
            C.Problem(
                company_id=r["company_id"], company=C._code_of(ctx, r["company_id"]),
                title_fa=f"دانش {r['ref']}@{r['version']}: {'بی‌منبع' if not r['n'] else 'بی کار بازبینی پیش از انقضا'}",
                body_md=f"{r['ref']}@{r['version']} (valid until {r['valid_until']}): {why}.",
                key=f"knowledge:{r['ref']}:{'source' if not r['n'] else 'review'}",
                evidence=[{"kind": "knowledge", "ref": f"{r['ref']}@{r['version']}"}],
            )
        )  # fmt: skip
    cited = await ctx.tx.all(
        """SELECT d.ref AS deliverable, d.company_id, ev ->> 'ref' AS cited
           FROM cartable.deliverables d CROSS JOIN LATERAL jsonb_array_elements(d.evidence) AS ev
           WHERE d.created_at > now() - interval '1 day' AND ev ->> 'ref' ~ '^K-[0-9]{4,}'
             AND NOT EXISTS (SELECT 1 FROM knowledge.entries a WHERE a.ref = split_part(ev ->> 'ref', '@', 1)
                               AND a.status = 'approved')
             AND EXISTS (SELECT 1 FROM knowledge.entries x WHERE x.ref = split_part(ev ->> 'ref', '@', 1)
                           AND x.status = 'expired' AND x.expired_at < d.created_at)
           LIMIT 200"""
    )
    for r in cited:
        problems.append(
            C.Problem(
                company_id=r["company_id"], company=C._code_of(ctx, r["company_id"]),
                title_fa=f"خروجی {r['deliverable']} به دانش منقضی {r['cited']} استناد کرد",
                body_md=f"Deliverable {r['deliverable']} cites {r['cited']}, expired before it was written.",
                key=f"knowledge:cited:{r['deliverable']}:{r['cited']}",
                evidence=[{"kind": "deliverable", "ref": r["deliverable"]}, {"kind": "knowledge", "ref": r["cited"]}],
            )
        )  # fmt: skip
    return C.Checked(problems, C._ops(ctx), data={"approved_checked": True})


def _sourced_keys(claims: list[dict[str, Any]]) -> set[tuple[str, str | None, str | None]]:
    return {
        (c["text_fa"], c["source_kind"], c["source_ref"])
        for c in claims
        if c["status"] == "sourced"
    }


@C.check("PR-114")
async def meetings_kept_their_rules(ctx: C.CheckCtx) -> C.Checked:
    problems: list[C.Problem] = []
    meetings = await ctx.tx.all(
        """SELECT m.*, c.code AS company FROM meetings.meetings m JOIN core.companies c ON c.id = m.company_id
           WHERE m.state = 'ended' AND m.ended_at > now() - interval '1 day' AND m.type <> 'standup'
           ORDER BY m.ended_at LIMIT 200"""
    )

    def problem(m: dict[str, Any], key: str, title: str, body: str) -> None:
        problems.append(
            C.Problem(
                company_id=ctx.holding_id, company=ctx.holding, title_fa=f"جلسه‌ی {m['ref']}: {title}"[:300],
                body_md=body, key=f"meeting:{m['ref']}:{key}", evidence=[{"kind": "meeting", "ref": m["ref"]}],
            )
        )  # fmt: skip

    for m in meetings:
        s = dict(m["settings"] or {})
        if m["budget_cap"] is not None and int(m["used"]) > int(m["budget_cap"]):
            problem(
                m,
                "budget",
                "از بودجه گذشت",
                f"{m['ref']} used {m['used']} of its cap {m['budget_cap']}.",
            )
        rounds = int(
            await ctx.tx.scalar(
                "SELECT COALESCE(max(round), 0) FROM meetings.turns WHERE meeting_id = :m",
                m=m["id"],
            )
        )
        if rounds > int(s.get("max_rounds", 3)):
            problem(
                m, "rounds", "دورها از سقف گذشت", f"{rounds} rounds, at most {s.get('max_rounds')}."
            )
        for it in await ctx.tx.all("SELECT * FROM meetings.items WHERE meeting_id = :m", m=m["id"]):
            spoke = await ctx.tx.scalar(
                """SELECT count(DISTINCT speaker_code) FROM meetings.turns
                   WHERE item_id = :i AND kind IN ('statement', 'challenge', 'vote')""",
                i=it["id"],
            )
            if len(it["speakers"] or []) > int(s.get("max_speakers", 8)) or int(spoke or 0) > int(
                s.get("max_speakers", 8)
            ):
                problem(m, f"speakers:{it['n']}", f"سخنگوهای دستور {it['n']} از سقف گذشت",
                        f"item {it['n']}: {spoke} speakers, at most {s.get('max_speakers')}.")  # fmt: skip
        claims = await ctx.tx.all("SELECT * FROM meetings.claims WHERE meeting_id = :m", m=m["id"])
        sourced = _sourced_keys(claims)
        if m["minutes_ref"]:
            body = (
                await ctx.tx.scalar(
                    "SELECT body FROM cartable.deliverables WHERE ref = :r", r=m["minutes_ref"]
                )
                or ""
            )
            leaked = [
                c for c in claims if c["status"] != "sourced" and f"ادعا: {c['text_fa']}" in body
            ]
            if leaked:
                problem(
                    m,
                    "minutes",
                    "ادعای بی‌منبع در صورت‌جلسه",
                    f"{len(leaked)} unsourced or challenged claim(s) in {m['minutes_ref']}.",
                )
        cards = await ctx.tx.all(
            """SELECT d.ref, d.payload, d.status, d.decided_by_kind, r.ref AS resolution FROM cartable.decisions d
               LEFT JOIN cartable.resolutions r ON r.id = d.resolution_id
               WHERE d.kind = 'meeting_resolution' AND d.payload ->> 'meeting' = :ref""",
            ref=m["ref"],
        )
        for d in cards:
            payload = (
                d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"] or "{}")
            )
            for c in payload.get("claims") or []:
                src = c.get("source") or {}
                if (c.get("text_fa"), src.get("kind"), src.get("ref")) not in sourced:
                    problem(m, f"card:{d['ref']}", f"ادعای بی‌منبع در کارت {d['ref']}",
                            f"{d['ref']} carries a claim that is not sourced in {m['ref']}.")  # fmt: skip
                    break
            if d["resolution"] and (d["status"] != "approved" or d["decided_by_kind"] != "owner"):
                problem(m, f"seal:{d['ref']}", f"مصوبه‌ی {d['resolution']} بی مُهر مالک",
                        f"{d['resolution']} exists for {d['ref']} without the owner's seal.")  # fmt: skip
    return C.Checked(problems, {ctx.holding: ctx.holding_id}, data={"meetings": len(meetings)})
