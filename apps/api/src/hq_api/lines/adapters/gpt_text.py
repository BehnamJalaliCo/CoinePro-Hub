"""`gpt_text`: the step's prompt to ChatGPT (web chat on the owner's plan), text back (§30.2).

It goes through the substitutes' seat call (domain/substitutes.py): the data guard, the launch gate,
the seat's daily cap, the 60 s pace per player and the ledger are theirs. GPT's text seat today is
`assistant_errand` (the only GPT text seat the database allows; a seat of its own for lines needs a
migration, noted for the engine). No fallback to another model: a signed-out or limited ChatGPT is a
plain failure. ⟨1.37⟩ §59.2 each text is a new temporary chat: the `chatgpt-web` recipe's text task
opens `?temporary-chat=true` for every job (one chat per job; nothing stays in the history).

⟨1.37⟩ `settings.parts: true` (a flow's script step): the answer is asked for in labelled parts
(`voice:`, `caption:`, `keyword:`, `match:`, `reply:`, `public:`; lines/adapters/_flow.py) and
read by code: the output's `text` is the narrator's part alone (what `tts` speaks and
`voice_check` hears) and `data.parts` holds every part (what `package` writes). An answer with no
voice part is a failure with a retry.
"""

from __future__ import annotations

from decimal import Decimal

from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import _flow as FW
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

MAX_CHARS = 20_000
PARTS_FA = (
    "\n\nپاسخ را دقیقاً با این برچسب‌ها بنویس، هر برچسب اول یک خط و متنش بعد از آن:\n"
    "voice: متنی که گوینده میخواند (کلمه‌ی کامنت را بلند بگوید)\n"
    "caption: کپشن با هشتگ‌ها\n"
    "keyword: همان یک کلمه‌ای که ویدیو میگوید زیر پست کامنت کنند\n"
    "reply: پیام دایرکت (چند خط مجاز است)\n"
    "public: یک جواب عمومی کوتاه و گرم با ایموجی (برای هر جواب یک خط public: جدا)\n"
    "هیچ متن دیگری بیرون از این برچسب‌ها ننویس."
)


class GptText:
    kind = "gpt_text"

    async def run(self, ctx: StepContext) -> StepOutput:
        prompt = (ctx.prompt or "").strip()
        if not prompt:
            raise StepFailed("متن درخواست این مرحله خالی است.", code="empty_prompt")
        parts = bool(C.setting(ctx, "parts", False))
        if parts:
            prompt += PARTS_FA
        if len(prompt) > MAX_CHARS:
            raise StepFailed("متن درخواست این مرحله خیلی بلند است.", code="too_long")
        got = await C.ask_seat(ctx, prompt, player=str(C.setting(ctx, "player", "gpt")))
        text = str(got["text"] or "").strip()
        if not text:
            raise StepFailed("ChatGPT جواب خالی داد.", code="empty_answer", retry=True)
        data: dict[str, object] = {"model": got["model"]}
        if parts:
            found = FW.script_parts(text)
            voice = str(found.get("voice") or "").strip()
            if not voice:
                raise StepFailed(
                    "جواب ChatGPT بخش متن گوینده (voice:) را نداشت.", code="no_parts", retry=True
                )
            data.update(parts=found, full=text[:MAX_CHARS])
            text = voice
        return StepOutput(
            text=text,
            via="chatgpt-web",
            tokens=int(got["tokens"]),
            usd_equiv=Decimal(str(got["usd_equiv"] or 0)),
            data=data,
        )


register(GptText())
