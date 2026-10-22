"""The support desk's outbound calls (prompt 10 §4.2, §10; contract §19.3,
§19.8): one message to a customer on Telegram or Chatwoot, and the Telegram
webhook set once. Code calls it (the worker, on hq-egress-api), never an
agent: every word in it already passed the outbound guard in the api.

    POST /v1/support/send
      {channel: "telegram" | "chatwoot", method, token, base_url?, path_args?, payload}
      -> {outcome: ok | blocked | error, code, data, entries}

telegram  method sendMessage | setWebhook | deleteWebhook | getWebhookInfo | getMe;
          https://api.telegram.org/bot<token>/<method>. The payload's keys are an
          allow-list per method: sendMessage is plain text only (no parse_mode,
          no markup, no buttons); setWebhook's url is the hub's own
          https://<host>/intake/v1/telegram/... and nothing else (no ip_address,
          no certificate).
chatwoot  method message: POST {base_url}/api/v1/accounts/{account_id}/
          conversations/{conversation_id}/messages with the api_access_token
          header; payload {content, message_type: "outgoing", private: false}.

Answers: `ok` with the few fields the caller needs (a message id, the webhook
state); `blocked` for anything outside the allow-lists or the guard (a private
or hub address, a non-https Chatwoot, a bad token shape); `error` with a
stable code: `no_channel` when the channel itself refuses to deliver
(Telegram's 403 "bot was blocked", "chat not found", a Business-connection
refusal; Chatwoot's 404): the caller records it and never forces it;
`send_limit` (429, `data.retry_after` in seconds); `send_error` otherwise.

The token arrives with the call (read from OpenBao by the worker) and is held
for that call only: it goes on the request, never into an entry (host,
status, sizes and time only), an error, a log line (httpx's request line is
filtered here too) or the answer (scrubbed in every form).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_egress.accounts import scrub
from hq_egress.guard import Blocked
from hq_egress.net import CALL_ENTRIES, Entry, FetchError, track
from hq_egress.proxy import entries_json

log = logging.getLogger("hq_egress.support")
router = APIRouter()

TOOL = "support.send"
CLS = "A2"  # a message to a customer: an external effect (decided by code in the api)
TELEGRAM_API = "https://api.telegram.org"
MAX_BODY = 1024 * 1024
TEXT_MAX = 4096  # Telegram's own limit for one message
CHATWOOT_TEXT_MAX = 10_000
BOT_TOKEN = re.compile(r"^[0-9]{5,16}:[A-Za-z0-9_-]{30,64}$")
CHATWOOT_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
CHAT_ID = re.compile(r"^-?[0-9]{1,20}$")
SECRET_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
WEBHOOK_PATH = re.compile(r"^/intake/v1/telegram/[A-Z][A-Z0-9]{1,9}/[a-z_]{3,30}$")
UPDATES = frozenset(
    {
        "message",
        "edited_message",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    }
)
# The keys each Telegram method may carry (anything else is refused).
TELEGRAM_KEYS: dict[str, frozenset[str]] = {
    "sendMessage": frozenset(
        {
            "chat_id",
            "text",
            "business_connection_id",
            "reply_to_message_id",
            "disable_web_page_preview",
            "link_preview_options",
            "disable_notification",
            "parse_mode",  # only absent or null: plain text
        }
    ),
    "setWebhook": frozenset(
        {"url", "secret_token", "allowed_updates", "drop_pending_updates", "max_connections"}
    ),
    "deleteWebhook": frozenset({"drop_pending_updates"}),
    "getWebhookInfo": frozenset(),
    "getMe": frozenset(),
}
TELEGRAM_REQUIRED: dict[str, frozenset[str]] = {
    "sendMessage": frozenset({"chat_id", "text"}),
    "setWebhook": frozenset({"url", "secret_token"}),
}
# Telegram's own refusals that mean "this channel cannot deliver it": recorded
# no_channel by the caller, never retried or forced (contract §19.5).
NO_CHANNEL = (
    "bot was blocked",
    "chat not found",
    "user is deactivated",
    "bot can't initiate conversation",
    "bot can't send messages to bots",
    "business connection",
    "business_connection",
    "business_peer",
    "peer_id_invalid",
    "have no rights to send",
    "not enough rights",
)
# The bot token in a Telegram URL path, wherever a log line could show it.
_BOT_PATH = re.compile(r"/bot[0-9]{5,16}:[A-Za-z0-9_-]+")


class _NoTokenInLogs(logging.Filter):
    """httpx writes each request's URL (Telegram's carries the bot token) at
    INFO; the service runs httpx at WARNING, and this filter makes sure no
    level ever shows the token."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except (TypeError, ValueError):
            return True
        clean = _BOT_PATH.sub("/bot[secret]", msg)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


