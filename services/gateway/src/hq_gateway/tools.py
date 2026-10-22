"""The tools of agents/tools.md, each validated and carried out through the
internal API with the run's own agent token (so RLS, OPA and audit are the
api's, as for any agent call). Inputs are Pydantic models (extra keys are
refused, so a model learns the exact shape; numbers of budgets and quotas
are strict: a JSON true is not a token count); text an agent writes is
redacted before it leaves, never shortened.

A tool returns a Result: outcome ok | denied | error, a stable `code` on
anything but ok, a `ref` (W-…, D-…, O-…, the message ref, ...), the data
for the model (redacted again by the gateway) and, on a refusal, the api's
short Persian explanation (`hint_fa`) so the model knows what to do instead.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from hq_common.redact import MAX_DEPTH, redact_async, scrub

WORK_REF = r"^W-[0-9]{6,}$"
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
THREAD = r"^(A|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"
UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
MIME_OK = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$")
NS = uuid.UUID("6a0f1c3e-5b7d-4e21-9c3a-0d7f2b6e8a41")  # idempotency keys per action
HINT_CHARS = 300

# Budgets and quotas: strict (a JSON true or "50000" is not a number) and never negative.
Tokens = Annotated[StrictInt, Field(ge=0)]
Usd = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]  # inf/nan: invalid_args


@dataclass
class Result:
    outcome: Literal["ok", "denied", "error"]
    code: str | None = None
    ref: str | None = None
    data: Any = None
    fields: dict[str, str] = field(default_factory=dict)
    hint_fa: str | None = None


@dataclass
class Call:
    """One tool call in context: the run's token and gate, the step, the action index."""

    token: str
    gate: dict[str, Any]
    step: int
    index: int
    cls: str = "A0"  # the call's own class (per call for an `A0/A2` tool)

    def idem(self, tool: str) -> str:
        return str(uuid.uuid5(NS, f"{self.gate['run_id']}:{self.step}:{self.index}:{tool}"))


class Api:
    """The internal API (api:8000), always with the agent's token."""

    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        egress: Any = None,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self.egress = egress  # hq_gateway.web.Egress (the internet tools); None = not wired

    async def aclose(self) -> None:
        await self._http.aclose()
        if self.egress is not None:
            await self.egress.aclose()

    async def upload(
        self,
        path: str,
        token: str,
        content: bytes,
        content_type: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """A raw-body upload (an agent file) with the agent's token."""
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": content_type,
        }
        return await self._http.post(path, content=content, params=params, headers=headers)

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        idem: str | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}", "X-Request-ID": str(uuid.uuid4())}
        if idem:
            headers["Idempotency-Key"] = idem
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._http.request(method, path, json=json, params=clean, headers=headers)


def from_response(resp: httpx.Response, ref_key: str | None = "ref") -> Result:
    """The api's answer as a tool result (problem+json -> denied/error + code,
    the field errors and the Persian explanation, all scrubbed)."""
    try:
        body: Any = resp.json()
    except ValueError:
        body = None
    if resp.status_code < 300:
        ref = None
        if ref_key and isinstance(body, dict):
            ref = body.get(ref_key) if isinstance(body.get(ref_key), str) else None
        return Result("ok", ref=ref, data=body)
    problem = body if isinstance(body, dict) else {}
    code = problem.get("code")
    fields = problem.get("fields")
    hint = problem.get("message_fa")
    denied = resp.status_code in (401, 403, 423, 429)
    if resp.status_code == 401:
        code = "run_not_running"  # the agent token is accepted only while its run runs
    return Result(
        "denied" if denied else "error",
        code=str(code or f"http_{resp.status_code}"),
        fields={scrub(str(k))[:60]: scrub(str(v))[:200] for k, v in fields.items()}
        if isinstance(fields, dict)
        else {},
        hint_fa=scrub(hint)[:HINT_CHARS] if isinstance(hint, str) and hint.strip() else None,
    )


# ------------------------------------------------------------------ inputs --
class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(In):
    pass


class WorkRef(In):
    ref: str = Field(pattern=WORK_REF)


class FileIn(In):
    file_id: str = Field(pattern=UUID_RE)
    # What to look at (agents/tools.md): the picture as the model may see it
    # (an image's agent copy, a video's key frames), its small thumb, or a
    # video's poster frame only.
    variant: Literal["original", "thumb", "poster"] = "original"


