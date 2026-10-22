"""Prompt 10 §1.2-§1.3: a customer's message is masked before it is stored or
read by a model (seed phrases, private keys, cards on top of §16.6), and a
customer is known outside support only by an HMAC pseudonym."""

from __future__ import annotations

import hashlib

import pytest

from hq_common import customer_mask as M
from hq_common import pseudonym as P

WORDS = sorted(M.wordlist())
TWELVE = " ".join(WORDS[100:112])
TWENTY_FOUR = " ".join(WORDS[500:524])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58check(payload: bytes) -> str:
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out


def _luhn(prefix: str) -> str:
    for d in "0123456789":
        n = prefix + d
        total = 0
        for i, c in enumerate(reversed(n)):
            x = int(c)
            if i % 2:
                x = x * 2 - 9 if x > 4 else x * 2
            total += x
        if total % 10 == 0:
            return n
    raise AssertionError


KEY_HEX = hashlib.sha256(b"not a real key").hexdigest()  # 64 hex digits, made at run time
WIF = _b58check(b"\x80" + bytes.fromhex(KEY_HEX))
WIF_COMPRESSED = _b58check(b"\x80" + bytes.fromhex(KEY_HEX) + b"\x01")
CARD = _luhn("603799759940414")
ARMOUR = "-" * 5
PK = "PRIVATE " + "KEY"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def test_the_wordlist_is_the_pinned_bip39_list() -> None:
    assert len(WORDS) == 2048 and WORDS[0] == "abandon" and "zoo" in WORDS


@pytest.mark.parametrize(
    "text",
    [
        f"سلام، کلمات کیف پولم این‌ها هستند: {TWELVE} لطفاً کمک کنید",
        TWENTY_FOUR,
        TWELVE.upper(),
        ", ".join(TWELVE.split()),
        "\n".join(f"{i}. {w}" for i, w in enumerate(TWELVE.split(), 1)),
        " ".join(f"({i}) {w}" for i, w in enumerate(TWELVE.split(), 1)),
        # one typo inside the phrase does not save it
        " ".join([*TWELVE.split()[:5], "abandn", *TWELVE.split()[5:]]),
        # full-width letters (NFKC) and an invisible split
        TWELVE.replace(WORDS[100], "".join(chr(ord(c) + 0xFEE0) for c in WORDS[100])),
        TWELVE.replace(" ", "​ ", 3),
    ],
)
def test_a_seed_phrase_is_masked(text: str) -> None:
    out = M.mask(text)
    assert "seed_phrase" in out.kinds and out.needs_safety_line
    assert M.SEED in out.text
    for w in TWELVE.split()[:11]:
        assert w not in out.text.lower(), w


@pytest.mark.parametrize(
    "text",
    [
        " ".join(WORDS[100:111]),  # eleven words
        "I can not access my account since the update please help me today",
        "abandon ability able about above absent سلام absorb abstract absurd abuse access accident",
        "قیمت امروز چند است؟",
    ],
)
def test_ordinary_text_is_not_a_seed_phrase(text: str) -> None:
    assert "seed_phrase" not in M.mask(text).kinds


@pytest.mark.parametrize(
    "secret",
    [
        KEY_HEX,
        KEY_HEX.upper(),
        "0x" + KEY_HEX,
        WIF,
        WIF_COMPRESSED,
        "xprv" + "9" * 107,
        # armoured blocks, assembled here so no scanner reads the file as holding a key
        f"{ARMOUR}BEGIN EC {PK}{ARMOUR}\nMHcCAQEE\n{ARMOUR}END EC {PK}{ARMOUR}",
        f"{ARMOUR}BEGIN OPENSSH {PK}{ARMOUR}\nb3BlbnNzaC1rZXktdjEAAAAA",
    ],
)
def test_a_private_key_is_masked(secret: str) -> None:
    out = M.mask(f"کلید من {secret} است")
    assert out.kinds == ("private_key",) and secret not in out.text
    assert out.text.startswith("کلید من ") and out.text.endswith(" است")


@pytest.mark.parametrize(
    "card",
    [
        CARD,
        f"{CARD[:4]} {CARD[4:8]} {CARD[8:12]} {CARD[12:]}",
        f"{CARD[:4]}-{CARD[4:8]}-{CARD[8:12]}-{CARD[12:]}",
        CARD.translate(FA_DIGITS),
        "378282246310005",  # a 15-digit network test number
    ],
)
def test_a_card_number_is_masked(card: str) -> None:
    out = M.mask(f"شماره کارتم {card}")
    assert "card" in out.kinds and card not in out.text and M.CARD in out.text


@pytest.mark.parametrize(
    "number",
    [
        CARD[:-1] + str((int(CARD[-1]) + 1) % 10),  # fails Luhn
        CARD + "12345",  # 21 digits: not a card
        "1234567",  # a short id
        "8812345678",  # an exchange UID
    ],
)
def test_other_numbers_stay(number: str) -> None:
    assert M.mask(f"uid {number}").text == f"uid {number}"


def test_redact_shapes_still_apply_and_kinds_are_told_apart() -> None:
    out = M.mask("ایمیلم ali@example.com و password: hunter2hunter")
    assert out.kinds == ("personal", "secret") and out.needs_safety_line
    assert "ali@example.com" not in out.text and "hunter2hunter" not in out.text
    personal = M.mask("ایمیلم ali@example.com")
    assert personal.kinds == ("personal",) and not personal.needs_safety_line
    assert M.mask("") == M.Masked("", ())
    assert M.mask("سلام") == M.Masked("سلام", ())


def test_masking_twice_changes_nothing() -> None:
    once = M.mask(f"{TWELVE} {KEY_HEX} {CARD}").text
    assert M.mask(once).text == once and M.mask(once).kinds == ()


def test_a_quote_hides_handles_and_long_ids() -> None:
    q = M.quote(f"@ali_reza گفت uid من 88123456 است و کارت {CARD}  " + "خ" * 400)
    assert "@ali_reza" not in q and "88123456" not in q and CARD not in q
    assert M.HANDLE in q and M.ID in q and len(q) <= 280 and q.endswith("…")
    assert M.quote("ایمیل a@b.co") == "ایمیل [email]"


KEY = bytes(range(32))


def test_the_pseudonym_is_a_keyed_hash() -> None:
    s = P.subject(KEY, "co-1", "telegram_bot", "42")
    assert P.is_subject(s) and s == P.subject(KEY, "co-1", "telegram_bot", " 42 ")
    others = {
        P.subject(KEY, "co-2", "telegram_bot", "42"),
        P.subject(KEY, "co-1", "telegram_business", "42"),
        P.subject(KEY, "co-1", "telegram_bot", "43"),
        P.subject(bytes(32), "co-1", "telegram_bot", "42"),
        P.subject(KEY, "co-1", "uid:lbank", "42"),
    }
    assert s not in others and len(others) == 5
    assert not P.is_subject("88123456") and not P.is_subject(s.upper())


def test_no_pseudonym_without_the_key_or_with_odd_parts() -> None:
    with pytest.raises(P.KeyMissing):
        P.subject(b"", "co", "telegram_bot", "1")
    with pytest.raises(ValueError, match="channel"):
        P.subject(KEY, "co", "sms", "1")
    for company, ext in (("", "1"), ("co", " "), ("c\x1fo", "1"), ("co", "x" * 129)):
        with pytest.raises(ValueError):
            P.subject(KEY, company, "telegram_bot", ext)
