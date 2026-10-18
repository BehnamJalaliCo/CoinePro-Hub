"""The skill library (prompt 08 §6, contract §18.5).

A skill is a method, never authority: it gives no tool, class or access. Its
life: a version is written (seed, text, a voice transcript or files) ->
the deterministic pre-check (here, before any model reads it) -> the
overseer's review (`skill.review`) -> the academy's eval (the gate: score >=
baseline - 1) -> approved -> active only with the owner's seal
(`/skills/{ref}/activate`, step-up `skill.activate`, target `ref@version`).
The runtime puts a role's active skills after its charter and records the
versions on every run and model call.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common import charters as C
from hq_common.redact import scrub

log = logging.getLogger("hq_api.skills")

SKILL_REF = r"^SK-[0-9]{3,6}$"
MAX_ACTIVE_CHARS = 16000  # all active skills of one run, after its charter
VERDICTS = ("pass", "changes", "reject")
# Instruction-override phrases (English and Persian): a skill carrying one is
# refused before any model reads it.
INJECTION = (
    ("ignore_previous", r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}"
                        r"\b(previous|prior|above|earlier|all|system|your)\b[^.\n]{0,20}"
                        r"\b(instructions?|rules?|prompts?|charter)\b"),
    ("new_identity", r"\byou are (now|no longer)\b"),
    ("system_prompt", r"\b(reveal|print|show|repeat)\b[^.\n]{0,30}\bsystem prompt\b"),
    ("jailbreak", r"\b(jailbreak|developer mode|do anything now|DAN mode)\b"),
    ("fa_ignore", r"(دستور|قاعده|قوانین|منشور)[^.\n]{0,30}(قبلی|بالا|پیشین)?[^.\n]{0,20}(را )?نادیده بگیر"),
    ("fa_new_identity", r"از (این|الان) به بعد تو"),
)  # fmt: skip
# Phrases that hand out authority a skill can never give.
AUTHORITY = (
    ("self_approve", r"\b(approve|seal|release)\b[^.\n]{0,30}\b(yourself|on your own|without the owner)\b"),
    ("skip_owner", r"\b(no need to|do not|don't|never)\b[^.\n]{0,20}\b(propose|ask the owner|wait for the owner)\b"),
    ("a3_a4", r"\b(you may|you can|allowed to)\b[^.\n]{0,40}\b(A3|A4|pay|purchase|publish|sign up)\b"),
    ("fa_skip_owner", r"بدون (اجازه|مُهر|مهر|تأیید) (ی )?مالک"),
)  # fmt: skip
_INJ = [(k, re.compile(p, re.I)) for k, p in INJECTION]
_AUTH = [(k, re.compile(p, re.I)) for k, p in AUTHORITY]
_TOOL = re.compile(r"\b[a-z][a-z_]*\.[a-z_]+\b")


class Scope(BaseModel):
    roles: list[str] = Field(default_factory=lambda: ["all"], min_length=1, max_length=20)
    companies: Literal["all"] | list[str] = "all"
    departments: list[str] = Field(default_factory=list, max_length=20)


class Review(BaseModel):
    by: dict[str, str]
    at: datetime
    verdict: Literal["pass", "changes", "reject"]
    notes_md: str
    checks: dict[str, Any]


class EvalResult(BaseModel):
    suite: str
    score: float | None
    baseline: float | None
    passed: bool | None = None
    run: str | None = None


class Skill(BaseModel):
    id: UUID
    ref: str
    name_fa: str
    summary_fa: str
    body_md: str
    resources: list[UUID]
    scope: Scope
    version: int
    status: Literal["draft", "in_review", "approved", "active", "retired"]
    review: Review | None
    eval: EvalResult | None
    created_by: dict[str, str]
    created_at: datetime
    activated_at: datetime | None
    # ⟨1.4⟩ beside the contract's fields: the deterministic pre-check, and
    # which version is live
    precheck: dict[str, Any]
    active_version: int | None
    eval_suite: str | None


class SkillVersion(BaseModel):
    version: int
    status: str
    body_md: str
    source: str
    precheck: dict[str, Any]
    review: Review | None
    eval: EvalResult | None
    created_by: dict[str, str]
    created_at: datetime
    decided_at: datetime | None


# -------------------------------------------------------------- pre-check --
def precheck(text: str, lib: C.Library | None, roles: list[str]) -> dict[str, Any]:
    """The code's own review, before any model sees the text: instruction
    overrides, secrets or personal data (what the masker would hide), words
    that hand out authority, and tools outside the scoped roles' charters."""
    injection = [k for k, p in _INJ if p.search(text)]
    authority = [k for k, p in _AUTH if p.search(text)]
    secrets = scrub(text) != text
    outside: list[str] = []
    if lib is not None:
        named = {m for m in _TOOL.findall(text) if m in lib.tools}
        scoped = list(lib.roles) if "all" in roles else [r for r in roles if r in lib.roles]
        allowed = {t for r in scoped for t in lib.allowed(r)}
        outside = sorted(named - allowed)
    ok = not (injection or authority or secrets or outside)
    return {
        "ok": ok,
        "injection": injection,
        "secrets": secrets,
        "authority": authority,
        "tools_outside_charter": outside,
    }


