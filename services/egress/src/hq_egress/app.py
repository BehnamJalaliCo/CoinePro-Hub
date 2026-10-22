"""HTTP API of the egress service, for the Tool Gateway only (network
hq-egress-api; a client from anywhere else is refused).

    POST /v1/search        web.search through the hub's own SearXNG
    POST /v1/read          web.read: one page or file as readable text
    POST /v1/http          http.request: one request to an external API
    POST /v1/browse        web.browse: steps in a fresh browser session
    POST /v1/proxy/drain   the entries of one tool call's proxied connections
    POST /v1/connectors/call  one call of a connector of code (prompt 10 §2.3):
                           a fixed endpoint of an exchange, signed by a
                           reviewed signer, its answer reduced in egress
    GET  /v1/health

Every answer is {outcome: ok | blocked | error, code, data, entries}: the
entries (one per request that left or was stopped) go to the egress log
through the gateway. Web content is untrusted: `source: "web"`,
`untrusted: true`, the final URL, the time, and `suspected_injection`. A
service account's secret is scrubbed from a text before it is cut (7.1); a
GET that commits (rules.get_commitment) is `needs_owner` like any other.
An account with a signer (prompt 10 §2.2) is refused by every tool but a
connector (`policy_denied`).
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import contextlib
import functools
import ipaddress
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_common import untrusted
from hq_egress import __version__
from hq_egress import connectors as K
from hq_egress import extract as X
from hq_egress.accounts import Account, margin, scrub, scrub_cut
from hq_egress.config import Settings
from hq_egress.guard import Blocked, Guard
from hq_egress.net import CALL_ENTRIES, Entry, Fetcher, FetchError, track
from hq_egress.proxy import Buckets, entries_json
from hq_egress.rules import get_commitment
from hq_egress.signers import SIGNERS, SignerError

log = logging.getLogger("hq_egress")
TEXT_TYPES = ("text/", "application/json", "application/xml", "application/javascript")
KEEP_HEADERS = (
    "content-type",
    "content-length",
    "date",
    "etag",
    "last-modified",
    "location",
    "link",
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
)
CLASS = Literal["A0", "A1", "A2"]
CONNECTOR_BYTES = 2 * 1024 * 1024  # one exchange answer (a page of 100 rows is ~20 KB)


class Ctx(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    actor: str = Field(min_length=2, max_length=60)
    run_id: str | None = Field(default=None, max_length=64)
    cls: CLASS = "A0"
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=200 * 1024 * 1024)


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ctx: Ctx
    q: str = Field(min_length=1, max_length=500)
    lang: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    recency_days: int | None = Field(default=None, ge=1, le=3650)
    site: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.-]{3,253}$")
    n: int = Field(default=8, ge=1, le=20)


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ctx: Ctx
    url: str = Field(min_length=8, max_length=4000)
    mode: Literal["text", "pdf", "html"] = "text"
    max_chars: int = Field(default=20_000, ge=200, le=200_000)
    account: Account | None = None


class HttpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ctx: Ctx
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    url: str = Field(min_length=8, max_length=4000)
    headers: dict[str, str] = Field(default_factory=dict, max_length=30)
    json_body: Any = None
    body: str | None = Field(default=None, max_length=1_000_000)
    max_chars: int = Field(default=20_000, ge=200, le=200_000)
    account: Account | None = None


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    do: Literal[
        "goto", "click", "type", "select", "scroll", "wait", "read", "screenshot", "download"
    ]
    target: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=5000)
    url: str | None = Field(default=None, max_length=4000)


class BrowseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ctx: Ctx
    steps: list[Step] = Field(min_length=1, max_length=30)
    account: Account | None = None
    time_s: float = Field(default=20, gt=0, le=120)


Scalar = str | int


class ConnectorIn(BaseModel):
    """One call of a connector (prompt 10 §2.3): `params` go to the exchange
    (each endpoint's list only), `local` stays here (the company's minimum
    balance, for meets_minimum)."""

    model_config = ConfigDict(extra="forbid")
    ctx: Ctx
    adapter: str = Field(pattern=r"^[a-z][a-z0-9-]{1,40}$")
    tool: Literal["revenue.pull", "referral.check"]
    endpoint: str = Field(pattern=r"^[a-z][a-z/._-]{1,60}$")
    params: dict[str, Scalar] = Field(default_factory=dict, max_length=20)
    local: dict[str, Scalar | float | None] = Field(default_factory=dict, max_length=10)
    account: Account | None = None


class DrainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(min_length=8, max_length=64)


class State:
    def __init__(
        self,
        settings: Settings,
        guard: Guard,
        buckets: Buckets,
        *,
        internal: httpx.AsyncClient | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.settings = settings
        self.guard = guard
        self.buckets = buckets
        self.fetcher = fetcher or Fetcher(guard, settings.fetch_timeout_s)
        self.rates = K.Buckets()  # the connectors' rate limits, per account
        # The hub's own upstreams (SearXNG, the browser): fixed addresses, not agent input.
        self.internal = internal or httpx.AsyncClient(
            timeout=settings.browse_call_s + 15, trust_env=False
        )


def answer(
    outcome: str,
    data: Any = None,
    entries: list[Entry] | None = None,
    code: str | None = None,
    secrets: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body = {
        "outcome": outcome,
        "code": code,
        "data": scrub(data, secrets or []),
        "entries": entries_json(entries or []),
    }
    if files:
        body["files"] = files  # binary (base64), never scrubbed as text
    return JSONResponse(body)


def build_app(state: State) -> FastAPI:
    app = FastAPI(
        title="egress", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.egress = state
    untrusted.set_slots(X.SLOTS)

    def guarded(
        fn: Callable[[Any], Awaitable[JSONResponse]],
    ) -> Callable[[Any], Awaitable[JSONResponse]]:
        """One call: within its deadline (below the gateway's), and whatever
        a hostile server or parser does, an answer with the call's entries,
        so every request that left reaches the egress log and the limits."""

        @functools.wraps(fn)
        async def call(a: Any) -> JSONResponse:
            entries: list[Entry] = []
            token = CALL_ENTRIES.set(entries)
            secrets = _secrets(a)
            start = time.monotonic()
            code = "egress_failed"
            try:
                async with asyncio.timeout(state.settings.call_deadline_s):
                    return await fn(a)
            except TimeoutError:
                code = "call_timeout"
            except Exception as exc:  # noqa: BLE001 - the answer must still carry the entries
                log.warning("%s failed: %s", fn.__name__, type(exc).__name__)
            finally:
                CALL_ENTRIES.reset(token)
            ms = int((time.monotonic() - start) * 1000)
            for e in entries:
                if e.status is None and e.blocked_reason is None:
                    e.blocked_reason, e.ms = code, e.ms or ms  # in flight when it stopped
            return answer("error", None, entries, code, secrets)

        return call

    @app.middleware("http")
    async def clients_only(request: Request, call_next: Any) -> Any:
        try:
            ip = ipaddress.ip_address((request.client.host if request.client else "") or "")
        except ValueError:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if not any(ip in net for net in state.settings.api_clients):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {".".join(str(p) for p in e["loc"][1:]) or "body": e["type"] for e in exc.errors()}
        return JSONResponse({"outcome": "error", "code": "invalid_args", "fields": fields}, 422)

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.post("/v1/search")
    @guarded
    async def search(a: SearchIn) -> JSONResponse:
        q = f"site:{a.site} {a.q}" if a.site else a.q
        params: dict[str, Any] = {"q": q, "format": "json", "pageno": 1, "safesearch": 0}
        if a.lang:
            params["language"] = a.lang
        if a.recency_days:
            d = a.recency_days
            params["time_range"] = (
                "day" if d <= 1 else "week" if d <= 7 else "month" if d <= 31 else "year"
            )
        entry = track(Entry("web.search", "GET", "searxng", kind="search", cls=a.ctx.cls))
        start = time.monotonic()
        try:
            resp = await state.internal.get(
                state.settings.searxng_url.rstrip("/") + "/search", params=params
            )
            entry.status = resp.status_code
            entry.bytes_in = len(resp.content)
            body = resp.json() if resp.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            body = None
        entry.ms = int((time.monotonic() - start) * 1000)
        if not isinstance(body, dict):
            return answer("error", None, [entry], "search_unavailable")
        results = []
        for r in (body.get("results") or [])[: a.n]:
            if not isinstance(r, dict) or not isinstance(r.get("url"), str):
                continue
            results.append(
                {
                    "title": str(r.get("title") or "")[:300],
                    "url": r["url"][:2000],
                    "snippet": str(r.get("content") or "")[:600],
                    "date": r.get("publishedDate"),
                    "engine": r.get("engine"),
                }
            )
        flags = X.injection_flags(*(f"{r['title']} {r['snippet']}" for r in results))
        return answer(
            "ok",
            {
                "results": results,
                "source": "web",
                "untrusted": True,
                "fetched_at": _now(),
                "suspected_injection": flags,
            },
            [entry],
        )

    @app.post("/v1/read")
    @guarded
    async def read(a: ReadIn) -> JSONResponse:
        if a.account is not None and a.account.is_signer:
            return _signer_refused("web.read", "GET", a.url, a.ctx.cls, a.account)
        secrets = _secrets(a)
        try:
            got = await state.fetcher.fetch(
                "GET",
                a.url,
                tool="web.read",
                cls=a.ctx.cls,
                max_bytes=min(a.ctx.max_bytes, state.settings.max_call_bytes),
                account=a.account,
                check=_get_check,
            )
        except Blocked as b:
            return _blocked(b, secrets)
        except FetchError as e:
            return answer("error", None, e.entries, "fetch_failed", secrets)
        ctype = got.content_type
        if a.mode == "pdf" or ctype == "application/pdf" or got.body[:5] == b"%PDF-":
            title, text, cut = await X.read_text("pdf", got.body, a.max_chars, secrets)
            kind = "pdf"
        elif a.mode == "html":
            text, cut = _text_of(got.body, got.headers, a.max_chars, secrets)
            title, kind = "", "html"
        elif ctype.startswith("text/html") or ctype in ("application/xhtml+xml", ""):
            head = got.body[: X.HTML_PARSE_BYTES]
            title, text, cut = await X.read_text("html", head, a.max_chars, secrets)
            cut, kind = cut or len(got.body) > len(head), "text"
        elif ctype.startswith(TEXT_TYPES):
            text, cut = _text_of(got.body, got.headers, a.max_chars, secrets)
            title, kind = "", "text"
        else:
            title, text, cut, kind = "", "", False, "binary"
        data = {
            "final_url": got.final_url,
            "status": got.status,
            "content_type": ctype,
            "kind": kind,
            "title": title,
            "text": text,
            "truncated": cut or got.truncated,
            "source": "web",
            "untrusted": True,
            "fetched_at": _now(),
            "suspected_injection": X.injection_flags(title, text),
        }
        return answer("ok", data, got.entries, None, secrets)

    @app.post("/v1/http")
    @guarded
    async def http_request(a: HttpIn) -> JSONResponse:
        if a.account is not None and a.account.is_signer:
            return _signer_refused("http.request", a.method, a.url, a.ctx.cls, a.account)
        secrets = _secrets(a)
        headers = dict(a.headers)
        content: bytes | None = None
        if a.json_body is not None:
            content = json.dumps(a.json_body, ensure_ascii=False).encode()
            headers.setdefault("Content-Type", "application/json")
        elif a.body is not None:
            content = a.body.encode()
        try:
            got = await state.fetcher.fetch(
                a.method,
                a.url,
                tool="http.request",
                cls=a.ctx.cls,
                headers=headers,
                content=content,
                max_bytes=min(a.ctx.max_bytes, state.settings.max_call_bytes),
                account=a.account,
                check=_get_check,
            )
        except Blocked as b:
            return _blocked(b, secrets)
        except FetchError as e:
            return answer("error", None, e.entries, "fetch_failed", secrets)
        ctype = got.content_type
        text, cut = "", False
        if ctype.startswith(TEXT_TYPES) or ctype.endswith("+json"):
            text, cut = _text_of(got.body, got.headers, a.max_chars, secrets)
        data = {
            "status": got.status,
            "final_url": got.final_url,
            "headers": {k: v for k, v in got.headers.items() if k in KEEP_HEADERS},
            "body": text,
            "bytes": len(got.body),
            "truncated": got.truncated or cut,
            "source": "web",
            "untrusted": True,
            "fetched_at": _now(),
            "suspected_injection": X.injection_flags(text),
        }
        return answer("ok", data, got.entries, None, secrets)

    @app.post("/v1/browse")
    @guarded
    async def browse(a: BrowseIn) -> JSONResponse:
        if a.account is not None and a.account.is_signer:
            first = next((s.url for s in a.steps if s.url), None) or "about:blank"
            return _signer_refused("web.browse", "BROWSE", first, a.ctx.cls, a.account)
        ports = a.account.ports_for if a.account else None
        for i, s in enumerate(a.steps):
            if s.url:
                try:
                    state.guard.target(s.url, extra_ports=ports)
                    if state.guard.is_hub(urlsplit(s.url).hostname or ""):
                        raise Blocked("hub_internal")
                    why = get_commitment(s.url)  # a GET that commits (7.1)
                    if why:
                        raise Blocked("needs_owner", why)
                except Blocked as b:
                    e = Entry("web.browse", "GOTO", _host(s.url), kind="browse", cls=a.ctx.cls,
                              blocked_reason=b.reason)  # fmt: skip
                    data = _needs_owner(b, step=i)
                    return answer("blocked", data, [e], b.reason)
        secrets = _secrets(a)
        key, password = state.buckets.open(
            "web.browse",
            a.ctx.cls,
            a.ctx.max_bytes,
            site=a.account.site if a.account else None,
            ports=tuple(a.account.ports) if a.account else (),
        )
        # The browser's own budget leaves room for its hard stop (time_s + 3)
        # inside this call's deadline.
        time_s = max(1.0, min(a.time_s, state.settings.browse_call_s,
                              state.settings.call_deadline_s - 4))  # fmt: skip
        payload = {
            "steps": [s.model_dump(exclude_none=True) for s in a.steps],
            "proxy": {
                "server": state.settings.browser_proxy_url,
                "username": key,
                "password": password,
            },
            "account": a.account.model_dump() if a.account else None,
            "time_s": time_s,
            "max_download_bytes": min(a.ctx.max_bytes, state.settings.max_call_bytes),
            # Every file of the call together (screenshots and downloads, 7.1).
            "max_files_bytes": min(a.ctx.max_bytes, state.settings.browse_files_bytes),
        }
        first = next((s.url for s in a.steps if s.url), None) or "about:blank"
        session = track(Entry("web.browse", "BROWSE", _host(first), kind="browse", cls=a.ctx.cls))
        start = time.monotonic()
        try:
            got = await _browser_run(state, payload, time_s + 10)
        except (httpx.HTTPError, ValueError):
            got = None
        finally:
            entries = [track(e) for e in state.buckets.drain(key)]
            session.ms = int((time.monotonic() - start) * 1000)
        entries = [session, *entries]
        if not isinstance(got, dict):
            session.status = 502
            return answer("error", None, entries, "browser_unavailable", secrets)
        if got.get("code") == "busy":
            session.status = 503
            return answer("error", None, entries, "browser_busy", secrets)
        session.status = 200
        if got.get("code") == "sign_in_failed":  # the account's own login, not the browser
            return answer("error", None, entries, "sign_in_failed", secrets)
        texts = [str(st.get("text") or "") for st in got.get("steps") or [] if isinstance(st, dict)]
        files = [f for f in got.get("files") or [] if isinstance(f, dict)]
        data = {
            "final_url": got.get("final_url"),
            "title": got.get("title"),
            "steps": got.get("steps") or [],
            "blocked": got.get("blocked"),
            "source": "web",
            "untrusted": True,
            "fetched_at": _now(),
            "suspected_injection": X.injection_flags(*scrub(texts, secrets)),
        }
        blocked = got.get("blocked")
        if isinstance(blocked, dict) and blocked.get("code") == "needs_owner":
            session.blocked_reason = "needs_owner"
            return answer("blocked", data, entries, "needs_owner", secrets, files)
        return answer("ok", data, entries, None, secrets, files)

    @app.post("/v1/connectors/call")
    @guarded
    async def connector(a: ConnectorIn) -> JSONResponse:
        return await _connector(state, a)

    @app.post("/v1/proxy/drain")
    async def drain(a: DrainIn) -> JSONResponse:
        return answer("ok", {"call_id": a.call_id}, state.buckets.drain(a.call_id))

    return app


async def _browser_run(state: State, payload: dict[str, Any], timeout: float) -> Any:  # noqa: ASYNC109
    """The browser's answer, parsed; its raw body (files in base64) is let go
    on return, not held beside the parsed copy (7.1 §2.20, measured)."""
    resp = await state.internal.post(
        state.settings.browser_url.rstrip("/") + "/v1/run", json=payload, timeout=timeout
    )
    return resp.json() if resp.status_code in (200, 503) else None


def _secrets(a: Any) -> list[str]:
    account = getattr(a, "account", None)
    return account.secrets() if isinstance(account, Account) else []


def _signer_refused(tool: str, method: str, url: str, cls: str, account: Account) -> JSONResponse:
    """A signer's account outside a connector: refused, and logged as such."""
    e = track(Entry(tool, method[:10], _host(url), cls=cls, blocked_reason="policy_denied"))
    return answer("blocked", None, [e], "policy_denied", account.secrets())


async def _connector(state: State, a: ConnectorIn) -> JSONResponse:
    """One fixed endpoint of an adapter: checked, rate-limited, signed, sent,
    and its answer reduced (connectors.py) and scrubbed of the secret."""
    secrets = _secrets(a)
    adapter = K.ADAPTERS.get(a.adapter)
    ep = adapter.endpoints.get(a.endpoint) if adapter else None
    if adapter is None or ep is None:
        return answer("blocked", None, [], "unknown_endpoint", secrets)
    bad = sorted(set(a.params) - ep.params) + sorted(set(a.local) - ep.local)
    if bad:
        return answer("error", {"fields": bad[:10]}, [], "invalid_args", secrets)
    if ep.signed:
        acct = a.account
        if acct is None or not acct.is_signer or acct.inject.signer != adapter.signer:
            return answer("blocked", None, [], "policy_denied", secrets)
        port = f":{acct.ports[0]}" if acct.ports else ""
        url = f"https://{acct.site.lower().rstrip('.')}{port}{ep.path}"
        key = acct.key
    else:
        if a.account is not None:  # a keyless endpoint never carries a key
            return answer("blocked", None, [], "policy_denied", secrets)
        url = str(getattr(state.settings, adapter.public_url)).rstrip("/") + ep.path
        key = "public"
    wait = await state.rates.of(adapter, key).take(state.settings.connector_wait_s)
    if wait > 0:
        return answer("error", {"retry_after_s": max(1, int(wait + 0.999))}, [], "rate_limited")
    headers: dict[str, str] = {"Accept": "application/json"}
    content: bytes | None = None
    params = {k: str(v) for k, v in a.params.items()}
    if ep.signed:
        assert a.account is not None and a.account.inject.signer is not None
        try:
            signed = SIGNERS[a.account.inject.signer](params, a.account.secret)
        except SignerError:
            return answer("error", None, [], "account_not_configured", secrets)
        content = urlencode(signed.form).encode()
        headers.update(signed.headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        del signed
    elif params:
        url = f"{url}?{urlencode(params)}"
    try:
        got = await state.fetcher.fetch(
            ep.method,
            url,
            tool=a.tool,
            cls="A0",
            headers=headers,
            content=content,
            max_bytes=min(a.ctx.max_bytes, CONNECTOR_BYTES, state.settings.max_call_bytes),
            account=a.account,
        )
    except Blocked as b:
        return _blocked(b, secrets)
    except FetchError as e:
        return answer("error", None, e.entries, "fetch_failed", secrets)
    if got.status != 200:
        return answer("error", {"status": got.status}, got.entries, "upstream_status", secrets)
    try:
        body = json.loads(bytes(got.body).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return answer("error", None, got.entries, "upstream_malformed", secrets)
    ok, code = K.succeeded(body)
    if not ok:
        return answer("error", {"error_code": code}, got.entries, "upstream_error", secrets)
    try:
        data = ep.reduce(body.get("data") if isinstance(body, dict) else None, dict(a.local))
    except K.Malformed:
        return answer("error", None, got.entries, "upstream_malformed", secrets)
    return answer("ok", data, got.entries, None, secrets)


def _get_check(method: str, url: str) -> str | None:
    """A GET (or HEAD) that commits (rules.get_commitment); another method's
    line is the api's (reserve: needs_owner unless the account lists it)."""
    return get_commitment(url) if method in ("GET", "HEAD") else None


def _needs_owner(b: Blocked, step: int | None = None) -> dict[str, Any] | None:
    if b.reason != "needs_owner":
        return None
    return {"blocked": {"step": step, "code": "needs_owner", "reason": b.detail or "commitment"}}


def _blocked(b: Blocked, secrets: list[str]) -> JSONResponse:
    return answer("blocked", _needs_owner(b), b.entries, b.reason, secrets)


def _text_of(
    body: bytes | bytearray, headers: dict[str, str], limit: int, secrets: list[str]
) -> tuple[str, bool]:
    """(text, cut): the body as text, scrubbed of the secrets, THEN cut to
    `limit` characters (7.1). Only what can reach the cut is decoded (no
    codec takes more than 4 bytes a character), not a 20 MB body."""
    want = (limit + margin(secrets)) * 4
    head = body[:want]
    text, cut = scrub_cut(head.decode(_charset(headers), "replace"), secrets, limit)
    return text, cut or len(body) > len(head)


def _charset(headers: dict[str, str]) -> str:
    """The declared text encoding; a codec that is not one (hex, rot13,
    base64, zlib: bytes-to-bytes) or an unknown name reads as UTF-8."""
    ctype = headers.get("content-type", "")
    for part in ctype.split(";")[1:]:
        k, _, v = part.strip().partition("=")
        if k.lower() == "charset" and v:
            try:
                info = codecs.lookup(v.strip("\"' "))
            except (LookupError, ValueError):
                continue
            if getattr(info, "_is_text_encoding", True):
                return info.name
    return "utf-8"


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:255]
    except ValueError:
        return "?"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextlib.asynccontextmanager
async def lifespan_noop(_: FastAPI) -> AsyncIterator[None]:
    yield


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
