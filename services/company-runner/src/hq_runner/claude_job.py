"""The `claude` job (contract §26.2, §26.3): the server's own Claude Code on a
brief, in the repository folder `args.cwd`, under that repository's CLAUDE.md.

    claude -p <brief> --output-format stream-json --verbose --settings <tmp>/settings.json
           [--resume <session_id>] [--model M] [--permission-mode P] [--max-turns N]
           [--allowedTools <tool> ...]

⟨0.3.2⟩ a workspace turn that ended well sends the files it left in `out/` of
its folder to the hub (outbox.py; contract §43, the holding's workshop) and
the result names them (`files`, `files_skipped`).

⟨0.3.0⟩ `args.workspace: "<work-ref>"` (contract §33.10): the session works
in the work's own persistent folder `~/hq-workspace/<work-ref>` (700, made
on first use, kept across resumes) instead of `args.cwd`; the hub's close of
the work and the 30-day sweep are in workspace.py.

⟨0.2.2⟩ `args.token_cap` (contract §28.6, prompt 20.1): the session's token
cap. Every assistant message's usage (input + output + cache reads and
writes, counted once per message id) is added up as it streams; the moment
the total passes the cap the session is stopped like a cancel and the job
ends `token_cap` with the usage it reached, so no run spends past the cap
the hub gave it (a catalogue once spent 50M tokens in an hour without one).

⟨0.2.1⟩ `args.allowed_tools` (contract §28.6): the hub's allow-list of tools
and read-only Bash prefixes, handed to Claude Code as --allowedTools and as
the settings' `permissions.allow`, so a non-interactive session is not
refused a read it was asked for. The PreToolUse hook still sees every Bash
call (an allowed prefix is never past the hub's destructive classifier).

The temporary settings file adds one PreToolUse hook for Bash that runs
`hq-runner classify-hook`: it asks the hub to classify the command and blocks
the call (exit code 2) when the hub names a seal-required category, so the hub
raises the owner's seal card. The settings file and its folder exist only for
this run. Each stream-json line becomes a `session_event` event; usage comes
from the final result line and goes back with the result.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import hq_runner
from hq_runner import outbox
from hq_runner import workspace as workspace_state
from hq_runner.config import config_path
from hq_runner.jobs import JobContext, JobError, JobResult, _cwd, _timeout
from hq_runner.mask import Masker, StreamMasker
from hq_runner.proc import run_streamed
from hq_runner.workspace import WorkspaceError, prepare

CLAUDE_DEFAULT_TIMEOUT_S = 3600
CLAUDE_MAX_TIMEOUT_S = 4 * 3600
PERMISSION_MODES = {"default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"}
# ⟨0.2.0⟩ nothing the owner or an agent relies on is cut: an event's text (a
# message of the session, a command) keeps up to EVENT_TEXT; the final answer
# comes back whole (the hub keeps a long one in its file store). Only past
# MAX_ANSWER_CHARS (≈16 MB of Persian, the hub's result body cap) is the end
# cut, and then the result says so (`answer_truncated`), never silently.
EVENT_TEXT = 64_000
MAX_TEXT = EVENT_TEXT  # (the name earlier versions used)
MAX_ANSWER_CHARS = 8_000_000
JSON_LINE_BYTES = 64 * 1024 * 1024  # one stream-json line (the final answer) read whole
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
ALLOWED_TOOL = re.compile(r"^(?:[A-Z][A-Za-z]{1,30}|Bash\([^()\n\x00]{1,200}\))$")
MAX_ALLOWED_TOOLS = 200
# ⟨0.3.1⟩ a Claude subscription token as `claude setup-token` prints it
OAUTH_RE = re.compile(r"sk-ant-oat[A-Za-z0-9_-]{20,300}")
EXIT_TOKEN_CAP = 125  # the session passed its token cap and was stopped


def allowed_tools(value: Any) -> list[str]:
    """The hub's allow-list, checked: a tool name or a Bash(<prefix>) pattern
    each; anything else refuses the job (never a widened permission)."""
    if value is None:
        return []
    if (
        not isinstance(value, list)
        or len(value) > MAX_ALLOWED_TOOLS
        or not all(isinstance(t, str) and ALLOWED_TOOL.match(t) for t in value)
    ):
        raise JobError("فهرست ابزارهای مجاز (allowed_tools) درست نیست.")
    return list(dict.fromkeys(value))


async def _relay(cancel: asyncio.Event, stop: asyncio.Event) -> None:
    await cancel.wait()
    stop.set()


def find_claude(configured: str | None = None) -> str | None:
    """The CLI: the configured path, HQ_RUNNER_CLAUDE_BIN, PATH, then the usual
    per-user install places (systemd's PATH does not include ~/.local/bin)."""
    for cand in (configured, os.environ.get("HQ_RUNNER_CLAUDE_BIN")):
        if cand:
            return cand
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for p in (
        home / ".local/bin/claude",
        home / ".claude/local/claude",
        Path("/usr/local/bin/claude"),
    ):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def hook_command(job_id: str) -> str:
    """The hook as a shell command line; it runs this same installation of the
    runner whether or not `hq-runner` is on PATH."""
    root = str(Path(hq_runner.__file__).resolve().parent.parent)
    return (
        f"PYTHONPATH={shlex.quote(root)} {shlex.quote(sys.executable)} -m hq_runner "
        f"classify-hook --job {shlex.quote(job_id)}"
    )


def hook_settings(job_id: str, allow: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"permissions": {"allow": list(allow)}} if allow else {}
    return out | {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": hook_command(job_id), "timeout": 60}],
                }
            ]
        }
    }


