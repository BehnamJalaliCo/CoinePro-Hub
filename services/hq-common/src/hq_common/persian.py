"""Deterministic Persian text normalisation for speech-to-text (contract §17.2).

API (stable, used by the stt service and by apps/api):
  normalise(text) -> str        Whisper's raw Persian made written-standard,
                                without changing a single word
  words(text) -> list[str]      the comparable words of a text (normalised,
                                punctuation and ZWNJ splits ignored)
  word_edit_distance(a, b) -> int
                                Levenshtein distance between the words of a and b
  wer(reference, hypothesis) -> float
                                word error rate (0.0 when both are empty)

What normalise() does, and nothing else (no translation, no paraphrase, no
spelling "fixes", numbers kept exactly as spoken):
  - Arabic letters to Persian: ي ى -> ی, ك -> ک.
  - The verb prefixes «می» / «نمی» joined to their verb with ZWNJ (U+200C):
    "می خواهم" -> "می‌خواهم"; written attached ("میخواهم") only for a list of
    verb stems, never for words that merely start with «می» (میز، میوه، میدان،
    میلیون، میگو، میمون ...).
  - The suffixes «ها»، «های»، «هایی»، «ترین»، «تر»، «ام»، «ای» joined with ZWNJ
    when Whisper wrote them as a separate word: "کتاب ها" -> "کتاب‌ها". «ام» and
    «ای» only after a word ending in a vowel letter (ه ی ا و), where they are
    the written suffix ("خسته ام" -> "خسته‌ام") and not the interjection
    ("گفتم ای خدا" stays). «تر» not after a few nouns it often qualifies as
    the adjective "wet" ("لباس تر"). Never inside a word: «تری»، «همایش»،
    «تنها» are untouched.
  - Persian punctuation: , ; ? -> ، ؛ ؟ next to Persian text (not inside
    numbers such as 1,000 or in Latin text), no space before it, one after.
  - Spaces: runs collapsed, trimmed.
"""

from __future__ import annotations

import re

ZWNJ = "\u200c"
PERSIAN_LETTER = "\u0621-\u063a\u0641-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc\u0622"
_LETTER = f"[{PERSIAN_LETTER}]"
_WORD = f"[{PERSIAN_LETTER}{ZWNJ}]+"

_ARABIC = str.maketrans({"\u064a": "\u06cc", "\u0649": "\u06cc", "\u0643": "\u06a9"})

# Present and past stems that follow «می»/«نمی» when Whisper writes them
# attached. Only these are split; every other word starting with «می» stays.
VERB_STEMS = (
    "خواه",
    "خوا",
    "کن",
    "کرد",
    "شو",
    "شد",
    "شه",
    "دان",
    "دون",
    "دانست",
    "رو",
    "رف",
    "ره",
    "رم",
    "گوی",
    "گفت",
    "گه",
    "گم",
    "توان",
    "تون",
    "تونست",
    "توانست",
    "آی",
    "آمد",
    "آد",
    "اد",
    "بین",
    "دید",
    "گیر",
    "گرفت",
    "ده",
    "دهد",
    "داد",
    "دم",
    "زن",
    "زد",
    "نویس",
    "نوشت",
    "خور",
    "خورد",
    "رس",
    "رسید",
    "ساز",
    "ساخت",
    "فرست",
    "فرستاد",
    "پرس",
    "پرسید",
    "گذار",
    "گذاشت",
    "گذر",
    "گذشت",
    "مان",
    "ماند",
    "خوان",
    "خواند",
    "دار",
    "داشت",
    "نشین",
    "نشست",
    "پذیر",
    "فهم",
    "فهمید",
    "شناس",
    "شناخت",
    "کش",
    "کشید",
    "بر",
    "برد",
    "آور",
    "آورد",
    "یاب",
    "یافت",
    "بخش",
    "پوش",
    "پوشید",
    "ترس",
    "ترسید",
    "خند",
    "خندید",
    "چرخ",
    "دو",
    "دوید",
    "سوز",
    "شکن",
    "شکست",
    "فروش",
    "فروخت",
    "خر",
    "خرید",
    "رسان",
    "گرد",
    "گردد",
    "افت",
    "افتاد",
    "اندیش",
    "پرداز",
    "پرداخت",
    "بند",
    "بست",
    "کار",
    "کاشت",
    "شنو",
    "شنید",
    "گشت",
    "گرد",
)
# Words that start with «می»/«نمی» + a stem above but are not verbs.
NOT_VERBS = frozenset(
    {
        "میز",
        "میزان",
        "میزبان",
        "میدان",
        "میدانی",
        "میوه",
        "میراث",
        "میل",
        "میلیون",
        "میلیارد",
        "میهن",
        "میانه",
        "میان",
        "میانگین",
        "میگو",
        "میگرن",
        "میمون",
        "میش",
        "میخ",
        "میکروب",
        "میکروفون",
        "میکرو",
        "میترا",
        "میرزا",
        "میر",
        "میرا",
        "میلاد",
        "میهمان",
        "میهمانی",
        "میکده",
        "میخانه",
        "میگساری",
        "میرس",
        "میرسن",
        "میدون",
        "میوند",
        "میگل",
        "میکل",
        "میشل",
        "میکائیل",
        "میکاپ",
        "میتینگ",
        "میراژ",
        "میرحسین",
        "میزگرد",
        "میشن",
        "نمیر",
    }
)
SUFFIXES = ("هایی", "هایم", "هایت", "هایش", "های", "ها", "ترین", "تر", "ام", "ای")
# «تر» right after these is usually the adjective "wet", not the comparative.
WET_NOUNS = frozenset(
    {"لباس", "دست", "چشم", "چشمان", "زمین", "علف", "خاک", "هوا", "مو", "موی", "پا"}
)
_VOWEL_END = ("ه", "ی", "ا", "و")

