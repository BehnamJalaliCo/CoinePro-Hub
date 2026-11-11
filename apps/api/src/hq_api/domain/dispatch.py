"""The holding's secretary (dispatcher, chief of staff; contract §29.4).

One order of the owner becomes one `Route`: the companies (the first holds
the root work, the others are collaborators with a child work each), the
department that owns the output, the output kind and how many, the budget,
single or council, the player, one line for the owner (`preview_fa`), how
sure the secretary is and why.

Rules first (seed/order_rules.yaml, data):
  - the secretary's memory (owner.dispatch_memory) is read first: the
    owner's corrections of an earlier preview of a like order win;
  - companies by their names (code, name_fa, name_en, the yaml's aliases), in
    the order the order names them (a longer name beats one inside it);
  - a person named by title (مدیر فنی …) is who receives it; else the
    department that owns the output (a reel to the media director, never AI
    operations: finding 1 of prompt 20); else a department word; ⟨2026-11-06⟩ an
    automation («اتوماسیون», «n8n») goes to the CEO (the holding's: AI
    operations) before any output or department word;
  - the output kind and its count («۳ ریلز»); the budget from the kind's
    table (`budgets`);
  - questions: an inside one (servers, data, code, real figures) goes to the
    company's own Claude on its server when one is online (§29.8, a capped
    claude job); an outside one (market, competitors, ideas, SEO, ads,
    pricing) to the council; any other to the advisor;
  - `mode` is `single` unless the owner says «شورا» or the order is an
    outside question (finding 4 of prompt 20).
Then ONE light-model call (the existing order_routing path, through the
worker and the LLM Router) only when the rules leave the company or the
department open; its answer is checked against the directory and may not
choose a `model_never` department by itself.

`remember(tx, kind, text_fa, data)` writes the memory: the owner's
corrections (here) and every «نه» reason of the home's cards (§29.13, called
by the home's code).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field

from hq_api.db import Tx
from hq_api.domain import humanize
from hq_api.domain import kits as KT
from hq_api.domain import orders as O
from hq_api.domain import players as PL
from hq_api.errors import ApiError
from hq_api.schemas import Model

OUTPUT_KINDS = ("post", "reel", "story", "article", "report", "plan", "code", "answer", "other")
OutputKind = Literal[
    "post", "reel", "story", "article", "report", "plan", "code", "answer", "other"
]
RouteKind = Literal["work", "code", "meeting", "question", "server", "kit"]
Player = Literal["auto", "claude", "gpt", "gemini", "deepseek"]
OUTPUT_FA = {
    "post": "پست",
    "reel": "ریلز",
    "story": "استوری",
    "article": "مقاله",
    "report": "گزارش",
    "plan": "برنامه",
    "code": "کار کد",
    "answer": "پاسخ",
    "other": "کار",
}
MEMORY_KINDS = ("correction", "no")
# the fields of a route the owner may correct (and the memory remembers)
CORRECTABLE = ("companies", "department", "collaborators", "output_kind", "mode", "player", "kind")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ARABIC_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})


class Route(Model):
    """§29.4 `Route`. ⟨additive⟩ `kind`: how the order is carried out (work for
    a department or the CEO; code for the workshop; meeting; question for the
    advisor or, with mode council, the council; server for the company's own
    Claude on its server)."""

    companies: list[str] = Field(min_length=1, max_length=10)
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    collaborators: list[str] = Field(default_factory=list, max_length=10)
    output_kind: OutputKind = "other"
    count: int | None = Field(default=None, ge=1, le=100)
    budget_tokens: int = Field(default=200_000, ge=10_000, le=10_000_000)
    mode: Literal["single", "council"] = "single"
    player: Player = "auto"
    preview_fa: str = Field(default="", max_length=600)
    confidence: float = Field(default=1.0, ge=0, le=1)
    why_fa: str = Field(default="", max_length=1000)
    kind: RouteKind = "work"
    # ⟨additive⟩ §31.2 kind `kit`: the draft of a new company; nothing is made before the seal
    kit: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    kit_name_fa: str | None = Field(default=None, max_length=200)


@dataclass
class Draft:
    """What the rules (and the memory, then the model) found."""

    kind: str = "work"
    companies: list[str] = field(default_factory=list)
    department: str | None = None
    department_open: bool = True  # nothing decided the department (the CEO by default)
    output_kind: str = "other"
    count: int | None = None
    mode: str = "single"
    player: str = "auto"
    confidence: float = 0.0
    why: list[str] = field(default_factory=list)
    by: str = "rules"  # rules | model | advisor (owner.orders.routed_by)
    remembered: bool = False
    workspace: str | None = None  # the model's workspace of a code order
    kit: str | None = None  # §31.2 the kit of «یک شرکت تازه …»
    kit_name_fa: str | None = None
    automation: bool = False  # ⟨2026-11-06⟩ an automation order: the CEO's (the holding's: AIOPS)

    def open(self) -> bool:
        """The rules left the company (work, code, meeting) or the department
        (work) open: the light model is asked once."""
        if self.kind not in ("work", "code", "meeting"):
            return False
        return not self.companies or (self.kind == "work" and self.department_open)


# ------------------------------------------------------------------ data --
def rules() -> dict[str, Any]:
    return O.rules()


def _words(key: str) -> dict[str, list[str]]:
    raw = rules().get(key) or {}
    return {str(k): [str(w) for w in v or []] for k, v in raw.items()}


def _pos(norm: str, phrase: str) -> int | None:
    """Where a whole-word phrase starts in the normalised text, or None."""
    p = O.normalise(phrase)
    if not p:
        return None
    i = f" {norm} ".find(f" {p} ")
    return None if i < 0 else i


def companies_in_order(norm: str, d: dict[str, Any]) -> list[str]:
    """The companies the order names, in the order it names them; a name
    inside a longer name of another company does not count («آی جی هاب» is
    IG-Hub, not also the holding's «هاب»)."""
    extra = rules().get("companies") or {}
    spans: list[tuple[int, int, str]] = []
    for code, c in d["companies"].items():
        names = [code, c["name_fa"] or "", c["name_en"] or "", *(extra.get(code) or [])]
        for n in names:
            p = O.normalise(str(n))
            if not p:
                continue
            start = 0
            hay = f" {norm} "
            while (i := hay.find(f" {p} ", start)) >= 0:
                spans.append((i, i + len(p), code))
                start = i + 1
    kept = [
        s
        for s in spans
        if not any(
            o[2] != s[2] and o[0] <= s[0] and s[1] <= o[1] and (o[1] - o[0]) > (s[1] - s[0])
            for o in spans
        )
    ]
    first: dict[str, int] = {}
    for start, _, code in kept:
        first[code] = min(start, first.get(code, start))
    return sorted(first, key=lambda c: first[c])


def output_of(norm: str) -> tuple[str, int | None, str | None]:
    """(output kind, count, the word found) by the rules' `outputs`, first
    kind of the list wins."""
    numbers = {O.normalise(str(k)): int(v) for k, v in (rules().get("numbers") or {}).items()}
    digits = norm.translate(_DIGITS)
    for kind, words in _words("outputs").items():
        for w in sorted(words, key=len, reverse=True):
            p = O.normalise(w)
            if _pos(norm, w) is None:
                continue
            m = re.search(
                rf"(?:^|\s)(\d{{1,3}}|\S+)\s+(?:تا\s+|عدد\s+)?{re.escape(p)}(?:\s|$)", digits
            )
            count = None
            if m:
                tok = m.group(1)
                count = int(tok) if tok.isdigit() else numbers.get(tok)
            return kind, count if count and count > 0 else None, w
    return "other", None, None


def _phrase_re(phrase: str) -> str:
    """A rule phrase as a pattern that also matches its ZWNJ spellings."""
    return r"[\s\u200c]*".join(re.escape(t) for t in O.normalise(phrase).split())


def kit_of(text: str, norm: str) -> tuple[str, str | None] | None:
    """§31.2 (kit, the company's name as said) when the order asks for a new
    company («یک شرکت تازه برای … بساز»), by the rules' `kit` (no model)."""
    spec = rules().get("kit") or {}
    triggers = [str(w) for w in spec.get("triggers") or []]
    if not any(_pos(norm, w) is not None for w in triggers):
        return None
    known = KT.kits()
    scored = [
        (sum(_pos(norm, w) is not None for w in words or []), -i, str(key))
        for i, (key, words) in enumerate((spec.get("kits") or {}).items())
        if str(key) in known
    ]
    best = max(scored, default=(0, 0, ""))
    key = best[2] if best[0] > 0 else str(spec.get("default") or "")
    if key not in known:
        return None
    light = text.translate(_ARABIC_LETTERS)
    start = "|".join(_phrase_re(w) for w in triggers)
    end = "|".join(_phrase_re(w) for w in spec.get("make") or [])
    m = re.search(rf"(?:{start})[\s\u200c]*(.*)", light, flags=re.S)
    name = None
    if m:
        part = (
            re.split(rf"(?:^|[\s\u200c])(?:{end})(?=$|[\s\u200c.،!؟?])", m.group(1))[0]
            if end
            else m.group(1)
        )
        part = re.sub(r"^\s*(?:برای|به نام|با نام|به اسم)\s+", "", part.strip())
        part = re.sub(r"[«»\"']", " ", part)
        part = re.sub(r"(?:\s|‌)+را\s*$", "", part.strip())
        part = part.strip(" \t\n.،:؛!؟?")
        name = " ".join(part.split())[:200] or None
        if name is not None and len(name) < 2:
            name = None
    return key, name


def is_automation(norm: str) -> bool:
    """⟨2026-11-06⟩ the order asks for an automation (the rules' `automation.words`), not one
    that only says how a production runs («اتوماسیون شده»: a word of `not_before` after it)."""
    a = rules().get("automation") or {}
    after = {O.normalise(str(x)) for x in a.get("not_before") or []}
    hay = f" {norm} "
    for w in a.get("words") or []:
        p = O.normalise(str(w))
        start = 0
        while p and (i := hay.find(f" {p} ", start)) >= 0:
            rest = hay[i + len(p) + 2 :].split()
            if not rest or rest[0] not in after:
                return True
            start = i + 1
    return False


def automation_department(company: str | None, d: dict[str, Any]) -> str | None:
    """Who receives an automation order: the company's CEO (None); the holding has none, so its
    `holding_department` (AI operations)."""
    if company is None or company != O.holding_code(d):
        return None
    dept = (rules().get("automation") or {}).get("holding_department")
    return str(dept) if dept else None


def question_scope(norm: str) -> str | None:
    """inside | outside | None by the rules' `questions` (inside wins)."""
    q = _words("questions")
    if any(_pos(norm, w) is not None for w in q.get("inside", [])):
        return "inside"
    if any(_pos(norm, w) is not None for w in q.get("outside", [])):
        return "outside"
    return None


def budget_of(kind: str, count: int | None) -> int:
    table = rules().get("budgets") or {}
    row = table.get(kind) or table.get("other") or {"base": 200_000}
    base = int(row.get("base", 200_000))
    extra = int(row.get("per_extra", 0)) * max(0, (count or 1) - 1)
    return min(base + extra, int(row.get("max", base + extra)))


def base_budget(kind: str) -> int:
    return budget_of(kind, 1)


# ---------------------------------------------------------------- memory --
def similarity(a: str, b: str) -> float:
    """The share of words two normalised texts share (Jaccard)."""
    x, y = set(a.split()), set(b.split())
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


async def remember(tx: Tx, kind: str, text_fa: str, data: dict[str, Any] | None = None,
                   *, order_ref: str | None = None) -> None:  # fmt: skip
    """§29.4 the secretary's memory: `correction` (the owner changed a
    preview: data {from, to}) or `no` (a «نه» reason of a home card: data
    {suggestion, company, reason_fa, ...}). The holding's, append-only."""
    if kind not in MEMORY_KINDS:
        raise ValueError(f"unknown memory kind {kind}")
    text = " ".join(str(text_fa or "").split())[:10000] or "-"
    await tx.exec(
        """INSERT INTO owner.dispatch_memory (company_id, kind, text_fa, norm, data, order_ref)
           VALUES ((SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1), :k, :t, :n,
                   CAST(:d AS jsonb), :o)""",
        k=kind,
        t=text,
        n=O.normalise(text)[:10000],
        d=json.dumps(data or {}, ensure_ascii=False, default=str),
        o=order_ref,
    )


async def recall(tx: Tx, kind: str, text: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """The remembered rows of `kind` like `text` (most alike first, then newest)."""
    mem = rules().get("memory") or {}
    floor = float(mem.get("similarity", 0.6))
    rows = await tx.all(
        """SELECT text_fa, norm, data, order_ref, created_at FROM owner.dispatch_memory
           WHERE kind = :k ORDER BY created_at DESC LIMIT :n""",
        k=kind,
        n=int(limit or mem.get("look_back", 200)),
    )
    norm = O.normalise(text)
    hits = [(similarity(norm, r["norm"]), i, r) for i, r in enumerate(rows)]
    return [dict(r) for s, _, r in sorted(hits, key=lambda h: (-h[0], h[1])) if s >= floor]


# ----------------------------------------------------------------- rules --
def by_rules(
    text: str,
    d: dict[str, Any],
    hint: str | None,
    *,
    online: set[str] | frozenset[str] = frozenset(),
    memory: dict[str, Any] | None = None,
) -> Draft:
    """The secretary's rules (no model). `online`: the companies with a
    paired server online; `memory`: the `to` of a remembered correction."""
    norm = O.normalise(text)
    dr = Draft()
    kind = O.kind_of(norm, text)
    if kind == "work" and (made := kit_of(text, norm)) is not None:
        return kit_draft(dr, made, d)
    named = companies_in_order(norm, d)
    if not named and hint in d["companies"]:
        named = [str(hint)]
        dr.why.append("شرکت از انتخاب تو در اپ")
    elif named:
        dr.why.append("شرکت از نام آن در متن")
    dr.companies = named
    dr.output_kind, dr.count, _word = output_of(norm)
    player, mode = PL.from_voice(text)
    dr.player, dr.mode = player or "auto", mode or "single"
    if mode == "council":
        dr.why.append("شورا چون خودت گفتی")
    titled = O.roles_addressed(norm)
    roles = [r for r in O.roles_named(norm) if r not in ("ceo", "advisor")]
    if kind == "question" and len(named) == 1 and titled and titled[0] != "advisor":
        kind = "work"  # a role named outright receives it (06.1 §2)
    scope = question_scope(norm) if kind == "question" else None
    if kind == "question":
        dr.output_kind, dr.count = "answer", None
        if scope == "inside" and named and named[0] in online:
            kind = "server"
            dr.mode = "single"
            dr.why.append("پرسش درباره‌ی داده و کار داخلی شرکت است؛ Claude سرور خود شرکت جواب میدهد")
        elif scope == "outside" or dr.mode == "council":
            dr.mode = "council"
            dr.output_kind = "plan"
            if scope == "outside":
                dr.why.append("پرسش بیرونی است (بازار، رقبا، ایده، تبلیغ)؛ شورای مشاوران")
        else:
            dr.why.append("پرسش است؛ مشاور هلدینگ جواب میدهد")
        dr.department_open = False
    elif kind == "code":
        dr.output_kind = "code"
        dr.department, dr.department_open = "TECH", False
        dr.why.append("کار کد است")
    elif kind == "meeting":
        dr.department_open = False
        dr.why.append("جلسه با مدیرعامل")
    else:
        owners = {str(k): str(v) for k, v in (rules().get("output_department") or {}).items()}
        if titled and titled[0] not in ("ceo", "advisor"):
            dr.department, dr.department_open = titled[0], False
            dr.why.append("مدیر را خودت نام بردی")
        elif titled and titled[0] == "ceo":
            dr.department_open = False
            dr.why.append("مدیرعامل را خودت نام بردی")
        elif is_automation(norm):
            # ⟨2026-11-06⟩ never a production department by a stray word: the CEO proposes it
            dr.automation = True
            dr.department = automation_department(named[0] if named else None, d)
            dr.department_open = False
            dr.output_kind, dr.count = "other", None
            dr.why.append("کار خودکارسازی است و پیشنهادش با مدیرعامل است")
        elif dr.output_kind in owners:
            dr.department, dr.department_open = owners[dr.output_kind], False
            dr.why.append(f"خروجی {OUTPUT_FA[dr.output_kind]} است و کار همان بخش است")
        elif roles:
            dr.department, dr.department_open = roles[0], False
            dr.why.append("بخش از واژه‌های متن")
    dr.kind = kind
    if memory:
        apply_memory(dr, memory)
    dr.confidence = confidence(dr)
    return dr


def kit_draft(dr: Draft, made: tuple[str, str | None], d: dict[str, Any]) -> Draft:
    """§31.2 a new company is asked for: a kit preview in the order report, no
    work item and no company until the owner seals. It sits in the holding."""
    dr.kind, dr.kit, dr.kit_name_fa = "kit", made[0], made[1]
    dr.companies = [O.holding_code(d)]
    dr.department, dr.department_open = None, False
    dr.output_kind, dr.count = "other", None
    dr.why = ["شرکت تازه خواستی؛ پیش‌نمایش ساخته شد و تا مُهر تو چیزی ساخته نمیشود"]
    dr.confidence = confidence(dr)
    return dr


def apply_memory(dr: Draft, to: dict[str, Any]) -> None:
    """A remembered correction of a like order wins over the rules."""
    if to.get("companies"):
        dr.companies = [str(c) for c in to["companies"]]
    if "department" in to:
        dr.department = to["department"]
        dr.department_open = False
    if to.get("output_kind") in OUTPUT_KINDS:
        dr.output_kind = str(to["output_kind"])
    for key in ("mode", "player", "kind"):
        if to.get(key):
            setattr(dr, key, str(to[key]))
    if to.get("collaborators"):
        dr.companies = list(dict.fromkeys([*dr.companies, *map(str, to["collaborators"])]))
    dr.remembered = True
    dr.why.insert(0, "مثل اصلاح قبلی تو برای فرمانی شبیه همین")


def confidence(dr: Draft) -> float:
    if dr.remembered:
        return 0.95
    if dr.by == "model":
        return 0.7
    if dr.by == "advisor":
        return 0.3
    if not dr.companies:
        return 0.4
    if dr.kind in ("question", "server", "code", "meeting", "kit"):
        return 0.85
    return 0.9 if not dr.department_open else 0.6


def apply_model(dr: Draft, routes: list[O.Route], d: dict[str, Any]) -> Draft:
    """The light model's answer, already checked against the directory: it
    fills only what the rules left open (company, department); a
    `model_never` department stays the CEO's."""
    never = {str(x) for x in rules().get("model_never") or []}
    if not routes:
        return dr
    if not dr.companies:
        # nothing named: the model's first route says where and how (a code
        # route acts on its own only when a rule agrees, 06.1 §3)
        lead = routes[0]
        dr.kind = lead.kind
        dr.companies = list(dict.fromkeys(r.company for r in routes if r.kind == lead.kind))
        dr.why.append("شرکت و مسیر را مدل سبک از متن فهمید")
        if lead.kind == "code":
            dr.output_kind, dr.workspace = "code", lead.workspace
        elif lead.kind == "question":
            dr.output_kind, dr.count, dr.mode = "answer", None, "single"
        elif (
            lead.kind == "work"
            and dr.department_open
            and lead.department
            and lead.department not in never
        ):
            dr.department = lead.department
        dr.department_open = False
    else:
        first = next((r for r in routes if r.company == dr.companies[0] and r.kind == "work"), None)
        if dr.department_open and first is not None:
            if first.department and first.department not in never:
                dr.department = first.department
                dr.why.append("بخش را مدل سبک از متن فهمید")
            dr.department_open = False
    dr.by = "model"
    dr.confidence = confidence(dr)
    return dr


# ----------------------------------------------------------- the route --
def complete(dr: Draft, d: dict[str, Any], names: dict[str, dict[str, str]]) -> Route:
    """The Route of a draft: the budget from the kind's table, the line for
    the owner (`preview_fa`) and the why, both plain Persian."""
    companies = list(dict.fromkeys(dr.companies))
    if dr.kind == "question" and dr.mode != "council":
        adv = d.get("advisor") or {}
        companies = companies[:1] or [adv.get("company") or O.holding_code(d)]
    if not companies:
        companies = [O.holding_code(d)]
    if dr.automation and dr.kind == "work" and not dr.department:
        dr.department = automation_department(companies[0], d)  # the model chose the holding
    if dr.department and dr.department not in (names.get(companies[0]) or {}):
        dr.department = None  # the company has no such department: its CEO
    collaborators = companies[1:] if dr.kind == "work" else []
    route = Route(
        companies=companies,
        department=dr.department,
        collaborators=collaborators,
        output_kind=dr.output_kind,
        count=dr.count,
        budget_tokens=budget_of(dr.output_kind, dr.count),
        mode="council" if dr.mode == "council" else "single",
        player=dr.player if dr.player in PL.PLAYERS else "auto",
        confidence=round(min(max(dr.confidence, 0.0), 1.0), 2),
        why_fa=humanize.humanize("؛ ".join(dict.fromkeys(dr.why)) or "قاعده‌ی پیش‌فرض"),
        kind=dr.kind,
        kit=dr.kit if dr.kind == "kit" else None,
        kit_name_fa=dr.kit_name_fa if dr.kind == "kit" else None,
    )
    route.preview_fa = preview_line(route, d, names)
    return route


def _co_fa(code: str, d: dict[str, Any]) -> str:
    c = d["companies"].get(code) or {}
    return str(c.get("name_fa") or c.get("name_en") or code)


def _dept_fa(code: str, dept: str | None, names: dict[str, dict[str, str]]) -> str:
    if not dept:
        return "مدیرعامل"
    return (names.get(code) or {}).get(dept) or dept


def preview_line(r: Route, d: dict[str, Any], names: dict[str, dict[str, str]]) -> str:
    """«→ تریدیار/رسانه + IG-Hub/رسانه؛ خروجی: 3 ریلز؛ بودجه: 400 هزار توکن»."""
    first = r.companies[0]
    if r.kind == "kit":
        title = (KT.kits().get(r.kit or "") or {}).get("title_fa") or "شرکت تازه"
        name = f"؛ نام: {r.kit_name_fa}" if r.kit_name_fa else ""
        return humanize.humanize(
            f"→ شرکت تازه از روی «{title}»{name}؛ تا مُهر نکنی چیزی ساخته نمیشود"
        )
    if r.kind == "question" and r.mode == "single":
        head = "مشاور هلدینگ"
    elif r.kind == "server":
        head = f"{_co_fa(first, d)}/Claude سرور خود شرکت"
    elif r.kind == "code":
        head = f"{_co_fa(first, d)}/کارگاه کد"
    elif r.kind == "question":
        head = f"{_co_fa(first, d)}/شورای مشاوران"
    else:
        head = f"{_co_fa(first, d)}/{_dept_fa(first, r.department, names)}"
        for c in r.collaborators:
            dept = r.department if r.department in (names.get(c) or {}) else None
            head += f" + {_co_fa(c, d)}/{_dept_fa(c, dept, names)}"
    out = OUTPUT_FA.get(r.output_kind, "کار")
    # ⟨2026-11-08⟩ no «بودجه: …» line: an owner's order has no token cap (budget_tokens is the
    # secretary's estimate of the work, kept for the apps that show it)
    parts = [
        f"→ {head}",
        f"خروجی: {r.count} {out}" if r.count else f"خروجی: {out}",
    ]
    if r.mode == "council":
        parts.append("با شورا")
    if r.player != "auto":
        parts.append(f"با {PL.PLAYER_FA.get(r.player, r.player)}")
    return humanize.humanize("؛ ".join(parts))


# --------------------------------------------------------- the database --
async def department_names(tx: Tx) -> dict[str, dict[str, str]]:
    """{company code: {department code: its Persian name}}."""
    out: dict[str, dict[str, str]] = {}
    for r in await tx.all(
        """SELECT c.code AS company, d.code, d.name_fa FROM core.departments d
           JOIN core.companies c ON c.id = d.company_id ORDER BY c.code, d.code"""
    ):
        out.setdefault(r["company"], {})[r["code"]] = r["name_fa"] or r["code"]
    return out


async def online_companies(tx: Tx) -> dict[str, dict[str, Any]]:
    """{company code: its first paired server that is online}."""
    from hq_api.domain import servers as SV

    out: dict[str, dict[str, Any]] = {}
    for s in await tx.all(
        SV.SERVER_SQL
        + " WHERE s.origin = 'attached' AND s.state = 'online' ORDER BY c.code, s.name"
    ):
        if SV.state_of(s) == "online":
            out.setdefault(s["company"], dict(s))
    return out


async def remembered_route(tx: Tx, text: str) -> dict[str, Any] | None:
    """The `to` of the most alike remembered correction, or None."""
    for row in await recall(tx, "correction", text):
        data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"] or "{}")
        to = data.get("to")
        if isinstance(to, dict) and to:
            return to
    return None


@dataclass
class Context:
    directory: dict[str, Any]
    names: dict[str, dict[str, str]]
    online: dict[str, dict[str, Any]]
    memory: dict[str, Any] | None


async def context(tx: Tx, text: str) -> Context:
    return Context(
        directory=await O.directory(tx),
        names=await department_names(tx),
        online=await online_companies(tx),
        memory=await remembered_route(tx, text),
    )


def check_route(r: Route, ctx: Context) -> Route:
    """An edited route is followed exactly, once it names what exists."""
    d = ctx.directory
    bad = [c for c in [*r.companies, *r.collaborators] if c not in d["companies"]]
    if bad:
        raise ApiError(422, "validation_failed", fields={"route.companies": f"unknown: {bad[0]}"})
    if r.department and r.department not in (ctx.names.get(r.companies[0]) or {}):
        raise ApiError(
            422, "validation_failed", fields={"route.department": "not a department of the company"}
        )
    if r.kind == "kit" and (r.kit or "") not in KT.kits():
        raise ApiError(422, "validation_failed", fields={"route.kit": "unknown kit"})
    if r.kind == "server" and r.companies[0] not in ctx.online:
        raise ApiError(
            422, "validation_failed", fields={"route.kind": "the company has no server online"}
        )
    return r


def corrected(proposed: Draft, given: Route) -> dict[str, Any] | None:
    """What the owner changed of what the rules were sure of: {from, to},
    or None when nothing definite was changed."""
    was: dict[str, Any] = {
        "companies": proposed.companies[:1],
        "collaborators": proposed.companies[1:] if proposed.kind == "work" else [],
        "department": None if proposed.department_open else proposed.department,
        "output_kind": proposed.output_kind,
        "mode": proposed.mode,
        "player": proposed.player,
        "kind": proposed.kind,
    }
    now: dict[str, Any] = {
        "companies": given.companies[:1],
        "collaborators": list(dict.fromkeys([*given.companies[1:], *given.collaborators])),
        "department": given.department,
        "output_kind": given.output_kind,
        "mode": given.mode,
        "player": given.player,
        "kind": given.kind,
    }
    changed = []
    for k in CORRECTABLE:
        if k == "department" and proposed.department_open:
            continue  # the rules were not sure: nothing to correct
        if k == "companies" and not proposed.companies:
            continue
        if was[k] != now[k]:
            changed.append(k)
    if not changed:
        return None
    return {"from": {k: was[k] for k in changed}, "to": {k: now[k] for k in changed}}


# ------------------------------------------- §29.8 an inside question --
SERVER_ACTOR = "secretary"
SERVER_TURNS = 15
SERVER_TIMEOUT_S = 900
SERVER_MIN_TOKENS = 60_000
SERVER_BRIEF = (
    "پرسش مدیر کل هلدینگ درباره‌ی همین شرکت؛ از روی داده و کد واقعی همین سرور جواب بده.\n"
    "- فقط بخوان؛ هیچ چیزی را تغییر نده، پاک نکن و راه‌اندازی دوباره نکن.\n"
    "- هیچ رمز، کلید، توکن یا داده‌ی شخصی را در جواب ننویس.\n"
    "- جواب فارسی و ساده: اول خود جواب در چند خط، بعد اینکه از کجا فهمیدی (فایل، فرمان، جدول)، "
    "و آنچه نتوانستی بسنجی.\n\n"
    "پرسش:\n{text}"
)


async def ask_server(
    tx: Tx, hub: Any, w: dict[str, Any], server: dict[str, Any], text: str, budget: int
) -> dict[str, Any]:
    """The capped claude job of an inside question on the company's own
    server (§26, §28.7 `token_cap`), read-only tools only; its answer becomes
    the work's deliverable (after_server_job)."""
    from hq_api.domain import catalogue
    from hq_api.domain import servers as SV

    cap = max(SERVER_MIN_TOKENS, int(budget))
    return await SV.create_job(
        tx,
        server=server,
        kind="claude",
        args={
            "brief": SERVER_BRIEF.format(text=text),
            "title": f"پرسش مدیر کل: {' '.join(text.split())[:80]}",
            "timeout_s": SERVER_TIMEOUT_S,
            "max_turns": SERVER_TURNS,
            "token_cap": cap,
            "allowed_tools": list(catalogue.ALLOWED_TOOLS),
        },
        actor_kind="service",
        actor_code=SERVER_ACTOR,
        work_ref=w["ref"],
        summary=f"پرسش مدیر کل ({w['ref']})",
        timeout_s=SERVER_TIMEOUT_S,
    )


async def server_job_of(tx: Tx, work_ref: str) -> dict[str, Any] | None:
    """The latest inside-question job of a work, if any."""
    return await tx.first(
        """SELECT j.id, j.state, j.finished_at FROM infra.server_jobs j
           WHERE j.work_ref = :r AND j.kind = 'claude' AND j.actor_kind = 'service'
             AND j.actor_code = :a ORDER BY j.created_at DESC LIMIT 1""",
        r=work_ref,
        a=SERVER_ACTOR,
    )


async def after_server_job(hub: Any, job_id: Any) -> None:
    """A job of an inside question ended (after the runner's commit): its
    answer is the work's deliverable, labelled with the server; a failed job
    leaves the work to its assignee (the worker's sweep queues its run)."""
    from hq_api.domain import servers as SV
    from hq_api.domain import work as W

    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await SV.load_job(tx, job_id)
        if j["actor_code"] != SERVER_ACTOR or not j["work_ref"] or j["state"] not in SV.FINAL:
            return
        w = await tx.first(
            """SELECT w.*, c.code AS company FROM work.work w
               JOIN core.companies c ON c.id = w.company_id WHERE w.ref = :r FOR UPDATE OF w""",
            r=j["work_ref"],
        )
        if w is None or w["status"] not in W.OPEN:
            return
        answer = (await SV.full_answer(tx, hub, j)).strip() if j["state"] == "done" else ""
        if not answer:
            await W.event(tx, w, "server_failed", PL.SERVICE, {"job": str(j["id"])})
            return
        name = await tx.scalar(
            "SELECT name_fa FROM core.companies WHERE id = :id", id=w["company_id"]
        )
        await PL.deliver(
            tx,
            dict(w),
            title=w["title"],
            body=answer,
            produced_with={
                "via": "server",
                "server": j["server_name"],
                "server_job": str(j["id"]),
                "label_fa": f"پاسخ Claude سرور {name or w['company']}",
            },
            hub=hub,
        )
