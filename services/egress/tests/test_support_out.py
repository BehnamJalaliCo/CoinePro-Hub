"""POST /v1/support/send (prompt 10 §4.2, §10): a support message to a
customer on Telegram or Chatwoot and the Telegram webhook, against a fake
Telegram and a fake Chatwoot (no real call: the fetcher's client is a mock
transport; the guard still checks every name and address)."""

from __future__ import annotations

import ipaddress
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.net import Fetcher
from hq_egress.proxy import Buckets

LOCAL = ipaddress.ip_network("127.0.0.1/32")
BOT = "123456789:AAH" + "x" * 32  # a bot token's shape (fake)
CW = "cw-access-" + "Q" * 20  # a Chatwoot api_access_token (fake)
HOOK = "https://hq.coinepro.com/intake/v1/telegram/TY/telegram_bot"


class Fakes:
    """Telegram by chat id (111 ok, 222 blocked, 333 not found, 444 flood,
    555 a server error that echoes the token), Chatwoot by conversation."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.host == "api.telegram.org":
            return self.telegram(request)
        return self.chatwoot(request)

    def telegram(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        if method == "sendMessage":
            chat = int(body["chat_id"])
            if chat == 222:
                return httpx.Response(403, json={"ok": False, "error_code": 403,
                                                 "description": "Forbidden: bot was blocked by the user"})  # fmt: skip
            if chat == 333:
                return httpx.Response(400, json={"ok": False, "error_code": 400,
                                                 "description": "Bad Request: chat not found"})  # fmt: skip
            if chat == 444:
                return httpx.Response(429, json={"ok": False, "error_code": 429,
                                                 "description": "Too Many Requests: retry after 17",
                                                 "parameters": {"retry_after": 17}})  # fmt: skip
            if chat == 555:
                return httpx.Response(
                    500, json={"ok": False, "description": f"oops /bot{BOT}/x {BOT}"}
                )
            return httpx.Response(200, json={"ok": True, "result": {
                "message_id": 42, "date": 1700000000, "chat": {"id": chat, "type": "private"},
                "text": body["text"]}})  # fmt: skip
        if method == "setWebhook":
            return httpx.Response(200, json={"ok": True, "result": True,
                                             "description": "Webhook was set"})  # fmt: skip
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {
                "url": HOOK, "pending_update_count": 0, "has_custom_certificate": False}})  # fmt: skip
        return httpx.Response(200, json={"ok": True, "result": {"id": 1, "is_bot": True,
                                                                "username": "coine_support_bot"}})  # fmt: skip

    def chatwoot(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("api_access_token") != CW:
            return httpx.Response(401, json={"error": "unauthorized"})
        if "/conversations/404/" in request.url.path:
            return httpx.Response(404, json={"error": "not found"})
        if "/conversations/429/" in request.url.path:
            return httpx.Response(429, headers={"Retry-After": "9"}, json={})
        return httpx.Response(200, json={"id": 99, "conversation_id": 7, "content": "x"})


@pytest.fixture
async def egress() -> AsyncIterator[tuple[httpx.AsyncClient, Fakes]]:
    table = {
        "api.telegram.org": ["149.154.167.220"],
        "chat.example.com": ["93.184.216.34"],
        "evil.example.com": ["10.0.0.5"],
    }

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such name")
        return table[host]

    guard = Guard(hub_hosts=frozenset({"hq.coinepro.com"}), resolver=resolve)
    fakes = Fakes()
    fetcher = Fetcher(guard, 5)
    await fetcher.http.aclose()
    fetcher.http = httpx.AsyncClient(transport=httpx.MockTransport(fakes), follow_redirects=False)
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({"hq.coinepro.com"}))
    state = State(settings, guard, Buckets(), fetcher=fetcher)
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, fakes
    await fetcher.aclose()


def _tg(method: str, payload: dict[str, Any], token: str = BOT) -> dict[str, Any]:
    return {"channel": "telegram", "method": method, "token": token, "payload": payload}


def _cw(conv: int = 7, **over: Any) -> dict[str, Any]:
    return {"channel": "chatwoot", "method": "message", "token": CW,
            "base_url": "https://chat.example.com", "path_args": {"account_id": 1,
            "conversation_id": conv}, "payload": {"content": "سلام، پشتیبانی Coine"},
            **over}  # fmt: skip


def _no_secret(text: str) -> None:
    assert BOT not in text and CW not in text and BOT.split(":")[1] not in text


async def test_a_plain_message_goes_out_and_the_token_never_comes_back(
    egress: Any, caplog: pytest.LogCaptureFixture
) -> None:
    c, fakes = egress
    caplog.set_level(logging.DEBUG)
    r = await c.post("/v1/support/send", json=_tg("sendMessage", {
        "chat_id": 111, "text": "سلام! پاسخ شما ...", "business_connection_id": "bc-1",
        "link_preview_options": {"is_disabled": True}}))  # fmt: skip
    out = r.json()
    assert r.status_code == 200 and out["outcome"] == "ok" and out["code"] is None
    assert out["data"] == {"message_id": 42, "chat_id": 111, "date": 1700000000,
                           "business_connection_id": None}  # fmt: skip
    [sent] = fakes.seen
    assert sent.url.path == f"/bot{BOT}/sendMessage" and sent.method == "POST"
    assert json.loads(sent.content)["business_connection_id"] == "bc-1"
    [e] = out["entries"]
    assert (e["tool"], e["method"], e["host"], e["status"], e["class"]) == (
        "support.send", "POST", "api.telegram.org", 200, "A2",
    )  # fmt: skip
    _no_secret(r.text)
    _no_secret(caplog.text)  # httpx's own request line is filtered
    # A hostile answer echoing the token is scrubbed too.
    r = await c.post("/v1/support/send", json=_tg("sendMessage", {"chat_id": 555, "text": "x"}))
    out = r.json()
    assert (out["outcome"], out["code"]) == ("error", "send_error")
    _no_secret(r.text)
    _no_secret(caplog.text)


@pytest.mark.parametrize(
    ("chat", "code", "extra"),
    [(222, "no_channel", {}), (333, "no_channel", {}), (444, "send_limit", {"retry_after": 17})],
)
async def test_telegrams_own_refusals_are_recorded_never_forced(
    egress: Any, chat: int, code: str, extra: dict[str, Any]
) -> None:
    c, fakes = egress
    out = (
        await c.post("/v1/support/send", json=_tg("sendMessage", {"chat_id": chat, "text": "x"}))
    ).json()
    assert (out["outcome"], out["code"]) == ("error", code)
    assert extra.items() <= out["data"].items()
    assert len(fakes.seen) == 1  # tried once, not retried


@pytest.mark.parametrize(
    ("method", "payload", "token", "code"),
    [
        ("sendPhoto", {"chat_id": 111}, BOT, "method_not_allowed"),
        ("forwardMessage", {"chat_id": 111}, BOT, "method_not_allowed"),
        ("sendMessage", {"chat_id": 111, "text": "x", "reply_markup": {}}, BOT, "payload_not_allowed"),
        ("sendMessage", {"chat_id": 111, "text": "x", "parse_mode": "HTML"}, BOT, "parse_mode_not_allowed"),
        ("sendMessage", {"chat_id": 111, "text": "x", "parse_mode": "MarkdownV2"}, BOT, "parse_mode_not_allowed"),
        ("sendMessage", {"chat_id": 111}, BOT, "payload_incomplete"),
        ("sendMessage", {"chat_id": "@somechannel", "text": "x"}, BOT, "payload_not_allowed"),
        ("sendMessage", {"chat_id": 111, "text": "x" * 4097}, BOT, "text_not_allowed"),
        ("sendMessage", {"chat_id": 111, "text": "x"}, "123:../../etc", "bad_token"),
        ("setWebhook", {"url": "https://evil.example.com/hook", "secret_token": "s"}, BOT, "webhook_url_not_allowed"),
        ("setWebhook", {"url": "http://hq.coinepro.com/intake/v1/telegram/TY/telegram_bot",
                        "secret_token": "s"}, BOT, "webhook_url_not_allowed"),
        ("setWebhook", {"url": "https://hq.coinepro.com/internal/v1/x", "secret_token": "s"}, BOT,
         "webhook_url_not_allowed"),
        ("setWebhook", {"url": HOOK + "?x=1", "secret_token": "s"}, BOT, "webhook_url_not_allowed"),
        ("setWebhook", {"url": HOOK, "secret_token": "s", "ip_address": "1.2.3.4"}, BOT, "payload_not_allowed"),
        ("setWebhook", {"url": HOOK, "secret_token": "bad token!"}, BOT, "payload_not_allowed"),
        ("setWebhook", {"url": HOOK, "secret_token": "s", "allowed_updates": ["callback_query"]}, BOT,
         "payload_not_allowed"),
    ],
)  # fmt: skip
async def test_anything_outside_the_allow_lists_is_blocked_before_it_leaves(
    egress: Any, method: str, payload: dict[str, Any], token: str, code: str
) -> None:
    c, fakes = egress
    r = await c.post("/v1/support/send", json=_tg(method, payload, token))
    out = r.json()
    assert (out["outcome"], out["code"]) == ("blocked", code), out
    assert fakes.seen == []
    [e] = out["entries"]
    assert e["blocked_reason"] == code and e["status"] is None
    _no_secret(r.text)


async def test_the_webhook_is_set_once_on_the_hubs_intake_route(egress: Any) -> None:
    c, fakes = egress
    out = (await c.post("/v1/support/send", json=_tg("setWebhook", {
        "url": HOOK, "secret_token": "s3cr3t-Token_1", "allowed_updates": ["message", "business_message"],
        "drop_pending_updates": True}))).json()  # fmt: skip
    assert (out["outcome"], out["data"]) == ("ok", {"result": True})
    assert json.loads(fakes.seen[0].content)["url"] == HOOK
    info = (await c.post("/v1/support/send", json=_tg("getWebhookInfo", {}))).json()
    assert info["outcome"] == "ok" and info["data"] == {"url": HOOK, "pending_update_count": 0}
    me = (await c.post("/v1/support/send", json=_tg("getMe", {}))).json()
    assert me["data"] == {"id": 1, "is_bot": True, "username": "coine_support_bot"}
    gone = (
        await c.post("/v1/support/send", json=_tg("deleteWebhook", {"drop_pending_updates": False}))
    ).json()
    assert gone["outcome"] == "ok"


async def test_a_chatwoot_reply_goes_to_its_conversation(egress: Any) -> None:
    c, fakes = egress
    r = await c.post("/v1/support/send", json=_cw())
    out = r.json()
    assert out["outcome"] == "ok" and out["data"] == {"message_id": 99, "conversation_id": 7}
    [sent] = fakes.seen
    assert sent.url.path == "/api/v1/accounts/1/conversations/7/messages"
    assert json.loads(sent.content) == {"content": "سلام، پشتیبانی Coine", "message_type": "outgoing",
                                        "private": False}  # fmt: skip
    _no_secret(r.text)
    nf = (await c.post("/v1/support/send", json=_cw(404))).json()
    assert (nf["outcome"], nf["code"]) == ("error", "no_channel")
    lim = (await c.post("/v1/support/send", json=_cw(429))).json()
    assert (lim["code"], lim["data"]["retry_after"]) == ("send_limit", 9)


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"base_url": "http://chat.example.com"}, "https_required"),
        ({"base_url": "https://evil.example.com"}, "private_address"),
        ({"base_url": "https://10.0.0.9"}, "private_address"),
        ({"base_url": "https://hq.coinepro.com"}, "hub_internal"),
        ({"base_url": "https://chat.example.com/api"}, "bad_url"),
        ({"base_url": None}, "base_url_required"),
        ({"method": "conversations"}, "method_not_allowed"),
        ({"path_args": {"account_id": 1}}, "path_args_required"),
        ({"payload": {"content": "x", "private": True}}, "payload_not_allowed"),
        ({"payload": {"content": "x", "message_type": "template"}}, "payload_not_allowed"),
        ({"payload": {"content": "x", "content_attributes": {}}}, "payload_not_allowed"),
        ({"token": "bad token"}, "bad_token"),
    ],
)
async def test_chatwoot_outside_its_rules_is_blocked(
    egress: Any, over: dict[str, Any], code: str
) -> None:
    c, fakes = egress
    r = await c.post("/v1/support/send", json=_cw(**over))
    out = r.json()
    assert (out["outcome"], out["code"]) == ("blocked", code), out
    assert fakes.seen == []
    _no_secret(r.text)


async def test_only_the_api_network_may_call_it(egress: Any) -> None:
    c, _ = egress
    state = c._transport.app.state.egress  # type: ignore[attr-defined]
    outside = httpx.ASGITransport(app=build_app(state), client=("172.30.9.5", 1))
    async with httpx.AsyncClient(transport=outside, base_url="http://egress") as o:
        r = await o.post("/v1/support/send", json=_tg("getMe", {}))
    assert r.status_code == 403
    bad = await c.post("/v1/support/send", json={"channel": "sms", "method": "x", "token": "t"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_args"
    _no_secret(bad.text)
