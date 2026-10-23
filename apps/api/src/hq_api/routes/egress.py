"""The agents' internet (prompt 07 §2, contract §18.7).

Owner:
    GET  /egress              the egress log (?company&since&blocked), newest first
    GET  /egress/summary      per day and company (?period=day: today)
    GET  /tools/accounts      the holding's service accounts (metadata only)
    POST /tools/accounts      add or change one 🔏 (`account.put`, the body's SHA-256;
                              the secret: `make account-secret`)
Gateway (the run's agent token):
    POST /internal/v1/egress/reserve   before a request leaves: data guard, limits, account
    POST /internal/v1/egress/log       its log entries afterwards
    GET  /internal/v1/egress/recent    egress.recent (holding-scope roles)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import egress as G
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["egress"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 429)
CLASSES = Literal["A0", "A1", "A2", "A3"]
TOOL = r"^[a-z][a-z_]*(\.[a-z_]+)?$"


class EgressEntry(Model):
    id: str
    at: datetime
    company: str
    actor: str
    run_id: str | None = None
    tool: str
    kind: Literal["request", "connect", "search", "browse"]
    method: str
    host: str
    status: int | None = None
    bytes_in: int
    bytes_out: int
    ms: int
    blocked_reason: str | None = None
    class_: CLASSES = Field(alias="class")

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class EgressDay(Model):
    day: str
    company: str
    requests: int
    blocked: int
    bytes: int
    browser_s: int
    hosts: int


class InjectPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ⟨1.5⟩ "signer" (contract §19.1): a reviewed request signer of egress, for
    # the worker's connector only (http.request and web.browse refuse it).
    kind: Literal["bearer", "header", "basic", "cookie", "signer"] = "bearer"
    name: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]{1,100}$")
    username: str | None = Field(default=None, max_length=200)
    signer: Literal["lbank-v2"] | None = None

    @model_validator(mode="after")
    def _signer_with_its_kind(self) -> InjectPolicy:
        if (self.kind == "signer") != (self.signer is not None):
            raise ValueError("signer goes with kind 'signer', and only with it")
        return self


class BrowsePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ⟨1.5⟩ "profile" (contract §21.13): a signed-in browser profile of the
    # profile browser (chatgpt-web, gemini-web, deepseek-web); no secret at all.
    kind: Literal["cookie", "header", "form", "profile"]
    name: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]{1,100}$")
    login_url: str | None = Field(default=None, max_length=2000, pattern=r"^https://")
    username: str | None = Field(default=None, max_length=200)
    user_selector: str | None = Field(default=None, max_length=200)
    pass_selector: str | None = Field(default=None, max_length=200)
    submit_selector: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _profile_alone(self) -> BrowsePolicy:
        extra = (self.name, self.login_url, self.username, self.user_selector,
                 self.pass_selector, self.submit_selector)  # fmt: skip
        if self.kind == "profile" and any(v is not None for v in extra):
            raise ValueError("a profile takes nothing but its kind")
        return self


class AllowRule(BaseModel):
    """A call other than GET/HEAD the owner lists as non-committing."""

    model_config = ConfigDict(extra="forbid")
    methods: list[Literal["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]] = Field(min_length=1)
    path_prefix: str = Field(min_length=1, max_length=500, pattern=r"^/")
    note_fa: str | None = Field(default=None, max_length=300)


class MailPolicy(BaseModel):
    """⟨1.6⟩ the `mail` account's servers (prompt 13 §3.2) when they are not
    imap.<site> and smtp.<site>; both must be the account's own site."""

    model_config = ConfigDict(extra="forbid")
    imap_host: str | None = Field(default=None, pattern=r"^[a-z0-9]([a-z0-9.-]{1,251}[a-z0-9])?$")
    smtp_host: str | None = Field(default=None, pattern=r"^[a-z0-9]([a-z0-9.-]{1,251}[a-z0-9])?$")


class AccountPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inject: InjectPolicy = Field(default_factory=InjectPolicy)
    browse: BrowsePolicy | None = None
    allow: list[AllowRule] = Field(default_factory=list, max_length=50)
    ports: list[int] = Field(default_factory=list, max_length=5)
    mail: MailPolicy | None = None

    @model_validator(mode="after")
    def _profile_injects_nothing(self) -> AccountPolicy:
        profile = self.browse is not None and self.browse.kind == "profile"
        if profile and (self.inject.kind == "signer" or self.ports):
            raise ValueError("a profile account injects nothing and opens no port")
        return self


class ServiceAccount(Model):
    id: str
    key: str
    site: str
    title_fa: str
    companies: Literal["all"] | list[str]
    has_secret: bool
    last_used_at: datetime | None = None
    policy: dict[str, Any]


class AccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    site: str = Field(pattern=r"^[a-z0-9]([a-z0-9.-]{1,251}[a-z0-9])?$")
    title_fa: str = Field(min_length=1, max_length=200)
    companies: Literal["all"] | list[str] = "all"
    policy: AccountPolicy = Field(default_factory=AccountPolicy)

    @model_validator(mode="after")
    def _mail_hosts_on_the_site(self) -> AccountIn:
        # ⟨1.6⟩ egress reaches only the account's own site (prompt 13 §3.2)
        m = self.policy.mail
        for host in (m.imap_host, m.smtp_host) if m else ():
            if host and host != self.site and not host.endswith("." + self.site):
                raise ValueError(f"{host} is not on the account's site {self.site}")
        return self


class ReserveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    tool: str = Field(pattern=TOOL, max_length=40)
    cls: CLASSES = Field(alias="class")
    strings: list[str] = Field(default_factory=list, max_length=500)
    method: str = Field(default="GET", pattern=r"^[A-Z]{3,7}$")
    url: str | None = Field(default=None, max_length=4000)
    account: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")


class LogEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    tool: str = Field(pattern=TOOL, max_length=40)
    method: str = Field(min_length=1, max_length=10)
    host: str = Field(min_length=1, max_length=255)
    kind: Literal["request", "connect", "search", "browse"] = "request"
    status: int | None = Field(default=None, ge=100, le=999)
    bytes_in: int = Field(default=0, ge=0)
    bytes_out: int = Field(default=0, ge=0)
    ms: int = Field(default=0, ge=0)
    blocked_reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    cls: CLASSES = Field(default="A0", alias="class")
    # An aggregated row (the gateway sums a call's rows beyond the batch's 200).
    requests: int = Field(default=1, ge=1, le=1_000_000)


class LogIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    tool: str = Field(pattern=TOOL, max_length=40)
    cls: CLASSES = Field(alias="class")
    entries: list[LogEntryIn] = Field(max_length=200)
    # The call's row that reserve wrote: these entries settle it.
    reservation: UUID | None = None


def _entry(r: dict[str, Any]) -> EgressEntry:
    return EgressEntry(
        id=str(r["id"]),
        at=r["at"],
        company=r["company"],
        actor=r["actor"],
        run_id=str(r["run_id"]) if r.get("run_id") else None,
        tool=r["tool"],
        kind=r["kind"],
        method=r["method"],
        host=r["host"],
        status=r["status"],
        bytes_in=int(r["bytes_in"]),
        bytes_out=int(r["bytes_out"]),
        ms=int(r["ms"]),
        blocked_reason=r["blocked_reason"],
        **{"class": r["class"]},
    )


