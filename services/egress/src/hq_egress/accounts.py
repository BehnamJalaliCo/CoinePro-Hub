"""Holding service accounts at egress (prompt 07 §2.5).

The secret reaches egress inside one call (from the api, through the gateway)
and is put on the request at send time, for the account's own host only. It
is never in a result: every outgoing value is scrubbed of it (as written,
percent-encoded and base64), and a browser screenshot masks the fields it was
typed into.
"""

from __future__ import annotations

import base64
from typing import Any, Literal
from urllib.parse import quote, quote_plus

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


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    site: str = Field(min_length=3, max_length=253)
    secret: str = Field(min_length=1, max_length=8000)
    inject: Inject = Field(default_factory=Inject)
    browse: BrowseLogin | None = None
    ports: list[int] = Field(default_factory=list, max_length=5)

    def covers(self, host: str) -> bool:
        site = self.site.lower().rstrip(".")
        return host == site or host.endswith("." + site)

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
