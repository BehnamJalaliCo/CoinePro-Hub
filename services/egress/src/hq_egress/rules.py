"""The A3 line on the web (owner decision, prompt 07 §2.4): research, reading
and working inside tools are A0-A2; an external commitment in the holding's
name (paying, buying, publishing, messaging a person, creating an account,
changing an account's security) is never done by an agent: the step is
refused with `needs_owner` and the agent proposes it instead.

`commitment(facts, action)` decides from what the browser sees of the target
element, its form and the page. When in doubt (a form submit that is not a
plain search), it refuses: the safe side.

`get_commitment(url)` is the same line for a plain GET (7.1): some commit
with a GET alone (a Google Form's `formResponse`, a webhook or automation
trigger, a messaging bot's send call). It judges http.request and web.read
(every hop), and the browser's goto, download and every request it sends.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlsplit

ZWNJ = "‌"
# Arabic letters typed for their Persian twins, tatweel and short vowels (7.1).
_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ـ": None})
_MARKS = re.compile("[ً-ٰٟ]")

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
    r"delete(\s+(my\s+)?account)?",
    r"(change|reset|update)\s+(my\s+)?password",
    r"(enable|disable|turn\s+(on|off))\s+(2fa|two[-\s]factor)",
    r"transfer",
    r"withdraw",
    r"deposit",
    r"book\s+now",
    r"reserve",
    r"upgrade(\s+plan)?",
    r"submit",
    r"continue(?!\s+(reading|to\s+read))",  # "Continue reading" only shows more
    r"confirm",
    r"share",
    r"promote",
    # Persian (after normalisation: Persian ی and ک, no tatweel or vowel marks)
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
    r"حذف(\s*حساب)?",
    r"(تغییر|بازیابی)\s*(رمز|گذرواژه)",
    r"انتقال\s*وجه",
    r"برداشت",
    r"واریز",
    r"رزرو",
    r"ثبت",
    r"تایید",
    r"تأیید",
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
# A GET that commits (7.1): a form's answer, a trigger, a bot's send call.
GET_PATHS = re.compile(
    r"/(formResponse|form-response)(/|$)"  # Google Forms: /forms/d/e/<id>/formResponse
    r"|/webhook(-test)?/[^/]+"  # n8n and the like: /webhook/<id>
    r"|/hooks/catch/"  # Zapier
    r"|/trigger/[^/]+/(with/key|json/with/key)/"  # IFTTT Maker
    r"|/api/webhooks/"  # Discord
    r"|/generic-webhook-trigger/|/buildbytoken/"  # Jenkins
    r"|/bot\d+:[\w-]+/(send|forward|copy|edit|delete|ban|unban|restrict|promote|pin|unpin|set|"
    r"leave|create|approve|decline|revoke|answer)\w*(/|$)",  # a Telegram-style bot API
    re.IGNORECASE,
)
GET_HOSTS = re.compile(
    r"(^|\.)(maker\.ifttt\.com|hooks\.zapier\.com|hook\.([a-z0-9-]+\.)?(make|integromat)\.com|"
    r"m\.pipedream\.net|hooks\.slack\.com|webhook\.office\.com|outlook\.office\.com)$",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    """What a label says, as the patterns read it: compatibility forms
    (NFKC: presentation forms, full-width letters), Persian ی and ک for the
    Arabic ي and ك, no tatweel or short vowels, a ZWNJ as a space."""
    text = unicodedata.normalize("NFKC", text)
    return _MARKS.sub("", text.translate(_PERSIAN)).replace(ZWNJ, " ")


def _text(*parts: Any) -> str:
    return norm(" ".join(str(p) for p in parts if p))[:500]


def secret_field(facts: dict[str, Any]) -> bool:
    if str(facts.get("type") or "").lower() == "password":
        return True
    names = _text(facts.get("name"), facts.get("id"), facts.get("autocomplete"))
    return bool(SECRET_FIELDS.search(names))


def get_commitment(url: str) -> str | None:
    """Why a GET of `url` is an external commitment, or None (reading)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    path = parts.path or "/"
    for _ in range(3):  # however it is percent-encoded
        path = unquote(path)
    if GET_HOSTS.search(host):
        return "webhook_trigger"
    m = GET_PATHS.search(path)
    if m is None:
        return None
    return "form_response" if "form" in m.group(0).lower() else "webhook_trigger"


