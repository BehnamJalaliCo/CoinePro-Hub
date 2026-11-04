"""The code-only step adapters (contract §30.2): `dedupe`, `quality`, `seal`.
No model and no outside call: each reads the line's and the company's past
outputs (lines.step_runs) and answers by rule.

- dedupe   the input's text against this line's and the company's past texts
           (word 3-shingles, Jaccard); too alike -> StepFailed(retry=True):
           the engine makes the input step again (`reruns_input`), up to the
           dedupe step's own `max_attempts`.
- quality  before publishing: not a repeat, every figure with a source (when
           the step's settings or the owner's sealed rules ask for it),
           Persian, length bounds and banned words from the settings, and the
           platform's rules in data (§31.1, seed/lines/rules.yaml: links,
           financial claims, banned phrases).
- seal     the gate itself is the engine's (a line_publish card, A3); this
           step only records that it was sealed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hq_api.domain import humanize
from hq_api.domain import rules as owner_rules
from hq_api.domain.briefings import numbers_of
from hq_api.lines import learning
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

HISTORY = 300  # past texts compared, newest first
HISTORY_DAYS = 365
TEXT_KINDS = ("gpt_text", "opus_build", "n8n")
_ARABIC = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا"})
_MARKS = re.compile(r"[ً-ٰٟ‌‍]")
_WORD = re.compile(r"[\w]+", re.UNICODE)
ILLUSTRATIVE = re.compile(r"فرض\s*کنید|مثلاً|مثلا|برای\s*مثال|فرضی|به\s*عنوان\s*مثال")
SOURCE_WORDS = ("منبع", "مأخذ", "ماخذ")
LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|ir|net|org|io|me)\b", re.I)


# ------------------------------------------------------------- similarity --
def words(text: str) -> list[str]:
    t = _MARKS.sub("", (text or "").translate(_ARABIC)).lower()
    return _WORD.findall(t)


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    w = words(text)
    if len(w) < n:
        return {tuple(w)} if w else set()
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def similarity(a: str, b: str) -> float:
    """Jaccard of the two texts' word 3-shingles (0..1)."""
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass(frozen=True)
class Past:
    run: str
    line: str
    text: str


async def past_texts(ctx: StepContext) -> list[Past]:
    """This company's earlier texts (its lines' real runs, newest first),
    never this run's own nor a copy a rerun reused."""
    company = await ctx.hub.companies.by_code(ctx.company)
    async with ctx.hub.db.tx([company.id]) as tx:
        rows = await tx.all(
            """SELECT r.ref AS run, l.ref AS line, s.output->>'text' AS text
               FROM lines.step_runs s JOIN lines.runs r ON r.id = s.run_id
               JOIN lines.lines l ON l.id = r.line_id
               WHERE s.company_id = :co AND s.state = 'done' AND NOT s.reused AND NOT r.dry
                 AND s.kind = ANY(CAST(:kinds AS text[])) AND r.ref <> :run
                 AND coalesce(s.output->>'text', '') <> ''
                 AND r.at > now() - make_interval(days => :days)
               ORDER BY (l.ref = :line) DESC, s.ended_at DESC NULLS LAST LIMIT :n""",
            co=company.id,
            kinds=list(TEXT_KINDS),
            run=ctx.run_ref,
            line=ctx.line_ref,
            days=HISTORY_DAYS,
            n=HISTORY,
        )
    return [Past(str(r["run"]), str(r["line"]), str(r["text"])) for r in rows]


def most_alike(text: str, past: list[Past]) -> tuple[float, Past | None]:
    best, of = 0.0, None
    for p in past:
        s = similarity(text, p.text)
        if s > best:
            best, of = s, p
    return best, of


def _keys(v: Any) -> list[str]:
    if isinstance(v, str) and v:
        return [v]
    return [str(x) for x in v] if isinstance(v, list) else []


