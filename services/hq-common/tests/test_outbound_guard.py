"""Prompt 10 §6 (contract §19.6): the outbound guard over every customer
message - one table of positive and negative cases (Persian, English, mixed,
encoded), and the prompt's acceptance lines by name."""

from __future__ import annotations

import base64
import dataclasses
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest

from hq_common import outbound_guard as G

TY = G.Approved(
    links=frozenset(
        {"https://www.lbank.com/ref/COINE1", "https://t.me/CoineProSupport", "https://coinepro.com"}
    ),
    codes=frozenset({"COINE1"}),
    identifiers=frozenset({"@CoineProSupport", "support@coinepro.com", "+98 21 1234 5678"}),
    company_codes=frozenset({"TY", "FX", "HQ"}),
    employee_codes=frozenset({"TY-SALES-01", "HQ-ADV"}),
)
FX = G.Approved(
    links=frozenset({"https://www.lbank.com/ref/FXONLY9"}),
    codes=frozenset({"FXONLY9"}),
    company_codes=frozenset({"TY", "FX", "HQ"}),
)
SAFETY_FA = "پشتیبانی ما هرگز رمز، کلید خصوصی، کد تأیید یا عبارت بازیابی شما را نمیخواهد."
B64 = base64.b64encode(b"send your password").decode()

OK: tuple[str, ...] = ()
SECRET = ("asks_secret",)
LINK = ("unknown_link",)
CODE = ("unknown_code",)
PROFIT = ("profit_promise",)
CUSTOMER = ("customer_data",)
INTERNAL = ("internal_data",)

