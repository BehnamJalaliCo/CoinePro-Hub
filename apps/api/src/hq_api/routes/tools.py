"""MCP servers and the tool catalog (prompt 07 §3, contract §18.7, §18.10, §18.13).

Owner:    GET /tools/mcp · POST /tools/mcp 🔏 (`mcp.add`, the body's SHA-256)
          POST /tools/mcp/{key}/enable 🔏 (`mcp.enable`, the key) · /disable
          (the three POSTs require `Idempotency-Key`, claimed before the seal
          is consumed: a replay answers what the first one did)
          GET /tools/catalog
Gateway:  POST /internal/v1/tools/mcp/resolve (one mcp.call: may this agent
          call that tool, at which class; an A3 tool becomes the owner's
          `a3_action` decision instead, and the approved card runs its one
          call once) · POST /internal/v1/tools/mcp/{key}/listing (what the
          server lists: pinned once after an enable; a change switches the
          server off and raises a `tool_enable` card for the owner's seal).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from hq_api import idempotency, workflows_client
from hq_api.audit import SYSTEM
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import decisions as D
from hq_api.domain import mcp as M
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup
from hq_common.redact import mask_secrets, scrub

log = logging.getLogger("hq_api.tools")
router = APIRouter(tags=["tools"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
EI = responses(401, 403, 404, 409, 422, 423, 429, 503)
# A call refused for the run's own cap: the next step may ask again (a run at
# its cap ends before then); the company-day cap answers when the day turns.
RUN_CAP_RETRY_S = 30


async def _rendered(ctx: Ctx, rows: list[dict[str, Any]]) -> list[M.McpServer]:
    return [M.render(r, await M.has_secret(ctx.hub, r)) for r in rows]


def _key(key: str) -> None:
    if not re.fullmatch(M.SERVER_KEY, key):
        raise ApiError(404, "not_found")


def _json(out: M.McpServer) -> dict[str, Any]:
    """The response as FastAPI serializes it (aliases), for an idempotent replay."""
    data: dict[str, Any] = out.model_dump(mode="json", by_alias=True)
    return data


async def _withdrawn(ctx: Ctx, tx: Any, key: str, note: str) -> None:
    """Pending `tool_enable` cards of `key` withdrawn (their server changed)."""
    for card in await M.withdraw_cards(tx, key, note):
        await ctx.audit(
            tx,
            company_id=card["company_id"],
            action="decision.withdraw",
            action_class="A1",
            target_kind="decision",
            target_ref=card["ref"],
            summary=f"tool_enable {key}: {note}"[:200],
        )


# ------------------------------------------------------------------- owner --
@router.get("/tools/mcp", response_model=list[M.McpServer], responses=E)
async def list_mcp(ctx: Ctx = Depends(owner_ctx)) -> list[M.McpServer]:
    """Every registered MCP server (none is enabled without the owner's seals);
    `has_secret` only says whether OpenBao holds one, never what it is."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM tools.mcp_servers ORDER BY key")
    return await _rendered(ctx, rows)