MCP_SERVER = r"^[a-z][a-z0-9-]{1,39}$"
MCP_TOOL = r"^[A-Za-z0-9_][A-Za-z0-9_.:/-]{0,127}$"


class McpCallIn(In):
    """mcp.call (class `per tool`): one tool of an MCP server the owner enabled."""

    server: str = Field(pattern=MCP_SERVER)
    tool: str = Field(pattern=MCP_TOOL)
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def _small(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v, ensure_ascii=False, default=str)) > 20_000:
            raise ValueError("at most 20000 characters of arguments")
        return v


class CompanyIn(In):
    company: str | None = Field(default=None, pattern=CODE)


class SitesIn(CompanyIn):
    since: datetime | None = None


class UsageIn(In):
    scope: str = Field(default="company", pattern=r"^(company|holding|[A-Z][A-Z0-9]{1,9})$")
    period: Literal["day", "month"] = "month"


class SearchIn(In):
    q: str = Field(min_length=2, max_length=200)
    kinds: list[Literal["resolutions", "deliverables", "decisions", "work", "messages"]] | None = (
        None
    )


class AuditIn(CompanyIn):
    action: str | None = Field(default=None, pattern=r"^[a-z_]+(\.[a-z_]+)?$")
    since: datetime | None = None


class GithubIn(In):
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
    what: Literal["commits", "issues", "pulls", "file"]
    path: str | None = Field(default=None, max_length=500)

    @field_validator("path")
    @classmethod
    def _relative_path(cls, v: str | None) -> str | None:
        # A file inside the repo only: no "..", no absolute path, no tricks.
        if v is not None and (
            v.startswith("/") or "\\" in v or "\x00" in v or ".." in v.split("/")
        ):
            raise ValueError("a relative path inside the repository")
        return v


class EvidenceIn(In):
    kind: Literal["deliverable", "link", "metric", "log"]
    ref: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class DeliverIn(In):
    work_ref: str = Field(pattern=WORK_REF)
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=200_000)
    evidence: list[EvidenceIn] = Field(default_factory=list, max_length=50)


class QuotaIn(In):
    tokens: Tokens | None = None
    usd: Usd | None = None


class ProposeIn(In):
    kind: Literal[
        "hire",
        "dismissal",
        "recurring_approval",
        "deploy",
        "a3_action",
        "proposal",
        "budget_change",
        "evaluation",
    ]
    title_fa: str = Field(min_length=1, max_length=300)
    what_md: str = Field(default="", max_length=20000)
    why_md: str = Field(default="", max_length=20000)
    risk: Literal["low", "medium", "high"] = "low"
    reversible: bool = True
    quota_estimate: QuotaIn | Tokens | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_depth(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Refused, never flattened: the payload leaves exactly as written (scrubbed only).
        if _depth(v) > MAX_DEPTH:
            raise ValueError(f"payload nested deeper than {MAX_DEPTH} levels")
        return v


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


class LinksIn(In):
    decision: str | None = Field(default=None, max_length=20)
    work: str | None = Field(default=None, max_length=20)
    resolution: str | None = Field(default=None, max_length=20)
    corrects: str | None = Field(default=None, max_length=40)


class CitationIn(In):
    kind: Literal["decision", "resolution", "deliverable", "work", "message", "audit"]
    ref: str = Field(min_length=1, max_length=40)


class OwnerMessageIn(In):
    body_md: str = Field(min_length=1, max_length=20000)
    links: LinksIn | None = None


class ThreadMessageIn(In):
    thread: str = Field(pattern=THREAD)
    body_md: str = Field(min_length=1, max_length=50000)
    links: LinksIn | None = None
    citations: list[CitationIn] = Field(default_factory=list, max_length=50)


class MemoryIn(In):
    note_md: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [t[:40] for t in v if t.strip()]


class AcceptIn(In):
    ref: str = Field(pattern=WORK_REF)
    note: str | None = Field(default=None, max_length=2000)


class ProgressIn(In):
    ref: str = Field(pattern=WORK_REF)
    note: str = Field(min_length=1, max_length=2000)
    pct: int | None = Field(default=None, ge=0, le=100)


class FailIn(In):
    ref: str = Field(pattern=WORK_REF)
    reason: str = Field(min_length=1, max_length=2000)
    decline: bool = False


class BudgetIn(In):
    tokens: Tokens | None = None
    usd: Usd | None = None


class DelegateIn(In):
    ref: str = Field(pattern=WORK_REF)
    to: str = Field(pattern=EMP)
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=50000)
    budget: BudgetIn | Tokens | None = None


