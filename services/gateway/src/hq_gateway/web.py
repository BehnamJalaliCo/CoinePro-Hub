"""The internet tools (agents/tools.md v2, contract §18.7): web.search,
web.read, web.browse, http.request and egress.recent.

Every call goes the same way:
1. reserve at the api (`/internal/v1/egress/reserve`, the run's token): the
   data guard on everything that would leave (query, URL, body), the run's
   and the company's egress limits, and a service account the company may
   use (its secret comes back for this call only);
2. the egress service carries it out (it alone reaches the internet; it
   checks every address and redirect, and refuses an external commitment);
3. its log entries go to the egress log (`/internal/v1/egress/log`);
4. the model gets the result as untrusted web data, without the secret.

A browse screenshot or download becomes an agent file of the run's company
(`/internal/v1/files`), named in the result by its file id.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import Field, field_validator

from hq_gateway import tools as T

NEEDS_OWNER_FA = (
    "این کار یک تعهد بیرونی به نام هلدینگ است (پرداخت، خرید، انتشار، پیام به یک آدم بیرونی، "
    "ساخت حساب یا تغییر امنیت حساب). آن را انجام نده؛ با propose برای مالک پیشنهادش بده."
)
BROWSE_S = float(os.environ.get("EGRESS_BROWSE_S", "15"))
READ_METHODS = ("GET", "HEAD")


class Egress:
    """The egress service's API (hq-egress-api, the gateway's only peer there)."""

    def __init__(
        self, base_url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport, trust_env=False
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(path, json=body)
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("egress answered no object")
        return data


# ------------------------------------------------------------------ inputs --
ACCOUNT = r"^[a-z0-9][a-z0-9_.-]{1,40}$"


class WebSearchIn(T.In):
    q: str = Field(min_length=2, max_length=400)
    lang: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    recency_days: int | None = Field(default=None, ge=1, le=3650)
    site: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.-]{3,253}$")
    n: int = Field(default=8, ge=1, le=20)


class WebReadIn(T.In):
    url: str = Field(min_length=8, max_length=4000, pattern=r"^https?://")
    mode: Literal["text", "pdf", "html"] = "text"
    max_chars: int = Field(default=20_000, ge=200, le=100_000)


class BrowseStepIn(T.In):
    do: Literal[
        "goto", "click", "type", "select", "scroll", "wait", "read", "screenshot", "download"
    ]
    target: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=5000)
    url: str | None = Field(default=None, max_length=4000, pattern=r"^https?://")


class WebBrowseIn(T.In):
    steps: list[BrowseStepIn] = Field(min_length=1, max_length=20)
    account: str | None = Field(default=None, pattern=ACCOUNT)


class HttpRequestIn(T.In):
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    url: str = Field(min_length=8, max_length=4000, pattern=r"^https?://")
    headers: dict[str, str] | None = Field(default=None, max_length=30)
    json_: Any = Field(default=None, alias="json")
    body: str | None = Field(default=None, max_length=200_000)
    account: str | None = Field(default=None, pattern=ACCOUNT)

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        for k, val in v.items():
            if not k or len(k) > 100 or len(val) > 4000 or any(c in k for c in ":\r\n "):
                raise ValueError("a header name without ':', spaces or newlines; values up to 4000")
            if "\r" in val or "\n" in val:
                raise ValueError("no newline in a header value")
        return v


class EgressRecentIn(T.In):
    company: str | None = Field(default=None, pattern=T.CODE)
    actor: str | None = Field(default=None, pattern=T.EMP)
    since: datetime | None = None
    blocked: bool | None = None


# ------------------------------------------------------- the call's class --
def browse_class(a: WebBrowseIn) -> str:
    """Reading is A0; using a holding service account is A2."""
    return "A2" if a.account else "A0"


def http_class(a: HttpRequestIn) -> str:
    """GET/HEAD without an account are A0; anything else is A2."""
    return "A0" if a.method in READ_METHODS and not a.account else "A2"


# --------------------------------------------------------------- the path --
def _strings(*values: Any) -> list[str]:
    out: list[str] = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out += _strings(*v.keys(), *v.values())
        elif isinstance(v, list):
            out += _strings(*v)
        else:
            out.append(str(v))
    return out


async def _reserve(
    api: T.Api,
    call: T.Call,
    tool: str,
    cls: str,
    strings: list[str],
    *,
    method: str = "GET",
    url: str | None = None,
    account: str | None = None,
) -> tuple[dict[str, Any] | None, T.Result | None]:
    resp = await api.request(
        "POST",
        "/internal/v1/egress/reserve",
        call.token,
        json={
            "tool": tool,
            "class": cls,
            "strings": strings,
            "method": method,
            "url": url,
            "account": account,
        },
    )
    r = T.from_response(resp, None)
    if r.outcome != "ok":
        if r.code == "needs_owner":
            r.hint_fa = r.hint_fa or NEEDS_OWNER_FA
        return None, r
    if not isinstance(r.data, dict):
        return None, T.Result("error", code="api_bad_answer")
    return r.data, None


async def _log(api: T.Api, call: T.Call, tool: str, cls: str, out: dict[str, Any]) -> None:
    entries = out.get("entries")
    if isinstance(entries, list) and entries:
        await api.request(
            "POST",
            "/internal/v1/egress/log",
            call.token,
            json={"tool": tool, "class": cls, "entries": entries[:200]},
        )


def _ctx(call: T.Call, cls: str, grant: dict[str, Any]) -> dict[str, Any]:
    g = call.gate
    return {
        "company": g["company"],
        "actor": g["employee"],
        "run_id": str(g.get("run_id")) if g.get("run_id") else None,
        "cls": cls,
        "max_bytes": int(grant.get("max_bytes") or 1),
    }


def _result(out: dict[str, Any], ref: str | None = None) -> T.Result:
    outcome, code, data = out.get("outcome"), out.get("code"), out.get("data")
    if outcome == "ok":
        return T.Result("ok", ref=ref, data=data)
    if outcome == "blocked":
        hint = NEEDS_OWNER_FA if code == "needs_owner" else None
        return T.Result("denied", code=str(code or "egress_blocked"), data=data, hint_fa=hint)
    return T.Result("error", code=str(code or "egress_failed"))


async def _carry(
    api: T.Api,
    call: T.Call,
    tool: str,
    cls: str,
    path: str,
    payload: dict[str, Any],
    strings: list[str],
    *,
    method: str = "GET",
    url: str | None = None,
    account: str | None = None,
) -> tuple[dict[str, Any] | None, T.Result | None]:
    if api.egress is None:
        return None, T.Result("error", code="channel_not_configured")
    grant, err = await _reserve(
        api, call, tool, cls, strings, method=method, url=url, account=account
    )
    if err is not None:
        return None, err
    assert grant is not None
    body = {"ctx": _ctx(call, cls, grant), **payload}
    if grant.get("account") is not None:
        body["account"] = grant["account"]
    try:
        out = await api.egress.post(path, body)
    finally:
        grant.pop("account", None)  # the secret lives for this call only
    await _log(api, call, tool, cls, out)
    return out, None


# -------------------------------------------------------------- the tools --
async def web_search(api: T.Api, call: T.Call, a: WebSearchIn) -> T.Result:
    payload = a.model_dump(exclude_none=True)
    out, err = await _carry(
        api, call, "web.search", "A0", "/v1/search", payload, _strings(a.q, a.site)
    )
    return err or _result(out or {})


async def web_read(api: T.Api, call: T.Call, a: WebReadIn) -> T.Result:
    out, err = await _carry(
        api, call, "web.read", "A0", "/v1/read", a.model_dump(), _strings(a.url), url=a.url
    )
    return err or _result(out or {})


async def web_browse(api: T.Api, call: T.Call, a: WebBrowseIn) -> T.Result:
    cls = browse_class(a)
    steps = [s.model_dump(exclude_none=True) for s in a.steps]
    first = next((s.url for s in a.steps if s.url), None)
    out, err = await _carry(
        api,
        call,
        "web.browse",
        cls,
        "/v1/browse",
        {"steps": steps, "time_s": BROWSE_S},
        _strings(steps),
        url=first,
        account=a.account,
    )
    if err is not None:
        return err
    assert out is not None
    r = _result(out)
    stored: list[dict[str, Any]] = []
    for f in out.get("files") or []:
        if not isinstance(f, dict) or not isinstance(f.get("data_b64"), str):
            continue
        ref = await _store(api, call, f)
        if ref is not None:
            stored.append(ref)
    if isinstance(r.data, dict):
        r.data["files"] = stored
    return r


async def _store(api: T.Api, call: T.Call, f: dict[str, Any]) -> dict[str, Any] | None:
    """A screenshot or download as an agent file of the run's company."""
    data = base64.b64decode(f["data_b64"])
    mime = str(f.get("mime") or "application/octet-stream")
    resp = await api.upload(
        "/internal/v1/files",
        call.token,
        data,
        mime if T.MIME_OK.match(mime) else "application/octet-stream",
        params={"name": str(f.get("name") or "download")[:120]},
    )
    if resp.status_code != 201:
        return None
    ref = resp.json()
    return {
        "file_id": ref.get("id"),
        "kind": f.get("kind"),
        "mime": ref.get("mime"),
        "size": ref.get("size"),
        "step": f.get("step"),
    }


