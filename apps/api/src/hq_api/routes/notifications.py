"""Notifications, their settings and push registrations (contract §6)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from hq_api import pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain.notify import COLUMNS, LEVELS
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["notifications"])

Level = Literal["urgent", "decision", "report", "info", "learning"]


class Link(BaseModel):
    kind: str
    ref: str | None = None


class Choice(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label_fa: str = Field(min_length=1, max_length=120)


class Delivered(BaseModel):
    in_app: bool
    web_push: bool
    fcm: bool
    telegram: bool


class Notification(BaseModel):
    id: UUID
    level: Level
    company: str
    title_fa: str
    body_fa: str
    link: Link | None
    created_at: datetime
    read_at: datetime | None
    choices: list[Choice] | None
    answer: str | None
    state: str
    delivered: Delivered


class NotificationPage(BaseModel):
    items: list[Notification]
    next_cursor: str | None


class ReadAllIn(BaseModel):
    before: datetime | None = None
    level: Level | None = None


class Count(BaseModel):
    updated: int


class ReadManyIn(BaseModel):
    """⟨1.7.5⟩ several notifications read in one request (contract §25)."""

    ids: list[UUID] = Field(min_length=1, max_length=500)


class AnswerIn(BaseModel):
    choice_id: str = Field(min_length=1, max_length=40)


class LevelSettings(BaseModel):
    in_app: bool | None = None
    push: bool | None = None
    sound: bool | None = None
    muted_until: datetime | None = None


class NotificationSettings(BaseModel):
    matrix: dict[str, dict[Level, LevelSettings]]
    version: int


class NotificationSettingsIn(BaseModel):
    matrix: dict[str, dict[Level, LevelSettings]]

    @field_validator("matrix")
    @classmethod
    def _scopes(cls, v: dict[str, dict[str, LevelSettings]]) -> dict[str, dict[str, LevelSettings]]:
        for scope in v:
            if scope != "*" and not (2 <= len(scope) <= 10 and scope.isalnum() and scope.isupper()):
                raise ValueError(f"scope {scope!r} must be '*' or a company code")
        return v


class VapidKey(BaseModel):
    public_key: str


class WebPushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class WebSubscriptionIn(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=2000)
    keys: WebPushKeys
    device_name: str = Field(min_length=1, max_length=100)


class FcmTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    device_name: str = Field(min_length=1, max_length=100)


class Device(BaseModel):
    id: UUID
    device_name: str
    created_at: datetime
    revoked_at: datetime | None


def to_notification(r: dict[str, Any]) -> Notification:
    return Notification(
        id=r["id"],
        level=r["level"],
        company=r["company"],
        title_fa=r["title_fa"],
        body_fa=r["body_fa"],
        link=Link(kind=r["link_kind"], ref=r["link_ref"]) if r["link_kind"] else None,
        created_at=r["created_at"],
        read_at=r["read_at"],
        choices=[Choice(**c) for c in r["choices"]] if r["choices"] is not None else None,
        answer=r["answer"],
        state=r["state"],
        delivered=Delivered(
            in_app=r["delivered_in_app"],
            web_push=r["delivered_web_push"],
            fcm=r["delivered_fcm"],
            telegram=r["delivered_telegram"],
        ),
    )


def time_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    """Decode a (created_at, id) cursor into typed values (asyncpg binds by type)."""
    return pagination.time_id(cursor)


def if_match(request: Request) -> int:
    raw = request.headers.get("if-match")
    if raw is None:
        raise ApiError(428, "validation_failed", fields={"If-Match": "required"})
    value = raw.strip().removeprefix("W/").strip('"')
    if not value.isdigit():
        raise ApiError(422, "validation_failed", fields={"If-Match": "must be the version number"})
    return int(value)


async def company_ids_for(ctx: Ctx, codes: list[str] | None) -> list[UUID] | None:
    if not codes:
        return None
    out: list[UUID] = []
    for code in codes:
        c = await ctx.hub.companies.find(code)
        if c is None:
            raise ApiError(422, "validation_failed", fields={"company": f"unknown company {code}"})
        out.append(c.id)
    return out


@router.get("/notifications", response_model=NotificationPage, responses=responses(401, 422))
async def list_notifications(
    ctx: Ctx = Depends(owner_ctx),
    level: list[Level] | None = Query(default=None),
    company: list[str] | None = Query(default=None),
    unread: bool | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
) -> NotificationPage:
    """Notifications shown in the app (newest first). Held or queued items appear
    once they are released (Khalvat off, digest)."""
    c0, c1 = time_cursor(cursor)
    ids = await company_ids_for(ctx, company)
    async with ctx.tx() as tx:
        rows = await tx.all(
            f"""SELECT {COLUMNS} FROM notify.notifications n
                JOIN core.companies c ON c.id = n.company_id
                WHERE n.delivered_in_app
                  AND (CAST(:levels AS text[]) IS NULL OR n.level = ANY(CAST(:levels AS text[])))
                  AND (CAST(:cos AS uuid[]) IS NULL OR n.company_id = ANY(CAST(:cos AS uuid[])))
                  AND (CAST(:unread AS boolean) IS NULL
                       OR (n.read_at IS NULL) = CAST(:unread AS boolean))
                  AND (CAST(:c0 AS timestamptz) IS NULL
                       OR (n.created_at, n.id) < (CAST(:c0 AS timestamptz), CAST(:c1 AS uuid)))
                ORDER BY n.created_at DESC, n.id DESC
                LIMIT :lim""",  # noqa: S608 - constant column list, values are bound
            levels=level,
            cos=ids,
            unread=unread,
            c0=c0,
            c1=c1,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return NotificationPage(items=[to_notification(r) for r in items], next_cursor=nxt)


async def _get(ctx: Ctx, tx: Any, nid: UUID, *, lock: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = await tx.one(
        f"""SELECT {COLUMNS} FROM notify.notifications n
            JOIN core.companies c ON c.id = n.company_id
            WHERE n.id = :id {"FOR UPDATE OF n" if lock else ""}""",  # noqa: S608 - constant column list, values are bound
        id=nid,
    )
    return row


@router.post(
    "/notifications/{notification_id}/read",
    response_model=Notification,
    responses=responses(401, 404),
)
async def read_notification(notification_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Notification:
    """Marks one notification read."""
    async with ctx.tx() as tx:
        row = await _get(ctx, tx, notification_id, lock=True)
        if row["read_at"] is None:
            await tx.exec(
                "UPDATE notify.notifications SET read_at = now() WHERE id = :id", id=notification_id
            )
            await ctx.audit(
                tx,
                company_id=row["company_id"],
                action="notification.read",
                action_class="A0",
                target_kind="notification",
                target_ref=str(notification_id),
            )
            await ctx.interaction(
                tx,
                company_id=row["company_id"],
                kind="edit",
                action="notification.read",
                target_kind="notification",
                target_ref=str(notification_id),
                data={"level": row["level"]},
            )
        row = await _get(ctx, tx, notification_id)
    return to_notification(row)


@router.post("/notifications/read", response_model=Count, responses=responses(401, 422))
async def read_notifications(body: ReadManyIn, ctx: Ctx = Depends(owner_ctx)) -> Count:
    """⟨1.7.5⟩ Marks these read (ids not found or already read are skipped);
    one audit row and one interaction for the whole request."""
    holding = await ctx.hub.companies.holding()
    ids = list(dict.fromkeys(body.ids))
    async with ctx.tx() as tx:
        n = await tx.exec(
            """UPDATE notify.notifications SET read_at = now()
               WHERE read_at IS NULL AND id = ANY(CAST(:ids AS uuid[]))""",
            ids=[str(i) for i in ids],
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="notification.read_many",
            action_class="A0",
            target_kind="notifications",
            target_ref=f"{len(ids)} ids",
            summary=f"{n} marked read",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="edit",
            action="notification.read_many",
            target_kind="notifications",
            target_ref=f"{len(ids)} ids",
            data={"count": n},
        )
    return Count(updated=n)


@router.post("/notifications/read-all", response_model=Count, responses=responses(401, 422))
async def read_all_notifications(body: ReadAllIn, ctx: Ctx = Depends(owner_ctx)) -> Count:
    """Marks every notification read (optionally only before a time or of one level)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        n = await tx.exec(
            """UPDATE notify.notifications SET read_at = now()
               WHERE read_at IS NULL AND delivered_in_app
                 AND (CAST(:before AS timestamptz) IS NULL
                      OR created_at <= CAST(:before AS timestamptz))
                 AND (CAST(:level AS text) IS NULL OR level = CAST(:level AS text))""",
            before=body.before,
            level=body.level,
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="notification.read_all",
            action_class="A0",
            target_kind="notifications",
            target_ref=body.level or "all",
            summary=f"{n} marked read",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="edit",
            action="notification.read_all",
            target_kind="notifications",
            target_ref=body.level or "all",
            data={"count": n},
        )
    return Count(updated=n)


