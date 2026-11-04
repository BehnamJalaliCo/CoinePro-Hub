"""A persona's answer: the strict schema of contract §32.2, checked by code.

One router call per step answers

    {tools: [{tool, args}] (read tools to run first; empty for the answer),
     say_fa (≤ 400 characters: what is spoken), show_md (the full answer on
     screen), cards: [≤ 3], invite: {role, company} | null,
     minutes: {...} | null (only when the code asked for minutes)}

`tools` comes first in the schema so that, while the answer streams, the code
already knows whether this step is an answer (speak it, show it) or a tool
step (wait). `say_fa` comes next, so the first sentence is spoken as soon as
it is written (sentence streaming, §32.7). Nothing the model writes is
trusted: `validate` drops a card of a kind the persona may not offer, cuts
`say_fa` at 400 characters, and masks every secret again.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from hq_api.talk import data
from hq_api.talk.scrub import clean

SAY_MAX = 400
SHOW_MAX = 8000
CARDS_MAX = 3
TOOLS_MAX = 3
TASKS_MAX = 12
CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "title_fa", "body_fa", "payload"],
    "properties": {
        "kind": {"type": "string", "enum": [k for k in data.CARD_KINDS if k != "minutes"]},
        "title_fa": {"type": "string", "maxLength": 200},
        "body_fa": {"type": "string", "maxLength": 2000},
        "payload": {"type": "object"},
    },
}
MINUTES_SCHEMA: dict[str, Any] = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["summary_fa", "decisions_fa", "tasks"],
    "properties": {
        "summary_fa": {"type": "string", "maxLength": 2000},
        "decisions_fa": {
            "type": "array",
            "maxItems": 10,
            "items": {"type": "string", "maxLength": 300},
        },
        "tasks": {
            "type": "array",
            "maxItems": TASKS_MAX,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title_fa", "company", "department", "due"],
                "properties": {
                    "title_fa": {"type": "string", "maxLength": 300},
                    "company": {"type": ["string", "null"], "maxLength": 10},
                    "department": {"type": ["string", "null"], "maxLength": 12},
                    "due": {"type": ["string", "null"], "maxLength": 10},
                },
            },
        },
    },
}


def schema(*, tools: bool, minutes: bool) -> dict[str, Any]:
    """The step's schema: no tools on the last step, minutes only when asked."""
    props: dict[str, Any] = {
        "tools": {
            "type": "array",
            "maxItems": TOOLS_MAX if tools else 0,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "args"],
                "properties": {
                    "tool": {"type": "string", "maxLength": 40},
                    "args": {"type": "object"},
                },
            },
        },
        "say_fa": {"type": "string", "maxLength": SAY_MAX},
        "show_md": {"type": "string", "maxLength": SHOW_MAX},
        "cards": {"type": "array", "maxItems": CARDS_MAX, "items": CARD_SCHEMA},
        "invite": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["role", "company"],
            "properties": {
                "role": {"type": "string", "maxLength": 41},
                "company": {"type": "string", "maxLength": 10},
            },
        },
    }
    required = ["tools", "say_fa", "show_md", "cards", "invite"]
    if minutes:
        props["minutes"] = MINUTES_SCHEMA
        required.append("minutes")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": props,
    }


@dataclass
class Answer:
    say_fa: str
    show_md: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    invite: dict[str, str] | None = None
    minutes: dict[str, Any] | None = None
    dropped: int = 0  # cards the persona may not offer


class BadAnswer(Exception):
    pass


def parse(structured: Any, text: str | None) -> dict[str, Any]:
    out = structured
    if out is None and text:
        try:
            out = json.loads(text)
        except ValueError as exc:
            raise BadAnswer("not JSON") from exc
    if not isinstance(out, dict):
        raise BadAnswer("not an object")
    return out


def _text(v: Any, limit: int) -> str:
    s = v if isinstance(v, str) else ""
    return clean(s.strip())[0][:limit]


