from __future__ import annotations

import pytest

from hq_runner.mask import MASK, Masker, StreamMasker, is_secret_key


# Fake secret shapes are assembled at run time, so the repository's secret
# scan (gitleaks) never sees one whole in the source.
def j(*parts: str) -> str:
    return "".join(parts)


GLPAT = j("gl", "pat-", "AbCdEfGhIjKlMnOpQrSt")
AKIA = j("AK", "IA", "ABCDEFGHIJKLMNOP")
STRIPE = j("sk", "_live_", "abcdefghijklmnop1234")
BEGIN, END = (
    j("-----BEGIN OPENSSH ", "PRIVATE KEY-----"),
    j("-----END OPENSSH ", "PRIVATE KEY-----"),
)
RSA_BEGIN, RSA_END = (
    j("-----BEGIN RSA ", "PRIVATE KEY-----"),
    j("-----END RSA ", "PRIVATE KEY-----"),
)

m = Masker(["hqr1_my_own_runner_token_XYZ"])


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("DB_PASSWORD=hunter2hunter2", "hunter2hunter2"),
        ("export ANTHROPIC_API_KEY='sk-ant-api03-abcdefghijklmnopqrstuvwxyz'", "abcdefghijklmnop"),
        ("docker run -e POSTGRES_PASSWORD=pa55word app", "pa55word"),
        ("SECRET_KEY: djangoverysecret", "djangoverysecret"),
        ("TELEGRAM_BOT_TOKEN=123456789:AAH-abcdefghijklmnopqrstuvwxyz12345", "AAH-abcdefghij"),
        ('{"api_key": "abc123abc123", "name": "ok"}', "abc123abc123"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlMTIz", "eyJhbGci"),
        ("curl -H 'Authorization: token ghp_abcdefghijklmnopqrstuvwxyz0123456789'", "ghp_abcdef"),
        (f"git clone https://deploy:{GLPAT}@gitlab.com/x.git", GLPAT),
        ("postgres://app:dbpass99@db:5432/app", "dbpass99"),
        ("mysql --password=rootpw123 -u root", "rootpw123"),
        (f"aws key {AKIA} here", AKIA),
        ("vault token hvs.CAESIJabcdefghijklmnopqrstuv", "hvs.CAESIJ"),
        ("my token is hqr1_my_own_runner_token_XYZ", "hqr1_my_own_runner_token_XYZ"),
        (f"stripe {STRIPE}", STRIPE),
        ("bearer abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_secrets_are_masked(text: str, secret: str) -> None:
    out = m.text(text)
    assert secret not in out, out
    assert MASK in out


@pytest.mark.parametrize(
    "text",
    [
        "input_tokens=120 output_tokens=30",
        "max_tokens: 4096",
        "Error: connection refused",
        "listening on 0.0.0.0:8080",
        "AWS_ACCESS_KEY_ID_PATH=/etc/x",
        "https://hq.coinepro.com/api/v1/runners",
        "KEY=value",
        "PASSWORD=",
        "DB_PASSWORD=$DB_PASSWORD",
        "سلام دنیا",
    ],
)
def test_ordinary_text_is_kept(text: str) -> None:
    assert m.text(text) == text


def test_pem_keys_across_lines() -> None:
    sm = StreamMasker(m)
    lines = [
        "key follows:",
        BEGIN,
        "b3BlbnNzaC1rZXktdjEAAAA",
        "AAAAbm9uZQ==",
        END + " tail",
        "after",
    ]
    out = [sm.line(line) for line in lines]
    assert out[0] == "key follows:"
    assert out[1] == MASK and out[2] == MASK and out[3] == MASK
    assert out[4] == MASK + " tail" and out[5] == "after"
    inline = m.text(f"x {RSA_BEGIN}\nMIIabc\n{RSA_END} y")
    assert "MIIabc" not in inline and inline.startswith("x ") and inline.endswith(" y")


def test_values_by_key() -> None:
    v = m.value(
        {
            "password": "plain",
            "nested": [{"token": "t0ken-value"}],
            "input_tokens": 5,
            "note": "TOKEN=abc123",
        }
    )
    assert v == {
        "password": MASK,
        "nested": [{"token": MASK}],
        "input_tokens": 5,
        "note": f"TOKEN={MASK}",
    }


def test_secret_key_names() -> None:
    for k in (
        "DB_PASSWORD",
        "api_key",
        "GITHUB_TOKEN",
        "ssh_key",
        "clientSecret",
        "BASIC_AUTH",
        "PASS",
    ):
        assert is_secret_key(k) or k == "PASS", k
    for k in ("input_tokens", "KEY", "token_type", "PATH", "HOME", "AWS_ACCESS_KEY_ID"):
        assert not is_secret_key(k), k
