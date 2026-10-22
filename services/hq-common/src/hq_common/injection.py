"""Instruction-like passages in untrusted text (prompt 07 §2.7, 7.1 §3): what a
web page, a fetched file or an MCP server's answer says to the model as if it
were its operator. Such passages are flagged (`suspected_injection`), never
removed: the agent and the overseer see the data as it is, and what was found.

The patterns are English and Persian. The egress service flags web content
with the same list (hq_egress.extract.INJECTION; a test keeps the two equal).
"""

from __future__ import annotations

import re
from typing import Any

MAX_FLAGS = 10

INJECTION = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}"
        r"\b(instructions?|prompts?|rules|directions)\b",
        r"\byou are now\b",
        r"\b(new|updated) (system )?instructions?\b",
        r"\bsystem prompt\b",
        r"\bdo not (tell|inform|show) (the )?(user|owner|human)\b",
        r"\b(act|behave) as (an?|the)\b.{0,30}\b(assistant|ai|model|agent)\b",
        r"\bcall (the )?(tool|function)\b",
        r"<\|?(system|im_start|assistant)\|?>",
        r"دستور(ها|ات)?(ی)?\s*(قبلی|پیشین|بالا).{0,20}(نادیده|فراموش|توجه\s*نکن)",
        r"(نادیده|فراموش)\s*(بگیر|کن).{0,20}دستور",
        r"(تو|شما)\s*(اکنون|از\s*این\s*به\s*بعد)\s*(یک|نقش)",
        r"به\s*(کاربر|مالک)\s*(نگو|اطلاع\s*نده)",
    )
]


def injection_flags(*texts: str) -> list[dict[str, Any]]:
    """Instruction-like passages (at most 10), each with a short snippet."""
    found: list[dict[str, Any]] = []
    for text in texts:
        for rx in INJECTION:
            for m in rx.finditer(text or ""):
                a, b = max(0, m.start() - 40), min(len(text), m.end() + 40)
                found.append({"pattern": rx.pattern[:60], "snippet": text[a:b].replace("\n", " ")})
                if len(found) >= MAX_FLAGS:
                    return found
    return found
