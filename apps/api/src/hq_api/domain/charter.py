"""The charter and its addenda (prompt 11 §2, contract §20.2).

One holding charter and at most one addendum per company, versioned in
governance.charters. Only the owner seals (🔏 `charter.seal`, target =
`body_sha256`), and a version never changes after it is written:

    body_sha256 = sha256 of the canonical JSON {body_md, red_lines}
                  (sorted keys, no spaces, UTF-8): the seal binds the red
                  lines as well as the text, so a version with the same text
                  and weaker red lines is never sealed with another's token.

Agents read, never write: the runtime puts the sealed holding charter and the
company's sealed addendum between `_common` and the role charter (the cached
prefix of the system prompt) and records `charter_docs` on every model call.
Until a holding version is sealed only the four red lines of OPERATING_MODEL
§1.15 apply: their text (and the reviewed patterns of the first one) come
from agents/charter/HOLDING.md as it is in the repository, never from a
proposed version in the database, so an unsealed edit never takes effect.

Red lines with `check: rule` are matched by code (hq_common.outbound_guard's
normalisation) on deliverables, messages to the owner and stories (a finding
of PR-115), and they go into the support outbound guard (refusal `red_line`,
no override: §19.6). Lines with `check: sample` are the overseer's (PR-115).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field, field_validator

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Model, actor
from hq_common import outbound_guard as G

log = logging.getLogger("hq_api.charter")
HOLDING = "holding"
HOLDING_MAX = 6000
ADDENDUM_MAX = 3000
SEED_FILE = Path("charter") / "HOLDING.md"
SCOPE_RE = r"^(holding|[A-Z][A-Z0-9]{1,9})$"


# ------------------------------------------------------------------ models --
class RedLine(Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    text_fa: str = Field(min_length=1, max_length=500)
    check: Literal["rule", "sample"]
    patterns: list[str] | None = Field(default=None, max_length=20)

    @field_validator("patterns")
    @classmethod
    def _compiles(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for p in v:
            if not p.strip() or len(p) > 300:
                raise ValueError("a pattern is 1..300 characters")
            try:
                re.compile(p)
            except (re.error, OverflowError, RecursionError) as exc:
                raise ValueError(f"not a regular expression: {exc}") from exc
        return v


class CharterIn(Model):
    body_md: str = Field(min_length=1, max_length=HOLDING_MAX)
    red_lines: list[RedLine] = Field(default_factory=list, max_length=20)


class CharterVersion(BaseModel):
    scope: str
    version: int
    status: str
    body_md: str
    red_lines: list[dict[str, Any]]
    body_sha256: str
    created_by: Actor
    created_at: Any
    sealed_by: Actor | None
    sealed_at: Any


class VersionBrief(BaseModel):
    version: int
    status: str
    created_by: Actor
    created_at: Any
    sealed_at: Any


class CharterScope(BaseModel):
    scope: str
    sealed: CharterVersion | None
    proposed: CharterVersion | None
    versions: list[VersionBrief]


class CharterDiff(BaseModel):
    scope: str
    version: int
    against: int
    diff: str


# ------------------------------------------------------------------- hashes --
def red_lines_json(red_lines: list[Any]) -> list[dict[str, Any]]:
    """Red lines as stored and hashed: every key present (patterns null when none)."""
    out = []
    for r in red_lines:
        d = r.model_dump() if isinstance(r, BaseModel) else dict(r)
        out.append(
            {
                "key": d["key"],
                "text_fa": d["text_fa"],
                "check": d["check"],
                "patterns": list(d["patterns"]) if d.get("patterns") else None,
            }
        )
    return out


def canonical(body_md: str, red_lines: list[Any]) -> str:
    return json.dumps(
        {"body_md": body_md, "red_lines": red_lines_json(red_lines)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def body_sha256(body_md: str, red_lines: list[Any]) -> str:
    return hashlib.sha256(canonical(body_md, red_lines).encode("utf-8")).hexdigest()


def check_length(scope: str, body_md: str) -> None:
    limit = HOLDING_MAX if scope == HOLDING else ADDENDUM_MAX
    if len(body_md) > limit:
        raise ApiError(
            422,
            "validation_failed",
            fields={
                "body_md": f"at most {limit} characters for {'the holding' if scope == HOLDING else 'an addendum'}"
            },
        )


# ------------------------------------------------------------- the seed file --
@lru_cache(maxsize=4)
def seed_document(root: str) -> dict[str, Any]:
    """agents/charter/HOLDING.md: its body and red lines (data, read-only)."""
    path = Path(root) / SEED_FILE
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path}: no frontmatter")
    _, meta_raw, body = text.split("---", 2)
    meta = yaml.safe_load(meta_raw) or {}
    lines = [RedLine.model_validate(r) for r in meta.get("red_lines") or []]
    return {"body_md": body.strip(), "red_lines": red_lines_json(lines)}


def default_red_lines(root: str) -> list[dict[str, Any]]:
    """The four red lines of OPERATING_MODEL §1.15 (the seed file's), in force
    until the owner seals a holding version."""
    try:
        return list(seed_document(root)["red_lines"])
    except (OSError, ValueError, yaml.YAMLError):
        return []


async def seed(tx: Tx, holding_id: UUID, root: str) -> bool:
    """Version 1 of the holding charter, `proposed`, from the seed file (once):
    the owner edits and seals it in the app; the server never seals it."""
    if await tx.scalar("SELECT 1 FROM governance.charters WHERE scope = 'holding' LIMIT 1"):
        return False
    try:
        doc = seed_document(root)
    except (OSError, ValueError, yaml.YAMLError):
        return False
    check_length(HOLDING, doc["body_md"])
    await tx.exec(
        """INSERT INTO governance.charters (company_id, scope, version, status, body_md, red_lines,
               body_sha256, source, created_by_kind, created_by_code)
           VALUES (:co, 'holding', 1, 'proposed', :body, CAST(:rl AS jsonb), :sha, 'seed', 'service', 'seed')""",
        co=holding_id,
        body=doc["body_md"],
        rl=json.dumps(doc["red_lines"], ensure_ascii=False),
        sha=body_sha256(doc["body_md"], doc["red_lines"]),
    )
    return True


# ------------------------------------------------------------------ reading --
SQL = "SELECT * FROM governance.charters"


def render(r: dict[str, Any]) -> CharterVersion:
    created = actor(r["created_by_kind"], r["created_by_code"])
    assert created is not None
    return CharterVersion(
        scope=r["scope"],
        version=r["version"],
        status=r["status"],
        body_md=r["body_md"],
        red_lines=list(r["red_lines"] or []),
        body_sha256=r["body_sha256"],
        created_by=created,
        created_at=r["created_at"],
        sealed_by=actor(r["sealed_by_kind"], r["sealed_by_code"]),
        sealed_at=r["sealed_at"],
    )


def brief(r: dict[str, Any]) -> VersionBrief:
    created = actor(r["created_by_kind"], r["created_by_code"])
    assert created is not None
    return VersionBrief(
        version=r["version"],
        status=r["status"],
        created_by=created,
        created_at=r["created_at"],
        sealed_at=r["sealed_at"],
    )


async def versions(tx: Tx, scope: str) -> list[dict[str, Any]]:
    return await tx.all(SQL + " WHERE scope = :s ORDER BY version DESC", s=scope)


async def load(tx: Tx, scope: str, version: int, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        SQL + " WHERE scope = :s AND version = :v" + (" FOR UPDATE" if lock else ""),
        s=scope,
        v=version,
    )


async def sealed(tx: Tx, scope: str) -> dict[str, Any] | None:
    return await tx.first(SQL + " WHERE scope = :s AND status = 'sealed'", s=scope)


def summary(scope: str, rows: list[dict[str, Any]]) -> CharterScope:
    s = next((r for r in rows if r["status"] == "sealed"), None)
    p = next((r for r in rows if r["status"] == "proposed"), None)  # rows: newest first
    return CharterScope(
        scope=scope,
        sealed=render(s) if s else None,
        proposed=render(p) if p else None,
        versions=[brief(r) for r in rows],
    )


def _diff_text(r: dict[str, Any]) -> list[str]:
    lines: list[str] = str(r["body_md"]).splitlines()
    lines += ["", "## خطوط قرمز"]
    for x in r["red_lines"] or []:
        n = len(x.get("patterns") or [])
        lines.append(f"- [{x['check']}] {x['key']}: {x['text_fa']}" + (f" ({n} الگو)" if n else ""))
    return lines


def diff(scope: str, a: dict[str, Any], b: dict[str, Any]) -> CharterDiff:
    """Unified, line by line, on the server: `against` -> `version` (the body
    and the red lines)."""
    out = difflib.unified_diff(
        _diff_text(b),
        _diff_text(a),
        fromfile=f"{scope}@{b['version']}",
        tofile=f"{scope}@{a['version']}",
        lineterm="",
    )
    return CharterDiff(scope=scope, version=a["version"], against=b["version"], diff="\n".join(out))


# ------------------------------------------------------------------ writing --
async def propose_version(
    tx: Tx,
    who: Principal,
    *,
    scope: str,
    company_id: UUID,
    body_md: str,
    red_lines: list[Any],
    source: Literal["owner", "decision"] = "owner",
    decision_ref: str | None = None,
) -> dict[str, Any]:
    """A new `proposed` version (the owner's PUT); nothing in force changes."""
    check_length(scope, body_md)
    lines = red_lines_json(red_lines)
    nxt = int(
        await tx.scalar(
            "SELECT COALESCE(max(version), 0) + 1 FROM governance.charters WHERE scope = :s",
            s=scope,
        )
    )
    await tx.exec(
        """INSERT INTO governance.charters (company_id, scope, version, status, body_md, red_lines,
               body_sha256, source, decision_ref, created_by_kind, created_by_code)
           VALUES (:co, :s, :v, 'proposed', :body, CAST(:rl AS jsonb), :sha, :src, :dec, :bk, :bc)""",
        co=company_id,
        s=scope,
        v=nxt,
        body=body_md,
        rl=json.dumps(lines, ensure_ascii=False),
        sha=body_sha256(body_md, lines),
        src=source,
        dec=decision_ref,
        bk=who.kind,
        bc=who.code,
    )
    return await load(tx, scope, nxt)


async def seal(
    tx: Tx,
    who: Principal,
    row: dict[str, Any],
    *,
    company_code: str,
    step_up_id: UUID | None,
) -> dict[str, Any]:
    """The owner's seal on a proposed version: the earlier sealed version is
    superseded in the same transaction (one sealed version per scope)."""
    if not who.is_owner:
        raise ApiError(403, "forbidden", "only the owner seals the charter")
    if row["status"] != "proposed":
        raise ApiError(
            409, "validation_failed", f"{row['scope']}@{row['version']} is {row['status']}"
        )
    if body_sha256(row["body_md"], list(row["red_lines"] or [])) != row["body_sha256"]:
        raise ApiError(409, "seal_mismatch", "the stored hash does not match the version")
    await tx.exec(
        """UPDATE governance.charters SET status = 'superseded', superseded_at = now()
           WHERE scope = :s AND status = 'sealed'""",
        s=row["scope"],
    )
    await tx.exec(
        """UPDATE governance.charters SET status = 'sealed', sealed_at = now(), sealed_by_kind = 'owner',
               sealed_by_code = :c, seal_step_up_id = :su
           WHERE id = :id""",
        c=who.code,
        su=step_up_id,
        id=row["id"],
    )
    await events.emit(
        tx,
        company_code,
        "charter.sealed",
        f"{row['scope']}@{row['version']}",
        {"scope": row["scope"], "version": row["version"], "body_sha256": row["body_sha256"]},
    )
    return await load(tx, row["scope"], row["version"])


# ----------------------------------------------- the decision card (§20.2) --
class CharterAmendmentPayload(Model):
    """An agent's amendment: {scope, base_version, body_md, red_lines, diff_md,
    body_sha256}; base_version 0 = nothing sealed yet."""

    scope: str = Field(pattern=SCOPE_RE)
    base_version: int = Field(ge=0)
    body_md: str = Field(min_length=1, max_length=HOLDING_MAX)
    red_lines: list[RedLine] = Field(default_factory=list, max_length=20)
    diff_md: str = Field(default="", max_length=20000)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


async def current_version(tx: Tx, scope: str) -> int:
    row = await sealed(tx, scope)
    return int(row["version"]) if row else 0


async def check_amendment(
    tx: Tx, who: Principal, payload: dict[str, Any], company_code: str, holding_code: str
) -> None:
    """At propose time: a CEO amends its own company's addendum, the overseer
    and the advisor the holding's (OPA decides who may propose the kind at
    all); the hash is the canonical one; the length fits the scope."""
    scope = payload["scope"]
    if who.is_agent:
        if scope == HOLDING and who.charter not in ("overseer", "advisor"):
            raise ApiError(
                403,
                "policy_denied",
                "the holding charter is amended by the overseer or the advisor",
            )
        if scope != HOLDING and (who.role != "ceo" or scope != company_code):
            raise ApiError(403, "policy_denied", "a CEO amends its own company's addendum only")
    check_length(scope, payload["body_md"])
    if body_sha256(payload["body_md"], payload.get("red_lines") or []) != payload["body_sha256"]:
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.body_sha256": "not the canonical sha256 of {body_md, red_lines}"},
        )
    if scope == HOLDING and company_code != holding_code:
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.scope": "the holding's card lives in the holding"},
        )


