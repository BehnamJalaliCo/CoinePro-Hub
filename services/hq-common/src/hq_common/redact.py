"""Redaction for the whole hub (prompt 05 §3, prompt 5.1 §2.1): what a model
reads and what an agent writes never carries a secret or a customer's
personal data. One module, used by the Tool Gateway (tool results, write
tools) and by apps/api (run context, step summaries, live deltas, error
fields that go back to a model).

API (stable):
  MASK                          what replaces a value under a secret key
  scrub(text) -> str            a text with every secret / personal-data shape
                                masked; never shortened otherwise
  redact(value, *, max_string=None, max_list=None) -> Any
                                a copy of a JSON-like value: strings AND dict
                                keys scrubbed, any value under a secret key
                                masked (booleans and null kept). Sizes are cut
                                only when max_string / max_list are given
                                (what an agent writes is never cut).
  fit(value, max_chars) -> (value, truncated)
                                for what goes back to a model: redacted with
                                caps, its JSON at most max_chars
  is_secret_key(name) -> bool   whether a key names a secret or a personal datum
  mask_secrets(value) -> Any    a copy of a JSON-like value with credentials only
                                masked (keys, tokens, passwords, codes; by value
                                and by key) and personal data kept: what the owner
                                approves on an A3 card (recipients, amounts) must
                                be shown to them (contract §18.13, 7.1)
  spans(text) -> [(start, end)] the ranges of `text` (its own indices, end
                                exclusive) that scrub(text) replaces: sorted,
                                touching or overlapping ranges merged. For a
                                caller that must cut a text without cutting
                                through a secret (the live stream to the owner)
  await scrub_async(text), await redact_async(value, ...), await fit_async(...)
                                the same; a large input is scrubbed in a
                                worker thread, so the event loop never blocks

By value. The text is normalised for matching only - NFKC, then every format
character (Unicode Cf) and every other default-ignorable code point (variation
selectors, U+034F, the Hangul fillers, ...: invisible, and they would split a
secret) dropped - so a full-width or invisibly split secret is still found;
each match is mapped back and masked in the original text, which keeps its
Persian ZWNJs everywhere else. A token right after a JSON escape (\\n, \\t, \\r
in a JSON-dumped text) is at a boundary like one at the start of a line.
Every pattern has bounded repetitions and the rules are applied in one pass
over the text, so the work is linear in its length.
Shapes: PEM and PGP private keys (with or without the END line), Anthropic, OpenAI,
hqa1 agent tokens, GitHub, AWS, Slack, Telegram bot, JWT, OpenBao/Vault
(hvs./hvb./hvr.), Google (AIza), Stripe (sk_/rk_), Bearer and Basic
credentials, credentials in URLs, KEY=value and "key": "value" secrets
(DB_PASSWORD=, ANTHROPIC_API_KEY=, CLIENT_SECRET:, Persian رمز/گذرواژه),
one-time and PIN codes, national codes, e-mail addresses, Iranian mobile and
landline numbers and international numbers (Latin, Persian and Arabic-Indic
digits), card numbers (Luhn only) and IBANs. Ordinary numbers - a ref, a
token count, a rial amount, a year - are left alone.

By key. A value under a key naming a secret or a personal datum (password,
api_key, secret_key, aws_secret_access_key, access_key, signing_key,
ssh_key, passphrase, accessToken, refreshToken, otp_code, pin_code,
national_code, mobile_number, phones, emails, ...; snake, kebab or camel
case) is masked whatever it looks like, and so is the `value` of a
name/value pair that names one ({"name": "DB_PASSWORD", "value": ...}).
Counter keys of the treasury (tokens, *_tokens, token_limit) are numbers,
not secrets. An integer is masked only when its digits are a card (Luhn, a
card network's first digit) or a phone number; any other number is kept.
"""

from __future__ import annotations

import asyncio
import functools
import itertools
import json
import re
import unicodedata
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

MASK = "[redacted]"
MAX_STRING = 4000
MAX_LIST = 60
MAX_DEPTH = 12
THREAD_ABOVE = 20_000  # chars: scrub in a worker thread above this
CUT_MARGIN = 2048  # a capped string is cut to max_string + this before scrubbing


# ------------------------------------------------------------ normalising --
# Unicode's Default_Ignorable_Code_Point (DerivedCoreProperties.txt): rendered
# as nothing, so they can split a secret; beyond Cf they include variation
# selectors, U+034F, the Hangul fillers and the Mongolian selectors.
DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


