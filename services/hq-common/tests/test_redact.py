"""Redaction (prompt 05 §3, prompt 5.1 §2.1): keys, tokens, e-mails, phones
never reach a model or leave in an agent's output, however they are written
(Latin, Persian, Arabic-Indic digits, zero-width characters, full width),
ordinary numbers survive, and the work stays linear on hostile input.

Every sample is assembled at runtime so that no scanner (gitleaks) sees a
secret-looking literal in the source: none of these is or was a real value."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from hq_common.redact import (
    MASK,
    fit,
    fit_async,
    is_secret_key,
    redact,
    redact_async,
    scrub,
    scrub_async,
)

_ALNUM = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
ZW = "\u200b"  # zero-width space
ZWNJ = "\u200c"
SECRETS = {
    "anthropic key": "-".join(("sk", "ant", "oat01", _ALNUM + "-_xyz")),
    "openai key": "-".join(("sk", "proj", _ALNUM)),
    "agent token": ".".join(
        ("hqa1", "eyJzdWIiOiJUWS1DRU8iLCJydW4iOiJ4In0", "c2lnbmF0dXJlLXZhbHVlLXh5eg")
    ),
    "github token": "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "github pat": "github" + "_pat_" + "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
    "aws key": "AKIA" + "IOSFODNN7EXAMPLE",
    "slack token": "-".join(("xoxb", "123456789012", "1234567890123", "AbCdEfGhIjKlMnOp")),
    "telegram bot": "123456789" + ":" + "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw0",
    "jwt": ".".join(
        (
            "eyJhbGciOiJIUzI1NiJ9",
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        )
    ),
    "openbao token": "hv" + "s." + "CAESIJ" + _ALNUM[:24] + "Zx9",
    "google key": "AI" + "za" + "SyA" + _ALNUM[:32],
    "stripe live key": "sk" + "_live_" + _ALNUM[:28],
    "stripe restricted key": "rk" + "_live_" + _ALNUM[4:30],
}


def card(prefix: str) -> str:
    """A 16-digit number that passes Luhn."""
    digits = [int(c) for c in prefix.ljust(15, "1")[:15]]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


@pytest.mark.parametrize(("name", "secret"), sorted(SECRETS.items()))
def test_key_and_token_shapes_are_removed(name: str, secret: str) -> None:
    for text in (
        f"گزارش: کلید سرویس این است {secret} و تمام.",
        f"گزارش:کلید{secret}تمام",  # glued to Persian letters
        f"x_{secret}",  # glued to an underscore
    ):
        out = scrub(text)
        assert secret not in out, name
        assert "گزارش" in out or "x_" in out


def test_pem_bearer_basic_urls_and_assignments() -> None:
    begin, end = "-----BEGIN " + "PRIVATE KEY-----", "-----END " + "PRIVATE KEY-----"
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
    pem = f"{begin}\n{body}\n{end}"
    cut_short = f"{begin}\n{body}\nMIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0"
    rsa = "-----BEGIN RSA " + "PRIVATE KEY-----\nProc-Type: 4,ENCRYPTED\n" + body
    basic = "Basic " + "dXNlcjpwYXNzd29yZDEyMw=="
    pw, key = "hunter22" + "hunter", "9f8e7d6c" + "5b4a3210"
    text = (
        f"{pem}\nAuthorization: Bearer abcdefghijklmnop1234567890\n"
        f"curl -H 'Authorization: {basic}'\n"
        f"db: postgres://hq:S3cret{pw}@postgres:5432/hq\n"
        f"config: api_key={key} password: '{pw}'\n{cut_short} و ادامه‌ی متن\n{rsa}"
    )
    out = scrub(text)
    for leaked in (body, "abcdefghijklmnop1234567890", "dXNlcjpw", pw, key, "MIIEowIBAA"):
        assert leaked not in out
    assert out.count("[private-key]") == 3 and "و ادامه‌ی متن" in out
    assert "Bearer [token]" in out and "[credentials]@postgres" in out
    assert "Basic [credentials]" in out


@pytest.mark.parametrize(
    "line",
    [
        "DB_PASSWORD={v}",
        "ANTHROPIC_API_KEY={v}",
        "CLIENT_SECRET: {v}",
        'export SECRET_KEY="{v}"',
        "aws_secret_access_key = {v}",
        "accessToken={v}",
        "refreshToken: {v}",
        'signing_key: "{v}"',
        "ssh_key={v}",
        "passphrase: {v}",
        '{{"password": "{v}"}}',
        '{{"api_key":"{v}"}}',
        "{{'client_secret': '{v}'}}",
        "DB_PASS={v}",
        "رمز: {v}",
        "رمز عبور = {v}",
        "گذرواژه:{v}",
        "Authorization: Token {v}",
    ],
)
def test_assignments_without_a_word_boundary(line: str) -> None:
    value = "Zq7" + "Xw9-" + "Lm3Kp"
    out = scrub(line.format(v=value))
    assert value not in out and MASK in out


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("otp_code: {v}", "482913"),
        ("PIN: {v}", "4829"),
        ("pin_code={v}", "۴۸۲۹"),
        ("کد تایید: {v}", "۴۸۲۹۱۳"),
        ("national_code: {v}", "0012345678"),
        ("کد ملی {v}", "۰۰۱۲۳۴۵۶۷۸"),
        ("شماره ملی: {v}", "٠٠١٢٣٤٥٦٧٨"),
    ],
)
def test_codes(line: str, value: str) -> None:
    out = scrub(line.format(v=value))
    assert value not in out and MASK in out


@pytest.mark.parametrize(
    "phone",
    [
        "09121234567",
        "+989121234567",
        "00989121234567",
        "989121234567",
        "0912 123 4567",
        "0912-123-4567",
        "0912 - 123 - 4567",
        "(0912) 123 4567",
        "912 123 4567",
        "۰۹۱۲۱۲۳۴۵۶۷",
        "۰۹۱۲ ۱۲۳ ۴۵۶۷",
        "٠٩١٢١٢٣٤٥٦٧",
        "۰۹۱۲123۴۵۶۷",  # Persian and Latin digits mixed
        f"0912{ZW}123{ZWNJ}4567",  # zero-width characters inside
        "０９１２１２３４５６７",  # full width
        "021-12345678",
        "(021) 1234 5678",
        "+98 21 1234 5678",
        "+1 415 555 2671",
        "+44 20 7946 0958",
        "0044 20 7946 0958",
    ],
)
def test_phone_numbers_are_removed(phone: str) -> None:
    for text in (f"شماره‌ی مشتری {phone} است", f"tel_{phone}", f"شماره{phone}"):
        out = scrub(text)
        assert phone not in out and "[phone]" in out, text
        digits = "".join(c for c in phone if c.isdigit())
        assert digits[-4:] not in "".join(c for c in out if c.isdigit())


def test_emails_cards_and_ibans() -> None:
    latin, persian = (
        card("6037991"),
        card("5022291").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")),
    )
    spaced = " ".join(latin[i : i + 4] for i in range(0, 16, 4))
    text = (
        f"ایمیل مشتری ali.rezaei+vip@example.co.ir و کارت {spaced} "
        f"و کارت {persian} و شبا IR06 0170 0000 0012 3456 7890 01 "
        f"و ali{ZW}@exa{ZWNJ}mple.com و ａｌｉ＠ｅｘａｍｐｌｅ．ｃｏｍ"
    )
    out = scrub(text)
    assert "ali.rezaei" not in out and out.count("[email]") == 3
    assert latin[:8] not in out.replace(" ", "") and persian[:8] not in out
    assert out.count("[card]") == 2
    assert "0170 0000" not in out and "[iban]" in out


def test_ordinary_numbers_and_refs_survive() -> None:
    valid = card("6037991")
    not_a_card = valid[:15] + str((int(valid[15]) + 1) % 10)  # fails Luhn
    assert scrub(f"کد پیگیری {not_a_card}") == f"کد پیگیری {not_a_card}"
    text = (
        "کار W-000123 و تصمیم D-000045، مصرف 182000 توکن، هزینه $2.94، سال 1405، ۳ شرکت، "
        "مبلغ 9500000000 ریال و ۹۵۰۰۰۰۰۰۰۰ ریال، تاریخ 2026-10-17، نسخه 1.4.2، "
        "tokens: 600000, input_tokens=5000, token_limit=99, سقف 200,000 نویسه"
    )
    assert scrub(text) == text


def test_ids_are_not_cards() -> None:
    """A UUID's tail can be 16 digits that pass Luhn ("8000-000000000003"):
    an id in every tool result, never a card (prompt 06: file ids)."""
    ids = [f"0193e7a1-0000-7000-8000-0000000000{i:02d}" for i in range(100)]
    assert any(card_like for card_like in ids if _luhn_digits(card_like[-17:]))
    text = " ".join(ids)
    assert scrub(text) == text
    assert scrub("deadbeef8000000000000003cafe") == "deadbeef8000000000000003cafe"
    valid = card("6037991")
    assert scrub(f"کارت {valid}") == "کارت [card]"  # a real one still goes


def _luhn_digits(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    total = sum(
        d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(reversed(digits))
    )
    return len(digits) == 16 and total % 10 == 0


def test_zwnj_and_formatting_of_ordinary_text_are_kept() -> None:
    text = f"می{ZWNJ}خواهم گزارش‌ها را ببینم؛ تماس 09121234567 گرفته شد."
    out = scrub(text)
    assert out == f"می{ZWNJ}خواهم گزارش‌ها را ببینم؛ تماس [phone] گرفته شد."


def test_secret_key_names() -> None:
    for name in (
        "password",
        "bot_token",
        "api_key",
        "apiKey",
        "APIKey",
        "secret_key",
        "aws_secret_access_key",
        "access_key",
        "signing_key",
        "ssh_key",
        "passphrase",
        "accessToken",
        "refreshToken",
        "otp_code",
        "pin_code",
        "national_code",
        "mobile_number",
        "phones",
        "emails",
        "e-mail",
        "client-secret",
        "Set-Cookie",
        "ｐａｓｓｗｏｒｄ",
        f"pass{ZW}word",
    ):
        assert is_secret_key(name), name
    for name in ("tokens", "input_tokens", "token_limit", "tokens_left", "name", "bypass", "key"):
        assert not is_secret_key(name), name


def test_redact_by_key_and_nested_structures() -> None:
    email = "ali" + "@" + "example.com"
    value = {
        "password": "x",
        "bot_token": "y",
        "api_key": 123,
        "email": "z",
        "phone_number": "w",
        "phones": ["09121234567"],
        "accessToken": "t",
        "tokens": 1200,
        "input_tokens": 10,
        "token_limit": 99,
        "tokens_left": 5,
        "flag": True,
        "nested": [
            {"customer": {"mobile": "09121234567", "name": "Ali", "note": "call 09121234567"}}
        ],
        "missing": None,
        email: "the key itself is personal data",
        "secret_key": True,
    }
    out = redact(value)
    for k in ("password", "bot_token", "api_key", "email", "phone_number", "phones", "accessToken"):
        assert out[k] == MASK, k
    assert out["tokens"] == 1200 and out["input_tokens"] == 10 and out["token_limit"] == 99
    assert out["tokens_left"] == 5 and out["flag"] is True and out["missing"] is None
    assert out["secret_key"] is True  # a boolean says nothing
    customer = out["nested"][0]["customer"]
    assert customer["mobile"] == MASK and customer["name"] == "Ali"
    assert "09121234567" not in json.dumps(out) and email not in json.dumps(out)
    assert out["[email]"] == "the key itself is personal data"
    # Two keys that scrub to the same text both stay.
    two = redact({"a" + "@" + "b.com": 1, "c" + "@" + "d.com": 2})
    assert sorted(two.values()) == [1, 2]


def test_sizes_are_capped_only_when_asked() -> None:
    long = "الف" * 10_000
    assert redact(long) == long  # what an agent writes is never shortened
    assert len(redact(long, max_string=4000)) < 4100
    big = {"items": list(range(200))}
    assert redact(big) == big
    assert redact(big, max_list=60)["items"][-1] == "…[140 more]"
    deep: dict[str, object] = {}
    cur = deep
    for _ in range(20):
        cur["x"] = {}
        cur = cur["x"]  # type: ignore[assignment]
    assert "[too deep]" in json.dumps(redact(deep))
    out, cut = fit({"a": "b" * 50_000, "c": [{"d": "e" * 5000}] * 40}, 8000)
    assert cut is True and len(json.dumps(out, ensure_ascii=False)) <= 8000
    small, cut = fit({"ok": 1}, 8000)
    assert small == {"ok": 1} and cut is False
    huge, cut = fit({"k": [str(i) * 50 for i in range(60)] * 1}, 300)
    assert cut is True and len(json.dumps(huge, ensure_ascii=False)) <= 300


def test_a_secret_at_the_cut_never_leaks_a_piece() -> None:
    secret = SECRETS["agent token"]
    for limit in (4000, 1000, 160):
        for offset in range(-60, 10, 7):
            text = "ا" * (limit + offset) + secret + " پایان" * 3000  # well past the margin
            out = redact(text, max_string=limit)
            assert secret[:12] not in out and len(out) <= limit + 10, (limit, offset)


HOSTILE = {
    "e-mail local parts": "a" * 200_000,
    "e-mail domains": "a@" + "a." * 100_000,
    "many at signs": "a@a" * 70_000,
    "url credentials": "a://" + "b:" * 100_000,
    "url schemes": "a+" * 100_000 + "://x",
    "assignments": "password=" * 22_000,
    "digits": "9" * 200_000,
    "spaced digits": "9 " * 100_000,
    "persian digits": "۹-" * 100_000,
    "pem headers": ("-----BEGIN " + "PRIVATE KEY-----") * 7_100,
    "zero width": ("0" + ZW) * 100_000,
    "full width": "０９" * 100_000,
    "iban": "IR" + "0 " * 100_000,
    "bearer": "Bearer " * 30_000,
    "mixed": ("tel_0912 ۱۲۳ ٤٥٦٧ " + ZWNJ + "ali@x " + "sk-") * 8_000,
    # prompt 5.1 review
    "json escapes": ("\\n" + "sk-ant-" + "\\t" + "Bearer ") * 12_000,
    "pgp headers": ("-----BEGIN PGP " + "PRIVATE KEY BLOCK-----") * 5_200,
    "ignorables": ("0" + "\ufe0f" + "9" + "\u3164") * 50_000,
    "url users": ("a://" + "b" * 600 + ":" + "c" * 30) * 320,
    "decimals": "0." * 100_000,
    "name value": ('{"name": "DB_PASSWORD", "value": ' * 6_000),
}


# --------------------------------------------------- review of 5.1 (§A) --
LINE_SECRETS = {
    k: SECRETS[k] for k in ("anthropic key", "github token", "aws key", "jwt", "openbao token")
}
LINE_SECRETS["bearer"] = "Bearer " + "Tk9z" * 6 + "_x"


@pytest.mark.parametrize(("name", "secret"), sorted(LINE_SECRETS.items()))
def test_a_secret_at_the_start_of_a_line_and_inside_json(name: str, secret: str) -> None:
    """A JSON-dumped text turns a new line into the two characters \\n, which
    put a Latin letter right before the token (prompt 5.1 review, blocker 1)."""
    core = secret.split(" ")[-1]
    for sep in ("\n", "\t", "\r", "\r\n"):
        text = f"خط اول{sep}{secret} پایان"
        for form in (
            text,
            json.dumps({"brief": text}, ensure_ascii=False),
            json.dumps({"brief": text}),
            json.dumps([{"what": f"x{sep}{secret}"}], ensure_ascii=False),
        ):
            out = scrub(form)
            assert core not in out, (name, repr(sep), form[:40])


@pytest.mark.parametrize("mark", ["️", "͏", "ㅤ", "ᅟ", "᠋", "︀", "ﾠ", "­"])
def test_default_ignorable_characters_inside_a_secret(mark: str) -> None:
    secret = SECRETS["github token"]
    broken = secret[:6] + mark + secret[6:14] + mark + secret[14:]
    out = scrub(f"کلید {broken} پایان")
    assert "[token]" in out and secret[10:24] not in out.replace(mark, ""), repr(mark)
    kept = scrub(f"می{ZWNJ}خواهم {broken} و می{ZWNJ}روم")
    assert kept.startswith(f"می{ZWNJ}خواهم ") and kept.endswith(f" و می{ZWNJ}روم")


def test_pgp_private_key_blocks() -> None:
    begin = "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----"
    end = "-----END PGP " + "PRIVATE KEY BLOCK-----"
    body = "\n".join(("Version: GnuPG v2", "", "lQOYBF" + "Ab9+/" * 12, "Ab9+" * 10, "=Xy3Q"))
    for text in (f"قبل\n{begin}\n{body}\n{end}\nبعد", f"قبل\n{begin}\n{body}"):
        out = scrub(text)
        assert "lQOYBF" not in out and "Ab9+Ab9+" not in out and "=Xy3Q" not in out, text
        assert out.startswith("قبل\n") and "[private-key]" in out
    assert scrub(f"قبل\n{begin}\n{body}\n{end}\nبعد").endswith("\nبعد")


def test_name_value_pairs_and_numbers_given_as_json_integers() -> None:
    v = "q8Zr" * 4
    env = [
        {"name": "DB_PASSWORD", "value": v},
        {"key": "apiKey", "value": v},
        {"Name": "client-secret", "Value": v},
        {"name": "LOG_LEVEL", "value": "info"},
        {"name": "DB_PASSWORD", "value": None},
    ]
    assert redact({"env": env}) == {
        "env": [
            {"name": "DB_PASSWORD", "value": MASK},
            {"key": "apiKey", "value": MASK},
            {"Name": "client-secret", "Value": MASK},
            {"name": "LOG_LEVEL", "value": "info"},
            {"name": "DB_PASSWORD", "value": None},
        ]
    }
    numbers = {
        "n": int(card("6037991")),
        "m": 989121234567,
        "tokens": 600_000,
        "at_ms": 1_760_000_000_000,
        "amount": 9_500_000_000,
        "ok": True,
        "items": [int(card("5022291")), 7],
    }
    assert redact(numbers) == {
        "n": "[card]",
        "m": "[phone]",
        "tokens": 600_000,
        "at_ms": 1_760_000_000_000,
        "amount": 9_500_000_000,
        "ok": True,
        "items": ["[card]", 7],
    }


def test_long_url_users_and_decimal_fractions() -> None:
    user, password = "u" * 200, "p9Q" * 5
    out = scrub(f"اتصال https://{user}:{password}@db.example.com/x")
    assert password not in out and user not in out and "[credentials]@" in out
    for text in ("ضریب 0.9876543210 است", "x=12.09121234567", "نسبت ۰٫۹۸۷۶۵۴۳۲۱۰", "0.9123456789"):
        assert scrub(text) == text, text
    assert scrub("تماس 0912.123.4567") == "تماس [phone]"  # a phone written with dots still is


def test_spans_are_the_ranges_scrub_masks() -> None:
    import re

    from hq_common.redact import spans

    token = SECRETS["github token"]
    text = f"آ {token} و ۰۹۱۲۱۲۳۴۵۶۷ و ali{ZW}@example.com و x"
    got = spans(text)
    assert got == sorted(got) and len(got) == 3
    pieces, pos = [], 0
    for s, e in got:
        assert s < e and s >= pos
        pieces.append(text[pos:s])
        pieces.append("#")
        pos = e
    pieces.append(text[pos:])
    assert re.sub(r"\[[a-z\-]+\]@?", "#", scrub(text)) == "".join(pieces)
    assert spans("") == [] and spans("بدون هیچ راز") == []
    broken = token[:10] + ZW + token[10:]
    (only,) = spans(f"ab {broken} cd")
    assert f"ab {broken} cd"[only[0] : only[1]] == broken  # mapped back to the original
    two = f"{token} {token}"
    assert spans(two) == [(0, len(token)), (len(token) + 1, len(two))]


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_linear_time_on_hostile_input(name: str) -> None:
    text = HOSTILE[name]
    assert len(text) >= 190_000
    t0 = time.perf_counter()
    scrub(text)
    assert time.perf_counter() - t0 < 1.0, name


async def test_async_helpers_give_the_same_answer() -> None:
    small = "تماس 09121234567"
    big = ("متن " * 10_000) + small
    assert await scrub_async(small) == scrub(small)
    assert await scrub_async(big) == scrub(big)
    value = {"note": big, "password": "x"}
    assert await redact_async(value) == redact(value)
    assert await redact_async({"a": small}) == {"a": "تماس [phone]"}
    assert await fit_async(value, 500) == fit(value, 500)
    assert await fit_async({"a": 1}, 500) == ({"a": 1}, False)
    # The event loop stays free while a large text is scrubbed.
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.001)
            ticks += 1

    task = asyncio.create_task(ticker())
    await scrub_async(HOSTILE["mixed"] * 2)
    task.cancel()
    assert ticks > 0
