"""Classify a finished SDK run: ok, refusal, quota, rate limit, error.

The quota guard needs two facts: "is this the subscription usage limit?"
and "when does it reset?". Sources, most reliable first:
  1. a rate_limit_event with status "rejected" (carries resetsAt)
  2. an assistant error "rate_limit"/"billing_error" or HTTP 429 together
     with usage-limit wording (the reset may be embedded as "|<epoch>")
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


@dataclass(frozen=True)
class Verdict:
    status: str
    error_class: str | None = None
    resets_at: float | None = None


def _reset_from_text(text: str) -> float | None:
    m = _EPOCH.search(text)
    return float(m.group(1)) if m else None


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
    if not s.result_seen:
        return Verdict(ERROR, "no_result")
    if s.is_error:
        if s.api_error_status:
            return Verdict(ERROR, f"api_{s.api_error_status}")
        return Verdict(ERROR, s.subtype or "error")
    return Verdict(OK)
