"""Identity and sessions (contract §2): passkeys, step-up, devices.

No password exists anywhere. The first passkey is registered with a one-time
enrolment token (`make owner-enroll`, the owner's own terminal); later ones
from a signed-in session plus a step-up. Without a domain and HTTPS, every
passkey and step-up endpoint answers 503 origin_not_configured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.principal import OWNER_CODE, Principal
from hq_api.security import deps, passkeys, sessions, stepup
from hq_common.tokens import bearer, digest

router = APIRouter(tags=["auth"])

OWNER = Principal(kind="owner", code=OWNER_CODE, role="owner")
ACTION_PATTERN = r"^[a-z_]+\.[a-z_]+$"


# ------------------------------------------------------------------ models --
class PublicKeyCredential(BaseModel):
    """A WebAuthn credential as the browser / Credential Manager returns it (JSON)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=1024)
    rawId: str = Field(min_length=1, max_length=1024)
    type: Literal["public-key"]
    response: dict[str, Any]
    clientExtensionResults: dict[str, Any] = Field(default_factory=dict)
    authenticatorAttachment: str | None = None


class RegisterOptionsIn(BaseModel):
    enrolment_token: str | None = Field(default=None, min_length=16, max_length=200)


class RegisterVerifyIn(BaseModel):
    credential: PublicKeyCredential
    device_name: str = Field(min_length=1, max_length=100)


class LoginVerifyIn(BaseModel):
    credential: PublicKeyCredential
    device_name: str | None = Field(default=None, min_length=1, max_length=100)


class StepUpOptionsIn(BaseModel):
    action: str = Field(pattern=ACTION_PATTERN, max_length=60)
    target: str = Field(min_length=1, max_length=200)


class StepUpVerifyIn(BaseModel):
    credential: PublicKeyCredential


class Device(BaseModel):
    id: UUID
    name: str
    kind: Literal["passkey", "session"]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None = None
    current: bool = False


class DeviceOut(BaseModel):
    device: Device


class DeviceList(BaseModel):
    items: list[Device]
    next_cursor: str | None = None


class SessionOut(BaseModel):
    token: str | None = Field(
        default=None, description="Android only (Bearer). Web clients get the hq_session cookie."
    )
    client: Literal["web", "android", "other"]
    device: Device
    expires_at: datetime
    absolute_expires_at: datetime


class LoginOut(BaseModel):
    session: SessionOut


class StepUpOut(BaseModel):
    step_up_token: str
    expires_at: datetime


class PrincipalOut(BaseModel):
    kind: str
    code: str


class SessionInfo(BaseModel):
    principal: PrincipalOut
    device: Device
    expires_at: datetime


# ------------------------------------------------------------ dependencies --
def login_enabled(hub: Hub = Depends(get_hub)) -> None:
    if not hub.settings.login_configured:
        raise ApiError(503, "origin_not_configured")


def web_csrf(request: Request, hub: Hub = Depends(get_hub)) -> None:
    """Unauthenticated auth POSTs from the web carry X-HQ-Client: web and our Origin."""
    if request.headers.get("x-hq-client") == "web" or request.cookies.get(sessions.COOKIE):
        deps.check_csrf(hub, request)


PUBLIC_AUTH = [Depends(login_enabled), Depends(deps.auth_rate_limit), Depends(web_csrf)]
SIGNED_IN_AUTH = [Depends(login_enabled), Depends(deps.auth_rate_limit)]


async def _optional_owner(request: Request, hub: Hub) -> Principal | None:
    if not (bearer(request.headers.get("authorization")) or request.cookies.get(sessions.COOKIE)):
        return None
    return await deps.owner(request, hub)


def _client(request: Request) -> Literal["web", "android"]:
    return "web" if request.headers.get("x-hq-client") == "web" else "android"


async def _holding_id(hub: Hub) -> UUID:
    return (await hub.companies.holding()).id


