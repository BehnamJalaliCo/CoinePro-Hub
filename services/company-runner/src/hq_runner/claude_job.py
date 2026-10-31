"""The `claude` job (contract §26.2, §26.3): the server's own Claude Code on a
brief, in the repository folder `args.cwd`, under that repository's CLAUDE.md.

    claude -p <brief> --output-format stream-json --verbose --settings <tmp>/settings.json
           [--resume <session_id>] [--model M] [--permission-mode P] [--max-turns N]

The temporary settings file adds one PreToolUse hook for Bash that runs
`hq-runner classify-hook`: it asks the hub to classify the command and blocks
the call (exit code 2) when the hub names a seal-required category, so the hub
raises the owner's seal card. The settings file and its folder exist only for
this run. Each stream-json line becomes a `session_event` event; usage comes
from the final result line and goes back with the result.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import hq_runner
from hq_runner.config import config_path
from hq_runner.jobs import JobContext, JobError, JobResult, _cwd, _timeout
from hq_runner.mask import Masker, StreamMasker
from hq_runner.proc import run_streamed

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


def hook_settings(job_id: str) -> dict[str, Any]:
    return {
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
    cwd = _cwd(args.get("cwd"))
    timeout = _timeout(args, CLAUDE_DEFAULT_TIMEOUT_S, CLAUDE_MAX_TIMEOUT_S)
    claude = find_claude(ctx.cfg.claude_bin)
    if not claude:
        raise JobError("Claude Code روی این سرور پیدا نشد.", 127)
    tmp = Path(tempfile.mkdtemp(prefix="hq-claude-"))
    os.chmod(tmp, 0o700)
    settings = tmp / "settings.json"
    hook_log = tmp / "hook-events.jsonl"
    settings.write_text(json.dumps(hook_settings(ctx.id)), encoding="utf-8")
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
    env = dict(ctx.env)
    env.update(
        {
            "HQ_RUNNER_CONFIG": str((ctx.cfg_path or config_path()).resolve()),
            "HQ_RUNNER_VIA": ctx.via,
            "HQ_RUNNER_HOOK_EVENTS": str(hook_log),
            "HQ_RUNNER_JOB_ID": ctx.id,
        }
    )
    final: dict[str, Any] = {}
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
            cancel=ctx.cancel,
            on_stdout=on_stdout,
            on_stderr=ctx.line_sink("stderr"),
            max_line=JSON_LINE_BYTES,
        )
        drain_hook_log()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    usage = usage_from_result(final) if final else None
    exit_code = res.exit_code
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
    if res.reason == "timeout":
        summary = "نشست Claude به سقف زمان رسید و متوقف شد."
    elif res.reason == "cancelled":
        summary = "نشست Claude لغو شد."
    elif exit_code == 0:
        summary = "نشست Claude روی سرور تمام شد."
    else:
        summary = f"نشست Claude با کد خروج {exit_code} تمام شد."
    if cut:
        summary += f" جواب {len(whole)} نویسه بود و فقط {MAX_ANSWER_CHARS} نویسه‌ی اول آن آمد."
    return JobResult(exit_code, summary, usage=usage, output=output)
