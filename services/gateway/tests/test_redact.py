"""Redaction (prompt 05 §3, §12): keys, tokens, e-mails, phones never reach the
model or an agent's output. Realistic samples, Latin and Persian digits."""

from __future__ import annotations

import json

import pytest

from hq_gateway.redact import MASK, fit, redact, scrub

# Realistic shapes, assembled at runtime so that no scanner (gitleaks) sees a
# secret-looking literal in the source: none of these is or was a real token.
_ALNUM = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
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
}


@pytest.mark.parametrize(("name", "secret"), sorted(SECRETS.items()))
def test_key_and_token_shapes_are_removed(name: str, secret: str) -> None:
    text = f"گزارش: کلید سرویس این است {secret} و تمام."
    out = scrub(text)
    assert secret not in out, name
    assert "گزارش" in out and "تمام" in out


def test_pem_bearer_urls_and_assignments() -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----"
    text = (
        f"{pem}\nAuthorization: Bearer abcdefghijklmnop1234567890\n"
        "db: postgres://hq:S3cretPassw0rd@postgres:5432/hq\n"
        "config: api_key" + "=" + "9f8e7d6c5b4a3210 password: 'hunter22hunter'"
    )
    out = scrub(text)
    for leaked in (
        "MIIEvQIBADANBg",
        "abcdefghijklmnop1234567890",
        "S3cretPassw0rd",
        "9f8e7d6c5b4a3210",
        "hunter22hunter",
    ):
        assert leaked not in out
    assert "[private-key]" in out and "Bearer [token]" in out and "[credentials]@" in out


@pytest.mark.parametrize(
    "phone",
    [
        "09121234567",
        "+989121234567",
        "00989121234567",
        "0912 123 4567",
        "0912-123-4567",
        "۰۹۱۲۱۲۳۴۵۶۷",
        "۰۹۱۲ ۱۲۳ ۴۵۶۷",
        "+1 415 555 2671",
        "+44 20 7946 0958",
    ],
)
def test_phone_numbers_are_removed(phone: str) -> None:
    out = scrub(f"شماره‌ی مشتری {phone} است")
    assert phone not in out and "[phone]" in out


def test_emails_cards_and_ibans() -> None:
    text = (
        "ایمیل مشتری ali.rezaei+vip@example.co.ir و کارت 6037-9912-3456-7890 "
        "و کارت ۶۰۳۷۹۹۱۲۳۴۵۶۷۸۹۰ و شبا IR06 0170 0000 0012 3456 7890 01"
    )
    out = scrub(text)
    assert "ali.rezaei" not in out and "[email]" in out
    assert "6037-9912" not in out and "۶۰۳۷۹۹۱۲" not in out and out.count("[card]") == 2
    assert "0170 0000" not in out and "[iban]" in out


def test_ordinary_numbers_and_refs_survive() -> None:
    text = "کار W-000123 و تصمیم D-000045، مصرف 182000 توکن، هزینه $2.94، سال 1405، ۳ شرکت"
    assert scrub(text) == text


def test_redact_by_key_and_nested_structures() -> None:
    value = {
        "password": "x",
        "bot_token": "y",
        "api_key": 123,
        "email": "z",
        "phone_number": "w",
        "tokens": 1200,
        "input_tokens": 10,
        "token_limit": 99,
        "tokens_left": 5,
        "flag": True,
        "nested": [
            {"customer": {"mobile": "09121234567", "name": "Ali", "note": "call 09121234567"}}
        ],
        "missing": None,
    }
    out = redact(value)
    for k in ("password", "bot_token", "api_key", "email", "phone_number"):
        assert out[k] == MASK
    assert out["tokens"] == 1200 and out["input_tokens"] == 10 and out["token_limit"] == 99
    assert out["tokens_left"] == 5 and out["flag"] is True and out["missing"] is None
    customer = out["nested"][0]["customer"]
    assert customer["mobile"] == MASK and customer["name"] == "Ali"
    assert "09121234567" not in customer["note"]
    assert "09121234567" not in json.dumps(out)


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
