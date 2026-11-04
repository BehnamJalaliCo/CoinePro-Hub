"""§31.1 The learning loop of a line, by code (no model anywhere here).

- At a run's first publish, `record_features` keeps what it was made of
  (lines.run_features): the hook (the script's first line), its words and
  length, the voice of its tts step, the pattern the council picked, the
  publish hour in the owner's zone, the caption's length.
- 24 hours and 7 days after a publish, `read_metrics` asks the publish
  adapter's optional `insights(ctx, published) -> {figure: value}` and keeps
  the answer in Run.metrics (h24, d7); then `compute` ranks the line's
  published runs by its template's metric (defaults.insights.metric) and
  writes lines.insights: the best hour, length bucket, voice and pattern
  source, the top hooks and plain Persian lessons. A clear winner raises one
  home suggestion (§29.13), never one the owner said «نه» to.
- Prompts read `{{insights.lessons}}` and `{{insights.top_hooks}}`.
- The quality step's platform rules (links, financial claims, banned phrases
  per platform) are data: apps/api/seed/lines/rules.yaml.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.domain import home as HM
from hq_api.domain.gov_common import zone
from hq_api.lines import adapters, store
from hq_api.lines import templates as T
from hq_api.lines.base import REGISTRY, StepContext

log = logging.getLogger("hq_api.lines.learning")

RULES_FILE = T.SEED_DIR / "rules.yaml"
WINDOW = 30  # the latest published runs ranked
MIN_RUNS = 3  # fewer runs with a figure: no lesson yet
WIN_RATIO = 1.5  # a choice this much better than the rest (each side ≥ 2 runs) is a clear winner
READS_PER_TICK = 50
H24, D7, LAST_READ = timedelta(hours=24), timedelta(days=7), timedelta(days=30)
METRIC_FA = {
    "views": "بازدید", "reach": "دسترسی", "clicks": "کلیک", "watch_s": "زمان تماشا",
    "likes": "پسند", "saves": "ذخیره", "shares": "هم‌رسانی", "followers": "دنبال‌کننده",
    "comments": "دیدگاه", "impressions": "نمایش",
}  # fmt: skip
SECONDS = ((15, "0-15s", "تا ۱۵ ثانیه"), (30, "15-30s", "۱۵ تا ۳۰ ثانیه"),
           (60, "30-60s", "۳۰ تا ۶۰ ثانیه"), (120, "60-120s", "یک تا دو دقیقه"))  # fmt: skip
WORDS = ((50, "0-50w", "تا ۵۰ واژه"), (100, "50-100w", "۵۰ تا ۱۰۰ واژه"),
         (200, "100-200w", "۱۰۰ تا ۲۰۰ واژه"), (400, "200-400w", "۲۰۰ تا ۴۰۰ واژه"))  # fmt: skip
BUCKET_FA = {key: fa for _, key, fa in (*SECONDS, *WORDS)} | {
    "120s+": "بیش از دو دقیقه", "400w+": "بیش از ۴۰۰ واژه",
}  # fmt: skip


# ----------------------------------------------------------- platform rules --
@lru_cache(maxsize=4)
def _rules(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def platform_rules(platform: str, path: Path | None = None) -> dict[str, Any]:
    """The rules for one platform: `all`'s merged with the platform's own."""
    data = _rules(str(path or RULES_FILE))
    base = dict(data.get("all") or {})
    own = dict((data.get("platforms") or {}).get(platform) or {})
    out: dict[str, Any] = {"links": own.get("links", base.get("links", "allowed"))}
    for k in ("financial_claims", "banned_phrases"):
        out[k] = [str(x) for x in [*(base.get(k) or []), *(own.get(k) or [])] if str(x).strip()]
    out["links_note_fa"] = str(own.get("links_note_fa") or base.get("links_note_fa") or "")
    return out


# ----------------------------------------------------------------- features --
def first_line(text: str | None) -> str | None:
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()[:500]
    return None


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None and not isinstance(v, bool) else None
    except (TypeError, ValueError):
        return None


async def record_features(tx: Tx, run: dict[str, Any], tz: str) -> None:
    """What the run was made of, kept once at its first publish (by code)."""
    if await tx.scalar("SELECT 1 FROM lines.run_features WHERE run_id = :id", id=run["id"]):
        return
    body = await store.version_body(tx, run["line_id"], run["line_version"])
    defs = {s["key"]: s for s in body.get("steps") or []}
    steps = [s for s in await store.step_rows(tx, run["id"]) if s["state"] == "done"]

    def out(s: dict[str, Any]) -> dict[str, Any]:
        return s["output"] or {}

    script = next((s for s in steps if s["key"] == "script" and out(s).get("text")), None) or next(
        (s for s in steps if s["kind"] in ("gpt_text", "opus_build") and out(s).get("text")), None
    )
    text = out(script).get("text") if script else None
    length = next(
        (
            _num((out(s).get("data") or {}).get("duration_s"))
            for s in steps
            if s["kind"] in ("tts", "render") and _num((out(s).get("data") or {}).get("duration_s"))
        ),
        None,
    )
    voice = None
    for s in steps:
        if s["kind"] == "tts":
            st = (defs.get(s["key"]) or {}).get("settings") or {}
            voice = st.get("voice") or st.get("speaker") or (out(s).get("data") or {}).get("voice")
            break
    pattern = None
    for s in steps:
        if s["kind"] == "council_pick":
            d = out(s).get("data") or {}
            pattern = (
                d.get("pattern")
                or d.get("source")
                or d.get("choice")
                or first_line(out(s).get("text"))
            )
            break
    caption = None
    for s in reversed(steps):
        c = (out(s).get("data") or {}).get("caption")
        if isinstance(c, str) and c.strip():
            caption = c
            break
    await tx.exec(
        """INSERT INTO lines.run_features (run_id, company_id, line_id, platform, hook, words,
               length_s, voice, pattern, publish_hour, caption_len)
           VALUES (:run, :co, :line, :platform, :hook, :words, :length, :voice, :pattern, :hour,
                   :caption) ON CONFLICT (run_id) DO NOTHING""",
        run=run["id"],
        co=run["company_id"],
        line=run["line_id"],
        platform=run["platform"],
        hook=first_line(text),
        words=len(text.split()) if text else None,
        length=round(length, 1) if length is not None else None,
        voice=str(voice)[:120] if voice else None,
        pattern=str(pattern)[:300] if pattern else None,
        hour=datetime.now(UTC).astimezone(zone(tz)).hour,
        caption=len(caption) if caption else None,
    )


# ----------------------------------------------------------------- insights --
def length_bucket(length_s: Any, words: Any) -> str | None:
    if (s := _num(length_s)) is not None:
        return next((key for top, key, _ in SECONDS if s < top), "120s+")
    if (w := _num(words)) is not None:
        return next((key for top, key, _ in WORDS if w < top), "400w+")
    return None


def figure(metrics: dict[str, Any] | None, metric: str) -> float | None:
    m = metrics or {}
    for window in ("d7", "h24"):
        v = _num((m.get(window) or {}).get(metric))
        if v is not None:
            return v
    return None


def fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:.1f}".rstrip("0").rstrip(".")


def _winner(groups: dict[Any, list[float]]) -> tuple[Any, float, float, int] | None:
    """(the best choice, its mean, the others' mean, its runs) when there are
    at least two choices; None otherwise."""
    groups = {k: v for k, v in groups.items() if k not in (None, "") and v}
    if len(groups) < 2:
        return None
    best = max(groups, key=lambda k: (sum(groups[k]) / len(groups[k]), len(groups[k])))
    rest = [x for k, v in groups.items() if k != best for x in v]
    return best, sum(groups[best]) / len(groups[best]), sum(rest) / len(rest), len(groups[best])


def metric_of(template_key: str) -> str:
    t = T.load().get(template_key)
    return t.defaults.insights.metric if t is not None else "views"


async def compute(tx: Tx, line_id: UUID) -> store.Insights:
    """The line's insights again from its latest published runs (code only)."""
    line = await store.by_id(tx, line_id)
    metric = metric_of(line["template"])
    mfa = METRIC_FA.get(metric, metric)
    rows = await tx.all(
        """SELECT r.ref, r.metrics, f.hook, f.words, f.length_s, f.voice, f.pattern, f.publish_hour
           FROM lines.runs r JOIN lines.run_features f ON f.run_id = r.id
           WHERE r.line_id = :id AND r.state = 'done' AND NOT r.dry
           ORDER BY r.at DESC LIMIT :n""",
        id=line_id,
        n=WINDOW,
    )
    scored = [(v, r) for r in rows if (v := figure(r["metrics"], metric)) is not None]
    scored.sort(key=lambda x: -x[0])
    best: dict[str, Any] = {}
    lessons: list[str] = []
    winners: list[tuple[str, Any, float, float, int]] = []
    dims: dict[str, Callable[[dict[str, Any]], Any]] = {
        "hour": lambda r: r["publish_hour"],
        "length_bucket": lambda r: length_bucket(r["length_s"], r["words"]),
        "voice": lambda r: r["voice"],
        "pattern_source": lambda r: r["pattern"],
    }
    if len(scored) >= MIN_RUNS:
        for dim, of in dims.items():
            groups: dict[Any, list[float]] = defaultdict(list)
            for v, r in scored:
                groups[of(r)].append(v)
            w = _winner(groups)
            if w is None:
                continue
            choice, mean, rest, n = w
            best[dim] = choice
            lessons.append(lesson(dim, choice, mean, rest, mfa))
            others = len(scored) - n
            if n >= 2 and others >= 2 and rest > 0 and mean >= WIN_RATIO * rest:
                winners.append((dim, choice, mean, rest, n))
    else:
        lessons.append(
            f"هنوز {len(scored)} اجرای منتشرشده با عدد {mfa} هست؛ از {MIN_RUNS} اجرا به بعد درس نوشته میشود."
        )
    hooks = list(dict.fromkeys(str(r["hook"]) for _, r in scored if r["hook"]))[:3]
    await tx.exec(
        """INSERT INTO lines.insights (line_id, company_id, metric, window_runs, best, top_hooks,
               lessons_fa, updated_at)
           VALUES (:id, :co, :m, :n, CAST(:best AS jsonb), CAST(:hooks AS jsonb),
                   CAST(:lessons AS jsonb), now())
           ON CONFLICT (line_id) DO UPDATE SET metric = EXCLUDED.metric,
               window_runs = EXCLUDED.window_runs, best = EXCLUDED.best,
               top_hooks = EXCLUDED.top_hooks, lessons_fa = EXCLUDED.lessons_fa, updated_at = now()""",
        id=line_id,
        co=line["company_id"],
        m=metric,
        n=len(scored),
        best=json.dumps(best, ensure_ascii=False),
        hooks=json.dumps(hooks, ensure_ascii=False),
        lessons=json.dumps(lessons, ensure_ascii=False),
    )
    for dim, choice, mean, rest, n in winners:
        await suggest(tx, line, dim, choice, mean, rest, n, mfa)
    await events.emit(
        tx,
        line["company"],
        "insights.updated",
        line["ref"],
        {"metric": metric, "runs": len(scored)},
    )
    return await get(tx, line)


def _choice_fa(dim: str, choice: Any) -> str:
    if dim == "hour":
        return f"ساعت {int(choice)}"
    if dim == "length_bucket":
        return BUCKET_FA.get(str(choice), str(choice))
    if dim == "voice":
        return f"گوینده‌ی «{choice}»"
    return f"الگوی «{choice}»"


def lesson(dim: str, choice: Any, mean: float, rest: float, mfa: str) -> str:
    what = {
        "hour": "بهترین ساعت انتشار",
        "length_bucket": "بهترین اندازه",
        "voice": "بهترین گوینده",
        "pattern_source": "بهترین الگو",
    }[dim]
    return f"{what}: {_choice_fa(dim, choice)}؛ میانگین {mfa} {fmt(mean)} در برابر {fmt(rest)} برای بقیه."


async def suggest(
    tx: Tx, line: dict[str, Any], dim: str, choice: Any, mean: float, rest: float, n: int, mfa: str
) -> None:
    title = {
        "hour": f"«{line['title_fa']}» را {_choice_fa(dim, choice)} منتشر کن",
        "length_bucket": f"«{line['title_fa']}» را {_choice_fa(dim, choice)} بساز",
        "voice": f"در «{line['title_fa']}» {_choice_fa(dim, choice)} را نگه دار",
        "pattern_source": f"در «{line['title_fa']}» {_choice_fa(dim, choice)} را بیشتر به کار ببر",
    }[dim]
    await HM.add_suggestion(
        tx,
        company_id=line["company_id"],
        company_code=line["company"],
        title_fa=title,
        why_fa=f"میانگین {mfa} با این انتخاب {fmt(mean)} بوده و با بقیه {fmt(rest)} ({n} اجرا).",
        impact_fa=f"حدود {mean / rest:.1f} برابر {mfa}",
        cost_fa="یک تغییر در تنظیم خط",
        impact=3,
        cost=1,
        source="group",
        key=f"line:{line['ref']}:{dim}:{choice}",
        source_ref=line["ref"],
    )


async def get(tx: Tx, line: dict[str, Any]) -> store.Insights:
    r = await tx.first("SELECT * FROM lines.insights WHERE line_id = :id", id=line["id"])
    if r is None:
        return store.Insights(
            line=line["ref"], metric=metric_of(line["template"]), window_runs=0,
            best=store.InsightsBest(), top_hooks=[], lessons_fa=[], updated_at=None,
        )  # fmt: skip
    return store.Insights(
        line=line["ref"],
        metric=r["metric"],
        window_runs=r["window_runs"],
        best=store.InsightsBest.model_validate(r["best"] or {}),
        top_hooks=list(r["top_hooks"] or []),
        lessons_fa=list(r["lessons_fa"] or []),
        updated_at=r["updated_at"],
    )


async def prompt_vars(tx: Tx, line_id: UUID) -> dict[str, str]:
    r = await tx.first(
        "SELECT top_hooks, lessons_fa FROM lines.insights WHERE line_id = :id", id=line_id
    )
    if r is None:
        return {}
    return {
        "lessons": "\n".join(str(x) for x in r["lessons_fa"] or []),
        "top_hooks": "\n".join(str(x) for x in r["top_hooks"] or []),
    }


# -------------------------------------------------------------- the reads --
async def read_metrics(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The 24h and 7d reads of every published run due (the publish adapter's
    optional `insights`), then each line's insights again."""
    now = now or datetime.now(UTC)
    adapters.load()
    read = getattr(REGISTRY.get("publish"), "insights", None)
    if read is None:
        return {"read": 0, "skipped": "no_insights"}
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.holding_lock(tx)) is not None:
            return gate.skipped(lock)
        due = await tx.all(
            store.RUN_SQL
            + """ WHERE r.state = 'done' AND NOT r.dry AND r.published <> '[]'::jsonb
                    AND ((r.metrics->'h24' IS NULL AND r.ended_at <= :h24 AND r.ended_at > :d7)
                      OR (r.metrics->'d7' IS NULL AND r.ended_at <= :d7 AND r.ended_at > :last))
                  ORDER BY r.ended_at LIMIT :n""",
            h24=now - H24,
            d7=now - D7,
            last=now - LAST_READ,
            n=READS_PER_TICK,
        )
        bodies = {
            r["ref"]: await store.version_body(tx, r["line_id"], r["line_version"]) for r in due
        }
    done = 0
    lines: set[UUID] = set()
    for r in due:
        body = bodies[r["ref"]]
        step = next((s for s in body.get("steps") or [] if s["kind"] == "publish"), None)
        if step is None:
            continue
        ctx = StepContext(
            run_ref=r["ref"], line_ref=r["line_ref"], company=r["company"], platform=r["platform"],
            channel=dict(body.get("channel") or {}), step=step, prompt=None, inputs={}, library=(),
            dry=False, hub=hub,
        )  # fmt: skip
        try:
            figures = await asyncio.wait_for(read(ctx, list(r["published"] or [])), timeout=120)
        except Exception as exc:  # noqa: BLE001 - read again at the next tick
            log.warning(
                "line insights read failed", extra={"run": r["ref"], "error": type(exc).__name__}
            )
            continue
        if not isinstance(figures, dict):
            continue
        window = "d7" if r["ended_at"] <= now - D7 else "h24"
        async with hub.db.tx(ids) as tx:
            await tx.exec(
                """UPDATE lines.runs SET metrics = metrics || jsonb_build_object(CAST(:w AS text),
                       CAST(:f AS jsonb)), updated_at = now() WHERE id = :id""",
                id=r["id"],
                w=window,
                f=json.dumps(figures, ensure_ascii=False, default=str),
            )
        done += 1
        lines.add(r["line_id"])
    for line_id in lines:
        async with hub.db.tx(ids) as tx:
            await compute(tx, line_id)
    return {"read": done, "lines": len(lines)}