def validate(raw: dict[str, Any], allowed_cards: tuple[str, ...]) -> Answer:
    """The answer as code accepts it."""
    if not isinstance(raw.get("say_fa", ""), str) or not isinstance(raw.get("show_md", ""), str):
        raise BadAnswer("say_fa and show_md are text")
    tools = []
    for t in (raw.get("tools") or [])[:TOOLS_MAX]:
        if isinstance(t, dict) and isinstance(t.get("tool"), str):
            tools.append({"tool": t["tool"][:40], "args": t.get("args")})
    cards, dropped = [], 0
    for c in (raw.get("cards") or [])[:CARDS_MAX]:
        if (
            not isinstance(c, dict)
            or c.get("kind") not in allowed_cards
            or c.get("kind") == "minutes"
        ):
            dropped += 1
            continue
        title = _text(c.get("title_fa"), 200)
        if not title:
            dropped += 1
            continue
        payload = c.get("payload") if isinstance(c.get("payload"), dict) else {}
        cards.append(
            {
                "kind": c["kind"],
                "title_fa": title,
                "body_fa": _text(c.get("body_fa"), 2000),
                "payload": json.loads(clean(json.dumps(payload, ensure_ascii=False))[0]),
            }
        )
    inv = raw.get("invite")
    invite = None
    if (
        isinstance(inv, dict)
        and isinstance(inv.get("role"), str)
        and isinstance(inv.get("company"), str)
    ):
        invite = {"role": inv["role"][:41], "company": inv["company"][:10]}
    minutes = raw.get("minutes") if isinstance(raw.get("minutes"), dict) else None
    say = _text(raw.get("say_fa"), SAY_MAX)
    show = _text(raw.get("show_md"), SHOW_MAX) or say
    return Answer(
        say_fa=say,
        show_md=show,
        tools=tools,
        cards=cards,
        invite=invite,
        minutes=minutes,
        dropped=dropped,
    )


# ------------------------------------------------------------ streaming --
_ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def partial_string(buf: str, key: str) -> tuple[str, bool] | None:
    """The value of string field `key` as far as `buf` (a JSON object being
    streamed) holds it: (text so far, complete). None before the key."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"', buf)
    if m is None:
        return None
    i = m.end()
    out: list[str] = []
    while i < len(buf):
        c = buf[i]
        if c == '"':
            return "".join(out), True
        if c == "\\":
            if i + 1 >= len(buf):
                break
            e = buf[i + 1]
            if e == "u":
                if i + 6 > len(buf):
                    break
                try:
                    code = int(buf[i + 2 : i + 6], 16)
                except ValueError:
                    break
                if 0xD800 <= code < 0xDC00:  # a surrogate pair: wait for its second half
                    if i + 12 > len(buf):
                        break
                    try:
                        low = int(buf[i + 8 : i + 12], 16)
                    except ValueError:
                        break
                    out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                    i += 12
                    continue
                out.append(chr(code))
                i += 6
                continue
            out.append(_ESC.get(e, e))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out), False


EMPTY_TOOLS = re.compile(r'"tools"\s*:\s*\[\s*\]')


def is_answer_step(buf: str) -> bool | None:
    """Once `say_fa` has begun: whether this step answers (no tools). None
    while the stream has not reached it yet."""
    if re.search(r'"say_fa"\s*:', buf) is None:
        return None
    return EMPTY_TOOLS.search(buf) is not None or re.search(r'"tools"\s*:', buf) is None


_END = re.compile(r"[.!?؟…](?=\s)|\n+")


def sentences(text: str, *, final: bool) -> tuple[list[str], int]:
    """The finished sentences of `text` and how many characters they take; at
    the end (`final`) whatever is left is a sentence too."""
    out: list[str] = []
    start = 0
    for m in _END.finditer(text):
        s = text[start : m.end()].strip()
        if s:
            out.append(s)
        start = m.end()
    if final and text[start:].strip():
        out.append(text[start:].strip())
        start = len(text)
    return out, start
