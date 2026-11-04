"""`opus_build`: the build of a piece: a render spec, the caption and the hashtags (§30.2).

The LLM router with the top Claude model at effort `high` (task class `line_build`, ledgered there;
the line's `caps.opus_per_day` is the engine's to check before this step). The answer is ONE JSON
object in the media studio's own formats (domain/studio.py, hq_common.composition):

    {"composition": {"format": "html"|"lottie", "source": "<document>"},
     "direction": {"shots": [{"duration_s": 3, "text_fa": "...", "visual_fa": "..."}]},
     "duration_s": 30, "caption_fa": "...", "hashtags": ["#..."],
     "title_fa": "...", "description_fa": "..."}

The composition is checked here by the same rules as the studio's (a refusal is told to the model
once, then the step fails plainly). The result is `data.spec` (what `render` takes), `data.caption`,
`data.hashtags`, `data.title`, `data.description`; `text` is the caption with the hashtags.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from hq_api.agents.clients import ModelCall, Router
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register
from hq_common import composition as COMP

MODEL = "claude-opus-5-5"
EFFORT = "high"
TASK_CLASS = "line_build"
MAX_OUTPUT_TOKENS = 32_000
HASHTAGS = 30  # Instagram's own cap

SYSTEM = (
    "تو سازنده‌ی محتوای ویدیویی کوتاه هستی. فقط یک شیء JSON معتبر برگردان، بدون هیچ متن دیگر و بدون "
    "بلوک کد. ساختار: "
    '{"composition": {"format": "html", "source": "<یک سند HTML کامل>"}, '
    '"direction": {"shots": [{"duration_s": <ثانیه>, "text_fa": "<متنی که گفته/نوشته می‌شود>", '
    '"visual_fa": "<تصویر و حرکت>"}]}, "duration_s": <جمع زمان نماها>, "caption_fa": "<کپشن>", '
    '"hashtags": ["#..."], "title_fa": "<عنوان کوتاه>", "description_fa": "<توضیح>"}.\n'
    "قواعد سند HTML: یک سند کاملاً مستقل با lang=fa و dir=rtl؛ فقط CSS، SVG، Web Animations و کتابخانه‌های "
    '<script src="/lib/anime.min.js"> یا "/lib/lottie.min.js">؛ تنها فونت IRANYekanX؛ هیچ شبکه (fetch، '
    "XHR، پیوند، iframe، form، @import)، هیچ ذخیره‌سازی و eval؛ تصویر فقط از /assets/<شناسه‌ی فایل> یا "
    "data:image. اندازه‌ی صفحه ۱۰۸۰×۱۹۲۰ (۹:۱۶) مگر خلاف آن گفته شود. جمع duration_s نماها برابر "
    "duration_s کل باشد. متن‌های فارسی روان، بدون ادعای بی‌منبع و بدون وعده‌ی سود."
)


def router_for(hub: Any) -> Router:
    if C.ROUTER_OVERRIDE is not None:
        return C.ROUTER_OVERRIDE  # type: ignore[no-any-return]
    return Router(hub.settings.llm_router_url, lambda: hub.secrets.llm_router_token)


def hashtags_of(raw: Any) -> list[str]:
    out: list[str] = []
    for h in raw if isinstance(raw, list) else re.findall(r"#?\w+", str(raw or "")):
        tag = "#" + re.sub(r"[\s#]+", "_", str(h).strip().lstrip("#")).strip("_")
        if len(tag) > 1 and tag not in out:
            out.append(tag[:60])
    return out[:HASHTAGS]


def validate(obj: dict[str, Any]) -> dict[str, Any]:
    """The spec in the studio's format, or ValueError naming what is wrong."""
    comp = obj.get("composition")
    if not isinstance(comp, dict) or comp.get("format") not in ("html", "lottie"):
        raise ValueError("composition.format must be html or lottie")
    source = comp.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("composition.source is empty")
    report = COMP.check(str(comp["format"]), source, None)
    if not report.ok:
        raise ValueError(
            "composition refused: "
            + "; ".join(f"{p['rule']}: {p['detail']}" for p in report.problems[:6])
        )
    shots = (obj.get("direction") or {}).get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("direction.shots needs at least one shot")
    total = 0.0
    for s in shots:
        try:
            total += float(s["duration_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("every shot has duration_s") from exc
    caption = str(obj.get("caption_fa") or "").strip()
    if not caption:
        raise ValueError("caption_fa is empty")
    return {
        "composition": {"format": comp["format"], "source": source},
        "direction": {"shots": shots},
        "duration_s": float(obj.get("duration_s") or total),
        "caption": caption,
        "hashtags": hashtags_of(obj.get("hashtags")),
        "title": str(obj.get("title_fa") or "").strip()[:100],
        "description": str(obj.get("description_fa") or "").strip(),
    }


class OpusBuild:
    kind = "opus_build"

    async def run(self, ctx: StepContext) -> StepOutput:
        prompt = (ctx.prompt or "").strip()
        if not prompt:
            raise StepFailed("متن درخواست ساخت خالی است.", code="empty_prompt")
        await C.check_unlocked(ctx.hub)
        router = router_for(ctx.hub)
        tokens, usd = 0, Decimal(0)
        asked = prompt
        last = ""
        for attempt in (1, 2):  # the second asks again once, with what the first got wrong
            call: ModelCall = await router.run(
                {
                    "company_code": ctx.company,
                    "actor_ref": f"{ctx.company}-LINES",
                    "task_class": TASK_CLASS,
                    "priority": 2,
                    "model": str(C.setting(ctx, "model", MODEL)),
                    "effort": str(C.setting(ctx, "effort", EFFORT)),
                    "system": SYSTEM,
                    "prompt": asked,
                    "timeout_s": C.timeout_of(ctx, 600),
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "meta": {"purpose": "line_build"},
                },
                C.timeout_of(ctx, 600),
            )
            tokens += call.tokens
            usd += Decimal(str(call.equiv_cost_usd or 0))
            if not call.ok:
                raise StepFailed(
                    f"ساخت با مدل اصلی انجام نشد ({call.code or call.status}); "
                    "جایگزین بی‌صدا به مدل دیگر نداریم.",
                    code=str(call.code or "router"),
                    retry=True,
                )
            try:
                spec = validate(
                    call.structured
                    if isinstance(call.structured, dict)
                    else C.parse_json_object(call.text or "")
                )
            except (ValueError, json.JSONDecodeError) as exc:
                last = str(exc)[:300]
                asked = (
                    f"{prompt}\n\nپاسخ قبلی تو پذیرفته نشد: {last}\n"
                    "دوباره و کامل، فقط با یک شیء JSON درست."
                )
                continue
            text = spec["caption"] + (
                "\n\n" + " ".join(spec["hashtags"]) if spec["hashtags"] else ""
            )
            return StepOutput(
                text=text,
                via=f"router:{call.model or MODEL}",
                tokens=tokens,
                usd_equiv=usd,
                data={
                    "spec": spec,
                    "caption": spec["caption"],
                    "hashtags": spec["hashtags"],
                    "title": spec["title"],
                    "description": spec["description"],
                    "duration_s": spec["duration_s"],
                    "attempt": attempt,
                },
            )
        raise StepFailed(f"خروجی ساخت قابل‌قبول نبود: {last}", code="bad_spec", retry=True)


register(OpusBuild())
