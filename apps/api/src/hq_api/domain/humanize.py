"""The owner's plain Persian (contract §29.7, «بازنویسی برای مدیر کل»): every
text that reaches the owner (a notification, a card, an order's report, a
summary, a home card, a council's plan) passes `humanize` first.

Rules first (seed/plain_language.yaml, data): the `replace` pairs turn an
English or code word into the Persian the owner uses; the `forbidden`
patterns (refs, ids, code words, tool and service names, raw English or
Chinese) are cut; Arabic ي/ك become Persian; spaces are tidied. `check`
names what is still wrong; a caller that may spend a light model call does
so only when `check` is not empty after the rules (never by default here).

`plain(what, why, need)` writes the three-part shape: «چه شد» · «چرا مهم
است» · «از شما چه لازم است» (the last only when something is needed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_FILE = Path(__file__).resolve().parents[3] / "seed" / "plain_language.yaml"
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})
_SPACES = re.compile(r"[ \t\u00a0]{2,}")
_EMPTY_BRACKETS = re.compile(r"[(\[«]\s*[,،:؛-]?\s*[)\]»]")
_DANGLING = re.compile(r"\s+([،.؛:!؟)])")
FIRST = ("english_run", "cjk")


@dataclass(frozen=True)
class Rules:
    allowed: tuple[str, ...]
    replace: tuple[tuple[re.Pattern[str], str], ...]
    forbidden: tuple[tuple[str, re.Pattern[str]], ...]


@lru_cache(maxsize=1)
def rules(path: str | None = None) -> Rules:
    data: dict[str, Any] = (
        yaml.safe_load(Path(path or RULES_FILE).read_text(encoding="utf-8")) or {}
    )
    allowed = tuple(str(a) for a in data.get("allowed") or [])
    pairs = sorted(((str(k), str(v)) for k, v in (data.get("replace") or {}).items()),
                   key=lambda kv: -len(kv[0]))  # fmt: skip
    replace = tuple(
        (re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(k)}(?![A-Za-z0-9_-])", re.I), v)
        for k, v in pairs
    )
    forbidden = tuple(
        (str(k), re.compile(str(v))) for k, v in (data.get("forbidden") or {}).items()
    )
    return Rules(allowed, replace, forbidden)


def _protect(text: str, allowed: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """The allowed names are kept aside while the patterns run."""
    keep: dict[str, str] = {}
    for i, name in enumerate(sorted(allowed, key=len, reverse=True)):
        token = f"\ue000{i}\ue001"
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])")
        if pattern.search(text):
            text = pattern.sub(token, text)
            keep[token] = name
    return text, keep


def _restore(text: str, keep: dict[str, str]) -> str:
    for token, name in keep.items():
        text = text.replace(token, name)
    return text


def _tidy(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = _EMPTY_BRACKETS.sub("", line)
        line = _DANGLING.sub(r"\1", line)
        line = _SPACES.sub(" ", line).strip()
        line = re.sub(r"^[,،:؛\-–—\s]+", "", line)
        lines.append(line)
    out = re.sub(r"(?<!\.)\.\.(?!\.)", ".", "\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def humanize(text: str | None) -> str:
    """The text as the owner should read it (rules only, no model)."""
    if not text:
        return ""
    r = rules()
    out = text.translate(_ARABIC)
    out, keep = _protect(out, r.allowed)
    # raw English sentences and Chinese go whole, before single words are translated
    for name, pattern in r.forbidden:
        if name in FIRST:
            out = pattern.sub("", out)
    for pattern, fa in r.replace:
        out = pattern.sub(fa, out)
    for name, pattern in r.forbidden:
        if name not in FIRST:
            out = pattern.sub("", out)
    return _tidy(_restore(out, keep))


def check(text: str | None) -> list[str]:
    """What in the text breaks the owner's plain Persian: the names of the
    forbidden patterns found (and `not_persian` when there is hardly any
    Persian at all). Empty: the text may be shown."""
    if not text or not text.strip():
        return []
    r = rules()
    body, _ = _protect(text, r.allowed)
    found = [name for name, pattern in r.forbidden if pattern.search(body)]
    letters = [ch for ch in body if ch.isalpha()]
    persian = [ch for ch in letters if "\u0600" <= ch <= "\u06ff"]
    if letters and len(persian) / len(letters) < 0.5:
        found.append("not_persian")
    return found


def plain(what_fa: str, why_fa: str | None = None, need_fa: str | None = None) -> str:
    """The three-part shape (§29.7), each line humanized; the third only when
    something is needed from the owner."""
    parts = [f"چه شد: {humanize(what_fa)}"]
    if why_fa:
        parts.append(f"چرا مهم است: {humanize(why_fa)}")
    if need_fa:
        parts.append(f"از شما چه لازم است: {humanize(need_fa)}")
    return "\n".join(parts)


def persian_share(text: str) -> float:
    """The share of Persian letters among the letters (0..1); 1 for no letters."""
    letters = [ch for ch in text or "" if ch.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for ch in letters if "\u0600" <= ch <= "\u06ff") / len(letters)


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")


def is_persian_answer(text: str, *, threshold: float = 0.6) -> bool:
    """§29.7 a player's answer counts as Persian: no CJK, and at least
    `threshold` of its letters Persian (names, code and figures aside)."""
    if CJK.search(text or ""):
        return False
    stripped = re.sub(r"`[^`]*`|https?://\S+", "", text or "")
    return persian_share(stripped) >= threshold
