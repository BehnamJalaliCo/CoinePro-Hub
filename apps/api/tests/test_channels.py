"""Delivery channels: Web Push (VAPID + aes128gcm), FCM HTTP v1, Telegram.

No real network: every channel gets an httpx.MockTransport. Payloads must
carry only title/level/link, never a body or a secret.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from hq_api.channels import Channels, PushMessage, generate_vapid_keys
from hq_api.channels.fcm import TOKEN_URI, signed_assertion
from hq_api.channels.telegram import render
from hq_api.errors import ApiError
from hq_api.hub import Hub

PUSH_HOST = "https://push.example.test"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class Browser:
    """A fake browser push subscription that can decrypt what it receives."""

    endpoint: str
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    auth: bytes = field(default_factory=lambda: os.urandom(16))

    @property
    def p256dh(self) -> str:
        return _b64(
            self.key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        )

    def decrypt(self, body: bytes) -> dict[str, Any]:
        plain = http_ece.decrypt(
            body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
        )
        data: dict[str, Any] = json.loads(plain)
        return data


@dataclass
class Capture:
    requests: list[httpx.Request] = field(default_factory=list)
    status: dict[str, int] = field(default_factory=dict)  # url prefix -> forced status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for prefix, code in self.status.items():
            if url.startswith(prefix):
                return httpx.Response(code)
        if url.startswith(TOKEN_URI):
            return httpx.Response(200, json={"access_token": "fcm-access", "expires_in": 3600})
        return httpx.Response(201 if url.startswith(PUSH_HOST) else 200, json={})

    def to(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).startswith(prefix)]


def service_account() -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return {
        "project_id": "hq-test",
        "client_email": "push@hq-test.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": TOKEN_URI,
    }


@contextlib.asynccontextmanager
async def push_channels(
    hub: Hub, *, web: bool = True, fcm: bool = False, telegram: bool = False
) -> AsyncIterator[tuple[Capture, Browser | None]]:
    """Configure channels against a capture transport; restore everything after."""
    cap = Capture()
    sec = hub.secrets
    saved = (
        sec.vapid_private_pem,
        sec.vapid_public_key,
        sec.vapid_subject,
        sec.fcm_service_account,
        sec.telegram_bot_token,
        sec.telegram_chat_id,
    )
    saved_channels = hub.channels
    browser: Browser | None = None
    sub_id = None
    fcm_id = None
    if web:
        sec.vapid_private_pem, sec.vapid_public_key = generate_vapid_keys()
        sec.vapid_subject = "mailto:owner@hq.test"
        browser = Browser(endpoint=f"{PUSH_HOST}/sub/{os.urandom(6).hex()}")
        async with hub.db.raw() as tx:
            sub_id = await tx.scalar(
                """INSERT INTO notify.web_push_subscriptions (endpoint, p256dh, auth, device_name)
                   VALUES (:e, :p, :a, 'pytest browser') RETURNING id""",
                e=browser.endpoint,
                p=browser.p256dh,
                a=_b64(browser.auth),
            )
    if fcm:
        sec.fcm_service_account = service_account()
        async with hub.db.raw() as tx:
            fcm_id = await tx.scalar(
                """INSERT INTO notify.fcm_tokens (token, device_name) VALUES (:t, 'pytest phone')
                   RETURNING id""",
                t="fcm-device-token-" + os.urandom(8).hex(),
            )
    if telegram:
        sec.telegram_bot_token, sec.telegram_chat_id = "123456:test-bot-token", "42"
    hub.channels = Channels(hub, transport=httpx.MockTransport(cap.handler))
    try:
        yield cap, browser
    finally:
        await hub.channels.aclose()
        hub.channels = saved_channels
        (
            sec.vapid_private_pem,
            sec.vapid_public_key,
            sec.vapid_subject,
            sec.fcm_service_account,
            sec.telegram_bot_token,
            sec.telegram_chat_id,
        ) = saved
        async with hub.db.raw() as tx:
            if sub_id is not None:
                await tx.exec(
                    "UPDATE notify.web_push_subscriptions SET revoked_at = now() WHERE id = :id",
                    id=sub_id,
                )
            if fcm_id is not None:
                await tx.exec(
                    "UPDATE notify.fcm_tokens SET revoked_at = now() WHERE id = :id", id=fcm_id
                )


MSG = PushMessage(
    title="خرابی سرور",
    level="urgent",
    company="TY",
    link_kind="work",
    link_ref="W-000001",
    sound=True,
)


def test_vapid_keys_and_push_payload() -> None:
    pem, pub = generate_vapid_keys()
    assert pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert len(_unb64(pub)) == 65 and _unb64(pub)[0] == 4
    data = MSG.data()
    assert set(data) == {"title", "level", "count", "company", "link_kind", "link_ref", "sound"}
    assert "body" not in json.dumps(data)


async def test_channels_are_off_without_credentials(hub: Hub) -> None:
    ch = Channels(hub, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    try:
        assert ch.status() == {"in_app": True, "web_push": False, "fcm": False, "telegram": False}
        assert await ch.push(MSG) == {"web_push": False, "fcm": False, "telegram": False}
        for channel in (ch.web_push, ch.fcm, ch.telegram):
            with pytest.raises(ApiError) as info:
                await channel.send(MSG)
            assert info.value.code == "channel_not_configured"
    finally:
        await ch.aclose()


async def test_web_push_is_vapid_signed_and_encrypted(hub: Hub) -> None:
    async with push_channels(hub) as (cap, browser):
        assert browser is not None
        assert hub.channels.status()["web_push"] is True
        result = await hub.channels.push(MSG)
        assert result["web_push"] is True
        (req,) = cap.to(browser.endpoint)
        assert req.headers["authorization"].startswith("vapid t=")
        assert req.headers["content-encoding"] == "aes128gcm"
        assert req.headers["urgency"] == "high"
        payload = browser.decrypt(req.content)
        assert payload["title"] == "خرابی سرور" and payload["level"] == "urgent"
        assert payload["link_ref"] == "W-000001"
        async with hub.db.raw() as tx:
            row = await tx.one(
                "SELECT failures, last_success_at FROM notify.web_push_subscriptions WHERE endpoint = :e",
                e=browser.endpoint,
            )
        assert row["failures"] == 0 and row["last_success_at"] is not None


async def test_web_push_counts_failures_and_drops_gone_subscriptions(hub: Hub) -> None:
    async with push_channels(hub) as (cap, browser):
        assert browser is not None
        cap.status[browser.endpoint] = 500
        assert (await hub.channels.push(MSG))["web_push"] is False
        cap.status[browser.endpoint] = 410
        assert (await hub.channels.push(MSG))["web_push"] is False
        async with hub.db.raw() as tx:
            row = await tx.one(
                "SELECT failures, revoked_at FROM notify.web_push_subscriptions WHERE endpoint = :e",
                e=browser.endpoint,
            )
        assert row["failures"] == 1 and row["revoked_at"] is not None


async def test_fcm_http_v1_with_service_account(hub: Hub) -> None:
    async with push_channels(hub, web=False, fcm=True) as (cap, _):
        assert hub.channels.status()["fcm"] is True
        assert (await hub.channels.push(MSG))["fcm"] is True
        (token_req,) = cap.to(TOKEN_URI)
        form = parse_qs(token_req.content.decode())
        assertion = form["assertion"][0]
        head, claims, sig = assertion.split(".")
        sa = hub.secrets.fcm_service_account
        assert sa is not None
        key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
        assert isinstance(key, rsa.RSAPrivateKey)
        key.public_key().verify(
            _unb64(sig), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        assert json.loads(_unb64(claims))["scope"].endswith("firebase.messaging")
        sends = cap.to("https://fcm.googleapis.com/v1/projects/hq-test/messages:send")
        assert sends and sends[-1].headers["authorization"] == "Bearer fcm-access"
        message = json.loads(sends[-1].content)["message"]
        assert message["notification"] == {"title": "خرابی سرور"}
        assert message["android"]["priority"] == "high"
        # the access token is cached; an unregistered device is revoked
        cap.status["https://fcm.googleapis.com/"] = 404
        assert (await hub.channels.push(MSG))["fcm"] is False
        assert len(cap.to(TOKEN_URI)) == 1
        async with hub.db.raw() as tx:
            left = await tx.scalar(
                "SELECT count(*) FROM notify.fcm_tokens WHERE device_name = 'pytest phone' AND revoked_at IS NULL"
            )
        assert left == 0


async def test_fcm_auth_failure_and_no_devices(hub: Hub) -> None:
    async with push_channels(hub, web=False, fcm=True) as (cap, _):
        cap.status[TOKEN_URI] = 401
        assert (await hub.channels.push(MSG))["fcm"] is False
    sa = service_account()
    assert signed_assertion(sa, now=1_800_000_000).count(".") == 2


async def test_telegram_is_backup_only(hub: Hub) -> None:
    text = render(MSG)
    assert "خرابی سرور" in text and "[TY]" in text and "تأیید از تلگرام ممکن نیست" in text
    for forbidden in ("approve", "reject", "/api/", "http"):
        assert forbidden not in text.lower()
    async with push_channels(hub, web=False, telegram=True) as (cap, _):
        assert (await hub.channels.push(MSG))["telegram"] is True
        (req,) = cap.to("https://api.telegram.org/")
        body = json.loads(req.content)
        assert body["chat_id"] == "42" and body["disable_notification"] is False
        assert "reply_markup" not in body  # no buttons, ever
        cap.status["https://api.telegram.org/"] = 502
        assert (await hub.channels.push(MSG))["telegram"] is False


async def test_one_failing_channel_does_not_block_the_others(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with push_channels(hub, web=True, telegram=True) as (_, _browser):

        async def boom(msg: PushMessage) -> bool:
            raise RuntimeError("down")

        monkeypatch.setattr(hub.channels.web_push, "send", boom)
        result = await hub.channels.push(MSG)
        assert result == {"web_push": False, "fcm": False, "telegram": True}


def transport_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("unreachable", request=request)


async def test_network_errors_are_contained(hub: Hub) -> None:
    async with push_channels(hub, web=True, fcm=True, telegram=True) as (_, _browser):
        await hub.channels.aclose()
        hub.channels = Channels(hub, transport=httpx.MockTransport(_fcm_token_then_error()))
        result = await hub.channels.push(MSG)
        assert result == {"web_push": False, "fcm": False, "telegram": False}


def _fcm_token_then_error() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URI):
            return httpx.Response(200, json={"access_token": "x", "expires_in": 3600})
        return transport_error(request)

    return handler