def _cut(text: str, n: int = MAX_TEXT) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def session_events(obj: dict[str, Any], masker: Masker) -> list[dict[str, Any]]:
    """One stream-json object as SessionEvent-shaped items {type, at, summary_fa, data}."""
    at = _now()
    t = obj.get("type")
    out: list[dict[str, Any]] = []

    def ev(type_: str, summary: str, data: dict[str, Any]) -> None:
        out.append({"type": type_, "at": at, "summary_fa": summary, "data": masker.value(data)})

    if t == "system" and obj.get("subtype") == "init":
        ev(
            "state",
            "نشست Claude روی سرور آغاز شد.",
            {
                "state": "working",
                "session_id": obj.get("session_id"),
                "model": obj.get("model"),
                "cwd": obj.get("cwd"),
            },
        )
    elif t == "assistant":
        content = (obj.get("message") or {}).get("content") or []
        for block in content if isinstance(content, list) else []:
            bt = block.get("type")
            if bt == "text" and block.get("text"):
                ev("message", "پیام Claude", {"role": "assistant", "text": _cut(block["text"])})
            elif bt == "tool_use":
                name = str(block.get("name"))
                inp = block.get("input") or {}
                if name == "Bash":
                    ev(
                        "command",
                        "دستور",
                        {"cmd": _cut(str(inp.get("command", ""))), "tool_use_id": block.get("id")},
                    )
                elif name in FILE_TOOLS:
                    ev(
                        "file_change",
                        "تغییر فایل",
                        {
                            "path": inp.get("file_path") or inp.get("notebook_path"),
                            "tool": name,
                            "tool_use_id": block.get("id"),
                        },
                    )
                else:
                    ev(
                        "progress",
                        f"ابزار {name}",
                        {
                            "tool": name,
                            "input": _cut(json.dumps(inp, ensure_ascii=False), 1000),
                            "tool_use_id": block.get("id"),
                        },
                    )
    elif t == "user":
        content = (obj.get("message") or {}).get("content") or []
        for block in content if isinstance(content, list) else []:
            if block.get("type") != "tool_result":
                continue
            raw = block.get("content")
            if isinstance(raw, list):
                raw = " ".join(str(c.get("text", "")) for c in raw if isinstance(c, dict))
            ev(
                "progress",
                "نتیجه‌ی ابزار",
                {
                    "tool_use_id": block.get("tool_use_id"),
                    "is_error": bool(block.get("is_error")),
                    "text": _cut(str(raw or "")),
                },
            )
    elif t == "result":
        failed = bool(obj.get("is_error"))
        ev(
            "state",
            "نشست Claude با خطا تمام شد." if failed else "نشست Claude تمام شد.",
            {
                "state": "failed" if failed else "done",
                "session_id": obj.get("session_id"),
                "num_turns": obj.get("num_turns"),
                "duration_ms": obj.get("duration_ms"),
                "stop_reason": obj.get("stop_reason"),
                "result": _cut(str(obj.get("result") or "")),
            },
        )
    elif t == "rate_limit_event":
        ev("progress", "وضعیت سهمیه‌ی Claude", {"rate_limit": obj.get("rate_limit_info")})
    return out


