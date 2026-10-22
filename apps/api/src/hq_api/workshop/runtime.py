"""Where a workshop session really runs (contract §17.3 "Runtime").

One interface, three implementations:

  fake         tests and CI: scripted events in process (progress, a command,
               a file change, usage, an approval_request before the push).
  managed      Claude Managed Agents: Anthropic hosts the loop and a
               per-session container. The repository is attached as a
               `github_repository` resource; its fine-grained token is read
               from OpenBao at session start and handed to Anthropic's git
               proxy, which injects it at egress: it never enters the sandbox,
               never reaches a model, an event, a log or this database. The
               agent's tools ask before running (`always_ask`, checked when
               the runtime is built and at every session start: a tool that
               would run without asking keeps the runtime off); the hub then
               answers what the grant's actions and its allow-list permit
               itself, refuses what is never allowed or not granted (a
               read-only grant never edits, pushes or opens a PR), and turns
               every other ask (push, PR, the web, anything unknown) into an
               approval_request for the owner, so no session waits for ever.
               Built, NOT enabled:
               the owner chooses the runtime (WORKSHOP_RUNTIME) and creates
               the API key, the agent, the environment and the tokens.
  self_hosted  design only (docs/ops/WORKSHOP.md); not built.

Every method returns RuntimeEvents; the control plane (workshop.domain)
stores them, enforces the budget and the locks, and publishes them.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

from hq_api.workshop import commands
from hq_common.redact import redact, scrub

log = logging.getLogger("hq_api.workshop")
RUNTIMES = ("managed", "self_hosted")
CLAUDE_CODE = ("system", "claude-code")


@dataclass
class ApprovalAsk:
    external_id: str | None
    action: str  # push_branch | open_pr | command
    detail: str


@dataclass
class RuntimeEvent:
    """One thing that happened in a session. `type` None = no stored event
    (only state or usage changed)."""

    type: str | None = None
    summary_fa: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    actor: tuple[str, str] = CLAUDE_CODE
    state: str | None = None
    held: str | None = None
    usd: Decimal | None = None  # cumulative list cost of the session
    tokens: tuple[int, int] | None = None  # (input, output) added by this event
    approval: ApprovalAsk | None = None
    branch: str | None = None
    pr_url: str | None = None


@dataclass
class SessionSpec:
    ref: str
    workspace: str
    repo: str
    default_branch: str
    branch: str
    title: str
    brief: str
    model: str
    effort: str
    budget_usd: Decimal
    actions: list[str]
    branch_prefix: str = "hq/"
    external_id: str | None = None
    cursor: str | None = None


class Runtime(Protocol):
    name: str

    async def start(self, s: SessionSpec) -> tuple[str, list[RuntimeEvent]]: ...

    async def send(self, s: SessionSpec, text: str) -> list[RuntimeEvent]: ...

    async def answer(
        self, s: SessionSpec, external_id: str | None, action: str, allow: bool
    ) -> list[RuntimeEvent]: ...

    async def stop(self, s: SessionSpec) -> list[RuntimeEvent]: ...

    async def poll(self, s: SessionSpec) -> tuple[list[RuntimeEvent], str | None]: ...

    async def transcript(self, s: SessionSpec) -> bytes: ...


# ------------------------------------------------------------------- fake --
@dataclass
class FakeRuntime:
    """Deterministic sessions for tests and CI (no network, no model)."""

    name: str = "fake"
    usd_per_turn: Decimal = Decimal("0.40")
    ask_push: bool = True
    output: str = "12 passed"
    log_: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    usd: dict[str, Decimal] = field(default_factory=dict)

    def _rec(self, s: SessionSpec, kind: str, **data: Any) -> None:
        self.log_.setdefault(s.ref, []).append({"kind": kind, **data})

    def _turn(self, s: SessionSpec) -> RuntimeEvent:
        self.usd[s.ref] = self.usd.get(s.ref, Decimal(0)) + self.usd_per_turn
        return RuntimeEvent(usd=self.usd[s.ref], tokens=(12_000, 3_400))

    async def start(self, s: SessionSpec) -> tuple[str, list[RuntimeEvent]]:
        self._rec(s, "start", brief=s.brief)
        events = [
            RuntimeEvent(
                "state", "سشن روی یک کلون تازه شروع شد", {"state": "working"}, state="working"
            ),
            RuntimeEvent("progress", "خواندن CLAUDE.md و ساختار ریپو"),
        ]
        if "run" in s.actions:  # what the grant allows, like the managed adapter
            events.append(
                RuntimeEvent(
                    "command",
                    f"تست‌ها اجرا شد: {self.output}",
                    {"cmd": "pytest -q", "exit_code": 0, "duration_s": 4.2},
                )
            )
        if "edit" in s.actions:
            events.append(
                RuntimeEvent(
                    "file_change",
                    "README.md به‌روز شد",
                    {"path": "README.md", "added": 3, "removed": 1},
                )
            )
        events.append(self._turn(s))
        if self.ask_push and "push_branch" in s.actions:
            cmd = f"git push origin {s.branch}"
            events.append(
                RuntimeEvent(
                    "approval_request",
                    f"اجازه برای push شاخه‌ی {s.branch}",
                    {"action": "push_branch", "detail": cmd},
                    state="waiting_approval",
                    approval=ApprovalAsk(f"fake-{s.ref}-push", "push_branch", cmd),
                )
            )
        else:
            events.append(
                RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle")
            )
        return f"fake-{s.ref}", events

    async def send(self, s: SessionSpec, text: str) -> list[RuntimeEvent]:
        self._rec(s, "message", text=text)
        return [
            RuntimeEvent("state", "در حال کار", {"state": "working"}, state="working"),
            RuntimeEvent("message", "دستور دریافت شد و انجام شد"),
            self._turn(s),
            RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle"),
        ]

    async def answer(
        self, s: SessionSpec, external_id: str | None, action: str, allow: bool
    ) -> list[RuntimeEvent]:
        self._rec(s, "answer", approval=external_id, allow=allow)
        if not allow:
            return [
                RuntimeEvent(
                    "state", "push انجام نشد؛ منتظر دستور", {"state": "idle"}, state="idle"
                )
            ]
        if action == "open_pr":
            url = f"https://github.com/{s.repo}/pull/1"
            return [
                RuntimeEvent(
                    "command",
                    "PR باز شد",
                    {"cmd": "gh pr create", "exit_code": 0, "duration_s": 1.1},
                    pr_url=url,
                ),
                RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle"),
            ]
        return [
            RuntimeEvent(
                "command",
                f"شاخه‌ی {s.branch} push شد",
                {"cmd": f"git push origin {s.branch}", "exit_code": 0, "duration_s": 2.3},
                branch=s.branch,
            ),
            RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle"),
        ]

    async def stop(self, s: SessionSpec) -> list[RuntimeEvent]:
        self._rec(s, "stop")
        return []

    async def poll(self, s: SessionSpec) -> tuple[list[RuntimeEvent], str | None]:
        return [], s.cursor

    async def transcript(self, s: SessionSpec) -> bytes:
        rows = redact(self.log_.get(s.ref, []))
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()


# ---------------------------------------------------------------- managed --
API_VERSION = "2023-06-01"
BETA = "managed-agents-2026-04-01"
RULES_FA = (
    "قواعد کارگاه (غیرقابل‌تغییر): فقط روی شاخه‌ی {branch} کار کن و فقط همان را push کن؛ "
    "به main یا شاخه‌ی دیگری push نکن؛ merge و deploy با مُهر مالک است؛ هیچ رمز، کلید، SSH یا "
    "اتصال production وجود ندارد و نباید دنبالش بگردی؛ قوانین CLAUDE.md همین ریپو لازم‌الاجراست. "
    "این مجوز فقط اجازه‌ی این‌ها را میدهد: {actions}؛ هر کار دیگری رد میشود."
)
ACTIONS_FA = {
    "read": "خواندن",
    "edit": "ویرایش فایل‌ها",
    "run": "اجرای دستورها و تست‌ها",
    "push_branch": "push همان شاخه (با اجازه‌ی مالک)",
    "open_pr": "باز کردن PR (با اجازه‌ی مالک)",
}
# The agent toolset's tools (agent_toolset_20260401) and how the hub answers
# each one's ask; MCP and any other tool become an approval for the owner.
TOOLSET_TOOLS = ("bash", "read", "write", "edit", "glob", "grep", "web_fetch", "web_search")
READ_TOOLS = ("read", "glob", "grep")
EDIT_TOOLS = ("write", "edit")


def _policy(cfg: Any) -> str | None:
    pp = cfg.get("permission_policy") if isinstance(cfg, dict) else None
    return str(pp["type"]) if isinstance(pp, dict) and pp.get("type") else None


def permission_problems_of(agent: dict[str, Any]) -> list[str]:
    """The agent's tools that would run without asking the hub first: every
    enabled tool must be `always_ask` (the agent toolset defaults to
    always_allow, MCP to always_ask); a custom tool, which the hub would have
    to carry out, is refused too. Empty: the agent may be used."""
    problems: list[str] = []
    for t in agent.get("tools") or []:
        if not isinstance(t, dict):
            problems.append("a tool the hub cannot read")
            continue
        kind = str(t.get("type") or "")
        raw_default = t.get("default_config")
        default: dict[str, Any] = raw_default if isinstance(raw_default, dict) else {}
        configs = {str(c.get("name")): c for c in t.get("configs") or [] if isinstance(c, dict)}
        if kind.startswith("agent_toolset"):
            names, base = sorted(set(TOOLSET_TOOLS) | set(configs)), "always_allow"
        elif kind == "mcp_toolset":
            names, base = sorted(set(configs) | {"*"}), "always_ask"
            kind = f"mcp {t.get('mcp_server_name') or ''}".strip()
        else:
            problems.append(f"{kind or 'tool'}: not carried out by the hub")
            continue
        on_default = default.get("enabled", True) is not False
        policy_default = _policy(default) or base
        for name in names:
            c = configs.get(name, {})
            on = c.get("enabled", on_default) is not False
            policy = _policy(c) or policy_default
            if on and policy != "always_ask":
                problems.append(f"{kind}/{name}: {policy}")
    return problems


def _at(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _text_of(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content or "")


@dataclass
class ManagedRuntime:
    """Claude Managed Agents over its REST API (beta header managed-agents-2026-04-01)."""

    api_key: Callable[[], str]
    agent_id: str
    environment_id: str
    github_token: Callable[[str], Awaitable[str | None]]
    base_url: str = "https://api.anthropic.com"
    transport: httpx.AsyncBaseTransport | None = None
    timeout_s: float = 30.0
    name: str = "managed"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_s,
            transport=self.transport,
            headers={
                "x-api-key": self.api_key(),
                "anthropic-version": API_VERSION,
                "anthropic-beta": BETA,
                "content-type": "application/json",
            },
        )

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.post(path, json=body)
        if r.status_code >= 300:
            # Never the body: it may echo what was sent.
            raise RuntimeError(f"managed agents: HTTP {r.status_code} on {path.split('/')[2]}")
        data: dict[str, Any] = r.json() if r.content else {}
        return data

    async def _events(self, sid: str, events: list[dict[str, Any]]) -> None:
        await self._post(f"/v1/sessions/{sid}/events", {"events": events})

    async def permission_problems(self) -> list[str]:
        """The agent's permission settings as Anthropic stores them now
        (permission_problems_of); raises when they cannot be read."""
        async with self._client() as c:
            r = await c.get(f"/v1/agents/{self.agent_id}")
        if r.status_code >= 300:
            raise RuntimeError(f"managed agents: HTTP {r.status_code} on agents")
        body = r.json()
        return permission_problems_of(body if isinstance(body, dict) else {})

    async def start(self, s: SessionSpec) -> tuple[str, list[RuntimeEvent]]:
        if await self.permission_problems():  # checked again: the agent may have changed
            raise RuntimeError("the managed agent does not ask before every tool")
        token = await self.github_token(s.workspace)
        if not token:
            raise RuntimeError(f"no GitHub credential for workspace {s.workspace}")
        body: dict[str, Any] = {
            "agent": self.agent_id,
            "environment_id": self.environment_id,
            "title": f"{s.ref} {s.title}"[:200],
            "metadata": {"hq_session": s.ref, "hq_workspace": s.workspace},
            "resources": [
                {
                    "type": "github_repository",
                    "url": f"https://github.com/{s.repo}",
                    "mount_path": "/workspace/repo",
                    "authorization_token": token,
                    "checkout": {"type": "branch", "name": s.default_branch},
                }
            ],
            # The platform's own hard cap, as well as the hub's (minor units, USD).
            "budget": {
                "type": "limit",
                "max_list_cost": {"amount": str(int(s.budget_usd * 100)), "currency": "USD"},
            },
        }
        session = await self._post("/v1/sessions", body)
        del token, body
        sid = str(session["id"])
        allowed = "، ".join(ACTIONS_FA.get(a, a) for a in s.actions)
        text = f"{RULES_FA.format(branch=s.branch, actions=allowed)}\n\n# {s.title}\n\n{s.brief}"
        await self._events(
            sid, [{"type": "user.message", "content": [{"type": "text", "text": text}]}]
        )
        return sid, [
            RuntimeEvent(
                "state", "سشن در Managed Agents ساخته شد", {"state": "working"}, state="working"
            )
        ]

    async def send(self, s: SessionSpec, text: str) -> list[RuntimeEvent]:
        assert s.external_id
        await self._events(
            s.external_id, [{"type": "user.message", "content": [{"type": "text", "text": text}]}]
        )
        return []

    async def answer(
        self, s: SessionSpec, external_id: str | None, action: str, allow: bool
    ) -> list[RuntimeEvent]:
        assert s.external_id
        assert external_id
        await self._events(
            s.external_id,
            [
                {
                    "type": "user.tool_confirmation",
                    "tool_use_id": external_id,
                    "result": "allow" if allow else "deny",
                }
            ],
        )
        return []

    async def stop(self, s: SessionSpec) -> list[RuntimeEvent]:
        if s.external_id:
            await self._events(s.external_id, [{"type": "user.interrupt"}])
        return []

    async def _all_events(self, sid: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page: str | None = None
        async with self._client() as c:
            for _ in range(50):
                params: dict[str, Any] = {"limit": 1000}
                if page:
                    params["page"] = page
                r = await c.get(f"/v1/sessions/{sid}/events", params=params)
                if r.status_code >= 300:
                    raise RuntimeError(f"managed agents: HTTP {r.status_code} on events")
                body = r.json()
                out += list(body.get("data") or [])
                page = body.get("next_page")
                if not page:
                    break
        return out

    async def poll(self, s: SessionSpec) -> tuple[list[RuntimeEvent], str | None]:
        """New events since the cursor, mapped; asks are answered here when the
        grant, the allow-list or the deny-list decides, else they become
        approvals. A cursor the runtime no longer lists (06.1 §3) replays the
        events, but never a second approval or confirmation for an ask that
        was already answered, and never the tokens twice."""
        assert s.external_id
        raw = await self._all_events(s.external_id)
        start, replay = 0, False
        if s.cursor:
            ids = [e.get("id") for e in raw]
            if s.cursor in ids:
                start = ids.index(s.cursor) + 1
            else:
                replay = True
                log.warning("workshop: runtime cursor lost; replaying", extra={"session": s.ref})
        answered = {
            str(e.get("tool_use_id"))
            for e in raw
            if e.get("type") == "user.tool_confirmation" and e.get("tool_use_id")
        }
        uses = {str(e["id"]): e for e in raw if e.get("type") == "agent.tool_use" and e.get("id")}
        out: list[RuntimeEvent] = []
        confirmations: list[dict[str, Any]] = []
        cursor = s.cursor
        for e in raw[start:]:
            cursor = str(e.get("id") or cursor)
            if replay and str(e.get("id")) in answered:
                continue  # handled before the cursor was lost
            mapped = self._map(s, e, confirmations, uses)
            if replay:
                for ev in mapped:
                    ev.tokens = None
            out += mapped
        confirmations = [
            c
            for c in confirmations
            if c.get("type") != "user.tool_confirmation" or c.get("tool_use_id") not in answered
        ]
        if confirmations:
            await self._events(s.external_id, confirmations)
        return out, cursor

    def _map(
        self,
        s: SessionSpec,
        e: dict[str, Any],
        confirm: list[dict[str, Any]],
        uses: dict[str, dict[str, Any]] | None = None,
    ) -> list[RuntimeEvent]:
        t = str(e.get("type") or "")
        if t == "agent.message":
            return [RuntimeEvent("message", scrub(_text_of(e.get("content")))[:500])]
        if t in ("agent.tool_use", "agent.mcp_tool_use"):
            return self._tool_use(s, e, confirm)
        if t == "agent.tool_result":
            return self._tool_result(e, uses or {})
        if t == "agent.custom_tool_use":  # the hub carries out no custom tool
            confirm.append({"type": "user.interrupt"})
            return [
                RuntimeEvent(
                    "error",
                    "ابزاری خارج از کارگاه خواسته شد؛ سشن متوقف شد",
                    {"code": "runtime_permission"},
                    state="failed",
                )
            ]
        if t == "span.model_request_end":
            u = e.get("model_usage") or {}
            tin = (
                int(u.get("input_tokens") or 0)
                + int(u.get("cache_read_input_tokens") or 0)
                + int(u.get("cache_creation_input_tokens") or 0)
            )
            return [RuntimeEvent(tokens=(tin, int(u.get("output_tokens") or 0)))]
        if t == "session.usage":
            cost = e.get("list_cost") or {}
            return [RuntimeEvent(usd=Decimal(str(cost.get("amount") or 0)) / 100)]
        if t == "session.status_running":
            return [RuntimeEvent(state="working")]
        if t == "session.status_idle":
            reason = str((e.get("stop_reason") or {}).get("type") or "")
            if reason == "budget_reached":
                return [
                    RuntimeEvent(
                        "error", "سقف بودجه‌ی سشن رسید", {"code": "budget_reached"}, held="budget"
                    )
                ]
            if reason == "requires_action":
                return []
            return [RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle")]
        if t == "session.status_terminated":
            return [RuntimeEvent("state", "سشن پایان یافت", {"state": "done"}, state="done")]
        if t == "session.error":
            msg = scrub(str((e.get("error") or {}).get("message") or e.get("message") or "error"))
            return [RuntimeEvent("error", msg[:300], {"code": "runtime_error"})]
        return []

    def _tool_use(
        self, s: SessionSpec, e: dict[str, Any], confirm: list[dict[str, Any]]
    ) -> list[RuntimeEvent]:
        """One tool call: answered by the grant and the rules, or asked of the owner."""
        name = str(e.get("name") or "")
        raw_input = e.get("input")
        inp: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
        mcp = e.get("type") == "agent.mcp_tool_use"
        granted = set(s.actions)
        eid = str(e.get("id") or "")

        def answer(result: str, why: str = "") -> None:
            c: dict[str, Any] = {"type": "user.tool_confirmation", "tool_use_id": eid,
                                 "result": result}  # fmt: skip
            if result == "deny" and why:
                c["deny_message"] = why[:300]
            confirm.append(c)

        if e.get("evaluated_permission") != "ask":
            if e.get("evaluated_permission") == "deny" or (name in READ_TOOLS and not mcp):
                return [RuntimeEvent("progress", f"ابزار {name}"[:300])]
            # It ran without asking the hub: the agent's settings changed after
            # the check. The session stops; nothing more runs unseen.
            confirm.append({"type": "user.interrupt"})
            return [
                RuntimeEvent(
                    "error",
                    f"ابزار {name} بدون اجازه‌ی هاب اجرا شد؛ سشن متوقف شد"[:300],
                    {"code": "runtime_permission"},
                    state="failed",
                )
            ]
        if mcp or name not in TOOLSET_TOOLS or name in ("web_fetch", "web_search"):
            what = str(inp.get("url") or inp.get("query") or "")
            label = (
                f"mcp {e.get('server_name') or e.get('mcp_server_name') or ''}.{name}"
                if mcp
                else name
            )
            detail = scrub(f"{label} {what}".strip())[:500]
            return [self._ask(eid, "command", f"اجازه لازم است: {label}", detail)]
        if name in READ_TOOLS:
            answer("allow")
            return [RuntimeEvent("progress", f"ابزار {name}")]
        if name in EDIT_TOOLS:
            path = str(inp.get("file_path") or inp.get("path") or "")
            if "edit" not in granted:
                answer("deny", "this grant is read-only: no file is edited")
                return [self._refused(f"ویرایش {path}: این مجوز فقط‌خواندنی است", "not_granted")]
            answer("allow")
            return [RuntimeEvent("file_change", f"تغییر {path}"[:300], {"path": path})]
        cmd = str(inp.get("command") or "")
        ruling = commands.classify(cmd, session_ref=s.ref, branch_prefix=s.branch_prefix)
        missing = commands.needs(cmd) - granted
        if ruling.verdict == "deny":
            answer("deny", ruling.reason)
            return [self._refused(f"دستور رد شد: {ruling.reason}", "command_refused", cmd)]
        if missing:
            names = "، ".join(ACTIONS_FA.get(a, a) for a in sorted(missing))
            answer("deny", f"not in this grant: {', '.join(sorted(missing))}")
            return [self._refused(f"این مجوز اجازه نمیدهد: {names}", "not_granted", cmd)]
        if ruling.verdict == "allow":
            answer("allow")
            return [RuntimeEvent("progress", f"اجرا: {scrub(cmd)}"[:300])]
        return [self._ask(eid, ruling.action, f"اجازه لازم است: {ruling.reason}", scrub(cmd)[:500])]

    @staticmethod
    def _ask(eid: str, action: str, summary: str, detail: str) -> RuntimeEvent:
        return RuntimeEvent(
            "approval_request",
            summary[:300],
            {"action": action, "detail": detail},
            state="waiting_approval",
            approval=ApprovalAsk(eid, action, detail),
        )

    @staticmethod
    def _refused(summary: str, code: str, cmd: str | None = None) -> RuntimeEvent:
        data: dict[str, Any] = {"code": code}
        if cmd is not None:
            data["cmd"] = scrub(cmd)[:500]
        return RuntimeEvent("error", summary[:300], data)

    @staticmethod
    def _tool_result(e: dict[str, Any], uses: dict[str, dict[str, Any]]) -> list[RuntimeEvent]:
        """A shell command that ran: its `command` event, with how long it took."""
        use = uses.get(str(e.get("tool_use_id") or ""))
        if use is None or str(use.get("name") or "") != "bash":
            return []
        raw_input = use.get("input")
        cmd = scrub(str((raw_input if isinstance(raw_input, dict) else {}).get("command") or ""))
        began, ended = _at(use.get("processed_at")), _at(e.get("processed_at"))
        data: dict[str, Any] = {
            "cmd": cmd[:500],
            "exit_code": e["exit_code"]
            if isinstance(e.get("exit_code"), int)
            else (1 if e.get("is_error") else 0),
        }
        if began and ended and ended >= began:
            data["duration_s"] = round((ended - began).total_seconds(), 3)
        return [RuntimeEvent("command", cmd[:300], data)]

    async def transcript(self, s: SessionSpec) -> bytes:
        if not s.external_id:
            return b""
        rows = redact(await self._all_events(s.external_id))
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()


def configured(settings: Any) -> str | None:
    """The runtime the owner chose (contract §17.7), or None."""
    name = str(getattr(settings, "workshop_runtime", "") or "")
    return name if name in RUNTIMES else None
