"""Classify a finished SDK run: ok, refusal, quota, rate limit, error.

The quota guard needs two facts: "is this the subscription usage limit?"
and "when does it reset?". Sources, most reliable first:
  1. a rate_limit_event with status "rejected" (carries resetsAt)
  2. an assistant error "rate_limit"/"billing_error" or HTTP 429 together
     with usage-limit wording (the reset may be embedded as "|<epoch>")
  3. ⟨2026-11-11⟩ the CLI's own limit notice without a 429, in an error result or as
     the whole answer of a run: short, limit wording AND the CLI's reset marker
     ("|<epoch>" or "resets ..."), no structured output. Such a text is never handed
     back as the model's answer. Limit wording alone never counts ("Disk usage limit
     reached; cleaned /var/log." is an answer): a false positive would mark the account
     full and move every call to the other one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OK, ERROR, REFUSAL, TIMEOUT, RATE_LIMITED, QUOTA = (
    "ok",
    "error",
    "refusal",
    "timeout",
    "rate_limited",
    "quota_exhausted",
)
_LIMIT_TEXT = re.compile(r"usage limit|limit reached|out of (?:extra )?usage|quota", re.IGNORECASE)
# The CLI's own notice when the subscription is out ("Claude AI usage limit reached|<epoch>",
# "5-hour limit reached ∙ resets 3pm", "You've hit your limit · resets ...", "Weekly limit
# reached ∙ resets Mon 9am"): stricter than _LIMIT_TEXT (no bare "quota"), only a short text,
# and always with the reset marker every real notice carries. The hub's api keeps the same rule
# (apps/api hq_api/domain/servers.py limit_notice) for a runner's Claude Code turns.
_LIMIT_NOTICE = re.compile(
    r"\blimit (?:reached|hit)\b|\byou(?:'|\u2019)?ve (?:hit|reached) your (?:[\w-]+ )?limit\b"
    r"|\bout of (?:extra )?usage\b|\busage limit\b",
    re.IGNORECASE,
)
NOTICE_CHARS = 400
_RESET_MARK = re.compile(r"\|\d{10}\b|\bresets?\b", re.IGNORECASE)
_EPOCH = re.compile(r"\|(\d{10})\b")


@dataclass
class Signals:
    rejected_resets_at: list[float | None] = field(default_factory=list)
    assistant_errors: list[str] = field(default_factory=list)
    api_error_status: int | None = None
    is_error: bool = False
    subtype: str | None = None
    stop_reason: str | None = None
    text: str = ""
    result_seen: bool = False
    structured: bool = False  # the run returned structured output (a real answer)


@dataclass(frozen=True)
class Verdict:
    status: str
    error_class: str | None = None
    resets_at: float | None = None


def _reset_from_text(text: str) -> float | None:
    m = _EPOCH.search(text)
    return float(m.group(1)) if m else None


def limit_notice(text: str | None) -> bool:
    """The CLI's own short usage-limit notice: limit wording with its reset marker (not an
    answer that merely mentions a limit)."""
    t = (text or "").strip()
    return (
        0 < len(t) <= NOTICE_CHARS
        and _LIMIT_NOTICE.search(t) is not None
        and _RESET_MARK.search(t) is not None
    )


def classify(s: Signals) -> Verdict:
    if s.rejected_resets_at:
        resets = [r for r in s.rejected_resets_at if r]
        return Verdict(QUOTA, "usage_limit", max(resets) if resets else _reset_from_text(s.text))
    limit_words = bool(_LIMIT_TEXT.search(s.text))
    if "billing_error" in s.assistant_errors:
        return Verdict(QUOTA, "billing_error", _reset_from_text(s.text))
    if "rate_limit" in s.assistant_errors or s.api_error_status == 429:
        if limit_words:
            return Verdict(QUOTA, "usage_limit", _reset_from_text(s.text))
        return Verdict(RATE_LIMITED, "rate_limit")
    if "authentication_failed" in s.assistant_errors or s.api_error_status in (401, 403):
        return Verdict(ERROR, "auth_failed")
    if s.stop_reason == "refusal":
        return Verdict(REFUSAL, "refusal")
    # ⟨2026-11-11⟩ the CLI's limit notice without a 429 (audit C1c), as an error result or as the
    # whole answer: returned as an answer, the agent's run read it as the model's word and the call
    # never moved to the other account. Only the marked notice, never bare limit wording.
    if not s.structured and limit_notice(s.text):
        return Verdict(QUOTA, "usage_limit", _reset_from_text(s.text))
    if not s.result_seen:
        return Verdict(ERROR, "no_result")
    if s.is_error:
        if s.api_error_status:
            return Verdict(ERROR, f"api_{s.api_error_status}")
        return Verdict(ERROR, s.subtype or "error")
    return Verdict(OK)