def input_texts(ctx: StepContext) -> list[tuple[str, str]]:
    """(input key, text) of the inputs the step reads (`settings.text_from` or
    `settings.of`: step keys; else every input), plus the data fields it
    names in `settings.fields` (a caption, a title)."""
    s = ctx.step.get("settings", {})
    fields = [str(f) for f in s.get("fields") or []]
    only = _keys(s.get("text_from")) + _keys(s.get("of"))
    out: list[tuple[str, str]] = []
    for key, o in ctx.inputs.items():
        if only and key not in only:
            continue
        if o.text and o.text.strip():
            out.append((key, o.text))
        for f in fields:
            v = o.data.get(f)
            if isinstance(v, str) and v.strip():
                out.append((f"{key}.{f}", v))
    return out


def _pct(x: float) -> str:
    return f"{round(x * 100)}٪"


# ------------------------------------------------------------------ dedupe --
class Dedupe:
    kind = "dedupe"
    reruns_input = True  # too alike: the step that wrote the text writes it again

    async def run(self, ctx: StepContext) -> StepOutput:
        texts = input_texts(ctx)
        if not texts:
            raise StepFailed("متنی برای سنجیدن نرسید.", code="no_input")
        limit = float(ctx.step.get("settings", {}).get("threshold") or 0.6)
        past = await past_texts(ctx)
        worst, of, at = 0.0, None, ""
        for key, text in texts:
            s, p = most_alike(text, past)
            if s > worst:
                worst, of, at = s, p, key
        if of is not None and worst >= limit:
            raise StepFailed(
                f"متن «{at}» {_pct(worst)} شبیه متن اجرای {of.run} است؛ دوباره نوشته میشود.",
                code="too_alike",
                retry=True,
            )
        return StepOutput(
            text=texts[0][1],
            data={
                "similarity": round(worst, 3),
                "against": of.run if of else None,
                "checked": len(past),
            },
            via="code",
        )


# ----------------------------------------------------------------- quality --
async def sources_required(ctx: StepContext) -> bool:
    """The step's own setting, else whether a sealed rule of the owner that
    binds this company asks for sources (§29.3)."""
    s = ctx.step.get("settings", {})
    for k in ("sources_required", "require_sources"):
        if k in s:
            return bool(s[k])
    company = await ctx.hub.companies.by_code(ctx.company)
    async with ctx.hub.db.tx([company.id]) as tx:
        rows = await tx.all(
            """SELECT text_md, applies_to, applies_codes FROM oversight.orders
               WHERE status = 'sealed'"""
        )
    return any(
        any(w in str(o["text_md"] or "") for w in SOURCE_WORDS)
        and owner_rules.applies(o, "agent", None, ctx.company)
        for o in rows
    )


def figures_without_source(text: str, sources: list[dict[str, Any]]) -> list[str]:
    lines = [ln for ln in text.splitlines() if not ILLUSTRATIVE.search(ln)]
    figures = {n for n in numbers_of("\n".join(lines)) if not re.fullmatch(r"[1-9]", n)}
    noted: set[str] = set()
    for s in sources:
        noted |= numbers_of(" ".join(str(s.get(k) or "") for k in ("note", "ref", "url", "text")))
    return sorted(figures - noted)


def platform_checks(platform: str, texts: list[str], check: Any) -> None:
    """§31.1 the platform's rules (data): links, financial claims, banned phrases."""
    rules = learning.platform_rules(platform)
    if rules["links"] == "none":
        linked = any(LINK.search(t) for t in texts)
        check(
            "links",
            not linked,
            (rules["links_note_fa"] or "لینک در این پلتفرم کار نمیکند.") if linked else "بی لینک",
        )
    for key, label in (("financial_claims", "ادعای مالی"), ("banned_phrases", "عبارت ممنوع")):
        hits = sorted({p for p in rules[key] for t in texts if p in t})
        if rules[key]:
            check(key, not hits, (f"{label}: " + "، ".join(hits[:4])) if hits else "پاک است")


HASHTAG = re.compile(r"#[\w\u200c]+", re.UNICODE)


