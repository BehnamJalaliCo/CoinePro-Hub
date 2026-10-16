"""A software WebAuthn authenticator for tests (ES256, attestation "none").

Produces exactly what a browser / Credential Manager would send, with knobs
to break it: drop user verification, sign for another origin or RP, etc.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class SoftAuthenticator:
    rp_id: str = "hq.test"
    origin: str = "https://hq.test"
    credential_id: bytes = field(default_factory=lambda: os.urandom(32))
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    sign_count: int = 0
    user_handle: bytes = b""

    def _cose_public_key(self) -> bytes:
        nums = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}
        )

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge,
                "origin": origin or self.origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def _flags(self, uv: bool, extra: int = 0) -> int:
        return FLAG_UP | (FLAG_UV if uv else 0) | extra

    def register(
        self,
        options: dict[str, Any],
        *,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
    ) -> dict[str, Any]:
        """navigator.credentials.create() for the given creation options."""
        self.user_handle = unb64url(options["user"]["id"])
        cdj = self._client_data("webauthn.create", options["challenge"], origin)
        attested = (
            b"\x00" * 16  # AAGUID
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_public_key()
        )
        auth_data = (
            hashlib.sha256((rp_id or self.rp_id).encode()).digest()
            + bytes([self._flags(uv, FLAG_AT)])
            + struct.pack(">I", self.sign_count)
            + attested
        )
        att_obj = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(cdj),
                "attestationObject": b64url(att_obj),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def sign(
        self,
        options: dict[str, Any],
        *,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
        challenge: str | None = None,
        bump: bool = True,
    ) -> dict[str, Any]:
        """navigator.credentials.get() for the given request options."""
        if bump:
            self.sign_count += 1
        cdj = self._client_data("webauthn.get", challenge or options["challenge"], origin)
        auth_data = (
            hashlib.sha256((rp_id or self.rp_id).encode()).digest()
            + bytes([self._flags(uv)])
            + struct.pack(">I", self.sign_count)
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(cdj),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self.user_handle),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
