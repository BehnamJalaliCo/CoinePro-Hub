"""Contract §29.7: what reaches the owner is plain Persian. The rules (data,
seed/plain_language.yaml) cut refs, ids, code words, tool and service names
and raw English or Chinese; names the owner knows stay; check() names what is
left; the three-part shape; a player's answer counts as Persian or not."""

from __future__ import annotations

import pytest

from hq_api.domain import humanize as H

RAW = [
    "کار W-000094 به IG-AIOPS-MGR سپرده شد و delivered شد؛ treasury.usage خطای invalid_args داد.",
    "خروجی ناقص: limit_reached در runner سرور. The job failed because the token envelope was exhausted.",
    "DeepSeek پاسخ داد: 我们建议使用 Google Search Console 和 Instagram",
    "یافته‌ی FI-0012 روی PR-140: پورت 5432 روی 0b0e9f7a-1c2d-4e5f-8a9b-0c1d2e3f4a5b باز است (api, worker).",
    "سری انتشار TY-MEDIA-MGR در کارت D-000011 منتظر seal است.",
]


@pytest.mark.parametrize("text", RAW)
def test_every_raw_text_comes_out_clean(text: str) -> None:
    assert H.check(text), text  # the raw one breaks the rules
    out = H.humanize(text)
    assert H.check(out) == [], (out, H.check(out))
    assert out.strip()


def test_names_the_owner_knows_and_figures_stay() -> None:
    text = "ریلز TradeYar در Instagram از راه IG-Hub منتشر شد؛ رتبه در Google Search Console از 18 به 9 رسید."
    assert H.check(text) == []
    assert H.humanize(text) == text


def test_the_three_part_shape() -> None:
    out = H.plain("سه پست منتشر شد", "فالوور 4٪ بیشتر شد", None)
    assert out.splitlines() == ["چه شد: سه پست منتشر شد", "چرا مهم است: فالوور 4٪ بیشتر شد"]
    need = H.plain("ریلز آماده است", None, "سری انتشار را مُهر کنید")
    assert need.splitlines()[-1].startswith("از شما چه لازم است:")


def test_a_players_answer_is_persian_or_not() -> None:
    assert H.is_persian_answer(
        "پیشنهاد من سه ریلز کوتاه است با `hook` قوی و لینک https://example.com/a"
    )
    assert not H.is_persian_answer("这是一个建议")
    assert not H.is_persian_answer("My proposal is three short reels with a strong hook every day.")
    assert H.persian_share("") == 1.0