def caption_checks(ctx: StepContext, s: dict[str, Any], check: Any) -> None:
    """`caption_max` (letters) and `hashtags_max` on the inputs' caption."""
    cap_max, tags_max = s.get("caption_max"), s.get("hashtags_max")
    if cap_max is None and tags_max is None:
        return
    for o in ctx.inputs.values():
        caption = o.data.get("caption")
        if not isinstance(caption, str):
            continue
        if cap_max is not None:
            ok = len(caption) <= int(cap_max)
            check(
                "caption", ok, f"کپشن {len(caption)} نویسه" + ("" if ok else f" (بیش از {cap_max})")
            )
        if tags_max is not None:
            tags = o.data.get("hashtags")
            n = len(tags) if isinstance(tags, list) else len(HASHTAG.findall(caption))
            ok = n <= int(tags_max)
            check("hashtags", ok, f"{n} هشتگ" + ("" if ok else f" (بیش از {tags_max})"))
        return


class Quality:
    kind = "quality"
    reruns_input = True  # a fixable miss: the text is written again (≤ max_attempts)

    async def run(self, ctx: StepContext) -> StepOutput:
        s = ctx.step.get("settings", {})
        texts = input_texts(ctx)
        if not texts:
            raise StepFailed("متنی برای سنجیدن نرسید.", code="no_input")
        checks: list[dict[str, Any]] = []

        def check(key: str, ok: bool, note_fa: str) -> None:
            checks.append({"key": key, "ok": ok, "note_fa": note_fa})

        if s.get("repeat", True):
            limit = float(s.get("repeat_threshold") or 0.8)
            past = await past_texts(ctx)
            worst, of = max((most_alike(t, past) for _, t in texts), key=lambda x: x[0])
            check(
                "repeat",
                of is None or worst < limit,
                f"{_pct(worst)} شبیه اجرای {of.run}" if of else "تکراری نیست",
            )
        if await sources_required(ctx):
            sources: list[dict[str, Any]] = []
            for o in ctx.inputs.values():
                sources += [x for x in o.data.get("sources") or [] if isinstance(x, dict)]
            missing = sorted({n for _, t in texts for n in figures_without_source(t, sources)})
            check(
                "sources",
                not missing,
                ("عدد بی‌منبع: " + "، ".join(missing[:6])) if missing else "هر عدد منبع دارد",
            )
        if s.get("persian", True):
            bad = [k for k, t in texts if not humanize.is_persian_answer(t)]
            check("persian", not bad, ("فارسی نیست: " + "، ".join(bad)) if bad else "فارسی است")
        lo, hi = s.get("min_chars"), s.get("max_chars")
        if lo is not None or hi is not None:
            n = len(texts[0][1].strip())
            ok = (lo is None or n >= int(lo)) and (hi is None or n <= int(hi))
            check("length", ok, f"{n} نویسه" + ("" if ok else f" (باید {lo or 0} تا {hi or '∞'})"))
        if s.get("platform_rules", True):
            platform_checks(ctx.platform, [t for _, t in texts], check)
        caption_checks(ctx, s, check)
        banned = [str(w) for w in s.get("banned_words") or [] if str(w).strip()]
        if banned:
            hits = sorted({w for w in banned for _, t in texts if w in t})
            check("banned", not hits, ("واژه‌ی ممنوع: " + "، ".join(hits)) if hits else "پاک است")
        failed = [c for c in checks if not c["ok"]]
        if failed:
            raise StepFailed(
                "؛ ".join(c["note_fa"] for c in failed), code="quality_failed", retry=True
            )
        return StepOutput(text=texts[0][1], data={"checks": checks}, via="code")


# -------------------------------------------------------------------- seal --
class Seal:
    """The engine holds the run at this step until its card is decided (the
    owner's, or the CEO's for `gate: ceo`); after the seal this records it."""

    kind = "seal"

    async def run(self, ctx: StepContext) -> StepOutput:
        sealed = ctx.step.get("_sealed") or {}
        return StepOutput(
            text=None,
            data={"sealed": bool(sealed), "by": sealed.get("by"), "dry": ctx.dry},
            via="seal",
        )


register(Dedupe())
register(Quality())
register(Seal())