for _name in ("httpx", "httpcore", "hq_egress"):
    logging.getLogger(_name).addFilter(_NoTokenInLogs())


class PathArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int | None = Field(default=None, ge=1, le=2**31 - 1)
    conversation_id: int | None = Field(default=None, ge=1, le=2**31 - 1)


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["telegram", "chatwoot"]
    method: str = Field(min_length=1, max_length=40)
    token: str = Field(min_length=1, max_length=512, repr=False)
    base_url: str | None = Field(default=None, max_length=500)
    path_args: PathArgs = Field(default_factory=PathArgs)
    payload: dict[str, Any] = Field(default_factory=dict)


class Refused(Exception):
    """The call is outside the allow-lists: `code` is the stable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _answer(
    outcome: str,
    data: Any,
    entries: list[Entry],
    code: str | None,
    token: str,
    status: int = 200,
) -> JSONResponse:
    body = {
        "outcome": outcome,
        "code": code,
        "data": scrub(data, [token]),
        "entries": entries_json(entries),
    }
    return JSONResponse(body, status_code=status)


# --------------------------------------------------------------- telegram --
def _telegram_payload(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = TELEGRAM_KEYS.get(method)
    if allowed is None:
        raise Refused("method_not_allowed")
    extra = set(payload) - allowed
    if extra:
        raise Refused("payload_not_allowed")
    if not TELEGRAM_REQUIRED.get(method, frozenset()) <= set(payload):
        raise Refused("payload_incomplete")
    out = dict(payload)
    if method == "sendMessage":
        if out.get("parse_mode") is not None:
            raise Refused("parse_mode_not_allowed")  # plain text only: no markup
        out.pop("parse_mode", None)
        chat = out["chat_id"]
        if isinstance(chat, bool) or not CHAT_ID.match(str(chat)):
            raise Refused("payload_not_allowed")
        text = out["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
            raise Refused("text_not_allowed")
        bc = out.get("business_connection_id")
        if bc is not None and (not isinstance(bc, str) or not 1 <= len(bc) <= 128):
            raise Refused("payload_not_allowed")
        reply = out.get("reply_to_message_id")
        if reply is not None and (isinstance(reply, bool) or not isinstance(reply, int)):
            raise Refused("payload_not_allowed")
        lpo = out.get("link_preview_options")
        if lpo is not None and (not isinstance(lpo, dict) or set(lpo) - {"is_disabled"}):
            raise Refused("payload_not_allowed")
        for flag in ("disable_web_page_preview", "disable_notification"):
            if flag in out and not isinstance(out[flag], bool):
                raise Refused("payload_not_allowed")
    elif method == "setWebhook":
        _check_webhook_url(out["url"])
        if not isinstance(out["secret_token"], str) or not SECRET_TOKEN.match(out["secret_token"]):
            raise Refused("payload_not_allowed")
        updates = out.get("allowed_updates")
        if updates is not None and (
            not isinstance(updates, list)
            or not all(isinstance(u, str) and u in UPDATES for u in updates)
        ):
            raise Refused("payload_not_allowed")
        mc = out.get("max_connections")
        if mc is not None and (
            isinstance(mc, bool) or not isinstance(mc, int) or not 1 <= mc <= 100
        ):
            raise Refused("payload_not_allowed")
        if "drop_pending_updates" in out and not isinstance(out["drop_pending_updates"], bool):
            raise Refused("payload_not_allowed")
    elif method == "deleteWebhook":
        if "drop_pending_updates" in out and not isinstance(out["drop_pending_updates"], bool):
            raise Refused("payload_not_allowed")
    return out


def _check_webhook_url(url: Any) -> None:
    """The hub's own intake route over https, nothing else (contract §19.8)."""
    if not isinstance(url, str) or len(url) > 300:
        raise Refused("webhook_url_not_allowed")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise Refused("webhook_url_not_allowed") from exc
    if (
        parts.scheme != "https"
        or not parts.hostname
        or "." not in parts.hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.query
        or parts.fragment
        or not WEBHOOK_PATH.match(parts.path)
    ):
        raise Refused("webhook_url_not_allowed")


