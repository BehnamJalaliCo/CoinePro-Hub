# ruff: noqa: RUF003
"""The outbound guard (prompt 10 §6, contract §19.6): code, not a model, over
EVERY message that leaves for a customer on every channel - a verbatim
answer, an agent's draft, a rule's template, the owner's own reply, the
mystery channel. One function, no author exception.

API (stable, used by apps/api):
  CODES, NO_OVERRIDE, MAX_CHARS
  Approved(links, codes, identifiers, company_codes, employee_codes, red_lines)
                          what this company may send: its approved
                          official/referral links and referral codes, the
                          handles/e-mails/phones/ids that may appear, the codes
                          of companies and employees (internal), the sealed
                          charter's red lines (prompt 11; empty today)
  approved_from_articles(rows, *, now=None) -> Approved
                          from the company's approved KB rows (kind referral /
                          official_link give links and codes; every handle,
                          e-mail, phone or long id written in an approved answer
                          may appear again)
  check(text, approved, *, max_chars=MAX_CHARS) -> Verdict(ok, reasons, findings)
  normalise(text), normalise_url(url), urls(text), referral_codes(text)

Refusal codes (in this order):
  asks_secret     the text ASKS the customer to send, tell, share or type a
                  password, private key, seed phrase, 2FA/SMS/verification
                  code, API secret or card number. Saying that support never
                  asks for them is fine (the sealed safety line).
  unknown_link    a URL that is not exactly (after normalise_url) one of the
                  company's approved links; another company's approved link
                  is unknown here.
  unknown_code    a referral-looking code (after a marker, or in a referral
                  URL) that is not exactly approved (case-insensitive).
  profit_promise  «سود تضمینی»، «بدون ضرر»، "guaranteed profit", "risk-free" ...
                  unless the clause negates it («هیچ سود تضمینی وجود ندارد»).
  customer_data   an @handle, e-mail, phone number or a standalone id of 6+
                  digits (a UID) that is not one of approved.identifiers.
  internal_data   the hub's refs (W-…, D-…, SC-…, KB-…@v ...), employee codes,
                  private addresses, internal names and paths, or a secret
                  hq_common.redact would mask.
  too_long        longer than max_chars.
  red_line        a red-line pattern of the sealed charter.
There is no override for asks_secret, profit_promise and red_line
(NO_OVERRIDE); the owner may edit and resend for the rest.

Encoding never hides a reason: every check runs on the text as its reader
sees it (normalise: percent-decoding to a fixed point, NFKC so full-width is
ASCII, Arabic ي ى ك ة as Persian, invisible marks and ZWNJ dropped, Persian and
Arabic-Indic digits as Latin, every dash a hyphen) and on the readable text
inside base64 and hex runs of 16+ characters. The word lists are data in
this module (reviewed), never a prompt. Pure and deterministic: no I/O.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from hq_common import redact

CODES = (
    "asks_secret",
    "unknown_link",
    "unknown_code",
    "profit_promise",
    "customer_data",
    "internal_data",
    "too_long",
    "red_line",
)
NO_OVERRIDE = frozenset({"asks_secret", "profit_promise", "red_line"})
MAX_CHARS = 3500
MAX_RUNS = 50  # base64/hex runs decoded per text


@dataclass(frozen=True)
class Approved:
    links: frozenset[str] = frozenset()
    codes: frozenset[str] = frozenset()
    identifiers: frozenset[str] = frozenset()
    company_codes: frozenset[str] = frozenset()
    employee_codes: frozenset[str] = frozenset()
    red_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reasons: tuple[str, ...]
    findings: tuple[dict[str, str], ...] = field(default=())

    @property
    def overridable(self) -> bool:
        """True when the owner may edit and resend: no reason without override."""
        return not NO_OVERRIDE.intersection(self.reasons)


# ------------------------------------------------------------ normalising --
_INVISIBLE = re.compile(
    "[\u00ad\u034f\u061c\u0640\u064b-\u065f\u0670\u115f\u1160\u17b4\u17b5\u180b-\u180f"
    "\u200b-\u200f\u202a-\u202e\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0]"
)
_LETTERS = str.maketrans(
    {
        "\u064a": "\u06cc",  # ي -> ی
        "\u0649": "\u06cc",  # ى -> ی
        "\u0643": "\u06a9",  # ك -> ک
        "\u0629": "\u0647",  # ة -> ه
        "\u06c0": "\u0647",  # ۀ -> ه
        "\u0623": "\u0627",  # أ -> ا
        "\u0625": "\u0627",  # إ -> ا
        "\u2018": "'",
        "\u2019": "'",
        "\u02bc": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u066a": "%",  # Arabic percent sign
        "\u066b": ".",  # Arabic decimal separator
        "\u066c": ",",  # Arabic thousands separator
    }
)
_DIGITS = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"  # Persian
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",  # Arabic-Indic
    "01234567890123456789",
)
_DASHES = re.compile("[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")
_SPACES = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")


def _decode_percent(text: str) -> str:
    for _ in range(10):
        once = unquote(text)
        if once == text:
            break
        text = once
    return text


def _plain(text: str) -> str:
    """The text as its reader sees it, case kept (URL paths, employee codes)."""
    text = _decode_percent(text)
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = _DASHES.sub("-", text.translate(_LETTERS).translate(_DIGITS))
    return _SPACES.sub(" ", text)


def normalise(text: str) -> str:
    """For matching: _plain() and casefolded."""
    return _plain(text).casefold()


# -------------------------------------------------------------------- URLs --
_TLDS = (
    "com|net|org|io|me|co|ir|app|xyz|info|biz|pro|exchange|finance|ai|dev|gg|cc|to|tv|us|uk|de|"
    "cn|ru|ae|tr|link|site|online|top|vip|club|live|network|trade|market|money|global|academy|"
    "capital|fund|cash|crypto|bot|chat|news|blog|page|website|space|store|shop|tech|cloud|world|"
    "email|one|ws|ly|eu|fr|nl|ch|se|pl|es|ca|au|jp|kr|hk|sg|asia|mobi|name|tel|game|games|"
    "bet|win|pw|su|ac|im|in|is|it|no|la|ma|sh"
)
_URL_CHARS = r"[^\s<>\"'`()\[\]{}|^،؛«»]"
_URL = re.compile(
    rf"(?:(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]{{1,15}}://{_URL_CHARS}+"
    rf"|(?<![\w@./:\-])www\.{_URL_CHARS}+"
    rf"|(?<![\w@./:\-])(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{{0,61}}[A-Za-z0-9])?\.)+"
    rf"(?:(?:{_TLDS})(?![A-Za-z0-9\-])(?::[0-9]{{1,5}})?(?:/{_URL_CHARS}*)?"
    rf"|[A-Za-z]{{2,24}}(?::[0-9]{{1,5}})?/{_URL_CHARS}*))",
    re.IGNORECASE,
)
_TRAIL = ".,;:!?'\"»«،؛…*_~"
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]{1,15}://", re.IGNORECASE)
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _strip_url(u: str) -> str:
    u = u.strip().rstrip(_TRAIL)
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1].rstrip(_TRAIL)
    return u


def normalise_url(url: str) -> str:
    """One spelling per link: scheme lower (none = https), host lower without
    "www." and a trailing dot, no default port, no fragment, the path decoded
    without a trailing "/", the query's parameters sorted. http stays http."""
    u = _strip_url(_plain(url))
    if u.startswith("//"):
        u = "https:" + u
    elif not _SCHEME.match(u):
        u = "https://" + u
    try:
        parts = urlsplit(u)
        port = parts.port
    except ValueError:
        return u.casefold()
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    netloc = parts.netloc
    userinfo = netloc.rpartition("@")[0] + "@" if "@" in netloc else ""
    port_s = f":{port}" if port is not None and port != _DEFAULT_PORTS.get(scheme) else ""
    path = parts.path.rstrip("/")
    query = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return f"{scheme}://{userinfo}{host}{port_s}{path}" + (f"?{query}" if query else "")