async def http_request(api: T.Api, call: T.Call, a: HttpRequestIn) -> T.Result:
    cls = http_class(a)
    payload: dict[str, Any] = {"method": a.method, "url": a.url, "headers": a.headers or {}}
    if a.json_ is not None:
        payload["json_body"] = a.json_
    if a.body is not None:
        payload["body"] = a.body
    out, err = await _carry(
        api,
        call,
        "http.request",
        cls,
        "/v1/http",
        payload,
        _strings(a.url, a.headers, a.json_, a.body),
        method=a.method,
        url=a.url,
        account=a.account,
    )
    return err or _result(out or {})


async def egress_recent(api: T.Api, call: T.Call, a: EgressRecentIn) -> T.Result:
    params = {
        "company": a.company,
        "actor": a.actor,
        "since": a.since.isoformat() if a.since else None,
        "blocked": None if a.blocked is None else str(a.blocked).lower(),
    }
    return T.from_response(
        await api.request("GET", "/internal/v1/egress/recent", call.token, params=params), None
    )


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "web.search": (WebSearchIn, web_search),
    "web.read": (WebReadIn, web_read),
    "web.browse": (WebBrowseIn, web_browse),
    "http.request": (HttpRequestIn, http_request),
    "egress.recent": (EgressRecentIn, egress_recent),
}
CALL_CLASS: dict[str, Callable[[Any], str]] = {
    "web.browse": browse_class,
    "http.request": http_class,
}

# Registered with the gateway's tools (tools.py itself knows nothing of the web).
T.TOOLS.update(TOOLS)
T.CALL_CLASS.update(CALL_CLASS)