async def _security_event(
    ctx: Ctx,
    tx: Tx,
    *,
    action: str,
    action_class: str,
    target_kind: str,
    target_ref: str,
    step_up: bool = False,
) -> None:
    holding = await _holding_id(ctx.hub)
    await ctx.audit(
        tx,
        company_id=holding,
        action=action,
        action_class=action_class,
        target_kind=target_kind,
        target_ref=target_ref,
        summary=action,
        step_up=step_up,
    )
    await ctx.interaction(
        tx,
        company_id=holding,
        kind="security",
        action=action,
        target_kind=target_kind,
        target_ref=target_ref,
    )


async def _active_credential_ids(tx: Tx) -> list[bytes]:
    rows = await tx.all(
        "SELECT credential_id FROM auth.passkeys WHERE revoked_at IS NULL ORDER BY created_at"
    )
    return [bytes(r["credential_id"]) for r in rows]


async def _assert(hub: Hub, tx: Tx, credential: dict[str, Any], challenge: bytes) -> dict[str, Any]:
    """Verify an assertion against a stored, non-revoked passkey; update its counter."""
    cred_id = passkeys.credential_id_of(credential)
    hub.limiter.check(f"auth-cred:{cred_id.hex()[:64]}", hub.settings.auth_rate_per_ip)
    pk = await tx.first(
        """SELECT id, public_key, sign_count, name, created_at, last_used_at
           FROM auth.passkeys WHERE credential_id = :cid AND revoked_at IS NULL FOR UPDATE""",
        cid=cred_id,
    )
    if pk is None:
        raise passkeys.PasskeyError("unknown or revoked credential")
    verified = passkeys.verify_assertion(
        hub.settings,
        credential,
        challenge=challenge,
        public_key=bytes(pk["public_key"]),
        sign_count=int(pk["sign_count"]),
    )
    await tx.exec(
        """UPDATE auth.passkeys SET sign_count = :n, last_used_at = now(),
               backup_eligible = backup_eligible OR :be
           WHERE id = :id""",
        n=verified.new_sign_count,
        be=verified.credential_backed_up,
        id=pk["id"],
    )
    return pk


def _passkey_device(row: dict[str, Any]) -> Device:
    return Device(
        id=row["id"],
        name=row["name"],
        kind="passkey",
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row.get("revoked_at"),
    )


def _session_device(row: dict[str, Any], current: UUID | None = None) -> Device:
    return Device(
        id=row["id"],
        name=row["device_name"],
        kind="session",
        created_at=row["created_at"],
        last_used_at=row.get("last_used_at"),
        revoked_at=row.get("revoked_at"),
        current=row["id"] == current,
    )


# ------------------------------------------------------------ registration --
@router.post(
    "/auth/passkey/register/options",
    dependencies=PUBLIC_AUTH,
    response_model=dict[str, Any],
    responses=responses(401, 403, 422, 429, 503),
)
async def passkey_register_options(
    body: RegisterOptionsIn, request: Request, hub: Hub = Depends(get_hub)
) -> dict[str, Any]:
    """WebAuthn creation options. Needs a valid enrolment token (first device,
    recovery) or a signed-in session with a step-up for `passkey.register`/`self`."""
    who = await _optional_owner(request, hub)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        enrolment_id: UUID | None = None
        session_id: UUID | None = None
        if body.enrolment_token:
            row = await tx.first(
                """SELECT id FROM auth.enrolment_tokens
                   WHERE token_sha256 = :h AND used_at IS NULL AND expires_at > now()""",
                h=digest(body.enrolment_token),
            )
            if row is None:
                raise ApiError(401, "unauthenticated", "enrolment token invalid or expired")
            enrolment_id = row["id"]
        elif who is not None:
            await stepup.consume(tx, request, who, "passkey.register", "self")
            session_id = who.session_id
        else:
            raise ApiError(401, "unauthenticated")
        challenge = passkeys.new_challenge()
        await tx.exec(
            """INSERT INTO auth.challenges (purpose, challenge, session_id, enrolment_token_id,
                   expires_at)
               VALUES ('register', :c, :s, :e, now() + make_interval(secs => :ttl))""",
            c=challenge,
            s=session_id,
            e=enrolment_id,
            ttl=hub.settings.challenge_ttl_s,
        )
        user_id = bytes(await tx.scalar("SELECT webauthn_user_id FROM owner.settings WHERE id = 1"))
        return passkeys.registration_options(
            hub.settings,
            user_id=user_id,
            challenge=challenge,
            exclude=await _active_credential_ids(tx),
        )