async def _entries(
    ctx: Ctx,
    tx: Any,
    *,
    company: str | None,
    actor: str | None,
    since: datetime | None,
    blocked: bool | None,
    limit: int,
    cursor: str | None,
) -> Page[EgressEntry]:
    at, eid = pagination.time_id(cursor)
    rows = await tx.all(
        G.ENTRY_SQL
        + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
              AND (CAST(:actor AS text) IS NULL OR l.actor = :actor)
              AND (CAST(:since AS timestamptz) IS NULL OR l.at >= :since)
              AND (CAST(:blocked AS boolean) IS NULL OR (l.blocked_reason IS NOT NULL) = :blocked)
              AND (CAST(:at AS timestamptz) IS NULL OR (l.at, l.id) < (CAST(:at AS timestamptz), CAST(:id AS uuid)))
              AND """
        + G.LIVE
        + """ ORDER BY l.at DESC, l.id DESC LIMIT :lim""",
        co=company,
        actor=actor,
        since=since,
        blocked=blocked,
        at=at,
        id=eid,
        lim=limit + 1,
    )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return Page(items=[_entry(r) for r in items], next_cursor=nxt)


# ------------------------------------------------------------------ owner --
@router.get("/egress", response_model=Page[EgressEntry], responses=E)
async def list_egress(
    company: str | None = Query(default=None, pattern=CODE),
    since: datetime | None = None,
    blocked: bool | None = None,
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[EgressEntry]:
    """Every request the agents' tools sent out or that was stopped; newest first."""
    async with ctx.tx() as tx:
        return await _entries(
            ctx,
            tx,
            company=company,
            actor=None,
            since=since,
            blocked=blocked,
            limit=limit,
            cursor=cursor,
        )


@router.get("/egress/summary", response_model=list[EgressDay], responses=E)
async def egress_summary(
    period: Literal["day", "week", "month"] = "day",
    ctx: Ctx = Depends(owner_ctx),
) -> list[EgressDay]:
    """Per owner day and company: requests, blocked, bytes, browser seconds, hosts."""
    days = {"day": 1, "week": 7, "month": 31}[period]
    async with ctx.tx() as tx:
        rows = await tx.all(
            f"""WITH tz AS (SELECT COALESCE((SELECT timezone FROM owner.settings WHERE id = 1), 'Asia/Tehran') AS tz)
               SELECT to_char(l.at AT TIME ZONE tz.tz, 'YYYY-MM-DD') AS day, c.code AS company,
                      sum(l.requests) AS requests,
                      COALESCE(sum(l.requests) FILTER (WHERE l.blocked_reason IS NOT NULL), 0) AS blocked,
                      COALESCE(sum(l.bytes_in + l.bytes_out), 0) AS bytes,
                      COALESCE(sum(l.ms) FILTER (WHERE l.kind = 'browse'), 0) / 1000 AS browser_s,
                      count(DISTINCT l.host) AS hosts
               FROM egress.log l JOIN core.companies c ON c.id = l.company_id, tz
               WHERE l.at >= (date_trunc('day', now() AT TIME ZONE tz.tz) AT TIME ZONE tz.tz)
                             - make_interval(days => :back)
                 AND {G.LIVE}
               GROUP BY 1, 2 ORDER BY 1 DESC, 2""",  # noqa: S608 - composed from module constants; values are bound
            back=days - 1,
        )
    return [
        EgressDay(
            day=r["day"],
            company=r["company"],
            requests=int(r["requests"]),
            blocked=int(r["blocked"]),
            bytes=int(r["bytes"]),
            browser_s=int(r["browser_s"]),
            hosts=int(r["hosts"]),
        )
        for r in rows
    ]


async def _account_out(ctx: Ctx, r: dict[str, Any]) -> ServiceAccount:
    return ServiceAccount(
        id=str(r["id"]),
        key=r["key"],
        site=r["site"],
        title_fa=r["title_fa"],
        companies="all" if r["companies"] is None else list(r["companies"]),
        has_secret=await G.has_secret(ctx.hub.bao, r["key"]),
        last_used_at=r["last_used_at"],
        policy=r["policy"] or {},
    )


@router.get("/tools/accounts", response_model=list[ServiceAccount], responses=E)
async def list_accounts(ctx: Ctx = Depends(owner_ctx)) -> list[ServiceAccount]:
    """Every holding service account with its policy and whether the owner has
    stored its secret (`has_secret`); never the secret itself."""
    async with ctx.tx() as tx:
        rows = await tx.all("SELECT * FROM tools.accounts ORDER BY key")
    return [await _account_out(ctx, r) for r in rows]


@router.post("/tools/accounts", response_model=ServiceAccount, status_code=201, responses=E)
async def put_account(body: AccountIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`account.put`, target = SHA-256 of the exact body; 7.1 §2.14): a new
    site, allow rule or port widens what a stored secret can do. Adds an
    account, or changes one with the same key. Metadata and policy only: the
    owner writes the secret on the server (`make account-secret`). Requires
    `Idempotency-Key` (claimed before the seal: a replay answers the same)."""
    companies = None if body.companies == "all" else sorted(set(body.companies))
    if companies is not None:
        known = {c.code for c in await ctx.hub.companies.all()}
        unknown = [c for c in companies if c not in known]
        if unknown or not companies:
            raise ApiError(422, "validation_failed", fields={"companies": "unknown company code"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        step_up_id = await stepup.consume(
            tx, request, ctx.who, "account.put", await stepup.body_target(request)
        )
        row = await tx.one(
            """INSERT INTO tools.accounts (key, site, title_fa, companies, policy)
               VALUES (:k, :site, :t, CAST(:co AS text[]), CAST(:p AS jsonb))
               ON CONFLICT (key) DO UPDATE SET site = EXCLUDED.site, title_fa = EXCLUDED.title_fa,
                   companies = EXCLUDED.companies, policy = EXCLUDED.policy, updated_at = now()
               RETURNING *""",
            k=body.key,
            site=body.site,
            t=body.title_fa,
            co=companies,
            p=body.policy.model_dump_json(exclude_none=True),
        )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="tools.account",
            action_class="A2",
            target_kind="service_account",
            target_ref=body.key,
            summary=f"{body.site}; companies: {','.join(companies or ['all'])}",
            step_up=step_up_id is not None,
        )
        out = await _account_out(ctx, row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


# --------------------------------------------------------------- internal --
@internal_router.post("/egress/reserve", responses=E)
async def reserve(body: ReserveIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """Before an agent's request leaves: what it would send, the limits, the
    account. The answer carries the account's secret for this call only, and
    `reservation`: the call's row, written now, so a call whose answer is
    lost still counts (its log entries settle it)."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    who = ctx.who
    assert who.company is not None
    assert who.company_id is not None
    company_id = who.company_id
    await allow(ctx, "egress.use", {"company": who.company})
    codes = {c.code for c in await ctx.hub.companies.all()}
    async with ctx.tx() as tx:
        employees = frozenset(r["code"] for r in await tx.all("SELECT code FROM core.employees"))
    host = G.host_of(body.url)

    async def refuse(reason: str, err: ApiError) -> NoReturn:
        """A refused call: its row in the egress log and in the audit log (7.1)."""
        async with ctx.hub.db.tx([company_id]) as tx:
            await G.record(
                tx,
                company_id=company_id,
                actor=who.code,
                run_id=who.run_id,
                entries=[{"tool": body.tool, "kind": "request", "class": body.cls,
                          "method": body.method[:10], "host": host, "blocked_reason": reason}],
            )  # fmt: skip
            await ctx.audit(
                tx,
                company_id=company_id,
                action="egress.refused",
                action_class=body.cls,
                target_kind="host",
                target_ref=host[:200],  # the audit's limit (a host may have 255)
                summary=f"{body.tool} {body.method[:10]} refused: {reason}",
            )
        raise err

    reason = G.internal_data([*body.strings, body.url or ""], codes, employees)
    if reason:
        await refuse("internal_data", ApiError(403, "internal_data", reason))
    try:
        async with ctx.tx() as tx:
            usage = await tx.one(G.USAGE_SQL, run=who.run_id, co=company_id, actor=who.code[:60])
            left = G.limits_left(ctx.hub.settings, usage)
            acct = None
            if body.account:
                acct = await G.account(tx, ctx.hub.bao, body.account, who.company)
    except ApiError as err:  # the account: unknown, not this company's, no secret yet
        await refuse(err.code, err)
    if acct is not None and (acct.get("inject") or {}).get("kind") == "signer":
        # A signer's account (prompt 10 §2.2) serves the worker's connector only.
        acct = None
        await refuse("policy_denied", ApiError(403, "policy_denied", "a connector's account"))
    if acct is not None and G.is_profile(acct) and body.tool != "web.browse":
        # A signed-in profile (contract §21.13) is a browser's: web.browse only.
        acct = None
        await refuse("policy_denied", ApiError(403, "policy_denied", "a browser profile's account"))
    if (
        left["requests"] <= 0
        or left["bytes"] <= 0
        or (body.tool == "web.browse" and left["browser_s"] <= 0)
    ):
        retry = G.retry_after(ctx.hub.settings, usage)
        await refuse(
            "egress_limit", ApiError(429, "egress_limit", headers={"Retry-After": str(retry)})
        )
    if body.tool == "http.request" and body.method not in G.READ_METHODS:
        policy = acct.get("_policy") if acct else None
        if not acct or not G.non_committing(policy or {}, acct["site"], body.method, body.url):
            await refuse("needs_owner", ApiError(403, "needs_owner"))
    if acct is not None:
        acct.pop("_policy", None)
    async with ctx.hub.db.tx([company_id]) as tx:
        reservation = await G.reserve_row(
            tx,
            company_id=company_id,
            actor=who.code,
            run_id=who.run_id,
            entry={
                "tool": body.tool,
                "kind": G.KINDS.get(body.tool, "request"),
                "class": body.cls,
                "method": "BROWSE" if body.tool == "web.browse" else body.method[:10],
                "host": host if body.url else ("searxng" if body.tool == "web.search" else "-"),
            },
        )
    return {
        "max_bytes": max(1, min(ctx.hub.settings.egress_call_bytes, left["bytes"])),
        "requests_left": left["requests"],
        "browser_s_left": max(0, left["browser_s"]),
        "account": acct,
        "reservation": reservation,
    }


@internal_router.post("/egress/log", status_code=204, responses=E)
async def log_entries(body: LogIn, ctx: Ctx = Depends(internal_ctx)) -> None:
    """The entries of one tool call (the gateway, after egress answered)."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    who = ctx.who
    assert who.company is not None
    assert who.company_id is not None
    company_id = who.company_id
    await allow(ctx, "egress.use", {"company": who.company})
    async with ctx.tx() as tx:
        call_id = None
        if body.reservation is not None and await G.own_reservation(
            tx, body.reservation, actor=who.code, run_id=who.run_id
        ):
            call_id = body.reservation
        await G.record(
            tx,
            company_id=company_id,
            actor=who.code,
            run_id=who.run_id,
            entries=[e.model_dump(by_alias=True) for e in body.entries],
            call_id=call_id,
        )
        for e in body.entries:
            await ctx.audit(
                tx,
                company_id=company_id,
                action="egress.request",
                action_class=e.cls,
                target_kind="host",
                target_ref=e.host[:200],
                summary=f"{e.tool} {e.method} {e.status or '-'}"
                + (f" x{e.requests}" if e.requests > 1 else "")
                + (f" blocked: {e.blocked_reason}" if e.blocked_reason else "")
                + f", {e.bytes_in + e.bytes_out} B",
            )


@internal_router.get("/egress/recent", response_model=Page[EgressEntry], responses=E)
async def recent(
    company: str | None = Query(default=None, pattern=CODE),
    actor: str | None = Query(default=None, max_length=60),
    since: datetime | None = None,
    blocked: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    ctx: Ctx = Depends(internal_ctx),
) -> Page[EgressEntry]:
    """egress.recent: the overseer, the security analyst and AI safety (holding scope)."""
    await allow(ctx, "egress.read", {"company": company or ctx.who.company})
    ids = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(ids) as tx:
        return await _entries(
            ctx,
            tx,
            company=company,
            actor=actor,
            since=since,
            blocked=blocked,
            limit=limit,
            cursor=None,
        )
