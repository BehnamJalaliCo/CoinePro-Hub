"""The authority matrix (prompt 11 §7, contract §20.7): the numbers and the
"who approves" tables that were in rego or in code, as data.

    rows        governance.authority, seeded from apps/api/seed/authority.yaml
                (the seed rewrites the locked rows and every row's bounds, class
                and default actor; the owner's actor and limit of an unlocked
                row survive)
    owner       PUT /authority (🔏 authority.update on the body's SHA-256):
                unlocked rows only, inside `bounds` (422 otherwise), `actor`
                only back to the owner or to the seeded actor
    agents      propose `authority_change` (🔏 on approval); read their rows
                with authority.read
    OPA         the rows go to data.hq.authority (push(): at the first use in
                a process, after every change, and whenever OPA's copy has
                another digest); hq.limits clamps every number into the files'
                bounds, so the database and OPA must both allow a count

`limit_value()` is what code that enforces a number reads (hire.per_day,
notify.urgent_per_hour, story.per_day, batch.max_usd, batch.max_items);
`within()` asks the database row and OPA together.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.authority")

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "authority.yaml"
WEEKDAYS = ("sat", "sun", "mon", "tue", "wed", "thu", "fri")
NUMBER_KEYS = ("tokens_month", "usd", "count_day", "count_hour", "items")
LIST_KEYS = ("days", "kinds")
ATTENTION = "ceo.attention_per_day"  # its number is owner.settings.ceo_daily_attention
TTL_S = 60.0
_SYNC: dict[str, Any] = {"at": 0.0, "digest": None}


class AuthorityRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    title_fa: str
    action: str
    actor: str
    scope: str
    limit: dict[str, Any] | None
    bounds: dict[str, Any] | None
    step_up: bool
    class_: str = Field(alias="class")
    locked: bool
    note_fa: str
    version: int


class AuthorityMatrix(BaseModel):
    rules: list[AuthorityRule]
    digest: str


class AuthorityRuleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_.]{1,60}$")
    actor: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    limit: dict[str, Any] | None = None
    version: int = Field(ge=1)


class AuthorityMatrixIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[AuthorityRuleChange] = Field(min_length=1, max_length=50)


# ------------------------------------------------------------------- seed --
def load_seed(path: Path = SEED_FILE) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows: list[dict[str, Any]] = []
    for i, r in enumerate(data.get("rules") or []):
        lim = r.get("limit")
        bounds = r.get("bounds")
        if lim and "days" in lim:
            bounds = {"allowed": list(r.get("allowed_days") or WEEKDAYS)}
        elif lim and "kinds" in lim and not r.get("locked"):
            bounds = {"allowed": list(lim["kinds"])}  # only ever shorter
        rows.append(
            {
                "key": str(r["key"]),
                "title_fa": str(r["title_fa"]),
                "action": str(r["action"]),
                "actor": str(r["actor"]),
                "scope": str(r["scope"]),
                "lim": lim,
                "bounds": bounds,
                "step_up": bool(r.get("step_up", False)),
                "class": str(r["class"]),
                "locked": bool(r.get("locked", False)),
                "note_fa": " ".join(str(r.get("note_fa") or "").split()),
                "sort": i,
            }
        )
    return rows


async def seed(tx: Tx) -> int:
    """Rows of the seed file (as the owner role hq): a missing row is added;
    an existing one keeps the owner's actor and limit unless it is locked."""
    changed = 0
    for r in load_seed():
        params = {**r, "lim": _j(r["lim"]), "bounds": _j(r["bounds"])}
        exists = await tx.scalar(
            "SELECT 1 FROM governance.authority WHERE key = :key", key=r["key"]
        )
        if not exists:
            await tx.exec(
                """INSERT INTO governance.authority (key, title_fa, action, actor, default_actor, scope,
                       lim, bounds, step_up, class, locked, note_fa, sort)
                   VALUES (:key, :title_fa, :action, :actor, :actor, :scope, CAST(:lim AS jsonb),
                           CAST(:bounds AS jsonb), :step_up, :class, :locked, :note_fa, :sort)""",
                **params,
            )
            changed += 1
            continue
        changed += await tx.exec(
            """UPDATE governance.authority SET title_fa = :title_fa, action = :action,
                   default_actor = :actor, scope = :scope, bounds = CAST(:bounds AS jsonb),
                   step_up = :step_up, class = :class, locked = :locked, note_fa = :note_fa, sort = :sort,
                   actor = CASE WHEN :locked THEN :actor ELSE actor END,
                   lim = CASE WHEN :locked THEN CAST(:lim AS jsonb) ELSE lim END
               WHERE key = :key
                 AND ((title_fa, action, default_actor, scope, bounds::text, step_up, class, locked, note_fa,
                       sort)
                      IS DISTINCT FROM (:title_fa, :action, :actor, :scope, CAST(:bounds AS jsonb)::text,
                                        :step_up, :class, :locked, :note_fa, :sort)
                      OR (:locked AND (actor, lim::text) IS DISTINCT FROM (:actor, CAST(:lim AS jsonb)::text)))""",
            **params,
        )
    return changed