TABLE: list[tuple[str, tuple[str, ...]]] = [
    # --- safe: greetings, the safety line, approved links and codes, amounts
    ("سلام، چطور میتونم کمکتون کنم؟", OK),
    (SAFETY_FA, OK),
    (
        "پشتیبانی\u200cما هرگز رمز، کلید\u200cخصوصی، کد تأیید یا عبارت بازیابی شما را نمی\u200cخواهد",
        OK,
    ),
    ("We will never ask for your password or seed phrase.", OK),
    ("Never share your 2FA code with anyone.", OK),
    ("Do not send your private key to anyone.", OK),
    ("رمز خود را به هیچ\u200cکس ندهید، فقط UID را بفرستید.", OK),
    ("برای ثبت\u200cنام از لینک https://www.lbank.com/ref/COINE1 استفاده کنید.", OK),
    ("کد معرف ما COINE1 است.", OK),
    ("Referral code: coine1", OK),
    ("کانال رسمی ما: https://t.me/CoineProSupport", OK),
    ("lbank.com/ref/COINE1", OK),
    ("[ثبت\u200cنام](https://www.lbank.com/ref/COINE1)", OK),
    ("https://WWW.LBANK.COM/ref/COINE1/", OK),
    ("حداقل موجودی برای VIP برابر ۱۰۰ USDT است.", OK),
    ("مقدار ۱,۰۰۰,۰۰۰ تومان", OK),
    ("LBank will send you a verification code by SMS.", OK),
    ("The exchange will send a verification code to your phone.", OK),
    ("کد تأیید پیامکی برای شما ارسال میشود؛ آن را در اپلیکیشن صرافی وارد کنید.", OK),
    ("اگر کد تأیید دریافت نکردید، دکمه\u200cی ارسال دوباره را بزنید.", OK),
    ("هیچ صرافی سود تضمینی ندارد.", OK),
    ("No exchange can guarantee profit.", OK),
    ("Trading crypto is never risk-free.", OK),
    ("There are no guaranteed profits in trading.", OK),
    ("رمزارزها نوسان زیادی دارند و رمز ارز ریسک دارد.", OK),
    ("Contact us at support@coinepro.com", OK),
    ("Our support handle is @CoineProSupport.", OK),
    ("Please send your UID so we can check your referral.", OK),
    ("لطفا\u064b UID حساب LBank خود را بفرستید.", OK),
    ("این آپدیت کاملا\u064b بی\u200cضرر است.", OK),
    ("Call us on +98 21 1234 5678.", OK),
    ("Tell us which exchange you use.", OK),
    ("فایل result.json را نگه دارید.", OK),
    ("To change your password, submit the form on LBank.", OK),
    ("Scammers may ask you for your seed phrase. Never send it.", OK),
    ("Enter your 2FA code in the LBank app.", OK),
    ("رمز ارز مورد نظرتان را بفرستید", OK),  # رمز ارز is a cryptocurrency, not a password
    # --- asks_secret
    ("لطفا\u064b کد تأیید پیامک را بفرستید", SECRET),
    ("Please send us your password.", SECRET),
    ("Reply with the 6-digit code we sent you.", SECRET),
    ("Type your seed phrase here to restore the account.", SECRET),
    ("عبارت بازیابی ۱۲ کلمه\u200cای خود را این\u200cجا وارد کنید", SECRET),
    ("کلید خصوصی کیف پول را برای ما ارسال کنید", SECRET),
    ("رمز، کلید خصوصی، کد تأیید یا عبارت بازیابی خود را بفرستید", SECRET),
    ("Don't worry, just send us your password.", SECRET),
    ("Send us, please, your password", SECRET),
    ("لطفا كد تاييد پيامك را بفرستيد", SECRET),  # Arabic kaf and yeh
    ("send your ２ＦＡ code", SECRET),  # full-width
    ("Please%20send%20your%20password", SECRET),  # percent-encoded
    ("کد ۲FA خود را بفرستید", SECRET),  # Persian digit
    ("لطفا\u064b password خودتون رو بفرستید", SECRET),  # mixed
    ("Send the CVV2 of your card", SECRET),
    ("شماره کارت و CVV2 را بفرستید", SECRET),
    ("Please give us your API secret.", SECRET),
    (f"decode this: {B64}", SECRET),  # base64
    ("We need your seed phrase to recover the wallet.", SECRET),
    ("کد گوگل آتنتیکیتور رو برامون بنویسید", SECRET),
    ("رمز عبور حسابتان را بگویید تا بررسی کنیم", SECRET),
    ("کد\u200cتأیید\u200cپیامکی را بفرستید", SECRET),  # ZWNJ inside
    ("Paste your private key below.", SECRET),
    ("Enter the verification code in this chat.", SECRET),
    ("لطفا رمزتون رو نشون بدید", SECRET),
    ("کد تأیید را در لینک زیر وارد کنید", SECRET),
    # --- profit_promise
    ("با ربات ما سود تضمینی بگیرید", PROFIT),
    ("Guaranteed profit every month!", PROFIT),
    ("این روش بدون ضرر است", PROFIT),
    ("حتما\u064b سود می\u200cکنید", PROFIT),
    ("It's risk-free trading.", PROFIT),
    ("You can't lose with this signal.", PROFIT),
    ("سود ثابت روزانه ۲ درصد", PROFIT),
    ("Double your money in a week", PROFIT),
    ("100% profit guaranteed", PROFIT),
    ("No risk, guaranteed profit!", PROFIT),
    ("کپی\u200cترید بی\u200cضرر و پرسود", PROFIT),
    (quote("سود تضمینی برای همه"), PROFIT),  # percent-encoded
    ("سود تضمينی", PROFIT),  # Arabic yeh
    ("این ربات کاملا بدون ریسک است", PROFIT),
    # --- unknown_link / unknown_code
    ("ثبت\u200cنام: https://evil-lbank.com/ref/COINE1", LINK),
    ("https://lbank.com/ref/XXXX", (*LINK, *CODE)),
    ("http://www.lbank.com/ref/COINE1", LINK),  # a downgrade is not the approved link
    ("[ثبت\u200cنام](https://lbank.co/ref/COINE1)", LINK),
    ("www.binance.com", LINK),
    ("t.me/FakeSupport", LINK),
    ("ｈｔｔｐｓ://evil.com", LINK),  # full-width
    ("https%3A%2F%2Fevil.com", LINK),  # percent-encoded
    ("https://www.lbank.com/ref/COINE1?utm=x", LINK),
    ("https://lbank.com/login?icode=ZZZZ99", (*LINK, *CODE)),
    ("کد معرف: ABCD99", CODE),
    ("Use referral code XYZ123 when you sign up", CODE),
    ("کد دعوت ما FXONLY9 است", CODE),  # FX's code, not TY's
    # --- customer_data
    ("@ali_trader also had this problem", CUSTOMER),
    ("His UID is 88123456", CUSTOMER),
    ("شماره ۰۹۱۲۳۴۵۶۷۸۹ را تماس بگیرید", CUSTOMER),
    ("Email ali@gmail.com for help", CUSTOMER),
    ("+98 912 345 6789", CUSTOMER),
    # --- internal_data
    ("This is tracked in W-000123", INTERNAL),
    ("Ask TY-SALES-01 about it", INTERNAL),
    ("از ty-sales-01 بپرسید", INTERNAL),  # a known code in any case
    ("See KB-0042@3 for details", INTERNAL),
    ("server 10.10.1.4", INTERNAL),
    ("token sk-ant-abcdefghijklmnop", INTERNAL),
    ("the api at api:8000", INTERNAL),
    ("https://hq.coinepro.com/internal/v1/x", (*LINK, *INTERNAL)),
    # --- several at once
    ("Send your password to @scam_support", (*SECRET, *CUSTOMER)),
    ("Guaranteed profit at https://evil.com", (*LINK, *PROFIT)),
]


