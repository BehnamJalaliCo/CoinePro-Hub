"""Firebase Cloud Messaging (HTTP v1) for the Android app. OAuth2 with the
service account (a JWT signed by its private key, exchanged for an access
token). Off until kv/hq-api/channels/fcm holds a service account."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hq_api.errors import ApiError

if TYPE_CHECKING:
    from hq_api.channels import PushMessage
    from hq_api.hub import Hub

log = logging.getLogger("hq_api.channels.fcm")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def signed_assertion(sa: dict[str, Any], now: float | None = None) -> str:
    t = int(time.time() if now is None else now)
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "scope": SCOPE,
        "aud": sa.get("token_uri") or TOKEN_URI,
        "iat": t,
        "exp": t + 3600,
    }
    signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    key = serialization.load_pem_private_key(str(sa["private_key"]).encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("service account key is not RSA")
    sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing}.{_b64(sig)}"


class FcmChannel:
    def __init__(self, hub: Hub, http: httpx.AsyncClient) -> None:
        self._hub = hub
        self._http = http
        self._token = ""
        self._token_exp = 0.0

    @property
    def configured(self) -> bool:
        sa = self._hub.secrets.fcm_service_account or {}
        return bool(
            self._hub.secrets.fcm_ready and sa.get("client_email") and sa.get("private_key")
        )

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        sa = self._hub.secrets.fcm_service_account or {}
        resp = await self._http.post(
            sa.get("token_uri") or TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_assertion(sa),
            },
        )
        if resp.status_code != 200:
            raise ApiError(
                503, "channel_not_configured", f"fcm auth failed (HTTP {resp.status_code})"
            )
        body = resp.json()
        self._token = str(body["access_token"])
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    async def send(self, msg: PushMessage) -> bool:
        if not self.configured:
            raise ApiError(503, "channel_not_configured", "fcm")
        sa = self._hub.secrets.fcm_service_account or {}
        async with self._hub.db.raw() as tx:
            tokens = await tx.all(
                """SELECT id, token FROM notify.fcm_tokens
                   WHERE revoked_at IS NULL ORDER BY created_at"""
            )
        if not tokens:
            return False
        access = await self._access_token()
        delivered = False
        url = SEND_URL.format(project=sa["project_id"])
        for t in tokens:
            message = {
                "message": {
                    "token": t["token"],
                    "notification": {"title": msg.title},
                    "data": msg.data(),
                    "android": {"priority": "high" if msg.level == "urgent" else "normal"},
                }
            }
            try:
                resp = await self._http.post(
                    url, json=message, headers={"Authorization": f"Bearer {access}"}
                )
                status = resp.status_code
            except httpx.HTTPError as exc:
                log.warning("fcm send failed", extra={"error": type(exc).__name__})
                status = 0
            async with self._hub.db.raw() as tx:
                if status == 200:
                    delivered = True
                    await tx.exec(
                        "UPDATE notify.fcm_tokens SET failures = 0 WHERE id = :id", id=t["id"]
                    )
                elif status in (400, 404):  # UNREGISTERED / INVALID_ARGUMENT token
                    await tx.exec(
                        "UPDATE notify.fcm_tokens SET revoked_at = now() WHERE id = :id", id=t["id"]
                    )
                else:
                    await tx.exec(
                        "UPDATE notify.fcm_tokens SET failures = failures + 1 WHERE id = :id",
                        id=t["id"],
                    )
        return delivered
