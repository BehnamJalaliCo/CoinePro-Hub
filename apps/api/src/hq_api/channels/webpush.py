"""Web Push with VAPID (RFC 8030/8291/8292) via pywebpush's encryption and
py_vapid's signing; the HTTP call goes through httpx. Keys live in OpenBao
(kv/hq-api/webpush); without them, or without a public origin, it is off."""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid
from pywebpush import WebPusher

from hq_api.errors import ApiError

if TYPE_CHECKING:
    from hq_api.channels import PushMessage
    from hq_api.hub import Hub

log = logging.getLogger("hq_api.channels.webpush")
TTL_S = 12 * 3600
GONE = (404, 410)


def generate_vapid_keys() -> tuple[str, str]:
    """A fresh P-256 VAPID key pair: (private key PEM, public key base64url)."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return pem, base64.urlsafe_b64encode(raw).decode().rstrip("=")


class WebPushChannel:
    def __init__(self, hub: Hub, http: httpx.AsyncClient) -> None:
        self._hub = hub
        self._http = http

    @property
    def subject(self) -> str:
        return self._hub.secrets.vapid_subject or self._hub.settings.public_origin

    @property
    def configured(self) -> bool:
        return bool(self._hub.secrets.web_push_ready and self.subject)

    def _vapid_headers(self, endpoint: str) -> dict[str, str]:
        parts = urlsplit(endpoint)
        vapid = Vapid.from_pem(self._hub.secrets.vapid_private_pem.encode())
        claims: dict[str, Any] = {"sub": self.subject, "aud": f"{parts.scheme}://{parts.netloc}"}
        headers: dict[str, str] = vapid.sign(claims)
        return headers

    async def send_one(self, sub: dict[str, Any], payload: bytes, urgent: bool) -> int:
        info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
        prepared = WebPusher(info)._prepare_send_data(payload, {}, ttl=TTL_S)
        headers = {str(k): str(v) for k, v in prepared["headers"].items()}
        headers.update(self._vapid_headers(sub["endpoint"]))
        headers["Urgency"] = "high" if urgent else "normal"
        resp = await self._http.post(sub["endpoint"], content=prepared["data"], headers=headers)
        return resp.status_code

    async def send(self, msg: PushMessage) -> bool:
        if not self.configured:
            raise ApiError(503, "channel_not_configured", "web push")
        payload = json.dumps(msg.data(), ensure_ascii=False).encode()
        async with self._hub.db.raw() as tx:
            subs = await tx.all(
                """SELECT id, endpoint, p256dh, auth FROM notify.web_push_subscriptions
                   WHERE revoked_at IS NULL ORDER BY created_at"""
            )
        delivered = False
        for sub in subs:
            try:
                status = await self.send_one(sub, payload, msg.level == "urgent")
            except Exception as exc:  # noqa: BLE001 - network or a malformed stored key: count it
                log.warning("web push failed", extra={"error": type(exc).__name__})
                status = 0
            async with self._hub.db.raw() as tx:
                if 200 <= status < 300:
                    delivered = True
                    await tx.exec(
                        """UPDATE notify.web_push_subscriptions
                           SET failures = 0, last_success_at = now() WHERE id = :id""",
                        id=sub["id"],
                    )
                elif status in GONE:
                    await tx.exec(
                        """UPDATE notify.web_push_subscriptions SET revoked_at = now()
                           WHERE id = :id""",
                        id=sub["id"],
                    )
                else:
                    await tx.exec(
                        """UPDATE notify.web_push_subscriptions SET failures = failures + 1
                           WHERE id = :id""",
                        id=sub["id"],
                    )
        return delivered
