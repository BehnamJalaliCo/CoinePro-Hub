"""The digital CEO, prediction only (prompt 12 §13, contract §21.10,
OPERATING_MODEL §1.8): it records what the owner will decide and is measured
against what the owner decides. It NEVER acts.

The red line
  - It is a service (principal `service:dceo`), not an agent: no Gateway
    tool, no thread, no notification. OPA refuses it every operation but its
    own `dceo.*` (infra/opa/policy/owner_tools.rego); decisions.rego refuses
    every service a decision. It never approves, rejects, messages or
    notifies, at any accuracy.

Predictions (dceo.predictions), for every card the owner decides, BEFORE the
decision:
  - baseline (no model, always): the owner's past verdicts on cards of the
    same kind, risk and proposer kind, Laplace-smoothed over the three
    verdicts; made with the card itself (code, no model, no outside call);
  - model (optional): Haiku 5.5 `medium`, task class dceo_predict, for medium-
    and high-risk cards, at most owner_settings.digital_ceo.max_model_per_day
    (20) a day, <= 8 000 tokens each, from the masked card, the active
    principles and the 10 most similar past decisions with the owner's verdict
    and note. Only the worker's sweep makes them, and never while the holding
    is locked or the owner zone's share is spent (then: the baseline only).
  - Each is sealed: sealed_hash = sha256 of its canonical JSON, one audit row
    (whose summary never shows the verdict); a prediction written after the
    card's decision is discarded.
Hidden until the owner decides (reveal "after", the default):
`Decision.digital_ceo_prediction` is null while pending, then {verdict,
confidence, method, correct}; with reveal "before" the owner's own card views
show it at once and those predictions are `seen_before` (outside the clean
accuracy). Scoring: the owner's verdict writes `actual` and `correct`;
`dceo.scored` (topic dceo) only then.
Principles (dceo.principles, DP-001, versioned, append-only rows): each
Saturday 11:00 a model run (dceo_principles, Sonnet 5.5, <= 120 000 tokens)
over the week's owner interactions (masked) and the missed predictions
proposes at most 5; the owner adds, edits, accepts or retires them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.domain import oversight_checks as C
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model
from hq_common import owner_zone
from hq_common.redact import redact, scrub

log = logging.getLogger("hq_api.dceo")

SERVICE = Principal(kind="service", code="dceo", role="service")
VERDICT_OF = {"approved": "approve", "rejected": "reject", "returned": "return"}
VERDICTS = ("approve", "return", "reject")  # the tie order of the baseline
PREDICT_MODEL = "claude-haiku-5-5"
PRINCIPLES_MODEL = "claude-sonnet-5-5"
PREDICT_TOKENS = 8_000
PRINCIPLES_TOKENS = 120_000
PREDICT_PROMPT_CHARS = 14_000
PRINCIPLES_PROMPT_CHARS = 200_000
MAX_PROPOSED = 5
CLEAN_BEFORE_WARNING = 30
WINDOWS = {"30d": timedelta(days=30), "90d": timedelta(days=90), "all": None}
DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "reveal": "after",
    "model_predictions": True,
    "max_model_per_day": 20,
}
PR121 = "PR-121"
Verdict = Literal["approve", "reject", "return"]


# ------------------------------------------------------------------ shapes --
class Prediction(BaseModel):
    decision: str
    kind: str
    title: str
    made_at: datetime
    method: Literal["baseline", "model"]
    verdict: Verdict
    confidence: float
    rationale_fa: str | None
    principles: list[str]
    sealed_hash: str
    seen_before: bool
    actual: Verdict | None
    correct: bool | None


class Principle(BaseModel):
    id: UUID
    ref: str
    text_fa: str
    sources: list[dict[str, Any]]
    status: Literal["proposed", "active", "retired"]
    edited_by_owner: bool
    version: int
    updated_at: datetime


class Bucket(BaseModel):
    bucket: str
    n: int
    hit_rate: float | None


class KindStat(BaseModel):
    n: int
    accuracy: float | None


class DceoStats(BaseModel):
    window: Literal["30d", "90d", "all"]
    n: int
    accuracy: float | None
    baseline_accuracy: float | None
    model_accuracy: float | None
    brier: float | None
    by_kind: dict[str, KindStat]
    calibration: list[Bucket]


class DceoSettings(BaseModel):
    enabled: bool = True
    reveal: Literal["after", "before"] = "after"
    model_predictions: bool = True
    max_model_per_day: int = 20


class DigitalCeo(BaseModel):
    stats: list[DceoStats]
    settings: DceoSettings
    hidden: int
    warning_fa: str | None = None


class Source(Model):
    kind: str = Field(min_length=1, max_length=30)
    ref: str = Field(min_length=1, max_length=60)


class PrincipleIn(Model):
    text_fa: str = Field(min_length=1, max_length=1000)
    sources: list[Source] = Field(default_factory=list, max_length=20)


class PrincipleEdit(Model):
    text_fa: str = Field(min_length=1, max_length=1000)
    status: Literal["active", "retired"] = "active"


def render_prediction(r: dict[str, Any]) -> Prediction:
    return Prediction(
        decision=r["decision_ref"],
        kind=r["decision_kind"],
        title=r["decision_title"],
        made_at=r["made_at"],
        method=r["method"],
        verdict=r["verdict"],
        confidence=float(r["confidence"]),
        rationale_fa=r["rationale_fa"],
        principles=list(r["principles"] or []),
        sealed_hash=r["sealed_hash"],
        seen_before=r["seen_before"],
        actual=r["actual"],
        correct=r["correct"],
    )


def render_principle(r: dict[str, Any]) -> Principle:
    return Principle(
        id=r["id"],
        ref=r["ref"],
        text_fa=r["text_fa"],
        sources=list(r["sources"] or []),
        status=r["status"],
        edited_by_owner=r["edited_by_owner"],
        version=r["version"],
        updated_at=r["created_at"],
    )


# --------------------------------------------------------------- settings --
async def settings(tx: Tx) -> dict[str, Any]:
    row = await tx.one("SELECT digital_ceo FROM owner.settings WHERE id = 1")
    return {**DEFAULT_SETTINGS, **(row["digital_ceo"] or {})}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sealed_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def require(hub: Any, op: str, target: dict[str, Any]) -> None:
    """OPA, for the service's own writes (the worker's sweeps)."""
    if hub is not None and getattr(hub, "policy", None) is not None:
        await hub.policy.require(
            "internal", {"principal": SERVICE.opa(), "op": op, "target": target}
        )


# --------------------------------------------------------------- baseline --
def laplace(counts: dict[str, int]) -> tuple[str, float]:
    """(verdict, confidence): p(v) = (n_v + 1) / (n + 3), the most likely
    verdict (ties: approve, return, reject)."""
    n = sum(counts.get(v, 0) for v in VERDICTS)
    probs = {v: (counts.get(v, 0) + 1) / (n + 3) for v in VERDICTS}
    best = max(VERDICTS, key=lambda v: (probs[v], -VERDICTS.index(v)))
    return best, round(probs[best], 3)


async def baseline(tx: Tx, d: dict[str, Any]) -> tuple[str, float, dict[str, Any]]:
    rows = await tx.all(
        """SELECT status, count(*) AS n FROM cartable.decisions
           WHERE kind = :k AND risk = :r AND proposer_kind = :pk AND approver_code IS NULL
             AND decided_by_kind = 'owner' AND status IN ('approved', 'rejected', 'returned')
             AND id <> :id
           GROUP BY status""",
        k=d["kind"],
        r=d["risk"],
        pk=d["proposer_kind"],
        id=d["id"],
    )
    counts = {VERDICT_OF[r["status"]]: int(r["n"]) for r in rows}
    verdict, conf = laplace(counts)
    return verdict, conf, {"counts": counts, "n": sum(counts.values())}


async def record(
    tx: Tx,
    d: dict[str, Any],
    *,
    method: str,
    verdict: str,
    confidence: float,
    basis: dict[str, Any],
    rationale_fa: str | None = None,
    principles: list[str] | None = None,
    model: str | None = None,
    usage_tokens: int = 0,
    seen_before: bool = False,
) -> dict[str, Any] | None:
    """One sealed prediction of a pending card (None: decided meanwhile, or
    this method's prediction exists). It carries the card's company: the
    baseline is sealed in the proposer's own transaction, under its RLS."""
    company = d["company_id"]
    made_at = await tx.scalar("SELECT clock_timestamp()")
    sealed = {
        "decision": d["ref"],
        "decision_version": d["version"],
        "method": method,
        "verdict": verdict,
        "confidence": round(float(confidence), 3),
        "rationale_fa": rationale_fa,
        "principles": principles or [],
        "made_at": made_at.isoformat(),
    }
    digest = sealed_hash(sealed)
    row = await tx.first(
        """INSERT INTO dceo.predictions (company_id, decision_id, decision_ref, decision_kind, decision_title,
               decision_risk, proposer_kind, method, verdict, confidence, rationale_fa, principles, basis,
               sealed, sealed_hash, made_at, seen_before, model, usage_tokens)
           SELECT :co, d.id, d.ref, d.kind, left(d.title, 300), d.risk, d.proposer_kind, :m, :v, :c, :rat,
                  :pr, CAST(:basis AS jsonb), CAST(:sealed AS jsonb), :h, :at, :seen, :model, :tok
           FROM cartable.decisions d WHERE d.id = :d AND d.status = 'pending'
           ON CONFLICT (decision_id, method) DO NOTHING RETURNING *""",
        co=company,
        d=d["id"],
        m=method,
        v=verdict,
        c=Decimal(str(round(float(confidence), 3))),
        rat=rationale_fa,
        pr=principles or [],
        basis=canonical(basis),
        sealed=canonical(sealed),
        h=digest,
        at=made_at,
        seen=seen_before,
        model=model,
        tok=usage_tokens,
    )
    if row is None:
        return None
    await audit.record(
        tx,
        SERVICE,
        company_id=company,
        action="dceo.predict",
        action_class="A0",
        target_kind="decision",
        target_ref=d["ref"],
        summary=f"{method} prediction sealed {digest[:16]}",  # never the verdict before the decision
    )
    return row


async def on_proposed(tx: Tx, d: dict[str, Any]) -> dict[str, Any] | None:
    """A new card for the owner: its baseline prediction, sealed now."""
    if d.get("approver_code") or d["status"] != "pending":
        return None
    s = await settings(tx)
    if not s.get("enabled", True):
        return None
    verdict, conf, basis = await baseline(tx, d)
    return await record(
        tx, d, method="baseline", verdict=verdict, confidence=conf, basis=basis,
        seen_before=s.get("reveal") == "before",
    )  # fmt: skip


async def score(tx: Tx, who: Principal, d: dict[str, Any], verdict: str) -> int:
    """The owner decided: each prediction made before it is scored."""
    if not who.is_owner or verdict not in VERDICT_OF:
        return 0
    actual = VERDICT_OF[verdict]
    rows = await tx.all(
        """UPDATE dceo.predictions SET actual = :a, correct = (verdict = :a), decided_at = now(),
               scored_at = now()
           WHERE decision_id = :d AND actual IS NULL AND made_at < now() RETURNING *""",
        a=actual,
        d=d["id"],
    )
    if not rows:
        return 0
    holding = await tx.one(
        "SELECT id, code FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    await audit.record(
        tx, SERVICE, company_id=holding["id"], action="dceo.score", action_class="A0",
        target_kind="decision", target_ref=d["ref"],
        summary=", ".join(f"{r['method']}: {'correct' if r['correct'] else 'missed'}" for r in rows),
    )  # fmt: skip
    await events.emit(
        tx,
        holding["code"],
        "dceo.scored",
        d["ref"],
        {r["method"]: {"verdict": r["verdict"], "correct": r["correct"]} for r in rows},
    )
    return len(rows)


async def reveal(tx: Tx, decisions: list[Any]) -> None:
    """reveal "before": the owner's card views show a pending card's
    prediction at once (the predictions were sealed `seen_before`)."""
    pending = [d for d in decisions if d.status == "pending" and d.digital_ceo_prediction is None]
    if not pending or (await settings(tx)).get("reveal") != "before":
        return
    rows = await tx.all(
        """SELECT DISTINCT ON (decision_id) decision_id, verdict, confidence, method, correct
           FROM dceo.predictions WHERE decision_id = ANY(:ids)
           ORDER BY decision_id, method = 'model' DESC""",
        ids=[d.id for d in pending],
    )
    by = {r["decision_id"]: r for r in rows}
    for d in pending:
        r = by.get(d.id)
        if r is not None:
            d.digital_ceo_prediction = {
                "verdict": r["verdict"],
                "confidence": float(r["confidence"]),
                "method": r["method"],
                "correct": r["correct"],
            }


# ------------------------------------------------------------------ model --
PREDICT_SYSTEM = (
    "You predict how the owner of a holding company will decide one decision card, from the "
    "owner's principles and past decisions. You never act and nobody sees your answer before the "
    "owner decides. Answer with ONE JSON object and nothing else: "
    '{"verdict": "approve"|"reject"|"return", "confidence": 0..1, '
    '"rationale_fa": "<at most 300 characters, Persian>", "principles": ["DP-…", ...]}.'
)


async def model_input(tx: Tx, d: dict[str, Any]) -> tuple[str, list[str]]:
    from hq_api.domain import advisor

    facts = advisor.facts_pack(d)["card"]
    active = await tx.all(
        "SELECT ref, text_fa FROM dceo.current_principles WHERE status = 'active' ORDER BY ref"
    )
    similar = await tx.all(
        """SELECT ref, kind, risk, left(title, 200) AS title, status, left(COALESCE(note, ''), 300) AS note
           FROM cartable.decisions
           WHERE kind = :k AND approver_code IS NULL AND decided_by_kind = 'owner'
             AND status IN ('approved', 'rejected', 'returned') AND id <> :id
           ORDER BY (risk = :r) DESC, decided_at DESC LIMIT 10""",
        k=d["kind"],
        r=d["risk"],
        id=d["id"],
    )
    body = {
        "card": facts,
        "principles": [{"ref": p["ref"], "text": scrub(p["text_fa"])} for p in active],
        "similar_past_decisions": [
            {**dict(s), "title": scrub(s["title"]), "note": scrub(s["note"]),
             "verdict": VERDICT_OF[s["status"]]}
            for s in similar
        ],
    }  # fmt: skip
    return canonical(redact(body, max_string=2000, max_list=20))[:PREDICT_PROMPT_CHARS], [
        p["ref"] for p in active
    ]


def parse_prediction(text: str, refs: list[str]) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("verdict") not in VERDICTS:
        return None
    try:
        conf = min(max(float(raw.get("confidence", 0)), 0.0), 1.0)
    except (TypeError, ValueError):
        return None
    cited: list[Any] = raw["principles"] if isinstance(raw.get("principles"), list) else []
    return {
        "verdict": raw["verdict"],
        "confidence": round(conf, 3),
        "rationale_fa": scrub(str(raw.get("rationale_fa") or ""))[:300] or None,
        "principles": [str(p) for p in cited if str(p) in refs][:10],
    }


async def _owner_day_count(tx: Tx, method: str) -> int:
    n = await tx.scalar(
        """SELECT count(*) FROM dceo.predictions p, owner.settings s
           WHERE s.id = 1 AND p.method = :m
             AND (p.made_at AT TIME ZONE s.timezone)::date = (now() AT TIME ZONE s.timezone)::date""",
        m=method,
    )
    return int(n or 0)


async def sweep(hub: Any, router: Any, tx_factory: Any) -> dict[str, Any]:
    """Every few minutes (worker): a baseline for a pending owner card that
    has none, then model predictions of medium- and high-risk cards inside
    the day's cap. Nothing at all while the holding is locked."""
    from hq_api.domain import advisor
    from hq_api.domain import decisions as D

    async with tx_factory() as tx:
        lock = await gate.automation_lock(tx)
        if lock is not None:
            return gate.skipped(lock)
        s = await settings(tx)
        if not s.get("enabled", True):
            return {"skipped": True, "reason": "off"}
        missing = await tx.all(
            D.DECISION_SQL  # noqa: S608 - constant SQL, every value bound
            + """ WHERE d.status = 'pending' AND d.approver_code IS NULL
                    AND NOT EXISTS (SELECT 1 FROM dceo.predictions p WHERE p.decision_id = d.id
                                    AND p.method = 'baseline')
                  ORDER BY d.created_at LIMIT 100"""
        )
        made = 0
        for d in missing:
            await require(hub, "dceo.predict", {"decision": d["ref"], "method": "baseline"})
            verdict, conf, basis = await baseline(tx, d)
            if await record(tx, d, method="baseline", verdict=verdict, confidence=conf,
                            basis=basis, seen_before=s.get("reveal") == "before"):  # fmt: skip
                made += 1
        out: dict[str, Any] = {"baseline": made, "model": 0}
        if not s.get("model_predictions", True) or router is None:
            return {**out, "model_reason": "off"}
        if await advisor.zone_spent(tx, hub):
            return {**out, "model_reason": "owner_zone_share"}  # the baseline stands
        room = int(s.get("max_model_per_day", 20)) - await _owner_day_count(tx, "model")
        if room <= 0:
            return {**out, "model_reason": "max_model_per_day"}
        todo = await tx.all(
            D.DECISION_SQL  # noqa: S608 - constant SQL, every value bound
            + """ WHERE d.status = 'pending' AND d.approver_code IS NULL AND d.risk IN ('medium', 'high')
                    AND NOT EXISTS (SELECT 1 FROM dceo.predictions p WHERE p.decision_id = d.id
                                    AND p.method = 'model')
                  ORDER BY d.created_at LIMIT :n""",
            n=room,
        )
        inputs = [(d, *(await model_input(tx, d))) for d in todo]
        holding = await hub.companies.holding()
    for d, prompt, refs in inputs:
        await require(hub, "dceo.predict", {"decision": d["ref"], "method": "model"})
        call = await router.run(
            {
                "company_code": holding.code,
                "actor_ref": f"{holding.code}-SYS",
                "task_class": "dceo_predict",
                "priority": 4,
                "model": PREDICT_MODEL,
                "effort": "medium",
                "system": PREDICT_SYSTEM,
                "prompt": prompt,
                "max_output_tokens": 600,
                "timeout_s": 60,
                "meta": {"purpose": "dceo_predict", "decision": d["ref"],
                         "owner_zone": owner_zone.AUTO},
            },
            60,
        )  # fmt: skip
        if not getattr(call, "ok", False):
            continue
        p = parse_prediction(str(getattr(call, "text", "") or ""), refs)
        if p is None:
            continue
        tokens = int(getattr(call, "input_tokens", 0) or 0) + int(
            getattr(call, "output_tokens", 0) or 0
        )
        async with tx_factory() as tx:
            await tx.exec("SELECT 1 FROM cartable.decisions WHERE id = :id FOR UPDATE", id=d["id"])
            if await record(
                tx, d, method="model", verdict=p["verdict"], confidence=p["confidence"],
                basis={"principles_offered": len(refs)}, rationale_fa=p["rationale_fa"],
                principles=p["principles"], model=getattr(call, "model", None) or PREDICT_MODEL,
                usage_tokens=tokens, seen_before=s.get("reveal") == "before",
            ):  # fmt: skip
                out["model"] += 1
            else:
                out.setdefault("discarded", 0)
                out["discarded"] += 1
    return out


# ------------------------------------------------------------------ stats --
def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def compute_stats(rows: list[dict[str, Any]], window: str) -> DceoStats:
    """From the scored, clean predictions: the primary one of each card (the
    model's when there is one), each method's accuracy, Brier, calibration."""
    by_decision: dict[Any, list[dict[str, Any]]] = {}
    for r in rows:
        by_decision.setdefault(r["decision_id"], []).append(r)
    primary = [
        next((p for p in ps if p["method"] == "model"), ps[0]) for ps in by_decision.values()
    ]
    hits = [1.0 if p["correct"] else 0.0 for p in primary]
    kinds: dict[str, list[float]] = {}
    for p, h in zip(primary, hits, strict=True):
        kinds.setdefault(p["decision_kind"], []).append(h)
    buckets: dict[int, list[float]] = {}
    for p, h in zip(primary, hits, strict=True):
        b = min(int(float(p["confidence"]) * 10), 9)
        buckets.setdefault(b, []).append(h)
    return DceoStats(
        window=window,
        n=len(primary),
        accuracy=_mean(hits),
        baseline_accuracy=_mean([1.0 if r["correct"] else 0.0 for r in rows if r["method"] == "baseline"]),
        model_accuracy=_mean([1.0 if r["correct"] else 0.0 for r in rows if r["method"] == "model"]),
        brier=_mean([(float(p["confidence"]) - h) ** 2 for p, h in zip(primary, hits, strict=True)]),
        by_kind={k: KindStat(n=len(v), accuracy=_mean(v)) for k, v in sorted(kinds.items())},
        calibration=[
            Bucket(bucket=f"{b / 10:.1f}-{(b + 1) / 10:.1f}", n=len(v), hit_rate=_mean(v))
            for b, v in sorted(buckets.items())
        ],
    )  # fmt: skip


async def stats(tx: Tx, now: datetime | None = None) -> list[DceoStats]:
    now = now or datetime.now(UTC)
    rows = [
        dict(r)
        for r in await tx.all(
            """SELECT decision_id, decision_kind, method, confidence, correct, decided_at
               FROM dceo.predictions WHERE actual IS NOT NULL AND NOT seen_before"""
        )
    ]
    out = []
    for name, span in WINDOWS.items():
        since = now - span if span else None
        part = [r for r in rows if since is None or r["decided_at"] >= since]
        out.append(compute_stats(part, name))
    return out


async def overview(tx: Tx) -> DigitalCeo:
    s = await settings(tx)
    hidden = int(
        await tx.scalar(
            "SELECT count(DISTINCT decision_id) FROM dceo.predictions WHERE NOT seen_before"
        )
        or 0
    )
    warning = None
    if hidden < CLEAN_BEFORE_WARNING:
        warning = (
            f"دقت هنوز سنجیده نشده: {hidden} پیش‌بینی پنهان از دست‌کم {CLEAN_BEFORE_WARNING}؛ "
            "با «پیش از تصمیم» پیش‌بینی‌های دیده‌شده در دقت تمیز شمرده نمیشوند."
        )
    return DigitalCeo(
        stats=await stats(tx), settings=DceoSettings.model_validate(s), hidden=hidden,
        warning_fa=warning,
    )  # fmt: skip


# ------------------------------------------------------------- principles --
async def principle(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"hq:dceo:{ref}")
    row = await tx.first("SELECT * FROM dceo.current_principles WHERE ref = :r", r=ref)
    if row is None:
        raise ApiError(404, "not_found", "no such principle")
    return row


async def add_principle(
    tx: Tx,
    who: Principal,
    *,
    text_fa: str,
    sources: list[dict[str, Any]],
    status: str,
    ref: str | None = None,
    version: int = 1,
    edited: bool = False,
) -> dict[str, Any]:
    holding = await tx.scalar(
        "SELECT id FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    if ref is None:
        ref = "DP-" + str(await tx.scalar("SELECT nextval('dceo.principle_ref_seq')")).zfill(3)
    row = await tx.one(
        """INSERT INTO dceo.principles (company_id, ref, version, text_fa, sources, status, edited_by_owner,
               created_by_kind, created_by_code)
           VALUES (:co, :ref, :v, :t, CAST(:src AS jsonb), :st, :ed, :ck, :cc) RETURNING *""",
        co=holding,
        ref=ref,
        v=version,
        t=scrub(text_fa) if who.kind != "owner" else text_fa,
        src=json.dumps(sources, ensure_ascii=False),
        st=status,
        ed=edited,
        ck="owner" if who.is_owner else "service",
        cc=who.code,
    )
    await audit.record(
        tx, who, company_id=holding, action="dceo.principle", action_class="A1",
        target_kind="principle", target_ref=f"{ref}@{version}", summary=status,
    )  # fmt: skip
    return row


async def edit_principle(
    tx: Tx, who: Principal, ref: str, body: PrincipleEdit, expected: int
) -> dict[str, Any]:
    from hq_api.http import check_version

    cur = await principle(tx, ref, lock=True)
    check_version(int(cur["version"]), expected)
    return await add_principle(
        tx, who, text_fa=body.text_fa, sources=list(cur["sources"] or []), status=body.status,
        ref=ref, version=int(cur["version"]) + 1, edited=True,
    )  # fmt: skip


async def accept_principle(tx: Tx, who: Principal, ref: str) -> dict[str, Any]:
    cur = await principle(tx, ref, lock=True)
    if cur["status"] == "active":
        return cur
    if cur["status"] != "proposed":
        raise ApiError(409, "version_conflict", f"{ref} is {cur['status']}")
    return await add_principle(
        tx, who, text_fa=cur["text_fa"], sources=list(cur["sources"] or []), status="active",
        ref=ref, version=int(cur["version"]) + 1, edited=bool(cur["edited_by_owner"]),
    )  # fmt: skip


PRINCIPLES_SYSTEM = (
    "You help the owner of a holding company write down the principles behind their decisions. "
    "From the week's interactions and the predictions that missed, propose at most 5 new or "
    "changed principles, each short and testable, each with its source refs. Answer with ONE JSON "
    'object and nothing else: {"principles": [{"text_fa": "<Persian, <= 300 characters>", '
    '"changes": "DP-…"|null, "sources": [{"kind": "decision"|"interaction"|"prediction", '
    '"ref": "…"}]}]}.'
)


async def principles_input(tx: Tx, now: datetime) -> dict[str, Any]:
    since = now - timedelta(days=7)
    interactions = await tx.all(
        """SELECT at, kind, action, target_kind, target_ref, data FROM owner.interactions
           WHERE at >= :s ORDER BY at LIMIT 500""",
        s=since,
    )
    missed = await tx.all(
        """SELECT p.decision_ref, p.decision_kind, p.decision_risk, p.method, p.verdict, p.actual,
                  left(COALESCE(d.note, ''), 300) AS note
           FROM dceo.predictions p JOIN cartable.decisions d ON d.id = p.decision_id
           WHERE p.correct = false AND p.decided_at >= :s ORDER BY p.decided_at LIMIT 100""",
        s=since,
    )
    current = await tx.all(
        "SELECT ref, text_fa, status FROM dceo.current_principles WHERE status <> 'retired' ORDER BY ref"
    )
    out: dict[str, Any] = redact(
        {
            "interactions": [dict(i) for i in interactions],
            "missed_predictions": [dict(m) for m in missed],
            "current_principles": [dict(c) for c in current],
        },
        max_string=500,
        max_list=500,
    )
    return out


def parse_principles(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return []
    items = raw.get("principles") if isinstance(raw, dict) else None
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not str(it.get("text_fa") or "").strip():
            continue
        sources = [
            {"kind": str(s.get("kind"))[:30], "ref": str(s.get("ref"))[:60]}
            for s in (it["sources"] if isinstance(it.get("sources"), list) else [])
            if isinstance(s, dict) and s.get("kind") and s.get("ref")
        ][:20]
        if it.get("changes") and re.fullmatch(r"DP-[0-9]{3,}", str(it["changes"])):
            sources.append({"kind": "principle", "ref": str(it["changes"])})
        out.append({"text_fa": scrub(str(it["text_fa"]))[:1000], "sources": sources})
    return out[:MAX_PROPOSED]


async def propose_principles(
    hub: Any, router: Any, tx_factory: Any, now: datetime | None = None
) -> dict[str, Any]:
    """Saturday 11:00 (worker): at most 5 proposed principles. Nothing while
    the holding is locked or the owner zone is spent; no model call when the
    week has nothing to learn from."""
    from hq_api.domain import advisor

    now = now or datetime.now(UTC)
    async with tx_factory() as tx:
        lock = await gate.automation_lock(tx)
        if lock is not None:
            return gate.skipped(lock)
        s = await settings(tx)
        if not s.get("enabled", True) or not s.get("model_predictions", True):
            return {"skipped": True, "reason": "off"}
        if await advisor.zone_spent(tx, hub):
            return {"skipped": True, "reason": "owner_zone_share"}
        body = await principles_input(tx, now)
        holding = await hub.companies.holding()
    if not body["interactions"] and not body["missed_predictions"]:
        return {"proposed": 0, "reason": "nothing to learn from"}
    if router is None:
        return {"skipped": True, "reason": "no router"}
    await require(hub, "dceo.principles", {"week": now.date().isoformat()})
    call = await router.run(
        {
            "company_code": holding.code,
            "actor_ref": f"{holding.code}-SYS",
            "task_class": "dceo_principles",
            "priority": 4,
            "model": PRINCIPLES_MODEL,
            "effort": "medium",
            "system": PRINCIPLES_SYSTEM,
            "prompt": canonical(body)[:PRINCIPLES_PROMPT_CHARS],
            "max_output_tokens": 4000,
            "timeout_s": 300,
            "meta": {"purpose": "dceo_principles", "owner_zone": owner_zone.AUTO},
        },
        300,
    )
    if not getattr(call, "ok", False):
        return {"proposed": 0, "reason": str(getattr(call, "status", "error"))}
    made = []
    async with tx_factory() as tx:
        for p in parse_principles(str(getattr(call, "text", "") or "")):
            row = await add_principle(
                tx, SERVICE, text_fa=p["text_fa"], sources=p["sources"], status="proposed"
            )
            made.append(row["ref"])
    return {"proposed": len(made), "refs": made}


# ------------------------------------------------------------------ PR-121 --
@C.check(PR121)
async def predictions_sealed(ctx: C.CheckCtx) -> C.Checked:
    """Every prediction scored in the last day was made and sealed before the
    owner's decision (made_at < decided_at, its sealed_hash matches its
    canonical JSON) and was not shown before it (seen_before false, unless
    the owner chose reveal "before")."""
    rows = await ctx.tx.all(
        """SELECT p.*, d.decided_at AS card_decided_at FROM dceo.predictions p
           JOIN cartable.decisions d ON d.id = p.decision_id
           WHERE p.scored_at >= :since""",
        since=ctx.now - timedelta(days=1),
    )
    reveal_before = (await settings(ctx.tx)).get("reveal") == "before"
    problems = []
    for r in rows:
        why = []
        if r["card_decided_at"] is None or r["made_at"] >= r["card_decided_at"]:
            why.append("made after the decision")
        if sealed_hash(dict(r["sealed"] or {})) != r["sealed_hash"]:
            why.append("sealed_hash does not match")
        if r["seen_before"] and not reveal_before:
            why.append("shown before the decision")
        if why:
            problems.append(
                C.Problem(ctx.holding_id, ctx.holding,
                          f"پیش‌بینی {r['decision_ref']} ({r['method']}) مُهر درست ندارد",
                          f"{r['decision_ref']} {r['method']}: {', '.join(why)}.",
                          f"dceo:{r['decision_ref']}:{r['method']}",
                          [{"kind": "log", "ref": r["decision_ref"]}])
            )  # fmt: skip
    return C.Checked(problems, {ctx.holding: ctx.holding_id}, data={"checked": len(rows)})


async def activate(tx: Tx) -> bool:
    """PR-121 from paused to active where only its seeded version exists (the
    seed of a fresh database; migration 0027_2 does it on an existing one)."""
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended('hq:protocol:PR-121', 0))")
    cur = await tx.first("SELECT * FROM oversight.current_protocols WHERE ref = :r", r=PR121)
    if cur is None or cur["version"] != 1 or cur["source"] != "seed" or cur["status"] != "paused":
        return False
    await tx.exec(
        """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
               schedule, scope, evidence_md, severity, answerable, status, source, created_by_kind,
               created_by_code, calendar)
           SELECT company_id, ref, 2, title_fa, area, check_md, method, schedule, scope, evidence_md,
                  severity, answerable, 'active', 'seed', 'service', 'prompt-12', calendar
           FROM oversight.protocols WHERE id = :id""",
        id=cur["id"],
    )
    await audit.record(
        tx, audit.SYSTEM, company_id=cur["company_id"], action="oversight.protocol_activate",
        action_class="A1", target_kind="protocol", target_ref=f"{PR121}@2",
        summary="prompt 12 §13: the digital CEO's predictions",
    )  # fmt: skip
    return True
