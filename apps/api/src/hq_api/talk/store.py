"""The talk's records (contract §32.1, §32.8): conversations, turns, cards,
the turns' stream events and the owner's memory, and their API shapes.

Every model name starts with `Talk` (unique across the whole API, so OpenAPI
never renames one). Conversations are the owner's: their rows carry the
holding's company_id; a manager's turns and cards carry its company's.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.errors import ApiError

Mode = Literal["consult", "work"]
Source = Literal["typed", "hold", "handsfree"]
TurnState = Literal["streaming", "done", "stopped", "failed"]
CardKind = Literal[
    "order", "ask", "hire", "decision", "planner", "rule", "automation", "minutes", "invite"
]
CardState = Literal["offered", "done", "dismissed", "failed"]
EVENT_TYPES = ("text", "say", "audio", "card", "invite", "meter", "tool", "done", "error")
FINAL = ("done", "stopped", "failed")


# ------------------------------------------------------------------ shapes --
class TalkVoice(BaseModel):
    engine: str
    voice: str
    rate: float = Field(ge=0.8, le=1.25)


class TalkBrain(BaseModel):
    task_class: Literal["talk_turn"] = "talk_turn"
    effort: Literal["low", "medium", "high", "xhigh", "max"]


class TalkPersona(BaseModel):
    key: str
    kind: Literal["secretary", "overseer", "assistant", "advisor", "manager"]
    role: str
    title_fa: str
    company: str | None
    voice: TalkVoice
    brain: TalkBrain
    tools: list[str]
    face: str | None
    consult_only: bool
    # ⟨additive⟩ the card kinds this persona may offer
    cards: list[CardKind]


class TalkCost(BaseModel):
    tokens: int
    usd_equiv: Decimal
    voice_usd: Decimal


class TalkConversation(BaseModel):
    ref: str
    title_fa: str
    persona: str
    present: list[str]
    mode: Mode
    started_at: datetime
    last_turn_at: datetime | None
    turns: int
    summary_fa: str | None
    cost: TalkCost
    open_cards: int
    # ⟨1.16⟩ §34.2 the owner's order this talk is the live line of (F-…), or null
    order_ref: str | None = None


class TalkAudio(BaseModel):
    seq: int
    file_id: str
    seconds: float
    engine: str


class TalkTokens(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


class TalkVoiceUse(BaseModel):
    engine: str
    seconds: float
    audio_tokens: int
    usd: Decimal


class TalkCard(BaseModel):
    id: UUID
    turn: UUID
    kind: CardKind
    title_fa: str
    body_fa: str
    payload: dict[str, Any]
    state: CardState
    made: list[str]
    reason_fa: str | None


class TalkTurn(BaseModel):
    id: UUID
    conversation: str
    n: int
    by: str  # "owner" | a persona key
    source: Literal["typed", "hold", "handsfree", "system"]
    text: str
    say_fa: str | None
    show_md: str | None
    cards: list[TalkCard]
    audio: list[TalkAudio]
    tokens: TalkTokens
    voice: TalkVoiceUse | None
    state: TurnState
    reason_fa: str | None
    at: datetime


class TalkTurnPage(BaseModel):
    items: list[TalkTurn]
    next_cursor: str | None = None


class TalkConversationDetail(TalkConversation):
    # ⟨additive⟩ the turns page (oldest first from the cursor) and the personas present
    turns_page: TalkTurnPage
    personas: list[TalkPersona]


class TalkTurnAccepted(BaseModel):
    turn: TalkTurn  # the persona's answer, streaming
    # ⟨additive⟩ the owner's words as stored (a key already removed); null for /minutes
    owner_turn: TalkTurn | None
    events: str  # the SSE path of the answer


class TalkCardRun(BaseModel):
    made: list[str]
    card: TalkCard


# ------------------------------------------------------------------ render --
def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def render_card(r: dict[str, Any]) -> TalkCard:
    return TalkCard(
        id=r["id"],
        turn=r["turn_id"],
        kind=r["kind"],
        title_fa=r["title_fa"],
        body_fa=r["body_fa"],
        payload=_j(r["payload"]) or {},
        state=r["state"],
        made=list(r["made"] or []),
        reason_fa=r["reason_fa"],
    )


def render_turn(r: dict[str, Any], ref: str, cards: list[dict[str, Any]]) -> TalkTurn:
    tokens = _j(r["tokens"]) or {}
    voice = _j(r["voice"])
    return TalkTurn(
        id=r["id"],
        conversation=ref,
        n=r["n"],
        by="owner" if r["by_kind"] == "owner" else str(r["persona"]),
        source=r["source"],
        text=r["text"],
        say_fa=r["say_fa"],
        show_md=r["show_md"],
        cards=[render_card(c) for c in cards],
        audio=[TalkAudio(**a) for a in _j(r["audio"]) or []],
        tokens=TalkTokens(**{k: int(tokens.get(k) or 0) for k in TalkTokens.model_fields}),
        voice=TalkVoiceUse(**voice) if isinstance(voice, dict) and voice.get("engine") else None,
        state=r["state"],
        reason_fa=r["reason_fa"],
        at=r["at"],
    )


async def render_conversation(tx: Tx, r: dict[str, Any]) -> TalkConversation:
    open_cards = await tx.scalar(
        "SELECT count(*) FROM talk.cards WHERE conversation_id = :c AND state = 'offered'",
        c=r["id"],
    )
    return TalkConversation(
        ref=r["ref"],
        title_fa=r["title_fa"],
        persona=r["persona"],
        present=list(r["present"] or []),
        mode=r["mode"],
        started_at=r["started_at"],
        last_turn_at=r["last_turn_at"],
        turns=r["turns"],
        summary_fa=r["summary_fa"],
        cost=TalkCost(
            tokens=int(r["tokens"]),
            usd_equiv=Decimal(r["usd_equiv"]),
            voice_usd=Decimal(r["voice_usd"]),
        ),
        open_cards=int(open_cards or 0),
        order_ref=r.get("order_ref"),
    )


# -------------------------------------------------------------------- read --
NOT_FOUND_FA = "این گفتگو پیدا نشد."


async def conversation(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM talk.conversations WHERE ref = :r"  # noqa: S608 - constants only
        + (" FOR UPDATE" if lock else ""),
        r=ref,
    )
    if row is None:
        raise ApiError(404, "not_found", "unknown conversation", message_fa=NOT_FOUND_FA)
    return dict(row)


async def turn(tx: Tx, turn_id: UUID | str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        """SELECT t.*, c.ref AS conversation_ref FROM talk.turns t
           JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE t.id = CAST(:id AS uuid)"""  # noqa: S608 - constants only
        + (" FOR UPDATE OF t" if lock else ""),
        id=str(turn_id),
    )
    if row is None:
        raise ApiError(404, "not_found", "unknown turn", message_fa="این نوبت پیدا نشد.")
    return dict(row)


async def cards_of(tx: Tx, turn_ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    out: dict[UUID, list[dict[str, Any]]] = {t: [] for t in turn_ids}
    if not turn_ids:
        return out
    for c in await tx.all(
        "SELECT * FROM talk.cards WHERE turn_id = ANY(:ids) ORDER BY created_at, id", ids=turn_ids
    ):
        out.setdefault(c["turn_id"], []).append(dict(c))
    return out


async def turn_out(tx: Tx, turn_id: UUID | str) -> TalkTurn:
    t = await turn(tx, turn_id)
    cards = await cards_of(tx, [t["id"]])
    return render_turn(t, t["conversation_ref"], cards[t["id"]])


async def last_turns(
    tx: Tx, conversation_id: UUID, limit: int, *, before_n: int
) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT * FROM talk.turns WHERE conversation_id = :c AND n < :n AND state <> 'failed'
           ORDER BY n DESC LIMIT :l""",
        c=conversation_id,
        n=before_n,
        l=limit,
    )
    return [dict(r) for r in reversed(rows)]


