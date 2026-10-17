"""MCP servers and the tool catalog (prompt 07 §3, contract §18.7, §18.10).

Owner:    GET /tools/mcp · POST /tools/mcp 🔏 (`mcp.add`, the body's SHA-256)
          POST /tools/mcp/{key}/enable 🔏 (`mcp.enable`, the key) · /disable
          GET /tools/catalog
Gateway:  POST /internal/v1/tools/mcp/resolve (one mcp.call: may this agent
          call that tool, at which class; an A3 tool becomes the owner's
          `a3_action` decision instead) · POST /internal/v1/tools/mcp/{key}/listing
          (what the server lists: pinned once after an enable; a change
          switches the server off until the owner seals it again).
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hq_api import workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import decisions as D
from hq_api.domain import mcp as M
from hq_api.domain import notify
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup

log = logging.getLogger("hq_api.tools")
router = APIRouter(tags=["tools"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
EI = responses(401, 403, 404, 409, 422, 423, 429, 503)


async def _rendered(ctx: Ctx, rows: list[dict[str, Any]]) -> list[M.McpServer]:
    return [M.render(r, await M.has_secret(ctx.hub, r["key"])) for r in rows]


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
    `container` on the internal network hq-mcp), the tools with their class
    and the companies that may call it. Pending until `/enable`. The secret is
    written on the server (`make mcp-secret KEY=…`), never through the API."""
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "mcp.add", await stepup.body_target(request))
        codes = {c.code for c in await ctx.hub.companies.all()}
        row = await M.put(tx, body, ctx.who.code, codes)
        holding = (await ctx.hub.companies.holding()).id
        await ctx.audit(
            tx,
            company_id=holding,
            action="mcp.add",
            action_class="A2",
            target_kind="mcp_server",
            target_ref=body.key,
            summary=f"{body.transport}, {len(body.tools)} tools, v{row['version']}",
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
    return M.render(row, await M.has_secret(ctx.hub, body.key))


@router.post("/tools/mcp/{key}/enable", response_model=M.McpServer, responses=E)
async def enable_mcp(key: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> M.McpServer:
    """🔏 (`mcp.enable`, target = the key). The gateway pins the server's tool
    listing on its next call; a later change switches it off again."""
    _key(key)
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "mcp.enable", key)
        row = await M.set_status(tx, key, "enabled", None, enable=True)
        await _audit_status(ctx, tx, key, "mcp.enable", "A2")
    return M.render(row, await M.has_secret(ctx.hub, key))


@router.post("/tools/mcp/{key}/disable", response_model=M.McpServer, responses=E)
async def disable_mcp(key: str, ctx: Ctx = Depends(owner_ctx)) -> M.McpServer:
    """Switches a server off at once (no step-up: stopping is always allowed)."""
    _key(key)
    async with ctx.tx() as tx:
        row = await M.set_status(tx, key, "disabled", "the owner switched it off")
        await _audit_status(ctx, tx, key, "mcp.disable", "A1")
    return M.render(row, await M.has_secret(ctx.hub, key))


def _key(key: str) -> None:
    import re

    if not re.fullmatch(M.SERVER_KEY, key):
        raise ApiError(404, "not_found")


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
    build (`live`, `off`, `channel_not_configured`, `pending`)."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM tools.mcp_servers ORDER BY key")
    return M.catalog(ctx.hub.charters, rows)


# ---------------------------------------------------------------- internal --
class ResolveIn(Model):
    server: str = Field(pattern=M.SERVER_KEY)
    tool: str = Field(pattern=M.TOOL_NAME)
    args_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview: str = Field(default="", max_length=20000)


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
    decision: str | None = None
    message_fa: str | None = None


def _agent(ctx: Ctx) -> None:
    if ctx.who.kind != "agent" or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


@internal_router.post("/tools/mcp/resolve", response_model=Resolved, responses=EI)
async def resolve_mcp(body: ResolveIn, ctx: Ctx = Depends(internal_ctx)) -> Resolved:
    """The gateway's question before one mcp.call. Refused: an unknown server
    or tool (always: a tool outside the sealed registration), a company the
    server is not for, a server not enabled, the caps. An A3 tool never runs:
    an `a3_action` decision for the owner is made (once per run and arguments)."""
    _agent(ctx)
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(ctx, "mcp.call", {"company": ctx.who.company})
    s = ctx.hub.settings
    decision_ref: str | None = None
    async with ctx.tx() as tx:
        row = await M.load(tx, body.server)
        if row is None:
            raise ApiError(403, "policy_denied", "mcp_server_unknown")
        if row["companies"] is not None and ctx.who.company not in row["companies"]:
            raise ApiError(403, "policy_denied", "mcp_server_not_for_this_company")
        tool = M.sealed_tool(row, body.tool)
        if tool is None:
            raise ApiError(403, "policy_denied", "mcp_tool_not_sealed")
        if row["status"] != "enabled":
            raise ApiError(503, "channel_not_configured", f"mcp server {row['status']}")
        used = await tx.first(
            """SELECT count(*) FILTER (WHERE run_id = CAST(:run AS uuid)) AS run,
                      count(*) FILTER (WHERE at >= (SELECT date_trunc('day', now() AT TIME ZONE o.timezone)
                                                           AT TIME ZONE o.timezone
                                                    FROM owner.settings o WHERE o.id = 1)) AS day
               FROM tools.mcp_calls WHERE company_id = :co AND at > now() - interval '2 days'""",
            run=ctx.who.run_id,
            co=ctx.who.company_id,
        )
        cls = str(tool["class"])
        if cls == "A3":
            decision_ref = await _a3_decision(ctx, tx, body, row)
        else:
            if (used or {}).get("run", 0) >= s.mcp_calls_per_run or (used or {}).get(
                "day", 0
            ) >= s.mcp_calls_per_company_day:
                raise ApiError(429, "rate_limited", "mcp call caps")
            await _record(tx, ctx, body, cls, "resolved", None)
    if decision_ref is not None:
        await workflows_client.decision_created(ctx.hub, decision_ref)
        return Resolved(
            cls="A3",
            tool=body.tool,
            decision=decision_ref,
            message_fa=(
                f"این ابزار A3 است و اجرا نشد؛ تصمیم {decision_ref} برای مدیر کل ساخته شد."
            ),
        )
    return Resolved(
        cls=cls,
        tool=body.tool,
        server=ResolvedServer(
            key=row["key"],
            transport=row["transport"],
            url=row["url"],
            auth_header=row["auth_header"],
            secret=await M.secret(ctx.hub, row["key"]) if row["auth_header"] else None,
            listing_sha256=row["listing_sha256"],
        ),
    )