class RequestIn(In):
    to: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+(-[A-Z0-9]+)?)?$")
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=50000)


class ActivityIn(In):
    state: Literal["working", "waiting", "idle"]
    note: str | None = Field(default=None, max_length=500)


class LinkIn(In):
    kind: str = Field(pattern=r"^[a-z_]{2,30}$")
    ref: str = Field(min_length=1, max_length=100)


class NotifyIn(In):
    level: Literal["urgent", "decision", "report", "info", "learning"]
    category: Literal["service_down", "security", "data_loss", "budget_hard_stop"] | None = None
    title_fa: str = Field(min_length=1, max_length=300)
    body_fa: str = Field(default="", max_length=4000)
    link: LinkIn | None = None


# ------------------------------------------------------------ the tools ---
Handler = Callable[[Api, Call, Any], Awaitable[Result]]


async def _text(value: Any) -> Any:
    """Outgoing text of a write tool, redacted (a key or a customer's data the
    model may have echoed never leaves) and never shortened: the input models
    already refuse anything above the contract's caps (invalid_args), so no
    deliverable, message, proposal or payload is cut on its way out. A large
    text is scrubbed in a worker thread."""
    return await redact_async(value)


async def _work_id(api: Api, call: Call, ref: str) -> tuple[str | None, Result | None]:
    resp = await api.request("GET", f"/internal/v1/work/ref/{ref}", call.token)
    r = from_response(resp, None)
    if r.outcome != "ok":
        return None, r
    if not isinstance(r.data, dict) or not isinstance(r.data.get("id"), str):
        return None, Result("error", code="api_bad_answer")
    return str(r.data["id"]), None


async def work_get(api: Api, call: Call, a: WorkRef) -> Result:
    return from_response(await api.request("GET", f"/internal/v1/work/ref/{a.ref}", call.token))


# What files.read shows of a FileRef (contract §17.1): never its name or hash
# (a model sees no file name it did not need), nor a variant it cannot use.
FILE_FIELDS = (
    "id",
    "mime",
    "size",
    "kind",
    "status",
    "width",
    "height",
    "duration_s",
    "transcript",
    "text",
)
MAX_VIEW_IMAGES = 13  # a video's poster and its (up to 12) key frames


async def files_read(api: Api, call: Call, a: FileIn) -> Result:
    """A file of the agent's own company (the api checks the tenant): its
    metadata and transcript, and `view.image_file_ids`, the pictures the runner
    attaches to the next step as vision input (an image itself; a video's key
    frames). Raw video or audio never reaches a model (prompt 06 §2)."""
    r = from_response(
        await api.request("GET", f"/internal/v1/files/{a.file_id}/meta", call.token), None
    )
    if r.outcome != "ok":
        return r
    d = r.data
    if not isinstance(d, dict) or not isinstance(d.get("id"), str):
        return Result("error", code="api_bad_answer")
    meta = {k: d.get(k) for k in FILE_FIELDS if d.get(k) is not None}
    raw_variants = d.get("variants")
    variants: dict[str, Any] = raw_variants if isinstance(raw_variants, dict) else {}

    def one(value: Any) -> list[str]:
        return [value] if isinstance(value, str) else []

    images: list[str] = []
    if d.get("status") == "ready":
        if a.variant == "thumb":
            images = one(variants.get("thumb"))
        elif a.variant == "poster":
            images = one(variants.get("poster"))
        elif d.get("kind") == "image":
            images = one(d.get("agent"))  # the copy a model sees (<= 1568 px, no EXIF)
        elif d.get("kind") == "video":
            raw = d.get("frames")  # [{id, at_s}] (contract §17.8); plain ids before
            frames: list[Any] = raw if isinstance(raw, list) else []
            pairs = [
                (f.get("id"), f.get("at_s")) if isinstance(f, dict) else (f, None) for f in frames
            ]
            shown = [(i, at) for i, at in pairs if isinstance(i, str)]
            images = [i for i, _ in shown] or one(variants.get("poster"))
            if any(isinstance(at, int | float) for _, at in shown):
                # where each picture is in the video (s), in the order of image_file_ids
                meta["frames_at_s"] = [at for _, at in shown][:MAX_VIEW_IMAGES]
    meta["view"] = {"variant": a.variant, "image_file_ids": images[:MAX_VIEW_IMAGES]}
    return Result("ok", ref=f"file:{d['id']}", data=meta)