def _form_submit(form: dict[str, Any], page: dict[str, Any]) -> str | None:
    """A form being sent: refused unless it is a plain search."""
    if form.get("password") or form.get("card"):
        return "credentials_or_payment_form"
    action = str(form.get("action") or "")
    if PATHS.search(action) or PATHS.search(str(page.get("url") or "")):
        return "commitment_form"
    if get_commitment(action) or get_commitment(str(form.get("abs_action") or "")):
        return "commitment_form"
    plain = not (form.get("textarea") or form.get("email") or form.get("tel") or form.get("file"))
    if form.get("search_like") and plain:
        return None
    return "form_submit"


def commitment(facts: dict[str, Any], action: str) -> str | None:
    """None if the step is not an external commitment; else the reason."""
    tag = str(facts.get("tag") or "").lower()
    kind = str(facts.get("type") or "").lower()
    role = str(facts.get("role") or "").lower()
    raw_form, raw_page = facts.get("form"), facts.get("page")
    form: dict[str, Any] | None = raw_form if isinstance(raw_form, dict) else None
    page: dict[str, Any] = raw_page if isinstance(raw_page, dict) else {}
    if action in ("type", "select"):
        if secret_field(facts):
            return "payment_or_credentials_field"
        # A choice (or a text) whose change handler sends the form: a submit (7.1).
        if facts.get("autosubmit") and form is not None:
            return _form_submit(form, page)
        return None
    if action not in ("click", "download"):
        return None
    label = _text(facts.get("text"), facts.get("value"), facts.get("label"), facts.get("title"))
    href = str(facts.get("href") or "")
    submits = form is not None and (
        (tag == "button" and kind in ("", "submit"))
        or (tag == "input" and kind in ("submit", "image"))
        or role == "button"  # a scripted control in a form: it may submit it
    )
    if submits and form is not None:
        return _form_submit(form, page)
    if tag == "a":
        absolute = str(facts.get("abs_href") or "")
        if PATHS.search(href) or STRONG.search(label):
            return "commitment_link"
        if get_commitment(href) or get_commitment(absolute):
            return "commitment_link"
        return None
    if WORDS.search(label):
        return "commitment_button"
    return None


# What the browser collects about a target (run in the page; no side effect).
# A click lands on the element's activation target: a span inside a button is
# the button, a label is the control it labels (7.1). A select or field whose
# change handler submits the form is marked (`autosubmit`, 7.1).
FACTS_JS = """
(el) => {
  el = el.closest('button,input,select,textarea,a,[role=button],label') || el;
  if (el.tagName === 'LABEL') { el = el.control || el; }
  const f = el.form || el.closest('form');
  const q = (s) => f ? f.querySelectorAll(s).length : 0;
  const inputs = f ? Array.from(f.querySelectorAll('input,select,textarea'))
      .filter(i => i.type !== 'hidden') : [];
  const names = inputs.map(i =>
      ((i.name || '') + ' ' + (i.id || '') + ' ' + (i.autocomplete || '')).toLowerCase());
  const searchy = f && (f.getAttribute('role') === 'search' || q('input[type=search]') > 0 ||
      names.some(n => /(^|\\s)(q|query|search|s|keyword|keywords|term)(\\s|$)/.test(n)) ||
      /search|جستجو/i.test(f.getAttribute('action') || ''));
  const handler = (el.getAttribute('onchange') || '') + ' ' + (el.getAttribute('oninput') || '');
  return {
    tag: el.tagName, type: el.getAttribute('type') || '', role: el.getAttribute('role') || '',
    text: (el.innerText || '').slice(0, 200),
    value: (el.type === 'password' ? '' : (el.value || '')).toString().slice(0, 100),
    label: el.getAttribute('aria-label') || '', title: el.getAttribute('title') || '',
    name: el.getAttribute('name') || '', id: el.id || '',
    autocomplete: el.getAttribute('autocomplete') || '',
    href: el.getAttribute('href') || '',
    abs_href: (el.tagName === 'A' && el.href) ? String(el.href).slice(0, 2000) : '',
    autosubmit: /submit\\s*\\(|requestSubmit|\\.submit\\b/i.test(handler),
    form: f ? {
      action: f.getAttribute('action') || '',
      abs_action: String(f.action || '').slice(0, 2000),
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
