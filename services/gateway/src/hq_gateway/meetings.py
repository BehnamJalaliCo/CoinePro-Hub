"""The meeting room's agent tools (agents/tools.md v1.5 "Governance", contract
§20.1; prompt 11 §1, §11). The meeting itself is run by code (agenda, speakers,
turn order, budget, claim checks, the minutes); these tools only carry one
speaker's words to the api, which decides whether the call fits the meeting.

    meeting.statement  A1  a speaker's turn (statement, claims, a draft, a vote),
                           only inside a run with trigger `meeting`
    meeting.challenge  A1  the devil's advocate's challenge (oversight roles)
    meeting.whisper    A1  the advisor's note to the owner only (never the meeting)
    meeting.item       A1  an agenda item for the next meeting of a type
    meeting.minutes    A1  the secretary's summary, from sourced claims only

Every claim carries its source; the api checks it like a message citation
(§16.3) and marks it `unsourced` otherwise, or refuses an expired knowledge
entry (`422 knowledge_expired`); a meeting that is not live answers
`409 meeting_not_live`. Every text an agent writes leaves redacted (never
shortened: the input models refuse anything above the caps), and every write
carries its Idempotency-Key. Registered with the gateway's tools on import
(gateway.py).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, StrictInt

from hq_gateway import tools as T

MEETING = r"^MT-[0-9]{4,}$"
KREF = r"^K-[0-9]{4,}$"
CODE = T.CODE


class SourceIn(T.In):
    """A source of a claim, an item or a knowledge entry: `{kind, ref, note}`."""

    kind: str = Field(pattern=r"^[a-z][a-z_]{1,20}$")
    ref: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class ClaimIn(T.In):
    text_fa: str = Field(min_length=1, max_length=1000)
    source: SourceIn | None = None


class StanceIn(T.In):
    """A round-2 vote on a draft; a manager's vote never replaces the owner's seal."""

    draft: str | None = Field(default=None, pattern=T.UUID_RE)
    vote: Literal["support", "oppose", "abstain"]
    reason_fa: str = Field(min_length=1, max_length=500)


class StatementIn(T.In):
    meeting: str = Field(pattern=MEETING)
    item: StrictInt = Field(ge=1, le=50)
    statement_md: str = Field(min_length=1, max_length=8000)
    claims: list[ClaimIn] = Field(default_factory=list, max_length=20)
    draft_md: str | None = Field(default=None, max_length=8000)
    stance: StanceIn | None = None


class ChallengeIn(T.In):
    meeting: str = Field(pattern=MEETING)
    item: StrictInt = Field(ge=1, le=50)
    claim: str | None = Field(default=None, pattern=T.UUID_RE)
    statement_md: str = Field(min_length=1, max_length=8000)
    claims: list[ClaimIn] = Field(default_factory=list, max_length=20)


class WhisperIn(T.In):
    meeting: str = Field(pattern=MEETING)
    item: StrictInt = Field(ge=1, le=50)
    text_md: str = Field(min_length=1, max_length=4000)
    sources: list[SourceIn] = Field(default_factory=list, max_length=10)


class ItemIn(T.In):
    type: Literal["board", "company", "strategy", "postmortem"]
    company: str = Field(pattern=CODE)
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=8000)
    sources: list[SourceIn] = Field(default_factory=list, max_length=10)


class MinutesIn(T.In):
    meeting: str = Field(pattern=MEETING)
    summary_md: str = Field(min_length=1, max_length=4000)


# ------------------------------------------------------------ redaction --
async def sources_out(sources: list[SourceIn]) -> list[dict[str, Any]]:
    """Sources as sent: kind and ref as written (the api checks the ref like a
    citation), the agent's note redacted."""
    out: list[dict[str, Any]] = []
    for s in sources:
        row: dict[str, Any] = {"kind": s.kind, "ref": s.ref}
        if s.note is not None:
            row["note"] = await T._text(s.note)
        out.append(row)
    return out


async def _claims(claims: list[ClaimIn]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in claims:
        row: dict[str, Any] = {"text_fa": await T._text(c.text_fa)}
        if c.source is not None:
            row["source"] = (await sources_out([c.source]))[0]
        out.append(row)
    return out


# ------------------------------------------------------------- the tools --
async def meeting_statement(api: T.Api, call: T.Call, a: StatementIn) -> T.Result:
    body: dict[str, Any] = {
        "item": a.item,
        "statement_md": await T._text(a.statement_md),
        "claims": await _claims(a.claims),
    }
    if a.draft_md is not None:
        body["draft_md"] = await T._text(a.draft_md)
    if a.stance is not None:
        stance: dict[str, Any] = {
            "vote": a.stance.vote,
            "reason_fa": await T._text(a.stance.reason_fa),
        }
        if a.stance.draft is not None:
            stance["draft"] = a.stance.draft
        body["stance"] = stance
    resp = await api.request(
        "POST", f"/internal/v1/meetings/{a.meeting}/statement", call.token, json=body,
        idem=call.idem("meeting.statement"),
    )  # fmt: skip
    return T.from_response(resp)


async def meeting_challenge(api: T.Api, call: T.Call, a: ChallengeIn) -> T.Result:
    body: dict[str, Any] = {
        "item": a.item,
        "statement_md": await T._text(a.statement_md),
        "claims": await _claims(a.claims),
    }
    if a.claim is not None:
        body["claim"] = a.claim
    resp = await api.request(
        "POST", f"/internal/v1/meetings/{a.meeting}/challenge", call.token, json=body,
        idem=call.idem("meeting.challenge"),
    )  # fmt: skip
    return T.from_response(resp)


async def meeting_whisper(api: T.Api, call: T.Call, a: WhisperIn) -> T.Result:
    body = {
        "item": a.item,
        "text_md": await T._text(a.text_md),
        "sources": await sources_out(a.sources),
    }
    resp = await api.request(
        "POST", f"/internal/v1/meetings/{a.meeting}/whisper", call.token, json=body,
        idem=call.idem("meeting.whisper"),
    )  # fmt: skip
    return T.from_response(resp)


async def meeting_item(api: T.Api, call: T.Call, a: ItemIn) -> T.Result:
    body = {
        "type": a.type,
        "company": a.company,
        "title_fa": await T._text(a.title_fa),
        "brief_md": await T._text(a.brief_md),
        "sources": await sources_out(a.sources),
    }
    resp = await api.request(
        "POST", "/internal/v1/meetings/items", call.token, json=body,
        idem=call.idem("meeting.item"),
    )  # fmt: skip
    return T.from_response(resp)


async def meeting_minutes(api: T.Api, call: T.Call, a: MinutesIn) -> T.Result:
    resp = await api.request(
        "POST", f"/internal/v1/meetings/{a.meeting}/minutes", call.token,
        json={"summary_md": await T._text(a.summary_md)}, idem=call.idem("meeting.minutes"),
    )  # fmt: skip
    return T.from_response(resp)


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "meeting.statement": (StatementIn, meeting_statement),
    "meeting.challenge": (ChallengeIn, meeting_challenge),
    "meeting.whisper": (WhisperIn, meeting_whisper),
    "meeting.item": (ItemIn, meeting_item),
    "meeting.minutes": (MinutesIn, meeting_minutes),
}

# Registered with the gateway's tools (tools.py itself knows nothing of these).
T.TOOLS.update(TOOLS)
