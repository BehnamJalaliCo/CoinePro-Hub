"""`pattern_search`: the best patterns for a query, Pinterest read only (§30.2).

The egress recipe `pinterest-web` searches the query in the hub's own browser profile and returns the
top pins as JSON text (image URL, link, title). Nothing is saved, pinned or followed. The query is
`settings.query`, else the first input's text, else the prompt; `settings.limit` (default 8) pins.
Output: `data.items` = [{image, link, title}], and the same as text lines for the next prompt.
"""

from __future__ import annotations

import json
from typing import Any

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

ACCOUNT = "pinterest-web"
QUERY_CHARS = 200
DEFAULT_LIMIT = 8


def parse_pins(raw: str, limit: int) -> list[dict[str, str]]:
    try:
        rows = json.loads(raw)
    except ValueError as exc:
        raise StepFailed("خروجی جستجوی پینترست خوانده نشد.", code="bad_answer", retry=True) from exc
    out: list[dict[str, str]] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        image, link = str(r.get("image") or ""), str(r.get("link") or "")
        if image.startswith("https://") or link.startswith("https://"):
            out.append({"image": image, "link": link, "title": str(r.get("title") or "")[:200]})
    return out[:limit]


class PatternSearch:
    kind = "pattern_search"

    async def run(self, ctx: StepContext) -> StepOutput:
        src = C.first_input(ctx)
        query = str(
            C.setting(ctx, "query") or ctx.prompt or (src.text if src is not None else "") or ""
        ).strip()
        query = " ".join(query.split())[:QUERY_CHARS]
        if not query:
            raise StepFailed("عبارت جستجوی الگوها خالی است.", code="empty_query")
        limit = max(1, min(int(C.setting(ctx, "limit", DEFAULT_LIMIT)), 30))
        got = await C.web_job(
            ctx.hub,
            account=ACCOUNT,
            task="search",
            prompt=query,
            timeout_s=C.timeout_of(ctx, 90),
            limit=limit,
        )
        pins = parse_pins(str(got.get("text_md") or ""), limit)
        if not pins:
            raise StepFailed(f"برای «{query}» الگویی در پینترست پیدا نشد.", code="no_results")
        lines = [
            f"{i + 1}. {p['title'] or '(بی‌عنوان)'} | {p['link']} | {p['image']}"
            for i, p in enumerate(pins)
        ]
        data: dict[str, Any] = {"query": query, "items": pins}
        return StepOutput(text="\n".join(lines), via=ACCOUNT, data=data)


register(PatternSearch())