async def apply_amendment(
    tx: Tx, who: Principal, d: dict[str, Any], step_up_id: UUID | None
) -> dict[str, Any]:
    """The owner sealed the card: the amendment becomes the sealed version.
    Superseded (409, nothing changes) when its base is no longer current."""
    p = d["payload"]
    scope = p["scope"]
    if await current_version(tx, scope) != int(p["base_version"]):
        raise ApiError(
            409,
            "decision_not_pending",
            f"{d['ref']}: {scope}@{p['base_version']} is no longer the current version",
        )
    row = await propose_version(
        tx,
        Principal(kind="agent", code=d["proposer_code"], role="agent"),
        scope=scope,
        company_id=d["company_id"],
        body_md=p["body_md"],
        red_lines=p.get("red_lines") or [],
        source="decision",
        decision_ref=d["ref"],
    )
    return await seal(tx, who, row, company_code=d["company"], step_up_id=step_up_id)


# ------------------------------------------------------- what agents read --
FALLBACK_TITLE = "# خطوط قرمز هلدینگ (مدل عملیاتی §۱.۱۵؛ اساسنامه هنوز مُهر نشده)"


async def prompt_section(tx: Tx, company_code: str, root: str) -> tuple[str, list[str]]:
    """The sealed holding charter and the company's sealed addendum, as they
    go into the system prompt, and their refs (`["holding@3", "TY@1"]`)."""
    parts: list[str] = []
    refs: list[str] = []
    h = await sealed(tx, HOLDING)
    if h is not None:
        parts.append(f"# اساسنامه‌ی هلدینگ (نسخه‌ی {h['version']}، مُهر مالک)\n{h['body_md']}")
        refs.append(f"holding@{h['version']}")
    else:
        lines = "\n".join(f"{i}. {r['text_fa']}" for i, r in enumerate(default_red_lines(root), 1))
        parts.append(f"{FALLBACK_TITLE}\n{lines}")
    if company_code:
        a = await sealed(tx, company_code)
        if a is not None:
            parts.append(
                f"# الحاقیه‌ی {company_code} (نسخه‌ی {a['version']}، مُهر مالک)\n{a['body_md']}"
            )
            refs.append(f"{company_code}@{a['version']}")
    return "\n\n".join(parts), refs


