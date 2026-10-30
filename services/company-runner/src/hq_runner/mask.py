"""Secret masking for everything the runner streams to the hub (contract §26.3).

Masked by name: KEY=value and "key": "value" pairs whose key names a secret
(PASSWORD, SECRET, TOKEN, API_KEY, PRIVATE_KEY, CREDENTIALS, ...), command-line
flags such as --password X, Authorization headers and Bearer/Basic credentials,
passwords inside URLs. Masked by shape: PEM private keys (across lines, see
StreamMasker), Anthropic/OpenAI, GitHub, GitLab, Slack, AWS, Google, Stripe,
OpenBao/Vault, npm, Telegram bot tokens, JWTs and hq agent tokens.
Counters such as input_tokens are not secrets and stay.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

MASK = "[redacted]"

_SECRET_WORDS = {
    "password",
    "passwd",
    "pwd",
    "pass",
    "secret",
    "token",
    "apikey",
    "key",
    "credential",
    "credentials",
    "auth",
    "cookie",
    "dsn",
    "salt",
    "passphrase",
    "private",
    "signature",
    "otp",
}
_NOT_SECRET_SUFFIXES = ("tokens", "_count", "_id", "_ids", "_len", "_length", "_ttl", "_path")
_NOT_SECRET_KEYS = {"key", "keys", "monkey", "token_type", "auth_mode", "authority"}


def is_secret_key(name: str) -> bool:
    low = name.strip().strip("\"'").lower().replace("-", "_")
    if not low or low in _NOT_SECRET_KEYS:
        return False
    if low.endswith(_NOT_SECRET_SUFFIXES):
        return False
    compact = low.replace("_", "").replace(".", "")
    if any(w in compact for w in ("password", "passwd", "secret", "apikey", "privatekey")):
        return True
    if "token" in compact or "credential" in compact or "passphrase" in compact:
        return True
    parts = [p for p in re.split(r"[_.]", low) if p]
    return any(p in _SECRET_WORDS for p in parts) and len(parts) > 1


_TOKEN_SHAPES = [
    r"sk-ant-[A-Za-z0-9_-]{16,}",
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"glpat-[A-Za-z0-9_-]{20,}",
    r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"(?:AKIA|ASIA)[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z_-]{35}",
    r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}",
    r"hv[sbr]\.[A-Za-z0-9_-]{20,}",
    r"npm_[A-Za-z0-9]{36}",
    r"hqa1[_.-][A-Za-z0-9_.-]{16,}",
    r"hqr1[_.-][A-Za-z0-9_.-]{16,}",
    r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    r"\d{8,10}:AA[A-Za-z0-9_-]{30,}",
]
_SHAPES_RE = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(_TOKEN_SHAPES) + r")")
_AUTH_HEADER_RE = re.compile(
    r"(?i)((?:proxy-)?authorization\s*[:=]\s*[\"']?)((?:bearer|basic|token|digest)\s+)?([^\s\"',;]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)(\s+)([A-Za-z0-9._~+/=-]{8,})")
_URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]{1,20}://[^/\s:@]{1,256}:)([^@\s/]{1,256})@")
_FLAG_RE = re.compile(
    r"(?i)(--?(?:password|passwd|pass|token|secret|api-key|apikey|access-key|secret-key|"
    r"auth-token|client-secret)(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"
)
# KEY=value / KEY: value (env files, docker -e, logs), the key checked by is_secret_key.
_KV_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_.-]{0,80})(\s*=\s*|:\s+|:(?=[\"']))"
    r"(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&|]+)"
)
# "key": "value" in JSON.
_JSON_KV_RE = re.compile(r"(\"([A-Za-z0-9_.-]{1,80})\"\s*:\s*)\"((?:[^\"\\\n]|\\.)*)\"")
_PEM_BEGIN_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PEM_END_RE = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PEM_INLINE_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY"
    r"(?: BLOCK)?-----|$)",
    re.S,
)


def _kv(m: re.Match[str]) -> str:
    key, sep, value = m.group(1), m.group(2), m.group(3)
    if not is_secret_key(key) or value in (MASK, '""', "''") or value.startswith("$"):
        return m.group(0)
    quote = value[0] if value[:1] in ("'", '"') else ""
    return f"{key}{sep}{quote}{MASK}{quote}"


def _json_kv(m: re.Match[str]) -> str:
    if not is_secret_key(m.group(2)) or not m.group(3):
        return m.group(0)
    return f'{m.group(1)}"{MASK}"'


def _auth(m: re.Match[str]) -> str:
    return f"{m.group(1)}{m.group(2) or ''}{MASK}"


class Masker:
    """Masks secrets in one text. `literals` are exact values always masked
    (the runner's own token)."""

    def __init__(self, literals: Iterable[str] = ()) -> None:
        self.literals = sorted({s for s in literals if s and len(s) >= 6}, key=len, reverse=True)

    def text(self, text: str) -> str:
        if not text:
            return text
        for lit in self.literals:
            if lit in text:
                text = text.replace(lit, MASK)
        text = _PEM_INLINE_RE.sub(MASK, text)
        text = _AUTH_HEADER_RE.sub(_auth, text)
        text = _BEARER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
        text = _URL_CRED_RE.sub(lambda m: f"{m.group(1)}{MASK}@", text)
        text = _FLAG_RE.sub(lambda m: f"{m.group(1)}{MASK}", text)
        text = _JSON_KV_RE.sub(_json_kv, text)
        text = _KV_RE.sub(_kv, text)
        return _SHAPES_RE.sub(MASK, text)

    def value(self, value: Any) -> Any:
        """A copy of a JSON-like value: strings masked, values under secret keys masked."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and is_secret_key(k) and isinstance(v, str) and v:
                    out[k] = MASK
                else:
                    out[k] = self.value(v)
            return out
        if isinstance(value, list):
            return [self.value(v) for v in value]
        return value


class StreamMasker:
    """Line-by-line masking of one output stream; a PEM private key spread over
    lines is masked from its BEGIN line to its END line."""

    def __init__(self, masker: Masker) -> None:
        self.masker = masker
        self.in_pem = False

    def line(self, line: str) -> str:
        if self.in_pem:
            if _PEM_END_RE.search(line):
                self.in_pem = False
                return MASK + self.masker.text(_PEM_END_RE.split(line, 1)[1])
            return MASK
        begin = _PEM_BEGIN_RE.search(line)
        if begin and not _PEM_END_RE.search(line, begin.end()):
            self.in_pem = True
            return self.masker.text(line[: begin.start()]) + MASK
        return self.masker.text(line)
