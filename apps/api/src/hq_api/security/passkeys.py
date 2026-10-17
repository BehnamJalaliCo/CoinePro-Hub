"""WebAuthn (passkeys) for the owner, on py_webauthn (contract §2).

User verification is always required. Challenges are generated here, stored
server-side (auth.challenges / auth.step_ups) and found again from the
challenge echoed inside clientDataJSON, so a response can be bound to exactly
one stored, unexpired, unused challenge (no replay).
"""

from __future__ import annotations

import json
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.authentication.verify_authentication_response import VerifiedAuthentication
from webauthn.helpers import base64url_to_bytes, generate_challenge, parse_client_data_json
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from hq_api.config import Settings

ALGORITHMS = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.EDDSA,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
]
TIMEOUT_MS = 300_000  # matches the 5-minute challenge lifetime


class PasskeyError(ValueError):
    """The response does not verify (any reason; the detail is never shown)."""


def new_challenge() -> bytes:
    return generate_challenge()


def registration_options(
    s: Settings, *, user_id: bytes, challenge: bytes, exclude: list[bytes]
) -> dict[str, Any]:
    options = generate_registration_options(
        rp_id=s.rp_id,
        rp_name=s.rp_name,
        user_id=user_id,
        user_name="owner",
        user_display_name="CoinePro HQ owner",
        challenge=challenge,
        timeout=TIMEOUT_MS,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in exclude],
        supported_pub_key_algs=ALGORITHMS,
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


def authentication_options(s: Settings, *, challenge: bytes, allow: list[bytes]) -> dict[str, Any]:
    options = generate_authentication_options(
        rp_id=s.rp_id,
        challenge=challenge,
        timeout=TIMEOUT_MS,
        allow_credentials=[PublicKeyCredentialDescriptor(id=c) for c in allow],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


def challenge_of(credential: dict[str, Any]) -> bytes:
    """The challenge the authenticator signed (from clientDataJSON)."""
    try:
        raw = base64url_to_bytes(str(credential["response"]["clientDataJSON"]))
        return bytes(parse_client_data_json(raw).challenge)
    except (KeyError, TypeError, ValueError, WebAuthnException) as exc:
        raise PasskeyError("malformed clientDataJSON") from exc


def credential_id_of(credential: dict[str, Any]) -> bytes:
    try:
        return base64url_to_bytes(str(credential["rawId"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PasskeyError("malformed rawId") from exc


def verify_registration(
    s: Settings, credential: dict[str, Any], *, challenge: bytes
) -> VerifiedRegistration:
    try:
        return verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=s.rp_id,
            expected_origin=s.public_origin,
            require_user_presence=True,
            require_user_verification=True,
            supported_pub_key_algs=ALGORITHMS,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        raise PasskeyError(type(exc).__name__) from exc


def verify_assertion(
    s: Settings,
    credential: dict[str, Any],
    *,
    challenge: bytes,
    public_key: bytes,
    sign_count: int,
) -> VerifiedAuthentication:
    try:
        return verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=s.rp_id,
            expected_origin=s.public_origin,
            credential_public_key=public_key,
            credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        raise PasskeyError(type(exc).__name__) from exc


def transports_of(credential: dict[str, Any]) -> list[str]:
    raw = credential.get("response", {}).get("transports") or []
    return [str(t)[:20] for t in raw if isinstance(t, str)][:8]
