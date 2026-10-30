"""Holding service accounts at egress (prompt 07 §2.5).

The secret reaches egress inside one call (from the api, through the gateway)
and is put on the request at send time, for the account's own host only and
over https only. It is never in a result: every outgoing value is scrubbed of
it (as written, percent-encoded, base64 with or without padding, and the
Basic pair `base64("user:secret")`) BEFORE any text is cut (7.1), a file that
holds it is dropped, and a browser screenshot masks the fields it was typed
into. An extra port of the account's policy opens for its own site only.

A `profile` account (prompt 12 §9.1, contract §21.13: chatgpt-web,
gemini-web, deepseek-web) has no secret at all: it names a signed-in browser
profile that only the profile browser (browser-web) mounts; web.browse with
it runs in that profile and reaches only its site's own hosts.
"""

from __future__ import annotations

import base64
import posixpath
from typing import Any, Literal
from urllib.parse import quote, quote_plus, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hq_egress.signers import parts

MASK = "[secret]"


class Inject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # "signer" (prompt 10 §2.2): a reviewed request signer (signers.SIGNERS),
    # for a connector of code only; it injects nothing into any other request.
    kind: Literal["bearer", "header", "basic", "cookie", "signer"] = "bearer"
    name: str | None = Field(default=None, max_length=100)  # header or cookie name
    username: str | None = Field(default=None, max_length=200)  # basic
    signer: Literal["lbank-v2"] | None = None  # kind "signer" only

    @model_validator(mode="after")
    def _signer_with_its_kind(self) -> Inject:
        if (self.kind == "signer") != (self.signer is not None):
            raise ValueError("a signer goes with kind 'signer', and only with it")
        return self


class BrowseLogin(BaseModel):
    """How the browser signs in: a cookie or header, or a login form egress fills."""

    model_config = ConfigDict(extra="forbid")
    # "profile" (prompt 12 §9.1): a signed-in browser profile, no secret.
    kind: Literal["cookie", "header", "form", "profile"]
    name: str | None = Field(default=None, max_length=100)
    login_url: str | None = Field(default=None, max_length=2000)
    username: str | None = Field(default=None, max_length=200)
    user_selector: str | None = Field(default=None, max_length=200)
    pass_selector: str | None = Field(default=None, max_length=200)
    submit_selector: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _profile_alone(self) -> BrowseLogin:
        extra = (self.name, self.login_url, self.username, self.user_selector,
                 self.pass_selector, self.submit_selector)  # fmt: skip
        if self.kind == "profile" and any(v is not None for v in extra):
            raise ValueError("a profile takes nothing but its kind")
        return self


class AllowRule(BaseModel):
    """A call other than GET/HEAD the owner listed as non-committing. `host`:
    on that host (and its subdomains) instead of the account's site, e.g. the
    bot check a signed-in site puts in front of its pages (2026-10-29, the
    owner's look at chatgpt.com); never a host the credential goes to."""

    model_config = ConfigDict(extra="forbid")
    methods: list[str] = Field(default_factory=list, max_length=5)
    path_prefix: str = Field(default="", max_length=500)
    host: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.-]{3,253}$")


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    site: str = Field(min_length=3, max_length=253)
    # None only for a signed-in profile (it has no secret at all).
    secret: str | None = Field(default=None, min_length=1, max_length=8000)
    inject: Inject = Field(default_factory=Inject)
    browse: BrowseLogin | None = None
    ports: list[int] = Field(default_factory=list, max_length=5)
    allow: list[AllowRule] = Field(default_factory=list, max_length=50)
    # A signed-in profile's own pages (path prefixes on its site) where a plain
    # form may be sent: the owner's own chat there (2026-10-29). Never a
    # password, payment or commitment form (rules.commitment's other reasons).
    submit_on: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _secret_unless_profile(self) -> Account:
        if self.is_profile:
            if self.secret is not None or self.inject.kind == "signer":
                raise ValueError("a profile account carries no secret")
        elif not self.secret:
            raise ValueError("an account needs its secret")
        if self.submit_on and not self.is_profile:
            raise ValueError("only a profile account sends forms")
        if any(not p.startswith("/") or len(p) < 2 or len(p) > 200 for p in self.submit_on):
            raise ValueError("submit_on takes path prefixes other than /")
        return self

    @property
    def is_profile(self) -> bool:
        return self.browse is not None and self.browse.kind == "profile"

    def submits_on(self, url: str) -> bool:
        """`url` is one of the pages its plain forms may be sent from."""
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        path = clean_path(parts.path or "/")
        return (
            self.is_profile
            and parts.scheme == "https"
            and self.covers((parts.hostname or "").lower().rstrip("."))
            and path is not None
            and any(path.startswith(p) for p in self.submit_on)
        )

    def covers(self, host: str) -> bool:
        return _under(host, self.site)

    def ports_for(self, host: str) -> tuple[int, ...]:
        """The policy's extra ports: for the account's own site only (7.1),
        never for a host a redirect or a page sends the call to."""
        return tuple(self.ports) if self.covers(host) else ()

    @property
    def is_signer(self) -> bool:
        """A signed connector's account (prompt 10 §2.2): never for http.request,
        web.read or web.browse."""
        return self.inject.kind == "signer"

    def secrets(self) -> list[str]:
        """What a result must never hold: the secret, and the `user:secret`
        pair a Basic header carries (its base64 is a form of it, 7.1); a
        signer's secret also as each of its parts (api key, secret key)."""
        if self.secret is None:
            return []
        users = {self.browse.username if self.browse else None}
        if self.inject.kind == "basic":
            users.add(self.inject.username or "")
        pairs = [f"{u}:{self.secret}" for u in sorted(u for u in users if u is not None)]
        signer = parts(self.inject.signer, self.secret) if self.inject.signer else []
        return [self.secret, *pairs, *signer]

    def allows(self, method: str, url: str) -> bool:
        """A GET/HEAD, or a call the owner listed (method, path prefix) on the
        account's own site, or on the rule's own host when it names one: what
        web.browse may send while signed in."""
        method = method.upper()
        if method in ("GET", "HEAD"):
            return True
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        host = (parts.hostname or "").lower().rstrip(".")
        path = clean_path(parts.path or "/")
        return path is not None and any(
            method in (m.upper() for m in r.methods)
            and r.path_prefix.startswith("/")
            and path.startswith(r.path_prefix)
            and (_under(host, r.host) if r.host else self.covers(host))
            for r in self.allow
        )

    def headers_for(
        self, host: str, headers: dict[str, str], scheme: str = "https"
    ) -> dict[str, str]:
        """`headers` with the credential: for the account's own host, over
        https only (never in clear text, whatever the policy says; 7.1)."""
        if scheme != "https" or not self.covers(host) or self.is_signer or self.secret is None:
            return headers  # a signer signs each request itself; a profile has no secret
        out = dict(headers)
        i = self.inject
        if i.kind == "bearer":
            out["Authorization"] = f"Bearer {self.secret}"
        elif i.kind == "header":
            out[i.name or "X-API-Key"] = self.secret
        elif i.kind == "basic":
            raw = f"{i.username or ''}:{self.secret}".encode()
            out["Authorization"] = "Basic " + base64.b64encode(raw).decode()
        elif i.kind == "cookie":
            out["Cookie"] = f"{i.name or 'session'}={self.secret}"
        return out