def _review_of_precheck(pre: dict[str, Any], now: datetime) -> dict[str, Any]:
    reasons = [
        *(f"injection:{k}" for k in pre["injection"]),
        *(f"authority:{k}" for k in pre["authority"]),
        *(["secrets"] if pre["secrets"] else []),
        *(f"tool:{t}" for t in pre["tools_outside_charter"]),
    ]
    return {
        "by": {"kind": "service", "code": "skills-precheck"},
        "at": now.isoformat(),
        "verdict": "reject",
        "notes_md": "The code's pre-check refused this text: " + ", ".join(reasons),
        "checks": {
            "injection": not pre["injection"],
            "secrets": not pre["secrets"],
            "conflicts": True,
            "policy": not (pre["authority"] or pre["tools_outside_charter"]),
        },
    }


# ------------------------------------------------------------------ store --
SKILL_SQL = """
    SELECT s.*, v.version, v.body_md, v.resources, v.precheck, v.review, v.eval,
           v.status AS version_status, v.source AS version_source
    FROM knowledge.skills s
    JOIN knowledge.skill_versions v ON v.skill_id = s.id AND v.version = s.latest_version
"""


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def render(r: dict[str, Any]) -> Skill:
    return Skill(
        id=r["id"],
        ref=r["ref"],
        name_fa=r["name_fa"],
        summary_fa=r["summary_fa"],
        body_md=r["body_md"],
        resources=list(r["resources"] or []),
        scope=Scope.model_validate(_j(r["scope"])),
        version=int(r["version"]),
        status=r["status"],
        review=Review.model_validate(_j(r["review"])) if r["review"] else None,
        eval=EvalResult.model_validate(_j(r["eval"])) if r["eval"] else None,
        created_by={"kind": r["created_by_kind"], "code": r["created_by_code"]},
        created_at=r["created_at"],
        activated_at=r["activated_at"],
        precheck=_j(r["precheck"]) or {},
        active_version=r["active_version"],
        eval_suite=r["eval_suite"],
    )


