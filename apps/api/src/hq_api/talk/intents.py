"""What the owner's words mean in a conversation, by rule and before any model
(contract §32.3, §32.4, §32.8): «اول قاعده، آخر هوش مصنوعی».

The phrases are data (seed/talk/intents.yaml), matched on the same
normalised text as the order rules (domain.orders.normalise: Arabic ي/ك as
Persian, ZWNJ and punctuation as spaces), whole phrases only. Companies and
roles are named as the order rules name them (any number of companies:
read from the directory, never a fixed list).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hq_api.domain import orders as O
from hq_api.talk import data


@dataclass
class Intent:
    work_mode: bool = False
    consult_mode: bool = False
    minutes: bool = False  # «صورت‌جلسه کن»: in any mode
    end_meeting: bool = False  # «پایان جلسه»: the closing minutes of a working meeting
    secretary: bool = False  # back to the holding secretary
    invite: tuple[str, str] | None = None  # (role word: ceo | advisor | a department code, company)
    remember: str | None = None  # the fact to keep
    imperative: bool = False
    everyone: bool = False  # ⟨1.17⟩ §35.4 «نظر همه»: each participant answers once

    @property
    def wants_minutes(self) -> bool:
        return self.minutes or self.end_meeting


def _any(norm: str, key: str) -> str | None:
    """The longest phrase of `key` the text holds, or None."""
    hits = [p for p in data.intents().get(key, []) if O.has(norm, p)]
    return max(hits, key=len) if hits else None


def read(text: str, directory: dict[str, Any] | None) -> Intent:
    norm = O.normalise(text)
    it = Intent()
    if not norm:
        return it
    it.work_mode = _any(norm, "work_mode") is not None
    it.consult_mode = not it.work_mode and _any(norm, "consult_mode") is not None
    it.minutes = _any(norm, "minutes") is not None
    it.end_meeting = _any(norm, "end_meeting") is not None
    first = norm.split()[0]
    it.secretary = any(
        norm == O.normalise(p) or norm.startswith(O.normalise(p) + " ") or first == O.normalise(p)
        for p in data.intents().get("secretary", [])
    )
    if directory is not None and _any(norm, "invite") is not None:
        companies = [c for c in O.companies_named(norm, directory) if not _holding(directory, c)]
        roles = [r for r in O.roles_named(norm) if r != "advisor"]
        if companies and roles:
            it.invite = (roles[0], companies[0])
    phrase = _any(norm, "remember")
    if phrase is not None:
        fact = _strip_phrase(text, phrase)
        it.remember = fact or None
    it.imperative = _any(norm, "imperative") is not None
    it.everyone = _any(norm, "everyone") is not None
    return it


def _holding(d: dict[str, Any], code: str) -> bool:
    return bool((d["companies"].get(code) or {}).get("holding"))


def _strip_phrase(text: str, phrase: str) -> str:
    """The sentence without the «یادت باشه» phrase (matched loosely on words)."""
    words = O.normalise(phrase).split()
    kept = [w for w in text.split() if O.normalise(w) not in words]
    out = " ".join(kept).strip(" ،,.:؛;!؟?-")
    return out[:2000]
