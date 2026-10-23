"""The archive's open layer (contract §23.2-§23.4, §23.7, §23.10, §23.12).

Everything that describes the archive is a versioned row the owner extends
from the app: classes and their fields, folders, levels, clearance, retention
and reminder rules, party kinds, link kinds, automations. `put` validates a
body against the closed vocabulary (422 schema_invalid with `fields`),
reports its impact and applies it; a class change is a new class version, a
field is never deleted (only `retired`), a used level keeps its rank.

The body of `PUT /archive/schema/{part}/{key}` is the row as the app shows it
(server fields such as `version`, usage counts or `ref` are ignored). Parts
keyed by a ref (folders, retention, reminders, automations) are created with
key `new`, and the server assigns the ref.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import yaml

from hq_api.archive import vocab as V
from hq_api.archive.common import J, actor_of, dumps, holding, invalid
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal

SEED_DIR = Path(os.environ.get("HQ_ARCHIVE_SEED", "/app/seed/archive"))
IGNORED = {
    "key",
    "ref",
    "version",
    "status",
    "records",
    "parties",
    "usage",
    "runs_30d",
    "last_run_at",
    "created_at",
    "updated_at",
    "subject",
}
FOLDER_RE = re.compile(r"^FP-[0-9]{4,}$")
RR_RE = re.compile(r"^RR-[0-9]{4,}$")
TO_ROLE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
SUBJECT = re.compile(
    r"^(role|employee):([a-z][a-z0-9_]{1,40}|\*|[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?)$"
)


# ================================================================ reading ==
async def levels(tx: Tx) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT l.*, (SELECT count(*) FROM archive.records r WHERE r.level = l.key) AS records
           FROM archive.levels l ORDER BY l.rank"""
    )


async def level(tx: Tx, key: str) -> dict[str, Any] | None:
    return await tx.first("SELECT * FROM archive.levels WHERE key = :k", k=key)


async def class_row(tx: Tx, key: str) -> dict[str, Any] | None:
    return await tx.first("SELECT * FROM archive.classes WHERE key = :k", k=key)


async def class_at(tx: Tx, key: str, version: int) -> dict[str, Any]:
    """A class as it was at `version` (spec and fields)."""
    row = await tx.first(
        "SELECT spec, fields FROM archive.class_versions WHERE class_key = :k AND version = :v",
        k=key,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no class {key}@{version}")
    return {"key": key, "version": version, **J(row["spec"], {}), "fields": J(row["fields"], [])}


def render_class(r: dict[str, Any]) -> dict[str, Any]:
    spec = J(r["spec"], {})
    out = {
        "key": r["key"],
        **spec,
        "fields": J(r["fields"], []),
        "version": r["version"],
        "status": r["status"],
    }
    if "records" in r:
        out["records"] = int(r["records"] or 0)
    return out


def render_level(r: dict[str, Any]) -> dict[str, Any]:
    out = {
        k: r[k]
        for k in (
            "key",
            "title_fa",
            "rank",
            "color_index",
            "watermark",
            "encrypt",
            "step_up_to_view",
            "agents_max",
            "status",
            "version",
        )
    }
    if "records" in r:
        out["records"] = int(r["records"] or 0)
    return out


def render_clearance(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": r["subject"],
        "grants": J(r["grants"], []),
        "metadata_level": r["metadata_level"],
        "status": r["status"],
        "version": r["version"],
    }


async def render_folder(tx: Tx, r: dict[str, Any]) -> dict[str, Any]:
    parent = None
    if r["parent_id"]:
        parent = await tx.scalar("SELECT ref FROM archive.folders WHERE id = :p", p=r["parent_id"])
    out = {
        "ref": r["ref"],
        "scope": r.get("scope")
        or await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=r["company_id"]),
        "parent": parent,
        "title_fa": r["title_fa"],
        "classes": list(r["classes"] or []),
        "default_level": r["default_level"],
        "order": r["sort"],
        "status": r["status"],
        "version": r["version"],
    }
    if "records" in r:
        out["records"] = int(r["records"] or 0)
    return out


def render_retention(r: dict[str, Any]) -> dict[str, Any]:
    out = {
        "ref": r["ref"],
        "title_fa": r["title_fa"],
        "trigger": r["trigger"],
        "keep": J(r["keep"]),
        "then": r["then_do"],
        "status": r["status"],
        "version": r["version"],
    }
    if "records" in r:
        out["records"] = int(r["records"] or 0)
    return out


def render_reminder(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": r["ref"],
        "class": r["class_key"],
        "field": r["field"],
        "lead_days": list(r["lead_days"]),
        "to": J(r["to_whom"]),
        "channel": r["channel"],
        "status": r["status"],
        "version": r["version"],
    }


def render_party_kind(r: dict[str, Any]) -> dict[str, Any]:
    out = {
        "key": r["key"],
        "title_fa": r["title_fa"],
        "identifier_fields": J(r["identifier_fields"], []),
        "status": r["status"],
        "version": r["version"],
    }
    if "parties" in r:
        out["parties"] = int(r["parties"] or 0)
    return out


def render_link_kind(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r[k] for k in ("key", "title_fa", "inverse_fa", "status", "version")}
    out["to_kinds"] = list(r["to_kinds"])
    if "records" in r:
        out["records"] = int(r["records"] or 0)
    return out


def render_automation(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": r["ref"],
        "title_fa": r["title_fa"],
        "on": r["on_event"],
        "when": J(r["when_cond"], {}),
        "do": J(r["actions"], []),
        "status": r["status"],
        "version": r["version"],
        "runs_30d": int(r.get("runs_30d") or 0),
        "last_run_at": r.get("last_run_at"),
    }


async def render_party(tx: Tx, r: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": r["ref"],
        "kind": r["kind"],
        "name_fa": r["name_fa"],
        "name_en": r["name_en"],
        "identifiers": J(r["identifiers"], {}),
        "scopes": list(r["scopes"] or []),
        "status": r["status"],
        "version": r["version"],
    }


