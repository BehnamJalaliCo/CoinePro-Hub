"""⟨1.37⟩ `inspire`: one fresh reference for the day's build (contract §59.2, §47).

`pattern_search` (Pinterest, read only, in the hub's own browser profile) finds pins for the day's
topic; code keeps the first whose address is not in the ledger's references (§47: a pin by its
number) and claims it for the run, so no day takes another day's reference. A dry run only asks
the ledger.

Settings: `query` (else the topic step's text, `topic_from`, else the first input's, else the
prompt), `limit` (pins to look at, default 12).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from hq_api.domain import topics as T
from hq_api.errors import ApiError
from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import _flow as FW
from hq_api.lines.adapters.pattern_search import PatternSearch
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

LIMIT = 12


def query_of(ctx: StepContext) -> str:
    src = ctx.inputs.get(str(C.setting(ctx, "topic_from") or "")) or C.first_input(ctx)
    return " ".join(
        str(
            C.setting(ctx, "query") or (src.text if src is not None else "") or ctx.prompt or ""
        ).split()
    )[:200]


class Inspire:
    kind = "inspire"

    async def run(self, ctx: StepContext) -> StepOutput:
        query = query_of(ctx)
        if not query:
            raise StepFailed("موضوعی برای جستجوی الگو نرسید.", code="empty_query")
        limit = max(1, min(int(C.setting(ctx, "limit", LIMIT)), 30))
        settings = {**(ctx.step.get("settings") or {}), "query": query, "limit": limit}
        found = await PatternSearch().run(
            dataclasses.replace(ctx, step={**ctx.step, "settings": settings}, prompt=query)
        )
        pins: list[dict[str, Any]] = list((found.data or {}).get("items") or [])
        co = await C.company_of(ctx)
        hub = ctx.hub
        taken = 0
        async with hub.db.tx(await hub.companies.ids()) as tx:
            flow = await FW.flow_of(tx, ctx)
            run = await FW.run_of(tx, ctx)
            scope = FW.scope_of(co.id, flow, run)
        for pin in pins:
            url = pin.get("link") or pin.get("image") or ""
            key = T.norm_url(url)
            if key is None:
                continue
            try:
                async with hub.db.tx(await hub.companies.ids()) as tx:
                    if ctx.dry:
                        hit = await T.taken_by(tx, scope, "reference", [], key,
                                               but_run=scope.get("run_id"))  # fmt: skip
                        if hit is not None:
                            raise T.taken_error(hit, [])
                    else:
                        await T.claim(
                            tx, scope, kind="reference", title=pin.get("title") or url, url=url,
                            source="claim", by=f"line:{ctx.run_ref}",
                        )  # fmt: skip
            except ApiError as exc:
                if exc.code not in ("topic_taken", "validation_failed"):
                    raise
                taken += 1
                continue
            text = "\n".join(x for x in (pin.get("title"), pin.get("link"), pin.get("image")) if x)
            return StepOutput(
                text=text,
                via=found.via,
                data={"reference": pin, "query": query, "taken": taken, "claimed": not ctx.dry},
            )
        raise StepFailed(
            f"برای «{query}» نمونه‌ی تازه‌ای پیدا نشد (همه پیش‌تر به کار رفته بودند).",
            code="no_fresh_reference",
            retry=True,
        )


register(Inspire())