def _j(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


# ------------------------------------------------------------------- read --
async def rows(tx: Tx) -> list[dict[str, Any]]:
    out = [dict(r) for r in await tx.all("SELECT * FROM governance.authority ORDER BY sort, key")]
    attention = await tx.scalar("SELECT ceo_daily_attention FROM owner.settings WHERE id = 1")
    for r in out:
        if r["key"] == ATTENTION and attention is not None:
            r["lim"] = {"count_day": int(attention)}
    return out


def render(r: dict[str, Any]) -> AuthorityRule:
    return AuthorityRule(
        key=r["key"],
        title_fa=r["title_fa"],
        action=r["action"],
        actor=r["actor"],
        scope=r["scope"],
        limit=r["lim"],
        bounds=r["bounds"],
        step_up=r["step_up"],
        class_=r["class"],
        locked=r["locked"],
        note_fa=r["note_fa"],
        version=r["version"],
    )


def opa_doc(rs: list[dict[str, Any]]) -> dict[str, Any]:
    """data.hq.authority: the rows OPA needs, and their digest."""
    rules = {
        r["key"]: {
            "actor": r["actor"],
            "limit": r["lim"],
            "locked": r["locked"],
            "class": r["class"],
        }
        for r in rs
    }
    canon = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"version": hashlib.sha256(canon.encode()).hexdigest(), "rules": rules}


async def matrix(tx: Tx) -> AuthorityMatrix:
    rs = await rows(tx)
    return AuthorityMatrix(rules=[render(r) for r in rs], digest=opa_doc(rs)["version"])


async def for_agent(tx: Tx, who: Principal) -> list[AuthorityRule]:
    """authority.read: the rows that apply to the agent's company (a
    holding-scope role also sees the holding's)."""
    return [
        render(r) for r in await rows(tx) if r["scope"] == "own_company" or who.scope == "holding"
    ]


async def row(tx: Tx, key: str) -> dict[str, Any] | None:
    for r in await rows(tx):
        if r["key"] == key:
            return r
    return None


def _number_key(r: dict[str, Any]) -> str | None:
    for k in NUMBER_KEYS:
        if k in (r.get("lim") or {}):
            return k
    return None


def clamp(r: dict[str, Any], value: float) -> float:
    b = r.get("bounds") or {}
    if "min" in b:
        value = max(value, float(b["min"]))
    if "max" in b:
        value = min(value, float(b["max"]))
    return value


async def limit_value(tx: Tx, key: str, default: float) -> float:
    """The number in force for `key` (the row's, clamped into its bounds)."""
    r = await row(tx, key)
    field = _number_key(r) if r else None
    if r is None or field is None:
        return default
    value = (r["lim"] or {}).get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return clamp(r, float(value))


async def list_value(tx: Tx, key: str, default: list[str]) -> list[str]:
    r = await row(tx, key)
    if r is None:
        return default
    lim = r["lim"] or {}
    field = next((k for k in LIST_KEYS if k in lim), None)
    if field is None or not isinstance(lim[field], list):
        return default
    allowed = set((r.get("bounds") or {}).get("allowed") or lim[field])
    return [str(x) for x in lim[field] if x in allowed]


# ----------------------------------------------------------------- change --
def validate_change(
    r: dict[str, Any] | None, c: AuthorityRuleChange
) -> tuple[str, dict[str, Any] | None]:
    """(actor, limit) of an allowed change; 422 for a locked row, a number
    outside its bounds, an actor other than the owner or the seeded one."""
    if r is None:
        raise ApiError(422, "validation_failed", fields={c.key: "no such rule"})
    if r["locked"]:
        raise ApiError(422, "validation_failed", fields={c.key: "locked: it comes from code"})
    actor = c.actor or r["actor"]
    if actor not in (r["default_actor"], "owner"):
        raise ApiError(
            422, "validation_failed", fields={c.key: f"actor: owner or {r['default_actor']}"}
        )
    current = r["lim"]
    if current is None:
        if c.limit:
            raise ApiError(422, "validation_failed", fields={c.key: "this rule has no limit"})
        return actor, None
    lim = c.limit if c.limit is not None else current
    if set(lim) != set(current):
        raise ApiError(
            422, "validation_failed", fields={c.key: f"limit keys: {', '.join(sorted(current))}"}
        )
    out: dict[str, Any] = {}
    bounds = r.get("bounds") or {}
    for k, v in lim.items():
        if k in NUMBER_KEYS:
            if isinstance(v, bool) or not isinstance(v, int | float):
                raise ApiError(422, "validation_failed", fields={f"{c.key}.{k}": "a number"})
            lo, hi = bounds.get("min"), bounds.get("max")
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                raise ApiError(
                    422, "validation_failed", fields={f"{c.key}.{k}": f"outside bounds {lo}..{hi}"}
                )
            out[k] = v
        elif k in LIST_KEYS:
            allowed = list(bounds.get("allowed") or [])
            if not isinstance(v, list) or len(set(map(str, v))) != len(v):
                raise ApiError(
                    422, "validation_failed", fields={f"{c.key}.{k}": "a list, no repeats"}
                )
            if not set(map(str, v)) <= set(allowed):
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={f"{c.key}.{k}": f"only of {', '.join(allowed)}"},
                )
            out[k] = [x for x in allowed if x in v]
        else:
            raise ApiError(422, "validation_failed", fields={f"{c.key}.{k}": "unknown limit"})
    return actor, out


