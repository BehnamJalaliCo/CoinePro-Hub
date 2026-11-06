"""Who speaks in a conversation (contract §32.1, §32.4): a persona is a charter,
a voice, a brain setting and a tool allow-list, all data.

The fixed personas (secretary, overseer, assistant, advisor) are the holding's
employees with those charters; `manager` is a template: `role@CODE` is the
employee of company CODE whose charter is `role` (ceo@TY, media_director@FX).
A persona's read tools are its charter's A0 tools (intersected with the
persona file's list): talking never writes anything (§32 "Talking is A0").
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.talk import data
from hq_api.voice.base import VoiceChoice

KEY = re.compile(
    r"^(?:(secretary|overseer|assistant|advisor)|([a-z][a-z0-9_]{1,40})@([A-Z][A-Z0-9]{1,9})"
    r"|player:(gpt|gemini|deepseek))$"
)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
FIXED = ("secretary", "overseer", "assistant", "advisor")
# ⟨1.17⟩ §35.4 a player in a session: ChatGPT, Gemini or DeepSeek through its substitute seat
PLAYER_FA = {"gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
# ⟨2026-11-06⟩ A0 in every charter, but never a talk read: in talk it would answer `queued` and land as
# a work item; a player comes into a session as a participant (the `invite` card with `player`)
NOT_IN_TALK = ("substitute.call",)


@dataclass(frozen=True)
class Persona:
    key: str  # "secretary" | "ceo@TY" | "player:gpt"
    kind: str  # secretary | overseer | assistant | advisor | manager | player
    role: str  # the charter (a player: "player")
    title_fa: str
    company: str  # the persona's company code (the holding's for the fixed four)
    company_id: UUID
    is_manager: bool
    employee: dict[str, Any] | None  # {id, code, company_id, department, status}; None = no reads
    voice: VoiceChoice
    effort: str
    tools: tuple[str, ...]
    cards: tuple[str, ...]
    consult_only: bool
    face: str | None

    @property
    def company_code(self) -> str | None:
        """The API's `company`: only a manager names one."""
        return self.company if self.is_manager else None

    @property
    def is_player(self) -> bool:
        return self.kind == "player"

    @property
    def player(self) -> str | None:
        """gpt | gemini | deepseek for a player persona."""
        return self.key.split(":", 1)[1] if self.is_player else None


def parse(key: str) -> tuple[str, str | None, str | None]:
    """(kind, role, company) of a persona key; 404 for anything else."""
    m = KEY.match(key or "")
    if m is None:
        raise ApiError(404, "not_found", "unknown persona", message_fa="این نقش در گفتگو نیست.")
    if m.group(1):
        return m.group(1), None, None
    if m.group(4):
        return "player", m.group(4), None
    return "manager", m.group(2), m.group(3)


def read_tools(lib: Any, role: str, wanted: tuple[str, ...] | None) -> tuple[str, ...]:
    """The A0 tools of the charter (and of the persona's list, when it has one)."""
    charter = lib.get(role) if lib is not None else None
    if charter is None:
        return ()
    reads = [
        t
        for t in charter.tools
        if t in lib.tools and lib.tools[t].cls == "A0" and t not in NOT_IN_TALK
    ]
    return tuple(t for t in reads if wanted is None or t in wanted)


def default_voice(key: str, kind: str) -> VoiceChoice:
    v = data.voices()
    engine = str(v.get("engine") or "piper")
    if kind != "manager":
        p = (v.get("personas") or {}).get(kind) or {}
        return VoiceChoice(engine, str(p.get("voice") or ""), float(p.get("rate") or 1.0))
    pool = v.get("pool") or [{"voice": "", "rate": 1.0}]
    # stable for a role@company until it is stored (then the stored one is kept)
    i = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(pool)
    return VoiceChoice(engine, str(pool[i]["voice"]), float(pool[i].get("rate") or 1.0))


async def _employee(
    tx: Tx, role: str, company_id: UUID, prefer: str | None = None
) -> dict[str, Any] | None:
    """The company's employee of that charter; `prefer` names the one meant (⟨1.17⟩ an order's
    holder, so the persona never resolves to another employee of the same charter)."""
    return await tx.first(
        """SELECT e.id, e.code, e.company_id, e.kind, e.title_fa, e.status, d.code AS department
           FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND e.role = :r AND e.status <> 'dismissed'
           ORDER BY (e.code = :pref) DESC, (e.status = 'active') DESC, e.hired_at LIMIT 1""",
        co=company_id,
        r=role,
        pref=prefer or "",
    )


def _player(key: str, player: str, holding: Any, row: dict[str, Any] | None) -> Persona:
    """⟨1.17⟩ §35.4 a player persona: no charter, no reads, no cards; it answers through its
    substitute seat from the masked conversation (talk.player)."""
    voice = default_voice(key, "assistant")
    if row is not None:
        voice = VoiceChoice(
            row["engine"] or voice.engine,
            row["voice"] or voice.voice,
            float(row["rate"]) if row["rate"] is not None else voice.rate,
        )
    return Persona(
        key=key,
        kind="player",
        role="player",
        title_fa=PLAYER_FA[player],
        company=holding.code,
        company_id=holding.id,
        is_manager=False,
        employee=None,
        voice=voice,
        effort="medium",
        tools=(),
        cards=(),
        consult_only=True,
        face=None,
    )


