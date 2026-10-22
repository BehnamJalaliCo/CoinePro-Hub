"""Intake from outside (prompt 10 §9, contract §19.8).

Owner (/api/v1, router):
  GET  /intake/sources        configured? last event, events and refusals in 24 h
  POST /intake/sources        🔏 intake.source (the body's SHA-256): {company, kind, channel?,
                              allowed_ips, kinds}; a source moves its support channel from
                              not_configured to shadow (never live: only a go-live card)
Public (/intake/v1, webhook_router): the only public routes prompt 10 adds,
served by Caddy (body <= 1 MB, Telegram's ranges for /telegram; /internal is
never routed). Every refusal answers with no detail and writes one row of
intake.rejections only (counts): nothing else is stored.
  POST /telegram/{company}/{channel}   X-Telegram-Bot-Api-Secret-Token must equal the
                                       channel's webhook secret (kv/support/telegram/<CO>/<channel>);
                                       Telegram's published ranges only; update_id is the nonce
  POST /chatwoot/{company}             X-Chatwoot-Signature: sha256=HMAC(secret, "<ts>.<body>"),
                                       X-Chatwoot-Timestamp within ±INTAKE_MAX_SKEW_S
  POST /product/{company}              X-HQ-Signature / X-HQ-Timestamp likewise;
                                       {events: [{id, kind, at, subject, data}]}, each id once
Secrets: `make intake-secret COMPANY=… SOURCE=chatwoot|product` and `make
telegram-bot-token COMPANY=… CHANNEL=…` (the owner's terminal; never the API).
A customer's message goes to domain.support.store_inbound (masked first) and
then to the worker's SupportInbound; a product's own events (signup,
referral_failed ...) are stored masked (the UID becomes its pseudonym) and
handed to the handler registered for their kind (APPLIERS), if any.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import support as S
from hq_api.errors import ApiError, problem_response, responses
from hq_api.hub import Hub, get_hub
from hq_api.schemas import CODE, Model
from hq_api.security import deps, stepup
from hq_common import customer_mask, pseudonym

router = APIRouter(tags=["intake"])
webhook_router = APIRouter(tags=["intake"])
E = responses(401, 403, 404, 409, 413, 422, 429)
# Telegram's published webhook ranges (core.telegram.org/bots/webhooks); Caddy
# checks them too, the api again (defence in depth).
TELEGRAM_RANGES = (ipaddress.ip_network("149.154.160.0/20"), ipaddress.ip_network("91.108.4.0/22"))
PRODUCT_KINDS = (
    "signup", "uid_submitted", "referral_verified", "referral_failed", "vip_activated",
    "support_message",
)  # fmt: skip
SourceKind = Literal["telegram", "chatwoot", "product"]
ChannelKind = Literal["telegram_business", "telegram_bot", "chatwoot", "product_bot"]
MAX_EVENTS = 100
# Product events other parts of prompt 10 act on (referral rescue, the
# funnel): kind -> handler(tx, hub, company_id, event_row). Without one the
# event stays `accepted` for them.
Applier = Callable[[Tx, Hub, UUID, dict[str, Any]], Awaitable[str | None]]
APPLIERS: dict[str, Applier] = {}


class IntakeSourceIn(Model):
    company: str = Field(pattern=CODE)
    kind: SourceKind
    channel: ChannelKind | None = None
    allowed_ips: list[str] = Field(default_factory=list, max_length=50)
    kinds: list[Literal[
        "signup", "uid_submitted", "referral_verified", "referral_failed", "vip_activated",
        "support_message",
    ]] = Field(default_factory=list, max_length=6)  # fmt: skip


class IntakeSource(BaseModel):
    company: str
    kind: SourceKind
    channel: str | None
    configured: bool
    enabled: bool
    allowed_ips: list[str]
    kinds: list[str]
    last_event_at: datetime | None
    events_24h: int
    rejected_24h: int
    version: int


# ----------------------------------------------------------------- secrets --
async def _kv(hub: Hub, path: str) -> dict[str, Any]:
    if hub.bao is None:
        return {}
    from hq_common.openbao import OpenBaoError

    try:
        data = await hub.bao.read_kv(path)
    except OpenBaoError:
        return {}
    return data if isinstance(data, dict) else {}


def secret_path(company: str, kind: str, channel: str | None) -> tuple[str, str]:
    if kind == "telegram":
        return f"support/telegram/{company}/{channel}", "webhook_secret"
    return f"support/intake/{company}/{kind}", "secret"


async def _secret(hub: Hub, company: str, kind: str, channel: str | None) -> str | None:
    path, key = secret_path(company, kind, channel)
    value = (await _kv(hub, path)).get(key)
    return value if isinstance(value, str) and value else None


# ------------------------------------------------------------------- owner --
def _render(r: dict[str, Any], company: str, configured: bool) -> IntakeSource:
    return IntakeSource(
        company=company, kind=r["kind"], channel=r["channel"], configured=configured,
        enabled=bool(r["enabled"]), allowed_ips=[str(x) for x in r["allowed_ips"] or []],
        kinds=list(r["kinds"] or []), last_event_at=r["last_event_at"],
        events_24h=int(r["events_24h"] or 0), rejected_24h=int(r["rejected_24h"] or 0),
        version=r["version"],
    )  # fmt: skip


SOURCE_SQL = """SELECT s.*,
       (SELECT count(*) FROM intake.events e WHERE e.source_id = s.id
          AND e.received_at > now() - interval '24 hours') AS events_24h,
       (SELECT count(*) FROM intake.rejections j WHERE j.source_id = s.id
          AND j.at > now() - interval '24 hours') AS rejected_24h
    FROM intake.sources s"""


@router.get("/intake/sources", response_model=list[IntakeSource], responses=E)
async def list_sources(ctx: Ctx = Depends(owner_ctx)) -> list[IntakeSource]:
    """Every source with whether its secret is stored (never the secret)."""
    async with ctx.tx() as tx:
        rows = await tx.all(SOURCE_SQL + " ORDER BY s.company_id, s.kind, s.channel")
    out = []
    for r in rows:
        company = await ctx.hub.companies.code_of(r["company_id"])
        configured = await _secret(ctx.hub, company, r["kind"], r["channel"]) is not None
        out.append(_render(r, company, configured))
    return out


@router.post("/intake/sources", response_model=IntakeSource, status_code=201, responses=E)
async def put_source(body: IntakeSourceIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `intake.source`, target = the SHA-256 of the exact body: registers
    or changes one source (allowed IPs, event kinds). Requires `Idempotency-Key`."""
    channel = body.channel
    if body.kind == "telegram" and channel not in ("telegram_bot", "telegram_business"):
        raise ApiError(
            422, "validation_failed", fields={"channel": "telegram_bot or telegram_business"}
        )
    if body.kind == "chatwoot":
        channel = "chatwoot"
    if body.kind == "product":
        channel = None
    if body.kind != "product" and body.kinds:
        raise ApiError(422, "validation_failed", fields={"kinds": "product sources only"})
    try:
        nets = sorted({str(ipaddress.ip_network(x, strict=False)) for x in body.allowed_ips})
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"allowed_ips": "CIDR blocks"}) from exc
    co = await ctx.hub.companies.find(body.company)
    if co is None:
        raise ApiError(404, "not_found", f"no company {body.company}")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        step_up_id = await stepup.consume(
            tx, request, ctx.who, "intake.source", await stepup.body_target(request)
        )
        row = await tx.one(
            """INSERT INTO intake.sources (company_id, kind, channel, allowed_ips, kinds, body_sha256)
               VALUES (:co, :k, :ch, CAST(:ips AS cidr[]), :kinds, :sha)
               ON CONFLICT (company_id, kind, channel) DO UPDATE SET allowed_ips = EXCLUDED.allowed_ips,
                   kinds = EXCLUDED.kinds, body_sha256 = EXCLUDED.body_sha256, enabled = true,
                   updated_at = now()
               RETURNING id""",
            co=co.id,
            k=body.kind,
            ch=channel,
            ips=nets,
            kinds=sorted(set(body.kinds)),
            sha=await stepup.body_target(request),
        )
        shadow_channel = channel or ("product_bot" if "support_message" in body.kinds else None)
        if shadow_channel:
            await S.channel(tx, co.id, shadow_channel)
            await tx.exec(
                """UPDATE support.channels SET state = 'shadow', updated_at = now()
                   WHERE company_id = :co AND kind = :k AND state = 'not_configured'""",
                co=co.id,
                k=shadow_channel,
            )
        full = await tx.one(SOURCE_SQL + " WHERE s.id = :id", id=row["id"])
        await ctx.audit(
            tx, company_id=co.id, action="intake.source", action_class="A2",
            target_kind="intake_source", target_ref=f"{co.code}/{body.kind}/{channel or '-'}",
            summary=f"{len(nets)} ip ranges, kinds {','.join(body.kinds)}"[:300],
            step_up=step_up_id is not None,
        )  # fmt: skip
        configured = await _secret(ctx.hub, co.code, body.kind, channel) is not None
        out = _render(full, co.code, configured)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


