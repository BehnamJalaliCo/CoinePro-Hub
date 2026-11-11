"""`persona_test`: the message against the company's personas, before it goes on (§30.2, §33.9).

ONE mid-model call for all the personas (task class `persona_test`, through `domain/personas.py`, the
same function as the owner's `POST /companies/{code}/personas/test`); code checks the answer and
computes the score. The step's settings (data): `min_score` (0..100, default 60), `aggregate`
(`mean` of the personas' scores, or `min`), `text_from` (the step whose text is tested; else the
last input with a text).

At or above `min_score` the text goes on unchanged. Below it the step answers `hold: owner` and the
engine parks the run with a card that shows the objections; the owner's seal lets the run go on (the
step then passes the text through without asking the model again), his refusal ends it. A dry run
tests and shows the result but never waits. A model that cannot answer fails the step plainly
(retry allowed); nothing silently passes an untested message.
"""

from __future__ import annotations

from typing import Any

from hq_api.domain import personas as P
from hq_api.errors import ApiError
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

DEFAULT_MIN_SCORE = 60


def text_of(ctx: StepContext) -> str:
    src = C.input_with(ctx, "text", C.setting(ctx, "text_from"))
    text = str(getattr(src, "text", None) or ctx.prompt or "").strip()
    if not text:
        raise StepFailed("متنی برای آزمودن روی پرسوناها نیست.", code="no_input")
    return text


def why_fa(score: int, need: int, aggregate: str, results: list[dict[str, Any]]) -> str:
    """The card's reason, written by code from the checked results (the model's words are quoted
    only as the personas' objections)."""
    basis = "کمترین امتیاز" if aggregate == "min" else "میانگین امتیاز"
    lines = [f"{basis} پرسوناها {score} از ۱۰۰ شد و کمتر از حد لازم ({need}) است."]
    for r in results:
        if r.get("objection_fa"):
            lines.append(f"• {r['name_fa']} ({r['score']}): {r['objection_fa']}")
        if r.get("fix_fa"):
            lines.append(f"  پیشنهاد: {r['fix_fa']}")
    lines.append("اگر با همین متن موافقی مُهر کن؛ وگرنه رد کن تا متن عوض شود.")
    return "\n".join(lines)


class PersonaTestStep:
    kind = "persona_test"

    async def run(self, ctx: StepContext) -> StepOutput:
        text = text_of(ctx)
        sealed = ctx.step.get("_sealed")
        if sealed:  # the owner passed it with the objections in front of him: no second call
            return StepOutput(
                text=text,
                data={"passed": True, "passed_by": "owner", "sealed": True},
                via="persona_test",
            )
        await C.check_unlocked(ctx.hub)
        company = await C.company_of(ctx)
        try:
            test, tokens = await P.run_test(
                ctx.hub, company, text, source="line", run_ref=ctx.run_ref
            )
        except ApiError as exc:
            raise StepFailed(
                exc.message_fa or "آزمون پیام روی پرسوناها انجام نشد.",
                code=exc.code,
                retry=exc.status == 502 or isinstance(exc, P.ModelDown),
            ) from exc
        aggregate = str(C.setting(ctx, "aggregate", "mean"))
        need = int(C.setting(ctx, "min_score", DEFAULT_MIN_SCORE))
        score = test.lowest if aggregate == "min" else test.average
        results = [r.model_dump(mode="json") for r in test.results]
        passed = score >= need
        data: dict[str, Any] = {
            "test_id": str(test.id),
            "score": score,
            "min_score": need,
            "aggregate": aggregate,
            "passed": passed,
            "results": results,
        }
        if not passed:
            data["hold"] = "owner"
            data["why_fa"] = why_fa(score, need, aggregate, results)
        return StepOutput(text=text, data=data, via="router:persona_test", tokens=tokens)


register(PersonaTestStep())