def _telegram_result(method: str, result: Any) -> Any:
    keep: tuple[str, ...]
    if method == "sendMessage" and isinstance(result, dict):
        raw = result.get("chat")
        chat: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return {
            "message_id": result.get("message_id"),
            "chat_id": chat.get("id"),
            "date": result.get("date"),
            "business_connection_id": result.get("business_connection_id"),
        }
    if method == "getWebhookInfo" and isinstance(result, dict):
        keep = ("url", "pending_update_count", "last_error_date", "last_error_message",
                "max_connections", "allowed_updates")  # fmt: skip
        return {k: result.get(k) for k in keep if k in result}
    if method == "getMe" and isinstance(result, dict):
        keep = ("id", "username", "is_bot", "can_connect_to_business")
        return {k: result.get(k) for k in keep if k in result}
    return {"result": result if isinstance(result, bool) else bool(result)}


def _telegram_outcome(
    method: str, status: int, body: Any
) -> tuple[str, str | None, dict[str, Any] | Any]:
    doc = body if isinstance(body, dict) else {}
    description = str(doc.get("description") or "")[:200]
    if status == 200 and doc.get("ok") is True:
        return "ok", None, _telegram_result(method, doc.get("result"))
    raw = doc.get("parameters")
    params: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if status == 429:
        retry = params.get("retry_after")
        retry_s = retry if isinstance(retry, int) and not isinstance(retry, bool) else 30
        return "error", "send_limit", {"status": 429, "retry_after": max(1, retry_s)}
    low = description.lower()
    if status == 403 or (status == 400 and any(m in low for m in NO_CHANNEL)):
        return "error", "no_channel", {"status": status, "description": description}
    return "error", "send_error", {"status": status, "description": description}


# --------------------------------------------------------------- chatwoot --
def _chatwoot_target(a: SendIn) -> str:
    if a.method != "message":
        raise Refused("method_not_allowed")
    if not CHATWOOT_TOKEN.match(a.token):
        raise Refused("bad_token")
    if not a.base_url:
        raise Refused("base_url_required")
    try:
        parts = urlsplit(a.base_url)
        parts.port  # noqa: B018 - raises on a bad port
    except ValueError as exc:
        raise Refused("bad_url") from exc
    if parts.scheme != "https":
        raise Refused("https_required")
    if (
        not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise Refused("bad_url")
    acc, conv = a.path_args.account_id, a.path_args.conversation_id
    if acc is None or conv is None:
        raise Refused("path_args_required")
    return f"{a.base_url.rstrip('/')}/api/v1/accounts/{acc}/conversations/{conv}/messages"


def _chatwoot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) - {"content", "message_type", "private"}:
        raise Refused("payload_not_allowed")
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip() or len(content) > CHATWOOT_TEXT_MAX:
        raise Refused("text_not_allowed")
    if payload.get("message_type", "outgoing") != "outgoing":
        raise Refused("payload_not_allowed")
    if payload.get("private", False) is not False:
        raise Refused("payload_not_allowed")
    return {"content": content, "message_type": "outgoing", "private": False}