@router.post(
    "/auth/passkey/register/verify",
    dependencies=PUBLIC_AUTH,
    response_model=DeviceOut,
    status_code=201,
    responses=responses(401, 403, 409, 422, 429, 503),
)
async def passkey_register_verify(
    body: RegisterVerifyIn, request: Request, hub: Hub = Depends(get_hub)
) -> DeviceOut:
    """Verify the attestation and store the new passkey (public key only)."""
    credential = body.credential.model_dump()
    who = await _optional_owner(request, hub)
    ctx = Ctx(hub=hub, who=who or OWNER, request=request)
    try:
        challenge = passkeys.challenge_of(credential)
    except passkeys.PasskeyError as exc:
        raise ApiError(422, "validation_failed", "registration response does not verify") from exc
    async with ctx.tx() as tx:
        ch = await tx.first(
            """SELECT id, session_id, enrolment_token_id FROM auth.challenges
               WHERE challenge = :c AND purpose = 'register' AND used_at IS NULL
                 AND expires_at > now()
               FOR UPDATE""",
            c=challenge,
        )
        if ch is None:
            raise ApiError(401, "unauthenticated", "challenge unknown, used or expired")
        if ch["session_id"] is not None and (who is None or who.session_id != ch["session_id"]):
            raise ApiError(401, "unauthenticated")
        if ch["enrolment_token_id"] is not None:
            burned = await tx.exec(
                """UPDATE auth.enrolment_tokens SET used_at = now()
                   WHERE id = :id AND used_at IS NULL AND expires_at > now()""",
                id=ch["enrolment_token_id"],
            )
            if burned != 1:
                raise ApiError(401, "unauthenticated", "enrolment token invalid or expired")
        try:
            verified = passkeys.verify_registration(hub.settings, credential, challenge=challenge)
        except passkeys.PasskeyError as exc:
            raise ApiError(
                422, "validation_failed", "registration response does not verify"
            ) from exc
        await tx.exec("UPDATE auth.challenges SET used_at = now() WHERE id = :id", id=ch["id"])
        row = await tx.one(
            """INSERT INTO auth.passkeys (credential_id, public_key, sign_count, transports, aaguid,
                   backup_eligible, name)
               VALUES (:cid, :pub, :n, :tr, :aaguid, :be, :name)
               RETURNING id, name, created_at, last_used_at, revoked_at""",
            cid=verified.credential_id,
            pub=verified.credential_public_key,
            n=verified.sign_count,
            tr=passkeys.transports_of(credential),
            aaguid=verified.aaguid,
            be=verified.credential_backed_up,
            name=body.device_name,
        )
        await _security_event(
            ctx,
            tx,
            action="auth.passkey_register",
            action_class="A4",
            target_kind="passkey",
            target_ref=str(row["id"]),
        )
    return DeviceOut(device=_passkey_device(row))


# ------------------------------------------------------------------- login --
@router.post(
    "/auth/passkey/login/options",
    dependencies=PUBLIC_AUTH,
    response_model=dict[str, Any],
    responses=responses(403, 429, 503),
)
async def passkey_login_options(hub: Hub = Depends(get_hub)) -> dict[str, Any]:
    """WebAuthn request options for signing in (user verification required)."""
    challenge = passkeys.new_challenge()
    async with hub.db.raw() as tx:
        await tx.exec(
            """INSERT INTO auth.challenges (purpose, challenge, expires_at)
               VALUES ('login', :c, now() + make_interval(secs => :ttl))""",
            c=challenge,
            ttl=hub.settings.challenge_ttl_s,
        )
        allow = await _active_credential_ids(tx)
    return passkeys.authentication_options(hub.settings, challenge=challenge, allow=allow)


