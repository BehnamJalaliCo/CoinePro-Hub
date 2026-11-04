"""`tts`: text to speech with Gemini TTS in Google AI Studio, the owner's account (§30.2).

The egress recipe `aistudio-web` (infra/egress/recipes/aistudio-web.yaml) opens AI Studio's speech
page in the hub's own browser profile, picks `settings.voice` (a prebuilt speaker's name), writes
`settings.style`, pastes the text, generates and downloads the audio. The profile is its own (one
recipe, one profile, one lock) and is signed in once by the owner with `make aistudio-web-login`
(the same Google account as the Gemini profile; the sessions are not shared between profiles).

Settings: `voice` (speaker name, default Kore), `style` (a style note in plain words, optional).
The text to speak is the first input step's text (`settings.text_from` names another), else the prompt.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

log = logging.getLogger("hq_api.lines.tts")
ACCOUNT = "aistudio-web"
DEFAULT_VOICE = "Kore"
MAX_CHARS = 5_000  # one generation; a longer text is cut into lines by the script step
CACHE_S = 24 * 3600

# AI Studio's documented prebuilt speakers (Gemini speech generation), used when no live list is
# available: (name, gender, trait in Persian). A fallback, labelled as such in the list.
DOCUMENTED = (
    ("Zephyr", "female", "روشن"), ("Puck", "male", "سرزنده"), ("Charon", "male", "اطلاع‌رسان"),
    ("Kore", "female", "محکم"), ("Fenrir", "male", "پرشور"), ("Leda", "female", "جوان"),
    ("Orus", "male", "محکم"), ("Aoede", "female", "نرم و هوایی"), ("Callirrhoe", "female", "راحت"),
    ("Autonoe", "female", "روشن"), ("Enceladus", "male", "نفس‌دار"), ("Iapetus", "male", "شفاف"),
    ("Umbriel", "male", "راحت"), ("Algieba", "male", "نرم"), ("Despina", "female", "نرم"),
    ("Erinome", "female", "شفاف"), ("Algenib", "male", "خش‌دار"), ("Rasalgethi", "male", "اطلاع‌رسان"),
    ("Laomedeia", "female", "سرزنده"), ("Achernar", "female", "آرام"), ("Alnilam", "male", "محکم"),
    ("Schedar", "male", "یکنواخت"), ("Gacrux", "female", "پخته"), ("Pulcherrima", "female", "رو به جلو"),
    ("Achird", "male", "دوستانه"), ("Zubenelgenubi", "male", "خودمانی"),
    ("Vindemiatrix", "female", "ملایم"), ("Sadachbia", "male", "پرجنب‌وجوش"),
    ("Sadaltager", "male", "دانا"), ("Sulafat", "female", "گرم"),
)  # fmt: skip
_cache: dict[str, Any] = {"at": 0.0, "rows": []}


async def voices(hub: Any = None, *, now: float | None = None) -> list[dict[str, Any]]:
    """`GET /tts/voices` (contract §30.5): [{name, title_fa, gender, sample_file, source}], cached a day.

    AI Studio has no list API the hub may read, so the list is its documented prebuilt speakers,
    labelled `source: "documented"`; a live list (when one is wired) replaces it with
    `source: "live"`. `sample_file` is null until the owner adds samples to the library.
    """
    t = time.monotonic() if now is None else now
    if _cache["rows"] and t - float(_cache["at"]) < CACHE_S:
        return [dict(r) for r in _cache["rows"]]
    rows = [
        {
            "name": name,
            "title_fa": f"{name} · {trait}",
            "gender": gender,
            "sample_file": None,
            "source": "documented",
        }
        for name, gender, trait in DOCUMENTED
    ]
    _cache["rows"], _cache["at"] = rows, t
    return [dict(r) for r in rows]


def known_voice(name: str) -> bool:
    return name.lower() in {v[0].lower() for v in DOCUMENTED}


class Tts:
    kind = "tts"

    async def run(self, ctx: StepContext) -> StepOutput:
        voice = str(C.setting(ctx, "voice", DEFAULT_VOICE)).strip()
        style = str(C.setting(ctx, "style", "") or "").strip()
        src = C.first_input(ctx, C.setting(ctx, "text_from"))
        text = str((src.text if src is not None else None) or ctx.prompt or "").strip()
        if not text:
            raise StepFailed("متنی برای صداگذاری نیست.", code="empty_text")
        if len(text) > MAX_CHARS:
            raise StepFailed(
                f"متن برای یک بار صداگذاری بلند است ({len(text)} نویسه؛ سقف {MAX_CHARS}).",
                code="too_long",
            )
        if not known_voice(voice):
            log.info("tts voice not in the documented list", extra={"voice": voice})
        got = await C.web_job(
            ctx.hub,
            account=ACCOUNT,
            task="tts",
            prompt=text,
            timeout_s=C.timeout_of(ctx, 240),
            voice=voice,
            style=style or None,
        )
        data, _name, mime = C.decode_b64(got.get("file"))
        if not mime.startswith("audio/"):
            raise StepFailed("چیزی که از ای‌آی استودیو آمد صدا نبود.", code="not_audio", retry=True)
        co = await C.company_of(ctx)
        fid = await C.store_file(
            ctx.hub,
            co.id,
            data,
            name=f"{ctx.run_ref}-{ctx.step.get('key', 'voice')}.{_ext(mime)}",
            mime=mime,
        )
        return StepOutput(
            file_id=str(fid),
            files=(str(fid),),
            via=ACCOUNT,
            data={"voice": voice, "style": style, "mime": mime, "bytes": len(data)},
        )


def _ext(mime: str) -> str:
    return {"audio/wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/flac": "flac"}.get(
        mime, "bin"
    )


register(Tts())