def _invisible_class() -> str:
    """The format characters (Cf) of the planes that have any and the
    default-ignorable code points, as one regex class."""
    ranges: list[tuple[int, int]] = list(DEFAULT_IGNORABLE)
    start = prev = -1
    for cp in itertools.chain(range(0x20000), range(0xE0000, 0xE1000)):
        if unicodedata.category(chr(cp)) == "Cf":
            if start < 0:
                start = cp
            prev = cp
        elif start >= 0:
            ranges.append((start, prev))
            start = -1
    if start >= 0:
        ranges.append((start, prev))
    merged: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return "".join(f"\\U{a:08x}" if a == b else f"\\U{a:08x}-\\U{b:08x}" for a, b in merged)


_INVISIBLE = re.compile(f"[{_invisible_class()}]+")
_NON_ASCII = re.compile(r"[^\x00-\x7f]+")
_CHARS: dict[str, str] = {}


def _norm_char(ch: str) -> str:
    n = _CHARS.get(ch)
    if n is None:
        n = "" if _INVISIBLE.fullmatch(ch) else unicodedata.normalize("NFKC", ch)
        if len(_CHARS) < 50_000:
            _CHARS[ch] = n
    return n


def _normalise(text: str) -> tuple[str, array[int] | None]:
    """(the text to match on, the index in `text` of each of its chars), or
    (text, None) when matching on the text itself is the same."""
    if text.isascii():
        return text, None
    pieces: list[str] = []
    origin: array[int] = array("q")
    pos = 0
    if unicodedata.is_normalized("NFKC", text):
        if _INVISIBLE.search(text) is None:
            return text, None
        for m in _INVISIBLE.finditer(text):
            pieces.append(text[pos : m.start()])
            origin.extend(range(pos, m.start()))
            pos = m.end()
    else:
        for m in _NON_ASCII.finditer(text):
            pieces.append(text[pos : m.start()])  # ASCII is NFKC-stable and all visible
            origin.extend(range(pos, m.start()))
            for i in range(m.start(), m.end()):
                n = _norm_char(text[i])
                if n:
                    pieces.append(n)
                    origin.extend((i,) * len(n))
            pos = m.end()
    pieces.append(text[pos:])
    origin.extend(range(pos, len(text)))
    return "".join(pieces), origin


# ------------------------------------------------------------------ rules --
_DIGIT = "0-9۰-۹٠-٩"
D = f"[{_DIGIT}]"
# Not right after a digit (a letter or _ is fine: tel_0912…), nor after the
# decimal point of a number (0.9876543210 is a fraction, not a phone).
ND = f"(?<![{_DIGIT}])(?<![{_DIGIT}][.٫])"
NA = f"(?![{_DIGIT}])"
SEP = r"[\s\-.()]{0,3}"  # optional separators between digits
SEPR = r"[\s\-.]{1,3}"  # required separators
# A token shape glued to a Latin letter or digit is something else, except
# right after a JSON escape: in a JSON-dumped text a new line is the two
# characters \n, and a key at the start of a line follows that "n".
ESC = r"(?<=\\[ntr])"
NB = rf"(?:(?<![A-Za-z0-9])|{ESC})"
NL = rf"(?:(?<![a-z])|{ESC})"  # a word not glued to a letter before it
ZERO = "[0۰٠]"
NOT_DECIMAL = f"(?![.٫]{D})"  # 0.9… after a leading zero is a fraction
NINE = "[9۹٩]"
IR = "(?:98|۹۸|٩٨)"
_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _luhn(text: str) -> bool:
    digits = [int(c) for c in text.translate(_TO_ASCII) if c in "0123456789"]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return 13 <= len(digits) <= 19 and total % 10 == 0


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    repl: str
    groups: tuple[str | int, ...] = (0,)  # the first group that matched is masked
    needles: tuple[str, ...] = ()  # the rule runs only when one is in the text (lowercased)
    check: Callable[[str], bool] | None = None
    personal: bool = False  # a personal datum (kept by mask_secrets), not a credential


def _rule(
    pattern: str,
    repl: str,
    *,
    groups: tuple[str | int, ...] = (0,),
    needles: tuple[str, ...] = (),
    check: Callable[[str], bool] | None = None,
    flags: int = 0,
    personal: bool = False,
) -> _Rule:
    return _Rule(re.compile(pattern, flags), repl, groups, needles, check, personal)


