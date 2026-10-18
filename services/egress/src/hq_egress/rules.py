"""The A3 line on the web (owner decision, prompt 07 §2.4): research, reading
and working inside tools are A0-A2; an external commitment in the holding's
name (paying, buying, publishing, messaging a person, creating an account,
changing an account's security) is never done by an agent: the step is
refused with `needs_owner` and the agent proposes it instead.

`commitment(facts, action)` decides from what the browser sees of the target
element, its form and the page. When in doubt (a form submit that is not a
plain search), it refuses: the safe side.
"""

from __future__ import annotations

import re
from typing import Any

ZWNJ = "‌"

_WORDS = [
    # English
    r"pay(\s+now)?",
    r"payment",
    r"check\s*out",
    r"buy(\s+now)?",
    r"purchase",
    r"(place|confirm|complete|submit)\s+(the\s+)?order",
    r"order\s+now",
    r"subscribe",
    r"donate",
    r"publish",
    r"post(\s+(it|now|comment|reply))?",
    r"tweet",
    r"send(\s+(message|now|email|it))?",
    r"reply",
    r"comment",
    r"sign\s*up",
    r"register",
    r"create\s+(an\s+)?account",
    r"join(\s+now)?",
    r"delete\s+(my\s+)?account",
    r"(change|reset|update)\s+(my\s+)?password",
    r"(enable|disable|turn\s+(on|off))\s+(2fa|two[-\s]factor)",
    r"transfer",
    r"withdraw",
    r"deposit",
    r"book\s+now",
    r"reserve",
    r"upgrade(\s+plan)?",
    # Persian
    r"پرداخت",
    r"خرید",
    r"بخر",
    r"(ثبت|تکمیل|تایید|تأیید)\s*(سفارش|خرید|پرداخت)",
    r"سفارش\s*(بده|دهید)",
    r"تسویه",
    r"اشتراک",
    r"عضویت",
    r"ثبت\s*نام",
    r"ایجاد\s*حساب",
    r"انتشار",
    r"منتشر",
    r"ارسال",
    r"بفرست",
    r"فرستادن",
    r"پاسخ\s*(بده|دهید|بفرست)",
    r"(ثبت|ارسال)\s*نظر",
    r"حذف\s*حساب",
    r"(تغییر|بازیابی)\s*(رمز|گذرواژه)",
    r"انتقال\s*وجه",
    r"برداشت",
    r"واریز",
    r"رزرو",
]
WORDS = re.compile(r"(?<!\w)(" + "|".join(_WORDS) + r")(?!\w)", re.IGNORECASE)
# A link is only refused for these (a link named "posts" or "reply" is reading).
_STRONG = [
    r"pay(\s+now)?",
    r"check\s*out",
    r"buy(\s+now)?",
    r"purchase",
    r"(place|confirm|complete)\s+(the\s+)?order",
    r"subscribe",
    r"donate",
    r"sign\s*up",
    r"register",
    r"create\s+(an\s+)?account",
    r"delete\s+(my\s+)?account",
    r"transfer",
    r"withdraw",
    r"پرداخت",
    r"(ثبت|تکمیل)\s*(سفارش|خرید)",
    r"ثبت\s*نام",
    r"ایجاد\s*حساب",
    r"حذف\s*حساب",
    r"انتقال\s*وجه",
]
STRONG = re.compile(r"(?<!\w)(" + "|".join(_STRONG) + r")(?!\w)", re.IGNORECASE)
PATHS = re.compile(
    r"/(checkout|cart/checkout|pay|payments?|purchase|buy|orders?(/new)?|subscribe|subscriptions?|"
    r"donate|sign-?up|register|join|create-account|account/(security|password|delete)|password|"
    r"reset|2fa|compose|publish|post/new|send|share|transfer|withdraw)(/|$|\?|#|\.)",
    re.IGNORECASE,
)
SECRET_FIELDS = re.compile(
    r"(card|cc-?(num|number|exp|csc|name)|cvv|cvc|csc|iban|shaba|expiry|exp-?date|"
    r"otp|one-time|کارت|شبا|رمز)",
    re.IGNORECASE,
)