def _under(host: str, site: str) -> bool:
    """`host` is `site` or one of its subdomains."""
    site = site.lower().rstrip(".")
    host = host.lower().rstrip(".")
    return host == site or host.endswith("." + site)


def clean_path(raw: str) -> str | None:
    """The path as the server will see it, or None when it can be read two
    ways: a dot segment, an encoded dot, slash or backslash (at any depth of
    percent-encoding), a backslash or an empty segment
    (`/api/search/../../v1/charges` is sent as `/v1/charges`)."""
    path = raw
    for _ in range(5):
        low = path.lower()
        if any(x in low for x in ("%2e", "%2f", "%5c", "\\", "//")):
            return None
        if any(seg in (".", "..") for seg in path.split("/")):
            return None
        once = unquote(path)
        if once == path:
            break
        path = once
    else:
        return None
    if posixpath.normpath(path) not in (path, path.rstrip("/")):
        return None
    return unquote(raw)


def variants(secret: str) -> list[str]:
    """The forms a secret can take in a page or a header (longest first):
    as written, percent-encoded, and base64 (standard and URL-safe, with and
    without its padding)."""
    raw = secret.encode()
    b64 = base64.b64encode(raw).decode()
    url64 = base64.urlsafe_b64encode(raw).decode()
    forms = {secret, quote(secret, safe=""), quote_plus(secret), b64, b64.rstrip("="), url64,
             url64.rstrip("=")}  # fmt: skip
    return sorted((f for f in forms if len(f) >= 4), key=len, reverse=True)


def forms_of(secrets: list[str]) -> list[str]:
    """Every form of every secret, longest first (a longer one may hold a shorter)."""
    return sorted({f for s in secrets for f in variants(s)}, key=len, reverse=True)


def margin(secrets: list[str]) -> int:
    """How far past a cut a form of a secret can reach. Text is read this much
    longer, scrubbed, and only then cut: a secret cut in half by the cut would
    no longer match, and its first half would go out (7.1)."""
    return max((len(f) for f in forms_of(secrets)), default=0)


def scrub(value: Any, secrets: list[str]) -> Any:
    """`value` with every form of every secret replaced (deep, any JSON value)."""
    if not secrets:
        return value
    return _scrub(value, forms_of(secrets))


def scrub_cut(text: str, secrets: list[str], limit: int) -> tuple[str, bool]:
    """`text` scrubbed, THEN cut to `limit` characters; (text, cut)."""
    clean = scrub(text, secrets)
    return clean[:limit], len(clean) > limit


def holds_secret(data: bytes, secrets: list[str]) -> bool:
    """Whether a file's bytes hold a form of a secret (as UTF-8, or as the
    UTF-16 an office file or a PDF may store text in): such a file is
    dropped, never passed on (7.1)."""
    if not secrets or not data:
        return False
    return any(f.encode() in data or f.encode("utf-16-le") in data for f in forms_of(secrets))


def _scrub(value: Any, forms: list[str]) -> Any:
    if isinstance(value, str):
        for f in forms:
            if f in value:
                value = value.replace(f, MASK)
        return value
    if isinstance(value, dict):
        return {_scrub(k, forms): _scrub(v, forms) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, forms) for v in value]
    return value
