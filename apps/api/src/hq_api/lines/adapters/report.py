"""⟨1.37⟩ `report`: the day's line for the owner's summary, by code (contract §59.2, §59.9).

One plain Persian line from what the run did: what went out (the publish step's published
entries, with the topic), what was set for its hour, or why nothing went out; and what the run
cost so far. The 21:30 summary (`POST /internal/v1/flows/summary`) gathers these lines; the post's
figures (comments, DMs, clicks, views) are read from IG-Hub later and never guessed here.

Settings: `publish_from` (the publish step, default `publish`; else the input with `published` or
`would_publish`), `topic_from` (default `topic`; else the input whose output has a topic).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepOutput, register

KIND_FA = {"reel": "ریلز", "post": "پست", "story": "استوری", "carousel": "اسلاید", "short": "شورتس",
           "video": "ویدیو", "message": "پیام", "article": "مقاله"}  # fmt: skip
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
COST_SQL = "SELECT usd_equiv, tokens, dry FROM lines.runs WHERE ref = :r"


def _find(ctx: StepContext, setting: str, default: str, *keys: str) -> Any:
    named = ctx.inputs.get(str(C.setting(ctx, setting) or default))
    if named is not None:
        return named
    return next(
        (
            o
            for o in reversed(list(ctx.inputs.values()))
            if any((o.data or {}).get(k) for k in keys)
        ),
        None,
    )


def line_fa(topic: str, published: list[dict[str, Any]], pub: Any, dry: bool) -> str:
    about = f" «{topic}»" if topic else ""
    if dry:
        return f"اجرای آزمایشی: ساخته شد{about}؛ چیزی منتشر نشد."
    out = [p for p in published if isinstance(p, dict)]
    if out:
        kinds = " و ".join(dict.fromkeys(KIND_FA.get(str(p.get("kind")), "پست") for p in out))
        return f"امروز: {kinds}{about} منتشر شد."
    data = (pub.data if pub is not None else None) or {}
    if data.get("wait") or data.get("jobs"):
        return f"امروز: ریلز{about} برای ساعت انتشارش به IG-Hub رفت."
    why = (pub.text if pub is not None else None) or "قدم انتشار اجرا نشد"
    return f"امروز چیزی منتشر نشد: {why}"


class Report:
    kind = "report"

    async def run(self, ctx: StepContext) -> StepOutput:
        pub = _find(ctx, "publish_from", "publish", "published", "would_publish", "jobs")
        top = _find(ctx, "topic_from", "topic", "topic")
        topic = " ".join(str(((top.data or {}).get("topic") or top.text) if top else "").split())
        given = (pub.data or {}).get("published") if pub is not None else None
        published = given if isinstance(given, list) else [given] if isinstance(given, dict) else []
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
            row = await tx.first(COST_SQL, r=ctx.run_ref)
        usd = Decimal(str((row or {}).get("usd_equiv") or 0))
        line = line_fa(topic[:120], published, pub, ctx.dry)
        return StepOutput(
            text=line,
            via="code",
            data={
                "line_fa": line,
                "topic": topic or None,
                "published": published,
                "cost_usd": float(round(usd, 4)),
                "dry": ctx.dry,
            },
        )


register(Report())
