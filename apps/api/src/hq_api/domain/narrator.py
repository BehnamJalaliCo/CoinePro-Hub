"""⟨1.31⟩ §48 A company's narrator: the voice and the style, set once.

The owner's order (2026-11-10): «گوینده یک بار برای همیشه تنظیم شود». Until now the voice and its
style were words in a working group's instructions that a model passed along each time. Here
they are one row for each company (`media.narrators`), and `speech.make` takes them by code
whenever the content is that company's: whatever voice or style the model asks for is put aside.
A company with no narrator set speaks as before (the model's choice, else AI Studio's default).

Who sets it: the owner (the company's page, or the working group's), and an agent that works on
the owner's own order in his session (`narrator.set`: he says «گوینده را … بگذار» there).

⟨1.37⟩ §59.4 the use form's «بشنو»: `sample()` speaks a short sentence (at most about eight
seconds) in a voice and style before the owner chooses; Gemini's API first, as every speech
(domain/speech_make.py: on the voice meter, the treasury), the AI Studio page second; the same
voice, style and words are made once a day (the file is kept on the holding).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.lines.adapters import tts
from hq_api.principal import Principal

STYLE_MAX = 500
SAMPLE_FA = "سلام! این نمونه‌ی کوتاهی از صدای گوینده است؛ ببین به کار این شرکت میآید یا نه."
SAMPLE_CHARS = 100  # about eight seconds of Persian speech
SAMPLE_WEB_S = 120  # the AI Studio page, when the API does not speak
SAMPLE_FAILED_FA = "نمونه‌ی صدا الان ساخته نشد؛ کمی بعد دوباره امتحان کن."


class VoiceOption(BaseModel):
    name: str
    gender: str
    trait_fa: str


class Narrator(BaseModel):
    """`set: false`: the company has none yet (`voice` is then AI Studio's default, which a model
    may still override). `voices`: AI Studio's prebuilt speakers. `aistudio`: whether the hub's
    browser is signed in to it (`signed_in`, `signed_out`, `unknown`)."""

    company: str
    set: bool = False
    voice: str = tts.DEFAULT_VOICE
    style_fa: str = ""
    by: str | None = None
    updated_at: datetime | None = None
    voices: list[VoiceOption] = Field(default_factory=list)
    aistudio: str = "unknown"


def voices() -> list[VoiceOption]:
    return [VoiceOption(name=n, gender=g, trait_fa=t) for n, g, t in tts.DOCUMENTED]


def canonical(voice: str) -> str:
    """The voice as AI Studio names it, or 422."""
    for name, _, _ in tts.DOCUMENTED:
        if name.lower() == voice.strip().lower():
            return str(name)
    names = "، ".join(v[0] for v in tts.DOCUMENTED[:6])
    raise ApiError(
        422,
        "validation_failed",
        fields={"voice": "not one of AI Studio's prebuilt voices"},
        message_fa=f"صدای «{voice[:30]}» در ای‌آی استودیو نیست؛ یکی از صداهای آماده مثل {names}.",
    )


async def of(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    row = await tx.first("SELECT * FROM media.narrators WHERE company_id = :co", co=company_id)
    return dict(row) if row is not None else None


async def put(
    tx: Tx, company_id: UUID, *, voice: str, style_fa: str | None, by: Principal
) -> dict[str, Any]:
    name = canonical(voice)
    style = " ".join((style_fa or "").split())[:STYLE_MAX]
    kind = "owner" if by.kind == "owner" else "agent"
    return dict(
        await tx.one(
            """INSERT INTO media.narrators (company_id, voice, style_fa, by_kind, by_code)
               VALUES (:co, :v, :s, :bk, :bc)
               ON CONFLICT (company_id) DO UPDATE
               SET voice = EXCLUDED.voice, style_fa = EXCLUDED.style_fa,
                   by_kind = EXCLUDED.by_kind, by_code = EXCLUDED.by_code, updated_at = now()
               RETURNING *""",
            co=company_id,
            v=name,
            s=style,
            bk=kind,
            bc=str(by.code)[:64],
        )
    )


async def render(tx: Tx, company: Any, *, full: bool = True) -> Narrator:
    row = await of(tx, company.id)
    state = "unknown"
    if full:
        from hq_api.domain import speech_make as SM

        state = (await SM.speech_state(tx))["aistudio"]
    if row is None:
        return Narrator(company=company.code, voices=voices() if full else [], aistudio=state)
    return Narrator(
        company=company.code, set=True, voice=row["voice"], style_fa=row["style_fa"],
        by=row["by_code"], updated_at=row["updated_at"], voices=voices() if full else [],
        aistudio=state,
    )  # fmt: skip


async def for_work(tx: Tx, who: Principal) -> tuple[UUID | None, dict[str, Any] | None]:
    """Whose content an agent's voice is for: the company of its run's work (a holding role
    working on a company's order speaks with that company's narrator), else its own. Returns
    (that company's id, its narrator row or None)."""
    company_id = who.company_id
    if who.run_id:
        wid = await tx.scalar(
            """SELECT w.company_id FROM agents.runs r JOIN work.work w ON w.id = r.work_id
               WHERE r.id = CAST(:r AS uuid) AND r.employee_id = :e""",
            r=who.run_id,
            e=who.employee_id,
        )
        company_id = wid or company_id
    if company_id is None:
        return None, None
    return company_id, await of(tx, company_id)


# ------------------------------------------------------------- §59.4 a sample --
class SampleFile(BaseModel):
    id: str
    name: str
    mime: str
    size: int


class NarratorSample(BaseModel):
    file: SampleFile


def sample_text(text_fa: str | None) -> str:
    """The words of a sample: the owner's (else the hub's sentence), cut to about 8 seconds."""
    text = " ".join((text_fa or "").split()) or SAMPLE_FA
    if len(text) <= SAMPLE_CHARS:
        return text
    cut = text.rfind(" ", 0, SAMPLE_CHARS)
    return text[: cut if cut > 0 else SAMPLE_CHARS].strip()


def sample_key(voice: str, style: str, text: str) -> str:
    return hashlib.sha256(f"{voice}\n{style}\n{text}".encode()).hexdigest()


async def sample(
    hub: Any, who: Principal, *, voice: str, style_fa: str | None, text_fa: str | None
) -> NarratorSample:
    """`POST /narrators/sample`: a short voice to hear, made once a day per (voice, style, words)."""
    from hq_api import audit
    from hq_api.domain import files as F
    from hq_api.domain import speech_make as SM
    from hq_api.lines.base import StepFailed

    name = canonical(voice)
    style = " ".join((style_fa or "").split())[:STYLE_MAX]
    text = sample_text(text_fa)
    key = sample_key(name, style, text)
    holding = await hub.companies.holding()
    q = """SELECT id, name, mime, size FROM files.files
           WHERE company_id = :co AND meta ->> 'narrator_sample' = :k
             AND created_at > now() - interval '1 day' ORDER BY created_at DESC LIMIT 1"""
    async with hub.db.tx([holding.id]) as tx:
        hit = await tx.first(q, co=holding.id, k=key)
    if hit is not None:
        return NarratorSample(file=SampleFile(
            id=str(hit["id"]), name=hit["name"], mime=hit["mime"], size=int(hit["size"]),
        ))  # fmt: skip
    job = {"job": key[:16], "company_id": holding.id, "company": holding.code,
           "by": who.code, "text": text, "voice": name, "style": style}  # fmt: skip
    got = await SM.api_speak(hub, job)
    if got is None:
        try:
            got = await tts.speak(hub, text, voice=name, style=style, timeout_s=SAMPLE_WEB_S)
        except StepFailed as exc:
            raise ApiError(
                503, "channel_not_configured", f"no voice: {exc.code}", message_fa=SAMPLE_FAILED_FA
            ) from exc
    data, mime = got
    storage_key, sha = await hub.storage.put(data)
    async with hub.db.tx([holding.id]) as tx:
        fid = await F.insert(
            tx, company_id=holding.id, name=f"narrator-{name.lower()}.{tts.ext(mime)}", mime=mime,
            size=len(data), sha256=sha, storage_key=storage_key, kind="audio",
            by_kind="owner" if who.kind == "owner" else "service", by_code=str(who.code)[:64],
            meta={"narrator_sample": key, "voice": name},
        )  # fmt: skip
        await audit.record(
            tx, who, company_id=holding.id, action="narrator.sample", action_class="A1",
            target_kind="file", target_ref=str(fid),
            summary=f"a sample of {name}" + (" with a style" if style else "") + f", {len(text)} chars",
        )  # fmt: skip
    return NarratorSample(file=SampleFile(id=str(fid), name=f"narrator-{name.lower()}.{tts.ext(mime)}",
                                          mime=mime, size=len(data)))  # fmt: skip