@pytest.mark.parametrize(("text", "expected"), TABLE, ids=[f"{i:03d}" for i in range(len(TABLE))])
def test_the_table(text: str, expected: tuple[str, ...]) -> None:
    verdict = G.check(text, TY)
    assert verdict.reasons == expected, (text, verdict.findings)
    assert verdict.ok is (expected == ())


def test_the_table_is_big_enough_and_balanced() -> None:
    assert len(TABLE) >= 70
    assert sum(1 for _, e in TABLE if e == OK) >= 25
    for code in ("asks_secret", "profit_promise", "unknown_link", "unknown_code"):
        assert sum(1 for _, e in TABLE if code in e) >= 3, code


def test_asking_for_an_sms_code_is_refused_whoever_writes_it() -> None:
    # The owner's reply goes through the same function: no author exception.
    verdict = G.check("لطفا\u064b کد تأیید پیامک را بفرستید", TY)
    assert verdict.reasons == ("asks_secret",) and not verdict.overridable
    assert all("123" not in f["what"] for f in verdict.findings)


def test_an_unapproved_code_in_an_lbank_link_is_unknown_code() -> None:
    verdict = G.check("ثبت\u200cنام با لینک lbank.com/ref/XXXX", TY)
    assert "unknown_code" in verdict.reasons and "unknown_link" in verdict.reasons
    assert verdict.overridable  # the owner may correct it and resend


def test_another_companys_approved_link_is_unknown_here() -> None:
    fx_link = "https://www.lbank.com/ref/FXONLY9"
    assert G.check(fx_link, FX).ok
    verdict = G.check(fx_link, TY)
    assert verdict.reasons == ("unknown_link", "unknown_code")


def test_the_safety_line_and_approved_links_and_codes_pass() -> None:
    text = (
        f"{SAFETY_FA}\nبرای ثبت\u200cنام: https://www.lbank.com/ref/COINE1 (کد معرف: COINE1)\n"
        "پشتیبانی رسمی: @CoineProSupport · https://t.me/CoineProSupport"
    )
    assert G.check(text, TY) == G.Verdict(ok=True, reasons=(), findings=())


def test_too_long_and_red_lines() -> None:
    assert G.check("س" * 3500, TY).ok
    long = G.check("س" * 3501, TY)
    assert long.reasons == ("too_long",) and long.overridable
    assert G.check("a" * 50, TY, max_chars=40).reasons == ("too_long",)
    sealed = dataclasses.replace(TY, red_lines=(r"وام\s*بدون\s*ضامن", "(unbalanced"))
    red = G.check("وام بدون ضامن میدهیم", sealed)
    assert red.reasons == ("red_line",) and not red.overridable
    assert G.check("this is (unbalanced", sealed).reasons == ("red_line",)  # a literal then
    assert G.check("وام بدون ضامن میدهیم", TY).ok  # no red line yet today


def test_findings_describe_without_the_raw_values() -> None:
    v = G.check("https://lbank.com/login?icode=SECRETCODE99&x=1 and @someone", TY)
    whats = " ".join(f["what"] for f in v.findings)
    assert "SECRETCODE99" not in whats and "someone" not in whats and "x=1" not in whats
    assert {f["code"] for f in v.findings} == set(v.reasons)