# ------------------------------------------------------------------- write --
async def add_event(
    tx: Tx, turn_id: UUID | str, company_id: UUID, type_: str, data: dict[str, Any]
) -> int:
    """One event of a turn's stream, in order (the SSE route reads them)."""
    seq: int = await tx.scalar(
        """INSERT INTO talk.turn_events (turn_id, company_id, seq, type, data)
           SELECT CAST(:t AS uuid), :co,
                  COALESCE((SELECT max(seq) FROM talk.turn_events WHERE turn_id = CAST(:t AS uuid)), 0) + 1,
                  :ty, CAST(:d AS jsonb)
           RETURNING seq""",
        t=str(turn_id),
        co=company_id,
        ty=type_,
        d=json.dumps(data, ensure_ascii=False, default=str),
    )
    return seq


async def add_card(
    tx: Tx,
    *,
    conversation_id: UUID,
    turn_id: UUID,
    company_id: UUID,
    kind: str,
    title_fa: str,
    body_fa: str,
    payload: dict[str, Any],
    unsolicited: bool = False,
) -> dict[str, Any]:
    row = await tx.one(
        """INSERT INTO talk.cards (conversation_id, turn_id, company_id, kind, title_fa, body_fa,
               payload, unsolicited)
           VALUES (:c, :t, :co, :k, :ti, :b, CAST(:p AS jsonb), :u) RETURNING *""",
        c=conversation_id,
        t=turn_id,
        co=company_id,
        k=kind,
        ti=title_fa[:200],
        b=body_fa[:8000],
        p=json.dumps(payload, ensure_ascii=False, default=str),
        u=unsolicited,
    )
    return dict(row)


async def remember(tx: Tx, company_id: UUID, fact_fa: str, turn_id: UUID | None) -> None:
    await tx.exec(
        "INSERT INTO talk.memory (company_id, fact_fa, turn_id) VALUES (:co, :f, :t)",
        co=company_id,
        f=fact_fa[:2000],
        t=turn_id,
    )


async def memory(tx: Tx, limit: int = 30) -> list[str]:
    rows = await tx.all(
        "SELECT fact_fa FROM talk.memory ORDER BY created_at DESC LIMIT :l", l=limit
    )
    return [r["fact_fa"] for r in reversed(rows)]
