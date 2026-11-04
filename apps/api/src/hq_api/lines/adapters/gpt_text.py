"""`gpt_text`: the step's prompt to ChatGPT (web chat on the owner's plan), text back (§30.2).

It goes through the substitutes' seat call (domain/substitutes.py): the data guard, the launch gate,
the seat's daily cap, the 60 s pace per player and the ledger are theirs. GPT's text seat today is
`assistant_errand` (the only GPT text seat the database allows; a seat of its own for lines needs a
migration, noted for the engine). No fallback to another model: a signed-out or limited ChatGPT is a
plain failure.
"""

from __future__ import annotations

from decimal import Decimal

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

MAX_CHARS = 20_000


class GptText:
    kind = "gpt_text"

    async def run(self, ctx: StepContext) -> StepOutput:
        prompt = (ctx.prompt or "").strip()
        if not prompt:
            raise StepFailed("متن درخواست این مرحله خالی است.", code="empty_prompt")
        if len(prompt) > MAX_CHARS:
            raise StepFailed("متن درخواست این مرحله خیلی بلند است.", code="too_long")
        got = await C.ask_seat(ctx, prompt, player=str(C.setting(ctx, "player", "gpt")))
        text = str(got["text"] or "").strip()
        if not text:
            raise StepFailed("ChatGPT جواب خالی داد.", code="empty_answer", retry=True)
        return StepOutput(
            text=text,
            via="chatgpt-web",
            tokens=int(got["tokens"]),
            usd_equiv=Decimal(str(got["usd_equiv"] or 0)),
            data={"model": got["model"]},
        )


register(GptText())