@router.post(
    "/notifications/{notification_id}/answer",
    response_model=Notification,
    responses=responses(401, 404, 409, 422),
)
async def answer_notification(
    notification_id: UUID, body: AnswerIn, ctx: Ctx = Depends(owner_ctx)
) -> Notification:
    """One-tap answer to a learning question; recorded as an owner interaction."""
    async with ctx.tx() as tx:
        row = await _get(ctx, tx, notification_id, lock=True)
        choices = {c["id"] for c in row["choices"] or []}
        if body.choice_id not in choices:
            raise ApiError(
                422, "validation_failed", fields={"choice_id": "not one of this question's choices"}
            )
        if row["answer"] is not None:
            raise ApiError(409, "validation_failed", "already answered")
        await tx.exec(
            """UPDATE notify.notifications
               SET answer = :a, answered_at = now(), read_at = COALESCE(read_at, now())
               WHERE id = :id""",
            a=body.choice_id,
            id=notification_id,
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="notification.answer",
            action_class="A0",
            target_kind="notification",
            target_ref=str(notification_id),
        )
        await ctx.interaction(
            tx,
            company_id=row["company_id"],
            kind="answer",
            action="notification.answer",
            target_kind=row["link_kind"] or "notification",
            target_ref=row["link_ref"] or str(notification_id),
            data={
                "choice_id": body.choice_id,
                "level": row["level"],
                "notification": str(notification_id),
            },
        )
        row = await _get(ctx, tx, notification_id)
    return to_notification(row)


