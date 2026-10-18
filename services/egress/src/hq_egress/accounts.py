"""Holding service accounts at egress (prompt 07 §2.5).

The secret reaches egress inside one call (from the api, through the gateway)
and is put on the request at send time, for the account's own host only. It
is never in a result: every outgoing value is scrubbed of it (as written,
percent-encoded and base64), and a browser screenshot masks the fields it was
typed into.
"""

from __future__ import annotations

import base64
import posixpath
from typing import Any, Literal
from urllib.parse import quote, quote_plus, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field

MASK = "[secret]"


class Inject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["bearer", "header", "basic", "cookie"] = "bearer"
    name: str | None = Field(default=None, max_length=100)  # header or cookie name
    username: str | None = Field(default=None, max_length=200)  # basic


class BrowseLogin(BaseModel):
    """How the browser signs in: a cookie or header, or a login form egress fills."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["cookie", "header", "form"]
    name: str | None = Field(default=None, max_length=100)
    login_url: str | None = Field(default=None, max_length=2000)
    username: str | None = Field(default=None, max_length=200)
    user_selector: str | None = Field(default=None, max_length=200)
    pass_selector: str | None = Field(default=None, max_length=200)
    submit_selector: str | None = Field(default=None, max_length=200)


class AllowRule(BaseModel):
    """A call other than GET/HEAD the owner listed as non-committing."""

    model_config = ConfigDict(extra="forbid")
    methods: list[str] = Field(default_factory=list, max_length=5)
    path_prefix: str = Field(default="", max_length=500)


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    site: str = Field(min_length=3, max_length=253)
    secret: str = Field(min_length=1, max_length=8000)
    inject: Inject = Field(default_factory=Inject)
    browse: BrowseLogin | None = None
    ports: list[int] = Field(default_factory=list, max_length=5)
    allow: list[AllowRule] = Field(default_factory=list, max_length=50)

    def covers(self, host: str) -> bool:
        site = self.site.lower().rstrip(".")
        return host == site or host.endswith("." + site)

    def allows(self, method: str, url: str) -> bool:
        """A GET/HEAD, or a call the owner listed (method, path prefix) on the
        account's own site: what web.browse may send while signed in."""
        method = method.upper()
        if method in ("GET", "HEAD"):
            return True
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        if not self.covers((parts.hostname or "").lower().rstrip(".")):
            return False
        path = clean_path(parts.path or "/")
        return path is not None and any(
            method in (m.upper() for m in r.methods)
            and r.path_prefix.startswith("/")
            and path.startswith(r.path_prefix)
            for r in self.allow
        )

    def headers_for(self, host: str, headers: dict[str, str]) -> dict[str, str]:
        if not self.covers(host):
            return headers
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
    """The forms a secret can take in a page or a header (longest first)."""
    forms = {
        secret,
        quote(secret, safe=""),
        quote_plus(secret),
        base64.b64encode(secret.encode()).decode(),
    }
    return sorted((f for f in forms if len(f) >= 4), key=len, reverse=True)


def scrub(value: Any, secrets: list[str]) -> Any:
    """`value` with every form of every secret replaced (deep, any JSON value)."""
    if not secrets:
        return value
    forms = [f for s in secrets for f in variants(s)]
    return _scrub(value, forms)


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
