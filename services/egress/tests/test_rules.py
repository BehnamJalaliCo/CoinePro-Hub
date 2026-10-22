"""The A3 line on the web (prompt 07 §2.4): what the browser refuses with
needs_owner, from what it sees of a target, its form and the page."""

from __future__ import annotations

from typing import Any

import pytest

from hq_egress.rules import commitment, get_commitment

SEARCH = {"action": "/search", "method": "get", "search_like": True, "inputs": 1}
PLAN = {"action": "/billing/plan"}
CART = {"action": "/cart/checkout"}
FORM_URL = "https://docs.google.com/forms/d/e/1/formResponse?entry.1=a"
FORM_POST = {"action": "/forms/d/e/1/formResponse", "search_like": True}
IFTTT_URL = "https://maker.ifttt.com/trigger/e/with/key/k"
LABELS_71 = (
    "Submit",
    "Continue",
    "Confirm",
    "Share",
    "Delete",
    "Promote",
    "ثبت",
    "تایید",
    "تأیید",
    "تاييد",  # Arabic yeh
    "ثبت سفارش",
    "حذف",
    "ﺛﺒﺖ",  # Arabic presentation forms (NFKC)
)


def el(tag: str = "button", **kw: Any) -> dict[str, Any]:
    return {"tag": tag.upper(), "page": {"url": "https://shop.example/", "title": "Shop"}, **kw}


@pytest.mark.parametrize(
    ("facts", "action", "want"),
    [
        # Forms: a search goes; payment, login and sign-up forms never do.
        (el(type="submit", text="Search", form=SEARCH), "click", None),
        (
            el(type="submit", text="Go", form={**SEARCH, "card": True}),
            "click",
            "credentials_or_payment_form",
        ),
        (
            el(type="submit", text="Log in", form={"password": True}),
            "click",
            "credentials_or_payment_form",
        ),
        (
            el(type="submit", text="Continue", form={"action": "/checkout/step2"}),
            "click",
            "commitment_form",
        ),
        (
            el(type="submit", text="Send", form={"textarea": True, "search_like": False}),
            "click",
            "form_submit",
        ),
        (
            el(type="submit", text="OK", form={"email": True, "search_like": True}),
            "click",
            "form_submit",
        ),
        (el("input", type="image", form={"action": "/x"}), "click", "form_submit"),  # doubt: refuse
        # Buttons outside a form: by what they say.
        (el(text="Buy now"), "click", "commitment_button"),
        (el(text="Place order"), "click", "commitment_button"),
        (el(text="ثبت سفارش"), "click", "commitment_button"),
        (el(text="پرداخت"), "click", "commitment_button"),
        (el(label="Publish post"), "click", "commitment_button"),
        (el(text="Load more"), "click", None),
        (el(text="Next page"), "click", None),
        # Links: reading, unless they go to a commitment.
        (el("a", text="Posts", href="/blog/posts"), "click", None),
        (el("a", text="پاسخ‌ها", href="/answers"), "click", None),
        (el("a", text="Buy now", href="/p/1"), "click", "commitment_link"),
        (el("a", text="Continue", href="/checkout"), "click", "commitment_link"),
        (el("a", text="Create an account", href="/start"), "click", "commitment_link"),
        (el("a", text="ثبت نام", href="/u"), "click", "commitment_link"),
        # Typing: never a card number, a CVV or a password; any other field is fine.
        (el("input", type="password"), "type", "payment_or_credentials_field"),
        (el("input", name="cardnumber"), "type", "payment_or_credentials_field"),
        (el("input", autocomplete="cc-csc"), "type", "payment_or_credentials_field"),
        (el("input", name="shaba"), "type", "payment_or_credentials_field"),
        (el("input", name="q", type="search"), "type", None),
        (el("select", name="country"), "select", None),
        (el(text="Pay"), "scroll", None),
        # A scripted control inside a form may submit it (7.1).
        (
            el("div", role="button", text="Continue", form={"action": "/feedback"}),
            "click",
            "form_submit",
        ),
        (
            el("a", role="button", href="#", text="Next", form={"action": "/checkout"}),
            "click",
            "commitment_form",
        ),
        # 7.1 §2.21: more labels, the Arabic letters for Persian, an auto-submit.
        *[(el(text=t), "click", "commitment_button") for t in LABELS_71],
        (el(text="اشتراك‌گذاري"), "click", "commitment_button"),  # Arabic kaf and yeh, a ZWNJ
        (el(text="Continue reading"), "click", None),
        (el(text="Show more"), "click", None),
        (el("select", name="sort", autosubmit=True, form=SEARCH), "select", None),
        (el("select", name="plan", autosubmit=True, form=PLAN), "select", "form_submit"),
        (el("select", name="qty", autosubmit=True, form=CART), "select", "commitment_form"),
        (el("select", name="plan", form=PLAN), "select", None),  # no handler: a choice only
        # A link to a GET that commits.
        (el("a", text="Answer", href=FORM_URL), "click", "commitment_link"),
        (el("a", text="Go", href="/x", abs_href=IFTTT_URL), "click", "commitment_link"),
        (el(type="submit", text="Go", form=FORM_POST), "click", "commitment_form"),
    ],
)
def test_commitment(facts: dict[str, Any], action: str, want: str | None) -> None:
    assert commitment(facts, action) == want


@pytest.mark.parametrize(
    ("url", "want"),
    [
        ("https://docs.google.com/forms/d/e/1FAIpQ/formResponse?entry.1=yes", "form_response"),
        ("https://docs.google.com/forms/u/0/d/e/1FAIpQ/formResponse", "form_response"),
        ("https://docs.google.com/forms/d/e/1FAIpQ/%66ormResponse", "form_response"),  # encoded
        ("https://maker.ifttt.com/trigger/door/with/key/abc", "webhook_trigger"),
        ("https://hooks.zapier.com/hooks/catch/123/abc/", "webhook_trigger"),
        ("https://hook.eu1.make.com/abcdef", "webhook_trigger"),
        ("https://hook.integromat.com/abcdef", "webhook_trigger"),
        ("https://eo1x.m.pipedream.net/", "webhook_trigger"),
        ("https://hooks.slack.com/services/T/B/x", "webhook_trigger"),
        ("https://discord.com/api/webhooks/1/abc", "webhook_trigger"),
        ("https://n8n.example.org/webhook/7f1c2a", "webhook_trigger"),
        ("https://n8n.example.org/webhook-test/7f1c2a", "webhook_trigger"),
        ("https://ci.example.org/generic-webhook-trigger/invoke?token=x", "webhook_trigger"),
        ("https://api.telegram.org/bot123:AAF-x/sendMessage?chat_id=1&text=hi", "webhook_trigger"),
        ("https://tapi.bale.ai/bot99:k/sendPhoto", "webhook_trigger"),
        # Reading.
        ("https://docs.google.com/forms/d/e/1FAIpQ/viewform", None),
        ("https://docs.github.com/en/webhooks/about-webhooks", None),
        ("https://api.github.com/repos/o/r/hooks/1", None),
        ("https://api.telegram.org/bot123:AAF-x/getUpdates", None),
        ("https://www.botanical.example/settings", None),
        ("https://example.com/blog/how-to-use-ifttt", None),
        ("not a url", None),
    ],
)
def test_a_get_that_commits(url: str, want: str | None) -> None:
    assert get_commitment(url) == want