@router.post("/tools/mcp", response_model=M.McpServer, status_code=201, responses=E)
async def add_mcp(body: M.McpServerIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`mcp.add`, target = SHA-256 of the exact body). Registers a server,
    or a new version of it: its transport (`http` through the egress proxy;
    `container` on the internal network hq-mcp, only exactly as the reviewed
    allow-list infra/mcp/servers.yaml names it: else 422, and 409 not_ready
    for one that needs the internet or a secret), the tools with their class
    and the companies that may call it. Pending until `/enable`; the same body
    again changes nothing. Another host voids the stored secret (`has_secret`
    false until it is written again). The secret is written on the server
    (`make mcp-secret KEY=…`), never through the API. Requires
    `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if body.transport == "container":  # before the seal is spent
            M.check_container(body)
        await stepup.consume(tx, request, ctx.who, "mcp.add", await stepup.body_target(request))
        codes = {c.code for c in await ctx.hub.companies.all()}
        row, changed = await M.put(tx, body, ctx.who.code, codes)
        if changed:
            await _withdrawn(ctx, tx, body.key, "the server's registration changed")
        holding = (await ctx.hub.companies.holding()).id
        await ctx.audit(
            tx,
            company_id=holding,
            action="mcp.add",
            action_class="A2",
            target_kind="mcp_server",
            target_ref=body.key,
            summary=f"{body.transport}, {len(body.tools)} tools, v{row['version']}"
            + ("" if changed else ", unchanged"),
        )
        await ctx.interaction(
            tx,
            company_id=holding,
            kind="setting",
            action="mcp.add",
            target_kind="mcp_server",
            target_ref=body.key,
            data={"tools": [t.name for t in body.tools], "transport": body.transport},
        )
        out = M.render(row, await M.has_secret(ctx.hub, row))
        if idem:
            await idem.store(tx, 201, _json(out))
    return out


@router.post("/tools/mcp/{key}/enable", response_model=M.McpServer, responses=E)
async def enable_mcp(key: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`mcp.enable`, target = the key). The gateway pins the server's tool
    listing on its next call; a later change switches it off again. A
    `container` server runs only while the `mcp` profile is on and its sealed
    image is still the reviewed one: else 409 not_ready (the detail says
    why). Requires `Idempotency-Key`."""
    _key(key)
    on = ctx.hub.settings.mcp_containers
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await M.load(tx, key)
        if row is None:
            raise ApiError(404, "not_found")
        if (why := M.runnable(row, on)) is not None:  # before the seal is spent
            raise ApiError(409, "not_ready", why)
        await stepup.consume(tx, request, ctx.who, "mcp.enable", key)
        row = await M.set_status(tx, key, "enabled", None, enable=True, containers_on=on)
        await _withdrawn(ctx, tx, key, "the owner enabled the server again")
        await _audit_status(ctx, tx, key, "mcp.enable", "A2")
        out = M.render(row, await M.has_secret(ctx.hub, row))
        if idem:
            await idem.store(tx, 200, _json(out))
    return out


@router.post("/tools/mcp/{key}/disable", response_model=M.McpServer, responses=E)
async def disable_mcp(key: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Switches a server off at once (no step-up: stopping is always allowed);
    a pending `tool_enable` card of it is withdrawn. Requires `Idempotency-Key`."""
    _key(key)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await M.set_status(tx, key, "disabled", "the owner switched it off")
        await _withdrawn(ctx, tx, key, "the owner switched the server off")
        await _audit_status(ctx, tx, key, "mcp.disable", "A1")
        out = M.render(row, await M.has_secret(ctx.hub, row))
        if idem:
            await idem.store(tx, 200, _json(out))
    return out


async def _audit_status(ctx: Ctx, tx: Any, key: str, action: str, cls: str) -> None:
    await ctx.audit(
        tx,
        company_id=(await ctx.hub.companies.holding()).id,
        action=action,
        action_class=cls,
        target_kind="mcp_server",
        target_ref=key,
        summary=action,
    )


@router.get("/tools/catalog", response_model=list[M.CatalogTool], responses=E)
async def tool_catalog(ctx: Ctx = Depends(owner_ctx)) -> list[M.CatalogTool]:
    """Every tool the agents may be given (agents/tools.md, and each sealed
    MCP tool): class (`A0/A2` = decided per call; `per tool` = the server's
    registration), the roles whose charters grant it, and its status in this
    build (`live`, `off`, `channel_not_configured`, `pending`). A `container`
    server's tools are `channel_not_configured` while the `mcp` profile is off
    (or its sealed image is no longer the reviewed one)."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM tools.mcp_servers ORDER BY key")
    return M.catalog(ctx.hub.charters, rows, ctx.hub.settings.mcp_containers)


# ---------------------------------------------------------------- internal --
class ResolveIn(Model):
    server: str = Field(pattern=M.SERVER_KEY)
    tool: str = Field(pattern=M.TOOL_NAME)
    args_sha256: str = Field(pattern=M.SHA256)
    preview: str = Field(default="", max_length=20000)
    # The arguments with their secrets masked (the gateway's mask_secrets):
    # what an A3 card shows the owner (recipients, amounts).
    args: dict[str, Any] | None = None

    @field_validator("args")
    @classmethod
    def _small(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # mcp.call takes 20000 characters of arguments; masks may lengthen them a little.
        if v is not None and len(json.dumps(v, ensure_ascii=False, default=str)) > 40000:
            raise ValueError("at most 40000 characters of arguments")
        return v


class ResolvedServer(BaseModel):
    key: str
    transport: Literal["http", "container"]
    url: str
    auth_header: str | None
    secret: str | None = Field(default=None, description="for this one call; never logged")
    listing_sha256: str | None


class Resolved(BaseModel):
    cls: Literal["A0", "A1", "A2", "A3"] = Field(serialization_alias="class")
    tool: str
    server: ResolvedServer | None = None
    # An A3 tool: the card made (or still pending) and no server; or the
    # approved card this one call carries out, with the server.
    decision: str | None = None
    message_fa: str | None = None


def _agent(ctx: Ctx) -> None:
    if ctx.who.kind != "agent" or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


CAP_SQL = """
    WITH day AS (
        SELECT (date_trunc('day', now() AT TIME ZONE tz) AT TIME ZONE tz) AS start
        FROM (SELECT COALESCE((SELECT timezone FROM owner.settings WHERE id = 1), 'Asia/Tehran') AS tz) t
    )
    SELECT count(c.id) FILTER (WHERE c.run_id = CAST(:run AS uuid)) AS run,
           count(c.id) FILTER (WHERE c.at >= day.start) AS day,
           GREATEST(1, ceil(extract(epoch FROM day.start + interval '1 day' - now())))::int AS reset_s
    FROM day LEFT JOIN tools.mcp_calls c
         ON c.company_id = :co AND c.at > now() - interval '2 days'
    GROUP BY day.start
"""


async def _caps(ctx: Ctx, tx: Any) -> None:
    """The per-run and per-company-day caps, for every class (A3 too). The
    count is locked per company, so concurrent calls cannot both pass the
    last free place; 429 with Retry-After."""
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))",
        k=f"tools.mcp_calls:{ctx.who.company_id}",
    )
    used = await tx.one(CAP_SQL, run=ctx.who.run_id, co=ctx.who.company_id)
    s = ctx.hub.settings
    if used["day"] >= s.mcp_calls_per_company_day:
        raise ApiError(
            429, "rate_limited", "mcp calls: company-day cap",
            headers={"Retry-After": str(used["reset_s"])},
        )  # fmt: skip
    if used["run"] >= s.mcp_calls_per_run:
        raise ApiError(
            429, "rate_limited", "mcp calls: run cap",
            headers={"Retry-After": str(RUN_CAP_RETRY_S)},
        )  # fmt: skip


@internal_router.post("/tools/mcp/resolve", response_model=Resolved, responses=EI)
async def resolve_mcp(body: ResolveIn, ctx: Ctx = Depends(internal_ctx)) -> Resolved:
    """The gateway's question before one mcp.call. Refused: an unknown server
    or tool (always: a tool outside the sealed registration), a company the
    server is not for, a server not enabled, the caps (429, Retry-After). An
    A3 tool runs only as the one call of an approved card (same company,
    server, tool, arguments and registration; sealed in the last 24 hours;
    consumed atomically, so it runs once); otherwise an `a3_action` card for
    the owner is made (once: the same pending card is answered again), and a
    card the owner rejected answers 403 without a new one."""
    _agent(ctx)
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(ctx, "mcp.call", {"company": ctx.who.company})
    made: str | None = None
    server: ResolvedServer | None = None
    async with ctx.tx() as tx:
        row = await M.load(tx, body.server)
        if row is None:
            raise ApiError(403, "policy_denied", "mcp_server_unknown")
        if not M.for_company(row, ctx.who.company):
            raise ApiError(403, "policy_denied", "mcp_server_not_for_this_company")
        tool = M.sealed_tool(row, body.tool)
        if tool is None:
            raise ApiError(403, "policy_denied", "mcp_tool_not_sealed")
        if row["status"] != "enabled":
            raise ApiError(503, "channel_not_configured", f"mcp server {row['status']}")
        if (why := M.runnable(row, ctx.hub.settings.mcp_containers)) is not None:
            raise ApiError(503, "channel_not_configured", why)
        await _caps(ctx, tx)
        cls = str(tool["class"])
        approved: str | None = None
        if cls == "A3":
            state, ref = await _a3(ctx, tx, body, row)
            if state == "approved":
                approved = ref
            elif state == "made":
                made = ref
            else:  # still pending: the same card, nothing new
                return _card(body.tool, ref, pending=True)
        else:
            await _record(tx, ctx, body, cls, "resolved", None)
        if made is None:  # a call that runs: the server, and its secret for this call
            server = ResolvedServer(
                key=row["key"],
                transport=row["transport"],
                url=row["url"],
                auth_header=row["auth_header"],
                secret=await M.secret(ctx.hub, row) if row["auth_header"] else None,
                listing_sha256=row["listing_sha256"],
            )
    if made is not None:
        await workflows_client.decision_created(ctx.hub, made)
        return _card(body.tool, made, pending=False)
    return Resolved(cls=cls, tool=body.tool, server=server, decision=approved)


def _card(tool: str, ref: str, *, pending: bool) -> Resolved:
    return Resolved(
        cls="A3",
        tool=tool,
        decision=ref,
        message_fa=(
            f"این ابزار A3 است و اجرا نشد؛ تصمیم {ref} "
            + ("هنوز منتظر مدیر کل است." if pending else "برای مدیر کل ساخته شد.")
            + " بعد از تأیید، همین فراخوانی با همین ورودی یک بار اجرا میشود."
        ),
    )


async def _record(
    tx: Any, ctx: Ctx, body: ResolveIn, cls: str, outcome: str, decision_id: UUID | None
) -> bool:
    """One row of tools.mcp_calls; for `approved` the card's one row (False
    when another call consumed the card first)."""
    conflict = (
        "ON CONFLICT (decision_id) WHERE outcome = 'approved' DO NOTHING"
        if outcome == "approved"
        else ""
    )
    got = await tx.first(
        f"""INSERT INTO tools.mcp_calls (company_id, run_id, actor_code, server_key, tool, class,
               outcome, args_sha256, decision_id)
           VALUES (:co, CAST(:run AS uuid), :by, :srv, :tool, :cls, :out, :sha, :d)
           {conflict} RETURNING id""",  # noqa: S608 - a constant clause; values are bound
        co=ctx.who.company_id,
        run=ctx.who.run_id,
        by=ctx.who.code,
        srv=body.server,
        tool=body.tool,
        cls=cls,
        out=outcome,
        sha=body.args_sha256,
        d=decision_id,
    )
    return got is not None


CARDS_SQL = f"""
    SELECT d.id, d.ref, d.status, d.note, d.created_at,
           d.status = 'approved' AND d.decided_at > now() - interval '{M.A3_CARD_HOURS} hours' AS fresh,
           d.decided_at > now() - interval '{M.A3_CARD_HOURS} hours' AS recent,
           EXISTS (SELECT 1 FROM tools.mcp_calls c
                   WHERE c.decision_id = d.id AND c.outcome = 'approved') AS used
    FROM cartable.decisions d
    WHERE d.company_id = :co AND d.kind = 'a3_action' AND d.payload ->> 'action' = 'mcp_call'
      AND d.payload ->> 'args_sha256' = :sha AND d.payload ->> 'server' = :srv
      AND d.payload ->> 'tool' = :tool AND d.payload ->> 'registration_sha256' = :reg
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT 50
    FOR SHARE OF d
"""  # noqa: S608 - a module constant; values are bound


async def _a3(ctx: Ctx, tx: Any, body: ResolveIn, row: dict[str, Any]) -> tuple[str, str]:
    """("approved" | "pending" | "made", ref) for one A3 call (contract §18.13):
    an approved, unused card of the same company, server, tool, arguments and
    registration from the last 24 hours is consumed (from any run, once);
    the latest card still pending is the answer again; a rejected or returned
    one answers 403 policy_denied (no new card); otherwise a new card."""
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    cards = await tx.all(
        CARDS_SQL,
        co=ctx.who.company_id,
        sha=body.args_sha256,
        srv=body.server,
        tool=body.tool,
        reg=row["registration_sha256"],
    )
    unused = sorted(
        (c for c in cards if c["fresh"] and not c["used"]), key=lambda c: c["created_at"]
    )
    for card in unused:  # the oldest first
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        if await _record(tx, ctx, body, "A3", "approved", card["id"]):
            return "approved", str(card["ref"])
    latest = cards[0] if cards else None
    if latest is not None and latest["status"] == "pending":
        return "pending", str(latest["ref"])
    if latest is not None and latest["status"] in ("rejected", "returned") and latest["recent"]:
        note = f" یادداشت مدیر کل: {latest['note']}" if latest["note"] else ""
        raise ApiError(
            403,
            "policy_denied",
            f"a3_rejected {latest['ref']}",
            message_fa=(
                f"مدیر کل همین فراخوانی را با همین ورودی رد کرده است ({latest['ref']}).{note}"
                " آن را دوباره نخواه؛ اگر هنوز لازم است، با ورودی تازه یا propose توضیح بده."
            )[:500],
        )
    return "made", await _a3_card(ctx, tx, body, row)


async def _a3_card(ctx: Ctx, tx: Any, body: ResolveIn, row: dict[str, Any]) -> str:
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(
        ctx,
        "decision.propose",
        {"company": ctx.who.company, "kind": "a3_action", "scope": None, "hiring": None},
    )
    await ctx.ensure_unlocked(tx, ctx.who.company_id)
    target = f"{body.server}/{body.tool}"[:300]
    # Only the secrets masked (again here: the gateway masked them already):
    # the owner must see the recipients and amounts they approve.
    args = mask_secrets(body.args) if body.args is not None else None
    proposal = D.DecisionIn(
        kind="a3_action",
        title=f"MCP: {target}"[:300],
        what=(
            f"ابزار `{body.tool}` از سرور MCP «{row['title_fa']}» ({body.server}) کلاس A3 دارد "
            "(تعهد بیرونی) و بدون تصمیم مدیر کل اجرا نمیشود. ورودی آن (فقط رمزها پوشانده "
            "شده‌اند) در payload است. با تأیید، همین فراخوانی با همین ورودی یک بار اجرا میشود."
        ),
        why="کلاس این ابزار در ثبت مُهرشده‌ی سرور A3 است.",
        risk="medium",
        reversible=False,
        payload={
            "action": "mcp_call",
            "target": target,
            "server": body.server,
            "tool": body.tool,
            "args": args,
            "preview": scrub(body.preview, secrets_only=True)[:20000],
            "args_sha256": body.args_sha256,
            "registration_sha256": row["registration_sha256"],
        },
    )
    d = await D.propose(
        tx,
        ctx.who,
        company_id=ctx.who.company_id,
        company_code=ctx.who.company,
        body=proposal,
        thread_code=ctx.who.code
        if await tx.scalar("SELECT 1 FROM msg.threads WHERE code = :c", c=ctx.who.code)
        else None,
        charters=ctx.hub.charters,
        company_kind=(await ctx.hub.companies.by_id(ctx.who.company_id)).kind,
    )
    await ctx.audit(
        tx,
        company_id=ctx.who.company_id,
        action="decision.propose",
        action_class="A1",
        target_kind="decision",
        target_ref=d["ref"],
        summary=f"a3_action (mcp {target})"[:200],
    )
    await _record(tx, ctx, body, "A3", "decision", d["id"])
    return str(d["ref"])


# ------------------------------------------------------------- the listing --
class ListedIn(Model):
    """One tool as the server listed it: its name, description (cut by the
    gateway) and the digest of everything the seal covers (description,
    title, input and output schemas, annotations)."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    sha256: str = Field(pattern=M.SHA256)


class ListingIn(Model):
    listing_sha256: str = Field(pattern=M.SHA256)
    tools: list[str] = Field(default_factory=list, max_length=500)  # names (older gateways)
    listing: list[ListedIn] | None = Field(default=None, max_length=500)


class ListingOut(BaseModel):
    status: Literal["pending", "enabled", "disabled"]


@internal_router.post("/tools/mcp/{key}/listing", response_model=ListingOut, responses=EI)
async def mcp_listing(key: str, body: ListingIn, ctx: Ctx = Depends(internal_ctx)) -> ListingOut:
    """What the server listed on a call (only from a company the server is
    for). The first listing after an enable is pinned. Any other one switches
    the server off (`tools changed`) and raises a `tool_enable` card in the
    holding's cartable (`{key, listing_sha256, diff}`); its seal re-enables the
    server with exactly that listing. A listing that differs again before the
    seal supersedes the card (withdrawn) and raises a new one."""
    _agent(ctx)
    _key(key)
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(ctx, "mcp.call", {"company": ctx.who.company})
    if body.listing is not None:
        listing = [
            {"name": t.name[:128], "description": t.description[:500], "sha256": t.sha256}
            for t in body.listing
        ]
    else:  # names only: each name's digest is the listing's (any change is a change)
        listing = [
            {"name": n[:128], "description": "", "sha256": body.listing_sha256} for n in body.tools
        ]
    names = [t["name"] for t in listing][:500]
    holding = await ctx.hub.companies.holding()
    card: str | None = None
    switched_off = False
    # The calling agent's company and the holding (where the card belongs).
    async with ctx.hub.db.tx([ctx.who.company_id, holding.id]) as tx:
        row = await M.load(tx, key, lock=True)
        if row is None:
            raise ApiError(403, "policy_denied", "mcp_server_unknown")
        if not M.for_company(row, ctx.who.company):
            raise ApiError(403, "policy_denied", "mcp_server_not_for_this_company")
        status, sha = row["status"], body.listing_sha256
        seen = {"sha": sha, "listing": json.dumps(listing, ensure_ascii=False), "names": names}
        if status == "enabled" and row["listing_sha256"] is None:
            await tx.exec(
                """UPDATE tools.mcp_servers SET listing_sha256 = :sha, pinned = CAST(:listing AS jsonb),
                       listed_sha256 = :sha, listing = CAST(:listing AS jsonb), listed_tools = :names,
                       listed_at = now(), updated_at = now() WHERE key = :k""",
                k=key,
                **seen,
            )
        elif status == "enabled" and row["listing_sha256"] != sha:
            await tx.exec(
                """UPDATE tools.mcp_servers SET status = 'disabled', status_reason = :why,
                       listed_sha256 = :sha, listing = CAST(:listing AS jsonb), listed_tools = :names,
                       listed_at = now(), updated_at = now()
                   WHERE key = :k""",
                k=key,
                why=M.TOOLS_CHANGED,
                **seen,
            )
            status, switched_off = "disabled", True
            card = await _tool_enable_card(ctx, tx, row, sha, listing, holding)
        elif (
            status == "disabled"
            and row["status_reason"] == M.TOOLS_CHANGED
            and row["listed_sha256"] != sha
        ):
            # Changed again before the owner's seal: that card is superseded.
            await tx.exec(
                """UPDATE tools.mcp_servers SET listed_sha256 = :sha, listing = CAST(:listing AS jsonb),
                       listed_tools = :names, listed_at = now(), updated_at = now()
                   WHERE key = :k""",
                k=key,
                **seen,
            )
            await _withdrawn(ctx, tx, key, "the server's listing changed again")
            card = await _tool_enable_card(ctx, tx, row, sha, listing, holding)
    if card is not None:
        await workflows_client.decision_created(ctx.hub, card)
    if switched_off:
        log.warning("mcp server switched off: its tools changed", extra={"server": key})
    return ListingOut(status=status)


async def _tool_enable_card(
    ctx: Ctx, tx: Any, row: dict[str, Any], sha: str, listing: list[dict[str, Any]], holding: Any
) -> str:
    """The owner's card to re-enable the server with exactly this listing."""
    change = M.diff(row["pinned"], listing)

    def names(kind: str) -> str:
        items = change[kind]
        return "، ".join(items[:20]) + (
            f" و {len(items) - 20} مورد دیگر" if len(items) > 20 else ""
        )

    lines = [
        f"{fa}: {names(kind)}"
        for kind, fa in (("added", "تازه"), ("changed", "عوض‌شده"), ("removed", "حذف‌شده"))
        if change[kind]
    ]
    proposal = D.DecisionIn(
        kind="tool_enable",
        title=f"MCP: فهرست ابزارهای «{row['title_fa']}» ({row['key']}) عوض شد"[:300],
        what=(
            f"فهرست ابزارهای سرور MCP «{row['title_fa']}» بعد از مُهر تو عوض شده است، پس سرور "
            "خاموش شد. با مُهر این کارت، سرور دقیقاً با همین فهرست دوباره روشن میشود؛ اگر فهرست "
            "پیش از مُهر دوباره عوض شود، این کارت کنار میرود و کارت تازه می‌آید.\n"
            + ("\n".join(lines) or "توضیح یا شِمای ابزارها عوض شده است.")
        )[:20000],
        why="ابزاری که مالک مُهر نکرده نباید به دست ایجنت‌ها برسد.",
        risk="medium",
        reversible=True,
        payload={
            "key": row["key"],
            "listing_sha256": sha,
            "diff": change,
            "registration_sha256": row["registration_sha256"],
        },
    )
    d = await D.propose(
        tx,
        SYSTEM,
        company_id=holding.id,
        company_code=holding.code,
        body=proposal,
        thread_code=None,
        charters=ctx.hub.charters,
        company_kind=holding.kind,
    )
    await ctx.audit(
        tx,
        company_id=holding.id,
        action="mcp.tools_changed",
        action_class="A1",
        target_kind="mcp_server",
        target_ref=row["key"],
        summary=(
            f"switched off; {d['ref']}: +{len(change['added'])} -{len(change['removed'])}"
            f" ~{len(change['changed'])}"
        ),
    )
    return str(d["ref"])