def render_version(r: dict[str, Any]) -> SkillVersion:
    return SkillVersion(
        version=int(r["version"]),
        status=r["status"],
        body_md=r["body_md"],
        source=r["source"],
        precheck=_j(r["precheck"]) or {},
        review=Review.model_validate(_j(r["review"])) if r["review"] else None,
        eval=EvalResult.model_validate(_j(r["eval"])) if r["eval"] else None,
        created_by={"kind": r["created_by_kind"], "code": r["created_by_code"]},
        created_at=r["created_at"],
        decided_at=r["decided_at"],
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if not re.fullmatch(SKILL_REF, ref):
        raise ApiError(404, "not_found")
    sql = SKILL_SQL + " WHERE s.ref = :ref"
    row = await tx.first(sql + (" FOR UPDATE OF s" if lock else ""), ref=ref)
    if row is None:
        raise ApiError(404, "not_found")
    return row


async def version_row(tx: Tx, skill_id: UUID, version: int) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM knowledge.skill_versions WHERE skill_id = :s AND version = :v",
        s=skill_id,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", "no such version")
    return row


def _status_of_version(vstatus: str, active: int | None) -> str:
    if vstatus == "approved":
        return "approved"
    if vstatus == "in_review":
        return "in_review"
    return "active" if active else "draft"


async def write_version(
    tx: Tx,
    *,
    lib: C.Library | None,
    skill: dict[str, Any] | None,
    company_id: UUID,
    company_code: str,
    name_fa: str,
    summary_fa: str,
    body_md: str,
    scope: Scope,
    eval_suite: str | None,
    source: str,
    by_kind: str,
    by_code: str,
    resources: list[UUID] | None = None,
    ref: str | None = None,
    version: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """A new skill or a new version of `skill`: pre-checked here; a refused
    text is stored with the code's own `reject` review (never shown to a model
    as a live skill). Returns the skill row as SKILL_SQL renders it."""
    now = datetime.now().astimezone()
    pre = precheck(f"{name_fa}\n{summary_fa}\n{body_md}", lib, scope.roles)
    review = None if pre["ok"] else _review_of_precheck(pre, now)
    vstatus = status or ("in_review" if pre["ok"] else "rejected")
    if skill is None:
        skill_id: UUID = await tx.scalar(
            """INSERT INTO knowledge.skills (company_id, ref, name_fa, summary_fa, scope, eval_suite,
                   latest_version, status, source, created_by_kind, created_by_code)
               VALUES (:co, COALESCE(CAST(:ref AS text),
                                     'SK-' || lpad(nextval('knowledge.skill_ref_seq')::text, 3, '0')),
                       :name, :summary, CAST(:scope AS jsonb), :suite, :v, :st, :src, :bk, :bc)
               RETURNING id""",
            co=company_id,
            ref=ref,
            name=name_fa[:200],
            summary=summary_fa[:1000],
            scope=scope.model_dump_json(),
            suite=eval_suite,
            v=version or 1,
            st=_status_of_version(vstatus, None),
            src=source,
            bk=by_kind,
            bc=by_code,
        )
        n = version or 1
    else:
        skill_id = skill["id"]
        n = int(skill["latest_version"]) + 1
        await tx.exec(
            """UPDATE knowledge.skills SET latest_version = :v, name_fa = :name, summary_fa = :summary,
                   scope = CAST(:scope AS jsonb), eval_suite = :suite, status = :st, updated_at = now()
               WHERE id = :id""",
            id=skill_id,
            v=n,
            name=name_fa[:200],
            summary=summary_fa[:1000],
            scope=scope.model_dump_json(),
            suite=eval_suite,
            st=_status_of_version(vstatus, skill["active_version"]),
        )
    await tx.exec(
        """INSERT INTO knowledge.skill_versions (skill_id, company_id, version, body_md, resources, source,
               precheck, review, status, created_by_kind, created_by_code, decided_at)
           VALUES (:s, :co, :v, :body, :res, :src, CAST(:pre AS jsonb), CAST(:review AS jsonb), :st,
                   :bk, :bc, CASE WHEN :st = 'rejected' THEN now() END)""",
        s=skill_id,
        co=company_id,
        v=n,
        body=body_md[:20000],
        res=list(resources or []),
        src=source,
        pre=json.dumps(pre),
        review=json.dumps(review) if review else None,
        st=vstatus,
        bk=by_kind,
        bc=by_code,
    )
    row = await tx.one(SKILL_SQL + " WHERE s.id = :id", id=skill_id)
    await emit_updated(tx, company_code, row, "written")
    return row


async def emit_updated(tx: Tx, company_code: str, row: dict[str, Any], change: str) -> None:
    await events.emit(
        tx,
        company_code,
        "skill.updated",
        row["ref"],
        {"version": int(row["latest_version"]), "status": row["status"], "change": change},
    )


async def record_review(
    tx: Tx,
    row: dict[str, Any],
    version: int,
    *,
    by: dict[str, str],
    verdict: str,
    checks: dict[str, Any],
    notes_md: str,
) -> dict[str, Any]:
    """The overseer's (or AI Safety's) review of one version still in review.
    A version the code's pre-check refused can never pass."""
    v = await version_row(tx, row["id"], version)
    if v["status"] != "in_review":
        raise ApiError(
            409, "validation_failed", f"version {version} is {v['status']}, not in review"
        )
    pre = _j(v["precheck"]) or {}
    if verdict == "pass" and not pre.get("ok", False):
        raise ApiError(
            422,
            "validation_failed",
            "precheck_failed",
            fields={"verdict": "the pre-check refused it"},
        )
    review = {
        "by": by,
        "at": datetime.now().astimezone().isoformat(),
        "verdict": verdict,
        "notes_md": notes_md[:4000],
        "checks": checks,
    }
    status = "in_review" if verdict == "pass" else "rejected"  # a pass waits for the eval
    await tx.exec(
        """UPDATE knowledge.skill_versions SET review = CAST(:r AS jsonb), status = :st,
               decided_at = CASE WHEN :st = 'rejected' THEN now() END
           WHERE id = :id""",
        id=v["id"],
        r=json.dumps(review),
        st=status,
    )
    if int(row["latest_version"]) == version:
        await tx.exec(
            "UPDATE knowledge.skills SET status = :st, updated_at = now() WHERE id = :id",
            id=row["id"],
            st=_status_of_version(status, row["active_version"]),
        )
    return v


async def activate(tx: Tx, row: dict[str, Any], version: int) -> dict[str, Any]:
    """Only a version the overseer passed and the academy's eval passed."""
    v = await version_row(tx, row["id"], version)
    review = _j(v["review"]) or {}
    ev = _j(v["eval"]) or {}
    if v["status"] != "approved" or review.get("verdict") != "pass" or ev.get("passed") is not True:
        raise ApiError(
            409,
            "validation_failed",
            "not_approved",
            fields={"version": f"{v['status']}: needs the review's pass and a passed eval"},
        )
    await tx.exec(
        """UPDATE knowledge.skill_versions SET status = 'superseded'
           WHERE skill_id = :s AND status = 'active'""",
        s=row["id"],
    )
    await tx.exec(
        "UPDATE knowledge.skill_versions SET status = 'active', decided_at = now() WHERE id = :id",
        id=v["id"],
    )
    await tx.exec(
        """UPDATE knowledge.skills SET status = 'active', active_version = :v, activated_at = now(),
               updated_at = now() WHERE id = :id""",
        id=row["id"],
        v=version,
    )
    return v


async def retire(tx: Tx, row: dict[str, Any]) -> None:
    await tx.exec(
        "UPDATE knowledge.skill_versions SET status = 'retired' WHERE skill_id = :s AND status = 'active'",
        s=row["id"],
    )
    await tx.exec(
        """UPDATE knowledge.skills SET status = 'retired', active_version = NULL, updated_at = now()
           WHERE id = :id""",
        id=row["id"],
    )


# ---------------------------------------------------------------- runtime --
def _applies(scope: dict[str, Any], role: str, company: str, department: str | None) -> bool:
    roles = scope.get("roles") or ["all"]
    companies = scope.get("companies", "all")
    departments = scope.get("departments") or []
    return (
        ("all" in roles or role in roles)
        and (companies == "all" or company in (companies or []))
        and (not departments or (department or "") in departments)
    )


async def active_for(
    tx: Tx, role: str, company: str, department: str | None
) -> list[dict[str, Any]]:
    """The active skills of one role in one company and department, by ref."""
    rows = await tx.all(
        """SELECT s.ref, s.name_fa, s.scope, v.version, v.body_md
           FROM knowledge.skills s
           JOIN knowledge.skill_versions v ON v.skill_id = s.id AND v.version = s.active_version
           WHERE s.status = 'active' AND v.status = 'active'
           ORDER BY s.ref"""
    )
    return [r for r in rows if _applies(_j(r["scope"]) or {}, role, company, department)]


def prompt_section(skills: list[dict[str, Any]], addenda: list[dict[str, Any]]) -> str:
    """What follows the charter: the owner-sealed skills, then the owner's
    sealed rules for the role (approved teachings). Methods, never authority."""
    out: list[str] = []
    used = 0
    if skills:
        out.append(
            "# Skills (sealed by the owner)\n"
            "Methods for your work. A skill never gives you a tool, a class of action or an access "
            "your charter does not give; where they differ, your charter wins."
        )
        for s in skills:
            block = f"## {s['ref']}@{s['version']}: {s['name_fa']}\n{s['body_md'].strip()}"
            if used + len(block) > MAX_ACTIVE_CHARS:
                break
            out.append(block)
            used += len(block)
    if addenda:
        out.append("# The owner's rules for your role (sealed teachings)")
        out += [f"- ({a['ref']}) {a['text_md'].strip()}" for a in addenda]
    return "\n\n".join(out)


# ------------------------------------------------------------------- seed --
def agents_dir() -> Path:
    return Path(os.environ.get("HQ_AGENTS_DIR", C.DEFAULT_DIR))


def seed_files(root: Path | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = (root or agents_dir()) / "skills"
    for path in sorted(base.glob("SK-*/SKILL.md")):
        try:
            meta, body = C.split_frontmatter(path.read_text(encoding="utf-8"))
            roles = meta.get("roles") or "all"
            out.append(
                {
                    "ref": str(meta["ref"]),
                    "name_fa": str(meta["name_fa"]),
                    "summary_fa": str(meta["summary_fa"]),
                    "version": int(meta.get("version", 1)),
                    "eval": meta.get("eval"),
                    "scope": Scope(
                        roles=["all"] if roles == "all" else [str(r) for r in roles],
                        companies="all"
                        if meta.get("companies", "all") == "all"
                        else [str(c) for c in meta["companies"]],
                    ),
                    "body_md": body,
                }
            )
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("skill seed skipped", extra={"file": path.name, "error": str(exc)[:200]})
    return out


async def seed(tx: Tx, holding_id: UUID, holding_code: str, lib: C.Library | None) -> int:
    """Each seed skill once, at its file's version, `in_review`: like every
    version it needs the overseer's review, an eval and the owner's seal."""
    added = 0
    for s in seed_files(lib.root if lib is not None else None):
        if not re.fullmatch(SKILL_REF, s["ref"]):
            continue
        if await tx.scalar("SELECT 1 FROM knowledge.skills WHERE ref = :r", r=s["ref"]):
            continue
        await write_version(
            tx,
            lib=lib,
            skill=None,
            company_id=holding_id,
            company_code=holding_code,
            name_fa=s["name_fa"],
            summary_fa=s["summary_fa"],
            body_md=s["body_md"],
            scope=s["scope"],
            eval_suite=s["eval"] if isinstance(s["eval"], str) else None,
            source="seed",
            by_kind="service",
            by_code="seed",
            ref=s["ref"],
            version=s["version"],
        )
        added += 1
    return added