_SECRET_WORDS = (
    r"api[_\-.]?key|apikey|client[_\-.]?secret|secret(?:[_\-.]?access)?(?:[_\-.]?key)?|"
    r"token|password|passwd|passphrase|"  # no \b: DB_PASSWORD=, accessToken: are caught
    rf"{NL}pass|{NL}pwd|(?:access|signing|ssh|private|encryption)[_\-.]?key|"
    r"credentials?|session[_\-.]?id|cookie|"
    r"رمز(?:\s?عبور)?|گذرواژه|پسورد|کلمه(?:\s?ی)?\s?عبور"
)
_CODE_WORDS = (
    rf"{NL}(?:otp|pin|cvv2?)(?:[_\-.\s]?code)?|verification[_\-.\s]?code|"
    r"کد\s?(?:تایید|تأیید|یکبار\s?مصرف|امنیتی)|رمز\s?(?:یکبار\s?مصرف|پویا)"
)
_ASSIGN = r"[\"']?\s{0,5}[:=]\s{0,5}"
_DIGITS = re.compile(D)

RULES: tuple[_Rule, ...] = (
    _rule(
        r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----[^-]{0,20000}-----END [A-Z ]{0,40}PRIVATE KEY-----",
        "[private-key]",
        needles=("private key-----",),
    ),
    _rule(  # cut short: the header and whatever key lines follow it
        r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"
        r"(?:\s{0,4}(?:[A-Za-z0-9+/=]{16,}|[A-Za-z][A-Za-z\-]{1,30}:[^\n]{0,200}))*",
        "[private-key]",
        needles=("private key-----",),
    ),
    _rule(  # OpenPGP armour: header lines, the key, its checksum (=XXXX), the END if any
        # (the markers are written in two pieces so no scanner reads them as a key)
        r"-----BEGIN PGP PRIVATE KEY"
        r" BLOCK-----"
        # a header line first: "Version" is base64 too
        r"(?:\s{0,4}(?:[A-Za-z][A-Za-z\-]{1,30}:[^\n]{0,200}|[A-Za-z0-9+/=]{4,}))*"
        r"(?:\s{0,4}-----END PGP PRIVATE KEY"
        r" BLOCK-----)?",
        "[private-key]",
        needles=("pgp private key block",),
    ),
    _rule(rf"{NB}sk-ant-[A-Za-z0-9_\-]{{8,}}", "[key]", needles=("sk-ant-",)),
    _rule(rf"{NB}sk-(?:proj-)?[A-Za-z0-9_\-]{{20,}}", "[key]", needles=("sk-",)),
    _rule(rf"{NB}hqa1\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[token]", needles=("hqa1.",)),
    _rule(rf"{NB}gh[pousr]_[A-Za-z0-9]{{20,}}", "[token]", needles=("gh",)),
    _rule(rf"{NB}github_pat_[A-Za-z0-9_]{{20,}}", "[token]", needles=("github_pat_",)),
    _rule(rf"{NB}(?:AKIA|ASIA)[0-9A-Z]{{16}}(?![A-Za-z0-9])", "[key]", needles=("akia", "asia")),
    _rule(rf"{NB}xox[abposr]-[A-Za-z0-9\-]{{10,}}", "[token]", needles=("xox",)),
    _rule(r"(?<![0-9])[0-9]{8,10}:[A-Za-z0-9_\-]{35}(?![A-Za-z0-9_\-])", "[token]", needles=(":",)),
    _rule(
        rf"{NB}eyJ[A-Za-z0-9_\-]{{8,}}\.[A-Za-z0-9_\-]{{8,}}\.[A-Za-z0-9_\-]{{8,}}",
        "[token]",
        needles=("eyj",),
    ),
    _rule(rf"{NB}hv[sbr]\.[A-Za-z0-9_\-]{{20,}}", "[token]", needles=("hvs.", "hvb.", "hvr.")),
    _rule(rf"{NB}AIza[0-9A-Za-z_\-]{{35}}", "[key]", needles=("aiza",)),
    _rule(rf"{NB}[sr]k_(?:live|test)_[A-Za-z0-9]{{16,}}", "[key]", needles=("k_live_", "k_test_")),
    _rule(
        rf"{NB}bearer\s{{1,5}}(?P<v>[A-Za-z0-9._~+/=\-]{{12,}})",
        "[token]",
        groups=("v",),
        needles=("bearer",),
        flags=re.I,
    ),
    _rule(  # base64 user:password; a plain word after "Basic" is left alone
        rf"{NB}Basic\s{{1,5}}(?P<v>(?=[A-Za-z0-9+/]{{0,400}}[0-9+/=])[A-Za-z0-9+/]{{12,}}={{0,2}})"
        r"(?![A-Za-z0-9+/=])",
        "[credentials]",
        groups=("v",),
        needles=("basic",),
    ),
    _rule(
        r"authorization" + _ASSIGN + r"[\"']?(?:(?:basic|bearer|digest|token|negotiate)\s{1,5})?"
        r"(?P<v>[A-Za-z0-9._~+/=\-]{6,})",
        MASK,
        groups=("v",),
        needles=("authorization",),
        flags=re.I,
    ),
    _rule(
        r"(?<![a-z0-9+.\-])[a-z][a-z0-9+.\-]{0,30}://(?P<v>[^\s/:@]{1,512}:[^\s/@]{1,256}@)",
        "[credentials]@",
        groups=("v",),
        needles=("://",),
        flags=re.I,
    ),
    _rule(
        rf"(?:{_SECRET_WORDS}){_ASSIGN}"
        r"(?:\"(?P<q>[^\"\n]{1,512})\"|'(?P<s>[^'\n]{1,512})'|(?P<v>[^\s\"',;]{6,512}))",
        MASK,
        groups=("q", "s", "v"),
        needles=(":", "="),
        flags=re.I,
    ),
    _rule(
        rf"(?:{_CODE_WORDS}){_ASSIGN}[\"']?(?P<v>{D}{{3,8}}){NA}",
        MASK,
        groups=("v",),
        needles=(":", "="),
        flags=re.I,
    ),
    _rule(
        r"(?:national[_\-.\s]?(?:code|id)|کد\s?ملی|شماره\s?ملی)[\"']?\s{0,5}[:=]?\s{0,5}[\"']?"
        rf"(?P<v>{D}(?:[\s\-]?{D}){{9}}){NA}",
        MASK,
        groups=("v",),
        needles=("national", "ملی"),
        flags=re.I,
        personal=True,
    ),
    _rule(  # not starting inside a JSON escape: \nali@x keeps its \n
        r"(?<!\\)[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63}){0,8}"
        r"\.[A-Za-z]{2,24}(?![A-Za-z])",
        "[email]",
        needles=("@",),
        personal=True,
    ),
    _rule(
        rf"{NB}IR(?:[\s\-.]?{D}){{24}}{NA}", "[iban]", needles=("ir",), flags=re.I, personal=True
    ),
    # Not inside a UUID or a hex string: "…-7000-8000-000000000003" is an id.
    _rule(
        rf"(?<![0-9A-Fa-f]-){ND}{D}{{4}}(?:[\s\-.]{{0,3}}{D}{{4}}){{3}}{NA}(?![A-Fa-f])",
        "[card]",
        check=_luhn,
        personal=True,
    ),
    # Iranian mobiles: 09…, +98 9…, 0098 9…, 98 9… (a bare 9xxxxxxxxx only when spaced
    # like a phone: a 10-digit rial amount is not one).
    _rule(
        rf"{ND}(?:(?:\+|00)?{IR}{SEP}(?:\(?{ZERO}\)?{SEP})?|{ZERO}{NOT_DECIMAL}{SEP})"
        rf"{NINE}(?:{SEP}{D}){{9}}{NA}",
        "[phone]",
        personal=True,
    ),
    _rule(rf"{ND}{NINE}{D}{{2}}{SEPR}{D}{{3}}{SEPR}{D}{{4}}{NA}", "[phone]", personal=True),
    # Landlines: 021-…, (021) …, +98 21 …
    _rule(
        rf"{ND}(?:(?:\+|00){IR}{SEP}\(?|\(?{ZERO})[1-8۱-۸١-٨]{D}\)?(?:{SEP}{D}){{8}}{NA}",
        "[phone]",
        personal=True,
    ),
    _rule(
        rf"(?<![{_DIGIT}+])\+[1-9۱-۹١-٩](?:{SEP}{D}){{7,14}}{NA}",
        "[phone]",
        needles=("+",),
        personal=True,
    ),
    _rule(
        rf"{ND}00[1-9]{D}{{0,2}}(?:{SEPR}{D}{{2,5}}){{2,5}}{NA}",
        "[phone]",
        needles=("00",),
        personal=True,
    ),
)
_DIGIT_RULES = frozenset(i for i, r in enumerate(RULES) if not r.needles)


