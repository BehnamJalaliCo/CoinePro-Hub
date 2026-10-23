"""The legal counsel's tools and a media item's voice (agents/tools.md v1.6,
contract §22.3, §22.4; prompt 13 §3, §4).

    case.open    A1  the counsel opens a case (company, kind, title, brief, counterpart)
    case.note    A1  a note, a form's outcome or a decision on its own case;
                     `deadline` adds one
    email.draft  A1  the exact message of an email; it becomes an `email_send`
                     card for the owner's seal (nothing is ever sent here)
    mail.read    A0  the masked emails of one of the counsel's own cases
    media.voice  A2  a media item's narration with the hub's active voice

The api decides who may (OPA hq.internal, legal_voice.rego: the legal counsel;
the voice producer); every text leaves redacted, except an email's recipient
addresses, which are checked to be addresses and go as written (the owner
sees and seals exactly them). Registered with the gateway's tools on import.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

CASE = r"^LC-[0-9]{4,}$"
ADDRESS = r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$"
Kind = Literal[
    "platform_restriction", "account_appeal", "takedown", "partner_dispute", "policy_review",
    "contract_review", "compliance", "other",
]  # fmt: skip


class CounterpartIn(T.In):
    name: str = Field(default="", max_length=200)
    channel: Literal["email", "form", "portal", "other"] = "other"
    address: str | None = Field(default=None, max_length=500)


class CaseOpenIn(T.In):
    company: str = Field(pattern=T.CODE)
    title_fa: str = Field(min_length=1, max_length=300)
    kind: Kind
    brief_md: str = Field(default="", max_length=20000)
    counterpart: CounterpartIn | None = None


class DeadlineIn(T.In):
    at: datetime
    what_fa: str = Field(min_length=1, max_length=500)


class CaseNoteIn(T.In):
    ref: str = Field(pattern=CASE)
    kind: Literal["note", "form", "decision"]
    summary_fa: str = Field(min_length=1, max_length=4000)
    ref_link: str | None = Field(default=None, max_length=80)
    deadline: DeadlineIn | None = None
    status: Literal["open", "waiting_reply", "resolved"] | None = None


class EmailDraftIn(T.In):
    case: str = Field(pattern=CASE)
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=998)
    body_md: str = Field(min_length=1, max_length=100000)
    lang: Literal["fa", "en"]
    file_ids: list[str] = Field(default_factory=list, max_length=10)


class MailReadIn(T.In):
    case: str = Field(pattern=CASE)


class MediaVoiceIn(T.In):
    ref: str = Field(pattern=r"^MI-[0-9]{4,}$")
    text_fa: str = Field(min_length=1, max_length=20000)
    voice_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_.-]{1,60}$")


def _bad_address(values: list[str]) -> str | None:
    import re

    for v in values:
        if not re.fullmatch(ADDRESS, v.strip()):
            return v[:60]
    return None


def _brief(case: Any) -> Any:
    """What the counsel needs back from a case (never the whole timeline)."""
    if not isinstance(case, dict):
        return case
    return {
        k: case.get(k)
        for k in ("ref", "company", "title_fa", "kind", "status", "counsel", "deadlines")
    } | {"timeline": (case.get("timeline") or [])[-5:]}


async def case_open(api: T.Api, call: T.Call, a: CaseOpenIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True, exclude={"link"}))
    resp = await api.request(
        "POST", "/internal/v1/legal/cases", call.token, json=body, idem=call.idem("case.open")
    )
    r = T.from_response(resp)
    if r.outcome == "ok":
        r.data = _brief(r.data)
    return r


async def case_note(api: T.Api, call: T.Call, a: CaseNoteIn) -> T.Result:
    body = await T._text(a.model_dump(mode="json", exclude_none=True, exclude={"ref", "link"}))
    resp = await api.request(
        "POST",
        f"/internal/v1/legal/cases/{a.ref}/notes",
        call.token,
        json=body,
        idem=call.idem(f"case.note:{a.ref}"),
    )
    r = T.from_response(resp)
    if r.outcome == "ok":
        r.data = _brief(r.data)
    return r


async def email_draft(api: T.Api, call: T.Call, a: EmailDraftIn) -> T.Result:
    bad = _bad_address(a.to + a.cc)
    if bad is not None:
        return T.Result(
            "error",
            code="invalid_args",
            fields={"to": "not an email address"},
            hint_fa="گیرنده باید یک نشانی ایمیل درست باشد.",
        )
    body = {
        "to": [x.strip() for x in a.to],
        "cc": [x.strip() for x in a.cc],
        "subject": await T._text(a.subject),
        "body_md": await T._text(a.body_md),
        "lang": a.lang,
        "file_ids": a.file_ids,
    }
    resp = await api.request(
        "POST",
        f"/internal/v1/legal/cases/{a.case}/emails",
        call.token,
        json=body,
        idem=call.idem(f"email.draft:{a.case}"),
    )
    r = T.from_response(resp, "decision")
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {k: r.data.get(k) for k in ("case", "decision", "digest", "from", "state")} | {
            "note": "an email_send card waits for the owner's seal; nothing was sent"
        }
    return r


async def mail_read(api: T.Api, call: T.Call, a: MailReadIn) -> T.Result:
    resp = await api.request("GET", f"/internal/v1/legal/cases/{a.case}/mail", call.token)
    return T.from_response(resp, "case")


async def media_voice(api: T.Api, call: T.Call, a: MediaVoiceIn) -> T.Result:
    body = {
        "ref": a.ref,
        "text_fa": await T._text(a.text_fa),
        **({"voice_id": a.voice_id} if a.voice_id else {}),
    }
    resp = await api.request(
        "POST",
        "/internal/v1/media/voice",
        call.token,
        json=body,
        idem=call.idem(f"media.voice:{a.ref}"),
    )
    return T.from_response(resp, "job")


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "case.open": (CaseOpenIn, case_open),
    "case.note": (CaseNoteIn, case_note),
    "email.draft": (EmailDraftIn, email_draft),
    "mail.read": (MailReadIn, mail_read),
    "media.voice": (MediaVoiceIn, media_voice),
}
T.TOOLS.update(TOOLS)