def _url_spans(plain: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for m in _URL.finditer(plain):
        raw = _strip_url(m.group(0))
        if not raw:
            continue
        out.append((m.start(), m.start() + len(raw), normalise_url(raw)))
    return out


def urls(text: str) -> list[str]:
    """Every URL of the text, normalised (in order, without repeats)."""
    return list(dict.fromkeys(u for _, _, u in _url_spans(_plain(text))))


# ---------------------------------------------------------- referral codes --
_CODE_MARKER = re.compile(
    r"(?:کد\s*(?:ی\s*)?(?:معرف\w*|دعوت\w*|رفرال|ریفرال|تخفیف|هدیه|پروموشن|ref\w*)"
    r"|\b(?:referral|referal|ref|invite|invitation|promo|promotion|bonus|affiliate|coupon)"
    r"[\s_\-]*(?:code|id)\b|\breferral\b|\bicode\b)"
    r"(?:\s*(?:[:=\-«»\"'`(\[]|\bis\b|\bour\b|\bthe\b|\byour\b|ما|را|رو|است|هست|شما|هلدینگ)\s*){0,4}"
    r"\s*(?P<code>[A-Za-z0-9]{4,20})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CODE_PARAMS = frozenset(
    {
        "ref",
        "icode",
        "invite_code",
        "invitecode",
        "invite",
        "inviteid",
        "invite_id",
        "referral",
        "referral_code",
        "referralcode",
        "refcode",
        "ref_code",
        "ref_id",
        "refid",
        "affiliate",
        "aff",
        "promo",
        "promocode",
    }
)
_CODE_SEGMENTS = frozenset({"ref", "invite", "referral", "refer", "aff", "affiliate"})
_EXCHANGE_HOSTS = (
    "lbank.com",
    "lbank.info",
    "lbank.me",
    "lbkex.com",
    "binance.com",
    "bybit.com",
    "okx.com",
    "kucoin.com",
    "mexc.com",
    "bitget.com",
    "gate.io",
    "gate.com",
    "htx.com",
    "huobi.com",
    "coinex.com",
    "bingx.com",
    "toobit.com",
    "nobitex.ir",
    "wallex.ir",
    "ramzinex.com",
    "bitpin.ir",
    "exir.io",
)


def _exchange(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _EXCHANGE_HOSTS)


def _url_codes(url: str) -> list[str]:
    """The referral codes a normalised URL carries (path segment or parameter)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return []
    host = (parts.hostname or "").lower()
    on_exchange = _exchange(host)
    out: list[str] = []
    segs = [s for s in parts.path.split("/") if s]
    for i, seg in enumerate(segs[:-1]):
        low = seg.lower()
        if low in _CODE_SEGMENTS or (on_exchange and low in ("r", "i", "join")):
            nxt = segs[i + 1].strip()
            if 0 < len(nxt) <= 64:
                out.append(nxt)
    for k, v in parse_qsl(parts.query, keep_blank_values=False):
        key = k.lower()
        if key in _CODE_PARAMS or (on_exchange and key in ("r", "code", "c")):
            v = v.strip()
            if 0 < len(v) <= 64:
                out.append(v)
    return out


def _codes_in(plain: str, spans: list[tuple[int, int, str]]) -> list[str]:
    codes: list[str] = []
    for m in _CODE_MARKER.finditer(plain):
        code = m.group("code")
        if any(ch.isdigit() for ch in code) or code.isupper():
            codes.append(code)
    for _, _, u in spans:
        codes += _url_codes(u)
    return list(dict.fromkeys(codes))


def referral_codes(text: str) -> list[str]:
    """Referral-looking codes: after a marker (کد معرف، referral code ...) and
    in referral URLs (/ref/<code>, ?ref=, icode=, invite_code= ...)."""
    plain = _plain(text)
    return _codes_in(plain, _url_spans(plain))


# ------------------------------------------------------------- the words --
_W = r"(?<!\w)"  # a word starts here (Persian letters are \w too)
_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "password",
        re.compile(
            rf"{_W}(?:رمز(?!\s*ارز)(?!نگار)(?!گشا)|پسورد|پس\s*ورد|گذرواژه|کلمه\s*(?:ی\s*)?عبور)"
            r"|\b(?:password|passwords|passcode|passwd|pin(?:\s*code)?)\b"
        ),
    ),
    ("private_key", re.compile(rf"{_W}کلید\s*(?:ی\s*)?خصوصی|\bprivate[\s\-]*keys?\b")),
    (
        "seed_phrase",
        re.compile(
            rf"{_W}(?:عبارت|کلمات|کلمه\s*های|جمله)\s*(?:ی\s*)?(?:های\s*)?(?:بازیابی|امنیتی|پشتیبان)"
            rf"|{_W}سید\s*فریز|{_W}(?:12|24)\s*کلمه"
            r"|\b(?:seed(?:\s*(?:phrase|words?))?|mnemonic|recovery\s*(?:phrase|words?|seed)"
            r"|secret\s*(?:recovery\s*)?phrase|backup\s*phrase)\b"
        ),
    ),
    (
        "otp_code",
        re.compile(
            rf"{_W}کد\s*(?:ی\s*)?(?:تایید|تائید|پیامک\w*|اس\s*ام\s*اس|sms|ورود|امنیتی|دو\s*عاملی|"
            r"دومرحله\w*|دو\s*مرحله\w*|یک\s*بار\s*مصرف|یکبار\s*مصرف|otp|2fa|گوگل|google|احراز\w*|"
            r"[0-9]+\s*رقمی)"
            rf"|{_W}رمز\s*(?:یک\s*بار|یکبار|پویا)"
            r"|\b(?:2fa|otp|totp|one[\s\-]*time\s*(?:pass)?(?:code|word)|sms\s*code"
            r"|verification\s*code|confirmation\s*code|auth(?:entication|enticator)?\s*code"
            r"|security\s*code|[0-9]+[\s\-]*digit\s*code|google\s*authenticator)\b"
        ),
    ),
    (
        "api_secret",
        re.compile(
            r"\b(?:api[\s_\-]*(?:secret|key)s?|secret[\s_\-]*keys?)\b"
            rf"|{_W}کلید\s*(?:ی\s*)?(?:api|ای\s*پی\s*آی|ای\s*پی\s*ای)|{_W}سکرت\s*کی"
        ),
    ),
    (
        "card",
        re.compile(
            rf"{_W}شماره\s*(?:ی\s*)?کارت|{_W}سی\s*وی\s*وی|{_W}تاریخ\s*انقضا\w*\s*کارت"
            r"|\bcard\s*(?:number|no|details?)\b|\bcvv2?\b"
        ),
    ),
)
# Asking (positive, to us): Persian imperatives and "we need"; English
# imperatives (never after a modal or a subject: "LBank will send a code" is
# not a request) and "we need".
_NOT_IMPERATIVE = (
    r"(?<!will\s)(?<!'ll\s)(?<!would\s)(?<!may\s)(?<!might\s)(?<!can\s)(?<!could\s)"
    r"(?<!shall\s)(?<!we\s)(?<!they\s)(?<!it\s)(?<!which\s)(?<!that\s)"
)
_ASK = re.compile(
    rf"{_W}بفرست(?:ید|ین|ی)?(?!\w)|{_W}بگو(?:یید|ئید|ید|ین|ی)?(?!\w)"
    rf"|{_W}بنویس(?:ید|ین|ی)?(?!\w)|{_W}بده(?:ید|ین)?(?!\w)|{_W}بد(?:ید|ین)(?!\w)"
    rf"|{_W}بفرما(?:یید|ئید|ید|ین)?(?!\w)"
    rf"|{_W}(?:ارسال|اعلام|شیر|share|پیام|اطلاع)\s*(?:کن(?:ید|ین)?|نمایید|بفرمایید|بدید|بدهید)(?!\w)"
    rf"|{_W}در\s*اختیار\s*(?:ما|پشتیبانی|کارشناس\w*|همکاران\w*)?\s*(?:بگذار\w*|قرار\s*(?:ده|بده)\w*)"
    rf"|{_W}(?:میخواهیم|میخوایم|میخوام|میخواهم|لازم\s*دار(?:یم|م)|نیاز\s*دار(?:یم|م)"
    r"|احتیاج\s*دار(?:یم|م))(?!\w)"
    rf"|{_NOT_IMPERATIVE}\b(?:send|forward|dm|share)\b(?!\s+you\b)"
    r"|\btell\s+(?:us|me)\b|\bgive\s+(?:us|me|it|them)\b"
    r"|\b(?:reply|respond|answer)\s+with\b|\b(?:we|i)\s+(?:need|require|want)\b|\bneed\s+your\b"
)
# Typing it somewhere: only when the place is here (this chat, a link, a form, a bot).
_ENTER = re.compile(
    rf"{_W}(?:وارد|تایپ|جایگذاری|پیست|کپی)\s*(?:کن(?:ید|ین)?|نمایید|بفرمایید)(?!\w)"
    r"|\b(?:enter|type|paste|input|write|fill\s+in|submit|provide)\b"
)
_HERE = re.compile(
    rf"{_W}(?:اینجا|همینجا|این\s*جا|لینک|فرم|ربات|بات|چت|پایین|زیر|همین\s*صفحه|پیوند)"
    r"|\b(?:here|below|this\s+(?:chat|bot|form|link|page|thread)|the\s+(?:link|form)\s+below|reply"
    r"|our\s+bot|to\s+us|with\s+us)\b"
)
_NEGATION = re.compile(
    rf"{_W}(?:هرگز|هیچ\w*|نه|نباید\w*|نمی\w*|"
    r"ن(?:فرست|گو|ده|دی|کن|کرد|زن|نویس|گذار|خواه|پرس|دار|یست|فرما|پذیر|گیر)\w*"
    r"|ن(?:شود|شوید|شده|شد)(?!\w))(?!\w)"
    r"|\b(?:never|not|no|none|nobody|nothing|neither|nor|without|don'?t|doesn'?t|didn'?t|won'?t"
    r"|wouldn'?t|shouldn'?t|mustn'?t|cannot|can'?t|isn'?t|aren'?t)\b"
)
_TRADE = re.compile(rf"{_W}(?:سود|معامله|ترید|سرمایه|کپی|ربات|سیگنال|بازار|خرید|فروش|پول)")
_PROFIT: tuple[tuple[re.Pattern[str], re.Pattern[str] | None], ...] = (
    (
        re.compile(
            rf"{_W}سود\s*(?:ی\s*)?(?:تضمین\w*|قطعی|حتمی|ثابت|بی\s*ریسک|بدون\s*ریسک|بدون\s*ضرر"
            r"|صد\s*در\s*صد\w*|100\s*(?:%|درصد)\w*)"
            rf"|{_W}تضمین\s*(?:ی\s*)?(?:سود|بازده\w*|درآمد|برگشت\s*سرمایه|سوددهی)"
            rf"|{_W}(?:بازده|درآمد|سوددهی)\s*(?:ی\s*)?(?:تضمین\w*|قطعی|حتمی|ثابت)"
            rf"|{_W}بدون\s*(?:هیچ\s*)?(?:ضرر|زیان|ریسک)|{_W}(?:ریسک|ضرر|زیان)\s*صفر"
            rf"|{_W}صفر\s*(?:ریسک|ضرر)|{_W}حتما\s+(?:\w+\s+){{0,2}}سود"
            r"|(?:100|صد)\s*(?:%|درصد)\s*(?:سود|تضمین)"
            rf"|{_W}(?:پول|سرمایه)\w*\s+(?:\w+\s+){{0,3}}(?:دو|سه|چند)\s*برابر"
        ),
        None,
    ),
    (re.compile(rf"{_W}بی\s*(?:ضرر|زیان|ریسک)"), _TRADE),
    (
        re.compile(
            r"\bguarantee[sd]?\s+(?:you\s+)?(?:an?\s+|your\s+)?(?:profits?|returns?|income|gains?"
            r"|earnings?|roi)\b"
            r"|\b(?:profits?|returns?|income|gains?|earnings?|roi)\s+(?:are\s+|is\s+)?guaranteed\b"
            r"|\bguaranteed\s+(?:\w+\s+)?(?:profits?|returns?|income|gains?|earnings?|roi|wins?)\b"
            r"|\brisk[\s\-]*free\b|\bno[\s\-]*risk\b|\bzero[\s\-]*risk\b"
            r"|\bwithout\s+(?:any\s+)?(?:risk|loss(?:es)?)\b|\bno[\s\-]*loss(?:es)?\b"
            r"|\b(?:can'?t|cannot|can\s+not)\s+lose\b(?!\s+(?:access|your\s+(?:password|key|account"
            r"|code|seed)))"
            r"|\bnever\s+lose\s+(?:your\s+|any\s+)?(?:money|funds?|capital|investment)\b"
            r"|\b100\s*%\s*(?:profits?|guaranteed|returns?|wins?)\b|\bsure[\s\-]*(?:profit|win|fire)\b"
            r"|\bdouble\s+your\s+(?:money|investment|capital|funds?)\b"
            r"|\bfixed\s+(?:daily|weekly|monthly)\s+(?:profits?|returns?|income)\b"
        ),
        None,
    ),
)
_SENTENCE = re.compile(r"[.!?؟\n;؛:]+|\s[-]\s")
_CLAUSE = re.compile(rf"[،,()\[\]]|{_W}(?:ولی|اما|بلکه)(?!\w)|\b(?:but|however|although)\b")


def _clauses(folded: str) -> list[list[str]]:
    return [
        [c for c in _CLAUSE.split(sentence) if c and c.strip()]
        for sentence in _SENTENCE.split(folded)
        if sentence.strip()
    ]


def _asks_secret(folded: str) -> list[str]:
    """The secret kinds the text asks for (per clause; a clause without a verb
    takes the nearest one after it, else before it: «رمز، کلید ... را بفرستید»)."""
    found: list[str] = []
    for sentence in _clauses(folded):
        verb = [bool(_ASK.search(c) or _NEGATION.search(c) or _ENTER.search(c)) for c in sentence]
        for i, clause in enumerate(sentence):
            kinds = [k for k, rx in _SECRETS if rx.search(clause)]
            if not kinds:
                continue
            j = i
            if not verb[i]:
                after = [k for k in range(i + 1, len(sentence)) if verb[k]]
                before = [k for k in range(i - 1, -1, -1) if verb[k]]
                if not after and not before:
                    continue
                j = after[0] if after else before[0]
            c = sentence[j]
            if _NEGATION.search(c):
                continue
            asked = _ASK.search(c) or (_ENTER.search(c) and _HERE.search(c))
            if asked:
                found += kinds
    return list(dict.fromkeys(found))


def _profit(folded: str) -> list[str]:
    found: list[str] = []
    for sentence in _clauses(folded):
        for clause in sentence:
            for rx, context in _PROFIT:
                for m in rx.finditer(clause):
                    if context is not None and not context.search(clause):
                        continue
                    rest = clause[: m.start()] + " " + clause[m.end() :]
                    if _NEGATION.search(rest):
                        continue
                    found.append(m.group(0).strip()[:40])
    return found


# ----------------------------------------------------------- identifiers --
_EMAIL = re.compile(
    r"(?<![\w.%+\-])[a-z0-9._%+\-]{1,64}@[a-z0-9\-]{1,63}(?:\.[a-z0-9\-]{1,63}){0,8}\.[a-z]{2,24}"
    r"(?![a-z])",
    re.IGNORECASE,
)
_HANDLE = re.compile(r"(?<![\w@.])@[a-z][a-z0-9_]{3,31}(?!\w)", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<![\w+])(?:\+|00)[1-9](?:[\s\-()]{0,2}[0-9]){7,14}(?![0-9])"
    r"|(?<![\w])09[0-9]{2}(?:[\s\-]?[0-9]){7}(?![0-9])"
)
_UNIT = (
    r"usdt|usd|usdc|dollars?|دلار|تومان|ریال|تتر|btc|eth|trx|bnb|sol|درصد|%|\$|سکه|کوین|coins?"
    r"|ساتوشی|sats?|lbk|واحد|عدد"
)
_ID = re.compile(rf"(?<![\w.,/:%$€£#\-])[0-9]{{6,20}}(?![0-9.,%]|\s*(?:{_UNIT})(?!\w))")


def _phone_canon(text: str) -> str:
    d = re.sub(r"[^0-9]", "", text)
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("0") and len(d) == 11 and d[1] == "9":
        d = "98" + d[1:]
    return d


def _identifiers(folded: str) -> list[tuple[str, str]]:
    """(kind, canonical form) of every handle, e-mail, phone and long id."""
    out: list[tuple[str, str]] = []
    rest = folded
    for m in _EMAIL.finditer(folded):
        out.append(("email", m.group(0).casefold()))
    rest = _EMAIL.sub(" ", rest)
    for m in _HANDLE.finditer(rest):
        out.append(("handle", m.group(0).casefold()))
    rest = _HANDLE.sub(" ", rest)
    for m in _PHONE.finditer(rest):
        out.append(("phone", _phone_canon(m.group(0))))
    rest = _PHONE.sub(" ", rest)
    for m in _ID.finditer(rest):
        out.append(("id", m.group(0)))
    return out


def _canon_ids(values: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for v in values:
        f = normalise(str(v)).strip()
        if not f:
            continue
        out.add(f)
        if f.startswith("@"):
            out.add(f[1:])
        else:
            out.add("@" + f)
        digits = re.sub(r"[^0-9]", "", f)
        if digits and len(digits) >= 6 and re.fullmatch(r"[0-9+\s\-()]+", f):
            out.add(_phone_canon(f))
            out.add(digits)
    return frozenset(out)


# ----------------------------------------------------------- internal data --
_INTERNAL_REF = re.compile(
    r"(?<![A-Za-z0-9])(?:[WDO]-\d{6,}|(?:I|N|P|S|C|AP|PV|ST)-\d{4,6}|SC-\d{6,}"
    r"|KB-\d{4,6}(?:@\d+)?|TM-\d{4,6}(?:@\d+)?|LR-\d{4,6}(?:@\d+)?|RC-\d{6,}|FB-\d{6,}"
    r"|FI-\d+|PR-\d{3,}|M-\d+|EV-\d{3,6}|TE-\d{4,8}|NP-\d{4}Q[1-4]-[A-Z][A-Z0-9]{1,9})"
    r"(?![A-Za-z0-9])"
)
_EMPLOYEE = re.compile(
    r"(?<![A-Za-z0-9\-])([A-Za-z][A-Za-z0-9]{1,9})-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?(?![A-Za-z0-9])"
)
_IPV4 = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_PRIVATE_NETS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "0.0.0.0/8",
    )
)
_HUB = re.compile(
    r"/internal(?![\w])|:8000\b|\bopenbao\b|(?<![\w])kv/|\btemporal\b|\bllm[\-_]router\b"
    r"|\.internal\b|\blocalhost\b|\bhq-(?:internal|core|agent|edge|egress|llm|prov)\b"
    r"|\b(?:postgres(?:ql)?|nats|redis|valkey)://|\b(?:api|worker|gateway|egress|opa):[0-9]{2,5}\b"
)


def _internal(plain: str, folded: str, approved: Approved) -> list[str]:
    found: list[str] = []
    if _INTERNAL_REF.search(plain):
        found.append("internal_ref")
    employees = {e.upper() for e in approved.employee_codes}
    companies = {c.upper() for c in approved.company_codes}
    for m in _EMPLOYEE.finditer(plain):
        code = m.group(0)
        if code.upper() in employees or (code.isupper() and m.group(1) in companies):
            found.append("employee_code")
            break
    for m in _IPV4.finditer(plain):
        try:
            ip = ipaddress.ip_address(m.group(0))
        except ValueError:
            continue
        if any(ip in n for n in _PRIVATE_NETS):
            found.append("private_address")
            break
    if re.search(r"(?<![\w:])::1(?![\w:])", plain):
        found.append("private_address")
    if _HUB.search(folded):
        found.append("hub_internal")
    if redact.scrub(plain, secrets_only=True) != plain:
        found.append("secret")
    return found


# ----------------------------------------------------------- hidden runs --
_B64_RUN = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")
_HEX_RUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")


def _b64(run: str) -> list[bytes]:
    raw = run.rstrip("=")
    padded = raw + "=" * (-len(raw) % 4)
    out: list[bytes] = []
    for alt in (None, b"-_"):
        try:
            out.append(base64.b64decode(padded, altchars=alt, validate=True))
        except (binascii.Error, ValueError):
            continue
    return out


def _hidden(plain: str) -> list[str]:
    """The readable text inside base64 and hex runs of 16+ characters."""
    blobs = [bytes.fromhex(m.group(0)) for m in _HEX_RUN.finditer(plain)][:MAX_RUNS]
    for m in list(_B64_RUN.finditer(plain))[:MAX_RUNS]:
        blobs += _b64(m.group(0))
    out: list[str] = []
    for blob in blobs:
        try:
            t = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(t) >= 4 and sum(ch.isprintable() or ch.isspace() for ch in t) >= 0.9 * len(t):
            out.append(_plain(t))
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------- API --
def _short_url(u: str) -> str:
    try:
        parts = urlsplit(u)
    except ValueError:
        return u[:40]
    return f"{parts.hostname or ''}{parts.path}"[:60] + ("?…" if parts.query else "")


def _mask_code(code: str) -> str:
    return f"{code[:3]}…({len(code)})" if len(code) > 3 else f"…({len(code)})"


def _red_line(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def check(text: str, approved: Approved, *, max_chars: int = MAX_CHARS) -> Verdict:
    """The guard's verdict on one outbound message (the same for every author)."""
    findings: list[tuple[str, str]] = []
    if len(text) > max_chars:
        findings.append(("too_long", f"{len(text)} > {max_chars} characters"))
    links = {normalise_url(u) for u in approved.links if u.strip()}
    codes = {normalise(c).strip() for c in approved.codes if c.strip()}
    for u in links:
        codes.update(normalise(c) for c in _url_codes(u))
    ids = _canon_ids([*approved.identifiers, *approved.codes])
    red = [_red_line(p) for p in approved.red_lines if p.strip()]
    plain = _plain(text)
    if redact.scrub(text, secrets_only=True) != text:  # as written (redact normalises itself)
        findings.append(("internal_data", "secret"))
    for view in [plain, *_hidden(plain)]:
        folded = view.casefold()
        spans = _url_spans(view)
        for kind in _asks_secret(folded):
            findings.append(("asks_secret", f"asks for {kind}"))
        for _, _, u in spans:
            if u not in links:
                findings.append(("unknown_link", _short_url(u)))
        for c in _codes_in(view, spans):
            if normalise(c).strip() not in codes:
                findings.append(("unknown_code", _mask_code(c)))
        for what in _profit(folded):
            findings.append(("profit_promise", what))
        no_urls = view
        for s, e, _ in reversed(spans):
            no_urls = no_urls[:s] + " " + no_urls[e:]
        for kind, value in _identifiers(no_urls.casefold()):
            if value not in ids and value.lstrip("@") not in ids:
                findings.append(("customer_data", kind))
        for kind in _internal(view, folded, approved):
            findings.append(("internal_data", kind))
        if any(rx.search(folded) or rx.search(view) for rx in red):
            findings.append(("red_line", "a red line of the sealed charter"))
    unique = list(dict.fromkeys(findings))
    reasons = tuple(c for c in CODES if any(f[0] == c for f in unique))
    return Verdict(
        ok=not reasons,
        reasons=reasons,
        findings=tuple({"code": c, "what": w} for c, w in unique),
    )


def _jsonish(value: Any) -> Any:
    if isinstance(value, str | bytes):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def approved_from_articles(
    articles: Iterable[Mapping[str, Any]], *, now: datetime | None = None
) -> Approved:
    """What a company may send, from its approved KB rows (support.kb_articles):
    referral / official_link rows give links and codes; every handle, e-mail,
    phone or long id written in an approved answer may appear again. A row
    that is not approved (or expired at `now`) gives nothing. Company and
    employee codes are the caller's (dataclasses.replace)."""
    links: set[str] = set()
    codes: set[str] = set()
    identifiers: set[str] = set()
    for row in articles:
        status = row.get("status")
        if status is not None and status != "approved":
            continue
        expires = row.get("expires_at")
        if now is not None and isinstance(expires, datetime) and expires <= now:
            continue
        if row.get("kind") in ("referral", "official_link"):
            for link in _jsonish(row.get("links")) or []:
                url = link.get("url") if isinstance(link, Mapping) else link
                if isinstance(url, str) and url.strip():
                    links.add(normalise_url(url))
            for code in _jsonish(row.get("codes")) or []:
                value = code.get("code") if isinstance(code, Mapping) else code
                if isinstance(value, str) and value.strip():
                    codes.add(value.strip())
        answer = row.get("answer_md")
        if isinstance(answer, str) and answer:
            plain = _plain(answer)
            no_urls = _URL.sub(" ", plain)
            identifiers.update(v for _, v in _identifiers(no_urls.casefold()))
    return Approved(
        links=frozenset(links), codes=frozenset(codes), identifiers=frozenset(identifiers)
    )