def _spans(text: str, secrets_only: bool = False) -> list[tuple[int, int, str]]:
    """Non-overlapping (start, end, replacement) in `text`: when matches
    overlap, the one starting first (then the longest, then the earlier rule)
    is kept and stretched over the others, so nothing of any match leaks.
    `secrets_only`: the credential rules only (no personal data)."""
    low = text.lower()
    has_digit = _DIGITS.search(text) is not None
    found: list[tuple[int, int, int, str]] = []
    for prio, rule in enumerate(RULES):
        if secrets_only and rule.personal:
            continue
        if rule.needles and not any(n in low for n in rule.needles):
            continue
        if prio in _DIGIT_RULES and not has_digit:
            continue
        for m in rule.pattern.finditer(text):
            g = next((g for g in rule.groups if m.group(g) is not None), None)
            if g is None:
                continue
            s, e = m.span(g)
            if e <= s or (rule.check is not None and not rule.check(text[s:e])):
                continue
            found.append((s, -e, prio, rule.repl))
    found.sort()
    merged: list[tuple[int, int, str]] = []
    for s, neg_e, _, repl in found:
        e = -neg_e
        if merged and s < merged[-1][1]:
            ls, le, lr = merged[-1]
            if e > le:
                merged[-1] = (ls, e, lr)
            continue
        merged.append((s, e, repl))
    return merged


