"""The company servers' tools (prompt 17, contract §26.2, agents/tools.md v1.8):

    server.map     A0  the servers the role may work on, or a server's inventory
    server.read    A0  one file (≤ 20 MB, masked)
    server.exec    A2  a command as the server's work user
    server.write   A2  a file (the runner keeps <file>.hq-bak)
    server.claude  A2  the server's own Claude Code on a brief (a Workshop session)

Each call is a job the hub queues for the server's runner (the hub never
connects into a company server); the tool waits a little for it and answers
`running` with the job when it takes longer: the same tool with `{job}` reads
it again. A destructive command waits for the owner's seal: the call is
refused with `awaiting_seal` and the card's ref, and never retried here.

Scope (checked here before anything reaches the api, then again by the api
against the database): the agent's own company; any company for the
holding's platform SRE and the overseer; another company's server only on a
cross-company request that company's CEO accepted, named by the agent's own
work item (`via_work`, by default the run's work item).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from hq_gateway import tools as T

NAME = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$"
UUID_RE = T.UUID_RE
HOLDING_ROLES = ("hub_platform_sre", "overseer")
WAIT_S = 18  # within the gateway's own tool timeout
OTHER_FA = (
    "این سرور شرکت دیگری است: فقط با درخواست میان‌شرکتی که مدیرعامل آن شرکت پذیرفته "
    "(work.request و بعد via_work) یا برای SRE سکو و ناظر کل."
)


class _ServerIn(T.In):
    """Either a new job (server, company?, …) or `{job}` to read one again."""

    job: str | None = Field(default=None, pattern=UUID_RE)
    server: str | None = Field(default=None, pattern=NAME)
    company: str | None = Field(default=None, pattern=T.CODE)
    via_work: str | None = Field(default=None, pattern=T.WORK_REF)

    def needs(self) -> tuple[str, ...]:
        return ("server",)

    @model_validator(mode="after")
    def _either(self) -> _ServerIn:
        if self.job is None:
            missing = [k for k in self.needs() if getattr(self, k) in (None, "")]
            if missing:
                raise ValueError(f"{', '.join(missing)} required (or job)")
        return self

    def args(self) -> dict[str, Any]:
        return {}


class MapIn(_ServerIn):
    def needs(self) -> tuple[str, ...]:
        return ()


class ReadIn(_ServerIn):
    path: str | None = Field(default=None, min_length=1, max_length=1000)
    max_bytes: int | None = Field(default=None, ge=1, le=20 * 1024 * 1024)

    def needs(self) -> tuple[str, ...]:
        return ("server", "path")

    def args(self) -> dict[str, Any]:
        return {"path": self.path, **({"max_bytes": self.max_bytes} if self.max_bytes else {})}


class ExecIn(_ServerIn):
    cmd: str | None = Field(default=None, min_length=1, max_length=20000)
    cwd: str | None = Field(default=None, min_length=1, max_length=500)
    timeout_s: int = Field(default=600, ge=1, le=3600)
    sudo: bool = False

    def needs(self) -> tuple[str, ...]:
        return ("server", "cmd")

    def args(self) -> dict[str, Any]:
        out: dict[str, Any] = {"cmd": self.cmd, "timeout_s": self.timeout_s, "sudo": self.sudo}
        if self.cwd:
            out["cwd"] = self.cwd
        return out


class WriteIn(_ServerIn):
    path: str | None = Field(default=None, min_length=1, max_length=1000)
    content: str | None = Field(default=None, max_length=1024 * 1024)
    encoding: Literal["utf8", "base64"] = "utf8"
    mode: str | None = Field(default=None, pattern=r"^0?[0-7]{3}$")

    def needs(self) -> tuple[str, ...]:
        return ("server", "path", "content")

    def args(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "path": self.path,
            "content": self.content,
            "encoding": self.encoding,
        }
        if self.mode:
            out["mode"] = self.mode
        return out


class ClaudeIn(_ServerIn):
    brief: str | None = Field(default=None, min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    cwd: str | None = Field(default=None, min_length=1, max_length=500)

    def needs(self) -> tuple[str, ...]:
        return ("server", "brief")

    def args(self) -> dict[str, Any]:
        out: dict[str, Any] = {"brief": self.brief}
        if self.title:
            out["title"] = self.title
        if self.cwd:
            out["cwd"] = self.cwd
        return out


def scope(call: T.Call, a: _ServerIn) -> tuple[str | None, T.Result | None]:
    """The cross-company rule (the gateway's scope check): (via_work, None)
    when the call may go on, or (None, the refusal)."""
    own = call.gate.get("company")
    if a.company is None or a.company == own:
        return a.via_work, None
    holding = call.gate.get("scope") == "holding" and call.gate.get("role") in HOLDING_ROLES
    if holding:
        return a.via_work, None
    via = a.via_work or call.gate.get("work_ref")
    if not via or not re.fullmatch(T.WORK_REF, str(via)):
        return None, T.Result("denied", code="other_company", hint_fa=OTHER_FA)
    return str(via), None


def _shape(r: T.Result) -> T.Result:
    """The api's AgentJob as the model reads it: ok with the job's state and
    output; `awaiting_seal` is a refusal with the card's ref."""
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    job = r.data.get("job") or {}
    r.ref = f"job:{job.get('id')}" if job.get("id") else None
    hint = r.data.get("hint_fa")
    if hint:
        r.hint_fa = str(hint)[: T.HINT_CHARS]
    if job.get("state") == "awaiting_seal":
        return T.Result(
            "denied",
            code="awaiting_seal",
            ref=str(job.get("decision_ref") or r.ref or ""),
            data={
                "job": job.get("id"),
                "state": "awaiting_seal",
                "decision": job.get("decision_ref"),
            },
            hint_fa=r.hint_fa,
        )
    if job.get("state") == "cancelled":
        r.outcome, r.code = "error", str(job.get("error_code") or "cancelled")
    return r


async def _job(api: T.Api, call: T.Call, tool: str, kind: str, a: _ServerIn) -> T.Result:
    if a.job is not None:
        resp = await api.request(
            "GET", f"/internal/v1/servers/jobs/{a.job}", call.token, params={"wait_s": WAIT_S}
        )
        return _shape(T.from_response(resp, None))
    via, refused = scope(call, a)
    if refused is not None:
        return refused
    args = a.args()
    # Prose an agent writes leaves redacted; a command, a path and a file are
    # code and leave as written (the hub masks what it stores).
    for key in ("brief", "title"):
        if isinstance(args.get(key), str):
            args[key] = await T._text(args[key])
    resp = await api.request(
        "POST",
        "/internal/v1/servers/jobs",
        call.token,
        json={
            "kind": kind,
            "server": a.server,
            **({"company": a.company} if a.company else {}),
            **({"via_work": via} if via else {}),
            "args": args,
            "wait_s": WAIT_S,
        },
        idem=call.idem(f"{tool}:{a.server}"),
    )
    return _shape(T.from_response(resp, None))


async def server_map(api: T.Api, call: T.Call, a: MapIn) -> T.Result:
    if a.job is None and a.server is None:
        resp = await api.request(
            "GET", "/internal/v1/servers", call.token, params={"company": a.company}
        )
        r = T.from_response(resp, None)
        if r.outcome == "ok" and isinstance(r.data, list):
            r.data = {
                "servers": [
                    {
                        k: s.get(k)
                        for k in ("id", "company", "name", "state", "via", "map_at", "hostname")
                    }
                    for s in r.data
                    if isinstance(s, dict)
                ]
            }
        return r
    return await _job(api, call, "server.map", "map", a)


async def server_read(api: T.Api, call: T.Call, a: ReadIn) -> T.Result:
    return await _job(api, call, "server.read", "read", a)


async def server_exec(api: T.Api, call: T.Call, a: ExecIn) -> T.Result:
    return await _job(api, call, "server.exec", "exec", a)


async def server_write(api: T.Api, call: T.Call, a: WriteIn) -> T.Result:
    return await _job(api, call, "server.write", "write", a)


async def server_claude(api: T.Api, call: T.Call, a: ClaudeIn) -> T.Result:
    return await _job(api, call, "server.claude", "claude", a)


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "server.map": (MapIn, server_map),
    "server.read": (ReadIn, server_read),
    "server.exec": (ExecIn, server_exec),
    "server.write": (WriteIn, server_write),
    "server.claude": (ClaudeIn, server_claude),
}
T.TOOLS.update(TOOLS)