def token_cap(value: Any) -> int | None:
    """The hub's token cap of the session: a positive integer, or none."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise JobError("سقف توکن (token_cap) درست نیست.")
    return value


class TokenMeter:
    """⟨0.2.2⟩ The session's tokens so far, from each assistant message's
    usage. Claude Code repeats a message's usage on every content block of it,
    so a message counts once (its latest usage)."""

    def __init__(self) -> None:
        self.by_message: dict[str, dict[str, int]] = {}
        self.model: str | None = None

    def add(self, obj: dict[str, Any]) -> None:
        if obj.get("type") != "assistant":
            return
        msg = obj.get("message") or {}
        u = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(u, dict):
            return
        key = str(msg.get("id") or f"m{len(self.by_message)}")
        self.model = self.model or msg.get("model")

        def n(k: str) -> int:
            v = u.get(k)
            return max(0, int(v)) if isinstance(v, int | float) and not isinstance(v, bool) else 0

        self.by_message[key] = {
            "input_tokens": n("input_tokens"),
            "output_tokens": n("output_tokens"),
            "cache_read_tokens": n("cache_read_input_tokens"),
            "cache_write_tokens": n("cache_creation_input_tokens"),
        }

    def sum(self, k: str) -> int:
        return sum(m[k] for m in self.by_message.values())

    @property
    def total(self) -> int:
        return sum(sum(m.values()) for m in self.by_message.values())

    def usage(self, session_id: Any) -> dict[str, Any]:
        return {
            "input_tokens": self.sum("input_tokens"),
            "output_tokens": self.sum("output_tokens"),
            "cache_read_tokens": self.sum("cache_read_tokens"),
            "cache_write_tokens": self.sum("cache_write_tokens"),
            "thinking_tokens": 0,
            "cost_usd": 0.0,
            "model": self.model,
            "session_id": session_id,
        }


def usage_from_result(obj: dict[str, Any]) -> dict[str, Any]:
    u = obj.get("usage") or {}
    details = u.get("output_tokens_details") or {}
    model_usage = obj.get("modelUsage") or {}
    return {
        "input_tokens": int(u.get("input_tokens") or 0),
        "output_tokens": int(u.get("output_tokens") or 0),
        "cache_read_tokens": int(u.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(u.get("cache_creation_input_tokens") or 0),
        "thinking_tokens": int(details.get("thinking_tokens") or 0),
        "cost_usd": float(obj.get("total_cost_usd") or 0.0),
        "model": next(iter(model_usage), None) if isinstance(model_usage, dict) else None,
        "session_id": obj.get("session_id"),
    }


async def run_claude(ctx: JobContext) -> JobResult:
    args = ctx.args
    brief = args.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise JobError("شرح کار (brief) داده نشده است.")
    workspace = args.get("workspace")
    if workspace is not None:
        # ⟨0.3.0⟩ §33.10: the work's own persistent folder, never args.cwd
        try:
            cwd = str(await asyncio.to_thread(prepare, workspace, ctx.cfg_path))
        except WorkspaceError:
            raise JobError(
                "نام محیط کاری (workspace) باید شماره‌ی یک کار باشد، مثل W-000123."
            ) from None
        ctx.sink.emit("progress", {"text": f"workspace {workspace}"})
    else:
        cwd = _cwd(args.get("cwd"))
    timeout = _timeout(args, CLAUDE_DEFAULT_TIMEOUT_S, CLAUDE_MAX_TIMEOUT_S)
    allow = allowed_tools(args.get("allowed_tools"))
    cap = token_cap(args.get("token_cap"))
    claude = find_claude(ctx.cfg.claude_bin)
    if not claude:
        raise JobError("Claude Code روی این سرور پیدا نشد.", 127)
    tmp = Path(tempfile.mkdtemp(prefix="hq-claude-"))
    os.chmod(tmp, 0o700)
    settings = tmp / "settings.json"
    hook_log = tmp / "hook-events.jsonl"
    settings.write_text(json.dumps(hook_settings(ctx.id, allow)), encoding="utf-8")
    argv = [
        claude,
        "-p",
        brief,
        "--output-format",
        "stream-json",
        "--verbose",
        "--settings",
        str(settings),
    ]
    resume = args.get("session_id") or args.get("resume")
    if resume:
        argv += ["--resume", str(resume)]
    if args.get("model"):
        argv += ["--model", str(args["model"])]
    if args.get("permission_mode") in PERMISSION_MODES:
        argv += ["--permission-mode", str(args["permission_mode"])]
    if args.get("max_turns"):
        argv += ["--max-turns", str(int(args["max_turns"]))]
    if allow:  # last: the option takes every value after it
        argv += ["--allowedTools", *allow]
    env = dict(ctx.env)
    # ⟨0.3.1⟩ the hub's own Claude account for this session (the companies have no subscription
    # of their own): only in this process's environment, never written, never logged; without
    # it, this server's own Claude login
    oauth = ctx.job.get("claude_oauth")
    if isinstance(oauth, str) and OAUTH_RE.fullmatch(oauth):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth
        ctx.masker.literals = sorted({*ctx.masker.literals, oauth}, key=len, reverse=True)
    env.update(
        {
            "HQ_RUNNER_CONFIG": str((ctx.cfg_path or config_path()).resolve()),
            "HQ_RUNNER_VIA": ctx.via,
            "HQ_RUNNER_HOOK_EVENTS": str(hook_log),
            "HQ_RUNNER_JOB_ID": ctx.id,
        }
    )
    final: dict[str, Any] = {}
    meter = TokenMeter()
    capped = False
    session_id: Any = None
    # the session stops on the job's cancel or once it passes its token cap
    stop = asyncio.Event()
    relay = asyncio.ensure_future(_relay(ctx.cancel, stop))
    files_changed: list[str] = []
    hook_seen = 0
    stderr_masker = StreamMasker(ctx.masker)

    def drain_hook_log() -> None:
        nonlocal hook_seen
        with contextlib.suppress(OSError):
            lines = hook_log.read_text(encoding="utf-8").splitlines()
            for line in lines[hook_seen:]:
                with contextlib.suppress(ValueError):
                    rec = json.loads(line)
                    ctx.sink.emit(
                        "session_event",
                        {
                            "type": "approval_request",
                            "at": _now(),
                            "summary_fa": "این دستور مُهر مالک میخواهد؛ در ستاد منتظر تأیید است.",
                            "data": ctx.masker.value(
                                {
                                    "action": "server_destructive",
                                    "category": rec.get("category"),
                                    "cmd": _cut(str(rec.get("cmd", ""))),
                                }
                            ),
                        },
                    )
            hook_seen = len(lines)

    def on_stdout(line: str) -> None:
        nonlocal capped, session_id
        drain_hook_log()
        s = line.strip()
        if not s:
            return
        try:
            obj = json.loads(s)
        except ValueError:
            ctx.sink.emit("stdout", {"text": stderr_masker.line(line)})
            return
        if not isinstance(obj, dict):
            return
        session_id = obj.get("session_id") or session_id
        meter.add(obj)
        if cap is not None and not capped and meter.total > cap:
            capped = True
            ctx.sink.emit(
                "session_event",
                {
                    "type": "state",
                    "at": _now(),
                    "summary_fa": "نشست Claude به سقف توکنش رسید و متوقف شد.",
                    "data": {"state": "failed", "token_cap": cap, "tokens": meter.total},
                },
            )
            stop.set()
        if obj.get("type") == "result":
            final.clear()
            final.update(obj)
        for item in session_events(obj, ctx.masker):
            if item["type"] == "file_change" and item["data"].get("path"):
                path = str(item["data"]["path"])
                if path not in files_changed:
                    files_changed.append(path)
            ctx.sink.emit("session_event", item)

    try:
        res = await run_streamed(
            argv,
            cwd=cwd,
            env=env,
            limit_s=timeout,
            cancel=stop,
            on_stdout=on_stdout,
            on_stderr=ctx.line_sink("stderr"),
            max_line=JSON_LINE_BYTES,
        )
        drain_hook_log()
    finally:
        relay.cancel()
        shutil.rmtree(tmp, ignore_errors=True)
    if final:
        usage: dict[str, Any] | None = usage_from_result(final)
    else:  # stopped (cap, cancel, timeout): what the messages counted so far
        usage = meter.usage(session_id) if meter.by_message else None
    exit_code = res.exit_code
    if capped and not ctx.cancel.is_set():
        exit_code = EXIT_TOKEN_CAP
    if final.get("is_error") and exit_code == 0:
        exit_code = 1
    whole = str(final.get("result") or "")
    cut = len(whole) > MAX_ANSWER_CHARS
    answer = ctx.masker.text(whole[:MAX_ANSWER_CHARS] if cut else whole)
    output = {
        "session_id": final.get("session_id"),
        "result_fa": answer,
        "answer_chars": len(whole),
        "answer_truncated": cut,
        "files_changed": files_changed,
        "num_turns": final.get("num_turns"),
        "stop_reason": final.get("stop_reason"),
    }
    if cap is not None:
        output["token_cap"] = cap
        output["token_cap_reached"] = capped
    if workspace is not None:
        output["workspace"] = {"ref": workspace, "path": cwd}
    sent_n = 0
    after_post = None
    timed_out = res.reason == "timeout"
    if (
        workspace is not None
        and (exit_code == 0 or timed_out)
        and not ctx.cancel.is_set()
        and not capped
    ):
        # ⟨0.3.2⟩ §43 the files the turn left in out/ go to the hub before the result names them
        # ⟨0.3.3⟩ also when the turn was stopped at its time limit: what it had made reaches the
        # owner as an unfinished output instead of staying on the server
        files, skipped, marks = await outbox.send(ctx, Path(cwd), str(workspace))
        if marks:
            after_post = functools.partial(
                workspace_state.mark_sent, str(workspace), marks, "", ctx.cfg_path
            )
        sent_n = len(files)
        if files:
            output["files"] = files
        if skipped:
            output["files_skipped"] = skipped[: outbox.MAX_FILES * 2]
    if capped and not ctx.cancel.is_set():
        summary = f"نشست Claude به سقف {cap} توکن رسید و متوقف شد."
    elif res.reason == "timeout":
        summary = "نشست Claude به سقف زمان رسید و متوقف شد."
    elif res.reason == "cancelled":
        summary = "نشست Claude لغو شد."
    elif exit_code == 0:
        summary = "نشست Claude روی سرور تمام شد."
    else:
        summary = f"نشست Claude با کد خروج {exit_code} تمام شد."
    if cut:
        summary += f" جواب {len(whole)} نویسه بود و فقط {MAX_ANSWER_CHARS} نویسه‌ی اول آن آمد."
    if sent_n:
        summary += f" {sent_n} فایل از out/ به ستاد رفت."
    return JobResult(exit_code, summary, usage=usage, output=output, after_post=after_post)