@router.post(
    "/auth/passkey/login/verify",
    dependencies=PUBLIC_AUTH,
    response_model=LoginOut,
    responses=responses(401, 403, 422, 429, 503),
)
async def passkey_login_verify(
    body: LoginVerifyIn, request: Request, response: Response, hub: Hub = Depends(get_hub)
) -> LoginOut:
    """Verify the assertion and open a session: a cookie on the web, a Bearer
    token in the body on Android."""
    credential = body.credential.model_dump()
    ctx = Ctx(hub=hub, who=OWNER, request=request)
    client = _client(request)
    try:
        challenge = passkeys.challenge_of(credential)
    except passkeys.PasskeyError as exc:
        raise ApiError(401, "unauthenticated") from exc
    async with ctx.tx() as tx:
        ch = await tx.first(
            """SELECT id FROM auth.challenges
               WHERE challenge = :c AND purpose = 'login' AND used_at IS NULL AND expires_at > now()
               FOR UPDATE""",
            c=challenge,
        )
        if ch is None:
            raise ApiError(401, "unauthenticated", "challenge unknown, used or expired")
        try:
            pk = await _assert(hub, tx, credential, challenge)
        except passkeys.PasskeyError as exc:
            raise ApiError(401, "unauthenticated") from exc
        await tx.exec("UPDATE auth.challenges SET used_at = now() WHERE id = :id", id=ch["id"])
        token, srow = await sessions.create(
            tx,
            hub.settings,
            passkey_id=pk["id"],
            client=client,
            device_name=body.device_name or pk["name"],
            ip_hash=deps.ip_hash(request),
        )
        await _security_event(
            ctx,
            tx,
            action="auth.login",
            action_class="A2",
            target_kind="session",
            target_ref=str(srow["id"]),
        )
    if client == "web":
        response.set_cookie(
            sessions.COOKIE,
            token,
            max_age=hub.settings.session_absolute_days * 86400,
            path="/api",
            secure=True,
            httponly=True,
            samesite="strict",
        )
    return LoginOut(
        session=SessionOut(
            token=None if client == "web" else token,
            client=client,
            device=_session_device(srow, srow["id"]),
            expires_at=srow["expires_at"],
            absolute_expires_at=srow["absolute_expires_at"],
        )
    )


# ----------------------------------------------------------------- step-up --
@router.post(
    "/auth/step-up/options",
    dependencies=SIGNED_IN_AUTH,
    response_model=dict[str, Any],
    responses=responses(401, 403, 422, 429, 503),
)
async def step_up_options(body: StepUpOptionsIn, ctx: Ctx = Depends(owner_ctx)) -> dict[str, Any]:
    """Request options for a fresh passkey assertion bound to one action and target."""
    challenge = passkeys.new_challenge()
    async with ctx.hub.db.raw() as tx:
        await tx.exec(
            """INSERT INTO auth.step_ups (session_id, action, target, challenge,
                   challenge_expires_at)
               VALUES (:s, :a, :t, :c, now() + make_interval(secs => :ttl))""",
            s=ctx.who.session_id,
            a=body.action,
            t=body.target,
            c=challenge,
            ttl=ctx.hub.settings.challenge_ttl_s,
        )
        allow = await _active_credential_ids(tx)
    return passkeys.authentication_options(ctx.hub.settings, challenge=challenge, allow=allow)


