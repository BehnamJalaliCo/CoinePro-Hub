"""The owner's rules (contract §29.3): «این دیگر تکرار نشود» in one sentence,
as a standing order (§18.1, `oversight.orders`, SO-…).

- `POST /rules` writes a `proposed` standing order: the owner's words kept
  (`owner_text`), a precise `text_md` written from them by rules (fillers
  and the «قانون تازه:» lead cut, Arabic letters as Persian, one sentence
  per line), the light model only to make one clear imperative of a long or
  many-sentence text. `applies_to` from the words: a role named -> {roles},
  a company named -> {companies}, «ناظر» -> overseer, else all.
- The owner seals it with one tap (🔏, the existing seal route); a new
  version (PUT /rules/{ref}, 🔏) changes the text in place, the previous one
  kept in `history`; retire stops it from the next run.
- Sealed rules join the system prompt of every role they apply to (the
  runner's «Owner's standing orders» block): `applies(order, kind, role,
  company)` is the one test, `for_run` the query.
- Counts: the runs it applied to since its seal, the findings that name it
  (violations) and how many of those were fixed. The first enforcement
  report goes to the owner 24 hours after the seal (a `report`
  notification, stream `rule.report`), by the worker's tick, no model.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import humanize, notify
from hq_api.domain import orders as O
from hq_api.schemas import Model

REPORT_AFTER = timedelta(hours=24)
APPLIES = ("all", "overseer", "roles", "companies")
# a role word of the owner -> the charter roles it means (data of the rules)
ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "ceo": ("مدیرعامل", "مدیرعامل ها", "مدیر عامل", "مدیران عامل", "ceo"),
    "cto": ("مدیر فنی", "مدیران فنی", "cto"),
    "media_director": ("مدیر رسانه", "مدیر محتوا", "مدیران رسانه"),
    "manager": ("مدیر بخش", "مدیران بخش", "مدیرها", "مدیران"),
    "scriptwriter": ("سناریست", "نویسنده"),
    "publisher": ("مسئول انتشار",),
    "sre": ("sre",),
    "advisor": ("مشاور", "مشاور کل"),
    "assistant": ("دستیار",),
}
OVERSEER_WORDS = ("ناظر", "ناظر کل", "ناظرها", "نظارت")
FILLERS = (
    "لطفا", "لطفاً", "خب", "خوب ببین", "ببین", "یعنی", "اممم", "امم", "دیگه", "حتما", "حتماً",
)  # fmt: skip
LEADS = re.compile(
    r"^\s*(?:قانون(?:\s*تازه)?(?:\s*برای\s*هلدینگ)?|دستور(?:\s*دائمی)?|rule)\s*[:：،-]\s*", re.I
)
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})
_SENTENCES = re.compile(r"(?<=[.!؟?])\s+|\n+")


class AppliesRoles(Model):
    roles: list[str] = Field(min_length=1, max_length=50)


class AppliesCompanies(Model):
    companies: list[str] = Field(min_length=1, max_length=50)


Applies = Literal["all", "overseer"] | AppliesRoles | AppliesCompanies


class RuleCounts(BaseModel):
    runs: int
    violations: int
    fixed: int


class Rule(BaseModel):
    """§29.3: a standing order (§18.1) with its counts and its first report."""

    id: str
    ref: str
    text_md: str
    owner_text: str | None
    source: str
    file_id: str | None
    applies_to: Applies
    status: Literal["proposed", "sealed", "retired"]
    version: int
    sealed_at: datetime | None
    created_at: datetime
    counts: RuleCounts
    report_at: datetime | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------- writing --
def clean(text: str) -> str:
    """The owner's words as a precise rule, by rules: the lead and the fillers
    cut, Arabic letters as Persian, spaces tidied, each sentence closed."""
    t = (text or "").translate(_ARABIC).replace("‏", "")
    t = LEADS.sub("", t)
    for f in sorted(FILLERS, key=len, reverse=True):
        t = re.sub(rf"(?:(?<=\s)|^){re.escape(f)}(?=[\s،,]|$)[،,]?", " ", t)
    sentences = [" ".join(s.split()).strip(" ،,") for s in _SENTENCES.split(t)]
    sentences = [s for s in sentences if s]
    out = [s if s[-1] in ".!؟?" else s + "." for s in sentences]
    return "\n".join(out)[:10000] or " ".join((text or "").split())[:10000]


def needs_model(text_md: str) -> bool:
    """One clear imperative is short and one sentence; else the light model
    is asked to make one (when it is reachable)."""
    return len(text_md.splitlines()) > 1 or len(text_md.split()) > 35


MODEL_SYSTEM = (
    "You rewrite one standing order of the holding's owner (Persian, masked) as ONE clear, "
    "precise Persian imperative sentence that an AI employee can follow and an overseer can check. "
    "Keep every condition and exception; add nothing; no preamble. Answer as JSON "
    '{"routes": [{"text_fa": "<the rule>"}]}.'
)
MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {"text_fa": {"type": "string"}},
                "required": ["text_fa"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}


def model_request(masked_text: str, holding: str) -> dict[str, Any]:
    """The light model's one-imperative rewrite (the worker's order_routing
    path: same light model, its answer under `routes`)."""
    return {
        "company_code": holding,
        "actor_ref": "rules",
        "task_class": O.TASK_CLASS,
        "priority": 1,
        "model": O.MODEL,
        "effort": "low",
        "system": MODEL_SYSTEM,
        "prompt": masked_text,
        "json_schema": MODEL_SCHEMA,
        "max_output_tokens": 600,
        "timeout_s": 40,
        "meta": {"purpose": "rule_text"},
    }


def model_text(answer: dict[str, Any] | None) -> str | None:
    routes = (answer or {}).get("routes")
    if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
        return None
    text = " ".join(str(routes[0].get("text_fa") or "").split())
    return text[:2000] if text and humanize.persian_share(text) >= 0.6 else None


def applies_of(text: str, d: dict[str, Any]) -> tuple[str, list[str]]:
    """(applies_to, codes) from the owner's words."""
    from hq_api.domain import dispatch

    norm = O.normalise(text)
    roles = [r for r, words in ROLE_WORDS.items() if any(O.has(norm, w) for w in words)]
    if roles:
        return "roles", roles
    companies = [
        c for c in dispatch.companies_in_order(norm, d) if not d["companies"][c]["holding"]
    ]
    if companies:
        return "companies", companies
    if any(O.has(norm, w) for w in OVERSEER_WORDS):
        return "overseer", []
    return "all", []