def _masks(text: str, secrets_only: bool = False) -> list[tuple[int, int, str]]:
    """(start, end, replacement) in `text` itself (not its normalised view):
    sorted and non-overlapping."""
    if not text:
        return []
    norm, origin = _normalise(text)
    out: list[tuple[int, int, str]] = []
    pos = 0
    for s, e, repl in _spans(norm, secrets_only):
        if origin is not None:
            s, e = origin[s], origin[e - 1] + 1
        s = max(s, pos)
        e = max(e, s)
        out.append((s, e, repl))
        pos = e
    return out


# -------------------------------------------------------------------- API --
def scrub(text: str, *, secrets_only: bool = False) -> str:
    """`text` with every secret and personal-data shape masked (never shortened);
    `secrets_only`: credentials only, personal data kept (see mask_secrets)."""
    masks = _masks(text, secrets_only)
    if not masks:
        return text
    out: list[str] = []
    pos = 0
    for s, e, repl in masks:
        out.append(text[pos:s])
        out.append(repl)
        pos = e
    out.append(text[pos:])
    return "".join(out)


def spans(text: str) -> list[tuple[int, int]]:
    """The [start, end) ranges of `text` that scrub(text) replaces, sorted,
    with touching or overlapping ranges merged."""
    merged: list[tuple[int, int]] = []
    for s, e, _ in _masks(text):
        if e <= s:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


