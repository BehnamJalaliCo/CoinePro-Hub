"""H2 `connection.set` (agents/tools.md, 2026-11-08): a company's connection's NON-SECRET
settings, registered by an agent (the owner could not have the account names and the read
command registered from a session).

    connection.set  A2  {company?, kind, accounts?: [@handle], via?: "ig_hub",
                        server?: {company, name}, read_command?, publish_command?, channels?:
                        [{chat, title_fa?, role?}], site_url?, channel_id?, handle?, property_id?}
                        Instagram: the account names and that they are read through IG-Hub (its
                        server), a read-only command the daily read runs there; Telegram: the
                        public channels; a site's address; YouTube's channel id. The company's
                        CEO, media director and technical roles for their own company; a technical
                        role for another company within the linked rule (H1). Never a secret: the
                        api refuses anything that looks like one (the owner stores those once).

Held by the CEO, the CTO, the media director and the DevOps engineer (their charters); the api and
the policy (hq.internal, connections.rego) decide which company may be written.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field

from hq_gateway import tools as T

HANDLE = r"^@?[A-Za-z0-9_.\-]{2,64}$"


class ServerIn(T.In):
    company: str = Field(pattern=T.CODE)
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


class ChannelIn(T.In):
    chat: str = Field(pattern=r"^(@[A-Za-z0-9_]{4,64}|-?[0-9]{5,20})$")
    title_fa: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=40)


class ConnectionSetIn(T.In):
    company: str | None = Field(default=None, pattern=T.CODE)
    kind: Literal[
        "search_console", "ga4", "instagram", "telegram", "youtube", "x", "pagespeed", "trends",
        "bing", "play_console", "google_ads", "meta_ads",
    ]  # fmt: skip
    accounts: list[str] | None = Field(default=None, max_length=20)
    via: Literal["ig_hub"] | None = None
    server: ServerIn | None = None
    read_command: str | None = Field(default=None, min_length=2, max_length=500)
    # ⟨2026-11-10⟩ §44.5 the command the server's own runner runs to publish a file
    publish_command: str | None = Field(default=None, min_length=2, max_length=500)
    channels: list[ChannelIn] | None = Field(default=None, max_length=20)
    site_url: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    channel_id: str | None = Field(default=None, pattern=HANDLE)
    handle: str | None = Field(default=None, pattern=HANDLE)
    property_id: str | None = Field(default=None, pattern=r"^[0-9]{3,20}$")


async def connection_set(api: T.Api, call: T.Call, a: ConnectionSetIn) -> T.Result:
    body: dict[str, Any] = a.model_dump(mode="json", exclude_none=True)
    if a.accounts is not None and not all(re.fullmatch(HANDLE, x) for x in a.accounts):
        return T.Result(
            "error",
            code="invalid_args",
            fields={"accounts": "handles like @name"},
            hint_fa="نام حساب باید کوتاه و بی‌فاصله باشد: حرف لاتین، عدد، نقطه، خط.",
        )
    if len(body) <= 1 + (1 if a.company else 0):
        return T.Result(
            "error",
            code="invalid_args",
            fields={"kind": "give at least one setting"},
            hint_fa="دست‌کم یک تنظیم لازم است: نام حساب، سرور، دستور خواندن، کانال یا نشانی سایت.",
        )
    # a command and a site address are code: they leave as written (the api checks them); the
    # titles are prose and leave redacted
    for c in body.get("channels") or []:
        if isinstance(c.get("title_fa"), str):
            c["title_fa"] = await T._text(c["title_fa"])
    resp = await api.request("POST", "/internal/v1/connections/set", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"{r.data.get('company')}:{a.kind}"
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "connection.set": (ConnectionSetIn, connection_set),
}
T.TOOLS.update(TOOLS)