async def red_lines_in_force(tx: Tx, company_code: str | None, root: str) -> list[dict[str, Any]]:
    """The holding's sealed red lines (or the four of §1.15 until one is
    sealed) and the company's sealed addendum's."""
    h = await sealed(tx, HOLDING)
    lines = list(h["red_lines"] or []) if h is not None else default_red_lines(root)
    if company_code:
        a = await sealed(tx, company_code)
        if a is not None:
            lines += list(a["red_lines"] or [])
    return lines


def rule_patterns(lines: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(p for r in lines if r.get("check") == "rule" for p in r.get("patterns") or [] if p)


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except (re.error, OverflowError, RecursionError):
        return re.compile(re.escape(pattern), re.IGNORECASE)


def matches(text: str, lines: list[dict[str, Any]]) -> list[str]:
    """The keys of the `rule` red lines the text breaks (normalised like the
    outbound guard: Persian letters and digits, invisible marks, encodings)."""
    if not text:
        return []
    views = [text, G.normalise(text)]
    hit = []
    for r in lines:
        if r.get("check") != "rule":
            continue
        for p in r.get("patterns") or []:
            rx = _compile(p)
            if any(rx.search(v) or rx.search(v.casefold()) for v in views):
                hit.append(str(r["key"]))
                break
    return hit


async def scan_internal(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    kind: Literal["deliverable", "message", "story"],
    ref: str,
    text: str,
    root: str,
) -> list[str]:
    """A deliverable, a message to the owner or a story that breaks a `rule`
    red line becomes a finding of PR-115 (when it is in force; one open
    finding per item). Internal text is never held: only text to customers is."""
    lines = await red_lines_in_force(tx, company_code, root)
    hit = matches(text, lines)
    if not hit:
        return []
    from hq_api.domain import oversight as O

    protocol = await O.protocol_in_force(tx, "PR-115")
    if protocol is None:
        return hit
    await O.raise_finding(
        tx,
        company_id=company_id,
        company_code=company_code,
        severity="high",
        title_fa=f"خط قرمز اساسنامه در {ref}: {', '.join(hit)}"[:300],
        body_md=f"The {kind} {ref} matches the rule red line(s) {', '.join(hit)} of the charter in force.",
        evidence=[{"kind": kind, "ref": ref}, *({"kind": "red_line", "ref": k} for k in hit)],
        protocol=protocol,
        dedupe_key=f"red_line:{kind}:{ref}",
    )
    return hit


async def scan_after(
    hub: Any,
    *,
    company_id: UUID,
    company_code: str,
    kind: Literal["deliverable", "message", "story"],
    ref: str,
    text: str,
) -> list[str]:
    """`scan_internal` once the item is stored, over every company (PR-115 and
    its findings are the holding's); a failure here never undoes the item."""
    root = str(hub.charters.root) if hub.charters is not None else "/app/agents"
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await scan_internal(
                tx,
                company_id=company_id,
                company_code=company_code,
                kind=kind,
                ref=ref,
                text=text,
                root=root,
            )
    except Exception:
        log.exception("red-line scan failed", extra={"ref": ref})
        return []
