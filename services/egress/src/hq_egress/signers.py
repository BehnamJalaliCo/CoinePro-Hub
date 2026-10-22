"""Reviewed request signers (prompt 10 §2.2, contract §19.1 ⟨1.5⟩).

Some exchange APIs want an HMAC over the request's parameters, not a fixed
header, so egress's four injections (bearer, header, basic, cookie) cannot
carry them. A service account whose policy says
`inject: {kind: "signer", signer: "<name>"}` is signed here, by a signer from
this fixed list: never user input, never a model's choice.

A signer account is used only by a connector of code (connectors.py, reached
through `POST /internal/v1/egress/connectors/{adapter}/pull`, the worker
only); http.request, web.read and web.browse refuse it (`policy_denied`).
The secret arrives inside one call, is used for that call only and is
scrubbed from everything that goes back (accounts.scrub): no log, error or
answer holds it.

lbank-v2   LBank API v2 (HmacSHA256): the secret is "<api_key>:<secret_key>"
           (one line, as `make account-secret` takes it). Every parameter
           plus api_key, timestamp (ms), signature_method and echostr,
           sorted by name and joined as k=v&k=v, is MD5-hashed (upper-case
           hex); `sign` = HMAC-SHA256(secret_key, that hash), lower-case hex.
           The request is a form POST; timestamp, signature_method and
           echostr also go as headers (LBank's v2 convention).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

ECHO_ALPHABET = string.ascii_letters + string.digits


class SignerError(ValueError):
    """The secret does not have the shape the signer needs (never says why
    beyond that: the secret itself is never in a message)."""


@dataclass(frozen=True)
class Signed:
    form: dict[str, str]  # the request's parameters, `sign` included
    headers: dict[str, str]


def split_pair(secret: str) -> tuple[str, str]:
    """"<api_key>:<secret_key>" -> (api_key, secret_key)."""
    api_key, sep, secret_key = secret.strip().partition(":")
    if not sep or not api_key or not secret_key:
        raise SignerError("this signer needs the secret as 'api_key:secret_key'")
    return api_key, secret_key


def parts(name: str, secret: str) -> list[str]:
    """The pieces of a signer's secret that must be scrubbed too."""
    if name == "lbank-v2":
        try:
            return [p for p in split_pair(secret) if len(p) >= 4]
        except SignerError:
            return []
    return []


def lbank_v2(
    params: Mapping[str, str],
    secret: str,
    *,
    now_ms: int | None = None,
    echostr: str | None = None,
) -> Signed:
    api_key, secret_key = split_pair(secret)
    ts = str(now_ms if now_ms is not None else int(time.time() * 1000))
    echo = echostr or "".join(secrets.choice(ECHO_ALPHABET) for _ in range(35))
    form = {str(k): str(v) for k, v in params.items()}
    form.update({"api_key": api_key, "timestamp": ts, "signature_method": "HmacSHA256", "echostr": echo})
    form["sign"] = lbank_v2_sign(form, secret_key)
    headers = {"timestamp": ts, "signature_method": "HmacSHA256", "echostr": echo}
    return Signed(form, headers)


def lbank_v2_sign(form: Mapping[str, str], secret_key: str) -> str:
    """The `sign` of a parameter set (the `sign` key itself is left out)."""
    payload = "&".join(f"{k}={form[k]}" for k in sorted(form) if k != "sign")
    digest = hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest().upper()
    return hmac.new(secret_key.encode(), digest.encode(), hashlib.sha256).hexdigest()


SIGNERS: dict[str, Callable[..., Signed]] = {"lbank-v2": lbank_v2}