async def mcp_call(api: Api, call: Call, a: McpCallIn) -> Result:
    """Never reached: the gateway carries mcp.call out itself (its class comes
    from the server's registration, before the policy; hq_gateway.mcp)."""
    raise RuntimeError("mcp.call is carried out by the gateway")


async def company_state(api: Api, call: Call, a: CompanyIn) -> Result:
    return from_response(
        await api.request(
            "GET", "/internal/v1/company/state", call.token, params={"company": a.company}
        ),
        None,
    )


async def health_sites(api: Api, call: Call, a: SitesIn) -> Result:
    params = {"company": a.company, "since": a.since.isoformat() if a.since else None}
    return from_response(
        await api.request("GET", "/internal/v1/health/sites", call.token, params=params), None
    )


async def health_hub(api: Api, call: Call, a: Empty) -> Result:
    return from_response(await api.request("GET", "/internal/v1/health/hub", call.token), None)


async def backups_status(api: Api, call: Call, a: Empty) -> Result:
    """The backup status (contract §18.9): metadata only; restore is never a tool."""
    return from_response(await api.request("GET", "/internal/v1/backups/status", call.token), None)


async def treasury_usage(api: Api, call: Call, a: UsageIn) -> Result:
    params = {"scope": a.scope, "period": a.period}
    return from_response(
        await api.request("GET", "/internal/v1/treasury/usage", call.token, params=params), None
    )


async def knowledge_search(api: Api, call: Call, a: SearchIn) -> Result:
    params: dict[str, Any] = {"q": a.q, "kinds": a.kinds}
    return from_response(
        await api.request("GET", "/internal/v1/knowledge/search", call.token, params=params), None
    )


async def audit_recent(api: Api, call: Call, a: AuditIn) -> Result:
    params = {
        "company": a.company,
        "action": a.action,
        "since": a.since.isoformat() if a.since else None,
    }
    return from_response(
        await api.request("GET", "/internal/v1/audit/recent", call.token, params=params), None
    )


async def memory_read(api: Api, call: Call, a: Empty) -> Result:
    return from_response(await api.request("GET", "/internal/v1/memory", call.token), None)


def github_repos() -> frozenset[str]:
    """The repositories github.read may read (GITHUB_READ_REPOS, comma list)."""
    raw = os.environ.get("GITHUB_READ_REPOS", "")
    return frozenset(r.strip().lower() for r in raw.split(",") if r.strip())


async def github_read(api: Api, call: Call, a: GithubIn) -> Result:
    # Before it is switched on (prompt 5.1 §3): only an allowed repository, a
    # path inside it (GithubIn), and the token from OpenBao (the owner's call).
    if a.repo.lower() not in github_repos():
        return Result("denied", code="repo_not_allowed")
    # Off until the owner provides a read-only token (agents/tools.md).
    return Result("error", code="channel_not_configured")


async def deliver(api: Api, call: Call, a: DeliverIn) -> Result:
    wid, err = await _work_id(api, call, a.work_ref)
    if err is not None:
        return err
    body = await _text(a.body_md)
    summary = next((p.strip() for p in body.split("\n\n") if p.strip()), "")[:500]
    g = call.gate
    produced = {
        k: v
        for k, v in {"model": g.get("model"), "effort": g.get("effort")}.items()
        if v is not None
    }
    resp = await api.request(
        "POST",
        f"/internal/v1/work/{wid}/deliver",
        call.token,
        json={
            "title": await _text(a.title_fa),
            "summary": summary,
            "body": body,
            "evidence": await _text([e.model_dump(exclude_none=True) for e in a.evidence]),
            "produced_with": produced,
        },
        idem=call.idem("deliver"),
    )
    r = from_response(resp, None)
    if r.outcome == "ok":
        data = r.data if isinstance(r.data, dict) else {}
        r.ref = data.get("deliverable") if isinstance(data.get("deliverable"), str) else None
        r.data = {
            "deliverable": r.ref,
            "work": a.work_ref,
            "closed_children": data.get("closed_children"),
        }
    return r


