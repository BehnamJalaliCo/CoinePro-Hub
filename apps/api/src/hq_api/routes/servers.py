"""Company server runners (contract §26 ⟨1.8⟩, prompt 17).

Runner (each company server's `hq-runner`, outbound HTTPS only; the hub never
connects into a company server):
    POST /runners/pair              unauthenticated, rate-limited: a user code
    POST /runners/token             the device code -> 428 until approved, then
                                    the runner's credential, once
    POST /runners/rotate            bearer: a fresh credential (every 24 h)
    GET  /runners/jobs/next         bearer: long-poll ≤ 30 s -> {job, cancel} or 204;
                                    each poll reports `via` and `hub_rtt_ms`
    POST /runners/jobs/{id}/events  bearer: a batch of {seq, type, data}
    POST /runners/jobs/{id}/result  bearer: {exit_code, summary_fa?, usage?, data?, error?}
    POST /runners/classify          bearer: {cmd, job?} -> {category|null, …} (the
                                    Claude Code PreToolUse hook)
    POST /runners/jobs/{id}/files   bearer: ⟨2026-11-09⟩ a file a workspace turn left in
                                    `out/` (raw body), an attachment of its output (§43)
Owner:
    POST   /runners/approve 🔏 server.attach (company:<CODE>)
    DELETE /infra/servers/{id} 🔏 server.detach (<CODE>:<server>)
    GET|POST /infra/servers/{id}/map · GET …/activity · POST …/exec 🔏 (SSE)
    GET …/jobs/{job} · GET …/jobs/{job}/transcript
    GET|PUT /control/server-policy (PUT 🔏 server.policy, SHA-256 of the body)
    GET /infra/network · POST /infra/network/check
Agents (Tool Gateway, /internal/v1): /servers, /servers/{id}/map,
    POST /servers/jobs and GET /servers/jobs/{id} (server.map/exec/read/write/claude);
    ⟨2026-11-09⟩ POST /workshop/runs (workshop.run: any role, the holding's workshop, §43).

A runner's requests run in its own company's scope only (RLS): it never
sees another company's jobs. Its credential is compared by its SHA-256 in
constant time; only the hash is stored.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from hq_api import audit, idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.domain import hands as HANDS
from hq_api.domain import links as LK
from hq_api.domain import order_turns as OT
from hq_api.domain import servers as SV
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.principal import Principal
from hq_api.routes.files import Prepared, Upload, file_name, prepare_file, store_file
from hq_api.routes.internal import action_gate, allow
from hq_api.schemas import FileRef, Model, Page
from hq_api.security import deps, stepup
from hq_api.workshop import domain as W
from hq_api.workshop import server_sessions
from hq_common.tokens import bearer

router = APIRouter(tags=["servers"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
ER = responses(401, 403, 404, 409, 410, 422, 423, 428, 429)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
NAME = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$"
log = logging.getLogger("hq_api.servers")
LONG_POLL_S = 30
POLL_S = 1.0
SSE_POLL_S = 0.3
HEARTBEAT_S = 15.0
PAIR_PER_IP = 10  # a minute
PAIR_ALL = 120
TOKEN_PER_IP = 60
RUNNER_PER_MIN = 600
AGENT_WAIT_S = 20
MAX_READ_BYTES = 20 * 1024 * 1024
AGENT_STDOUT = 12_000  # the tail an agent's tool answer shows (the whole output: a file)
AGENT_STDERR = 4_000
MAX_WRITE_CHARS = 1024 * 1024
HOLDING_SERVER_ROLES = ("hub_platform_sre", "overseer")
FA_AWAITING = "این فرمان ویرانگر است و منتظر مُهر تو ماند."


# ------------------------------------------------------------------ inputs --
class PairIn(Model):
    company: str = Field(pattern=CODE)
    name: str = Field(pattern=NAME)
    hostname: str | None = Field(default=None, max_length=253)
    private_ip: str | None = Field(default=None, max_length=45, pattern=r"^[0-9a-fA-F:.]{2,45}$")
    os: str | None = Field(default=None, max_length=120)
    runner_version: str | None = Field(default=None, max_length=40)
    # ⟨additive⟩ the server's work user the runner runs as (never root)
    user: str | None = Field(default=None, pattern=r"^[a-z_][a-z0-9_.-]{0,31}$")

    @field_validator("user")
    @classmethod
    def _not_root(cls, v: str | None) -> str | None:
        if v == "root":
            raise ValueError("the runner never runs as root")
        return v


class Paired(BaseModel):
    device_code: str
    user_code: str
    expires_in: int
    interval: int


class TokenIn(Model):
    device_code: str = Field(min_length=20, max_length=200)


class RunnerToken(BaseModel):
    runner_token: str
    server_id: UUID | None = None
    rotate_after_s: int = 86400


class ApproveIn(Model):
    user_code: str = Field(min_length=8, max_length=20)


class Approved(BaseModel):
    server: SV.ServerOut


class EventIn(Model):
    seq: int = Field(ge=1, le=2**31 - 1)
    type: Literal["stdout", "stderr", "session_event", "progress"]
    data: Any = None


class EventsIn(Model):
    events: list[EventIn] = Field(max_length=1000)


class ResultIn(Model):
    exit_code: int | None = Field(default=None, ge=-1024, le=1024)
    summary_fa: str | None = Field(default=None, max_length=4000)
    usage: dict[str, Any] | None = None
    # ⟨additive⟩ what a kind returns: map (§26.5), a read's content, a
    # netcheck's links, a publish's {external_id, url}, a claude session id
    data: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=200)


class ClassifyIn(Model):
    cmd: str = Field(min_length=1, max_length=100_000)
    # ⟨additive⟩ the job also comes in the X-HQ-Runner-Job header (the runner's way)
    job: UUID | None = None
    cwd: str | None = Field(default=None, max_length=500)


class ExecIn(Model):
    """§26.5 the owner's terminal (the agents' server.exec too)."""

    cmd: str = Field(min_length=1, max_length=20000)
    cwd: str | None = Field(default=None, max_length=500)
    timeout_s: int = Field(default=600, ge=1, le=3600)
    sudo: bool = False


class ServerPolicy(Model):
    seal_required: list[
        Literal["db_drop", "volume_delete", "backup_delete", "disk_wipe", "access_change",
                "server_delete"]
    ] = Field(max_length=6)  # fmt: skip


class MapOut(BaseModel):
    at: datetime
    map: dict[str, Any]


class JobQueued(BaseModel):
    job: SV.Job


class NetworkNode(BaseModel):
    id: str
    company: str
    name: str
    private_ip: str | None
    via: str | None
    state: str
    hub_rtt_ms: float | None


class NetworkLink(BaseModel):
    model_config = {"populate_by_name": True}
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    port: int
    ok: bool
    ms: float | None
    error: str | None
    at: datetime


class Network(BaseModel):
    at: datetime | None
    nodes: list[NetworkNode]
    links: list[NetworkLink]


class NetworkCheck(BaseModel):
    queued: int
    jobs: list[str]


# ------------------------------------------------------------- runner auth --
def _rtt(value: str | None) -> float | None:
    try:
        v = float(value) if value not in (None, "") else None
    except ValueError:
        return None
    return round(v, 2) if v is not None and 0 <= v < 1e7 else None


async def _wide(hub: Hub) -> list[UUID]:
    return await hub.companies.ids()


async def runner(request: Request, hub: Hub = Depends(get_hub)) -> dict[str, Any]:
    """The calling runner (bearer credential). Every runner request carries
    `X-HQ-Runner-Via`, `X-HQ-Runner-Hub-Rtt-Ms` and `X-HQ-Runner-Version`
    (the long-poll also `?via&hub_rtt_ms`): stored on the server row, and the
    server is online. 401 unauthenticated (pair again); 410 runner_revoked
    once the owner detached the server (the runner stops)."""
    token = bearer(request.headers.get("authorization"))
    if not token or len(token) > 200 or not token.startswith(SV.TOKEN_PREFIX):
        raise ApiError(401, "unauthenticated")
    q = request.query_params
    via = q.get("via") or request.headers.get("x-hq-runner-via")
    rtt = _rtt(q.get("hub_rtt_ms") or request.headers.get("x-hq-runner-hub-rtt-ms"))
    version = (request.headers.get("x-hq-runner-version") or "")[:40] or None
    async with hub.db.tx(await _wide(hub)) as tx:
        r = await SV.runner_by_token(tx, token)
        if r is None:
            revoked = await tx.scalar(
                """SELECT 1 FROM infra.runners WHERE (token_sha256 = :h OR prev_sha256 = :h)
                     AND revoked_at IS NOT NULL""",
                h=SV.token_digest(token),
            )
            if revoked:
                raise ApiError(410, "runner_revoked")
            raise ApiError(401, "unauthenticated")
        hub.limiter.check(f"runner:{r['id']}", max(RUNNER_PER_MIN, hub.settings.rate_per_principal))
        await SV.seen(tx, r, via if via in ("private", "public") else None, rtt, version)
    return r


def _scope(r: dict[str, Any]) -> list[UUID]:
    return [r["company_id"]]


async def _runner_job(tx: Any, r: dict[str, Any], job_id: UUID) -> dict[str, Any]:
    j: dict[str, Any] | None = await tx.first(
        SV.JOB_SQL + " WHERE j.id = :id FOR UPDATE OF j", id=job_id
    )
    if j is None or j["server_id"] != r["server_id"]:
        raise ApiError(404, "not_found", "no such job of this server")
    return j


# ------------------------------------------------------------------ pairing --
@router.post("/runners/pair", response_model=Paired, status_code=201, responses=ER)
async def runner_pair(body: PairIn, request: Request, hub: Hub = Depends(get_hub)) -> Paired:
    """Unauthenticated (contract §26.1 step 1), rate-limited per address: a
    pairing of `company` with a short `user_code` (`ABCD-1234`) the runner
    shows on the server, valid 15 minutes; the owner approves it in the app.
    Nothing secret is shown: the `device_code` is the runner's own."""
    ip = deps.ip_hash(request)
    hub.limiter.check(f"runner-pair:{ip}", PAIR_PER_IP)
    hub.limiter.check("runner-pair:*", PAIR_ALL)
    co = await hub.companies.find(body.company)
    # ⟨2026-11-09⟩ §43 the holding pairs its workshop (a locked-down user on the hub host): every
    # holding server is the workshop; the owner's seal on the pairing is the gate, as for any server
    if co is None or co.kind not in ("company", "holding"):
        raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
    async with hub.db.tx([co.id]) as tx:
        out = await SV.pair(
            tx,
            {"id": co.id, "code": co.code},
            body.model_dump(exclude_none=True, exclude={"company"}),
            ip,
        )
    return Paired(**out)


