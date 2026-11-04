"""The talk's data files (apps/api/seed/talk, contract §32.1, §32.3, §32.5):
personas, voices, the owner's phrases and the key shapes. Read once per
process; a new persona or phrase is a line in a file, never code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SEED = Path(__file__).resolve().parents[3] / "seed" / "talk"
KINDS = ("secretary", "overseer", "assistant", "advisor", "manager")
CARD_KINDS = (
    "order",
    "ask",
    "hire",
    "decision",
    "planner",
    "rule",
    "automation",
    "minutes",
    "invite",
)


@dataclass(frozen=True)
class PersonaSpec:
    key: str
    role: str | None  # the charter; None for the manager template
    employee_role: str | None
    title_fa: str
    effort: str
    tools: tuple[str, ...] | None  # None = every A0 tool of the charter
    cards: tuple[str, ...]
    consult_only: bool
    face: str


@dataclass(frozen=True)
class SecretShape:
    name: str
    pattern: re.Pattern[str]


def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((SEED / name).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"seed/talk/{name} is not a mapping")
    return data


@lru_cache(maxsize=1)
def personas() -> dict[str, PersonaSpec]:
    out: dict[str, PersonaSpec] = {}
    for p in _load("personas.yaml").get("personas") or []:
        key = str(p["key"])
        if key not in KINDS:
            raise ValueError(f"unknown persona {key!r}")
        tools = p.get("tools")
        cards = tuple(str(c) for c in p.get("cards") or ())
        if any(c not in CARD_KINDS for c in cards):
            raise ValueError(f"{key}: unknown card kind")
        consult_only = bool(p.get("consult_only"))
        if consult_only:  # §32.3: never an order card, whatever the file says
            cards = tuple(c for c in cards if c != "order")
        out[key] = PersonaSpec(
            key=key,
            role=p.get("role"),
            employee_role=p.get("employee_role"),
            title_fa=str(p["title_fa"]),
            effort=str(p.get("effort") or "medium"),
            tools=None if tools == "charter_reads" else tuple(str(t) for t in tools or ()),
            cards=cards,
            consult_only=consult_only,
            face=str(p.get("face") or f"{key}.webp"),
        )
    return out


@lru_cache(maxsize=1)
def summary_spec() -> dict[str, Any]:
    spec = _load("personas.yaml").get("summary") or {}
    return {
        "model": spec.get("model"),
        "effort": str(spec.get("effort") or "low"),
        "max_output_tokens": int(spec.get("max_output_tokens") or 700),
        "every_turns": int(spec.get("every_turns") or 10),
    }


@lru_cache(maxsize=1)
def voices() -> dict[str, Any]:
    return _load("voices.yaml")


@lru_cache(maxsize=1)
def intents() -> dict[str, list[str]]:
    return {k: [str(x) for x in v or []] for k, v in _load("intents.yaml").items()}


@lru_cache(maxsize=1)
def secrets() -> tuple[str, str, tuple[SecretShape, ...]]:
    """(the replacement, the persona's fixed answer, the shapes)."""
    data = _load("secrets.yaml")
    shapes = tuple(
        SecretShape(str(p["name"]), re.compile(str(p["regex"]))) for p in data.get("patterns") or []
    )
    return str(data["replacement"]), str(data["answer_fa"]), shapes
