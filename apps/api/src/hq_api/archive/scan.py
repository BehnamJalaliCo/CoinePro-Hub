"""No secret ever enters the archive (prompt 14 red line 1, contract §23.0).

Every file's text (a PDF's text layer, an image's or a scan's OCR), its name
and every value written with it are scanned before anything is stored, with
the hub's own patterns: hq_common.redact's credential rules (the shapes the
gitleaks gate and the outbound guard of §19.6 know: API keys, tokens,
passwords and one-time codes after their label, PEM private keys) and
hq_common.customer_mask's seed phrases (12+ BIP-39 words) and private keys
(WIF, extended keys), plus what only a document carries: an `otpauth://`
2FA secret, a labelled 64-hex private key, labelled backup or recovery codes.

`kinds(text)` names what was found and never returns any part of it: the
caller answers `422 secret_in_document` and logs nothing of the file.
A certificate, a public key or a transaction hash is not a secret here.
"""

from __future__ import annotations

import re
from typing import Any

from hq_common import customer_mask, redact

PRIVATE_ARMOUR = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----", re.I)
B58 = "1-9A-HJ-NP-Za-km-z"
WIF = re.compile(rf"(?<![{B58}])(?:5[HJK][{B58}]{{49}}|[KL][{B58}]{{51}})(?![{B58}])")
XPRV = re.compile(rf"(?<![{B58}])[xyzt]prv[{B58}]{{100,112}}(?![{B58}])")
OTPAUTH = re.compile(r"otpauth://[th]otp/[^\s]{0,300}secret=[A-Z2-7]{8,}", re.I)
LABELLED_HEX = re.compile(
    r"(?:private[\s_\-]*key|priv[\s_\-]*key|secret[\s_\-]*key|کلید\s*(?:‌)?خصوصی)"
    r"[^0-9A-Za-z]{0,12}(?:0x)?[0-9A-Fa-f]{64}(?![0-9A-Fa-f])",
    re.I,
)
LABELLED_CODES = re.compile(
    r"(?:backup|recovery|2fa|two[\s\-]*factor)[\s_\-]*(?:codes?|keys?)"
    r"|کد(?:\s|‌)*(?:های)?(?:\s|‌)*(?:بازیابی|پشتیبان|دومرحله\w*)",
    re.I,
)
CODE_RUN = re.compile(r"(?:[0-9A-Za-z]{4,10}[\s,;\-]+){3,}[0-9A-Za-z]{4,10}")
SEED_LABEL = re.compile(
    r"(?:seed|mnemonic|recovery)[\s_\-]*(?:phrase|words?)|عبارت\s*(?:‌)?(?:بازیابی|امنیتی)", re.I
)


def kinds(text: str | None) -> list[str]:
    """What kinds of secret `text` holds (empty: none). Deterministic, no I/O."""
    if not text:
        return []
    found: set[str] = set()
    norm, _ = redact._normalise(text)
    if customer_mask._seed_spans(norm):
        found.add("seed_phrase")
    if PRIVATE_ARMOUR.search(norm) or WIF.search(norm) or XPRV.search(norm):
        found.add("private_key")
    if LABELLED_HEX.search(norm):
        found.add("private_key")
    if OTPAUTH.search(norm):
        found.add("2fa_secret")
    for m in LABELLED_CODES.finditer(norm):
        if CODE_RUN.search(norm[m.end() : m.end() + 400]):
            found.add("2fa_secret")
            break
    if SEED_LABEL.search(norm):
        # a labelled phrase shorter than 12 words, numbered or in a grid
        for m in SEED_LABEL.finditer(norm):
            words = re.findall(r"[a-z]{3,8}", norm[m.end() : m.end() + 400].lower())
            if sum(1 for w in words if w in customer_mask.wordlist()) >= 8:
                found.add("seed_phrase")
                break
    for _s, _e, repl in redact._masks(text, secrets_only=True):
        found.add("private_key" if repl == "[private-key]" else "credential")
    return sorted(found)


def values_kinds(values: Any) -> list[str]:
    """The same scan over every string inside a JSON value (metadata, notes)."""
    out: set[str] = set()

    def walk(v: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(v, str):
            out.update(kinds(v))
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(str(k), depth + 1)
                walk(x, depth + 1)
        elif isinstance(v, list):
            for x in v:
                walk(x, depth + 1)

    walk(values)
    return sorted(out)