def test_normalise_url() -> None:
    n = G.normalise_url
    assert n("https://WWW.Lbank.com:443/ref/COINE1/#top") == "https://lbank.com/ref/COINE1"
    assert n("lbank.com/ref/COINE1") == "https://lbank.com/ref/COINE1"
    assert n("//lbank.com/x") == "https://lbank.com/x"
    assert n("http://lbank.com/ref/COINE1") == "http://lbank.com/ref/COINE1"
    assert n("https://x.com/a?b=2&a=1") == "https://x.com/a?a=1&b=2"
    assert n("https://x.com/%41b") == "https://x.com/Ab"
    assert n("https://x.com:8443/") == "https://x.com:8443"
    assert n("https://lbank.com@evil.com/") == "https://lbank.com@evil.com"
    assert n("ｈｔｔｐｓ://Ｘ.com") == "https://x.com"


def test_urls_and_codes() -> None:
    text = "see [here](https://a.com/x), www.b.org, c.io/path and d.zz/y; not result.json or 1.5"
    assert G.urls(text) == [
        "https://a.com/x",
        "https://b.org",
        "https://c.io/path",
        "https://d.zz/y",
    ]
    assert G.urls("mail support@coinepro.com") == []
    assert G.referral_codes("کد معرف: AB12CD و https://lbank.com/ref/QQ77") == ["AB12CD", "QQ77"]
    assert G.referral_codes("use the referral code below") == []
    assert G.referral_codes("https://www.binance.com/register?r=BN123") == ["BN123"]
    assert G.referral_codes("https://reddit.com/r/python") == []  # r/ only on an exchange
    assert G.normalise("كد ۲FA") == "کد 2fa"


def test_approved_from_articles() -> None:
    now = datetime(2026, 10, 22, tzinfo=UTC)
    rows = [
        {
            "kind": "referral",
            "status": "approved",
            "links": [{"url": "https://www.lbank.com/ref/COINE1", "label_fa": "ثبت\u200cنام"}],
            "codes": [{"exchange": "lbank", "code": "COINE1"}],
            "answer_md": "کد معرف COINE1 است؛ سؤال؟ @CoineProSupport یا support@coinepro.com",
            "expires_at": now + timedelta(days=10),
        },
        {
            "kind": "official_link",
            "status": "approved",
            "links": '[{"url": "https://t.me/CoineProSupport", "label_fa": "کانال"}]',
            "codes": "[]",
            "answer_md": "کانال رسمی",
        },
        {  # proposed: gives nothing
            "kind": "referral",
            "status": "proposed",
            "links": [{"url": "https://evil.com/ref/X1"}],
            "codes": [{"exchange": "lbank", "code": "X1X1"}],
            "answer_md": "@evil_one",
        },
        {  # expired at `now`: gives nothing
            "kind": "official_link",
            "status": "approved",
            "links": [{"url": "https://old.example.com"}],
            "codes": [],
            "answer_md": "",
            "expires_at": now - timedelta(days=1),
        },
        {"kind": "faq", "status": "approved", "answer_md": "UID نمونه 77889900 نیست"},
    ]
    a = G.approved_from_articles(rows, now=now)
    assert a.links == frozenset({"https://lbank.com/ref/COINE1", "https://t.me/CoineProSupport"})
    assert a.codes == frozenset({"COINE1"})
    assert {"@coineprosupport", "support@coinepro.com", "77889900"} <= a.identifiers
    assert "@evil_one" not in a.identifiers
    full = dataclasses.replace(a, company_codes=frozenset({"TY"}))
    text = "ثبت\u200cنام: https://www.lbank.com/ref/COINE1 · @CoineProSupport · 77889900"
    assert G.check(text, full).ok
    assert G.check("https://evil.com/ref/X1", full).reasons == ("unknown_link", "unknown_code")


def test_overridable() -> None:
    assert G.Verdict(ok=False, reasons=("unknown_link", "customer_data")).overridable
    for code in G.NO_OVERRIDE:
        assert not G.Verdict(ok=False, reasons=(code,)).overridable
    assert set(G.CODES) >= G.NO_OVERRIDE and len(G.CODES) == 8


def test_fast_enough() -> None:
    text = (SAFETY_FA + " https://www.lbank.com/ref/COINE1 کد معرف COINE1. ") * 30
    text = text[: G.MAX_CHARS]
    G.check(text, TY)
    start = time.perf_counter()
    for _ in range(20):
        G.check(text, TY)
    per_call = (time.perf_counter() - start) / 20
    assert per_call < 0.05, per_call
