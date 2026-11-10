"""⟨1.31⟩ §48 A company's narrator: the voice and the style, set once.

The owner's order (2026-11-10): «گوینده یک بار برای همیشه تنظیم شود». Until now the voice and its
style were words in a working group's instructions that a model passed along each time. Here
they are one row for each company (`media.narrators`), and `speech.make` takes them by code
whenever the content is that company's: whatever voice or style the model asks for is put aside.
A company with no narrator set speaks as before (the model's choice, else AI Studio's default).

Who sets it: the owner (the company's page, or the working group's), and an agent that works on
the owner's own order in his session (`narrator.set`: he says «گوینده را … بگذار» there).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.lines.adapters import tts
from hq_api.principal import Principal

STYLE_MAX = 500


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