async def propose(api: Api, call: Call, a: ProposeIn) -> Result:
    work_id = None
    if call.gate.get("work_ref"):
        work_id, _ = await _work_id(api, call, call.gate["work_ref"])
    quota: dict[str, Any] | None
    if isinstance(a.quota_estimate, int):
        quota = {"tokens": a.quota_estimate}
    elif a.quota_estimate is not None:
        quota = a.quota_estimate.model_dump(exclude_none=True)
    else:
        quota = None
    resp = await api.request(
        "POST",
        "/internal/v1/decisions",
        call.token,
        json={
            "kind": a.kind,
            "title": await _text(a.title_fa),
            "what": await _text(a.what_md),
            "why": await _text(a.why_md),
            "risk": a.risk,
            "reversible": a.reversible,
            "quota_estimate": quota,
            "payload": await _text(a.payload),
            **({"work_id": work_id} if work_id else {}),
        },
        idem=call.idem("propose"),
    )
    r = from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {"decision": r.ref, "status": r.data.get("status"), "kind": a.kind}
    return r


async def _post_message(
    api: Api, call: Call, thread: str, body: str, links: Any, citations: list[Any], key: str
) -> Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/threads/{thread}/messages",
        call.token,
        json={
            "body": await _text(body),
            **({"links": links.model_dump(exclude_none=True)} if links else {}),
            **({"citations": [c.model_dump() for c in citations]} if citations else {}),
        },
        idem=call.idem(key),
    )
    r = from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {
            "message": r.ref,
            "thread": thread,
            "citations_kept": len(r.data.get("citations") or []),
            "citations_dropped": (r.data.get("meta") or {}).get("citations_dropped", 0),
        }
    return r


async def message_owner(api: Api, call: Call, a: OwnerMessageIn) -> Result:
    thread = call.gate.get("own_thread")
    if not thread:
        return Result("error", code="no_thread")
    r = await _post_message(api, call, thread, a.body_md, a.links, [], "message.owner")
    if r.outcome == "ok":
        # The owner hears of it on the report rhythm; a CEO's attention quota
        # applies (non-urgent items beyond it wait for the next digest).
        await api.request(
            "POST",
            "/internal/v1/notifications",
            call.token,
            json={
                "level": "report",
                "title_fa": f"پیام تازه از {call.gate['employee']}",
                "link_kind": "message",
                "link_ref": r.ref,
            },
        )
    return r


async def message_thread(api: Api, call: Call, a: ThreadMessageIn) -> Result:
    return await _post_message(
        api, call, a.thread, a.body_md, a.links, a.citations, f"message.thread:{a.thread}"
    )


async def memory_write(api: Api, call: Call, a: MemoryIn) -> Result:
    resp = await api.request(
        "POST",
        "/internal/v1/memory",
        call.token,
        json={"note": await _text(a.note_md), "tags": await _text(a.tags)},
        idem=call.idem("memory.write"),
    )
    r = from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"memory:{r.data.get('id')}"
        r.data = {"note": r.data.get("id")}
    return r


async def _on_work(
    api: Api, call: Call, ref: str, action: str, body: dict[str, Any] | None
) -> Result:
    wid, err = await _work_id(api, call, ref)
    if err is not None:
        return err
    r = from_response(
        await api.request("POST", f"/internal/v1/work/{wid}/{action}", call.token, json=body), None
    )
    if r.outcome == "ok":
        r.ref = ref
        r.data = {"work": ref, "status": r.data.get("status") if isinstance(r.data, dict) else None}
    return r


async def work_accept(api: Api, call: Call, a: AcceptIn) -> Result:
    r = await _on_work(api, call, a.ref, "accept", None)
    if r.outcome == "ok" and a.note:
        await _on_work(api, call, a.ref, "progress", {"note": await _text(a.note)})
    return r


async def work_progress(api: Api, call: Call, a: ProgressIn) -> Result:
    return await _on_work(api, call, a.ref, "progress", {"note": await _text(a.note), "pct": a.pct})


async def work_fail(api: Api, call: Call, a: FailIn) -> Result:
    return await _on_work(
        api, call, a.ref, "fail", {"reason": await _text(a.reason), "decline": a.decline}
    )


async def work_delegate(api: Api, call: Call, a: DelegateIn) -> Result:
    wid, err = await _work_id(api, call, a.ref)
    if err is not None:
        return err
    budget: dict[str, Any] | None
    if isinstance(a.budget, int):
        budget = {"tokens": a.budget}
    elif a.budget is not None:
        budget = a.budget.model_dump(exclude_none=True)
    else:
        budget = None
    resp = await api.request(
        "POST",
        f"/internal/v1/work/{wid}/delegate",
        call.token,
        json={
            "to": a.to,
            "title": await _text(a.title_fa),
            "brief": await _text(a.brief_md),
            **({"budget": budget} if budget else {}),
        },
        idem=call.idem("work.delegate"),
    )
    r = from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {"work": r.ref, "parent": a.ref, "assignee": a.to}
    return r