def _chatwoot_outcome(
    status: int, body: Any, headers: dict[str, str]
) -> tuple[str, str | None, dict[str, Any]]:
    doc = body if isinstance(body, dict) else {}
    if 200 <= status < 300:
        return (
            "ok",
            None,
            {"message_id": doc.get("id"), "conversation_id": doc.get("conversation_id")},
        )
    if status == 429:
        try:
            retry = int(headers.get("retry-after", "30"))
        except ValueError:
            retry = 30
        return "error", "send_limit", {"status": 429, "retry_after": max(1, retry)}
    if status == 404:
        return "error", "no_channel", {"status": 404}
    return "error", "send_error", {"status": status}


# ------------------------------------------------------------------ route --
def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:255]
    except ValueError:
        return "?"


@router.post("/v1/support/send")
async def send(a: SendIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    entries: list[Entry] = []
    ctx_token = CALL_ENTRIES.set(entries)
    secret = a.token
    try:
        async with asyncio.timeout(state.settings.call_deadline_s):
            return await _send(state, a, entries)
    except TimeoutError:
        code = "call_timeout"
    except Exception as exc:  # noqa: BLE001 - the answer must still carry the entries
        log.warning("support.send failed: %s", type(exc).__name__)
        code = "send_error"
    finally:
        CALL_ENTRIES.reset(ctx_token)
    for e in entries:
        if e.status is None and e.blocked_reason is None:
            e.blocked_reason = code
    return _answer("error", None, entries, code, secret)


async def _send(state: Any, a: SendIn, entries: list[Entry]) -> JSONResponse:
    secret = a.token
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    host = _host(TELEGRAM_API) if a.channel == "telegram" else _host(a.base_url or "")
    try:
        if a.channel == "telegram":
            if not BOT_TOKEN.match(a.token):
                raise Refused("bad_token")
            if a.base_url is not None or a.path_args.account_id or a.path_args.conversation_id:
                raise Refused("payload_not_allowed")
            body = _telegram_payload(a.method, a.payload)
            url = f"{TELEGRAM_API}/bot{a.token}/{a.method}"
        else:
            url = _chatwoot_target(a)
            body = _chatwoot_payload(a.payload)
            headers["api_access_token"] = a.token
            if state.guard.is_hub(host):
                raise Refused("hub_internal")  # Chatwoot never runs on the hub (§10)
        # The guard first, by name and every address (a private or hub address
        # is refused before anything leaves; the connection checks it again).
        target = state.guard.target(url)
        await state.guard.addresses(target.host, target.port)
    except Refused as r:
        track(Entry(TOOL, "POST", host, blocked_reason=r.code, cls=CLS))
        return _answer("blocked", None, entries, r.code, secret)
    except Blocked as b:
        track(Entry(TOOL, "POST", host, blocked_reason=b.reason, cls=CLS))
        return _answer("blocked", None, entries, b.reason, secret)
    content = json.dumps(body, ensure_ascii=False).encode()
    start = time.monotonic()
    try:
        got = await state.fetcher.fetch(
            "POST",
            url,
            tool=TOOL,
            cls=CLS,
            headers=headers,
            content=content,
            max_bytes=MAX_BODY,
        )
    except Blocked as b:
        return _answer("blocked", None, entries, b.reason, secret)
    except FetchError:
        if entries:
            entries[-1].ms = entries[-1].ms or int((time.monotonic() - start) * 1000)
        return _answer("error", None, entries, "send_error", secret)
    try:
        parsed: Any = json.loads(bytes(got.body).decode("utf-8", "replace") or "null")
    except ValueError:
        parsed = None
    if a.channel == "telegram":
        outcome, code, data = _telegram_outcome(a.method, got.status, parsed)
    else:
        outcome, code, data = _chatwoot_outcome(got.status, parsed, got.headers)
    return _answer(outcome, data, entries, code, secret)
