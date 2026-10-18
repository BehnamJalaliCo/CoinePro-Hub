"""The A3 line on the web (prompt 07 §2.4): what the browser refuses with
needs_owner, from what it sees of a target, its form and the page."""

from __future__ import annotations

from typing import Any

import pytest

from hq_egress.rules import commitment

SEARCH = {"action": "/search", "method": "get", "search_like": True, "inputs": 1}


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
    ],
)
def test_commitment(facts: dict[str, Any], action: str, want: str | None) -> None:
    assert commitment(facts, action) == want