def applies_out(kind: str, codes: list[str] | None) -> Any:
    if kind == "roles":
        return AppliesRoles(roles=list(codes or []))
    if kind == "companies":
        return AppliesCompanies(companies=list(codes or []))
    return kind


def applies_in(value: Any) -> tuple[str, list[str]]:
    if isinstance(value, AppliesRoles):
        return "roles", list(dict.fromkeys(value.roles))
    if isinstance(value, AppliesCompanies):
        return "companies", list(dict.fromkeys(value.companies))
    return str(value), []


# ------------------------------------------------------------ who it binds --
def applies(o: dict[str, Any], kind: str, role: str | None, company: str | None) -> bool:
    """Whether a sealed rule binds a run of this charter kind and role, in
    this company: all; the overseer's own; its roles; its companies."""
    to = o["applies_to"]
    codes = list(o.get("applies_codes") or [])
    if to == "all":
        return True
    if to == "overseer":
        return kind == "overseer"
    if to == "roles":
        return role is not None and role in codes
    if to == "companies":
        return company is not None and company in codes
    return False


async def for_run(
    tx: Tx, kind: str, role: str | None = None, company: str | None = None
) -> list[dict[str, Any]]:
    """The sealed rules a run of this charter kind, role and company obeys
    (oldest seal first); without a role or company only all/overseer rules."""
    rows = await tx.all(
        """SELECT ref, text_md, applies_to, applies_codes FROM oversight.orders
           WHERE status = 'sealed' ORDER BY sealed_at, ref"""
    )
    return [dict(o) for o in rows if applies(o, kind, role, company)]