# ---------------------------------------------------------------- webhooks --
class Refused(Exception):
    def __init__(self, status: int, reason: str, source_id: UUID | None = None) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason
        self.source_id = source_id
        self.company_id: UUID | None = None  # set once the company is known (the count's row)


CODES = {401: "unauthenticated", 403: "forbidden", 409: "validation_failed", 413: "validation_failed",
         422: "validation_failed", 429: "rate_limited"}  # fmt: skip


async def _refuse(
    hub: Hub, request: Request, company_id: UUID | None, kind: str, err: Refused
) -> JSONResponse:
    if company_id is not None:
        async with hub.db.tx([company_id]) as tx:
            await tx.exec(
                "INSERT INTO intake.rejections (company_id, source_id, kind, reason) VALUES (:co, :s, :k, :r)",
                co=company_id,
                s=err.source_id,
                k=kind,
                r=err.reason,
            )
            if err.source_id is not None:
                await tx.exec(
                    "UPDATE intake.sources SET last_rejected_at = now() WHERE id = :id",
                    id=err.source_id,
                )
    headers = {"Retry-After": "60"} if err.status == 429 else None
    return problem_response(
        request, ApiError(err.status, CODES.get(err.status, "forbidden"), headers=headers)
    )


def _obj(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _ip_ok(ip: str, nets: list[Any], *, telegram: bool) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if telegram and not any(addr in n for n in TELEGRAM_RANGES):
        return False
    allowed = [ipaddress.ip_network(str(n), strict=False) for n in nets or []]
    return not allowed or any(addr in n for n in allowed)


async def _source(
    hub: Hub, request: Request, company: str, kind: str, channel: str | None
) -> tuple[Any, dict[str, Any], bytes]:
    """The company, its source row and the body, after the cheap checks
    (size, rate, IP). Raises Refused (401 for anything unknown)."""
    co = await hub.companies.find(company) if company.isalnum() else None
    if co is None:
        raise Refused(401, "unknown_source")
    try:
        src, body = await _checked(hub, request, co, kind, channel)
    except Refused as err:
        err.company_id = co.id
        raise
    return co, src, body


async def _checked(
    hub: Hub, request: Request, co: Any, kind: str, channel: str | None
) -> tuple[dict[str, Any], bytes]:
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > hub.settings.intake_max_body:
        raise Refused(413, "too_large")
    body = await request.body()
    if len(body) > hub.settings.intake_max_body:
        raise Refused(413, "too_large")
    async with hub.db.tx([co.id]) as tx:
        src = await tx.first(
            """SELECT * FROM intake.sources WHERE company_id = :co AND kind = :k
                 AND channel IS NOT DISTINCT FROM CAST(:ch AS text)""",
            co=co.id,
            k=kind,
            ch=channel,
        )
    if src is None:
        raise Refused(401, "unknown_source")
    if not src["enabled"]:
        raise Refused(401, "disabled", src["id"])
    try:
        hub.limiter.check(f"intake:{co.code}:{kind}:{channel}", hub.settings.intake_rate_per_min)
    except ApiError as exc:
        raise Refused(429, "rate_limited", src["id"]) from exc
    if not _ip_ok(
        deps.client_ip(request), list(src["allowed_ips"] or []), telegram=kind == "telegram"
    ):
        raise Refused(403, "ip_not_allowed", src["id"])
    return src, body


def _signed(secret: str, ts: str, body: bytes, given: str, skew: int) -> str | None:
    """None when good, else the reason (bad_signature | stale)."""
    if not ts.isdigit() or not given:
        return "bad_signature"
    expected = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(given.removeprefix("sha256=").lower(), expected):
        return "bad_signature"
    if abs(time.time() - int(ts)) > skew:
        return "stale"
    return None


async def _nonce(tx: Tx, company_id: UUID, source_id: UUID, nonce: str) -> bool:
    """True the first time (company, source, nonce) is seen in a day."""
    row = await tx.first(
        """INSERT INTO intake.nonces (company_id, source_id, nonce) VALUES (:co, :s, :n)
           ON CONFLICT DO NOTHING RETURNING nonce""",
        co=company_id,
        s=source_id,
        n=nonce[:128],
    )
    if row is None:
        return False
    # An id seen before as an event (older than the nonce's day) is still a duplicate.
    return not await tx.scalar(
        "SELECT 1 FROM intake.events WHERE source_id = :s AND event_id = :n",
        s=source_id,
        n=nonce[:128],
    )


def _masked(data: dict[str, Any]) -> dict[str, Any]:
    """An event's data as stored: strings masked, no raw identity keys."""
    out: dict[str, Any] = {}
    for k, v in list(data.items())[:30]:
        if k.lower() in ("uid", "user_id", "subject", "phone", "email", "username", "handle"):
            continue
        if isinstance(v, str):
            out[k[:40]] = customer_mask.quote(v, max_chars=500)
        elif isinstance(v, bool | int | float) or v is None:
            out[k[:40]] = v
    return out


async def _event(
    tx: Tx, company_id: UUID, source_id: UUID, kind: str, event_id: str, *,
    subject: str | None = None, data: dict[str, Any] | None = None, at: datetime | None = None,
    state: str = "accepted",
) -> dict[str, Any]:  # fmt: skip
    await tx.exec("UPDATE intake.sources SET last_event_at = now() WHERE id = :id", id=source_id)
    return await tx.one(
        """INSERT INTO intake.events (company_id, source_id, kind, event_id, at, subject, data, state)
           VALUES (:co, :s, :k, :e, :at, :sub, CAST(:d AS jsonb), :st) RETURNING *""",
        co=company_id,
        s=source_id,
        k=kind,
        e=event_id[:128],
        at=at,
        sub=subject,
        d=json.dumps(data or {}, ensure_ascii=False),
        st=state,
    )


@webhook_router.post("/telegram/{company}/{channel}", include_in_schema=True, responses=E)
async def telegram_webhook(
    company: str, channel: str, request: Request, hub: Hub = Depends(get_hub)
) -> Any:
    """Telegram's webhook for a support channel (the bot API's update)."""
    co_id: UUID | None = None
    try:
        if channel not in ("telegram_bot", "telegram_business"):
            raise Refused(401, "unknown_source")
        co, src, body = await _source(hub, request, company, "telegram", channel)
        co_id = co.id
        secret = await _secret(hub, co.code, "telegram", channel)
        given = request.headers.get("x-telegram-bot-api-secret-token", "")
        if secret is None or not hmac.compare_digest(given.encode(), secret.encode()):
            raise Refused(401, "bad_signature", src["id"])
        try:
            update = json.loads(body)
            update_id = str(int(update["update_id"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise Refused(422, "malformed", src["id"]) from exc
        queued: list[str] = []
        async with hub.db.tx([co.id]) as tx:
            if not await _nonce(tx, co.id, src["id"], update_id):
                raise Refused(409, "duplicate", src["id"])
            queued = await _telegram_update(tx, hub, co.id, src, channel, update_id, update)
    except Refused as err:
        if err.reason == "duplicate":
            await _refuse(hub, request, co_id or err.company_id, "telegram", err)
            return {"ok": True, "duplicate": True}  # Telegram stops retrying on 200
        return await _refuse(hub, request, co_id or err.company_id, "telegram", err)
    for mid in queued:
        await workflows_client.support(hub, "SupportInbound", mid)
    return {"ok": True}


async def _telegram_update(
    tx: Tx, hub: Hub, company_id: UUID, src: dict[str, Any], channel: str, update_id: str,
    update: dict[str, Any],
) -> list[str]:  # fmt: skip
    conn = update.get("business_connection")
    if isinstance(conn, dict):
        if channel == "telegram_business":
            await S.channel(tx, company_id, channel)
            await tx.exec(
                """UPDATE support.channels SET premium_connected = :on, updated_at = now()
                   WHERE company_id = :co AND kind = 'telegram_business'""",
                on=bool(conn.get("is_enabled")),
                co=company_id,
            )
        await _event(tx, company_id, src["id"], "telegram_update", update_id,
                     data={"type": "business_connection", "enabled": bool(conn.get("is_enabled"))},
                     state="applied")  # fmt: skip
        return []
    msg = (
        update.get("business_message") if channel == "telegram_business" else update.get("message")
    )
    if not isinstance(msg, dict):
        await _event(tx, company_id, src["id"], "telegram_update", update_id,
                     data={"type": "other"}, state="ignored")  # fmt: skip
        return []
    sender = _obj(msg.get("from"))
    chat = _obj(msg.get("chat"))
    text = msg.get("text") or msg.get("caption")
    if (
        chat.get("type") != "private"
        or not sender.get("id")
        or sender.get("is_bot")
        or not isinstance(text, str)
    ):
        await _event(tx, company_id, src["id"], "telegram_update", update_id,
                     data={"type": "message", "kept": False}, state="ignored")  # fmt: skip
        return []
    stored = await S.store_inbound(
        tx, hub, company_id=company_id, channel_kind=channel, external_user_id=str(sender["id"]),
        body=text, external_message_id=str(msg.get("message_id") or update_id),
        handle=f"@{sender['username']}" if sender.get("username") else None,
        display_name=str(sender.get("first_name") or "")[:200] or None,
        lang=str(sender.get("language_code") or "fa")[:2],
        external={"chat_id": chat.get("id"),
                  "business_connection_id": msg.get("business_connection_id")},
    )  # fmt: skip
    await _event(tx, company_id, src["id"], "telegram_update", update_id, subject=stored["subject"],
                 data={"type": "message", "conversation": stored["conversation"]["ref"]},
                 state="applied")  # fmt: skip
    return [] if stored["duplicate"] else [str(stored["message"]["id"])]


@webhook_router.post("/chatwoot/{company}", responses=E)
async def chatwoot_webhook(company: str, request: Request, hub: Hub = Depends(get_hub)) -> Any:
    """Chatwoot's agent-bot webhook (HMAC over "<timestamp>.<body>")."""
    co_id: UUID | None = None
    try:
        co, src, body = await _source(hub, request, company, "chatwoot", "chatwoot")
        co_id = co.id
        secret = await _secret(hub, co.code, "chatwoot", "chatwoot")
        why = (
            _signed(
                secret,
                request.headers.get("x-chatwoot-timestamp", ""),
                body,
                request.headers.get("x-chatwoot-signature", ""),
                hub.settings.intake_max_skew_s,
            )
            if secret
            else "bad_signature"
        )
        if why:
            raise Refused(401, why, src["id"])
        try:
            event = json.loads(body)
            event_id = f"{event.get('event', 'event')}:{int(event['id'])}"
        except (ValueError, KeyError, TypeError) as exc:
            raise Refused(422, "malformed", src["id"]) from exc
        queued: list[str] = []
        async with hub.db.tx([co.id]) as tx:
            if not await _nonce(tx, co.id, src["id"], event_id):
                raise Refused(409, "duplicate", src["id"])
            queued = await _chatwoot_event(tx, hub, co.id, src, event_id, event)
    except Refused as err:
        if err.reason == "duplicate":
            await _refuse(hub, request, co_id or err.company_id, "chatwoot", err)
            return {"ok": True, "duplicate": True}
        return await _refuse(hub, request, co_id or err.company_id, "chatwoot", err)
    for mid in queued:
        await workflows_client.support(hub, "SupportInbound", mid)
    return {"ok": True}


async def _chatwoot_event(
    tx: Tx, hub: Hub, company_id: UUID, src: dict[str, Any], event_id: str, event: dict[str, Any]
) -> list[str]:
    sender = _obj(event.get("sender"))
    conv = _obj(event.get("conversation"))
    account = _obj(event.get("account"))
    content = event.get("content")
    if (
        event.get("event") != "message_created"
        or event.get("message_type") not in ("incoming", 0)
        or event.get("private")
        or not isinstance(content, str)
        or not sender.get("id")
    ):
        await _event(tx, company_id, src["id"], "chatwoot_event", event_id,
                     data={"event": str(event.get("event"))[:40]}, state="ignored")  # fmt: skip
        return []
    stored = await S.store_inbound(
        tx, hub, company_id=company_id, channel_kind="chatwoot", external_user_id=str(sender["id"]),
        body=content, external_message_id=str(event.get("id")),
        display_name=str(sender.get("name") or "")[:200] or None,
        external={"account_id": account.get("id"), "conversation_id": conv.get("id")},
    )  # fmt: skip
    await tx.exec(
        "UPDATE support.customers SET started_at = COALESCE(started_at, now()) WHERE id = :id",
        id=stored["customer_id"],
    )
    await _event(tx, company_id, src["id"], "chatwoot_event", event_id, subject=stored["subject"],
                 data={"event": "message_created", "conversation": stored["conversation"]["ref"]},
                 state="applied")  # fmt: skip
    return [] if stored["duplicate"] else [str(stored["message"]["id"])]


class ProductEvent(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    kind: str = Field(max_length=40)
    at: datetime | None = None
    subject: str = Field(min_length=1, max_length=128)
    data: dict[str, Any] = Field(default_factory=dict)


@webhook_router.post("/product/{company}", responses=E)
async def product_webhook(company: str, request: Request, hub: Hub = Depends(get_hub)) -> Any:
    """A product's events (CR-009/010/011), HMAC over "<timestamp>.<body>"."""
    co_id: UUID | None = None
    try:
        co, src, body = await _source(hub, request, company, "product", None)
        co_id = co.id
        secret = await _secret(hub, co.code, "product", None)
        why = (
            _signed(
                secret,
                request.headers.get("x-hq-timestamp", ""),
                body,
                request.headers.get("x-hq-signature", ""),
                hub.settings.intake_max_skew_s,
            )
            if secret
            else "bad_signature"
        )
        if why:
            raise Refused(401, why, src["id"])
        try:
            raw = json.loads(body)
            events = [ProductEvent.model_validate(e) for e in raw["events"]][:MAX_EVENTS]
        except (ValueError, KeyError, TypeError) as exc:
            raise Refused(422, "malformed", src["id"]) from exc
        counts = {"accepted": 0, "duplicates": 0, "ignored": 0}
        queued: list[str] = []
        async with hub.db.tx([co.id]) as tx:
            for ev in events:
                if ev.kind not in PRODUCT_KINDS or ev.kind not in (src["kinds"] or []):
                    counts["ignored"] += 1
                    continue
                if not await _nonce(tx, co.id, src["id"], ev.id):
                    counts["duplicates"] += 1
                    continue
                queued += await _product_event(tx, hub, co.id, src, ev)
                counts["accepted"] += 1
            if events and counts["duplicates"] == len(events):
                raise Refused(409, "duplicate", src["id"])
    except Refused as err:
        if err.reason == "duplicate":
            await _refuse(hub, request, co_id or err.company_id, "product", err)
            return {"accepted": 0, "duplicates": "all", "ignored": 0}
        return await _refuse(hub, request, co_id or err.company_id, "product", err)
    for mid in queued:
        await workflows_client.support(hub, "SupportInbound", mid)
    return counts


async def _product_event(
    tx: Tx, hub: Hub, company_id: UUID, src: dict[str, Any], ev: ProductEvent
) -> list[str]:
    """Stored masked, the UID as its pseudonym (uid:<exchange>); a
    support_message enters the support desk on product_bot (CR-011)."""
    exchange = str(ev.data.get("exchange") or "").lower()
    channel = f"uid:{exchange}" if exchange.isalnum() else "product_bot"
    try:
        subject = pseudonym.subject(
            hub.secrets.support_pseudonym_key, str(company_id), channel, ev.subject
        )
    except pseudonym.KeyMissing as exc:
        raise ApiError(503, "not_ready", "the customer pseudonym key is not loaded") from exc
    if ev.kind == "support_message":
        text = ev.data.get("text")
        if not isinstance(text, str) or not text.strip():
            await _event(tx, company_id, src["id"], ev.kind, ev.id, subject=subject, at=ev.at,
                         state="ignored")  # fmt: skip
            return []
        stored = await S.store_inbound(
            tx, hub, company_id=company_id, channel_kind="product_bot", external_user_id=ev.subject,
            body=text, external_message_id=ev.id, external={"product": True},
        )  # fmt: skip
        await tx.exec(
            "UPDATE support.customers SET started_at = COALESCE(started_at, now()) WHERE id = :id",
            id=stored["customer_id"],
        )
        await _event(tx, company_id, src["id"], ev.kind, ev.id, subject=stored["subject"], at=ev.at,
                     data={"conversation": stored["conversation"]["ref"]}, state="applied")  # fmt: skip
        return [] if stored["duplicate"] else [str(stored["message"]["id"])]
    row = await _event(tx, company_id, src["id"], ev.kind, ev.id, subject=subject, at=ev.at,
                       data=_masked(ev.data))  # fmt: skip
    applier = APPLIERS.get(ev.kind)
    if applier is not None:
        state = await applier(tx, hub, company_id, row)
        if state:
            await tx.exec(
                "UPDATE intake.events SET state = :s, applied_at = now() WHERE id = :id",
                s=state,
                id=row["id"],
            )
    return []