async def apply(
    tx: Tx,
    who: Principal,
    changes: list[AuthorityRuleChange],
    *,
    decision_ref: str | None = None,
    check_versions: bool = True,
) -> list[dict[str, Any]]:
    """Every change or none (one transaction): each row's version must match
    (409 version_conflict), then the history row and the new version."""
    if len({c.key for c in changes}) != len(changes):
        raise ApiError(422, "validation_failed", fields={"rules": "each key once"})
    current = {r["key"]: r for r in await rows(tx)}
    done = []
    for c in changes:
        r = current.get(c.key)
        actor, lim = validate_change(r, c)
        assert r is not None
        if check_versions and r["version"] != c.version:
            raise ApiError(409, "version_conflict", f"{c.key} is at version {r['version']}")
        before = {"actor": r["actor"], "limit": r["lim"]}
        after = {"actor": actor, "limit": lim}
        if before == after:
            continue
        await tx.exec(
            """UPDATE governance.authority SET actor = :a, lim = CAST(:l AS jsonb),
                   updated_by_kind = :bk, updated_by_code = :bc WHERE key = :k""",
            a=actor,
            l=_j(lim),
            bk="owner" if who.is_owner else "service",
            bc=who.code,
            k=c.key,
        )
        if c.key == ATTENTION and lim is not None:
            await tx.exec(
                "UPDATE owner.settings SET ceo_daily_attention = :n WHERE id = 1",
                n=int(lim["count_day"]),
            )
        version = int(
            await tx.scalar("SELECT version FROM governance.authority WHERE key = :k", k=c.key)
        )
        await tx.exec(
            """INSERT INTO governance.authority_history (key, version, before, after, by_kind, by_code,
                   decision_ref)
               VALUES (:k, :v, CAST(:b AS jsonb), CAST(:a AS jsonb), :bk, :bc, :d)""",
            k=c.key,
            v=version,
            b=json.dumps(before, ensure_ascii=False),
            a=json.dumps(after, ensure_ascii=False),
            bk="owner" if who.is_owner else "service",
            bc=who.code,
            d=decision_ref,
        )
        done.append({"key": c.key, "from": before, "to": after, "version": version})
    return done


# -------------------------------------------------------------------- OPA --
async def push(hub: Any) -> bool:
    """The rows to data.hq.authority now."""
    async with hub.db.raw() as tx:
        doc = opa_doc(await rows(tx))
    ok: bool = await hub.policy.put_authority(doc)
    if ok:
        _SYNC.update(at=time.monotonic(), digest=doc["version"])
    return ok


async def ensure(hub: Any, *, force: bool = False) -> None:
    """Push when OPA's copy is not this database's (an OPA restart loses the
    pushed data: its defaults would apply until then). Checked at most every
    TTL_S seconds per process; `force` after a change."""
    if not force and time.monotonic() - float(_SYNC["at"]) < TTL_S:
        return
    async with hub.db.raw() as tx:
        digest = opa_doc(await rows(tx))["version"]
    if force or await hub.policy.value("limits/version") != digest:
        await push(hub)
    else:
        _SYNC.update(at=time.monotonic(), digest=digest)


async def within(hub: Any, tx: Tx, key: str, count: int, default: float) -> bool:
    """count < the rule's number, by the database row and by OPA (both)."""
    ok = count < await limit_value(tx, key, default)
    policy = getattr(hub, "policy", None) if hub is not None else None
    if policy is None or not ok:
        return ok
    await ensure(hub)
    verdict = await policy.query("limits", {"rule": key, "count": count})
    if "policy_unavailable" in verdict.reasons:
        raise ApiError(503, "policy_unavailable", "policy service unavailable (fail-closed)")
    return bool(verdict.allow)
