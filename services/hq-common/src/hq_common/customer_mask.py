"""What a customer writes, masked before it is stored or shown to a model
(prompt 10 §1.3, contract §19.6 "Inbound"). The raw text is never stored and
never reaches a model: the caller keeps only `mask(text).text`.

API (stable):
  mask(text) -> Masked        the text with every secret and personal-data shape
                              masked, and the kinds that were found
  quote(text, max_chars=280)  a masked quote for statistics and the feedback
                              inbox: also Telegram handles (@name) and long
                              digit runs (exchange UIDs, phone-like ids) masked
  KINDS                       the kinds `Masked.kinds` may hold:
      seed_phrase   12 or more BIP-39 English words in a row (one typo allowed)
      private_key   64 hex digits (0x optional), a WIF or an extended private
                    key (xprv/yprv/zprv/tprv), any -----BEGIN ...----- block
      card          13-19 digits passing Luhn (spaces or dashes between digits;
                    Latin, Persian or Arabic-Indic digits)
      secret        any other credential hq_common.redact finds (keys, tokens,
                    passwords and codes after their label)
      personal      e-mail, phone, IBAN, national code (redact's personal data)
  SAFETY_KINDS                the kinds after which the customer gets the safety
                              line once (§19.6): everything but `personal`

On top of the whole hub's redaction (redact.scrub, §16.6) this adds the shapes
only a customer of an exchange sends. A transaction hash is 64 hex digits too
and is masked as well: the support desk asks for the exchange UID, never for a
hash, and a masked hash costs one question while a leaked key costs a wallet.
Matching runs on the NFKC view of the text without invisible characters (the
same view redact uses), so a full-width or invisibly split secret is found; the
replacement is made in the original text.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from hq_common import redact

SEED = "[seed-phrase]"
KEY = "[private-key]"
CARD = "[card]"
HANDLE = "[handle]"
ID = "[id]"
KINDS = ("seed_phrase", "private_key", "card", "secret", "personal")
SAFETY_KINDS = frozenset({"seed_phrase", "private_key", "card", "secret"})
SEED_WORDS = 12  # the shortest BIP-39 phrase
_WORDLIST = Path(__file__).with_name("bip39_english.txt")
# sha256 of bitcoin/bips bip-0039/english.txt (2048 words, MIT licence).
_WORDLIST_SHA256 = "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"


@dataclass(frozen=True)
class Masked:
    text: str
    kinds: tuple[str, ...]  # sorted, each in KINDS

    @property
    def needs_safety_line(self) -> bool:
        return any(k in SAFETY_KINDS for k in self.kinds)


@cache
def wordlist() -> frozenset[str]:
    raw = _WORDLIST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _WORDLIST_SHA256:
        raise RuntimeError("bip39_english.txt does not match its pinned sha256")
    words = frozenset(raw.decode("ascii").split())
    if len(words) != 2048:
        raise RuntimeError("bip39_english.txt must hold 2048 words")
    return words


_DIGIT = "0-9\u06f0-\u06f9\u0660-\u0669"
_B58 = "1-9A-HJ-NP-Za-km-z"
_KEY_RULES = (
    # any armoured block (a key, whatever its label), with or without its END line
    re.compile(
        r"-----BEGIN [A-Z0-9 ]{1,40}-----(?:[^-]{0,20000}-----END [A-Z0-9 ]{1,40}-----)?",
    ),
    re.compile(r"(?<![0-9A-Za-z])(?:0[xX])?[0-9A-Fa-f]{64}(?![0-9A-Za-z])"),
    re.compile(
        rf"(?<![{_B58}])(?:5[HJK][{_B58}]{{49}}|[KLc][{_B58}]{{51}}|9[{_B58}]{{50}})(?![{_B58}])"
    ),
    re.compile(rf"(?<![{_B58}])[xyzt]prv[{_B58}]{{100,112}}(?![{_B58}])"),
)
_CARD_FIRST = "2-6\u06f2-\u06f6\u0662-\u0666"  # the card networks' first digit
_CARD = re.compile(rf"(?<![{_DIGIT}])[{_CARD_FIRST}](?:[ \-]?[{_DIGIT}]){{12,18}}(?![{_DIGIT}])")
# A word of the phrase; what lies between two words may hold no letter (of any
# script): spaces, commas, numbering such as "1." or "(2)", new lines.
_WORD = re.compile(r"[A-Za-z]+")
_GAP_MAX = 16
_HANDLE = re.compile(r"(?<![A-Za-z0-9_@.])@[A-Za-z][A-Za-z0-9_]{3,31}(?![A-Za-z0-9_])")
_LONG_DIGITS = re.compile(rf"(?<![{_DIGIT}])[{_DIGIT}](?:[ \-]?[{_DIGIT}]){{5,}}(?![{_DIGIT}])")


def _letterless(gap: str) -> bool:
    return len(gap) <= _GAP_MAX and not any(ch.isalpha() for ch in gap)


def _seed_spans(norm: str) -> list[tuple[int, int]]:
    """Runs of >= 12 BIP-39 words in `norm` (one word outside the list may sit
    inside a run: a typo does not save a phrase from the mask)."""
    words = wordlist()
    out: list[tuple[int, int]] = []
    # Segments of consecutive words with letterless gaps.
    segment: list[tuple[int, int, bool]] = []
    prev_end = -1

    def close() -> None:
        if not segment:
            return
        # good runs: (first index, last index, count) of in-list words
        runs: list[tuple[int, int]] = []
        i = 0
        while i < len(segment):
            if segment[i][2]:
                j = i
                while j + 1 < len(segment) and segment[j + 1][2]:
                    j += 1
                runs.append((i, j))
                i = j + 1
            else:
                i += 1
        for n, (a, b) in enumerate(runs):
            count = b - a + 1
            if count >= SEED_WORDS:
                out.append((segment[a][0], segment[b][1]))
            if n + 1 < len(runs):
                c, d = runs[n + 1]
                if c == b + 2 and count + (d - c + 1) >= SEED_WORDS:
                    out.append((segment[a][0], segment[d][1]))

    for m in _WORD.finditer(norm):
        if segment and not _letterless(norm[prev_end : m.start()]):
            close()
            segment = []
        word = m.group().lower()
        segment.append((m.start(), m.end(), word in words))
        prev_end = m.end()
    close()
    return out


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def _own_spans(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, replacement, kind) in `text` itself."""
    norm, origin = redact._normalise(text)

    def back(s: int, e: int) -> tuple[int, int]:
        if origin is None:
            return s, e
        return origin[s], origin[e - 1] + 1

    found: list[tuple[int, int, str, str]] = []
    for s, e in _seed_spans(norm):
        found.append((*back(s, e), SEED, "seed_phrase"))
    for rule in _KEY_RULES:
        for m in rule.finditer(norm):
            found.append((*back(*m.span()), KEY, "private_key"))
    for m in _CARD.finditer(norm):
        if redact._luhn(_digits(m.group())):
            found.append((*back(*m.span()), CARD, "card"))
    return found


