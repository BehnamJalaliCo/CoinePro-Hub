"""Redaction (prompt 05 §3): what reaches the model, and what an agent writes,
never carries a secret or a customer's personal data.

Two layers, applied to every JSON value (results going back to the model,
and the text of write tools going out):
  1. by key: a value under a key that names a secret or personal datum
     (password, api_key, token, cookie, private_key, email, phone, ...) is
     replaced whatever it looks like. Plural/counter keys (tokens, *_tokens,
     token_limit) are numbers of the treasury, not secrets.
  2. by value: strings are scrubbed of key and token shapes (Anthropic,
     OpenAI-style, our hqa1 agent tokens, GitHub, AWS, Slack, Telegram bot,
     JWT, PEM private keys, Bearer values, credentials in URLs,
     key=value secrets), e-mail addresses, phone numbers (Latin, Persian and
     Arabic digits), card numbers and IBANs.
Sizes are capped too: long strings and lists are cut, so a result never
floods the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

MASK = "[redacted]"
D = "[0-9۰-۹٠-٩]"  # Latin, Persian and Arabic-Indic digits
SEP = r"[\s\-.()‌]?"

SECRET_KEY = re.compile(
    r"^(.*[_-])?(token|secret|password|passwd|pwd|api[_-]?key|apikey|authorization|cookie|"
    r"private[_-]?key(_pem)?|client[_-]?secret|credentials?|session[_-]?id|otp|pin|"
    r"email|e[_-]?mail|phone(_number)?|mobile|tel|national[_-]?id|ssn|iban|card[_-]?number)$",
    re.IGNORECASE,
)
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[private-key]",
    ),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}"), "[key]"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), "[key]"),
    (re.compile(r"\bhqa1\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[token]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[token]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[key]"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"), "[token]"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"), "[token]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{12,}"), "Bearer [token]"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^\s/:@]+:[^\s/@]+@"), r"\1[credentials]@"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)(\s*[:=]\s*)"
            r"[\"']?[^\s\"',;]{6,}"
        ),
        r"\1\2[redacted]",
    ),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\bIR" + SEP + r"\d{2}(?:" + SEP + r"\d{2,4}){5,}\b", re.IGNORECASE), "[iban]"),
    (re.compile(rf"(?<![0-9۰-۹٠-٩])(?:{D}{{4}}{SEP}){{3}}{D}{{4}}(?![0-9۰-۹٠-٩])"), "[card]"),
    (
        re.compile(
            rf"(?<![0-9۰-۹٠-٩\w])(?:\+|00)?(?:98|۹۸)?{SEP}?(?:0|۰)?(?:9|۹)(?:{D}{SEP}?){{9}}"
            rf"(?![0-9۰-۹٠-٩])"
        ),
        "[phone]",
    ),
    (re.compile(rf"(?<![\w+])\+{D}{{1,3}}(?:{SEP}{D}{{2,5}}){{2,5}}(?![0-9۰-۹٠-٩])"), "[phone]"),
]
MAX_STRING = 4000
MAX_LIST = 60
MAX_DEPTH = 12


def scrub(text: str) -> str:
    for pattern, repl in PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact(
    value: Any, *, max_string: int | None = None, max_list: int | None = None, _depth: int = 0
) -> Any:
    """A copy of `value` with secrets and personal data removed. Sizes are capped
    only when asked (results going back to a model, see fit); what an agent
    writes is never shortened."""
    if _depth > MAX_DEPTH:
        return "[too deep]"
    if isinstance(value, str):
        out = scrub(value)
        if max_string is None or len(out) <= max_string:
            return out
        return out[:max_string] + " …[cut]"
    if isinstance(value, dict):
        res: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if SECRET_KEY.match(key) and not isinstance(v, bool) and v is not None:
                res[key] = MASK
            else:
                res[key] = redact(v, max_string=max_string, max_list=max_list, _depth=_depth + 1)
        return res
    if isinstance(value, list | tuple):
        kept = value if max_list is None else value[:max_list]
        items = [
            redact(v, max_string=max_string, max_list=max_list, _depth=_depth + 1) for v in kept
        ]
        if len(value) > len(kept):
            items.append(f"…[{len(value) - len(kept)} more]")
        return items
    return value


def fit(value: Any, max_chars: int) -> tuple[Any, bool]:
    """Redacted `value` whose JSON fits in `max_chars` (strings cut harder if needed)."""
    out = redact(value, max_string=MAX_STRING, max_list=MAX_LIST)
    if len(json.dumps(out, ensure_ascii=False, default=str)) <= max_chars:
        return out, False
    for limit in (1000, 400, 160):
        out = redact(value, max_string=limit, max_list=MAX_LIST)
        if len(json.dumps(out, ensure_ascii=False, default=str)) <= max_chars:
            return out, True
    text = json.dumps(out, ensure_ascii=False, default=str)
    return {"truncated": text[: max(0, max_chars - 40)]}, True
