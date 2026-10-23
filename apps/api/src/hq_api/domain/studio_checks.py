"""The media studio's checks, by code (prompt 13 §2.3, contract §22.2 step 7).

    brand         IRANYekanX only; colours from the company's palette; the mark
                  placed by the hub (the render or the creative's overlay)
    red_lines     the sealed charter's rule patterns (prompt 11's
                  governance.charters, holding and the company's addendum;
                  until one is sealed, the rule red lines of agents/charter/
                  HOLDING.md) on the script, the voice, the captions, the
                  on-screen text and the caption
    risk_warning  trading content carries the warning, spoken or captioned
                  (or on the frame, for a still) AND in the caption
    facts         every figure of the script has a source whose note names it
                  (illustrative figures say «فرض کنید»)
    rights        only the company's own files, the hub's own (creatives, the
                  voice) or a licensed library (none yet: music `none`)
    platform      aspect, length, size per placement, by the platform's limits
`qc` is the media director's review (media.review), not here.
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from hq_api.db import Tx
from hq_api.domain import studio as S
from hq_api.domain.briefings import numbers_of
from hq_common import composition as C

TRADING = re.compile(
    r"(?i)ترید|معامله|اهرم|لوریج|leverage|سیگنال|signal|بیت[‌ ]?کوین|bitcoin|\bBTC\b|"
    r"اتریوم|ethereum|\bETH\b|کریپتو|crypto|رمزارز|ارز\s*دیجیتال|فارکس|forex|\bfx\b|فیوچرز|futures|"
    r"مارجین|margin|پوزیشن|position|لانگ|شورت|\bRSI\b|اندیکاتور|indicator|حمایت|مقاومت|"
    r"حد\s*ضرر|stop\s*loss|طلا|xau|سهام|بورس|نمودار|چارت|قیمت"
)
WARNING = re.compile(
    r"هشدار\s*ریسک|(?:ریسک|خطر)[^.\n؟!]{0,80}(?:سرمایه|زیان|ضرر|از\s*دست)|"
    r"(?:سرمایه|پول)[^.\n؟!]{0,60}(?:از\s*دست|زیان|ضرر)|(?i:risk\s+warning|capital\s+(?:is\s+)?at\s+risk)"
)
ILLUSTRATIVE = re.compile(r"فرض\s*کنید|مثلاً|مثلا|برای\s*مثال|فرضی|به\s*عنوان\s*مثال")
PART = re.compile(r"«?\s*(قلاب|بدنه|جمع[‌ ]?بندی(?:\s*و\s*دعوت)?|هشدار\s*ریسک|کپشن)\s*»?\s*[:：]?")
_TAGS = re.compile(r"<script\b.*?</script>|<style\b.*?</style>|<[^>]+>", re.S | re.I)
OWN_SERVICES = ("substitutes", "media", "tts", "brand")


def _result(key: str, ok: bool | None, note: str | None) -> dict[str, Any]:
    return {
        "key": key,
        "result": "n/a" if ok is None else ("pass" if ok else "fail"),
        "note_fa": note,
    }


def parts(text: str) -> dict[str, str]:
    """The scriptwriter's parts («قلاب», «بدنه», …, «کپشن») by their headings."""
    out: dict[str, str] = {}
    marks = list(PART.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        key = re.sub(r"[‌ ]", "", m.group(1))
        key = "جمع‌بندی" if key.startswith("جمع") else key
        out[key] = (out.get(key, "") + "\n" + text[m.end() : end]).strip()
    return out


def visible_text(source: str, fmt: str) -> str:
    if fmt == "html":
        return html.unescape(_TAGS.sub(" ", source))
    return " ".join(re.findall(r'"t"\s*:\s*"([^"]{1,500})"', source))  # Lottie text layers


async def texts(tx: Tx, item: dict[str, Any]) -> dict[str, str]:
    script = str((item.get("script") or {}).get("text_fa") or "")
    p = parts(script)
    shots = (item.get("direction") or {}).get("shots") or []
    voice = "\n".join(str(s.get("voice_fa") or "") for s in shots)
    screen = "\n".join(str(s.get("text_on_screen_fa") or "") for s in shots)
    narration = str((item.get("narration") or {}).get("text_fa") or "")
    frame = ""
    if item.get("composition_id"):
        comp = await tx.first(
            "SELECT format, source FROM media.compositions WHERE id = :c", c=item["composition_id"]
        )
        if comp is not None:
            frame = visible_text(comp["source"], comp["format"])
    if item.get("assets"):
        rows = await tx.all(
            "SELECT overlay FROM substitutes.creatives WHERE composed_file_id = ANY(:ids)",
            ids=list(item["assets"]),
        )
        for r in rows:
            o = r["overlay"] or {}
            frame += "\n" + "\n".join(
                str(o.get(k) or "") for k in ("title_fa", "body_fa", "cta_fa")
            )
    return {
        "script": script,
        "caption": p.get("کپشن") or "",
        "warning_part": p.get("هشدارریسک") or "",
        "voice": "\n".join(x for x in (voice, narration) if x),
        "screen": screen,
        "frame": frame,
    }


# ------------------------------------------------------------ red lines --
@lru_cache(maxsize=4)
def _file_red_lines(path: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    p = Path(path)
    if not p.exists():
        return ()
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ()
    meta = yaml.safe_load(text.split("---", 2)[1]) or {}
    out = []
    for r in meta.get("red_lines") or []:
        if r.get("check") == "rule" and r.get("patterns"):
            out.append(
                (
                    str(r["key"]),
                    str(r.get("text_fa") or r["key"]),
                    tuple(str(x) for x in r["patterns"]),
                )
            )
    return tuple(out)


async def red_line_patterns(
    tx: Tx, hub: Any, company: str
) -> list[tuple[str, str, tuple[str, ...]]]:
    """The sealed charter's rule red lines (holding and the company's
    addendum); until one is sealed, those of agents/charter/HOLDING.md."""
    out: list[tuple[str, str, tuple[str, ...]]] = []
    if await tx.scalar("SELECT to_regclass('governance.charters') IS NOT NULL"):
        rows = await tx.all(
            """SELECT DISTINCT ON (scope) scope, red_lines FROM governance.charters
               WHERE status = 'sealed' AND scope IN ('holding', :co) ORDER BY scope, version DESC""",
            co=company,
        )
        for r in rows:
            for x in r["red_lines"] or []:
                if isinstance(x, dict) and x.get("check") == "rule" and x.get("patterns"):
                    out.append(
                        (
                            str(x.get("key")),
                            str(x.get("text_fa") or x.get("key")),
                            tuple(map(str, x["patterns"])),
                        )
                    )
        if rows:
            return out
    lib = getattr(hub, "charters", None)
    root = getattr(lib, "root", None)
    if root is not None:
        out.extend(_file_red_lines(str(Path(root) / "charter" / "HOLDING.md")))
    return out


def _search(pattern: str, text: str) -> re.Match[str] | None:
    try:
        return re.search(pattern, text)
    except re.error:
        return None


# ---------------------------------------------------------------- run --
async def run(tx: Tx, hub: Any, item: dict[str, Any]) -> list[dict[str, Any]]:
    t = await texts(tx, item)
    fmt = S.fmt_of(item)
    return [
        await brand(tx, item, fmt),
        await red_lines(tx, hub, item, t),
        risk_warning(item, fmt, t),
        facts(item, t),
        await rights(tx, item, fmt),
        platform(item),
    ]


async def brand(tx: Tx, item: dict[str, Any], fmt: dict[str, Any]) -> dict[str, Any]:
    b = await S.brand_of(tx, item["company_id"])
    if b is None:
        return _result(
            "brand", False, "برند فعال شرکت نیست (مُهر شرکت)؛ رنگ و نشان را نمیشود سنجید."
        )
    rep = item.get("composition_report") or {}
    problems = []
    fonts = [f for f in rep.get("fonts") or [] if f and not f.startswith(C.FONT)]
    if fonts:
        problems.append("قلم غیرمجاز: " + "، ".join(fonts[:3]))
    off = C.off_palette(list(rep.get("colors") or []), S.brand_colours(b))
    if off:
        problems.append("رنگ بیرون از پالت: " + "، ".join(off[:6]))
    meta = item.get("render_meta") or {}
    if (fmt.get("overlay") or {}).get("mark", True) and not meta.get("mark"):
        problems.append("نشان شرکت روی خروجی نیامد")
    if problems:
        return _result("brand", False, "؛ ".join(problems))
    n = len(rep.get("colors") or [])
    return _result("brand", True, f"IRANYekanX؛ {n} رنگ، همه از پالت شرکت؛ نشان را هاب گذاشت.")


async def red_lines(tx: Tx, hub: Any, item: dict[str, Any], t: dict[str, str]) -> dict[str, Any]:
    pats = await red_line_patterns(tx, hub, item["company"])
    if not pats:
        return _result("red_lines", None, "خط قرمز قاعده‌ای در اساسنامه نیست.")
    where = {
        "script": "سناریو",
        "voice": "صدا و زیرنویس",
        "screen": "متن روی صفحه",
        "frame": "متن روی تصویر",
        "caption": "کپشن",
    }
    for _key, title, patterns in pats:
        for part, label in where.items():
            for pat in patterns:
                m = _search(pat, t.get(part) or "")
                if m:
                    return _result("red_lines", False, f"«{title}» در {label}: «{m.group(0)[:60]}»")
    return _result(
        "red_lines",
        True,
        f"{len(pats)} خط قرمز قاعده‌ای روی سناریو، صدا، زیرنویس، متن تصویر و کپشن.",
    )


def risk_warning(item: dict[str, Any], fmt: dict[str, Any], t: dict[str, str]) -> dict[str, Any]:
    body = "\n".join(t[k] for k in ("script", "voice", "screen", "frame"))
    if not TRADING.search(body):
        return _result("risk_warning", None, "محتوای ترید نیست.")
    video = S.is_video(item["kind"], fmt)
    seen = (
        "\n".join((t["voice"], t["screen"]))
        if video
        else "\n".join((t["frame"], t["screen"], t["warning_part"]))
    )
    caption = t["caption"] or t["script"]
    on_item = bool(WARNING.search(seen))
    in_caption = bool(WARNING.search(caption))
    if on_item and in_caption:
        return _result(
            "risk_warning",
            True,
            "هشدار ریسک " + ("در صدا یا زیرنویس" if video else "روی تصویر") + " و در کپشن هست.",
        )
    missing = [
        x
        for x, ok in (("صدا یا زیرنویس" if video else "تصویر", on_item), ("کپشن", in_caption))
        if not ok
    ]
    return _result("risk_warning", False, "محتوای ترید بی هشدار ریسک در " + " و ".join(missing))


def facts(item: dict[str, Any], t: dict[str, str]) -> dict[str, Any]:
    script = item.get("script") or {}
    lines = [
        ln
        for ln in str(script.get("text_fa") or "").splitlines()
        if not ILLUSTRATIVE.search(ln) and not WARNING.search(ln)
    ]
    figures = {n for n in numbers_of("\n".join(lines)) if _is_figure(n)}
    if not figures:
        return _result("facts", None, "عددی در سناریو نیست.")
    sources = script.get("sources") or []
    noted: set[str] = set()
    for s in sources:
        noted |= numbers_of(" ".join(str(s.get(k) or "") for k in ("note", "ref", "url")))
    missing = sorted(figures - noted)
    if not sources or missing:
        return _result(
            "facts", False, "عدد بی‌منبع: " + "، ".join(missing[:6] or sorted(figures)[:6])
        )
    return _result("facts", True, f"{len(figures)} عدد، هر کدام با منبع.")


def _is_figure(n: str) -> bool:
    """A counting word (1-9 alone) is not a market figure; every other number is."""
    return not re.fullmatch(r"[1-9]", n)


async def rights(tx: Tx, item: dict[str, Any], fmt: dict[str, Any]) -> dict[str, Any]:
    if fmt.get("music") not in (None, "none"):
        return _result("rights", False, "کتابخانه‌ی موسیقی با مجوز نیست؛ موسیقی باید none باشد.")
    ids = list(item.get("assets") or [])
    if not ids:
        return _result("rights", True, "بی دارایی بیرونی؛ همه ساخته‌ی هاب.")
    rows = await tx.all(
        "SELECT id, company_id, created_by_kind, created_by_code FROM files.files WHERE id = ANY(:ids)",
        ids=ids,
    )
    found = {r["id"]: r for r in rows}
    bad = []
    own = made = 0
    for i in ids:
        r = found.get(i)
        if r is None or r["company_id"] != item["company_id"]:
            bad.append(str(i)[:8])
        elif r["created_by_kind"] == "owner":
            own += 1
        elif r["created_by_kind"] == "service" and r["created_by_code"] in OWN_SERVICES:
            made += 1
        else:
            bad.append(str(i)[:8])
    if bad:
        return _result(
            "rights", False, "دارایی بی‌مجوز یا بیرون از فایل‌های شرکت: " + "، ".join(bad[:5])
        )
    return _result(
        "rights", True, f"{own} فایل خود شرکت، {made} ساخته‌شده (AI-generated، برچسب‌دار)."
    )


def platform(item: dict[str, Any]) -> dict[str, Any]:
    outputs = item.get("outputs") or []
    targets = S.targets_of(item)
    if not targets:
        return _result("platform", None, "جای انتشاری ندارد.")
    problems: list[str] = []
    seen: list[str] = []
    for tg in targets:
        p = tg["placement"]
        lim = S.LIMITS[p]
        outs = [o for o in outputs if o.get("placement") == p]
        if not outs:
            problems.append(f"{p}: خروجی ندارد")
            continue
        if item["kind"] == "carousel" and p == "instagram_post" and not 2 <= len(outs) <= 10:
            problems.append(f"{p}: کاروسل ۲ تا ۱۰ قاب میخواهد ({len(outs)})")
        for o in outs:
            w, h = int(o.get("width") or 0), int(o.get("height") or 0)
            if (
                not w
                or not h
                or not any(
                    abs(w / h - a / b) < 0.01
                    for a, b in (map(int, x.split(":")) for x in lim["aspects"])
                )
            ):
                problems.append(f"{p}: نسبت {w}×{h} مجاز نیست")
            size = int(o.get("bytes") or 0)
            if o.get("kind") == "video":
                if lim["video"] is None:
                    problems.append(f"{p}: ویدیو نمیپذیرد")
                    continue
                lo, hi, mx = lim["video"]
                d = float(o.get("duration_s") or 0)
                if not lo <= d <= hi:
                    problems.append(f"{p}: {d:g} ثانیه بیرون از {lo} تا {hi}")
                if size > mx:
                    problems.append(f"{p}: {size // S.MB}MB بیشتر از {mx // S.MB}MB")
            else:
                if lim["image"] is None:
                    problems.append(f"{p}: تصویر نمیپذیرد")
                elif size > lim["image"]:
                    problems.append(f"{p}: {size // S.MB}MB بیشتر از {lim['image'] // S.MB}MB")
        seen.append(p)
    if problems:
        return _result("platform", False, "؛ ".join(problems[:6]))
    o = outputs[0]
    dur = f"، {float(o['duration_s']):g} ثانیه" if o.get("duration_s") else ""
    return _result(
        "platform",
        True,
        f"{o.get('width')}×{o.get('height')}{dur}؛ داخل محدودیت {'، '.join(seen)}.",
    )