_SPACES = re.compile(r"[ \t\u00a0]+")
_SPACED_PREFIX = re.compile(rf"(?<![{PERSIAN_LETTER}{ZWNJ}])(ن?می) (?={_LETTER})")
_ATTACHED = re.compile(rf"(?<![{PERSIAN_LETTER}{ZWNJ}])(ن?می)({_LETTER}[{PERSIAN_LETTER}]*)")
_SUFFIX = re.compile(rf"({_WORD}) ({'|'.join(SUFFIXES)})(?![{PERSIAN_LETTER}{ZWNJ}])")
_PUNCT = {",": "،", ";": "؛", "?": "؟"}
_PUNCT_RE = re.compile(r"\s*([,;?،؛؟])")
_WORD_SPLIT = re.compile(rf"[^\w{ZWNJ}]+", re.UNICODE)


def _attached_prefix(m: re.Match[str]) -> str:
    prefix, rest = m.group(1), m.group(2)
    whole = prefix + rest
    if whole in NOT_VERBS or (prefix == "نمی" and "می" + rest in NOT_VERBS):
        return whole
    if any(rest.startswith(stem) for stem in VERB_STEMS):
        return prefix + ZWNJ + rest
    return whole


def _suffix(m: re.Match[str]) -> str:
    word, suffix = m.group(1), m.group(2)
    if suffix in ("ام", "ای") and not word.endswith(_VOWEL_END):
        return m.group(0)
    if suffix == "تر" and word in WET_NOUNS:
        return m.group(0)
    return word + ZWNJ + suffix


def _punct(m: re.Match[str], text: str) -> str:
    mark = m.group(1)
    start = m.start(1)
    before = text[:start].rstrip()
    after = text[m.end(1) : m.end(1) + 1]
    prev = before[-1:] if before else ""
    if mark in _PUNCT:
        between_digits = (
            prev.isdigit() and after.isdigit()
        )  # 1,000 or \u06f1,\u06f0\u06f0\u06f0: a number
        persian_side = bool(prev) and re.match(_LETTER, prev) is not None
        if between_digits or not persian_side:
            return m.group(0)
        mark = _PUNCT[mark]
    return mark


def normalise(text: str) -> str:
    """Whisper's raw Persian output in written-standard form (see module doc)."""
    t = text.translate(_ARABIC)
    t = _SPACES.sub(" ", t).strip()
    t = _SPACED_PREFIX.sub(lambda m: m.group(1) + ZWNJ, t)
    t = _ATTACHED.sub(_attached_prefix, t)
    t = _SUFFIX.sub(_suffix, t)
    t = _PUNCT_RE.sub(lambda m: _punct(m, t), t)
    t = re.sub(r"([،؛؟])(?=[^\s،؛؟.!»)\]])", r"\1 ", t)
    return _SPACES.sub(" ", t).strip()


def words(text: str) -> list[str]:
    """The comparable words of a text: normalised, with ZWNJ joins and
    punctuation ignored, so "می‌خواهم" and "می خواهم" compare equal."""
    t = normalise(text).replace(ZWNJ, "").lower()
    return [w for w in _WORD_SPLIT.split(t) if w]


def word_edit_distance(a: str | list[str], b: str | list[str]) -> int:
    """Levenshtein distance between two texts' words (insert, delete, substitute)."""
    x = words(a) if isinstance(a, str) else a
    y = words(b) if isinstance(b, str) else b
    prev = list(range(len(y) + 1))
    for i, wx in enumerate(x, 1):
        cur = [i]
        for j, wy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wx != wy)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate of `hypothesis` against `reference` (0.0 when both are empty;
    1.0 per word when the reference is empty and the hypothesis is not)."""
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else float(len(hyp))
    return word_edit_distance(ref, hyp) / len(ref)