def mask(text: str) -> Masked:
    """`text` masked for storage and for any model: redact's shapes (§16.6)
    plus seed phrases, private keys and cards (Luhn)."""
    if not text:
        return Masked(text, ())
    spans = _own_spans(text)
    credentials = [(s, e) for s, e, _ in redact._masks(text, secrets_only=True)]
    for s, e, repl in redact._masks(text):
        kind = "personal"
        if repl == CARD:
            kind = "card"
        elif repl == KEY:
            kind = "private_key"
        elif any(cs < e and s < ce for cs, ce in credentials):
            kind = "secret"
        spans.append((s, e, repl, kind))
    if not spans:
        return Masked(text, ())
    spans.sort(key=lambda x: (x[0], -x[1]))
    merged: list[tuple[int, int, str]] = []
    kinds: set[str] = set()
    for s, e, repl, kind in spans:
        kinds.add(kind)
        if merged and s < merged[-1][1]:
            first, last, first_repl = merged[-1]
            merged[-1] = (first, max(last, e), first_repl)
            continue
        merged.append((s, e, repl))
    parts: list[str] = []
    pos = 0
    for s, e, repl in merged:
        parts.append(text[pos:s])
        parts.append(repl)
        pos = e
    parts.append(text[pos:])
    return Masked("".join(parts), tuple(sorted(kinds)))


def quote(text: str, max_chars: int = 280) -> str:
    """A masked quote (statistics, the feedback inbox, what a CEO, the advisor
    or the overseer may read): `mask` plus handles and long digit runs."""
    out = mask(text).text
    out = _HANDLE.sub(HANDLE, out)
    out = _LONG_DIGITS.sub(ID, out)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out
