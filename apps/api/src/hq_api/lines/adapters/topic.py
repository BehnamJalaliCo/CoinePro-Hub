"""⟨1.37⟩ `topic`: the day's topic, never one said before (contract §59.2, §47).

A small model (task class `flow_topic`, Sonnet-class, through the LLM router like every model call)
proposes three candidates from what the company has said (the ledger: never again) and what its
last runs did (their topics and figures); code claims the first the ledger accepts (§47.2: the
same words, or four of five shared, is the same topic). If the ledger refuses all three, the model
is asked once more with them named. A dry run checks the ledger without writing in it.

The ledger is the flow's working group's (its playbook's group), else the company's own list; the
run is the line run, so `POST /line-runs/{ref}/cancel {skip: true}` frees its topic.

Settings: `model` (default claude-sonnet-5-5), `effort` (default low), `brief_fa` (what the flow is
about; else the step's prompt, else the playbook's title).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from hq_api.domain import topics as T
from hq_api.errors import ApiError
from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import _flow as FW
from hq_api.lines.adapters.opus_build import router_for
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

MODEL = "claude-sonnet-5-5"
EFFORT = "low"
TASK_CLASS = "flow_topic"
CANDIDATES = 3
ROUNDS = 2
RECENT = 40
RESULTS = 10
MAX_OUTPUT_TOKENS = 1_000
SYSTEM = (
    "You choose the day's topic for one company's short daily video. Answer ONLY one JSON object, "
    'no other text: {"candidates": ["<topic 1>", "<topic 2>", "<topic 3>"]}. Three different topics '
    "in Persian, each a short title of at most 12 words, none of them one already said (the list "
    "you are given: never the same thing in other words), leaning toward what did best in the last "
    "results. No promise of profit, no claim without a source."
)
RESULTS_SQL = """SELECT r.ref, s.output ->> 'text' AS topic, rr.comments, rr.likes, rr.views,
       rr.dms_sent, rr.clicks
FROM lines.runs r
JOIN lines.lines l ON l.id = r.line_id
JOIN lines.step_runs s ON s.run_id = r.id AND s.kind = 'topic' AND s.state = 'done'
LEFT JOIN growth.run_results rr ON rr.run_id = r.id
WHERE l.ref = :line AND r.ref <> :run AND NOT r.dry
ORDER BY r.at DESC LIMIT :n"""


def candidates_of(answer: Any, text: str) -> list[str]:
    obj = answer if isinstance(answer, dict) else C.parse_json_object(text or "")
    raw = obj.get("candidates") or obj.get("topics") or []
    out = [" ".join(str(x).split())[: T.TITLE_MAX] for x in raw if str(x).strip()]
    return list(dict.fromkeys(out))[:CANDIDATES]


def figures_fa(r: dict[str, Any]) -> str:
    names = (("views", "بازدید"), ("likes", "لایک"), ("comments", "کامنت"), ("dms_sent", "دایرکت"),
             ("clicks", "کلیک"))  # fmt: skip
    got = [f"{r[k]} {fa}" for k, fa in names if r.get(k) is not None]
    return "، ".join(got) or "هنوز خوانده نشده"


class Topic:
    kind = "topic"

    async def run(self, ctx: StepContext) -> StepOutput:
        await C.check_unlocked(ctx.hub)
        co = await C.company_of(ctx)
        hub = ctx.hub
        async with hub.db.tx(await hub.companies.ids()) as tx:
            flow = await FW.flow_of(tx, ctx)
            run = await FW.run_of(tx, ctx)
            scope = FW.scope_of(co.id, flow, run)
            said = [str(r["title_fa"]) for r in await T.recent(tx, scope, "topic", RECENT)]
            results = [
                dict(r)
                for r in await tx.all(RESULTS_SQL, line=ctx.line_ref, run=ctx.run_ref, n=RESULTS)
            ]
        brief = str(
            C.setting(ctx, "brief_fa") or ctx.prompt or (flow or {}).get("playbook_fa") or ""
        ).strip()
        router = router_for(hub)
        tokens, usd = 0, Decimal(0)
        refused: list[str] = []
        model = str(C.setting(ctx, "model") or MODEL)
        for _round in range(ROUNDS):
            prompt = "\n".join([
                f"What the flow is about: {brief or '-'}",
                "Already said (never again): " + ("؛ ".join(said[:RECENT]) or "-"),
                "Refused just now (taken): " + ("؛ ".join(refused) or "-"),
                "Last results (topic: figures):",
                *[f"- {r['topic']}: {figures_fa(r)}" for r in results if r.get("topic")],
            ])  # fmt: skip
            call = await router.run(
                {
                    "company_code": ctx.company,
                    "actor_ref": f"{ctx.company}-LINES",
                    "task_class": TASK_CLASS,
                    "priority": 2,
                    "model": model,
                    "effort": str(C.setting(ctx, "effort") or EFFORT),
                    "system": SYSTEM,
                    "prompt": prompt,
                    "timeout_s": C.timeout_of(ctx, 120),
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "meta": {"purpose": TASK_CLASS},
                },
                C.timeout_of(ctx, 120),
            )
            tokens += call.tokens
            usd += Decimal(str(call.equiv_cost_usd or 0))
            if not call.ok:
                raise StepFailed(
                    f"پیشنهاد موضوع از مدل نرسید ({call.code or call.status}).",
                    code=str(call.code or "router"),
                    retry=True,
                )
            try:
                found = candidates_of(call.structured, call.text or "")
            except (ValueError, json.JSONDecodeError):
                found = []
            got = await self._claim(ctx, scope, found, refused)
            if got is not None:
                return StepOutput(
                    text=got,
                    via=f"router:{call.model or model}",
                    tokens=tokens,
                    usd_equiv=usd,
                    data={
                        "topic": got,
                        "candidates": found,
                        "refused": refused,
                        "model": call.model or model,
                        "claimed": not ctx.dry,
                    },
                )
        raise StepFailed(
            "هر سه پیشنهاد موضوع پیش‌تر گفته شده بود؛ دوباره امتحان میشود.",
            code="topic_taken",
            retry=True,
        )

    async def _claim(
        self, ctx: StepContext, scope: dict[str, Any], found: list[str], refused: list[str]
    ) -> str | None:
        """The first candidate the ledger accepts (claimed for the run; a dry run only asks)."""
        hub = ctx.hub
        for title in found:
            try:
                async with hub.db.tx(await hub.companies.ids()) as tx:
                    if ctx.dry:
                        text, _url, tokens, norm = T.parts("topic", title, None)
                        hit = await T.taken_by(tx, scope, "topic", tokens, norm,
                                               but_run=scope.get("run_id"))  # fmt: skip
                        if hit is not None:
                            raise T.taken_error(hit, [])
                        return text
                    row, _new = await T.claim(
                        tx, scope, kind="topic", title=title, source="claim",
                        by=f"line:{ctx.run_ref}",
                    )  # fmt: skip
                    return str(row["title_fa"])
            except ApiError as exc:
                if exc.code not in ("topic_taken", "validation_failed"):
                    raise
                refused.append(title)
        return None


register(Topic())