@router.post("/runners/token", response_model=RunnerToken, responses=ER)
async def runner_token(body: TokenIn, request: Request, hub: Hub = Depends(get_hub)) -> RunnerToken:
    """The runner polls with its device code every `interval` seconds:
    `428 authorization_pending` until the owner approved, then its credential
    `{runner_token, server_id}` exactly once (`410 expired_token` after that,
    or after 15 minutes). Only the credential's SHA-256 is kept."""
    hub.limiter.check(
        f"runner-token:{deps.ip_hash(request)}", max(TOKEN_PER_IP, hub.settings.auth_rate_per_ip)
    )
    try:  # the runner asks every `interval` (5 s): faster than that is slow_down
        hub.limiter.check(f"runner-device:{SV.token_digest(body.device_code)}", 20)
    except ApiError as exc:
        raise ApiError(429, "slow_down", headers={"Retry-After": "5"}) from exc
    async with hub.db.tx(await _wide(hub)) as tx:
        out = await SV.claim_token(tx, body.device_code)
    return RunnerToken(**out)


@router.post("/runners/approve", response_model=Approved, responses=ER)
async def runner_approve(body: ApproveIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `server.attach`, target `company:<CODE>` (the company the runner
    named): the server joins the holding; the runner takes its credential on
    its next poll. `404 invalid_user_code` · `410 expired_token` ·
    `409 code_used`. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        p = await SV.pairing_by_code(tx, body.user_code, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "server.attach", f"company:{p['company']}")
        s = await SV.approve(tx, ctx.who, p, su)
        await ctx.interaction(
            tx,
            company_id=p["company_id"],
            kind="setting",
            action="server.attach",
            target_kind="server",
            target_ref=f"{s['company']}:{s['name']}",
            data={"server": str(s["id"])},
        )
        out = Approved(server=SV.render_server(s))
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.post("/runners/rotate", response_model=RunnerToken, responses=ER)
async def runner_rotate(
    r: dict[str, Any] = Depends(runner), hub: Hub = Depends(get_hub)
) -> RunnerToken:
    """A fresh credential (the runner rotates every 24 h); the previous one
    keeps working for ten minutes, so a lost answer locks nobody out."""
    async with hub.db.tx(_scope(r)) as tx:
        out = await SV.rotate(tx, r)
    return RunnerToken(server_id=r["server_id"], **out)


# -------------------------------------------------------------------- jobs --
@router.get(
    "/runners/jobs/next",
    responses={**ER, 200: {"description": "{job, cancels}"}, 204: {"description": "nothing to do"}},
)
async def runner_next(
    request: Request,
    wait: int = Query(default=LONG_POLL_S, ge=0, le=LONG_POLL_S),
    via: Literal["private", "public"] | None = None,
    hub_rtt_ms: str | None = Query(default=None, max_length=20),
    slots: int = Query(default=1, ge=0, le=16),
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> Any:
    """Long-poll ≤ 30 s: `{job, cancels: [job ids]}` (the jobs it was given
    that were cancelled since: it kills their process group), or 204.
    ⟨1.15⟩ `closed: [{workspace, closed_at}]` (§33.10): the works whose
    workspace folder the runner removes 30 days after their close.
    `slots`: how many more jobs it can run now (0: only cancels). `via` and
    `hub_rtt_ms` (also the X-HQ-Runner-* headers) are stored on the server.
    Nothing new starts while the company is locked."""
    del via, hub_rtt_ms  # read by the runner dependency (documented here for the schema)
    deadline = asyncio.get_running_loop().time() + wait
    # ⟨2026-11-10⟩ the holding's runner is the workshop: it holds works of every company, so its
    # poll reads in every company's view (in its own scope a company's closed work was never seen
    # and no folder was removed, and a locked company's turn could not be told from another's)
    scope = _scope(r)
    if (await hub.companies.holding()).id == r["company_id"]:
        scope = await hub.companies.ids()
    while True:
        async with hub.db.tx(scope) as tx:
            if await tx.scalar(
                "SELECT revoked_at IS NOT NULL FROM infra.runners WHERE id = :id", id=r["id"]
            ):
                raise ApiError(410, "runner_revoked")
            cancels = await SV.cancels_for(tx, r)
            # ⟨2026-11-09⟩ a Claude Code job runs on the hub's account of the moment; both full: it waits
            pick = await SV.runner_claude_pick(tx, hub) if slots > 0 else SV.NO_PICK
            job = await SV.dispatch(tx, r, hold_claude=pick.hold) if slots > 0 else None
            if job is not None and job["kind"] == "claude":
                # ⟨2026-11-11⟩ the account is written on the job: its usage and its rate-limit
                # events are that account's (a turn the limit stopped takes the other one)
                pick = await SV.claim_account(tx, hub, job, pick)
            out = SV.runner_job(job, hub, claude_token=pick.token) if job else None
            # ⟨1.15⟩ §33.10 the works closed since, once each: the runner removes their
            # folders 30 days later (only a runner on 0.3.0 has workspaces)
            closed = await WS.closed_for(tx, r["server_id"])
        if out is not None or cancels or closed:
            return {"job": out, "cancels": cancels, **({"closed": closed} if closed else {})}
        if await request.is_disconnected() or asyncio.get_running_loop().time() >= deadline:
            return Response(status_code=204)
        await asyncio.sleep(POLL_S)


@router.post("/runners/jobs/{id}/events", responses=ER)
async def runner_events(
    id: UUID,
    request: Request,
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> dict[str, Any]:
    """A batch `{events: [{seq, type, data}]}` (or the bare list): stdout and
    stderr `{text}`, a Claude Code `session_event` (a SessionEvent), progress.
    Masked before stored; a seq already stored is ignored. `cancel: true`
    when the job was cancelled meanwhile (kill it)."""
    try:
        raw = json.loads(await request.body() or b"[]")
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"events": "JSON"}) from exc
    items = EventsIn.model_validate(raw if isinstance(raw, dict) else {"events": raw}).events
    async with hub.db.tx(_scope(r)) as tx:
        j = await _runner_job(tx, r, id)
        _still_running(j)
        n = await SV.add_events(tx, j, [e.model_dump() for e in items])
    return {"accepted": n, "state": j["state"]}


def _still_running(j: dict[str, Any]) -> None:
    """409 job_cancelled / job_finished: the runner stops (kills) it."""
    if j["state"] == "cancelled":
        raise ApiError(409, "job_cancelled", "the job was cancelled")
    if j["state"] in SV.FINAL:
        raise ApiError(409, "job_finished", "the job has ended")


@router.post("/runners/jobs/{id}/result", responses=ER)
async def runner_result(
    id: UUID,
    body: ResultIn,
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> dict[str, Any]:
    """The end of a job: `{exit_code, summary_fa?, usage?, data?, error?}`
    (idempotent). `usage` of a claude job goes into the Token Treasury."""
    async with hub.db.tx(_scope(r)) as tx:
        j = await _runner_job(tx, r, id)
        if j["state"] == "cancelled":
            raise ApiError(409, "job_cancelled", "the job was cancelled")
        j = await SV.finish(
            tx,
            hub,
            j,
            exit_code=body.exit_code,
            summary_fa=body.summary_fa,
            usage=body.usage,
            data=body.data if body.data is not None else body.result,
            error=body.error,
        )
    if j.get("requeued_as"):
        # ⟨2026-11-11⟩ the account's usage limit stopped this turn and it runs again on the other
        # account (a new job of the same session and workspace): what follows a turn's end waits
        # for that job
        return {"state": j["state"]}
    if j["actor_code"] == "catalogue" and j["state"] in SV.FINAL:
        from hq_api.domain import catalogue

        await catalogue.after_job(hub, j["id"])  # ⟨1.10⟩ §28.2, after the commit
    elif j["actor_code"] == "secretary" and j["state"] in SV.FINAL:
        from hq_api.domain import dispatch

        await dispatch.after_server_job(hub, j["id"])  # ⟨1.11⟩ §29.8 an inside question
    elif (
        j["kind"] == "claude" and (j.get("args") or {}).get("workspace") and j["state"] in SV.FINAL
    ):
        await WS.after_job(hub, j["id"])  # ⟨1.15⟩ §33.10 a workspace's turn, after the commit
    elif j["kind"] == "netcheck" and j["state"] == "done":
        await SV.after_netcheck(hub, j)  # ⟨1.24⟩ §42.2 an offline server's reason, measured again
    elif j["kind"] == "publish" and (j.get("args") or {}).get("session") and j["state"] in SV.FINAL:
        from hq_api.domain import session_publish as SPB

        await SPB.after_job(hub, j["id"])  # ⟨2026-11-10⟩ §44.5 the session hears its publish
    return {"state": j["state"]}


RAW_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


class ToolCallIn(Model):
    """⟨1.32⟩ §54 one call of a direct session: `name` as the session's tool list gave it."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    args: dict[str, Any] = Field(default_factory=dict)


@router.get("/runners/jobs/{id}/tools", responses=ER, include_in_schema=True)
async def runner_tools(
    id: UUID, r: dict[str, Any] = Depends(runner), hub: Hub = Depends(get_hub)
) -> dict[str, Any]:
    """⟨1.32⟩ §54 The hub's tools a direct session holds, for the runner of that turn's server
    while the turn runs: `{tools: [{name, description, input_schema}]}`: the tools of the
    turn's holder (its role's own, without the workshop's), each with the JSON Schema of its
    input, and `skill_list` / `skill_read` (the roles' guides). `422` for a job that is not a
    direct turn, `404` for another server's job, `409` once it ended."""
    from hq_api.domain import direct as DR

    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await _runner_job(tx, r, id)
        _still_running(j)
        return {"tools": await DR.tools_for(tx, hub, dict(j))}


@router.post("/runners/jobs/{id}/tools/call", responses=ER, include_in_schema=True)
async def runner_tool_call(
    id: UUID,
    body: ToolCallIn,
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> dict[str, Any]:
    """⟨1.32⟩ §54 One tool call of a direct session, relayed by its runner. The hub carries it
    to the Tool Gateway as the turn's holder, for the turn's own run: the gateway reserves the
    call, checks the role's tools and the policy, decides its class and writes its audit row,
    exactly as for any agent. Answers the gateway's outcome `{outcome: ok | denied | error,
    class, code, ref, result?, hint_fa?, fields?}` (always `200`: a refusal is an outcome the
    session reads). `422` for a job that is not a direct turn, `409` once it ended."""
    from hq_api.domain import direct as DR

    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = dict(await _runner_job(tx, r, id))
        _still_running(j)
        turn = DR._turn_of(j)
    # the call itself runs outside the job's row lock (it may take as long as a tool takes)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await DR.call(tx, hub, {**j, "args": turn}, body.name, body.args)


# ⟨2026-11-09⟩ §43 what a turn may send back: everything the owner may upload but fonts
RUNNER_FILE_KINDS = {"video", "image", "audio", "document"}


@router.get("/runners/jobs/{id}/inputs/{file_id}", responses=ER, include_in_schema=True)
async def runner_input(
    id: UUID,
    file_id: UUID,
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> Any:
    """⟨2026-11-10⟩ §43.8: one input file of a workspace turn (the narration, a logo, the owner's
    upload), for the runner of that job's server while the job runs. Only a file the job's own
    `args.inputs` names (checked when the turn was made); `404` for any other, `409` once the job
    ended. The bytes as stored."""
    async with hub.db.tx(_scope(r)) as tx:
        j = await _runner_job(tx, r, id)
        _still_running(j)
    args = j.get("args") or {}
    # a workspace turn's inputs, or ⟨§44.5⟩ the files of a publish the owner tapped in a session
    listed = (
        args.get("inputs")
        if j["kind"] == "claude"
        else args.get("files")
        if j["kind"] == "publish" and args.get("session")
        else None
    )
    named = {str(f.get("file_id")) for f in listed or [] if isinstance(f, dict)}
    if str(file_id) not in named:
        raise ApiError(404, "not_found", "not an input of this job")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        f = await tx.first(
            "SELECT storage_key, mime, size FROM files.files WHERE id = :id AND variant = 'original'",
            id=file_id,
        )
    if f is None:
        raise ApiError(404, "not_found", "no such file")
    path = hub.storage.local_path(f["storage_key"])

    def chunks() -> Any:
        with open(path, "rb") as fh:
            while block := fh.read(1024 * 1024):
                yield block

    return StreamingResponse(
        chunks(),
        media_type=f["mime"],
        headers={"Cache-Control": "no-store", "Content-Length": str(f["size"])},
    )


@router.post(
    "/runners/jobs/{id}/files",
    response_model=FileRef,
    status_code=201,
    responses={**ER, **responses(413, 415)},
    openapi_extra=RAW_BODY,
)
async def runner_file(
    id: UUID,
    request: Request,
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> Any:
    """⟨2026-11-09⟩ §43: a file a workspace turn (a `claude` job with `workspace`) left in `out/`
    of its work's folder, sent while the job still runs (before its result). Raw body as an owner
    upload (`Content-Type`, `X-File-Name`): the type checked by its bytes, the size while it
    streams (video ≤ 200 MB and 10 min, image 20 MB, PDF 30 MB, text and ZIP 50 MB, audio 25 MB).
    The file belongs to the work's company, made by the job's agent (`meta.job`); the job's
    result names it in `data.files` and it becomes an attachment of the turn's output. The same
    bytes twice for one job answer the same file. At most 20 files a job (429). `409` once the
    job ended; `422` for a job that is not a workspace turn of this server."""
    async with hub.db.tx(_scope(r)) as tx:
        j = await _runner_job(tx, r, id)
        _still_running(j)
    ref = (j.get("args") or {}).get("workspace")
    if j["kind"] != "claude" or not isinstance(ref, str):
        raise ApiError(422, "validation_failed", fields={"job": "not a workspace turn"})
    wide = await hub.companies.ids()
    async with hub.db.tx(wide) as tx:
        ws = await tx.first(
            "SELECT company_id FROM work.workspaces WHERE work_ref = :w AND server_id = :s",
            w=ref,
            s=r["server_id"],
        )
    if ws is None:
        raise ApiError(422, "validation_failed", fields={"job": "no workspace of this server"})
    scope = list(dict.fromkeys([r["company_id"], ws["company_id"]]))
    name = file_name(request.headers.get("x-file-name"))
    up = await Upload.receive(request, hub.storage.scratch())
    prep = Prepared()
    follow: str | None = None
    row: dict[str, Any] | None = None
    try:
        if up.kind.kind not in RUNNER_FILE_KINDS:
            raise ApiError(415, "validation_failed", fields={"Content-Type": "not a deliverable"})
        async with hub.db.tx(scope) as tx:
            await tx.exec("SELECT 1 FROM infra.server_jobs WHERE id = :j FOR UPDATE", j=id)
            same = await tx.first(
                """SELECT id FROM files.files WHERE company_id = :co AND variant = 'original'
                     AND meta->>'job' = :j AND sha256 = :sha""",
                co=ws["company_id"],
                j=str(id),
                sha=up.sha256,
            )
            if same is not None:
                return F.render(await F.load(tx, same["id"]))
            n = await tx.scalar(
                """SELECT count(*) FROM files.files WHERE company_id = :co
                     AND variant = 'original' AND meta->>'job' = :j""",
                co=ws["company_id"],
                j=str(id),
            )
            if int(n or 0) >= HANDS.FILES_MAX:
                raise ApiError(429, "rate_limited", f"at most {HANDS.FILES_MAX} files a job")
        prep = await prepare_file(hub, up)
        async with hub.db.tx(scope) as tx:
            j = await _runner_job(tx, r, id)
            _still_running(j)
            fid, follow = await store_file(
                hub, tx, up, name, prep, company_id=ws["company_id"],
                by=("agent", str(j["actor_code"])), meta={"job": str(id), "workspace": ref},
            )  # fmt: skip
            await audit.record(
                tx,
                WS.SERVICE,
                company_id=ws["company_id"],
                action="file.upload",
                action_class="A1",
                target_kind="file",
                target_ref=str(fid),
                summary=f"{up.kind.kind} {up.mime}, {up.size} bytes from {ref}'s turn "
                f"(job {id}, server {r['server_id']})",
            )
            row = await F.load(tx, fid)
    finally:
        up.discard()
        prep.discard()
    assert row is not None
    if follow == "text":  # its text for files.read, outside any transaction
        await asyncio.shield(
            F.extract_text(
                lambda: hub.db.tx(scope),
                row["id"],
                hub.storage.local_path(row["storage_key"]),
                mime=row["mime"],
            )
        )
    elif follow == "workflow":
        from hq_api import workflows_client

        await workflows_client.file_uploaded(hub, str(row["id"]))
    return F.render(row)


@router.post("/runners/classify", responses=ER)
async def runner_classify(
    body: ClassifyIn,
    x_hq_runner_job: UUID | None = Header(default=None),
    r: dict[str, Any] = Depends(runner),
    hub: Hub = Depends(get_hub),
) -> dict[str, Any]:
    """The runner's Claude Code hook asks before each Bash command (§26.3),
    the job in `X-HQ-Runner-Job`: `{category|null, …}`. `category` is set
    only when the command must not run now: its category is in the policy
    and the owner has not sealed it (the `server_destructive` card is raised
    once per server and command; the job waits in `awaiting_seal`). A sealed
    command (within 24 h), a free one or one the policy does not list: null.
    `423 company_locked` under a kill switch, `423 deploy_frozen` for a
    deploy under a freeze (the hook blocks on any error)."""
    hit = SV.classify_detail(body.cmd)
    deploy = SV.is_deploy(body.cmd)
    detail: dict[str, Any] = {
        "category": None,
        "detected": hit[0] if hit else None,
        "pattern": hit[1] if hit else None,
        "deploy": deploy,
        "state": "free",
    }
    job_id = body.job or x_hq_runner_job
    async with hub.db.tx(_scope(r)) as tx:
        await SV.check_lock(tx, r["company_id"], deploy=deploy)
        if hit is None or hit[0] not in await SV.seal_required(tx):
            return detail
        sha = hashlib.sha256(body.cmd.encode()).hexdigest()
        prev = await tx.first(
            """SELECT ref, status FROM cartable.decisions
               WHERE kind = 'server_destructive' AND payload -> 'server' ->> 'id' = :s
                 AND payload ->> 'cmd_sha256' = :h
                 AND (status = 'pending' OR (status = 'approved' AND decided_at > now() - interval '24 hours'))
               ORDER BY created_at DESC LIMIT 1""",
            s=str(r["server_id"]),
            h=sha,
        )
        if prev is not None and prev["status"] == "approved":
            return {**detail, "state": "sealed", "decision_ref": prev["ref"]}
        blocked = {**detail, "category": hit[0], "state": "awaiting_seal"}
        if prev is not None:
            return {**blocked, "decision_ref": prev["ref"]}
        if job_id is None:
            return blocked
        j = await _runner_job(tx, r, job_id)
        if j["state"] in SV.FINAL:
            return blocked
        server = await SV.load_server(tx, j["server_id"])
        j = await SV.raise_seal(
            tx, j, server, hit[0], hit[1], SV.mask(body.cmd)[:4000], cwd=body.cwd,
            cmd_sha256=sha, session_ref=j.get("session_ref"),
        )  # fmt: skip
        if j["session_id"]:
            await tx.exec(
                "UPDATE workshop.sessions SET state = 'waiting_approval' WHERE id = :s AND state = 'working'",
                s=j["session_id"],
            )
            await W.emit_state(tx, await W.load(tx, j["session_id"]))
        return {**blocked, "decision_ref": j["decision_ref"]}


# ------------------------------------------------------------------- owner --
async def _owner_server(tx: Any, id: str) -> dict[str, Any]:
    return await SV.load_server(tx, id)


@router.delete("/infra/servers/{id}", response_model=SV.ServerOut, responses=E)
async def detach_server(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `server.detach`, target `<CODE>:<server>`: the runner's credential
    is revoked at once (it stops on its next poll) and the server's open jobs
    are cancelled. The row and its history stay. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await SV.load_server(tx, id, lock=True)
        su = await stepup.consume(
            tx, request, ctx.who, "server.detach", f"{s['company']}:{s['name']}"
        )
        if s["origin"] != "attached" and s["state"] is None:
            raise ApiError(409, "validation_failed", fields={"server": "has no runner to detach"})
        s = await SV.detach(tx, ctx.who, s, su)
        await ctx.interaction(
            tx,
            company_id=s["company_id"],
            kind="setting",
            action="server.detach",
            target_kind="server",
            target_ref=f"{s['company']}:{s['name']}",
        )
        out = SV.render_server(s)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.get("/infra/servers/{id}/map", response_model=MapOut, responses=E)
async def server_map(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> MapOut:
    """The latest `server.map` (§26.5 shape); 404 before the first."""
    async with ctx.tx() as tx:
        s = await SV.load_server(tx, id)
    if not s["map"] or not s["map_at"]:
        raise ApiError(404, "not_found", "no map yet")
    return MapOut(at=s["map_at"], map=s["map"])


async def _wait_job(hub: Hub, scope: list[UUID], job_id: UUID, wait_s: float,
                    *, until_open: bool = False) -> dict[str, Any]:  # fmt: skip
    """The job once it is finished or waits for a seal (or after `wait_s`)."""
    deadline = asyncio.get_running_loop().time() + wait_s
    while True:
        async with hub.db.tx(scope) as tx:
            j = await SV.load_job(tx, job_id)
        if (
            j["state"] in SV.FINAL
            or j["state"] == "awaiting_seal"
            or (until_open and j["state"] != "queued")
        ):
            return j
        if asyncio.get_running_loop().time() >= deadline:
            return j
        await asyncio.sleep(0.5)


@router.post(
    "/infra/servers/{id}/map",
    response_model=MapOut,
    responses={**E, 202: {"model": JobQueued, "description": "queued; server.state follows"}},
)
async def refresh_server_map(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Queues a `map` job: the map when the runner answers within 10 s,
    else `202 {job}` (the map arrives with the job's server.call)."""
    async with ctx.tx() as tx:
        s = await SV.load_server(tx, id)
        j = await SV.create_job(
            tx, server=s, kind="map", args={}, actor_kind="owner", actor_code="owner",
            summary="نقشه‌ی سرور", timeout_s=300, request_id=ctx.request_id,
        )  # fmt: skip
    j = await _wait_job(ctx.hub, await ctx.scope(), j["id"], 10)
    if j["state"] == "done":
        async with ctx.tx() as tx:
            s = await SV.load_server(tx, id)
        if s["map"] and s["map_at"]:
            return MapOut(at=s["map_at"], map=s["map"])
    return JSONResponse(JobQueued(job=SV.render_job(j)).model_dump(mode="json"), status_code=202)


ACTIVITY_SQL = """
    SELECT * FROM (
        SELECT j.id::text AS id, j.created_at AS at, 'job' AS row_kind, j.id AS job_id,
               j.kind, j.args, j.actor_kind, j.actor_code, j.state, j.summary_fa, j.summary_in,
               j.exit_code, j.created_at, COALESCE(j.started_at, j.dispatched_at) AS started_at,
               j.finished_at, j.transcript_file_id, j.server_id, ws.ref AS session_ref,
               NULL::jsonb AS ev
        FROM infra.server_jobs j LEFT JOIN workshop.sessions ws ON ws.id = j.session_id
        WHERE j.server_id = :s
        UNION ALL
        SELECT j.id::text || ':' || e.seq, e.at, 'command', j.id, 'exec', NULL, j.actor_kind,
               j.actor_code, NULL, NULL, '', NULL, e.at, NULL, NULL, j.transcript_file_id,
               j.server_id, ws.ref, e.data
        FROM infra.server_job_events e JOIN infra.server_jobs j ON j.id = e.job_id
        LEFT JOIN workshop.sessions ws ON ws.id = j.session_id
        WHERE j.server_id = :s AND e.type = 'session_event' AND e.data ->> 'type' = 'command'
    ) x
    WHERE (CAST(:actor AS text) IS NULL OR x.actor_code = :actor)
      AND (CAST(:f AS timestamptz) IS NULL OR x.at >= :f)
      AND (CAST(:t AS timestamptz) IS NULL OR x.at < :t)
      AND (CAST(:ca AS timestamptz) IS NULL OR (x.at, x.id) < (CAST(:ca AS timestamptz), CAST(:cid AS text)))
    ORDER BY x.at DESC, x.id DESC LIMIT :lim
"""


def _activity_row(r: dict[str, Any]) -> SV.ServerCall:
    a = SV.actor_of(r["actor_kind"], r["actor_code"])
    transcript = (
        f"/api/v1/infra/servers/{r['server_id']}/jobs/{r['job_id']}/transcript"
        if r["transcript_file_id"]
        else None
    )
    if r["row_kind"] == "command":
        inner = (r["ev"] or {}).get("data") or {}
        code = inner.get("exit_code")
        secs = inner.get("duration_s")
        return SV.ServerCall(
            id=r["id"],
            at=r["at"],
            actor=a,
            tool="server.exec",
            summary_fa=str((r["ev"] or {}).get("summary_fa") or "")[:500] or None,
            cmd_masked=SV.mask(str(inner.get("cmd") or ""))[:2000],
            exit_code=code if isinstance(code, int) else None,
            duration_ms=int(float(secs) * 1000) if isinstance(secs, int | float) else None,
            session_ref=r["session_ref"],
            transcript_url=transcript,
            server=str(r["server_id"]),
            state="failed" if isinstance(code, int) and code != 0 else "done",
            created_at=r["at"],
        )
    job = {"started_at": r["started_at"], "dispatched_at": None, "finished_at": r["finished_at"]}
    return SV.ServerCall(
        id=r["id"],
        at=r["at"],
        actor=a,
        tool=SV.TOOL_OF.get(r["kind"], "server.exec"),
        kind=r["kind"],
        args=SV.shown_args(r["kind"], r["args"] or {}),
        summary_fa=r["summary_fa"] or r["summary_in"] or SV.KIND_FA.get(r["kind"]),
        cmd_masked=SV.shown_cmd(r["kind"], r["args"] or {}),
        exit_code=r["exit_code"],
        duration_ms=SV.duration_ms(job),
        session_ref=r["session_ref"],
        transcript_url=transcript,
        server=str(r["server_id"]),
        state=r["state"],
        created_at=r["created_at"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
    )


@router.get("/infra/servers/{id}/activity", response_model=Page[SV.ServerCall], responses=E)
async def server_activity(
    id: UUID,
    actor: str | None = Query(default=None, max_length=64),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[SV.ServerCall]:
    """Who did what on the server, newest first: its jobs and every command
    inside its `claude` jobs (masked). `actor`: an employee code or `owner`."""
    after = pagination.decode(cursor, 2)
    async with ctx.tx() as tx:
        s = await SV.load_server(tx, id)
        rows = await tx.all(
            ACTIVITY_SQL,
            s=s["id"],
            actor=actor,
            f=from_,
            t=to,
            ca=after[0] if after else None,
            cid=after[1] if after else None,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return Page(items=[_activity_row(r) for r in items], next_cursor=nxt)


@router.get("/infra/servers/{id}/jobs/{job}", response_model=SV.Job, responses=E)
async def server_job(id: UUID, job: UUID, ctx: Ctx = Depends(owner_ctx)) -> SV.Job:
    """One job of the server (§26.2 shape, its masked arguments, the card
    that holds it, its session, its result and transcript)."""
    async with ctx.tx() as tx:
        j = await SV.load_job(tx, job)
    if j["server_id"] != id:
        raise ApiError(404, "not_found")
    return SV.render_job(j)


@router.get("/infra/servers/{id}/jobs/{job}/transcript", responses=E)
async def server_job_transcript(id: UUID, job: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """Owner only: the job's whole record (JSON lines, masked), stored when it ended."""
    async with ctx.tx() as tx:
        j = await SV.load_job(tx, job)
        if j["server_id"] != id or not j["transcript_file_id"]:
            raise ApiError(404, "not_found", "no transcript yet")
        f = await tx.one(
            "SELECT storage_key, name FROM files.files WHERE id = :id", id=j["transcript_file_id"]
        )
    data = await ctx.hub.storage.get(f["storage_key"])
    return Response(
        data,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'inline; filename="{f["name"]}"',
            "Cache-Control": "no-store",
        },
    )


def _sse(event: str, data: dict[str, Any], seq: int | None = None) -> str:
    head = f"id: {seq}\n" if seq is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/infra/servers/{id}/exec",
    responses={
        **responses(401, 403, 404, 409, 422, 423),
        200: {"content": {"text/event-stream": {}}, "description": "SSE"},
        202: {"description": "awaiting_seal: {decision_ref, message_fa, job}"},
    },
)
async def server_exec(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `server.exec`, target = SHA-256 of the exact body `{cmd, cwd?,
    timeout_s, sudo}`: the owner's own command, as an `exec` job, streamed as
    SSE: `stdout` / `stderr` `{text}`, then `exit` `{code, duration_ms}` (or
    `error` `{code, message}`). A destructive command the policy holds
    answers `202 {decision_ref, message_fa, job}` (the card waits for the
    seal); `423 company_locked` / `deploy_frozen`. Requires `Idempotency-Key`."""
    raw = await request.body()
    try:
        body = ExecIn.model_validate_json(raw or b"{}")
    except ValueError as exc:
        raise ApiError(
            422, "validation_failed", fields={"body": "{cmd, cwd?, timeout_s, sudo}"}
        ) from exc
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            if idem.replay.status_code != 200:
                return idem.replay
            job_id = UUID(json.loads(bytes(idem.replay.body))["job"])
            s = await SV.load_server(tx, id)
        else:
            s = await SV.load_server(tx, id)
            await stepup.consume(
                tx, request, ctx.who, "server.exec", hashlib.sha256(raw).hexdigest()
            )
            j = await SV.create_job(
                tx,
                server=s,
                kind="exec",
                args=body.model_dump(),
                actor_kind="owner",
                actor_code="owner",
                summary="فرمان مدیر کل",
                timeout_s=body.timeout_s,
                request_id=ctx.request_id,
            )
            await ctx.interaction(
                tx,
                company_id=s["company_id"],
                kind="order",
                action="server.exec",
                target_kind="server",
                target_ref=f"{s['company']}:{s['name']}",
                data={"job": str(j["id"]), "chars": len(body.cmd)},
            )
            if j["state"] == "awaiting_seal":
                out = {
                    "decision_ref": j["decision_ref"],
                    "message_fa": FA_AWAITING,
                    "job": str(j["id"]),
                    "category": j["category"],
                }
                if idem:
                    await idem.store(tx, 202, out)
                return JSONResponse(out, status_code=202)
            job_id = j["id"]
            if idem:
                await idem.store(tx, 200, {"job": str(job_id)})
    hub, scope = ctx.hub, await ctx.scope()
    limit_s = body.timeout_s + SV.DISPATCH_GRACE_S + 600  # queued while the runner is away

    async def stream() -> AsyncIterator[str]:
        seq, idle, waited = 0, 0.0, 0.0
        yield ": live\n\n"
        while True:
            if await request.is_disconnected():
                return
            async with hub.db.tx(scope) as tx:
                rows = await tx.all(
                    """SELECT seq, type, data FROM infra.server_job_events
                       WHERE job_id = :j AND seq > :a ORDER BY seq LIMIT 500""",
                    j=job_id,
                    a=seq,
                )
                j = await SV.load_job(tx, job_id)
            for r in rows:
                seq = r["seq"]
                if r["type"] in ("stdout", "stderr"):
                    yield _sse(r["type"], {"text": r["data"].get("text", "")}, seq)
            if rows:
                idle = 0.0
                continue
            if j["state"] in SV.FINAL:
                if j["state"] == "done" or (j["state"] == "failed" and j["exit_code"] is not None):
                    yield _sse("exit", {"code": j["exit_code"], "exit_code": j["exit_code"],
                                        "duration_ms": SV.duration_ms(j)})  # fmt: skip
                else:
                    yield _sse("error", {"code": j["error_code"] or j["state"],
                                         "message": j["summary_fa"] or j["state"]})  # fmt: skip
                return
            if j["state"] == "awaiting_seal":
                yield _sse(
                    "awaiting_seal", {"decision_ref": j["decision_ref"], "message_fa": FA_AWAITING}
                )
                return
            await asyncio.sleep(SSE_POLL_S)
            idle += SSE_POLL_S
            waited += SSE_POLL_S
            if waited >= limit_s:
                yield _sse("error", {"code": "timed_out", "message": "no answer from the server"})
                return
            if idle >= HEARTBEAT_S:
                idle = 0.0
                yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/control/server-policy", response_model=ServerPolicy, responses=E)
async def get_server_policy(ctx: Ctx = Depends(owner_ctx)) -> ServerPolicy:
    """The destructive categories that wait for the owner's seal; everything
    else runs free (contract §26.3)."""
    async with ctx.tx() as tx:
        return ServerPolicy.model_validate({"seal_required": await SV.seal_required(tx)})


@router.put("/control/server-policy", response_model=ServerPolicy, responses=E)
async def put_server_policy(
    body: ServerPolicy, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> ServerPolicy:
    """🔏 `server.policy`, target = SHA-256 of the exact body."""
    wanted = [c for c in SV.CATEGORIES if c in set(body.seal_required)]
    async with ctx.tx() as tx:
        su = await stepup.consume(
            tx, request, ctx.who, "server.policy", await stepup.body_target(request)
        )
        before = await SV.seal_required(tx)
        await tx.exec(
            """UPDATE control.server_policy SET seal_required = :s, updated_at = now(),
                   updated_by_kind = 'owner', updated_by_code = :c, step_up_id = :su WHERE id""",
            s=wanted,
            c=ctx.who.code,
            su=su,
        )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="server.policy",
            action_class="A2",
            target_kind="server_policy",
            target_ref="seal_required",
            summary=f"{','.join(before) or '-'} -> {','.join(wanted) or '-'}",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="server.policy",
            target_kind="server_policy",
            target_ref="seal_required",
            data={"seal_required": wanted},
        )
        await ctx.emit(
            tx, holding.code, "control.changed", "server_policy", {"seal_required": wanted}
        )
    return ServerPolicy.model_validate({"seal_required": wanted})


@router.get("/infra/network", response_model=Network, response_model_by_alias=True, responses=E)
async def infra_network(ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Can every server reach the hub and the others (contract §26.1a)? The
    nodes (the hub and every paired server, with its route and round trip
    to the hub) and the latest result of each link a `netcheck` measured:
    from a server to the hub (443) and to each other server's private
    address (443, 80; SSH between servers is not a path of the work)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        out = await SV.network(tx, SV.hub_ip(), holding.code)
    return Network.model_validate(out)


@router.post("/infra/network/check", response_model=NetworkCheck, status_code=202, responses=E)
async def infra_network_check(ctx: Ctx = Depends(owner_ctx)) -> NetworkCheck:
    """A `netcheck` job on every online runner now (read-only, free); the
    results arrive with each job's server.call and in GET /infra/network."""
    async with ctx.tx() as tx:
        jobs = await SV.queue_netchecks(tx, SV.hub_ip(), ctx.who)
    return NetworkCheck(queued=len(jobs), jobs=[str(j["id"]) for j in jobs])


# --------------------------------------------------------------- the agents --
class AgentJobIn(Model):
    """server.map / exec / read / write / claude (contract §26.2)."""

    kind: Literal["map", "exec", "read", "write", "claude"]
    server: str = Field(min_length=1, max_length=63)
    company: str | None = Field(default=None, pattern=CODE)
    args: dict[str, Any] = Field(default_factory=dict)
    # a cross-company request the server's company accepted (the agent's own work item)
    via_work: str | None = Field(default=None, pattern=r"^W-[0-9]{6,}$")
    wait_s: int = Field(default=AGENT_WAIT_S, ge=0, le=20)


class ExecArgs(Model):
    cmd: str = Field(min_length=1, max_length=20000)
    cwd: str | None = Field(default=None, max_length=500)
    timeout_s: int = Field(default=600, ge=1, le=3600)
    sudo: bool = False


class ReadArgs(Model):
    path: str = Field(min_length=1, max_length=1000)
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)


class WriteArgs(Model):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=MAX_WRITE_CHARS)
    encoding: Literal["utf8", "base64"] = "utf8"
    mode: str | None = Field(default=None, pattern=r"^0?[0-7]{3}$")


class ClaudeArgs(Model):
    brief: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    cwd: str | None = Field(default=None, max_length=500)


class MapArgs(Model):
    pass


ARGS: dict[str, type[Model]] = {
    "exec": ExecArgs,
    "read": ReadArgs,
    "write": WriteArgs,
    "claude": ClaudeArgs,
    "map": MapArgs,
}
OP_OF = {"map": "server.read", "read": "server.read", "exec": "server.run", "write": "server.run",
         "claude": "server.run"}  # fmt: skip


class AgentJob(BaseModel):
    job: SV.Job
    # stdout/stderr (their tails; `stdout_chars`/`stderr_chars` and, once the
    # job ended, `full_output_file`: everything, for files.read)
    output: dict[str, Any] | None = None
    map: dict[str, Any] | None = None
    hint_fa: str | None = None


def _agent(ctx: Ctx) -> Principal:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    return ctx.who


def _holding_power(who: Principal) -> bool:
    return who.scope == "holding" and who.charter in HOLDING_SERVER_ROLES


TECH_DEPARTMENT = "TECH"


def _technical(lib: Any, charter: str | None) -> bool:
    """⟨2026-11-08⟩ H1: a company's technical role, read from the charters (the TECH department's:
    cto, devops_engineer, sre, lead_developer), never a hardcoded company."""
    c = lib.get(charter) if lib is not None and charter else None
    return c is not None and c.department == TECH_DEPARTMENT and c.scope == "company"


async def _reachable(ctx: Ctx, tx: Any, who: Principal, company_id: UUID) -> bool:
    """⟨2026-11-08⟩ H1 (the owner: «مگه نگفتم همه شرکت‌ها به هم راه داشته باشند»): another
    company's servers are within a technical role's reach by the rule of linked.read and
    work.create (audit B4): while the owner does not enforce links, any active operating company;
    while he does, one sharing an `on` link, or one present in the session of the run's order."""
    from hq_api.routes.internal import _session_companies

    co = await tx.first("SELECT code, kind, status FROM core.companies WHERE id = :c", c=company_id)
    if co is None or co["kind"] != "company" or co["status"] != "active":
        return False
    if not await LK.enforced(tx):
        return True
    assert who.company_id is not None
    if await LK.linked(tx, who.company_id, company_id):
        return True
    return str(co["code"]) in await _session_companies(ctx, None)


async def _reach_ids(ctx: Ctx, tx: Any, who: Principal) -> list[UUID]:
    """The companies whose servers `server.map` lists for this agent (H1)."""
    assert who.company_id is not None
    ids: list[UUID] = [who.company_id]
    if not _technical(ctx.hub.charters, who.charter):
        return ids
    if not await LK.enforced(tx):
        rows = await tx.all(
            "SELECT id FROM core.companies WHERE kind = 'company' AND status = 'active'"
        )
        return list({*ids, *(r["id"] for r in rows)})
    linked = await LK.links_of(tx, who.company_id)
    codes = {str(x["company"]) for x in linked} | await _session_companies_safe(ctx)
    if codes:
        rows = await tx.all(
            """SELECT id FROM core.companies WHERE code = ANY(:c) AND kind = 'company'
                 AND status = 'active'""",
            c=sorted(codes),
        )
        ids += [r["id"] for r in rows]
    return list(dict.fromkeys(ids))


async def _session_companies_safe(ctx: Ctx) -> set[str]:
    from hq_api.routes.internal import _session_companies

    try:
        return await _session_companies(ctx, None)
    except Exception:  # noqa: BLE001 - a listing never fails on the session lookup
        return set()


async def _authorize(ctx: Ctx, tx: Any, server: dict[str, Any], kind: str,
                     via_work: str | None) -> tuple[str, str, str | None, str]:  # fmt: skip
    """Who the job runs as (kind, code), on whose behalf, and how it is
    allowed: its own company's server; any server for the holding's platform
    SRE and the overseer; another company's server only through a
    cross-company request that company's CEO accepted (the job then runs as
    that CEO). Everything else: 403 policy_denied (other_company)."""
    who = _agent(ctx)
    lib = ctx.hub.charters
    if (
        lib is not None
        and lib.get(who.charter) is not None
        and f"server.{kind}" not in lib.allowed(who.charter)
    ):
        raise ApiError(403, "policy_denied", f"server.{kind} is not in the charter")
    if server["company_id"] == who.company_id:
        return "agent", who.code, None, "own"
    if _holding_power(who):
        return "agent", who.code, None, "holding"
    if _technical(lib, who.charter) and await _reachable(ctx, tx, who, server["company_id"]):
        # ⟨2026-11-08⟩ H1: a technical role on another company's server, as on its own (the
        # destructive classification and the owner's seal unchanged; the job audited on both)
        return "agent", who.code, None, "linked"
    if not via_work:
        raise ApiError(403, "policy_denied", "other_company: a cross-company request first")
    row = await tx.first(
        """SELECT e.code AS ceo FROM work.work mine
           JOIN work.work req ON req.requested_by_work_id = mine.id
           JOIN core.employees e ON e.id = req.assignee_id
           WHERE mine.ref = :w AND mine.company_id = :me AND mine.assignee_id = :emp
             AND req.company_id = :co AND e.kind = 'ceo' AND req.accepted_at IS NOT NULL
             AND req.status IN ('in_progress', 'waiting')
           ORDER BY req.created_at DESC LIMIT 1""",
        w=via_work,
        me=who.company_id,
        emp=who.employee_id,
        co=server["company_id"],
    )
    if row is None:
        raise ApiError(
            403, "policy_denied", "other_company: no request of yours that company's CEO accepted"
        )
    return "agent", str(row["ceo"]), who.code, "accepted_request"


def _agent_view(
    j: dict[str, Any], rows: list[dict[str, Any]], s: dict[str, Any] | None
) -> AgentJob:
    out = None
    if rows:
        so = "".join(r["data"].get("text", "") for r in rows if r["type"] == "stdout")
        se = "".join(r["data"].get("text", "") for r in rows if r["type"] == "stderr")
        out = {
            "stdout": so[-AGENT_STDOUT:],
            "stderr": se[-AGENT_STDERR:],
            "stdout_chars": len(so),
            "stderr_chars": len(se),
        }
        res = j.get("result") or {}
        whole = res.get("output_file") or (
            str(j["transcript_file_id"]) if j.get("transcript_file_id") else None
        )
        if whole and (len(so) > AGENT_STDOUT or len(se) > AGENT_STDERR or res.get("output_file")):
            out["full_output_file"] = whole  # ⟨1.10.1⟩ nothing is lost: the whole output
    hint = None
    if j["state"] == "awaiting_seal":
        hint = f"این کار ویرانگر است و منتظر مُهر مدیر کل ماند ({j['decision_ref']}); بعداً با job وضعش را ببین."
    elif j["state"] in ("queued", "running"):
        hint = "کار هنوز تمام نشده؛ با همین job دوباره بپرس."
    return AgentJob(
        job=SV.render_job(j),
        output=out,
        map=(s or {}).get("map") if j["kind"] == "map" and j["state"] == "done" else None,
        hint_fa=hint,
    )


async def _agent_scope(ctx: Ctx) -> list[UUID]:
    who = _agent(ctx)
    if _holding_power(who):
        return await ctx.hub.companies.ids()
    return [who.company_id]  # type: ignore[list-item]


@internal_router.get("/servers", response_model=list[SV.ServerOut], responses=E)
async def agent_servers(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(internal_ctx)
) -> list[SV.ServerOut]:
    """server.map without a server: the servers the agent may work on."""
    who = _agent(ctx)
    await allow(ctx, "server.read", {"company": company or who.company, "charter": who.charter,
                                     "via": None})  # fmt: skip
    # ⟨2026-11-08⟩ H1: a technical role sees the other companies' servers it may work on too
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        scope = wide if _holding_power(who) else await _reach_ids(ctx, tx, who)
    async with ctx.hub.db.tx(scope) as tx:
        rows = await tx.all(
            SV.SERVER_SQL
            + " WHERE s.state IS NOT NULL AND (CAST(:co AS text) IS NULL OR c.code = :co) ORDER BY c.code, s.name",
            co=company,
        )
    return [SV.render_server(r) for r in rows]


@internal_router.post("/servers/jobs", response_model=AgentJob, status_code=201, responses=ER)
async def agent_job(body: AgentJobIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """A job on a company server for the calling agent, then waits up to
    `wait_s` (≤ 20) for it: finished, waiting for the seal, or still running
    (ask again with GET /servers/jobs/{id}). A `claude` job opens a
    CodeSession (`runtime: company_server`). Requires `Idempotency-Key`."""
    who = _agent(ctx)
    try:
        args = ARGS[body.kind].model_validate(body.args).model_dump(exclude_none=True)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"args": str(exc)[:200]}) from exc
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        server = await SV.load_server(tx, body.server, company=body.company or who.company)
        ak, ac, behalf, via = await _authorize(ctx, tx, server, body.kind, body.via_work)
    await allow(
        ctx, OP_OF[body.kind], {"company": server["company"], "charter": who.charter, "via": via}
    )
    scope = list({who.company_id, server["company_id"]})
    async with ctx.hub.db.tx(scope) as tx:
        idem = await idempotency.claim(tx, request, who, required=True)
        if idem and idem.replay:
            return idem.replay
        server = await SV.load_server(tx, server["id"])
        if body.kind == "claude":
            _, j = await server_sessions.open_session(
                tx,
                who,
                server=server,
                driver=ac,
                title=str(args.get("title") or args["brief"][:120]),
                brief=args["brief"],
                cwd=args.get("cwd"),
                actor=(ak, ac),
                on_behalf=behalf,
                work_ref=body.via_work,
                request_id=ctx.request_id,
                holding_driver=via == "holding",
            )
        else:
            j = await SV.create_job(
                tx,
                server=server,
                kind=body.kind,
                args=args,
                actor_kind=ak,
                actor_code=ac,
                on_behalf=behalf,
                work_ref=body.via_work,
                summary=f"{SV.KIND_FA[body.kind]} ({who.code})",
                timeout_s=int(args.get("timeout_s") or 600),
                request_id=ctx.request_id,
            )
        if via == "linked":
            # ⟨2026-11-08⟩ H1: the job on both companies' trails (the server's row holds it)
            for co_id in scope:
                await audit.record(
                    tx,
                    who,
                    company_id=co_id,
                    action=f"server.{body.kind}",
                    action_class="A0" if body.kind in ("map", "read") else "A2",
                    target_kind="server",
                    target_ref=f"{server['company']}:{server['name']}",
                    summary=f"{who.code} on {server['company']}'s server via linked, job {j['id']}",
                )
        if idem:
            await idem.store(tx, 201, {"job": {"id": str(j["id"])}, "replayed": True})
    return await _agent_wait(ctx, scope, j["id"], body.wait_s)


async def _agent_wait(ctx: Ctx, scope: list[UUID], job_id: UUID, wait_s: int) -> AgentJob:
    j = await _wait_job(ctx.hub, scope, job_id, wait_s)
    async with ctx.hub.db.tx(scope) as tx:
        rows = await tx.all(
            """SELECT type, data FROM infra.server_job_events WHERE job_id = :j
                 AND type IN ('stdout', 'stderr') ORDER BY seq""",
            j=job_id,
        )
        s = await SV.load_server(tx, j["server_id"]) if j["kind"] == "map" else None
    return _agent_view(j, rows, s)


@internal_router.get("/servers/jobs/{id}", response_model=AgentJob, responses=ER)
async def agent_get_job(
    id: UUID, wait_s: int = Query(default=0, ge=0, le=20), ctx: Ctx = Depends(internal_ctx)
) -> AgentJob:
    """A job the agent started (or of its company), waiting up to `wait_s`."""
    who = _agent(ctx)
    await allow(ctx, "server.read", {"company": who.company, "charter": who.charter, "via": None})
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        j = await tx.first(SV.JOB_SQL + " WHERE j.id = :id", id=id)
    if j is None or not (
        j["company_id"] == who.company_id
        or j["on_behalf_code"] == who.code
        or j["actor_code"] == who.code  # H1: a technical role's own job on another company's server
        or _holding_power(who)
    ):
        raise ApiError(403, "policy_denied", "server.read_not_permitted")
    return await _agent_wait(ctx, list({who.company_id, j["company_id"]}), id, wait_s)  # type: ignore[arg-type]


class WorkshopRunIn(Model):
    """⟨2026-11-09⟩ workshop.run (contract §43): the ask, for the run's work or `work`."""

    brief: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{6,}$")
    # ⟨2026-11-10⟩ the plan task this turn is for: required in a step-by-step order («با من»)
    task: int | None = Field(default=None, ge=1, le=99)
    # ⟨2026-11-10⟩ hub files the turn takes with it (the narration, a logo, the owner's uploads of
    # the session): downloaded by the runner into `in/` of the work's folder
    files: list[UUID] = Field(default_factory=list, max_length=10)
    # ⟨1.31⟩ §53 how hard the turn thinks; left out: the most the model can (`max`)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


class WorkshopStopIn(Model):
    """⟨2026-11-10⟩ workshop.stop: the caller's own turn (its run's work, or `work`)."""

    work: str | None = Field(default=None, pattern=r"^W-[0-9]{6,}$")
    reason: str | None = Field(default=None, max_length=300)


class WorkshopStopped(BaseModel):
    work_ref: str
    stopped: bool  # false: no turn of that work was running
    job: str | None = None


async def _workshop_gate(ctx: Ctx, who: Any, server: dict[str, Any]) -> None:
    """Who may (hq.internal: any working role, only on the holding's workshop), then the action
    gate by the tool's own name: `workshop.run` is every working kind's A2, `server.run` is not
    (the advisor, the assistant and QC were refused here)."""
    await ctx.hub.policy.require(
        "internal",
        {
            "principal": who.opa(),
            "op": "server.run",
            "target": {"company": server["company"], "charter": who.charter, "via": "workshop"},
        },
    )
    await action_gate(ctx.hub, who, "workshop.run", "A2", escrow_classes=[])


@internal_router.post("/workshop/stop", response_model=WorkshopStopped, responses=ER)
async def workshop_stop(body: WorkshopStopIn, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """⟨2026-11-10⟩ workshop.stop (contract §43.6): the caller stops the workshop turn of its own
    work (its run's work, or `work`, assigned to it). The owner: the holder had started a turn
    he had not asked for and could only answer «نمیتوانم متوقفش کنم». The turn's process is killed
    by the runner on its next poll; the workspace stays (a later `workshop.run` goes on in the
    same folder, a fresh session). `stopped: false` when nothing was running."""
    who = _agent(ctx)
    if who.role == "system":
        raise ApiError(403, "policy_denied", "a working role only")
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        server = await HANDS.workshop_server(tx)
        if server is None:
            raise ApiError(409, "workshop_unavailable")
    await _workshop_gate(ctx, who, server)
    async with ctx.hub.db.tx(wide) as tx:
        w = await HANDS.the_work(tx, who, body.work, closed_ok=True)
        return await HANDS.stop_turn(tx, who, w, body.reason, request_id=ctx.request_id)


@internal_router.post(
    "/workshop/runs",
    response_model=HANDS.WorkshopRun,
    status_code=201,
    responses={**ER, 200: {"description": "a turn still runs (`state: working`)"}},
)
async def workshop_run(
    body: WorkshopRunIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """⟨2026-11-09⟩ The workshop (contract §43; the owner: «سرور کامپیوتر است»): any working
    agent of any company hands a task with no tool of its own to Claude Code on the holding's
    workshop server, for its run's work item (or `work`, assigned to it). Answers at once:
    `201 {job, work_ref, state: starting, turn, path, server}`; `200` with `state: working` while
    a turn of that work still runs (nothing new starts). ⟨2026-11-10⟩ In a step-by-step order
    («با من») with a plan, `task` must be the plan's next open task: `409 not_next_step` names
    it. The turn's answer and `out/` files come back as an output of the work.
    `409 workshop_unavailable` (no paired workshop on runner ≥ 0.3.2, or it is not online now),
    `409 workshop_stopped` (the owner stopped it), `409 workspace_elsewhere` (the work runs on
    its company's own server), `409 work_closed`. Requires `Idempotency-Key`."""
    who = _agent(ctx)
    if who.role == "system":
        raise ApiError(403, "policy_denied", "a working role only")
    wide = await ctx.hub.companies.ids()
    async with ctx.hub.db.tx(wide) as tx:
        server = await HANDS.workshop_server(tx)
        if server is None:
            raise ApiError(409, "workshop_unavailable")
        w = await HANDS.the_work(tx, who, body.work)
        # ⟨2026-11-10⟩ «با من»: only the plan's next open task starts, and the caller names it
        nxt = await OT.step_next(tx, w["id"])
        if nxt is not None and body.task != nxt["n"]:
            raise ApiError(
                409,
                "not_next_step",
                fields={
                    "task": f"the plan's next open task is {nxt['n']}: {nxt['title_fa'][:160]}"
                },
            )
    if SV.state_of(server) != "online":
        # ⟨2026-11-10⟩ said at once, not a turn that waits in a queue nobody reads
        raise ApiError(409, "workshop_unavailable")
    await _workshop_gate(ctx, who, server)
    scope = list(dict.fromkeys([who.company_id, server["company_id"], w["company_id"]]))
    async with ctx.hub.db.tx(scope) as tx:
        idem = await idempotency.claim(tx, request, who, required=True)
        if idem and idem.replay:
            return idem.replay
        server = await SV.load_server(tx, server["id"])
        out = await HANDS.start(
            tx, who, server, w, brief=body.brief, title=body.title, request_id=ctx.request_id,
            files=body.files, effort=body.effort,
        )  # fmt: skip
        status = 200 if out.state == "working" else 201
        if idem:
            await idem.store(tx, status, out.model_dump(mode="json"))
    return JSONResponse(out.model_dump(mode="json"), status_code=status)


async def loop(hub: Hub) -> None:
    """The api's background sweep: runners that stopped polling go offline;
    a dispatched job past its timeout fails."""
    while True:
        await asyncio.sleep(30)
        ended: list[UUID] = []
        with contextlib.suppress(Exception):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await SV.sweep(tx, ended=ended)
        for jid in ended:
            # ⟨2026-11-10⟩ a workspace turn the sweep failed (its hour passed, its server went
            # away) ends like any other: the workspace is marked, the work's assignee is told
            try:
                await WS.after_job(hub, jid)
                # ⟨§44.5⟩ a session's publish that timed out is said in its session too
                from hq_api.domain import session_publish as SPB

                await SPB.after_job(hub, jid)
            except Exception:  # noqa: BLE001 - one job never stops the sweep
                log.warning("after_job failed for a swept job", extra={"job": str(jid)})
        # ⟨§46⟩ publications IG-Hub still holds (set for a time, or being prepared) are asked about
        with contextlib.suppress(Exception):
            from hq_api.domain import session_publish as SPB

            await SPB.follow_up(hub)
