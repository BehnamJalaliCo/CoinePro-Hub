"""⟨1.37⟩ `voice_check`: the voice against its script, by code (contract §59.2).

Gemini takes no audio file (the fault log's item 20), so this is no model: the hub's own speech to
text (§17, the worker's `Transcribe`) hears the voice, and code compares. It passes when
- the words match: at least 0.85 of the script's words are heard, in order;
- the length is within ±25% of the script's estimate (`estimate_s`, else its words at
  `words_per_min`, default 150);
- no silence is longer than 2 s (between the heard segments, at the start or at the end).
Otherwise the step fails with a retry and the engine makes its input again first (`reruns_input`:
the `tts` step named by `settings.of`, or its first input), up to this step's `max_attempts`.

Settings: `of` (the tts step), `script_from` (the script step; else the text the tts step read),
`min_match` (0.85), `length_tolerance` (0.25), `max_silence_s` (2.0), `words_per_min` (150),
`estimate_s`. With the hub's speech to text off the step fails plainly (`stt_off`, no retry; mark
it optional to let the flow go on without it).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

MIN_MATCH = 0.85
TOLERANCE = 0.25
MAX_SILENCE_S = 2.0
WORDS_PER_MIN = 150.0
TRANSCRIBE_WAIT_S = 600
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا",
                         "آ": "ا", "ؤ": "و", "ئ": "ی"})  # fmt: skip
MARKS = re.compile("[ً-ٰٟۖ-ۭـ]")
WORD = re.compile(r"[^\W_]+", re.UNICODE)
PREFIX = re.compile(r"\b(ن?می)\s+(?=\w)")  # «می روم» heard for «می‌روم»

# Tests put a fake here: (hub, file_id) -> the transcript {text, duration_s, segments}.
TRANSCRIBE_OVERRIDE: Any = None


def words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKC", text or "").translate(LETTERS).translate(FA_DIGITS)
    t = MARKS.sub("", t).replace("‌", "").lower()
    t = PREFIX.sub(r"\1", t)
    return WORD.findall(t)


def match_ratio(script: list[str], heard: list[str]) -> float:
    """The share of the script's words heard, in order."""
    if not script:
        return 0.0
    blocks = SequenceMatcher(None, script, heard, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(script)


def longest_silence(transcript: dict[str, Any]) -> float | None:
    """The longest gap without speech (start, between segments, end), or None without segments."""
    segs = [
        (float(s.get("start_s") or 0), float(s.get("end_s") or 0))
        for s in transcript.get("segments") or []
        if isinstance(s, dict)
    ]
    if not segs:
        return None
    segs.sort()
    gaps = [segs[0][0]]
    last = segs[0][1]
    for start, end in segs[1:]:
        gaps.append(start - last)
        last = max(last, end)
    total = float(transcript.get("duration_s") or 0)
    if total:
        gaps.append(total - last)
    return max(0.0, *gaps)


async def transcribe(ctx: StepContext, file_id: str) -> dict[str, Any]:
    if TRANSCRIBE_OVERRIDE is not None:
        got: dict[str, Any] = await TRANSCRIBE_OVERRIDE(ctx.hub, file_id)
        return got
    from hq_api import workflows_client

    if not getattr(ctx.hub.settings, "stt_url", ""):
        raise StepFailed("تبدیل گفتار به متن هاب خاموش است؛ صدا بازبینی نشد.", code="stt_off")
    try:
        return await workflows_client.transcribe(
            ctx.hub, file_id, min(C.timeout_of(ctx, TRANSCRIBE_WAIT_S), TRANSCRIBE_WAIT_S)
        )
    except Exception as exc:
        raise StepFailed(
            "تبدیل گفتار به متن هاب جواب نداد؛ صدا بازبینی نشد.", code="stt_off"
        ) from exc


def _n(x: float) -> str:
    return f"{x:.0f}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


class VoiceCheck:
    kind = "voice_check"
    reruns_input = True  # a voice that fails is made again (the tts step), then heard again

    async def run(self, ctx: StepContext) -> StepOutput:
        voice = C.input_with(ctx, "file_id", C.setting(ctx, "of"))
        if voice is None or not voice.file_id:
            raise StepFailed("صدایی برای بازبینی از قدم صدا نرسید.", code="no_voice")
        named = ctx.inputs.get(str(C.setting(ctx, "script_from") or ""))
        script_text = str(
            (named.text if named is not None else None)
            or next((o.text for k, o in ctx.inputs.items() if o is not voice and o.text), None)
            or ""
        )
        script = words(script_text)
        if not script:
            raise StepFailed("متن سناریو برای سنجش صدا نرسید.", code="no_script")
        heard_doc = await transcribe(ctx, str(voice.file_id))
        heard = words(str(heard_doc.get("text") or ""))
        ratio = match_ratio(script, heard)
        duration = float(heard_doc.get("duration_s") or 0)
        wpm = float(C.setting(ctx, "words_per_min", WORDS_PER_MIN))
        estimate = float(C.setting(ctx, "estimate_s") or 0) or len(script) / wpm * 60
        tolerance = float(C.setting(ctx, "length_tolerance", TOLERANCE))
        silence = longest_silence(heard_doc)
        max_silence = float(C.setting(ctx, "max_silence_s", MAX_SILENCE_S))
        problems: list[str] = []
        if ratio < float(C.setting(ctx, "min_match", MIN_MATCH)):
            problems.append(f"فقط {_n(ratio * 100)}٪ کلمه‌های سناریو شنیده شد")
        if duration and abs(duration - estimate) > tolerance * estimate:
            problems.append(f"طول صدا {_n(duration)} ثانیه است، نه حدود {_n(estimate)} ثانیه")
        if silence is not None and silence > max_silence:
            problems.append(f"یک سکوت {_n(silence)} ثانیه‌ای دارد")
        data = {"match": round(ratio, 3), "duration_s": duration, "estimate_s": round(estimate, 1),
                "longest_silence_s": silence, "words": len(script), "heard": len(heard)}  # fmt: skip
        if problems:
            raise StepFailed(
                "صدا با سناریو نخواند: " + "؛ ".join(problems) + ".",
                code="voice_mismatch",
                retry=True,
            )
        return StepOutput(
            text=f"صدا با سناریو خواند ({_n(ratio * 100)}٪ کلمه‌ها، {_n(duration)} ثانیه).",
            file_id=str(voice.file_id),
            files=(str(voice.file_id),),
            via="stt",
            data=data,
        )


register(VoiceCheck())