@router.get("/notification-settings", response_model=NotificationSettings, responses=responses(401))
async def get_notification_settings(
    response: Response, ctx: Ctx = Depends(owner_ctx)
) -> NotificationSettings:
    """Per-company, per-level matrix; "*" applies to every company."""
    async with ctx.tx() as tx:
        row = await tx.one("SELECT matrix, version FROM notify.settings WHERE id = 1")
    response.headers["ETag"] = f'"{row["version"]}"'
    return NotificationSettings(matrix=row["matrix"], version=row["version"])


@router.put(
    "/notification-settings",
    response_model=NotificationSettings,
    responses=responses(401, 409, 422, 428),
)
async def put_notification_settings(
    body: NotificationSettingsIn,
    request: Request,
    response: Response,
    ctx: Ctx = Depends(owner_ctx),
) -> NotificationSettings:
    """Replaces the per-company, per-level matrix. Requires `If-Match: <version>`."""
    version = if_match(request)
    for scope in body.matrix:
        if scope != "*" and await ctx.hub.companies.find(scope) is None:
            raise ApiError(422, "validation_failed", fields={"matrix": f"unknown company {scope}"})
    matrix = {
        scope: {lvl: s.model_dump(mode="json", exclude_none=True) for lvl, s in levels.items()}
        for scope, levels in body.matrix.items()
    }
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        row = await tx.first(
            """UPDATE notify.settings SET matrix = CAST(:m AS jsonb)
               WHERE id = 1 AND version = :v RETURNING matrix, version""",
            m=json.dumps(matrix),
            v=version,
        )
        if row is None:
            raise ApiError(409, "version_conflict")
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="notification.settings",
            action_class="A1",
            target_kind="settings",
            target_ref="notification-settings",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="notification.settings",
            target_kind="settings",
            target_ref="notification-settings",
            data={"matrix": matrix},
        )
    response.headers["ETag"] = f'"{row["version"]}"'
    return NotificationSettings(matrix=row["matrix"], version=row["version"])


