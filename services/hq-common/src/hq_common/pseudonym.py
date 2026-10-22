"""The customer pseudonym (prompt 10 §1.2, contract §19.0): analytics, the
revenue radar, referral rescue and the feedback inbox know a customer only by
`subject`, never by a handle or an exchange UID.

    subject = HMAC-SHA256(key, company || channel || external_id), hex

`key` is kv/support/pseudonym in OpenBao (32 random bytes, made once with KV
check-and-set cas 0 by infra/openbao/kv-once.sh; never rotated unless the
owner asks: a new key makes every past subject a stranger). The three parts
are joined with the unit separator (U+001F), which none of them may contain,
so ("ab", "c") and ("a", "bc") never meet.

`channel` names where the external id comes from:
  telegram_business | telegram_bot | chatwoot | product_bot | mystery
                       a support channel kind (contract §19.3): the channel's
                       own user id (a Telegram user id, a Chatwoot contact id)
  uid:<exchange>       an exchange UID (uid:lbank): the affiliate team list,
                       referral.check and the products' events, so the same
                       person has one subject across them
`company` is the company's id (uuid text): stable, and never shown.
"""

from __future__ import annotations

import hashlib
import hmac
import re

SEP = "\x1f"
SUBJECT = re.compile(r"^[0-9a-f]{64}$")
CHANNEL = re.compile(
    r"^(?:telegram_business|telegram_bot|chatwoot|product_bot|mystery|uid:[a-z][a-z0-9_-]{1,30})$"
)
MIN_KEY_BYTES = 32


class KeyMissing(RuntimeError):
    """kv/support/pseudonym is not loaded: no subject may be made without it."""


def subject(key: bytes, company: str, channel: str, external_id: str) -> str:
    if len(key) < MIN_KEY_BYTES:
        raise KeyMissing("the pseudonym key (kv/support/pseudonym) is not loaded")
    if not CHANNEL.match(channel):
        raise ValueError(f"unknown pseudonym channel {channel!r}")
    ext = external_id.strip()
    if not company or not ext or any(SEP in part for part in (company, ext)):
        raise ValueError("company and external_id must be non-empty and hold no U+001F")
    if len(ext) > 128:
        raise ValueError("external_id is longer than 128 characters")
    msg = SEP.join((company, channel, ext)).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def is_subject(value: str) -> bool:
    return bool(SUBJECT.match(value))