async def work_request(api: Api, call: Call, a: RequestIn) -> Result:
    parts = a.to.split("-")
    target: dict[str, Any]
    if len(parts) == 1:
        target = {"company": a.to}  # CEO to another company's CEO
    elif len(parts) == 2:
        target = {"company": parts[0], "department": parts[1]}  # a department (its manager)
    else:
        target = {"to": a.to}  # an employee (a manager) by code
    if "company" in target and target["company"] == call.gate.get("company"):
        target.pop("company")
    req_by = None
    if call.gate.get("work_ref"):
        req_by, _ = await _work_id(api, call, call.gate["work_ref"])
    resp = await api.request(
        "POST",
        "/internal/v1/work",
        call.token,
        json={
            **target,
            "title": await _text(a.title_fa),
            "brief": await _text(a.brief_md),
            **({"requested_by_work_id": req_by} if req_by else {}),
        },
        idem=call.idem("work.request"),
    )
    r = from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        work = r.data.get("work") or {}
        r.ref = work.get("ref")
        r.data = {"work": r.ref, "assignee": (work.get("assignee") or {}).get("code")}
    return r


async def activity_set(api: Api, call: Call, a: ActivityIn) -> Result:
    state = "sleeping" if a.state == "idle" else a.state
    r = from_response(
        await api.request(
            "POST",
            "/internal/v1/activity",
            call.token,
            json={
                "employee": call.gate["employee"],
                "activity": state,
                "note": await _text(a.note),
            },
        ),
        None,
    )
    if r.outcome == "ok":
        r.data = {"activity": state}
    return r


async def notify(api: Api, call: Call, a: NotifyIn) -> Result:
    link = {"link_kind": a.link.kind, "link_ref": await _text(a.link.ref)} if a.link else {}
    resp = await api.request(
        "POST",
        "/internal/v1/notifications",
        call.token,
        json={
            "level": a.level,
            "title_fa": await _text(a.title_fa),
            "body_fa": await _text(a.body_fa),
            **({"category": a.category} if a.category else {}),
            **link,
        },
    )
    r = from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"notification:{r.data.get('id')}"
        r.data = {"level": r.data.get("level"), "state": r.data.get("state")}
    return r


TOOLS: dict[str, tuple[type[In], Handler]] = {
    "work.get": (WorkRef, work_get),
    "company.state": (CompanyIn, company_state),
    "health.sites": (SitesIn, health_sites),
    "health.hub": (Empty, health_hub),
    "backups.status": (Empty, backups_status),
    "treasury.usage": (UsageIn, treasury_usage),
    "knowledge.search": (SearchIn, knowledge_search),
    "audit.recent": (AuditIn, audit_recent),
    "memory.read": (Empty, memory_read),
    "files.read": (FileIn, files_read),
    "github.read": (GithubIn, github_read),
    "deliver": (DeliverIn, deliver),
    "propose": (ProposeIn, propose),
    "message.owner": (OwnerMessageIn, message_owner),
    "message.thread": (ThreadMessageIn, message_thread),
    "memory.write": (MemoryIn, memory_write),
    "work.accept": (AcceptIn, work_accept),
    "work.progress": (ProgressIn, work_progress),
    "work.fail": (FailIn, work_fail),
    "work.delegate": (DelegateIn, work_delegate),
    "work.request": (RequestIn, work_request),
    "activity.set": (ActivityIn, activity_set),
    "notify": (NotifyIn, notify),
    "mcp.call": (McpCallIn, mcp_call),
}


# The class of one call of an `A0/A2` tool, from its parsed input (web.py).
CALL_CLASS: dict[str, Callable[[Any], str]] = {}


def call_class(tool: str, parsed: Any, default: str) -> str:
    """The call's class; a tool without its own rule keeps the catalog's."""
    rule = CALL_CLASS.get(tool)
    return rule(parsed) if rule is not None else default


def validate(tool: str, args: Any) -> tuple[Any, dict[str, str]]:
    """(parsed input, {}) or (None, field errors without the submitted values).
    Arguments that are not a JSON object are refused, never taken as {}."""
    model, _ = TOOLS[tool]
    if not isinstance(args, dict):
        return None, {"args": "must be a JSON object"}
    try:
        return model.model_validate(args), {}
    except ValidationError as exc:
        return None, {
            ".".join(str(p) for p in e["loc"]) or "args": e["msg"][:160] for e in exc.errors()[:10]
        }