async def everything(tx: Tx) -> dict[str, Any]:
    """GET /archive/schema: everything that describes the archive."""
    classes = await tx.all(
        """SELECT c.*, (SELECT count(*) FROM archive.records r WHERE r.class_key = c.key
                          AND r.state <> 'disposed') AS records
           FROM archive.classes c ORDER BY c.key"""
    )
    folders = await tx.all(
        """SELECT f.*, co.code AS scope,
                  (SELECT count(*) FROM archive.records r WHERE r.folder_id = f.id) AS records
           FROM archive.folders f JOIN core.companies co ON co.id = f.company_id
           ORDER BY co.code, f.sort, f.ref"""
    )
    retention = await tx.all(
        """SELECT x.*, (SELECT count(*) FROM archive.records r WHERE r.retention_rule_id = x.id) AS records
           FROM archive.retention_rules x ORDER BY x.ref"""
    )
    link_kinds = await tx.all(
        """SELECT k.*, (SELECT count(*) FROM archive.links l WHERE l.kind = k.key
                          AND l.removed_at IS NULL) AS records
           FROM archive.link_kinds k ORDER BY k.key"""
    )
    party_kinds = await tx.all(
        """SELECT k.*, (SELECT count(*) FROM archive.parties p WHERE p.kind = k.key) AS parties
           FROM archive.party_kinds k ORDER BY k.key"""
    )
    autos = await tx.all(
        """SELECT a.*, (SELECT count(*) FROM archive.automation_runs x WHERE x.automation_id = a.id
                          AND x.at > now() - interval '30 days') AS runs_30d,
                  (SELECT max(x.at) FROM archive.automation_runs x WHERE x.automation_id = a.id) AS last_run_at
           FROM archive.automations a ORDER BY a.ref"""
    )
    lv = await levels(tx)
    from hq_api.archive import sources as S

    return {
        "classes": [render_class(r) for r in classes],
        "field_types": list(V.FIELD_TYPES),
        "folders": [await render_folder(tx, r) for r in folders],
        "levels": [render_level(r) for r in lv],
        "clearance": [
            render_clearance(r)
            for r in await tx.all("SELECT * FROM archive.clearance ORDER BY subject")
        ],
        "retention": [render_retention(r) for r in retention],
        "reminders": [
            render_reminder(r)
            for r in await tx.all("SELECT * FROM archive.reminder_rules ORDER BY ref")
        ],
        "party_kinds": [render_party_kind(r) for r in party_kinds],
        "parties": [
            await render_party(tx, r)
            for r in await tx.all("SELECT * FROM archive.parties ORDER BY ref")
        ],
        "link_kinds": [render_link_kind(r) for r in link_kinds],
        "automations": [render_automation(r) for r in autos],
        "sources": await S.listing(tx),
        "vocab": {
            "events": list(V.EVENTS),
            "actions": list(V.ACTIONS),
            "ops": list(V.OPS),
            "ref_kinds": list(V.REF_KINDS),
            "currencies": list(V.CURRENCIES),
            "mimes": list(V.MIMES),
            "link_to_kinds": list(V.LINK_TO_KINDS),
            "triggers": [*V.TRIGGERS_FIXED, "field:<key>"],
            "channels": list(V.CHANNELS),
            "notify_levels": list(V.NOTIFY_LEVELS),
        },
        "owner_settings": {
            "agents_max": next((r["key"] for r in lv if r["agents_max"]), None),
        },
    }


# ============================================================= validating ==
def _clean(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in IGNORED}


def _str(
    errors: dict[str, str], path: str, v: Any, *, cap: int, required: bool = True
) -> str | None:
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v.strip() or len(v) > cap:
        errors[path] = f"text of 1-{cap} characters"
        return None
    return v.strip()