@router.post(
    "/auth/step-up/verify",
    dependencies=SIGNED_IN_AUTH,
    response_model=StepUpOut,
    responses=responses(401, 403, 422, 429, 503),
)
async def step_up_verify(body: StepUpVerifyIn, ctx: Ctx = Depends(owner_ctx)) -> StepUpOut:
    """Verify the assertion -> a single-use step-up token (120 s) for the action/target
    chosen at options time. Send it as `X-Step-Up`."""
    credential = body.credential.model_dump()
    try:
        challenge = passkeys.challenge_of(credential)
    except passkeys.PasskeyError as exc:
        raise ApiError(403, "step_up_invalid") from exc
    token = sessions.new_token()
    async with ctx.tx() as tx:
        su = await tx.first(
            """SELECT id, action, target FROM auth.step_ups
               WHERE challenge = :c AND session_id = :s AND verified_at IS NULL
                 AND challenge_expires_at > now()
               FOR UPDATE""",
            c=challenge,
            s=ctx.who.session_id,
        )
        if su is None:
            raise ApiError(403, "step_up_invalid", "challenge unknown, used or expired")
        try:
            await _assert(ctx.hub, tx, credential, challenge)
        except passkeys.PasskeyError as exc:
            raise ApiError(403, "step_up_invalid") from exc
        row = await tx.one(
            """UPDATE auth.step_ups SET token_sha256 = :h, verified_at = now(),
                   expires_at = now() + make_interval(secs => :ttl)
               WHERE id = :id RETURNING expires_at""",
            h=digest(token),
            ttl=ctx.hub.settings.step_up_ttl_s,
            id=su["id"],
        )
        await _security_event(
            ctx,
            tx,
            action="auth.step_up",
            action_class="A2",
            target_kind="step_up",
            target_ref=f"{su['action']}:{su['target']}"[:200],
        )
    return StepUpOut(step_up_token=token, expires_at=row["expires_at"])


# ---------------------------------------------------------------- sessions --
@router.get("/auth/session", response_model=SessionInfo, responses=responses(401))
async def get_session(ctx: Ctx = Depends(owner_ctx)) -> SessionInfo:
    """Who is signed in, on which device, until when."""
    async with ctx.hub.db.raw() as tx:
        row = await tx.one(
            """SELECT id, device_name, created_at, last_used_at, revoked_at, expires_at
               FROM auth.sessions WHERE id = :id""",
            id=ctx.who.session_id,
        )
    return SessionInfo(
        principal=PrincipalOut(kind=ctx.who.kind, code=ctx.who.code),
        device=_session_device(row, ctx.who.session_id),
        expires_at=row["expires_at"],
    )


@router.post(
    "/auth/logout", status_code=204, response_class=Response, responses=responses(401, 403)
)
async def logout(ctx: Ctx = Depends(owner_ctx)) -> Response:
    """End this session (the row stays, revoked)."""
    assert ctx.who.session_id is not None
    async with ctx.tx() as tx:
        await sessions.revoke(tx, ctx.who.session_id)
        await _security_event(
            ctx,
            tx,
            action="auth.logout",
            action_class="A2",
            target_kind="session",
            target_ref=str(ctx.who.session_id),
        )
    out = Response(status_code=204)
    out.delete_cookie(sessions.COOKIE, path="/api", secure=True, httponly=True, samesite="strict")
    return out


@router.get("/auth/devices", response_model=DeviceList, responses=responses(401))
async def list_devices(ctx: Ctx = Depends(owner_ctx)) -> DeviceList:
    """Every passkey and every session that has not reached its absolute expiry."""
    async with ctx.hub.db.raw() as tx:
        keys = await tx.all(
            """SELECT id, name, created_at, last_used_at, revoked_at
               FROM auth.passkeys ORDER BY created_at"""
        )
        live = await tx.all(
            """SELECT id, device_name, created_at, last_used_at, revoked_at
               FROM auth.sessions WHERE absolute_expires_at > now() ORDER BY created_at"""
        )
    items = [_passkey_device(k) for k in keys] + [
        _session_device(s, ctx.who.session_id) for s in live
    ]
    return DeviceList(items=items)


@router.post(
    "/auth/devices/{device_id}/revoke",
    status_code=204,
    response_class=Response,
    responses=responses(401, 403, 404),
)
async def revoke_device(
    device_id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Response:
    """🔏 Revoke a passkey (its sessions stop working too) or a session.
    Step-up: action `device.revoke`, target = the device id."""
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "device.revoke", str(device_id))
        kind = "passkey"
        found = await tx.exec(
            "UPDATE auth.passkeys SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id",
            id=device_id,
        )
        if not found:
            kind = "session"
            found = await tx.exec(
                "UPDATE auth.sessions SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id",
                id=device_id,
            )
        if not found:
            raise ApiError(404, "not_found")
        await _security_event(
            ctx,
            tx,
            action="auth.device_revoke",
            action_class="A4",
            target_kind=kind,
            target_ref=str(device_id),
            step_up=True,
        )
    return Response(status_code=204)