# ----------------------------------------------------------------- counts --
async def counts(tx: Tx, o: dict[str, Any]) -> RuleCounts:
    """The runs it bound since its seal, the findings that name it, how many
    of those were fixed."""
    runs = 0
    if o.get("sealed_at") is not None:
        runs = int(
            await tx.scalar(
                """SELECT count(*) FROM agents.runs r
                   JOIN core.employees e ON e.id = r.employee_id
                   JOIN core.companies c ON c.id = r.company_id
                   WHERE r.started_at >= :since
                     AND (CAST(:to AS text) = 'all'
                          OR (CAST(:to AS text) = 'overseer' AND e.kind = 'overseer')
                          OR (CAST(:to AS text) = 'roles'
                              AND COALESCE(r.charter_role, e.role) = ANY(CAST(:codes AS text[])))
                          OR (CAST(:to AS text) = 'companies'
                              AND c.code = ANY(CAST(:codes AS text[]))))""",
                since=o["sealed_at"],
                to=o["applies_to"],
                codes=list(o.get("applies_codes") or []),
            )
            or 0
        )
    row = await tx.one(
        """SELECT count(*) AS n,
                  count(*) FILTER (WHERE status IN ('fixed', 'verified', 'closed')) AS fixed
           FROM oversight.findings
           WHERE evidence @> CAST(:ev AS jsonb) OR title_fa LIKE :like OR body_md LIKE :like""",
        ev=json.dumps([{"ref": o["ref"]}]),
        like=f"%{o['ref']}%",
    )
    return RuleCounts(runs=runs, violations=int(row["n"] or 0), fixed=int(row["fixed"] or 0))


async def render(tx: Tx, o: dict[str, Any]) -> Rule:
    return Rule(
        id=str(o["id"]),
        ref=o["ref"],
        text_md=o["text_md"],
        owner_text=o.get("owner_text"),
        source=o["source"],
        file_id=str(o["file_id"]) if o.get("file_id") else None,
        applies_to=applies_out(o["applies_to"], o.get("applies_codes")),
        status=o["status"],
        version=o["version"],
        sealed_at=o["sealed_at"],
        created_at=o["created_at"],
        counts=await counts(tx, o),
        report_at=o.get("report_at"),
        history=list(o.get("history") or []),
    )


# ----------------------------------------------------------------- report --
def report_text(o: dict[str, Any], c: RuleCounts) -> tuple[str, str]:
    """(title, body) of the first enforcement report, plain Persian (§29.7)."""
    rule = humanize.humanize(" ".join(str(o["text_md"]).split()))[:300]
    if c.violations == 0:
        what = f"قانون شما در 24 ساعت اول در {c.runs} اجرای کارمندها رعایت شد و هیچ تخلفی دیده نشد."
    else:
        what = (
            f"قانون شما در 24 ساعت اول در {c.runs} اجرای کارمندها به کار رفت؛ "
            f"{c.violations} تخلف دیده شد و {c.fixed} مورد رفع شد."
        )
    need = None
    if c.violations > c.fixed:
        need = "اگر قانون روشن نیست، متنش را دقیق‌تر کنید؛ ناظر بقیه را پیگیری میکند."
    body = humanize.plain(what, f"قانون: {rule}", need)
    return "نخستین گزارش اجرای قانون شما", body


async def report_due(tx: Tx, now: datetime | None = None) -> int:
    """The worker's tick: the first enforcement report of every rule sealed at
    least 24 hours ago (once per rule). Rule-based, no model."""
    now = now or datetime.now(UTC)
    holding = await tx.first("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    if holding is None:
        return 0
    n = 0
    for o in await tx.all(
        """SELECT * FROM oversight.orders WHERE status = 'sealed' AND report_at IS NULL
             AND sealed_at <= :due ORDER BY sealed_at LIMIT 20 FOR UPDATE SKIP LOCKED""",
        due=now - REPORT_AFTER,
    ):
        c = await counts(tx, o)
        title, body = report_text(o, c)
        await notify.raise_notification(
            tx,
            company_id=holding["id"],
            company_code=holding["code"],
            level="report",
            title_fa=title,
            body_fa=body,
            link_kind="rule",
            link_ref=o["ref"],
            source_kind="system",
            source_code="rules",
        )
        data = {**c.model_dump(), "at": now.isoformat()}
        await tx.exec(
            """UPDATE oversight.orders SET report_at = :at, report = CAST(:r AS jsonb), updated_at = now()
               WHERE id = :id""",
            at=now,
            r=json.dumps(data),
            id=o["id"],
        )
        await events.emit(tx, holding["code"], "rule.report", o["ref"], data)
        n += 1
    return n