def _bool(errors: dict[str, str], path: str, v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if not isinstance(v, bool):
        errors[path] = "true or false"
        return default
    return v


def _int(
    errors: dict[str, str], path: str, v: Any, lo: int, hi: int, default: int | None = None
) -> int:
    if v is None and default is not None:
        return default
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        errors[path] = f"an integer {lo}-{hi}"
        return default or lo
    return v


def _unknown(
    errors: dict[str, str], body: dict[str, Any], known: set[str], prefix: str = ""
) -> None:
    for k in body:
        if k not in known:
            errors[f"{prefix}{k}"] = "unknown field"


def check_field(
    errors: dict[str, str], path: str, f: Any, *, identifier: bool = False
) -> dict[str, Any]:
    if not isinstance(f, dict):
        errors[path] = "a field object"
        return {}
    known = {
        "key",
        "title_fa",
        "type",
        "required",
        "searchable",
        "sensitive",
        "options",
        "ref_kinds",
        "currency",
        "help_fa",
        "status",
    }
    _unknown(errors, f, known, f"{path}.")
    out: dict[str, Any] = {}
    key = f.get("key")
    if not isinstance(key, str) or not V.KEY.fullmatch(key):
        errors[f"{path}.key"] = "a key (a-z, 0-9, _)"
    out["key"] = key
    out["title_fa"] = _str(errors, f"{path}.title_fa", f.get("title_fa"), cap=120)
    t = f.get("type")
    allowed = ("text", "id_code", "iban", "url", "email", "phone") if identifier else V.FIELD_TYPES
    if t not in allowed:
        errors[f"{path}.type"] = f"one of {', '.join(allowed)}"
    out["type"] = t
    for flag in ("required", "searchable", "sensitive"):
        out[flag] = _bool(errors, f"{path}.{flag}", f.get(flag))
    if t in ("enum", "multi_enum"):
        opts = f.get("options")
        if not isinstance(opts, list) or not opts or len(opts) > 100:
            errors[f"{path}.options"] = "1-100 options {key, title_fa}"
        else:
            seen: set[str] = set()
            clean = []
            for i, o in enumerate(opts):
                ok = (
                    isinstance(o, dict)
                    and isinstance(o.get("key"), str)
                    and V.KEY.fullmatch(o["key"])
                    and isinstance(o.get("title_fa"), str)
                    and 0 < len(o["title_fa"]) <= 120
                    and o["key"] not in seen
                )
                if not ok:
                    errors[f"{path}.options.{i}"] = "{key, title_fa}, keys unique"
                else:
                    seen.add(o["key"])
                    clean.append({"key": o["key"], "title_fa": o["title_fa"]})
            out["options"] = clean
    elif f.get("options") is not None:
        errors[f"{path}.options"] = "only for enum and multi_enum"
    if t == "ref":
        kinds = f.get("ref_kinds") or list(V.REF_KINDS)
        if not isinstance(kinds, list) or not all(k in V.REF_KINDS for k in kinds):
            errors[f"{path}.ref_kinds"] = f"some of {', '.join(V.REF_KINDS)}"
        out["ref_kinds"] = list(kinds) if isinstance(kinds, list) else []
    elif f.get("ref_kinds") is not None:
        errors[f"{path}.ref_kinds"] = "only for ref"
    if t == "money" and f.get("currency") is not None:
        if f["currency"] not in V.CURRENCIES:
            errors[f"{path}.currency"] = f"one of {', '.join(V.CURRENCIES)}"
        out["currency"] = f["currency"]
    elif f.get("currency") is not None:
        errors[f"{path}.currency"] = "only for money"
    if f.get("help_fa") is not None:
        out["help_fa"] = _str(errors, f"{path}.help_fa", f["help_fa"], cap=500)
    status = f.get("status", "active")
    if status not in ("active", "retired"):
        errors[f"{path}.status"] = "active or retired"
    out["status"] = status
    return out


async def _scopes(tx: Tx, errors: dict[str, str], path: str, v: Any) -> Any:
    if v in (None, "all"):
        return "all"
    if not isinstance(v, list) or not v or len(v) > 200:
        errors[path] = '"all" or a list of scopes'
        return "all"
    out = []
    for i, code in enumerate(v):
        if not isinstance(code, str) or not await tx.scalar(
            "SELECT 1 FROM core.companies WHERE code = :c", c=code
        ):
            errors[f"{path}.{i}"] = "an existing company code"
        else:
            out.append(code)
    return out


async def check_class(
    tx: Tx, key: str, body: dict[str, Any], current: dict[str, Any] | None
) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    known = {
        "title_fa",
        "parent",
        "scopes",
        "icon",
        "default_level",
        "default_folder",
        "fields",
        "required_files",
        "allowed_mime",
        "ocr",
        "retention",
        "reminder_fields",
        "auto_link",
    }
    _unknown(errors, b, known)
    spec: dict[str, Any] = {"title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=120)}
    parent = b.get("parent")
    if parent is not None:
        if parent == key or not await class_row(tx, parent):
            errors["parent"] = "an existing class (not itself)"
        else:  # no cycle
            seen, at = {key}, parent
            while at:
                if at in seen:
                    errors["parent"] = "a cycle"
                    break
                seen.add(at)
                p = await class_row(tx, at)
                at = J(p["spec"], {}).get("parent") if p else None
    spec["parent"] = parent
    spec["scopes"] = await _scopes(tx, errors, "scopes", b.get("scopes"))
    icon = b.get("icon") or "folder"
    if not isinstance(icon, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", icon):
        errors["icon"] = "an icon name"
    spec["icon"] = icon
    dl = b.get("default_level") or "internal"
    if not await level(tx, dl):
        errors["default_level"] = "an existing level"
    spec["default_level"] = dl
    df = b.get("default_folder")
    if df is not None and (
        not isinstance(df, str)
        or not FOLDER_RE.fullmatch(df)
        or not await tx.scalar("SELECT 1 FROM archive.folders WHERE ref = :r", r=df)
    ):
        errors["default_folder"] = "an existing folder FP-…"
    spec["default_folder"] = df
    spec["required_files"] = _int(errors, "required_files", b.get("required_files"), 0, 20, 0)
    mimes = b.get("allowed_mime") or list(V.MIMES)
    if not isinstance(mimes, list) or not all(m in V.MIMES for m in mimes):
        errors["allowed_mime"] = f"some of {', '.join(V.MIMES)}"
    spec["allowed_mime"] = list(dict.fromkeys(mimes)) if isinstance(mimes, list) else []
    spec["ocr"] = _bool(errors, "ocr", b.get("ocr"), True)
    rr = b.get("retention")
    if rr is not None and (
        not isinstance(rr, str)
        or not RR_RE.fullmatch(rr)
        or not await tx.scalar("SELECT 1 FROM archive.retention_rules WHERE ref = :r", r=rr)
    ):
        errors["retention"] = "an existing retention rule RR-…"
    spec["retention"] = rr
    raw_fields = b.get("fields") or []
    if not isinstance(raw_fields, list) or len(raw_fields) > 200:
        errors["fields"] = "a list of at most 200 fields"
        raw_fields = []
    fields = [check_field(errors, f"fields.{i}", f) for i, f in enumerate(raw_fields)]
    keys = [f.get("key") for f in fields]
    for i, k in enumerate(keys):
        if k is not None and keys.index(k) != i:
            errors[f"fields.{i}.key"] = "used twice"
    if current is not None:  # a field is never deleted, its type never changes
        old = {f["key"]: f for f in J(current["fields"], [])}
        new = {f.get("key"): (i, f) for i, f in enumerate(fields)}
        for k, f in old.items():
            if k not in new:
                errors[f"fields.{k}"] = "a field is retired, never removed"
                continue
            i, nf = new[k]
            if nf.get("type") != f["type"]:
                errors[f"fields.{i}.type"] = f"was {f['type']}: a field keeps its type"
            if f["type"] in ("enum", "multi_enum"):
                gone = {o["key"] for o in f.get("options") or []} - {
                    o["key"] for o in nf.get("options") or []
                }
                if gone:
                    errors[f"fields.{i}.options"] = (
                        f"options are never removed: {', '.join(sorted(gone))}"
                    )
    by_key = {f.get("key"): f for f in fields}
    rf = b.get("reminder_fields") or []
    if not isinstance(rf, list) or not all(
        isinstance(k, str) and by_key.get(k, {}).get("type") in ("date", "date_range") for k in rf
    ):
        errors["reminder_fields"] = "keys of this class's date fields"
    spec["reminder_fields"] = list(rf) if isinstance(rf, list) else []
    al = b.get("auto_link") or []
    clean_al = []
    if not isinstance(al, list):
        errors["auto_link"] = "a list of {field, link_kind}"
        al = []
    for i, a in enumerate(al):
        ok = (
            isinstance(a, dict)
            and set(a) == {"field", "link_kind"}
            and by_key.get(a["field"], {}).get("type") in ("ref", "party", "company")
            and await tx.scalar("SELECT 1 FROM archive.link_kinds WHERE key = :k", k=a["link_kind"])
        )
        if not ok:
            errors[f"auto_link.{i}"] = (
                "{field: a ref, party or company field, link_kind: an existing link kind}"
            )
        else:
            clean_al.append({"field": a["field"], "link_kind": a["link_kind"]})
    spec["auto_link"] = clean_al
    if errors:
        raise invalid(errors)
    return {"spec": spec, "fields": fields}


async def check_folder(
    tx: Tx, body: dict[str, Any], current: dict[str, Any] | None
) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    b.pop("scope", None) if current is not None else None
    _unknown(errors, b, {"scope", "parent", "title_fa", "classes", "default_level", "order"})
    out: dict[str, Any] = {"title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=200)}
    if current is None:
        code = body.get("scope")
        co = (
            await tx.first("SELECT id FROM core.companies WHERE code = :c", c=code)
            if isinstance(code, str)
            else None
        )
        if co is None:
            errors["scope"] = "an existing company code"
        out["company_id"] = co["id"] if co else None
    else:
        out["company_id"] = current["company_id"]
    parent = b.get("parent")
    out["parent_id"] = None
    if parent is not None:
        p = (
            await tx.first("SELECT id, company_id FROM archive.folders WHERE ref = :r", r=parent)
            if isinstance(parent, str)
            else None
        )
        if p is None or (out["company_id"] and p["company_id"] != out["company_id"]):
            errors["parent"] = "a folder of the same scope"
        elif current is not None and p["id"] == current["id"]:
            errors["parent"] = "not itself"
        else:
            out["parent_id"] = p["id"]
            if current is not None:  # no cycle
                at = p["id"]
                for _ in range(50):
                    if at is None:
                        break
                    if at == current["id"]:
                        errors["parent"] = "a cycle"
                        break
                    at = await tx.scalar(
                        "SELECT parent_id FROM archive.folders WHERE id = :i", i=at
                    )
    classes = b.get("classes") or []
    if not isinstance(classes, list) or len(classes) > 100:
        errors["classes"] = "a list of class keys"
        classes = []
    for i, k in enumerate(classes):
        if not isinstance(k, str) or not await class_row(tx, k):
            errors[f"classes.{i}"] = "an existing class"
    out["classes"] = [k for k in classes if isinstance(k, str)]
    dl = b.get("default_level")
    if dl is not None and not await level(tx, dl):
        errors["default_level"] = "an existing level"
    out["default_level"] = dl
    out["sort"] = _int(errors, "order", b.get("order"), 0, 100000, 100)
    if errors:
        raise invalid(errors)
    return out


async def check_level(
    tx: Tx, key: str, body: dict[str, Any], current: dict[str, Any] | None
) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    known = {
        "title_fa",
        "rank",
        "color_index",
        "watermark",
        "encrypt",
        "step_up_to_view",
        "agents_max",
    }
    _unknown(errors, b, known)
    if not V.KEY.fullmatch(key) or len(key) > 31:
        errors["key"] = "a key (a-z, 0-9, _)"
    out: dict[str, Any] = {"title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=60)}
    out["rank"] = _int(errors, "rank", b.get("rank"), 0, 1000)
    out["color_index"] = _int(errors, "color_index", b.get("color_index"), 0, 11, 0)
    for flag in ("watermark", "encrypt", "step_up_to_view", "agents_max"):
        out[flag] = _bool(errors, flag, b.get(flag))
    if "rank" not in errors:
        clash = await tx.scalar(
            "SELECT key FROM archive.levels WHERE rank = :r AND key <> :k", r=out["rank"], k=key
        )
        if clash:
            errors["rank"] = f"the rank of {clash}"
    if current is not None and out.get("rank") != current["rank"]:
        used = await tx.scalar("SELECT count(*) FROM archive.records WHERE level = :k", k=key)
        if used:
            errors["rank"] = f"fixed: {used} record(s) use this level"
    if (
        current is not None
        and bool(current["encrypt"]) != bool(out["encrypt"])
        and await tx.scalar("SELECT 1 FROM archive.records WHERE level = :k LIMIT 1", k=key)
    ):
        errors["encrypt"] = "fixed: records of this level are stored that way"
    if errors:
        raise invalid(errors)
    return out


async def check_clearance(tx: Tx, subject: str, body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    _unknown(errors, b, {"grants", "metadata_level"})
    if not SUBJECT.fullmatch(subject):
        errors["subject"] = "role:<role>, role:* or employee:<code>"
    cap = await tx.first("SELECT key, rank FROM archive.levels WHERE agents_max")
    ranks = {r["key"]: r["rank"] for r in await tx.all("SELECT key, rank FROM archive.levels")}
    grants = b.get("grants")
    if not isinstance(grants, list) or len(grants) > 100:
        errors["grants"] = "a list of {scope, level}"
        grants = []
    out_grants = []
    for i, g in enumerate(grants):
        if not isinstance(g, dict) or set(g) - {"scope", "level"}:
            errors[f"grants.{i}"] = "{scope, level}"
            continue
        scope, lv = g.get("scope"), g.get("level")
        if scope not in ("own", "holding", "all") and not (
            isinstance(scope, str)
            and await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=scope)
        ):
            errors[f"grants.{i}.scope"] = "own, holding, all or a company code"
        if lv not in ranks:
            errors[f"grants.{i}.level"] = "an existing level"
        elif cap is not None and ranks[lv] > cap["rank"]:
            errors[f"grants.{i}.level"] = f"above agents_max ({cap['key']})"
        out_grants.append({"scope": scope, "level": lv})
    ml = b.get("metadata_level")
    if ml is not None and ml not in ranks:
        errors["metadata_level"] = "an existing level"
    if errors:
        raise invalid(errors)
    return {"grants": out_grants, "metadata_level": ml}


async def check_retention(body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    _unknown(errors, b, {"title_fa", "trigger", "keep", "then"})
    out: dict[str, Any] = {"title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=200)}
    trig = b.get("trigger")
    if not isinstance(trig, str) or not (
        trig in V.TRIGGERS_FIXED or re.fullmatch(r"field:[a-z][a-z0-9_]{1,40}", trig)
    ):
        errors["trigger"] = "filed, case_closed, superseded or field:<key>"
    out["trigger"] = trig
    keep = b.get("keep")
    if keep == "permanent":
        out["keep"] = "permanent"
    elif isinstance(keep, dict) and keep and not set(keep) - {"years", "months"}:
        k = {u: keep[u] for u in ("years", "months") if u in keep}
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100 for v in k.values()
        ) or not any(k.values()):
            errors["keep"] = "{years?, months?}: whole numbers, not both 0"
        out["keep"] = k
    else:
        errors["keep"] = '{years?, months?} or "permanent"'
    then = b.get("then")
    if then not in V.THEN:
        errors["then"] = "review or dispose_card"
    out["then_do"] = then
    if out.get("keep") == "permanent" and then == "dispose_card":
        errors["then"] = "a permanent record is never disposed"
    if errors:
        raise invalid(errors)
    return out


async def check_reminder(tx: Tx, body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    cls_key = b.pop("class", None)
    _unknown(errors, b, {"field", "lead_days", "to", "channel"})
    c = await class_row(tx, cls_key) if isinstance(cls_key, str) else None
    if c is None:
        errors["class"] = "an existing class"
    field = b.get("field")
    types = {f["key"]: f["type"] for f in J(c["fields"], [])} if c else {}
    if types.get(field) not in ("date", "date_range"):
        errors["field"] = "a date field of the class"
    lead = b.get("lead_days")
    if (
        not isinstance(lead, list)
        or not 1 <= len(lead) <= 10
        or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 3650 for x in lead)
        or len(set(lead)) != len(lead)
    ):
        errors["lead_days"] = "1-10 distinct whole days 0-3650"
    to = b.get("to", "owner")
    if not (
        to == "owner"
        or (
            isinstance(to, dict)
            and (
                (
                    set(to) == {"role"}
                    and isinstance(to["role"], str)
                    and TO_ROLE.fullmatch(to["role"])
                )
                or to == {"company_ceo": True}
            )
        )
    ):
        errors["to"] = "owner, {role} or {company_ceo: true}"
    ch = b.get("channel", "cartable")
    if ch not in V.CHANNELS:
        errors["channel"] = "cartable or digest"
    if errors:
        raise invalid(errors)
    return {
        "class_key": cls_key,
        "field": field,
        "lead_days": sorted(lead or [], reverse=True),
        "to_whom": to,
        "channel": ch,
    }


async def check_party_kind(body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    _unknown(errors, b, {"title_fa", "identifier_fields"})
    title = _str(errors, "title_fa", b.get("title_fa"), cap=100)
    raw = b.get("identifier_fields") or []
    if not isinstance(raw, list) or len(raw) > 30:
        errors["identifier_fields"] = "a list of at most 30 fields"
        raw = []
    fields = [
        check_field(errors, f"identifier_fields.{i}", f, identifier=True) for i, f in enumerate(raw)
    ]
    if errors:
        raise invalid(errors)
    return {"title_fa": title, "identifier_fields": fields}


async def check_link_kind(body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    _unknown(errors, b, {"title_fa", "inverse_fa", "to_kinds"})
    out: dict[str, Any] = {
        "title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=100),
        "inverse_fa": _str(errors, "inverse_fa", b.get("inverse_fa"), cap=100),
    }
    kinds = b.get("to_kinds")
    if not isinstance(kinds, list) or not kinds or not all(k in V.LINK_TO_KINDS for k in kinds):
        errors["to_kinds"] = f"some of {', '.join(V.LINK_TO_KINDS)}"
        kinds = []
    out["to_kinds"] = list(dict.fromkeys(kinds))
    if errors:
        raise invalid(errors)
    return out


async def check_automation(tx: Tx, body: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    b = _clean(body)
    _unknown(errors, b, {"title_fa", "on", "when", "do"})
    out: dict[str, Any] = {"title_fa": _str(errors, "title_fa", b.get("title_fa"), cap=200)}
    on = b.get("on")
    if on not in V.EVENTS:
        errors["on"] = f"one of {', '.join(V.EVENTS)}"
    out["on_event"] = on
    when = b.get("when") or {}
    if not isinstance(when, dict):
        errors["when"] = "{class?, scope?, level_min?, field?}"
        when = {}
    _unknown(errors, when, {"class", "scope", "level_min", "field"}, "when.")
    if "class" in when and not (
        isinstance(when["class"], str) and await class_row(tx, when["class"])
    ):
        errors["when.class"] = "an existing class"
    if "scope" in when and not (
        isinstance(when["scope"], str)
        and await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=when["scope"])
    ):
        errors["when.scope"] = "an existing company code"
    if "level_min" in when and not (
        isinstance(when["level_min"], str) and await level(tx, when["level_min"])
    ):
        errors["when.level_min"] = "an existing level"
    if "field" in when:
        f = when["field"]
        if not (
            isinstance(f, dict)
            and set(f) == {"key", "op", "value"}
            and isinstance(f["key"], str)
            and V.KEY.fullmatch(f["key"])
            and f["op"] in V.OPS
            and isinstance(f["value"], (str, int, float, bool))
        ):
            errors["when.field"] = "{key, op: eq|lt|gt|contains, value}"
    out["when_cond"] = when
    actions = b.get("do")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 10:
        errors["do"] = "1-10 actions"
        actions = []
    clean = []
    for i, a in enumerate(actions):
        p = f"do.{i}"
        if (
            not isinstance(a, dict)
            or a.get("action") not in V.ACTIONS
            or set(a) - {"action", "args"}
        ):
            errors[p] = f"{{action: one of {', '.join(V.ACTIONS)}, args}}"
            continue
        args = a.get("args") or {}
        if not isinstance(args, dict):
            errors[f"{p}.args"] = "an object"
            continue
        act = a["action"]
        if act == "notify":
            _unknown(errors, args, {"to", "level", "text_fa"}, f"{p}.args.")
            to = args.get("to", "owner")
            if not (to == "owner" or (isinstance(to, str) and TO_ROLE.fullmatch(to))):
                errors[f"{p}.args.to"] = "owner or a role key"
            if args.get("level", "info") not in V.NOTIFY_LEVELS:
                errors[f"{p}.args.level"] = "info, report or decision (never urgent)"
            _str(errors, f"{p}.args.text_fa", args.get("text_fa"), cap=500)
        elif act == "work_item":
            _unknown(errors, args, {"role", "title_fa"}, f"{p}.args.")
            if not (isinstance(args.get("role"), str) and TO_ROLE.fullmatch(args["role"])):
                errors[f"{p}.args.role"] = "a role key of the hub (never a person outside it)"
            _str(errors, f"{p}.args.title_fa", args.get("title_fa"), cap=300)
        elif act == "link":
            _unknown(errors, args, {"kind", "to"}, f"{p}.args.")
            if not (
                isinstance(args.get("kind"), str)
                and await tx.scalar(
                    "SELECT 1 FROM archive.link_kinds WHERE key = :k", k=args["kind"]
                )
            ):
                errors[f"{p}.args.kind"] = "an existing link kind"
            to = args.get("to")
            if not (
                isinstance(to, dict)
                and set(to) == {"kind", "ref"}
                and to["kind"] in V.LINK_TO_KINDS
                and isinstance(to["ref"], str)
                and V.REF_PATTERNS.get(to["kind"], re.compile("^$")).fullmatch(to["ref"])
            ):
                errors[f"{p}.args.to"] = "{kind, ref}"
        elif act == "move_to_folder":
            _unknown(errors, args, {"folder"}, f"{p}.args.")
            if not (
                isinstance(args.get("folder"), str)
                and await tx.scalar(
                    "SELECT 1 FROM archive.folders WHERE ref = :r", r=args["folder"]
                )
            ):
                errors[f"{p}.args.folder"] = "an existing folder"
        elif act == "raise_level":
            _unknown(errors, args, {"level"}, f"{p}.args.")
            if not (isinstance(args.get("level"), str) and await level(tx, args["level"])):
                errors[f"{p}.args.level"] = "an existing level (raised only, never lowered)"
        elif act == "add_reminder":
            _unknown(errors, args, {"field", "lead_days"}, f"{p}.args.")
            if not (isinstance(args.get("field"), str) and V.KEY.fullmatch(args["field"])):
                errors[f"{p}.args.field"] = "a date field key"
            ld = args.get("lead_days")
            if not (isinstance(ld, int) and not isinstance(ld, bool) and 0 <= ld <= 3650):
                errors[f"{p}.args.lead_days"] = "whole days 0-3650"
        clean.append({"action": act, "args": args})
    out["actions"] = clean
    if errors:
        raise invalid(errors)
    return out


# ================================================================ impact ==
async def impact(tx: Tx, part: str, key: str, checked: dict[str, Any] | None) -> dict[str, int]:
    """How many records a change touches, and how many would miss a newly
    required field (classes)."""
    records = 0
    missing = 0
    if part == "classes":
        records = int(
            await tx.scalar(
                "SELECT count(*) FROM archive.records WHERE class_key = :k AND state <> 'disposed'",
                k=key,
            )
            or 0
        )
        if checked is not None:
            req = [
                f["key"]
                for f in checked["fields"]
                if f.get("required") and f.get("status") == "active"
            ]
            if req:
                missing = int(
                    await tx.scalar(
                        """SELECT count(*) FROM archive.records WHERE class_key = :k
                         AND state IN ('filed', 'sealed', 'superseded')
                         AND NOT (metadata ?& CAST(:req AS text[]))""",
                        k=key,
                        req=req,
                    )
                    or 0
                )
    elif part == "levels":
        records = int(
            await tx.scalar("SELECT count(*) FROM archive.records WHERE level = :k", k=key) or 0
        )
    elif part == "folders" and key != "new":
        records = int(
            await tx.scalar(
                "SELECT count(*) FROM archive.records r JOIN archive.folders f ON f.id = r.folder_id WHERE f.ref = :k",
                k=key,
            )
            or 0
        )
    elif part == "retention" and key != "new":
        records = int(
            await tx.scalar(
                """SELECT count(*) FROM archive.records r JOIN archive.retention_rules x ON x.id = r.retention_rule_id
               WHERE x.ref = :k""",
                k=key,
            )
            or 0
        )
    elif part == "link_kinds":
        records = int(
            await tx.scalar(
                "SELECT count(DISTINCT record_id) FROM archive.links WHERE kind = :k AND removed_at IS NULL",
                k=key,
            )
            or 0
        )
    elif part == "party_kinds":
        records = int(
            await tx.scalar("SELECT count(*) FROM archive.parties WHERE kind = :k", k=key) or 0
        )
    elif part == "reminders" and checked is not None:
        records = int(
            await tx.scalar(
                "SELECT count(*) FROM archive.records WHERE class_key = :c AND state IN ('filed', 'sealed')",
                c=checked["class_key"],
            )
            or 0
        )
    return {"records": records, "missing_required": missing}


# ================================================================ writing ==
TABLE = {
    "classes": ("archive.classes", "key"),
    "levels": ("archive.levels", "key"),
    "clearance": ("archive.clearance", "subject"),
    "party_kinds": ("archive.party_kinds", "key"),
    "link_kinds": ("archive.link_kinds", "key"),
    "folders": ("archive.folders", "ref"),
    "retention": ("archive.retention_rules", "ref"),
    "reminders": ("archive.reminder_rules", "ref"),
    "automations": ("archive.automations", "ref"),
}


async def current(tx: Tx, part: str, key: str, *, lock: bool = False) -> dict[str, Any] | None:
    if part not in TABLE:
        raise ApiError(404, "not_found", f"no schema part {part}")
    if key == "new":
        return None
    table, col = TABLE[part]
    return await tx.first(
        f"SELECT * FROM {table} WHERE {col} = :k" + (" FOR UPDATE" if lock else ""),  # noqa: S608
        k=key,
    )


async def check(
    tx: Tx, part: str, key: str, body: dict[str, Any], row: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise invalid({"body": "an object"})
    if part in V.REF_PARTS and row is None and key != "new":
        raise ApiError(404, "not_found", f"no {part} {key}; create it with key `new`")
    if part not in V.REF_PARTS and not V.KEY.fullmatch(key) and part != "clearance":
        raise invalid({"key": "a key (a-z, 0-9, _)"})
    if part == "classes":
        return await check_class(tx, key, body, row)
    if part == "folders":
        return await check_folder(tx, body, row)
    if part == "levels":
        return await check_level(tx, key, body, row)
    if part == "clearance":
        return await check_clearance(tx, key, body)
    if part == "retention":
        return await check_retention(body)
    if part == "reminders":
        return await check_reminder(tx, body)
    if part == "party_kinds":
        return await check_party_kind(body)
    if part == "link_kinds":
        return await check_link_kind(body)
    if part == "automations":
        return await check_automation(tx, body)
    raise ApiError(404, "not_found", f"no schema part {part}")


async def render_row(tx: Tx, part: str, row: dict[str, Any]) -> dict[str, Any]:
    if part == "classes":
        return render_class(row)
    if part == "levels":
        return render_level(row)
    if part == "clearance":
        return render_clearance(row)
    if part == "folders":
        return await render_folder(tx, row)
    if part == "retention":
        return render_retention(row)
    if part == "reminders":
        return render_reminder(row)
    if part == "party_kinds":
        return render_party_kind(row)
    if part == "link_kinds":
        return render_link_kind(row)
    return render_automation(row)


async def apply(
    tx: Tx, who: Principal, part: str, key: str, c: dict[str, Any], row: dict[str, Any] | None
) -> dict[str, Any]:
    """Writes a checked body -> the new row (its version is the new version)."""
    h = await holding(tx)
    kind, code = actor_of(who)
    if part == "classes":
        if row is None:
            new = await tx.one(
                """INSERT INTO archive.classes (key, company_id, spec, fields)
                   VALUES (:k, :co, CAST(:s AS jsonb), CAST(:f AS jsonb)) RETURNING *""",
                k=key,
                co=h["id"],
                s=dumps(c["spec"]),
                f=dumps(c["fields"]),
            )
        else:
            new = await tx.one(
                """UPDATE archive.classes SET spec = CAST(:s AS jsonb), fields = CAST(:f AS jsonb)
                   WHERE key = :k RETURNING *""",
                k=key,
                s=dumps(c["spec"]),
                f=dumps(c["fields"]),
            )
        await tx.exec(
            """INSERT INTO archive.class_versions (company_id, class_key, version, spec, fields,
                   created_by_kind, created_by_code)
               VALUES (:co, :k, :v, CAST(:s AS jsonb), CAST(:f AS jsonb), :bk, :bc)""",
            co=h["id"],
            k=key,
            v=new["version"],
            s=dumps(c["spec"]),
            f=dumps(c["fields"]),
            bk=kind,
            bc=code,
        )
        for f in c["fields"]:
            await tx.exec(
                """INSERT INTO archive.fields (company_id, class_key, key, type, spec, status, since_version,
                       retired_version)
                   VALUES (:co, :c, :k, :t, CAST(:s AS jsonb), :st, :v,
                           CASE WHEN :st = 'retired' THEN CAST(:v AS int) END)
                   ON CONFLICT (class_key, key) DO UPDATE SET spec = EXCLUDED.spec, status = EXCLUDED.status,
                       retired_version = CASE WHEN EXCLUDED.status = 'retired'
                                              THEN COALESCE(archive.fields.retired_version, EXCLUDED.since_version)
                                         END,
                       updated_at = now()""",
                co=h["id"],
                c=key,
                k=f["key"],
                t=f["type"],
                s=dumps(f),
                st=f.get("status", "active"),
                v=new["version"],
            )
        return new
    if part == "levels":
        if c["agents_max"]:
            await tx.exec(
                "UPDATE archive.levels SET agents_max = false WHERE agents_max AND key <> :k", k=key
            )
        cols = (
            "title_fa",
            "rank",
            "color_index",
            "watermark",
            "encrypt",
            "step_up_to_view",
            "agents_max",
        )
        if row is None:
            return await tx.one(
                f"""INSERT INTO archive.levels (key, company_id, {", ".join(cols)})
                    VALUES (:key, :co, {", ".join(":" + x for x in cols)}) RETURNING *""",  # noqa: S608
                key=key,
                co=h["id"],
                **{x: c[x] for x in cols},
            )
        return await tx.one(
            f"UPDATE archive.levels SET {', '.join(f'{x} = :{x}' for x in cols)} WHERE key = :key RETURNING *",  # noqa: S608
            key=key,
            **{x: c[x] for x in cols},
        )
    if part == "clearance":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.clearance (subject, company_id, grants, metadata_level)
                   VALUES (:s, :co, CAST(:g AS jsonb), :m) RETURNING *""",
                s=key,
                co=h["id"],
                g=dumps(c["grants"]),
                m=c["metadata_level"],
            )
        return await tx.one(
            """UPDATE archive.clearance SET grants = CAST(:g AS jsonb), metadata_level = :m, status = 'active'
               WHERE subject = :s RETURNING *""",
            s=key,
            g=dumps(c["grants"]),
            m=c["metadata_level"],
        )
    if part == "party_kinds":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.party_kinds (key, company_id, title_fa, identifier_fields)
                   VALUES (:k, :co, :t, CAST(:f AS jsonb)) RETURNING *""",
                k=key,
                co=h["id"],
                t=c["title_fa"],
                f=dumps(c["identifier_fields"]),
            )
        return await tx.one(
            """UPDATE archive.party_kinds SET title_fa = :t, identifier_fields = CAST(:f AS jsonb)
               WHERE key = :k RETURNING *""",
            k=key,
            t=c["title_fa"],
            f=dumps(c["identifier_fields"]),
        )
    if part == "link_kinds":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.link_kinds (key, company_id, title_fa, inverse_fa, to_kinds)
                   VALUES (:k, :co, :t, :i, :tk) RETURNING *""",
                k=key,
                co=h["id"],
                t=c["title_fa"],
                i=c["inverse_fa"],
                tk=c["to_kinds"],
            )
        return await tx.one(
            """UPDATE archive.link_kinds SET title_fa = :t, inverse_fa = :i, to_kinds = :tk
               WHERE key = :k RETURNING *""",
            k=key,
            t=c["title_fa"],
            i=c["inverse_fa"],
            tk=c["to_kinds"],
        )
    if part == "folders":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.folders (company_id, parent_id, title_fa, classes, default_level, sort)
                   VALUES (:co, :p, :t, :cl, :dl, :s) RETURNING *""",
                co=c["company_id"],
                p=c["parent_id"],
                t=c["title_fa"],
                cl=c["classes"],
                dl=c["default_level"],
                s=c["sort"],
            )
        return await tx.one(
            """UPDATE archive.folders SET parent_id = :p, title_fa = :t, classes = :cl, default_level = :dl, sort = :s
               WHERE id = :id RETURNING *""",
            id=row["id"],
            p=c["parent_id"],
            t=c["title_fa"],
            cl=c["classes"],
            dl=c["default_level"],
            s=c["sort"],
        )
    if part == "retention":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.retention_rules (company_id, title_fa, trigger, keep, then_do)
                   VALUES (:co, :t, :tr, CAST(:k AS jsonb), :th) RETURNING *""",
                co=h["id"],
                t=c["title_fa"],
                tr=c["trigger"],
                k=dumps(c["keep"]),
                th=c["then_do"],
            )
        return await tx.one(
            """UPDATE archive.retention_rules SET title_fa = :t, trigger = :tr, keep = CAST(:k AS jsonb), then_do = :th
               WHERE id = :id RETURNING *""",
            id=row["id"],
            t=c["title_fa"],
            tr=c["trigger"],
            k=dumps(c["keep"]),
            th=c["then_do"],
        )
    if part == "reminders":
        if row is None:
            return await tx.one(
                """INSERT INTO archive.reminder_rules (company_id, class_key, field, lead_days, to_whom, channel)
                   VALUES (:co, :c, :f, :ld, CAST(:to AS jsonb), :ch) RETURNING *""",
                co=h["id"],
                c=c["class_key"],
                f=c["field"],
                ld=c["lead_days"],
                to=dumps(c["to_whom"]),
                ch=c["channel"],
            )
        return await tx.one(
            """UPDATE archive.reminder_rules SET class_key = :c, field = :f, lead_days = :ld,
                   to_whom = CAST(:to AS jsonb), channel = :ch WHERE id = :id RETURNING *""",
            id=row["id"],
            c=c["class_key"],
            f=c["field"],
            ld=c["lead_days"],
            to=dumps(c["to_whom"]),
            ch=c["channel"],
        )
    # automations
    if row is None:
        return await tx.one(
            """INSERT INTO archive.automations (company_id, title_fa, on_event, when_cond, actions)
               VALUES (:co, :t, :on, CAST(:w AS jsonb), CAST(:a AS jsonb)) RETURNING *""",
            co=h["id"],
            t=c["title_fa"],
            on=c["on_event"],
            w=dumps(c["when_cond"]),
            a=dumps(c["actions"]),
        )
    return await tx.one(
        """UPDATE archive.automations SET title_fa = :t, on_event = :on, when_cond = CAST(:w AS jsonb),
               actions = CAST(:a AS jsonb) WHERE id = :id RETURNING *""",
        id=row["id"],
        t=c["title_fa"],
        on=c["on_event"],
        w=dumps(c["when_cond"]),
        a=dumps(c["actions"]),
    )


def row_key(part: str, row: dict[str, Any]) -> str:
    return str(row[TABLE[part][1]])


async def retire(tx: Tx, part: str, row: dict[str, Any]) -> dict[str, Any]:
    """Retired, never deleted: what uses it keeps it."""
    table, col = TABLE[part]
    if part == "levels" and row["agents_max"]:
        raise invalid({"key": "the agents_max level; move agents_max to another level first"})
    if part == "clearance":
        return await tx.one(
            "UPDATE archive.clearance SET status = 'retired' WHERE subject = :k RETURNING *",
            k=row["subject"],
        )
    return await tx.one(
        f"UPDATE {table} SET status = 'retired' WHERE {col} = :k RETURNING *",  # noqa: S608
        k=row[col],
    )


# =================================================================== seed ==
def _load(name: str) -> Any:
    path = SEED_DIR / name
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


async def seed(tx: Tx, holding_id: Any) -> dict[str, int]:
    """infra/seed/archive/*.yaml -> the first version of the open layer. Only
    what is missing is added; nothing the owner changed is written again."""
    added = {
        "levels": 0,
        "clearance": 0,
        "classes": 0,
        "folders": 0,
        "retention": 0,
        "reminders": 0,
        "party_kinds": 0,
        "link_kinds": 0,
        "sources": 0,
    }
    if not await asyncio.to_thread(SEED_DIR.exists):
        return added
    seeder = Principal(kind="service", code="seed", role="service")
    for lv in (_load("levels.yaml") or {}).get("levels") or []:
        if await level(tx, lv["key"]):
            continue
        if lv.get("agents_max") and await tx.scalar(
            "SELECT 1 FROM archive.levels WHERE agents_max"
        ):
            lv = {**lv, "agents_max": False}
        if await tx.scalar("SELECT 1 FROM archive.levels WHERE rank = :r", r=lv["rank"]):
            continue
        await tx.exec(
            """INSERT INTO archive.levels (key, company_id, title_fa, rank, color_index, watermark, encrypt,
                   step_up_to_view, agents_max)
               VALUES (:k, :co, :t, :r, :ci, :w, :e, :s, :a)""",
            k=lv["key"],
            co=holding_id,
            t=lv["title_fa"],
            r=lv["rank"],
            ci=lv.get("color_index", 0),
            w=bool(lv.get("watermark")),
            e=bool(lv.get("encrypt")),
            s=bool(lv.get("step_up_to_view")),
            a=bool(lv.get("agents_max")),
        )
        added["levels"] += 1
    for pk in (_load("party_kinds.yaml") or {}).get("party_kinds") or []:
        added["party_kinds"] += await tx.exec(
            """INSERT INTO archive.party_kinds (key, company_id, title_fa, identifier_fields)
               VALUES (:k, :co, :t, CAST(:f AS jsonb)) ON CONFLICT (key) DO NOTHING""",
            k=pk["key"],
            co=holding_id,
            t=pk["title_fa"],
            f=dumps(
                [
                    {
                        "required": False,
                        "searchable": False,
                        "sensitive": False,
                        "status": "active",
                        **f,
                    }
                    for f in pk.get("identifier_fields") or []
                ]
            ),
        )
    for lk in (_load("link_kinds.yaml") or {}).get("link_kinds") or []:
        added["link_kinds"] += await tx.exec(
            """INSERT INTO archive.link_kinds (key, company_id, title_fa, inverse_fa, to_kinds)
               VALUES (:k, :co, :t, :i, :tk) ON CONFLICT (key) DO NOTHING""",
            k=lk["key"],
            co=holding_id,
            t=lk["title_fa"],
            i=lk["inverse_fa"],
            tk=list(lk["to_kinds"]),
        )
    rr_ref: dict[str, str] = {}
    for rr in (_load("retention.yaml") or {}).get("retention") or []:
        got = await tx.first(
            "SELECT ref FROM archive.retention_rules WHERE seed_key = :s", s=rr["seed_key"]
        )
        if got is None:
            got = await tx.one(
                """INSERT INTO archive.retention_rules (company_id, seed_key, title_fa, trigger, keep, then_do)
                   VALUES (:co, :sk, :t, :tr, CAST(:k AS jsonb), :th) RETURNING ref""",
                co=holding_id,
                sk=rr["seed_key"],
                t=rr["title_fa"],
                tr=rr["trigger"],
                k=dumps(rr["keep"]),
                th=rr["then"],
            )
            added["retention"] += 1
        rr_ref[rr["seed_key"]] = got["ref"]
    for cl in (_load("classes.yaml") or {}).get("classes") or []:
        if await class_row(tx, cl["key"]):
            continue
        fields = [
            {"required": False, "searchable": False, "sensitive": False, "status": "active", **f}
            for f in cl.get("fields") or []
        ]
        spec = {
            "title_fa": cl["title_fa"],
            "parent": cl.get("parent"),
            "scopes": cl.get("scopes", "all"),
            "icon": cl.get("icon", "folder"),
            "default_level": cl.get("default_level", "internal"),
            "default_folder": None,
            "required_files": int(cl.get("required_files", 0)),
            "allowed_mime": list(cl.get("allowed_mime") or V.MIMES),
            "ocr": bool(cl.get("ocr", True)),
            "retention": rr_ref.get(cl.get("retention") or ""),
            "reminder_fields": list(cl.get("reminder_fields") or []),
            "auto_link": list(cl.get("auto_link") or []),
        }
        await apply(tx, seeder, "classes", cl["key"], {"spec": spec, "fields": fields}, None)
        added["classes"] += 1
    for rm in (_load("reminders.yaml") or {}).get("reminders") or []:
        if await tx.scalar(
            "SELECT 1 FROM archive.reminder_rules WHERE seed_key = :s", s=rm["seed_key"]
        ):
            continue
        if not await class_row(tx, rm["class"]):
            continue
        await tx.exec(
            """INSERT INTO archive.reminder_rules (company_id, seed_key, class_key, field, lead_days, to_whom, channel)
               VALUES (:co, :sk, :c, :f, :ld, CAST(:to AS jsonb), :ch)""",
            co=holding_id,
            sk=rm["seed_key"],
            c=rm["class"],
            f=rm["field"],
            ld=sorted(rm["lead_days"], reverse=True),
            to=dumps(rm.get("to", "owner")),
            ch=rm.get("channel", "cartable"),
        )
        added["reminders"] += 1
    for cl in (_load("clearance.yaml") or {}).get("clearance") or []:
        added["clearance"] += await tx.exec(
            """INSERT INTO archive.clearance (subject, company_id, grants, metadata_level)
               VALUES (:s, :co, CAST(:g AS jsonb), :m) ON CONFLICT (subject) DO NOTHING""",
            s=cl["subject"],
            co=holding_id,
            g=dumps(cl.get("grants") or []),
            m=cl.get("metadata_level"),
        )
    for src in (_load("sources.yaml") or {}).get("sources") or []:
        if src["key"] not in V.SOURCES or not await class_row(tx, src["class"]):
            continue
        added["sources"] += await tx.exec(
            """INSERT INTO archive.sources (key, company_id, title_fa, class_key)
               VALUES (:k, :co, :t, :c) ON CONFLICT (key) DO NOTHING""",
            k=src["key"],
            co=holding_id,
            t=src["title_fa"],
            c=src["class"],
        )
    for co in await tx.all("SELECT id, code FROM core.companies ORDER BY code"):
        added["folders"] += await seed_folders(tx, co["id"], co["code"])
    return added


async def seed_folders(tx: Tx, company_id: Any, code: str) -> int:
    """The file plan of one scope (the holding or a company), once."""
    data = _load("folders.yaml") or {}
    n = 0
    for f in data.get("folders") or []:
        n += await tx.exec(
            """INSERT INTO archive.folders (company_id, seed_key, title_fa, classes, sort)
               SELECT :co, :sk, :t, CAST(:cl AS text[]), :s
               WHERE NOT EXISTS (SELECT 1 FROM archive.folders WHERE seed_key = :sk)
               ON CONFLICT (seed_key) DO NOTHING""",
            co=company_id,
            sk=f"{code.lower()}:{f['key']}",
            t=f["title_fa"],
            cl=list(f.get("classes") or []),
            s=int(f.get("order", 100)),
        )
    return n
