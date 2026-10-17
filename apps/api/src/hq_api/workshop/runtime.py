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
               agent's tools ask before running (`always_ask`); the hub then
               answers commands on its allow-list itself, refuses what is
               never allowed, and turns everything else (push, PR, the rest)
               into an approval_request for the owner. Built, NOT enabled:
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
            RuntimeEvent(
                "command", f"تست‌ها اجرا شد: {self.output}", {"cmd": "pytest -q", "exit_code": 0}
            ),
            RuntimeEvent(
                "file_change", "README.md به‌روز شد", {"path": "README.md", "added": 3, "removed": 1}
            ),
            self._turn(s),
        ]
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
                    "command", "PR باز شد", {"cmd": "gh pr create", "exit_code": 0}, pr_url=url
                ),
                RuntimeEvent("state", "منتظر دستور بعدی", {"state": "idle"}, state="idle"),
            ]
        return [
            RuntimeEvent(
                "command",
                f"شاخه‌ی {s.branch} push شد",
                {"cmd": f"git push origin {s.branch}", "exit_code": 0},
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
    "اتصال production وجود ندارد و نباید دنبالش بگردی؛ قوانین CLAUDE.md همین ریپو لازم‌الاجراست."
)


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

    async def start(self, s: SessionSpec) -> tuple[str, list[RuntimeEvent]]:
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
        text = f"{RULES_FA.format(branch=s.branch)}\n\n# {s.title}\n\n{s.brief}"
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
        allow-list or the deny-list decides, else they become approvals."""
        assert s.external_id
        raw = await self._all_events(s.external_id)
        start = 0
        if s.cursor:
            ids = [e.get("id") for e in raw]
            start = ids.index(s.cursor) + 1 if s.cursor in ids else 0
        out: list[RuntimeEvent] = []
        confirmations: list[dict[str, Any]] = []
        cursor = s.cursor
        for e in raw[start:]:
            cursor = str(e.get("id") or cursor)
            out += self._map(s, e, confirmations)
        if confirmations:
            await self._events(s.external_id, confirmations)
        return out, cursor

    def _map(
        self, s: SessionSpec, e: dict[str, Any], confirm: list[dict[str, Any]]
    ) -> list[RuntimeEvent]:
        t = str(e.get("type") or "")
        if t == "agent.message":
            return [RuntimeEvent("message", scrub(_text_of(e.get("content")))[:500])]
        if t == "agent.tool_use":
            name = str(e.get("name") or "")
            raw_input = e.get("input")
            inp: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
            if name in ("write", "edit"):
                path = str(inp.get("file_path") or inp.get("path") or "")
                return [RuntimeEvent("file_change", f"تغییر {path}"[:300], {"path": path})]
            if name != "bash":
                return [RuntimeEvent("progress", f"ابزار {name}")]
            cmd = str(inp.get("command") or "")
            if e.get("evaluated_permission") != "ask":
                return [RuntimeEvent("command", scrub(cmd)[:300], {"cmd": scrub(cmd)[:500]})]
            ruling = commands.classify(cmd, session_ref=s.ref, branch_prefix=s.branch_prefix)
            if ruling.verdict == "allow":
                confirm.append(
                    {"type": "user.tool_confirmation", "tool_use_id": e["id"], "result": "allow"}
                )
                return [RuntimeEvent("command", scrub(cmd)[:300], {"cmd": scrub(cmd)[:500]})]
            if ruling.verdict == "deny":
                confirm.append(
                    {"type": "user.tool_confirmation", "tool_use_id": e["id"], "result": "deny"}
                )
                return [
                    RuntimeEvent(
                        "error",
                        f"دستور رد شد: {ruling.reason}"[:300],
                        {"code": "command_refused", "cmd": scrub(cmd)[:500]},
                    )
                ]
            return [
                RuntimeEvent(
                    "approval_request",
                    f"اجازه لازم است: {ruling.reason}"[:300],
                    {"action": ruling.action, "detail": scrub(cmd)[:500]},
                    state="waiting_approval",
                    approval=ApprovalAsk(str(e["id"]), ruling.action, scrub(cmd)[:500]),
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

    async def transcript(self, s: SessionSpec) -> bytes:
        if not s.external_id:
            return b""
        rows = redact(await self._all_events(s.external_id))
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()


def configured(settings: Any) -> str | None:
    """The runtime the owner chose (contract §17.7), or None."""
    name = str(getattr(settings, "workshop_runtime", "") or "")
    return name if name in RUNTIMES else None