@router.get("/push/vapid-public-key", response_model=VapidKey, responses=responses(401, 503))
async def get_vapid_public_key(ctx: Ctx = Depends(owner_ctx)) -> VapidKey:
    """The VAPID public key for Web Push subscriptions (503 channel_not_configured without keys)."""
    if not ctx.hub.secrets.vapid_public_key:
        raise ApiError(503, "channel_not_configured", "web push has no VAPID key yet")
    return VapidKey(public_key=ctx.hub.secrets.vapid_public_key)


async def _device_audit(ctx: Ctx, tx: Any, action: str, ref: str) -> None:
    holding = await ctx.hub.companies.holding()
    await ctx.audit(
        tx,
        company_id=holding.id,
        action=action,
        action_class="A1",
        target_kind="push_device",
        target_ref=ref,
    )
    await ctx.interaction(
        tx,
        company_id=holding.id,
        kind="setting",
        action=action,
        target_kind="push_device",
        target_ref=ref,
    )


@router.post(
    "/push/web-subscriptions", response_model=Device, status_code=201, responses=responses(401, 422)
)
async def create_web_subscription(body: WebSubscriptionIn, ctx: Ctx = Depends(owner_ctx)) -> Device:
    """Register (or re-activate) this browser's push subscription."""
    async with ctx.tx() as tx:
        row = await tx.one(
            """INSERT INTO notify.web_push_subscriptions (endpoint, p256dh, auth, device_name)
               VALUES (:e, :p, :a, :n)
               ON CONFLICT (endpoint) DO UPDATE SET revoked_at = NULL, failures = 0
               RETURNING id, device_name, created_at, revoked_at""",
            e=body.endpoint,
            p=body.keys.p256dh,
            a=body.keys.auth,
            n=body.device_name,
        )
        await _device_audit(ctx, tx, "push.web_subscribe", str(row["id"]))
    return Device(**row)


@router.post(
    "/push/web-subscriptions/{subscription_id}/revoke",
    status_code=204,
    responses=responses(401, 404),
)
async def revoke_web_subscription(subscription_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """Stops pushing to a browser (revocation is a state; the row stays)."""
    async with ctx.tx() as tx:
        n = await tx.exec(
            """UPDATE notify.web_push_subscriptions SET revoked_at = COALESCE(revoked_at, now())
               WHERE id = :id""",
            id=subscription_id,
        )
        if n == 0:
            raise ApiError(404, "not_found")
        await _device_audit(ctx, tx, "push.web_revoke", str(subscription_id))
    return Response(status_code=204)


@router.post(
    "/push/fcm-tokens", response_model=Device, status_code=201, responses=responses(401, 422)
)
async def create_fcm_token(body: FcmTokenIn, ctx: Ctx = Depends(owner_ctx)) -> Device:
    """Registers this Android device for FCM push (off until FCM has credentials)."""
    async with ctx.tx() as tx:
        row = await tx.one(
            """INSERT INTO notify.fcm_tokens (token, device_name) VALUES (:t, :n)
               ON CONFLICT (token) DO UPDATE SET revoked_at = NULL, failures = 0
               RETURNING id, device_name, created_at, revoked_at""",
            t=body.token,
            n=body.device_name,
        )
        await _device_audit(ctx, tx, "push.fcm_register", str(row["id"]))
    return Device(**row)


@router.post("/push/fcm-tokens/{token_id}/revoke", status_code=204, responses=responses(401, 404))
async def revoke_fcm_token(token_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """Stops pushing to an Android device (revocation is a state; the row stays)."""
    async with ctx.tx() as tx:
        n = await tx.exec(
            "UPDATE notify.fcm_tokens SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id",
            id=token_id,
        )
        if n == 0:
            raise ApiError(404, "not_found")
        await _device_audit(ctx, tx, "push.fcm_revoke", str(token_id))
    return Response(status_code=204)


assert set(LEVELS) == {"urgent", "decision", "report", "info", "learning"}
