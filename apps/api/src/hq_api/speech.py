"""fa_speech_script (prompt 12 §4.1, contract §21.4): the spoken script of a
briefing, built by code from its written text. Deterministic, no model.

    script = fa_speech_script(markdown, refs={"D-000123": "خرید سرور"},
                              codes={"TY-CEO": "مدیرعامل تریدیار"})

What it does, in this order:
- markdown goes: headings, emphasis, code marks, links (their text stays),
  bare URLs, quotes, list marks; a table row is read as its cells;
- refs (D-000123, W-…, O-…, M-…, PR-082, …) are read as their titles (`refs`),
  else as their kind and number in words;
- employee codes (TY-CEO, HQ-TECH-MGR) are read as their Persian titles
  (`codes`), else as the role and the company;
- model names come from a fixed table (claude-opus-5-5 -> «اپوس پنج و نیم»);
- dates: a Jalali date (1405/08/01), a Jalali month (1405-08) and an ISO
  Gregorian date (2026-10-22, read as its Jalali day) become words; a clock
  time (09:30) too;
- money ($4.20 -> «چهار دلار و بیست سنت», $1.6M, 12 USD), percentages
  (15% / ۱۵٪), scaled figures (1.6M -> «یک و شش دهم میلیون»), thousands
  separators and decimals become Persian words;
- Persian and Arabic-Indic digits are read the same way as Latin ones.

No Latin (or Persian) digit is left in the result (`assert_spoken`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from hq_api.worker.jalali import MONTHS_FA, to_jalali

ONES = ("", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه")
TEENS = (
    "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده",
)  # fmt: skip
TENS = ("", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود")
HUNDREDS = ("", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد")
SCALES = ("", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون")
FRACTIONS = {1: "دهم", 2: "صدم", 3: "هزارم", 4: "ده‌هزارم", 5: "صدهزارم", 6: "میلیونیم"}
SUFFIX_SCALE = {"k": "هزار", "K": "هزار", "M": "میلیون", "B": "میلیارد", "T": "تریلیون"}
ZWNJ = "‌"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")

# The kinds of refs (contract §5-§21) as they are read when no title is known.
REF_KINDS = {
    "W": "کار",
    "D": "تصمیم",
    "O": "خروجی",
    "M": "مصوبه",
    "A": "پیام",
    "PR": "پروتکل",
    "DM": "یادداشت تصمیم",
    "WR": "مرور هفتگی",
    "BR": "گزارش",
    "HR": "دور ارزیابی",
    "NT": "یادداشت",
    "CL": "ادعا",
    "AK": "پرسش",
    "TE": "آموزش",
    "SK": "مهارت",
    "EV": "آزمون",
    "F": "یافته",
    "FD": "یافته",
    "CH": "چالش",
    "RC": "پرونده‌ی نجات",
    "SC": "گفت‌وگو",
    "KB": "مقاله",
    "FB": "بازخورد",
    "CR": "طرح",
    "DP": "اصل",
}
ROLES_FA = {
    "CEO": "مدیرعامل",
    "SYS": "سامانه",
    "ADV": "مشاور",
    "OVR": "ناظر کل",
    "PA": "دستیار",
    "LIB": "کتابدار",
    "MGR": "مدیر",
    "CTO": "مدیر فنی",
}
DEPARTMENTS_FA = {
    "TECH": "فنی",
    "GROWTH": "رشد",
    "SALES": "فروش",
    "PRODUCT": "محصول",
    "FIN": "مالی",
    "QUANT": "کوانت",
    "AIOPS": "عملیات هوش مصنوعی",
    "HR": "منابع انسانی",
    "OVS": "نظارت",
    "SUP": "پشتیبانی",
}
# Model names, read from a fixed table (prompt 12 §4.1).
MODEL_NAMES = {
    "opus": "اپوس",
    "sonnet": "سانِت",
    "haiku": "هایکو",
    "claude": "کلود",
    "gpt": "جی‌پی‌تی",
    "gemini": "جمنای",
    "deepseek": "دیپ‌سیک",
    "codex": "کودکس",
    "whisper": "ویسپر",
    "piper": "پایپر",
}
LETTERS_FA = {
    "A": "اِی", "B": "بی", "C": "سی", "D": "دی", "E": "ای", "F": "اِف", "G": "جی", "H": "اِچ",
    "I": "آی", "J": "جِی", "K": "کِی", "L": "اِل", "M": "اِم", "N": "اِن", "O": "او", "P": "پی",
    "Q": "کیو", "R": "آر", "S": "اِس", "T": "تی", "U": "یو", "V": "وی", "W": "دابلیو",
    "X": "اِکس", "Y": "وای", "Z": "زِد",
}  # fmt: skip
WORDS_FA = {"USD": "دلار", "OK": "اوکی", "API": "اِی‌پی‌آی", "CEO": "مدیرعامل"}


# ----------------------------------------------------------------- numbers --
def _below_1000(n: int) -> str:
    parts: list[str] = []
    if n >= 100:
        parts.append(HUNDREDS[n // 100])
    rest = n % 100
    if rest >= 20:
        parts.append(TENS[rest // 10])
        if rest % 10:
            parts.append(ONES[rest % 10])
    elif rest >= 10:
        parts.append(TEENS[rest - 10])
    elif rest > 0:
        parts.append(ONES[rest])
    return " و ".join(parts)


def int_words(n: int) -> str:
    """12345 -> «دوازده هزار و سیصد و چهل و پنج»; 1000 -> «هزار»."""
    if n == 0:
        return "صفر"
    if n < 0:
        return "منفی " + int_words(-n)
    groups: list[int] = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    if len(groups) > len(SCALES):
        return " ".join(
            int_words(int(d)) for d in str(sum(g * 1000**i for i, g in enumerate(groups)))
        )
    parts: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        if i == 1 and g == 1:
            parts.append("هزار")
        else:
            parts.append(_below_1000(g) + (f" {SCALES[i]}" if i else ""))
    return " و ".join(parts)


def ordinal_words(n: int) -> str:
    """1 -> «یکم», 3 -> «سوم», 23 -> «بیست و سوم», 30 -> «سی‌ام»."""
    w = int_words(n)
    if w.endswith("سه"):
        return w[:-2] + "سوم"
    if w.endswith("سی"):
        return w + ZWNJ + "ام"
    return w + "م"


def decimal_words(raw: str) -> str:
    """«1.6» -> «یک و شش دهم», «0.25» -> «بیست و پنج صدم», «-3» -> «منفی سه»."""
    s = raw.translate(_DIGITS).replace(",", "").strip()
    neg = s.startswith("-")
    s = s.lstrip("+-")
    whole, _, frac = s.partition(".")
    frac = frac.rstrip("0")
    if len(frac) > 6:
        q = Decimal("0." + frac).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        frac = format(q, "f").partition(".")[2].rstrip("0")
    head = int_words(int(whole or "0"))
    if frac:
        tail = f"{int_words(int(frac))} {FRACTIONS[len(frac)]}"
        out = tail if not whole or int(whole) == 0 else f"{head} و {tail}"
    else:
        out = head
    return ("منفی " if neg else "") + out


def money_words(raw: str, scale: str = "") -> str:
    """Dollars: «$4.20» -> «چهار دلار و بیست سنت»; «$1.6M» -> «یک و شش دهم میلیون دلار»."""
    s = raw.translate(_DIGITS).replace(",", "")
    if scale:
        return f"{decimal_words(s)} {SUFFIX_SCALE[scale]} دلار"
    try:
        amount = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return decimal_words(s) + " دلار"
    neg = amount < 0
    amount = abs(amount)
    dollars = int(amount)
    cents = int((amount - dollars) * 100)
    parts = []
    if dollars or not cents:
        parts.append(f"{int_words(dollars)} دلار")
    if cents:
        parts.append(f"{int_words(cents)} سنت")
    return ("منفی " if neg else "") + " و ".join(parts)


# ------------------------------------------------------------------- dates --
def jalali_date_words(y: int, m: int, d: int) -> str:
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return f"{int_words(y)} {int_words(m)} {int_words(d)}"
    return f"{ordinal_words(d)} {MONTHS_FA[m - 1]} {int_words(y)}"


def gregorian_date_words(y: int, m: int, d: int) -> str:
    try:
        jy, jm, jd = to_jalali(date(y, m, d))
    except ValueError:
        return f"{int_words(y)} {int_words(m)} {int_words(d)}"
    return jalali_date_words(jy, jm, jd)


def time_words(h: int, m: int) -> str:
    if m == 0:
        return f"ساعت {int_words(h)}"
    return f"ساعت {int_words(h)} و {int_words(m)} دقیقه"


# ---------------------------------------------------------------- markdown --
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def strip_markdown(text: str) -> list[str]:
    """Plain lines: no markdown marks; a table row becomes its cells."""
    out: list[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or _TABLE_SEP.match(line) or line.strip("-*_ ") == "":
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            line = "، ".join(c for c in cells if c and c not in ("—", "-"))
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = _BULLET.sub("", line)
        line = _LINK.sub(r"\1", line)
        line = _URL.sub("", line)
        line = re.sub(r"(\*\*|__|\*|`|~~)", "", line)
        line = line.replace("·", "، ").replace("→", "، ").replace("←", "، ").replace("—", "، ")
        line = re.sub(r"\s+", " ", line).strip(" ،")
        if line:
            out.append(line)
    return out


# -------------------------------------------------------------- the script --
_REF = re.compile(r"\b([A-Z]{1,3})-0*([0-9]{1,8})\b")
_CODE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)?)\b")
_MODEL = re.compile(
    r"\b(claude|gpt|gemini|deepseek)[- ]?(opus|sonnet|haiku|pro|flash)?[- ]?([0-9]+)(?:[-.]([0-9]+))?\b",
    re.IGNORECASE,
)
_JDATE = re.compile(r"\b(1[34][0-9]{2})/([0-9]{1,2})/([0-9]{1,2})\b")
_GDATE = re.compile(r"\b((?:19|20)[0-9]{2})-([0-9]{2})-([0-9]{2})\b")
_JMONTH = re.compile(r"\b(1[34][0-9]{2})-([0-9]{2})\b")
_TIME = re.compile(r"\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b")
_MONEY_PRE = re.compile(r"\$\s?(-?[0-9][0-9,]*(?:\.[0-9]+)?)([kKMBT])?\b")
_MONEY_POST = re.compile(r"\b(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s?(?:USD|usd|دلار)\b")
_PERCENT = re.compile(r"(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s?[%٪]")
_SCALED = re.compile(r"\b(-?[0-9][0-9,]*(?:\.[0-9]+)?)([kKMBT])\b")
_NUMBER = re.compile(r"-?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?")
_ACRONYM = re.compile(r"\b[A-Z]{2,10}\b")
_LEFT_DIGIT = re.compile(r"[0-9۰-۹٠-٩]")


def _model(m: re.Match[str]) -> str:
    vendor, family, major, minor = m.group(1), m.group(2), m.group(3), m.group(4)
    name = [MODEL_NAMES.get(vendor.lower(), vendor)]
    if family:
        name = [MODEL_NAMES.get(family.lower(), family.lower())]
    version = int_words(int(major))
    if minor is not None:
        version += " و نیم" if minor == "5" else f" و {int_words(int(minor))} دهم"
    return " ".join([*name, version])


def _code(m: re.Match[str], codes: Mapping[str, str], companies: Mapping[str, str]) -> str:
    whole = m.group(0)
    if whole in codes:
        return codes[whole]
    company, role = m.group(1), m.group(2)
    co = companies.get(company) or spell(company)
    head, _, tail = role.partition("-")
    if tail and tail in ROLES_FA and head in DEPARTMENTS_FA:
        title = f"{ROLES_FA[tail]} {DEPARTMENTS_FA[head]}"
    elif role in ROLES_FA:
        title = ROLES_FA[role]
    elif head in DEPARTMENTS_FA:
        title = f"{DEPARTMENTS_FA[head]} {spell(tail)}" if tail else DEPARTMENTS_FA[head]
    else:
        title = spell(role.replace("-", " "))
    return f"{title} {co}"


def spell(word: str) -> str:
    """An acronym letter by letter (TY -> «تی وای»); digits as words."""
    out = []
    for ch in word:
        if ch.isdigit():
            out.append(int_words(int(ch)))
        elif ch.upper() in LETTERS_FA:
            out.append(LETTERS_FA[ch.upper()])
        elif ch.strip():
            out.append(ch)
    return " ".join(out)


def _line(
    line: str,
    refs: Mapping[str, str] | Callable[[str], str | None],
    codes: Mapping[str, str],
    companies: Mapping[str, str],
) -> str:
    s = line.translate(_DIGITS)
    lookup = refs if callable(refs) else refs.get

    def ref(m: re.Match[str]) -> str:
        kind, num = m.group(1), m.group(2)
        title = lookup(m.group(0))
        if title:
            return title
        if kind not in REF_KINDS:
            return f"{spell(kind)} {int_words(int(num))}"
        return f"{REF_KINDS[kind]} شماره‌ی {int_words(int(num))}"

    s = _MODEL.sub(_model, s)
    s = _JDATE.sub(lambda m: jalali_date_words(*(int(g) for g in m.groups())), s)
    s = _GDATE.sub(lambda m: gregorian_date_words(*(int(g) for g in m.groups())), s)
    s = _JMONTH.sub(
        lambda m: (
            f"{MONTHS_FA[int(m.group(2)) - 1]} {int_words(int(m.group(1)))}"
            if 1 <= int(m.group(2)) <= 12
            else m.group(0)
        ),
        s,
    )
    s = _REF.sub(ref, s)
    s = _CODE.sub(lambda m: _code(m, codes, companies), s)
    s = _TIME.sub(lambda m: time_words(int(m.group(1)), int(m.group(2))), s)
    s = _MONEY_PRE.sub(lambda m: money_words(m.group(1), m.group(2) or ""), s)
    s = _MONEY_POST.sub(lambda m: money_words(m.group(1)), s)
    s = _PERCENT.sub(lambda m: f"{decimal_words(m.group(1))} درصد", s)
    s = _SCALED.sub(lambda m: f"{decimal_words(m.group(1))} {SUFFIX_SCALE[m.group(2)]}", s)
    s = _NUMBER.sub(lambda m: decimal_words(m.group(0)), s)
    s = _ACRONYM.sub(
        lambda m: WORDS_FA.get(m.group(0)) or companies.get(m.group(0)) or spell(m.group(0)), s
    )
    s = re.sub(r"\s+", " ", s).strip()
    if s and s[-1] not in ".!?؟:؛":
        s += "."
    return s


def fa_speech_script(
    text: str,
    *,
    refs: Mapping[str, str] | Callable[[str], str | None] | None = None,
    codes: Mapping[str, str] | None = None,
    companies: Mapping[str, str] | None = None,
) -> str:
    """The spoken Persian script of `text` (markdown): one sentence per line."""
    lines = [_line(line, refs or {}, codes or {}, companies or {}) for line in strip_markdown(text)]
    script = "\n".join(x for x in lines if x.strip(". "))
    # Anything still holding a digit (an exotic format) is read digit by digit.
    script = _LEFT_DIGIT.sub(
        lambda m: " " + int_words(int(m.group(0).translate(_DIGITS))) + " ", script
    )
    return re.sub(r"[ \t]+", " ", script).strip()


def assert_spoken(script: str) -> None:
    """No Latin or Persian digit is left (contract §21.4)."""
    found = _LEFT_DIGIT.search(script)
    if found:
        raise ValueError(f"a digit is left in the spoken script at {found.start()}")


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text) if w])
