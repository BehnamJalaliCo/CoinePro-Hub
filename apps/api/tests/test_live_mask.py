"""Review of 5.1 (must 8): the owner's live stream never shows a secret,
wherever the model's deltas happen to split the text."""

from __future__ import annotations

import pytest

from hq_api.agents import protocol as P
from hq_common.redact import scrub


def _secrets() -> list[tuple[str, str]]:
    """(text around the secret, the part that must never appear), built here."""
    value = "Sup3r" + "S3cret" + "Value9"
    token = "abc" * 10
    return [
        ("password: " + value, value),
        ("Authorization: Bearer " + token, token),
        ("کلید " + "sk-" + "ant-" + "api03-" + "Xy9" * 14 + " بود", "Xy9" * 14),
        ("شماره ۰۹۱۲" + "۳۴۵۶۷۸۹" + " است", "۳۴۵۶۷۸۹"),
        ("DB_PASSWORD=" + "q8Zr" * 4, "q8Zr" * 4),
    ]


FILLER = "این یک متن طولانی برای آزمایش استریم زنده است و کلمه‌های زیادی دارد " * 12


def _stream(text: str, size: int) -> str:
    buf = P.ScrubBuffer()
    out = [buf.feed(text[i : i + size]) for i in range(0, len(text), size)]
    return "".join(out) + buf.flush()


@pytest.mark.parametrize("where", ["start", "middle", "end", "own line"])
def test_no_split_shows_a_secret(where: str) -> None:
    seen = 0
    for around, secret in _secrets():
        text = {
            "start": around + " " + FILLER,
            "middle": FILLER + around + " " + FILLER,
            "end": FILLER + around,
            "own line": FILLER + "\n" + around + "\n" + FILLER,
        }[where]
        whole = scrub(text)
        assert secret not in whole
        for size in range(1, 97):
            got = _stream(text, size)
            assert secret not in got, (where, around[:20], size)
            assert got == whole, (where, around[:20], size)  # nothing lost, nothing extra
            seen += 1
    assert seen == len(_secrets()) * 96


def test_a_long_line_still_flows_and_a_pem_block_waits() -> None:
    buf = P.ScrubBuffer()
    assert buf.feed(FILLER)  # past HOLD: the safe part leaves before any newline
    head = "-----BEGIN " + "PRIVATE KEY-----\n" + "MIIB" + "x" * 40 + "\n"
    assert "MIIB" not in buf.feed(head)  # the key block is held for its END line
    assert "MIIB" not in buf.flush()
