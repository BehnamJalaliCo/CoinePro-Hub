"""The holding academy (prompt 08 §7, contract §18.6).

Curricula and golden eval suites are data (agents/academy, seeded once).
An eval run gives each case to the role under test (its charter, plus the
skill or the draft rule under test, on its model) and a judge scores the
answer against the case's rubric. THE GATE: a new charter rule, skill or
model goes live only with score >= baseline - 1; the baseline rises when a
version goes live. The owner's teaching follows one path: the AI Ops head
drafts a precise proposal (`teach.draft`), the overseer reviews it, an eval
runs, the owner approves (step-up `academy.approve`). Charters live in
agents/ and are never edited here: an approved charter rule becomes a sealed
addendum after the role's charter. Evals cost tokens: they are booked in the
treasury and held under a monthly cap (a share of the holding's budget).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import skills as S
from hq_api.domain import work as W
from hq_api.domain.hiring import jalali_month_start
from hq_api.errors import ApiError
from hq_common import charters as C

log = logging.getLogger("hq_api.academy")

SUITE_REF = r"^EV-[0-9]{3,6}$"
TEACHING_REF = r"^TE-[0-9]{4,8}$"
DEFAULT_SUITE = "EV-001"  # evidence discipline: every role
PROPOSAL_KINDS = ("charter_rule", "skill", "memory", "playbook")
BUDGET_WARN = 0.8
# What one case is held at against the monthly cap while its run is queued or
# running (8.1 §2.11): the role's answer (system prompt + up to 4000 output
# tokens) and the judge's score. Replaced by what the run really used.
EVAL_CASE_ESTIMATE = 15_000
RESERVE_HOURS = 6  # how long a queued or running run holds its estimate
RECENT_RUNS = 10  # GET /academy/evals: each suite's last runs, oldest first
TREND_SCORES = 12  # a training record's trend: the last 12 eval scores, oldest first


class Subject(BaseModel):
    kind: Literal["charter", "skill", "model"]
    ref: str = Field(min_length=1, max_length=60)
    version: str | int = Field(description="charter/skill version; for kind model, the model id")


class CaseResult(BaseModel):
    id: str
    score: float
    notes: str


class RunTokens(BaseModel):
    input: int
    output: int


class EvalRun(BaseModel):
    """Contract §18.15: `score` and `passed` are null until the run is `done`;
    a `failed` run (any model call failed) is never a pass."""

    id: UUID
    suite: str
    subject: Subject
    state: Literal["queued", "running", "done", "failed"]
    score: float | None
    passed: bool | None
    cases: list[CaseResult]
    at: datetime
    tokens: RunTokens
    equiv_cost_usd: Decimal
    # ⟨1.4⟩ beside the contract's fields
    purpose: str
    gate: dict[str, Any] | None
    error: str | None = None
    finished_at: datetime | None


class EvalCase(BaseModel):
    id: str
    input_md: str
    rubric_md: str
    weight: float


class Baseline(BaseModel):
    subject: Subject
    score: float


class EvalSuite(BaseModel):
    ref: str
    role: str
    title_fa: str
    cases: list[EvalCase]
    baseline: Baseline | None
    recent: list[EvalRun] = Field(default_factory=list)  # the last 10 runs, oldest first


class Curriculum(BaseModel):
    role: str
    version: int
    modules: list[dict[str, Any]]
    updated_at: datetime


class TeachingEval(BaseModel):
    id: UUID
    score: float | None
    baseline: float | None
    passed: bool | None


class Teaching(BaseModel):
    id: UUID
    ref: str
    target: dict[str, str]
    source: str
    text_md: str
    file_id: UUID | None
    proposal: dict[str, Any] | None
    eval_run: TeachingEval | None
    status: Literal["drafting", "proposed", "approved", "rejected"]
    created_at: datetime
    # ⟨1.4⟩ beside the contract's fields
    review: dict[str, Any] | None
    precheck: dict[str, Any] | None
    result: dict[str, Any] | None
    decided_at: datetime | None


class TrainingRecord(BaseModel):
    employee: str
    charter_version: int | None
    curriculum_version: int | None
    skills: list[str]
    evals: list[dict[str, Any]]
    lessons: list[str]
    trend: list[float]
    # ⟨1.4⟩ the owner's sealed rules the role runs with
    addenda: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    month_start: str
    cap_tokens: int
    used_tokens: int  # used by runs, plus what queued and running runs hold
    share: float
    warning: bool
    reserved_tokens: int = 0  # ⟨8.1⟩ of used_tokens: held for queued and running runs


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


# ------------------------------------------------------------------ seeds --
def _root(lib: C.Library | None) -> Path:
    return (lib.root if lib is not None else S.agents_dir()) / "academy"


async def seed(tx: Tx, holding_id: UUID, lib: C.Library | None) -> dict[str, int]:
    """Curricula and eval suites from agents/academy, once (rows are only
    added; a suite's baseline then lives here)."""
    root = _root(lib)
    added = {"curricula": 0, "eval_suites": 0}
    cur = root / "curricula.yaml"
    if cur.exists():
        data = yaml.safe_load(cur.read_text(encoding="utf-8")) or {}
        version = int(data.get("version", 1))
        for c in data.get("curricula") or []:
            row = await tx.first(
                """INSERT INTO academy.curricula (company_id, role, version, modules)
                   VALUES (:co, :role, :v, CAST(:m AS jsonb))
                   ON CONFLICT (role, version) DO NOTHING RETURNING id""",
                co=holding_id,
                role=str(c["role"]),
                v=version,
                m=json.dumps(c.get("modules") or [], ensure_ascii=False),
            )
            added["curricula"] += row is not None
    for path in sorted((root / "evals").glob("EV-*.yaml")):
        try:
            s = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cases = [
                {
                    "id": str(c["id"]),
                    "input_md": str(c["input"]),
                    "rubric_md": str(c["rubric"]),
                    "weight": float(c.get("weight", 1)),
                    **({"sensitive": True} if c.get("sensitive") else {}),
                }
                for c in s.get("cases") or []
            ]
            row = await tx.first(
                """INSERT INTO academy.eval_suites (company_id, ref, role, title_fa, cases, baseline)
                   VALUES (:co, :ref, :role, :t, CAST(:cases AS jsonb), CAST(:b AS jsonb))
                   ON CONFLICT (ref) DO NOTHING RETURNING id""",
                co=holding_id,
                ref=str(s["ref"]),
                role=str(s.get("role") or "all"),
                t=str(s.get("title_fa") or s["ref"])[:200],
                cases=json.dumps(cases, ensure_ascii=False),
                b=json.dumps(s["baseline"]) if isinstance(s.get("baseline"), dict) else None,
            )
            added["eval_suites"] += row is not None
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            log.warning("eval suite skipped", extra={"file": path.name, "error": str(exc)[:200]})
    return added


# ---------------------------------------------------------------- budget --
async def budget(tx: Tx, settings: Any) -> Budget:
    """This (Jalali) month's academy tokens against its cap: a share of the
    holding's monthly budget (every company's envelope), or a fixed default
    while no envelope is set."""
    start = jalali_month_start(datetime.now(UTC).date())
    total = await tx.scalar(
        """SELECT COALESCE(sum(token_limit), 0) FROM llm.budgets
           WHERE enabled AND period = 'month' AND scope_type = 'company'"""
    )
    share = float(settings.academy_budget_share)
    cap = int(int(total or 0) * share) if total else int(settings.academy_monthly_tokens)
    # A queued or running run holds its estimate (less what it used so far)
    # for as long as it can still run: RESERVE_HOURS after it was queued (a
    # run lasts at most 90 minutes; one whose workflow never started is stale).
    row = await tx.one(
        """SELECT COALESCE(sum(tokens), 0) AS used,
                  COALESCE(sum(GREATEST(reserved_tokens - tokens, 0))
                           FILTER (WHERE status IN ('queued', 'running')
                                     AND at > now() - make_interval(hours => :h)), 0) AS held
           FROM academy.eval_runs
           WHERE at >= CAST(:s AS date)""",
        s=start,
        h=RESERVE_HOURS,
    )
    used = int(row["used"] or 0) + int(row["held"] or 0)
    return Budget(
        month_start=start.isoformat(),
        cap_tokens=cap,
        used_tokens=used,
        share=share,
        warning=used >= cap * BUDGET_WARN,
        reserved_tokens=int(row["held"] or 0),
    )


# ------------------------------------------------------------------ evals --
async def suite(tx: Tx, ref: str) -> dict[str, Any]:
    row = await tx.first("SELECT * FROM academy.eval_suites WHERE ref = :r", r=ref)
    if row is None:
        raise ApiError(404, "not_found", "no such eval suite")
    return row


def render_baseline(value: Any) -> Baseline | None:
    b = _j(value) or {}
    if b.get("score") is None or not isinstance(b.get("subject"), dict):
        return None
    return Baseline(subject=Subject.model_validate(b["subject"]), score=float(b["score"]))


def render_suite(r: dict[str, Any], recent: list[dict[str, Any]] | None = None) -> EvalSuite:
    return EvalSuite(
        ref=r["ref"],
        role=r["role"],
        title_fa=r["title_fa"],
        cases=[EvalCase.model_validate(c) for c in _j(r["cases"]) or []],
        baseline=render_baseline(r["baseline"]),
        recent=[render_run(x) for x in recent or []],
    )


def render_run(r: dict[str, Any]) -> EvalRun:
    done = r["status"] == "done"
    return EvalRun(
        id=r["id"],
        suite=r["suite_ref"],
        subject=Subject.model_validate(_j(r["subject"])),
        state=r["status"],
        score=float(r["score"]) if done and r["score"] is not None else None,
        passed=r["passed"] if done else (False if r["status"] == "failed" else None),
        cases=[CaseResult.model_validate(c) for c in _j(r["cases"]) or []],
        at=r["at"],
        tokens=RunTokens(input=int(r["input_tokens"] or 0), output=int(r["output_tokens"] or 0)),
        equiv_cost_usd=Decimal(r["equiv_cost_usd"] or 0),
        purpose=r["purpose"],
        gate=_j(r["gate"]),
        error=r["error"],
        finished_at=r["finished_at"],
    )


async def recent_runs(tx: Tx, refs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Each suite's last RECENT_RUNS runs, oldest first."""
    rows = await tx.all(
        """SELECT * FROM (
               SELECT r.*, row_number() OVER (PARTITION BY suite_ref ORDER BY at DESC, id DESC) AS n
               FROM academy.eval_runs r WHERE suite_ref = ANY(:refs)) x
           WHERE n <= :k ORDER BY suite_ref, at, id""",
        refs=refs,
        k=RECENT_RUNS,
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["suite_ref"], []).append(r)
    return out


async def baseline_score(tx: Tx, suite_ref: str) -> float | None:
    """The suite's baseline score now (None: no baseline yet)."""
    row = await tx.first("SELECT baseline FROM academy.eval_suites WHERE ref = :r", r=suite_ref)
    b = render_baseline(row["baseline"]) if row else None
    return b.score if b else None


async def queue_eval(
    tx: Tx,
    settings: Any,
    *,
    company_id: UUID,
    suite_ref: str,
    subject: Subject,
    purpose: str,
    by_kind: str,
    by_code: str,
    candidate: dict[str, Any] | None = None,
    skill_version_id: UUID | None = None,
    teaching_id: UUID | None = None,
) -> dict[str, Any]:
    """A queued eval run (the caller starts its workflow after commit). It
    holds an estimate against the month's academy cap while it waits and runs
    (8.1 §2.11), so runs queued together cannot pass the cap: refused with
    409 academy_budget when the estimate does not fit (a cap of 0 stops all).
    The month's runs are counted under a lock (two queues at once wait)."""
    s = await suite(tx, suite_ref)
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended('academy:budget', 0))")
    estimate = max(1, len(_j(s["cases"]) or [])) * EVAL_CASE_ESTIMATE
    b = await budget(tx, settings)
    if b.used_tokens + estimate > b.cap_tokens:
        raise ApiError(
            409,
            "academy_budget",
            f"{b.used_tokens} of {b.cap_tokens} tokens used or held; this run needs ~{estimate}",
        )
    return await tx.one(
        """INSERT INTO academy.eval_runs (company_id, suite_ref, subject, candidate, purpose,
               skill_version_id, teaching_id, requested_by_kind, requested_by_code, reserved_tokens)
           VALUES (:co, :suite, CAST(:subj AS jsonb), CAST(:cand AS jsonb), :p, :sv, :te, :bk, :bc, :est)
           RETURNING *""",
        est=estimate,
        co=company_id,
        suite=suite_ref,
        subj=subject.model_dump_json(),
        cand=json.dumps(candidate, ensure_ascii=False) if candidate else None,
        p=purpose,
        sv=skill_version_id,
        te=teaching_id,
        bk=by_kind,
        bc=by_code,
    )


def gate(score: float, baseline: dict[str, Any] | None) -> dict[str, Any]:
    """score >= baseline - 1. A suite without a baseline: this (successful)
    run sets it, but it is not a pass by itself (8.1 §2.10): a second run, now
    against that baseline, decides."""
    base = float(baseline["score"]) if baseline and baseline.get("score") is not None else None
    if base is None:
        return {"baseline": None, "threshold": None, "passed": False, "sets_baseline": True}
    threshold = round(base - 1, 2)
    return {"baseline": base, "threshold": threshold, "passed": score >= threshold}


async def set_first_baseline(tx: Tx, suite_ref: str, subject: dict[str, Any], score: float) -> bool:
    """A suite's first successful run sets its baseline (only when none is set)."""
    n = await tx.exec(
        """UPDATE academy.eval_suites SET baseline = CAST(:b AS jsonb), updated_at = now()
           WHERE ref = :r AND (baseline IS NULL OR baseline->>'score' IS NULL)""",
        r=suite_ref,
        b=json.dumps({"subject": subject, "score": score}, ensure_ascii=False),
    )
    return bool(n)


def weighted(cases: list[dict[str, Any]], scores: list[float]) -> float:
    """0..100 from case scores 0..10 by the cases' weights."""
    total = sum(float(c.get("weight", 1)) for c in cases) or 1.0
    return round(
        sum(float(c.get("weight", 1)) * s * 10 for c, s in zip(cases, scores, strict=True)) / total,
        2,
    )


async def raise_baseline(tx: Tx, suite_ref: str, subject: dict[str, Any], score: float) -> None:
    """A version went live with this score: the suite's baseline rises (never falls)."""
    row = await suite(tx, suite_ref)
    current = _j(row["baseline"]) or {}
    if current.get("score") is not None and float(current["score"]) >= score:
        return
    await tx.exec(
        """UPDATE academy.eval_suites SET baseline = CAST(:b AS jsonb), updated_at = now()
           WHERE ref = :r""",
        r=suite_ref,
        b=json.dumps({"subject": subject, "score": score}, ensure_ascii=False),
    )


def suite_for_role(curricula: list[dict[str, Any]], role: str) -> str:
    """The first eval suite of the role's curriculum (else every role's)."""
    for want in (role, "all"):
        for c in curricula:
            if c["role"] != want:
                continue
            for m in _j(c["modules"]) or []:
                for ev in m.get("evals") or []:
                    return str(ev)
    return DEFAULT_SUITE


async def curricula(tx: Tx) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT DISTINCT ON (role) * FROM academy.curricula ORDER BY role, version DESC"""
    )


def render_curriculum(r: dict[str, Any]) -> Curriculum:
    return Curriculum(
        role=r["role"],
        version=int(r["version"]),
        modules=_j(r["modules"]) or [],
        updated_at=r["updated_at"],
    )


# -------------------------------------------------------------- teachings --
def teaching_eval(run: dict[str, Any] | None) -> TeachingEval | None:
    if run is None:
        return None
    r = render_run(run)
    return TeachingEval(
        id=r.id, score=r.score, baseline=(r.gate or {}).get("baseline"), passed=r.passed
    )


async def runs_by_id(tx: Tx, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    rows = await tx.all("SELECT * FROM academy.eval_runs WHERE id = ANY(:ids)", ids=ids)
    return {r["id"]: r for r in rows}


def render_teaching(r: dict[str, Any], runs: dict[UUID, dict[str, Any]] | None = None) -> Teaching:
    return Teaching(
        id=r["id"],
        ref=r["ref"],
        target=_j(r["target"]),
        source=r["source"],
        text_md=r["text_md"],
        file_id=r["file_id"],
        proposal=_j(r["proposal"]),
        eval_run=teaching_eval((runs or {}).get(r["eval_run_id"])),
        status=r["status"],
        created_at=r["created_at"],
        review=_j(r["review"]),
        precheck=_j(r["precheck"]),
        result=_j(r["result"]),
        decided_at=r["decided_at"],
    )


async def teaching(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    sql = "SELECT * FROM academy.teachings WHERE ref = :r"
    row = await tx.first(sql + " FOR UPDATE" if lock else sql, r=ref)
    if row is None:
        raise ApiError(404, "not_found")
    return row


def target_role(lib: C.Library, tx_emp: dict[str, Any] | None, target: dict[str, Any]) -> str:
    if target["kind"] == "role":
        return str(target["ref"])
    return str((tx_emp or {}).get("role") or "employee")


async def addenda_for(tx: Tx, role: str, employee: str | None = None) -> list[dict[str, Any]]:
    """The sealed addenda a run carries: its role's, and (8.1 §2.14) those
    taught to this one employee; never another employee's."""
    return await tx.all(
        """SELECT a.id, a.role, a.version, a.text_md, a.employee_code, t.ref FROM academy.addenda a
           JOIN academy.teachings t ON t.id = a.teaching_id
           WHERE a.role = :role AND a.active
             AND (a.employee_code IS NULL OR a.employee_code = CAST(:emp AS text))
           ORDER BY a.employee_code NULLS FIRST, a.version""",
        role=role,
        emp=employee,
    )


async def apply_teaching(
    tx: Tx,
    lib: C.Library,
    t: dict[str, Any],
    *,
    company_id: UUID,
    company_code: str,
    eval_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """The owner approved it: the new version it describes, never an edit of agents/."""
    proposal = _j(t["proposal"]) or {}
    target = _j(t["target"]) or {}
    kind, text = proposal["kind"], str(proposal["diff_md"])
    emp = None
    if target["kind"] == "employee":
        emp = await tx.first(
            "SELECT id, code, role, company_id, department_id FROM core.employees WHERE code = :c",
            c=target["ref"],
        )
    role = target_role(lib, emp, target)
    if kind == "charter_rule" or (kind in ("skill", "playbook") and emp is not None):
        # A rule, or a method taught to ONE employee: an addendum for that
        # employee only (8.1 §2.14); taught to a role, the role's.
        v = await tx.scalar(
            "SELECT COALESCE(max(version), 0) + 1 FROM academy.addenda WHERE role = :r", r=role
        )
        aid = await tx.scalar(
            """INSERT INTO academy.addenda (company_id, role, version, text_md, teaching_id,
                   employee_code)
               VALUES (:co, :role, :v, :text, :t, :emp) RETURNING id""",
            co=company_id,
            role=role,
            v=v,
            text=text[:8000],
            t=t["id"],
            emp=emp["code"] if emp is not None else None,
        )
        result: dict[str, Any] = {
            "addendum": f"{role}@{v}",
            "addendum_id": str(aid),
            **({"employee": emp["code"]} if emp is not None else {}),
        }
    elif kind in ("skill", "playbook"):
        review = _j(t["review"])
        row = await S.write_version(
            tx,
            lib=lib,
            skill=None,
            company_id=company_id,
            company_code=company_code,
            name_fa=f"{'دستورکار' if kind == 'playbook' else 'مهارت'} از آموزش {t['ref']}",
            summary_fa=str(t["text_md"])[:900],
            body_md=text,
            scope=S.Scope(roles=[role]),
            eval_suite=eval_row["suite_ref"] if eval_row else None,
            source="teaching",
            by_kind="owner",
            by_code="owner",
            status="approved",
        )
        sv = await S.version_row(tx, row["id"], int(row["latest_version"]))
        await tx.exec(
            """UPDATE knowledge.skill_versions SET review = CAST(:r AS jsonb), eval = CAST(:e AS jsonb)
               WHERE id = :id""",
            id=sv["id"],
            r=json.dumps(review),
            e=json.dumps(_eval_of(eval_row)),
        )
        await S.activate(
            tx,
            row,
            int(row["latest_version"]),
            await baseline_score(tx, eval_row["suite_ref"]) if eval_row else None,
        )
        result = {"skill": f"{row['ref']}@{row['latest_version']}"}
    else:  # memory: one employee's note
        if emp is None:
            raise ApiError(
                422, "validation_failed", fields={"target": "a memory is one employee's"}
            )
        mid = await tx.scalar(
            """INSERT INTO core.employee_memory (company_id, employee_id, note, tags)
               VALUES (:co, :e, :note, ARRAY['teaching', :ref]) RETURNING id""",
            co=emp["company_id"],
            e=emp["id"],
            note=text[:4000],
            ref=t["ref"],
        )
        result = {"memory": str(mid)}
    if eval_row is not None and eval_row["score"] is not None:
        await raise_baseline(
            tx, eval_row["suite_ref"], _j(eval_row["subject"]), float(eval_row["score"])
        )
    return result


def _eval_of(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    g = _j(run["gate"]) or {}
    return {
        "suite": run["suite_ref"],
        "score": float(run["score"]) if run["score"] is not None else None,
        "baseline": g.get("baseline"),
        "passed": bool(run["passed"]) and run["status"] == "done",
        "run": str(run["id"]),
    }


async def emit_eval(tx: Tx, company_code: str, run: dict[str, Any]) -> None:
    await events.emit(
        tx,
        company_code,
        "academy.eval",
        str(run["id"]),
        {
            "suite": run["suite_ref"],
            "status": run["status"],
            "score": float(run["score"]) if run["score"] is not None else None,
            "passed": run["passed"],
        },
    )


# ------------------------------------------------------------------ wake --
async def wake(
    tx: Tx,
    who: Any,
    *,
    holding_id: UUID,
    holding_code: str,
    suffix: str,
    title: str,
    brief: str,
) -> str | None:
    """A work item for a holding position (the overseer's review, the AI Ops
    head's draft): it wakes that agent. None when the position is not there."""
    code = f"{holding_code}-{suffix}"
    if not await tx.scalar(
        "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active'", c=code
    ):
        return None
    w = await W.create(
        tx,
        who,
        company_id=holding_id,
        company_code=holding_code,
        title=title[:300],
        brief=brief[:4000],
        kind="one_off",
        priority="P2",
        assignee_code=code,
    )
    return str(w["ref"])


# ---------------------------------------------------------------- records --
async def record(tx: Tx, lib: C.Library, code: str) -> TrainingRecord:
    emp = await tx.first(
        """SELECT e.code, e.role, e.kind, c.code AS company, d.code AS department
           FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           LEFT JOIN core.departments d ON d.id = e.department_id WHERE e.code = :c""",
        c=code,
    )
    if emp is None:
        raise ApiError(404, "not_found")
    role = emp["role"] or emp["kind"]
    charter = lib.get(role)
    cur = await tx.scalar(
        "SELECT max(version) FROM academy.curricula WHERE role = :r", r=role
    ) or await tx.scalar("SELECT max(version) FROM academy.curricula WHERE role = 'all'")
    active = await S.active_for(tx, role, emp["company"], emp["department"])
    skills = [f"{s['ref']}@{s['version']}" for s in active]
    refs = [s["ref"] for s in active]
    runs = await tx.all(
        """SELECT suite_ref, score, finished_at FROM academy.eval_runs
           WHERE status = 'done' AND score IS NOT NULL
             AND ((subject->>'kind' = 'charter' AND subject->>'ref' = :role)
                  OR (subject->>'kind' = 'skill' AND subject->>'ref' = ANY(:refs))
                  OR (subject->>'kind' = 'model' AND subject->>'ref' = :role))
           ORDER BY finished_at DESC LIMIT :n""",
        role=role,
        refs=refs,
        n=max(20, TREND_SCORES),
    )
    lessons: list[str] = []
    # knowledge.lessons comes with the stars (another part of prompt 8): read
    # only when it is there with the columns this query needs.
    if (
        await tx.scalar(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_schema = 'knowledge' AND table_name = 'lessons'
                 AND column_name IN ('ref', 'company_id')"""
        )
        == 2
    ):
        lessons = [
            r["ref"]
            for r in await tx.all(
                """SELECT l.ref FROM knowledge.lessons l JOIN core.companies c ON c.id = l.company_id
                   WHERE c.code = :co ORDER BY l.ref DESC LIMIT 20""",
                co=emp["company"],
            )
        ]
    addenda = [
        f"{a['ref']} ({a['role']}@{a['version']})" for a in await addenda_for(tx, role, emp["code"])
    ]
    return TrainingRecord(
        employee=emp["code"],
        charter_version=charter.version if charter else None,
        curriculum_version=int(cur) if cur is not None else None,
        skills=skills,
        evals=[
            {"suite": r["suite_ref"], "score": float(r["score"]), "at": r["finished_at"]}
            for r in runs
        ],
        lessons=lessons,
        trend=[float(r["score"]) for r in reversed(runs[:TREND_SCORES])],
        addenda=addenda,
    )