_SECRET_KEY = re.compile(
    r"^(?:.*_)?(?:token|access_token|refresh_token|id_token|auth_token|bot_token|"
    r"secret|secret_key|client_secret|secret_access_key|password|passwd|pwd|pass|passphrase|"
    r"api_?key|access_key|signing_key|ssh_key|encryption_key|private_key(?:_pem)?|"
    r"authorization|cookies?|set_cookie|credentials?|session_?id|"
    r"otp|otp_code|pin|pin_code|cvv2?|verification_code|"
    r"e_?mails?|phones?|phone_numbers?|mobiles?|mobile_numbers?|tel|telephone|"
    r"national_id|national_code|ssn|iban|card_number)$"
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_KEY_SEP = re.compile(r"[\s\-.]+")


_PERSONAL_KEY = re.compile(
    r"^(?:.*_)?(?:e_?mails?|phones?|phone_numbers?|mobiles?|mobile_numbers?|tel|telephone|"
    r"national_id|national_code|ssn|iban|card_number)$"
)


def _key_form(name: str) -> str:
    return _KEY_SEP.sub("_", _CAMEL.sub("_", _normalise(name)[0])).lower()


def is_secret_key(name: str) -> bool:
    """Whether a key names a secret or a personal datum (snake, kebab or camel case)."""
    return _SECRET_KEY.match(_key_form(name)) is not None


def is_credential_key(name: str) -> bool:
    """Whether a key names a credential: a secret key that is no personal datum."""
    key = _key_form(name)
    return _SECRET_KEY.match(key) is not None and _PERSONAL_KEY.match(key) is None


# A name/value pair ({"name": "DB_PASSWORD", "value": ...}, as in environment
# lists and key-value stores): the value is a secret when the name names one.
_PAIR_NAMES = frozenset({"name", "key", "variable", "var", "env", "param", "parameter", "field"})
_PAIR_VALUES = frozenset({"value", "val"})
_CARD_FIRST = "23456"  # the first digit of the card networks (an epoch in ms starts with 1)


def _pair_secret(d: dict[Any, Any]) -> bool:
    return any(
        str(k).lower() in _PAIR_NAMES and isinstance(v, str) and is_secret_key(v)
        for k, v in d.items()
    )


def _number(n: int) -> int | str:
    """An integer as it is, unless its digits are a card or a phone number."""
    digits = str(abs(n))
    if len(digits) < 10:
        return n
    if 13 <= len(digits) <= 19 and digits[0] in _CARD_FIRST and _luhn(digits):
        return "[card]"
    out = scrub(digits)
    return n if out == digits else out


def redact(
    value: Any, *, max_string: int | None = None, max_list: int | None = None, _depth: int = 0
) -> Any:
    """A copy of `value` with secrets and personal data removed. Sizes are cut
    only when asked (what goes back to a model, see fit)."""
    if _depth > MAX_DEPTH:
        return "[too deep]"
    if isinstance(value, str):
        if max_string is not None and len(value) > max_string + CUT_MARGIN:
            # Cut before scrubbing (linear time); the margin keeps a secret that
            # straddles max_string whole, so the final cut never leaves a piece of it.
            value = value[: max_string + CUT_MARGIN]
        out = scrub(value)
        if max_string is None or len(out) <= max_string:
            return out
        return out[:max_string] + " …[cut]"
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return _number(value)
    if isinstance(value, dict):
        res: dict[str, Any] = {}
        pair = _pair_secret(value)
        for k, v in value.items():
            key = scrub(str(k))
            if key in res:
                key = f"{key}#{len(res)}"
            secret = is_secret_key(str(k)) or (pair and str(k).lower() in _PAIR_VALUES)
            if secret and not isinstance(v, bool) and v is not None:
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


def mask_secrets(value: Any, _depth: int = 0) -> Any:
    """A copy of `value` with credentials masked and everything else kept,
    numbers included (an amount, the card a payment goes to). Never shortened."""
    if _depth > MAX_DEPTH:
        return "[too deep]"
    if isinstance(value, str):
        return scrub(value, secrets_only=True)
    if isinstance(value, dict):
        res: dict[str, Any] = {}
        pair = any(
            str(k).lower() in _PAIR_NAMES and isinstance(v, str) and is_credential_key(v)
            for k, v in value.items()
        )
        for k, v in value.items():
            key = scrub(str(k), secrets_only=True)
            if key in res:
                key = f"{key}#{len(res)}"
            secret = is_credential_key(str(k)) or (pair and str(k).lower() in _PAIR_VALUES)
            if secret and not isinstance(v, bool) and v is not None:
                res[key] = MASK
            else:
                res[key] = mask_secrets(v, _depth + 1)
        return res
    if isinstance(value, list | tuple):
        return [mask_secrets(v, _depth + 1) for v in value]
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


def _big(value: Any, limit: int = THREAD_ABOVE) -> bool:
    """Whether the strings in `value` add up to more than `limit` chars."""
    stack, total = [value], 0
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, dict):
            stack.extend(v.values())
            total += sum(len(str(k)) for k in v)
        elif isinstance(v, list | tuple):
            stack.extend(v)
        if total > limit:
            return True
    return False


async def scrub_async(text: str) -> str:
    if len(text) <= THREAD_ABOVE:
        return scrub(text)
    return await asyncio.to_thread(scrub, text)


async def redact_async(
    value: Any, *, max_string: int | None = None, max_list: int | None = None
) -> Any:
    if not _big(value):
        return redact(value, max_string=max_string, max_list=max_list)
    return await asyncio.to_thread(
        functools.partial(redact, value, max_string=max_string, max_list=max_list)
    )


async def fit_async(value: Any, max_chars: int) -> tuple[Any, bool]:
    if not _big(value):
        return fit(value, max_chars)
    return await asyncio.to_thread(fit, value, max_chars)
