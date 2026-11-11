"""Server defence of the talk (contract §32.5): a key never enters a
conversation, a log, the Audit body or a model prompt.

Every turn's text passes `clean` before it is stored and before any model
call. The providers' key shapes (seed/talk/secrets.yaml) become «[کلید حذف شد]»
and are reported, so the persona answers «کلید را با دکمه‌ی 🔑 بده» instead of
sending anything to a model; hq_common.redact then masks whatever other
credential shape is left (personal data stays: the owner may speak of people).
"""

from __future__ import annotations

from hq_api.talk import data
from hq_common.redact import scrub


def clean(text: str) -> tuple[str, bool]:
    """(the text without any key, whether a key was in it)."""
    replacement, _, shapes = data.secrets()
    out = text
    for shape in shapes:
        out = shape.pattern.sub(replacement, out)
    found = out != text
    masked = scrub(out, secrets_only=True)
    return masked, found or masked != out


def key_answer() -> str:
    return data.secrets()[1]


def marker() -> str:
    return data.secrets()[0]