async def resolve(
    tx: Tx, hub: Any, key: str, *, store_voice: bool = True, employee_code: str | None = None
) -> Persona:
    """The persona behind a key, with the owner's choices applied; a manager's
    voice is stored the first time (it keeps it). `employee_code` names the one employee a
    manager key means when the company has several of that charter (the order's holder)."""
    kind, role, code = parse(key)
    holding = await hub.companies.holding()
    if kind == "player":
        assert role is not None
        return _player(
            key, role, holding, await tx.first("SELECT * FROM talk.personas WHERE key = :k", k=key)
        )
    spec = data.personas()[kind]
    if kind == "manager":
        assert role is not None
        assert code is not None
        co = await hub.companies.find(code)
        if co is None or co.kind == "holding":
            raise ApiError(404, "not_found", "unknown company", message_fa="این شرکت را نمیشناسم.")
        emp = await _employee(tx, role, co.id, employee_code)
        if emp is None:
            raise ApiError(
                404,
                "not_found",
                "no employee with this role in the company",
                message_fa="این شرکت کسی با این نقش ندارد.",
            )
        title = f"{emp['title_fa']} {co.name_fa or co.code}"
        company, company_id = co.code, co.id
    else:
        role = str(spec.role)
        emp = await _employee(tx, str(spec.employee_role), holding.id)
        title, company, company_id = spec.title_fa, holding.code, holding.id
    lib = hub.charters
    tools = read_tools(lib, role, spec.tools) if emp is not None else ()
    row = await tx.first("SELECT * FROM talk.personas WHERE key = :k", k=key)
    voice = default_voice(key, kind)
    if row is None and kind == "manager" and store_voice:
        await tx.exec(
            """INSERT INTO talk.personas (company_id, key, engine, voice, rate)
               VALUES (:co, :k, :e, :v, :r) ON CONFLICT (key) DO NOTHING""",
            co=company_id,
            k=key,
            e=voice.engine,
            v=voice.voice,
            r=voice.rate,
        )
    if row is not None:
        voice = VoiceChoice(
            row["engine"] or voice.engine,
            row["voice"] or voice.voice,
            float(row["rate"]) if row["rate"] is not None else voice.rate,
        )
    return Persona(
        key=key,
        kind=kind,
        role=role,
        title_fa=title,
        company=company,
        company_id=company_id,
        is_manager=kind == "manager",
        employee=dict(emp) if emp is not None else None,
        voice=voice,
        effort=(row["effort"] if row is not None and row["effort"] else spec.effort),
        tools=tools,
        cards=spec.cards,
        consult_only=spec.consult_only,
        face=spec.face,
    )


async def resolve_in(
    tx: Tx, hub: Any, key: str, conv: dict[str, Any] | None, *, store_voice: bool = True
) -> Persona:
    """The persona of a key inside a conversation: the holder's key of an order's talk resolves to
    the holder employee itself (⟨1.17⟩ W6 f: never another employee of the same charter)."""
    pref = None
    if conv is not None and key == conv.get("holder") and conv.get("holder_code"):
        pref = str(conv["holder_code"])
    return await resolve(tx, hub, key, store_voice=store_voice, employee_code=pref)


async def invite_key(tx: Tx, hub: Any, role_word: str, company: str) -> str:
    """role@CODE for a role named by the order rules (ceo, or a department code
    whose manager is meant) or by its charter key; ⟨1.17⟩ §35.4 a fixed persona of the holding
    (advisor, overseer, assistant) by its own name, whatever company is given."""
    if role_word in ("advisor", "overseer", "assistant"):
        return role_word
    co = await hub.companies.find(company)
    if co is None or co.kind == "holding":
        raise ApiError(404, "not_found", "unknown company", message_fa="این شرکت را نمیشناسم.")
    if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", role_word):  # a department: its manager
        role = await tx.scalar(
            """SELECT e.role FROM core.employees e JOIN core.departments d ON d.id = e.department_id
               WHERE e.company_id = :co AND d.code = :d AND e.kind = 'manager'
                 AND e.status = 'active' AND e.role IS NOT NULL
               ORDER BY e.hired_at LIMIT 1""",
            co=co.id,
            d=role_word,
        )
    elif role_word == "ceo":
        role = await tx.scalar(
            """SELECT role FROM core.employees WHERE company_id = :co AND kind = 'ceo'
                 AND status = 'active' AND role IS NOT NULL ORDER BY hired_at LIMIT 1""",
            co=co.id,
        )
    else:
        role = role_word
    if not role:
        raise ApiError(
            404, "not_found", "nobody holds this role", message_fa="این شرکت کسی با این نقش ندارد."
        )
    key = f"{role}@{co.code}"
    parse(key)
    return key