def _text(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p).replace(ZWNJ, " ")[:500]


def secret_field(facts: dict[str, Any]) -> bool:
    if str(facts.get("type") or "").lower() == "password":
        return True
    names = _text(facts.get("name"), facts.get("id"), facts.get("autocomplete"))
    return bool(SECRET_FIELDS.search(names))


def commitment(facts: dict[str, Any], action: str) -> str | None:
    """None if the step is not an external commitment; else the reason."""
    tag = str(facts.get("tag") or "").lower()
    kind = str(facts.get("type") or "").lower()
    raw_form, raw_page = facts.get("form"), facts.get("page")
    form: dict[str, Any] | None = raw_form if isinstance(raw_form, dict) else None
    page: dict[str, Any] = raw_page if isinstance(raw_page, dict) else {}
    if action in ("type", "select"):
        return "payment_or_credentials_field" if secret_field(facts) else None
    if action not in ("click", "download"):
        return None
    label = _text(facts.get("text"), facts.get("value"), facts.get("label"), facts.get("title"))
    href = str(facts.get("href") or "")
    submits = form is not None and (
        (tag == "button" and kind in ("", "submit"))
        or (tag == "input" and kind in ("submit", "image"))
    )
    if submits and form is not None:
        if form.get("password") or form.get("card"):
            return "credentials_or_payment_form"
        if PATHS.search(str(form.get("action") or "")) or PATHS.search(str(page.get("url") or "")):
            return "commitment_form"
        plain = not (
            form.get("textarea") or form.get("email") or form.get("tel") or form.get("file")
        )
        if form.get("search_like") and plain:
            return None
        return "form_submit"
    if tag == "a":
        if PATHS.search(href) or STRONG.search(label):
            return "commitment_link"
        return None
    if WORDS.search(label):
        return "commitment_button"
    return None


# What the browser collects about a target (run in the page; no side effect).
FACTS_JS = """
(el) => {
  const f = el.form || el.closest('form');
  const q = (s) => f ? f.querySelectorAll(s).length : 0;
  const inputs = f ? Array.from(f.querySelectorAll('input,select,textarea'))
      .filter(i => i.type !== 'hidden') : [];
  const names = inputs.map(i =>
      ((i.name || '') + ' ' + (i.id || '') + ' ' + (i.autocomplete || '')).toLowerCase());
  const searchy = f && (f.getAttribute('role') === 'search' || q('input[type=search]') > 0 ||
      names.some(n => /(^|\\s)(q|query|search|s|keyword|keywords|term)(\\s|$)/.test(n)) ||
      /search|جستجو/i.test(f.getAttribute('action') || ''));
  return {
    tag: el.tagName, type: el.getAttribute('type') || '',
    text: (el.innerText || '').slice(0, 200),
    value: (el.type === 'password' ? '' : (el.value || '')).toString().slice(0, 100),
    label: el.getAttribute('aria-label') || '', title: el.getAttribute('title') || '',
    name: el.getAttribute('name') || '', id: el.id || '',
    autocomplete: el.getAttribute('autocomplete') || '',
    href: el.getAttribute('href') || '',
    form: f ? {
      action: f.getAttribute('action') || '',
      method: (f.getAttribute('method') || 'get').toLowerCase(),
      password: q('input[type=password]') > 0,
      card: names.some(n => /(card|cc-|cvv|cvc|iban|expiry|shaba)/.test(n)),
      textarea: q('textarea') > 0, email: q('input[type=email]') > 0,
      tel: q('input[type=tel]') > 0,
      file: q('input[type=file]') > 0, inputs: inputs.length,
      search_like: !!searchy && inputs.length <= 4,
    } : null,
    page: {url: location.href, title: document.title},
  };
}
"""