async def _record(
    tx: Any, ctx: Ctx, body: ResolveIn, cls: str, outcome: str, decision_id: UUID | None
) -> None:
    await tx.exec(
        """INSERT INTO tools.mcp_calls (company_id, run_id, actor_code, server_key, tool, class,
               outcome, args_sha256, decision_id)
           VALUES (:co, CAST(:run AS uuid), :by, :srv, :tool, :cls, :out, :sha, :d)""",
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


async def _a3_decision(ctx: Ctx, tx: Any, body: ResolveIn, row: dict[str, Any]) -> str:
    """The same run asking again with the same arguments gets the same card."""
    prev = await tx.first(
        """SELECT d.ref FROM tools.mcp_calls c JOIN cartable.decisions d ON d.id = c.decision_id
           WHERE c.run_id = CAST(:run AS uuid) AND c.server_key = :srv AND c.tool = :tool
             AND c.args_sha256 = :sha AND c.outcome = 'decision'""",
        run=ctx.who.run_id,
        srv=body.server,
        tool=body.tool,
        sha=body.args_sha256,
    )
    if prev is not None:
        return str(prev["ref"])
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(
        ctx,
        "decision.propose",
        {"company": ctx.who.company, "kind": "a3_action", "scope": None, "hiring": None},
    )
    await ctx.ensure_unlocked(tx, ctx.who.company_id)
    target = f"{body.server}/{body.tool}"[:300]
    proposal = D.DecisionIn(
        kind="a3_action",
        title=f"MCP: {target}"[:300],
        what=(
            f"ابزار `{body.tool}` از سرور MCP «{row['title_fa']}» ({body.server}) کلاس A3 دارد "
            "(تعهد بیرونی) و بدون تصمیم مدیر کل اجرا نمیشود. ورودی ماسک‌شده در payload است."
        ),
        why="کلاس این ابزار در ثبت مُهرشده‌ی سرور A3 است.",
        risk="medium",
        reversible=False,
        payload={
            "action": "mcp_call",
            "target": target,
            "preview": body.preview,
            "args_sha256": body.args_sha256,
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


class ListingIn(Model):
    listing_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tools: list[str] = Field(default_factory=list, max_length=200)


class ListingOut(BaseModel):
    status: Literal["pending", "enabled", "disabled"]


@internal_router.post("/tools/mcp/{key}/listing", response_model=ListingOut, responses=EI)
async def mcp_listing(key: str, body: ListingIn, ctx: Ctx = Depends(internal_ctx)) -> ListingOut:
    """What the server listed on a call. The first listing after an enable is
    pinned; any other one switches the server off (`tools changed`) and tells
    the owner, who seals it again (`POST /tools/mcp`, then `/enable`)."""
    _agent(ctx)
    _key(key)
    assert ctx.who.company is not None
    await allow(ctx, "mcp.call", {"company": ctx.who.company})
    names = [n[:128] for n in body.tools]
    switched_off = False
    async with ctx.tx() as tx:
        row = await M.load(tx, key, lock=True)
        if row is None:
            raise ApiError(403, "policy_denied", "mcp_server_unknown")
        status = row["status"]
        if status == "enabled" and row["listing_sha256"] is None:
            await tx.exec(
                """UPDATE tools.mcp_servers SET listing_sha256 = :sha, listed_tools = :names,
                       listed_at = now(), updated_at = now() WHERE key = :k""",
                sha=body.listing_sha256,
                names=names,
                k=key,
            )
        elif status == "enabled" and row["listing_sha256"] != body.listing_sha256:
            await tx.exec(
                """UPDATE tools.mcp_servers SET status = 'disabled', status_reason = 'tools changed',
                       listed_tools = :names, listed_at = now(), updated_at = now()
                   WHERE key = :k""",
                names=names,
                k=key,
            )
            status, switched_off = "disabled", True
        if switched_off:
            holding = await ctx.hub.companies.holding()
            await notify.raise_notification(
                tx,
                company_id=holding.id,
                company_code=holding.code,
                level="report",
                title_fa=f"سرور MCP «{row['title_fa']}» خاموش شد",
                body_fa=(
                    "فهرست ابزارهای این سرور بعد از مُهر تو عوض شده است. تا وقتی دوباره ثبت و "
                    "مُهرش نکنی، هیچ ایجنتی از آن استفاده نمیکند."
                ),
                link_kind="mcp_server",
                link_ref=key,
            )
            await ctx.audit(
                tx,
                company_id=holding.id,
                action="mcp.tools_changed",
                action_class="A1",
                target_kind="mcp_server",
                target_ref=key,
                summary=f"{len(names)} tools listed; switched off",
            )
    if switched_off:
        log.warning("mcp server switched off: its tools changed", extra={"server": key})
    return ListingOut(status=status)
