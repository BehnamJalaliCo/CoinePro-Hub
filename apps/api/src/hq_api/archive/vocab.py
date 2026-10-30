"""The archive's closed vocabulary (contract §23.2, §23.7, §23.8) and the
validation of a record's values against its class version's fields.

Only these lists need code: field types, automation events, actions and
operators, the kinds a `ref` field may name, and the system sources. Adding
to them is a prompt; using them (a class, a field, a rule, an automation) is
data the owner edits in the app.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from hq_api import media

FIELD_TYPES = (
    "text",
    "long_text",
    "number",
    "money",
    "percent",
    "date",
    "date_range",
    "enum",
    "multi_enum",
    "boolean",
    "party",
    "company",
    "ref",
    "url",
    "email",
    "phone",
    "id_code",
    "iban",
)
REF_KINDS = ("decision", "resolution", "case", "work", "record", "employee", "revenue_account")
CURRENCIES = ("USD", "USDT", "EUR", "IRR", "IRT", "AED", "TRY", "GBP", "BTC", "ETH")
EVENTS = ("filed", "sealed", "reminder_due", "retention_due", "hold_set", "version_added")
ACTIONS = ("notify", "work_item", "link", "move_to_folder", "raise_level", "add_reminder")
OPS = ("eq", "lt", "gt", "contains")
NOTIFY_LEVELS = ("info", "report", "decision")  # never urgent (contract §23.7)
SOURCES = (
    "charter_sealed",
    "resolution_month",
    "brand_sealed",
    "founding_registration",
    "legal_email",
    "case_closed",
    "server_plan_sealed",
    "backup_restore_test",
)
# What a record may be linked to (a link kind names a subset).
# ⟨1.7.3⟩ a deliverable filed in the archive is linked `about` itself
LINK_TO_KINDS = (*REF_KINDS, "party", "company", "deliverable")
MIMES = tuple(sorted(media.ALLOWED))
TRIGGERS_FIXED = ("filed", "case_closed", "superseded")
THEN = ("review", "dispose_card")
CHANNELS = ("cartable", "digest")
PARTS = (
    "classes",
    "folders",
    "levels",
    "clearance",
    "retention",
    "reminders",
    "party_kinds",
    "link_kinds",
    "automations",
)
# Parts keyed by a ref the server assigns (created with key `new`).
REF_PARTS = {"folders": "FP", "retention": "RR", "reminders": "RM", "automations": "AU"}

KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
CODE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
EMPLOYEE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$")
REF_PATTERNS = {
    "decision": re.compile(r"^D-[0-9]{6,}$"),
    "resolution": re.compile(r"^M-[0-9]{4,}$"),
    "case": re.compile(r"^LC-[0-9]{4,}$"),
    "work": re.compile(r"^[A-Z][A-Z0-9]{1,9}-W-?[0-9]{1,}$|^W-[0-9]{4,}$|^[A-Z0-9-]{3,40}$"),
    "record": re.compile(r"^AR-[0-9]{6,}$"),
    "employee": EMPLOYEE,
    "revenue_account": re.compile(r"^[A-Za-z0-9_.:-]{2,80}$"),
    "party": re.compile(r"^PT-[0-9]{4,}$"),
    "company": CODE,
    "deliverable": re.compile(r"^O-[0-9]{6,}$"),
}
AMOUNT = re.compile(r"^-?[0-9]{1,18}(\.[0-9]{1,8})?$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
PHONE = re.compile(r"^\+?[0-9][0-9 ()\-]{4,28}$")
ID_CODE = re.compile(r"^[A-Za-z0-9\-/]{2,40}$")
IBAN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$")
URL = re.compile(r"^https?://[^\s<>\"']{1,2000}$", re.I)
MASK_LAST = 4


def _date(v: Any) -> date | None:
    if not isinstance(v, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _amount(v: Any) -> str | None:
    if isinstance(v, bool):
        return None
    s = str(v).strip() if isinstance(v, (int, float, str, Decimal)) else ""
    if not AMOUNT.fullmatch(s):
        return None
    try:
        Decimal(s)
    except InvalidOperation:
        return None
    return s


def check_value(field: dict[str, Any], v: Any) -> tuple[Any, str | None]:
    """(the stored value, None) or (None, the reason) for one field's value."""
    t = field["type"]
    if t in ("text", "long_text"):
        cap = 500 if t == "text" else 20000
        if not isinstance(v, str) or not v.strip() or len(v) > cap:
            return None, f"text of 1-{cap} characters"
        return v.strip(), None
    if t in ("number", "percent"):
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            return None, "a number"
        s = _amount(v)
        if s is None:
            return None, "a number"
        if t == "percent" and not (Decimal(0) <= Decimal(s) <= Decimal(100)):
            return None, "a percent between 0 and 100"
        n = Decimal(s)
        return (int(n) if n == n.to_integral_value() and "." not in s else float(n)), None
    if t == "money":
        if not isinstance(v, dict) or set(v) - {"amount", "currency"}:
            return None, "{amount, currency}"
        amount, cur = _amount(v.get("amount")), v.get("currency")
        if amount is None:
            return None, "amount: a decimal string"
        allowed = [field["currency"]] if field.get("currency") else list(CURRENCIES)
        if cur not in allowed:
            return None, f"currency: one of {', '.join(allowed)}"
        return {"amount": amount, "currency": cur}, None
    if t == "date":
        d = _date(v)
        return (v, None) if d else (None, "a date YYYY-MM-DD")
    if t == "date_range":
        if not isinstance(v, dict) or set(v) - {"from", "to"}:
            return None, "{from, to}"
        a, b = _date(v.get("from")), _date(v.get("to"))
        if a is None or b is None or a > b:
            return None, "{from, to}: two dates, from <= to"
        return {"from": v["from"], "to": v["to"]}, None
    if t == "enum":
        keys = [o["key"] for o in field.get("options") or []]
        return (v, None) if v in keys else (None, f"one of {', '.join(keys)}")
    if t == "multi_enum":
        keys = [o["key"] for o in field.get("options") or []]
        if not isinstance(v, list) or not all(x in keys for x in v) or len(set(v)) != len(v):
            return None, f"a list of {', '.join(keys)}"
        return list(v), None
    if t == "boolean":
        return (v, None) if isinstance(v, bool) else (None, "true or false")
    if t == "party":
        ok = isinstance(v, str) and REF_PATTERNS["party"].fullmatch(v)
        return (v, None) if ok else (None, "a party ref PT-…")
    if t == "company":
        ok = isinstance(v, str) and CODE.fullmatch(v)
        return (v, None) if ok else (None, "a company code")
    if t == "ref":
        kinds = field.get("ref_kinds") or list(REF_KINDS)
        if not isinstance(v, dict) or set(v) != {"kind", "ref"} or v["kind"] not in kinds:
            return None, f"{{kind, ref}} with kind one of {', '.join(kinds)}"
        pat = REF_PATTERNS.get(v["kind"])
        if not isinstance(v["ref"], str) or pat is None or not pat.fullmatch(v["ref"]):
            return None, f"not a {v['kind']} ref"
        return {"kind": v["kind"], "ref": v["ref"]}, None
    if t == "url":
        ok = isinstance(v, str) and URL.fullmatch(v.strip())
        return (v.strip(), None) if ok else (None, "an http(s) URL")
    if t == "email":
        ok = isinstance(v, str) and EMAIL.fullmatch(v.strip())
        return (v.strip().lower(), None) if ok else (None, "an email address")
    if t == "phone":
        ok = isinstance(v, str) and PHONE.fullmatch(v.strip())
        return (v.strip(), None) if ok else (None, "a phone number")
    if t == "id_code":
        s = v.strip() if isinstance(v, str) else ""
        return (s, None) if ID_CODE.fullmatch(s) else (None, "an identifier")
    if t == "iban":
        s = re.sub(r"[\s-]", "", v).upper() if isinstance(v, str) else ""
        return (s, None) if IBAN.fullmatch(s) else (None, "an IBAN (IR + 24 digits)")
    return None, f"unknown type {t}"


def validate_metadata(
    fields: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    complete: bool,
    keep: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Values against the class version's fields -> (clean values, missing
    required keys, errors). A retired field keeps the value an old record
    already has (`keep`), but takes no new one; an unknown key is an error.
    `complete`: a filed record needs every active required field."""
    by_key = {f["key"]: f for f in fields}
    keep = keep or {}
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for k, v in metadata.items():
        f = by_key.get(k)
        if f is None:
            errors[f"metadata.{k}"] = "not a field of this class"
            continue
        if v is None:
            continue
        if f.get("status") == "retired":
            if k in keep and keep[k] == v:
                out[k] = v
            else:
                errors[f"metadata.{k}"] = "retired: it keeps old values only"
            continue
        clean, why = check_value(f, v)
        if why is not None:
            errors[f"metadata.{k}"] = why
        else:
            out[k] = clean
    for k, v in keep.items():  # retired values an old record keeps
        f = by_key.get(k)
        if k not in metadata and f is not None and f.get("status") == "retired":
            out[k] = v
    missing = [
        f["key"]
        for f in fields
        if f.get("required") and f.get("status", "active") == "active" and f["key"] not in out
    ]
    if complete:
        for k in missing:
            errors.setdefault(f"metadata.{k}", "required")
    return out, missing, errors


def masked(v: Any) -> str:
    s = str(v)
    return "•" * max(len(s) - MASK_LAST, 0) + s[-MASK_LAST:] if len(s) > MASK_LAST else "•" * len(s)


def mask_metadata(
    fields: list[dict[str, Any]], metadata: dict[str, Any], *, agent: bool, full: bool
) -> tuple[dict[str, Any], list[str]]:
    """What a reader is shown: `id_code` and `iban` to the last 4 for every
    agent; a `sensitive` field hidden below `confidential` (`full`: the
    reader's clearance in this scope reaches `confidential`)."""
    by_key = {f["key"]: f for f in fields}
    out: dict[str, Any] = {}
    hidden: list[str] = []
    for k, v in metadata.items():
        f = by_key.get(k) or {}
        if f.get("type") in ("id_code", "iban") and (agent or not full):
            out[k] = masked(v)
            hidden.append(k)
        elif f.get("sensitive") and not full:
            out[k] = None
            hidden.append(k)
        else:
            out[k] = v
    return out, sorted(hidden)


def field_dates(field: dict[str, Any] | None, v: Any) -> date | None:
    """The date a reminder or a retention trigger reads from a value: a date,
    or a date range's end."""
    if field is None or v is None:
        return None
    if field.get("type") == "date":
        return _date(v)
    if field.get("type") == "date_range" and isinstance(v, dict):
        return _date(v.get("to"))
    return None


def search_words(fields: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[str, str]:
    """(searchable text, sensitive searchable text) of a record's values."""
    plain: list[str] = []
    sens: list[str] = []
    by_key = {f["key"]: f for f in fields}
    for k, v in metadata.items():
        f = by_key.get(k)
        if f is None or not f.get("searchable"):
            continue
        if isinstance(v, dict):
            words = " ".join(str(x) for x in v.values())
        elif isinstance(v, list):
            words = " ".join(str(x) for x in v)
        else:
            words = str(v)
        if f.get("sensitive") or f.get("type") in ("id_code", "iban"):
            sens.append(words)
        else:
            plain.append(words)
    return " ".join(plain), " ".join(sens)
